import SwiftUI

/// Playlists: what the frame presents now and all collections, smart and manual.
struct PlaylistsView: View {
    @Environment(AppModel.self) private var model
    @State private var editing: Playlist?
    @State private var path = NavigationPath()

    private var active: PlaylistSummary? {
        guard let id = model.settings?.playlistId else { return nil }
        return model.playlists.first { $0.id == id }
    }

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 26) {
                    if let active {
                        NavigationLink(value: active.id) {
                            NowPlayingCard(playlist: active)
                        }
                        .buttonStyle(.plain)
                    }
                    SectionHeader(title: "Kolekcje", subtitle: "Dzieła według artystów, stylów i kolorów oraz albumy iCloud")
                    LazyVGrid(columns: [GridItem(.flexible(), spacing: 16), GridItem(.flexible(), spacing: 16)], spacing: 22) {
                        ForEach(model.playlists) { playlist in
                            NavigationLink(value: playlist.id) {
                                PlaylistCard(playlist: playlist, isActive: playlist.id == active?.id)
                            }
                            .buttonStyle(.plain)
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
            .navigationDestination(for: String.self) { id in
                ItemDetailView(itemID: id)
            }
            .sheet(item: $editing) { playlist in
                PlaylistEditorView(playlist: playlist)
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

extension Playlist: Identifiable {}

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

/// Large card for the playlist the frame presents.
struct NowPlayingCard: View {
    let playlist: PlaylistSummary

    var body: some View {
        HStack(spacing: 16) {
            Collage(itemIDs: playlist.coverItemIds, title: playlist.name)
                .frame(width: 112, height: 112)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Image(systemName: "photo.artframe")
                    Eyebrow("Teraz prezentowane", color: Theme.vermilion)
                }
                .foregroundStyle(Theme.vermilion)
                Text(playlist.name)
                    .font(.serif(24, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(2)
                Text(playlist.countText)
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
