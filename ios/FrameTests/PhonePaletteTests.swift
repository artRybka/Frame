@testable import Frame
import XCTest

/// "Barwy": the phone makes a photograph's colours as the server's
/// `palettes.colours_of` does. The rows below are the server's
/// (`tests/test_palettes.py` checks them against it).
final class PhonePaletteTests: XCTestCase {
    /// The made-up picture of `test_palettes._made_up`, 40 × 30.
    static func madeUp() -> [UInt8] {
        var rgb = [UInt8]()
        for y in 0 ..< 30 {
            for x in 0 ..< 40 {
                if (30 ..< 34).contains(x), (5 ..< 9).contains(y) {
                    rgb += [40, 140, 60]
                } else if x < 14 {
                    rgb += [UInt8(180 + y), UInt8(40 + x), 30]
                } else if x < 27 {
                    rgb += [30, UInt8(60 + y), UInt8(150 + x)]
                } else {
                    rgb += [UInt8(220 - y), UInt8(205 - y), 180]
                }
            }
        }
        return rgb
    }

    static let madeUpRows: [[Float]] = [
        // made-up: begin
        [0.44152, -0.02132, -0.17722, 0.32500],
        [0.53663, 0.17287, 0.10011, 0.35000],
        [0.77394, 0.00470, 0.02312, 0.17583],
        [0.83390, 0.00744, 0.03317, 0.14917],
        [0.56486, -0.12389, 0.08157, 0.01333],
        // made-up: end
    ]

    /// `DemoImages/aic_14598.jpg`, as the server reads it.
    static let demoRows: [[Float]] = [
        // demo: begin
        [0.56107, -0.01950, -0.01206, 0.34589],
        [0.66027, -0.00789, -0.00912, 0.18750],
        [0.69200, -0.00511, -0.00430, 0.16184],
        [0.72358, -0.00164, 0.00658, 0.13043],
        [0.76917, -0.00187, 0.01034, 0.17434],
        [0.36178, -0.00892, -0.04374, 0.03503],
        [0.44624, -0.00411, 0.01540, 0.05378],
        [0.55969, 0.00221, 0.02525, 0.04367],
        // demo: end
    ]

    func testTheMadeUpPicturesColoursAreTheServers() {
        let rows = PhonePalette.colours(rgb: Self.madeUp())
        XCTAssertEqual(rows.count, Self.madeUpRows.count)
        for (phone, server) in zip(rows, Self.madeUpRows) {
            for (p, s) in zip(phone, server) {
                XCTAssertEqual(p, s, accuracy: 1e-3, "\(phone) is not \(server)")
            }
        }
    }

    /// A photograph read and made smaller by each in its own way: its
    /// palette lies nearer the server's than a work's nearest works do
    /// (0.04-0.05 on the sketches of 2026-11-21; CI 0.017: two light tones
    /// fall into one mass on the phone, into two on the server).
    func testAPhotographsColoursLieNearTheServers() throws {
        let jpeg = try Data(contentsOf: try XCTUnwrap(Bundle.main.url(forResource: "aic_14598", withExtension: "jpg")))
        let rows = try XCTUnwrap(PhonePalette.colours(jpeg))
        let far = PhonePalette.far(PhonePalette.palette(rows), PhonePalette.palette(Self.demoRows))
        XCTAssertLessThan(far, 0.025, "the phone's colours are not the server's: \(rows)")
    }

    func testAPaletteIsNearestItselfAndFarFromAnother() {
        let red = PhonePalette.palette([[0.9, 0.0, 0.02, 0.7], [0.5, 0.18, 0.09, 0.3]])
        let blue = PhonePalette.palette([[0.9, 0.0, 0.02, 0.7], [0.45, -0.02, -0.18, 0.3]])
        XCTAssertLessThan(PhonePalette.far(red, red), 0.005)
        XCTAssertGreaterThan(PhonePalette.far(red, blue), 0.05)
    }
}
