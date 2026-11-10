import SwiftUI

/// "Droga dzieła" (Mateusz 2026-11-10, "S1"; first called "Losy dzieła",
/// too near "Dalsze losy"): how the work went from its maker to where it
/// hangs now, from the museum's provenance, as a road drawn with a pen. No
/// time line, no rhythm (14:59: „droga jako rysowana luźno linia, a nie
/// rytmiczny wąż… zamiast ikon kropki”; 15:18: „bardziej organiczna”): one
/// smooth stroke that swings wide through the gaps between the stops'
/// texts, never across one, drifts a little as a hand does, breathes in
/// width, winds longer over an ocean the work crossed, and goes dashed to
/// an exhibition it came back from. Each stop is a dot, the last (where it is now) in vermilion. The
/// road's shape comes from the work's id, so it is the same each time.
struct JourneyRoad: View {
    let journey: DailyWork.Journey
    /// The work's id: the road's wander.
    let seed: String

    /// Where each stop's text ended up, in the road's space.
    @State private var rows: [Int: CGRect] = [:]

    private static let gap: CGFloat = 110
    /// Before a stop across an ocean: room for the sea.
    private static let seaGap: CGFloat = 190
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

    /// A stop's dot: how far in from the column's edge, and on which side.
    private struct Place {
        var left: Bool
        var inset: CGFloat
    }

