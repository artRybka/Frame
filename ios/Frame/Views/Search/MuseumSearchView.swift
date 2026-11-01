import SwiftUI

/// The Szukaj tab's search: words, artists, styles, subjects, periods,
/// techniques, colours and museums as chips, over the catalogue (at once)
/// and the museums (each as it answers), in one grid that doesn't say which
/// is which (the user knows no "katalog"). Artists and words are the system
/// field's tokens; museums, colours, styles, subjects, periods and techniques
/// come from the glass groups over the field, which hide as the results
/// scroll and come back when the field is tapped or the scrolling stops. With nothing asked yet
/// the icon's squares play. The museums are asked for more on their own as
/// the results scroll towards their end, the squares playing at the bottom,
/// over the groups, while they answer. Coming back from a work finds the results
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
    /// The page to ask each museum for more; museums with no more are left out.
    @State private var next: [String: Int] = [:]
    /// The catalogue is being asked.
    @State private var searching = false
    /// The museums are still answering.
    @State private var asking = false
    @State private var loadingMore = false
    /// The results' end is less than a screen away: time to ask for more.
    @State private var nearEnd = false
    /// What the results are for, so that coming back from a work doesn't
    /// search again; the search goes on while a work is open.
    @State private var searched: SearchKey?
    @State private var loader: Task<Void, Never>?
    /// Works whose heart the server is still taking.
    @State private var liking: Set<String> = []
    @State private var editing: Playlist?
    @State private var lookup = TermLookup()
    @FocusState private var fieldFocused: Bool
    /// The groups over the field: hidden while scrolling the results.
    @State private var groupsShown = true
    /// The screen's height, for how tall an open group may be.
    @State private var height: CGFloat = 760
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

    /// Museum works the catalogue doesn't hold already, in any copy.
    private var fromMuseums: [RemoteItem] {
        let known = Set(catalogue?.items.map(\.id) ?? [])
        return results.filter { !known.contains($0.id) && !known.contains($0.twin ?? "") }
    }

    /// The museums' works on screen: only once the catalogue has answered,
    /// so that its works don't come in above them (the museums' grid jumped
    /// down) and the copies it holds are left out from the start.
    private var shownFromMuseums: [RemoteItem] { searching ? [] : fromMuseums }

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
            // Full width also while only the suggestions' spinner is there:
            // the scrolled content alone made the page a narrow strip.
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, SearchView.bottomPadding)
            .coordinateSpace(.named(SearchView.content))
        }
        .scrollDismissesKeyboard(.immediately)
        .hidesOnScroll($groupsShown)
        // Before the end shows, so the next works are mostly there already.
        .onScrollGeometryChange(for: Bool.self) { geometry in
            geometry.contentSize.height - geometry.visibleRect.maxY < geometry.containerSize.height
        } action: { _, near in
            nearEnd = near
            moreIfNeeded()
        }
        .paperPage()
        .safeAreaInset(edge: .bottom, spacing: 0) {
            // Hidden, the groups keep their room: the results' end (and the
            // squares there) stays above them when they come back. (Taken
            // out, they gave it up, and coming back covered the end.)
            TermFacetBar(
                tokens: tokens, museums: museums, colors: ColorTag.families + ColorTag.moods,
                focus: $fieldFocused, panelHeight: height * TermFacetBar.panelShare
            )
            .padding(.horizontal, Theme.gutter)
            .opacity(groupsShown ? 1 : 0)
            .offset(y: groupsShown ? 0 : 48)
            .allowsHitTesting(groupsShown)
            .accessibilityHidden(!groupsShown)
        }
        // Measured outside the groups' inset: an open group grows it.
        .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { height = $0 }
        .termSearch(lookup, tokens: tokens, focused: $fieldFocused)
        // Tapping the field brings the groups back, as does asking nothing.
        .onChange(of: fieldFocused) { _, focused in
            if focused, !groupsShown { withAnimation(.snappy) { groupsShown = true } }
        }
        .onChange(of: asked) { _, asked in
            if !asked, !groupsShown { withAnimation(.snappy) { groupsShown = true } }
        }
        // A first page shorter than the screen asks for the next at once.
        .onChange(of: asking) { moreIfNeeded() }
        .task {
            await model.loadVocabulary()
            if museums.isEmpty { museums = (try? await model.backend.museums()) ?? [] }
            if LaunchRoute.screen == "museums", rules.isEmpty {
                rules.artists = ["Utagawa Hiroshige"]
            }
            // CI screenshots: a group's choice alone, the X next to the field.
            if ["search-chosen", "search-colors"].contains(LaunchRoute.screen), rules.colors.isEmpty {
                rules.colors = ["blue"]
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
            PlaylistEditorView(playlist: playlist)
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
                    // The same search, museums included; the playlist asks
                    // them for what it misses up to its limit.
                    var playlistRules = rules
                    playlistRules.sources = sources
                    let name = rules.suggestedName(names: model.termNames)
                    editing = Playlist(
                        name: name.isEmpty ? sources.map(museumName).joined(separator: " · ") : name,
                        kind: .smart, rules: playlistRules
                    )
                } label: {
                    Label("Utwórz playlistę z tego wyszukiwania", systemImage: "text.badge.plus")
                }
                .buttonStyle(PrimaryButtonStyle())
            }
            // One grid: the server's works first, the museums' coming in
            // under them. Where a work comes from isn't shown.
            worksGrid(catalogue?.items ?? [], shownFromMuseums)
            if !searching, !asking, catalogue?.items.isEmpty ?? true, fromMuseums.isEmpty {
                EmptyStateView(
                    title: "Nic tu nie ma",
                    message: "Usuń któryś z chipów albo poszukaj innymi słowami.",
                    systemImage: "magnifyingglass"
                )
            }
            if !asking, !next.isEmpty {
                // The end: the icon's squares as long as a museum may still
                // have more (also while one hasn't answered and waits to be
                // asked again), nothing to read or pull.
                SquaresAnimation(inScreenMiddle: false, tapForNext: false)
                    .frame(height: 96)
                    .frame(maxWidth: .infinity)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("Doczytuję")
            }
        }
    }

    /// The works found, a museum's with its picture from the museum.
    private func worksGrid(_ known: [ItemSummary], _ remotes: [RemoteItem]) -> some View {
        let thumbs = Dictionary(remotes.map { ($0.id, $0.thumb) }, uniquingKeysWith: { first, _ in first })
        return MasonryGrid(items: known + remotes.map(\.item.summary)) { summary in
            NavigationLink(value: summary.id) {
                ArtCard(item: summary, ref: thumbs[summary.id], showsFavorite: false)
            }
            .buttonStyle(.plain)
            .contextMenu { QueueButton(itemID: summary.id) }
            .overlay(alignment: .topTrailing) { heart(summary) }
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
        next = [:]
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
                next[answer.source] = answer.next
            }
        } catch {
            // A museum that doesn't answer (the Met's bot wall turns the
            // server away for a while) is left out quietly: the others'
            // works are enough (Mateusz, 2026-10-31).
        }
    }

    /// Asks the museums for their next pages while the results' end is near,
    /// again and again until it isn't (a page can bring few new works). When
    /// a round brought nothing (a museum that didn't answer), the next waits
    /// a while, so that the squares at the end keep their word without
    /// asking a museum that is down over and over.
    @MainActor
    private func moreIfNeeded(after pause: Duration = .zero) {
        guard nearEnd, asked, !asking, !loadingMore, !next.isEmpty, let key = searched else { return }
        loadingMore = true
        Task { @MainActor in
            if pause > .zero { try? await Task.sleep(for: pause) }
            guard key == searched, nearEnd, !next.isEmpty else {
                loadingMore = false
                moreIfNeeded()
                return
            }
            let found = results.count
            let pages = next
            await loadMore(key)
            loadingMore = false
            let moved = key != searched || results.count != found || next != pages
            moreIfNeeded(after: moved ? .zero : Self.retryPause)
        }
    }

    /// How long a round that brought nothing waits before the next.
    private static let retryPause: Duration = .seconds(10)

    /// The next page of each museum that has more.
    @MainActor
    private func loadMore(_ key: SearchKey) async {
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
