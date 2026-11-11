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
        // The branch is inked in short strokes by hand (2026-11-11 09:44:
        // „Kreskowana linia… musi wyglądać realistyczniej i powstawać
        // (rysować) się kreseczkami”): no two alike, none over its dot.
        let strokes = JourneyRoad.hand(way, until: stop, seed: "aic:27992hand2")
        XCTAssertGreaterThan(strokes.count, 3)
        XCTAssertGreaterThan(Set(strokes.map(\.way.count)).count, 1)
        XCTAssertGreaterThan(Set(strokes.map { ($0.wide * 100).rounded() }).count, 2)
        func across(_ outline: [CGPoint], _ j: Int) -> CGFloat {
            let other = outline[outline.count - 1 - j]
            return hypot(outline[j].x - other.x, outline[j].y - other.y)
        }
        for stroke in strokes {
            XCTAssertGreaterThanOrEqual(stroke.way.count, 5)
            XCTAssertLessThanOrEqual(stroke.way.count, 13)
            let whole = stroke.outline(1)
            XCTAssertEqual(whole.count, 2 * stroke.way.count)
            XCTAssertTrue(whole.allSatisfy { hypot($0.x - stop.x, $0.y - stop.y) > 3.6 })
            // Thin where the pen came down, pressed in the middle, never wider than the road's line.
            XCTAssertGreaterThan(across(whole, whole.count / 4), across(whole, 0))
            XCTAssertLessThan(across(whole, whole.count / 4), 3.7)
            // Drawn from its start: half way it is half as long.
            let half = stroke.outline(0.5)
            XCTAssertLessThan(half.count, whole.count)
            XCTAssertEqual(half[0].x, whole[0].x, accuracy: 0.001)
            XCTAssertEqual(half[0].y, whole[0].y, accuracy: 0.001)
            XCTAssertGreaterThanOrEqual(stroke.outline(0).count, 4)
        }
        // One after another along the branch, the pen lifted in between.
        for (a, b) in zip(strokes, strokes.dropFirst()) {
            let gap = hypot(b.way[0].x - a.way[a.way.count - 1].x, b.way[0].y - a.way[a.way.count - 1].y)
            XCTAssertGreaterThan(gap, 3)
            XCTAssertLessThan(gap, 8)
        }
        XCTAssertEqual(JourneyRoad.hand(way, until: stop, seed: "aic:27992hand2"), strokes)
        XCTAssertEqual(Array(JourneyRoad.hands(of: plan, seed: "aic:27992").keys), [2])
        // The stop waits for its branch: a stroke after a stroke, then its dot.
        XCTAssertEqual(RoadMarks.lead(dashes: 0), 0)
        XCTAssertEqual(RoadMarks.lead(dashes: strokes.count),
                       CGFloat(strokes.count) * RoadMarks.dash.apart + RoadMarks.dash.rest, accuracy: 0.0001)
        XCTAssertLessThanOrEqual(RoadMarks.dash.takes, RoadMarks.dash.apart)
        let marks = RoadMarks(plan, leads: [0, 0, RoadMarks.lead(dashes: strokes.count), 0, 0])
        XCTAssertEqual(marks.whole(1), RoadMarks.clock.dry)
        XCTAssertEqual(marks.whole(2), RoadMarks.clock.dry + marks.lead(2), accuracy: 0.0001)
        // 09:44: „okrąg musi się rysować po plamie… od początku do końca”:
        // the loop comes when the stain is there and the text is coming up.
        XCTAssertGreaterThan(RoadMarks.loop.at, RoadMarks.clock.spill + 1)
        XCTAssertLessThan(RoadMarks.loop.at + RoadMarks.loop.takes, RoadMarks.clock.dry)
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
            XCTAssertTrue(spill.into.contains(last.at))
            XCTAssertTrue(spill.lines.contains(spill.into))
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
        // A short line between two long ones is not a deep notch in the stain's side.
        let long = CGRect(x: 100, y: 0, width: 200, height: 20)
        let notched = JourneyRoad.spill(under: [long, CGRect(x: 100, y: 20, width: 60, height: 20), long.offsetBy(dx: 0, dy: 40)],
                                        from: CGPoint(x: 95, y: 5), line: [], width: 350, height: 400, seed: "notch")
        XCTAssertGreaterThanOrEqual(notched.lines[1].maxX,
                                    min(notched.lines[0].maxX, notched.lines[2].maxX) - JourneyRoad.notch - 0.01)
        XCTAssertLessThan(notched.lines[1].maxX, notched.lines[0].maxX)
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
        // 2026-11-11 11:56: „cienka kreska może się zaczyna rysować
        // wcześniej, prawie u dołu ekranu. Podobnie plamy pod teksty,
        // trochę wcześniej niż teraz.” On a phone, where the bars leave
        // 676 points of the screen, the tip is drawn just over the tab
        // bar; on a low screen as before.
        XCTAssertEqual(RoadMarks.reach(screen: 676), 318)
        XCTAssertEqual(RoadMarks.reach(screen: 500), 230)
        XCTAssertEqual(RoadMarks.reach(screen: 400), RoadMarks.ahead)
        XCTAssertEqual(marks.target(mid: 100, ahead: 337), 437)
        // A stop begins with its dot a little under the middle of the
        // screen, well over the tip of the line, and the line drawn through it.
        XCTAssertGreaterThanOrEqual(RoadMarks.near, 60)
        XCTAssertLessThan(RoadMarks.near, RoadMarks.ahead - 60)
        XCTAssertGreaterThan(RoadMarks.back, RoadMarks.near + 20)
        let dot = marks.dots[1]
        XCTAssertFalse(marks.due(1, mid: dot - RoadMarks.near - 30, pen: dot + 100))
        XCTAssertFalse(marks.due(1, mid: dot + 5, pen: dot - 1))
        XCTAssertTrue(marks.due(1, mid: dot + 5, pen: dot + 100))
        XCTAssertTrue(marks.due(1, mid: dot - RoadMarks.near + 5, pen: dot + 4))
        // 08:55: „najpierw pojawia się kropka, a z niej po chwili wylewa
        // się… plama pod tekst”, and the text on the stain after that.
        XCTAssertGreaterThan(RoadMarks.clock.spill, 0.3)
        XCTAssertGreaterThan(RoadMarks.clock.text, RoadMarks.clock.spill)
        XCTAssertLessThan(RoadMarks.clock.text + RoadMarks.clock.emerge, RoadMarks.clock.dry)
    }

    @MainActor
    func testStopsBeginOneAfterAnotherAndAreUndoneWhenThePageGoesBack() throws {
        let plan = try road(), marks = RoadMarks(plan)
        XCTAssertGreaterThan(plan.height, 500)
        let reveal = RoadReveal()
        reveal.lay(marks, still: false)
        XCTAssertTrue(reveal.settled)
        // The top of the road on screen: its middle 150 pt down the road.
        reveal.look(CGRect(x: 0, y: -100, width: 350, height: 500))
        XCTAssertFalse(reveal.settled)
        var now = Date(), began: [Int: Int] = [:], frames = 0
        func run(_ seconds: Int) {
            for _ in 0..<(60 * seconds) {
                now += 1.0 / 60
                frames += 1
                reveal.tick(now)
                XCTAssertLessThanOrEqual(reveal.thick, reveal.pen)
                for i in marks.dots.indices where reveal.drawing(i) >= 0 && began[i] == nil { began[i] = frames }
            }
        }
        func there(_ i: Int) -> Bool { abs(reveal.age(i) - RoadMarks.clock.dry) < 0.0001 }
        run(12)
        // The pen has gone ahead of the middle of the screen and the line has thickened up to it.
        XCTAssertEqual(reveal.pen, 150 + RoadMarks.reach(screen: 500), accuracy: 0.01)
        XCTAssertEqual(reveal.thick, reveal.pen, accuracy: 0.01)
        // The stops above the middle have begun, in turn and not all at once; the rest wait.
        for i in marks.dots.indices {
            if marks.dots[i] <= 150 {
                XCTAssertTrue(there(i), "stop \(i)")
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
        XCTAssertTrue(there(0))
        XCTAssertGreaterThanOrEqual(reveal.pen, plan.height - 380)
        run(14)
        XCTAssertEqual(reveal.pen, marks.full, accuracy: 0.01)
        XCTAssertEqual(reveal.thick, marks.full, accuracy: 0.01)
        XCTAssertTrue(marks.dots.indices.allSatisfy { there($0) })
        XCTAssertTrue(reveal.settled)
        // A bounce at the page's end is not going back: nothing moves.
        reveal.look(CGRect(x: 0, y: plan.height - 330, width: 350, height: 500))
        XCTAssertTrue(reveal.settled)
        // 2026-11-11 09:44: „gdy cofam ekran rysunek niech zanika (czyli
        // odwrócona animacja”. The page goes back to where it was at
        // first: what is under the middle of the screen again goes, not
        // at once, and the line draws back up.
        reveal.look(CGRect(x: 0, y: -100, width: 350, height: 500))
        XCTAssertFalse(reveal.settled)
        let lowest = marks.dots.count - 1
        var before = reveal.age(lowest), pen = reveal.pen
        XCTAssertGreaterThan(marks.dots[lowest], 150 + RoadMarks.back)
        for _ in 0..<12 {
            now += 1.0 / 60
            reveal.tick(now)
            XCTAssertLessThan(reveal.age(lowest), before)
            XCTAssertLessThan(reveal.pen, pen)
            XCTAssertLessThanOrEqual(reveal.thick, reveal.pen)
            (before, pen) = (reveal.age(lowest), reveal.pen)
        }
        XCTAssertGreaterThan(reveal.age(lowest), 0)
        // The line is not drawn back over a stop that is still there.
        XCTAssertGreaterThanOrEqual(reveal.pen, marks.dots[lowest])
        run(8)
        for i in marks.dots.indices {
            if marks.dots[i] <= 150 {
                XCTAssertTrue(there(i), "stop \(i)")
            } else if marks.dots[i] > 150 + RoadMarks.back {
                XCTAssertLessThan(reveal.drawing(i), 0, "stop \(i)")
            }
        }
        XCTAssertEqual(reveal.pen, 150 + RoadMarks.reach(screen: 500), accuracy: 0.01)
        XCTAssertEqual(reveal.thick, reveal.pen, accuracy: 0.01)
        XCTAssertTrue(reveal.settled)
        // And down again: it is drawn again.
        reveal.look(CGRect(x: 0, y: 100, width: 350, height: 500))
        run(12)
        XCTAssertTrue(marks.dots.indices.filter { marks.dots[$0] <= 350 }.allSatisfy { there($0) })
        XCTAssertEqual(reveal.pen, 350 + RoadMarks.reach(screen: 500), accuracy: 0.01)
    }

    func testAStopsClockRunsBackFasterAndThePenDrawsBackUp() {
        // To be there: on to the whole of it and no further.
        XCTAssertEqual(RoadMarks.older(-1, drawn: true, whole: 6, passed: 0.1), 0.1, accuracy: 0.0001)
        XCTAssertEqual(RoadMarks.older(5.95, drawn: true, whole: 6, passed: 0.1), 6)
        // Undone: back, faster the more there is to undo, never slowly, and gone at 0.
        XCTAssertEqual(RoadMarks.older(6, drawn: false, whole: 6, passed: 0.1), 6 - RoadMarks.undo.rate * 0.6, accuracy: 0.0001)
        XCTAssertEqual(RoadMarks.older(1, drawn: false, whole: 6, passed: 0.1), 1 - RoadMarks.undo.slow * 0.1, accuracy: 0.0001)
        XCTAssertEqual(RoadMarks.older(0.1, drawn: false, whole: 6, passed: 0.1), -1)
        XCTAssertEqual(RoadMarks.older(-1, drawn: false, whole: 6, passed: 0.1), -1)
        // All of a stop goes in a second or two: quicker than it came, and not in a blink.
        var age = RoadMarks.clock.dry, frames = 0
        while age >= 0, frames < 6000 {
            age = RoadMarks.older(age, drawn: false, whole: RoadMarks.clock.dry, passed: 1.0 / 60)
            frames += 1
        }
        XCTAssertGreaterThan(frames, 60)
        XCTAssertLessThan(frames, 130)
        // The pen back up to its target, quicker than it goes down, the full width never past it.
        let back = RoadMarks.advance(pen: 600, thick: 600, target: 300, passed: 0.1)
        XCTAssertEqual(back.pen, 600 - 300 / RoadMarks.retreat * 0.1, accuracy: 0.01)
        XCTAssertEqual(back.thick, back.pen)
        XCTAssertEqual(RoadMarks.advance(pen: 301, thick: 290, target: 300, passed: 0.1).pen, 300)
        XCTAssertLessThan(RoadMarks.retreat, RoadMarks.lag.pen)
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
        // And stays, wherever the page goes.
        reveal.look(CGRect(x: 0, y: -400, width: 350, height: 500))
        reveal.tick(Date() + 1)
        XCTAssertEqual(reveal.pen, marks.full)
        XCTAssertTrue(marks.dots.indices.allSatisfy { reveal.age($0) == RoadMarks.clock.dry })
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

    func testWhiteLiesBesideTheLine() throws {
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
    }

    func testTheRoadEndsInABlotOfRedTheBlackRunsInto() throws {
        // 2026-11-11 09:44: „czerwona kropka na końcu także jako plama
        // akwareli, bez białego otoku. Na styku z czernią miesza się jak
        // prawdziwa akwarela”.
        let plan = try road(), end = plan.dots.count - 1, last = plan.dots[end]
        let lines = JourneyRoad.lines(of: plan.hugs.isEmpty ? plan.texts[end] : plan.hugs[end], head: nil, widths: [],
                                      leading: plan.leading[end])
        let spill = JourneyRoad.spill(under: lines, from: last, line: plan.line, width: 350, height: plan.height,
                                      seed: "aic:27992spill\(end)")
        let blot = JourneyRoad.blot(for: spill, line: plan.line, seed: "aic:27992")
        XCTAssertEqual(blot.at, last)
        // The line runs into it from a little way back.
        XCTAssertTrue(plan.line.contains(blot.back))
        let back = hypot(blot.back.x - last.x, blot.back.y - last.y)
        XCTAssertGreaterThan(back, JourneyRoad.blotRadius)
        XCTAssertLessThan(back, JourneyRoad.blotRoom - 4)
        // The last stop's ink comes out of it, into the stain under the text.
        XCTAssertEqual(blot.to, spill.way[spill.way.count - 1].at)
        XCTAssertTrue(blot.into.contains(blot.to))
        XCTAssertTrue(spill.lines.contains(blot.into))
        // Its outline wanders, the same way every time; bigger than a
        // dot, and its field has room for the red that runs along the black.
        XCTAssertEqual(blot.lobes.count, 3)
        XCTAssertTrue(blot.lobes.allSatisfy { $0 >= 0 && $0 <= 2 * .pi })
        XCTAssertEqual(JourneyRoad.blot(for: spill, line: plan.line, seed: "aic:27992"), blot)
        XCTAssertGreaterThan(JourneyRoad.blotRadius, 5.4 * 1.5)
        XCTAssertGreaterThan(JourneyRoad.blotRoom, JourneyRoad.blotRadius * 1.16 + 10 + 4)
        // A road with nothing drawn yet has its blot at the dot all the same.
        XCTAssertEqual(JourneyRoad.blot(for: spill, line: [], seed: "aic:27992").back, last)
    }

    // MARK: "Dalsze losy" as the road going on

    /// The line going on from the road's end into "Dalsze losy": the
    /// heading 36 pt under the road and three later works under it.
    private func goingOn(leading: Bool? = nil) throws
        -> (plan: RoadPlan, heading: CGRect, years: [CGFloat], onward: JourneyRoad.Onward) {
        let plan = try road(), end = plan.dots.count - 1
        let lines = JourneyRoad.lines(of: plan.hugs.isEmpty ? plan.texts[end] : plan.hugs[end], head: nil, widths: [],
                                      leading: plan.leading[end])
        let spill = JourneyRoad.spill(under: lines, from: plan.dots[end], line: plan.line, width: 350, height: plan.height,
                                      seed: "aic:27992spill\(end)")
        let heading = CGRect(x: JourneyRoad.rail + JourneyRoad.lassoPad.side, y: plan.height + JourneyRoad.laterGap,
                             width: 112, height: 24)
        let years = [heading.maxY + 34, heading.maxY + 150, heading.maxY + 270]
        let onward = try XCTUnwrap(JourneyRoad.onward(from: plan.dots[end], past: spill.box, leading: leading ?? plan.leading[end],
                                                      heading: heading, years: years, width: 350, seed: "aic:27992"))
        return (plan, heading, years, onward)
    }

    func testTheLineGoesOnOutOfARingRoundTheBlotRoundTheHeadingAndDownTheLeft() throws {
        // 2026-11-11 10:20: „dodać sekcje „Dalsze losy” jako kontynuację
        // linii Drogi dzieła… kreska przy dalszych losach już prosta z
        // lewej, a informacje po jej prawej stronie. Na pewno zostawiamy
        // nagłówek sekcji Dalsze losy. Więc kreska mogłaby go np
        // „opisywać” i lecieć dalej?”; 10:39: „niech po chwili, na
        // czerwonym kółku robi się okrągłe zakreślenie i to z niego
        // wychodzi dalsza kreska? Kreska przy dalszych losach nie aż tak
        // prosta, z odrobiną lekkości.”
        let (plan, heading, years, onward) = try goingOn()
        let last = plan.dots[plan.dots.count - 1], line = onward.line
        // Once round the blot, clear of it, ending under it.
        XCTAssertGreaterThan(onward.ring, 40)
        let ring = line[0...onward.ring]
        for (k, point) in ring.enumerated() {
            let far = hypot(point.x - last.x, point.y - last.y)
            XCTAssertGreaterThan(far, JourneyRoad.blotRadius + 2, "ring \(k)")
            XCTAssertLessThan(far, JourneyRoad.ringRadius + 4, "ring \(k)")
        }
        XCTAssertLessThan(try XCTUnwrap(ring.map(\.x).min()), last.x - 12)
        XCTAssertGreaterThan(try XCTUnwrap(ring.map(\.x).max()), last.x + 12)
        XCTAssertLessThan(try XCTUnwrap(ring.map(\.y).min()), last.y - 12)
        XCTAssertGreaterThan(try XCTUnwrap(ring.map(\.y).max()), last.y + 12)
        XCTAssertGreaterThan(line[onward.ring].y, last.y + 10)
        XCTAssertLessThan(abs(line[onward.ring].x - last.x), 8)
        // Then the heading, then the later works, in turn; the line ends at the last.
        XCTAssertLessThan(onward.ring, onward.entry)
        XCTAssertLessThan(onward.entry, onward.exit)
        XCTAssertLessThan(onward.exit, onward.marks[0])
        XCTAssertEqual(onward.marks, onward.marks.sorted())
        XCTAssertEqual(Set(onward.marks).count, 3)
        XCTAssertEqual(onward.marks[2], line.count - 1)
        // The loop goes right round the heading and nowhere through it.
        let loop = line[onward.entry...onward.exit]
        XCTAssertLessThan(try XCTUnwrap(loop.map(\.x).min()), heading.minX - 8)
        XCTAssertGreaterThan(try XCTUnwrap(loop.map(\.x).max()), heading.maxX + 8)
        XCTAssertLessThan(try XCTUnwrap(loop.map(\.y).min()), heading.minY - 3)
        XCTAssertGreaterThan(try XCTUnwrap(loop.map(\.y).max()), heading.maxY + 3)
        XCTAssertFalse(loop.contains { heading.insetBy(dx: 1, dy: 1).contains($0) })
        XCTAssertEqual(onward.foot, heading.maxY + JourneyRoad.lassoPad.over, accuracy: 0.001)
        // Each later work's blot is on the line at its year, down the left side.
        for (k, dot) in onward.dots.enumerated() {
            XCTAssertEqual(dot.y, years[k], accuracy: 2.5, "work \(k)")
            XCTAssertEqual(dot.x, JourneyRoad.rail, accuracy: 5.5, "work \(k)")
        }
        // Down the left side the line keeps to the edge, and it is not ruled.
        let rail = line[(onward.exit + 20)...]
        let left = try XCTUnwrap(rail.map(\.x).min()), right = try XCTUnwrap(rail.map(\.x).max())
        XCTAssertGreaterThan(left, 3)
        XCTAssertLessThan(right, 15)
        XCTAssertGreaterThan(right - left, 1)
        // The pen draws it downwards, but for the ring and the loop, which have their own time.
        for k in (onward.ring + 2)..<line.count {
            XCTAssertGreaterThanOrEqual(onward.gate[k], onward.gate[k - 1], "point \(k)")
        }
        XCTAssertEqual(onward.gate[onward.exit], onward.loopY)
        XCTAssertGreaterThan(onward.loopY, heading.minY - 30)
        XCTAssertLessThan(onward.loopY, onward.foot)
        XCTAssertGreaterThan(onward.gate[onward.ring + 1], last.y)
        // The same every time; with the last stop's text on the other side, the other way round.
        XCTAssertEqual(try goingOn().onward, onward)
        let other = try goingOn(leading: !plan.leading[plan.dots.count - 1]).onward
        XCTAssertEqual(other.line[0].x - last.x, last.x - line[0].x, accuracy: 0.5)
        XCTAssertEqual(other.line[10].x - last.x, last.x - line[10].x, accuracy: 0.5)
        XCTAssertEqual(other.line[10].y, line[10].y, accuracy: 0.5)
        XCTAssertEqual(other.marks.count, 3)
        // No heading under the road yet, or no later work: no line.
        XCTAssertNil(JourneyRoad.onward(from: last, past: .zero, leading: true, heading: .null, years: years, width: 350, seed: "x"))
        XCTAssertNil(JourneyRoad.onward(from: last, past: .zero, leading: true, heading: heading, years: [], width: 350, seed: "x"))
        XCTAssertNil(JourneyRoad.onward(from: last, past: .zero, leading: true, heading: heading.offsetBy(dx: 0, dy: -400),
                                        years: years, width: 350, seed: "x"))
    }

    func testTheLineGoingOnIsDrawnAsFarAsThePenTheRingAndTheLoopHaveCome() throws {
        let (plan, _, _, onward) = try goingOn()
        let count = onward.line.count, far = plan.height + 2000
        // Nothing before the ring; the ring by its own time, whatever the pen.
        XCTAssertEqual(onward.tip(pen: -50, ringed: 0, circled: 0), 0)
        XCTAssertEqual(onward.tip(pen: far, ringed: 0, circled: 1), 0)
        XCTAssertEqual(onward.tip(pen: far, ringed: 0.5, circled: 1), Int((CGFloat(onward.ring) * 0.5).rounded()))
        XCTAssertEqual(onward.tip(pen: -50, ringed: 1, circled: 0), onward.ring + 1)
        // Down to the heading with the pen; the loop by its own time; then on down.
        XCTAssertEqual(onward.tip(pen: onward.loopY - 1, ringed: 1, circled: 1), onward.gate.firstIndex { $0 > onward.loopY - 1 })
        XCTAssertLessThanOrEqual(onward.tip(pen: onward.loopY - 1, ringed: 1, circled: 1), onward.entry)
        XCTAssertEqual(onward.tip(pen: far, ringed: 1, circled: 0), onward.entry)
        XCTAssertEqual(onward.tip(pen: far, ringed: 1, circled: 0.5),
                       onward.entry + Int((CGFloat(onward.exit - onward.entry) * 0.5).rounded()))
        XCTAssertEqual(onward.tip(pen: far, ringed: 1, circled: 1), count)
        // Inked with a lighter nib than the road's, and to nothing at its tip.
        XCTAssertLessThan(JourneyRoad.onwardNib, JourneyRoad.nib)
        XCTAssertTrue(onward.outline(tip: 0, thick: far).isEmpty)
        XCTAssertTrue(onward.outline(tip: 1, thick: far).isEmpty)
        let whole = onward.outline(tip: count, thick: far)
        XCTAssertEqual(whole.count, 2 * count)
        let start = hypot(whole[0].x - whole[2 * count - 1].x, whole[0].y - whole[2 * count - 1].y)
        XCTAssertGreaterThan(start, JourneyRoad.onwardNib * 0.4)
        XCTAssertLessThan(start, JourneyRoad.onwardNib * 1.3)
        XCTAssertEqual(hypot(whole[count - 1].x - whole[count].x, whole[count - 1].y - whole[count].y), 0, accuracy: 0.001)
    }

    func testALaterWorksStainPoursOutOfItsBlotAndNothingDripsUnderIt() throws {
        let (_, _, years, onward) = try goingOn()
        // A later work's year and name as they stand to the right of the line.
        let hug = CGRect(x: JourneyRoad.laterInset, y: years[0] - 12, width: 150, height: 44)
        let lines = JourneyRoad.lines(of: hug, head: CGSize(width: 40, height: 22), widths: [150], leading: true)
        XCTAssertEqual(lines.count, 2)
        let shelf = JourneyRoad.shelf(under: lines, width: 350)
        XCTAssertTrue(shelf.allSatisfy { $0.y > hug.maxY })
        var spill = JourneyRoad.Spill()
        for seed in ["a", "b", "c", "d", "e", "f", "g", "h"] {
            spill = JourneyRoad.spill(under: lines, from: onward.dots[0], line: shelf, width: 350, height: hug.maxY + 100, seed: seed)
            // What is told of the work is written right under: nothing drips onto it.
            XCTAssertTrue(spill.drips.isEmpty, seed)
            XCTAssertEqual(spill.dot, onward.dots[0])
            XCTAssertEqual(spill.way.first?.at, onward.dots[0])
        }
        // Its blot: on the line, which runs into it from above and on out of it below.
        let blot = JourneyRoad.blot(on: onward, at: 0, spill: spill, seed: "aic:27992")
        XCTAssertEqual(blot.at, onward.dots[0])
        XCTAssertLessThan(blot.back.y, blot.at.y)
        XCTAssertGreaterThan(try XCTUnwrap(blot.on).y, blot.at.y)
        XCTAssertEqual(blot.to, spill.way[spill.way.count - 1].at)
        XCTAssertTrue(spill.lines.contains(blot.into))
        XCTAssertEqual(blot.lobes.count, 3)
        XCTAssertEqual(JourneyRoad.blot(on: onward, at: 0, spill: spill, seed: "aic:27992"), blot)
        // The line ends at the last later work: nothing goes on out of its blot.
        XCTAssertNil(JourneyRoad.blot(on: onward, at: 2, spill: spill, seed: "aic:27992").on)
        // Smaller than the road's blot, with room for its paint to run in.
        XCTAssertLessThan(JourneyRoad.smallBlot.radius, JourneyRoad.blotRadius)
        XCTAssertGreaterThan(JourneyRoad.smallBlot.room, JourneyRoad.smallBlot.radius * 1.16 + 10)
        XCTAssertLessThan(JourneyRoad.smallBlot.core, JourneyRoad.smallBlot.radius / 2)
    }

    func testALaterWorksNameIsSetInItsOwnFace() {
        let name = "Stephen Sondheim, „Niedziela w parku z George’em”"
        XCTAssertEqual(JourneyRoad.nameWidth(350), 290)
        XCTAssertEqual(JourneyRoad.nameWidth(280), 234)
        let set = JourneyRoad.setting(name, width: 290, plain: JourneyRoad.nameFace, bold: JourneyRoad.nameFace)
        XCTAssertEqual(set.lines.count, 2)
        XCTAssertEqual(set.text.components(separatedBy: "\n").count, 2)
        XCTAssertTrue(set.lines.allSatisfy { $0 <= 290 })
        // Wider than in the face of a stop's sentence: it is bigger and bolder.
        let plain = JourneyRoad.setting(name, width: 2000)
        XCTAssertEqual(plain.lines.count, 1)
        XCTAssertGreaterThan(JourneyRoad.setting(name, width: 2000, plain: JourneyRoad.nameFace, bold: JourneyRoad.nameFace).lines[0],
                             plain.lines[0])
    }

    @MainActor
    func testTheLineWaitsForTheRingAndTheLaterWorksForTheHeading() throws {
        let (plan, _, years, onward) = try goingOn()
        let count = plan.dots.count
        // The last later work ends far down: the page's end is not on screen here.
        let ends = [years[0] + 90, years[1] + 90, years[2] + 700]
        let marks = RoadMarks(plan, onward: onward, ends: ends)
        // After the road's stops: the loop round the heading, then the later works.
        XCTAssertEqual(marks.dots.count, count + 4)
        XCTAssertEqual(marks.feet.count, count + 4)
        XCTAssertEqual(marks.road, plan.height)
        XCTAssertEqual(marks.height, ends[2] + 6)
        XCTAssertEqual(marks.dots[count], onward.loopY)
        XCTAssertEqual(marks.dots[count + 1], onward.dots[0].y)
        XCTAssertEqual(marks.gates, [count - 1: RoadMarks.ring.at + RoadMarks.ring.takes, count: RoadMarks.lasso])
        XCTAssertEqual(marks.after, [count + 1: RoadMarks.lasso])
        XCTAssertGreaterThan(marks.whole(count), RoadMarks.lasso)
        XCTAssertLessThan(marks.whole(count), RoadMarks.clock.dry)
        XCTAssertEqual(marks.whole(count + 1), RoadMarks.clock.dry)
        // A road with nothing under it is as it was; so is one whose later works are not measured yet.
        XCTAssertEqual(RoadMarks(plan).height, plan.height)
        XCTAssertTrue(RoadMarks(plan).gates.isEmpty)
        XCTAssertEqual(RoadMarks(plan, onward: onward, ends: []), RoadMarks(plan))

        let reveal = RoadReveal()
        // The road is laid first, what is under it a moment later.
        reveal.lay(RoadMarks(plan), still: false)
        reveal.lay(marks, still: false)
        let end = marks.dots[count - 1], gate = RoadMarks.ring.at + RoadMarks.ring.takes
        // The road's end a little under the middle of the screen, where a stop begins.
        let first = end - RoadMarks.near + 10
        reveal.look(CGRect(x: 0, y: first - 250, width: 350, height: 500))
        var now = Date()
        func run(_ seconds: Int, _ check: () -> Void) {
            for _ in 0..<(60 * seconds) {
                now += 1.0 / 60
                reveal.tick(now)
                check()
            }
        }
        var held = 0
        run(16) {
            // Until the blot is ringed the line does not go on past it.
            if reveal.age(count - 1) < gate {
                XCTAssertLessThanOrEqual(reveal.pen, end + 6.001)
                if reveal.age(count - 1) >= 0 { held += 1 }
            }
            XCTAssertLessThan(reveal.age(count), 0)
        }
        XCTAssertGreaterThan(held, 100)
        XCTAssertEqual(reveal.age(count - 1), RoadMarks.clock.dry, accuracy: 0.001)
        // Ringed, the line goes on: as far as the heading, which is not at the middle of the screen yet.
        let waiting = min(first + RoadMarks.reach(screen: 500), onward.loopY + 6)
        XCTAssertGreaterThan(waiting, end + 30)
        XCTAssertEqual(reveal.pen, waiting, accuracy: 0.01)
        XCTAssertTrue(reveal.settled)
        // Scrolled on, the second later work where a stop begins: the
        // heading is circled first, and only then do the later works begin.
        let second = years[1] - RoadMarks.near + 10
        reveal.look(CGRect(x: 0, y: second - 250, width: 350, height: 500))
        XCTAssertFalse(reveal.settled)
        var circling = 0
        run(16) {
            if reveal.age(count) < RoadMarks.lasso {
                // Not past the heading until it is circled, and no later work yet.
                XCTAssertLessThanOrEqual(reveal.pen, onward.loopY + 6.001)
                XCTAssertLessThan(reveal.age(count + 1), 0)
                if reveal.age(count) >= 0 { circling += 1 }
            }
        }
        XCTAssertEqual(reveal.pen, second + RoadMarks.reach(screen: 500), accuracy: 0.01)
        XCTAssertGreaterThan(circling, 40)
        XCTAssertEqual(reveal.age(count), marks.whole(count), accuracy: 0.001)
        XCTAssertEqual(reveal.age(count + 1), RoadMarks.clock.dry, accuracy: 0.001)
        XCTAssertEqual(reveal.age(count + 2), RoadMarks.clock.dry, accuracy: 0.001)
        XCTAssertLessThan(reveal.age(count + 3), 0)
        XCTAssertTrue(reveal.settled)
        // The page goes back: the later works and the loop are undone, the ring stays.
        reveal.look(CGRect(x: 0, y: first - 250, width: 350, height: 500))
        run(8) {}
        XCTAssertLessThan(reveal.age(count + 1), 0)
        XCTAssertLessThan(reveal.age(count), 0)
        XCTAssertEqual(reveal.age(count - 1), RoadMarks.clock.dry, accuracy: 0.001)
        XCTAssertEqual(reveal.pen, waiting, accuracy: 0.01)
        XCTAssertTrue(reveal.settled)
        // "Ogranicz ruch": all of it at once.
        let still = RoadReveal()
        still.lay(marks, still: true)
        still.look(CGRect(x: 0, y: 0, width: 350, height: 500))
        XCTAssertEqual(still.pen, marks.full)
        XCTAssertTrue(marks.dots.indices.allSatisfy { still.drawing($0) == marks.whole($0) })
        XCTAssertTrue(still.settled)
    }

    @MainActor
    func testTheRoadIsLaidOutAsTheViewLastWorkedItOut() async throws {
        // What is under the road is measured in several steps, more than
        // one in a frame: the road is laid out as at the last of them (the
        // later works never came: it had stayed as at an earlier one).
        let (plan, _, years, onward) = try goingOn()
        let count = plan.dots.count
        let marks = RoadMarks(plan, onward: onward, ends: years.map { $0 + 90 })
        let reveal = RoadReveal()
        reveal.expect(nil, still: false)
        reveal.expect(RoadMarks(plan), still: false)
        reveal.expect(RoadMarks(plan, onward: onward, ends: years.map { $0 + 400 }), still: false)
        reveal.expect(marks, still: false)
        // Not while the view is being worked out: a moment later.
        XCTAssertTrue(reveal.stops.isEmpty)
        for _ in 0..<200 where reveal.stops.count != count + 4 { try await Task.sleep(for: .milliseconds(5)) }
        XCTAssertEqual(reveal.stops.count, count + 4)
        // Everything on screen and the page at rest: the later works come, where they are now.
        reveal.look(CGRect(x: 0, y: marks.height - 480, width: 350, height: 500))
        var now = Date()
        for _ in 0..<(60 * 20) {
            now += 1.0 / 60
            reveal.tick(now)
        }
        XCTAssertEqual(reveal.age(count + 3), RoadMarks.clock.dry, accuracy: 0.001)
        XCTAssertEqual(reveal.pen, marks.full, accuracy: 0.01)
        XCTAssertTrue(reveal.settled)
    }

    func testASeaIsAWashTheLineIsDrawnInto() throws {
        // 2026-11-11 11:09, of sketch 26: „Morze - super - wdrażamy.”
        let plan = try road()
        let band = JourneyRoad.seaBand(before: 7, on: plan)
        XCTAssertEqual(band.top, plan.texts[6].maxY + 16)
        XCTAssertEqual(band.bottom, plan.texts[7].minY - 14)
        XCTAssertGreaterThan(band.bottom - band.top, 40)
        let wash = try XCTUnwrap(JourneyRoad.wash(top: band.top, bottom: band.bottom, line: plan.line, width: 350))
        // Between the stains over and under it, across the road, with room for its uneven edge.
        XCTAssertGreaterThan(wash.box.minY, band.top)
        XCTAssertLessThan(wash.box.maxY, band.bottom)
        XCTAssertEqual(wash.box.minX, 5)
        XCTAssertEqual(wash.box.maxX, 345)
        XCTAssertTrue(wash.frame.insetBy(dx: 12, dy: 12).contains(wash.box))
        // It floods out from where the line comes into it, as far as its furthest corner.
        XCTAssertTrue(plan.line.contains(wash.entry))
        XCTAssertEqual(wash.entry.y, band.top - 4, accuracy: 3)
        XCTAssertGreaterThan(wash.reach, hypot(max(wash.entry.x - wash.box.minX, wash.box.maxX - wash.entry.x), wash.box.height))
        // The line through it, in the wash's own frame, a point in four.
        XCTAssertEqual(wash.points.count % 2, 0)
        XCTAssertGreaterThan(wash.points.count, 40)
        for k in stride(from: 0, to: wash.points.count, by: 2) {
            XCTAssertGreaterThanOrEqual(wash.points[k], 0, "point \(k / 2)")
            XCTAssertLessThanOrEqual(CGFloat(wash.points[k]), wash.frame.width, "point \(k / 2)")
            XCTAssertGreaterThanOrEqual(wash.points[k + 1], 0, "point \(k / 2)")
            XCTAssertLessThanOrEqual(CGFloat(wash.points[k + 1]), wash.frame.height + 4, "point \(k / 2)")
        }
        let first = CGPoint(x: CGFloat(wash.points[0]) + wash.frame.minX, y: CGFloat(wash.points[1]) + wash.frame.minY)
        let from = try XCTUnwrap(plan.line.firstIndex { hypot($0.x - first.x, $0.y - first.y) < 0.01 })
        let second = plan.line[from + JourneyRoad.washEach]
        XCTAssertEqual(CGFloat(wash.points[2]) + wash.frame.minX, second.x, accuracy: 0.01)
        XCTAssertEqual(CGFloat(wash.points[3]) + wash.frame.minY, second.y, accuracy: 0.01)
        XCTAssertEqual(wash.heights[0], plan.line[from].y)
        // The ink goes on running after the pen has left the sea: the line is followed past it.
        XCTAssertGreaterThan(wash.heights.count, (wash.points.count / 2 - 1) * JourneyRoad.washEach + 60)
        XCTAssertGreaterThan(try XCTUnwrap(wash.heights.last), band.bottom + 22)

        // Laid just before the pen gets there, and all there when the pen is in it.
        XCTAssertEqual(wash.came(pen: band.top - 70).spread, 0)
        XCTAssertGreaterThan(wash.came(pen: band.top - 40).spread, 0)
        XCTAssertEqual(wash.came(pen: band.top - 40).tip, 0)
        XCTAssertEqual(wash.came(pen: band.top + 80).spread, 1, accuracy: 0.001)
        XCTAssertEqual(wash.came(pen: band.bottom + 500).spread, 1.15)
        // Wet while the pen is in it; dry, and soaked into the paper round it, well after.
        XCTAssertEqual(wash.came(pen: band.bottom).dry, 0)
        XCTAssertEqual(wash.came(pen: band.bottom).soak, 0)
        XCTAssertGreaterThan(wash.came(pen: band.bottom + 150).dry, 0.1)
        XCTAssertLessThan(wash.came(pen: band.bottom + 150).dry, 0.9)
        XCTAssertEqual(wash.came(pen: band.bottom + 300).dry, 1)
        XCTAssertEqual(wash.came(pen: band.bottom + 300).soak, 1)
        // The line is drawn into it as far as the pen has come, and undone as the pen goes back.
        var before: CGFloat = -1
        for pen in stride(from: band.top - 30, through: band.bottom + 300, by: 7) {
            let tip = wash.came(pen: pen).tip
            XCTAssertGreaterThanOrEqual(tip, before)
            before = tip
        }
        XCTAssertGreaterThan(wash.came(pen: (band.top + band.bottom) / 2).tip, 10)
        XCTAssertLessThan(wash.came(pen: (band.top + band.bottom) / 2).tip, CGFloat(wash.heights.count - 60))
        XCTAssertEqual(wash.came(pen: band.bottom + 300).tip, CGFloat(wash.heights.count))
        // The same every time; nothing where there is no room for a sea.
        XCTAssertEqual(JourneyRoad.wash(top: band.top, bottom: band.bottom, line: plan.line, width: 350), wash)
        XCTAssertNil(JourneyRoad.wash(top: band.top, bottom: band.top + 40, line: plan.line, width: 350))
        XCTAssertNil(JourneyRoad.wash(top: band.top, bottom: band.bottom, line: [], width: 350))
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