    private var places: [Place] {
        var random = SeededRandom(seed)
        var left = random.next() % 2 == 0
        return journey.stops.indices.map { _ in
            defer {
                // Mostly the other side, now and then the same one again.
                if random.unit() > 0.2 { left.toggle() }
            }
            return Place(left: left, inset: 12 + 30 * random.unit())
        }
    }

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
        let places = self.places
        // Read here, not only in the Canvas: SwiftUI does not redraw a Canvas
        // for state its drawing closure reads, so the road came out blank
        // whenever the last row was measured after the first draw.
        let rows = self.rows
        return VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(journey.stops.enumerated()), id: \.offset) { i, stop in
                // Measured before the gap above it: the row's own text.
                row(stop, places[i])
                    .onGeometryChange(for: CGRect.self) { $0.frame(in: .named("road")) } action: { self.rows[i] = $0 }
                    .padding(.top, i == 0 ? 36 : overSea(i) ? Self.seaGap : Self.gap)
            }
        }
        .padding(.bottom, 28)
        .coordinateSpace(.named("road"))
        .background {
            Canvas { context, size in draw(in: &context, size: size, places: places, rows: rows) }
                .accessibilityHidden(true)
        }
        .overlay(alignment: .topLeading) { seaNames }
    }

    private func row(_ stop: DailyWork.Journey.Stop, _ place: Place) -> some View {
        VStack(alignment: place.left ? .leading : .trailing, spacing: 2) {
            Text("\(Text(stop.year).foregroundStyle(Theme.vermilion).fontWeight(.semibold))\(Text(stop.place.isEmpty ? "" : " · \(stop.place)").foregroundStyle(Theme.inkSoft))")
                .font(.caption)
                .monospacedDigit()
            Text(Self.marked(stop.text))
                .font(.serif(15))
                .foregroundStyle(Theme.ink)
                .multilineTextAlignment(place.left ? .leading : .trailing)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: place.left ? .leading : .trailing)
        .padding(place.left ? .leading : .trailing, place.inset + 16)
        .padding(place.left ? .trailing : .leading, 28)
        .accessibilityElement(children: .combine)
    }

    /// The telling words, between ** and **, in bold.
    static func marked(_ text: String) -> AttributedString {
        let options = AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        return (try? AttributedString(markdown: text, options: options)) ?? AttributedString(text)
    }

    @ViewBuilder
    private var seaNames: some View {
        ForEach(journey.stops.indices.filter { overSea($0) && !sea($0).isEmpty }, id: \.self) { i in
            if let before = rows[i - 1], let after = rows[i] {
                Text(sea(i))
                    .font(.serif(15).italic())
                    .foregroundStyle(Theme.inkSoft)
                    .position(x: before.width * 0.62, y: (before.maxY + after.minY) / 2 + 8)
            }
        }
    }

    // MARK: Drawing

    private func draw(in context: inout GraphicsContext, size: CGSize, places: [Place], rows: [Int: CGRect]) {
        let count = journey.stops.count
        guard count >= 2, (0..<count).allSatisfy({ rows[$0] != nil }) else { return }
        var random = SeededRandom(seed + "road")
        let width = size.width
        func dot(_ i: Int) -> CGPoint {
            CGPoint(x: places[i].left ? places[i].inset : width - places[i].inset, y: rows[i]!.minY + 8)
        }
        func out(_ i: Int) -> CGFloat { places[i].left ? -1 : 1 }
        // The seas first, under everything.
        for i in 1..<count where overSea(i) {
            drawSea(in: &context, top: rows[i - 1]!.maxY + 14, bottom: rows[i]!.minY - 10, width: width)
        }
        // The pen's way (15:18: „bardziej organiczna”; 15:26: „płynną linią,
        // bez ostrych zakrętów”; 17:11: no „oderwania ręki” at the dots, the
        // wide curves over the sea are the model): straight down through each
        // dot along its free side, past its text, then one wide sweep across
        // the gap to above the next dot. The turns happen in the gaps, never
        // at a dot, and the line never crosses a text.
        var route: [CGPoint] = [CGPoint(x: dot(0).x + out(0) * 12, y: 0)]
        var at: [Int] = []
        for i in 0..<count {
            let here = dot(i), row = rows[i]!
            route.append(CGPoint(x: here.x, y: here.y - 36))
            at.append(route.count)
            route.append(here)
            route.append(CGPoint(x: here.x, y: max(here.y + 16, row.maxY + 6)))
            guard i < count - 1 else { break }
            let top = row.maxY + 14, bottom = rows[i + 1]!.minY - 14, there = dot(i + 1)
            if overSea(i + 1) {
                // One swing per 70 pt of sea: closer they fold into hairpins.
                let turns = min(3, max(1, Int((bottom - top) / 70)))
                var left = places[i].left
                for t in 0..<turns {
                    let x = (left ? 0.24 : 0.72) + (random.unit() - 0.5) * 0.1
                    route.append(CGPoint(x: width * x, y: top + (bottom - top) * (CGFloat(t) + 0.5) / CGFloat(turns)))
                    left.toggle()
                }
            } else if places[i].left == places[i + 1].left {
                // The same side again: a soft bow inward.
                let inward: CGFloat = places[i].left ? 1 : -1
                route.append(CGPoint(x: here.x + inward * width * (0.1 + 0.06 * random.unit()),
                                     y: top + (bottom - top) * (0.4 + 0.2 * random.unit())))
            } else {
                let x = (here.x + there.x) / 2 + (random.unit() - 0.5) * 0.3 * abs(there.x - here.x)
                route.append(CGPoint(x: x, y: top + (bottom - top) * (0.4 + 0.2 * random.unit())))
            }
        }
        route.append(CGPoint(x: places[count - 1].left ? 4 : width - 4, y: min(size.height - 4, rows[count - 1]!.maxY + 22)))
        // The texts, with a little room: the line is kept out of them.
        let texts = (0..<count).map { i -> CGRect in
            let row = rows[i]!, inset = places[i].inset
            let x0 = places[i].left ? inset + 16 : 28, x1 = places[i].left ? width - 28 : width - inset - 16
            return CGRect(x: x0, y: row.minY, width: max(0, x1 - x0), height: row.height).insetBy(dx: -7, dy: -6)
        }
        let (line, pins) = Self.penLine(route, at: at, avoid: texts, random: &random)
        // Inked as one ribbon, dashed to and from an exhibition the work came
        // back from, as a side trip.
        var runs: [(Range<Int>, Bool)] = []
        func add(_ range: Range<Int>, _ dashed: Bool) {
            if case let (prev, was)? = runs.last, was == dashed { runs[runs.count - 1] = (prev.lowerBound..<range.upperBound, was) } else { runs.append((range, dashed)) }
        }
        add(0..<(pins[0] + 1), journey.stops[0].detour)
        for i in 0..<(count - 1) {
            add(pins[i]..<(pins[i + 1] + 1), journey.stops[i].detour || journey.stops[i + 1].detour)
        }
        add(pins[count - 1]..<line.count, journey.stops[count - 1].detour)
        for (range, dashed) in runs {
            let part = Array(line[range])
            if dashed {
                var path = Path()
                path.addLines(part)
                context.stroke(path, with: .color(Theme.ink.opacity(0.6)),
                               style: StrokeStyle(lineWidth: 1.5, lineCap: .round, dash: [3, 5]))
            } else {
                context.fill(Self.ribbon(part, random: &random, base: 2.2), with: .color(Theme.ink.opacity(0.85)))
            }
        }
        // The stops: dots, a ring round the last.
        for i in 0..<count {
            let p = dot(i)
            func circle(_ r: CGFloat) -> Path { Path(ellipseIn: CGRect(x: p.x - r, y: p.y - r, width: 2 * r, height: 2 * r)) }
            if journey.stops[i].detour {
                context.fill(circle(5), with: .color(Theme.paper))
                context.stroke(circle(4.5), with: .color(Theme.ink), lineWidth: 1.5)
            } else if i == count - 1 {
                context.fill(circle(9), with: .color(Theme.vermilion))
                context.stroke(circle(9), with: .color(Theme.paper), lineWidth: 2.5)
                context.stroke(circle(14), with: .color(Theme.vermilion), lineWidth: 1.5)
            } else {
                context.fill(circle(7), with: .color(Theme.ink))
                context.stroke(circle(7), with: .color(Theme.paper), lineWidth: 2.5)
            }
        }
    }

    /// A band of sea with loose edges and rows of small waves.
    private func drawSea(in context: inout GraphicsContext, top: CGFloat, bottom: CGFloat, width: CGFloat) {
        guard bottom - top > 30 else { return }
        var band = Path()
        band.move(to: CGPoint(x: 0, y: top))
        band.addCurve(to: CGPoint(x: width, y: top - 4), control1: CGPoint(x: width * 0.26, y: top - 14),
                      control2: CGPoint(x: width * 0.63, y: top + 16))
        band.addLine(to: CGPoint(x: width, y: bottom))
        band.addCurve(to: CGPoint(x: 0, y: bottom + 4), control1: CGPoint(x: width * 0.69, y: bottom + 12),
                      control2: CGPoint(x: width * 0.31, y: bottom - 14))
        band.closeSubpath()
        context.fill(band, with: .color(Self.sea.opacity(0.16)))
        var waves = Path()
        var y = top + 14
        var shift: CGFloat = 0
        while y < bottom - 10 {
            var x = 14 + shift
            while x < width - 24 {
                waves.move(to: CGPoint(x: x, y: y))
                waves.addQuadCurve(to: CGPoint(x: x + 12, y: y), control: CGPoint(x: x + 6, y: y - 5))
                waves.addQuadCurve(to: CGPoint(x: x + 24, y: y), control: CGPoint(x: x + 18, y: y + 5))
                x += 52
            }
            y += 30
            shift = shift == 0 ? 22 : 0
        }
        context.stroke(waves, with: .color(Self.sea.opacity(0.8)), style: StrokeStyle(lineWidth: 1.4, lineCap: .round))
    }

    private static let sea = Color(light: 0x9DB3C2, dark: 0x4F6878)

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

    /// One smooth stroke through the route: the spline evened out to a
    /// point every 2 pt, a slow drift of the hand, then relaxed until no turn
    /// is sharp. Near each stop (`at`: its index in the route) the line holds
    /// still; returns where each stop landed in the line.
    static func penLine(_ route: [CGPoint], at: [Int], avoid: [CGRect] = [], random: inout SeededRandom) -> ([CGPoint], [Int]) {
        let per = 24
        let (points, pins) = even(spline(route, per: per), step: 2, keep: at.map { $0 * per })
        guard points.count > 2 else { return (points, pins) }
        var a: CGFloat = 0, v: CGFloat = 0
        var line = points.indices.map { i in
            v = v * 0.985 + (random.unit() - 0.5) * 0.04
            a = min(2.5, max(-2.5, a + v))
            let n = normal(points, i)
            let near = pins.reduce(CGFloat(1)) { min($0, CGFloat(abs(i - $1)) / 30) }
            return CGPoint(x: points[i].x + n.x * a * near, y: points[i].y + n.y * a * near)
        }
        // How firmly each point keeps its place: fully at a dot, fading
        // over 16 points (32 pt) either side, the straight stretch through
        // the dot, so it leaves without a corner where the held part ends.
        var hold = [CGFloat](repeating: 0, count: line.count)
        for pin in pins {
            for i in max(0, pin - 16)...min(line.count - 1, pin + 16) {
                let f = 1 - CGFloat(abs(i - pin)) / 17
                hold[i] = max(hold[i], f * f)
            }
        }
        func clear(_ p: CGPoint) -> CGPoint {
            var p = p
            for text in avoid where text.contains(p) {
                let d = [p.x - text.minX, text.maxX - p.x, p.y - text.minY, text.maxY - p.y]
                switch d.firstIndex(of: d.min()!)! {
                case 0: p.x = text.minX
                case 1: p.x = text.maxX
                case 2: p.y = text.minY
                default: p.y = text.maxY
                }
            }
            return p
        }
        let start = line
        var next = line
        for _ in 0..<300 {
            for i in 1..<(line.count - 1) {
                let free = 1 - hold[i]
                next[i] = clear(CGPoint(x: start[i].x * hold[i] + free * (line[i - 1].x + 2 * line[i].x + line[i + 1].x) / 4,
                                        y: start[i].y * hold[i] + free * (line[i - 1].y + 2 * line[i].y + line[i + 1].y) / 4))
            }
            swap(&line, &next)
        }
        return (line, pins)
    }

    /// Points every `step` along the polyline; the points at `keep` are
    /// kept exactly, and where each landed is returned.
    static func even(_ points: [CGPoint], step: CGFloat, keep: [Int]) -> ([CGPoint], [Int]) {
        guard let first = points.first else { return ([], []) }
        let kept = Set(keep)
        var out = [first], landed: [Int: Int] = kept.contains(0) ? [0: 0] : [:]
        var carry: CGFloat = 0
        for i in 1..<points.count {
            let a = points[i - 1], b = points[i], d = hypot(b.x - a.x, b.y - a.y)
            var s = step - carry
            while s < d {
                out.append(CGPoint(x: a.x + (b.x - a.x) * s / d, y: a.y + (b.y - a.y) * s / d))
                s += step
            }
            carry = d - (s - step)
            if kept.contains(i) {
                out.append(b)
                landed[i] = out.count - 1
                carry = 0
            } else if i == points.count - 1 {
                out.append(b)
            }
        }
        return (out, keep.map { landed[$0] ?? 0 })
    }

    /// The line as a filled ribbon whose width breathes like a pen's
    /// pressure, thinner at both ends.
    static func ribbon(_ line: [CGPoint], random: inout SeededRandom, base: CGFloat) -> Path {
        var path = Path()
        guard line.count >= 2 else { return path }
        let n = line.count
        var a: CGFloat = 0, v: CGFloat = 0
        var left: [CGPoint] = [], right: [CGPoint] = []
        for i in 0..<n {
            v = v * 0.97 + (random.unit() - 0.5) * 0.06
            a = min(0.7, max(-0.7, a + v))
            let taper = min(1, CGFloat(i) / 40, CGFloat(n - 1 - i) / 40)
            let half = base * (1 + 0.45 * a) * (0.35 + 0.65 * taper) / 2
            let p = line[i], m = normal(line, i)
            left.append(CGPoint(x: p.x + m.x * half, y: p.y + m.y * half))
            right.append(CGPoint(x: p.x - m.x * half, y: p.y - m.y * half))
        }
        path.addLines(left + right.reversed())
        path.closeSubpath()
        return path
    }

    /// The unit normal of the line at a sample.
    private static func normal(_ line: [CGPoint], _ i: Int) -> CGPoint {
        let q = line[min(line.count - 1, i + 1)], o = line[max(0, i - 1)]
        let dx = q.x - o.x, dy = q.y - o.y, m = max(1e-6, hypot(dx, dy))
        return CGPoint(x: -dy / m, y: dx / m)
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
