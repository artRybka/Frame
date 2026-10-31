import SwiftUI

/// The Szukaj tab's search: words, artists, styles, subjects, periods,
/// techniques, colours and museums as chips, over the catalogue (at once)
/// and the museums (each as it answers). Artists and words are the system
/// field's tokens; museums, colours, styles, subjects, periods and techniques
/// come from the glass groups over the field, which hide as the results
/// scroll and come back when the field is tapped. With nothing asked yet
/// the icon's squares play, and at the end of the results they ask the
/// museums for more when pulled. Coming back from a work finds the results
/// as they were. The heart on a tile puts the work in Ulubione (a museum's
/// work joins the library with it).
struct MuseumSearchView: View {
    @Environment(AppModel.self) private var model
    @State private var museums: [Museum] = []
    /// What is asked for, as playlist rules (a playlist can be made from it).
    @State private var rules = PlaylistRules()
    /// Keys of the museums to ask; none means all of them.
    @State private var sources: [String] = []
    @State private var catalogue: ItemPage?
    @State private var results: [RemoteItem] = []
    /// How many works each museum has for the search.
    @State private var totals: [String: Int] = [:]
    /// The page to ask each museum for more; museums with no more are left out.
    @State private var next: [String: Int] = [:]
    @State private var failed: [String] = []
    /// The catalogue is being asked.
    @State private var searching = false
    /// The museums are still answering.
    @State private var asking = false
    @State private var loadingMore = false
    /// What the results are for, so that coming back from a work doesn't
    /// search again; the search goes on while a work is open.
    @State private var searched: SearchKey?
    @State private var loader: Task<Void, Never>?
    /// Works whose heart the server is still taking.
    @State private var liking: Set<String> = []
    @State private var editing: Playlist?
    /// Whether the playlist made from the search fetches the museums' works.
    @State private var fetchForPlaylist = false
    @State private var lookup = TermLookup()
    @FocusState private var fieldFocused: Bool
    /// The groups over the field: hidden while scrolling the results.
    @State private var groupsShown = true
    /// Where the squares start, from the top of the scrolled content.
    @State private var squaresTop: CGFloat = 0

    /// The rules' chips, then the colours' and the museums'.
    private var tokens: Binding<[SearchToken]> {
        Binding(
            get: {
                var tokens = rules.tokens(names: model.termNames)
                tokens += rules.colors.map { SearchToken(kind: "color", key: $0, name: ColorTag.name($0)) }
                tokens += sources.map { SearchToken(kind: "museum", key: $0, name: museumName($0)) }
                return tokens
            },
            set: { tokens in
                rules.setTokens(tokens)
                rules.colors = tokens.filter { $0.kind == "color" }.map(\.key)
                sources = tokens.filter { $0.kind == "museum" }.map(\.key)
            }
        )
    }

    private func museumName(_ key: String) -> String {
        museums.first { $0.key == key }?.name ?? Names.source(key)
    }

    private var asked: Bool { !rules.isEmpty || !sources.isEmpty }

    private var searchKey: SearchKey { SearchKey(rules: rules, sources: sources) }

    /// What the museums have for the search, as far as they said.
    private var total: Int { totals.values.reduce(0, +) }

