import SwiftUI

/// Discover's search: words, artists, styles, subjects, periods and
/// techniques as chips, over the catalogue (at once, with colours) and the
/// museums (as they answer). With nothing asked yet it offers styles,
/// subjects, periods and museums to browse by.
struct MuseumSearchView: View {
    @Environment(AppModel.self) private var model
    @State private var museums: [Museum] = []
    /// What is asked for, as playlist rules (a playlist can be made from it).
    @State private var rules = PlaylistRules()
    /// A museum's key, or "all".
    @State private var source = "all"
    @State private var catalogue: ItemPage?
    @State private var results: [RemoteItem] = []
    @State private var total = 0
    @State private var failed: [String] = []
    @State private var page = 1
    @State private var searching = false
    @State private var loadingMore = false
    @State private var adding: Set<String> = []
    @State private var editing: Playlist?

    private var tokens: Binding<[SearchToken]> {
        Binding(
            get: { rules.tokens(names: model.termNames) },
            set: { rules.setTokens($0) }
        )
    }

    private var asked: Bool { !rules.isEmpty || source != "all" }

    /// Museum works the catalogue doesn't hold already.
    private var fromMuseums: [RemoteItem] {
        let known = Set(catalogue?.items.map(\.id) ?? [])
        return results.filter { !known.contains($0.id) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            TermSearchField(tokens: tokens)
            if asked {
                filters
                resultsView
            } else {
                browse
            }
        }
        .task {
            await model.loadVocabulary()
            if museums.isEmpty { museums = (try? await model.backend.museums()) ?? [] }
            if LaunchRoute.screen == "museums", rules.isEmpty {
                rules.artists = ["Utagawa Hiroshige"]
            }
        }
        .task(id: SearchKey(rules: rules, source: source)) { await search() }
        .sheet(item: $editing) { playlist in
            PlaylistEditorView(playlist: playlist)
        }
    }

    // MARK: Browsing

    private func terms(_ kind: String) -> [TermInfo] { model.vocabulary.filter { $0.kind == kind } }

