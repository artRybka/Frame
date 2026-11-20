import CoreGraphics
import Foundation
import simd
import UIKit

/// The yellow taken off the sheet the full-screen viewer shows, on the
/// phone (Mateusz 2026-11-20: "A może warto jednak się pokłonić nad
/// papierem?"), as `VarnishSum` takes a varnish off. The server reads the
/// sheet's tone small (`GET …/colours`, `recovery.SheetSum`: a field of
/// some 192 px and a well-kept sheet's tone); only the sum is written
/// here, the same as `recovery.sheet_applied` there. Made small from the
/// field: its luminance, its OKLab a and b and the gain `fresh / field`,
/// carried to the picture's size as OpenCV's cubic resize does; per pixel,
/// in linear light:
///
///     lighter = clip((y - sheetY) / max(0.12 sheetY, 1e-3))
///     whiter  = clip((sheetB - b) / 0.012)
///     weight  = (1 - lighter * whiter) * smoothstep(clip((y / sheetY - 0.06) / 0.24))
///               (pastel and gouache: * exp(-½ (|ab - sheetAB| / 0.03)²))
///     out     = clip(lin * (1 + weight * (gain - 1)))
///
/// Held to the server's by a picture both go through (`SheetSumTests`,
/// `server/tests/test_cleaning.py`).
struct SheetSum: Sendable {
    /// The field's size.
    let width: Int
    let height: Int
    /// A cell's sheet luminance, OKLab a and b, and the gain of red, green
    /// and blue (the last two lanes unused).
    let cells: [SIMD8<Float>]
    let opaque: Bool

    static let luma = SIMD3<Float>(0.2126, 0.7152, 0.0722)
    // OKLab, as the server's `color.py`.
    static let m1 = simd_float3x3(rows: [
        SIMD3(0.4122214708, 0.5363325363, 0.0514459929),
        SIMD3(0.2119034982, 0.6806995451, 0.1073969566),
        SIMD3(0.0883024619, 0.2817188376, 0.6299787005),
    ])
    static let m2a = SIMD3<Float>(1.9779984951, -2.4285922050, 0.4505937099)
    static let m2b = SIMD3<Float>(0.0259040371, 0.7827717662, -0.8086757660)

    init?(_ view: ColoursView) {
        guard view.kind == "paper", view.width > 0, view.height > 0, view.fresh.count == 3,
              let data = Data(base64Encoded: view.field), data.count == view.width * view.height * 3 * 2
        else { return nil }
        let field: [Float] = data.withUnsafeBytes { raw in
            (0 ..< data.count / 2).map { at in
                Self.half(UInt16(raw[2 * at]) | UInt16(raw[2 * at + 1]) << 8)
            }
        }
        self.init(field: field, width: view.width, height: view.height,
                  fresh: SIMD3(Float(view.fresh[0]), Float(view.fresh[1]), Float(view.fresh[2])),
                  opaque: view.opaque)
    }

    /// `field`: linear RGB, row by row, `width` × `height` × 3.
    init(field: [Float], width: Int, height: Int, fresh: SIMD3<Float>, opaque: Bool) {
        self.width = width
        self.height = height
        self.opaque = opaque
        var cells = [SIMD8<Float>](repeating: .zero, count: width * height)
        for at in 0 ..< width * height {
            let tone = SIMD3(field[3 * at], field[3 * at + 1], field[3 * at + 2])
            let (a, b) = Self.ab(tone)
            let gain = fresh / simd_max(tone, SIMD3(repeating: 1e-3))
            cells[at] = SIMD8((tone * Self.luma).sum(), a, b, gain.x, gain.y, gain.z, 0, 0)
        }
        self.cells = cells
    }

    /// OKLab a and b of linear RGB.
    static func ab(_ lin: SIMD3<Float>) -> (Float, Float) {
        let lms = m1 * lin
        let c = SIMD3(cbrtf(lms.x), cbrtf(lms.y), cbrtf(lms.z))
        return ((c * m2a).sum(), (c * m2b).sum())
    }

    /// A half float's value.
    static func half(_ bits: UInt16) -> Float {
        let sign: Float = bits & 0x8000 != 0 ? -1 : 1
        let exponent = Int((bits >> 10) & 0x1F)
        let fraction = Float(bits & 0x3FF)
        switch exponent {
        case 0: return sign * fraction * powf(2, -24)
        case 31: return fraction == 0 ? sign * .infinity : .nan
        default: return sign * (1 + fraction / 1024) * powf(2, Float(exponent - 15))
        }
    }

    // MARK: OpenCV's cubic resize (A = -0.75, edges repeated)

