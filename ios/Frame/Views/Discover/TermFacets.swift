import SwiftUI
import UIKit

/// One group of the search's chips: a glass button on the bar over the
/// search field opens a small sheet with just that group. Within a group any
/// of the picked ones is enough; the groups together must all fit.
enum TermFacet: String, CaseIterable, Identifiable, Sendable {
    case technique, period, style, color, subject, museum

    var id: String { rawValue }

    var title: String {
        switch self {
        case .technique: "Technika"
        case .period: "Epoka"
        case .style: "Styl"
        case .color: "Kolor"
        case .subject: "Temat"
        case .museum: "Muzeum"
        }
    }

    /// Whether the group holds the chip.
    func holds(_ token: SearchToken) -> Bool {
        switch self {
        case .technique: token.kind == "technique"
        case .period: token.kind == "period"
        case .style: token.kind == "style" || token.kind == "legacy-style"
        case .color: token.kind == "color"
        case .subject: token.kind == "subject" || token.kind == "legacy-subject"
        case .museum: token.kind == "museum" || token.kind == SearchToken.museumOut
        }
    }

    /// What the field itself shows: artists, words, and what no group
    /// holds ("Arcydzieła muzeów", older playlists' Ulubione and Playlisty).
    static func inField(_ token: SearchToken) -> Bool {
        !allCases.contains { $0.holds(token) }
    }

    /// The groups narrowed by words (Mateusz 2026-11-08): while one is open,
    /// the search field's words narrow its list instead of searching, and
    /// the field says what they look for. nil: the field keeps searching
    /// (and tapping it closes the group). A group's own list reads the words
    /// as `filter` (`TermFacetPanel`).
    var fieldPrompt: String? {
        switch self {
        case .museum: "Muzeum albo miasto"
        case .style: "Szukaj stylu"
        case .subject: "Szukaj tematu"
        case .period: "Okres albo rok"
        case .technique, .color: nil
        }
    }

    /// What the group holds: "Ukiyo-e", "Ukiyo-e +2", nil for nothing;
    /// periods side by side on the axis read as one span ("1700–1900").
    func value(_ tokens: [SearchToken], periods: [TermInfo]) -> String? {
        let picked = tokens.filter(holds)
        guard let first = picked.first else { return nil }
        if self == .period, picked.count > 1, let span = PeriodAxis.span(picked.map(\.key), periods: periods) {
            return span
        }
        let more = picked.count > 1 ? " +\(picked.count - 1)" : ""
        let name = self == .color ? ColorTag.name(first.key) : first.name
        return name + more
    }

    /// The group in words: "Styl", "Styl: Ukiyo-e +2", "Epoka: 1700–1900".
    func label(_ tokens: [SearchToken], periods: [TermInfo]) -> String {
        guard let value = value(tokens, periods: periods) else { return title }
        // "Akcent: czerwień" and "Dominuje: błękit" say what they are on their own.
        if self == .color, let first = tokens.first(where: holds), first.key != ColorTag.family(first.key) { return value }
        return "\(title): \(value)"
    }
}

/// The periods as a time line: those that follow one another make the axis,
/// the ones across them (Belle Époque, Edo, Zabory) are named apart.
enum PeriodAxis {
    /// A group of named periods in the sheet.
    struct Region: Identifiable {
        let id: String
        let title: String
        /// The dot by its name and its periods' capsules.
        let colour: Color
    }

    /// The named periods' groups, in order.
    static let regions = [
        Region(id: "antiquity", title: "Starożytność i Bizancjum", colour: Color(light: 0xB07A2A, dark: 0xD9A85A)),
        Region(id: "europe", title: "Europa", colour: Color(light: 0x2F5D8C, dark: 0x7EA6D6)),
        Region(id: "poland", title: "Polska", colour: Color(light: 0xB8432F, dark: 0xE58A6F)),
        Region(id: "east-asia", title: "Japonia i Chiny", colour: Color(light: 0x3F7A55, dark: 0x7CC49A)),
    ]

    /// A named period's group colour; red for one with no group known.
    static func colour(of period: TermInfo) -> Color {
        regions.first { $0.id == period.region }?.colour ?? Theme.bad
    }

    static func split(_ periods: [TermInfo]) -> (axis: [TermInfo], named: [TermInfo]) {
        // The server says which are named; an older one doesn't.
        if periods.contains(where: { $0.region != nil }) {
            return (
                periods.filter { $0.region == nil }.sorted { ($0.yearFrom ?? Int.min) < ($1.yearFrom ?? Int.min) },
                periods.filter { $0.region != nil }
            )
        }
        var axis: [TermInfo] = []
        var named: [TermInfo] = []
        var end = Int.min
        let sorted = periods.enumerated().sorted {
            ($0.element.yearFrom ?? Int.min, $0.offset) < ($1.element.yearFrom ?? Int.min, $1.offset)
        }
        for (_, period) in sorted {
            let from = period.yearFrom ?? Int.min
            if from >= end {
                axis.append(period)
                end = period.yearTo ?? Int.max
            } else {
                named.append(period)
            }
        }
        return (axis, named)
    }

    /// The year a period is read to end with: 1399 → 1400, 1849 → 1850,
    /// but 1930 and the last free year as they are.
    static func shownEnd(_ year: Int) -> Int { (year + 1) % 50 == 0 ? year + 1 : year }

    /// How a span's end reads: "1400", "1955"; one that runs up to this
    /// year reads "obecnie" ("1945–obecnie").
    static func endYear(_ to: Int, now: Int = PeriodAxis.thisYear) -> String {
        to >= now ? "obecnie" : year(shownEnd(to))
    }

    static var thisYear: Int { Calendar.current.component(.year, from: .now) }

    /// A named period's years: "1880–1914"; before Christ (negative
    /// years) with the era: "3100–30 p.n.e.", "509 p.n.e.–476 n.e.".
    static func years(_ period: TermInfo) -> String {
        switch (period.yearFrom, period.yearTo) {
        case let (from?, to?) where to < 0: "\(-from)–\(-to) p.n.e."
        case let (from?, to?) where from < 0: "\(-from) p.n.e.–\(to) n.e."
        case let (from?, to?): "\(from)–\(to >= thisYear ? "obecnie" : "\(to)")"
        case let (nil, to?): "do \(year(to))"
        case let (from?, nil): "od \(year(from))"
        case (nil, nil): ""
        }
    }

    /// One year, before Christ with the era: "30 p.n.e.".
    static func year(_ value: Int) -> String {
        value < 0 ? "\(-value) p.n.e." : "\(value)"
    }

    /// How many years a piece of the axis with no start of its own (the
    /// oldest, "do 500") stands for, so named periods in it get their place.
    static let openStart = 1300

    /// How wide a piece of the axis is next to the others: more room from
    /// 1800 on, where the named periods crowd.
    static func weight(_ piece: TermInfo) -> CGFloat {
        let from = piece.yearFrom ?? Int.min
        if from < 1600 { return 0.7 }
        if from < 1800 { return 0.9 }
        if from < 1945 { return 1.3 }
        return 0.9
    }

    /// Where each piece of the axis starts, from 0 to 1, and last the
    /// axis' end, 1: one more than there are pieces.
    static func edges(_ axis: [TermInfo]) -> [CGFloat] {
        let total = axis.map(weight).reduce(0, +)
        guard total > 0 else { return [0] }
        var out: [CGFloat] = [0]
        var x: CGFloat = 0
        for piece in axis.dropLast() {
            x += weight(piece) / total
            out.append(x)
        }
        out.append(1)
        return out
    }

    /// Where a year falls on the axis, from 0 (its start) to 1 (its end):
    /// within its piece, the pieces as wide as `weight` says.
    static func position(_ year: Int, on axis: [TermInfo]) -> CGFloat {
        guard !axis.isEmpty else { return 0 }
        let edges = edges(axis)
        for (index, piece) in axis.enumerated() {
            let to = piece.yearTo ?? Int.max
            guard year <= to else { continue }
            let end = piece.yearTo.map { $0 + 1 } ?? (year + 1)
            let start = piece.yearFrom ?? (end - openStart)
            if year < start, index == 0 { return 0 }
            let within = min(max(CGFloat(year - start) / CGFloat(max(end - start, 1)), 0), 1)
            return edges[index] + within * (edges[index + 1] - edges[index])
        }
        return 1
    }

    /// Where a piece of the axis ends, for the year under the right bead:
    /// "1400", "1955", "obecnie".
    static func endMark(_ period: TermInfo) -> String {
        period.yearTo.map { endYear($0) } ?? "obecnie"
    }

    /// The top of the Epoka sheet: what is picked and, in grey beside it,
    /// what that means. "1600–1800" · "XVII i XVIII wiek", "XVII wiek" ·
    /// "1600–1700", "Starożytność" · "+ Starożytny Rzym", "Oświecenie" ·
    /// "1715–1789"; nothing picked: "Dowolna epoka".
    static func heading(_ tokens: [SearchToken], periods: [TermInfo]) -> (title: String, aside: String?) {
        let picked = tokens.filter { $0.kind == "period" }
        guard !picked.isEmpty else { return ("Dowolna epoka", nil) }
        let known = Dictionary(periods.map { ($0.key, $0) }, uniquingKeysWith: { first, _ in first })
        // Spans of older playlists ("years:1880-1914"): just the names.
        guard picked.allSatisfy({ known[$0.key] != nil }) else {
            return (picked.map(\.name).joined(separator: ", "), nil)
        }
        let axis = split(periods).axis
        let onAxis = axis.filter { piece in picked.contains { $0.key == piece.key } }
        let named = picked.filter { token in !axis.contains { $0.key == token.key } }
        guard !onAxis.isEmpty else {
            if named.count == 1, let period = known[named[0].key] { return (period.name, years(period)) }
            return (named.map(\.name).joined(separator: ", "), nil)
        }
        let title: String
        if onAxis.count == 1 {
            title = onAxis[0].name
        } else {
            title = span(onAxis.map(\.key), periods: periods) ?? onAxis.map(\.name).joined(separator: ", ")
        }
        if !named.isEmpty { return (title, "+ " + named.map(\.name).joined(separator: ", ")) }
        if onAxis.count == 1 {
            let piece = onAxis[0]
            // "1800–1850" already says its years.
            guard !piece.name.contains(where: \.isNumber) else { return (title, nil) }
            switch (piece.yearFrom, piece.yearTo) {
            case let (from?, to?): return (title, "\(year(from))–\(endYear(to))")
            case let (nil, to?): return (title, "do \(endYear(to))")
            default: return (title, nil)
            }
        }
        // Centuries side by side: "XVII i XVIII wiek", "XV–XVII wiek".
        let suffix = " wiek"
        guard span(onAxis.map(\.key), periods: periods) != nil,
              onAxis.allSatisfy({ $0.name.hasSuffix(suffix) }) else { return (title, nil) }
        let numerals = onAxis.map { String($0.name.dropLast(suffix.count)) }
        let joined = numerals.count == 2 ? "\(numerals[0]) i \(numerals[1])" : "\(numerals[0])–\(numerals[numerals.count - 1])"
        return (title, joined + suffix)
    }

