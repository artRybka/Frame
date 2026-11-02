import SwiftUI

/// What the words typed in the system search field could mean: styles,
/// subjects, periods, techniques and artists with how many works the
/// catalogue has, and when the catalogue has little, what the museums have.
///
/// Every letter shows something at once, from what the app already knows:
/// what was found for the letters before and still fits (artists, terms and
/// the works' keywords such as „wielka fala”), the vocabulary's
/// terms that start like the words, and the words themselves. The server's
/// answer (with the counts) replaces it a moment later; the museums, slow,
/// come last.
@MainActor
@Observable
final class TermLookup {
    var text = ""
    private(set) var hits: [TermHit] = []
    /// Hits of the guess whose count the server has not told yet.
    private(set) var uncounted: Set<String> = []
    private(set) var hint: MuseumHint?
    private(set) var askingMuseums = false
    /// The server's answers by the words typed: a letter taken back shows
    /// its answer again without asking.
    @ObservationIgnored private var answers: [String: [TermHit]] = [:]

    var trimmed: String { text.trimmingCharacters(in: .whitespaces) }
    var typing: Bool { !trimmed.isEmpty }

    /// Below this many works in the catalogue the museums are asked too.
    private static let few = 6
    /// How many suggestions the guess shows (the server's answer has up to 11).
    private static let guessed = 10

    func lookUp(_ backend: any FrameBackend, vocabulary: [TermInfo] = []) async {
        let words = trimmed
        hint = nil
        guard !words.isEmpty else {
            hits = []
            uncounted = []
            return
        }
        if let known = answers[words] {
            hits = known
            uncounted = []
        } else {
            guess(words, vocabulary: vocabulary)
            try? await Task.sleep(for: .milliseconds(120))  // debounce typing
            guard !Task.isCancelled else { return }
            do {
                let found = try await backend.terms(words)
                if answers.count > 200 { answers.removeAll() }
                answers[words] = found
                hits = found
                uncounted = []
            } catch {
                // Cut short by the next letter, or no answer: the guess stays.
                return
            }
        }
        // Museums only when the catalogue knows little: they answer slowly.
        let best = hits.filter { $0.kind != "word" }.map(\.count).max() ?? 0
        guard words.count >= 3, best < Self.few else { return }
        try? await Task.sleep(for: .milliseconds(380))
        guard !Task.isCancelled else { return }
        askingMuseums = true
        defer { askingMuseums = false }
        hint = try? await backend.museumHint(words)
    }

    /// Shows at once what the app knows for `words`.
    private func guess(_ words: String, vocabulary: [TermInfo]) {
        let wanted = Self.fold(words)
        // Counts of artists and terms do not depend on the words typed.
        // (The last hit is the words typed before: never carried.)
        let before = hits.last?.kind == "word" ? hits.dropLast() : hits[...]
        var guess = before.filter { hit in
            Self.fold(hit.name).contains(wanted) || Self.fold(hit.detail).contains(wanted)
        }
        var fresh = uncounted.intersection(guess.map(\.id))
        for info in vocabulary where guess.count < Self.guessed && Self.startsLike(info, wanted) {
            guard !guess.contains(where: { $0.kind == info.kind && $0.key == info.key }) else { continue }
            let hit = TermHit(
                kind: info.kind, key: info.key, name: info.name,
                detail: info.words.prefix(3).map { $0.replacingOccurrences(of: "*", with: "") }
                    .joined(separator: ", ")
            )
            guess.append(hit)
            fresh.insert(hit.id)
        }
        let word = TermHit(kind: "word", key: words, name: words)
        guess.append(word)
        fresh.insert(word.id)
        hits = guess
        uncounted = fresh
    }