    struct Taps {
        var index: SIMD4<Int32>
        var weight: SIMD4<Float>
    }

    static func taps(from source: Int, to size: Int) -> [Taps] {
        let scale = Double(source) / Double(size)
        return (0 ..< size).map { at in
            let f = (Double(at) + 0.5) * scale - 0.5
            let i = Int(f.rounded(.down))
            let t = Float(f - Double(i))
            let a: Float = -0.75
            func near(_ x: Float) -> Float { ((a + 2) * x - (a + 3)) * x * x + 1 }
            func far(_ x: Float) -> Float { ((a * x - 5 * a) * x + 8 * a) * x - 4 * a }
            let weight = SIMD4(far(t + 1), near(t), near(1 - t), far(2 - t))
            let index = SIMD4<Int32>((0 ..< 4).map { Int32(min(max(i + $0 - 1, 0), source - 1)) })
            return Taps(index: index, weight: weight)
        }
    }

    // MARK: The sum

    /// RGBA levels (`width` × `height` pixels, alpha left alone) with the
    /// sheet de-yellowed, in bands of rows on all the processor's cores.
    func apply(to pixels: UnsafeMutablePointer<UInt8>, width pictureWidth: Int, height pictureHeight: Int) {
        let across = Self.taps(from: width, to: pictureWidth)
        let down = Self.taps(from: height, to: pictureHeight)
        let band = 32
        let bands = (pictureHeight + band - 1) / band
        let base = UInt(bitPattern: pixels)
        let linear = VarnishSum.linear, levels = VarnishSum.levels, steps = Float(VarnishSum.steps)
        DispatchQueue.concurrentPerform(iterations: bands) { index in
            guard let start = UnsafeMutablePointer<UInt8>(bitPattern: base) else { return }
            var row = [SIMD8<Float>](repeating: .zero, count: width)
            for y in index * band ..< min((index + 1) * band, pictureHeight) {
                // The field's row at this height (down first: the same sum
                // as OpenCV's across first, to a rounding).
                let v = down[y]
                for at in 0 ..< width {
                    var sum = SIMD8<Float>.zero
                    for k in 0 ..< 4 {
                        sum += v.weight[k] * cells[Int(v.index[k]) * width + at]
                    }
                    row[at] = sum
                }
                for x in 0 ..< pictureWidth {
                    let h = across[x]
                    var cell = SIMD8<Float>.zero
                    for k in 0 ..< 4 {
                        cell += h.weight[k] * row[Int(h.index[k])]
                    }
                    let p = start + (y * pictureWidth + x) * 4
                    let lin = SIMD3(linear[Int(p[0])], linear[Int(p[1])], linear[Int(p[2])])
                    let gain = SIMD3(cell[3], cell[4], cell[5])
                    let weight = self.weight(lin, sheetY: cell[0], sheetA: cell[1], sheetB: cell[2])
                    let out = simd_clamp(lin * (1 + weight * (gain - 1)), SIMD3(repeating: 0), SIMD3(repeating: 1))
                    let level = out * steps + 0.5
                    p[0] = levels[Int(level.x)]
                    p[1] = levels[Int(level.y)]
                    p[2] = levels[Int(level.z)]
                }
            }
        }
    }

    /// How much of the sheet's loss a pixel takes back.
    func weight(_ lin: SIMD3<Float>, sheetY: Float, sheetA: Float, sheetB: Float) -> Float {
        let y = (lin * Self.luma).sum()
        let (a, b) = Self.ab(lin)
        // Lighter than the sheet and less yellow: white chalk, body colour.
        let lighter = min(max((y - sheetY) / max(0.12 * sheetY, 1e-3), 0), 1)
        let whiter = min(max((sheetB - b) / 0.012, 0), 1)
        var weight = 1 - lighter * whiter
        // Nearly black: thick ink, a border, the table under the sheet.
        let t = min(max((y / max(sheetY, 1e-3) - 0.06) / 0.24, 0), 1)
        weight *= t * t * (3 - 2 * t)
        if opaque {
            let away = ((a - sheetA) * (a - sheetA) + (b - sheetB) * (b - sheetB)).squareRoot()
            weight *= expf(-0.5 * (away / 0.03) * (away / 0.03))
        }
        return weight
    }

    /// `picture` with its sheet de-yellowed, as large as it is.
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
        apply(to: data.assumingMemoryBound(to: UInt8.self), width: width, height: height)
        guard let made = context.makeImage() else { return nil }
        return UIImage(cgImage: made, scale: picture.scale, orientation: picture.imageOrientation)
    }
}
