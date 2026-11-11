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
/// word. Under each text lies a stain of watercolour that ran and dried
/// with a sharp edge (white at first, an underpainting; dark since
/// 2026-11-11, see below); beside the black line there was, until
/// 2026-11-11 16:39, white here and there, as if the line had been
/// corrected, and at first white round the last dot too (18:48: „białym jakby korekty linii obok czarnej
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
/// there, the dots come up on it, the paint under the texts soaks into
/// the paper, and each text comes up out of it
/// (`RoadReveal`). The line comes out from under the rule below the
/// figures (22:21: „start kreski niech zaczyna się spod linii nad którą są
/// liczby”), and its turns, wide at the top, get narrower all the way
/// down (22:22: „zwężać się coraz bardziej ku dołowi”).
///
/// Since 2026-11-11 the pen goes first and the paint is dark (08:29:
/// „Kreska maluje się trochę szybciej niż powstają plamy i teksty (czyli
/// rysuje się niżej na ekranie) cieńszą kreską i potem grubnie. Na niej
/// powstają kropki jak teraz i z nich rozlewają się plamy pod tekst (czyli
/// plamy ciemnej farby (zanikające do ciemnoszarej akwareli) spływającej w
/// dół) a na plamach pojawiają się teksty koloru białego (daty nadal
/// czerwone). W animacji trochę więcej dynamizmu, drobinek nierównego
/// tuszu przy kresce, małych korekt białym przy linii”; 08:55, on the
/// sketch: „Za dużo małych kropeczek… jak przy zbyt szybkim rysowaniu
/// stalówką. Np. tylko przy zakrętach, mogą być po chwili korygowane
/// białym korektorem. Plamy… powinny powstawać jak akwarela (zaczynając
/// się od kropki) i nie spływać tak bardzo w dół. Czyli najpierw pojawia
/// się kropka, a z niej po chwili wylewa się jak akwarela plama pod tekst.
/// Plama może rozwiązać się czasami przy krawędzi. W motywie ciemnym
/// tekst czarny, a plamy pod nim białe”). The line's tip runs ahead, lower
/// on the screen, thin, and the line thickens behind it (`RoadLine`). A
/// stop begins when its dot is up at the middle of the screen: the dot,
/// then its stain spreading out of the dot under the text (`RoadStain`),
/// then the text on the stain. The stain is ink poured, not paint washed
/// in (09:11: „Rozlewanie tuszu a nie jego rozmywanie… papier na krawędzi
/// plam nasiąkał tuszem i już mniej mocnym odcieniem powstaje fragmentami
/// drugie halo plamy”). Each stop has a stain of its own; they are
/// no longer one wash, which in dark paint would be a band down the page
/// with the line lost in it.
///
/// 09:44, on the sketch of that („Jest pięknie! Rewelacja! Trzy ostatnie
/// uwagi”): „czerwona kropka na końcu także jako plama akwareli, bez
/// białego otoku. Na styku z czernią miesza się jak prawdziwa akwarela.”
/// (`RoadBlot`); „odnoga wystawy - okrąg musi się rysować po plamie, nie od
/// góry, tylko jako zakreślenie od początku do końca. Kreskowana linia do
/// niego prowadząca musi wyglądać realistyczniej i powstawać (rysować) się
/// kreseczkami.” (`RoadBranch`); „gdy cofam ekran rysunek niech zanika
/// (czyli odwrócona animacja.” (`RoadReveal`: a stop whose dot is under
/// the middle of the screen again is undone, its clock running back, and
/// the line draws back up).
///
/// 10:20, on the sketch of that („Jest cudownie!”): „A może dodać sekcje
/// „Dalsze losy” jako kontynuację linii Drogi dzieła, tylko innym kolorem
/// plam? Zaproponujesz coś? I wtedy kreska przy dalszych losach już prosta
/// z lewej, a informacje po jej prawej stronie. Na pewno zostawiamy
/// nagłówek sekcji Dalsze losy. Więc kreska mogłaby go np „opisywać” i
/// lecieć dalej?”; 10:39, on the sketch of that: „kreska wychodząca z
/// czerwonej kropki - to nie wygląda świetnie. Może niech po chwili, na
/// czerwonym kółku robi się okrągłe zakreślenie i to z niego wychodzi
/// dalsza kreska? Kreska przy dalszych losach nie aż tak prosta, z
/// odrobiną lekkości.” So with later works to tell of (`later`) the pen
/// goes on (`Onward`): a moment after the red blot is there it rings it,
/// once round, and out of that ring it goes down to the heading „Dalsze
/// losy”, round it the way one circles a word, and on down the left side
/// with a light hand. Each later work is a small blot of red on that
/// line; out of it a stain of indigo pours under the work's year and name
/// (one paint for all of them: his choice, 10:37), and where the red, the
/// indigo and the black meet they run into each other. What is told of
/// the work stays on the paper, to the right of the line.
///
/// 16:39, of the app: „Jednak bez białych „korekt” linii. Gdy szybko
/// przewijam stronę, to linie, plamy i opisy powinny pojawiać się
/// szybciej. Kropki bardziej dynamicznie. Bardziej jak „kleksy” przy
/// rysowaniu linii.” So there is no white beside the line any more, nor
/// over the nib's spatter; a page scrolled fast hurries the pen and the
/// stops' clocks (`RoadMarks.quick`, `hurry`); and a dot lands as a blot
/// off the nib: it bursts out ragged and settles, not quite round
/// (`DotMark`, `JourneyRoad.pop`).
struct JourneyRoad: View {
    let journey: DailyWork.Journey
    /// The work's id: the road's wander.
    let seed: String
    /// "Dalsze losy": the later works that drew on this one, told under
    /// the road as its going on. None: the road ends at its blot.
    var later: [DailyWork.Legacy] = []
    /// What is told of a later work under its year and name: its quote,
    /// its picture, a few words.
    var told: ((DailyWork.Legacy) -> AnyView)? = nil

