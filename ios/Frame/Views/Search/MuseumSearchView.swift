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
    /// What is asked for, as playlist rules (a playlist can be made from it).
    @State private var rules = PlaylistRules()
    /// Keys of the museums to ask; none means all of them.
    @State private var sources: [String] = []
    /// The catalogue's and the museums' works for what is asked: the same
    /// search as the playlist editor's.
    @State private var search = WorkSearch()
    /// Works whose heart the server is still taking.
    @State private var liking: Set<String> = []
    @State private var editing: Playlist?
    /// Nothing found: each choice with how many works the library has
    /// without it (only those with some), to give one up with a tap.
    @State private var without: [(token: SearchToken, count: Int)] = []
    /// Nothing found has stayed so for a moment: only then is it said, not
    /// at the start of every search (Mateusz).
    @State private var emptyShown = false
    @State private var lookup = TermLookup()
    @FocusState private var fieldFocused: Bool
    /// The groups over the field: hidden while scrolling the results.
    @State private var groupsShown = true
    /// The screen's height, for how tall an open group may be.
    @State private var height: CGFloat = 760
    /// Where the squares start, from the top of the scrolled content.
    @State private var squaresTop: CGFloat = 0
    /// Where the results are scrolled to: back to the top for a new search.
    @State private var position = ScrollPosition(edge: .top)

    /// The rules' chips, then the colours' and the museums'.
    private var tokens: Binding<[SearchToken]> {
        Binding(
            get: {
                var tokens = rules.tokens(names: model.termNames)
                tokens += rules.colors.map { SearchToken(kind: "color", key: $0, name: ColorTag.name($0)) }
                tokens += rules.museumTokens(name: model.placeName, sources: sources)
                return tokens
            },
            set: { tokens in (rules, sources) = rulesAsked(by: tokens) }
        )
    }

    /// The rules and museums the chips ask for.
    private func rulesAsked(by tokens: [SearchToken]) -> (PlaylistRules, [String]) {
        var rules = rules
        rules.setTokens(tokens)
        rules.colors = tokens.filter { $0.kind == "color" }.map(\.key)
        let sources = rules.setMuseums(tokens)
        return (rules, sources)
    }

    private var asked: Bool { !rules.isEmpty || !sources.isEmpty }

    private var searchKey: WorkSearch.Key { WorkSearch.Key(rules: rules, sources: sources) }

    var body: some View {
        ScrollView {
            // The suggestions are over the field (`termSuggestions`), not
            // here: the results stay put while words are typed.
            VStack(alignment: .leading, spacing: 16) {
                if asked {
                    resultsView
                } else {
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
        .scrollPosition($position)
        .scrollDismissesKeyboard(.immediately)
        .hidesOnScroll($groupsShown)
        // Before the end shows, so the next works are mostly there already.
        .onScrollGeometryChange(for: Bool.self) { geometry in
            geometry.contentSize.height - geometry.visibleRect.maxY < geometry.containerSize.height
        } action: { _, near in
            search.scrolled(nearEnd: near)
        }
        .paperPage()
        .safeAreaInset(edge: .bottom, spacing: 0) {
            // Hidden, the groups keep their room: the results' end (and the
            // squares there) stays above them when they come back. (Taken
            // out, they gave it up, and coming back covered the end.)
            TermFacetBar(
                tokens: tokens, lookup: lookup, colors: ColorTag.families + ColorTag.moods,
                focus: $fieldFocused, panelHeight: height * TermFacetBar.panelShare
            )
            .padding(.horizontal, Theme.gutter)
            // While typing the suggestions take their place (keeping the room).
            .opacity(groupsShown && !lookup.suggesting(fieldFocused) ? 1 : 0)
            .offset(y: groupsShown ? 0 : 48)
            .allowsHitTesting(groupsShown)
            .accessibilityHidden(!groupsShown)
        }
        // Measured outside the groups' inset: an open group grows it.
        .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { height = $0 }
        .termSuggestions(lookup, tokens: tokens, focused: $fieldFocused)
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
            await model.loadPlaceNames()
            if LaunchRoute.screen == "museums", rules.isEmpty {
                rules.artists = ["Utagawa Hiroshige"]
            }
            // CI screenshots: a group's choice alone, the X next to the field.
            if LaunchRoute.screen == "search-chosen", rules.colors.isEmpty {
                rules.colors = ["blue@much"]
            }
            // CI screenshots: the Kolor sheet's two cards.
            if LaunchRoute.screen == "search-colors", rules.colors.isEmpty {
                rules.colors = ["brown@much", "gray@clear"]
            }
            if LaunchRoute.screen == "search-tones", rules.colors.isEmpty {
                rules.colors = ["tone:neutral", "tone:dark", "tone:medium"]
            }
            // CI screenshots: nothing found, and what to give up.
            if LaunchRoute.screen == "search-empty", rules.colors.isEmpty {
                rules.colors = ["orange@clear", "yellow@clear", "tone:muted"]
            }
            // CI screenshots: the Epoka sheet with two centuries between the beads.
            if LaunchRoute.screen == "search-picker", rules.terms.isEmpty {
                rules.terms = ["period:17c", "period:18c"]
            }
            // CI screenshots: the Technika sheet with two picked.
            if LaunchRoute.screen == "search-techniques", rules.terms.isEmpty {
                rules.terms = ["technique:painting", "technique:drawing"]
            }
            // CI screenshots: every museum but the Met, with a colour.
            if LaunchRoute.screen == "search-museums", rules.excludePlaces.isEmpty {
                rules.colors = ["blue@much"]
                model.placeNames["Q160236"] = "Metropolitan Museum of Art"
                rules.excludePlaces = ["Q160236"]
            }
        }
        .task(id: searchKey) {
            let key = searchKey
            guard key != search.searched else { return }
            try? await Task.sleep(for: .milliseconds(150))
            guard !Task.isCancelled else { return }
            without = []
            // Something else asked: its results from their top, not from
            // where the last ones were scrolled to.
            withAnimation(.snappy) { position.scrollTo(edge: .top) }
            search.start(key, model: model)
        }
        // Nothing found: what giving up each choice would find.
        .task(id: search.settled) {
            guard let key = search.settled, key == searchKey, search.found == 0, !search.more else { return }
            let found = await withoutEach(tokens.wrappedValue)
            if !Task.isCancelled, key == search.searched { without = found }
        }
        // Said only once nothing found has lasted a moment.
        .task(id: nothingFound) {
            guard nothingFound else {
                emptyShown = false
                return
            }
            try? await Task.sleep(for: .milliseconds(700))
            guard !Task.isCancelled, nothingFound else { return }
            withAnimation(.easeOut(duration: 0.3)) { emptyShown = true }
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
        .onChange(of: model.placeSearch, initial: true) { _, place in
            guard let place else { return }
            var asked = PlaylistRules()
            asked.places = [place.key]
            rules = asked
            sources = []
            Task { model.placeSearch = nil }
        }
        .onChange(of: model.hearts) { _, hearts in
            // Liked or unliked on the work's card meanwhile.
            for (id, favorite) in hearts where !liking.contains(id) {
                search.mark(id, favorite: favorite)
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
                }
                TokenSummary(tokens: tokens.wrappedValue)
            }
            if asked, !nothingFound {
                Button {
                    // The same search, museums included; the playlist asks
                    // them for what it misses up to its limit.
                    var playlistRules = rules
                    playlistRules.sources = sources
                    let name = rules.suggestedName(names: model.termNames)
                    editing = Playlist(
                        name: name.isEmpty ? (rules.places + sources).map(model.placeName).joined(separator: " · ") : name,
                        kind: .smart, rules: playlistRules
                    )
                } label: {
                    Label("Utwórz playlistę z tego wyszukiwania", systemImage: "text.badge.plus")
                }
                .buttonStyle(PrimaryButtonStyle())
            }
            // One grid: the server's works first, the museums' coming in
            // under them. Where a work comes from isn't shown.
            worksGrid(search.shownCatalogue, search.shownFromMuseums)
            // Only once nothing more can come.
            if emptyShown {
                NothingFound(
                    without: without,
                    phrase: tokens.wrappedValue.first { $0.kind == "word" && $0.key.contains(" ") },
                    splitUp: splitUp
                ) { token in
                    withAnimation(.snappy) { tokens.wrappedValue.removeAll { $0 == token } }
                }
            }
            if search.busy || search.more {
                // The squares say "waiting" (Mateusz): while the search is
                // asked, and after as long as a museum may still have more,
                // also one that hasn't answered and waits to be asked again.
                SearchWaiting()
            }
        }
    }

    /// A phrase's words as chips of their own, where the phrase was.
    private func splitUp(_ phrase: SearchToken) {
        var chips = tokens.wrappedValue
        guard let at = chips.firstIndex(of: phrase) else { return }
        let words = SearchPhrases.words(phrase.key).map { SearchToken(kind: "word", key: $0, name: $0) }
        chips.replaceSubrange(at ... at, with: words.filter { !chips.contains($0) })
        withAnimation(.snappy) { tokens.wrappedValue = chips }
    }

    /// The works found, a museum's with its picture from the museum.
    private func worksGrid(_ known: [ItemSummary], _ remotes: [RemoteItem]) -> some View {
        let thumbs = Dictionary(remotes.map { ($0.id, $0.thumb) }, uniquingKeysWith: { first, _ in first })
        return MasonryGrid(items: known + remotes.map(\.summary)) { summary in
            NavigationLink(value: summary.id) {
                ArtCard(item: summary, ref: thumbs[summary.id], showsFavorite: false)
            }
            .buttonStyle(.plain)
            .contextMenu {
                QueueButton(itemID: summary.id)
                Button("Ukryj dzieło", systemImage: "eye.slash") {
                    Task { await search.hide(summary.id) }
                }
            }
            .overlay(alignment: .topTrailing) { heart(summary) }
        }
    }

    /// The search is over and found nothing.
    private var nothingFound: Bool {
        asked && search.searched == searchKey && search.nothingFound
    }

    private var summary: String { search.summary }

    private func heart(_ item: ItemSummary) -> some View {
        TileHeart(favorite: item.favorite) {
            guard !liking.contains(item.id) else { return }
            Task { await setFavorite(item.id, !item.favorite) }
        }
    }

    // MARK: Loading

    /// How many works the library has without each chip in turn, those
    /// with some (a single chip given up is no search at all).
    @MainActor
    private func withoutEach(_ all: [SearchToken]) async -> [(token: SearchToken, count: Int)] {
        guard all.count > 1 else { return [] }
        let asks = all.prefix(6).map { token in
            let (rules, sources) = rulesAsked(by: all.filter { $0 != token })
            var query = LibraryQuery(rules: rules)
            query.sources = sources
            query.limit = 1
            return (token, query)
        }
        let backend = model.backend
        var counts: [Int: Int] = [:]
        await withTaskGroup(of: (Int, Int).self) { group in
            for (index, ask) in asks.enumerated() {
                group.addTask { (index, (try? await backend.items(ask.1).total) ?? 0) }
            }
            for await (index, count) in group { counts[index] = count }
        }
        return asks.enumerated().compactMap { index, ask in
            let count = counts[index] ?? 0
            return count > 0 ? (ask.0, count) : nil
        }
    }

    /// Into Ulubione or out, the heart turned at once; a museum's work joins
    /// the library with it (the server keeps a work once it is liked).
    @MainActor
    private func setFavorite(_ id: String, _ favorite: Bool) async {
        liking.insert(id)
        defer { liking.remove(id) }
        let joins = search.results.contains { $0.id == id && !$0.inLibrary }
        search.mark(id, favorite: favorite)
        guard let item = await model.setFavorite(id, favorite) else {
            search.mark(id, favorite: !favorite)
            return
        }
        search.mark(id, favorite: item.favorite)
        if joins { await model.refreshFacets() }
    }
}

/// Wrapping row of chips; `centred` puts each row in the middle (the Temat
/// sheet).
struct FlowLayout: Layout {
    var spacing: CGFloat = 8
    var centred = false

    private struct Row {
        var indices: [Int] = []
        var width: CGFloat = 0
        var height: CGFloat = 0
    }

    private func rows(_ subviews: Subviews, width: CGFloat) -> [Row] {
        var rows: [Row] = []
        var row = Row()
        for (index, view) in subviews.enumerated() {
            let size = view.sizeThatFits(.unspecified)
            if !row.indices.isEmpty && row.width + spacing + size.width > width {
                rows.append(row)
                row = Row()
            }
            row.width += (row.indices.isEmpty ? 0 : spacing) + size.width
            row.height = max(row.height, size.height)
            row.indices.append(index)
        }
        if !row.indices.isEmpty { rows.append(row) }
        return rows
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        let lines = rows(subviews, width: width)
        let height = lines.map(\.height).reduce(0, +) + spacing * CGFloat(max(lines.count - 1, 0))
        return CGSize(width: width.isFinite ? width : lines.map(\.width).max() ?? 0, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in rows(subviews, width: bounds.width) {
            var x = bounds.minX + (centred ? max((bounds.width - row.width) / 2, 0) : 0)
            for index in row.indices {
                let size = subviews[index].sizeThatFits(.unspecified)
                subviews[index].place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
            y += row.height + spacing
        }
    }
}
