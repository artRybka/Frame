import FrameScan
import XCTest
@testable import Frame

/// Our restorer on the phone (`PhoneRestorer`; Mateusz 2026-11-27:
/// „Wszystko.”): the core takes a printed screen out of a picture before the
/// model draws it, and brings the drawing to 2K in the picture's colours
/// after, as the server's `imaging/descreen.py` and `restorer.recoloured`
/// do (checked number by number by `core/scan/tools/restore.py`; the
/// numbers below are the server's, held by `server/tests/test_scan_core.py`).
final class PhoneRestorerTests: XCTestCase {
    /// What `descreen.screen` finds in the made-up print: its points.
    static let screenPoints = 16

    /// A made-up print, 400 × 320: a light gradient seen through a dot
    /// screen of 4.5 px (`where (cos(2π x / 4.5) + cos(2π y / 4.5)) > 0`).
    static func print() -> MuseumCrop.Pixels {
        let rows = 320, columns = 400
        var rgb = [UInt8](repeating: 0, count: rows * columns * 3)
        for y in 0 ..< rows {
            for x in 0 ..< columns {
                let base = 40 + (x * 100) / columns + (y * 30) / rows
                let ink = cos(2 * Double.pi * Double(x) / 4.5) + cos(2 * Double.pi * Double(y) / 4.5) > 0
                let v = ink ? base : base + 70
                rgb[(y * columns + x) * 3] = UInt8(v)
                rgb[(y * columns + x) * 3 + 1] = UInt8(v)
                rgb[(y * columns + x) * 3 + 2] = UInt8(Double(v) * 0.8)
            }
        }
        return MuseumCrop.Pixels(rows: rows, columns: columns, rgb: rgb)
    }

    func testTheScreenIsTakenOutAndTheDrawingTakesThePicturesColours() {
        var photo = Self.print()
        let before = photo.rgb
        var error = [CChar](repeating: 0, count: 512)
        var found: Int32 = 0
        let rows = Int32(photo.rows), columns = Int32(photo.columns)
        let cleared = photo.rgb.withUnsafeMutableBufferPointer {
            frame_restore_descreen($0.baseAddress, rows, columns, &found, &error, Int32(error.count))
        }
        XCTAssertEqual(cleared, 0)
        XCTAssertEqual(Int(found), Self.screenPoints)
        // The dots are gone: what was 70 levels apart is near its mean.
        let changed = zip(before, photo.rgb).map { abs(Int($0) - Int($1)) }.reduce(0, +)
        XCTAssertGreaterThan(Double(changed) / Double(before.count), 25)

        // "The model's drawing": the picture four times larger, plainly.
        let scale = PhoneRestorer.scale
        var big = [UInt8](repeating: 0, count: photo.rows * scale * photo.columns * scale * 3)
        for y in 0 ..< photo.rows * scale {
            for x in 0 ..< photo.columns * scale {
                for c in 0 ..< 3 {
                    big[(y * photo.columns * scale + x) * 3 + c] = photo.rgb[((y / scale) * photo.columns + x / scale) * 3 + c]
                }
            }
        }
        var into = [UInt8](repeating: 0, count: PhoneRestorer.longest * PhoneRestorer.longest * 3)
        var height: Int32 = 0, width: Int32 = 0, laid: Int32 = 0
        let coloured = photo.rgb.withUnsafeBufferPointer { rgb in
            big.withUnsafeBufferPointer { big in
                into.withUnsafeMutableBufferPointer { into in
                    frame_restore_colours(
                        rgb.baseAddress, rows, columns, big.baseAddress, rows * Int32(scale), columns * Int32(scale),
                        PhoneRestorer.drawn, into.baseAddress, &height, &width, &laid, &error, Int32(error.count)
                    )
                }
            }
        }
        XCTAssertEqual(coloured, 0, String(cString: error))
        XCTAssertEqual(width, 2048)
        XCTAssertEqual(height, 1638)
        XCTAssertEqual(laid, 1)
        // In the picture's colours: its middle as the picture's middle.
        let middle = (Int(height) / 2 * Int(width) + Int(width) / 2) * 3
        let own = (photo.rows / 2 * photo.columns + photo.columns / 2) * 3
        XCTAssertLessThan(abs(Int(into[middle]) - Int(photo.rgb[own])), 8)
    }

    /// The drawing goes to the server as a JPEG of the server's own size.
    func testTheDrawingIsAJpeg() throws {
        let rgb = [UInt8](repeating: 128, count: 40 * 30 * 3)
        let image = try PhoneRestorer.picture(rgb, columns: 40, rows: 30)
        let jpeg = try PhoneRestorer.encoded(image)
        XCTAssertEqual(Array(jpeg.prefix(2)), [0xFF, 0xD8])
        XCTAssertEqual(image.width, 40)
    }
}