    /// A named period on its lane: where its capsule lies and how wide its
    /// name is, in points.
    struct LaneItem: Equatable {
        let key: String
        let from: CGFloat
        let to: CGFloat
        let label: CGFloat
    }

    /// Where a named period went: its row, its capsule, and its name beside
    /// it (right when there is room, else left) or, on a long capsule with
    /// no room either side, inside it.
    struct Placed: Equatable, Identifiable {
        enum Side: Equatable { case right, left, inside }
        let key: String
        let row: Int
        let from: CGFloat
        let to: CGFloat
        let labelX: CGFloat
        let side: Side
        /// What it takes of its row, the capsule and the name: the tap's place.
        let taken: ClosedRange<CGFloat>
        var id: String { key }
    }

    /// The lines of the named periods picked, under the axis: each goes on
    /// the first row where it keeps clear of the others, so two that
    /// overlap (Zabory and Biedermeier) lie one under the other. The rows,
    /// in the order given.
    static func stack(_ spans: [ClosedRange<CGFloat>], clear: CGFloat = 2) -> [Int] {
        var rows: [[ClosedRange<CGFloat>]] = []
        var out = Array(repeating: 0, count: spans.count)
        for index in spans.indices.sorted(by: { (spans[$0].lowerBound, $0) < (spans[$1].lowerBound, $1) }) {
            let span = spans[index]
            let row = rows.firstIndex { taken in
                taken.allSatisfy { span.upperBound + clear <= $0.lowerBound || span.lowerBound >= $0.upperBound + clear }
            } ?? rows.count
            if row == rows.count { rows.append([]) }
            rows[row].append(span)
            out[index] = row
        }
        return out
    }

    /// The named periods of one group in as few rows as they go: each takes
    /// the first row where its capsule and name keep clear of the others.
    static func pack(_ items: [LaneItem], width: CGFloat, gap: CGFloat = 7, clear: CGFloat = 8) -> [Placed] {
        var rows: [[ClosedRange<CGFloat>]] = []
        var out: [Placed] = []
        for item in items {
            let to = max(item.to, item.from + 6)
            var options: [(side: Placed.Side, taken: ClosedRange<CGFloat>, labelX: CGFloat)] = []
            if to + gap + item.label <= width {
                options.append((.right, item.from ... to + gap + item.label, to + gap))
            }
            if item.from - gap - item.label >= 0 {
                options.append((.left, item.from - gap - item.label ... to, item.from - gap - item.label))
            }
            if options.isEmpty { options.append((.inside, item.from ... to, item.from + 8)) }
            var place: (row: Int, option: Int)?
            search: for (index, row) in rows.enumerated() {
                for (choice, option) in options.enumerated() where row.allSatisfy({
                    option.taken.upperBound + clear <= $0.lowerBound || option.taken.lowerBound >= $0.upperBound + clear
                }) {
                    place = (index, choice)
                    break search
                }
            }
            if place == nil {
                rows.append([])
                place = (rows.count - 1, 0)
            }
            guard let place else { continue }
            let option = options[place.option]
            rows[place.row].append(option.taken)
            out.append(Placed(key: item.key, row: place.row, from: item.from, to: to,
                              labelX: option.labelX, side: option.side, taken: option.taken))
        }
        return out
    }

    /// Under each piece of the axis: where it starts; the oldest piece, with
    /// no start, by its name ("staroż.", "śr." from an older server).
    static func mark(_ period: TermInfo) -> String {
        if let from = period.yearFrom { return year(from) }
        return (period.yearTo ?? 0) < 1000 ? "staroż." : "śr."
    }

    /// Picked keys as one span when they are pieces of the axis side by side:
    /// "1700–1900", "do 1500", "od 1900"; nil otherwise.
    static func span(_ keys: [String], periods: [TermInfo]) -> String? {
        let axis = split(periods).axis
        let indices = keys.compactMap { key in axis.firstIndex { $0.key == key } }.sorted()
        guard indices.count == keys.count, let low = indices.first, let high = indices.last,
              high - low + 1 == indices.count
        else { return nil }
        let from = axis[low].yearFrom
        let to = axis[high].yearTo.map { endYear($0) }
        switch (from, to) {
        case let (from?, to?): return "\(from)–\(to)"
        case let (nil, to?): return "do \(to)"
        case let (from?, nil): return "od \(from)"
        case (nil, nil): return nil
        }
    }
}

/// The groups over the search field: six glass buttons, three to a row
/// across the width; a picked group turns blue and shows what it holds under
/// its name. A tapped group grows into its glass panel in the same place,
/// over the field. The X next to the field (`termSearch`) takes every
/// group's chips off along with the words.
struct TermFacetBar: View {
    @Environment(AppModel.self) private var model
    @Binding var tokens: [SearchToken]
    /// The search field's words: they narrow an open group that has a list
    /// to narrow (`TermFacet.fieldPrompt`).
    var lookup: TermLookup
    var colors: [String] = []
    /// The search field: a group opening puts its keyboard away, and the
    /// field tapped closes the group.
    var focus: FocusState<Bool>.Binding
    /// The tallest an open group may be.
    var panelHeight: CGFloat = 460

    @State private var open: TermFacet? = TermFacetBar.launched
    /// Where each group's button is on the screen: its panel grows out of it
    /// and shrinks back into it.
    @State private var frames: [TermFacet: CGRect] = [:]
    /// The open group's glass has grown out of its button (false while it
    /// grows and shrinks back).
    @State private var grown = false

    /// Over the keyboard the system field floats above the bar's usual place
    /// (the keyboard's top): the bar rises over the field.
    static let overField: CGFloat = 66
    /// How much of the screen between the title and the tab bar an open
    /// group may take (Epoka's periods need most of it).
    static let panelShare: CGFloat = 0.85
    /// Epoka may take all of that room: its time line and all four groups of
    /// lanes then fit without scrolling (at 94% Japonia i Chiny was still
    /// below the edge).
    static let periodGrowth: CGFloat = 1 / panelShare

    /// CI's screenshots of a group's panel.
    private static var launched: TermFacet? {
        switch LaunchRoute.screen {
        case "search-picker": .period
        case "search-colors", "search-tones": .color
        case "search-museums": .museum
        case "search-styles": .style
        case "search-subjects": .subject
        case "search-techniques": .technique
        default: nil
        }
    }

    /// Muzeum is always there (Mateusz 2026-11-08): its bands load their
    /// own places when opened, so the button waits for nothing. (It used to
    /// wait for the sources' list, and on the first visit the second row
    /// came without it for a moment.)
    private var facets: [TermFacet] {
        TermFacet.allCases.filter { $0 != .color || !colors.isEmpty }
    }

    private var periods: [TermInfo] { model.vocabulary.filter { $0.kind == "period" } }

    var body: some View {
        ZStack(alignment: .bottom) {
            GlassEffectContainer(spacing: 8) {
                if !grown {
                    Grid(horizontalSpacing: 8, verticalSpacing: 8) {
                        ForEach(Array(stride(from: 0, to: facets.count, by: 3)), id: \.self) { start in
                            GridRow {
                                ForEach(facets[start ..< min(start + 3, facets.count)]) { facet in button(facet) }
                            }
                        }
                    }
                }
            }
            // The panel's glass is its own, outside the buttons' container:
            // in it, the system's morph melted the panel out of the first
            // button ("Technika") whatever group it was, glassEffectID or
            // not. Here the glass itself stretches out of the tapped button
            // and back into it (PanelGlass).
            if let open {
                TermFacetPanel(
                    facet: open, tokens: $tokens, colors: colors,
                    filter: open.fieldPrompt == nil ? "" : lookup.trimmed,
                    // Over the keyboard the bar stands higher: so much less room.
                    maxHeight: (open == .period ? panelHeight * Self.periodGrowth : panelHeight)
                        - (focus.wrappedValue ? Self.overField : 0),
                    close: close
                )
                // The words come in once the glass has grown, and go first.
                .animation(grown ? .easeIn(duration: 0.22).delay(0.12) : .easeOut(duration: 0.1)) {
                    $0.opacity(grown ? 1 : 0)
                }
                .background { PanelGlass(source: frames[open], grown: grown) }
                // A tap between the chips stays in the panel, not outside it.
                .contentShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
                .allowsHitTesting(grown)
                // Another group tapped while one shrinks: a new panel.
                .id(open)
                .onAppear { withAnimation(Self.motion) { grown = true } }
            }
        }
        .frame(maxWidth: .infinity, alignment: .trailing)
        // A tap anywhere outside the open group is its "Gotowe". The layer
        // lies under the panel (which keeps its own taps, contentShape) and
        // reaches far past the bar, over the page above it; the system
        // search field and tab bar stay on top of it.
        .background {
            if grown {
                Color.clear
                    .contentShape(Rectangle())
                    .frame(width: Self.outside, height: Self.outside)
                    .onTapGesture(perform: close)
                    .accessibilityHidden(true)
            }
        }
        .preference(key: GroupPanelOpen.self, value: open != nil)
        .padding(.bottom, focus.wrappedValue ? Self.overField : 8)
        // The field tapped: a group with a list takes its words, any other
        // closes.
        .onChange(of: focus.wrappedValue) { _, focused in
            if focused, let open, open.fieldPrompt == nil { close() }
        }
        .onChange(of: open, initial: true) { _, open in
            lookup.narrow(open?.fieldPrompt == nil ? nil : open)
            // CI's screenshots of a narrowed group.
            if let open, open == Self.launched, let typed = LaunchRoute.typed { lookup.text = typed }
        }
        // Gone with a group open (the editor hides the groups while its
        // name is typed): the field searches again.
        .onDisappear { lookup.narrow(nil) }
        .task { await model.loadVocabulary() }
    }

