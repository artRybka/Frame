import SwiftUI

/// What Discover opens with: the work of the day, ideas for playlists in
/// groups in the server's order ("Dziś dla Ciebie" has the theme of the day
/// after the curator's cards and the artist of the week, then the cards
/// "Ponieważ lubisz" from the hearts) and, last, the works of the day and
/// those with a study ("Studia dzieł").
///
/// The last ones loaded show at once (also after a launch) while fresh ones
/// load, and only the cards and works on screen fetch their pictures.
struct SuggestionsView: View {
    @Environment(AppModel.self) private var model
    @State private var loading = false
    @Binding var path: NavigationPath

    private var rows: [SuggestionRow] { model.suggestionRows ?? [] }
    /// "Motyw dnia" is a card of "Dziś dla Ciebie"; "Dla Ciebie" (still the
    /// cover of Propozycje in Playlisty), "Nowe w katalogu" and "Dawno ich
    /// nie było" (Mateusz 2026-11-07) are not shown, nor the rows "Bo
    /// lubisz: …" of older servers once they send its cards.
    private var otherRows: [SuggestionRow] {
        let liked = themes.contains { $0.key.hasPrefix(DiscoverLayout.likedPrefix) }
        return rows.filter { row in
            !["theme", "for-you", "new", "back"].contains(row.key) && !(liked && row.key.hasPrefix("like:"))
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
                                .drawWeekArtistAgainMenu(theme)
                            }
                        }
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.vertical, 2)
                    }
                    .scrollClipDisabled()
                    .edgeToEdgeRow()
                }
            }
            ForEach(otherRows.filter { $0.key != DiscoverLayout.zoom }) { row in rowView(row) }
            if let studies = model.studyList, !studies.isEmpty { StudyRow(studies: studies).id("studies") }
            // "Pod lupą" last, after "Studia dzieł" (Mateusz 2026-11-11).
            if let zoom = otherRows.first(where: { $0.key == DiscoverLayout.zoom }) { rowView(zoom) }
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

    @ViewBuilder
    private func rowView(_ row: SuggestionRow) -> some View {
        if row.key == DiscoverLayout.zoom {
            ZoomRow(row: row).id("zoom")
        } else {
            SuggestionRowView(row: row, theme: (model.themes ?? []).first { $0.key == row.theme })
        }
    }
}

/// How Propozycje lays out the themes and rows the server sends.
enum DiscoverLayout {
    static let weekly = "Dziś dla Ciebie"
    /// The same group as older servers name it.
    static let oldWeekly = "Na ten tydzień"
    /// The group of the cards of favourite artists on older servers; they
    /// are in "Dziś dla Ciebie" now.
    static let likes = "Bo lubisz"
    static let likedPrefix = "like-"
    /// The row "Pod lupą", as cards (`ZoomRow`).
    static let zoom = "zoom"
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

    /// The themes as Propozycje shows them: the theme of the day in "Dziś
    /// dla Ciebie" after the curator's cards and the artist of the week,
    /// before "Ponieważ lubisz" and the week's pairs (Mateusz 2026-11-07;
    /// the group made for it when the week has no themes).
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
        all.insert(card, at: dayCardIndex(all))
        return all
    }

    /// Where the theme of the day goes in ``themes``: before the first card
    /// "Ponieważ lubisz" or pair of the week in "Dziś dla Ciebie", else
    /// after its last card, else first.
    static func dayCardIndex(_ themes: [ArtTheme]) -> Int {
        let later = themes.firstIndex { theme in
            theme.group == weekly && (theme.key.hasPrefix(likedPrefix) || theme.key.hasPrefix("week-mix-"))
        }
        if let later { return later }
        if let last = themes.lastIndex(where: { $0.group == weekly }) { return last + 1 }
        return 0
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
                        // Only the tick, where "+ Playlista" was.
                        Image(systemName: "checkmark")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(Theme.good)
                            .accessibilityLabel("Masz tę playlistę")
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
                            .foregroundStyle(Theme.ink)
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
                                    .scaleEffect(CoverZoom.scale)
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
            .edgeToEdgeRow()
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
        WorkTile(item: study.item, title: study.title)
            .accessibilityHint("Otwiera studium dzieła")
    }
}

/// A work as a card, like a theme's: the picture on top, its title and
/// artist below on the card's white ("Studia dzieł", "Pod lupą").
struct WorkTile: View {
    let item: RemoteItem
    /// The title shown (a study's Polish title; else the work's own).
    var title: String?
    /// The picture a little brighter than the page (`ArtGlow`, when
    /// Konfiguracja allows it), as on the work's card ("Pod lupą",
    /// Mateusz 2026-11-10): fully at the top, fading to a tenth of it at
    /// the caption (19:15); stronger, held over the top third (2026-11-11),
    /// cropped closer, with a glossy coat, lifted over the page with the
    /// phone's turn and casting a shadow on it.
    var brighten = false

    /// How much closer a brightened card crops its picture.
    static let closer: CGFloat = 1.18

