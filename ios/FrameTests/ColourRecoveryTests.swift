import XCTest
@testable import Frame

/// The card's colour recovery preview (`ColourRecovery`): the sum the app
/// does for a varnish, held to the server's own numbers
/// (`server/tests/test_recovery.py`).
final class ColourRecoveryTests: XCTestCase {
    private func told(steps: [Double] = [0, 0.5, 1], tops: [Double] = [0.8, 1.0, 1.4]) -> RecoveryView {
        RecoveryView(kind: "varnish", strength: 0.69, steps: steps, tops: tops)
    }

    private func picture(_ pixels: [[UInt8]]) throws -> CGImage {
        var bytes: [UInt8] = []
        for pixel in pixels { bytes += pixel + [UInt8(255)] }
        let space = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
        let provider = try XCTUnwrap(CGDataProvider(data: Data(bytes) as CFData))
        return try XCTUnwrap(CGImage(
            width: pixels.count, height: 1, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: pixels.count * 4,
            space: space, bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.noneSkipLast.rawValue),
            provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent
        ))
    }

    private func pixels(_ image: CGImage) throws -> [[Int]] {
        let data = try XCTUnwrap(image.dataProvider?.data) as Data
        let step = image.bitsPerPixel / 8
        return (0..<image.width).map { x in (0..<3).map { Int(data[x * step + $0]) } }
    }

    /// Oil and tempera have a varnish, drawings and prints a sheet; pastel
    /// and gouache cover theirs; a photograph or a poster has neither.
    func testWhatAWorkIsMadeInSaysWhatIsOffered() {
        XCTAssertEqual(ColourRecovery.made(.oil), "oil")
        XCTAssertEqual(ColourRecovery.made(.pen), "paper")
        XCTAssertEqual(ColourRecovery.made(.water), "paper")
        XCTAssertEqual(ColourRecovery.made(.woodblock), "paper")
        XCTAssertEqual(ColourRecovery.made(.grain), "paper")  // the stone's lithograph, 1.145.154
        XCTAssertEqual(ColourRecovery.made(.aquatint), "paper")  // the plate's aquatint, 1.145.156
        XCTAssertEqual(ColourRecovery.made(.pastel), "opaque")
        XCTAssertEqual(ColourRecovery.made(.gouache), "opaque")
        XCTAssertNil(ColourRecovery.made(.photo))
        XCTAssertNil(ColourRecovery.made(.offset))
        XCTAssertNil(ColourRecovery.made(nil))
        XCTAssertEqual(ColourRecovery.kind(told()), .varnish)
        XCTAssertEqual(ColourRecovery.kind(RecoveryView(kind: "paper")), .paper)
        XCTAssertNil(ColourRecovery.kind(RecoveryView(kind: "none")))
        XCTAssertNil(ColourRecovery.kind(nil))
    }

    /// Between the strengths the server read, the lightest of the result
    /// is on the line between them; past them, the nearest.
    func testTheLightestIsReadBetweenTheServersSteps() {
        let view = told()
        XCTAssertEqual(ColourRecovery.top(view, strength: 0), 0.8, accuracy: 1e-9)
        XCTAssertEqual(ColourRecovery.top(view, strength: 0.25), 0.9, accuracy: 1e-9)
        XCTAssertEqual(ColourRecovery.top(view, strength: 0.75), 1.2, accuracy: 1e-9)
        XCTAssertEqual(ColourRecovery.top(view, strength: 1), 1.4, accuracy: 1e-9)
        XCTAssertEqual(ColourRecovery.top(view, strength: 3), 1.4, accuracy: 1e-9)
        XCTAssertEqual(ColourRecovery.top(told(steps: [], tops: []), strength: 0.5), 0)
    }

    /// The varnish's colour off each channel, then the whole brought back
    /// only when its lights would leave the range.
    func testTheGainsAreTheServers() {
        // Nothing lighter than the range: the varnish alone.
        let low = ColourRecovery.gains(told(steps: [0, 1], tops: [0.9, 0.9]), strength: 0.4)
        XCTAssertEqual(low[0], 1.0618, accuracy: 0.0005)
        XCTAssertEqual(low[1], 1.1549, accuracy: 0.0005)
        XCTAssertEqual(low[2], 1.4918, accuracy: 0.0005)
        // Lights past the range: all three come down together.
        let high = ColourRecovery.gains(told(steps: [0, 1], tops: [1.3, 1.3]), strength: 0.7)
        XCTAssertEqual(high[0], 0.8288, accuracy: 0.0005)
        XCTAssertEqual(high[1], 0.96, accuracy: 0.0005)
        XCTAssertEqual(high[2], 1.5026, accuracy: 0.0005)
        // No strength: the picture as it is.
        XCTAssertEqual(ColourRecovery.gains(told(), strength: 0), [1, 1, 1])
    }

    /// The sum is done in linear light: the same pixels the server's sum
    /// gives (`recovery.gains`), to a level or two of rounding.
    func testThePictureIsDrawnAsTheServerWould() throws {
        let source = try picture([[200, 170, 90], [240, 225, 160], [40, 30, 20], [90, 120, 150]])
        let drawn = try XCTUnwrap(ColourRecovery.render(source, gains: [0.8288, 0.96, 1.5026]))
        let expected = [[184, 167, 109], [221, 221, 192], [36, 29, 26], [82, 118, 180]]
        for (got, want) in zip(try pixels(drawn), expected) {
            for channel in 0..<3 {
                XCTAssertEqual(Double(got[channel]), Double(want[channel]), accuracy: 2, "\(got) for \(want)")
            }
        }
    }

    /// A grey seen through a varnish of 0.8 is a grey again without it.
    func testAGreyUnderVarnishComesBackGrey() throws {
        let source = try picture([[178, 165, 130]])
        let view = told(steps: [0, 1.6], tops: [0.5, 0.5])
        let drawn = try XCTUnwrap(ColourRecovery.render(source, gains: ColourRecovery.gains(view, strength: 0.8)))
        let grey = try pixels(drawn)[0]
        XCTAssertEqual(Double(grey[0]), 188, accuracy: 2)
        XCTAssertEqual(Double(grey[1]), 188, accuracy: 2)
        XCTAssertEqual(Double(grey[2]), 188, accuracy: 2)
    }

    /// The slider's every point is not a picture of its own.
    func testTheStrengthIsDrawnInSteps() {
        XCTAssertEqual(ColourRecovery.snapped(0.694), 0.7, accuracy: 1e-9)
        XCTAssertEqual(ColourRecovery.snapped(0.689), 0.68, accuracy: 1e-9)
        XCTAssertEqual(ColourRecovery.snapped(0), 0)
    }

    /// The server's answer as it comes (snake case, every field).
    func testTheServersAnswerIsRead() throws {
        let json = """
        {"kind": "varnish", "strength": 0.72, "most": 1.6, "alpha": [0.15, 0.36, 1.0], "top": 0.97,
         "steps": [0.0, 0.1], "tops": [0.81, 0.84], "version": 1}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let view = try decoder.decode(RecoveryView.self, from: Data(json.utf8))
        XCTAssertEqual(view.strength, 0.72)
        XCTAssertEqual(view.tops, [0.81, 0.84])
        XCTAssertEqual(ColourRecovery.kind(view), .varnish)
    }
}