    /// The side of the tap-outside layer: more than any screen, around the bar.
    private static let outside: CGFloat = 4000

    /// How the glass stretches: a little give at the end, like the system's.
    static let motion = Animation.bouncy(duration: 0.45, extraBounce: 0.05)

    /// The glass shrinks back into the button; then the panel goes.
    private func close() {
        guard open != nil else { return }
        // Its "Gotowe" also ends the words typed for it.
        if lookup.narrowing != nil { focus.wrappedValue = false }
        withAnimation(Self.motion) {
            grown = false
        } completion: {
            // Not when another group opened meanwhile.
            if !grown { open = nil }
        }
    }

    private func button(_ facet: TermFacet) -> some View {
        let picked = tokens.filter(facet.holds)
        let value = facet.value(tokens, periods: periods)
        let on = value != nil
        return Button {
            focus.wrappedValue = false
            open = facet
        } label: {
            // Picked, the symbol stands for the group's name: "✎ Olej +1";
            // Kolor shows the picked colours' dots instead, Technika the
            // picked techniques' works in small circles, Styl the picked
            // styles' works in small frames.
            HStack(spacing: 5) {
                let swatches = facet == .color ? picked.map(\.key) : []
                let works = facet == .technique ? picked.compactMap { TechniqueArt.asset($0.key) } : []
                let covers = facet == .style ? picked.compactMap { StyleArt.asset($0.key) } : []
                if !swatches.isEmpty {
                    HStack(spacing: 3) {
                        ForEach(Array(swatches.prefix(3)), id: \.self) { tag in
                            ColorTagDot(tag: tag, size: 8, stroke: .white.opacity(0.7), lineWidth: 1)
                        }
                    }
                } else if !works.isEmpty {
                    HStack(spacing: -6) {
                        ForEach(Array(works.prefix(3)), id: \.self) { asset in
                            Image(asset)
                                .resizable()
                                .scaledToFill()
                                .frame(width: 17, height: 17)
                                .clipShape(Circle())
                                .overlay(Circle().stroke(.white.opacity(0.75), lineWidth: 1.5))
                        }
                    }
                    .accessibilityHidden(true)
                } else if !covers.isEmpty {
                    HStack(spacing: -4) {
                        ForEach(Array(covers.prefix(3)), id: \.self) { asset in
                            StyleCover(asset: asset, width: 14, height: 18, moulding: 1.5, shadow: false)
                        }
                    }
                    .accessibilityHidden(true)
                } else {
                    GroupMark(kind: facet.rawValue, bold: on)
                        .font(.subheadline.weight(on ? .semibold : .regular))
                        .imageScale(.small)
                }
                Text(value ?? facet.title)
                    .font(.subheadline.weight(on ? .semibold : .medium))
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
            }
            .padding(.horizontal, 8)
            .frame(maxWidth: .infinity, minHeight: 44)
            .foregroundStyle(on ? Theme.paper : Theme.ink)
            .contentShape(Capsule())
            .glassEffect(on ? Glass.regular.tint(Theme.ink).interactive() : Glass.regular.interactive(), in: .capsule)
            .onGeometryChange(for: CGRect.self) { $0.frame(in: .global) } action: { frames[facet] = $0 }
        }
        .buttonStyle(.plain)
        .sensoryFeedback(.selection, trigger: open == facet)
        .accessibilityLabel(facet.label(tokens, periods: periods))
        .accessibilityHint("Otwiera wybór: \(facet.title.lowercased())")
    }
}

/// An open group's glass: grown, the panel's whole rounded rectangle; not
/// grown, the tapped button's capsule in its place on the screen. Animated
/// between the two, the glass stretches out of the button and back.
struct PanelGlass: View {
    /// The button on the screen (nil: the glass grows from the middle).
    var source: CGRect?
    var grown: Bool

    var body: some View {
        GeometryReader { proxy in
            let panel = proxy.frame(in: .global)
            let from = source ?? CGRect(x: panel.midX - 30, y: panel.maxY - 44, width: 60, height: 44)
            let rect = grown
                ? CGRect(origin: .zero, size: proxy.size)
                : CGRect(x: from.minX - panel.minX, y: from.minY - panel.minY, width: from.width, height: from.height)
            Color.clear
                .glassEffect(
                    Glass.regular.tint(Theme.paper.opacity(grown ? 0.55 : 0.2)),
                    in: RoundedRectangle(cornerRadius: grown ? 28 : from.height / 2, style: .continuous)
                )
                .frame(width: rect.width, height: rect.height)
                .offset(x: rect.minX, y: rect.minY)
                // Over the button it would veil the button's name: it
                // shows at once when it leaves the button, and goes as it
                // lands back on it.
                // (Its own timing for the fade only, not for the stretch.)
                .animation(grown ? .easeOut(duration: 0.08) : .easeIn(duration: 0.16).delay(0.2)) {
                    $0.opacity(grown ? 1 : 0)
                }
        }
    }
}

/// The cards of the Kolor sheet: Kolorystyka (colours at a level) and
/// Tonacja (moods in pairs).
enum ColourCard: Hashable {
    case colours, tones
}

/// What an open group holds, over the search field, as tall as what it
/// holds (longer groups scroll inside it); its glass is PanelGlass.
struct TermFacetPanel: View {
    @Environment(AppModel.self) private var model
    let facet: TermFacet
    @Binding var tokens: [SearchToken]
    var colors: [String] = []
    /// The search field's words, narrowing the group's list (only for the
    /// groups with a `TermFacet.fieldPrompt`; "" for the others).
    var filter: String = ""
    var maxHeight: CGFloat = 460
    var close: () -> Void

    /// The Kolor sheet's card: Kolorystyka or Tonacja.
    @State private var colourCard = ColourCard.colours
    /// Museums: the picked ones are left out ("Wykluczone"), with none
    /// picked yet (with some, their kind says it).
    @State private var leaveOut = false
    /// How tall the group's content is.
    @State private var height: CGFloat = 280

