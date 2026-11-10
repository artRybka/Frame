import SwiftUI

/// "Droga dzieła" (Mateusz 2026-11-10, "S1"; first called "Losy dzieła",
/// too near "Dalsze losy"): how the work went from its maker to where it
/// hangs now, from the museum's provenance, as a drawing of a road. Not a
/// time line (14:51: „nie jak oś czasu, bo tę już mamy”) and not a rhythmic
/// snake (14:59: „droga jako rysowana luźno linia… zamiast ikon kropki”).
/// One line sweeps from side to side down the whole column, the way the
/// stretch over the Atlantic did in the sketch he circled (17:11): long
/// slanted runs and round turns. It is drawn first and no turn is tied to
/// a stop (17:19: „najpierw narysować całą linię i na niej nanieść
/// kropki”): each stop is a dot on a run, and its text hangs in the bay
/// under that run, its corner right at the dot (17:29), so the line never
/// runs into a text and needs no backing. The runs are only as steep as
/// the texts need. The line starts at the first stop and ends under the
/// vermilion seal of the last; over a sea the work crossed it makes two
/// free sweeps among waves. It is inked as with a broad nib held flat
/// (17:59: „przy zakrętach grubsza, jakby rysowana piórem do kaligrafii”):
/// thin along the runs, thick where it turns down. An exhibition the work
/// came back from is a hollow dot. The shape comes from the work's id.
struct JourneyRoad: View {
    let journey: DailyWork.Journey
    /// The work's id: the road's wander.
    let seed: String

    /// How tall each stop's text is at the width the road gives it.
    @State private var heights: [Int: CGFloat] = [:]
    /// How wide the road is.
    @State private var width: CGFloat = 0

