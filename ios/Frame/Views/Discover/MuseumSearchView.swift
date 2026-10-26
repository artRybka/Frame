import SwiftUI

/// Discover's search: words, artists, styles, subjects, periods, techniques,
/// colours and museums as chips, over the catalogue (at once) and the
/// museums (as they answer). Museums, colours, styles, subjects, periods and
/// techniques come from the field's "+"; with nothing asked yet the icon's
/// squares play.
struct MuseumSearchView: View {
    @Environment(AppModel.self) private var model
    @State private var museums: [Museum] = []
    /// What is asked for, as playlist rules (a playlist can be made from it).
    @State private var rules = PlaylistRules()
    /// Keys of the museums to ask; none means all of them.
    @State private var sources: [String] = []
    @State private var catalogue: ItemPage?
    @State private var results: [RemoteItem] = []
    @State private var total = 0
    @State private var failed: [String] = []
    @State private var page = 1
    @State private var searching = false
    @State private var loadingMore = false
    @State private var adding: Set<String> = []
    @State private var editing: Playlist?
    @State private var typing = false

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

    /// Museum works the catalogue doesn't hold already.
    private var fromMuseums: [RemoteItem] {
        let known = Set(catalogue?.items.map(\.id) ?? [])
        return results.filter { !known.contains($0.id) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            TermSearchField(
                tokens: tokens, museums: museums, colors: ColorTag.families + ColorTag.moods, typing: $typing
            )
            if asked {
                resultsView
            } else if !typing {
                idle
            }
        }
        .task {
            await model.loadVocabulary()
            if museums.isEmpty { museums = (try? await model.backend.museums()) ?? [] }
            if LaunchRoute.screen == "museums", rules.isEmpty {
                rules.artists = ["Utagawa Hiroshige"]
            }
        }
        .task(id: SearchKey(rules: rules, sources: sources)) { await search() }
        .onChange(of: model.artistSearch, initial: true) { _, artist in
            guard let artist else { return }
            var asked = PlaylistRules()
            asked.artists = [artist]
            rules = asked
            sources = []
            // Later, so the tab and Discover see the request first.
            Task { model.artistSearch = nil }
        }
        .sheet(item: $editing) { playlist in
            PlaylistEditorView(playlist: playlist)
        }
    }

    // MARK: Nothing asked yet

    private var idle: some View {
        VStack(spacing: 4) {
            Text("Muzea, kolory, style, tematy, epoki i techniki dodasz przyciskiem \(Image(systemName: "plus.circle.fill")) w polu wyszukiwania.")
                .font(.footnote)
                .foregroundStyle(Theme.inkSoft)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 12)
            // Room below the row for the squares to fall to the bottom.
            SquaresAnimation()
                .frame(maxWidth: .infinity)
                .containerRelativeFrame(.vertical) { height, _ in height * 0.55 }
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: Results

    private var resultsView: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                Text(summary)
                    .font(.serif(17, weight: .medium))
                    .foregroundStyle(Theme.ink)
                Spacer()
                if searching { ProgressView().controlSize(.small) }
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
                    .contextMenu { QueueButton(itemID: item.id) }
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
                    .contextMenu { QueueButton(itemID: summary.id) }
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
        let sources: [String]
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
        query.sources = sources
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
            let found = try await model.backend.searchMuseums(rules, sources: sources, page: 1)
            guard !Task.isCancelled else { return }
            results = found.items
            total = found.total
            failed = found.failed ?? []
        } catch is CancellationError {
        } catch {
            if !Task.isCancelled { failed = sources.isEmpty ? museums.map(\.key) : sources }
        }
    }

    private func loadMore() async {
        loadingMore = true
        defer { loadingMore = false }
        do {
            let found = try await model.backend.searchMuseums(rules, sources: sources, page: page + 1)
            results = results.adding(found.items)
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
