import XCTest
@testable import Frame

/// "Droga dzieła" (Mateusz 2026-11-10, "S1"): the server's journey read, and
/// what the road's numbers say.
final class JourneyRoadTests: XCTestCase {
    func testTheServersJourneyIsRead() throws {
        let json = """
        {"headline": "Z pracowni w Paryżu do Chicago", "lead": "", "from_where": "z Paryża",
         "stops": [{"year": "1886", "place": "Paryż", "lat": 48.86, "lon": 2.35, "kind": "shown",
                    "owner": false, "detour": false, "text": "Pierwszy raz pokazany, **nr 175**."},
                   {"year": "1926", "place": "Chicago", "lat": 41.88, "lon": -87.62, "kind": "museum",
                    "owner": true, "detour": false, "text": "Dar dla **Art Institute**."}],
         "years": 40, "km": 6650, "hands": 7, "exhibitions": null, "source": "Art Institute of Chicago"}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let journey = try decoder.decode(DailyWork.Journey.self, from: Data(json.utf8))
        XCTAssertEqual(journey.fromWhere, "z Paryża")
        XCTAssertEqual(journey.stops.last?.kind, "museum")
        XCTAssertNil(journey.exhibitions)
        // Over an ocean: the road leaves room for the sea.
        XCTAssertGreaterThan(JourneyRoad.km(journey.stops[0], journey.stops[1]), 6000)
    }

    func testPolishNumbersAgree() {
        XCTAssertEqual(JourneyRoad.plural(1, "rok", "lata", "lat"), "rok")
        XCTAssertEqual(JourneyRoad.plural(3, "rok", "lata", "lat"), "lata")
        XCTAssertEqual(JourneyRoad.plural(13, "rok", "lata", "lat"), "lat")
        XCTAssertEqual(JourneyRoad.plural(22, "rok", "lata", "lat"), "lata")
        XCTAssertEqual(JourneyRoad.plural(40, "rok", "lata", "lat"), "lat")
    }

    func testTheTellingWordsAreBold() {
        let text = JourneyRoad.marked("Sprzedany za **800 franków**.")
        XCTAssertEqual(String(text.characters), "Sprzedany za 800 franków.")
        let bold = text.runs.contains { $0.inlinePresentationIntent?.contains(.stronglyEmphasized) == true }
        XCTAssertTrue(bold)
    }

    func testTheSplineGoesThroughItsPointsWithoutAKnot() {
        let stops = [CGPoint(x: 20, y: 0), CGPoint(x: 40, y: 40), CGPoint(x: 42, y: 41), CGPoint(x: 300, y: 200)]
        let line = JourneyRoad.spline(stops, per: 24)
        XCTAssertEqual(line.count, 3 * 24 + 1)
        for (k, stop) in stops.enumerated() {
            XCTAssertEqual(line[k * 24].x, stop.x, accuracy: 0.01)
            XCTAssertEqual(line[k * 24].y, stop.y, accuracy: 0.01)
        }
        // Between two close points the line stays near them (centripetal: no loop).
        for p in line[(24)...(48)] {
            XCTAssertLessThan(hypot(p.x - 41, p.y - 40.5), 6)
        }
    }

    /// Nine stops with a sea before the eighth, as the Grande Jatte has.
    private func road(_ seed: String = "aic:27992", width: CGFloat = 350) throws -> RoadPlan {
        let heights: [CGFloat] = [54, 74, 54, 54, 54, 54, 54, 74, 74]
        let seas = [false, false, false, false, false, false, false, true, false]
        return try XCTUnwrap(JourneyRoad.plan(width: width, heights: heights, seas: seas, seed: seed))
    }

    func testTheRoadNeverRunsIntoAText() throws {
        for (seed, width) in [("aic:27992", 350), ("aic:1", 350), ("cma:1958.47", 402), ("x", 320)] as [(String, CGFloat)] {
            let plan = try road(seed, width: width)
            for (i, text) in plan.texts.enumerated() {
                let near = plan.line.map { p in
                    hypot(max(text.minX - p.x, 0, p.x - text.maxX), max(text.minY - p.y, 0, p.y - text.maxY))
                }.min() ?? 0
                XCTAssertGreaterThanOrEqual(near, 5, "text \(i), \(seed)")
                // Inside the road, and right at its dot.
                XCTAssertGreaterThanOrEqual(text.minX, 0)
                XCTAssertLessThanOrEqual(text.maxX, width)
                let dot = plan.dots[i]
                let away = hypot(max(text.minX - dot.x, 0, dot.x - text.maxX), max(text.minY - dot.y, 0, dot.y - text.maxY))
                XCTAssertLessThan(away, 26, "text \(i) is far from its dot, \(seed)")
            }
            XCTAssertLessThanOrEqual(plan.texts.map(\.maxY).max() ?? 0, plan.height)
        }
    }

    func testTheLineIsDrawnFirstAndTheDotsAreOnIt() throws {
        let plan = try road()
        // It starts at the first stop and ends at the last.
        XCTAssertEqual(plan.line.first, plan.dots.first)
        XCTAssertEqual(plan.line.last, plan.dots.last)
        for dot in plan.dots {
            XCTAssertTrue(plan.line.contains(dot))
        }
        // One flowing line: evenly spaced, and no bend anywhere, at a dot or not.
        for i in 2..<plan.line.count {
            let (a, b, c) = (plan.line[i - 2], plan.line[i - 1], plan.line[i])
            XCTAssertLessThan(hypot(c.x - b.x, c.y - b.y), 4)
            var turn = abs(atan2(b.y - a.y, b.x - a.x) - atan2(c.y - b.y, c.x - b.x))
            if turn > .pi { turn = 2 * .pi - turn }
            XCTAssertLessThan(turn * 180 / .pi, 20, "a bend at sample \(i)")
        }
        // It sweeps across the road, not down one side of it.
        let xs = plan.line.map(\.x)
        XCTAssertLessThan(xs.min() ?? 0, 60)
        XCTAssertGreaterThan(xs.max() ?? 0, 290)
    }

    func testTheNibIsWideWhereTheLineGoesDown() throws {
        let down = [CGPoint(x: 50, y: 0), CGPoint(x: 50, y: 10), CGPoint(x: 50, y: 20)]
        let outline = JourneyRoad.nibStroke(down, until: CGPoint(x: 500, y: 500), clear: 12)
        XCTAssertEqual(outline.count, 6)
        XCTAssertEqual(hypot(outline[0].x - outline[5].x, outline[0].y - outline[5].y), JourneyRoad.nib, accuracy: 0.01)
        // It stops short of the last dot's ring.
        let short = JourneyRoad.nibStroke(down, until: CGPoint(x: 50, y: 20), clear: 12)
        XCTAssertEqual(short.count, 2)
    }

    func testASideTripForksOffToACircledText() throws {
        let heights: [CGFloat] = [54, 74, 54, 54, 74]
        let seas = [false, false, false, false, false]
        let plan = try XCTUnwrap(JourneyRoad.plan(width: 350, heights: heights, seas: seas,
                                                  detours: [false, false, true, false, false],
                                                  widths: [180, 190, 150, 160, 170], seed: "aic:27992"))
        XCTAssertEqual(Array(plan.branches.keys), [2])
        let way = try XCTUnwrap(plan.branches[2]), box = try XCTUnwrap(plan.loops[2]), stop = plan.dots[2]
        // The branch leaves the road itself, the way the road goes there,
        // and ends at its stop, which is off the road, under it.
        let fork = try XCTUnwrap(plan.line.firstIndex(of: way[0]))
        XCTAssertEqual(way.last, stop)
        let road = atan2(plan.line[fork + 4].y - plan.line[fork - 4].y, plan.line[fork + 4].x - plan.line[fork - 4].x)
        let leaves = atan2(way[2].y - way[0].y, way[2].x - way[0].x)
        XCTAssertEqual(cos(road - leaves), 1, accuracy: 0.01)
        XCTAssertGreaterThan(zip(way, way.dropFirst()).map { hypot($1.x - $0.x, $1.y - $0.y) }.reduce(0, +), 70)
        let off = plan.line.map { hypot($0.x - stop.x, $0.y - stop.y) }.min() ?? 0
        XCTAssertGreaterThan(off, 20)
        // The loop's box is as wide as its text and holds it; the stop is
        // on the loop, and the road keeps clear of the box.
        XCTAssertEqual(box.width, 150 + 2 * JourneyRoad.loopPad.side, accuracy: 0.01)
        XCTAssertEqual(box.minY, plan.texts[2].minY - JourneyRoad.loopPad.top, accuracy: 0.01)
        XCTAssertEqual(box.maxY, plan.texts[2].maxY + JourneyRoad.loopPad.bottom, accuracy: 0.01)
        XCTAssertGreaterThanOrEqual(box.minX, 0)
        XCTAssertLessThanOrEqual(box.maxX, 350)
        var random = SeededRandom("loop")
        let ring = JourneyRoad.loop(box, dotRight: !plan.leading[2], random: &random)
        XCTAssertLessThan(ring.map { hypot($0.x - stop.x, $0.y - stop.y) }.min() ?? 9, 1.5)
        // It goes once round and a little more, and stays about its box.
        XCTAssertGreaterThan(hypot(ring[0].x - ring[ring.count - 1].x, ring[0].y - ring[ring.count - 1].y), 20)
        XCTAssertTrue(ring.allSatisfy { box.insetBy(dx: -box.width * 0.06, dy: -box.height * 0.06).contains($0) })
        for area in plan.texts + [box] {
            let near = plan.line.map { p in
                hypot(max(area.minX - p.x, 0, p.x - area.maxX), max(area.minY - p.y, 0, p.y - area.maxY))
            }.min() ?? 0
            XCTAssertGreaterThanOrEqual(near, 5)
        }
        // The branch is inked in short strokes, none of them over its dot.
        let strokes = JourneyRoad.dashes(way, until: stop)
        XCTAssertGreaterThan(strokes.count, 4)
        XCTAssertTrue(strokes.joined().allSatisfy { hypot($0.x - stop.x, $0.y - stop.y) > 4.6 })
    }

    func testEachTextHasAnUnderpainting() throws {
        let heights: [CGFloat] = [54, 74, 54], widths: [CGFloat] = [180, 150, 170]
        let plan = try XCTUnwrap(JourneyRoad.plan(width: 350, heights: heights, seas: [false, false, false],
                                                  widths: widths, seed: "aic:27992"))
        XCTAssertEqual(plan.hugs.count, 3)
        for (i, hug) in plan.hugs.enumerated() {
            // The text as it stands: its own width, at the side its dot is on.
            XCTAssertEqual(hug.width, widths[i], accuracy: 0.01)
            XCTAssertEqual(plan.leading[i] ? hug.minX : hug.maxX, plan.leading[i] ? plan.texts[i].minX : plan.texts[i].maxX,
                           accuracy: 0.01)
            var random = SeededRandom("wash\(i)")
            let wash = JourneyRoad.wash(under: hug, random: &random)
            // A closed stain about the text: it covers the text's middle and is not much bigger than it.
            let xs = wash.big.map(\.x), ys = wash.big.map(\.y)
            XCTAssertLessThan(xs.min() ?? 0, hug.midX - hug.width * 0.3)
            XCTAssertGreaterThan(xs.max() ?? 0, hug.midX + hug.width * 0.3)
            XCTAssertLessThan(ys.min() ?? 0, hug.midY - 5)
            XCTAssertGreaterThan(ys.max() ?? 0, hug.midY + 5)
            XCTAssertGreaterThan(xs.min() ?? 0, hug.minX - 70)
            XCTAssertLessThan(xs.max() ?? 0, hug.maxX + 70)
            XCTAssertEqual(wash.big.first, wash.big.last)
            XCTAssertTrue((0.8...1.2).contains(wash.tone))
        }
    }

    func testWhiteLiesBesideTheLineAndRoundTheLastDot() throws {
        let plan = try road(), last = plan.dots[plan.dots.count - 1]
        let strokes = JourneyRoad.corrections(along: plan.line, until: last, seed: "aic:27992")
        XCTAssertGreaterThanOrEqual(strokes.count, 2)
        for stroke in strokes {
            // Each keeps to the line: never further than a nib and a half from it.
            let far = stroke.map { p in plan.line.map { hypot($0.x - p.x, $0.y - p.y) }.min() ?? 99 }.max() ?? 99
            XCTAssertLessThan(far, 10)
            XCTAssertGreaterThan(stroke.count, 40)
        }
        var random = SeededRandom("halo")
        let halo = JourneyRoad.halo(round: last, random: &random)
        // Wider than the dot all round.
        XCTAssertGreaterThan(halo.map { hypot($0.x - last.x, $0.y - last.y) }.min() ?? 0, JourneyRoad.lastDot + 1.5)
        XCTAssertLessThan(halo.map { hypot($0.x - last.x, $0.y - last.y) }.max() ?? 99, 20)
    }

    func testLinesAreOfAboutTheSameLength() {
        // "Odbitka jest w rękach marszandów Yamanaka & Company.": the name is
        // one piece, and the word before it is not left alone on a line.
        XCTAssertEqual(JourneyRoad.evenBreaks([50, 26, 62, 84, 150], space: 4, width: 190), [2, 4])
        // One line when it all fits, as few lines as it takes otherwise.
        XCTAssertEqual(JourneyRoad.evenBreaks([50, 26, 62], space: 4, width: 190), [])
        XCTAssertEqual(JourneyRoad.evenBreaks([100, 100, 100, 100], space: 4, width: 210), [2])
        // A word wider than a line has a line to itself.
        XCTAssertEqual(JourneyRoad.evenBreaks([60, 300, 60], space: 4, width: 190), [1, 2])
        XCTAssertEqual(JourneyRoad.evenBreaks([60], space: 4, width: 190), [])
        // In the app's own faces: no line is wider than the column, the words stay in order.
        let text = "Odbitka jest w rękach marszandów **Yamanaka & Company**."
        let lines = JourneyRoad.broken(text, width: 193).components(separatedBy: "\n")
        XCTAssertEqual(lines.count, 3)
        XCTAssertEqual(lines.joined(separator: " "), JourneyRoad.typeset(text))
        XCTAssertEqual(lines.last, "**Yamanaka\u{00A0}&\u{00A0}Company**.")
        XCTAssertNotEqual(lines[1], "marszandów")
    }

    func testLinesAreNotBrokenWhereTheyMustNotBe() {
        let hard = "\u{00A0}"
        // A one-letter word never ends a line; the last line is not one word.
        XCTAssertEqual(JourneyRoad.typeset("Seurat maluje obraz; ramkę z kropek dokłada w **1888–89**."),
                       "Seurat maluje obraz; ramkę z\(hard)kropek dokłada w\(hard)**1888–89**.")
        // A number stays with its word, a telling name is whole.
        XCTAssertEqual(JourneyRoad.typeset("Pierwszy raz pokazany: VIII wystawa malarstwa, **nr 175** w katalogu."),
                       "Pierwszy raz pokazany: VIII\(hard)wystawa malarstwa, **nr\(hard)175**\(hard)w\(hard)katalogu.")
        XCTAssertEqual(JourneyRoad.typeset("Sprzedany za **20 000 dolarów** Frederikowi Clayowi i Helen Birch Bartlett."),
                       "Sprzedany za\(hard)**20\(hard)000\(hard)dolarów** Frederikowi Clayowi i\(hard)Helen Birch\(hard)Bartlett.")
        XCTAssertEqual(JourneyRoad.typeset("Po jej śmierci przechodzi na **brata, Émile’a**."),
                       "Po jej śmierci przechodzi na **brata,\(hard)Émile’a**.")
        // A year is not tied to the word after it, a long name is not tied at all.
        XCTAssertEqual(JourneyRoad.typeset("W 1924 obraz kupuje **Frederic Clay Bartlett z żoną Helen Birch**, kolekcjonerzy."),
                       "W\(hard)1924 obraz kupuje **Frederic\(hard)Clay\(hard)Bartlett z\(hard)żoną\(hard)Helen\(hard)Birch**, kolekcjonerzy.")
        XCTAssertEqual(JourneyRoad.typeset("Dar."), "Dar.")
    }

    func testAShortJourneyHasARoadToo() {
        XCTAssertNotNil(JourneyRoad.plan(width: 350, heights: [54, 54], seas: [false, false], seed: "x"))
        XCTAssertNotNil(JourneyRoad.plan(width: 350, heights: [54, 74], seas: [false, true], seed: "y"))
        // Nothing to draw for one stop, or before the width is known.
        XCTAssertNil(JourneyRoad.plan(width: 350, heights: [54], seas: [false], seed: "x"))
        XCTAssertNil(JourneyRoad.plan(width: 0, heights: [54, 54], seas: [false, false], seed: "x"))
    }

    func testTheSameWorkKeepsItsRoad() throws {
        var a = SeededRandom("aic:27992"), b = SeededRandom("aic:27992"), c = SeededRandom("aic:1")
        let first = (0..<5).map { _ in a.next() }
        XCTAssertEqual(first, (0..<5).map { _ in b.next() })
        XCTAssertNotEqual(first, (0..<5).map { _ in c.next() })
        // And the same road.
        XCTAssertEqual(try road().line, try road().line)
        XCTAssertNotEqual(try road().line, try road("aic:1").line)
    }
}