    /// A stop this far from the one before has crossed a sea.
    private static let seaKm = 2500.0

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                if !journey.headline.isEmpty {
                    Text(journey.headline)
                        .font(.serif(18, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                }
                if !journey.lead.isEmpty {
                    Text(journey.lead)
                        .font(.serif(16))
                        .foregroundStyle(Theme.inkSoft)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            if !facts.isEmpty { factsRow }
            road
            Text("Źródło: \(journey.source.isEmpty ? "muzeum" : journey.source). Opowiedziane przez Claude Haiku.")
                .font(.caption2)
                .foregroundStyle(Theme.inkSoft)
        }
    }

    // MARK: Facts

    private var facts: [(String, String)] {
        var found: [(String, String)] = []
        if let years = journey.years, years > 0 {
            found.append(("\(years) \(Self.plural(years, "rok", "lata", "lat"))", "w drodze"))
        }
        if let km = journey.km, km > 0 {
            found.append(("\(km.formatted(.number.grouping(.automatic).locale(Locale(identifier: "pl_PL")))) km",
                          journey.fromWhere.isEmpty ? "w linii prostej" : journey.fromWhere))
        }
        if let hands = journey.hands, hands > 1 {
            found.append(("\(hands)", Self.plural(hands, "para rąk", "pary rąk", "par rąk")))
        }
        if let shows = journey.exhibitions, shows > 0 {
            found.append(("\(shows)", Self.plural(shows, "wystawa", "wystawy", "wystaw")))
        }
        return found
    }

    private var factsRow: some View {
        HStack(alignment: .top, spacing: 18) {
            ForEach(facts, id: \.1) { value, label in
                VStack(alignment: .leading, spacing: 1) {
                    Text(value)
                        .font(.serif(19, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                        .monospacedDigit()
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                    Text(label)
                        .font(.caption2)
                        .foregroundStyle(Theme.inkSoft)
                        .lineLimit(1)
                }
            }
        }
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(alignment: .top) { Rectangle().fill(Theme.hairline).frame(height: 1) }
        .overlay(alignment: .bottom) { Rectangle().fill(Theme.hairline).frame(height: 1) }
        .accessibilityElement(children: .combine)
    }

    /// "1 rok", "3 lata", "5 lat", "22 lata".
    static func plural(_ n: Int, _ one: String, _ few: String, _ many: String) -> String {
        if n == 1 { return one }
        let last = n % 10, tens = n % 100
        return (2...4).contains(last) && !(12...14).contains(tens) ? few : many
    }

    // MARK: The road

    private var seas: [Bool] { journey.stops.indices.map(overSea) }

    /// Whether the stop crossed a sea from the one before.
    private func overSea(_ i: Int) -> Bool {
        guard i > 0 else { return false }
        let a = journey.stops[i - 1], b = journey.stops[i]
        guard (a.lat != 0 || a.lon != 0), (b.lat != 0 || b.lon != 0) else { return false }
        return Self.km(a, b) > Self.seaKm
    }

    static func km(_ a: DailyWork.Journey.Stop, _ b: DailyWork.Journey.Stop) -> Double {
        let r = Double.pi / 180
        let h = pow(sin((b.lat - a.lat) * r / 2), 2)
            + cos(a.lat * r) * cos(b.lat * r) * pow(sin((b.lon - a.lon) * r / 2), 2)
        return 2 * 6371 * asin(min(1, sqrt(h)))
    }

    /// The sea's name, when it is plain which one.
    private func sea(_ i: Int) -> String {
        let a = journey.stops[i - 1].lon, b = journey.stops[i].lon
        let (west, east) = (min(a, b), max(a, b))
        if west < -30, east > -30, west > -130, east < 60 { return "Atlantyk" }
        if west < -100, east > 100 { return "Pacyfik" }
        return ""
    }

    private var road: some View {
        let count = journey.stops.count
        let seas = self.seas
        // Worked out here, not in the Canvas: SwiftUI does not redraw a
        // Canvas for state only its drawing closure reads, so the road came
        // out blank whenever the last text was measured after the first draw.
        let measured = (0..<count).compactMap { heights[$0] }
        let plan = measured.count == count ? Self.plan(width: width, heights: measured, seas: seas, seed: seed) : nil
        let textWidth = Self.textWidth(width)
        return ZStack(alignment: .topLeading) {
            ForEach(Array(journey.stops.enumerated()), id: \.offset) { i, stop in
                // Each text is measured where the layout first puts it and
                // then moved to its dot; the move does not change its height.
                row(stop, leading: plan?.leading[i] ?? true)
                    .frame(width: textWidth, alignment: plan?.leading[i] ?? true ? .topLeading : .topTrailing)
                    .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { self.heights[i] = $0 }
                    .offset(x: plan?.texts[i].minX ?? 0, y: plan?.texts[i].minY ?? 0)
                    .opacity(plan == nil ? 0 : 1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .frame(height: plan?.height, alignment: .topLeading)
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { self.width = $0 }
        .background {
            Canvas { context, size in draw(in: &context, size: size, plan: plan, seas: seas) }
                .accessibilityHidden(true)
        }
    }

    private func row(_ stop: DailyWork.Journey.Stop, leading: Bool) -> some View {
        // The date in the hand, always the end of the line that is at the dot
        // (18:04: „czerwone daty zawsze przy kropce. Daty pismem pisanym”):
        // first where the text reads from its dot, last where it ends at it.
        let date = Text(stop.year).font(.hand(21)).foregroundStyle(Theme.vermilion)
        let place = Text(stop.place).font(.caption).foregroundStyle(Theme.inkSoft)
        let between = Text(stop.place.isEmpty ? "" : " · ").font(.caption).foregroundStyle(Theme.inkSoft)
        return VStack(alignment: leading ? .leading : .trailing, spacing: 0) {
            (leading ? Text("\(date)\(between)\(place)") : Text("\(place)\(between)\(date)"))
                .lineLimit(1)
                .truncationMode(leading ? .tail : .head)
            Text(Self.marked(stop.text))
                .font(.serif(15))
                .foregroundStyle(Theme.ink)
                .multilineTextAlignment(leading ? .leading : .trailing)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
    }

    /// The telling words, between ** and **, in bold.
    static func marked(_ text: String) -> AttributedString {
        let options = AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        return (try? AttributedString(markdown: text, options: options)) ?? AttributedString(text)
    }

    // MARK: Drawing

    private func draw(in context: inout GraphicsContext, size: CGSize, plan: RoadPlan?, seas: [Bool]) {
        guard let plan else { return }
        let count = journey.stops.count
        // The seas first, under everything.
        for i in 1..<count where seas[i] {
            var random = SeededRandom(seed + "sea\(i)")
            drawSea(in: &context, name: sea(i), top: plan.texts[i - 1].maxY + 16,
                    bottom: i == count - 1 ? plan.dots[i].y - 30 : plan.texts[i].minY - 14,
                    width: size.width, plan: plan, random: &random)
        }
        // The road, from the first dot to the seal of the last.
        var stroke = Path()
        stroke.addLines(Self.nibStroke(plan.line, until: plan.dots[count - 1], clear: Self.sealClear))
        stroke.closeSubpath()
        context.fill(stroke, with: .color(Theme.ink))
        context.stroke(stroke, with: .color(Theme.ink), style: StrokeStyle(lineWidth: Self.hair, lineJoin: .round))
        // The stops: dots, a hollow one for a side trip, a seal for the last.
        for i in 0..<count {
            let p = plan.dots[i]
            func circle(_ r: CGFloat) -> Path { Path(ellipseIn: CGRect(x: p.x - r, y: p.y - r, width: 2 * r, height: 2 * r)) }
            if i == count - 1 {
                // Where the work is now: a seal, as under a piece of
                // calligraphy (18:04: the dot in a ring did not please).
                let seal = Path(roundedRect: CGRect(x: -7, y: -7, width: 14, height: 14), cornerRadius: 2.2)
                    .applying(CGAffineTransform(translationX: p.x, y: p.y).rotated(by: -7 * .pi / 180))
                context.fill(seal, with: .color(Theme.vermilion))
            } else if journey.stops[i].detour {
                context.fill(circle(5), with: .color(Theme.paper))
                context.stroke(circle(5), with: .color(Theme.ink), lineWidth: 1.7)
            } else {
                context.fill(circle(5.4), with: .color(Theme.ink))
            }
        }
    }

    /// A sea as on a map: rows of short waves that keep clear of the road
    /// and of the texts, and the name between two rows, where there is room.
    private func drawSea(in context: inout GraphicsContext, name: String, top: CGFloat, bottom: CGFloat,
                         width: CGFloat, plan: RoadPlan, random: inout SeededRandom) {
        guard bottom - top > 40 else { return }
        let rows = max(3, Int(((bottom - top) / 30).rounded())), pitch = (bottom - top) / CGFloat(rows - 1)
        func inText(_ p: CGPoint, _ pad: CGFloat) -> Bool {
            plan.texts.contains { $0.insetBy(dx: -pad, dy: -pad).contains(p) }
        }
        var waves = Path()
        for q in 0..<rows {
            let y = top + pitch * CGFloat(q)
            let near = plan.line.filter { abs($0.y - y) < 10 }
            var x = 6 + 40 * random.unit()
            while x < width - 30 {
                let length = min(34 + 60 * random.unit(), width - 6 - x), phase = random.unit() * 6
                var run: [CGPoint] = []
                var u: CGFloat = 0
                while u <= length {
                    let swell = 2 * sin((u / 22 + phase) * 2 * .pi) * min(1, u / 8, (length - u) / 8)
                    let p = CGPoint(x: x + u, y: y + swell)
                    if inText(p, 10) || near.contains(where: { abs($0.x - p.x) < 9 && abs($0.y - p.y) < 7 }) {
                        if run.count > 6 { waves.addLines(run) }
                        run = []
                    } else {
                        run.append(p)
                    }
                    u += 3
                }
                if run.count > 6 { waves.addLines(run) }
                x += length + 14 + 30 * random.unit()
            }
        }
        context.stroke(waves, with: .color(Self.sea.opacity(0.75)),
                       style: StrokeStyle(lineWidth: 1.15, lineCap: .round, lineJoin: .round))
        guard !name.isEmpty else { return }
        var best: CGPoint?, clear: CGFloat = -1
        for q in 0..<(rows - 1) {
            for part in [0.2, 0.32, 0.5, 0.68, 0.8] as [CGFloat] {
                let spot = CGPoint(x: width * part, y: top + pitch * (CGFloat(q) + 0.5))
                if inText(spot, 34) { continue }
                let nearest = plan.line.map { hypot(($0.x - spot.x) / 2.6, $0.y - spot.y) }.min() ?? 0
                if nearest > clear + 1 { (best, clear) = (spot, nearest) }
            }
        }
        if let best {
            context.draw(Text(name).font(.serif(15).italic()).kerning(1.8).foregroundStyle(Theme.inkSoft), at: best)
        }
    }

    private static let sea = Color(light: 0x8FA9BA, dark: 0x5E7A8C)
}

// MARK: Geometry

/// The road worked out: the line, each stop's dot on it, and where each
/// stop's text goes.
struct RoadPlan {
    var line: [CGPoint]
    var dots: [CGPoint]
    var texts: [CGRect]
    /// Whether a text reads from its left edge (its dot is at its left).
    var leading: [Bool]
    var height: CGFloat
}

extension JourneyRoad {
    /// Where the date's figures are in a text (the hand's line is tall):
    /// level with a dot beside it.
    static let yearY: CGFloat = 14
    /// The line stops this short of the last stop, under its seal.
    static let sealClear: CGFloat = 3
    /// The nib's width, how far it is turned from flat, and the thinnest
    /// the stroke gets.
    static let nib: CGFloat = 6.2
    static let nibTilt: CGFloat = -8 * .pi / 180
    static let hair: CGFloat = 1.4

    /// Every text is this wide: a little over half the road, so a run has
    /// room to pass above it and the next one under it.
    static func textWidth(_ width: CGFloat) -> CGFloat { max(120, (width * 0.55).rounded()) }

    /// The road for texts of these heights. `seas[i]`: stop `i` is over a
    /// sea from the one before.
    ///
    /// The line is a hook from the first stop, then runs from side to side:
    /// two free ones over a sea, one for each stop between the first and the
    /// last, and one to the last stop, which hangs on a short drop. A stop's
    /// dot is on its run just past its text's corner, and its text is in the
    /// bay under that run, on the side the run came from. The line is drawn
    /// through the turns alone; then, where a text would not clear the run
    /// under it, that run is made steeper (or its turn sent out to the
    /// edge) and the line drawn again.
    static func plan(width: CGFloat, heights: [CGFloat], seas: [Bool], seed: String) -> RoadPlan? {
        let count = heights.count
        guard count >= 2, seas.count == count, width > 240 else { return nil }
        var random = SeededRandom(seed + "road")
        let textWidth = Self.textWidth(width)
        func x(_ left: Bool, _ fromEdge: CGFloat) -> CGFloat { left ? fromEdge : width - fromEdge }
        struct Run {
            var stop: Int?
            var sea = false
            /// The side its far turn is on.
            var left = false
            var fall: CGFloat = 0
            var inset: CGFloat = 0
            var margin: CGFloat = 0
            var bow: CGFloat = 0
            var turn = CGPoint.zero
        }
        let startLeft = random.next() % 2 == 0
        var runs: [Run] = []
        for k in 1..<count {
            if seas[k] { runs += [Run(sea: true), Run(sea: true)] }
            runs.append(Run(stop: k < count - 1 ? k : nil))
        }
        for i in runs.indices {
            runs[i].left = i % 2 == 1 ? startLeft : !startLeft
            runs[i].fall = runs[i].sea ? 54 + 14 * random.unit() : 58 + 22 * random.unit()
            // Most turns reach the edge; one in three stops short of it.
            runs[i].inset = runs[i].sea ? width * (0.2 + 0.14 * random.unit())
                : 14 + (random.unit() < 0.35 ? 30 + 34 * random.unit() : 22 * random.unit())
            runs[i].margin = 2 + 12 * random.unit()
            runs[i].bow = (random.unit() - 0.5) * 14
        }
        let start = CGPoint(x: x(startLeft, 52 + 10 * random.unit()), y: yearY)
        let hookInset = 16 + 10 * random.unit()
        var hook = max(44, heights[0] + 10), drop: CGFloat = 44
        var result: RoadPlan?
        for _ in 0..<60 {
            var route = [start, CGPoint(x: x(startLeft, hookInset), y: start.y + hook)]
            var y = start.y + hook
            for i in runs.indices {
                let from = route[route.count - 1]
                y += runs[i].fall
                runs[i].turn = CGPoint(x: x(runs[i].left, runs[i].inset), y: y)
                // A point mid-run, a little off the straight: the run bows.
                route.append(CGPoint(x: (from.x + runs[i].turn.x) / 2, y: (from.y + y) / 2 + runs[i].bow))
                route.append(runs[i].turn)
            }
            let endLeft = runs[runs.count - 1].left
            let end = CGPoint(x: x(endLeft, runs[runs.count - 1].inset + 26), y: y + drop)
            route.append(end)
            let line = Self.line(route)
            func index(at y: CGFloat) -> Int {
                var k = 0
                while k < line.count - 1, line[k].y < y { k += 1 }
                return k
            }
            // Where each turn is on the line: the hook's, then each run's.
            let turns = [index(at: route[1].y)] + runs.map { index(at: $0.turn.y) }
            /// The lowest and the highest the line is over a stretch of x, between two samples.
            func lowest(_ from: Int, _ to: Int, _ x0: CGFloat, _ x1: CGFloat) -> CGFloat? {
                line[from...to].filter { $0.x >= x0 && $0.x <= x1 }.map(\.y).max()
            }
            func highest(_ from: Int, _ to: Int, _ x0: CGFloat, _ x1: CGFloat) -> CGFloat? {
                line[from...to].filter { $0.x >= x0 && $0.x <= x1 }.map(\.y).min()
            }
            var texts = [CGRect](repeating: .zero, count: count)
            var dots = [CGPoint](repeating: .zero, count: count)
            var leading = [Bool](repeating: true, count: count)
            var changed = false
            // The first stop: the line starts at its dot and hooks away from its text.
            do {
                let x0 = startLeft ? start.x + 15 : start.x - 15 - textWidth
                texts[0] = CGRect(x: x0, y: 0, width: textWidth, height: heights[0])
                dots[0] = start
                leading[0] = startLeft
                if let under = highest(turns[0], turns[min(2, turns.count - 1)], x0 - 6, x0 + textWidth + 6),
                   heights[0] + 11 > under {
                    hook += heights[0] + 12 - under
                    changed = true
                }
            }
            for i in runs.indices {
                guard let k = runs[i].stop else { continue }
                // The text is on the open side of the bay: where the run came from.
                let left = !runs[i].left
                let x0 = left ? runs[i].margin : width - runs[i].margin - textWidth, x1 = x0 + textWidth
                let dotX = left ? x1 + 11 : x0 - 11
                var d = turns[i]
                for q in turns[i]...turns[i + 1] where abs(line[q].x - dotX) < abs(line[d].x - dotX) { d = q }
                dots[k] = line[d]
                leading[k] = !left
                let top = (lowest(turns[i], turns[i + 1], x0 - 5, x1 + 5) ?? line[d].y) + 5
                texts[k] = CGRect(x: x0, y: top, width: textWidth, height: heights[k])
                if let under = highest(turns[i + 1], turns[min(i + 3, turns.count - 1)], x0 - 6, x1 + 6),
                   top + heights[k] + 11 > under {
                    let need = top + heights[k] + 12 - under
                    // A tall text first sends its turn out to the edge, and
                    // only then makes the next run steeper.
                    if runs[i + 1].fall + need > 104, runs[i].inset > 16, !runs[i].sea {
                        runs[i].inset = max(14, runs[i].inset - 12)
                    } else {
                        runs[i + 1].fall += need
                    }
                    changed = true
                }
            }
            // The last stop: the line drops to its dot beside its text.
            do {
                let k = count - 1
                let x0 = endLeft ? end.x + 18 : end.x - 18 - textWidth
                texts[k] = CGRect(x: x0, y: end.y - yearY, width: textWidth, height: heights[k])
                dots[k] = end
                leading[k] = endLeft
                if let above = lowest(turns[turns.count - 2], turns[turns.count - 1], x0 - 6, x0 + textWidth + 6),
                   above > texts[k].minY - 8 {
                    drop += above - texts[k].minY + 9
                    changed = true
                }
            }
            result = RoadPlan(line: line, dots: dots, texts: texts, leading: leading,
                              height: max(texts[count - 1].maxY, end.y + 10) + 6)
            if !changed { break }
        }
        return result
    }

    /// The route as one line: a spline through it, a point every 2 pt, and
    /// a soft pass over the whole of it, so every turn is a round one.
    static func line(_ route: [CGPoint]) -> [CGPoint] {
        smooth(even(spline(route, per: 24), step: 2), sigma: 8)
    }

    /// The outline of the line inked with a broad nib: every point of it
    /// moved half the nib each way along the nib. Where the line goes along
    /// the nib the outline closes to nothing, and the hairline drawn round
    /// it is all there is. It stops `clear` short of `until`.
    static func nibStroke(_ line: [CGPoint], until end: CGPoint, clear: CGFloat) -> [CGPoint] {
        var cut = line.count
        while cut > 0, hypot(line[cut - 1].x - end.x, line[cut - 1].y - end.y) < clear { cut -= 1 }
        let dx = cos(nibTilt) * nib / 2, dy = sin(nibTilt) * nib / 2
        let body = line[..<cut]
        return body.map { CGPoint(x: $0.x + dx, y: $0.y + dy) } + body.reversed().map { CGPoint(x: $0.x - dx, y: $0.y - dy) }
    }

    /// Centripetal Catmull-Rom through the points, `per` samples between
    /// each two: smooth, and never a cusp or a knot between close points.
    /// Point `k` is sample `k * per`.
    static func spline(_ points: [CGPoint], per: Int) -> [CGPoint] {
        guard points.count >= 2 else { return points }
        func knot(_ a: CGPoint, _ b: CGPoint) -> CGFloat { max(1e-3, sqrt(hypot(b.x - a.x, b.y - a.y))) }
        func lerp(_ a: CGPoint, _ b: CGPoint, _ ta: CGFloat, _ tb: CGFloat, _ t: CGFloat) -> CGPoint {
            let u = (t - ta) / (tb - ta)
            return CGPoint(x: a.x + (b.x - a.x) * u, y: a.y + (b.y - a.y) * u)
        }
        var out: [CGPoint] = []
        out.reserveCapacity((points.count - 1) * per + 1)
        for i in 0..<(points.count - 1) {
            let p0 = points[max(0, i - 1)], p1 = points[i], p2 = points[i + 1], p3 = points[min(points.count - 1, i + 2)]
            let t1 = knot(p0, p1), t2 = t1 + knot(p1, p2), t3 = t2 + knot(p2, p3)
            for s in 0..<per {
                let t = t1 + (t2 - t1) * CGFloat(s) / CGFloat(per)
                let a1 = lerp(p0, p1, 0, t1, t), a2 = lerp(p1, p2, t1, t2, t), a3 = lerp(p2, p3, t2, t3, t)
                out.append(lerp(lerp(a1, a2, 0, t2, t), lerp(a2, a3, t1, t3, t), t1, t2, t))
            }
        }
        out.append(points[points.count - 1])
        return out
    }

    /// Points every `step` along the polyline, and its last point.
    static func even(_ points: [CGPoint], step: CGFloat) -> [CGPoint] {
        guard let first = points.first else { return [] }
        var out = [first]
        var carry: CGFloat = 0
        for i in 1..<points.count {
            let a = points[i - 1], b = points[i], d = hypot(b.x - a.x, b.y - a.y)
            var s = step - carry
            while s < d {
                out.append(CGPoint(x: a.x + (b.x - a.x) * s / d, y: a.y + (b.y - a.y) * s / d))
                s += step
            }
            carry = d - (s - step)
        }
        out.append(points[points.count - 1])
        return out
    }

    /// A Gaussian pass along the line (`sigma` in samples): a tight turn
    /// becomes a round one. Both ends stay where they are.
    static func smooth(_ line: [CGPoint], sigma: CGFloat) -> [CGPoint] {
        let n = line.count
        guard n > 2 else { return line }
        let reach = Int((sigma * 3).rounded(.up))
        let weights = (-reach...reach).map { exp(-CGFloat($0 * $0) / (2 * sigma * sigma)) }
        let total = weights.reduce(0, +)
        // Past an end: the line mirrored through that end.
        func at(_ i: Int) -> CGPoint {
            if i < 0 {
                let m = line[min(n - 1, -i)]
                return CGPoint(x: 2 * line[0].x - m.x, y: 2 * line[0].y - m.y)
            }
            if i >= n {
                let m = line[max(0, 2 * n - 2 - i)]
                return CGPoint(x: 2 * line[n - 1].x - m.x, y: 2 * line[n - 1].y - m.y)
            }
            return line[i]
        }
        return (0..<n).map { i in
            if i == 0 || i == n - 1 { return line[i] }
            var x: CGFloat = 0, y: CGFloat = 0
            for k in -reach...reach {
                let p = at(i + k), w = weights[k + reach]
                x += p.x * w
                y += p.y * w
            }
            return CGPoint(x: x / total, y: y / total)
        }
    }
}

/// The same numbers for the same seed: a work's road keeps its shape.
struct SeededRandom: RandomNumberGenerator {
    private var state: UInt64

    init(_ seed: String) {
        var hash: UInt64 = 0xcbf2_9ce4_8422_2325
        for byte in seed.utf8 {
            hash ^= UInt64(byte)
            hash = hash &* 0x100_0000_01b3
        }
        state = hash
    }

    mutating func next() -> UInt64 {
        state &+= 0x9e37_79b9_7f4a_7c15
        var z = state
        z = (z ^ (z >> 30)) &* 0xbf58_476d_1ce4_e5b9
        z = (z ^ (z >> 27)) &* 0x94d0_49bb_1331_11eb
        return z ^ (z >> 31)
    }

    /// 0 up to 1.
    mutating func unit() -> CGFloat {
        CGFloat(next() >> 11) / CGFloat(1 << 53)
    }
}
