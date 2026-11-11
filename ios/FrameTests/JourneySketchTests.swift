import XCTest
@testable import Frame

/// The pen drawings by "Droga dzieła": which stops get one, which one,
/// where it has room, and how the nib draws it.
final class JourneySketchTests: XCTestCase {
    private func stop(_ place: String, _ lat: Double, _ lon: Double, _ year: String, _ kind: String,
                      text: String = "", detour: Bool = false) -> JourneySketch.Stop {
        JourneySketch.Stop(place: place, lat: lat, lon: lon, year: year, kind: kind, text: text, detour: detour)
    }

    func testEveryDrawingIsAFewStrokesInItsBox() {
        for motif in JourneySketch.Motif.allCases {
            let strokes = JourneySketch.strokes(motif)
            XCTAssertTrue((4...40).contains(strokes.count), "\(motif): \(strokes.count) strokes")
            for stroke in strokes {
                XCTAssertGreaterThanOrEqual(stroke.points.count, 2, "\(motif)")
                XCTAssertTrue(stroke.light > 0.3 && stroke.light <= 1, "\(motif)")
                for point in stroke.points {
                    XCTAssertTrue((-6...106).contains(point.x) && (-6...106).contains(point.y), "\(motif): \(point)")
                }
            }
        }
    }

    func testAPlacesSightIsTheOneThatStoodInTheStopsYear() {
        // Mateusz 2026-11-11 20:02: „Paryż - wieża Eiffla”. From 1889 on; Notre-Dame before.
        XCTAssertEqual(JourneySketch.sight(stop("Paryż", 48.86, 2.35, "1900", "sold")), .eiffel)
        XCTAssertEqual(JourneySketch.sight(stop("Paryż", 48.86, 2.35, "1874", "shown")), .notredame)
        XCTAssertEqual(JourneySketch.sight(stop("Paryż", 48.86, 2.35, "przed 1905", "sold")), .notredame)
        XCTAssertEqual(JourneySketch.sight(stop("Paryż", 48.86, 2.35, "", "home")), .notredame)
        // No statue before 1886, and "przed 1905" may be before it.
        XCTAssertEqual(JourneySketch.sight(stop("Nowy Jork", 40.71, -74.0, "1913", "sold")), .liberty)
        XCTAssertNil(JourneySketch.sight(stop("Nowy Jork", 40.71, -74.0, "przed 1905", "sold")))
        XCTAssertNil(JourneySketch.sight(stop("Nowy Jork", 40.71, -74.0, "1870", "sold")))
        // Anywhere in Japan it is Fuji; Delft is the Netherlands, Amsterdam itself.
        XCTAssertEqual(JourneySketch.sight(stop("Edo", 35.68, 139.69, "ok. 1830–1832", "made")), .fuji)
        XCTAssertEqual(JourneySketch.sight(stop("Kioto", 35.01, 135.77, "1700", "made")), .fuji)
        XCTAssertEqual(JourneySketch.sight(stop("Delft", 52.01, 4.36, "1658", "made")), .windmill)
        XCTAssertEqual(JourneySketch.sight(stop("Amsterdam", 52.37, 4.9, "1885", "museum")), .canal)
        // A stop without coordinates goes by its name; a place without a sight has none.
        XCTAssertEqual(JourneySketch.sight(stop("Wiedeń, pałac", 0, 0, "1780", "home")), .stephansdom)
        XCTAssertNil(JourneySketch.sight(stop("Łódź", 51.76, 19.46, "1930", "museum")))
        XCTAssertNil(JourneySketch.sight(stop("", 0, 0, "1930", "museum")))
    }

    func testAYearIsReadOnlyWhereItIsPlain() {
        XCTAssertEqual(JourneySketch.year("1900"), 1900)
        XCTAssertEqual(JourneySketch.year("ok. 1830–1832"), 1830)
        XCTAssertEqual(JourneySketch.year("po 1945"), 1945)
        XCTAssertNil(JourneySketch.year("przed 1891"))
        XCTAssertNil(JourneySketch.year("XVII w."))
        XCTAssertNil(JourneySketch.year(""))
    }