    /// The term's name, a word of it or one of its museum words starts like
    /// `wanted` (as the server suggests them).
    private static func startsLike(_ info: TermInfo, _ wanted: String) -> Bool {
        let name = fold(info.name)
        let names = [name] + name.split(separator: " ").map(String.init)
        let words = info.words.map { fold($0.replacingOccurrences(of: "*", with: "")) }
        return (names + words).contains { $0.hasPrefix(wanted) }
    }

    static func fold(_ text: String) -> String {
        text.replacingOccurrences(of: "ł", with: "l").replacingOccurrences(of: "Ł", with: "L")
            .folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil)
    }

    /// Puts a chip in and empties the field.
    func pick(_ token: SearchToken, into tokens: Binding<[SearchToken]>) {
        if !tokens.wrappedValue.contains(token) { tokens.wrappedValue.append(token) }
        text = ""
        hits = []
        uncounted = []
        hint = nil
    }

    /// Return: the typed words as they are, and whether only the museums
    /// know them.
    func typed() -> (token: SearchToken, fromMuseums: Bool)? {
        let words = trimmed
        guard !words.isEmpty else { return nil }
        let word = hits.first { $0.kind == "word" && !uncounted.contains($0.id) }
        let fromMuseums = word.map { $0.count == 0 } ?? false
        return (SearchToken(kind: "word", key: words, name: words), fromMuseums)
    }
}

extension View {
    /// The system search field (at the bottom on iOS 26) over these chips:
    /// artists and words in the field as its tokens, the groups' chips on the
    /// bar above it (`TermFacetBar`).
    func termSearch(
        _ lookup: TermLookup,
        tokens: Binding<[SearchToken]>,
        focused: FocusState<Bool>.Binding,
        prompt: String = "Artysta albo słowo",
        pickedFromMuseums: @escaping () -> Void = {}
    ) -> some View {
        modifier(TermSearch(
            lookup: lookup, tokens: tokens, focused: focused, prompt: prompt, pickedFromMuseums: pickedFromMuseums
        ))
    }
}

private struct TermSearch: ViewModifier {
    @Environment(AppModel.self) private var model
    @Bindable var lookup: TermLookup
    @Binding var tokens: [SearchToken]
    var focused: FocusState<Bool>.Binding
    let prompt: String
    let pickedFromMuseums: () -> Void
    /// The search is open: the system's round X stands next to the field.
    @State private var presented = false
    /// A group's panel is open over the field (`TermFacetBar` says so).
    @State private var panelOpen = false
    /// The search was opened for the X, not by a tap on the field: opening
    /// it focuses the field (also again a moment later), and that keyboard
    /// goes straight back down.
    @State private var quiet = false

    /// Something is picked in the groups (not only in the field).
    private var grouped: Bool { tokens.contains { !TermFacet.inField($0) } }

    /// The chips the field shows; the groups' ones are on the bar.
    private var fieldTokens: Binding<[SearchToken]> {
        Binding(
            get: { tokens.filter(TermFacet.inField) },
            set: { field in tokens = tokens.filter { !TermFacet.inField($0) } + field }
        )
    }

    func body(content: Content) -> some View {
        content
            .searchable(
                text: $lookup.text, tokens: fieldTokens, isPresented: $presented, prompt: Text(prompt)
            ) { token in
                Label(token.shownName, systemImage: token.icon)
            }
            // The X: off with the words and every group's choices too.
            .onChange(of: presented) { _, presented in
                if presented, quiet { putKeyboardAway() }
                guard !presented else { return }
                lookup.text = ""
                if !tokens.isEmpty { withAnimation(.snappy) { tokens = [] } }
            }
            // A group's choice alone opens the search too, so that its X is
            // there (once its panel has closed: the keyboard the opening
            // brings would close the panel); with nothing left anywhere it
            // closes again.
            .onChange(of: grouped, initial: true) { _, grouped in
                if grouped {
                    openForX()
                } else if presented, !focused.wrappedValue, lookup.text.isEmpty, tokens.isEmpty {
                    presented = false
                }
            }
            .onPreferenceChange(GroupPanelOpen.self) { open in panelOpen = open }
            .onChange(of: panelOpen) { _, open in
                if !open { openForX() }
            }
            .onChange(of: focused.wrappedValue) { _, focused in
                guard focused, quiet else { return }
                putKeyboardAway()
            }
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .searchFocused(focused)
            .onSubmit(of: .search) {
                guard let typed = lookup.typed() else { return }
                lookup.pick(typed.token, into: $tokens)
                if typed.fromMuseums { pickedFromMuseums() }
            }
            .task(id: lookup.trimmed) { await lookup.lookUp(model.backend, vocabulary: model.vocabulary) }
    }

