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