    private static let header: CGFloat = 52

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Button("Wyczyść") { withAnimation(.snappy) { tokens.removeAll(where: facet.holds) } }
                    .disabled(!tokens.contains(where: facet.holds))
                Spacer()
                Text(facet.title).font(.headline).foregroundStyle(Theme.ink)
                Spacer()
                Button("Gotowe", action: close).fontWeight(.semibold)
            }
            .tint(Theme.ink)
            .padding(.horizontal, 18)
            .frame(height: Self.header)
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    content
                    if let footnote {
                        Text(footnote)
                            .font(.footnote)
                            .foregroundStyle(Theme.inkSoft)
                            .multilineTextAlignment(facet == .subject ? .center : .leading)
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, alignment: facet == .subject ? .center : .leading)
                    }
                }
                .padding(.horizontal, 18)
                .padding(.bottom, 18)
                .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { height = $0 }
            }
            .scrollBounceBehavior(.basedOnSize)
            .scrollDismissesKeyboard(.interactively)
            .frame(height: min(height, max(maxHeight - Self.header, 160)))
        }
        .task { await model.loadVocabulary(fresh: true) }
        // Opened (or first filled) with moods alone: show them. Later
        // changes keep the card the person is on.
        .onChange(of: colourKeys, initial: true) { old, keys in
            guard facet == .color, old == keys || old.isEmpty, !keys.isEmpty,
                  !keys.contains(where: { ColorTag.level(of: $0) != nil }) else { return }
            colourCard = .tones
        }
    }

    /// The Kolor sheet's picks, colours and moods.
    private var colourKeys: [String] {
        tokens.filter { $0.kind == "color" }.map(\.key)
    }

    /// Under the group; the Kolor sheet says what it does by itself.
    private var footnote: String? {
        switch facet {
        case .museum: nil
        // Epoka says it with its beads and band.
        case .color, .technique, .period: nil
        default: "Wybierz dowolnie wiele: wystarczy, że dzieło pasuje do jednego z nich."
        }
    }

    @ViewBuilder private var content: some View {
        switch facet {
        case .technique: techniques
        case .style: styles
        case .subject: terms
        case .period: PeriodPicker(tokens: $tokens, filter: filter)
        case .color: palette
        case .museum: museumList
        }
    }

    // MARK: Picking

    private func picked(_ kind: String, _ key: String) -> Bool {
        tokens.contains { $0.kind == kind && $0.key == key }
    }

    private func toggle(_ kind: String, _ key: String, _ name: String) {
        if picked(kind, key) {
            tokens.removeAll { $0.kind == kind && $0.key == key }
        } else {
            tokens.append(SearchToken(kind: kind, key: key, name: name))
        }
    }

    // MARK: Techniques, styles, subjects

    private func fold(_ text: String) -> String {
        text.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil)
    }

    /// The group's terms the search field's words fit (all with none).
    private func matching(_ all: [TermInfo]) -> [TermInfo] {
        let wanted = fold(filter.trimmingCharacters(in: .whitespaces))
        guard !wanted.isEmpty else { return all }
        return all.filter { term in
            fold(term.name).contains(wanted) || term.words.contains { fold($0).contains(wanted) }
        }
    }

    /// Older playlists' museum facet values: shown picked, a tap takes them off.
    private var legacy: [SearchToken] {
        tokens.filter { facet.holds($0) && $0.kind.hasPrefix("legacy-") }
    }

    private var terms: some View {
        let shown = matching(model.vocabulary.filter { $0.kind == facet.rawValue })
        return VStack(alignment: .leading, spacing: 12) {
            if facet == .subject {
                subjectList(shown)
            } else {
                FlowLayout(spacing: 8) {
                    legacyChips
                    ForEach(shown) { term in
                        Chip(title: term.name, selected: picked(term.kind, term.key)) {
                            toggle(term.kind, term.key, term.name)
                        }
                    }
                }
            }
            if shown.isEmpty { nothingFound }
        }
    }

    /// Temat as a list (PLAN 3.3zzz64): the subjects in five groups, two
    /// columns of rows with their drawings in watercolour. A subject the
    /// app has no drawing for (a new one on the server) and older
    /// playlists' values are chips under them.
    private func subjectList(_ shown: [TermInfo]) -> some View {
        let groups = TopicArt.groups.compactMap { group -> (title: String, terms: [TermInfo])? in
            let terms = group.keys.compactMap { key in shown.first { TopicArt.bare($0.key) == key } }
            return terms.isEmpty ? nil : (title: group.title, terms: terms)
        }
        let grouped = Set(TopicArt.groups.flatMap { $0.keys })
        let rest = shown.filter { !grouped.contains(TopicArt.bare($0.key)) }
        let columns = [GridItem(.flexible(), spacing: 14, alignment: .top), GridItem(.flexible(), alignment: .top)]
        return VStack(alignment: .leading, spacing: 4) {
            ForEach(groups, id: \.title) { group in
                Eyebrow(group.title)
                    .padding(.leading, 4)
                    .padding(.top, group.title == groups.first?.title ? 0 : 12)
                LazyVGrid(columns: columns, spacing: 0) {
                    ForEach(group.terms) { term in
                        TopicRow(
                            drawing: TopicArt.drawing(term.key),
                            wash: TopicArt.washAsset(term.key),
                            title: term.name,
                            selected: picked(term.kind, term.key)
                        ) {
                            toggle(term.kind, term.key, term.name)
                        }
                    }
                }
            }
            if !rest.isEmpty || !legacy.isEmpty {
                FlowLayout(spacing: 8) {
                    legacyChips
                    ForEach(rest) { term in
                        Chip(title: term.name, selected: picked(term.kind, term.key)) {
                            toggle(term.kind, term.key, term.name)
                        }
                    }
                }
                .padding(.top, 12)
            }
        }
    }

    @ViewBuilder private var legacyChips: some View {
        ForEach(legacy) { token in
            Chip(title: token.name, selected: true) {
                tokens.removeAll { $0.id == token.id }
            }
        }
    }

    /// The words typed for the group find nothing in it: they can go to the
    /// search as a word, the group closing.
    @ViewBuilder private var nothingFound: some View {
        let words = filter.trimmingCharacters(in: .whitespaces)
        if !words.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Nic takiego w tej grupie.")
                    .font(.footnote)
                    .foregroundStyle(Theme.inkSoft)
                Button {
                    let word = SearchToken(kind: "word", key: words, name: words)
                    if !tokens.contains(word) { tokens.append(word) }
                    close()
                } label: {
                    Label("Szukaj „\(filter)” jako słowa", systemImage: "magnifyingglass")
                        .font(.footnote.weight(.semibold))
                }
                .buttonStyle(.plain)
                .foregroundStyle(Theme.ink)
            }
        }
    }

    // MARK: Styles

    /// The Styl sheet (PLAN 3.3zzz61): a small framed work for each style,
    /// in light oak, its years under its name, on five shelves in the order
    /// of time that scroll sideways (`StyleArt.shelves`). A style the app
    /// has no work for (a new one on the server) is a chip under them.
    private var styles: some View {
        let shown = matching(model.vocabulary.filter { $0.kind == "style" })
        let shelves = StyleArt.shelves.compactMap { shelf -> StyleArt.Shelf? in
            let terms = shelf.keys.compactMap { key in shown.first { $0.key == key } }
            return terms.isEmpty ? nil : StyleArt.Shelf(title: shelf.title, span: shelf.span, terms: terms)
        }
        let rest = shown.filter { StyleArt.asset($0.key) == nil }
        return VStack(alignment: .leading, spacing: 6) {
            ForEach(shelves, id: \.title) { shelf in
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Eyebrow(shelf.title)
                    Text("· \(shelf.span)")
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.inkSoft)
                }
                .padding(.leading, 4)
                styleShelf(shelf.terms)
            }
            if !rest.isEmpty || !legacy.isEmpty {
                FlowLayout(spacing: 8) {
                    legacyChips
                    ForEach(rest) { term in
                        Chip(title: term.name, selected: picked(term.kind, term.key)) {
                            toggle(term.kind, term.key, term.name)
                        }
                    }
                }
                .padding(.top, 6)
            }
            if shown.isEmpty { nothingFound }
        }
    }

    /// One shelf, as wide as the panel (past its margins), scrolled at
    /// first to its first picked style.
    private func styleShelf(_ terms: [TermInfo]) -> some View {
        let first = terms.first { picked($0.kind, $0.key) }?.key
        return ScrollViewReader { proxy in
            ScrollView(.horizontal) {
                HStack(alignment: .top, spacing: 0) {
                    ForEach(terms) { term in
                        if let asset = StyleArt.asset(term.key) {
                            StyleFrame(key: term.key, name: term.name, asset: asset,
                                       picked: picked(term.kind, term.key)) {
                                withAnimation(.snappy(duration: 0.25)) { toggle(term.kind, term.key, term.name) }
                            }
                            .id(term.key)
                        }
                    }
                }
                .padding(.bottom, 8)
            }
            .scrollIndicators(.hidden)
            .contentMargins(.horizontal, 12, for: .scrollContent)
            .padding(.horizontal, -18)
            .onAppear {
                if let first { proxy.scrollTo(first, anchor: .center) }
            }
        }
    }

    // MARK: Techniques

    /// The Technika sheet (PLAN 3.3zzz4): a work in a circle for each
    /// technique, four to a row; first the pictures, then the other things
    /// (manuscripts, photographs, sculpture, crafts), which the search leaves
    /// out unless picked. A technique the app has no work for is a chip.
    private var techniques: some View {
        let all = model.vocabulary.filter { $0.kind == "technique" }
        let drawn = all.filter { TechniqueArt.asset($0.key) != nil }
        let pictures = drawn.filter { !TechniqueArt.objects.contains($0.key) }
        let objects = drawn.filter { TechniqueArt.objects.contains($0.key) }
        let rest = all.filter { TechniqueArt.asset($0.key) == nil }
        return VStack(alignment: .leading, spacing: 8) {
            techniqueGrid(pictures)
            if !objects.isEmpty {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Eyebrow("Inne")
                    Text("· dostępne wyłącznie po wybraniu")
                        .font(.system(size: 11))
                        .foregroundStyle(Theme.inkSoft)
                }
                .padding(.top, 6)
                .padding(.leading, 4)
                techniqueGrid(objects)
            }
            if !rest.isEmpty {
                FlowLayout(spacing: 8) {
                    ForEach(rest) { term in
                        Chip(title: term.name, selected: picked(term.kind, term.key)) {
                            toggle(term.kind, term.key, term.name)
                        }
                    }
                }
                .padding(.top, 6)
            }
        }
    }

    private func techniqueGrid(_ terms: [TermInfo]) -> some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 2), count: 4), alignment: .center, spacing: 8) {
            ForEach(terms) { term in
                if let asset = TechniqueArt.asset(term.key) {
                    TechniqueSwatch(name: term.name, asset: asset, picked: picked(term.kind, term.key)) {
                        withAnimation(.snappy(duration: 0.25)) { toggle(term.kind, term.key, term.name) }
                    }
                }
            }
        }
    }

    // MARK: Colours

    /// The Kolor sheet (PLAN 3.3zzt): Kolorystyka, up to three colours
    /// each at a level, picked by tapping the swatch again and again, its
    /// ring growing; Tonacja, the moods in pairs, one of each at most.
    private var palette: some View {
        let colours = tokens.filter { $0.kind == "color" && ColorTag.level(of: $0.key) != nil }
        let tones = tokens.filter { $0.kind == "color" && ColorTag.level(of: $0.key) == nil }
        return VStack(alignment: .leading, spacing: 16) {
            Picker("Jak", selection: $colourCard) {
                Text(colours.isEmpty ? "Kolorystyka" : "Kolorystyka · \(Set(colours.map { ColorTag.family($0.key) }).count)")
                    .tag(ColourCard.colours)
                Text(tones.isEmpty ? "Tonacja" : "Tonacja · \(toneGroupsPicked(tones))").tag(ColourCard.tones)
            }
            .pickerStyle(.segmented)
            // Both cards laid out, the other one unseen, so the sheet keeps
            // one height when switching (Mateusz 2026-11-05).
            ZStack(alignment: .top) {
                colourGrid.cardShown(colourCard == .colours)
                toneGrid.cardShown(colourCard == .tones)
            }
        }
    }

    /// How many Tonacja groups the tokens pick a side of (Ciemne and Średnie
    /// are one).
    private func toneGroupsPicked(_ tones: [SearchToken]) -> Int {
        Set(tones.map { token in
            ColorTag.toneGroups.firstIndex { $0.contains(ColorTag.family(token.key)) } ?? -1
        }).count
    }

    /// The level a family is picked at, nil for none.
    private func pickedLevel(_ family: String) -> ColorTag.Level? {
        tokens.filter { $0.kind == "color" && ColorTag.family($0.key) == family }
            .compactMap { ColorTag.level(of: $0.key) }
            .max { $0.rawValue < $1.rawValue }
    }

    private var pickedFamilies: [String] {
        ColorTag.families.filter { pickedLevel($0) != nil }
    }

    /// The family at ``level`` (nil: not picked), in place of its tokens
    /// (older rules' too) and where the first of them was.
    private func setLevel(_ family: String, _ level: ColorTag.Level?) {
        let at = tokens.firstIndex { $0.kind == "color" && ColorTag.level(of: $0.key) != nil && ColorTag.family($0.key) == family }
        tokens.removeAll { $0.kind == "color" && ColorTag.level(of: $0.key) != nil && ColorTag.family($0.key) == family }
        guard let level else { return }
        let key = ColorTag.level(family, level)
        let token = SearchToken(kind: "color", key: key, name: ColorTag.name(key))
        tokens.insert(token, at: min(at ?? tokens.count, tokens.count))
    }

    /// The next level of a tap: accent, clear, much, most, then off.
    private func tap(_ family: String) {
        let levels = ColorTag.Level.of(family)
        guard let now = pickedLevel(family) else {
            if pickedFamilies.count < ColorTag.maxLevels { setLevel(family, levels.first) }
            return
        }
        let next = levels.firstIndex(of: now).map { $0 + 1 } ?? 0
        setLevel(family, next < levels.count ? levels[next] : nil)
    }

    private var colourGrid: some View {
        let families = ColorTag.families.filter { colors.contains($0) || pickedLevel($0) != nil }
        let full = pickedFamilies.count >= ColorTag.maxLevels
        let columns = Array(repeating: GridItem(.flexible(), spacing: ToneGroup.columnGap), count: ToneRow.columns)
        return LazyVGrid(columns: columns, spacing: 10) {
            ForEach(families, id: \.self) { family in
                let level = pickedLevel(family)
                LevelSwatch(family: family, level: level, dimmed: full && level == nil) {
                    withAnimation(.snappy(duration: 0.25)) { tap(family) }
                }
                .contextMenu {
                    ForEach(ColorTag.Level.of(family), id: \.self) { choice in
                        Button {
                            withAnimation(.snappy(duration: 0.25)) { setLevel(family, choice) }
                        } label: {
                            if choice == level {
                                Label(choice.name(for: family).capitalized, systemImage: "checkmark")
                            } else {
                                Text(choice.name(for: family).capitalized)
                            }
                        }
                        .disabled(level == nil && full)
                    }
                    if level != nil {
                        Button("Usuń", role: .destructive) {
                            withAnimation(.snappy(duration: 0.25)) { setLevel(family, nil) }
                        }
                    }
                }
            }
        }
    }

    /// A mood picked: from the Tonacja card ("tone:warm") or an older rule ("warm").
    private func tonePicked(_ mood: String) -> Bool {
        tokens.contains { $0.kind == "color" && ($0.key == ColorTag.tone(mood) || $0.key == mood) }
    }

    /// A tap turns a side of a group on or off; sides of one group are
    /// either-or (Ciemne or Średnie). All of a group is the same as none,
    /// so the tap that would pick the last one leaves it alone picked.
    private func tapTone(_ mood: String, group: [String]) {
        let inGroup = { (token: SearchToken) in
            token.kind == "color" && group.contains(ColorTag.family(token.key)) && ColorTag.level(of: token.key) == nil
        }
        let at = tokens.firstIndex(where: inGroup)
        if tonePicked(mood) {
            tokens.removeAll { inGroup($0) && ColorTag.family($0.key) == mood }
            return
        }
        // Older rules' plain moods ("warm") turn into the card's tokens.
        var picked = group.filter(tonePicked) + [mood]
        // All of a group is none; two ends without the middle no range.
        let ends = Set([group.first, group.last].compactMap { $0 })
        if picked.count == group.count || (group.count > 2 && Set(picked) == ends) { picked = [mood] }
        tokens.removeAll(where: inGroup)
        let added = group.filter(picked.contains).map { side in
            let key = ColorTag.tone(side)
            return SearchToken(kind: "color", key: key, name: ColorTag.name(key))
        }
        tokens.insert(contentsOf: added, at: min(at ?? tokens.count, tokens.count))
    }

    /// Two groups in a row (szkic 14, T1): Temperatura and Nasycenie, then
    /// Barwność and Jasność. Each holds three of the seven Kolorystyka
    /// columns, the first three and the last three (``ToneRow``), with its
    /// middle dot on the middle one, on Kolorystyka's rows, so switching
    /// cards the middles stay put (Neutralne where Pomarańcz is, Umiarkowane
    /// on Błękit; Mateusz 2026-11-05 23:32, seven columns since Beż).
    private var toneGrid: some View {
        let groups = ColorTag.toneGroups
        return VStack(spacing: 10) {
            ForEach(Array(stride(from: 0, to: groups.count, by: 2)), id: \.self) { start in
                ToneRow {
                    ForEach(groups[start..<min(start + 2, groups.count)], id: \.self) { group in toneGroup(group) }
                }
            }
        }
    }

    private func toneGroup(_ group: [String]) -> some View {
        ToneGroup(moods: group, picked: tonePicked) { mood in
            withAnimation(.snappy(duration: 0.25)) { tapTone(mood, group: group) }
        }
    }

    // MARK: Museums

    /// "Wybrane" (false) or "Wykluczone" (true): what the picked
    /// museums mean. Switched with museums picked, they keep being picked
    /// and mean the other thing.
    private var museumsOut: Binding<Bool> {
        Binding(
            get: {
                if tokens.contains(where: { $0.kind == SearchToken.museumOut }) { return true }
                if tokens.contains(where: { $0.kind == "museum" }) { return false }
                return leaveOut
            },
            set: { out in
                leaveOut = out
                withAnimation(.snappy) {
                    tokens = tokens.map { token in
                        guard facet.holds(token) else { return token }
                        return SearchToken.museum(token.key, name: model.placeName(token.key), out: out)
                    }
                }
            }
        )
    }

    private var museumList: some View {
        let out = museumsOut.wrappedValue
        let count = tokens.filter(facet.holds).count
        return VStack(alignment: .leading, spacing: 14) {
            Picker("Które muzea", selection: museumsOut) {
                Text(!out && count > 0 ? "Wybrane · \(count)" : "Wybrane").tag(false)
                Text(out && count > 0 ? "Wykluczone · \(count)" : "Wykluczone").tag(true)
            }
            .pickerStyle(.segmented)
            // Bands with the museums' works, on the panel's glass (szkic 4;
            // no counts nor notes under them, Mateusz 2026-11-08).
            PlaceBands(tokens: $tokens, out: out, filter: filter)
        }
    }
}