    func testWhatHappenedIsDrawnFromTheStopsKind() {
        XCTAssertEqual(JourneySketch.event(stop("", 0, 0, "", "sold", text: "Kupuje ją kolekcjoner."), sea: false), .coins)
        XCTAssertEqual(JourneySketch.event(stop("", 0, 0, "", "sold", text: "Sprzedana na **aukcji** w Londynie."), sea: false), .gavel)
        XCTAssertEqual(JourneySketch.event(stop("", 0, 0, "", "travel"), sea: true), .ship)
        XCTAssertEqual(JourneySketch.event(stop("", 0, 0, "", "travel"), sea: false), .trunk)
        XCTAssertEqual(JourneySketch.event(stop("", 0, 0, "", "stolen"), sea: false), .emptyframe)
        XCTAssertNil(JourneySketch.event(stop("", 0, 0, "", "home"), sea: false))
        XCTAssertNil(JourneySketch.event(stop("", 0, 0, "", ""), sea: false))
    }

    /// The Great Wave's road, as the demo and sketch 32 have it.
    private var wave: [JourneySketch.Stop] {
        [
            stop("Edo", 35.68, 139.69, "ok. 1830–1832", "made"),
            stop("Nowy Jork", 40.71, -74.0, "przed 1905", "sold"),
            stop("Chicago", 41.88, -87.62, "1905", "sold"),
            stop("Chicago", 41.88, -87.62, "1913", "inherited"),
            stop("Chicago", 41.88, -87.62, "1925", "museum"),
        ]
    }

    func testARoadGetsAFewDrawingsNeverAtStopsNextToEachOther() {
        // „okazjonalnie a nie przy każdym Punkcie”: Fuji by Edo, a ship on
        // the Pacific, coins by the sale of 1905 (sketch 32).
        let picks = JourneySketch.picks(wave, seas: [false, true, false, false, false])
        XCTAssertEqual(picks, [
            JourneySketch.Pick(stop: 0, motif: .fuji),
            JourneySketch.Pick(stop: 1, motif: .ship, sea: true),
            JourneySketch.Pick(stop: 2, motif: .coins),
        ])
        // Whatever the road, the rules hold.
        var long = wave + wave + [stop("Paryż", 48.86, 2.35, "1950", "sold", detour: true)]
        long[6].kind = "stolen"
        for (stops, seas) in [(wave, [false, true, false, false, false]), (long, long.map { _ in false }),
                              (Array(wave.prefix(2)), [false, true]), (Array(wave.prefix(1)), [false])] {
            let picks = JourneySketch.picks(stops, seas: seas)
            XCTAssertLessThanOrEqual(picks.count, min(3, (stops.count + 1) / 2))
            XCTAssertEqual(Set(picks.map(\.motif)).count, picks.count, "none twice")
            let by = picks.filter { !$0.sea }.map(\.stop).sorted()
            for (a, b) in zip(by, by.dropFirst()) { XCTAssertGreaterThan(b - a, 1, "not at neighbours") }
            for pick in picks { XCTAssertFalse(stops[pick.stop].detour) }
        }
        XCTAssertTrue(JourneySketch.picks(Array(wave.prefix(1)), seas: [false]).isEmpty)
        // An old road and a new one are told the same way: nothing but the
        // stops decides (21:19: „Stare drogi… kompletność jak nowotworzone”).
        XCTAssertEqual(JourneySketch.picks(wave, seas: [false, true, false, false, false]), picks)
    }