    /// Opens the search for a group's choice, without the keyboard.
    private func openForX() {
        guard grouped, !presented, !panelOpen else { return }
        quiet = true
        // The field gets an empty keyboard while it opens: with the real
        // one coming up and going down twice the field flew up and back.
        SearchFieldKeyboard.empty(true)
        presented = true
        // Only the focus the opening brings (the system focuses the field
        // again a moment later): a later tap keeps its keyboard.
        Task {
            for _ in 0 ..< 6 {
                try? await Task.sleep(for: .milliseconds(150))
                if focused.wrappedValue { putKeyboardAway() }
            }
            SearchFieldKeyboard.empty(false)
            quiet = false
        }
    }

    /// The field's focus off, also where SwiftUI's focus alone doesn't
    /// take it (the system keeps the field it focused when opening).
    private func putKeyboardAway() {
        focused.wrappedValue = false
        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
    }
}

/// The system search fields' keyboard: none (an empty input view) while the
/// search opens for the X, the usual one again after.
@MainActor
private enum SearchFieldKeyboard {
    static func empty(_ on: Bool) {
        for case let scene as UIWindowScene in UIApplication.shared.connectedScenes {
            for window in scene.windows { visit(window, on: on) }
        }
    }

    private static func visit(_ view: UIView, on: Bool) {
        if let field = view as? UISearchTextField {
            field.inputView = on ? UIView(frame: .zero) : nil
            if field.isFirstResponder { field.reloadInputViews() }
        }
        for subview in view.subviews { visit(subview, on: on) }
    }
}

/// Whether a group's panel is open over the field: `TermFacetBar` tells the
/// search under it.
struct GroupPanelOpen: PreferenceKey {
    static let defaultValue = false
    static func reduce(value: inout Bool, nextValue: () -> Bool) { value = value || nextValue() }
}

extension View {
    /// While words are typed in the field: what they could mean, in a panel
    /// right over the field (where the groups are), the page as it is and
    /// standing still under it. (Put over the page's top, the suggestions
    /// pushed the scrolled results down and were off the screen themselves.)
    /// A tap on the page puts the keyboard away with the panel; the words
    /// stay in the field and come back with it.
    func termSuggestions(
        _ lookup: TermLookup,
        tokens: Binding<[SearchToken]>,
        focused: FocusState<Bool>.Binding,
        pickedFromMuseums: @escaping () -> Void = {}
    ) -> some View {
        modifier(SuggestionsPanel(
            lookup: lookup, tokens: tokens, focused: focused, pickedFromMuseums: pickedFromMuseums
        ))
    }
}

extension TermLookup {
    /// The suggestions' panel is over the field (the groups make way for it).
    func suggesting(_ focused: Bool) -> Bool { typing && focused }
}

private struct SuggestionsPanel: ViewModifier {
    let lookup: TermLookup
    @Binding var tokens: [SearchToken]
    var focused: FocusState<Bool>.Binding
    let pickedFromMuseums: () -> Void
    /// The suggestions' own height: the panel is as tall, up to the room
    /// over the field, and scrolls beyond it.
    @State private var listHeight: CGFloat = 44

    private var shown: Bool { lookup.suggesting(focused.wrappedValue) }