    /// How big each stop's text is at the width the road gives it.
    @State private var sizes: [Int: CGSize] = [:]
    /// How big each stop's first line is, the one with its date and place.
    @State private var heads: [Int: CGSize] = [:]
    /// How wide the road is.
    @State private var width: CGFloat = 0
    /// "Dalsze losy", on the road: where its heading is, where each later
    /// work's year and name are and how big its year is, and where each
    /// later work ends.
    @State private var heading = CGRect.null
    @State private var tops: [Int: CGRect] = [:]
    @State private var years: [Int: CGSize] = [:]
    @State private var ends: [Int: CGFloat] = [:]
    /// How far the drawing has come.
    @State private var reveal = RoadReveal()
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.accessibilityVoiceOverEnabled) private var voiceOver

    /// A stop this far from the one before has crossed a sea.
    private static let seaKm = 2500.0
    /// The road's own coordinates, for what lies under it.
    private static let space = "journey-road"

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
        // Each sentence broken into its lines, and how wide each line is.
        let set = journey.stops.map { Self.setting($0.text, width: textWidth) }
        let spills = plan.flatMap { stains(under: $0, lines: set.map(\.lines)) }
        // Each side trip's branch, stroke by stroke; a stop with one waits for it.
        let hands = plan.map { Self.hands(of: $0, seed: seed) } ?? [:]
        // "Dalsze losy": each later work's name set, the line going on,
        // and each later work's stain and blot on it.
        let names = later.map { Self.setting(name($0), width: Self.nameWidth(width), plain: Self.nameFace, bold: Self.nameFace) }
        let onward = plan.flatMap { plan in spills.flatMap { goingOn(after: plan, stain: $0[count - 1]) } }
        let paints = onward.map { poured(along: $0, names: names.map(\.lines)) }
        let marks = plan.map { plan in
            RoadMarks(plan, leads: plan.dots.indices.map { RoadMarks.lead(dashes: hands[$0]?.count ?? 0) },
                      onward: onward, ends: later.indices.map { ends[$0] ?? plan.height })
        }
        // Told here and not through `onChange`: of several changes in one
        // frame that runs for the first only, and what is under the road is
        // measured in several steps. The road stayed laid out as it was at
        // one of them, and the later works never came.
        reveal.expect(marks, still: still)
        let indigo = Ink.paint(Ink.indigo, dark: dark)
        // Each sea as a wash of watercolour the line is drawn into.
        let washes = plan.map { seaWashes(on: $0, seas: seas) } ?? [:]
        var soak = SeededRandom(seed + "soak")
        let paintSeed = Float(soak.next() % 50)
        let texts = ZStack(alignment: .topLeading) {
            ForEach(Array(journey.stops.enumerated()), id: \.offset) { i, stop in
                // Each text is measured where the layout first puts it and
                // then moved to its dot; the move does not change its height.
                // Measured before it is given the full width: a side trip's
                // loop is drawn round the text as it stands.
                Emerging(reveal: reveal, index: i, height: plan?.texts[i].height ?? 1) {
                    row(stop, index: i, text: set[i].text, leading: plan?.leading[i] ?? true, dark: dark)
                        .onGeometryChange(for: CGSize.self) { $0.size } action: { self.sizes[i] = $0 }
                }
                .frame(width: textWidth, alignment: plan?.leading[i] ?? true ? .topLeading : .topTrailing)
                .offset(x: plan?.texts[i].minX ?? 0, y: plan?.texts[i].minY ?? 0)
                .opacity(plan == nil ? 0 : 1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .frame(height: plan?.height, alignment: .topLeading)
        return VStack(alignment: .leading, spacing: 0) {
            texts
            if !later.isEmpty {
                laterColumn(names: names.map(\.text), first: count + 1)
                    .opacity(plan == nil ? 0 : 1)
            }
        }
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { self.width = $0 }
        .coordinateSpace(.named(Self.space))
        .background(alignment: .topLeading) {
            if let plan, let spills {
                // No specks on a stain, nor on a sea's wet wash.
                let ink = RoadInk(plan: plan, seed: seed, top: top, flow: Self.inkFlow(plan.line.count, seed: seed),
                                  stains: spills.map(\.box) + washes.sorted { $0.key < $1.key }.map(\.value.box))
                ZStack(alignment: .topLeading) {
                    // Under everything, the seas' washes: the line is drawn into them wet.
                    ForEach(washes.keys.sorted(), id: \.self) { i in
                        if let wash = washes[i] {
                            SeaWash(reveal: reveal, wash: wash, dark: dark, seed: paintSeed + 61 + Float(3 * i))
                        }
                    }
                    // The stains: one under each text, out of its dot.
                    ForEach(spills.indices, id: \.self) { i in
                        RoadStain(reveal: reveal, index: i, spill: spills[i], dark: dark, seed: paintSeed + Float(7 * i))
                    }
                    // And one of indigo under each later work's year and name.
                    if let paints {
                        ForEach(paints.indices, id: \.self) { k in
                            RoadStain(reveal: reveal, index: count + 1 + k, spill: paints[k].spill, dark: dark,
                                      seed: paintSeed + 31 + Float(7 * k), ink: indigo)
                        }
                    }
                    // The seas come up softly, a little behind the pen.
                    Canvas { context, size in drawSeas(in: &context, size: size, plan: plan, seas: seas) }
                        .mask { Curtain(reveal: reveal, soft: 44, behind: 30) }
                    // What the pen leaves as it passes, as far as it has come.
                    InkCanvas(ink: ink, part: .pen)
                        .equatable()
                        // Masked before it is moved up: the mask is as big as what it masks.
                        .mask { Curtain(reveal: reveal, soft: 5, above: top) }
                        .padding(.top, -top)
                    RoadLine(reveal: reveal, ink: ink)
                    ForEach(hands.keys.sorted(), id: \.self) { i in
                        RoadBranch(reveal: reveal, index: i, dashes: hands[i] ?? [], ring: ring(round: i, of: plan))
                    }
                    RoadDots(reveal: reveal, plan: plan, seed: seed)
                    // The line going on: round the blot, round "Dalsze losy" and down the left.
                    if let onward {
                        OnwardLine(reveal: reveal, onward: onward, last: count - 1)
                    }
                    // Where the work is now: a blot of red at the end of the line.
                    RoadBlot(reveal: reveal, index: count - 1,
                             blot: Self.blot(for: spills[count - 1], line: plan.line, seed: seed),
                             dark: dark, seed: paintSeed + 3)
                    // And a small one on the line for each later work.
                    if let paints {
                        ForEach(paints.indices, id: \.self) { k in
                            RoadBlot(reveal: reveal, index: count + 1 + k, blot: paints[k].blot, dark: dark,
                                     seed: paintSeed + 41 + Float(5 * k), small: true, paint: indigo.dense)
                        }
                    }
                }
                .allowsHitTesting(false)
                .accessibilityHidden(true)
            }
        }
        // Where the screen is on the road: its middle is where the drawing comes about.
        .onGeometryChange(for: CGRect.self) { $0.bounds(of: .scrollView) ?? .null } action: { reveal.look($0) }
        .background { RoadClock(reveal: reveal) }
    }

    /// "Dalsze losy" under the road: its heading, which the line goes
    /// round, and each later work to the right of the line: its year and
    /// its name on a stain of paint, and under them, on the paper, what
    /// is told of it. `first`: the first later work's clock.
    private func laterColumn(names: [String], first: Int) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Dalsze losy")
                .font(.serif(20, weight: .semibold))
                .foregroundStyle(Theme.ink)
                .accessibilityAddTraits(.isHeader)
                .onGeometryChange(for: CGRect.self) { $0.frame(in: .named(Self.space)) } action: { self.heading = $0 }
                .padding(.leading, Self.rail + Self.lassoPad.side)
                .padding(.top, Self.laterGap)
                // The page's own name for this section, to scroll to.
                .id("legacy")
            ForEach(Array(later.enumerated()), id: \.offset) { k, entry in
                VStack(alignment: .leading, spacing: 0) {
                    // Measured outside what brings it up: that moves it a little.
                    Emerging(reveal: reveal, index: first + k, height: tops[k]?.height ?? 1) {
                        laterHead(entry, index: k, name: names[k])
                    }
                    .onGeometryChange(for: CGRect.self) { $0.frame(in: .named(Self.space)) } action: { self.tops[k] = $0 }
                    if let told {
                        Told(reveal: reveal, index: first + k) { told(entry) }
                            .padding(.top, 14)
                            .padding(.leading, 2)
                    }
                }
                .onGeometryChange(for: CGFloat.self) { $0.frame(in: .named(Self.space)).maxY } action: { self.ends[k] = $0 }
                .padding(.leading, Self.laterInset)
                .padding(.top, 20)
            }
        }
        .padding(.bottom, 6)
    }

    /// A later work's year, in the hand and red as the road's dates, and
    /// its maker and title, on the stain.
    private func laterHead(_ entry: DailyWork.Legacy, index: Int, name: String) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            if !entry.year.isEmpty {
                Text(entry.year)
                    .font(.hand(21))
                    .foregroundStyle(Self.dateOnStain)
                    .lineLimit(1)
                    .onGeometryChange(for: CGSize.self) { $0.size } action: { self.years[index] = $0 }
            }
            Text(name)
                .font(.serif(16, weight: .semibold))
                .foregroundStyle(Self.onStain)
                .multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
    }

    /// A later work's maker and, when it has one, its title.
    private func name(_ entry: DailyWork.Legacy) -> String {
        entry.title.isEmpty ? Names.artist(entry.who) : "\(Names.artist(entry.who)), „\(entry.title)”"
    }

    /// The line going on from the road's end, once everything under the
    /// road is measured where the road has put it.
    private func goingOn(after plan: RoadPlan, stain: Spill) -> Onward? {
        guard !later.isEmpty, !heading.isNull, heading.minY >= plan.height else { return nil }
        var mids: [CGFloat] = []
        for k in later.indices {
            guard let top = tops[k], ends[k] != nil, top.minY > heading.maxY else { return nil }
            if later[k].year.isEmpty {
                mids.append(top.minY + 11)
            } else {
                guard let year = years[k] else { return nil }
                mids.append(top.minY + year.height / 2 + 1)
            }
        }
        let last = plan.dots.count - 1
        return Self.onward(from: plan.dots[last], past: stain.box, leading: plan.leading[last], heading: heading, years: mids,
                           width: width, seed: seed)
    }

    /// Each later work's stain, under its year and the lines of its name,
    /// and the blot on the line it pours out of.
    private func poured(along onward: Onward, names: [[CGFloat]]) -> [(spill: Spill, blot: Blot)] {
        later.indices.map { k -> (spill: Spill, blot: Blot) in
            let hug = tops[k] ?? .zero
            let rects = Self.lines(of: hug, head: later[k].year.isEmpty ? nil : years[k], widths: names[k], leading: true)
            let dot = onward.dots[k]
            let spill = Self.spill(under: rects, from: dot, line: Self.shelf(under: rects, width: width), width: width,
                                   height: hug.maxY + 100, seed: seed + "later\(k)")
            return (spill, Self.blot(on: onward, at: k, spill: spill, seed: seed))
        }
    }

    /// The loop round a side trip's text.
    private func ring(round index: Int, of plan: RoadPlan) -> Path? {
        guard let frame = plan.loops[index] else { return nil }
        var random = SeededRandom(seed + "loop\(index)")
        var ring = Path()
        ring.addLines(Self.loop(frame, dotRight: !plan.leading[index], random: &random))
        return ring
    }

    /// Each stop's stain, once every text's lines are known: the first
    /// line of a stop (its date and place) is measured as it stands.
    private func stains(under plan: RoadPlan, lines: [[CGFloat]]) -> [Spill]? {
        var out: [Spill] = []
        for (i, stop) in journey.stops.enumerated() {
            let headed = !(stop.year.isEmpty && stop.place.isEmpty)
            if headed, heads[i] == nil { return nil }
            let rects = Self.lines(of: plan.hugs[i], head: headed ? heads[i] : nil, widths: lines[i], leading: plan.leading[i])
            out.append(Self.spill(under: rects, from: plan.dots[i], line: plan.line, width: width, height: plan.height,
                                  seed: seed + "spill\(i)"))
        }
        return out
    }

    private func row(_ stop: DailyWork.Journey.Stop, index: Int, text: String, leading: Bool, dark: Bool) -> some View {
        // The date in the hand, always the end of the line that is at the dot
        // (18:04: „czerwone daty zawsze przy kropce. Daty pismem pisanym”):
        // first where the text reads from its dot, last where it ends at it.
        // A stop the record gives no date for has none here either, and
        // no line at all when it has no place (22:20: „Powtórzenia w
        // opisach braku daty są irytujące”; the server no longer writes
        // "bez daty"). The text lies on its stain: white on the dark paint,
        // black on the white paint of the dark page, the date red on both
        // (2026-11-11: „teksty koloru białego (daty nadal czerwone)… w
        // motywie ciemnym tekst czarny, a plamy pod nim białe”).
        let soft = Self.onStain.opacity(dark ? 0.62 : 0.76)
        let date = Text(stop.year).font(.hand(21)).foregroundStyle(Self.dateOnStain)
        let place = Text(stop.place).font(.caption).foregroundStyle(soft)
        let between = Text(stop.place.isEmpty || stop.year.isEmpty ? "" : " · ").font(.caption).foregroundStyle(soft)
        return VStack(alignment: leading ? .leading : .trailing, spacing: 0) {
            if !(stop.year.isEmpty && stop.place.isEmpty) {
                (leading ? Text("\(date)\(between)\(place)") : Text("\(place)\(between)\(date)"))
                    .lineLimit(1)
                    .truncationMode(leading ? .tail : .head)
                    // Its own size: the stain is cut to the text's lines.
                    .onGeometryChange(for: CGSize.self) { $0.size } action: { self.heads[index] = $0 }
            }
            Text(Self.marked(text))
                .font(.serif(15))
                .foregroundStyle(Self.onStain)
                .multilineTextAlignment(leading ? .leading : .trailing)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
    }

    /// The sentence set for a column this wide (18:26: „zadbaj o prawidłowe
    /// łamania tekstów”): its hard spaces put in (`typeset`), and broken
    /// into as few lines as it takes, of about the same length, so that a
    /// line is never one word between two full ones. The words are
    /// measured in the faces the text is drawn in. With it, how wide each
    /// of its lines is: a stop's stain keeps to them.
    static func setting(_ text: String, width: CGFloat) -> (text: String, lines: [CGFloat]) {
        setting(text, width: width, plain: face, bold: boldFace)
    }

    /// The same in other faces: `plain`, and `bold` between ** and **.
    static func setting(_ text: String, width: CGFloat, plain face: UIFont, bold boldFace: UIFont) -> (text: String, lines: [CGFloat]) {
        let set = typeset(text)
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
        let starts = width > 40 ? evenBreaks(widths, space: space, width: width - 3) : []
        var lines: [CGFloat] = [], from = 0
        for to in starts + [chunks.count] {
            let words = widths[from..<to].reduce(0, +)
            lines.append(words + space * CGFloat(max(0, to - from - 1)))
            from = to
        }
        let breaks = Set(starts)
        let broken = chunks.enumerated().map { k, chunk in (k == 0 ? "" : breaks.contains(k) ? "\n" : " ") + chunk }.joined()
        return (width > 40 ? broken : set, lines)
    }

    static func broken(_ text: String, width: CGFloat) -> String { setting(text, width: width).text }

    /// `Font.serif(15)` and its bold, to measure words with.
    private static let face = serifFace(.regular)
    private static let boldFace = serifFace(.bold)

    /// `Font.serif(16, weight: .semibold)`: a later work's name.
    static let nameFace = serifFace(.semibold, size: 16)

    private static func serifFace(_ weight: UIFont.Weight, size: CGFloat = 15) -> UIFont {
        let base = UIFont.systemFont(ofSize: size, weight: weight)
        return base.fontDescriptor.withDesign(.serif).map { UIFont(descriptor: $0, size: size) } ?? base
    }

    /// A later work's name is no wider than this on a road `width` wide.
    static func nameWidth(_ width: CGFloat) -> CGFloat { max(120, min(290, width - laterInset - 10)) }

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
            let band = Self.seaBand(before: i, on: plan)
            drawSea(in: &context, name: sea(i), top: band.top, bottom: band.bottom,
                    width: size.width, plan: plan, random: &random)
        }
    }

    /// Each sea's wash (`SeaWash`), by the stop that is over that sea.
    private func seaWashes(on plan: RoadPlan, seas: [Bool]) -> [Int: Wash] {
        var out: [Int: Wash] = [:]
        for i in plan.dots.indices.dropFirst() where i < seas.count && seas[i] {
            let band = Self.seaBand(before: i, on: plan)
            out[i] = Self.wash(top: band.top, bottom: band.bottom, line: plan.line, width: width)
        }
        return out
    }

    /// A sea as on a map: rows of short waves that keep clear of the road
    /// and of the texts with their stains, and the name between two rows,
    /// where there is room.
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
                    if inText(p, 22) || near.contains(where: { abs($0.x - p.x) < 9 && abs($0.y - p.y) < 7 }) {
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

    private static let sea = Color(light: 0x6E8FA8, dark: 0x86A6BC)

    fileprivate static func closed(_ points: [CGPoint]) -> Path {
        var path = Path()
        path.addLines(points)
        path.closeSubpath()
        return path
    }
}

// MARK: The drawing coming about

/// Where the stops are down the road, and how fast the pen goes (2026-11-11:
/// „kreska maluje się trochę szybciej niż powstają plamy i teksty (czyli
/// rysuje się niżej na ekranie) cieńszą kreską i potem grubnie”). The tip
/// of the line runs ahead of the middle of the screen; its full width
/// follows in time. A stop begins when its dot has come up to the middle
/// of the screen, one stop after another, and from then on it runs on its
/// own clock. When the page goes back the drawing goes back too (09:44:
/// „gdy cofam ekran rysunek niech zanika (czyli odwrócona animacja”): a
/// stop whose dot is well under the middle of the screen again is undone,
/// its clock running backwards, faster, and the line draws back up.
struct RoadMarks: Equatable {
    /// Each stop's dot and the foot of its text, down the road.
    var dots: [CGFloat] = []
    var feet: [CGFloat] = []
    var height: CGFloat = 0
    /// How long each stop waits for its branch to be drawn, stroke after
    /// stroke, before its dot comes up: a side trip's; the others do not wait.
    var leads: [CGFloat] = []
    /// The road's own height. With "Dalsze losy" under it `height` is more:
    /// after the road's stops come the loop round that heading and then
    /// the later works, each with a clock as a stop has.
    var road: CGFloat = 0
    /// A clock that stops sooner than a stop's (`clock.dry`): the loop's.
    var spans: [Int: CGFloat] = [:]
    /// The line goes on past this stop's dot only when the stop has run
    /// this long: at the road's end, until its blot is ringed, and at the
    /// heading "Dalsze losy", until it is circled.
    var gates: [Int: CGFloat] = [:]
    /// This stop begins only when the one before it has run this long:
    /// the first later work, when the heading is circled.
    var after: [Int: CGFloat] = [:]

    /// Past the road's end: everything is drawn.
    var full: CGFloat { height + 60 }

    init() {}

    /// `onward`: the line going on into "Dalsze losy"; `ends`: where each
    /// later work ends, down the road.
    init(_ plan: RoadPlan, leads: [CGFloat] = [], onward: JourneyRoad.Onward? = nil, ends: [CGFloat] = []) {
        height = plan.height
        road = plan.height
        dots = plan.dots.map(\.y)
        feet = plan.texts.map(\.maxY)
        self.leads = leads
        guard let onward, !dots.isEmpty, ends.count == onward.marks.count else { return }
        let last = dots.count - 1
        gates[last] = Self.ring.at + Self.ring.takes
        // And past the heading only when it is circled.
        gates[last + 1] = Self.lasso
        dots.append(onward.loopY)
        feet.append(onward.foot)
        spans[last + 1] = Self.lasso + 0.05
        after[last + 2] = Self.lasso
        dots += onward.dots.map(\.y)
        feet += ends
        height = max(height, (ends.max() ?? height) + 6)
    }