    func testADrawingKeepsClearOfTheLineAndOfWhatIsThere() {
        // A stain at the left, the line down the middle and across under it.
        let stain = CGRect(x: 20, y: 100, width: 150, height: 70)
        let line = (0...60).map { CGPoint(x: 200, y: CGFloat($0) * 5) } + (0...40).map { CGPoint(x: 200 - CGFloat($0) * 5, y: 300) }
        let box = JourneySketch.room(beside: stain, lines: [line], taken: [stain], width: 360, height: 600)
        XCTAssertNotNil(box)
        if let box {
            XCTAssertEqual(box.width, JourneySketch.side)
            XCTAssertFalse(box.insetBy(dx: -6, dy: -6).intersects(stain))
            XCTAssertTrue(line.allSatisfy { !box.insetBy(dx: -9, dy: -9).contains($0) })
            XCTAssertTrue(box.minX >= 4 && box.maxX <= 356)
            // Beside the stain, across the line from it, not far below.
            XCTAssertGreaterThan(box.minX, 200)
            XCTAssertLessThan(box.minY, stain.maxY)
        }
        // No room: no drawing.
        let wall = CGRect(x: 0, y: 0, width: 360, height: 600)
        XCTAssertNil(JourneySketch.room(beside: stain, lines: [line], taken: [stain, wall], width: 360, height: 600))
        // The ship keeps to its sea and off the line.
        let sea = CGRect(x: 0, y: 320, width: 360, height: 160)
        let ship = JourneySketch.room(on: sea, lines: [line], taken: [], width: 360, height: 600)
        XCTAssertNotNil(ship)
        if let ship { XCTAssertTrue(sea.contains(ship)) }
        // Two lines are two lines: nothing runs from the end of one to the start of the other.
        let apart = [[CGPoint(x: 10, y: 10), CGPoint(x: 10, y: 20)], [CGPoint(x: 300, y: 500), CGPoint(x: 300, y: 510)]]
        XCTAssertTrue(JourneySketch.free(CGRect(x: 150, y: 250, width: 46, height: 46), lines: apart, taken: [], width: 360, height: 600))
        XCTAssertEqual(JourneySketch.within([line], top: 100, bottom: 120).map(\.count), [5])
    }

    func testTheNibDrawsStrokeAfterStrokeThinAtTheEnds() {
        let box = CGRect(x: 100, y: 200, width: JourneySketch.side, height: JourneySketch.side)
        let lines = JourneySketch.lines(.eiffel, in: box, seed: "work")
        XCTAssertEqual(lines.count, JourneySketch.strokes(.eiffel).count)
        XCTAssertEqual(lines, JourneySketch.lines(.eiffel, in: box, seed: "work"), "the same hand for the same work")
        XCTAssertNotEqual(lines, JourneySketch.lines(.eiffel, in: box, seed: "other"))
        // Nothing before the pen begins; then one stroke after another; then all, and no more.
        let takes = JourneySketch.takes(lines)
        XCTAssertTrue(takes > 0.5 && takes <= JourneySketch.pace.most)
        XCTAssertTrue(JourneySketch.outlines(lines, age: 0).isEmpty)
        var before = 0
        for step in 1...10 {
            let now = JourneySketch.outlines(lines, age: takes * CGFloat(step) / 10).count
            XCTAssertGreaterThanOrEqual(now, before)
            before = now
        }
        XCTAssertEqual(before, lines.count)
        XCTAssertEqual(JourneySketch.outlines(lines, age: takes), JourneySketch.outlines(lines, age: takes + 5))
        // A stroke keeps to the box (with a little over for the hand) and is
        // widest in its middle: the leg of the tower, drawn downwards, is
        // about as wide as the nib there and a hair at its ends.
        let leg = JourneySketch.outline(lines[0])
        XCTAssertTrue(leg.allSatisfy { box.insetBy(dx: -6, dy: -6).contains($0) })
        let half = leg.count / 2
        func wide(_ j: Int) -> CGFloat { hypot(leg[j].x - leg[leg.count - 1 - j].x, leg[j].y - leg[leg.count - 1 - j].y) }
        XCTAssertGreaterThan(wide(half / 2), 1.5)
        XCTAssertLessThan(wide(half / 2), JourneySketch.nib + 0.3)
        XCTAssertLessThan(wide(0), 1.0)
        XCTAssertLessThan(wide(half - 1), 1.0)
        // Half drawn, it is half as long.
        XCTAssertLessThan(JourneySketch.outline(lines[0], part: 0.5).count, leg.count * 6 / 10)
    }
}