    private var shownTitle: String {
        let title = title ?? item.summary.title
        return title.isEmpty ? "Bez tytułu" : title
    }

    private var card: some View {
        VStack(alignment: .leading, spacing: 0) {
            Color.clear
                .frame(height: 118)
                .frame(maxWidth: .infinity)
                .overlay {
                    ArtImage(
                        ref: item.thumb,
                        fallback: item.thumbFallback,
                        placeholder: item.item.placeholderColor,
                        maxPixel: 500,
                        subjectFocus: true,
                        brighten: brighten,
                        // Brighter than the card's at the top, full over the
                        // top third, a tenth of it at the caption (Mateusz
                        // 2026-11-11 10:06: stronger, and a little lower).
                        glowFade: 0.1,
                        glowHold: 0.3,
                        glowBoost: 1.35
                    )
                    // Cropped a little closer than the studies' (2026-11-11).
                    .scaleEffect(brighten ? Self.closer : 1)
                }
                .clipped()
            VStack(alignment: .leading, spacing: 4) {
                Text(shownTitle)
                    .font(.serif(15, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(2, reservesSpace: true)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                Text(ArtCard.byline(item.summary))
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
        .overlay {
            // A glossy coat: a diagonal streak that runs with the phone's
            // turn, as on the "Ukryte" cover (Mateusz 2026-11-11).
            if brighten {
                GlassSheen(peak: 0.65)
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
        }
        .accessibilityElement(children: .combine)
    }

    var body: some View {
        // A brightened card stands a little over the page and moves with
        // the phone's turn, its shadow on the page the other way
        // (Mateusz 2026-11-11).
        if brighten {
            card.liftedCard(cornerRadius: 12)
        } else {
            card
        }
    }
}

/// "Pod lupą": the works to look at far closer, as cards like the
/// studies' (Mateusz 2026-11-10), each picture a little brighter (`ArtGlow`).
struct ZoomRow: View {
    let row: SuggestionRow

    /// Its subtitle, also over a server that words it otherwise.
    static let subtitle = "Dzieła w ogromnej rozdzielczości"

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                NavigationLink(value: SuggestionRowRoute(key: row.key)) {
                    SeeAllHeader(title: row.title, size: 22, weight: .semibold)
                }
                .buttonStyle(.plain)
                Text(Self.subtitle)
                    .font(.footnote)
                    .foregroundStyle(Theme.inkSoft)
            }
            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(alignment: .top, spacing: 12) {
                    ForEach(row.items) { remote in
                        ZoomWorkCard(remote: remote).frame(width: 172)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                .padding(.vertical, 2)
            }
            .scrollClipDisabled()
            .edgeToEdgeRow()
        }
    }
}

/// One work of "Pod lupą" as a card that opens the work (in the row and in
/// its grid); no heart on it (Mateusz 2026-11-10 19:23).
struct ZoomWorkCard: View {
    @Environment(AppModel.self) private var model
    let remote: RemoteItem

    var body: some View {
        NavigationLink(value: remote.id) {
            WorkTile(item: remote, brighten: true)
                .accessibilityHint("Otwiera dzieło, można je mocno przybliżyć")
        }
        .buttonStyle(.plain)
        .contextMenu { QueueButton(itemID: remote.id) }
        // The card opened from here shows this much while it loads.
        .onAppear {
            ItemPeeks.remember(remote.summary, thumb: remote.thumb)
            if let picture = remote.summary.picture { model.pictureSeen(remote.id, copy: picture) }
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
                            ArtCard(item: remote.summary, ref: remote.thumb, showsFavorite: false)
                                .frame(width: 150)
                        }
                        .buttonStyle(.plain)
                        .contextMenu { QueueButton(itemID: remote.id) }
                        .overlay(alignment: .topTrailing) { LikeHeart(item: remote.summary) }
                    }
                }
                .padding(.vertical, 4)
            }
            .scrollClipDisabled()
            .edgeToEdgeRow()
        }
    }

    private var title: some View {
        SeeAllHeader(title: row.title, size: 20, weight: .medium)
    }
}

/// A theme browsed from the museums (or the catalogue), its works shown as
/// each museum answers and more asked for while the end is near, with
/// buttons that make it a playlist.
/// An Odkrywaj set as it was left: its works, in their order, and where
/// asking had got to.
struct ThemeVisit {
    var weave: WorkWeave
    var page: Int
    var more: Bool
    var at = Date()

    /// How long a set opened again shows what it had at once (the server
    /// keeps museums' answers for 3 hours, the catalogue's pages until it
    /// changes).
    static let fresh: TimeInterval = 30 * 60
}

struct ThemeView: View {
    @Environment(AppModel.self) private var model
    let theme: ArtTheme
    /// The works come, woven so that one painter's or one museum's do not
    /// stand in a row.
    @State private var weave = WorkWeave()
    /// The page to ask for next.
    @State private var page = 1
    @State private var more = true
    @State private var loading = false
    /// Rounds in a row in which no museum answered.
    @State private var failures = 0
    /// Less than a screen to the end: the next works are asked for.
    @State private var nearEnd = true
    /// On screen (not left, nor under a work opened from it): asking goes on.
    @State private var shown = false
    @State private var playlistID: Int?
    @State private var busy = false
    /// "Pokaż na ramce" on its way: a spinner on it.
    @State private var playing = false

