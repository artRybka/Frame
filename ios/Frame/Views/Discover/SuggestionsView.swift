import SwiftUI

/// What Discover opens with: the work of the day, ideas for playlists in
/// groups ("Dziś dla Ciebie" opens with the theme of the day, "Bo lubisz" has
/// a card for each artist the owner likes), the owner's works not shown for
/// long and, last, the works of the day and those with a study ("Studia
/// dzieł").
///
/// The last ones loaded show at once (also after a launch) while fresh ones
/// load, and only the cards and works on screen fetch their pictures.
struct SuggestionsView: View {
    @Environment(AppModel.self) private var model
    @State private var loading = false
    @Binding var path: NavigationPath

    private var rows: [SuggestionRow] { model.suggestionRows ?? [] }
    /// "Motyw dnia" is a card of "Dziś dla Ciebie"; "Dla Ciebie" (still the
    /// cover of Propozycje in Playlisty) and "Nowe w katalogu" are not shown,
    /// nor the rows "Bo lubisz: …" of older servers once they send its cards.
    private var otherRows: [SuggestionRow] {
        let liked = themes.contains { $0.group == DiscoverLayout.likes }
        return rows.filter { row in
            !["theme", "for-you", "new"].contains(row.key) && !(liked && row.key.hasPrefix("like:"))
        }
    }
    private var themes: [ArtTheme] { DiscoverLayout.themes(model.themes ?? [], rows: rows) }

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
        LazyVStack(alignment: .leading, spacing: 28) {
            if let daily = model.daily { DailyTile(work: daily) }
            if rows.isEmpty && themes.isEmpty && !loading {
                EmptyStateView(
                    title: "Propozycje są w drodze",
                    message: "Serwer dobiera dzieła z muzeów w tle. Zajrzyj za chwilę.",
                    systemImage: "sparkles"
                )
            }
            ForEach(groups) { group in
                VStack(alignment: .leading, spacing: 12) {
                    NavigationLink(value: ThemeGroupRoute(name: group.name)) {
                        SeeAllHeader(title: group.name, size: 22, weight: .semibold)
                    }
                    .buttonStyle(.plain)
                    // One row per group, so all groups and the rows of works
                    // below fit in a few screens.
                    ScrollView(.horizontal, showsIndicators: false) {
                        LazyHStack(alignment: .top, spacing: 12) {
                            ForEach(group.themes) { theme in
                                NavigationLink(value: theme) {
                                    ThemeCard(theme: theme) {
                                        _ = await ThemeActions.makePlaylist(theme, play: false, model: model)
                                    }
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
            ForEach(otherRows) { row in rowView(row) }
            if let studies = model.studyList, !studies.isEmpty { StudyRow(studies: studies).id("studies") }
        }
        // Full width while it is still empty, so the spinner is in the middle.
        .pageWidth()
        .overlay(alignment: .top) {
            if loading && rows.isEmpty { ProgressView().padding(.top, 60) }
        }
        .task {
            loading = true
            await model.refreshDiscover()
            loading = false
        }
        .onChange(of: rows.first?.items.first?.id) { _, first in
            if ["detail", "original"].contains(LaunchRoute.screen), path.isEmpty, let first { path.append(first) }
        }
        .onChange(of: groups.first?.name, initial: true) { _, first in
            if LaunchRoute.screen == "discover-group", path.isEmpty, let first {  // CI screenshots
                path.append(ThemeGroupRoute(name: first))
            }
        }
        .onChange(of: model.daily?.day) { _, day in
            if LaunchRoute.screen == "daily", path.isEmpty, day != nil { path.append(DailyRoute(day: nil)) }  // CI screenshots
        }
    }

    private func rowView(_ row: SuggestionRow) -> some View {
        SuggestionRowView(row: row, theme: (model.themes ?? []).first { $0.key == row.theme })
    }
}

/// How Propozycje lays out the themes and rows the server sends.
enum DiscoverLayout {
    static let weekly = "Dziś dla Ciebie"
    /// The same group as older servers name it.
    static let oldWeekly = "Na ten tydzień"
    static let likes = "Bo lubisz"
    /// Groups made for this week or for this owner, not lasting themes.
    static let ownGroups: Set<String> = [weekly, likes]

    /// The theme of the day as a card, "Motyw dnia: …" with the day's works
    /// on its cover (by different artists where it can); it opens the theme.
    static func dayCard(_ row: SuggestionRow, themes: [ArtTheme]) -> ArtTheme? {
        guard let key = row.theme else { return nil }
        let base = themes.first { $0.key == key && $0.group != weekly }
        var cover: [RemoteItem] = []
        for remote in row.items where !cover.contains(where: { $0.item.artist == remote.item.artist }) {
            cover.append(remote)
            if cover.count == 4 { break }
        }
        for remote in row.items where cover.count < 4 && !cover.contains(remote) {
            cover.append(remote)
        }
        return ArtTheme(
            key: key,
            name: row.title,
            description: row.subtitle,
            group: weekly,
            count: base?.count,
            cover: cover.isEmpty ? base?.cover : cover,
            playlistId: base?.playlistId,
            rules: base?.rules
        )
    }

    /// The themes as Propozycje shows them: the theme of the day first in
    /// "Dziś dla Ciebie" (the group made for it when the week has no themes).
    static func themes(_ themes: [ArtTheme], rows: [SuggestionRow]) -> [ArtTheme] {
        let themes = themes.map { theme in
            var theme = theme
            if theme.group == oldWeekly { theme.group = weekly }
            return theme
        }
        guard let row = rows.first(where: { $0.key == "theme" }), let card = dayCard(row, themes: themes) else {
            return themes
        }
        var all = themes
        all.insert(card, at: all.firstIndex { $0.group == weekly } ?? 0)
        return all
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
            // The card says "Masz" from now on.
            if let fresh = try? await model.backend.themes() { model.themes = fresh }
            let name = made.playlist.name
            if play {
                model.notices.done("Teraz prezentowane: \(name)")
                await model.refreshPlayer()
            } else if let jobID = made.jobId {
                let card = model.notices.begin("Utworzono „\(name)”, pobieram dzieła z muzeów", background: true)
                Task {
                    do {
                        let job = try await watchJob(jobID, backend: model.backend) { job in
                            guard job.total > 0 else { return }
                            let seen = job.done + job.failed
                            model.notices.update(
                                card, fraction: Double(seen) / Double(job.total), count: "\(seen) z \(job.total)"
                            )
                        }
                        model.notices.end(card, .done, "„\(name)”: dodano \(Names.works(job.done))")
                    } catch {
                        model.notices.fail(error, in: card)
                    }
                    await model.refreshPlaylists()
                }
            } else {
                model.notices.info("Playlista „\(name)” jest w Playlistach")
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
                Text(Names.theme(theme))
                    .font(.serif(15, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(2, reservesSpace: true)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                Text(theme.description)
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .lineLimit(2, reservesSpace: true)
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
                                        maxPixel: 240,
                                        subjectFocus: true
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

/// "Studia dzieł": every study of the day and every study asked for, the
/// last written first, as cards to swipe through; each opens its page.
struct StudyRow: View {
    let studies: [StudyBrief]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                NavigationLink(value: StudiesRoute()) {
                    SeeAllHeader(title: "Studia dzieł", size: 22, weight: .semibold)
                }
                .buttonStyle(.plain)
                Text("Codzienne i zamówione studia dzieł")
                    .font(.footnote)
                    .foregroundStyle(Theme.inkSoft)
            }
            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(alignment: .top, spacing: 12) {
                    ForEach(studies) { study in
                        NavigationLink(value: study.route) {
                            StudyCard(study: study).frame(width: 172)
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
}

/// Opens every study and work of the day as a grid ("Studia dzieł" ›).
struct StudiesRoute: Hashable {}

/// Every study and work of the day, two cards to a row, the last written
/// first; each opens its page.
struct StudiesGridView: View {
    @Environment(AppModel.self) private var model

    private let columns = [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)]

    var body: some View {
        let studies = model.studyList ?? []
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Codzienne i zamówione studia dzieł")
                    .font(.serif(17))
                    .foregroundStyle(Theme.inkSoft)
                LazyVGrid(columns: columns, alignment: .leading, spacing: 12) {
                    ForEach(studies) { study in
                        NavigationLink(value: study.route) { StudyCard(study: study) }
                            .buttonStyle(.plain)
                    }
                }
                if studies.isEmpty {
                    EmptyStateView(
                        title: "Nie ma jeszcze studiów",
                        message: "Tu trafia każde studium dnia i każde zamówione na karcie dzieła.",
                        systemImage: "sparkles"
                    )
                }
            }
            .pageWidth()
            .padding(.horizontal, Theme.gutter)
            .padding(.top, 4)
            .padding(.bottom, 32)
        }
        .paperPage()
        .navigationTitle("Studia dzieł")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await model.loadStudyList(model.backend) }
    }
}

/// A study as a card, like a theme's: the work on top, its title and artist
/// below on the card's white.
struct StudyCard: View {
    let study: StudyBrief

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Color.clear
                .frame(height: 118)
                .frame(maxWidth: .infinity)
                .overlay {
                    ArtImage(
                        ref: study.item.thumb,
                        fallback: study.item.thumbFallback,
                        placeholder: study.item.item.placeholderColor,
                        maxPixel: 500,
                        subjectFocus: true
                    )
                }
                .clipped()
            VStack(alignment: .leading, spacing: 4) {
                Text(study.title)
                    .font(.serif(15, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(2, reservesSpace: true)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                Text(Names.artist(study.item.item.artist))
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .lineLimit(1)
            }
            .padding(10)
            .frame(maxHeight: .infinity, alignment: .top)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(Theme.hairline))
        .accessibilityElement(children: .combine)
        .accessibilityHint("Otwiera studium dzieła")
    }
}

/// One horizontal row of works.
struct SuggestionRowView: View {
    let row: SuggestionRow
    /// The theme behind the row, to browse further.
    var theme: ArtTheme?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                // The theme's works page by page, or the row's own works.
                Group {
                    if let theme {
                        NavigationLink(value: theme) { title }
                    } else {
                        NavigationLink(value: SuggestionRowRoute(key: row.key)) { title }
                    }
                }
                .buttonStyle(.plain)
                if !row.subtitle.isEmpty {
                    Text(row.subtitle)
                        .font(.footnote)
                        .foregroundStyle(Theme.inkSoft)
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
                        .contextMenu { QueueButton(itemID: remote.id) }
                    }
                }
                .padding(.vertical, 4)
            }
            .scrollClipDisabled()
        }
    }

    private var title: some View {
        SeeAllHeader(title: row.title, size: 20, weight: .medium)
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
    @State private var failed = false
    @State private var playlistID: Int?
    @State private var busy = false
    /// "Pokaż na ramce" on its way: a spinner on it.
    @State private var playing = false

    /// Pages that found nothing are followed by themselves, this many at most.
    private static let emptyPagesInARow = 6

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
                    .contextMenu { QueueButton(itemID: summary.id) }
                }
                if items.isEmpty && !more && !loading {
                    EmptyStateView(
                        title: "Muzea nic tu nie mają",
                        message: "Nie znalazłem teraz dzieł z tego motywu. Spróbuj później albo w zakładce Muzea.",
                        systemImage: "magnifyingglass"
                    )
                }
                if more {
                    Button {
                        Task { await loadMore() }
                    } label: {
                        HStack(spacing: 8) {
                            if loading { ProgressView().controlSize(.small) }
                            Text(moreLabel)
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
            .pageWidth()
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 32)
        }
        .paperPage()
        .navigationTitle(Names.theme(theme))
        .navigationBarTitleDisplayMode(.inline)
        .task {
            playlistID = theme.playlistId
            if items.isEmpty { await loadMore() }
        }
    }

    private var moreLabel: String {
        if loading { return items.isEmpty ? "Wczytuję…" : "Wczytuję więcej…" }
        if failed { return "Spróbuj ponownie" }
        return items.isEmpty ? "Wczytaj" : "Więcej"
    }

    private var actions: some View {
        HStack(spacing: 10) {
            Button {
                Task { await make(play: true) }
            } label: {
                Label {
                    Text("Pokaż na ramce")
                } icon: {
                    if playing {
                        ProgressView().tint(Theme.paper)
                    } else {
                        Image(systemName: "photo.artframe")
                    }
                }
            }
            .buttonStyle(PrimaryButtonStyle())
            .sensoryFeedback(.impact(weight: .medium), trigger: playing) { _, now in now }
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
        playing = play
        defer {
            busy = false
            playing = false
        }
        if let id = await ThemeActions.makePlaylist(theme, play: play, model: model) { playlistID = id }
    }

    private func loadMore() async {
        guard !loading else { return }
        loading = true
        failed = false
        defer { loading = false }
        do {
            for _ in 0 ..< Self.emptyPagesInARow {
                let found = try await model.backend.themePage(key: theme.key, page: page + 1)
                items = items.adding(found.items)
                page = (found.nextPage ?? page + 2) - 1
                more = found.more
                if !found.items.isEmpty || !more { break }
            }
        } catch {
            failed = !error.isCancellation
            model.show(error)
        }
    }
}
