import SwiftUI

/// Playlists: what the frame presents now and all collections, smart and manual.
struct PlaylistsView: View {
    @Environment(AppModel.self) private var model
    @State private var editing: Playlist?
    @State private var path = NavigationPath()
    /// The playlist whose deletion waits for a yes.
    @State private var deleting: PlaylistSummary?

    private var active: PlaylistSummary? {
        guard let id = model.settings?.playlistId else { return nil }
        return model.playlists.first { $0.id == id }
    }

    /// The frame plays Propozycje: no playlist.
    private var suggestionsActive: Bool { model.settings != nil && model.settings?.playlistId == nil }

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 26) {
                    if let active {
                        NavigationLink(value: active.id) {
                            NowPlayingCard(playlist: active)
                        }
                        .buttonStyle(.plain)
                    } else if suggestionsActive {
                        NavigationLink(value: SuggestionsRoute()) {
                            NowPlayingCard(title: "Propozycje", subtitle: "dobór z Odkrywaj") {
                                SuggestionsCover(works: model.suggestionCover)
                            }
                        }
                        .buttonStyle(.plain)
                    }
                    SectionHeader(
                        title: "Kolekcje",
                        subtitle: "Propozycje, dzieła według artystów, stylów i kolorów oraz albumy iCloud"
                    )
                    LazyVGrid(columns: [GridItem(.flexible(), spacing: 16), GridItem(.flexible(), spacing: 16)], spacing: 22) {
                        NavigationLink(value: SuggestionsRoute()) {
                            SuggestionsCard(works: model.suggestionCover, isActive: suggestionsActive)
                        }
                        .buttonStyle(.plain)
                        .contextMenu { suggestionsMenu }
                        ForEach(model.playlists) { playlist in
                            NavigationLink(value: playlist.id) {
                                PlaylistCard(playlist: playlist, isActive: playlist.id == active?.id)
                            }
                            .buttonStyle(.plain)
                            .contextMenu { menu(playlist) }
                        }
                        Button {
                            editing = Playlist(name: "")
                        } label: {
                            NewPlaylistTile()
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, Theme.gutter)
                .padding(.bottom, 40)
            }
            .background(Theme.paper)
            .navigationTitle("Playlisty")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        editing = Playlist(name: "")
                    } label: {
                        Image(systemName: "plus")
                    }
                    .accessibilityLabel("Nowa playlista")
                }
            }
            .navigationDestination(for: Int.self) { id in
                PlaylistDetailView(playlistID: id)
            }
            .navigationDestination(for: SuggestionsRoute.self) { _ in
                SuggestionsPage(path: $path)
            }
            .navigationDestination(for: String.self) { id in
                ItemDetailView(itemID: id)
            }
            .navigationDestination(for: ArtTheme.self) { theme in
                ThemeView(theme: theme)
            }
            .navigationDestination(for: ThemeGroupRoute.self) { route in
                ThemeGroupView(name: route.name)
            }
            .navigationDestination(for: SuggestionRowRoute.self) { route in
                SuggestionRowGridView(key: route.key)
            }
            .sheet(item: $editing) { playlist in
                PlaylistEditorView(playlist: playlist)
            }
            .confirmationDialog(
                "Usunąć playlistę „\(deleting?.name ?? "")”?",
                isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } }),
                titleVisibility: .visible,
                presenting: deleting
            ) { playlist in
                Button("Usuń", role: .destructive) {
                    Task { await delete(playlist) }
                }
            }
            .refreshable { await model.refreshPlaylists() }
            .task { if model.playlists.isEmpty { await model.refreshPlaylists() } }
            .onChange(of: model.playlists.first?.id) { _, first in
                if LaunchRoute.screen == "playlist", path.isEmpty, let first { path.append(first) }
                if LaunchRoute.screen == "editor", editing == nil {
                    editing = Playlist(name: "Błękitne krajobrazy", rules: PlaylistRules(colors: ["blue"]))
                }
                if LaunchRoute.screen == "editor-new", editing == nil {
                    editing = Playlist(name: "", rules: PlaylistRules())
                }
                if LaunchRoute.screen == "editor-manual", editing == nil {
                    editing = Playlist(name: "Na ścianę", kind: .manual)
                }
            }
        }
    }
}

