import XCTest
@testable import Frame

final class HDRBoostTests: XCTestCase {
    /// A histogram from (lightness, share) parts.
    private func histogram(_ parts: [(Float, Double)]) -> [Int] {
        var bins = [Int](repeating: 0, count: HDRBoost.bins)
        for (lightness, share) in parts {
            bins[min(HDRBoost.bins - 1, Int(lightness * Float(HDRBoost.bins)))] += Int(share * 10_000)
        }
        return bins
    }

    func testADarkPictureLiftsItsLightPartsFully() throws {
        let plan = try XCTUnwrap(HDRBoost.plan(histogram: histogram([(0.25, 0.97), (0.75, 0.03)]), headroom: 5))
        XCTAssertEqual(plan.gain, HDRBoost.maxGain, accuracy: 0.01)
        XCTAssertLessThan(plan.knee, 0.55)
        XCTAssertEqual(plan.top, 0.75, accuracy: 0.01)
    }

    func testALightPictureWithABigSkyIsLiftedGently() throws {
        let sky = try XCTUnwrap(HDRBoost.plan(histogram: histogram([(0.6, 0.5), (0.9, 0.35), (0.97, 0.15)]), headroom: 5))
        let dark = try XCTUnwrap(HDRBoost.plan(histogram: histogram([(0.25, 0.97), (0.75, 0.03)]), headroom: 5))
        XCTAssertLessThan(sky.gain, 1.6)
        XCTAssertGreaterThan(sky.knee, dark.knee + 0.2)
    }

    func testAnEvenPictureIsLeftAlone() {
        XCTAssertNil(HDRBoost.plan(histogram: histogram([(0.5, 1)]), headroom: 5))
        XCTAssertNil(HDRBoost.plan(histogram: histogram([(0.25, 0.97), (0.75, 0.03)]), headroom: 1))
    }

    func testTheScreensHeadroomCapsTheGain() throws {
        let plan = try XCTUnwrap(HDRBoost.plan(histogram: histogram([(0.25, 0.97), (0.75, 0.03)]), headroom: 1.6))
        XCTAssertLessThanOrEqual(plan.gain, 1.6 * 0.9 + 0.001)
    }

    func testTheLiftRisesSmoothlyFromTheKneeToTheTop() {
        let plan = HDRBoost.Plan(knee: 0.5, top: 0.8, gain: 2)
        XCTAssertEqual(HDRBoost.factor(plan, lightness: 0.4), 1)
        XCTAssertEqual(HDRBoost.factor(plan, lightness: 0.8), 2, accuracy: 0.001)
        let steps = (0...100).map { HDRBoost.factor(plan, lightness: 0.5 + 0.3 * Float($0) / 100) }
        let jumps = zip(steps, steps.dropFirst()).map { $1 - $0 }
        XCTAssertTrue(jumps.allSatisfy { $0 >= 0 })
        // No step steeper than twice the average one.
        XCTAssertLessThan(jumps.max() ?? 0, 2.0 / 100 * 2)
    }

    /// A dark picture with a lone bright speck and a big light window: the
    /// window glows, the speck no more than its dark surroundings.
    func testALoneSpeckIsNotLiftedButALitAreaIs() throws {
        let width = 400, height = 300
        var bytes = [UInt8](repeating: 40, count: width * height * 4)
        func paint(_ x0: Int, _ y0: Int, _ x1: Int, _ y1: Int, _ value: UInt8) {
            for y in y0..<y1 { for x in x0..<x1 { for c in 0..<3 { bytes[(y * width + x) * 4 + c] = value } } }
        }
        paint(250, 60, 380, 240, 235) // the window
        paint(60, 150, 63, 153, 255) // the speck
        let space = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
        let provider = try XCTUnwrap(CGDataProvider(data: Data(bytes) as CFData))
        let source = try XCTUnwrap(CGImage(width: width, height: height, bitsPerComponent: 8, bitsPerPixel: 32,
                                           bytesPerRow: width * 4, space: space,
                                           bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.noneSkipLast.rawValue),
                                           provider: provider, decode: nil, shouldInterpolate: false,
                                           intent: .defaultIntent))
        let lifted = try XCTUnwrap(HDRBoost.boost(source, headroom: 5))
        let data = try XCTUnwrap(lifted.dataProvider?.data) as Data
        func red(_ x: Int, _ y: Int) -> Float {
            data.withUnsafeBytes { Float($0.bindMemory(to: Float16.self)[(y * lifted.width + x) * 4]) }
        }
        let white = HDRBoost.linear[235]
        XCTAssertGreaterThan(red(315, 150) / white, 1.5) // the window's middle glows
        XCTAssertLessThan(red(61, 151) / HDRBoost.linear[255], 1.05) // the speck does not
        XCTAssertEqual(red(20, 20) / HDRBoost.linear[40], 1, accuracy: 0.02) // the dark stays
    }
}