    /// How far under the middle of the screen the tip of the line is
    /// drawn, at the least; on a screen tall enough it is drawn `foot`
    /// over the bottom of what the bars leave of the screen, which is just
    /// over the tab bar (2026-11-11 11:56: „cienka kreska może się zaczyna
    /// rysować wcześniej, prawie u dołu ekranu”).
    static let ahead: CGFloat = 190
    static let foot: CGFloat = 20
    /// A stop begins with its dot this far under the middle of the screen
    /// (11:56: „Podobnie plamy pod teksty, trochę wcześniej niż teraz”),
    /// and no sooner than this long after the stop before it.
    static let near: CGFloat = 80
    static let apart: CGFloat = 0.3
    /// The slowest the tip and the full width go, in points a second, and
    /// how long each takes to catch up with what it follows.
    static let pace: (pen: CGFloat, thick: CGFloat) = (110, 50)
    static let lag: (pen: CGFloat, thick: CGFloat) = (0.9, 0.8)
    /// A page scrolled fast is not kept waiting (16:39: „gdy szybko
    /// przewijam stronę, to linie, plamy i opisy powinny pojawiać się
    /// szybciej”). The tip and the full width, more than `spur` points
    /// behind, go as many times faster as they are further behind than
    /// that. And a stop's clock: with the page going down `brisk` points a
    /// second, a stop is `owed` so many seconds by the time its dot is
    /// where it is on the screen; a stop younger than that runs its clock
    /// faster, catching up in `haste.takes` seconds, at most `haste.most`
    /// times as fast, and the next stop begins sooner after it, though
    /// never less than `haste.apart` later: still one after another.
    static let spur: CGFloat = 120
    static let brisk: CGFloat = 60
    static let haste: (takes: CGFloat, most: CGFloat, apart: CGFloat) = (0.3, 8, 0.08)
    /// A stop's clock, in seconds: its dot comes up at 0, a moment later
    /// (`spill`) the paint starts out of it (08:55: „najpierw pojawia się
    /// kropka, a z niej po chwili wylewa się jak akwarela plama pod
    /// tekst”), its text comes up from `text` for `emerge`, and by `dry`
    /// nothing in it changes any more.
    static let clock: (spill: CGFloat, text: CGFloat, emerge: CGFloat, dry: CGFloat) = (0.45, 1.1, 1.2, 6)
    /// A side trip's branch (09:44: „powstawać (rysować) się kreseczkami”):
    /// a stroke begins this long after the one before and takes this long;
    /// after the last there is a moment's rest, and then the stop's dot.
    static let dash: (apart: CGFloat, takes: CGFloat, rest: CGFloat) = (0.085, 0.065, 0.1)
    /// The loop round a side trip's text is drawn when its stain is there
    /// (09:44: „okrąg musi się rysować po plamie”): from this long after
    /// the stop's dot came up, for this long.
    static let loop: (at: CGFloat, takes: CGFloat) = (2, 1)
    /// A stop is undone when its dot is this far under the middle of the
    /// screen again; its clock then runs back by this much a second, or
    /// this many times its age when that is more. The pen catches up with
    /// a page going back in `retreat` seconds.
    static let back: CGFloat = 110
    static let undo: (slow: CGFloat, rate: CGFloat) = (2.2, 1.6)
    static let retreat: CGFloat = 0.5
    /// The ring round the blot at the road's end (10:39: „niech po chwili,
    /// na czerwonym kółku robi się okrągłe zakreślenie i to z niego
    /// wychodzi dalsza kreska”): drawn from this long after the blot came,
    /// for this long; only then does the line go on.
    static let ring: (at: CGFloat, takes: CGFloat) = (1.5, 0.75)
    /// How long the loop round the heading "Dalsze losy" takes.
    static let lasso: CGFloat = 0.9
    /// What is told of a later work comes up on the paper from this long
    /// after its blot, for this long.
    static let told: (at: CGFloat, takes: CGFloat) = (1.5, 0.9)

    /// How long a branch of `dashes` strokes takes.
    static func lead(dashes: Int) -> CGFloat {
        dashes > 0 ? CGFloat(dashes) * dash.apart + dash.rest : 0
    }

    /// How long stop `index` waits for its branch.
    func lead(_ index: Int) -> CGFloat { index < leads.count ? leads[index] : 0 }

    /// A stop's clock when nothing in it changes any more.
    func whole(_ index: Int) -> CGFloat { (spans[index] ?? Self.clock.dry) + lead(index) }

    /// How far under the middle of a screen the tip is drawn; `screen`:
    /// the height the bars leave of it (the scroll view's bounds).
    static func reach(screen: CGFloat) -> CGFloat { max(ahead, screen / 2 - foot) }

    /// How far the tip of the line is to go with the middle of the screen
    /// at `mid`, drawn `ahead` under it.
    func target(mid: CGFloat, ahead: CGFloat = RoadMarks.ahead) -> CGFloat { min(mid + ahead, full) }

    /// Whether stop `index` may begin: its dot is up near the middle of
    /// the screen and the line is drawn through it.
    func due(_ index: Int, mid: CGFloat, pen: CGFloat) -> Bool {
        dots[index] <= mid + Self.near && pen >= min(dots[index] + 4, full)
    }

    /// How many times faster the tip (or the full width) goes, `gap`
    /// points behind what it follows: 1 up to `spur`.
    static func quick(_ gap: CGFloat) -> CGFloat { 1 + max(0, gap - spur) / spur }

    /// How old stop `index` is owed to be with the middle of the screen at `mid`.
    func owed(_ index: Int, mid: CGFloat) -> CGFloat { (mid + Self.near - dots[index]) / Self.brisk }

    /// How many times as fast a stop's clock runs, `behind` seconds
    /// younger than it is owed to be: 1 when it is not behind.
    static func hurry(behind: CGFloat) -> CGFloat { min(haste.most, max(1, behind / haste.takes)) }

    /// How long after the stop before it a stop begins that is owed
    /// `owed` seconds already.
    static func wait(owed: CGFloat) -> CGFloat { max(haste.apart, apart / hurry(behind: owed)) }

    /// The tip and the full width a moment later: each goes faster the
    /// further behind it is (`quick`), and never slower than its pace. The
    /// tip stops at `target`, the full width at the tip. With the target
    /// over the tip (the page went back) the line draws back up to it,
    /// quicker.
    static func advance(pen: CGFloat, thick: CGFloat, target: CGFloat, passed: CGFloat) -> (pen: CGFloat, thick: CGFloat) {
        let ahead = target - pen
        let drawn = ahead >= 0
            ? min(target, pen + max(pace.pen, ahead / lag.pen * quick(ahead)) * passed)
            : max(target, pen - max(pace.pen, -ahead / retreat) * passed)
        let thin = drawn - thick
        let filled = min(drawn, thick + max(pace.thick, thin / lag.thick * quick(thin)) * passed)
        return (drawn, filled)
    }

    /// A stop's clock a moment later. `drawn`: the stop is to be there, and
    /// its clock runs on to `whole`; otherwise it runs back, and under 0
    /// the stop is gone (-1).
    static func older(_ age: CGFloat, drawn: Bool, whole: CGFloat, passed: CGFloat) -> CGFloat {
        if drawn { return min(whole, max(0, age) + passed) }
        guard age >= 0 else { return -1 }
        let left = age - max(undo.slow, undo.rate * age) * passed
        return left > 0 ? left : -1
    }
}

/// One stop's clock, in seconds: how long it has been drawing; under 0
/// it is not there. Each stop has its own, so only what belongs to a stop
/// in motion is drawn again.
@MainActor
@Observable
final class StopClock {
    var age: CGFloat = -1
}

/// How far the drawing has come. `pen` is a height on the road: down to
/// there the line is drawn, thin; `thick` follows it: down to there the
/// line has its full width. Both follow the middle of the screen as the
/// page is scrolled (22:18: „na środku ekranu w trakcie przewijania”), the
/// pen ahead of it. The stops begin one by one as their dots come up to
/// the middle of the screen, and are undone when the page goes back
/// (`RoadMarks`).
@MainActor
@Observable
final class RoadReveal {
    private(set) var pen = RoadReveal.before
    private(set) var thick = RoadReveal.before
    private(set) var stops: [StopClock] = []
    /// Nothing is moving: no need to keep time.
    private(set) var settled = true

    @ObservationIgnored private var marks = RoadMarks()
    @ObservationIgnored private var still = false
    /// How the view last worked the road out (`expect`).
    @ObservationIgnored private var asked: (marks: RoadMarks, still: Bool)?
    /// The part of the road on screen, and when it last moved.
    @ObservationIgnored private var seen = CGRect.null
    @ObservationIgnored private var looked = false
    @ObservationIgnored private var moved = Date.distantPast
    @ObservationIgnored private var last: Date?
    /// Which stops are to be there; the others are not, or are being undone.
    @ObservationIgnored private var drawn: [Bool] = []
    /// How long the drawing has been going, in seconds, and when the
    /// latest stop began.
    @ObservationIgnored private var time: CGFloat = 0
    @ObservationIgnored private var latest = -CGFloat.infinity
    /// The page came to rest with the road's end on screen, and the rest
    /// was drawn: where the middle of the screen was then.
    @ObservationIgnored private var ended: CGFloat?

    /// Before anything is drawn: over the rule the line comes out from.
    static let before: CGFloat = -50
    /// With the road's end on screen and the page at rest this long, the
    /// rest is drawn: nothing more will come to the middle of the screen.
    /// It stays until the page has gone back by `slack` (a bounce at the
    /// page's end is not going back).
    static let rest: TimeInterval = 1.2
    static let slack: CGFloat = 60
    /// CI screenshots: "-journeyWash 0.45" holds the drawing as it is with
    /// the middle of the screen that far down the road and the page
    /// scrolling; 1 and more is all of it, dry.
    static let held: CGFloat? = UserDefaults.standard.object(forKey: "journeyWash") == nil
        ? nil : CGFloat(UserDefaults.standard.double(forKey: "journeyWash"))

    /// How long ago stop `index` began: its dot came up at 0; under 0 it
    /// is not there (or only its branch is being drawn).
    func age(_ index: Int) -> CGFloat {
        guard index < stops.count else { return -1 }
        let age = stops[index].age
        return age < 0 ? -1 : age - marks.lead(index)
    }

    /// How long stop `index` has been drawing, its branch first.
    func drawing(_ index: Int) -> CGFloat { index < stops.count ? stops[index].age : -1 }

    /// The view has worked the road out (again): it is laid out so a moment
    /// later, when the view is done, as the view last worked it out.
    func expect(_ marks: RoadMarks?, still: Bool) {
        guard let marks else { return }
        if let asked, asked.marks == marks, asked.still == still { return }
        asked = (marks, still)
        Task { @MainActor [weak self] in
            guard let self, let asked = self.asked else { return }
            self.lay(asked.marks, still: asked.still)
        }
    }