    /// Museum works the catalogue doesn't hold already, in any copy.
    private var fromMuseums: [RemoteItem] {
        let known = Set(catalogue?.items.map(\.id) ?? [])
        return results.filter { !known.contains($0.id) && !known.contains($0.twin ?? "") }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if lookup.typing {
                    TermSuggestions(lookup: lookup, tokens: tokens)
                }
                if asked {
                    resultsView
                } else if !lookup.typing {
                    idle
                }
            }
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, SearchView.bottomPadding)
            .coordinateSpace(.named(SearchView.content))
        }
        .scrollDismissesKeyboard(.immediately)
        .hidesOnScroll($groupsShown)
        .paperPage()
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if groupsShown {
                TermFacetBar(
                    tokens: tokens, museums: museums, colors: ColorTag.families + ColorTag.moods,
                    opening: { fieldFocused = false }
                )
                .padding(.horizontal, Theme.gutter)
                .padding(.bottom, 8)
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .termSearch(lookup, tokens: tokens, focused: $fieldFocused)
        // Tapping the field brings the groups back, as does asking nothing.
        .onChange(of: fieldFocused) { _, focused in
            if focused, !groupsShown { withAnimation(.snappy) { groupsShown = true } }
        }
        .onChange(of: asked) { _, asked in
            if !asked, !groupsShown { withAnimation(.snappy) { groupsShown = true } }
        }
        .task {
            await model.loadVocabulary()
            if museums.isEmpty { museums = (try? await model.backend.museums()) ?? [] }
            if LaunchRoute.screen == "museums", rules.isEmpty {
                rules.artists = ["Utagawa Hiroshige"]
            }
        }
        .task(id: searchKey) {
            let key = searchKey
            guard key != searched else { return }
            try? await Task.sleep(for: .milliseconds(150))
            guard !Task.isCancelled else { return }
            searched = key
            loader?.cancel()
            // Not tied to this view's task: it goes on while a work is open.
            loader = Task { await search(key) }
        }
        .onChange(of: model.artistSearch, initial: true) { _, artist in
            guard let artist else { return }
            var asked = PlaylistRules()
            asked.artists = [artist]
            rules = asked
            sources = []
            // Later, so the tab and the search's stack see the request first.
            Task { model.artistSearch = nil }
        }
        .onChange(of: model.hearts) { _, hearts in
            // Liked or unliked on the work's card meanwhile.
            for (id, favorite) in hearts where !liking.contains(id) {
                mark(id, favorite: favorite)
            }
        }
        .sheet(item: $editing) { playlist in
            PlaylistEditorView(playlist: playlist, fetchFromMuseums: fetchForPlaylist)
        }
    }

    // MARK: Nothing asked yet

    private var idle: some View {
        VStack(spacing: 4) {
            // Down to the tab bar, so the squares have room below their row
            // (in the middle of the screen) to fall to the bottom.
            SquaresAnimation()
                .frame(maxWidth: .infinity)
                .containerRelativeFrame(.vertical) { height, _ in
                    max(200, height - squaresTop - SearchView.bottomPadding)
                }
                .onGeometryChange(for: CGFloat.self) { proxy in
                    proxy.frame(in: .named(SearchView.content)).minY
                } action: { squaresTop = $0 }
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: Results

    private var resultsView: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .firstTextBaseline) {
                    Text(summary)
                        .font(.serif(17, weight: .medium))
                        .foregroundStyle(Theme.ink)
                    Spacer()
                    if searching || asking { ProgressView().controlSize(.small) }
                }
                TokenSummary(tokens: tokens.wrappedValue)
            }
            if asked {
                Button {
                    // The same search, museums included; what they show
                    // comes along when fetching is on.
                    var playlistRules = rules
                    playlistRules.sources = sources
                    let name = rules.suggestedName(names: model.termNames)
                    editing = Playlist(
                        name: name.isEmpty ? sources.map(museumName).joined(separator: " · ") : name,
                        kind: .smart, rules: playlistRules
                    )
                    fetchForPlaylist = !fromMuseums.isEmpty
                } label: {
                    Label("Utwórz playlistę z tego wyszukiwania", systemImage: "text.badge.plus")
                }
                .buttonStyle(PrimaryButtonStyle())
            }
            if let catalogue, !catalogue.items.isEmpty {
                Eyebrow("W katalogu · \(Names.works(catalogue.total))")
                MasonryGrid(items: catalogue.items) { item in
                    NavigationLink(value: item.id) {
                        ArtCard(item: item, showsFavorite: false)
                    }
                    .buttonStyle(.plain)
                    .contextMenu { QueueButton(itemID: item.id) }
                    .overlay(alignment: .topTrailing) { heart(item) }
                }
            }
            if !fromMuseums.isEmpty || asking {
                HStack {
                    Eyebrow("Z muzeów" + (total > 0 ? " · \(Names.works(total))" : ""))
                    Spacer()
                    if asking {
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
                NavigationLink(value: summary.id) {
                    ArtCard(item: summary, ref: remote?.thumb, showsFavorite: false)
                }
                .buttonStyle(.plain)
                .contextMenu { QueueButton(itemID: summary.id) }
                .overlay(alignment: .topTrailing) { heart(summary) }
            }
            if !searching, !asking, catalogue?.items.isEmpty ?? true, fromMuseums.isEmpty {
                EmptyStateView(
                    title: "Nic tu nie ma",
                    message: "Usuń któryś z chipów albo poszukaj innymi słowami.",
                    systemImage: "magnifyingglass"
                )
            }
            if !asking, !next.isEmpty {
                PullForMore(loading: loadingMore) {
                    Task { await loadMore() }
                }
            }
        }
    }

    private var summary: String {
        let inCatalogue = catalogue?.total ?? 0
        if (searching || asking) && inCatalogue == 0 && fromMuseums.isEmpty { return "Szukam…" }
        return Names.works(inCatalogue + fromMuseums.count) + (next.isEmpty ? "" : "+")
    }

    private func heart(_ item: ItemSummary) -> some View {
        TileHeart(favorite: item.favorite) {
            guard !liking.contains(item.id) else { return }
            Task { await setFavorite(item.id, !item.favorite) }
        }
    }

    // MARK: Loading

    /// What a search depends on, to start it again when it changes.
    private struct SearchKey: Hashable {
        let rules: PlaylistRules
        let sources: [String]
    }

    @MainActor
    private func search(_ key: SearchKey) async {
        results = []
        totals = [:]
        next = [:]
        failed = []
        guard !key.rules.isEmpty || !key.sources.isEmpty else {
            catalogue = nil
            searching = false
            asking = false
            return
        }
        searching = true
        asking = true
        async let museumsAnswered: Void = listen(key, sources: key.sources, page: 1)
        var query = LibraryQuery(rules: key.rules)
        query.sources = key.sources
        do {
            let found = try await model.backend.items(query)
            if !Task.isCancelled { catalogue = found }
        } catch {
            if !Task.isCancelled, !error.isCancellation { model.show(error) }
        }
        if !Task.isCancelled { searching = false }
        await museumsAnswered
        if !Task.isCancelled { asking = false }
    }

    /// Takes in the museums' answers as each comes.
    @MainActor
    private func listen(_ key: SearchKey, sources: [String], page: Int) async {
        // Favourites and playlists are the owner's: no museum has them.
        guard !key.rules.asksMine else { return }
        do {
            let answers = try await model.backend.museumAnswers(key.rules, sources: sources, page: page)
            for try await answer in answers {
                guard !Task.isCancelled, key == searched else { return }
                results = results.adding(answer.items)
                totals[answer.source] = max(totals[answer.source] ?? 0, answer.total)
                next[answer.source] = answer.next
                failed += (answer.failed ?? []).filter { !failed.contains($0) }
            }
        } catch {
            guard !Task.isCancelled, !error.isCancellation, key == searched else { return }
            if page > 1 {
                model.show(error)
            } else {
                let silent = (sources.isEmpty ? museums.map(\.key) : sources).filter { totals[$0] == nil }
                failed += silent.filter { !failed.contains($0) }
            }
        }
    }

    /// The next page of each museum that has more.
    @MainActor
    private func loadMore() async {
        guard let key = searched else { return }
        loadingMore = true
        defer { loadingMore = false }
        // Museums looked through for colours stop at different pages.
        let byPage = Dictionary(grouping: next.keys.sorted()) { next[$0] ?? 1 }
        await withTaskGroup(of: Void.self) { group in
            for (page, keys) in byPage {
                group.addTask { @MainActor in await listen(key, sources: keys, page: page) }
            }
        }
    }

    /// Into Ulubione or out, the heart turned at once; a museum's work joins
    /// the library with it (the server keeps a work once it is liked).
    @MainActor
    private func setFavorite(_ id: String, _ favorite: Bool) async {
        liking.insert(id)
        defer { liking.remove(id) }
        let joins = results.contains { $0.id == id && !$0.inLibrary }
        mark(id, favorite: favorite)
        guard let item = await model.setFavorite(id, favorite) else {
            mark(id, favorite: !favorite)
            return
        }
        mark(id, favorite: item.favorite)
        if joins { await model.refreshFacets() }
    }

    /// The tile's heart. A museum's work keeps its picture from the museum:
    /// the server's own would load it again.
    private func mark(_ id: String, favorite: Bool) {
        if let index = results.firstIndex(where: { $0.id == id }) {
            results[index].item.favorite = favorite
        }
        if let index = catalogue?.items.firstIndex(where: { $0.id == id }) {
            catalogue?.items[index].favorite = favorite
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
