import SwiftUI

/// "Do playlisty" (the button between the heart and "…" on a work's card and
/// its study): the person's manual playlists with their covers, ticked where
/// the work already is. A tap adds it or takes it out at once and the sheet
/// stays, so several can be ticked in one go; "Nowa playlista…" turns into a
/// name field in place and makes one with the work in it
/// (Mateusz 2026-11-13: the old list that closed on the first tap was hard
/// to use).
struct AddToPlaylistSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let item: Item
    /// Run first, e.g. to save the crop edited for it; false stops the adding.
    var beforeAdding: () async -> Bool = { true }

    /// Playlist id -> the copy of the work it holds (maybe another source's);
    /// nil until the server answered.
    @State private var holding: [Int: String]?
    /// The playlists as the server last returned them here: their counts and
    /// covers after a tap, before Playlisty is asked again on closing.
    @State private var fresh: [Int: PlaylistSummary] = [:]
    /// Playlists whose tap is still on its way to the server.
    @State private var busy: Set<Int> = []
    @State private var naming = false
    @State private var newName = ""
    @State private var creating = false
    @State private var changed = false
    /// Goes up with each tap on a playlist, for the tap's feel.
    @State private var taps = 0
    @FocusState private var nameFocused: Bool

    private var manual: [PlaylistSummary] {
        model.playlists.filter { $0.kind == .manual && $0.isMine }.map { fresh[$0.id] ?? $0 }
    }

    private var trimmedName: String { newName.trimmingCharacters(in: .whitespacesAndNewlines) }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    WorkLine(item: item)
                        .listRowBackground(Color.clear)
                        .listRowInsets(EdgeInsets(top: 0, leading: 4, bottom: 4, trailing: 4))
                }
                Section {
                    newRow
                    ForEach(manual) { row($0) }
                } footer: {
                    Text("Dotknięcie dodaje dzieło albo je zabiera. Zmiana zapisuje się od razu.")
                }
            }
            .listSectionSpacing(.compact)
            .navigationTitle("Do playlisty")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Gotowe", systemImage: "checkmark") { dismiss() }
                }
            }
        }
        .presentationDetents([.medium, .large])
        .sensoryFeedback(.selection, trigger: taps)
        .task { await loadHolding() }
        .onAppear {
            if manual.isEmpty || LaunchRoute.sheet == "playlists-new" { startNaming() }
            if LaunchRoute.sheet == "playlists-new" { newName = "Do przedpokoju" }
        }
        .onDisappear {
            // Playlisty's counts and covers as they are now.
            if changed { Task { await model.refreshPlaylists() } }
        }
    }

    // MARK: Rows

    @ViewBuilder
    private var newRow: some View {
        if naming {
            HStack(spacing: 14) {
                NewCover()
                TextField("Nazwa, np. Do sypialni", text: $newName)
                    .focused($nameFocused)
                    .submitLabel(.done)
                    .onSubmit { Task { await create() } }
                    .disabled(creating)
                Button {
                    Task { await create() }
                } label: {
                    ZStack {
                        Text("Utwórz").fontWeight(.semibold).opacity(creating ? 0 : 1)
                        if creating { ProgressView().tint(Theme.paper) }
                    }
                    .font(.subheadline)
                    .foregroundStyle(Theme.paper)
                    .padding(.horizontal, 14)
                    .frame(height: 34)
                    .background(Theme.ink, in: Capsule())
                    .opacity(trimmedName.isEmpty ? 0.35 : 1)
                }
                .buttonStyle(.plain)
                .disabled(trimmedName.isEmpty || creating)
            }
            .padding(.vertical, 2)
        } else {
            Button(action: startNaming) {
                HStack(spacing: 14) {
                    NewCover()
                    Text("Nowa playlista…").foregroundStyle(Theme.ink)
                    Spacer()
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .padding(.vertical, 2)
        }
    }

    private func row(_ playlist: PlaylistSummary) -> some View {
        let held = holding?[playlist.id] != nil
        return Button {
            Task { await toggle(playlist) }
        } label: {
            HStack(spacing: 14) {
                Collage(itemIDs: playlist.coverItemIds, title: playlist.name, spacing: 1.5)
                    .frame(width: 52, height: 52)
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                VStack(alignment: .leading, spacing: 2) {
                    Text(playlist.name)
                        .foregroundStyle(Theme.ink)
                        .lineLimit(2)
                    Text(held ? "\(Names.works(playlist.itemCount)) · jest tutaj" : Names.works(playlist.itemCount))
                        .font(.subheadline)
                        .foregroundStyle(held ? Theme.ink : Theme.inkSoft)
                        .contentTransition(.numericText())
                }
                Spacer(minLength: 8)
                Tick(on: held, loading: holding == nil || busy.contains(playlist.id))
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(.vertical, 2)
        .disabled(holding == nil || busy.contains(playlist.id))
        .accessibilityLabel(playlist.name)
        .accessibilityValue(held ? "Jest w playliście" : "Nie ma w playliście")
        .accessibilityAddTraits(held ? .isSelected : [])
    }

    // MARK: Actions

    private func startNaming() {
        withAnimation(.snappy) { naming = true }
        nameFocused = true
    }

    private func loadHolding() async {
        do {
            let found = try await model.backend.playlistsHolding(itemID: item.id)
            holding = Dictionary(found.map { ($0.playlistId, $0.itemId) }, uniquingKeysWith: { first, _ in first })
        } catch {
            // An older server: nothing ticked, a tap still adds.
            holding = [:]
        }
    }

    private func toggle(_ playlist: PlaylistSummary) async {
        guard var now = holding, !busy.contains(playlist.id) else { return }
        let held = now[playlist.id]
        if held == nil, !(await beforeAdding()) { return }
        busy.insert(playlist.id)
        taps += 1
        defer { busy.remove(playlist.id) }
        // At once; back as it was if the server says no.
        now[playlist.id] = held == nil ? item.id : nil
        withAnimation(.snappy) { holding = now }
        do {
            let detail: PlaylistDetail
            if let held {
                detail = try await model.backend.removeFromPlaylist(id: playlist.id, itemID: held)
            } else {
                detail = try await model.backend.addToPlaylist(id: playlist.id, itemIDs: [item.id])
            }
            withAnimation(.snappy) { fresh[playlist.id] = detail.playlist }
            changed = true
            if held == nil {
                // Another copy of the work may have been there already.
                await loadHolding()
            }
        } catch {
            withAnimation(.snappy) { holding?[playlist.id] = held }
            model.show(error)
        }
    }

    private func create() async {
        let name = trimmedName
        guard !name.isEmpty, !creating else { return }
        guard await beforeAdding() else { return }
        creating = true
        defer { creating = false }
        do {
            let detail = try await model.backend.savePlaylist(Playlist(name: name, kind: .manual, itemIds: [item.id]))
            await model.refreshPlaylists()
            withAnimation(.snappy) {
                fresh[detail.playlist.id] = detail.playlist
                holding?[detail.playlist.id] = item.id
                naming = false
                newName = ""
            }
            changed = true
            model.notices.done("Utworzono „\(name)”")
        } catch { model.show(error) }
    }
}

/// The work being added, small, above the playlists.
private struct WorkLine: View {
    let item: Item

    var body: some View {
        HStack(spacing: 12) {
            ArtImage(
                ref: .thumb(item.id), fallback: URL(string: item.thumbUrl).map { .url($0) },
                maxPixel: 160, subjectFocus: true
            )
            .frame(width: 38, height: 48)
            .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
            .shadow(color: .black.opacity(0.18), radius: 1.5, y: 1)
            VStack(alignment: .leading, spacing: 1) {
                Text(item.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(2)
                Text([item.artist, item.dateText].filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(.footnote)
                    .foregroundStyle(Theme.inkSoft)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
        }
        .accessibilityElement(children: .combine)
    }
}

/// "Nowa playlista…": an empty cover with a plus.
private struct NewCover: View {
    var body: some View {
        RoundedRectangle(cornerRadius: 10, style: .continuous)
            .strokeBorder(Theme.inkSoft.opacity(0.55), style: StrokeStyle(lineWidth: 1.5, dash: [4, 3]))
            .frame(width: 52, height: 52)
            .overlay {
                Image(systemName: "plus")
                    .font(.system(size: 20, weight: .medium))
                    .foregroundStyle(Theme.inkSoft)
            }
            .accessibilityHidden(true)
    }
}

/// The tick at a playlist's end: filled where the work is.
private struct Tick: View {
    let on: Bool
    var loading = false

    var body: some View {
        ZStack {
            Circle()
                .strokeBorder(Theme.inkSoft.opacity(on ? 0 : 0.45), lineWidth: 1.6)
            Circle()
                .fill(Theme.ink)
                .scaleEffect(on ? 1 : 0.4)
                .opacity(on ? 1 : 0)
            Image(systemName: "checkmark")
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(Theme.paper)
                .scaleEffect(on ? 1 : 0.4)
                .opacity(on ? 1 : 0)
        }
        .frame(width: 26, height: 26)
        .opacity(loading && !on ? 0.4 : 1)
        .accessibilityHidden(true)
    }
}
