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
        // It sweeps across the road, not down one side of it, and stays on the page.
        let xs = plan.line.map(\.x)
        XCTAssertLessThan(xs.min() ?? 0, 70)
        XCTAssertGreaterThan(xs.max() ?? 0, 280)
        XCTAssertGreaterThan(xs.min() ?? 0, 14)
        XCTAssertLessThan(xs.max() ?? 0, 336)
    }

    func testTheLineComesOutFromUnderTheRule() throws {
        // 22:21: „start kreski niech zaczyna się spod linii nad którą są
        // liczby”: with figures over the road the line starts at their
        // rule, over the road's top, and comes down through the first dot.
        let heights: [CGFloat] = [54, 74, 54, 54, 54, 54, 54, 74, 74]
        let seas = [false, false, false, false, false, false, false, true, false]
        for seed in ["aic:27992", "aic:1", "x"] {
            let plan = try XCTUnwrap(JourneyRoad.plan(width: 350, heights: heights, seas: seas, seed: seed,
                                                      lead: JourneyRoad.lead))
            let first = try XCTUnwrap(plan.line.first), dot = plan.dots[0]
            XCTAssertEqual(first.y, -JourneyRoad.lead, accuracy: 0.01)
            XCTAssertTrue(plan.line.contains(dot))
            XCTAssertEqual(dot.y, JourneyRoad.yearY, accuracy: 2)
            // Almost straight down to the dot, beside the first text.
            XCTAssertLessThan(abs(first.x - dot.x), 12)
            let near = plan.line.map { p in
                hypot(max(plan.texts[0].minX - p.x, 0, p.x - plan.texts[0].maxX),
                      max(plan.texts[0].minY - p.y, 0, p.y - plan.texts[0].maxY))
            }.min() ?? 0
            XCTAssertGreaterThanOrEqual(near, 5)
            XCTAssertEqual(plan.line.last, plan.dots.last)
        }
    }

    func testTheArcsNarrowTowardsTheBottom() throws {
        // 22:22: „albo zwężać się coraz bardziej ku dołowi”; his pick of
        // the two in sketch 19 (23:03: „B”).
        XCTAssertEqual(JourneyRoad.arcs, .narrow)
        let heights: [CGFloat] = [54, 74, 54, 54, 54, 54, 54, 74, 74]
        let seas = [false, false, false, false, false, false, false, true, false]
        for seed in ["aic:27992", "aic:1", "x"] {
            let plan = try XCTUnwrap(JourneyRoad.plan(width: 350, heights: heights, seas: seas, seed: seed))
            func span(_ from: CGFloat, _ to: CGFloat) -> CGFloat {
                let xs = plan.line.filter { $0.y >= from * plan.height && $0.y < to * plan.height }.map(\.x)
                return (xs.max() ?? 0) - (xs.min() ?? 0)
            }
            XCTAssertGreaterThan(span(0, 0.3), span(0.35, 0.65) + 30, seed)
            XCTAssertGreaterThan(span(0.35, 0.65), span(0.7, 1) + 30, seed)
            for text in plan.texts {
                let near = plan.line.map { p in
                    hypot(max(text.minX - p.x, 0, p.x - text.maxX), max(text.minY - p.y, 0, p.y - text.maxY))
                }.min() ?? 0
                XCTAssertGreaterThanOrEqual(near, 5, seed)
            }
        }
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

    func testAStainLiesUnderItsTextAndComesOutOfItsDot() throws {
        // 2026-11-11 08:29: „z nich rozlewają się plamy pod tekst”; 08:55:
        // „zaczynając się od kropki… nie spływać tak bardzo w dół”.
        let heights: [CGFloat] = [54, 74, 54], widths: [CGFloat] = [180, 150, 170]
        let plan = try XCTUnwrap(JourneyRoad.plan(width: 350, heights: heights, seas: [false, false, false],
                                                  widths: widths, seed: "aic:27992"))
        XCTAssertEqual(plan.hugs.count, 3)
        for (i, hug) in plan.hugs.enumerated() {
            // The text as it stands: its own width, at the side its dot is on.
            XCTAssertEqual(hug.width, widths[i], accuracy: 0.01)
            XCTAssertEqual(plan.leading[i] ? hug.minX : hug.maxX, plan.leading[i] ? plan.texts[i].minX : plan.texts[i].maxX,
                           accuracy: 0.01)
            // Its lines: the date's, then the sentence's two, each at the dot's side and inside the text.
            let lines = JourneyRoad.lines(of: hug, head: CGSize(width: 90, height: 22), widths: [widths[i] - 2, 120],
                                          leading: plan.leading[i])
            XCTAssertEqual(lines.count, 3)
            for (k, line) in lines.enumerated() {
                XCTAssertTrue(hug.insetBy(dx: -0.01, dy: -0.01).contains(line), "line \(k) of text \(i)")
                XCTAssertEqual(plan.leading[i] ? line.minX : line.maxX, plan.leading[i] ? hug.minX : hug.maxX, accuracy: 0.01)
                if k > 0 { XCTAssertGreaterThan(line.minY, lines[k - 1].minY) }
            }
            XCTAssertEqual(lines[0].width, 90, accuracy: 0.01)
            XCTAssertEqual(lines[2].width, 121, accuracy: 0.01)
            let dot = plan.dots[i], seed = "aic:27992spill\(i)"
            let spill = JourneyRoad.spill(under: lines, from: dot, line: plan.line, width: 350, height: plan.height, seed: seed)
            // The stain is the text's own lines with room round them, run into one.
            XCTAssertEqual(spill.lines.count, lines.count)
            for (k, line) in lines.enumerated() {
                XCTAssertTrue(spill.lines[k].contains(line), "line \(k) of text \(i)")
                XCTAssertGreaterThanOrEqual(spill.lines[k].minX, -13)
                XCTAssertLessThanOrEqual(spill.lines[k].maxX, 363)
                if k > 0 { XCTAssertGreaterThan(spill.lines[k - 1].maxY, spill.lines[k].minY) }
            }
            XCTAssertEqual(spill.bottom, spill.lines[2].maxY, accuracy: 0.01)
            XCTAssertTrue(spill.lines.allSatisfy { spill.box.insetBy(dx: -0.01, dy: -0.01).contains($0) })
            // The way out of the dot: from the dot itself into the stain, each drop over the next.
            let first = try XCTUnwrap(spill.way.first), last = try XCTUnwrap(spill.way.last)
            XCTAssertEqual(first.at.x, dot.x, accuracy: 0.01)
            XCTAssertEqual(first.at.y, dot.y, accuracy: 0.01)
            XCTAssertTrue(spill.lines.contains { $0.contains(last.at) })
            for (a, b) in zip(spill.way, spill.way.dropFirst()) {
                XCTAssertLessThan(hypot(b.at.x - a.at.x, b.at.y - a.at.y), a.radius + b.radius)
            }
            // The paint has the whole stain to go: as far as its far corner.
            XCTAssertGreaterThanOrEqual(spill.reach, hypot(spill.box.midX - dot.x, spill.box.midY - dot.y))
            // Not much runs down: one drip at most, a short one, and never onto the line.
            XCTAssertLessThanOrEqual(spill.drips.count, 1)
            for drip in spill.drips {
                XCTAssertLessThan(drip.from.y, spill.bottom)
                XCTAssertGreaterThanOrEqual(drip.to.y - drip.from.y, 6)
                XCTAssertLessThanOrEqual(drip.to.y - drip.from.y, 17.01)
                let under = plan.line.filter { abs($0.x - drip.from.x) < 9 && $0.y > drip.from.y - 4 }.map(\.y).min()
                if let under { XCTAssertGreaterThanOrEqual(under - drip.to.y, 7.99) }
            }
            // The field the paint is made of has room for all of it.
            XCTAssertTrue(spill.frame.contains(spill.box))
            XCTAssertTrue(spill.frame.contains(dot))
            for drop in spill.bulges + spill.way {
                XCTAssertGreaterThan(drop.at.x - drop.radius, spill.frame.minX + JourneyRoad.spillRoom - 0.01)
                XCTAssertLessThan(drop.at.y + drop.radius, spill.frame.maxY - JourneyRoad.spillRoom + 0.01)
            }
            // The same stain for the same seed, however often the view asks.
            XCTAssertEqual(JourneyRoad.spill(under: lines, from: dot, line: plan.line, width: 350, height: plan.height,
                                             seed: seed), spill)
        }
        // A text with nothing known of its lines has its stain under all of it.
        XCTAssertEqual(JourneyRoad.lines(of: plan.hugs[0], head: nil, widths: [], leading: true), [plan.hugs[0]])
    }

    func testThePenGoesAheadAndAStopBeginsAtTheMiddleOfTheScreen() throws {
        // 22:18: „ich pojawienie powinno być nie na dole a na środku
        // ekranu w trakcie przewijania”; 2026-11-11 08:29: „kreska maluje
        // się trochę szybciej niż powstają plamy i teksty (czyli rysuje
        // się niżej na ekranie)”.
        let plan = try road()
        let marks = RoadMarks(plan)
        XCTAssertEqual(marks.dots, plan.dots.map(\.y))
        XCTAssertEqual(marks.feet, plan.texts.map(\.maxY))
        // The tip of the line is under the middle of the screen, and never past the road's end.
        XCTAssertEqual(marks.target(mid: 100), 100 + RoadMarks.ahead)
        XCTAssertEqual(marks.target(mid: 99_999), marks.full)
        XCTAssertGreaterThan(marks.full, plan.height)
        // A stop begins with its dot up at the middle of the screen and the line drawn through it.
        let dot = marks.dots[1]
        XCTAssertFalse(marks.due(1, mid: dot - 40, pen: dot + 100))
        XCTAssertFalse(marks.due(1, mid: dot + 5, pen: dot - 1))
        XCTAssertTrue(marks.due(1, mid: dot + 5, pen: dot + 100))
        XCTAssertTrue(marks.due(1, mid: dot - 5, pen: dot + 4))
        // 08:55: „najpierw pojawia się kropka, a z niej po chwili wylewa
        // się… plama pod tekst”, and the text on the stain after that.
        XCTAssertGreaterThan(RoadMarks.clock.spill, 0.3)
        XCTAssertGreaterThan(RoadMarks.clock.text, RoadMarks.clock.spill)
        XCTAssertLessThan(RoadMarks.clock.text + RoadMarks.clock.emerge, RoadMarks.clock.dry)
    }

    @MainActor
    func testStopsBeginOneAfterAnotherAsTheScreenComesToThem() throws {
        let plan = try road(), marks = RoadMarks(plan)
        XCTAssertGreaterThan(plan.height, 500)
        let reveal = RoadReveal()
        reveal.lay(marks, still: false)
        XCTAssertTrue(reveal.settled)
        // The top of the road on screen: its middle 150 pt down the road.
        reveal.look(CGRect(x: 0, y: -100, width: 350, height: 500))
        XCTAssertFalse(reveal.settled)
        var now = Date(), began: [Int: Int] = [:]
        func run(_ seconds: Int) {
            for frame in 0..<(60 * seconds) {
                now += 1.0 / 60
                reveal.tick(now)
                XCTAssertLessThanOrEqual(reveal.thick, reveal.pen)
                for i in marks.dots.indices where reveal.age(i) >= 0 && began[i] == nil { began[i] = frame }
            }
        }
        run(12)
        // The pen has gone ahead of the middle of the screen and the line has thickened up to it.
        XCTAssertEqual(reveal.pen, 150 + RoadMarks.ahead, accuracy: 0.01)
        XCTAssertEqual(reveal.thick, reveal.pen, accuracy: 0.01)
        // The stops above the middle have begun, in turn and not all at once; the rest wait.
        for i in marks.dots.indices {
            if marks.dots[i] <= 150 {
                XCTAssertEqual(reveal.age(i), RoadMarks.clock.dry, "stop \(i)")
            } else if marks.dots[i] > 150 + RoadMarks.near {
                XCTAssertLessThan(reveal.age(i), 0, "stop \(i)")
            }
        }
        XCTAssertNotNil(began[0])
        for i in 1..<marks.dots.count {
            guard let this = began[i], let before = began[i - 1] else { continue }
            XCTAssertGreaterThanOrEqual(this - before, 17, "stop \(i)")
        }
        XCTAssertTrue(reveal.settled)
        // Scrolled on: it moves again.
        reveal.look(CGRect(x: 0, y: 100, width: 350, height: 500))
        XCTAssertFalse(reveal.settled)
        // With the end of the road on screen and the page at rest, all of
        // it is drawn; what is over the top of the screen is there at once.
        reveal.look(CGRect(x: 0, y: plan.height - 300, width: 350, height: 500))
        XCTAssertEqual(reveal.age(0), RoadMarks.clock.dry)
        XCTAssertGreaterThanOrEqual(reveal.pen, plan.height - 380)
        run(14)
        XCTAssertEqual(reveal.pen, marks.full, accuracy: 0.01)
        XCTAssertEqual(reveal.thick, marks.full, accuracy: 0.01)
        XCTAssertTrue(marks.dots.indices.allSatisfy { reveal.age($0) == RoadMarks.clock.dry })
        XCTAssertTrue(reveal.settled)
    }

    @MainActor
    func testWithReducedMotionTheRoadIsThereAtOnce() throws {
        let plan = try road(), marks = RoadMarks(plan)
        let reveal = RoadReveal()
        reveal.lay(marks, still: true)
        reveal.look(CGRect(x: 0, y: -100, width: 350, height: 500))
        XCTAssertEqual(reveal.pen, marks.full)
        XCTAssertEqual(reveal.thick, marks.full)
        XCTAssertTrue(marks.dots.indices.allSatisfy { reveal.age($0) == RoadMarks.clock.dry })
        XCTAssertTrue(reveal.settled)
    }

    func testTheArcsCanBeGentlerAllTheWay() throws {
        // The other one of the two (22:21: „łuki mogą być trochę
        // łagodniejsze, bliżej środka strony (nie sięgać tak bardzo na
        // boki)”), kept for a change of mind.
        let heights: [CGFloat] = [54, 74, 54, 54, 54, 54, 54, 74, 74]
        let seas = [false, false, false, false, false, false, false, true, false]
        for seed in ["aic:27992", "aic:1", "x"] {
            let plan = try XCTUnwrap(JourneyRoad.plan(width: 350, heights: heights, seas: seas, seed: seed, arcs: .soft))
            let xs = plan.line.map(\.x)
            XCTAssertGreaterThan(xs.min() ?? 0, 30, seed)
            XCTAssertLessThan(xs.max() ?? 0, 320, seed)
            XCTAssertLessThan(xs.min() ?? 0, 80, seed)
            XCTAssertGreaterThan(xs.max() ?? 0, 270, seed)
            for text in plan.texts {
                let near = plan.line.map { p in
                    hypot(max(text.minX - p.x, 0, p.x - text.maxX), max(text.minY - p.y, 0, p.y - text.maxY))
                }.min() ?? 0
                XCTAssertGreaterThanOrEqual(near, 5, seed)
            }
        }
    }

    func testThePenHurriesWhenItIsFarBehindAndTheFullWidthFollows() {
        // Far behind, the pen hurries; close, it keeps its pace and stops at its target.
        let far = RoadMarks.advance(pen: 0, thick: 0, target: 900, passed: 0.1)
        XCTAssertEqual(far.pen, 100, accuracy: 0.01)
        let close = RoadMarks.advance(pen: 594, thick: 0, target: 600, passed: 0.01)
        XCTAssertEqual(close.pen, 594 + RoadMarks.pace.pen * 0.01, accuracy: 0.01)
        XCTAssertEqual(RoadMarks.advance(pen: 599, thick: 0, target: 600, passed: 0.1).pen, 600)
        // The full width follows (2026-11-11: „cieńszą kreską i potem grubnie”) and never passes the pen.
        XCTAssertEqual(far.thick, 100 / RoadMarks.lag.thick * 0.1, accuracy: 0.01)
        XCTAssertEqual(RoadMarks.advance(pen: 600, thick: 599, target: 600, passed: 0.1).thick, 600)
        // With the page at rest, both come to it and stay.
        var state = (pen: CGFloat(-50), thick: CGFloat(-50)), frames = 0, thin: CGFloat = 0
        while state.pen < 400 || state.thick < 400, frames < 6000 {
            state = RoadMarks.advance(pen: state.pen, thick: state.thick, target: 400, passed: 1.0 / 60)
            XCTAssertLessThanOrEqual(state.thick, state.pen)
            thin = max(thin, state.pen - state.thick)
            frames += 1
        }
        // A good stretch of the line is thin behind the pen, for a few seconds, not for a moment and not for long.
        XCTAssertGreaterThan(thin, 60)
        XCTAssertGreaterThan(frames, 2 * 60)
        XCTAssertLessThan(frames, 8 * 60)
        let rest = RoadMarks.advance(pen: state.pen, thick: state.thick, target: 400, passed: 1.0 / 60)
        XCTAssertEqual(rest.pen, 400)
        XCTAssertEqual(rest.thick, 400)
    }

    func testADotGrowsALittleTooBigAndSettles() {
        // In seconds since its stop began.
        XCTAssertEqual(JourneyRoad.pop(-1), 0, accuracy: 0.001)
        XCTAssertEqual(JourneyRoad.pop(0), 0, accuracy: 0.001)
        XCTAssertLessThan(JourneyRoad.pop(0.02), 0.3)
        XCTAssertGreaterThan(JourneyRoad.pop(0.3), 1.05)
        XCTAssertEqual(JourneyRoad.pop(0.42), 1, accuracy: 0.001)
        XCTAssertEqual(JourneyRoad.pop(5), 1, accuracy: 0.001)
        XCTAssertEqual(JourneyRoad.ease(0.5), 0.5, accuracy: 0.001)
    }

    func testTheNibSpattersOnlyAtTurns() throws {
        // 08:55: „Za dużo małych kropeczek… jak przy zbyt szybkim
        // rysowaniu stalówką. Np. tylko przy zakrętach, mogą być po chwili
        // korygowane białym korektorem”.
        let plan = try road(), last = plan.dots[plan.dots.count - 1]
        XCTAssertGreaterThan(plan.turns.count, 4)
        XCTAssertTrue(plan.turns.allSatisfy { $0 >= 0 && $0 < plan.line.count })
        let ink = JourneyRoad.spatter(along: plan.line, turns: plan.turns, until: last, seed: "aic:27992")
        XCTAssertFalse(ink.specks.isEmpty)
        XCTAssertLessThanOrEqual(ink.specks.count, 6 * plan.turns.count)
        for speck in ink.specks {
            // At a turn, beside the line and not on it.
            let turn = plan.turns.map { hypot(plan.line[$0].x - speck.at.x, plan.line[$0].y - speck.at.y) }.min() ?? 999
            XCTAssertLessThan(turn, 50)
            let away = plan.line.map { hypot($0.x - speck.at.x, $0.y - speck.at.y) }.min() ?? 0
            XCTAssertGreaterThan(away, 2.5)
            XCTAssertLessThan(away, 17)
            // Fine, and longer the way it was flung.
            XCTAssertGreaterThanOrEqual(speck.short, 0.3)
            XCTAssertLessThanOrEqual(speck.short, 1)
            XCTAssertGreaterThanOrEqual(speck.long, speck.short)
            XCTAssertLessThanOrEqual(speck.long, 2.31)
        }
        // The corrector's white: fewer dabs than turns, each a closed patch beside the line.
        XCTAssertLessThan(ink.dabs.count, plan.turns.count)
        for dab in ink.dabs {
            XCTAssertGreaterThan(dab.count, 5)
            let far = dab.map { p in plan.line.map { hypot($0.x - p.x, $0.y - p.y) }.min() ?? 99 }.max() ?? 99
            XCTAssertLessThan(far, 12)
        }
        // The same every time, and nothing on a stain.
        XCTAssertEqual(JourneyRoad.spatter(along: plan.line, turns: plan.turns, until: last, seed: "aic:27992").specks, ink.specks)
        let all = CGRect(x: -100, y: -100, width: 600, height: plan.height + 200)
        let none = JourneyRoad.spatter(along: plan.line, turns: plan.turns, until: last, seed: "aic:27992", off: [all])
        XCTAssertTrue(none.specks.isEmpty)
        XCTAssertTrue(none.dabs.isEmpty)
    }

    func testTheLineIsThinAtThePenAndFullBehindIt() throws {
        // 08:29: „cieńszą kreską i potem grubnie… nierównego tuszu”.
        let plan = try road(), last = plan.dots[plan.dots.count - 1]
        let flow = JourneyRoad.inkFlow(plan.line.count, seed: "aic:27992")
        XCTAssertEqual(flow.count, plan.line.count)
        XCTAssertTrue(flow.allSatisfy { $0 > 0.6 && $0 < 1.15 })
        XCTAssertGreaterThan(Set(flow.map { ($0 * 100).rounded() }).count, 5)
        XCTAssertEqual(JourneyRoad.inkFlow(plan.line.count, seed: "aic:27992"), flow)
        func gap(_ a: CGPoint, _ b: CGPoint) -> CGFloat { hypot(a.x - b.x, a.y - b.y) }
        // The pen half way down, the full width 120 pt behind it.
        let mid = plan.height / 2
        let tip = JourneyRoad.tip(of: plan.line, flow: flow, until: last, pen: mid, thick: mid - 120)
        let count = tip.outline.count
        XCTAssertGreaterThan(count, 2 * 60)
        XCTAssertEqual(count % 2, 0)
        // A hairline at the pen, the nib's width where it meets the full line.
        XCTAssertLessThan(gap(tip.outline[count / 2 - 1], tip.outline[count / 2]), 0.01)
        XCTAssertGreaterThan(gap(tip.outline[0], tip.outline[count - 1]), JourneyRoad.nib * 0.6)
        XCTAssertLessThan(gap(tip.outline[0], tip.outline[count - 1]), JourneyRoad.nib * 1.15)
        XCTAssertTrue(tip.outline.allSatisfy { $0.y <= mid + 1 })
        // The full line is shown down to where the thin stretch begins.
        XCTAssertLessThanOrEqual(tip.full, mid - 120)
        XCTAssertGreaterThan(tip.full, mid - 160)
        // Even with the full width right behind the pen the very tip is thin.
        let close = JourneyRoad.tip(of: plan.line, flow: flow, until: last, pen: mid, thick: mid)
        XCTAssertGreaterThanOrEqual(close.outline.count, 2 * (JourneyRoad.taper + 1))
        XCTAssertLessThan(close.full, mid)
        // Nothing before the pen has started, and at the end the line is full to its last point.
        let none = JourneyRoad.tip(of: plan.line, flow: flow, until: last, pen: plan.line[0].y - 20, thick: plan.line[0].y - 20)
        XCTAssertTrue(none.outline.isEmpty)
        XCTAssertLessThan(none.full, plan.line[0].y)
        let done = JourneyRoad.tip(of: plan.line, flow: flow, until: last, pen: plan.height + 60, thick: plan.height + 60)
        XCTAssertTrue(done.outline.isEmpty)
        XCTAssertGreaterThan(done.full, last.y)
    }

    func testShortWhiteTouchesLieAtTheLineAndKeepOffTheStains() throws {
        // 08:29: „małych korekt białym przy linii”.
        let plan = try road(), last = plan.dots[plan.dots.count - 1]
        let touches = JourneyRoad.corrections(along: plan.line, until: last, seed: "aic:27992", fine: true)
        XCTAssertFalse(touches.isEmpty)
        XCTAssertEqual(touches.count % 2, 0)
        for touch in touches {
            XCTAssertGreaterThanOrEqual(touch.count, 6)
            XCTAssertLessThanOrEqual(touch.count, 24)
            let far = touch.map { p in plan.line.map { hypot($0.x - p.x, $0.y - p.y) }.min() ?? 99 }.max() ?? 99
            XCTAssertLessThan(far, 11.5)
        }
        // On dark paint white would be a bright dash by the text: none there, long or short.
        let all = CGRect(x: -100, y: -100, width: 600, height: plan.height + 200)
        XCTAssertTrue(JourneyRoad.corrections(along: plan.line, until: last, seed: "aic:27992", fine: true, off: [all]).isEmpty)
        XCTAssertTrue(JourneyRoad.corrections(along: plan.line, until: last, seed: "aic:27992", off: [all]).isEmpty)
    }

    func testWhiteLiesBesideTheLineAndRoundTheLastDot() throws {
        let plan = try road(), last = plan.dots[plan.dots.count - 1]
        let strokes = JourneyRoad.corrections(along: plan.line, until: last, seed: "aic:27992")
        // Each is a few bristles of a dry brush.
        XCTAssertGreaterThanOrEqual(strokes.count, 2 * JourneyRoad.bristles)
        XCTAssertEqual(strokes.count % JourneyRoad.bristles, 0)
        for stroke in strokes {
            // Each keeps to the line: never further than two nibs from it.
            let far = stroke.map { p in plan.line.map { hypot($0.x - p.x, $0.y - p.y) }.min() ?? 99 }.max() ?? 99
            XCTAssertLessThan(far, 11.5)
            XCTAssertGreaterThan(stroke.count, 24)
            // Ragged (19:08: „trochę bardziej poszarpane”): the edge is torn
            // from one point to the next, not a smooth curve.
            let half = stroke.count / 2
            let turns = (1..<(half - 1)).filter { q in
                let a = stroke[q - 1], b = stroke[q], c = stroke[q + 1]
                return abs((b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x)) > 0.15
            }
            XCTAssertGreaterThan(turns.count, half / 3)
        }
        // The bristles of one stroke do not all start and end together.
        let lengths = Set(strokes.prefix(JourneyRoad.bristles).map(\.count))
        XCTAssertGreaterThan(lengths.count, 1)
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
        // With the lines, how wide each is: a stop's stain keeps to them.
        let set = JourneyRoad.setting(text, width: 193)
        XCTAssertEqual(set.text, JourneyRoad.broken(text, width: 193))
        XCTAssertEqual(set.lines.count, 3)
        XCTAssertTrue(set.lines.allSatisfy { $0 > 20 && $0 <= 193 })
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