/// The periods as a time line: two beads on the axis pick the years between
/// them, and under it the named periods (Belle Époque, Edo, Zabory) on lanes
/// of the same scale, a band from the axis down through them over the years
/// picked.
struct PeriodPicker: View {
    @Environment(AppModel.self) private var model
    @Binding var tokens: [SearchToken]
    /// The search field's words ("Okres albo rok"): only the named periods
    /// they fit stay on the lanes (and the picked ones).
    var filter: String = ""

    @State private var width: CGFloat = 0
    /// While dragging: what was picked before and what the finger holds.
    @State private var before: [SearchToken]?
    @State private var grip: Grip?

    private enum Grip: Equatable {
        case low, high
        /// Painting pieces from this one on.
        case paint(Int)
    }

    /// The axis' line from the top; the band starts on it.
    private static let rail: CGFloat = 10
    private static let bead: CGFloat = 15
    private static let rowHeight: CGFloat = 16
    /// From one named period's line under the axis to the next one's.
    private static let lineStep: CGFloat = 5
    /// Narrower than this the two years go as one label, under the beads.
    private static let narrow: CGFloat = 40

    private var periods: [TermInfo] { model.vocabulary.filter { $0.kind == "period" } }

    private func picked(_ key: String) -> Bool {
        tokens.contains { $0.kind == "period" && $0.key == key }
    }

    /// The named period fits the words: its name or one of its words has
    /// them, or a year typed is in its years.
    private func fits(_ period: TermInfo) -> Bool {
        let wanted = TermLookup.fold(filter.trimmingCharacters(in: .whitespaces))
        guard !wanted.isEmpty, !picked(period.key) else { return true }
        if let year = Int(wanted) {
            return (period.yearFrom ?? Int.min) <= year && year <= (period.yearTo ?? Int.max)
        }
        return TermLookup.fold(period.name).contains(wanted)
            || period.words.contains { TermLookup.fold($0.replacingOccurrences(of: "*", with: "")).contains(wanted) }
    }

