import SwiftUI

/// What the words typed in the system search field could mean: styles,
/// subjects, periods, techniques and artists with how many works the
/// catalogue has, and when the catalogue has little, what the museums have.
@MainActor
@Observable
final class TermLookup {
    var text = ""
    private(set) var hits: [TermHit] = []
    private(set) var hint: MuseumHint?
    private(set) var askingMuseums = false

    var trimmed: String { text.trimmingCharacters(in: .whitespaces) }
    var typing: Bool { !trimmed.isEmpty }

    /// Below this many works in the catalogue the museums are asked too.
    private static let few = 6

    func lookUp(_ backend: any FrameBackend) async {
        let words = trimmed
        hint = nil
        guard !words.isEmpty else {
            hits = []
            return
        }
        try? await Task.sleep(for: .milliseconds(220))  // debounce typing
        guard !Task.isCancelled else { return }
        do {
            hits = try await backend.terms(words)
        } catch is CancellationError {
            return
        } catch {
            hits = []
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

    /// Puts a chip in and empties the field.
    func pick(_ token: SearchToken, into tokens: Binding<[SearchToken]>) {
        if !tokens.wrappedValue.contains(token) { tokens.wrappedValue.append(token) }
        text = ""
        hits = []
        hint = nil
    }

    /// Return: the typed words as they are, and whether only the museums
    /// know them.
    func typed() -> (token: SearchToken, fromMuseums: Bool)? {
        let words = trimmed
        guard !words.isEmpty else { return nil }
        let fromMuseums = hits.first { $0.kind == "word" }.map { $0.count == 0 } ?? false
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

    /// The chips the field shows; the groups' ones are on the bar.
    private var fieldTokens: Binding<[SearchToken]> {
        Binding(
            get: { tokens.filter(TermFacet.inField) },
            set: { field in tokens = tokens.filter { !TermFacet.inField($0) } + field }
        )
    }

    func body(content: Content) -> some View {
        content
            .searchable(text: $lookup.text, tokens: fieldTokens, prompt: Text(prompt)) { token in
                Label(token.name, systemImage: token.icon)
            }
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .searchFocused(focused)
            .onSubmit(of: .search) {
                guard let typed = lookup.typed() else { return }
                lookup.pick(typed.token, into: $tokens)
                if typed.fromMuseums { pickedFromMuseums() }
            }
            .task(id: lookup.trimmed) { await lookup.lookUp(model.backend) }
    }
}

/// While typing: what the words could mean, a tap puts it in as a chip.
struct TermSuggestions: View {
    let lookup: TermLookup
    @Binding var tokens: [SearchToken]
    /// Called when a chip comes from the museums (the catalogue has nothing
    /// for it yet).
    var pickedFromMuseums: () -> Void = {}

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(lookup.hits) { hit in
                row(
                    icon: hit.token.icon, title: hit.name, kind: hit.token.kindName,
                    detail: hit.detail, count: hit.count
                ) { pick(hit.token, fromMuseums: false) }
            }
            if lookup.askingMuseums {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Pytam muzea…").font(.subheadline).foregroundStyle(Theme.inkSoft)
                }
                .padding(12)
            } else if let hint = lookup.hint, hint.total > 0 {
                VStack(alignment: .leading, spacing: 0) {
                    Eyebrow("W muzeach: \(Names.works(hint.total))", color: Theme.accent)
                        .padding(.horizontal, 12)
                        .padding(.top, 12)
                    ForEach(hint.artists) { artist in
                        row(icon: "building.columns", title: artist.name, kind: "Artysta z muzeów",
                            detail: "", count: nil) { pick(artist.token, fromMuseums: true) }
                    }
                    row(icon: "building.columns", title: "„\(lookup.trimmed)” w muzeach", kind: "Słowo",
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
                Text("Nic nie znaleziono ani w katalogu, ani w muzeach.")
                    .font(.subheadline)
                    .foregroundStyle(Theme.inkSoft)
                    .padding(12)
            }
        }
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Theme.hairline))
    }

    private func row(
        icon: String, title: String, kind: String, detail: String, count: Int?, action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Image(systemName: icon)
                    .font(.subheadline)
                    .foregroundStyle(Theme.accent)
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
                        Text(token.name).lineLimit(1)
                    }
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(Theme.inkSoft)
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .background(Theme.ink.opacity(0.06), in: Capsule())
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Szukasz: " + tokens.map(\.name).joined(separator: ", "))
        }
    }
}

extension View {
    /// The groups over the search field: they hide at the first scroll down
    /// through the results and come back only when the field is tapped (or
    /// nothing is asked any more), as `shown` says.
    func hidesOnScroll(_ shown: Binding<Bool>) -> some View {
        modifier(HidesOnScroll(shown: shown))
    }
}

private struct HidesOnScroll: ViewModifier {
    @Binding var shown: Bool
    /// The finger moves the content (or it glides on after it).
    @State private var moving = false

    func body(content: Content) -> some View {
        content
            .onScrollPhaseChange { _, phase in
                moving = phase == .interacting || phase == .decelerating
            }
            .onScrollGeometryChange(for: CGFloat.self) { geometry in
                geometry.contentOffset.y + geometry.contentInsets.top
            } action: { old, new in
                guard moving, shown, new > 24, new > old + 1 else { return }
                withAnimation(.snappy) { shown = false }
            }
    }
}
