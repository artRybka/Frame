import SwiftUI

struct PlaylistDetailView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let playlistID: Int
    @State private var detail: PlaylistDetail?
    @State private var editing: Playlist?
    @State private var confirmDelete = false
    /// Tapping a work takes it out of the playlist instead of opening it.
    @State private var removingItems = false
    @State private var syncing = false

    private var isActive: Bool { model.settings?.playlistId == playlistID }
    private var isAlbum: Bool { detail?.playlist.kind == .album }

    var body: some View {
        ScrollView {
            if let detail {
                VStack(alignment: .leading, spacing: 22) {
                    header(detail.playlist)
                    if !detail.items.isEmpty {
                        MasonryGrid(items: detail.items) { item in card(item) }
                    } else {
                        EmptyStateView(
                            title: "Pusta playlista",
                            message: Self.emptyMessage(detail.playlist.kind)
                        )
                    }
                }
                .padding(.horizontal, Theme.gutter)
                .padding(.bottom, 40)
            } else {
                ProgressView().padding(.top, 120)
            }
        }
        .background(Theme.paper)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                if removingItems {
                    Button("Gotowe") { withAnimation { removingItems = false } }
                        .fontWeight(.semibold)
                } else {
                    Menu {
                        Button("Edytuj", systemImage: "slider.horizontal.3") { editing = playlistBody() }
                        if isAlbum {
                            Button("Synchronizuj z albumem", systemImage: "arrow.triangle.2.circlepath") { sync() }
                                .disabled(syncing)
                        }
                        Button(isAlbum ? "Usuń zdjęcia z playlisty" : "Usuń dzieła z playlisty", systemImage: "minus.circle") {
                            withAnimation { removingItems = true }
                        }
                        .disabled(detail?.items.isEmpty ?? true)
                        if let removed = detail?.playlist.rules.excludeIds.count, removed > 0,
                           detail?.playlist.kind != .manual
                        {
                            Button("Przywróć usunięte (\(removed))", systemImage: "arrow.uturn.backward") {
                                restoreRemoved()
                            }
                        }
                        Button("Usuń playlistę", systemImage: "trash", role: .destructive) { confirmDelete = true }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                }
            }
        }
        .task(id: playlistID) { await load() }
        .sheet(item: $editing, onDismiss: { Task { await load() } }) { playlist in
            PlaylistEditorView(playlist: playlist)
        }
        .confirmationDialog("Usunąć playlistę?", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Usuń", role: .destructive) {
                Task {
                    try? await model.backend.deletePlaylist(id: playlistID)
                    await model.refreshPlaylists()
                    dismiss()
                }
            }
        }
    }

    @ViewBuilder
    private func card(_ item: ItemSummary) -> some View {
        if removingItems {
            Button { remove(item) } label: {
                ArtCard(item: item)
                    .overlay(alignment: .topLeading) {
                        Image(systemName: "minus.circle.fill")
                            .font(.title2)
                            .symbolRenderingMode(.palette)
                            .foregroundStyle(.white, Theme.vermilion)
                            .shadow(color: .black.opacity(0.25), radius: 3, y: 1)
                            .padding(6)
                    }
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Usuń z playlisty: \(item.title)")
        } else {
            NavigationLink(value: item.id) { ArtCard(item: item) }
                .buttonStyle(.plain)
                .contextMenu {
                    Button("Usuń z playlisty", systemImage: "minus.circle", role: .destructive) { remove(item) }
                }
        }
    }

    private func header(_ playlist: PlaylistSummary) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Collage(itemIDs: playlist.coverItemIds, title: playlist.name, spacing: 3)
                .aspectRatio(1.6, contentMode: .fit)
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                .shadow(color: .black.opacity(0.15), radius: 18, y: 10)
            Eyebrow(Self.eyebrow(playlist.kind), color: Theme.vermilion)
            Text(playlist.name)
                .font(.serif(32, weight: .semibold))
                .foregroundStyle(Theme.ink)
            if !playlist.description.isEmpty {
                Text(playlist.description)
                    .font(.serif(17))
                    .foregroundStyle(Theme.inkSoft)
            }
            if playlist.kind == .smart && !playlist.rules.isEmpty {
                RulesSummary(rules: playlist.rules)
            }
            Text(playlist.countText)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(Theme.inkSoft)
            if let album = playlist.album {
                AlbumCard(album: album, sync: playlist.albumSync, syncing: syncing) { sync() }
            }
            if removingItems {
                Label(
                    Self.removeHint(playlist.kind),
                    systemImage: "hand.tap"
                )
                .font(.subheadline)
                .foregroundStyle(Theme.ink)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(14)
                .background(Theme.vermilion.opacity(0.1), in: RoundedRectangle(cornerRadius: 14))
            } else if isActive {
                Label("Teraz prezentowane na ramce", systemImage: "photo.artframe")
                    .font(.headline)
                    .foregroundStyle(Theme.vermilion)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 15)
                    .background(Theme.vermilion.opacity(0.1), in: RoundedRectangle(cornerRadius: 14))
            } else {
                Button {
                    Task { await model.play(playlist) }
                } label: {
                    Label("Prezentuj na ramce", systemImage: "photo.artframe")
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(playlist.itemCount == 0)
            }
        }
    }

    private static func eyebrow(_ kind: PlaylistKind) -> String {
        switch kind {
        case .smart: "Playlista inteligentna"
        case .album: "Album iCloud"
        case .manual: "Playlista"
        }
    }

    private static func emptyMessage(_ kind: PlaylistKind) -> String {
        switch kind {
        case .manual: "Dodawaj dzieła przyciskiem „Dodaj do playlisty” w ich szczegółach."
        case .album: "Album jest pusty albo jeszcze się synchronizuje."
        case .smart: "Żadne dzieło nie spełnia reguł. Zmień je albo dodaj nowe obrazy z muzeów."
        }
    }

    private static func removeHint(_ kind: PlaylistKind) -> String {
        switch kind {
        case .smart:
            "Stuknij dzieło, aby usunąć je z playlisty. Nie wróci, choć pasuje do reguł; "
                + "przywrócisz je w menu „…”."
        case .album:
            "Stuknij zdjęcie, aby nie pokazywać go na ramce. W albumie zostaje; "
                + "przywrócisz je w menu „…”."
        case .manual: "Stuknij dzieło, aby usunąć je z playlisty."
        }
    }

    private func playlistBody() -> Playlist? {
        guard let summary = detail?.playlist else { return nil }
        return Playlist(
            id: summary.id, name: summary.name, description: summary.description, kind: summary.kind,
            rules: summary.rules, itemIds: detail?.itemIds ?? [], album: summary.album
        )
    }

    /// Syncs the album now and shows the result when it is done.
    private func sync() {
        Task {
            syncing = true
            defer { syncing = false }
            do {
                let jobID = try await model.backend.syncAlbum(playlistID: playlistID)
                let job = try await watchJob(jobID, backend: model.backend) { _ in }
                await load()
                await model.refreshPlaylists()
                if !job.error.isEmpty {
                    model.toast = "Nie udało się zsynchronizować albumu"
                } else {
                    model.toast = job.itemIds.isEmpty ? "Album bez zmian" : "Nowe zdjęcia: \(job.itemIds.count)"
                }
            } catch {
                model.show(error)
            }
        }
    }

    private func remove(_ item: ItemSummary) {
        Task {
            do {
                let updated = try await model.backend.removeFromPlaylist(id: playlistID, itemID: item.id)
                withAnimation(.snappy) {
                    detail = updated
                    if updated.items.isEmpty { removingItems = false }
                }
                await model.refreshPlaylists()
            } catch {
                model.show(error)
            }
        }
    }

    /// Brings back the works taken out of a smart or album playlist.
    private func restoreRemoved() {
        guard var playlist = playlistBody() else { return }
        playlist.rules.excludeIds = []
        Task {
            do {
                let updated = try await model.backend.savePlaylist(playlist)
                withAnimation(.snappy) { detail = updated }
                await model.refreshPlaylists()
            } catch {
                model.show(error)
            }
        }
    }

    private func load() async {
        do {
            detail = try await model.backend.playlist(id: playlistID)
        } catch {
            model.show(error)
        }
    }
}

