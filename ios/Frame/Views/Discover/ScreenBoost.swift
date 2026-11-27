import CoreImage
import CoreImage.CIFilterBuiltins
import UIKit

/// Raises the screen to full brightness while a picture is looked at (the
/// full-screen viewer, with "Jaśniejsze dzieła" on, `ArtGlow.key`) and
/// gives the owner's own brightness back afterwards. iOS itself puts the
/// owner's brightness back when the app leaves the foreground, so a boost
/// that outlives that is raised again on return.
@MainActor
final class ScreenBoost {
    static let shared = ScreenBoost()

    private var boosted = false
    /// The owner's brightness, kept until the glide back to it ends (a
    /// boost again halfway back must not take the halfway value for it).
    private var own: CGFloat?
    private var ramp: Task<Void, Never>?

    private var screen: UIScreen? {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        return (scenes.first { $0.activationState == .foregroundActive } ?? scenes.first)?.screen
    }

    /// How many times brighter than its white this screen can light HDR
    /// content at best (1 when it cannot: no EDR, Low Power Mode).
    var headroom: CGFloat { screen?.potentialEDRHeadroom ?? 1 }

    func raise() {
        guard !boosted, let screen else { return }
        boosted = true
        if own == nil { own = screen.brightness }
        glide(to: 1)
    }

    func restore() {
        guard boosted, let back = own else { return }
        boosted = false
        glide(to: back) { [weak self] in
            if self?.boosted == false { self?.own = nil }
        }
    }

    /// The app went to the background: iOS restores the brightness itself.
    func forget() {
        ramp?.cancel()
        ramp = nil
        boosted = false
        own = nil
    }

    /// A gentle change over about a third of a second instead of a jump.
    private func glide(to target: CGFloat, then done: @escaping @MainActor () -> Void = {}) {
        ramp?.cancel()
        guard let screen else { return }
        let start = screen.brightness
        ramp = Task { @MainActor [weak self] in
            let steps = 20
            for step in 1...steps {
                try? await Task.sleep(for: .milliseconds(16))
                if Task.isCancelled { return }
                let t = CGFloat(step) / CGFloat(steps)
                screen.brightness = start + (target - start) * (t * t * (3 - 2 * t))
            }
            self?.ramp = nil
            done()
        }
    }
}

/// The artwork on the work's card and in the study a little brighter than
/// the page around it: an exposure lift in linear light (the gain set in
/// Konfiguracja, 2× by default), drawn as an extended-range copy that the
/// screen shows above its usual white where it has the headroom (EDR). A
/// bright picture is lifted less and its lights eased under 1.25× the
/// page's white (`Lights`), so white paper does not glow like a lightbox.
/// Konfiguracja → Wyświetlanie dzieł, on by default; nothing changes on
/// screens without headroom or in Low Power Mode.
enum ArtGlow {
    static let key = "art.glow"
    /// How many times brighter, set in Konfiguracja (`gains`).
    static let gainKey = "art.glowGain"
    /// About two thirds of a stop.
    static let defaultGain: Double = 2
    static let gains: ClosedRange<Double> = 1.1...3

    /// "1,6×", as Polish writes it.
    static func label(_ gain: Double) -> String {
        gain.formatted(.number.precision(.fractionLength(1)).locale(Locale(identifier: "pl_PL"))) + "×"
    }

    /// How the lights of a bright picture are kept from glowing like a
    /// lightbox over the page (Mateusz 2026-11-27: "gdy dzieło jest
    /// kontrastowe, ma sporo bardzo jasnych płaszczyzn to są one mocno
    /// prześwietlone"; of the trial's A, B and C he kept C, 18:59 UTC): the
    /// gain lowered so that no more than `share` of the picture is brighter
    /// than the page's white, and the lights eased from `knee` into at most
    /// `ceiling` times the page's white.
    enum Lights {
        static let share = 0.15
        static let knee = 0.9
        static let ceiling = 1.25
    }

    /// A brighter copy and the gain it was asked with.
    private final class Lit {
        let image: UIImage
        let gain: Double
        init(_ image: UIImage, gain: Double) {
            self.image = image
            self.gain = gain
        }
    }

    private static let cache: NSCache<UIImage, Lit> = {
        let cache = NSCache<UIImage, Lit>()
        cache.totalCostLimit = 160 * 1024 * 1024
        return cache
    }()
    private static let context = CIContext(options: [.cacheIntermediates: false])

    /// The brighter copy made before at this gain, if any.
    static func cached(_ image: UIImage, gain: Double) -> UIImage? {
        guard let lit = cache.object(forKey: image), abs(lit.gain - gain) < 0.001 else { return nil }
        return lit.image
    }

    /// The way in, on entering the work's card or the study: the picture
    /// as it is at first, then brighter evenly up to the gain set, in about
    /// a second (Mateusz 2026-11-07). Seconds from the picture's view
    /// appearing.
    enum WayIn {
        static let span: ClosedRange<Double> = 0.15...1.0

