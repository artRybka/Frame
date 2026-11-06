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

    func testDarksStayAndTheWhiteGetsTheGain() {
        let plan = HDRBoost.Plan(knee: 0.5, top: 0.9, gain: 2.5)
        let factors = HDRBoost.factors(plan)
        XCTAssertEqual(factors[0], 1)
        XCTAssertEqual(factors[Int(0.1 * Float(factors.count - 1))], 1) // lightness 0.46
        XCTAssertEqual(factors[factors.count - 1], 2.5, accuracy: 0.001)
        XCTAssertEqual(zip(factors, factors.dropFirst()).allSatisfy { $0 <= $1 }, true)
    }
}
