import SwiftUI

/// One search box for artists, styles, subjects, periods, techniques and
/// plain words. What is picked becomes a chip; while typing it suggests what
/// the words could mean, with how many works the catalogue has, and when the
/// catalogue has little, what the museums have.
struct TermSearchField: View {
    @Environment(AppModel.self) private var model
    @Binding var tokens: [SearchToken]
    var prompt = "Artysta, styl, temat, epoka albo słowo"
    /// Called when a chip comes from the museums (the catalogue has nothing
    /// for it yet).
    var pickedFromMuseums: () -> Void = {}

    @State private var text = ""
    @State private var hits: [TermHit] = []
    @State private var hint: MuseumHint?
    @State private var askingMuseums = false
    @FocusState private var focused: Bool

    private var trimmed: String { text.trimmingCharacters(in: .whitespaces) }

    /// Below this many works in the catalogue the museums are asked too.
    private static let few = 6

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            field
            if !trimmed.isEmpty {
                suggestions
            }
        }
        .task(id: trimmed) { await lookUp() }
    }

    private var field: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Image(systemName: "magnifyingglass").foregroundStyle(Theme.inkSoft)
            FlowLayout(spacing: 6) {
                ForEach(tokens) { token in
                    Button {
                        tokens.removeAll { $0.id == token.id }
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: token.icon).font(.caption2.weight(.semibold))
                            Text(token.name).font(.subheadline.weight(.medium)).lineLimit(1)
                            Image(systemName: "xmark").font(.caption2.weight(.bold))
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .foregroundStyle(Theme.paper)
                        .background(Theme.accent, in: Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("\(token.kindName): \(token.name), usuń")
                }
                TextField(tokens.isEmpty ? prompt : "Dodaj…", text: $text)
                    .focused($focused)
                    .submitLabel(.search)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .frame(minWidth: 120)
                    .onSubmit { addWords() }
            }
            if !text.isEmpty || !tokens.isEmpty {
                Button {
                    if text.isEmpty { tokens = [] } else { text = "" }
                } label: {
                    Image(systemName: "xmark.circle.fill").foregroundStyle(Theme.inkSoft)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(text.isEmpty ? "Wyczyść wszystko" : "Wyczyść tekst")
            }
        }
        .padding(12)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(focused ? Theme.accent : Theme.hairline))
    }

    private var suggestions: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(hits) { hit in
                row(
                    icon: hit.token.icon, title: hit.name, kind: hit.token.kindName,
                    detail: hit.detail, count: hit.count
                ) { pick(hit.token, fromMuseums: false) }
            }
            if askingMuseums {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Pytam muzea…").font(.subheadline).foregroundStyle(Theme.inkSoft)
                }
                .padding(12)
            } else if let hint, hint.total > 0 {
                VStack(alignment: .leading, spacing: 0) {
                    Eyebrow("W muzeach: \(Names.works(hint.total))", color: Theme.accent)
                        .padding(.horizontal, 12)
                        .padding(.top, 12)
                    ForEach(hint.artists) { artist in
                        row(icon: "building.columns", title: artist.name, kind: "Artysta z muzeów",
                            detail: "", count: nil) { pick(artist.token, fromMuseums: true) }
                    }
                    row(icon: "building.columns", title: "„\(trimmed)” w muzeach", kind: "Słowo",
                        detail: "", count: nil) {
                        pick(SearchToken(kind: "word", key: trimmed, name: trimmed), fromMuseums: true)
                    }
                    if !hint.items.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 6) {
                                ForEach(hint.items.prefix(6)) { remote in
                                    ArtImage(ref: remote.thumb, placeholder: remote.item.summary.placeholderColor, maxPixel: 200)
                                        .frame(width: 56, height: 56)
                                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                                }
                            }
                            .padding(12)
                        }
                    }
                }
            } else if let hint, hint.total == 0, hits.allSatisfy({ $0.count == 0 }) {
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
        if !tokens.contains(token) { tokens.append(token) }
        text = ""
        hits = []
        hint = nil
        if fromMuseums { pickedFromMuseums() }
    }

    /// Return adds the typed words as they are.
    private func addWords() {
        guard !trimmed.isEmpty else { return }
        let fromMuseums = hits.first { $0.kind == "word" }.map { $0.count == 0 } ?? false
        pick(SearchToken(kind: "word", key: trimmed, name: trimmed), fromMuseums: fromMuseums)
    }

    private func lookUp() async {
        let words = trimmed
        hint = nil
        guard !words.isEmpty else {
            hits = []
            return
        }
        try? await Task.sleep(for: .milliseconds(220))  // debounce typing
        guard !Task.isCancelled else { return }
        do {
            hits = try await model.backend.terms(words)
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
        hint = try? await model.backend.museumHint(words)
    }
}
