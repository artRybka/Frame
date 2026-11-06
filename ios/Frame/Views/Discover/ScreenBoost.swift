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
    /// Konfiguracja → Pełny ekran: the sun also lifts the picture's light
    /// parts above the screen's white (`HDRBoost`).
    static let hdrKey = "viewer.hdrBoost"
    /// With the HDR lift on: the sun leaves the screen's brightness alone
    /// and only lifts the picture.
    static let keepKey = "viewer.keepBrightness"

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

/// The artificial HDR "boost", fitted to each picture. A small histogram
/// of the picture's lightness (cube root of linear luminance, roughly how
/// light it looks) gives its middle (median) and its own white (99.5th
/// percentile). The lift starts halfway between them (`Plan.knee`), so a
/// dark picture lifts its relatively light parts (a face, a candle) and a
/// light one only its very top; it reaches full strength at the picture's
/// white (`Plan.top`). The strength (`Plan.gain`) is lower when much of the
/// picture would glow (a sky, a pale ground) and when the picture is light
/// overall, and nothing at all when its lights are hardly lighter than the
/// rest. Every pixel is multiplied by one factor of its luminance, so
/// hue and saturation stay and lights keep their gradation instead of the
/// channels clipping one by one. Drawn on the CPU in half floats, extended
/// linear sRGB, shown by a `UIImageView` allowed the high dynamic range.
/// Not how the original or the frame look: a choice in Konfiguracja.
enum HDRBoost {
    /// Never more than this much brighter than white.
    static let maxGain: Float = 3
    /// The longest side of the boosted copy: half floats take 8 bytes a
    /// pixel, a 4096 px original would take over 100 MB.
    static let maxSide = 3072
    static let bins = 512

    struct Plan: Equatable {
        /// Lightness (0…1) where the lift starts.
        var knee: Float
        /// Lightness at which the lift is full: the picture's own white.
        var top: Float
        /// How many times brighter than before the picture's white gets.
        var gain: Float
    }

    /// The lift for a lightness histogram (`bins` bins over 0…1), or nil
    /// when it would hardly show. `headroom`: what the screen can give.
    static func plan(histogram: [Int], headroom: Float) -> Plan? {
        let total = histogram.reduce(0, +)
        guard total > 0, histogram.count > 1 else { return nil }
        func percentile(_ p: Float) -> Float {
            let goal = Int((Float(total) * p).rounded(.up))
            var sum = 0
            for (bin, count) in histogram.enumerated() {
                sum += count
                if sum >= goal { return (Float(bin) + 0.5) / Float(histogram.count) }
            }
            return 1
        }
        func share(above lightness: Float) -> Float {
            let first = min(histogram.count, max(0, Int(lightness * Float(histogram.count))))
            return Float(histogram[first...].reduce(0, +)) / Float(total)
        }
        let middle = percentile(0.5)
        let top = max(percentile(0.995), 0.35)
        let knee = max(0.3, min(middle + 0.5 * (top - middle), 0.88, top - 0.08))
        guard top > knee else { return nil }
        // Glowing specks look like light; a glowing half of the picture
        // glares and wipes out its gradation.
        let lit = share(above: (knee + top) / 2)
        let area = max(0.3, min(1, 1 - (lit - 0.04) / 0.36))
        // A light picture as a whole needs less to look lit.
        let key = max(0.5, min(1, 1.25 - middle))
        // Lights hardly lighter than the rest are no lights: an even
        // picture would only get brighter all over.
        let spread = max(0, min(1, (top - middle - 0.05) / 0.2))
        let most = min(maxGain, headroom * 0.9)
        let gain = 1 + (most - 1) * area * key * spread
        guard gain > 1.08 else { return nil }
        return Plan(knee: knee, top: top, gain: gain)
    }

    /// The factor for each of `steps` linear luminances over 0…1.
    static func factors(_ plan: Plan, steps: Int = 4096) -> [Float] {
        (0..<steps).map { step in
            let lightness = cbrt(Float(step) / Float(steps - 1))
            let t = max(0, min(1, (lightness - plan.knee) / (plan.top - plan.knee)))
            return 1 + (plan.gain - 1) * t * t * (3 - 2 * t)
        }
    }

    /// Linear light of the 256 sRGB codes.
    static let linear: [Float] = (0..<256).map { code in
        let c = Float(code) / 255
        return c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
    }

    static func render(_ image: UIImage, headroom: CGFloat) async -> UIImage? {
        guard headroom > 1.05, let cg = image.cgImage else { return nil }
        let scale = image.scale
        let orientation = image.imageOrientation
        let room = Float(headroom)
        let out = await Task.detached(priority: .userInitiated) { boost(cg, headroom: room) }.value
        return out.map { UIImage(cgImage: $0, scale: scale, orientation: orientation) }
    }

    private static func boost(_ source: CGImage, headroom: Float) -> CGImage? {
        let longest = max(source.width, source.height)
        let shrink = longest > maxSide ? Double(maxSide) / Double(longest) : 1
        let width = max(1, Int((Double(source.width) * shrink).rounded()))
        let height = max(1, Int((Double(source.height) * shrink).rounded()))
        guard let srgb = CGColorSpace(name: CGColorSpace.sRGB),
              let wide = CGColorSpace(name: CGColorSpace.extendedLinearSRGB),
              let context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8,
                                      bytesPerRow: width * 4, space: srgb,
                                      bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue),
              let data = context.data
        else { return nil }
        context.interpolationQuality = .high
        context.draw(source, in: CGRect(x: 0, y: 0, width: width, height: height))
        let count = width * height
        let pixels = data.bindMemory(to: UInt8.self, capacity: count * 4)
        let linear = Self.linear

        // About 200 000 samples are plenty for the histogram.
        var histogram = [Int](repeating: 0, count: bins)
        let stride = max(1, count / 200_000)
        var index = 0
        while index < count {
            let p = index * 4
            let y = 0.2126 * linear[Int(pixels[p])] + 0.7152 * linear[Int(pixels[p + 1])]
                + 0.0722 * linear[Int(pixels[p + 2])]
            histogram[min(bins - 1, Int(cbrt(y) * Float(bins)))] += 1
            index += stride
        }
        guard let plan = Self.plan(histogram: histogram, headroom: headroom) else { return nil }
        let factors = Self.factors(plan)
        let last = Float(factors.count - 1)

        // Handed to the image without a copy and freed with it.
        let output = UnsafeMutablePointer<Float16>.allocate(capacity: count * 4)
        for i in 0..<count {
            let p = i * 4
            let r = linear[Int(pixels[p])]
            let g = linear[Int(pixels[p + 1])]
            let b = linear[Int(pixels[p + 2])]
            let m = factors[Int((0.2126 * r + 0.7152 * g + 0.0722 * b) * last)]
            output[p] = Float16(r * m)
            output[p + 1] = Float16(g * m)
            output[p + 2] = Float16(b * m)
            output[p + 3] = 1
        }
        guard let provider = CGDataProvider(dataInfo: nil, data: output, size: count * 8,
                                            releaseData: { _, data, _ in data.deallocate() })
        else {
            output.deallocate()
            return nil
        }
        return CGImage(width: width, height: height, bitsPerComponent: 16, bitsPerPixel: 64,
                       bytesPerRow: width * 8, space: wide,
                       bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue
                           | CGBitmapInfo.floatComponents.rawValue | CGBitmapInfo.byteOrder16Little.rawValue),
                       provider: provider, decode: nil, shouldInterpolate: true, intent: .defaultIntent)
    }
}
