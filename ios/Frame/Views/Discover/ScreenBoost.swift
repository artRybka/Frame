import CoreImage
import CoreImage.CIFilterBuiltins
import UIKit

/// Raises the screen to full brightness while a picture is looked at and
/// gives the owner's own brightness back afterwards. iOS itself puts the
/// owner's brightness back when the app leaves the foreground, so a boost
/// that outlives that is raised again on return.
@MainActor
final class ScreenBoost {
    static let shared = ScreenBoost()
    /// Remembered by the full-screen viewer's sun button.
    static let key = "viewer.brighten"

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
/// the page around it: the whole picture, evenly (an exposure lift in
/// linear light, the gain set in Konfiguracja), drawn as an extended-range copy that the
/// screen shows above its usual white where it has the headroom (EDR). No
/// part of the picture is lifted more than another, so it looks like the
/// same picture in more light. Konfiguracja → Wyświetlanie dzieł, on by
/// default; nothing changes on screens without headroom or in Low Power
/// Mode.
enum ArtGlow {
    static let key = "art.glow"
    /// How many times brighter, set in Konfiguracja (`gains`).
    static let gainKey = "art.glowGain"
    /// About two thirds of a stop.
    static let defaultGain: Double = 1.6
    static let gains: ClosedRange<Double> = 1.1...3

    /// "1,6×", as Polish writes it.
    static func label(_ gain: Double) -> String {
        gain.formatted(.number.precision(.fractionLength(1)).locale(Locale(identifier: "pl_PL"))) + "×"
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

    /// The way in, on entering the work's card or the study: the picture as
    /// it is, then its light parts brighter, then all of it, in about
    /// a second (Mateusz 2026-11-07). Seconds from the picture's view
    /// appearing.
    enum WayIn {
        static let light: ClosedRange<Double> = 0.15...0.55
        static let whole: ClosedRange<Double> = 0.55...1.0

        /// How far a copy is shown `t` seconds in (0 to 1), easing in and out.
        static func shown(_ span: ClosedRange<Double>, at t: Double) -> Double {
            let x = min(max((t - span.lowerBound) / (span.upperBound - span.lowerBound), 0), 1)
            return x * x * (3 - 2 * x)
        }
    }

    /// Where the light parts begin and end, in linear luminance: a mid grey
    /// gets nothing, a light tone (lightness about 0.84) all of the gain.
    static let lightFrom = 0.18
    static let lightTo = 0.6
    /// How soft the edge of the light parts is, of the shorter side: whole
    /// regions light up, not specks.
    static let lightSoftness = 0.012

    static func image(_ image: UIImage, gain: Double) async -> UIImage? {
        await copies(image, gain: gain, lightParts: false)?.whole
    }

    /// The brighter copy (from the cache when made before) and, for the way
    /// in, the one with only its light parts brighter, made together.
    static func copies(_ image: UIImage, gain asked: Double, lightParts: Bool) async
        -> (whole: UIImage, light: UIImage?)? {
        let done = cached(image, gain: asked)
        if let done, !lightParts { return (done, nil) }
        let headroom = await ScreenBoost.shared.headroom
        let gain = min(CGFloat(asked), headroom * 0.9)
        guard gain > 1.05, let cg = image.cgImage else { return nil }
        let scale = image.scale
        let orientation = image.imageOrientation
        let needsWhole = done == nil
        let made = await Task.detached(priority: .userInitiated) { () -> (CGImage?, CGImage?) in
            (needsWhole ? render(cg, gain: gain) : nil, lightParts ? renderLight(cg, gain: gain) : nil)
        }.value
        let whole: UIImage
        if let done {
            whole = done
        } else {
            guard let out = made.0 else { return nil }
            whole = UIImage(cgImage: out, scale: scale, orientation: orientation)
            cache.setObject(Lit(whole, gain: asked), forKey: image, cost: out.bytesPerRow * out.height)
        }
        return (whole, made.1.map { UIImage(cgImage: $0, scale: scale, orientation: orientation) })
    }

    /// Only the light parts brighter: the lifted picture over the picture
    /// itself through a soft mask of how light each region is.
    static func renderLight(_ source: CGImage, gain: CGFloat) -> CGImage? {
        let picture = CIImage(cgImage: source)
        let lifted = picture.applyingFilter("CIExposureAdjust", parameters: [kCIInputEVKey: log2(gain)])
        let scale = 1 / (lightTo - lightFrom)
        let weights = CIVector(x: 0.2126 * scale, y: 0.7152 * scale, z: 0.0722 * scale, w: 0)
        let bias = -lightFrom * scale
        let ramp = picture
            .applyingFilter("CIColorMatrix", parameters: [
                "inputRVector": weights, "inputGVector": weights, "inputBVector": weights,
                "inputAVector": CIVector(x: 0, y: 0, z: 0, w: 1),
                "inputBiasVector": CIVector(x: bias, y: bias, z: bias, w: 0),
            ])
            .applyingFilter("CIColorClamp", parameters: [
                "inputMinComponents": CIVector(x: 0, y: 0, z: 0, w: 0),
                "inputMaxComponents": CIVector(x: 1, y: 1, z: 1, w: 1),
            ])
        let sigma = Double(min(source.width, source.height)) * lightSoftness
        let mask = sigma < 0.5 ? ramp
            : ramp.clampedToExtent().applyingGaussianBlur(sigma: sigma).cropped(to: picture.extent)
        let output = lifted.applyingFilter("CIBlendWithMask", parameters: [
            kCIInputBackgroundImageKey: picture, kCIInputMaskImageKey: mask,
        ])
        guard let space = CGColorSpace(name: CGColorSpace.extendedLinearSRGB) else { return nil }
        return context.createCGImage(output, from: picture.extent, format: .RGBAh, colorSpace: space)
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
}
