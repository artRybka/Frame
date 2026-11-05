import SwiftUI

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

    /// The long groups: their sheet can be pulled up to the whole screen and
    /// has a field to narrow the list.
    var long: Bool { self == .style || self == .subject }

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
    }

    /// The named periods' groups, in order.
    static let regions = [
        Region(id: "europe", title: "Europa"),
        Region(id: "poland", title: "Polska"),
        Region(id: "east-asia", title: "Japonia i Chiny"),
    ]

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

    /// A named period's years: "1880–1914".
    static func years(_ period: TermInfo) -> String {
        switch (period.yearFrom, period.yearTo) {
        case let (from?, to?): "\(from)–\(to)"
        case let (nil, to?): "do \(to)"
        case let (from?, nil): "od \(from)"
        case (nil, nil): ""
        }
    }

    /// Where a year falls on the axis, from 0 (its start) to 1 (its end):
    /// the pieces are of equal width, so within its piece.
    static func position(_ year: Int, on axis: [TermInfo]) -> CGFloat {
        guard !axis.isEmpty else { return 0 }
        for (index, piece) in axis.enumerated() {
            let to = piece.yearTo ?? Int.max
            guard year <= to else { continue }
            let end = piece.yearTo.map { $0 + 1 } ?? (year + 1)
            let start = piece.yearFrom ?? min(end - 100, year)
            if year < start, index == 0 { return 0 }
            let within = CGFloat(year - start) / CGFloat(max(end - start, 1))
            return (CGFloat(index) + min(max(within, 0), 1)) / CGFloat(axis.count)
        }
        return 1
    }

    /// Under each piece of the axis: where it starts.
    static func mark(_ period: TermInfo) -> String {
        period.yearFrom.map(String.init) ?? "śr."
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
        let to = axis[high].yearTo.map(shownEnd)
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
    var museums: [Museum] = []
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

    /// CI's screenshots of a group's panel.
    private static var launched: TermFacet? {
        switch LaunchRoute.screen {
        case "search-picker": .period
        case "search-colors", "search-tones": .color
        case "search-museums": .museum
        case "search-styles": .style
        default: nil
        }
    }

    private var facets: [TermFacet] {
        TermFacet.allCases.filter { facet in
            switch facet {
            case .color: !colors.isEmpty
            case .museum: !museums.isEmpty
            default: true
            }
        }
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
                    facet: open, tokens: $tokens, museums: museums, colors: colors, maxHeight: panelHeight,
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
        .onChange(of: focus.wrappedValue) { _, focused in
            if focused, open != nil { close() }
        }
        .task { await model.loadVocabulary() }
    }

    /// The side of the tap-outside layer: more than any screen, around the bar.
    private static let outside: CGFloat = 4000

    /// How the glass stretches: a little give at the end, like the system's.
    static let motion = Animation.bouncy(duration: 0.45, extraBounce: 0.05)

    /// The glass shrinks back into the button; then the panel goes.
    private func close() {
        guard open != nil else { return }
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
            // Kolor shows the picked colours' dots instead.
            HStack(spacing: 5) {
                let swatches = facet == .color ? picked.map(\.key) : []
                if !swatches.isEmpty {
                    HStack(spacing: 3) {
                        ForEach(Array(swatches.prefix(3)), id: \.self) { tag in
                            ColorTagDot(tag: tag, size: 8, stroke: .white.opacity(0.7), lineWidth: 1)
                        }
                    }
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
    var museums: [Museum] = []
    var colors: [String] = []
    var maxHeight: CGFloat = 460
    var close: () -> Void

    @State private var filter = ""
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
                            .fixedSize(horizontal: false, vertical: true)
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
        .task {
            await model.loadVocabulary(fresh: true)
            // Opened with moods alone: show them.
            if facet == .color, tokens.contains(where: { $0.kind == "color" }),
               !tokens.contains(where: { $0.kind == "color" && ColorTag.level(of: $0.key) != nil }) {
                colourCard = .tones
            }
        }
    }

    /// Under the group; the Kolor sheet says what it does by itself.
    private var footnote: String? {
        switch facet {
        case .museum: "Nic nie wybrane: pytam wszystkie muzea."
        case .color: nil
        default: "Wybierz dowolnie wiele: wystarczy, że dzieło pasuje do jednego z nich."
        }
    }

    @ViewBuilder private var content: some View {
        switch facet {
        case .technique, .style, .subject: terms
        case .period: PeriodPicker(tokens: $tokens)
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

    private var terms: some View {
        let all = model.vocabulary.filter { $0.kind == facet.rawValue }
        let wanted = fold(filter.trimmingCharacters(in: .whitespaces))
        let shown = wanted.isEmpty ? all : all.filter { term in
            fold(term.name).contains(wanted) || term.words.contains { fold($0).contains(wanted) }
        }
        // Older playlists' museum facet values: shown picked, a tap takes them off.
        let legacy = tokens.filter { facet.holds($0) && $0.kind.hasPrefix("legacy-") }
        return VStack(alignment: .leading, spacing: 12) {
            if facet.long {
                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass").foregroundStyle(Theme.inkSoft)
                    TextField(facet == .style ? "Szukaj stylu" : "Szukaj tematu", text: $filter)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .submitLabel(.done)
                    if !filter.isEmpty {
                        Button { filter = "" } label: {
                            Image(systemName: "xmark.circle.fill").foregroundStyle(Theme.inkSoft)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Wyczyść")
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 9)
                .background(Theme.card, in: RoundedRectangle(cornerRadius: 10))
                .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Theme.hairline))
            }
            FlowLayout(spacing: 8) {
                ForEach(legacy) { token in
                    Chip(title: token.name, selected: true) {
                        tokens.removeAll { $0.id == token.id }
                    }
                }
                ForEach(shown) { term in
                    Chip(title: term.name, selected: picked(term.kind, term.key)) {
                        toggle(term.kind, term.key, term.name)
                    }
                }
            }
            if shown.isEmpty, !wanted.isEmpty {
                Text("Nic takiego. Wpisz to w pole wyszukiwania: znajdę to jako słowo.")
                    .font(.footnote)
                    .foregroundStyle(Theme.inkSoft)
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
                Text(tones.isEmpty ? "Tonacja" : "Tonacja · \(tones.count)").tag(ColourCard.tones)
            }
            .pickerStyle(.segmented)
            switch colourCard {
            case .colours: colourGrid
            case .tones: toneGrid
            }
        }
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
        return LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 2), count: 6), spacing: 10) {
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
                                Label(choice.name.capitalized, systemImage: "checkmark")
                            } else {
                                Text(choice.name.capitalized)
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

    /// One of a pair: picking it lets go of the other; picked, a tap lets it go.
    private func tapTone(_ mood: String, partner: String) {
        let on = tonePicked(mood)
        let at = tokens.firstIndex { $0.kind == "color" && [mood, partner].contains(ColorTag.family($0.key)) && ColorTag.level(of: $0.key) == nil }
        tokens.removeAll { $0.kind == "color" && [mood, partner].contains(ColorTag.family($0.key)) && ColorTag.level(of: $0.key) == nil }
        guard !on else { return }
        let key = ColorTag.tone(mood)
        tokens.insert(SearchToken(kind: "color", key: key, name: ColorTag.name(key)), at: min(at ?? tokens.count, tokens.count))
    }

    /// Three pairs in a row, Ciemne–Jasne alone under them.
    private var toneGrid: some View {
        let pairs = ColorTag.tonePairs
        return VStack(spacing: 18) {
            HStack(spacing: 0) {
                ForEach(pairs.dropLast(), id: \.0) { pair in tonePair(pair) }
            }
            // Under the first column, two empty columns beside it.
            if let last = pairs.last {
                HStack(spacing: 0) {
                    tonePair(last)
                    ForEach(0..<2, id: \.self) { _ in Color.clear.frame(maxWidth: .infinity, maxHeight: 1) }
                }
            }
        }
        .padding(.top, 4)
    }

    private func tonePair(_ pair: (String, String)) -> some View {
        TonePair(left: pair.0, right: pair.1, picked: tonePicked) { mood in
            let partner = mood == pair.0 ? pair.1 : pair.0
            withAnimation(.snappy(duration: 0.25)) { tapTone(mood, partner: partner) }
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
                        return SearchToken.museum(token.key, name: museumName(token.key), out: out)
                    }
                }
            }
        )
    }

    private func museumName(_ key: String) -> String {
        museums.first { $0.key == key }?.name ?? Names.source(key)
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
            Text(out
                ? "Pytam wszystkie muzea oprócz zaznaczonych."
                : "Pytam tylko zaznaczone muzea.")
                .font(.footnote)
                .foregroundStyle(Theme.inkSoft)
            checkList(
                museums.map {
                    CheckRow(
                        kind: out ? SearchToken.museumOut : "museum", key: $0.key, name: $0.name,
                        icon: "building.columns"
                    )
                },
                out: out
            )
        }
    }

    private struct CheckRow: Identifiable {
        let kind: String
        let key: String
        let name: String
        let icon: String
        var id: String { key }
    }

    /// The rows to pick; `out`: picked ones are left out (a minus, the name
    /// struck through), not asked alone (a tick).
    private func checkList(_ rows: [CheckRow], out: Bool = false) -> some View {
        VStack(spacing: 0) {
            ForEach(rows) { row in
                let on = picked(row.kind, row.key)
                Button {
                    toggle(row.kind, row.key, SearchToken.museum(row.key, name: row.name, out: out).name)
                } label: {
                    HStack(spacing: 10) {
                        GroupMark(kind: row.kind, symbol: row.icon, side: 17)
                            .font(.subheadline)
                            .foregroundStyle(on && out ? Theme.inkSoft : Theme.ink)
                            .frame(width: 22)
                        Text(row.name)
                            .font(.body)
                            .strikethrough(on && out, color: Theme.inkSoft)
                            .foregroundStyle(on && out ? Theme.inkSoft : Theme.ink)
                        Spacer()
                        Image(systemName: on ? (out ? "minus.circle.fill" : "checkmark.circle.fill") : "circle")
                            .foregroundStyle(on ? (out ? Theme.vermilion : Theme.ink) : Theme.hairline)
                            .font(.title3)
                            .contentTransition(.symbolEffect(.replace))
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .sensoryFeedback(.selection, trigger: on)
                .accessibilityLabel(on && out ? "\(row.name), wykluczone" : row.name)
                .accessibilityAddTraits(on ? .isSelected : [])
                if row.id != rows.last?.id {
                    Divider().overlay(Theme.hairline).padding(.leading, 44)
                }
            }
        }
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Theme.hairline))
    }
}

