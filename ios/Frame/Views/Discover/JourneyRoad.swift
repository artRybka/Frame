import SwiftUI
import UIKit

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
/// last one's dot, vermilion and bigger than the rest (18:16); over a sea
/// the work crossed it makes two free sweeps among waves. It is inked as with a broad nib held flat
/// (17:59: „przy zakrętach grubsza, jakby rysowana piórem do kaligrafii”):
/// thin along the runs, thick where it turns down. An exhibition the work
/// came back from is a side trip (18:16; 18:40: „odnoga musi wychodzić
/// naturalniej ze ścieżki, jak rozdroże; ramka… może jako zakreślenie?”):
/// a branch leaves the road as at a fork, inked with the same pen lifted
/// (short strokes), along the road at first and then down to a hollow dot
/// on a loop drawn by hand round the trip's text, the way one circles a
/// word. Under each text lies an underpainting, a stain of watercolour
/// that ran and dried with a sharp edge; beside the black line there is
/// white here and there, as if the line had been corrected, and white
/// round the last dot (18:48: „białym jakby korekty linii obok czarnej
/// ścieżki, białym otok wokół czerwonej kropki… plamy akwareli z
/// ostrzejszą krawędzią, nierówne podmalówki pod treściami”).
/// The texts are broken with care (18:26): see `typeset` and `broken`.
/// Nothing is written under the drawing (18:26: „bez podpisu o genezie i
/// źródle”). The shape comes from the work's id.
///
/// The drawing comes about as the page is scrolled, at the middle of the
/// screen and from the top (22:18: „plamy powinny rozlewać się wolniej,
/// najlepiej zlewać w jedną całość idąc od góry. Bardziej »wchłaniać« się
/// w papier… ich pojawienie powinno być nie na dole a na środku ekranu w
/// trakcie przewijania. Podobnie rysować się może linia i powstawać kropki
/// na niej. A podpisy płynnie się pojawiać”): the line is drawn down to
/// there, the dots come up on it, the white paint, one wash under all the
/// texts, soaks into the paper, and each text comes up out of it
/// (`RoadReveal`). The line comes out from under the rule below the
/// figures, and its turns keep nearer the middle of the page than they did
/// (22:21: „start kreski niech zaczyna się spod linii nad którą są liczby…
/// łuki mogą być trochę łagodniejsze, bliżej środka strony”).
struct JourneyRoad: View {
    let journey: DailyWork.Journey
    /// The work's id: the road's wander.
    let seed: String

