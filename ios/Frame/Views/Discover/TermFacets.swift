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
        case .museum: token.kind == "museum"
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

    /// The button's words: "Styl", "Styl: Ukiyo-e", "Styl: Ukiyo-e +2";
    /// periods side by side on the axis read as one span ("Epoka: 1700–1900").
    func label(_ tokens: [SearchToken], periods: [TermInfo]) -> String {
        let picked = tokens.filter(holds)
        guard let first = picked.first else { return title }
        if self == .period, picked.count > 1, let span = PeriodAxis.span(picked.map(\.key), periods: periods) {
            return "\(title): \(span)"
        }
        let more = picked.count > 1 ? " +\(picked.count - 1)" : ""
        // "Akcent: czerwień" says what it is on its own.
        if self == .color, first.key.hasPrefix(ColorTag.accentPrefix) { return ColorTag.name(first.key) + more }
        let name = self == .color ? ColorTag.name(first.key) : first.name
        return "\(title): \(name)\(more)"
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

/// The groups over the search field, as thin glass capsules that wrap onto
/// a second row (four and two) rather than scroll sideways; a picked group
/// turns blue and says what it holds ("Styl: Ukiyo-e").
struct TermFacetBar: View {
    @Environment(AppModel.self) private var model
    @Binding var tokens: [SearchToken]
    var museums: [Museum] = []
    var colors: [String] = []
    /// Called as a group opens (to put the keyboard away).
    var opening: () -> Void = {}

    @State private var open: TermFacet? = TermFacetBar.launched

    /// CI's screenshots of a group's sheet.
    private static var launched: TermFacet? {
        switch LaunchRoute.screen {
        case "search-picker": .period
        case "search-colors": .color
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
        GlassEffectContainer(spacing: 6) {
            FlowLayout(spacing: 6) {
                ForEach(facets) { facet in button(facet) }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .sheet(item: $open) { facet in
            TermFacetSheet(facet: facet, tokens: $tokens, museums: museums, colors: colors)
        }
        .task { await model.loadVocabulary() }
    }

    private func button(_ facet: TermFacet) -> some View {
        let picked = tokens.filter(facet.holds)
        let on = !picked.isEmpty
        return Button {
            opening()
            open = facet
        } label: {
            HStack(spacing: 5) {
                if facet == .color {
                    let swatches = picked.map(\.key).filter { !ColorTag.moods.contains($0) }
                    ForEach(Array(swatches.prefix(3)), id: \.self) { tag in
                        Circle()
                            .fill(ColorTag.color(tag))
                            .frame(width: 9, height: 9)
                            .overlay(Circle().strokeBorder(.white.opacity(0.7), lineWidth: 1))
                    }
                }
                Text(facet.label(tokens, periods: periods))
                    .font(.subheadline.weight(on ? .semibold : .medium))
                    .lineLimit(1)
            }
            .padding(.horizontal, 13)
            .padding(.vertical, 6)
            .foregroundStyle(on ? Theme.paper : Theme.ink)
            .contentShape(Capsule())
            .glassEffect(on ? Glass.regular.tint(Theme.accent).interactive() : Glass.regular.interactive(), in: .capsule)
        }
        .buttonStyle(.plain)
        .sensoryFeedback(.selection, trigger: open == facet)
        .accessibilityLabel(facet.label(tokens, periods: periods))
        .accessibilityHint("Otwiera wybór: \(facet.title.lowercased())")
    }
}

/// One group's sheet, as tall as what it holds.
struct TermFacetSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AppModel.self) private var model
    let facet: TermFacet
    @Binding var tokens: [SearchToken]
    var museums: [Museum] = []
    var colors: [String] = []

    @State private var filter = ""
    @State private var accents = false

    /// Fixed heights that fit each group: a sheet's detents changed after it
    /// opens are not followed (CI screenshots went to the whole screen).
    /// Longer groups scroll and can be pulled up.
    private var detents: Set<PresentationDetent> {
        switch facet {
        case .technique: [.height(320)]
        case .period: [.large]
        case .color: [.height(610), .large]
        case .museum: [.height(CGFloat(max(museums.count, 1)) * 46 + 200), .large]
        case .style, .subject: [.fraction(0.62), .large]
        }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    content
                    Text(footnote)
                        .font(.footnote)
                        .foregroundStyle(Theme.inkSoft)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.horizontal, Theme.gutter)
                .padding(.top, 4)
                .padding(.bottom, 12)
            }
            .scrollBounceBehavior(.basedOnSize)
            .scrollDismissesKeyboard(.interactively)
            .background(Theme.paper)
            .navigationTitle(facet.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Wyczyść") { tokens.removeAll(where: facet.holds) }
                        .disabled(!tokens.contains(where: facet.holds))
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Gotowe") { dismiss() }
                }
            }
        }
        .presentationDetents(detents)
        .presentationDragIndicator(.visible)
        .presentationBackground(Theme.paper)
        .task {
            await model.loadVocabulary()
            // Opened on an accent: show the accents.
            if facet == .color, tokens.contains(where: { $0.kind == "color" && $0.key.hasPrefix(ColorTag.accentPrefix) }),
               !tokens.contains(where: { $0.kind == "color" && ColorTag.families.contains($0.key) }) {
                accents = true
            }
        }
    }

    private var footnote: String {
        switch facet {
        case .museum: "Bez wybranych pytam wszystkie muzea. Wybrane: tylko je."
        case .color: "Wśród kolorów i nastrojów wystarczy jeden z wybranych, wśród akcentów też. Kolor i akcent muszą pasować razem: Błękit z akcentem czerwieni to niebieskie obrazy z czymś czerwonym."
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

    private var palette: some View {
        let families = accents ? ColorTag.accentFamilies : ColorTag.families.filter(colors.contains)
        let moods = colors.filter { !ColorTag.families.contains($0) }
        let pickedAccents = tokens.filter { $0.kind == "color" && $0.key.hasPrefix(ColorTag.accentPrefix) }.count
        let pickedMain = tokens.filter { $0.kind == "color" && ColorTag.families.contains($0.key) }.count
        return VStack(alignment: .leading, spacing: 14) {
            Picker("Jak", selection: $accents) {
                Text(pickedMain > 0 ? "Dominuje · \(pickedMain)" : "Dominuje").tag(false)
                Text(pickedAccents > 0 ? "Tylko akcent · \(pickedAccents)" : "Tylko akcent").tag(true)
            }
            .pickerStyle(.segmented)
            Text(accents
                ? "Kolor jako mały fragment obrazu, np. czerwony płaszcz na szarym tle."
                : "Kolor, którego w obrazie jest dużo.")
                .font(.footnote)
                .foregroundStyle(Theme.inkSoft)
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 4), count: 6), spacing: 12) {
                ForEach(families, id: \.self) { family in
                    let tag = accents ? ColorTag.accent(family) : family
                    swatch(tag: tag, family: family)
                }
            }
            if !moods.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Eyebrow("Nastrój")
                    FlowLayout(spacing: 8) {
                        ForEach(moods, id: \.self) { mood in
                            Chip(title: ColorTag.name(mood), swatch: ColorTag.color(mood), selected: picked("color", mood)) {
                                toggle("color", mood, ColorTag.name(mood))
                            }
                        }
                    }
                }
            }
        }
    }

    private func swatch(tag: String, family: String) -> some View {
        let on = picked("color", tag)
        return Button {
            toggle("color", tag, ColorTag.name(tag))
        } label: {
            VStack(spacing: 4) {
                Circle()
                    .fill(ColorTag.color(family))
                    .frame(width: 34, height: 34)
                    .overlay(Circle().strokeBorder(Theme.ink.opacity(0.25)))
                    .padding(3)
                    .overlay(Circle().strokeBorder(on ? Theme.ink : .clear, lineWidth: 2))
                    .overlay {
                        if on {
                            Image(systemName: "checkmark")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(["white", "yellow", "pink"].contains(family) ? Color(hex: 0x1D1B18) : .white)
                        }
                    }
                Text(ColorTag.name(family))
                    .font(.caption2.weight(on ? .semibold : .regular))
                    .foregroundStyle(on ? Theme.ink : Theme.inkSoft)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .sensoryFeedback(.selection, trigger: on)
        .accessibilityLabel(ColorTag.name(tag))
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    // MARK: Museums

    private var museumList: some View {
        checkList(museums.map { CheckRow(kind: "museum", key: $0.key, name: $0.name, icon: "building.columns") })
    }

    private struct CheckRow: Identifiable {
        let kind: String
        let key: String
        let name: String
        let icon: String
        var id: String { key }
    }

    private func checkList(_ rows: [CheckRow]) -> some View {
        VStack(spacing: 0) {
            ForEach(rows) { row in
                let on = picked(row.kind, row.key)
                Button {
                    toggle(row.kind, row.key, row.name)
                } label: {
                    HStack(spacing: 10) {
                        Image(systemName: row.icon)
                            .font(.subheadline)
                            .foregroundStyle(Theme.accent)
                            .frame(width: 22)
                        Text(row.name).font(.body).foregroundStyle(Theme.ink)
                        Spacer()
                        Image(systemName: on ? "checkmark.circle.fill" : "circle")
                            .foregroundStyle(on ? Theme.accent : Theme.hairline)
                            .font(.title3)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .sensoryFeedback(.selection, trigger: on)
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
