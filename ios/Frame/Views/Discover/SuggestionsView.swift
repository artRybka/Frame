import SwiftUI

/// What Discover opens with: ideas for playlists in groups, then rows of
/// works the server picked for the frame, works like the ones the owner
/// likes, the theme of the day and the best on e-paper.
struct SuggestionsView: View {
    @Environment(AppModel.self) private var model
    @State private var rows: [SuggestionRow] = []
    @State private var themes: [ArtTheme] = []
    @State private var loading = false
    @Binding var path: NavigationPath

    private struct ThemeGroup: Identifiable {
        let name: String
        var themes: [ArtTheme]
        var id: String { name }
    }

    /// Groups in the server's order.
    private var groups: [ThemeGroup] {
        var found: [ThemeGroup] = []
        for theme in themes {
            let name = theme.group ?? "Motywy"
            if let index = found.firstIndex(where: { $0.name == name }) {
                found[index].themes.append(theme)
            } else {
                found.append(ThemeGroup(name: name, themes: [theme]))
            }
        }
        return found
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 28) {
            if rows.isEmpty && themes.isEmpty && !loading {
                EmptyStateView(
                    title: "Propozycje są w drodze",
                    message: "Serwer dobiera dzieła z muzeów w tle. Zajrzyj za chwilę.",
                    systemImage: "sparkles"
                )
            }
            ForEach(groups) { group in
                VStack(alignment: .leading, spacing: 12) {
                    Text(group.name)
                        .font(.serif(22, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                    // One row per group, so all groups and the rows of works
                    // below fit in a few screens.
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(alignment: .top, spacing: 12) {
                            ForEach(group.themes) { theme in
                                NavigationLink(value: theme) {
                                    ThemeCard(theme: theme) { await makePlaylist(theme) }
                                        .frame(width: 172)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.vertical, 2)
                    }
                    .scrollClipDisabled()
                }
            }
            ForEach(rows) { row in
                SuggestionRowView(row: row, theme: themes.first { $0.key == row.theme })
            }
        }
        .overlay(alignment: .top) {
            if loading && rows.isEmpty { ProgressView().padding(.top, 60) }
        }
        .task { await load() }
        .onChange(of: rows.first?.items.first?.id) { _, first in
            if LaunchRoute.screen == "detail", path.isEmpty, let first { path.append(first) }
        }
    }

    private func load() async {
        loading = true
        defer { loading = false }
        do {
            async let found = model.backend.suggestions()
            async let all = model.backend.themes()
            (rows, themes) = try await (found, all)
        } catch is CancellationError {
        } catch {
            model.show(error)
        }
    }

    private func makePlaylist(_ theme: ArtTheme) async {
        await ThemeActions.makePlaylist(theme, play: false, model: model)
        if let fresh = try? await model.backend.themes() { themes = fresh }
    }
}

/// Making a playlist from a theme, from a card or the theme's page.
@MainActor
enum ThemeActions {
    /// Makes (or finds) the theme's playlist; returns its id.
    @discardableResult
    static func makePlaylist(_ theme: ArtTheme, play: Bool, model: AppModel) async -> Int? {
        do {
            let made = try await model.backend.themePlaylist(key: theme.key, play: play)
            await model.refreshPlaylists()
            if play {
                model.toast = "Teraz prezentowane: \(made.playlist.name)"
                await model.refreshPlayer()
            } else if let jobID = made.jobId {
                model.toast = "Utworzono „\(made.playlist.name)”, pobieram dzieła z muzeów"
                Task {
                    let job = try? await watchJob(jobID, backend: model.backend) { _ in }
                    if let job { model.toast = "„\(made.playlist.name)”: dodano \(Names.works(job.done))" }
                    await model.refreshPlaylists()
                }
            } else {
                model.toast = "Playlista „\(made.playlist.name)” jest w Playlistach"
            }
            return made.playlist.id
        } catch {
            model.show(error)
            return nil
        }
    }
}

/// A theme as a card: a cover of four works, its name and a button that
/// makes it a playlist (or says it is one already).
struct ThemeCard: View {
    let theme: ArtTheme
    var make: () async -> Void
    @State private var making = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            cover
            VStack(alignment: .leading, spacing: 4) {
                Text(theme.name)
                    .font(.serif(15, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                Text(theme.description)
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
                Spacer(minLength: 4)
                HStack {
                    if theme.playlistId != nil {
                        Label("Masz", systemImage: "checkmark")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(Theme.good)
                    } else {
                        Button {
                            Task {
                                making = true
                                await make()
                                making = false
                            }
                        } label: {
                            HStack(spacing: 4) {
                                if making { ProgressView().controlSize(.mini) } else { Image(systemName: "plus") }
                                Text("Playlista")
                            }
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(Theme.accent)
                        }
                        .buttonStyle(.plain)
                        .disabled(making)
                    }
                    Spacer()
                    if let count = theme.count, count > 0 {
                        Text("\(count)")
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(Theme.inkSoft)
                    }
                }
            }
            .padding(10)
            .frame(maxHeight: .infinity, alignment: .top)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(Theme.hairline))
    }

    /// Four works side by side in two rows; plain paper where the catalogue
    /// has none yet.
    private var cover: some View {
        let works = theme.cover ?? []
        return Grid(horizontalSpacing: 2, verticalSpacing: 2) {
            ForEach(0 ..< 2, id: \.self) { row in
                GridRow {
                    ForEach(0 ..< 2, id: \.self) { column in
                        let index = row * 2 + column
                        Color.clear
                            .frame(height: 44)
                            .frame(maxWidth: .infinity)
                            .overlay {
                                if index < works.count {
                                    ArtImage(
                                        ref: works[index].thumb,
                                        fallback: works[index].thumbFallback,
                                        placeholder: works[index].item.summary.placeholderColor,
                                        maxPixel: 240
                                    )
                                } else {
                                    Theme.mat
                                }
                            }
                            .clipped()
                    }
                }
            }
        }
    }
}

/// One horizontal row of works.
struct SuggestionRowView: View {
    let row: SuggestionRow
    /// The theme behind the row, to browse further.
    var theme: ArtTheme?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(row.title)
                        .font(.serif(20, weight: .medium))
                        .foregroundStyle(Theme.ink)
                    if !row.subtitle.isEmpty {
                        Text(row.subtitle)
                            .font(.footnote)
                            .foregroundStyle(Theme.inkSoft)
                    }
                }
                Spacer()
                if let theme {
                    NavigationLink("Więcej", value: theme)
                        .font(.subheadline.weight(.semibold))
                }
            }
            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(alignment: .top, spacing: 14) {
                    ForEach(row.items) { remote in
                        NavigationLink(value: remote.id) {
                            ArtCard(item: remote.item.summary, ref: remote.thumb)
                                .frame(width: 150)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.vertical, 4)
            }
            .scrollClipDisabled()
        }
    }
}