    /// After this many rounds in a row with no museum answering, the app
    /// stops asking until "Spróbuj ponownie".
    private static let failuresToStop = 3
    /// How long a round no museum answered waits before the next.
    private static let retryPause: Duration = .seconds(10)
    /// How long the first works of one museum wait for another museum's
    /// before they are shown side by side (`WorkWeave.showFirst`).
    private static let firstWorksWait: Duration = .seconds(2)

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(theme.description)
                    .font(.serif(17))
                    .foregroundStyle(Theme.inkSoft)
                actions
                MasonryGrid(items: items.map(\.summary)) { summary in
                    NavigationLink(value: summary.id) {
                        ArtCard(item: summary, ref: items.first { $0.id == summary.id }?.thumb, showsFavorite: false)
                    }
                    .buttonStyle(.plain)
                    .contextMenu { QueueButton(itemID: summary.id) }
                    .overlay(alignment: .topTrailing) { LikeHeart(item: summary) }
                }
                if items.isEmpty && !more && !loading {
                    EmptyStateView(
                        title: "Muzea nic tu nie mają",
                        message: "Nie znalazłem teraz dzieł z tego motywu. Spróbuj później albo w zakładce Muzea.",
                        systemImage: "magnifyingglass"
                    )
                }
                if more {
                    if stopped {
                        Button {
                            failures = 0
                            moreIfNeeded()
                        } label: {
                            Text("Spróbuj ponownie")
                                .font(.subheadline.weight(.semibold))
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 12)
                                .background(Theme.card, in: RoundedRectangle(cornerRadius: 12))
                                .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Theme.hairline))
                        }
                    } else {
                        // The squares say "waiting", as in Szukaj: for as
                        // long as the museums may have more.
                        SearchWaiting()
                    }
                }
            }
            .pageWidth()
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 32)
        }
        // Before the end shows, so the next works are mostly there already.
        .onScrollGeometryChange(for: Bool.self) { geometry in
            geometry.contentSize.height - geometry.visibleRect.maxY < geometry.containerSize.height
        } action: { _, near in
            nearEnd = near
            moreIfNeeded()
        }
        .paperPage()
        .navigationTitle(Names.theme(theme))
        .navigationBarTitleDisplayMode(.inline)
        .task { playlistID = theme.playlistId }
        .onAppear {
            shown = true
            restore()
            moreIfNeeded()
        }
        .onDisappear {
            shown = false
            remember()
        }
    }

    /// Opened again soon after: the works it had show at once (the round
    /// being asked when it was left is asked again; copies are left out).
    private func restore() {
        guard weave.shown.isEmpty, !loading, let visit = model.themeVisits[theme.key],
            Date().timeIntervalSince(visit.at) < ThemeVisit.fresh
        else { return }
        weave = visit.weave
        page = visit.page
        more = visit.more
    }

    private func remember() {
        guard !weave.shown.isEmpty else { return }
        model.themeVisits[theme.key] = ThemeVisit(weave: weave, page: page, more: more)
    }

    private var stopped: Bool { failures >= Self.failuresToStop && !loading }

    private var items: [RemoteItem] { weave.shown }

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
                        Image(systemName: "photo.fill")
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

    /// Asks for the next works while the end is near, round after round
    /// (a round can bring nothing new); a round no museum answered waits a
    /// while before the next.
    @MainActor
    private func moreIfNeeded(after pause: Duration = .zero) {
        guard shown, nearEnd, more, !loading, failures < Self.failuresToStop else { return }
        loading = true
        Task { @MainActor in
            if pause > .zero { try? await Task.sleep(for: pause) }
            guard shown, nearEnd else {
                loading = false
                return  // asked again on coming back or scrolling down
            }
            let answered = await loadMore()
            loading = false
            remember()
            if answered {
                failures = 0
            } else {
                failures += 1
            }
            moreIfNeeded(after: answered ? .zero : Self.retryPause)
        }
    }

    /// The next round of the theme's searches, its works shown as each
    /// museum answers. False when no museum did.
    @MainActor
    private func loadMore() async -> Bool {
        let firstWorks = Task { @MainActor in
            try? await Task.sleep(for: Self.firstWorksWait)
            if !Task.isCancelled { weave.showFirst() }
        }
        defer { firstWorks.cancel() }
        do {
            for try await line in try await model.backend.themeLines(key: theme.key, page: page) {
                weave.add(line.items)
                if line.end {
                    if line.failed { return false }
                    more = line.more
                    if let next = line.nextPage { page = next } else { more = false }
                    weave.endRound(more: more)
                    return true
                }
            }
            return false  // cut off before the end: asked again
        } catch {
            if !error.isCancellation, failures + 1 >= Self.failuresToStop { model.show(error) }
            return false
        }
    }
}
