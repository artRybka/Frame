import XCTest
@testable import Frame

/// The work's drawn contour round the colour bar (Mateusz 2026-11-13 06:52,
/// of sketch 38: „C, ale kreska od góry trochę krótsza niż dolna. Trzeba
/// uważać, bo w A i B wyszła zbyt przestrzenna”).
final class ContourTests: XCTestCase {
    private let matisse = [("#c07374", 0.261), ("#bc3b3f", 0.235), ("#c29794", 0.164), ("#d5b5ac", 0.149), ("#61383a", 0.074)]
        .map { PaintShare(rgb: Paint.rgb($0.0) ?? [0, 0, 0], weight: $0.1) }
    private let line = ContourLine(hex: "#2d1e1d", length: 3.4, width: 1.17)!

    private func bar(_ style: PaintStyle = .oil, line: ContourLine? = nil) -> PaintPainter {
        let paint: PaintPainter = style == .water
            ? WaterStrip(shares: matisse, width: 350, seed: 7)
            : OilStrip(shares: matisse, width: 350, seed: 7, dark: false, relief: 1)
        guard let line else { return paint }
        return ContouredStrip(paint, line: line, style: style, seed: 7)
    }

    /// Where the line is, against the same bar without it: the pixels that
    /// came out darker.
    private func drawn(_ style: PaintStyle = .oil, line: ContourLine, age: Double? = nil) -> [(x: Int, y: Int)] {
        let plain = bar(style), lined = bar(style, line: line)
        let a = plain.frame(age: plain.length), b = lined.frame(age: age ?? lined.length)
        var out: [(x: Int, y: Int)] = []
        for y in 0..<a.high {
            for x in 0..<a.wide {
                let p = 4 * (y * a.wide + x)
                let was = Double(a.bytes[p]) * Double(a.bytes[p + 3]) / 255, now = Double(b.bytes[p]) * Double(b.bytes[p + 3]) / 255
                let wasDark = 255 - was, nowDark = 255 - now
                if b.bytes[p + 3] > 200, nowDark - wasDark > 60 || (a.bytes[p + 3] < 60 && b.bytes[p + 3] > 200 && b.bytes[p] < 120) {
                    out.append((x, y))
                }
            }
        }
        return out
    }

    func testTheLineGoesRoundTheBeginningAndAlongTheFootFurtherThanAlongTheTop() {
        let points = drawn(line: line)
        XCTAssertFalse(points.isEmpty)
        let middle = Double(bar().high) / 2
        let top = points.filter { Double($0.y) < middle }.map(\.x).max() ?? 0
        let foot = points.filter { Double($0.y) > middle }.map(\.x).max() ?? 0
        XCTAssertGreaterThan(foot, top + 30, "the top's line is shorter than the foot's")
        let start = Int(Paint.pad) * Paint.scale
        XCTAssertLessThan(points.map(\.x).min() ?? 999, start + 10, "it goes round the paint's beginning")
        // Not along the whole bar: as far as the picture has line.
        let end = Int((350 + Paint.pad) * Double(Paint.scale))
        XCTAssertLessThan(foot, start + Int(Double(end - start) * 0.8))
    }

    func testMoreLineInThePictureRunsFurtherAlongTheBar() {
        let short = drawn(line: line).map(\.x).max() ?? 0
        let long = drawn(line: ContourLine(hex: "#231913", length: 9.4, width: 0.79)!).map(\.x).max() ?? 0
        XCTAssertGreaterThan(long, short + 100)
        XCTAssertEqual(ContourLine(hex: "#000000", length: 1, width: 1)!.reach, 0.45)
        XCTAssertEqual(ContourLine(hex: "#000000", length: 30, width: 1)!.reach, 0.95)
    }

    func testItIsDrawnOnceThePaintIsDownAndOnlyInPaintedBars() {
        let lined = bar(line: line) as? ContouredStrip
        XCTAssertNotNil(lined)
        guard let lined else { return }
        XCTAssertTrue(drawn(line: line, age: lined.begins).isEmpty, "nothing before the paint is down")
        XCTAssertGreaterThan(lined.length, lined.begins)
        XCTAssertFalse(drawn(.water, line: line).isEmpty)
        XCTAssertTrue(ContourLine.draws(in: .oil) && ContourLine.draws(in: .water) && ContourLine.draws(in: .dry))
        for style in [PaintStyle.burin, .pen, .pencil, .woodblock, .litho, .photo] {
            XCTAssertFalse(ContourLine.draws(in: style), "\(style) shows its lines already")
        }
    }

    func testTheLineIsFlatAndInTheContoursOwnColour() {
        // No gloss and no shadow: where the line covers the paint wholly it
        // is its colour, never lighter than the paint showing a little
        // through its streaks, never darker than itself.
        let wide = 400, high = 120
        let paint = { (x: Int, y: Int) -> Double in x >= 40 && x < 360 && y >= 34 && y < 86 ? 1 : 0 }
        guard let stroke = ContourStroke(bar: paint, wide: wide, high: high, line: line, style: .oil, seed: 3) else {
            return XCTFail("no line")
        }
        var frame = PaintFrame(wide: wide, high: high)
        for q in 0..<(wide * high) { frame.bytes[4 * q] = 230; frame.bytes[4 * q + 1] = 200; frame.bytes[4 * q + 2] = 190; frame.bytes[4 * q + 3] = 255 }
        stroke.draw(on: &frame, progress: 1, seed: 3)
        var whole = 0
        for y in 0..<high {
            for x in 0..<wide where stroke.covered(x, y) >= 1 {
                whole += 1
                let p = 4 * (y * wide + x)
                for (k, want) in line.rgb.enumerated() {
                    let under = [230.0, 200, 190][k], got = Double(frame.bytes[p + k])
                    XCTAssertGreaterThanOrEqual(got, want * 0.95 - 2)
                    XCTAssertLessThanOrEqual(got, want + 0.16 * (under - want) + 4)
                }
            }
        }
        XCTAssertGreaterThan(whole, 300)
        XCTAssertTrue(stroke.covered(200, 60) == 0, "nothing in the middle of the paint")
        XCTAssertEqual(stroke.covered(30, 60, progress: 0), 0, "nothing before the brush gets there")
    }
}