    /// How big each stop's text is at the width the road gives it.
    @State private var sizes: [Int: CGSize] = [:]
    /// How wide the road is.
    @State private var width: CGFloat = 0
    /// How far the drawing has come.
    @State private var reveal = RoadReveal()
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.accessibilityVoiceOverEnabled) private var voiceOver

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
        if west < -30, east > 100 { return "Pacyfik" }
        return ""
    }

    private var road: some View {
        let count = journey.stops.count
        let seas = self.seas
        // Worked out here, not in the Canvas: SwiftUI does not redraw a
        // Canvas for state only its drawing closure reads, so the road came
        // out blank whenever the last text was measured after the first draw.
        let measured = (0..<count).compactMap { sizes[$0] }
        // With figures over the road the line comes out from under their rule.
        let lead: CGFloat? = facts.isEmpty ? nil : Self.lead
        let plan = measured.count == count
            ? Self.plan(width: width, heights: measured.map(\.height), seas: seas, detours: journey.stops.map(\.detour),
                        widths: measured.map(\.width), seed: seed, lead: lead) : nil
        let textWidth = Self.textWidth(width)
        let dark = colorScheme == .dark
        // "Ogranicz ruch", and VoiceOver, which reads the texts whether
        // they are drawn yet or not: everything is there at once.
        let still = reduceMotion || voiceOver
        let top = lead ?? 0
        let paint = plan.map { Self.underpainting(under: $0.hugs, seas: seas, width: width, seed: seed) }
        let rim = plan.map { plan -> Path in
            var around = SeededRandom(seed + "halo")
            return Self.closed(Self.halo(round: plan.dots[count - 1], random: &around))
        }
        let marks = plan.map { RoadMarks($0) }
        var soak = SeededRandom(seed + "soak")
        let paintSeed = Float(soak.next() % 50)
        return ZStack(alignment: .topLeading) {
            ForEach(Array(journey.stops.enumerated()), id: \.offset) { i, stop in
                // Each text is measured where the layout first puts it and
                // then moved to its dot; the move does not change its height.
                // Measured before it is given the full width: a side trip's
                // loop is drawn round the text as it stands.
                Emerging(reveal: reveal, top: plan?.texts[i].minY ?? 0, height: plan?.texts[i].height ?? 1) {
                    row(stop, leading: plan?.leading[i] ?? true, width: textWidth)
                        .onGeometryChange(for: CGSize.self) { $0.size } action: { self.sizes[i] = $0 }
                }
                .frame(width: textWidth, alignment: plan?.leading[i] ?? true ? .topLeading : .topTrailing)
                .offset(x: plan?.texts[i].minX ?? 0, y: plan?.texts[i].minY ?? 0)
                .opacity(plan == nil ? 0 : 1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .frame(height: plan?.height, alignment: .topLeading)
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { self.width = $0 }
        .background(alignment: .topLeading) {
            if let plan, let paint, let rim {
                ZStack(alignment: .topLeading) {
                    // Under everything, the underpainting: one wash under all the texts.
                    RoadWash(reveal: reveal, stains: paint.stains, drops: paint.drops, dark: dark, seed: paintSeed)
                    // The seas come up softly, a little behind the drawing.
                    Canvas { context, size in drawSeas(in: &context, size: size, plan: plan, seas: seas) }
                        .mask { Curtain(reveal: reveal, soft: 44, behind: 6) }
                    // The line and what is drawn with it, as far as the drawing has come.
                    Canvas { context, _ in
                        context.translateBy(x: 0, y: top)
                        drawInk(in: &context, plan: plan, dark: dark)
                    }
                    // Masked before it is moved up: the mask is as big as what it masks.
                    .mask { Curtain(reveal: reveal, soft: 5, above: top) }
                    .padding(.top, -top)
                    RoadDots(reveal: reveal, plan: plan, rim: rim, dark: dark)
                }
                .allowsHitTesting(false)
                .accessibilityHidden(true)
            }
        }
        // Where the screen is on the road: its middle is where the drawing comes about.
        .onGeometryChange(for: CGRect.self) { $0.bounds(of: .scrollView) ?? .null } action: { reveal.look($0) }
        .onChange(of: marks, initial: true) { _, marks in reveal.lay(marks, still: still) }
        .onChange(of: still) { _, still in reveal.lay(marks, still: still) }
        .background { RoadClock(reveal: reveal) }
    }

    private func row(_ stop: DailyWork.Journey.Stop, leading: Bool, width: CGFloat) -> some View {
        // The date in the hand, always the end of the line that is at the dot
        // (18:04: „czerwone daty zawsze przy kropce. Daty pismem pisanym”):
        // first where the text reads from its dot, last where it ends at it.
        // A stop the record gives no date for has none here either, and
        // no line at all when it has no place (22:20: „Powtórzenia w
        // opisach braku daty są irytujące”; the server no longer writes
        // "bez daty").
        let date = Text(stop.year).font(.hand(21)).foregroundStyle(Theme.vermilion)
        let place = Text(stop.place).font(.caption).foregroundStyle(Theme.inkSoft)
        let between = Text(stop.place.isEmpty || stop.year.isEmpty ? "" : " · ").font(.caption).foregroundStyle(Theme.inkSoft)
        return VStack(alignment: leading ? .leading : .trailing, spacing: 0) {
            if !(stop.year.isEmpty && stop.place.isEmpty) {
                (leading ? Text("\(date)\(between)\(place)") : Text("\(place)\(between)\(date)"))
                    .lineLimit(1)
                    .truncationMode(leading ? .tail : .head)
            }
            Text(Self.marked(Self.broken(stop.text, width: width)))
                .font(.serif(15))
                .foregroundStyle(Theme.ink)
                .multilineTextAlignment(leading ? .leading : .trailing)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
    }

    /// The sentence set for a column this wide (18:26: „zadbaj o prawidłowe
    /// łamania tekstów”): its hard spaces put in (`typeset`), and broken
    /// into as few lines as it takes, of about the same length, so that a
    /// line is never one word between two full ones. The words are
    /// measured in the faces the text is drawn in.
    static func broken(_ text: String, width: CGFloat) -> String {
        let set = typeset(text)
        guard width > 40 else { return set }
        let chunks = set.split(separator: " ", omittingEmptySubsequences: true).map(String.init)
        var bold = false
        let widths = chunks.map { chunk -> CGFloat in
            var total: CGFloat = 0
            for (k, part) in chunk.components(separatedBy: "**").enumerated() {
                if k > 0 { bold.toggle() }
                total += (part as NSString).size(withAttributes: [.font: bold ? boldFace : face]).width
            }
            return total
        }
        let space = (" " as NSString).size(withAttributes: [.font: face]).width
        // A little under the column, so a line measured here never wraps there.
        let starts = Set(evenBreaks(widths, space: space, width: width - 3))
        return chunks.enumerated().map { k, chunk in (k == 0 ? "" : starts.contains(k) ? "\n" : " ") + chunk }.joined()
    }

    /// `Font.serif(15)` and its bold, to measure words with.
    private static let face = serifFace(.regular)
    private static let boldFace = serifFace(.bold)

    private static func serifFace(_ weight: UIFont.Weight) -> UIFont {
        let base = UIFont.systemFont(ofSize: 15, weight: weight)
        return base.fontDescriptor.withDesign(.serif).map { UIFont(descriptor: $0, size: 15) } ?? base
    }

    /// The telling words, between ** and **, in bold.
    static func marked(_ text: String) -> AttributedString {
        let options = AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        return (try? AttributedString(markdown: text, options: options)) ?? AttributedString(text)
    }

    // MARK: Drawing

    /// The seas, under the road.
    private func drawSeas(in context: inout GraphicsContext, size: CGSize, plan: RoadPlan, seas: [Bool]) {
        let count = journey.stops.count
        for i in 1..<count where seas[i] {
            var random = SeededRandom(seed + "sea\(i)")
            drawSea(in: &context, name: sea(i), top: plan.texts[i - 1].maxY + 16,
                    bottom: i == count - 1 ? plan.dots[i].y - 30 : plan.texts[i].minY - 14,
                    width: size.width, plan: plan, random: &random)
        }
    }

    /// What the pen and the dry brush drew: the white beside the line, the
    /// line itself, and each side trip's branch and loop. The dots are not
    /// here: each comes up on the line by itself (`RoadDots`).
    private func drawInk(in context: inout GraphicsContext, plan: RoadPlan, dark: Bool) {
        let count = journey.stops.count
        // White beside the black line, as if it had been corrected
        // (18:48), under the line.
        var white = Path()
        for stroke in Self.corrections(along: plan.line, until: plan.dots[count - 1], seed: seed) {
            white.addLines(stroke)
            white.closeSubpath()
        }
        context.fill(white, with: .color(Self.white(dark)))
        // The road, from under the rule (or from the first dot) to the last dot.
        var stroke = Path()
        stroke.addLines(Self.nibStroke(plan.line, until: plan.dots[count - 1], clear: Self.lastClear))
        stroke.closeSubpath()
        context.fill(stroke, with: .color(Theme.ink))
        context.stroke(stroke, with: .color(Theme.ink), style: StrokeStyle(lineWidth: Self.hair, lineJoin: .round))
        // A side trip the work came back from (18:16: „jako odnogę…
        // rysowaną przerywaną linią”; 18:40: „jak rozdroże… ramka może jako
        // zakreślenie”): the loop round its text, and the branch in short
        // strokes of the pen.
        for i in 0..<(count - 1) {
            guard let way = plan.branches[i] else { continue }
            if let frame = plan.loops[i] {
                var random = SeededRandom(seed + "loop\(i)")
                var ring = Path()
                ring.addLines(Self.loop(frame, dotRight: !plan.leading[i], random: &random))
                context.stroke(ring, with: .color(Theme.ink.opacity(0.82)),
                               style: StrokeStyle(lineWidth: 1.3, lineCap: .round, lineJoin: .round))
            }
            var spur = Path()
            for dash in Self.dashes(way, until: plan.dots[i]) {
                spur.addLines(dash)
                spur.closeSubpath()
            }
            context.fill(spur, with: .color(Theme.ink))
            context.stroke(spur, with: .color(Theme.ink), style: StrokeStyle(lineWidth: 1.2, lineJoin: .round))
        }
    }

    /// The white of the corrections and of the last dot's halo.
    fileprivate static func white(_ dark: Bool) -> Color { Color.white.opacity(dark ? 0.2 : 0.95) }

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

    fileprivate static func closed(_ points: [CGPoint]) -> Path {
        var path = Path()
        path.addLines(points)
        path.closeSubpath()
        return path
    }
}

// MARK: The drawing coming about

/// Where the stops are down the road, for the drawing to come to: a stop
/// starts when its dot is at the middle of the screen, and is then drawn
/// to the end of its text, whether the page goes on or not.
struct RoadMarks: Equatable {
    struct Start: Equatable {
        /// The stop's dot.
        var at: CGFloat
        /// How far the drawing goes once the stop has started: to where the next text begins to show.
        var to: CGFloat
    }

    var starts: [Start] = []
    var height: CGFloat = 0

    /// Past the road's end: everything is drawn.
    var full: CGFloat { height + 60 }

    init() {}

    init(_ plan: RoadPlan) {
        height = plan.height
        starts = plan.dots.indices.map { i in
            Start(at: plan.dots[i].y, to: i < plan.dots.count - 1 ? plan.texts[i + 1].minY + 44 : plan.height + 60)
        }
    }

    /// How far the drawing is to go with the middle of the screen at `mid`.
    func target(mid: CGFloat) -> CGFloat {
        var target = mid
        for start in starts where start.at <= mid { target = max(target, start.to) }
        return min(target, full)
    }

    /// The slowest the drawing and the drying go, in points a second, and
    /// how long each takes to catch up with what it follows.
    static let pace: (draw: CGFloat, dry: CGFloat) = (50, 25)
    static let lag: (draw: CGFloat, dry: CGFloat) = (0.6, 1.4)

    /// The drawing and the drying a moment later: each goes faster the
    /// further behind it is, and never slower than its pace. The drawing
    /// stops at `target`, the drying at the drawing.
    static func advance(front: CGFloat, done: CGFloat, target: CGFloat, passed: CGFloat) -> (front: CGFloat, done: CGFloat) {
        let drawn = min(target, front + max(pace.draw, (target - front) / lag.draw) * passed)
        let dried = min(drawn, done + max(pace.dry, (drawn - done) / lag.dry) * passed)
        return (drawn, dried)
    }
}

/// How far down the road the drawing has come (22:18). `front` is a height
/// on the road: above it the line is drawn, the dots are there, the paint
/// has come and the texts have come up; under it there is nothing yet. It
/// follows the middle of the screen as the page is scrolled, never back,
/// and never faster than paint flows. `done` follows it in time: how far
/// the paint has dried. Between the two the paint is wet.
@MainActor
@Observable
final class RoadReveal {
    private(set) var front = RoadReveal.before
    private(set) var done = RoadReveal.before
    /// Nothing is moving: no need to keep time.
    private(set) var settled = true

    @ObservationIgnored private var marks = RoadMarks()
    @ObservationIgnored private var still = false
    @ObservationIgnored private var target = RoadReveal.before
    /// The part of the road on screen, and when it last moved.
    @ObservationIgnored private var seen = CGRect.null
    @ObservationIgnored private var looked = false
    @ObservationIgnored private var moved = Date.distantPast
    @ObservationIgnored private var last: Date?

    /// Before anything is drawn: over the rule the line comes out from.
    static let before: CGFloat = -50
    /// With the road's end on screen and the page at rest this long, the
    /// rest is drawn: nothing more will come to the middle of the screen.
    static let rest: TimeInterval = 1.2
    /// CI screenshots: "-journeyWash 0.45" holds the drawing that far down
    /// the road, its paint still wet; 1 and more is all of it, dry.
    static let held: CGFloat? = UserDefaults.standard.object(forKey: "journeyWash") == nil
        ? nil : CGFloat(UserDefaults.standard.double(forKey: "journeyWash"))

    /// The road is laid out (or laid out again).
    func lay(_ marks: RoadMarks?, still: Bool) {
        guard let marks else { return }
        self.marks = marks
        self.still = still
        aim()
    }

    /// The page moved: `bounds` is the part of the road on screen, in the
    /// road's own coordinates (null outside a scroll view).
    func look(_ bounds: CGRect) {
        seen = bounds
        looked = true
        moved = Date()
        aim()
    }

    private func aim() {
        guard looked, !marks.starts.isEmpty else { return }
        if let held = Self.held {
            let all = held >= 1
            return set(front: all ? marks.full : held * marks.height, done: all ? marks.full : held * marks.height - 120)
        }
        if still || seen.isNull { return set(front: marks.full, done: marks.full) }
        target = max(target, marks.target(mid: seen.midY))
        // What is over the top of the screen is not watched: it is there at once.
        let over = min(seen.minY - 80, target)
        if front < over { front = over }
        if done < over - 60 { done = over - 60 }
        if front < target || done < front || waits { settled = false }
    }

    private func set(front: CGFloat, done: CGFloat) {
        target = front
        if self.front != front { self.front = front }
        if self.done != done { self.done = done }
        last = nil
        if !settled { settled = true }
    }

    /// The road's end is on screen and not all of it is to be drawn yet.
    private var waits: Bool { target < marks.full && !seen.isNull && seen.maxY >= marks.height }

    /// One frame on.
    func tick(_ now: Date) {
        guard !settled else { return }
        let passed = min(1.0 / 20, last.map { now.timeIntervalSince($0) } ?? 1.0 / 60)
        last = now
        if waits, now.timeIntervalSince(moved) > Self.rest { target = marks.full }
        let next = RoadMarks.advance(front: front, done: done, target: target, passed: CGFloat(max(0, passed)))
        if next.front != front { front = next.front }
        if next.done != done { done = next.done }
        if front >= target, done >= front, !waits {
            settled = true
            last = nil
        }
    }
}

/// Keeps time for the drawing while anything moves.
private struct RoadClock: View {
    let reveal: RoadReveal

    var body: some View {
        TimelineView(.animation(paused: reveal.settled)) { context in
            Color.clear.onChange(of: context.date) { _, now in reveal.tick(now) }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

/// What the drawing has passed: black down to the front, clear under it,
/// `soft` points of one going over to the other. `above`: how far over the
/// road's top the masked view starts; `behind`: how far it lags.
private struct Curtain: View {
    let reveal: RoadReveal
    var soft: CGFloat
    var above: CGFloat = 0
    var behind: CGFloat = 0

    var body: some View {
        let edge = reveal.front - behind + above
        GeometryReader { proxy in
            let tall = max(1, proxy.size.height)
            LinearGradient(colors: [.black, .clear],
                           startPoint: UnitPoint(x: 0.5, y: (edge - soft) / tall),
                           endPoint: UnitPoint(x: 0.5, y: edge / tall))
        }
    }
}

/// A stop's text coming up out of the paint once the drawing is past its
/// top (22:18: „podpisy płynnie się pojawiać. (Zlewać z akwareli?)”):
/// blurred and pale at first, line after line.
private struct Emerging<Content: View>: View {
    let reveal: RoadReveal
    let top: CGFloat
    let height: CGFloat
    let content: Content

    init(reveal: RoadReveal, top: CGFloat, height: CGFloat, @ViewBuilder content: () -> Content) {
        self.reveal = reveal
        self.top = top
        self.height = height
        self.content = content()
    }

    /// The mask reaches this far past the text all round, for the hand's
    /// tall strokes and the blur; a line comes up over this many points.
    private static var room: CGFloat { 8 }
    private static var line: CGFloat { 56 }

    var body: some View {
        let shown = JourneyRoad.ease((reveal.front - top - 46) / max(1, height * 0.6))
        let tall = height + 2 * Self.room, edge = shown * (tall + Self.line)
        content
            .opacity(shown <= 0 ? 0 : 0.25 + 0.75 * shown)
            .blur(radius: 3.2 * (1 - shown))
            .mask {
                LinearGradient(colors: [.black, .clear],
                               startPoint: UnitPoint(x: 0.5, y: (edge - Self.line) / tall),
                               endPoint: UnitPoint(x: 0.5, y: edge / tall))
                    .padding(-Self.room)
            }
    }
}

/// The dots, each coming up on the line as the drawing gets to it: it
/// grows a little too big and settles. A hollow one where a side trip's
/// branch ends, and a bigger red one for the last, where the work is now
/// (18:16: „czerwona, ale większa”), on white laid over the end of the
/// line (19:08: „powinien też nachodzić na czarną linię”): the paper
/// first, so the line ends under it on the dark page too, then the white.
private struct RoadDots: View {
    let reveal: RoadReveal
    let plan: RoadPlan
    let rim: Path
    let dark: Bool

    var body: some View {
        let front = reveal.front, last = plan.dots.count - 1
        let white = JourneyRoad.ease((front - plan.dots[last].y + 12) / 30)
        ZStack(alignment: .topLeading) {
            rim.fill(Theme.paper).opacity(white)
            rim.fill(JourneyRoad.white(dark)).opacity(white)
            ForEach(plan.dots.indices, id: \.self) { i in
                let size = JourneyRoad.pop(front - plan.dots[i].y)
                Group {
                    if i == last {
                        Circle().fill(Theme.vermilion).frame(width: 2 * JourneyRoad.lastDot, height: 2 * JourneyRoad.lastDot)
                    } else if plan.branches[i] != nil {
                        Circle().fill(Theme.paper).overlay { Circle().stroke(Theme.ink, lineWidth: 1.6) }
                            .frame(width: 9.2, height: 9.2)
                    } else {
                        Circle().fill(Theme.ink).frame(width: 10.8, height: 10.8)
                    }
                }
                .scaleEffect(size)
                .position(plan.dots[i])
            }
        }
    }
}

/// The underpainting (18:48: „plamy akwareli z ostrzejszą krawędzią jak
/// rozlana plama, nierówne podmalówki pod treściami”; 19:08: „jeżeli już,
/// to blado-białe”): a stain under each text, each joined to the next by a
/// run of paint, all one wash (22:18: „zlewać w jedną całość idąc od
/// góry”). It comes from the top as the drawing does and soaks into the
/// paper (`Watercolour.metal`, `soak`).
private struct RoadWash: View {
    let reveal: RoadReveal
    let stains: [[CGPoint]]
    let drops: [JourneyRoad.Drop]
    let dark: Bool
    /// Tells one road's paint from another's.
    let seed: Float

    var body: some View {
        let room = JourneyRoad.washRoom
        WashField(stains: stains, drops: drops)
            .equatable()
            // On the field itself, which is bigger than the road: the
            // shader is told where the road's corner is in it.
            .layerEffect(
                ShaderLibrary.soak(.float2(room), .float(Float(reveal.front)), .float(Float(reveal.done)), .float(seed)),
                maxSampleOffset: .zero
            )
            // On the dark page faint.
            .opacity(dark ? 0.1 : 1)
            .padding(.horizontal, -room.width)
            .padding(.vertical, -room.height)
    }
}

/// Where there can be paint and how near its edge each place is: the
/// stains and the runs between them, white and blurred. The shader makes
/// the paint of it; nobody sees this as it is. Drawn once: nothing in it
/// changes as the paint comes.
private struct WashField: View, Equatable {
    let stains: [[CGPoint]]
    let drops: [JourneyRoad.Drop]

    var body: some View {
        Canvas { context, _ in
            context.translateBy(x: JourneyRoad.washRoom.width, y: JourneyRoad.washRoom.height)
            context.addFilter(.blur(radius: JourneyRoad.washBlur))
            // One layer, so the blur is of all of it together.
            context.drawLayer { layer in
                for stain in stains { layer.fill(JourneyRoad.closed(stain), with: .color(.white)) }
                for drop in drops {
                    let box = CGRect(x: drop.at.x - drop.radius, y: drop.at.y - drop.radius,
                                     width: 2 * drop.radius, height: 2 * drop.radius)
                    layer.fill(Path(ellipseIn: box), with: .color(.white))
                }
            }
        }
    }
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
    /// A side trip's branch, from where it leaves the road to its stop's dot.
    var branches: [Int: [CGPoint]] = [:]
    /// The box of the loop round a side trip's text; its dot is on the loop.
    var loops: [Int: CGRect] = [:]
    /// Each text as it stands: as wide as its longest line.
    var hugs: [CGRect] = []
    var height: CGFloat
}

extension JourneyRoad {
    /// Where the date's figures are in a text (the hand's line is tall):
    /// level with a dot beside it.
    static let yearY: CGFloat = 14
    /// The line stops this short of the last stop, under its dot.
    static let lastClear: CGFloat = 3
    /// The last stop's dot, where the work is now: bigger than the others.
    static let lastDot: CGFloat = 9
    /// Bristles of the dry brush in one white correction.
    static let bristles = 3
    /// How far under the road a side trip's stop hangs, and how far back
    /// along the road its branch forks off.
    static let branch: CGFloat = 46
    static let branchSpan: CGFloat = 140
    /// The pen of the branch: a narrower nib, in strokes this long with
    /// this much between them.
    static let branchNib: CGFloat = 3.4
    static let branchDash = (on: 9, off: 5)
    /// The room between a side trip's text and the loop round it: at the
    /// sides, above and under.
    static let loopPad: (side: CGFloat, top: CGFloat, bottom: CGFloat) = (22, 10, 15)
    /// The loop is a rounded box (a superellipse of this power); its stop's
    /// dot is on it this far out from the middle, towards a top corner.
    static let loopPower: CGFloat = 3.2
    static let loopCorner: CGFloat = 0.8052
    /// The nib's width, how far it is turned from flat, and the thinnest
    /// the stroke gets.
    static let nib: CGFloat = 6.2
    static let nibTilt: CGFloat = -8 * .pi / 180
    static let hair: CGFloat = 1.4
    /// How far over the road's top the line starts, with figures above it:
    /// at the rule under them (22:21), which is the section's spacing away.
    static let lead: CGFloat = 12
    /// How far the road's turns reach to the sides (22:21: „łuki mogą być
    /// trochę łagodniejsze, bliżej środka strony (nie sięgać tak bardzo na
    /// boki)”; 22:22: „albo zwężać się coraz bardziej ku dołowi”).
    enum Arcs {
        /// Gentler all the way down: every turn well short of the edge.
        case soft
        /// From edge to edge at the top, narrower with every turn.
        case narrow
    }
    static let arcs = Arcs.soft
    /// The underpainting's field is this much bigger than the road each
    /// way, and blurred this much: its soft edge is what the paint seeps over.
    static let washRoom = CGSize(width: 48, height: 34)
    static let washBlur: CGFloat = 13

    /// 0 up to 1, slow at both ends.
    static func ease(_ x: CGFloat) -> CGFloat {
        let t = min(1, max(0, x))
        return t * t * (3 - 2 * t)
    }

    /// How big a dot is with the drawing `past` it: it grows a little too
    /// big and settles at 1.
    static func pop(_ past: CGFloat) -> CGFloat {
        let left = min(1, max(0, (past + 4) / 30)) - 1
        return 1 + 2.70158 * left * left * left + 1.70158 * left * left
    }

    /// Every text is this wide: a little over half the road, so a run has
    /// room to pass above it and the next one under it.
    static func textWidth(_ width: CGFloat) -> CGFloat { max(120, (width * 0.55).rounded()) }

    /// The road for texts of these heights. `seas[i]`: stop `i` is over a
    /// sea from the one before.
    ///
    /// The line comes down from `lead` over the road's top (from under the
    /// rule there; with no `lead` it starts at the first stop), through the
    /// first stop into a hook, then runs from side to side:
    /// two free ones over a sea, one for each stop between the first and the
    /// last, and one to the last stop, which hangs on a short drop. A stop's
    /// dot is on its run just past its text's corner, and its text is in the
    /// bay under that run, on the side the run came from. The line is drawn
    /// through the turns alone; then, where a text would not clear the run
    /// under it, that run is made steeper (or its turn sent out to the
    /// edge) and the line drawn again.
    static func plan(width: CGFloat, heights: [CGFloat], seas: [Bool], detours: [Bool] = [], widths: [CGFloat] = [],
                     seed: String, lead: CGFloat? = nil, arcs: Arcs = JourneyRoad.arcs) -> RoadPlan? {
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
            /// The nearest the edge its turn may be sent.
            var floor: CGFloat = 0
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
            switch arcs {
            case .soft:
                runs[i].inset = width * (runs[i].sea ? 0.25 + 0.1 * random.unit() : 0.13 + 0.07 * random.unit())
            case .narrow:
                let down = runs.count > 1 ? CGFloat(i) / CGFloat(runs.count - 1) : 0
                runs[i].inset = (runs[i].sea ? width * 0.07 : 0) + 20 + down * (width * 0.27 - 20) + 10 * random.unit()
            }
            runs[i].floor = max(14, runs[i].inset - 16)
            runs[i].margin = 2 + 12 * random.unit()
            runs[i].bow = (random.unit() - 0.5) * 14
            // A side trip's loop is wider than its text.
            if let k = runs[i].stop, k < detours.count, detours[k] { runs[i].margin = max(runs[i].margin, loopPad.side + 3) }
        }
        let hookInset = arcs == .soft ? width * (0.1 + 0.05 * random.unit()) : 16 + 10 * random.unit()
        let start = CGPoint(x: x(startLeft, hookInset + 34 + 10 * random.unit()), y: yearY)
        // Where the line comes out from under the rule over the road.
        let above = lead.map { CGPoint(x: x(startLeft, hookInset + 30 + 6 * random.unit()), y: -$0) }
        var hook = max(44, heights[0] + 10), drop: CGFloat = 44
        var result: RoadPlan?
        for _ in 0..<60 {
            let hooked = CGPoint(x: x(startLeft, hookInset), y: start.y + hook)
            var route = (above.map { [$0] } ?? []) + [start, hooked]
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
            let turns = [index(at: hooked.y)] + runs.map { index(at: $0.turn.y) }
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
            var branches: [Int: [CGPoint]] = [:]
            var loops: [Int: CGRect] = [:]
            var changed = false
            // The first stop: the line comes down through its dot (or
            // starts at it) and hooks away from its text.
            do {
                let x0 = startLeft ? start.x + 15 : start.x - 15 - textWidth
                texts[0] = CGRect(x: x0, y: 0, width: textWidth, height: heights[0])
                dots[0] = line[0...turns[0]].min { hypot($0.x - start.x, $0.y - start.y) < hypot($1.x - start.x, $1.y - start.y) }
                    ?? start
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
                let detour = k < detours.count && detours[k]
                // Round a side trip's text there is a loop, as wide as the
                // text as it stands, and its dot is on the loop, towards
                // the top corner nearest the road.
                let side = detour ? loopPad.side : 0, under = detour ? loopPad.bottom : 0
                let wide = detour && k < widths.count ? min(textWidth, max(40, widths[k])) : textWidth
                let halfWide = wide / 2 + loopPad.side, halfTall = (heights[k] + loopPad.top + loopPad.bottom) / 2
                let centre = (left ? x1 - wide : x0) + wide / 2
                let dotX = detour ? centre + (left ? 1 : -1) * loopCorner * halfWide : (left ? x1 + 11 : x0 - 11)
                var d = turns[i]
                for q in turns[i]...turns[i + 1] where abs(line[q].x - dotX) < abs(line[d].x - dotX) { d = q }
                dots[k] = line[d]
                leading[k] = !left
                var top = (lowest(turns[i], turns[i + 1], x0 - side - 5, x1 + side + 5) ?? line[d].y) + 5
                if detour {
                    // A side trip: the branch leaves the road as at a fork,
                    // along it at first, then bends down to the loop.
                    let loopTop = max(top + 4, line[d].y + branch - (1 - loopCorner) * halfTall)
                    let end = CGPoint(x: dotX, y: loopTop + (1 - loopCorner) * halfTall)
                    var a = d
                    while a > min(d, turns[i] + 12), abs(line[a].x - dotX) < branchSpan { a -= 1 }
                    let from = line[a], before = line[max(a - 4, 0)], after = line[min(a + 4, line.count - 1)]
                    let step = max(1e-3, hypot(after.x - before.x, after.y - before.y))
                    let along = CGPoint(x: (after.x - before.x) / step, y: (after.y - before.y) / step)
                    let down = CGPoint(x: (along.x < 0 ? -0.45 : 0.45) / hypot(0.45, 1), y: 1 / hypot(0.45, 1))
                    let reach = hypot(end.x - from.x, end.y - from.y)
                    let first = CGPoint(x: from.x + along.x * reach * 0.5, y: from.y + along.y * reach * 0.5)
                    let second = CGPoint(x: end.x - down.x * reach * 0.36, y: end.y - down.y * reach * 0.36)
                    branches[k] = (0...48).map { q in
                        let t = CGFloat(q) / 48, u = 1 - t
                        let b0 = u * u * u, b1 = 3 * u * u * t, b2 = 3 * u * t * t, b3 = t * t * t
                        return CGPoint(x: b0 * from.x + b1 * first.x + b2 * second.x + b3 * end.x,
                                       y: b0 * from.y + b1 * first.y + b2 * second.y + b3 * end.y)
                    }
                    dots[k] = end
                    top = loopTop + loopPad.top
                    loops[k] = CGRect(x: centre - halfWide, y: loopTop, width: 2 * halfWide, height: 2 * halfTall)
                }
                texts[k] = CGRect(x: x0, y: top, width: textWidth, height: heights[k])
                if let next = highest(turns[i + 1], turns[min(i + 3, turns.count - 1)], x0 - side - 6, x1 + side + 6),
                   top + heights[k] + under + 11 > next {
                    let need = top + heights[k] + under + 12 - next
                    // A tall text first sends its turn out to the edge, and
                    // only then makes the next run steeper.
                    if runs[i + 1].fall + need > 104, runs[i].inset > runs[i].floor + 2, !runs[i].sea {
                        runs[i].inset = max(runs[i].floor, runs[i].inset - 12)
                    } else {
                        runs[i + 1].fall += need
                    }
                    changed = true
                }
            }
            // The last stop: the line drops to its dot beside its text.
            do {
                let k = count - 1
                let x0 = endLeft ? end.x + 20 : end.x - 20 - textWidth
                texts[k] = CGRect(x: x0, y: end.y - yearY, width: textWidth, height: heights[k])
                dots[k] = end
                leading[k] = endLeft
                if let above = lowest(turns[turns.count - 2], turns[turns.count - 1], x0 - 6, x0 + textWidth + 6),
                   above > texts[k].minY - 8 {
                    drop += above - texts[k].minY + 9
                    changed = true
                }
            }
            let hugs = texts.indices.map { k -> CGRect in
                let wide = k < widths.count ? min(textWidth, max(40, widths[k])) : textWidth
                return CGRect(x: leading[k] ? texts[k].minX : texts[k].maxX - wide, y: texts[k].minY,
                              width: wide, height: texts[k].height)
            }
            result = RoadPlan(line: line, dots: dots, texts: texts, leading: leading, branches: branches, loops: loops,
                              hugs: hugs,
                              height: max(texts[count - 1].maxY, end.y + lastDot) + 6)
            if !changed { break }
        }
        return result
    }

    /// A stop's sentence with the spaces a line must not break at made hard
    /// (18:26: „zadbaj o prawidłowe łamania tekstów”): after a one-letter
    /// word ("w", "z", "i"), inside a number and between a number and its
    /// word ("20 000 dolarów", "nr 175", "VIII wystawa"), inside a short
    /// telling name (between ** and **), and before the last word, so the
    /// last line is not one word. Nothing longer than 22 letters is tied.
    static func typeset(_ text: String) -> String {
        let words = text.split(separator: " ", omittingEmptySubsequences: true).map(String.init)
        guard words.count > 1 else { return text }
        func core(_ word: String) -> String {
            String(word.replacingOccurrences(of: "**", with: "").drop { "„(".contains($0) })
        }
        func bare(_ word: String) -> String {
            var out = Substring(core(word))
            while let last = out.last, ".,;:!?”)".contains(last) { out.removeLast() }
            return String(out)
        }
        /// Whether a phrase ends with the word.
        func ends(_ word: String) -> Bool {
            guard let last = core(word).last else { return false }
            return ",;:!?".contains(last) || (last == "." && bare(word).count > 3)
        }
        func digits(_ word: String) -> Bool { !word.isEmpty && word.allSatisfy { ("0"..."9").contains($0) } }
        func marks(_ word: String) -> Int { word.components(separatedBy: "**").count - 1 }
        var out = words[0], chunk = core(words[0]).count
        var bold = marks(words[0]) % 2 == 1
        for i in 1..<words.count {
            let a = bare(words[i - 1]), b = bare(words[i]), length = core(words[i]).count
            let room = chunk + 1 + length <= 22
            var tie = room && bold
            if !tie, !ends(words[i - 1]) {
                if a.count == 1, a.first?.isLetter == true {
                    tie = true
                } else if room, digits(a), digits(String(b.prefix(3))), b.count >= 3 {
                    tie = true
                } else if room, a.count <= 3, let first = b.first, ("0"..."9").contains(first) {
                    tie = true
                } else if room, digits(a), !(a.count == 4 && ("1000"..."2099").contains(a)) {
                    tie = true
                } else if room, !a.isEmpty, a.allSatisfy({ "IVXLC".contains($0) }) {
                    tie = true
                }
            }
            if !tie, i == words.count - 1, core(words[i - 1]).count + 1 + length <= 16 { tie = true }
            out += (tie ? "\u{00A0}" : " ") + words[i]
            chunk = tie ? chunk + 1 + length : length
            if marks(words[i]) % 2 == 1 { bold.toggle() }
        }
        return out
    }

    /// Where to break words of these widths into lines no wider than
    /// `width`: as few lines as it takes and, of those, the most even ones
    /// (the least sum of squares of what each line leaves free), with no
    /// short word alone on a line where that can be helped. The index of
    /// the first word of each line after the first. A word wider than a
    /// line has a line to itself.
    static func evenBreaks(_ widths: [CGFloat], space: CGFloat, width: CGFloat) -> [Int] {
        let count = widths.count
        guard count > 1 else { return [] }
        var before: [CGFloat] = [0]
        for word in widths { before.append(before[before.count - 1] + word) }
        func span(_ i: Int, _ j: Int) -> CGFloat { before[j] - before[i] + space * CGFloat(j - i - 1) }
        var lines = 1, start = 0
        for j in 1..<count where span(start, j + 1) > width {
            lines += 1
            start = j
        }
        guard lines > 1 else { return [] }
        let never = CGFloat.greatestFiniteMagnitude
        // best[l][j]: the first j words in l lines.
        var best = [[CGFloat]](repeating: [CGFloat](repeating: never, count: count + 1), count: lines + 1)
        var from = [[Int]](repeating: [Int](repeating: 0, count: count + 1), count: lines + 1)
        best[0][0] = 0
        for l in 1...lines {
            for j in l...count {
                for i in (l - 1)..<j where best[l - 1][i] < never {
                    let wide = span(i, j)
                    guard wide <= width || j - i == 1 else { continue }
                    // A short word alone on a line counts against the breaks.
                    let free = max(0, width - wide), alone = j - i == 1 && free > width * 0.4
                    let cost = best[l - 1][i] + free * free + (alone ? width * width / 4 : 0)
                    if cost < best[l][j] {
                        best[l][j] = cost
                        from[l][j] = i
                    }
                }
            }
        }
        guard best[lines][count] < never else { return [] }
        var starts: [Int] = [], j = count
        for l in stride(from: lines, to: 1, by: -1) {
            j = from[l][j]
            starts.append(j)
        }
        return starts.reversed()
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
    static func nibStroke(_ line: [CGPoint], until end: CGPoint, clear: CGFloat, nib: CGFloat = JourneyRoad.nib) -> [CGPoint] {
        var cut = line.count
        while cut > 0, hypot(line[cut - 1].x - end.x, line[cut - 1].y - end.y) < clear { cut -= 1 }
        let dx = cos(nibTilt) * nib / 2, dy = sin(nibTilt) * nib / 2
        let body = line[..<cut]
        return body.map { CGPoint(x: $0.x + dx, y: $0.y + dy) } + body.reversed().map { CGPoint(x: $0.x - dx, y: $0.y - dy) }
    }

    /// A side trip's branch inked with the pen lifted: the outlines of short
    /// strokes of a narrower nib along it, the last one short of its dot.
    static func dashes(_ way: [CGPoint], until end: CGPoint) -> [[CGPoint]] {
        let fine = even(way, step: 1).filter { hypot($0.x - end.x, $0.y - end.y) > 6.5 }
        var out: [[CGPoint]] = []
        for start in stride(from: 0, to: fine.count, by: branchDash.on + branchDash.off) {
            let stroke = Array(fine[start..<min(fine.count, start + branchDash.on + 1)])
            guard stroke.count >= 3 else { break }
            out.append(nibStroke(stroke, until: end, clear: 0, nib: branchNib))
        }
        return out
    }

    /// A loop drawn by hand in a box, the way one circles a word: a rounded
    /// shape that wanders a little and drifts outward as it goes round, so
    /// its ends run past each other. It goes through its stop's dot, which
    /// is towards the top right corner or the top left one.
    static func loop(_ box: CGRect, dotRight: Bool, random: inout SeededRandom) -> [CGPoint] {
        let start = (dotRight ? 0.62 : 0.38) * CGFloat.pi + (random.unit() - 0.5) * 0.3
        let turn: CGFloat = dotRight ? -1 : 1, sweep = 2 * CGFloat.pi + 0.42 + 0.2 * random.unit()
        let sway = random.unit() * 2 * .pi, ripple = random.unit() * 2 * .pi
        func wander(_ t: CGFloat) -> CGFloat {
            let angle = start + turn * t * sweep
            return 0.05 * (t - 0.5) + 0.022 * sin(2 * angle + sway) + 0.014 * sin(3 * angle + ripple)
        }
        // Where the dot is on the way round: there the loop is on the box's own curve.
        let atDot = (dotRight ? start + .pi / 4 : 1.25 * .pi - start) / sweep
        let steps = 44, power = 2 / loopPower
        let points = (0...steps).map { q -> CGPoint in
            let t = CGFloat(q) / CGFloat(steps), angle = start + turn * t * sweep
            let grow = 1 + wander(t) - wander(atDot)
            let c = cos(angle), s = sin(angle)
            return CGPoint(x: box.midX + box.width / 2 * grow * (c < 0 ? -1 : 1) * pow(abs(c), power),
                           y: box.midY + box.height / 2 * grow * (s < 0 ? -1 : 1) * pow(abs(s), power))
        }
        return spline(points, per: 6)
    }

    /// A drop of paint in a run between two stains.
    struct Drop: Equatable {
        var at: CGPoint
        var radius: CGFloat
    }

    /// The underpainting's parts: a stain under each text as it stands
    /// (`hugs`), and drops in a row from each to the next, so that all of
    /// it is one wash (22:18); not across a sea.
    static func underpainting(under hugs: [CGRect], seas: [Bool], width: CGFloat, seed: String)
        -> (stains: [[CGPoint]], drops: [Drop]) {
        let stains = hugs.indices.map { stain(under: hugs[$0], seed: seed + "wash\($0)") }
        var drops: [Drop] = []
        for i in hugs.indices.dropLast() where !(i + 1 < seas.count && seas[i + 1]) {
            var random = SeededRandom(seed + "neck\(i)")
            drops += neck(from: hugs[i], to: hugs[i + 1], width: width, random: &random)
        }
        return (stains, drops)
    }

    static func stain(under box: CGRect, seed: String) -> [CGPoint] {
        var random = SeededRandom(seed)
        return stain(under: box, random: &random)
    }

    /// A stain of watercolour under a text: a closed rounded shape a little
    /// bigger than the text, off its middle and uneven all round.
    static func stain(under box: CGRect, random: inout SeededRandom) -> [CGPoint] {
        let long = box.width / 2 + 15 + 12 * random.unit(), short = (box.height - 3) / 2 + 9 + 8 * random.unit()
        let tilt = (random.unit() - 0.5) * 0.16
        let centre = CGPoint(x: box.midX + (random.unit() - 0.5) * 14, y: box.midY + 1.5 + (random.unit() - 0.5) * 8)
        let sides = 26, power: CGFloat = 2 / 2.3
        let first = random.unit() * 2 * .pi, second = random.unit() * 2 * .pi, third = random.unit() * 2 * .pi
        var ring: [CGPoint] = []
        for q in 0..<sides {
            let turn = CGFloat(q) / CGFloat(sides) * 2 * .pi, c = cos(turn), s = sin(turn)
            let uneven = 0.15 * sin(2 * turn + first) + 0.1 * sin(3 * turn + second) + 0.05 * sin(5 * turn + third)
            let reach = 1 + uneven + 0.06 * (random.unit() - 0.5)
            let x = long * reach * (c < 0 ? -1 : 1) * pow(abs(c), power)
            let y = short * reach * (s < 0 ? -1 : 1) * pow(abs(s), power)
            ring.append(CGPoint(x: centre.x + x * cos(tilt) - y * sin(tilt), y: centre.y + x * sin(tilt) + y * cos(tilt)))
        }
        // Round again past the start, so the spline closes smoothly.
        ring += ring[0..<3]
        return Array(spline(ring, per: 5).dropFirst(5).dropLast(5))
    }

    /// The paint that ran from one stain to the next: drops in a row from
    /// the foot of one to the head of the other, about the middle of the
    /// road, a little off the straight, each over the next.
    static func neck(from upper: CGRect, to lower: CGRect, width: CGFloat, random: inout SeededRandom) -> [Drop] {
        let high = min(upper.maxX - 26, max(upper.minX + 26, width / 2 + (random.unit() - 0.5) * 30))
        let low = min(lower.maxX - 26, max(lower.minX + 26, width / 2 + (random.unit() - 0.5) * 30))
        let from = CGPoint(x: high, y: upper.maxY - 8), to = CGPoint(x: low, y: lower.minY + 11)
        let far = hypot(to.x - from.x, to.y - from.y), count = max(2, Int((far / 22).rounded(.up)))
        var drops: [Drop] = []
        for q in 0...count {
            let part = CGFloat(q) / CGFloat(count)
            let bend = sin(part * .pi) * (random.unit() - 0.5) * 26
            let radius = (far > 90 ? 10 : 13) + 6 * random.unit() + 3 * sin(part * .pi)
            drops.append(Drop(at: CGPoint(x: from.x + (to.x - from.x) * part + bend, y: from.y + (to.y - from.y) * part),
                              radius: radius))
        }
        return drops
    }

    /// White beside the line, as if it had been corrected: a few strokes
    /// of a dry brush along it, about one for every 360 pt, each on one
    /// side of it or the other. A stroke is `bristles` outlines side by
    /// side, each starting and ending where it will, with torn edges, so
    /// the stroke is ragged and frayed at its ends. None past `end`.
    static func corrections(along line: [CGPoint], until end: CGPoint, seed: String) -> [[CGPoint]] {
        var cut = line.count
        while cut > 0, hypot(line[cut - 1].x - end.x, line[cut - 1].y - end.y) < lastClear { cut -= 1 }
        guard cut > 80 else { return [] }
        var random = SeededRandom(seed + "white")
        let count = max(2, Int((CGFloat(cut) * 2 / 360).rounded()))
        var strokes: [[CGPoint]] = []
        for k in 0..<count {
            let length = Int((28 + 34 * random.unit()).rounded())
            let spot = (CGFloat(k) + 0.15 + 0.7 * random.unit()) / CGFloat(count)
            let at = min(cut - length - 6, max(6, Int((CGFloat(cut) * spot).rounded())))
            let side = (random.unit() < 0.5 ? -1 : 1) * (4.4 + 1.6 * random.unit()), wide = 3.4 + 1.8 * random.unit()
            for b in 0..<bristles {
                let from = Int((7 * random.unit()).rounded()), to = length - Int((9 * random.unit()).rounded())
                let middle = side + (CGFloat(b) - CGFloat(bristles - 1) / 2) * wide / CGFloat(bristles)
                let half = wide / CGFloat(bristles) * (0.5 + 0.25 * random.unit())
                var one: [CGPoint] = [], other: [CGPoint] = []
                for q in from...to {
                    let p = line[at + q], before = line[max(0, at + q - 3)], after = line[min(cut - 1, at + q + 3)]
                    let step = max(1e-3, hypot(after.x - before.x, after.y - before.y))
                    let across = CGPoint(x: -(after.y - before.y) / step, y: (after.x - before.x) / step)
                    let off = middle + 0.8 * sin(CGFloat(q) / CGFloat(length) * 5 + CGFloat(k))
                    let out = off + half + 1.1 * (random.unit() - 0.5), back = off - half + 1.1 * (random.unit() - 0.5)
                    one.append(CGPoint(x: p.x + across.x * out, y: p.y + across.y * out))
                    other.append(CGPoint(x: p.x + across.x * back, y: p.y + across.y * back))
                }
                strokes.append(one + other.reversed())
            }
        }
        return strokes
    }

    /// White round the last dot, laid on with a brush: an uneven disc.
    static func halo(round dot: CGPoint, random: inout SeededRandom) -> [CGPoint] {
        let sides = 14, sway = random.unit() * 2 * .pi
        var ring = (0..<sides).map { q -> CGPoint in
            let turn = CGFloat(q) / CGFloat(sides) * 2 * .pi
            let reach = 14.5 * (1 + 0.1 * sin(2 * turn + sway) + 0.12 * (random.unit() - 0.5))
            return CGPoint(x: dot.x + reach * cos(turn), y: dot.y + reach * sin(turn))
        }
        ring += ring[0..<3]
        return Array(spline(ring, per: 5).dropFirst(5).dropLast(5))
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