extension PlaylistsView {
    /// Held on a cover: present it on the frame, or delete it ("Ulubione" stays).
    @ViewBuilder
    private func menu(_ playlist: PlaylistSummary) -> some View {
        if playlist.id != active?.id {
            Button("Prezentuj na ramce", systemImage: "photo.artframe") {
                Task { await model.play(playlist) }
            }
            .disabled(playlist.itemCount == 0)
        }
        if !playlist.isFavorites {
            Button("Usuń playlistę", systemImage: "trash", role: .destructive) { deleting = playlist }
        }
    }

    /// Held on "Propozycje": present them, or open them in Discover.
    @ViewBuilder
    private var suggestionsMenu: some View {
        if !suggestionsActive {
            Button("Prezentuj na ramce", systemImage: "photo.artframe") {
                Task { await model.playSuggestions() }
            }
        }
        Button("Otwórz w Odkrywaj", systemImage: "square.grid.2x2") { model.suggestionsOpened += 1 }
    }

    private func delete(_ playlist: PlaylistSummary) async {
        do {
            try await model.backend.deletePlaylist(id: playlist.id)
            model.notices.done("Usunięto „\(playlist.name)”")
        } catch {
            model.show(error)
        }
        await model.refreshPlaylists()
    }
}

extension Playlist: Identifiable {}

/// Opens Propozycje within Playlisty, pushed like a playlist.
struct SuggestionsRoute: Hashable {}

/// Propozycje opened from their tile: a header like a playlist's, with
/// "Prezentuj na ramce", over the same themes and rows as in Discover.
struct SuggestionsPage: View {
    @Environment(AppModel.self) private var model
    @Binding var path: NavigationPath
    @State private var starting = false

    private var isActive: Bool { model.settings != nil && model.settings?.playlistId == nil }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                header
                SuggestionsView(path: $path)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 40)
        }
        .background(Theme.paper.ignoresSafeArea())
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await model.refreshDiscover(force: true) }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 14) {
            SuggestionsCover(works: model.suggestionCover)
                .aspectRatio(1.6, contentMode: .fit)
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                .shadow(color: .black.opacity(0.15), radius: 18, y: 10)
            Eyebrow("Dobór z Odkrywaj", color: Theme.vermilion)
            Text("Propozycje")
                .font(.serif(32, weight: .semibold))
                .foregroundStyle(Theme.ink)
            Text("Dzieła, które serwer wybiera z muzeów, i motywy, z których zrobisz playlistę.")
                .font(.serif(17))
                .foregroundStyle(Theme.inkSoft)
            if isActive {
                Label("Teraz prezentowane na ramce", systemImage: "photo.artframe")
                    .font(.headline)
                    .foregroundStyle(Theme.vermilion)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 15)
                    .background(Theme.vermilion.opacity(0.1), in: RoundedRectangle(cornerRadius: 14))
            } else {
                Button {
                    Task {
                        starting = true
                        defer { starting = false }
                        await model.playSuggestions()
                    }
                } label: {
                    Label {
                        Text("Prezentuj na ramce")
                    } icon: {
                        if starting {
                            ProgressView().tint(Theme.paper)
                        } else {
                            Image(systemName: "photo.artframe")
                        }
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(starting)
                .sensoryFeedback(.impact(weight: .medium), trigger: starting) { _, now in now }
            }
        }
    }
}

extension PlaylistSummary {
    /// "12 dzieł", or "12 zdjęć" for an album.
    var countText: String { kind == .album ? Names.photos(itemCount) : Names.works(itemCount) }
}

extension PlaylistKind {
    /// Small symbol next to a playlist's name; none for manual ones.
    var icon: String? {
        switch self {
        case .smart: "sparkles"
        case .album: "icloud"
        case .manual: nil
        }
    }
}

/// Large card for the playlist the frame presents (or Propozycje).
struct NowPlayingCard<Cover: View>: View {
    let title: String
    let subtitle: String
    @ViewBuilder let cover: Cover

    var body: some View {
        HStack(spacing: 16) {
            cover
                .frame(width: 112, height: 112)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Image(systemName: "photo.artframe")
                    Eyebrow("Teraz prezentowane", color: Theme.vermilion)
                }
                .foregroundStyle(Theme.vermilion)
                Text(title)
                    .font(.serif(24, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(2)
                Text(subtitle)
                    .font(.subheadline)
                    .foregroundStyle(Theme.inkSoft)
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right").foregroundStyle(Theme.inkSoft)
        }
        .padding(16)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).strokeBorder(Theme.hairline))
        .shadow(color: .black.opacity(0.06), radius: 16, y: 8)
        .padding(.top, 6)
    }
}