    /// The road is laid out (or laid out again).
    func lay(_ marks: RoadMarks?, still: Bool) {
        guard let marks else { return }
        self.marks = marks
        self.still = still
        if stops.count != marks.dots.count {
            // The clocks that are running keep running: "Dalsze losy" is
            // measured a moment after the road and adds its own after them.
            let count = marks.dots.count, clocks = stops, were = drawn
            stops = (0..<count).map { $0 < clocks.count ? clocks[$0] : StopClock() }
            drawn = (0..<count).map { $0 < were.count ? were[$0] : false }
        }
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

    /// The middle of the screen on the road; past everything once the
    /// rest was drawn with the page at its end.
    private var mid: CGFloat { ended == nil ? seen.midY : .infinity }

    /// How far under the middle of this screen the tip of the line is drawn.
    private var ahead: CGFloat { seen.isNull ? RoadMarks.ahead : RoadMarks.reach(screen: seen.height) }

    /// How far the tip of the line is to be: ahead of the middle of the
    /// screen, never over a stop that is still there, and not past a stop
    /// the line is to wait at (`RoadMarks.gates`).
    private var target: CGFloat {
        var kept = -CGFloat.infinity
        for index in stops.indices where stops[index].age >= 0 { kept = max(kept, marks.dots[index] + 6) }
        var far = marks.target(mid: mid, ahead: ahead)
        for (index, long) in marks.gates where index < stops.count && age(index) < long {
            far = min(far, marks.dots[index] + 6)
        }
        return max(kept, far)
    }

    /// Whether the stop before `index` has run long enough for it to begin.
    private func ready(_ index: Int) -> Bool {
        guard index > 0, let long = marks.after[index] else { return true }
        return stops[index - 1].age >= long
    }

    private func aim() {
        guard looked, !marks.dots.isEmpty else { return }
        if let held = Self.held { return held >= 1 ? finish() : hold(held * marks.road) }
        if still || seen.isNull { return finish() }
        if let rested = ended, seen.midY < rested - Self.slack { ended = nil }
        // What is over the top of the screen is not watched: it is there at once.
        let over = min(seen.minY - 80, target)
        if pen < over { pen = over }
        if thick < over { thick = over }
        for index in drawn.indices where marks.feet[index] < seen.minY - 80 {
            drawn[index] = true
            let whole = marks.whole(index)
            if stops[index].age != whole { stops[index].age = whole }
        }
        if busy { settled = false }
    }

    /// All of it, dry.
    private func finish() {
        ended = nil
        if pen != marks.full { pen = marks.full }
        if thick != marks.full { thick = marks.full }
        for index in drawn.indices {
            drawn[index] = true
            let whole = marks.whole(index)
            if stops[index].age != whole { stops[index].age = whole }
        }
        last = nil
        if !settled { settled = true }
    }

    /// As it is with the middle of the screen at `mid` and the page
    /// scrolling steadily: the pen ahead, the stops above in turn.
    private func hold(_ mid: CGFloat) {
        let speed: CGFloat = 72
        pen = min(marks.full, mid + ahead - speed * RoadMarks.lag.pen)
        thick = pen - speed * RoadMarks.lag.thick
        for index in drawn.indices {
            let line = mid + RoadMarks.near
            let age = marks.dots[index] <= line ? min(marks.whole(index), (line - marks.dots[index]) / speed + 0.1) : -1
            drawn[index] = age >= 0
            if stops[index].age != age { stops[index].age = age }
        }
        last = nil
        if !settled { settled = true }
    }

    /// The road's end is on screen and not all of it is to be drawn yet.
    private var waits: Bool {
        ended == nil && !seen.isNull && seen.maxY >= marks.height
            && (marks.target(mid: seen.midY, ahead: ahead) < marks.full || drawn.contains(false))
    }

    /// Something is still to move.
    private var busy: Bool {
        if pen != target || thick < pen || waits { return true }
        for index in drawn.indices {
            if drawn[index] ? stops[index].age < marks.whole(index) : stops[index].age >= 0 { return true }
        }
        if let next = drawn.firstIndex(of: false), marks.dots[next] <= mid + RoadMarks.near { return true }
        return false
    }

    /// One frame on.
    func tick(_ now: Date) {
        guard !settled else { return }
        let passed = CGFloat(max(0, min(1.0 / 20, last.map { now.timeIntervalSince($0) } ?? 1.0 / 60)))
        last = now
        if waits, now.timeIntervalSince(moved) > Self.rest { ended = seen.midY }
        time += passed
        let mid = self.mid
        // The page went back: what is well under the middle of the screen again is undone.
        for index in drawn.indices where drawn[index] && marks.dots[index] > mid + RoadMarks.back {
            drawn[index] = false
        }
        // Where the middle of the screen is, also with the rest drawn at
        // the page's end: a stop left behind by a page scrolled fast hurries.
        let place = seen.isNull ? -CGFloat.infinity : seen.midY
        if let index = drawn.firstIndex(of: false), marks.due(index, mid: mid, pen: pen), ready(index),
           time >= latest + RoadMarks.wait(owed: marks.owed(index, mid: place)) {
            drawn[index] = true
            latest = time
        }
        for index in drawn.indices {
            let behind = marks.owed(index, mid: place) - max(0, stops[index].age)
            let rate = drawn[index] ? RoadMarks.hurry(behind: behind) : 1
            let age = RoadMarks.older(stops[index].age, drawn: drawn[index], whole: marks.whole(index), passed: passed * rate)
            if stops[index].age != age { stops[index].age = age }
        }
        let next = RoadMarks.advance(pen: pen, thick: thick, target: target, passed: passed)
        if next.pen != pen { pen = next.pen }
        if next.thick != thick { thick = next.thick }
        if !busy {
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

/// Black down to `edge`, clear under it, `soft` points of one going over
/// to the other: a mask for what is drawn down to there.
private struct Edge: View {
    var edge: CGFloat
    var soft: CGFloat

    var body: some View {
        GeometryReader { proxy in
            let tall = max(1, proxy.size.height)
            LinearGradient(colors: [.black, .clear],
                           startPoint: UnitPoint(x: 0.5, y: (edge - soft) / tall),
                           endPoint: UnitPoint(x: 0.5, y: edge / tall))
        }
    }
}

/// What the pen has passed. `above`: how far over the road's top the
/// masked view starts; `behind`: how far it lags.
private struct Curtain: View {
    let reveal: RoadReveal
    var soft: CGFloat
    var above: CGFloat = 0
    var behind: CGFloat = 0

    var body: some View {
        Edge(edge: reveal.pen - behind + above, soft: soft)
    }
}

/// What is inked on the road, drawn once: `body` is the line at its full
/// width, `pen` what the pen leaves as it passes (the drops of ink it
/// throws off at a turn).
private struct RoadInk: Equatable {
    var plan: RoadPlan
    var seed: String
    /// How far over the road's top the line starts.
    var top: CGFloat
    /// How full the nib runs along the line.
    var flow: [CGFloat]
    /// Where the stains and the seas' washes are: no specks there.
    var stains: [CGRect]

    private var end: CGPoint { plan.dots[plan.dots.count - 1] }

    /// The road itself, from under the rule (or from the first dot) to the
    /// last dot. Nothing white beside it (16:39: „Jednak bez białych
    /// „korekt” linii”; there had been since 2026-11-10 18:48).
    func drawBody(in context: inout GraphicsContext) {
        var stroke = Path()
        stroke.addLines(JourneyRoad.nibStroke(plan.line, until: end, clear: JourneyRoad.lastClear, flow: flow))
        stroke.closeSubpath()
        context.fill(stroke, with: .color(Theme.ink))
        context.stroke(stroke, with: .color(Theme.ink), style: StrokeStyle(lineWidth: JourneyRoad.hair, lineJoin: .round))
    }

    /// The fine drops of ink the nib throws off at a turn (2026-11-11
    /// 08:29: „drobinek nierównego tuszu przy kresce”; 08:55: „za dużo
    /// małych kropeczek… jak przy zbyt szybkim rysowaniu stalówką. Np.
    /// tylko przy zakrętach”).
    func drawPen(in context: inout GraphicsContext) {
        var dust = Path()
        for speck in JourneyRoad.spatter(along: plan.line, turns: plan.turns, until: end, seed: seed, off: stains) {
            let grain = Path(ellipseIn: CGRect(x: -speck.long, y: -speck.short, width: 2 * speck.long, height: 2 * speck.short))
            dust.addPath(grain, transform: CGAffineTransform(translationX: speck.at.x, y: speck.at.y).rotated(by: speck.turn))
        }
        context.fill(dust, with: .color(Theme.ink.opacity(0.9)))
    }
}

/// One of the two drawings of `RoadInk`, as big as the road and `top` more
/// above it. Drawn once: nothing in it changes as the drawing comes.
private struct InkCanvas: View, Equatable {
    enum Part { case body, pen }

    let ink: RoadInk
    let part: Part

    var body: some View {
        Canvas { context, _ in
            context.translateBy(x: 0, y: ink.top)
            switch part {
            case .body: ink.drawBody(in: &context)
            case .pen: ink.drawPen(in: &context)
            }
        }
    }
}

/// The line as far as the pen has come: at its full width down to where
/// it has thickened, and from there to the pen's tip thinner and thinner,
/// to a hairline (2026-11-11: „cieńszą kreską i potem grubnie”).
private struct RoadLine: View {
    let reveal: RoadReveal
    let ink: RoadInk

    var body: some View {
        let plan = ink.plan
        let tip = JourneyRoad.tip(of: plan.line, flow: ink.flow, until: plan.dots[plan.dots.count - 1],
                                  pen: reveal.pen, thick: reveal.thick)
        let end = JourneyRoad.closed(tip.outline)
        ZStack(alignment: .topLeading) {
            InkCanvas(ink: ink, part: .body)
                .equatable()
                // Masked before it is moved up: the mask is as big as what it masks.
                .mask { Edge(edge: tip.full + ink.top, soft: 2) }
                .padding(.top, -ink.top)
            end.fill(Theme.ink)
            end.stroke(Theme.ink, style: StrokeStyle(lineWidth: JourneyRoad.hair, lineJoin: .round))
        }
    }
}

/// A stop's text coming up on its stain (22:18: „podpisy płynnie się
/// pojawiać”; 2026-11-11: „na plamach pojawiają się teksty koloru
/// białego”): blurred and pale at first, line after line.
private struct Emerging<Content: View>: View {
    let reveal: RoadReveal
    let index: Int
    let height: CGFloat
    let content: Content

    init(reveal: RoadReveal, index: Int, height: CGFloat, @ViewBuilder content: () -> Content) {
        self.reveal = reveal
        self.index = index
        self.height = height
        self.content = content()
    }

    /// The mask reaches this far past the text all round, for the hand's
    /// tall strokes and the blur; a line comes up over this many points.
    private static var room: CGFloat { 8 }
    private static var line: CGFloat { 56 }

    var body: some View {
        let shown = JourneyRoad.ease((reveal.age(index) - RoadMarks.clock.text) / RoadMarks.clock.emerge)
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
            .offset(y: -3 * (1 - shown))
    }
}

/// A side trip the work came back from (18:16: „jako odnogę… rysowaną
/// przerywaną linią”; 18:40: „jak rozdroże… ramka może jako zakreślenie”;
/// 2026-11-11 09:44: „okrąg musi się rysować po plamie, nie od góry, tylko
/// jako zakreślenie od początku do końca. Kreskowana linia do niego
/// prowadząca musi wyglądać realistyczniej i powstawać (rysować) się
/// kreseczkami”): the branch is drawn first, when the stop begins, with
/// the pen lifted between strokes, one stroke after another by hand; then
/// the stop's dot, its stain and its text; and last the loop round the
/// text, the way one circles a word, from its start round to its end.
private struct RoadBranch: View {
    let reveal: RoadReveal
    let index: Int
    let dashes: [JourneyRoad.Dash]
    let ring: Path?

    var body: some View {
        let inked = strokes(reveal.drawing(index))
        let circled = JourneyRoad.ease((reveal.age(index) - RoadMarks.loop.at) / RoadMarks.loop.takes)
        ZStack(alignment: .topLeading) {
            if let ring, circled > 0 {
                ring.trimmedPath(from: 0, to: circled)
                    .stroke(Theme.ink.opacity(0.82), style: StrokeStyle(lineWidth: 1.3, lineCap: .round, lineJoin: .round))
            }
            inked.fill(Theme.ink)
            inked.stroke(Theme.ink, style: StrokeStyle(lineWidth: 0.7, lineJoin: .round))
        }
    }

    /// The branch as far as it is drawn `age` seconds after its first stroke began.
    private func strokes(_ age: CGFloat) -> Path {
        var path = Path()
        for (k, dash) in dashes.enumerated() {
            let part = min(1, (age - CGFloat(k) * RoadMarks.dash.apart) / RoadMarks.dash.takes)
            guard part > 0 else { break }
            path.addLines(dash.outline(part))
            path.closeSubpath()
        }
        return path
    }
}

/// The line going on into "Dalsze losy" (`JourneyRoad.Onward`), as far as
/// it is drawn: the ring round the blot in its own time, a moment after
/// the blot; from there down to the heading as the pen goes; the loop
/// round the heading in its own time; and down the left side as the pen
/// goes, thin at its tip. `last`: the road's last stop; the clock after
/// it is the loop's.
private struct OnwardLine: View {
    let reveal: RoadReveal
    let onward: JourneyRoad.Onward
    let last: Int

    var body: some View {
        let ringed = JourneyRoad.ease((reveal.age(last) - RoadMarks.ring.at) / RoadMarks.ring.takes)
        let circled = JourneyRoad.ease(reveal.age(last + 1) / RoadMarks.lasso)
        let tip = onward.tip(pen: reveal.pen, ringed: ringed, circled: circled)
        let inked = JourneyRoad.closed(onward.outline(tip: tip, thick: reveal.thick))
        ZStack(alignment: .topLeading) {
            inked.fill(Theme.ink)
            inked.stroke(Theme.ink, style: StrokeStyle(lineWidth: 1.1, lineJoin: .round))
        }
    }
}

/// What is told of a later work comes up on the paper a moment after its
/// name has come up on its stain.
private struct Told<Content: View>: View {
    let reveal: RoadReveal
    let index: Int
    let content: Content

    init(reveal: RoadReveal, index: Int, @ViewBuilder content: () -> Content) {
        self.reveal = reveal
        self.index = index
        self.content = content()
    }

    var body: some View {
        let shown = JourneyRoad.ease((reveal.age(index) - RoadMarks.told.at) / RoadMarks.told.takes)
        content
            .opacity(shown)
            .offset(y: 4 * (1 - shown))
    }
}

/// The dots, each coming up on the line when its stop begins. The last
/// stop has none: it has a blot (`RoadBlot`).
private struct RoadDots: View {
    let reveal: RoadReveal
    let plan: RoadPlan
    let seed: String

    var body: some View {
        ZStack(alignment: .topLeading) {
            ForEach(0..<max(0, plan.dots.count - 1), id: \.self) { i in
                DotMark(reveal: reveal, index: i, at: plan.dots[i], hollow: plan.branches[i] != nil,
                        edge: JourneyRoad.blotEdge(seed: seed + "dot\(i)"))
            }
        }
    }
}

/// A sea the work crossed, as a wash of watercolour (Mateusz 2026-11-11
/// 10:20: „Zlewanie czerwonej kropki wygląda tak dobrze, że aż kusi dodać
/// podobne mieszanie tego lub innych kolorów gdzieś jeszcze”; 11:09, of
/// sketch 26: „Morze - super - wdrażamy”): pale blue, laid just before
/// the pen gets there. It floods out from where the line comes into it,
/// with a wet front, and dries with its pigment gathered along its edge.
/// The line is drawn into it while it is wet, so its ink runs: behind the
/// pen the black feathers out into the blue, in places further
/// (`Watercolour.metal`, `sea`). All of it follows the pen, so it goes
/// back as the page does.
private struct SeaWash: View {
    let reveal: RoadReveal
    let wash: JourneyRoad.Wash
    let dark: Bool
    /// Tells one sea's paint from another's.
    let seed: Float

    var body: some View {
        let came = wash.came(pen: reveal.pen), frame = wash.frame, box = wash.box
        let paint = dark ? JourneyRoad.Wash.onDark : JourneyRoad.Wash.onLight
        Color.white
            .frame(width: frame.width, height: frame.height)
            .colorEffect(
                ShaderLibrary.sea(
                    .float4(Float(box.minX - frame.minX), Float(box.minY - frame.minY),
                            Float(box.maxX - frame.minX), Float(box.maxY - frame.minY)),
                    .float2(Float(wash.entry.x - frame.minX), Float(wash.entry.y - frame.minY)), .float(Float(wash.reach)),
                    .float4(Float(came.spread), Float(came.dry), Float(came.soak), Float(came.tip)),
                    .floatArray(wash.points), .float(Float(JourneyRoad.washEach)), .float(seed),
                    .color(paint.blue), .color(paint.deep), .color(paint.ink)
                )
            )
            .opacity(came.spread > 0 ? 1 : 0)
            .offset(x: frame.minX, y: frame.minY)
    }
}

/// One dot, a blot off the nib (16:39: „Kropki bardziej dynamicznie.
/// Bardziej jak „kleksy” przy rysowaniu linii”): it bursts out to well
/// over its size, ragged, and settles, not quite round (`JourneyRoad.pop`,
/// `ragged`, `blotEdge`). A hollow one where a side trip's branch ends.
private struct DotMark: View {
    let reveal: RoadReveal
    let index: Int
    let at: CGPoint
    let hollow: Bool
    /// How far out its edge is all round, at rest.
    let edge: [CGFloat]

    var body: some View {
        let age = reveal.age(index)
        let radius = (hollow ? JourneyRoad.dot.hollow : JourneyRoad.dot.full) * JourneyRoad.pop(age)
        let blot = JourneyRoad.closed(JourneyRoad.blotOutline(at: at, radius: radius, edge: edge, ragged: JourneyRoad.ragged(age)))
        ZStack(alignment: .topLeading) {
            if hollow {
                blot.fill(Theme.paper)
                blot.stroke(Theme.ink, style: StrokeStyle(lineWidth: 1.6, lineJoin: .round))
            } else {
                blot.fill(Theme.ink)
                blot.stroke(Theme.ink, style: StrokeStyle(lineWidth: 0.6, lineJoin: .round))
            }
        }
    }
}

/// Where the work is now (18:16: „czerwona, ale większa”; 2026-11-11
/// 09:44: „czerwona kropka na końcu także jako plama akwareli, bez białego
/// otoku. Na styku z czernią miesza się jak prawdziwa akwarela”): a blot
/// of red watercolour at the end of the line. It spreads from its middle
/// with a wet edge and dries with the pigment pooled along its rim; the
/// paper round it soaks some of it up; and where it meets the black (the
/// end of the line, and the last stop's ink, which comes out of it) the
/// two run into each other (`Watercolour.metal`, `blot`). `small`: a later
/// work's, on the line going on, which runs through it; out of it pours a
/// stain of another `paint`, and the red runs into that and into the line.
private struct RoadBlot: View {
    let reveal: RoadReveal
    let index: Int
    let blot: JourneyRoad.Blot
    let dark: Bool
    /// Tells this paint from the stains'.
    let seed: Float
    var small = false
    /// The paint that pours out of it, when it is not the line's ink.
    var paint: Color?

    var body: some View {
        let age = reveal.age(index), room = small ? JourneyRoad.smallBlot.room : JourneyRoad.blotRoom
        let corner = CGPoint(x: (blot.at.x - room).rounded(.down), y: (blot.at.y - room).rounded(.down))
        let ink = dark ? JourneyRoad.Ink.onDark : JourneyRoad.Ink.onLight
        // How big it is, how much of its middle stays red, and how wide
        // the line is that runs into it and, where it does, on out of it.
        let wide = JourneyRoad.onwardNib / 2
        let size: [CGFloat] = small
            ? [JourneyRoad.smallBlot.radius, JourneyRoad.smallBlot.core, wide, blot.on == nil ? 0 : wide]
            : [JourneyRoad.blotRadius, 2.5, 2.9, 0]
        let on = blot.on ?? blot.at
        Color.white
            .frame(width: 2 * room, height: 2 * room)
            .colorEffect(
                ShaderLibrary.blot(
                    .float2(Float(blot.at.x - corner.x), Float(blot.at.y - corner.y)),
                    .float2(Float(blot.back.x - corner.x), Float(blot.back.y - corner.y)),
                    .float2(Float(on.x - corner.x), Float(on.y - corner.y)),
                    .float2(Float(blot.to.x - corner.x), Float(blot.to.y - corner.y)),
                    .float4(Float(blot.into.minX - corner.x), Float(blot.into.minY - corner.y),
                            Float(blot.into.maxX - corner.x), Float(blot.into.maxY - corner.y)),
                    .float4(Float(size[0]), Float(size[1]), Float(size[2]), Float(size[3])), .float(Float(age)),
                    .float(Float(age - RoadMarks.clock.spill)), .float(seed),
                    .float3(Float(blot.lobes[0]), Float(blot.lobes[1]), Float(blot.lobes[2])),
                    .color(ink.red), .color(ink.dense), .color(paint ?? ink.dense)
                )
            )
            .opacity(age > 0 ? 1 : 0)
            .offset(x: corner.x, y: corner.y)
    }
}

/// A stop's stain (2026-11-11 08:29: „z nich rozlewają się plamy pod tekst
/// (czyli plamy ciemnej farby (zanikające do ciemnoszarej akwareli)…”;
/// 08:55: „powinny powstawać jak akwarela (zaczynając się od kropki) i nie
/// spływać tak bardzo w dół… Plama może rozwiązać się czasami przy
/// krawędzi. W motywie ciemnym tekst czarny, a plamy pod nim białe”; 09:11:
/// „Plamy mają powstawać z kropek. Teraz są nanoszone na nich. Rozlewanie
/// tuszu a nie jego rozmywanie… jakby papier na krawędzi plam nasiąkał
/// tuszem i już mniej mocnym odcieniem powstaje fragmentami drugie halo
/// plamy. Jakby akwarela wsiąkała w papier”): ink that pours out of the
/// stop's dot and spreads under its text with a sharp wet edge, dries, and
/// in places soaks on into the paper as a second, paler halo; dark on the
/// light page and white on the dark one (`Watercolour.metal`, `spill`).
private struct RoadStain: View {
    let reveal: RoadReveal
    let index: Int
    let spill: JourneyRoad.Spill
    let dark: Bool
    /// Tells one stain's paint from another's.
    let seed: Float
    /// Another paint than the road's ink: a later work's.
    var ink: JourneyRoad.Ink?

    var body: some View {
        let age = Float(reveal.age(index) - RoadMarks.clock.spill), box = spill.frame
        let ink = self.ink ?? (dark ? JourneyRoad.Ink.onDark : JourneyRoad.Ink.onLight)
        StainField(spill: spill)
            .equatable()
            .frame(width: box.width, height: box.height)
            .layerEffect(
                ShaderLibrary.spill(
                    .float2(Float(spill.dot.x - box.minX), Float(spill.dot.y - box.minY)),
                    .float(Float(spill.bottom - box.minY)), .float(Float(spill.reach)), .float(age), .float(seed),
                    .color(ink.wet), .color(ink.dense), .color(ink.wash), .color(ink.halo),
                    .float2(ink.cover.wet, ink.cover.dry), .float2(ink.soak.pale, ink.soak.lip),
                    .float2(ink.grain, ink.bloom)
                ),
                maxSampleOffset: .zero
            )
            .opacity(age > 0 ? 1 : 0)
            .offset(x: box.minX, y: box.minY)
    }
}

/// Where a stain can be and how near its edge each place is: its shape,
/// white and blurred. The shader makes the paint of it; nobody sees this
/// as it is. Drawn once: nothing in it changes as the paint comes.
private struct StainField: View, Equatable {
    let spill: JourneyRoad.Spill

    var body: some View {
        Canvas { context, _ in
            context.translateBy(x: -spill.frame.minX, y: -spill.frame.minY)
            func disc(_ drop: JourneyRoad.Drop) -> Path {
                Path(ellipseIn: CGRect(x: drop.at.x - drop.radius, y: drop.at.y - drop.radius,
                                       width: 2 * drop.radius, height: 2 * drop.radius))
            }
            // Each part in one layer, so the blur is of all of it together:
            // the stain softest, the way out of the dot and the drips finer.
            var wash = context
            wash.addFilter(.blur(radius: JourneyRoad.spillBlur.stain))
            wash.drawLayer { layer in
                for line in spill.lines { layer.fill(Path(roundedRect: line, cornerRadius: 8), with: .color(.white)) }
                for bulge in spill.bulges { layer.fill(disc(bulge), with: .color(.white)) }
            }
            var neck = context
            neck.addFilter(.blur(radius: JourneyRoad.spillBlur.way))
            neck.drawLayer { layer in
                for drop in spill.way { layer.fill(disc(drop), with: .color(.white)) }
            }
            var runs = context
            runs.addFilter(.blur(radius: JourneyRoad.spillBlur.drip))
            runs.drawLayer { layer in
                for drip in spill.drips {
                    var run = Path()
                    run.move(to: drip.from)
                    run.addQuadCurve(to: drip.to, control: drip.bend)
                    layer.stroke(run, with: .color(.white), style: StrokeStyle(lineWidth: 2 * drip.radius, lineCap: .round))
                    layer.fill(disc(JourneyRoad.Drop(at: drip.from, radius: drip.radius + 2.4)), with: .color(.white))
                    layer.fill(disc(JourneyRoad.Drop(at: drip.to, radius: drip.bead)), with: .color(.white))
                }
            }
        }
    }
}

// MARK: Geometry

/// The road worked out: the line, each stop's dot on it, and where each
/// stop's text goes.
struct RoadPlan: Equatable {
    var line: [CGPoint]
    /// Where each turn is on the line: the hook's, then each run's.
    var turns: [Int] = []
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
    /// The last stop's mark, where the work is now: bigger than the others.
    /// The road's height leaves this much for it under its dot.
    static let lastDot: CGFloat = 9
    /// It is a blot of red about this big, in a field that reaches this
    /// far from its middle: room for the red that runs along the black.
    static let blotRadius: CGFloat = 10.4
    static let blotRoom: CGFloat = 34
    /// A stop's dot: how far its edge is from its middle, a full one's and
    /// a hollow one's (a side trip's), and at how many points round it the
    /// edge is drawn.
    static let dot: (full: CGFloat, hollow: CGFloat) = (5.1, 4.6)
    static let blotSides = 40
    /// How a dot lands (16:39: „Kropki bardziej dynamicznie. Bardziej jak
    /// „kleksy” przy rysowaniu linii”): in `burst` seconds it is out at
    /// `over` times its size, its edge `ragged` times as uneven as it will
    /// stay, and by `settle` it has drawn back to its size.
    static let splat: (burst: CGFloat, settle: CGFloat, over: CGFloat, ragged: CGFloat) = (0.11, 0.46, 1.4, 2.6)
    /// How far under the road a side trip's stop hangs, and how far back
    /// along the road its branch forks off.
    static let branch: CGFloat = 46
    static let branchSpan: CGFloat = 140
    /// A line of a text much shorter than the ones over and under it is
    /// not a deep notch in the stain's side: no deeper than this.
    static let notch: CGFloat = 26
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
    /// Mateusz picked the narrowing ones (2026-11-10 23:03, sketch 19: „B”).
    static let arcs = Arcs.narrow
    /// A stain's field reaches this far past the stain all round, and is
    /// blurred this much: its soft edge is what the paint seeps over. The
    /// way out of the dot and the drips are finer.
    static let spillRoom: CGFloat = 20
    static let spillBlur: (stain: CGFloat, way: CGFloat, drip: CGFloat) = (6, 2.3, 1.5)
    /// The line is thin at the pen's tip and has its full width at least
    /// this many samples behind it.
    static let taper = 14
    /// "Dalsze losy": how far from the road's left edge the line going on
    /// runs down, how wide its nib is (a lighter hand than the road's), how
    /// big the ring round the road's blot is, how much room the loop
    /// leaves round the heading, how far under the road the heading is and
    /// how far in the later works are; and a later work's blot: its size,
    /// the room its paint has to run in, how much of its middle stays red.
    static let rail: CGFloat = 9
    static let onwardNib: CGFloat = 3.3
    static let ringRadius: CGFloat = 16.5
    static let lassoPad: (side: CGFloat, over: CGFloat) = (15, 8)
    static let laterGap: CGFloat = 36
    static let laterInset: CGFloat = 36
    static let smallBlot: (radius: CGFloat, room: CGFloat, core: CGFloat) = (6, 24, 1.7)

    /// On a stain: the text white on the dark paint, black on the white
    /// paint of the dark page; the date red on both, lighter on the dark paint.
    static let onStain = Color(light: 0xFBF8F2, dark: 0x1D1B18)
    static let dateOnStain = Color(light: 0xF47C62, dark: 0xB8432F)

    /// 0 up to 1, slow at both ends.
    static func ease(_ x: CGFloat) -> CGFloat {
        let t = min(1, max(0, x))
        return t * t * (3 - 2 * t)
    }

    /// How big a dot is `age` seconds after its stop began: it bursts out
    /// to `splat.over`, fast, and draws back to 1, a little under it on
    /// the way.
    static func pop(_ age: CGFloat) -> CGFloat {
        guard age > 0 else { return 0 }
        if age < splat.burst {
            let left = 1 - age / splat.burst
            return splat.over * (1 - left * left)
        }
        let part = min(1, (age - splat.burst) / (splat.settle - splat.burst))
        return 1 + (splat.over - 1) * (1 - part) * (1 - part) * cos(1.5 * .pi * part)
    }

    /// How uneven a dot's edge is `age` seconds after its stop began, 1
    /// being as it stays: most as it bursts out.
    static func ragged(_ age: CGFloat) -> CGFloat {
        guard age < splat.settle else { return 1 }
        let left = 1 - max(0, age - splat.burst) / (splat.settle - splat.burst)
        return 1 + (splat.ragged - 1) * left * left
    }

    /// A dot is not quite round: how far out its edge is at each of
    /// `blotSides` points round it, as a part of its radius (0: on the
    /// circle). A few slow waves, its own for each dot.
    static func blotEdge(seed: String) -> [CGFloat] {
        var random = SeededRandom(seed)
        var edge = [CGFloat](repeating: 0, count: blotSides)
        let waves: [(turns: CGFloat, least: CGFloat, most: CGFloat)] = [(2, 0.025, 0.045), (3, 0.02, 0.035), (5, 0.008, 0.018)]
        for wave in waves {
            let size = wave.least + (wave.most - wave.least) * random.unit()
            let shift = 2 * CGFloat.pi * random.unit()
            for k in 0..<blotSides {
                edge[k] += size * cos(wave.turns * 2 * CGFloat.pi * CGFloat(k) / CGFloat(blotSides) + shift)
            }
        }
        return edge
    }

    /// The outline of a dot round `at`: `edge` as in `blotEdge`, `ragged`
    /// times as uneven.
    static func blotOutline(at: CGPoint, radius: CGFloat, edge: [CGFloat], ragged: CGFloat) -> [CGPoint] {
        guard radius > 0, !edge.isEmpty else { return [] }
        var outline: [CGPoint] = []
        for k in edge.indices {
            let angle = 2 * CGFloat.pi * CGFloat(k) / CGFloat(edge.count)
            let out = radius * max(0.5, 1 + ragged * edge[k])
            outline.append(CGPoint(x: at.x + out * cos(angle), y: at.y + out * sin(angle)))
        }
        return outline
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
            result = RoadPlan(line: line, turns: turns, dots: dots, texts: texts, leading: leading, branches: branches, loops: loops,
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
    /// it is all there is. It stops `clear` short of `until`. `flow`: how
    /// full the nib runs at each sample (`inkFlow`); without it, evenly.
    static func nibStroke(_ line: [CGPoint], until end: CGPoint, clear: CGFloat, nib: CGFloat = JourneyRoad.nib,
                          flow: [CGFloat] = []) -> [CGPoint] {
        var cut = line.count
        while cut > 0, hypot(line[cut - 1].x - end.x, line[cut - 1].y - end.y) < clear { cut -= 1 }
        let dx = cos(nibTilt) * nib / 2, dy = sin(nibTilt) * nib / 2
        var one: [CGPoint] = [], other: [CGPoint] = []
        for q in 0..<cut {
            let full = q < flow.count ? flow[q] : 1
            one.append(CGPoint(x: line[q].x + dx * full, y: line[q].y + dy * full))
            other.append(CGPoint(x: line[q].x - dx * full, y: line[q].y - dy * full))
        }
        return one + other.reversed()
    }

    /// One stroke of a side trip's branch: its middle line, a point every
    /// point of length; how wide it is where the pen pressed hardest; how
    /// far off the branch it lies and how much it is turned from it.
    struct Dash: Equatable {
        var way: [CGPoint]
        var wide: CGFloat
        var off: CGFloat
        var skew: CGFloat

        /// Its outline, drawn as far as `part` of its length: thin where
        /// the pen came down and where it was lifted, pressed in between.
        func outline(_ part: CGFloat) -> [CGPoint] {
            let end = way.count - 1
            guard end >= 1 else { return [] }
            let upto = min(end, max(1, Int((CGFloat(end) * part).rounded())))
            var one: [CGPoint] = [], other: [CGPoint] = []
            for j in 0...upto {
                let before = way[max(0, j - 1)], after = way[min(end, j + 1)]
                let step = max(1e-3, hypot(after.x - before.x, after.y - before.y))
                let across = CGPoint(x: -(after.y - before.y) / step, y: (after.x - before.x) / step)
                let along = CGFloat(j) / CGFloat(end)
                let press = sin(CGFloat.pi * (0.05 + 0.9 * along))
                let half = wide / 2 * pow(press, 0.55)
                let side = off + skew * (CGFloat(j) - CGFloat(end) / 2)
                one.append(CGPoint(x: way[j].x + across.x * (side + half), y: way[j].y + across.y * (side + half)))
                other.append(CGPoint(x: way[j].x + across.x * (side - half), y: way[j].y + across.y * (side - half)))
            }
            return one + other.reversed()
        }
    }

    /// A side trip's branch drawn by hand with the pen lifted between
    /// strokes (09:44: „Kreskowana linia… musi wyglądać realistyczniej”):
    /// short strokes along it, no two alike (longer and shorter, wider and
    /// finer, a little off the branch and a little turned), the last one
    /// short of its dot.
    static func hand(_ way: [CGPoint], until end: CGPoint, seed: String) -> [Dash] {
        let fine = even(way, step: 1).filter { hypot($0.x - end.x, $0.y - end.y) > 7 }
        var random = SeededRandom(seed)
        var out: [Dash] = []
        var start = 0
        while start < fine.count - 4 {
            let long = Int((7 + 4.5 * random.unit()).rounded())
            let stroke = Array(fine[start..<min(fine.count, start + long + 1)])
            guard stroke.count >= 5 else { break }
            let wide = 2.5 + 1.1 * random.unit(), off = (random.unit() - 0.5) * 1.2, skew = (random.unit() - 0.5) * 0.16
            out.append(Dash(way: stroke, wide: wide, off: off, skew: skew))
            start += long + Int((4 + 2.6 * random.unit()).rounded())
        }
        return out
    }

    /// Every side trip's branch on the road, by its stop.
    static func hands(of plan: RoadPlan, seed: String) -> [Int: [Dash]] {
        var out: [Int: [Dash]] = [:]
        for (index, way) in plan.branches where index < plan.dots.count {
            out[index] = hand(way, until: plan.dots[index], seed: seed + "hand\(index)")
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

    /// A round bit of a stain: where it sags, where it bulges, the way out of its dot.
    struct Drop: Equatable {
        var at: CGPoint
        var radius: CGFloat
    }

    /// A drip under a stain: a thin run of paint with a bead at its end.
    struct Drip: Equatable {
        var from: CGPoint
        var bend: CGPoint
        var to: CGPoint
        var radius: CGFloat
        var bead: CGFloat
    }

    /// A stop's stain as it is drawn into its field (`StainField`).
    struct Spill: Equatable {
        /// Each line of the text with room round it.
        var lines: [CGRect] = []
        var bulges: [Drop] = []
        /// From the dot into the stain, and the line of the text it gets to.
        var way: [Drop] = []
        var into = CGRect.zero
        var drips: [Drip] = []
        var dot = CGPoint.zero
        /// The stain's foot: under it there are only sags and drips.
        var bottom: CGFloat = 0
        /// How far the paint has to go from the dot to the stain's far corner.
        var reach: CGFloat = 1
        /// About the text: no drops of ink go there.
        var box = CGRect.zero
        /// All of it, with room for its soft edge.
        var frame = CGRect.zero
    }

    /// The ink of the stains: as it comes (`wet`), dried where it lay
    /// thick, by the dot (`dense`), dried where it ran thin (`wash`), and
    /// soaked into the paper past the stain's edge (`halo`); how much of
    /// the page it covers wet and dry, how much the halo covers and how
    /// much more at its own edge, how much of the paper's grain shows in
    /// it and how uneven it dries. `red`: the blot at the road's end.
    struct Ink {
        var red: Color
        var wet: Color
        var dense: Color
        var wash: Color
        var halo: Color
        var cover: (wet: CGFloat, dry: CGFloat)
        var soak: (pale: CGFloat, lip: CGFloat)
        var grain: CGFloat
        var bloom: CGFloat

        /// Dark ink that dries to a dark-grey wash (08:29).
        static let onLight = Ink(red: Color(hex: 0xB8432F), wet: Color(hex: 0x1B1916), dense: Color(hex: 0x1F1D1A), wash: Color(hex: 0x4A4641),
                                 halo: Color(hex: 0x46423D), cover: (0.97, 0.85), soak: (0.34, 0.2), grain: 0.2,
                                 bloom: 22.0 / 255)
        /// On the dark page the stains are white (08:55).
        static let onDark = Ink(red: Color(hex: 0xE58A6F), wet: Color(hex: 0xFFFDF9), dense: Color(hex: 0xFFFEFA), wash: Color(hex: 0xECE7DE),
                                halo: Color(hex: 0xF6F2EA), cover: (0.97, 0.9), soak: (0.3, 0.16), grain: 0.09,
                                bloom: 10.0 / 255)

        /// The paint of "Dalsze losy" (Mateusz 10:20: „innym kolorem plam”;
        /// 10:37, of one paint for all or each in its work's colour: one).
        static let indigo = (red: 50.0 / 255, green: 70.0 / 255, blue: 138.0 / 255)

        /// A paint of this colour for a stain: deep on the light page, so
        /// white reads on it; pale on the dark page, where the text on a
        /// stain is black.
        static func paint(_ hue: (red: Double, green: Double, blue: Double), dark: Bool) -> Ink {
            /// The colour times `deep`, then `by` of the way to `grey`.
            func tone(_ deep: Double, _ grey: Double, _ by: Double) -> Color {
                func part(_ value: Double) -> Double { value * deep + (grey - value * deep) * by }
                return Color(red: part(hue.red), green: part(hue.green), blue: part(hue.blue))
            }
            if dark {
                return Ink(red: onDark.red, wet: tone(1, 1, 0.84), dense: tone(1, 1, 0.8), wash: tone(1, 1, 0.66),
                           halo: tone(1, 1, 0.74), cover: (0.97, 0.9), soak: (0.3, 0.16), grain: 0.09, bloom: 10.0 / 255)
            }
            return Ink(red: onLight.red, wet: tone(0.56, 0, 0), dense: tone(0.62, 0, 0), wash: tone(0.92, 0.5, 0.22),
                       halo: tone(1, 0.5, 0.28), cover: (0.97, 0.86), soak: (0.34, 0.2), grain: 0.2, bloom: 20.0 / 255)
        }
    }

    /// Where the lines of a stop's text are on the road. `hug` is the text
    /// as it stands, `head` its first line (the date and the place) when
    /// it has one, `widths` how wide each line of the sentence is. The
    /// lines start at the text's left edge or end at its right one.
    static func lines(of hug: CGRect, head: CGSize?, widths: [CGFloat], leading: Bool) -> [CGRect] {
        func span(_ wide: CGFloat) -> (x: CGFloat, width: CGFloat) {
            let width = max(1, min(hug.width, wide))
            return (leading ? hug.minX : hug.maxX - width, width)
        }
        var out: [CGRect] = []
        var y = hug.minY
        if let head {
            let across = span(head.width)
            out.append(CGRect(x: across.x, y: y + 3, width: across.width, height: max(4, head.height - 4)))
            y += head.height
        }
        let tall = max(0, hug.maxY - y) / CGFloat(max(1, widths.count))
        for (k, wide) in widths.enumerated() where tall > 4 {
            let across = span(wide + 1)
            out.append(CGRect(x: across.x, y: y + CGFloat(k) * tall + 1, width: across.width, height: tall - 2))
        }
        return out.isEmpty ? [hug] : out
    }

    /// A stop's stain: every line of its text with room round it, so the
    /// stain keeps the text's own ragged side (but a short line between
    /// two long ones is no deep notch in it); it sags along its foot,
    /// where the ink gathers, and bulges at a side or two; the ink comes
    /// out of the dot and goes from there into the stain; under
    /// some stains a short drip, where there is room for one (08:55: „nie
    /// spływać tak bardzo w dół”).
    static func spill(under lines: [CGRect], from dot: CGPoint, line: [CGPoint], width: CGFloat, height: CGFloat,
                      seed: String) -> Spill {
        var random = SeededRandom(seed)
        var rects: [CGRect] = []
        for (k, text) in lines.enumerated() {
            let left = max(-13, text.minX - 12 - 5 * random.unit()), right = min(width + 13, text.maxX + 12 + 5 * random.unit())
            let top = text.minY - (k == 0 ? 6 : 4), foot = text.maxY + (k == lines.count - 1 ? 7 : 5)
            rects.append(CGRect(x: left, y: top, width: max(1, right - left), height: max(1, foot - top)))
        }
        if rects.count > 2 {
            for k in 1..<(rects.count - 1) {
                let left = min(rects[k].minX, max(rects[k - 1].minX, rects[k + 1].minX) + notch)
                let right = max(rects[k].maxX, min(rects[k - 1].maxX, rects[k + 1].maxX) - notch)
                rects[k] = CGRect(x: left, y: rects[k].minY, width: right - left, height: rects[k].height)
            }
        }
        guard let first = rects.first, let last = rects.last else { return Spill() }
        let box = rects.dropFirst().reduce(first) { $0.union($1) }
        let bottom = last.maxY
        var bulges: [Drop] = []
        let sags = 2 + (random.unit() < 0.5 ? 1 : 0)
        for j in 0..<sags {
            let part = 0.12 + 0.76 * (CGFloat(j) + random.unit()) / CGFloat(sags)
            let low = bottom - 5 + 3 * random.unit()
            bulges.append(Drop(at: CGPoint(x: last.minX + last.width * part, y: low), radius: 7 + 5 * random.unit()))
        }
        for _ in 0..<2 {
            let rect = rects[min(rects.count - 1, Int(random.unit() * CGFloat(rects.count)))]
            let left = random.unit() < 0.5
            let level = rect.midY + (random.unit() - 0.5) * 6
            bulges.append(Drop(at: CGPoint(x: left ? rect.minX + 4 : rect.maxX - 4, y: level), radius: 8 + 3 * random.unit()))
        }
        // The way out of the dot: to the nearest place inside the stain, no
        // wider than the dot where it starts, so the dot is the stain's tip
        // and not under it (09:11: „Plamy mają powstawać z kropek. Teraz są
        // nanoszone na nich”).
        var near = dot, away = CGFloat.infinity, into = first
        for rect in rects {
            let spot = CGPoint(x: min(max(rect.minX + 9, dot.x), max(rect.minX + 9, rect.maxX - 9)),
                               y: min(max(rect.minY + 6, dot.y), max(rect.minY + 6, rect.maxY - 6)))
            let far = hypot(spot.x - dot.x, spot.y - dot.y)
            if far < away { (near, away, into) = (spot, far, rect) }
        }
        let steps = max(2, Int((away / 4).rounded(.up)))
        let way = (0...steps).map { q -> Drop in
            let part = CGFloat(q) / CGFloat(steps)
            return Drop(at: CGPoint(x: dot.x + (near.x - dot.x) * part, y: dot.y + (near.y - dot.y) * part), radius: 4.6 + 5.4 * part)
        }
        // A drip, rather on the stain's outer side, and only where the road is not right under it.
        var drips: [Drip] = []
        let outerLeft = box.midX < width / 2, want = random.unit() < 0.45 ? 1 : 0
        for _ in 0..<6 where drips.count < want {
            let part = random.unit() * random.unit(), span = max(0, last.width - 14)
            let x = outerLeft ? last.minX + 7 + span * part : last.maxX - 7 - span * part
            let from = bottom - 4
            let room = line.filter { abs($0.x - x) < 9 && $0.y > from - 4 }.map(\.y).min() ?? .infinity
            let long = min(7 + 10 * random.unit(), room - from - 8, height + 14 - from)
            let radius = 1.5 + 1.1 * random.unit(), lean = (random.unit() - 0.5) * 4
            let bead = radius + 0.7 + 0.9 * random.unit()
            guard long >= 6 else { continue }
            drips.append(Drip(from: CGPoint(x: x, y: from), bend: CGPoint(x: x + lean, y: from + long / 2),
                              to: CGPoint(x: x + lean * 0.6, y: from + long), radius: radius, bead: bead))
        }
        let corners = [CGPoint(x: box.minX, y: box.minY), CGPoint(x: box.maxX, y: box.minY),
                       CGPoint(x: box.minX, y: box.maxY), CGPoint(x: box.maxX, y: box.maxY)]
        let reach = max(1, corners.map { hypot($0.x - dot.x, $0.y - dot.y) }.max() ?? 1)
        var frame = box
        for drop in bulges + way {
            frame = frame.union(CGRect(x: drop.at.x - drop.radius, y: drop.at.y - drop.radius,
                                       width: 2 * drop.radius, height: 2 * drop.radius))
        }
        for drip in drips {
            frame = frame.union(CGRect(x: drip.to.x - drip.bead, y: drip.from.y, width: 2 * drip.bead,
                                       height: drip.to.y + drip.bead - drip.from.y))
        }
        return Spill(lines: rects, bulges: bulges, way: way, into: into, drips: drips, dot: dot, bottom: bottom, reach: reach,
                     box: box, frame: frame.insetBy(dx: -spillRoom, dy: -spillRoom))
    }

    /// The blot at the road's end: its middle, the last stop's dot; a
    /// place on the line a little before its end, where the line runs into
    /// it from; where the last stop's ink goes from it and the line of the
    /// text that gets to; and how its outline wanders (three turns).
    struct Blot: Equatable {
        var at: CGPoint
        var back: CGPoint
        var to: CGPoint
        var into: CGRect
        var lobes: [CGFloat]
        /// Where the line goes on to out of it: a later work's blot, on
        /// the line that runs through it.
        var on: CGPoint?
    }

    /// The blot at the end of `line`, with the last stop's stain `spill` coming out of it.
    static func blot(for spill: Spill, line: [CGPoint], seed: String) -> Blot {
        let end = spill.dot
        var cut = line.count
        while cut > 0, hypot(line[cut - 1].x - end.x, line[cut - 1].y - end.y) < lastClear { cut -= 1 }
        let back = line.isEmpty ? end : line[max(0, cut - 10)]
        var random = SeededRandom(seed + "blot")
        let lobes = (0..<3).map { _ in random.unit() * 2 * CGFloat.pi }
        return Blot(at: end, back: back, to: spill.way.last?.at ?? end, into: spill.into, lobes: lobes)
    }

    /// The line going on from the road's end into "Dalsze losy" (Mateusz
    /// 2026-11-11 10:20: „kontynuację linii Drogi dzieła… kreska mogłaby
    /// go [nagłówek] np „opisywać” i lecieć dalej”; 10:39: „na czerwonym
    /// kółku robi się okrągłe zakreślenie i to z niego wychodzi dalsza
    /// kreska… nie aż tak prosta, z odrobiną lekkości”). One line, a point
    /// every two points of length: once round the road's blot (to `ring`),
    /// from under the blot down to the heading, round the heading (`entry`
    /// to `exit`), and down the left side through each later work's blot
    /// (`marks`). `gate`: how far down the road the pen must be for each
    /// point to be drawn; the ring and the loop are drawn in their own
    /// time. `flow`: how full the nib runs. `foot`: the loop's lowest.
    struct Onward: Equatable {
        var line: [CGPoint] = []
        var ring = 0
        var entry = 0
        var exit = 0
        var gate: [CGFloat] = []
        var flow: [CGFloat] = []
        var marks: [Int] = []
        var foot: CGFloat = 0

        /// Each later work's place on the line.
        var dots: [CGPoint] { marks.map { line[$0] } }
        /// Where the loop round the heading begins, down the road.
        var loopY: CGFloat { entry < gate.count ? gate[entry] : 0 }

        /// How many points of the line are drawn with the pen at `pen`,
        /// `ringed` of the ring round the blot drawn and `circled` of the
        /// loop round the heading.
        func tip(pen: CGFloat, ringed: CGFloat, circled: CGFloat) -> Int {
            var tip = gate.firstIndex { $0 > pen } ?? line.count
            if circled < 1, tip > entry { tip = min(tip, entry + Int((CGFloat(exit - entry) * circled).rounded())) }
            if ringed < 1 { tip = min(tip, Int((CGFloat(ring) * ringed).rounded())) }
            return tip
        }

        /// The first `tip` points inked with the nib: at its full width
        /// down to `thick` (a height on the road) and thinner from there
        /// to the tip, to nothing.
        func outline(tip: Int, thick: CGFloat) -> [CGPoint] {
            guard tip > 1, tip <= line.count else { return [] }
            let full = gate[..<tip].firstIndex { $0 > thick } ?? tip
            let thin = CGFloat(max(JourneyRoad.taper, tip - full))
            let dx = cos(JourneyRoad.nibTilt) * JourneyRoad.onwardNib / 2
            let dy = sin(JourneyRoad.nibTilt) * JourneyRoad.onwardNib / 2
            var one: [CGPoint] = [], other: [CGPoint] = []
            for q in 0..<tip {
                let k = JourneyRoad.ease(CGFloat(tip - 1 - q) / thin) * (q < flow.count ? flow[q] : 1)
                one.append(CGPoint(x: line[q].x + dx * k, y: line[q].y + dy * k))
                other.append(CGPoint(x: line[q].x - dx * k, y: line[q].y - dy * k))
            }
            return one + other.reversed()
        }
    }

    /// The line going on from the road's blot at `at`. `box`: the last
    /// stop's stain, which the line goes down beside, on the side away
    /// from it (`leading`: the stain is to the right of the blot);
    /// `heading`: "Dalsze losy" as it stands under the road; `years`: how
    /// far down each later work's blot is to be. Nothing when the heading
    /// is not under the road yet.
    static func onward(from at: CGPoint, past box: CGRect, leading: Bool, heading: CGRect, years: [CGFloat], width: CGFloat,
                       seed: String) -> Onward? {
        guard let end = years.last, !heading.isNull, heading.minY > at.y + 60, end > heading.maxY + 20 else { return nil }
        var random = SeededRandom(seed + "onward")
        let turns = (0..<4).map { _ in random.unit() * 2 * CGFloat.pi }
        let side: CGFloat = leading ? 1 : -1
        var route: [CGPoint] = []
        // Once round the blot and a little more, from under it and back
        // to under it, wider at its end than at its start: drawn by hand.
        for step in 0...32 {
            let part = CGFloat(step) / 32
            let turn = (62 + 384 * part) * CGFloat.pi / 180
            let wander = 0.05 * sin(2 * turn + turns[2]) + 0.03 * sin(3 * turn + turns[3])
            let far = ringRadius * (1 + wander) - 1.3 + 2.6 * part
            route.append(CGPoint(x: at.x + side * far * cos(turn), y: at.y + far * sin(turn)))
        }
        let out = route[route.count - 1]
        // The loop round the heading: its middle, and half its width and height.
        let middle = CGPoint(x: heading.midX, y: heading.midY)
        let wide = heading.width / 2 + lassoPad.side, tall = heading.height / 2 + lassoPad.over
        let left = middle.x - wide
        // Down beside the last stop's stain and over to the left side, above the heading.
        let shelf = middle.y - tall - 14
        let down = at.y + min(52, max(24, (shelf - at.y) * 0.55))
        if leading {
            route.append(CGPoint(x: max(3, out.x - 15), y: out.y + 5))
            route.append(CGPoint(x: max(left - 6, min(at.x - 34, box.minX - 12)), y: down))
        } else {
            let beside = min(width - 3, max(at.x + 34, box.maxX + 12))
            route.append(CGPoint(x: min(width - 3, out.x + 15), y: out.y + 5))
            route.append(CGPoint(x: beside, y: down))
            if box.maxY + 4 > down + 12, box.maxY + 4 < shelf - 8 { route.append(CGPoint(x: beside - 2, y: box.maxY + 4)) }
        }
        route.append(CGPoint(x: left - 4.5, y: shelf))
        route.append(CGPoint(x: left - 5, y: middle.y - 2))
        // Round the heading the way one circles a word: from its lower
        // left along under it, up its right side, back over it, and down
        // to its left end, where the line goes on.
        let first = route.count
        let power: CGFloat = 2 / 3.2
        for step in 0...33 {
            let part = CGFloat(step) / 33
            let turn = (150 - 330 * part) * CGFloat.pi / 180
            let swell = 1 + 0.03 * sin(2 * turn + turns[0]) * sin(CGFloat.pi * part)
            let across = cos(turn), along = sin(turn)
            let right: CGFloat = across < 0 ? -1 : 1, under: CGFloat = along < 0 ? -1 : 1
            let x = middle.x + wide * swell * right * pow(abs(across), power)
            let y = middle.y + tall * swell * under * pow(abs(along), power)
            route.append(CGPoint(x: x, y: y))
        }
        let closing = route.count - 1
        // Down the left side, not ruled: it sways a little (10:39).
        func sway(_ y: CGFloat) -> CGFloat {
            let off = 2.6 * sin(y / 53 + turns[1]) + 1.2 * sin(y / 23 + turns[0])
            return left + off * min(1, max(0, (y - middle.y - 6) / 40))
        }
        var y = middle.y + 12
        while y < end - 6 {
            route.append(CGPoint(x: sway(y), y: y))
            y += 14
        }
        route.append(CGPoint(x: sway(end), y: end))
        let line = even(spline(route, per: 10), step: 2)
        func nearest(_ point: CGPoint, from: Int) -> Int {
            var best = from, least = CGFloat.infinity
            for k in from..<line.count {
                let far = hypot(line[k].x - point.x, line[k].y - point.y)
                if far < least { (best, least) = (k, far) }
            }
            return best
        }
        let ring = nearest(out, from: 0)
        let entry = nearest(route[first], from: ring)
        let exit = nearest(route[closing], from: min(line.count - 1, entry + 20))
        var gate: [CGFloat] = [], reached = -CGFloat.infinity
        for k in line.indices {
            if k > ring, k <= entry || k > exit { reached = max(reached, line[k].y) }
            gate.append(reached)
        }
        var marks: [Int] = [], k = exit
        for year in years {
            while k < line.count - 1, line[k].y < year { k += 1 }
            marks.append(k)
        }
        return Onward(line: line, ring: ring, entry: entry, exit: exit, gate: gate,
                      flow: inkFlow(line.count, seed: seed + "onward"), marks: marks, foot: middle.y + tall)
    }

    /// A later work's blot on the line going on: the line runs into it
    /// and, but for the last, on out of it; its stain `spill` pours out
    /// of it to the right.
    static func blot(on onward: Onward, at index: Int, spill: Spill, seed: String) -> Blot {
        let line = onward.line, k = onward.marks[index]
        var random = SeededRandom(seed + "blot\(index)")
        let lobes = (0..<3).map { _ in random.unit() * 2 * CGFloat.pi }
        return Blot(at: line[k], back: line[max(0, k - 8)], to: spill.way.last?.at ?? line[k], into: spill.into, lobes: lobes,
                    on: index < onward.marks.count - 1 ? line[min(line.count - 1, k + 8)] : nil)
    }

    /// A line right under a later work's year and name, for `spill` to
    /// keep clear of: nothing drips onto what is written under them.
    static func shelf(under lines: [CGRect], width: CGFloat) -> [CGPoint] {
        let foot = (lines.map(\.maxY).max() ?? 0) + 12
        return stride(from: CGFloat(-20), through: width + 20, by: 6).map { CGPoint(x: $0, y: foot) }
    }

    /// Where a sea is on the road: from under the text of the stop before
    /// it to over the text of stop `index`, which is across it.
    static func seaBand(before index: Int, on plan: RoadPlan) -> (top: CGFloat, bottom: CGFloat) {
        (plan.texts[index - 1].maxY + 16,
         index == plan.dots.count - 1 ? plan.dots[index].y - 30 : plan.texts[index].minY - 14)
    }

    /// A sea's wash on the road.
    struct Wash: Equatable {
        /// All of it, with room for its uneven edge.
        var frame = CGRect.zero
        /// The band it keeps to; its edge wanders in and out of it.
        var box = CGRect.zero
        /// Where the line comes into it: the paint floods out from there,
        /// and has this far to go.
        var entry = CGPoint.zero
        var reach: CGFloat = 1
        /// The line through it, every `washEach`th point of it, as x and y
        /// in the wash's own frame.
        var points: [Float] = []
        /// How far down the road each point of the line is, from the
        /// first of `points` to well past the sea: by them, how much of
        /// the line the pen has drawn.
        var heights: [CGFloat] = []
        var top: CGFloat = 0
        var bottom: CGFloat = 0

        /// The wash with the pen at `pen`: how far the paint has flooded
        /// (it starts before the pen gets to the sea), how dry it is and
        /// how far the paper round it has soaked (both well after the pen
        /// has left it), and how many points of the line are drawn.
        func came(pen: CGFloat) -> (spread: CGFloat, dry: CGFloat, soak: CGFloat, tip: CGFloat) {
            let spread = min(1.15, max(0, (pen - (top - 70)) / 150))
            let tip = heights.firstIndex { $0 > pen } ?? heights.count
            return (spread, JourneyRoad.ease((pen - bottom - 30) / 260), JourneyRoad.ease((pen - bottom) / 300), CGFloat(tip))
        }

        /// The paint, its darker edge, and the line's ink in it.
        static let onLight = (blue: Color(hex: 0x7098B8), deep: Color(hex: 0x487094), ink: Color(hex: 0x1D1B18))
        static let onDark = (blue: Color(hex: 0x6892B0), deep: Color(hex: 0x96BAD2), ink: Color(hex: 0xF1ECE4))
    }

    /// Every this many points of the line, one is given to a wash.
    static let washEach = 4

    /// The wash of the sea between `top` and `bottom` (its first and last
    /// row of waves) on a road `width` wide. Nothing where there is no
    /// room for a sea.
    static func wash(top: CGFloat, bottom: CGFloat, line: [CGPoint], width: CGFloat) -> Wash? {
        guard bottom - top > 40, line.count > 1 else { return nil }
        let pad: CGFloat = 22
        let frame = CGRect(x: -16, y: (top - pad).rounded(.down), width: width + 32, height: (bottom - top + 2 * pad).rounded(.up))
        // Clear of the stains over and under it.
        let box = CGRect(x: 5, y: top + 5, width: width - 10, height: bottom - top - 11)
        let from = line.firstIndex { $0.y >= top - pad } ?? line.count - 1
        let to = line[from...].firstIndex { $0.y >= bottom + pad } ?? line.count - 1
        let entry = line[line[from...to].firstIndex { $0.y >= top - 4 } ?? to]
        let corners = [CGPoint(x: box.minX, y: box.minY), CGPoint(x: box.maxX, y: box.minY),
                       CGPoint(x: box.minX, y: box.maxY), CGPoint(x: box.maxX, y: box.maxY)]
        // The front is uneven: a little more than the furthest corner.
        let reach = 1.15 * (corners.map { hypot($0.x - entry.x, ($0.y - entry.y) * 1.5) }.max() ?? 1)
        var points: [Float] = []
        for k in stride(from: from, through: to, by: washEach) {
            points.append(Float(line[k].x - frame.minX))
            points.append(Float(line[k].y - frame.minY))
        }
        // The ink goes on running for a while after the pen has left the sea.
        let heights = line[from..<min(line.count, to + 90)].map(\.y)
        return Wash(frame: frame, box: box, entry: entry, reach: reach, points: points, heights: heights, top: top, bottom: bottom)
    }

    /// A drop of ink beside the line: longer the way it was flung.
    struct Speck: Equatable {
        var at: CGPoint
        var long: CGFloat
        var short: CGFloat
        var turn: CGFloat
    }

    /// Where the nib went too fast it spattered (08:55: „jak przy zbyt
    /// szybkim rysowaniu stalówką. Np. tylko przy zakrętach, mogą być po
    /// chwili korygowane białym korektorem”): at a turn, and not at every
    /// one, a few fine drops of ink on the outer side of the bend, thrown
    /// outwards and on the way the pen was going. At some of those turns
    /// only the drops flung furthest are there: the ones nearest the line
    /// were under a touch of white, and with the white gone (16:39: „bez
    /// białych „korekt” linii”) they are not drawn, so that there are no
    /// more drops than there were. None on a stain.
    static func spatter(along line: [CGPoint], turns: [Int], until end: CGPoint, seed: String, off stains: [CGRect] = []) -> [Speck] {
        var cut = line.count
        while cut > 0, hypot(line[cut - 1].x - end.x, line[cut - 1].y - end.y) < lastClear { cut -= 1 }
        var random = SeededRandom(seed + "spatter")
        var specks: [Speck] = []
        /// The way the line goes at a sample.
        func along(_ index: Int) -> CGPoint {
            let before = line[index - 3], after = line[index + 3]
            let step = max(1e-3, hypot(after.x - before.x, after.y - before.y))
            return CGPoint(x: (after.x - before.x) / step, y: (after.y - before.y) / step)
        }
        for turn in turns {
            let here = random.unit()
            guard turn >= 14, turn <= cut - 14, here <= 0.72 else { continue }
            let before = line[turn - 10], at = line[turn], after = line[turn + 10]
            let cross = (at.x - before.x) * (after.y - at.y) - (at.y - before.y) * (after.x - at.x)
            // The outer side of the bend.
            let out: CGFloat = cross > 0 ? -1 : 1
            let count = 3 + Int(4 * random.unit())
            var mine: [(speck: Speck, away: CGFloat)] = []
            for _ in 0..<count {
                let shift = Int(((random.unit() - 0.3) * 22).rounded())
                let index = min(cut - 5, max(4, turn + shift))
                let way = along(index)
                let away = 4.5 + 11 * random.unit() * random.unit()
                let on = 6 * random.unit()
                let size = 0.3 + 0.7 * random.unit() * random.unit()
                let stretch = 1 + 1.3 * random.unit()
                let spot = CGPoint(x: line[index].x - way.y * out * away + way.x * on,
                                   y: line[index].y + way.x * out * away + way.y * on)
                guard spot.y > line[0].y + 4, !stains.contains(where: { $0.insetBy(dx: -4, dy: -4).contains(spot) }) else { continue }
                let flung = atan2(way.x * out + way.y * 0.7, -way.y * out + way.x * 0.7)
                mine.append((Speck(at: spot, long: size * stretch, short: size, turn: flung),
                             hypot(spot.x - line[index].x, spot.y - line[index].y)))
            }
            let fewer = random.unit() < 0.55 && mine.count > 1
            specks += mine.filter { !fewer || $0.away >= 8.5 }.map(\.speck)
        }
        return specks
    }

    /// How full the nib runs at each sample of the line (08:29: „nierównego
    /// tuszu”): a little more here and a little less there, and now and
    /// then a stretch where it runs dry and the line is thinner.
    static func inkFlow(_ count: Int, seed: String) -> [CGFloat] {
        var random = SeededRandom(seed + "flow")
        func wave(_ every: Int) -> [CGFloat] {
            let knots = (0...(count / every + 1)).map { _ in random.unit() }
            return (0..<count).map { q in
                let k = q / every
                return knots[k] + (knots[k + 1] - knots[k]) * ease(CGFloat(q % every) / CGFloat(every))
            }
        }
        let fine = wave(6), dry = wave(34)
        return (0..<count).map { q in 1 + 0.26 * (fine[q] - 0.5) - 0.24 * ease((dry[q] - 0.6) / 0.2) }
    }

    /// The end of the line as the pen draws it (08:29: „cieńszą kreską i
    /// potem grubnie”): from the pen's tip at `pen` (a height on the road)
    /// back to where the line has its full width, which is at `thick` or
    /// `taper` samples behind the tip, whichever is further back; in
    /// between it goes from a hairline to the full nib. `outline` is that
    /// stretch inked, starting a little inside the full line, and `full`
    /// the height down to which the full line is to be shown.
    static func tip(of line: [CGPoint], flow: [CGFloat], until end: CGPoint, pen: CGFloat, thick: CGFloat)
        -> (outline: [CGPoint], full: CGFloat) {
        var cut = line.count
        while cut > 0, hypot(line[cut - 1].x - end.x, line[cut - 1].y - end.y) < lastClear { cut -= 1 }
        let tip = line[..<cut].firstIndex { $0.y > pen } ?? cut
        guard tip > 1 else { return ([], (line.first?.y ?? 0) - 100) }
        let wide = line[..<tip].firstIndex { $0.y > thick } ?? tip
        // Past the line's end the pen is lifted: the taper closes up and the line ends full.
        let past = tip == cut ? max(0, pen - line[cut - 1].y) : 0
        let thin = max(max(0, taper - Int(past / 2)), tip - wide)
        guard thin > 0 else { return ([], line[cut - 1].y + 100) }
        let start = max(0, tip - 1 - thin)
        var from = start
        while from > 0, line[from].y > line[start].y - 5 { from -= 1 }
        let dx = cos(nibTilt) * nib / 2, dy = sin(nibTilt) * nib / 2
        var one: [CGPoint] = [], other: [CGPoint] = []
        for q in from..<tip {
            let full = q < flow.count ? flow[q] : 1
            let k = ease(CGFloat(tip - 1 - q) / CGFloat(thin)) * full
            one.append(CGPoint(x: line[q].x + dx * k, y: line[q].y + dy * k))
            other.append(CGPoint(x: line[q].x - dx * k, y: line[q].y - dy * k))
        }
        return (one + other.reversed(), line[start].y)
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