/// The periods as a time line to tap or drag over, and the named ones
/// (Belle Époque, Międzywojnie) under it.
struct PeriodPicker: View {
    @Environment(AppModel.self) private var model
    @Binding var tokens: [SearchToken]

    @State private var width: CGFloat = 0
    /// While dragging: what was picked before, where the drag began and
    /// whether it picks or takes off.
    @State private var before: [SearchToken]?
    @State private var start: Int?
    @State private var adding = true

    private var periods: [TermInfo] { model.vocabulary.filter { $0.kind == "period" } }

    private func picked(_ key: String) -> Bool {
        tokens.contains { $0.kind == "period" && $0.key == key }
    }

    var body: some View {
        let split = PeriodAxis.split(periods)
        let axis = split.axis
        let named = split.named
        let vocabulary = Set(periods.map(\.key))
        // Spans of older playlists ("years:1880-1914").
        let other = tokens.filter { $0.kind == "period" && !vocabulary.contains($0.key) }
        let keys = tokens.filter { $0.kind == "period" }.map(\.key)
        let regions = PeriodAxis.regions.filter { region in named.contains { $0.region == region.id } }
        // An older server: one group with no name of its own.
        let loose = named.filter { period in !PeriodAxis.regions.contains { $0.id == period.region } }
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(summary(keys))
                        .font(.title3.weight(.semibold))
                        .contentTransition(.numericText())
                    if keys.count == 1, let period = named.first(where: { $0.key == keys[0] }) {
                        Text(PeriodAxis.years(period))
                            .font(.subheadline.monospacedDigit())
                            .foregroundStyle(Theme.inkSoft)
                    }
                }
                Text("Stuknij odcinek albo przeciągnij palcem po osi.")
                    .font(.footnote)
                    .foregroundStyle(Theme.inkSoft)
            }
            if !axis.isEmpty {
                line(axis, brackets: named.filter { picked($0.key) })
            }
            ForEach(regions) { region in
                namedGroup(region.title, named.filter { $0.region == region.id })
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

    /// One group of named periods, each with its years.
    private func namedGroup(_ title: String, _ periods: [TermInfo]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Eyebrow(title)
            FlowLayout(spacing: 6) {
                ForEach(periods) { period in
                    let on = picked(period.key)
                    Button {
                        toggle(period)
                    } label: {
                        VStack(alignment: .leading, spacing: 0) {
                            Text(period.name).font(.subheadline.weight(.medium))
                            Text(PeriodAxis.years(period))
                                .font(.caption2.monospacedDigit())
                                .foregroundStyle(on ? Theme.paper.opacity(0.75) : Theme.inkSoft)
                        }
                        .padding(.horizontal, 11)
                        .padding(.vertical, 5)
                        .foregroundStyle(on ? Theme.paper : Theme.ink)
                        .background(on ? Theme.ink : Theme.card, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .strokeBorder(on ? .clear : Theme.hairline)
                        )
                    }
                    .buttonStyle(.plain)
                    .sensoryFeedback(.selection, trigger: on)
                    .accessibilityLabel("\(period.name), \(PeriodAxis.years(period))")
                    .accessibilityAddTraits(on ? .isSelected : [])
                }
            }
        }
    }

    private func summary(_ keys: [String]) -> String {
        if keys.isEmpty { return "Dowolna epoka" }
        if keys.count > 1, let span = PeriodAxis.span(keys, periods: periods) { return span }
        let names = tokens.filter { $0.kind == "period" }.map(\.name)
        return names.joined(separator: ", ")
    }

    private func toggle(_ period: TermInfo) {
        if picked(period.key) {
            tokens.removeAll { $0.kind == "period" && $0.key == period.key }
        } else {
            tokens.append(SearchToken(kind: "period", key: period.key, name: period.name))
        }
    }

    /// The axis; under it a red bracket for each picked named period, over
    /// its years.
    private func line(_ axis: [TermInfo], brackets: [TermInfo]) -> some View {
        let gap: CGFloat = 3
        let piece = width > 0 ? (width - gap * CGFloat(axis.count - 1)) / CGFloat(axis.count) : 0
        return VStack(spacing: 5) {
            HStack(spacing: gap) {
                ForEach(axis) { period in
                    let on = picked(period.key)
                    RoundedRectangle(cornerRadius: 5)
                        .fill(on ? Theme.ink : Theme.card)
                        .overlay(RoundedRectangle(cornerRadius: 5).strokeBorder(on ? .clear : Theme.hairline))
                        .frame(height: 34)
                        .accessibilityElement()
                        .accessibilityLabel(period.name)
                        .accessibilityAddTraits(on ? [.isButton, .isSelected] : .isButton)
                        .accessibilityAction { toggle(period) }
                }
            }
            .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { width = $0 }
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { drag in
                        guard piece > 0 else { return }
                        let index = min(axis.count - 1, max(0, Int(drag.location.x / (piece + gap))))
                        if start == nil {
                            start = index
                            before = tokens
                            adding = !picked(axis[index].key)
                        }
                        guard let start, let before else { return }
                        let range = min(start, index) ... max(start, index)
                        var next = before
                        for period in axis[range] {
                            next.removeAll { $0.kind == "period" && $0.key == period.key }
                            if adding {
                                next.append(SearchToken(kind: "period", key: period.key, name: period.name))
                            }
                        }
                        if next != tokens { tokens = next }
                    }
                    .onEnded { _ in
                        start = nil
                        before = nil
                    }
            )
            .sensoryFeedback(.selection, trigger: tokens.filter { $0.kind == "period" }.count)
            HStack(spacing: gap) {
                ForEach(axis) { period in
                    Text(PeriodAxis.mark(period))
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(Theme.inkSoft)
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                        .frame(maxWidth: .infinity)
                }
            }
            .accessibilityHidden(true)
            if !brackets.isEmpty, width > 0 {
                ZStack(alignment: .topLeading) {
                    ForEach(brackets) { period in
                        let from = PeriodAxis.position(period.yearFrom ?? Int.min / 2, on: axis) * (width + gap)
                        let to = PeriodAxis.position(period.yearTo ?? Int.max / 2, on: axis) * (width + gap) - gap
                        Bracket()
                            .stroke(Theme.bad, style: StrokeStyle(lineWidth: 1.5, lineCap: .round, lineJoin: .round))
                            .frame(width: max(to - from, 4), height: 7)
                            .offset(x: min(from, width - 4))
                    }
                }
                .frame(width: width, height: 7, alignment: .topLeading)
                .accessibilityHidden(true)
            }
        }
    }
}

