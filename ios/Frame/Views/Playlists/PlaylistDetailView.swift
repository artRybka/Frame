import SwiftUI

struct PlaylistDetailView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let playlistID: Int
    @State private var editing: Playlist?
    @State private var confirmDelete = false
    /// Tapping a work takes it out of the playlist instead of opening it.
    @State private var removingItems = false
    @State private var syncing = false
    /// A new order asked, until the works come back in it.
    @State private var sorting = false
    /// "Prezentuj na ramce" asked, until the playlist plays.
    @State private var starting = false
    /// The first load failed: a retry instead of the skeleton.
    @State private var failed = false
    /// How far the page is scrolled, for the glow at the top.
    @State private var scrolled: CGFloat = 0
    /// "Kreatywny restaurator" for the owner: the works under 1600 px the
    /// batch would draw; nil for others, an album, or an older server.
    @State private var restorer: RestorerState?
    @State private var askingRestore = false
    @State private var restoring = false

    /// The works as last loaded; nil until the first load.
    private var detail: PlaylistDetail? { model.playlistDetails[playlistID] }
    /// The header shows at once from the list's tile while the works load.
    private var summary: PlaylistSummary? { detail?.playlist ?? model.playlists.first { $0.id == playlistID } }
    private var isActive: Bool { model.settings?.playlistId == playlistID }
    private var isAlbum: Bool { summary?.kind == .album }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                if let summary {
                    header(summary)
                    if summary.itemCount > 0 {
                        gridHeader(summary)
                            .padding(.top, 4)
                            .padding(.bottom, -8)
                    }
                } else {
                    HeaderSkeleton()
                }
                if let detail {
                    works(detail)
                        .transition(.opacity)
                } else if failed {
                    Button("Spróbuj ponownie", systemImage: "arrow.clockwise") {
                        Task { await load() }
                    }
                    .buttonStyle(ActionButtonStyle(wide: false))
                    .frame(maxWidth: .infinity)
                    .padding(.top, 20)
                } else if (summary?.itemCount ?? 1) > 0 {
                    GridSkeleton(count: min(summary?.itemCount ?? 6, 6))
                        .transition(.opacity)
                }
            }
            // Full width from the first frame, also with nothing loaded yet.
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 40)
            .animation(.easeOut(duration: 0.3), value: detail == nil)
        }
        .glowLift($scrolled)
        // Its cover's four works glow at the top, as its card does in Playlisty.
        .paperPage(glow: summary?.coverColors ?? [], lift: scrolled, colours: 4)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                if removingItems {
                    Button("Gotowe") { withAnimation { removingItems = false } }
                        .fontWeight(.semibold)
                } else if summary?.isMine == false {
                    // Someone else's shared playlist: played, not changed.
                    if let name = summary?.ownerName, !name.isEmpty {
                        Text("Playlista: \(name)")
                            .font(.caption)
                            .foregroundStyle(Theme.inkSoft)
                    }
                } else {
                    Menu {
                        Button("Edytuj", systemImage: "slider.horizontal.3") { editing = playlistBody() }
                            .disabled(detail == nil)
                        if isAlbum {
                            Button("Synchronizuj z albumem", systemImage: "arrow.triangle.2.circlepath") { sync() }
                                .disabled(syncing)
                        }
                        if !isAlbum, let sort = summary?.sort {
                            sortMenu(sort)
                        }
                        if let restorer { restorerButton(restorer) }
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
                        if summary?.isFavorites != true {
                            // "Ulubione" is always there, even with no hearts.
                            Button("Usuń playlistę", systemImage: "trash", role: .destructive) { confirmDelete = true }
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                    .confirmationDialog(
                        restorer.map { "Odnowić \(Names.works($0.items))?" } ?? "",
                        isPresented: $askingRestore,
                        titleVisibility: .visible,
                        presenting: restorer
                    ) { asked in
                        Button("Odnów") { Task { await restore(asked) } }
                        Button("Anuluj", role: .cancel) {}
                    } message: { asked in
                        Text(
                            "Model graficzny Google przerysuje dzieła tej playlisty w niskiej rozdzielczości do ok. 2000 px. Około \(Money.usd(asked.usd)) w pakietach Google (połowa zwykłej ceny), w ciągu doby. „Przywróć zdjęcie muzeum” na karcie cofa zmianę."
                        )
                    }
                    .confirmationDialog("Usunąć playlistę?", isPresented: $confirmDelete, titleVisibility: .visible) {
                        Button("Usuń", role: .destructive) {
                            Task {
                                try? await model.backend.deletePlaylist(id: playlistID)
                                model.playlistDetails[playlistID] = nil
                                await model.refreshPlaylists()
                                dismiss()
                            }
                        }
                    }
                }
            }
        }
        .task(id: [playlistID, model.libraryRevision]) { await load() }
        .sheet(item: $editing, onDismiss: { Task { await load() } }) { playlist in
            PlaylistEditorView(playlist: playlist)
        }
    }

    @ViewBuilder
    private func works(_ detail: PlaylistDetail) -> some View {
        if !detail.items.isEmpty {
            VStack(spacing: 22) {
                MasonryGrid(items: detail.items) { item in card(item) }
                if detail.playlist.kind == .smart, detail.playlist.itemCount > detail.items.count {
                    // The server lists a part of a very large playlist.
                    Text("Widać \(Names.works(detail.items.count)) z \(detail.playlist.itemCount).")
                        .font(.footnote)
                        .foregroundStyle(Theme.inkSoft)
                        .frame(maxWidth: .infinity)
                }
            }
        } else {
            EmptyStateView(
                title: "Pusta playlista",
                message: Self.emptyMessage(detail.playlist)
            )
        }
    }

    /// Hearts only where they tell something: in Ulubione (or any list of
    /// favourites alone) every tile would wear one.
    private var hearts: Bool {
        !(detail?.items.allSatisfy(\.favorite) ?? false)
    }

    @ViewBuilder
    private func card(_ item: ItemSummary) -> some View {
        if removingItems {
            Button { remove(item) } label: {
                // The minus takes the heart's corner: what is yours.
                ArtCard(item: item, showsFavorite: false)
                    .overlay(alignment: .topTrailing) {
                        CornerMark(systemImage: "minus")
                            .offset(x: CornerMark.overhang, y: -CornerMark.overhang)
                    }
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Usuń z playlisty: \(item.title)")
        } else {
            NavigationLink(value: item.id) { ArtCard(item: item, showsFavorite: false) }
                .buttonStyle(.plain)
                .contextMenu {
                    QueueButton(itemID: item.id)
                    Button("Usuń z playlisty", systemImage: "minus.circle", role: .destructive) { remove(item) }
                }
                .overlay(alignment: .topTrailing) {
                    if hearts { LikeHeart(item: item) }
                }
        }
    }

    private func header(_ playlist: PlaylistSummary) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Collage(itemIDs: playlist.coverItemIds, title: playlist.name, spacing: 3, opensWorks: true)
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
            // Only rules that say more than the name; the count and the
            // order head the grid below (Mateusz 2026-11-13, variant B).
            if playlist.kind == .smart && RulesSummary.hasChips(playlist.rules, name: playlist.name) {
                RulesSummary(rules: playlist.rules, name: playlist.name)
            }
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
                // A state, not a button: outlined in vermilion, like a label button.
                Label("Teraz prezentowane na ramce", systemImage: "photo.fill")
                    .labelStyle(ActionLabelStyle())
                    .foregroundStyle(Theme.vermilion)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 15)
                    .background(LabelButton.shape.strokeBorder(Theme.vermilion, lineWidth: 1))
            } else {
                Button {
                    Task {
                        starting = true
                        defer { starting = false }
                        await model.play(playlist)
                    }
                } label: {
                    Label {
                        Text("Prezentuj na ramce")
                    } icon: {
                        if starting {
                            ProgressView().tint(Theme.paper)
                        } else {
                            Image(systemName: "photo.fill")
                        }
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(playlist.itemCount == 0 || starting)
                .sensoryFeedback(.impact(weight: .medium), trigger: starting) { _, now in now }
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

    private static func emptyMessage(_ playlist: PlaylistSummary) -> String {
        if playlist.isFavorites { return "Stuknij serduszko przy dziele, a trafi tutaj." }
        return switch playlist.kind {
        case .manual: "Dodawaj dzieła w edycji playlisty albo przyciskiem „Dodaj do playlisty” w ich szczegółach."
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

    /// Over the works: how many, and in what order. The order opens the
    /// same choice as "Sortuj" in the "…" menu; on someone else's playlist,
    /// and on an album, it only tells.
    private func gridHeader(_ playlist: PlaylistSummary) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text(playlist.countText)
                .font(.serif(19, weight: .semibold))
                .foregroundStyle(Theme.ink)
                .contentTransition(.numericText())
            Spacer(minLength: 0)
            if playlist.kind != .album, let sort = playlist.sort, let label = sort.shortCaption {
                if playlist.isMine {
                    Menu {
                        sortOptions(sort)
                    } label: {
                        SortChip(text: label, busy: sorting, menu: true)
                    }
                    .disabled(detail == nil || sorting)
                    .accessibilityLabel("Sortuj: \(sort.caption ?? label)")
                } else {
                    SortChip(text: label, busy: false, menu: false)
                        .accessibilityLabel(sort.caption ?? label)
                }
            }
        }
    }

    /// "Sortuj" in the "…" menu: the key, then which way round
    /// (Mateusz 2026-11-12: "ustawienie sortowania dajmy w menu „…”").
    private func sortMenu(_ sort: PlaylistSort) -> some View {
        Menu {
            sortOptions(sort)
        } label: {
            Label("Sortuj", systemImage: "arrow.up.arrow.down")
        }
        .disabled(detail == nil || sorting)
    }

    @ViewBuilder
    private func sortOptions(_ sort: PlaylistSort) -> some View {
        Picker("Sortuj według", selection: Binding(
            get: { sort.known },
            set: { key in if let key, key != sort.known { setSort(PlaylistSort(key)) } }
        )) {
            ForEach(PlaylistSort.Key.allCases) { key in
                Label(key.title, systemImage: key.systemImage).tag(Optional(key))
            }
        }
        .pickerStyle(.inline)
        if let key = sort.known {
            Picker("Kolejność", selection: Binding(
                get: { sort.reverse },
                set: { reverse in if reverse != sort.reverse { setSort(PlaylistSort(key, reverse: reverse)) } }
            )) {
                Text(key.direction(reverse: false)).tag(false)
                Text(key.direction(reverse: true)).tag(true)
            }
            .pickerStyle(.inline)
        }
    }

    /// Asks the server for the new order: the grid, and the frame's next
    /// pictures when it does not shuffle, follow it.
    private func setSort(_ sort: PlaylistSort) {
        Task {
            sorting = true
            defer { sorting = false }
            do {
                let updated = try await model.backend.sortPlaylist(id: playlistID, sort: sort)
                withAnimation(.snappy) { model.playlistDetails[playlistID] = updated }
                await model.refreshPlaylists()
            } catch {
                model.show(error)
            }
        }
    }

    private func playlistBody() -> Playlist? {
        guard let summary = detail?.playlist else { return nil }
        return Playlist(
            id: summary.id, name: summary.name, description: summary.description, kind: summary.kind,
            rules: summary.rules, itemIds: detail?.itemIds ?? [], album: summary.album,
            theme: summary.theme, shared: summary.shared, limit: summary.limit
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
                    model.notices.fail("Nie udało się zsynchronizować albumu", job.error)
                } else {
                    model.notices.done(job.itemIds.isEmpty ? "Album bez zmian" : "Nowe zdjęcia: \(job.itemIds.count)")
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
                    model.playlistDetails[playlistID] = updated
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
                withAnimation(.snappy) { model.playlistDetails[playlistID] = updated }
                await model.refreshPlaylists()
            } catch {
                model.show(error)
            }
        }
    }

    private func load() async {
        failed = false
        do {
            model.playlistDetails[playlistID] = try await model.backend.playlist(id: playlistID)
        } catch {
            if Task.isCancelled { return }
            failed = detail == nil
            model.show(error)
        }
        if model.isOwner, !isAlbum, summary?.isMine != false {
            restorer = await model.restorerState(playlistID: playlistID)
        }
    }

    /// "Kreatywny restaurator" in the "…" menu, for the owner (Mateusz
    /// 2026-11-13): the playlist's works under 1600 px drawn again by
    /// Google's image model, in its batches (half the price, within a day),
    /// as the favourites are from Konfiguracja → Gemini.
    private func restorerButton(_ state: RestorerState) -> some View {
        Button {
            askingRestore = true
        } label: {
            Label {
                Text("Kreatywny restaurator")
                Text(restorerLine(state))
            } icon: {
                Image(systemName: LowRes.restoredSymbol)
            }
        }
        .disabled(!state.enabled || state.items == 0 || restoring)
    }

    private func restorerLine(_ state: RestorerState) -> String {
        if !state.enabled { return "Brak klucza Gemini" }
        if restoring { return "Wysyłam do Google…" }
        if state.items > 0 { return "\(Names.works(state.items)) w niskiej rozdzielczości" }
        if state.waiting > 0 { return "Czeka w pakietach Google" }
        return "Nie ma czego odnawiać"
    }

    private func restore(_ asked: RestorerState) async {
        restoring = true
        defer { restoring = false }
        if let fresh = await model.restorePlaylist(id: playlistID, asked: asked.items) {
            restorer = fresh
        }
    }
}

/// The playlist's order over its grid: a quiet capsule, like a rule chip,
/// with a chevron when it opens the choice.
private struct SortChip: View {
    let text: String
    let busy: Bool
    let menu: Bool

    var body: some View {
        HStack(spacing: 6) {
            if busy {
                ProgressView().controlSize(.mini)
            } else {
                Image(systemName: "arrow.up.arrow.down")
                    .imageScale(.small)
            }
            Text(text)
                .lineLimit(1)
                .contentTransition(.opacity)
            if menu {
                Image(systemName: "chevron.down")
                    .font(.caption2.weight(.semibold))
            }
        }
        .font(.footnote.weight(.medium))
        .foregroundStyle(Theme.inkSoft)
        .padding(.horizontal, 11)
        .padding(.vertical, 6)
        .background(Theme.mat.opacity(0.7), in: Capsule())
        .contentShape(Capsule())
    }
}

/// Stand-in for a playlist's header when it opens before the list loaded.
private struct HeaderSkeleton: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(Theme.mat)
                .aspectRatio(1.6, contentMode: .fit)
            Capsule().fill(Theme.mat).frame(width: 120, height: 10)
            Capsule().fill(Theme.mat).frame(width: 220, height: 26)
        }
        .breathing()
        .accessibilityHidden(true)
    }
}