    /// As an open group's panel (PanelGlass, grown).
    private static let shape = RoundedRectangle(cornerRadius: 28, style: .continuous)

    func body(content: Content) -> some View {
        content.overlay {
            ZStack(alignment: .bottom) {
                if shown {
                    // The page stays as it is under the glass; a tap on it
                    // still puts the panel away.
                    Color.clear
                        .ignoresSafeArea()
                        .contentShape(Rectangle())
                        .onTapGesture(perform: putKeyboardAway)
                        .accessibilityHidden(true)
                        .transition(.opacity)
                    VStack(spacing: 0) {
                        Spacer(minLength: 12)
                        ScrollView {
                            TermSuggestions(lookup: lookup, tokens: $tokens, pickedFromMuseums: pickedFromMuseums)
                                // Off the glass's rounder corners.
                                .padding(.horizontal, 6)
                                .padding(.vertical, 6)
                                .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { listHeight = $0 }
                        }
                        .scrollBounceBehavior(.basedOnSize)
                        .frame(maxHeight: listHeight)
                        .clipShape(Self.shape)
                        // The same glass as an open group's panel.
                        .glassEffect(Glass.regular.tint(Theme.paper.opacity(0.55)), in: Self.shape)
                        // Before the spacer: all the room it needs.
                        .layoutPriority(1)
                    }
                    .padding(.horizontal, Theme.gutter)
                    // Where the groups' bar ends over the keyboard.
                    .padding(.bottom, TermFacetBar.overField)
                    .transition(.opacity.combined(with: .offset(y: 12)))
                }
            }
            .animation(.easeOut(duration: 0.18), value: shown)
        }
    }

    /// As in `TermSearch`: SwiftUI's focus alone doesn't always take the
    /// system field's keyboard.
    private func putKeyboardAway() {
        focused.wrappedValue = false
        UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
    }
}

/// While typing: what the words could mean, a tap puts it in as a chip.
/// Shown in the panel over the field (`termSuggestions`).
struct TermSuggestions: View {
    let lookup: TermLookup
    @Binding var tokens: [SearchToken]
    /// Called when a chip comes from the museums (the catalogue has nothing
    /// for it yet).
    var pickedFromMuseums: () -> Void = {}

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if lookup.hits.isEmpty, lookup.hint == nil, !lookup.askingMuseums {
                // Asking the catalogue (the words are still being typed).
                SearchWaiting(height: 72)
            }
            ForEach(lookup.hits) { hit in
                row(
                    mark: hit.token.kind, icon: hit.token.icon, title: hit.token.kind == "artist" ? Names.artist(hit.name) : hit.name, kind: kindName(of: hit),
                    detail: hit.detail, count: lookup.uncounted.contains(hit.id) ? nil : hit.count
                ) { pick(hit.token, fromMuseums: false) }
            }
            if lookup.askingMuseums {
                SearchWaiting(height: 72)
            } else if let hint = lookup.hint, hint.total > 0 {
                VStack(alignment: .leading, spacing: 0) {
                    Eyebrow("W muzeach: \(Names.works(hint.total))", color: Theme.vermilion)
                        .padding(.horizontal, 12)
                        .padding(.top, 12)
                    ForEach(hint.artists) { artist in
                        row(mark: "museum", icon: "building.columns", title: Names.artist(artist.name), kind: "Artysta z muzeów",
                            detail: "", count: nil) { pick(artist.token, fromMuseums: true) }
                    }
                    row(mark: "museum", icon: "building.columns", title: "„\(lookup.trimmed)” w muzeach", kind: "Słowo",
                        detail: "", count: nil) {
                        pick(SearchToken(kind: "word", key: lookup.trimmed, name: lookup.trimmed), fromMuseums: true)
                    }
                    if !hint.items.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 6) {
                                ForEach(hint.items.prefix(6)) { remote in
                                    ArtImage(ref: remote.thumb, fallback: remote.thumbFallback, placeholder: remote.item.summary.placeholderColor, maxPixel: 200)
                                        .frame(width: 56, height: 56)
                                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                                }
                            }
                            .padding(12)
                        }
                    }
                }
            } else if let hint = lookup.hint, hint.total == 0, lookup.hits.allSatisfy({ $0.count == 0 }) {
                Text("Nic nie znaleziono.")
                    .font(.subheadline)
                    .foregroundStyle(Theme.inkSoft)
                    .padding(12)
            }
        }
        .padding(.vertical, 4)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func row(
        mark tokenKind: String, icon: String, title: String, kind: String, detail: String, count: Int?,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: 10) {
                GroupMark(kind: tokenKind, symbol: icon, side: 17)
                    .font(.subheadline)
                    .foregroundStyle(Theme.ink)
                    .frame(width: 22)
                VStack(alignment: .leading, spacing: 1) {
                    Text(title).font(.body).foregroundStyle(Theme.ink).lineLimit(1)
                    Text(detail.isEmpty ? kind : "\(kind) · \(detail)")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .lineLimit(1)
                }
                Spacer()
                if let count {
                    Text(count == 0 ? "brak w bazie" : "\(count)")
                        .font(.footnote.monospacedDigit())
                        .foregroundStyle(Theme.inkSoft)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 9)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    /// A word the works were described with ("wielka fala"), apart from
    /// the words typed.
    private func kindName(of hit: TermHit) -> String {
        hit.kind == "word" && hit.key != lookup.trimmed ? "Słowo kluczowe" : hit.token.kindName
    }

    private func pick(_ token: SearchToken, fromMuseums: Bool) {
        lookup.pick(token, into: $tokens)
        if fromMuseums { pickedFromMuseums() }
    }
}