        /// How far the brighter copy is shown `t` seconds in (0 to 1),
        /// easing in and out.
        static func shown(at t: Double) -> Double {
            let x = min(max((t - span.lowerBound) / (span.upperBound - span.lowerBound), 0), 1)
            return x * x * (3 - 2 * x)
        }
    }

    static func image(_ image: UIImage, gain asked: Double) async -> UIImage? {
        if let done = cached(image, gain: asked) { return done }
        let headroom = await ScreenBoost.shared.headroom
        let gain = min(CGFloat(asked), headroom * 0.9)
        guard gain > 1.05, let cg = image.cgImage else { return nil }
        let scale = image.scale
        let orientation = image.imageOrientation
        guard let out = await Task.detached(priority: .userInitiated, operation: { lit(cg, gain: gain) }).value
        else { return nil }
        let result = UIImage(cgImage: out, scale: scale, orientation: orientation)
        cache.setObject(Lit(result, gain: asked), forKey: image, cost: out.bytesPerRow * out.height)
        return result
    }

    static func render(_ source: CGImage, gain: CGFloat) -> CGImage? {
        let filter = CIFilter.exposureAdjust()
        filter.inputImage = CIImage(cgImage: source)
        filter.ev = Float(log2(gain))
        guard let output = filter.outputImage,
              let space = CGColorSpace(name: CGColorSpace.extendedLinearSRGB)
        else { return nil }
        return context.createCGImage(output, from: output.extent, format: .RGBAh, colorSpace: space)
    }

    /// The gain for a picture whose lightness (linear, 0 to 1) is
    /// `lightness`: as asked, but no more than leaves `share` of it brighter
    /// than the page's white, and never below 1.
    static func fitted(_ asked: Double, lightness: [Float], share: Double) -> Double {
        guard !lightness.isEmpty else { return asked }
        let bins = 1024
        var counts = [Int](repeating: 0, count: bins)
        for value in lightness {
            counts[min(max(Int(value * Float(bins)), 0), bins - 1)] += 1
        }
        let over = Int((Double(lightness.count) * share).rounded(.down))
        var seen = 0
        var bin = bins - 1
        while bin > 0 {
            seen += counts[bin]
            if seen > over { break }
            bin -= 1
        }
        let top = Double(bin + 1) / Double(bins)
        return min(asked, max(1, 1 / top))
    }

    /// The shoulder of the lights: `u` (in the page's white) as it is up to
    /// the knee, then easing towards the ceiling, never past it.
    static func eased(_ u: Double, knee: Double, ceiling: Double) -> Double {
        guard u > knee, ceiling > knee else { return min(u, max(ceiling, knee)) }
        let room = ceiling - knee
        return knee + room * (1 - exp(-(u - knee) / room))
    }

    /// The brighter copy of an artwork, its lights kept down (`Lights`):
    /// brightness changed by the strongest of the three colours, so a
    /// colour keeps its hue and its saturation. `gain` is at most what the
    /// screen can show, and so is the ceiling of the lights.
    static func lit(_ source: CGImage, gain asked: CGFloat) -> CGImage? {
        let width = source.width, height = source.height
        guard width > 0, height > 0,
              let linear = CGColorSpace(name: CGColorSpace.extendedLinearSRGB),
              let bitmap = CGContext(
                  data: nil, width: width, height: height, bitsPerComponent: 32, bytesPerRow: width * 16,
                  space: linear,
                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
                      | CGBitmapInfo.floatComponents.rawValue | CGBitmapInfo.byteOrder32Little.rawValue
              ),
              let data = bitmap.data
        else { return nil }
        bitmap.draw(source, in: CGRect(x: 0, y: 0, width: width, height: height))
        let count = width * height
        let pixels = data.bindMemory(to: Float.self, capacity: count * 4)
        var gain = Double(asked)
        do {
            let step = max(1, count / 250_000)
            var lightness: [Float] = []
            lightness.reserveCapacity(count / step + 1)
            var i = 0
            while i < count {
                let p = i * 4
                lightness.append(0.2126 * pixels[p] + 0.7152 * pixels[p + 1] + 0.0722 * pixels[p + 2])
                i += step
            }
            gain = fitted(gain, lightness: lightness, share: Lights.share)
        }
        let ceiling = min(Lights.ceiling, Double(asked))
        let knee = min(Lights.knee, ceiling)
        for i in 0..<count {
            let p = i * 4
            let strongest = Double(max(pixels[p], pixels[p + 1], pixels[p + 2]))
            var factor = gain
            if strongest > 0 {
                // Never darker than the picture itself.
                factor = max(1, eased(strongest * gain, knee: knee, ceiling: ceiling) / strongest)
            }
            let f = Float(factor)
            pixels[p] *= f
            pixels[p + 1] *= f
            pixels[p + 2] *= f
        }
        guard let lifted = bitmap.makeImage() else { return nil }
        let image = CIImage(cgImage: lifted)
        return context.createCGImage(image, from: image.extent, format: .RGBAh, colorSpace: linear)
    }
}