/// Where a playlist's works will be: quiet cards in two columns, breathing
/// slowly, that give way to the works as they load.
struct GridSkeleton: View {
    var count = 6
    /// Proportions that read as a mix of portraits and landscapes.
    private static let aspects: [CGFloat] = [0.78, 1.3, 1.0, 0.72, 1.45, 0.9]

    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            ForEach(0 ..< 2, id: \.self) { column in
                VStack(spacing: 16) {
                    ForEach(Array(stride(from: column, to: count, by: 2)), id: \.self) { index in
                        card(Self.aspects[index % Self.aspects.count])
                    }
                }
                .frame(maxWidth: .infinity, alignment: .top)
            }
        }
        .breathing()
        .accessibilityElement()
        .accessibilityLabel("Wczytuję dzieła")
    }

    private func card(_ aspect: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            RoundedRectangle(cornerRadius: 6, style: .continuous)
                .fill(Theme.mat)
                .aspectRatio(aspect, contentMode: .fit)
            VStack(alignment: .leading, spacing: 5) {
                Capsule().fill(Theme.mat).frame(height: 11).padding(.trailing, 24)
                Capsule().fill(Theme.mat).frame(width: 70, height: 8)
            }
        }
    }
}

private struct Breathing: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var shown = false
    @State private var dim = false

    func body(content: Content) -> some View {
        content
            // Fades in only when the load takes a moment, so a quick one
            // goes straight from the header to the works without a flash.
            .opacity(shown ? 1 : 0)
            .opacity(dim ? 0.55 : 1)
            .onAppear {
                withAnimation(.easeIn(duration: 0.3).delay(0.2)) { shown = true }
                guard !reduceMotion else { return }
                withAnimation(.easeInOut(duration: 1.1).repeatForever(autoreverses: true).delay(0.5)) { dim = true }
            }
    }
}

extension View {
    /// A placeholder's slow pulse while something loads.
    func breathing() -> some View { modifier(Breathing()) }
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
                    .foregroundStyle(Theme.inkSoft)
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