/// A bracket under the axis: ⎣___⎦.
private struct Bracket: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.minX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY))
        return path
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
                Text(level?.name ?? " ")
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
        .accessibilityValue(level?.name ?? "nie wybrany")
        .accessibilityHint("Stuknij, by było go więcej; po większości kolor się wyłącza.")
        .accessibilityAddTraits(level != nil ? .isSelected : [])
    }
}

/// A pair of the Tonacja card: two mood swatches sunk in a grey track like
/// a switch (the grey of the Kolorystyka/Tonacja picker); the picked one's
/// ring fits in the track, the other fades. Under it one name for the pair
/// ("Temperatura").
struct TonePair: View {
    /// Between the two dots.
    private static let gap: CGFloat = 14
    /// Track around the dots, enough for the picked ring.
    private static let inset: CGFloat = 7

    let left: String
    let right: String
    let picked: (String) -> Bool
    let action: (String) -> Void

    var body: some View {
        let moods = [left, right]
        VStack(spacing: 7) {
            HStack(spacing: Self.gap) {
                ForEach(moods, id: \.self) { mood in dot(mood, other: mood == left ? right : left) }
            }
            .padding(Self.inset)
            .background(
                Capsule().fill(
                    Theme.ink.opacity(0.07)
                        .shadow(.inner(color: .black.opacity(0.1), radius: 1.5, y: 1))
                )
            )
            // What the pair is about; the picked side is told by its ring
            // alone (Mateusz: no word for it).
            let side = moods.contains(where: picked)
            Text(ColorTag.toneTitle(left))
                .font(.caption2.weight(side ? .semibold : .regular))
                .foregroundStyle(side ? Theme.ink : Theme.inkSoft)
                .lineLimit(1)
                .fixedSize()
        }
        .frame(maxWidth: .infinity)
    }

    private func dot(_ mood: String, other: String) -> some View {
        let on = picked(mood)
        let off = picked(other)
        return Button { action(mood) } label: {
            ZStack {
                MoodFill(tag: mood)
                    .overlay(Circle().strokeBorder(Theme.ink.opacity(0.2)))
                if on {
                    Circle()
                        .stroke(ColorTag.ring(mood), lineWidth: 3.5)
                        .padding(-5)
                    Image(systemName: "checkmark")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(ColorTag.light(mood) ? Color(hex: 0x1D1B18) : .white)
                        .shadow(color: .black.opacity(ColorTag.light(mood) ? 0 : 0.5), radius: 1)
                }
            }
            .frame(width: 34, height: 34)
            .opacity(off ? 0.38 : 1)
            .contentShape(Circle().inset(by: -8))
        }
        .buttonStyle(.plain)
        .sensoryFeedback(.selection, trigger: on)
        .accessibilityLabel(ColorTag.name(mood))
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}