    var body: some View {
        let split = PeriodAxis.split(periods)
        let axis = split.axis
        let all = split.named
        let named = all.filter(fits)
        let vocabulary = Set(periods.map(\.key))
        // Spans of older playlists ("years:1880-1914").
        let other = tokens.filter { $0.kind == "period" && !vocabulary.contains($0.key) }
        let regions = PeriodAxis.regions.filter { region in named.contains { $0.region == region.id } }
        // An older server: one group with no name of its own.
        let loose = named.filter { period in !PeriodAxis.regions.contains { $0.id == period.region } }
        let heading = PeriodAxis.heading(tokens, periods: periods)
        let edges = PeriodAxis.edges(axis)
        let range = Self.range(axis, in: tokens)
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(heading.title)
                    .font(.title3.weight(.semibold))
                    .contentTransition(.numericText())
                if let aside = heading.aside {
                    Text(aside)
                        .font(.subheadline.monospacedDigit())
                        .foregroundStyle(Theme.inkSoft)
                        .lineLimit(1)
                }
            }
            OfferedWidth(fallback: width > 0 ? width : 320) {
                VStack(alignment: .leading, spacing: 10) {
                    if !axis.isEmpty, width > 0 {
                        line(axis, edges: edges, range: range, brackets: all.filter { picked($0.key) })
                    }
                    if width > 0 {
                        ForEach(regions) { region in
                            lanes(region, named.filter { $0.region == region.id }, axis: axis, range: range)
                        }
                    }
                    if named.isEmpty, !all.isEmpty, !filter.isEmpty {
                        Text("Żaden nazwany okres nie pasuje do „\(filter)”.")
                            .font(.footnote)
                            .foregroundStyle(Theme.inkSoft)
                            .padding(.top, 4)
                    }
                }
            }
            .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { offered in
                // Only a real width: the axis and lanes are drawn to it.
                guard offered.isFinite, offered > 0, abs(offered - width) > 0.5 else { return }
                width = min(offered, 1200)
            }
            .background(alignment: .topLeading) {
                if let range, width > 0, edges.count > range.upperBound + 1 {
                    // The years picked, from the axis down through the lanes.
                    UnevenRoundedRectangle(bottomLeadingRadius: 12, bottomTrailingRadius: 12, style: .continuous)
                        .fill(Theme.ink.opacity(0.06))
                        .frame(width: (edges[range.upperBound + 1] - edges[range.lowerBound]) * width)
                        .padding(.top, Self.rail)
                        .offset(x: edges[range.lowerBound] * width)
                        .animation(.snappy(duration: 0.2), value: range)
                        .accessibilityHidden(true)
                }
            }
            if !loose.isEmpty || !other.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Eyebrow("Nazwane okresy")
                    FlowLayout(spacing: 8) {
                        ForEach(loose) { period in
                            Chip(title: period.name, selected: picked(period.key)) { toggle(period) }
                        }
                        ForEach(other) { token in
                            Chip(title: token.name, selected: true) {
                                tokens.removeAll { $0.id == token.id }
                            }
                        }
                    }
                }
            }
        }
    }

    // MARK: The axis

    /// The pieces of the axis picked, first to last; nil for none.
    private static func range(_ axis: [TermInfo], in tokens: [SearchToken]) -> ClosedRange<Int>? {
        let indices = axis.indices.filter { index in
            tokens.contains { $0.kind == "period" && $0.key == axis[index].key }
        }
        guard let low = indices.first, let high = indices.last else { return nil }
        return low ... high
    }

    /// The rail with a tick at every piece's edge, two beads on it, the
    /// years picked a darker stroke between them, and their years under
    /// them; a line under the rail for each named period picked, in its
    /// group's colour. The room for those lines is always kept, so the
    /// sheet does not jump when one is picked.
    private func line(_ axis: [TermInfo], edges: [CGFloat], range: ClosedRange<Int>?, brackets: [TermInfo]) -> some View {
        let rail = Self.rail
        let low = range?.lowerBound ?? 0
        let high = range?.upperBound ?? axis.count - 1
        let x0 = edges[low] * width
        let x1 = edges[high + 1] * width
        let left = PeriodAxis.mark(axis[low])
        let right = PeriodAxis.endMark(axis[high])
        // About 7 pt a character: room for the left year centred on its
        // bead and the right one ("obecnie" is long) up to its bead.
        let room = CGFloat(left.count) * 3.5 + CGFloat(right.count) * 7
        let narrow = x1 - x0 < max(Self.narrow, room)
        let showBrackets = !brackets.isEmpty && !(range != nil && narrow)
        let lines = brackets.map { period -> (period: TermInfo, from: CGFloat, width: CGFloat) in
            let from = PeriodAxis.position(period.yearFrom ?? Int.min / 2, on: axis) * width
            let to = PeriodAxis.position(period.yearTo ?? Int.max / 2, on: axis) * width
            let length = max(to - from, 4)
            return (period, min(from, width - 4), length)
        }
        let rows = PeriodAxis.stack(lines.map { $0.from ... $0.from + $0.width })
        // One line's room is always kept; more only when picks overlap.
        let extra = showBrackets ? CGFloat(rows.max() ?? 0) * Self.lineStep : 0
        let labelsTop = rail + 14 + extra
        let ink = range == nil ? Theme.inkSoft : Theme.ink
        return ZStack(alignment: .topLeading) {
            Capsule()
                .fill(Theme.hairline)
                .frame(width: width, height: 2)
                .offset(y: rail - 1)
            ForEach(edges.indices, id: \.self) { index in
                Capsule()
                    .fill(Theme.hairline)
                    .frame(width: 1.5, height: 8)
                    .offset(x: edges[index] * width - 0.75, y: rail - 4)
            }
            if range != nil {
                Capsule()
                    .fill(Theme.ink)
                    .frame(width: x1 - x0, height: 3)
                    .offset(x: x0, y: rail - 1.5)
            }
            if showBrackets {
                ForEach(lines.indices, id: \.self) { index in
                    let stroke = lines[index]
                    Capsule()
                        .fill(PeriodAxis.colour(of: stroke.period))
                        .frame(width: stroke.width, height: 2.5)
                        .offset(x: stroke.from, y: rail + 9 + CGFloat(rows[index]) * Self.lineStep)
                }
            }
            bead(at: x0)
            bead(at: x1)
            Group {
                if narrow {
                    // In the right half it ends at the right bead, so
                    // "1945–obecnie" stays inside the sheet.
                    let box = width
                    let trailing = x1 > width / 2
                    Text("\(left)–\(right)")
                        .fixedSize()
                        .frame(width: box, alignment: trailing ? .trailing : .leading)
                        .offset(x: trailing ? x1 + Self.bead / 2 - box : x0 - Self.bead / 2, y: labelsTop)
                } else {
                    yearLabel(left, at: x0, top: labelsTop, leading: x0 < 24)
                    yearLabel(right, at: x1, top: labelsTop, trailing: x1 > width - 24)
                }
            }
            .font(.caption.weight(.semibold).monospacedDigit())
            .foregroundStyle(ink)
        }
        .frame(width: width, height: labelsTop + 16, alignment: .topLeading)
        .animation(.snappy(duration: 0.2), value: range)
        .contentShape(Rectangle())
        .gesture(drag(axis, edges: edges, range: range))
        .sensoryFeedback(.selection, trigger: range)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Oś czasu")
        .accessibilityValue(range == nil ? "Dowolna epoka" : "\(left)–\(right)")
        .accessibilityAction(named: "Wcześniejszy początek") { setAxis(max(low - 1, 0) ... high, axis) }
        .accessibilityAction(named: "Późniejszy początek") { setAxis(min(low + 1, high) ... high, axis) }
        .accessibilityAction(named: "Wcześniejszy koniec") { setAxis(low ... max(high - 1, low), axis) }
        .accessibilityAction(named: "Późniejszy koniec") { setAxis(low ... min(high + 1, axis.count - 1), axis) }
        .accessibilityAction(named: "Cała oś") { setAxis(nil, axis) }
    }

    private func bead(at x: CGFloat) -> some View {
        Circle()
            .fill(Theme.ink)
            .frame(width: Self.bead, height: Self.bead)
            .shadow(color: .black.opacity(0.18), radius: 1.5, y: 1)
            .offset(x: x - Self.bead / 2, y: Self.rail - Self.bead / 2)
    }

    /// A bead's year, under its middle; at the axis' ends it keeps inside.
    private func yearLabel(_ text: String, at x: CGFloat, top: CGFloat, leading: Bool = false, trailing: Bool = false) -> some View {
        let box: CGFloat = 80
        let alignment: Alignment = leading ? .leading : (trailing ? .trailing : .center)
        let start = leading ? x - Self.bead / 2 : (trailing ? x + Self.bead / 2 - box : x - box / 2)
        return Text(text)
            .fixedSize()
            .frame(width: box, alignment: alignment)
            .offset(x: start, y: top)
    }

    /// A finger near a bead moves it from edge to edge of the pieces;
    /// elsewhere it paints the pieces it passes. A tap on the only piece
    /// picked takes it off.
    private func drag(_ axis: [TermInfo], edges: [CGFloat], range: ClosedRange<Int>?) -> some Gesture {
        DragGesture(minimumDistance: 0)
            .onChanged { drag in
                guard width > 0, !axis.isEmpty else { return }
                let x = drag.location.x
                if grip == nil {
                    before = tokens
                    let low = edges[range?.lowerBound ?? 0] * width
                    let high = edges[(range?.upperBound ?? axis.count - 1) + 1] * width
                    let toLow = abs(x - low)
                    let toHigh = abs(x - high)
                    if min(toLow, toHigh) <= 22 {
                        grip = toLow < toHigh || (toLow == toHigh && x < (low + high) / 2) ? Grip.low : Grip.high
                    } else {
                        grip = .paint(piece(at: x, edges: edges))
                    }
                }
                let held = Self.range(axis, in: before ?? tokens) ?? 0 ... axis.count - 1
                switch grip {
                case .low?:
                    setAxis(min(edge(near: x, edges: edges), held.upperBound) ... held.upperBound, axis)
                case .high?:
                    setAxis(held.lowerBound ... max(edge(near: x, edges: edges) - 1, held.lowerBound), axis)
                case let .paint(start)?:
                    let index = piece(at: x, edges: edges)
                    setAxis(min(start, index) ... max(start, index), axis)
                case nil:
                    break
                }
            }
            .onEnded { drag in
                if case let .paint(start)? = grip, abs(drag.translation.width) < 4, let before,
                   Self.range(axis, in: before) == start ... start {
                    setAxis(nil, axis)
                }
                grip = nil
                before = nil
            }
    }

    private func piece(at x: CGFloat, edges: [CGFloat]) -> Int {
        let count = edges.count - 1
        return (0 ..< count).first { x < edges[$0 + 1] * width } ?? count - 1
    }

    private func edge(near x: CGFloat, edges: [CGFloat]) -> Int {
        edges.indices.min { abs(edges[$0] * width - x) < abs(edges[$1] * width - x) } ?? 0
    }

    /// Picks these pieces of the axis and no others; the whole axis is the
    /// same as none.
    private func setAxis(_ range: ClosedRange<Int>?, _ axis: [TermInfo]) {
        let keys = Set(axis.map(\.key))
        var next = tokens.filter { !($0.kind == "period" && keys.contains($0.key)) }
        if let range, range != 0 ... axis.count - 1 {
            next += axis[range].map { SearchToken(kind: "period", key: $0.key, name: $0.name) }
        }
        if next != tokens { tokens = next }
    }

    // MARK: The named periods

    /// One group: its name with its colour's dot, then its periods on lanes
    /// of the axis' scale, each name beside its capsule. Those outside the
    /// years picked fade.
    private func lanes(_ region: PeriodAxis.Region, _ periods: [TermInfo], axis: [TermInfo],
                       range: ClosedRange<Int>?) -> some View {
        let sorted = periods.sorted { ($0.yearFrom ?? Int.min) < ($1.yearFrom ?? Int.min) }
        let items = sorted.map { period in
            PeriodAxis.LaneItem(
                key: period.key,
                from: PeriodAxis.position(period.yearFrom ?? Int.min / 2, on: axis) * width,
                to: PeriodAxis.position(period.yearTo ?? Int.max / 2, on: axis) * width,
                label: Self.labelWidth(period.name)
            )
        }
        let placed = PeriodAxis.pack(items, width: width)
        let rows = (placed.map(\.row).max() ?? -1) + 1
        let years = range.map { (axis[$0.lowerBound].yearFrom ?? Int.min, axis[$0.upperBound].yearTo ?? Int.max) }
        return VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 7) {
                Circle().fill(region.colour).frame(width: 8, height: 8)
                Eyebrow(region.title)
            }
            ZStack(alignment: .topLeading) {
                ForEach(placed) { place in
                    if let period = sorted.first(where: { $0.key == place.key }) {
                        let outside = years.map { span in
                            (period.yearTo ?? Int.max) < span.0 || (period.yearFrom ?? Int.min) > span.1
                        } ?? false
                        laneItem(period, place, colour: region.colour, faded: outside && !picked(period.key))
                    }
                }
            }
            .frame(width: width, height: CGFloat(rows) * Self.rowHeight, alignment: .topLeading)
        }
    }

    private func laneItem(_ period: TermInfo, _ place: PeriodAxis.Placed, colour: Color, faded: Bool) -> some View {
        let on = picked(period.key)
        let inside = place.side == .inside
        let height: CGFloat = inside ? 14 : (on ? 10 : 8)
        let start = place.taken.lowerBound
        return Button {
            toggle(period)
        } label: {
            ZStack(alignment: .topLeading) {
                Capsule()
                    .fill(colour.opacity(capsuleOpacity(on: on, inside: inside, faded: faded)))
                    .frame(width: place.to - place.from, height: height)
                    .overlay {
                        if on {
                            Capsule().stroke(colour, lineWidth: 1.5).padding(-3)
                        }
                    }
                    .offset(x: place.from - start, y: (Self.rowHeight - height) / 2)
                Text(period.name)
                    .font(.system(size: 12, weight: on ? .semibold : .medium))
                    // Outside the years picked: softer, but still easy to read.
                    .foregroundStyle(faded ? Theme.inkSoft : Theme.ink)
                    .fixedSize()
                    .offset(x: place.labelX - start, y: 1.5)
            }
            .frame(width: place.taken.upperBound - start, height: Self.rowHeight, alignment: .topLeading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .offset(x: start, y: CGFloat(place.row) * Self.rowHeight)
        .sensoryFeedback(.selection, trigger: on)
        .accessibilityLabel("\(period.name), \(PeriodAxis.years(period))")
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    /// A capsule's colour: full in the years picked (and picked ones),
    /// pale outside them; the long ones with the name inside lighter.
    private func capsuleOpacity(on: Bool, inside: Bool, faded: Bool) -> Double {
        if inside { return on ? 0.6 : (faded ? 0.18 : 0.42) }
        if on { return 1 }
        return faded ? 0.25 : 0.9
    }

    /// How wide a name is on its lane, bold as when picked.
    private static func labelWidth(_ name: String) -> CGFloat {
        let font = UIFont.systemFont(ofSize: 12, weight: .semibold)
        return ceil((name as NSString).size(withAttributes: [.font: font]).width)
    }

    private func toggle(_ period: TermInfo) {
        if picked(period.key) {
            tokens.removeAll { $0.kind == "period" && $0.key == period.key }
        } else {
            tokens.append(SearchToken(kind: "period", key: period.key, name: period.name))
        }
    }
}

/// Takes the width it is offered, never more: a finite one, or when asked
/// for its ideal size (no width, or an endless one) the last width it had.
/// The time line and its lanes are drawn to that width, so it must not
/// grow with them.
private struct OfferedWidth: Layout {
    var fallback: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width.flatMap { $0.isFinite ? $0 : nil } ?? fallback
        let height = subviews.first?.sizeThatFits(ProposedViewSize(width: width, height: nil)).height ?? 0
        return CGSize(width: width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        subviews.first?.place(at: bounds.origin, anchor: .topLeading,
                              proposal: ProposedViewSize(width: bounds.width, height: nil))
    }
}

/// The works that stand for the techniques in the Technika sheet and on
/// its button: public-domain museum images in the app's assets
/// ("technique-painting": Vermeer's Girl with a Pearl Earring).
enum TechniqueArt {
    /// The things that are no pictures; the search leaves them out unless
    /// picked (the server's `OBJECT_CATEGORIES`).
    static let objects: Set<String> = [
        "technique:manuscripts", "technique:photography", "technique:sculpture", "technique:decorative",
    ]

    private static let drawn: Set<String> = [
        "painting", "print", "drawing", "poster", "manuscripts", "photography", "sculpture", "decorative",
    ]

    /// The asset's name for a technique, nil for one with no work.
    static func asset(_ key: String) -> String? {
        guard key.hasPrefix("technique:") else { return nil }
        let name = String(key.dropFirst("technique:".count))
        return drawn.contains(name) ? "technique-\(name)" : nil
    }
}

/// A technique in the Technika sheet: a work in a circle, picked with a
/// ring like a colour's in the Kolor sheet (Mateusz 2026-11-06, C2), its
/// name under it.
/// The works that stand for the styles in the Styl sheet and on its
/// button, and the sheet's shelves (Mateusz 2026-11-08): public-domain
/// museum images in the app's assets ("style-rococo": Fragonard's Swing),
/// the years of each style, the shelves in the order of time.
enum StyleArt {
    struct Shelf {
        let title: String
        let span: String
        let keys: [String]
        /// The sheet's: the styles on it the search field's words fit.
        var terms: [TermInfo] = []

        init(title: String, span: String, keys: [String]) {
            self.title = title
            self.span = span
            self.keys = keys
        }

        init(title: String, span: String, terms: [TermInfo]) {
            self.title = title
            self.span = span
            keys = terms.map(\.key)
            self.terms = terms
        }
    }

    static let shelves: [Shelf] = [
        Shelf(title: "Dawni mistrzowie", span: "XIV–XVIII w.", keys: [
            "style:gothic", "style:renaissance", "style:mannerism", "style:dutch-golden-age", "style:baroque",
            "style:rococo", "style:neoclassicism",
        ]),
        Shelf(title: "Romantyzm i realizm", span: "1790–1900", keys: [
            "style:romanticism", "style:hudson-river", "style:barbizon", "style:academic", "style:orientalism",
            "style:realism", "style:pre-raphaelite", "style:munich-school",
        ]),
        Shelf(title: "Przełom wieków", span: "1867–1918", keys: [
            "style:impressionism", "style:japonisme", "style:tonalism", "style:symbolism", "style:pointillism",
            "style:post-impressionism", "style:nabis", "style:art-nouveau", "style:young-poland",
        ]),
        Shelf(title: "Awangarda", span: "1904–1940", keys: [
            "style:fauvism", "style:expressionism", "style:cubism", "style:futurism", "style:abstraction",
            "style:constructivism", "style:dada", "style:de-stijl", "style:bauhaus", "style:new-objectivity",
            "style:surrealism", "style:art-deco",
        ]),
        Shelf(title: "Japonia", span: "1600–1960", keys: ["style:rinpa", "style:ukiyo-e", "style:shin-hanga"]),
    ]

    /// When each style was, under its name.
    static let years: [String: String] = [
        "style:gothic": "1250–1500", "style:renaissance": "1400–1600", "style:dutch-golden-age": "1600–1690",
        "style:baroque": "1600–1750", "style:rococo": "1720–1780", "style:neoclassicism": "1760–1830",
        "style:romanticism": "1790–1850", "style:hudson-river": "1825–1875", "style:academic": "1830–1900",
        "style:realism": "1840–1880", "style:pre-raphaelite": "1848–1900", "style:impressionism": "1867–1890",
        "style:tonalism": "1880–1915", "style:symbolism": "1880–1910", "style:post-impressionism": "1886–1905",
        "style:nabis": "1888–1900", "style:art-nouveau": "1890–1910", "style:young-poland": "1890–1918",
        "style:fauvism": "1904–1908", "style:expressionism": "1905–1925", "style:cubism": "1907–1920",
        "style:abstraction": "od 1910", "style:constructivism": "1913–1930", "style:de-stijl": "1917–1931",
        "style:bauhaus": "1919–1933", "style:art-deco": "1920–1940", "style:ukiyo-e": "1660–1900",
        "style:shin-hanga": "od 1915",
        "style:mannerism": "1520–1600", "style:barbizon": "1830–1870", "style:orientalism": "1830–1900",
        "style:munich-school": "1860–1900", "style:japonisme": "1860–1910", "style:pointillism": "1884–1910",
        "style:futurism": "1909–1916", "style:dada": "1916–1924", "style:new-objectivity": "1919–1933",
        "style:surrealism": "od 1924", "style:rinpa": "1600–1870",
    ]

    /// Where a long name breaks under its small frame.
    private static let lines: [String: String] = [
        "style:post-impressionism": "Post-\nimpresjonizm",
        "style:constructivism": "Konstruktywizm\ni\u{00A0}suprematyzm",
        "style:hudson-river": "Szkoła znad\nrzeki Hudson",
        "style:dutch-golden-age": "Złoty wiek\nholenderski",
        "style:young-poland": "Młoda\nPolska",
        "style:barbizon": "Szkoła z\nBarbizonu",
        "style:munich-school": "Szkoła\nmonachijska",
        "style:new-objectivity": "Nowa\nRzeczowość",
    ]

    private static let drawn = Set(shelves.flatMap(\.keys))

    /// The asset's name for a style, nil for one with no work.
    static func asset(_ key: String) -> String? {
        guard drawn.contains(key) else { return nil }
        return "style-\(key.dropFirst("style:".count))"
    }

    /// The name as it stands under the frame.
    static func label(_ key: String, name: String) -> String {
        lines[key] ?? TechniqueSwatch.bound(name)
    }
}

/// A style's work in its light-oak frame: a 3 pt moulding and a soft
/// shadow, like a small picture on the wall; on the Styl button smaller,
/// with no shadow.
struct StyleCover: View {
    let asset: String
    var width: CGFloat = 50
    var height: CGFloat = 64
    var moulding: CGFloat = 3
    var shadow = true

    @Environment(\.colorScheme) private var scheme

    var body: some View {
        Image(asset)
            .resizable()
            .scaledToFill()
            .frame(width: width - 2 * moulding, height: height - 2 * moulding)
            .clipped()
            .overlay(Rectangle().strokeBorder(.black.opacity(0.3), lineWidth: 0.5))
            .padding(moulding)
            .background(Theme.oak)
            .shadow(color: Self.shade.opacity(shadow ? (scheme == .dark ? 0.6 : 0.3) : 0), radius: 2.5, y: 2)
    }

    private static let shade = Color(red: 30 / 255, green: 20 / 255, blue: 10 / 255)
}

/// A style in the Styl sheet: its framed work, a square ink ring around it
/// when picked, its name and years under it.
struct StyleFrame: View {
    let key: String
    let name: String
    let asset: String
    let picked: Bool
    let action: () -> Void

    static let width: CGFloat = 68

    var body: some View {
        Button(action: action) {
            VStack(spacing: 0) {
                ZStack {
                    if picked {
                        RoundedRectangle(cornerRadius: 3)
                            .strokeBorder(Theme.ink, lineWidth: 2.5)
                            .transition(.opacity)
                    }
                    StyleCover(asset: asset)
                }
                .frame(width: 58, height: 72)
                .padding(.top, 2)
                Text(StyleArt.label(key, name: name))
                    .font(.system(size: 11, weight: picked ? .semibold : .regular))
                    .foregroundStyle(picked ? Theme.ink : Theme.inkSoft)
                    .multilineTextAlignment(.center)
                    .lineLimit(2)
                    .minimumScaleFactor(0.8)
                    .padding(.top, 4)
                // No years under the name: the shelf heading carries the
                // span (Mateusz 2026-11-09, PLAN 3.3zzz65).
            }
            .frame(width: Self.width)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .sensoryFeedback(.selection, trigger: picked)
        .accessibilityLabel(StyleArt.years[key].map { "\(name), \($0)" } ?? name)
        .accessibilityAddTraits(picked ? .isSelected : [])
    }
}

struct TechniqueSwatch: View {
    let name: String
    let asset: String
    let picked: Bool
    let action: () -> Void

    private static let side: CGFloat = 60
    private static let ring: CGFloat = 74

    /// A one-letter word ("i", "w", "z") never ends a line: it keeps to the
    /// next word ("Rysunki / i akwarele", not "Rysunki i / akwarele").
    static func bound(_ text: String) -> String {
        let words = text.split(separator: " ", omittingEmptySubsequences: false)
        var out = ""
        for (index, word) in words.enumerated() {
            out += word
            if index < words.count - 1 { out += word.count == 1 ? "\u{00A0}" : " " }
        }
        return out
    }

    var body: some View {
        Button(action: action) {
            VStack(spacing: 4) {
                ZStack {
                    if picked {
                        Circle()
                            .strokeBorder(Theme.ink, lineWidth: 3.5)
                            .transition(.opacity)
                    }
                    Image(asset)
                        .resizable()
                        .scaledToFill()
                        .frame(width: Self.side, height: Self.side)
                        .clipShape(Circle())
                        .overlay(Circle().strokeBorder(Theme.ink.opacity(0.22), lineWidth: 0.5))
                }
                .frame(width: Self.ring, height: Self.ring)
                Text(Self.bound(name))
                    .font(.caption.weight(picked ? .semibold : .regular))
                    .foregroundStyle(picked ? Theme.ink : Theme.inkSoft)
                    .multilineTextAlignment(.center)
                    .lineLimit(2, reservesSpace: true)
                    .minimumScaleFactor(0.85)
            }
            .frame(maxWidth: .infinity)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .sensoryFeedback(.selection, trigger: picked)
        .accessibilityLabel(name)
        .accessibilityAddTraits(picked ? .isSelected : [])
    }
}

/// A colour in the Kolor sheet: its swatch, the ring of its level around
/// it (one quarter an accent, the whole ring most of the work) on a pale
/// track, its name and level under it.
struct LevelSwatch: View {
    let family: String
    let level: ColorTag.Level?
    var dimmed = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 3) {
                ZStack {
                    if let level {
                        Circle().stroke(Theme.hairline, lineWidth: 3.5)
                        Circle()
                            .trim(from: 0, to: level.fraction)
                            .stroke(ColorTag.ring(family), style: StrokeStyle(lineWidth: 3.5, lineCap: .round))
                            .rotationEffect(.degrees(-90))
                    }
                    Circle()
                        .fill(ColorTag.color(family))
                        .overlay(Circle().strokeBorder(Theme.ink.opacity(0.22)))
                        .frame(width: 34, height: 34)
                    if level != nil {
                        Image(systemName: "checkmark")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(ColorTag.light(family) ? Color(hex: 0x1D1B18) : .white)
                    }
                }
                .frame(width: 46, height: 46)
                Text(ColorTag.name(family))
                    .font(.caption2.weight(level != nil ? .semibold : .regular))
                    .foregroundStyle(level != nil ? Theme.ink : Theme.inkSoft)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                Text(level?.name(for: family) ?? " ")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }
            .opacity(dimmed ? 0.3 : 1)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .sensoryFeedback(.selection, trigger: level)
        .accessibilityLabel(ColorTag.name(family))
        .accessibilityValue(level?.name(for: family) ?? "nie wybrany")
        .accessibilityHint("Stuknij, by było go więcej; po większości kolor się wyłącza.")
        .accessibilityAddTraits(level != nil ? .isSelected : [])
    }
}

/// A row of the Tonacja card on Kolorystyka's columns: its first group on
/// the first three of them, its second on the last three, the middle
/// column between them empty.
struct ToneRow: Layout {
    /// Kolorystyka's swatches in a row.
    static let columns = 7
    /// The columns a group holds.
    static let span = 3

    /// How wide a group is in a row ``width`` wide.
    static func groupWidth(in width: CGFloat) -> CGFloat {
        let gap = ToneGroup.columnGap
        let column = (width - gap * CGFloat(columns - 1)) / CGFloat(columns)
        return max(column * CGFloat(span) + gap * CGFloat(span - 1), 0)
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.replacingUnspecifiedDimensions().width
        let each = ProposedViewSize(width: Self.groupWidth(in: width), height: proposal.height)
        let height = subviews.map { $0.sizeThatFits(each).height }.max() ?? 0
        return CGSize(width: width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let width = Self.groupWidth(in: bounds.width)
        let each = ProposedViewSize(width: width, height: bounds.height)
        for (index, subview) in subviews.enumerated() {
            // The first from the leading edge, the others from the trailing one.
            let x = index == 0 ? bounds.minX : bounds.maxX - width
            subview.place(at: CGPoint(x: x, y: bounds.minY), anchor: .topLeading, proposal: each)
        }
    }
}

/// A group of the Tonacja card: two or three mood swatches sunk in a grey
/// track like a switch (the grey of the Kolorystyka/Tonacja picker); the
/// picked one's ring fits in the track, the others fade. Every work is on
/// one side of each group, the middle one where the ends aren't all of it
/// (Mateusz 2026-11-05). Under it one name for the group ("Temperatura").
struct ToneGroup: View {
    /// Between Kolorystyka's columns (its grid's spacing).
    static let columnGap: CGFloat = 2
    /// Between the dots.
    private static let gap: CGFloat = 12
    /// Track around the dots, enough for the picked ring.
    private static let inset: CGFloat = 7
    private static let size: CGFloat = 34
    /// How far a ring stands off its dots.
    private static let ringOut: CGFloat = 5
    /// A Kolorystyka swatch's frame, so the rows line up.
    private static let cell: CGFloat = 46

    let moods: [String]
    let picked: (String) -> Bool
    let action: (String) -> Void

    var body: some View {
        // Like a Kolorystyka swatch: the dots, a name, a second line.
        VStack(spacing: 3) {
            GeometryReader { proxy in
                // The middle dot on the middle of three columns (Neutralne
                // where Pomarańcz is); the ends close to it, not out on the
                // columns, which would spread them too far (Mateusz 23:37).
                // Two dots (Barwność) either side of the middle.
                let step = Self.size + Self.gap
                let mid = proxy.size.width / 2
                let y = proxy.size.height / 2
                let x = { (index: Int) in mid + (CGFloat(index) - CGFloat(moods.count - 1) / 2) * step }
                ZStack {
                    Capsule()
                        .fill(
                            Theme.ink.opacity(0.07)
                                .shadow(.inner(color: .black.opacity(0.1), radius: 1.5, y: 1))
                        )
                        .frame(
                            width: CGFloat(moods.count - 1) * step + Self.size + 2 * Self.inset,
                            height: Self.size + 2 * Self.inset
                        )
                        .position(x: mid, y: y)
                    ForEach(Array(moods.enumerated()), id: \.element) { index, mood in
                        dot(mood, ringed: range == nil).position(x: x(index), y: y)
                    }
                    if let range {
                        Capsule()
                            .stroke(Theme.ink, lineWidth: 3.5)
                            .frame(
                                width: CGFloat(range.count - 1) * step + Self.size + 2 * Self.ringOut,
                                height: Self.size + 2 * Self.ringOut
                            )
                            .position(x: (x(range.lowerBound) + x(range.upperBound)) / 2, y: y)
                            .allowsHitTesting(false)
                            .transition(.opacity)
                    }
                }
            }
            .frame(height: Self.cell)
            // What the group is about; the picked side is told by its ring
            // alone (Mateusz: no word for it). A little lower than a
            // colour's name, clear of the track.
            let side = moods.contains(where: picked)
            Text(ColorTag.toneTitle(moods[0]))
                .font(.caption2.weight(side ? .semibold : .regular))
                .foregroundStyle(side ? Theme.ink : Theme.inkSoft)
                .lineLimit(1)
                .fixedSize()
                .offset(y: 4)
            // Kolorystyka's level line, so a row is as tall as its row.
            Text(" ")
                .font(.caption2.weight(.semibold))
                .accessibilityHidden(true)
        }
        .frame(maxWidth: .infinity)
    }

    /// Two neighbours picked (Ciemne and Średnie): their indices, held in
    /// one ring like a range from–to (szkic 15, W2).
    private var range: ClosedRange<Int>? {
        let on = moods.indices.filter { picked(moods[$0]) }
        guard on.count > 1, let first = on.first, let last = on.last else { return nil }
        return first...last
    }

    private func dot(_ mood: String, ringed: Bool) -> some View {
        let on = picked(mood)
        let off = !on && moods.contains(where: picked)
        return Button { action(mood) } label: {
            ZStack {
                MoodFill(tag: mood)
                    .overlay(Circle().strokeBorder(Theme.ink.opacity(0.2)))
                if on {
                    if ringed {
                        Circle()
                            .stroke(ColorTag.ring(mood), lineWidth: 3.5)
                            .padding(-Self.ringOut)
                    }
                    Image(systemName: "checkmark")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(ColorTag.light(mood) ? Color(hex: 0x1D1B18) : .white)
                        .shadow(color: .black.opacity(ColorTag.light(mood) ? 0 : 0.5), radius: 1)
                }
            }
            .frame(width: Self.size, height: Self.size)
            .opacity(off ? 0.38 : 1)
            .contentShape(Circle().inset(by: -8))
        }
        .buttonStyle(.plain)
        .sensoryFeedback(.selection, trigger: on)
        .accessibilityLabel(ColorTag.name(mood))
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}

private extension View {
    /// One of the Kolor sheet's cards: laid out either way, seen and
    /// touched only when it is the one picked.
    func cardShown(_ shown: Bool) -> some View {
        opacity(shown ? 1 : 0)
            .allowsHitTesting(shown)
            .accessibilityHidden(!shown)
    }
}
