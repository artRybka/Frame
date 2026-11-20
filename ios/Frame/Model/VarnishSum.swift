import CoreGraphics
import Foundation
import simd
import UIKit

/// The varnish taken off the picture the full-screen viewer shows, on the
/// phone (Mateusz 2026-11-20: "korekta może dotyczyć tylko tego co widać a
/// nie pliku i będzie szybciej i prościej"). The numbers are the server's,
/// read on the picture without the varnish (`GET …/colours`,
/// `recovery.VarnishSum`); only the sum per pixel is written here, the same
/// as `recovery._without` and `unvarnished` there, in linear light:
///
///     clear = clip((lin - haze) / (1 - haze))
///     share = smoothstep(clip(luminance(clear) / dark))
///     out   = clip(clear * (even + (colour - even) * share) * scale)
///
/// Held to the server's by a picture both go through
/// (`VarnishSumTests`, `server/tests/test_cleaning.py`). The file the
/// frame shows stays the server's.
struct VarnishSum: Hashable, Sendable {
    var haze: Float
    var colour: SIMD3<Float>
    var even: Float
    var dark: Float
    var scale: Float
    var luma: SIMD3<Float>

    init(_ view: ColoursView) {
        haze = Float(view.haze)
        colour = Self.three(view.colour, or: 1)
        even = Float(view.even)
        dark = Float(max(view.dark, 1e-6))
        scale = Float(view.scale)
        luma = Self.three(view.luma, or: 0)
    }

    private static func three(_ values: [Double], or fallback: Float) -> SIMD3<Float> {
        guard values.count == 3 else { return SIMD3(repeating: fallback) }
        return SIMD3(Float(values[0]), Float(values[1]), Float(values[2]))
    }

    // MARK: sRGB, as the server's `color.py`

    static let linear: [Float] = (0 ..< 256).map { level in
        let c = Float(level) / 255
        return c <= 0.04045 ? c / 12.92 : powf((c + 0.055) / 1.055, 2.4)
    }

    /// Linear light to a level, in this many steps (the darkest step is a
    /// fifth of a level apart).
    static let steps = 16384
    static let levels: [UInt8] = (0 ... steps).map { step in
        let l = Float(step) / Float(steps)
        let s = l <= 0.0031308 ? l * 12.92 : 1.055 * powf(l, 1 / 2.4) - 0.055
        return UInt8(max(0, min(255, (s * 255).rounded())))
    }

    // MARK: The sum

    /// One pixel's red, green and blue levels without the varnish.
    func level(_ r: UInt8, _ g: UInt8, _ b: UInt8) -> (UInt8, UInt8, UInt8) {
        let lin = SIMD3(Self.linear[Int(r)], Self.linear[Int(g)], Self.linear[Int(b)])
        let clear = simd_clamp((lin - haze) / (1 - haze), SIMD3(repeating: 0), SIMD3(repeating: 1))
        let x = min(max((clear * luma).sum() / dark, 0), 1)
        let share = x * x * (3 - 2 * x)
        let out = simd_clamp(clear * (even + (colour - even) * share) * scale,
                             SIMD3(repeating: 0), SIMD3(repeating: 1))
        let at = out * Float(Self.steps) + 0.5
        return (Self.levels[Int(at.x)], Self.levels[Int(at.y)], Self.levels[Int(at.z)])
    }

    /// RGBA levels (`count` pixels, alpha left alone) without the varnish,
    /// in bands of rows on all the processor's cores.
    func apply(to pixels: UnsafeMutablePointer<UInt8>, count: Int) {
        let band = 1 << 16
        let bands = (count + band - 1) / band
        let base = UInt(bitPattern: pixels)
        DispatchQueue.concurrentPerform(iterations: bands) { index in
            guard let start = UnsafeMutablePointer<UInt8>(bitPattern: base) else { return }
            let end = min((index + 1) * band, count)
            for at in index * band ..< end {
                let p = start + at * 4
                (p[0], p[1], p[2]) = level(p[0], p[1], p[2])
            }
        }
    }

    /// `picture` without the varnish, as large as it is.
    func apply(to picture: UIImage) -> UIImage? {
        guard let source = picture.cgImage else { return nil }
        let width = source.width, height = source.height
        guard let space = CGColorSpace(name: CGColorSpace.sRGB),
              let context = CGContext(
                  data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: width * 4,
                  space: space, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
              ),
              let data = context.data
        else { return nil }
        context.draw(source, in: CGRect(x: 0, y: 0, width: width, height: height))
        apply(to: data.assumingMemoryBound(to: UInt8.self), count: width * height)
        guard let made = context.makeImage() else { return nil }
        return UIImage(cgImage: made, scale: picture.scale, orientation: picture.imageOrientation)
    }
}

/// What the full-screen viewer's colours button switches for the person
/// (`GET /api/library/items/{id}/colours`).
struct ColoursView: Codable, Hashable, Sendable {
    /// "varnish", "paper" or "none".
    var kind: String
    /// They see the work so now.
    var on: Bool = false
    var haze: Double = 0
    var colour: [Double] = [1, 1, 1]
    var even: Double = 1
    var dark: Double = 1
    var scale: Double = 1
    var luma: [Double] = [0.2126, 0.7152, 0.0722]
    /// For a sheet (`SheetSum`): its tone, `height` × `width` × 3 half
    /// floats in base64 (empty from a server before it), and a well-kept
    /// sheet's tone; `opaque` for pastel and gouache.
    var field: String = ""
    var width: Int = 0
    var height: Int = 0
    var fresh: [Double] = [1, 1, 1]
    var opaque: Bool = false

    init(kind: String, on: Bool = false, haze: Double = 0, colour: [Double] = [1, 1, 1], even: Double = 1,
         dark: Double = 1, scale: Double = 1) {
        self.kind = kind
        self.on = on
        self.haze = haze
        self.colour = colour
        self.even = even
        self.dark = dark
        self.scale = scale
    }

    /// A server before the sheet's numbers sends none of them.
    init(from decoder: any Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        kind = try c.decode(String.self, forKey: .kind)
        on = try c.decodeIfPresent(Bool.self, forKey: .on) ?? false
        haze = try c.decodeIfPresent(Double.self, forKey: .haze) ?? 0
        colour = try c.decodeIfPresent([Double].self, forKey: .colour) ?? [1, 1, 1]
        even = try c.decodeIfPresent(Double.self, forKey: .even) ?? 1
        dark = try c.decodeIfPresent(Double.self, forKey: .dark) ?? 1
        scale = try c.decodeIfPresent(Double.self, forKey: .scale) ?? 1
        luma = try c.decodeIfPresent([Double].self, forKey: .luma) ?? [0.2126, 0.7152, 0.0722]
        field = try c.decodeIfPresent(String.self, forKey: .field) ?? ""
        width = try c.decodeIfPresent(Int.self, forKey: .width) ?? 0
        height = try c.decodeIfPresent(Int.self, forKey: .height) ?? 0
        fresh = try c.decodeIfPresent([Double].self, forKey: .fresh) ?? [1, 1, 1]
        opaque = try c.decodeIfPresent(Bool.self, forKey: .opaque) ?? false
    }
}