    private var browse: some View {
        VStack(alignment: .leading, spacing: 22) {
            TermBrowser(tokens: tokens)
            if !museums.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Eyebrow("Muzea")
                    FlowLayout(spacing: 8) {
                        ForEach(museums) { museum in
                            Chip(title: museum.name, systemImage: "building.columns") { source = museum.key }
                        }
                    }
                }
            }
            privateUseToggle
        }
    }

    private var privateUseToggle: some View {
        Toggle(isOn: privateUse) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Użytek prywatny")
                Text(
                    privateUse.wrappedValue
                        ? "Z Wikimedia Commons także dzieła na wolnych licencjach (np. CC BY-SA), z podanym autorem. Muzea nadal dają tylko domenę publiczną."
                        : "Tylko dzieła w domenie publicznej (CC0). Opisy w oryginale, po angielsku."
                )
                .font(.footnote)
                .foregroundStyle(Theme.inkSoft)
            }
        }
        .tint(Theme.accent)
        .disabled(model.settings == nil)
    }

    /// Saved with the frame settings, so imports on the server follow it.
    private var privateUse: Binding<Bool> {
        Binding(
            get: { model.settings?.privateUse ?? false },
            set: { value in
                guard var settings = model.settings else { return }
                settings.privateUse = value
                Task { await model.saveSettings(settings) }
            }
        )
    }

    // MARK: Filters and results

    private var filters: some View {
        VStack(alignment: .leading, spacing: 10) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(terms("technique")) { technique in
                        let on = rules.terms.contains(technique.key)
                        Chip(title: technique.name, selected: on) {
                            if on { rules.terms.removeAll { $0 == technique.key } } else { rules.terms.append(technique.key) }
                        }
                    }
                    Menu {
                        Picker("Muzeum", selection: $source) {
                            Text("Wszystkie muzea").tag("all")
                            ForEach(museums) { Text($0.name).tag($0.key) }
                        }
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: "building.columns").font(.caption.weight(.semibold))
                            Text(source == "all" ? "Muzea" : Names.source(source)).font(.subheadline.weight(.medium))
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 7)
                        .foregroundStyle(source == "all" ? Theme.ink : Theme.paper)
                        .background(source == "all" ? Theme.card : Theme.ink, in: Capsule())
                        .overlay(Capsule().strokeBorder(source == "all" ? Theme.hairline : .clear))
                    }
                }
                .padding(.vertical, 2)
            }
            .scrollClipDisabled()
            ColorFilterRow(selected: $rules.colors, available: model.facets.colors.map(\.value))
        }
    }

    private var resultsView: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                Text(summary)
                    .font(.serif(17, weight: .medium))
                    .foregroundStyle(Theme.ink)
                Spacer()
                if searching { ProgressView().controlSize(.small) }
            }
            if !rules.colors.isEmpty {
                Text("Kolory są znane tylko w katalogu, więc wyniki z muzeów ich nie uwzględniają.")
                    .font(.footnote)
                    .foregroundStyle(Theme.inkSoft)
            }
            if !rules.isEmpty {
                Button {
                    editing = Playlist(
                        name: rules.suggestedName(names: model.termNames), kind: .smart, rules: rules
                    )
                } label: {
                    Label("Utwórz playlistę z tego wyszukiwania", systemImage: "text.badge.plus")
                }
                .buttonStyle(PrimaryButtonStyle())
            }
            if let catalogue, !catalogue.items.isEmpty {
                Eyebrow("W katalogu · \(Names.works(catalogue.total))")
                MasonryGrid(items: catalogue.items) { item in
                    NavigationLink(value: item.id) {
                        ArtCard(item: item)
                    }
                    .buttonStyle(.plain)
                }
            }
            if !fromMuseums.isEmpty || searching {
                HStack {
                    Eyebrow("Z muzeów" + (total > 0 ? " · \(Names.works(total))" : ""))
                    Spacer()
                    if searching {
                        Text("doczytuję…").font(.caption).foregroundStyle(Theme.inkSoft)
                    }
                }
            }
            if !failed.isEmpty {
                Text("Nie odpowiedziało: " + failed.map(Names.source).joined(separator: ", "))
                    .font(.footnote)
                    .foregroundStyle(Theme.inkSoft)
            }
            MasonryGrid(items: fromMuseums.map(\.item.summary)) { summary in
                let remote = fromMuseums.first { $0.id == summary.id }
                VStack(alignment: .leading, spacing: 8) {
                    NavigationLink(value: summary.id) {
                        ArtCard(item: summary, ref: remote?.thumb)
                    }
                    .buttonStyle(.plain)
                    addButton(remote)
                }
            }
            if !searching, catalogue?.items.isEmpty ?? true, fromMuseums.isEmpty {
                EmptyStateView(
                    title: "Nic tu nie ma",
                    message: "Usuń któryś z chipów albo poszukaj innymi słowami.",
                    systemImage: "magnifyingglass"
                )
            }
            if !searching, results.count < total, !results.isEmpty {
                Button {
                    Task { await loadMore() }
                } label: {
                    HStack(spacing: 8) {
                        if loadingMore { ProgressView().controlSize(.small) }
                        Text("Więcej z muzeów")
                    }
                    .font(.subheadline.weight(.semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                    .background(Theme.card, in: RoundedRectangle(cornerRadius: 12))
                    .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Theme.hairline))
                }
                .disabled(loadingMore)
            }
        }
    }

    private var summary: String {
        let inCatalogue = catalogue?.total ?? 0
        if searching && inCatalogue == 0 { return "Szukam…" }
        return Names.works(inCatalogue + fromMuseums.count) + (results.count < total ? "+" : "")
    }

    @ViewBuilder
    private func addButton(_ remote: RemoteItem?) -> some View {
        if let remote {
            if remote.inLibrary {
                Label("Zapisane", systemImage: "checkmark")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Theme.good)
            } else {
                Button {
                    Task { await add(remote) }
                } label: {
                    HStack(spacing: 6) {
                        if adding.contains(remote.id) {
                            ProgressView().controlSize(.mini)
                        } else {
                            Image(systemName: "plus")
                        }
                        Text("Zapisz")
                    }
                    .font(.caption.weight(.semibold))
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(Theme.accent.opacity(0.12), in: Capsule())
                }
                .disabled(adding.contains(remote.id))
            }
        }
    }

    // MARK: Loading

    /// What a search depends on, to start it again when it changes.
    private struct SearchKey: Hashable {
        let rules: PlaylistRules
        let source: String
    }

    private func search() async {
        guard asked else {
            catalogue = nil
            results = []
            total = 0
            return
        }
        try? await Task.sleep(for: .milliseconds(150))
        guard !Task.isCancelled else { return }
        searching = true
        defer { searching = false }
        var query = LibraryQuery(rules: rules)
        if source != "all" { query.sources = [source] }
        do {
            catalogue = try await model.backend.items(query)
        } catch is CancellationError {
            return
        } catch {
            model.show(error)
        }
        results = []
        total = 0
        failed = []
        page = 1
        do {
            let found = try await model.backend.searchMuseums(rules, source: source, page: 1)
            guard !Task.isCancelled else { return }
            results = found.items
            total = found.total
            failed = found.failed ?? []
        } catch is CancellationError {
        } catch {
            if !Task.isCancelled { failed = [source] }
        }
    }

    private func loadMore() async {
        loadingMore = true
        defer { loadingMore = false }
        do {
            let found = try await model.backend.searchMuseums(rules, source: source, page: page + 1)
            let known = Set(results.map(\.id))
            results += found.items.filter { !known.contains($0.id) }
            page += 1
            // Some sources only learn the total as they go; stop when a page is empty.
            total = found.items.isEmpty ? results.count : max(found.total, results.count)
        } catch {
            model.show(error)
        }
    }

    private func add(_ remote: RemoteItem) async {
        adding.insert(remote.id)
        defer { adding.remove(remote.id) }
        do {
            _ = try await model.backend.importArtwork(source: remote.item.source, sourceID: remote.item.sourceId)
            if let index = results.firstIndex(where: { $0.id == remote.id }) {
                results[index].inLibrary = true
            }
            model.toast = "Zapisano"
            await model.refreshFacets()
        } catch {
            model.show(error)
        }
    }
}

/// Wrapping row of chips.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if x > 0 && x + size.width > width {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return CGSize(width: width.isFinite ? width : x, height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX
        var y = bounds.minY
        var rowHeight: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if x > bounds.minX && x + size.width > bounds.maxX {
                x = bounds.minX
                y += rowHeight + spacing
                rowHeight = 0
            }
            view.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}