/// Above the results: what is searched for, in small capsules, so it shows
/// also while the groups are hidden.
struct TokenSummary: View {
    let tokens: [SearchToken]

    var body: some View {
        if !tokens.isEmpty {
            FlowLayout(spacing: 4) {
                ForEach(tokens) { token in
                    HStack(spacing: 4) {
                        if token.kind == "color" {
                            Circle()
                                .fill(ColorTag.color(token.key))
                                .frame(width: 8, height: 8)
                        }
                        Text(token.shownName).lineLimit(1)
                    }
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(Theme.inkSoft)
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .background(Theme.ink.opacity(0.06), in: Capsule())
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Szukasz: " + tokens.map(\.shownName).joined(separator: ", "))
        }
    }
}

extension View {
    /// The groups over the search field: they hide at the first scroll down
    /// through the results and come back a moment after the scrolling stops,
    /// when the field is tapped or nothing is asked any more, as `shown` says.
    func hidesOnScroll(_ shown: Binding<Bool>) -> some View {
        modifier(HidesOnScroll(shown: shown))
    }
}

private struct HidesOnScroll: ViewModifier {
    @Binding var shown: Bool
    /// The finger moves the content (or it glides on after it).
    @State private var moving = false
    @State private var showing: Task<Void, Never>?

    /// How long the results rest before the groups come back.
    private static let rest: Duration = .seconds(1.2)

    func body(content: Content) -> some View {
        content
            .onScrollPhaseChange { _, phase in
                moving = phase == .interacting || phase == .decelerating
                showing?.cancel()
                guard phase == .idle else { return }
                showing = Task { @MainActor in
                    try? await Task.sleep(for: Self.rest)
                    guard !Task.isCancelled, !shown else { return }
                    withAnimation(.snappy) { shown = true }
                }
            }
            .onScrollGeometryChange(for: CGFloat.self) { geometry in
                geometry.contentOffset.y + geometry.contentInsets.top
            } action: { old, new in
                guard moving, shown, new > 24, new > old + 1 else { return }
                withAnimation(.snappy) { shown = false }
            }
    }
}