extension NowPlayingCard where Cover == Collage {
    init(playlist: PlaylistSummary) {
        self.init(title: playlist.name, subtitle: playlist.countText) {
            Collage(itemIDs: playlist.coverItemIds, title: playlist.name)
        }
    }
}

struct PlaylistCard: View {
    let playlist: PlaylistSummary
    var isActive = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Collage(itemIDs: playlist.coverItemIds, title: playlist.name)
                .aspectRatio(1, contentMode: .fit)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(alignment: .topLeading) {
                    if isActive {
                        Image(systemName: "play.fill")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.white)
                            .padding(7)
                            .background(Theme.vermilion, in: Circle())
                            .padding(8)
                    }
                }
                .shadow(color: .black.opacity(0.12), radius: 10, y: 6)
            VStack(alignment: .leading, spacing: 3) {
                Text(playlist.name)
                    .font(.serif(16, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(2)
                HStack(spacing: 4) {
                    if let icon = playlist.kind.icon {
                        Image(systemName: icon).font(.caption2)
                    }
                    Text(playlist.countText)
                }
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
            }
        }
    }
}

/// "Propozycje" first among the collections: the rotation the server picks
/// in Discover, marked with sparkles; it can't be edited or deleted.
struct SuggestionsCard: View {
    let works: [RemoteItem]
    var isActive = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SuggestionsCover(works: works)
                .aspectRatio(1, contentMode: .fit)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(alignment: .topLeading) {
                    if isActive {
                        Image(systemName: "play.fill")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.white)
                            .padding(7)
                            .background(Theme.vermilion, in: Circle())
                            .padding(8)
                    }
                }
                .overlay(alignment: .bottomTrailing) {
                    Image(systemName: "sparkles")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(Theme.accent)
                        .frame(width: 30, height: 30)
                        .background(Theme.paper.opacity(0.85), in: Circle())
                        .padding(8)
                }
                .shadow(color: .black.opacity(0.12), radius: 10, y: 6)
            VStack(alignment: .leading, spacing: 3) {
                Text("Propozycje")
                    .font(.serif(16, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                Text("dobór z Odkrywaj")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityHint("Otwiera Propozycje; przytrzymaj, by pokazać je na ramce")
    }
}

/// Four of the works next in Propozycje, two by two; plain paper where
/// there are fewer.
struct SuggestionsCover: View {
    let works: [RemoteItem]

    var body: some View {
        GeometryReader { geo in
            let side = (geo.size.width - 2) / 2
            let height = (geo.size.height - 2) / 2
            VStack(spacing: 2) {
                ForEach(0 ..< 2, id: \.self) { row in
                    HStack(spacing: 2) {
                        ForEach(0 ..< 2, id: \.self) { column in
                            tile(row * 2 + column)
                                .frame(width: side, height: height)
                                .clipped()
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder private func tile(_ index: Int) -> some View {
        if index < works.count {
            ArtImage(
                ref: works[index].thumb,
                fallback: works[index].thumbFallback,
                placeholder: works[index].item.summary.placeholderColor,
                maxPixel: 400
            )
        } else {
            Theme.mat
        }
    }
}

struct NewPlaylistTile: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(Theme.hairline, style: StrokeStyle(lineWidth: 1.5, dash: [6, 5]))
                .aspectRatio(1, contentMode: .fit)
                .overlay {
                    VStack(spacing: 8) {
                        Image(systemName: "plus").font(.title2.weight(.medium))
                        Text("Nowa playlista").font(.subheadline.weight(.medium))
                    }
                    .foregroundStyle(Theme.inkSoft)
                }
            Text(" ").font(.serif(16))
        }
    }
}

/// Human description of smart rules as chips.
struct RulesSummary: View {
    let rules: PlaylistRules

    var body: some View {
        FlowLayout(spacing: 6) {
            ForEach(rules.artists, id: \.self) { TagLabel(text: $0) }
            ForEach(rules.styles, id: \.self) { TagLabel(text: $0) }
            ForEach(rules.subjects, id: \.self) { TagLabel(text: "#\($0)") }
            ForEach(rules.colors, id: \.self) { TagLabel(text: ColorTag.name($0), swatch: ColorTag.color($0)) }
            if !rules.query.isEmpty { TagLabel(text: "„\(rules.query)”") }
            if let from = rules.yearFrom { TagLabel(text: "od \(String(from))") }
            if let to = rules.yearTo { TagLabel(text: "do \(String(to))") }
            if rules.favoritesOnly { TagLabel(text: "♥ ulubione") }
            ForEach(rules.sources, id: \.self) { TagLabel(text: Names.source($0)) }
        }
    }
}
