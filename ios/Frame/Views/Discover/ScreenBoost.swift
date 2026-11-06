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
    /// Konfiguracja → Pełny ekran: the sun also lifts the picture's light
    /// parts above the screen's white (`HDRBoost`).
    static let hdrKey = "viewer.hdrBoost"
    /// With the HDR lift on: the sun leaves the screen's brightness alone
    /// and only lifts the picture.
    static let keepKey = "viewer.keepBrightness"
    /// How many times brighter than white the picture's white goes
    /// (`HDRBoost.strengths`), set in Konfiguracja or by holding the sun.
    static let strengthKey = "viewer.hdrStrength"

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

/// The artificial HDR "boost": an SDR picture redrawn in extended linear
/// light so that its light parts go above the screen's white, up to the
/// screen's headroom, while darks and middle tones stay where they were
/// (x + (gain − 1)·x³ per channel in linear light: white → gain, 50 % grey
/// in sRGB → +2 % of the gain). Shown by a `UIImageView` allowed the high
/// dynamic range. Not how the original or the frame look: a choice in
/// Konfiguracja, off by default.
enum HDRBoost {
    /// The strength's range and its default (about one and a half stops);
    /// above the screen's headroom iOS clips anyway.
    static let strengths: ClosedRange<Double> = 1.3...4
    static let defaultStrength: Double = 2.8
    /// The longest side of the boosted copy: half floats take 8 bytes a
    /// pixel, a 4096 px original would take over 100 MB.
    static let maxSide: CGFloat = 3072

    /// "2,8×", as Polish writes it.
    static func label(_ strength: Double) -> String {
        strength.formatted(.number.precision(.fractionLength(1)).locale(Locale(identifier: "pl_PL"))) + "×"
    }

    static func render(_ image: UIImage, strength: Double, headroom: CGFloat) async -> UIImage? {
        let gain = min(CGFloat(strengths.clamped(strength)), headroom)
        guard gain > 1.05, let cg = image.cgImage else { return nil }
        let scale = image.scale
        let orientation = image.imageOrientation
        let out = await Task.detached(priority: .userInitiated) { boost(cg, gain: gain) }.value
        return out.map { UIImage(cgImage: $0, scale: scale, orientation: orientation) }
    }

    private static let context = CIContext(options: [.cacheIntermediates: false])

    private static func boost(_ cg: CGImage, gain: CGFloat) -> CGImage? {
        var input = CIImage(cgImage: cg)
        let longest = max(input.extent.width, input.extent.height)
        if longest > maxSide {
            let s = maxSide / longest
            input = input.transformed(by: CGAffineTransform(scaleX: s, y: s), highQualityDownsample: true)
        }
        let lift = CIVector(x: 0, y: 1, z: 0, w: gain - 1)
        let filter = CIFilter.colorPolynomial()
        filter.inputImage = input
        filter.redCoefficients = lift
        filter.greenCoefficients = lift
        filter.blueCoefficients = lift
        filter.alphaCoefficients = CIVector(x: 0, y: 1, z: 0, w: 0)
        guard let output = filter.outputImage,
              let space = CGColorSpace(name: CGColorSpace.extendedLinearDisplayP3)
        else { return nil }
        return context.createCGImage(output, from: output.extent.integral, format: .RGBAh, colorSpace: space)
    }
}

extension ClosedRange where Bound == Double {
    func clamped(_ value: Double) -> Double { Swift.min(upperBound, Swift.max(lowerBound, value)) }
}