/// A theme browsed page by page, from the museums (or the catalogue), with
/// buttons that make it a playlist.
struct ThemeView: View {
    @Environment(AppModel.self) private var model
    let theme: ArtTheme
    @State private var items: [RemoteItem] = []
    @State private var page = 0
    @State private var more = true
    @State private var loading = false
    @State private var playlistID: Int?
    @State private var busy = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(theme.description)
                    .font(.serif(17))
                    .foregroundStyle(Theme.inkSoft)
                actions
                MasonryGrid(items: items.map(\.item.summary)) { summary in
                    NavigationLink(value: summary.id) {
                        ArtCard(item: summary, ref: items.first { $0.id == summary.id }?.thumb)
                    }
                    .buttonStyle(.plain)
                }
                if more {
                    Button {
                        Task { await loadMore() }
                    } label: {
                        HStack(spacing: 8) {
                            if loading { ProgressView().controlSize(.small) }
                            Text(items.isEmpty ? "Wczytuję…" : "Więcej")
                        }
                        .font(.subheadline.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(Theme.card, in: RoundedRectangle(cornerRadius: 12))
                        .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Theme.hairline))
                    }
                    .disabled(loading)
                }
            }
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 32)
        }
        .background(Theme.paper)
        .navigationTitle(theme.name)
        .navigationBarTitleDisplayMode(.inline)
        .task {
            playlistID = theme.playlistId
            if items.isEmpty { await loadMore() }
        }
    }

    private var actions: some View {
        HStack(spacing: 10) {
            Button {
                Task { await make(play: true) }
            } label: {
                Label("Graj na ramce", systemImage: "play.fill")
            }
            .buttonStyle(PrimaryButtonStyle())
            if playlistID == nil {
                Button {
                    Task { await make(play: false) }
                } label: {
                    Label("Utwórz playlistę", systemImage: "plus")
                }
                .buttonStyle(SecondaryButtonStyle())
            } else {
                Label("Masz tę playlistę", systemImage: "checkmark")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Theme.good)
                    .frame(maxWidth: .infinity)
            }
        }
        .disabled(busy)
    }

    private func make(play: Bool) async {
        busy = true
        defer { busy = false }
        if let id = await ThemeActions.makePlaylist(theme, play: play, model: model) { playlistID = id }
    }

    private func loadMore() async {
        guard !loading else { return }
        loading = true
        defer { loading = false }
        do {
            let found = try await model.backend.themePage(key: theme.key, page: page + 1)
            let known = Set(items.map(\.id))
            items += found.items.filter { !known.contains($0.id) }
            page += 1
            more = found.more
        } catch {
            model.show(error)
        }
    }
}
