import SwiftUI

/// One search box for artists, styles, subjects, periods, techniques and
/// plain words. What is picked becomes a chip; while typing it suggests what
/// the words could mean, with how many works the catalogue has, and when the
/// catalogue has little, what the museums have.
struct TermSearchField: View {
    @Environment(AppModel.self) private var model
    @Binding var tokens: [SearchToken]
    var prompt = "Artysta, styl, temat, epoka albo słowo"
    /// Museums and colours the "+" offers too (Discover's search).
    var museums: [Museum] = []
    var colors: [String] = []
    /// Whether there are words typed in the field.
    var typing: Binding<Bool> = .constant(false)
    /// Called when a chip comes from the museums (the catalogue has nothing
    /// for it yet).
    var pickedFromMuseums: () -> Void = {}

    @State private var text = ""
    @State private var hits: [TermHit] = []
    @State private var hint: MuseumHint?
    @State private var askingMuseums = false
    @State private var picking = LaunchRoute.screen == "search-picker"
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
        .onChange(of: trimmed.isEmpty, initial: true) { _, empty in typing.wrappedValue = !empty }
        .sheet(isPresented: $picking) {
            TermPickerSheet(tokens: $tokens, museums: museums, colors: colors)
        }
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
                            if token.kind == "color" {
                                Circle()
                                    .fill(ColorTag.color(token.key))
                                    .frame(width: 10, height: 10)
                                    .overlay(Circle().strokeBorder(Theme.paper.opacity(0.7), lineWidth: 1))
                            } else {
                                Image(systemName: token.icon).font(.caption2.weight(.semibold))
                            }
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
            Button {
                picking = true
            } label: {
                Image(systemName: "plus.circle.fill")
                    .font(.title3)
                    .foregroundStyle(Theme.accent)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(
                museums.isEmpty ? "Dodaj styl, temat, epokę albo technikę" : "Dodaj muzeum, kolor, styl, temat, epokę albo technikę"
            )
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
                                    ArtImage(ref: remote.thumb, fallback: remote.thumbFallback, placeholder: remote.item.summary.placeholderColor, maxPixel: 200)
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

/// Styles, subjects, periods and techniques to tap, in sections (and
/// museums and colours when given); what is picked shows selected and a
/// second tap takes it off.
struct TermBrowser: View {
    @Environment(AppModel.self) private var model
    @Binding var tokens: [SearchToken]
    var museums: [Museum] = []
    var colors: [String] = []

    private func terms(_ kind: String) -> [TermInfo] { model.vocabulary.filter { $0.kind == kind } }

    private func picked(_ term: TermInfo) -> Bool { tokens.contains { $0.key == term.key } }

    private func toggle(_ term: TermInfo) {
        if picked(term) {
            tokens.removeAll { $0.key == term.key }
        } else {
            tokens.append(SearchToken(kind: term.kind, key: term.key, name: term.name))
        }
    }

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

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            if !museums.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Eyebrow("Muzea")
                    FlowLayout(spacing: 8) {
                        ForEach(museums) { museum in
                            Chip(title: museum.name, systemImage: "building.columns", selected: picked("museum", museum.key)) {
                                toggle("museum", museum.key, museum.name)
                            }
                        }
                    }
                }
            }
            section("Style i kierunki", terms("style"))
            section("Tematy", terms("subject"))
            periods
            section("Techniki", terms("technique"))
            if !colors.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Eyebrow("Kolory")
                    FlowLayout(spacing: 8) {
                        ForEach(colors, id: \.self) { tag in
                            Chip(title: ColorTag.name(tag), swatch: ColorTag.color(tag), selected: picked("color", tag)) {
                                toggle("color", tag, ColorTag.name(tag))
                            }
                        }
                    }
                }
            }
        }
        .task { await model.loadVocabulary() }
    }

    private func section(_ title: String, _ terms: [TermInfo]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Eyebrow(title)
            FlowLayout(spacing: 8) {
                ForEach(terms) { term in
                    Chip(title: term.name, selected: picked(term)) { toggle(term) }
                }
            }
        }
    }

    private var periods: some View {
        VStack(alignment: .leading, spacing: 10) {
            Eyebrow("Epoki")
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 0) {
                    ForEach(terms("period")) { period in
                        let on = picked(period)
                        Button { toggle(period) } label: {
                            VStack(spacing: 2) {
                                Text(period.name).font(.subheadline.weight(.semibold))
                                if let from = period.yearFrom ?? period.yearTo {
                                    Text(period.yearFrom == nil ? "do \(from)" : "od \(from)")
                                        .font(.caption2.monospacedDigit())
                                        .foregroundStyle(on ? Theme.paper.opacity(0.8) : Theme.inkSoft)
                                }
                            }
                            .foregroundStyle(on ? Theme.paper : Theme.ink)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 9)
                            .background(on ? Theme.ink : .clear)
                            .overlay(alignment: .leading) { Rectangle().fill(Theme.hairline).frame(width: 1) }
                        }
                        .buttonStyle(.plain)
                        .accessibilityAddTraits(on ? .isSelected : [])
                    }
                }
                .background(Theme.card, in: RoundedRectangle(cornerRadius: 10))
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Theme.hairline))
            }
            .scrollClipDisabled()
        }
    }
}

/// The browser in a sheet, opened from the search field's "+" to add a
/// subject to a style, a period to both, and so on.
struct TermPickerSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Binding var tokens: [SearchToken]
    var museums: [Museum] = []
    var colors: [String] = []

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text(museums.isEmpty
                        ? "Wybierz dowolnie wiele. Te same rodzaje to alternatywy, różne muszą pasować razem: np. Impresjonizm + Morze + 1850–1900."
                        : "Wybierz dowolnie wiele. Te same rodzaje to alternatywy, różne muszą pasować razem: np. dwa muzea + Impresjonizm + Morze + Błękit.")
                        .font(.footnote)
                        .foregroundStyle(Theme.inkSoft)
                        .fixedSize(horizontal: false, vertical: true)
                    TermBrowser(tokens: $tokens, museums: museums, colors: colors)
                }
                .padding(.horizontal, Theme.gutter)
                .padding(.bottom, 32)
            }
            .background(Theme.paper)
            .navigationTitle("Dodaj do wyszukiwania")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Gotowe") { dismiss() }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }
}