/// An album playlist's source: the order it shows photos in and the last sync.
struct AlbumCard: View {
    let album: AlbumSource
    let sync: AlbumSync?
    let syncing: Bool
    let onSync: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                Image(systemName: "icloud")
                    .font(.title3)
                    .foregroundStyle(Theme.accent)
                VStack(alignment: .leading, spacing: 2) {
                    Text(sync.flatMap { $0.name.isEmpty ? nil : $0.name } ?? "Album udostępniony")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(Theme.ink)
                    Text(status)
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
                Spacer()
                Button(action: onSync) {
                    if syncing {
                        ProgressView()
                    } else {
                        Image(systemName: "arrow.triangle.2.circlepath")
                    }
                }
                .disabled(syncing)
                .accessibilityLabel("Synchronizuj z albumem")
            }
            if let error = sync?.error, !error.isEmpty {
                Label("Ostatnia synchronizacja nie powiodła się: \(error)", systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(Theme.bad)
            }
            Divider()
            HStack {
                Text("Kolejność").foregroundStyle(Theme.ink)
                Spacer()
                Text(album.order.title).foregroundStyle(Theme.inkSoft)
            }
            .font(.subheadline)
        }
        .padding(14)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(Theme.hairline))
    }

    private var status: String {
        guard let sync else { return "Jeszcze nie synchronizowano" }
        return "Synchronizacja \(When.ago(sync.at) ?? "niedawno") · co 30 minut"
    }
}
