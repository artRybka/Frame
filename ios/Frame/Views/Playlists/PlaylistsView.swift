import SwiftUI
import UIKit
import UniformTypeIdentifiers

/// Playlists: what the frame presents now and all collections, smart and manual.
struct PlaylistsView: View {
    @Environment(AppModel.self) private var model
    @State private var editing: Playlist?
    @State private var path = NavigationPath()
    /// The playlist whose deletion waits for a yes.
    @State private var deleting: PlaylistSummary?
    /// How far the page is scrolled, for the glow of the card on top.
    @State private var scrolled: CGFloat = 0
    /// The playlist whose card is being moved with a finger.
    @State private var dragged: Int?

    private var active: PlaylistSummary? {
        guard let id = model.settings?.playlistId else { return nil }
        // Another person's private playlist on the frame: as the player has it.
        return model.playlists.first { $0.id == id } ?? model.player?.playlist.flatMap { $0.id == id ? $0 : nil }
    }

    /// Two columns, each card pinned to the top of its row.
    private static let columns = [
        GridItem(.flexible(), spacing: 16, alignment: .top),
        GridItem(.flexible(), spacing: 16, alignment: .top),
    ]

    /// The collections in the order I put the cards (the server keeps it for
    /// each person; my "Ulubione" first, next to "Propozycje", until then).
    private var ordered: [PlaylistSummary] { model.playlists }

    /// Under "Propozycje dnia": how many works today, else where they come from.
    private var suggestionsLine: String {
        guard let count = model.dayPicks?.items.count, count > 0 else { return "z „Dziś dla Ciebie”" }
        return "\(Names.works(count)) na dziś"
    }

    /// The frame plays Propozycje: no playlist.
    private var suggestionsActive: Bool { model.settings != nil && model.settings?.playlistId == nil }

    /// The cover of "Teraz prezentowane" glows behind it, as the picture
    /// does in Teraz: the main colour of each of its (up to) four works.
    private var glow: [ColorSwatch] {
        if let active { return active.coverColors ?? [] }
        guard suggestionsActive else { return [] }
        return model.suggestionCover.prefix(4).compactMap { work in
            work.item.colors.max { $0.weight < $1.weight }
        }
    }

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 26) {
                    if let active, model.playlists.contains(where: { $0.id == active.id }) {
                        NavigationLink(value: active.id) {
                            NowPlayingCard(playlist: active)
                        }
                        .buttonStyle(.plain)
                    } else if let active {
                        // Someone else's, not shared: nothing to open, so no arrow.
                        NowPlayingCard(playlist: active, opens: false)
                    } else if suggestionsActive {
                        NavigationLink(value: SuggestionsRoute()) {
                            NowPlayingCard(title: "Propozycje dnia", subtitle: "z „Dziś dla Ciebie”") {
                                CoverSlideshow(slides: model.suggestionCover.prefix(4).map(CoverSlideshow.Slide.init))
                            }
                        }
                        .buttonStyle(.plain)
                    }
                    // Every card is as tall as the others (`CardCaption`): rows of
                    // different heights made the lazy grid jump while scrolling.
                    LazyVGrid(columns: Self.columns, spacing: 22) {
                        NavigationLink(value: SuggestionsRoute()) {
                            SuggestionsCard(works: model.suggestionCover, subtitle: suggestionsLine, isActive: suggestionsActive)
                        }
                        .buttonStyle(.plain)
                        .contextMenu {
                            suggestionsMenu
                        } preview: {
                            CardMenuPreview(title: "Propozycje dnia", subtitle: suggestionsLine) {
                                SuggestionsCover(works: model.suggestionCover)
                            }
                            .environment(model)
                        }
                        ForEach(ordered) { playlist in
                            NavigationLink(value: playlist.id) {
                                PlaylistCard(playlist: playlist, isActive: playlist.id == active?.id)
                            }
                            .buttonStyle(.plain)
                            // A card of its own while held, cover left and name
                            // right: the options sit right under it, not under
                            // the caption of the tall grid card.
                            .contextMenu {
                                menu(playlist)
                            } preview: {
                                PlaylistMenuPreview(playlist: playlist)
                                    .environment(model)
                            }
                            // Held and moved, the card goes with the finger
                            // and the others make room (Mateusz 2026-11-09,
                            // variant A of playlisty-kolejnosc/szkic.png).
                            .onDrag {
                                dragged = playlist.id
                                return NSItemProvider(object: String(playlist.id) as NSString)
                            } preview: {
                                // Drawn apart from the page, without its
                                // environment: `ArtImage` needs the model
                                // (1.136.0 crashed as soon as a card was held).
                                Collage(itemIDs: playlist.coverItemIds, title: playlist.name)
                                    .frame(width: 150, height: 150)
                                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                                    .environment(model)
                            }
                            .onDrop(of: [.text], delegate: CardDrop(target: playlist.id, dragged: $dragged, model: model))
                            // On the card held, not the page: on iOS 26 the dialog
                            // is a popover pointing at the view it hangs on.
                            .confirmationDialog(
                                "Usunąć playlistę „\(playlist.name)”?",
                                isPresented: Binding(
                                    get: { deleting?.id == playlist.id },
                                    set: { if !$0 { deleting = nil } }
                                ),
                                titleVisibility: .visible,
                                presenting: deleting
                            ) { playlist in
                                Button("Usuń", role: .destructive) {
                                    Task { await delete(playlist) }
                                }
                            }
                        }
                        // New playlists come from the "+" at the top only
                        // (Mateusz 2026-11-09: no "Nowa playlista" tile).
                        // Last: the works hidden with "Ukryj dzieło".
                        NavigationLink(value: HiddenRoute()) {
                            HiddenCard(items: model.hidden)
                        }
                        .buttonStyle(.plain)
                    }
                    // Let go between the cards (or on Propozycje, Ukryte):
                    // the order as it stands is kept.
                    .onDrop(of: [.text], delegate: CardDrop(target: nil, dragged: $dragged, model: model))
                }
                .environment(\.parallaxLift, scrolled)
                .pageWidth()
                .padding(.horizontal, Theme.gutter)
                .padding(.bottom, 40)
            }
            .glowLift($scrolled)
            .paperPage(glow: glow, lift: scrolled, colours: 4)
            .navigationTitle("Playlisty")
            .serverLinkBadge()
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
            .navigationDestination(for: HiddenRoute.self) { _ in
                HiddenWorksView()
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
            .navigationDestination(for: DailyRoute.self) { route in
                DailyView(route: route)
            }
            .navigationDestination(for: StudiesRoute.self) { _ in
                StudiesGridView()
            }
            .sheet(item: $editing) { playlist in
                PlaylistEditorView(playlist: playlist)
            }
            .refreshable { await model.refreshPlaylists() }
            .task { if model.playlists.isEmpty { await model.refreshPlaylists() } }
            // Made once a day on the server: today's, also on a page kept open overnight.
            .task { await model.refreshDayPicks() }
            .onChange(of: model.playlists.first?.id) { _, first in
                if LaunchRoute.screen == "playlist", path.isEmpty, let first { path.append(first) }
                if LaunchRoute.screen == "suggestions", path.isEmpty { path.append(SuggestionsRoute()) }
                if LaunchRoute.screen == "editor", editing == nil {
                    editing = Playlist(name: "Błękitne krajobrazy", rules: PlaylistRules(colors: ["blue"]))
                }
                if LaunchRoute.screen == "editor-new", editing == nil {
                    editing = Playlist(name: "", rules: PlaylistRules())
                }
                if LaunchRoute.screen == "editor-manual", editing == nil {
                    editing = Playlist(name: "Na ścianę", kind: .manual)
                }
                if LaunchRoute.confirm == "delete-playlist", deleting == nil {
                    Task {
                        try? await Task.sleep(for: .seconds(3))
                        deleting = ordered.first { !$0.isFavorites && $0.isMine }
                    }
                }
            }
        }
        .opensStudies(on: $path)
    }
}

extension PlaylistsView {
    /// Held on a cover: present it on the frame, or delete it ("Ulubione" stays).
    @ViewBuilder
    private func menu(_ playlist: PlaylistSummary) -> some View {
        if playlist.id != active?.id {
            Button("Prezentuj na ramce", systemImage: "photo.fill") {
                Task { await model.play(playlist) }
            }
            .disabled(playlist.itemCount == 0)
        }
        if let index = model.playlists.firstIndex(where: { $0.id == playlist.id }), index > 0 {
            Button("Przesuń na początek", systemImage: "arrow.up.to.line") {
                var list = model.playlists
                list.insert(list.remove(at: index), at: 0)
                withAnimation(.snappy) { model.playlists = list }
                Task { await model.arrangePlaylists(list) }
            }
        }
        if !playlist.isFavorites, playlist.isMine {
            Button("Usuń playlistę", systemImage: "trash", role: .destructive) { deleting = playlist }
        }
    }

    /// Held on "Propozycje": present them, or open them in Discover.
    @ViewBuilder
    private var suggestionsMenu: some View {
        if !suggestionsActive {
            Button("Prezentuj na ramce", systemImage: "photo.fill") {
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

/// A card moved over the others in Playlisty: they make room as it passes
/// (the order changes at once), and where it is let go the order is kept on
/// the server. `target` nil: the grid around the cards.
private struct CardDrop: DropDelegate {
    let target: Int?
    @Binding var dragged: Int?
    let model: AppModel

    func dropEntered(info: DropInfo) {
        guard let target, let dragged, dragged != target,
              let from = model.playlists.firstIndex(where: { $0.id == dragged }),
              let to = model.playlists.firstIndex(where: { $0.id == target })
        else { return }
        withAnimation(.snappy) {
            model.playlists.move(fromOffsets: IndexSet(integer: from), toOffset: to > from ? to + 1 : to)
        }
    }

    func dropUpdated(info: DropInfo) -> DropProposal? {
        DropProposal(operation: dragged == nil ? .forbidden : .move)
    }

    func performDrop(info: DropInfo) -> Bool {
        guard dragged != nil else { return false }
        dragged = nil
        let list = model.playlists
        Task { await model.arrangePlaylists(list) }
        return true
    }
}

/// Opens Propozycje within Playlisty, pushed like a playlist.
struct SuggestionsRoute: Hashable {}

/// Opens "Ukryte" within Playlisty.
struct HiddenRoute: Hashable {}

/// Propozycje dnia opened from their tile (Mateusz 2026-11-09): a header
/// like a playlist's naming the cards of "Dziś dla Ciebie" they come from,
/// with "Prezentuj na ramce", over the works four by four, in the order the
/// frame shows them.
struct SuggestionsPage: View {
    @Environment(AppModel.self) private var model
    @Binding var path: NavigationPath
    @State private var starting = false

    private var isActive: Bool { model.settings != nil && model.settings?.playlistId == nil }
    private static let pair = [GridItem(.flexible(), spacing: 6), GridItem(.flexible(), spacing: 6)]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                header
                if let picks = model.dayPicks, !picks.items.isEmpty {
                    fours(picks)
                } else if model.dayPicks == nil {
                    GridSkeleton(count: 6)
                } else {
                    EmptyStateView(
                        title: "Propozycje dnia są w drodze",
                        message: "Składają się z kart „Dziś dla Ciebie”, gdy tylko w katalogu są ich dzieła."
                    )
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .pageWidth()
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 40)
        }
        .paperPage()
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await model.refreshDayPicks() }
        .task { await model.refreshDayPicks() }
    }

    /// The cards' names, in the order of "Dziś dla Ciebie".
    private var cardNames: String {
        (model.dayPicks?.cards ?? []).map { Names.theme($0) }.joined(separator: " · ")
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 14) {
            SuggestionsCover(works: model.suggestionCover)
                .aspectRatio(1.6, contentMode: .fit)
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                .shadow(color: .black.opacity(0.15), radius: 18, y: 10)
            Eyebrow("Dziś dla Ciebie", color: Theme.vermilion)
            Text("Propozycje dnia")
                .font(.serif(32, weight: .semibold))
                .foregroundStyle(Theme.ink)
            if !cardNames.isEmpty {
                Text(cardNames)
                    .font(.serif(17))
                    .foregroundStyle(Theme.inkSoft)
            }
            if isActive {
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
                        await model.playSuggestions()
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
                .disabled(starting)
                .sensoryFeedback(.impact(weight: .medium), trigger: starting) { _, now in now }
            }
        }
    }

    /// Each four two by two, a little apart from the next: four of one
    /// card, then four of the next, as the frame shows them.
    private func fours(_ picks: DayPicks) -> some View {
        LazyVStack(spacing: 18) {
            ForEach(Array(picks.fours.enumerated()), id: \.offset) { _, four in
                LazyVGrid(columns: Self.pair, spacing: 6) {
                    ForEach(four) { work in
                        NavigationLink(value: work.item.id) { tile(work) }
                            .buttonStyle(.plain)
                            .contextMenu { QueueButton(itemID: work.item.id) }
                    }
                }
            }
        }
    }

    private func tile(_ work: RemoteItem) -> some View {
        Color.clear
            .aspectRatio(1, contentMode: .fit)
            .overlay {
                ArtImage(
                    ref: work.thumb,
                    fallback: work.thumbFallback,
                    placeholder: work.item.summary.placeholderColor,
                    maxPixel: 500
                )
            }
            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            .accessibilityElement()
            .accessibilityLabel(work.item.title)
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

/// Card for the playlist the frame presents (or Propozycje), J1 from the
/// sketches (Mateusz 2026-11-05, `teraz-prezentowane-kafelek/szkic-7.png`):
/// the cover's works one at a time (`CoverSlideshow`, 2026-11-07; a 2×2
/// collage before) in a square flush with the card's left edge,
/// a third of the card wide and as tall as the card; beside it on white
/// "Teraz prezentowane", the name and, at the bottom, the count next to the
/// arrow. The card is always a third as tall as it is wide, so a long name
/// shrinks a little and then ends in an ellipsis instead of growing it.
struct NowPlayingCard<Cover: View>: View {
    let title: String
    let subtitle: String
    /// Whether the card opens a page; only then it carries the arrow.
    var opens = true
    @ViewBuilder let cover: Cover

    private static var shape: RoundedRectangle { RoundedRectangle(cornerRadius: 14, style: .continuous) }

    var body: some View {
        Color.clear
            .aspectRatio(3, contentMode: .fit)
            .overlay {
                GeometryReader { geo in
                    let side = geo.size.height
                    HStack(spacing: 0) {
                        cover
                            .frame(width: side, height: side)
                            .clipped()
                        text
                            .padding(.leading, 16)
                            .padding(.trailing, 12)
                            .padding(.vertical, 11)
                            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                    }
                }
            }
            .background(Theme.card)
            .clipShape(Self.shape)
            .overlay(Self.shape.strokeBorder(Theme.hairline))
            .shadow(color: .black.opacity(0.06), radius: 16, y: 8)
            .padding(.top, 6)
            .accessibilityElement(children: .combine)
    }

    private var text: some View {
        VStack(alignment: .leading, spacing: 4) {
            Eyebrow("Teraz prezentowane", color: Theme.vermilion)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            Text(title)
                .font(.serif(21, weight: .semibold))
                .foregroundStyle(Theme.ink)
                .lineLimit(2)
                .minimumScaleFactor(0.8)
                .multilineTextAlignment(.leading)
            Spacer(minLength: 0)
            HStack(alignment: .center, spacing: 8) {
                Text(subtitle)
                    .font(.subheadline)
                    .foregroundStyle(Theme.inkSoft)
                    .lineLimit(1)
                    .minimumScaleFactor(0.85)
                Spacer(minLength: 0)
                if opens {
                    CardArrow()
                }
            }
        }
    }
}

extension NowPlayingCard where Cover == CoverSlideshow {
    init(playlist: PlaylistSummary, opens: Bool = true) {
        self.init(title: playlist.name, subtitle: playlist.countText, opens: opens) {
            CoverSlideshow(slides: playlist.coverItemIds.map(CoverSlideshow.Slide.init), title: playlist.name)
        }
    }
}

/// The square of "Teraz prezentowane": the cover's works one at a time,
/// each for a few seconds, the next slowly coming through the one before
/// (variant A, "Ciche przenikanie", of
/// `teraz-prezentowane-animacja/szkic.png`, Mateusz 2026-11-07). The
/// pictures sit a little deeper than the card, with the study of the day's
/// parallax. All of them are laid out at once, so the next one is loaded
/// before its turn. Stands still off screen and with the app away.
struct CoverSlideshow: View {
    struct Slide: Identifiable, Equatable {
        let id: String
        var ref: ImageRef
        var fallback: ImageRef?
        var placeholder: Color = Theme.mat

        init(_ id: String) {
            self.id = id
            ref = .thumb(id)
        }

        init(_ work: RemoteItem) {
            id = work.id
            ref = work.thumb
            fallback = work.thumbFallback
            placeholder = work.item.summary.placeholderColor
        }
    }

    let slides: [Slide]
    var title = ""

    /// How long each work stands, and how long the next takes to come.
    static let hold: Duration = .seconds(6)
    static let fade: Double = 2

    @Environment(\.scenePhase) private var phase
    /// The work on top, and the one it is coming over while it does.
    @State private var shown = 0
    @State private var under: Int?
    @State private var onScreen = false

    private var running: Bool { onScreen && phase == .active && slides.count > 1 }

    var body: some View {
        ZStack {
            Theme.mat
            if slides.isEmpty {
                Collage(itemIDs: [], title: title)
            } else {
                GeometryReader { geo in
                    ZStack {
                        ForEach(Array(slides.enumerated()), id: \.element.id) { index, slide in
                            ArtImage(
                                ref: slide.ref,
                                fallback: slide.fallback,
                                placeholder: slide.placeholder,
                                maxPixel: 600,
                                subjectFocus: true
                            )
                            .frame(width: geo.size.width, height: geo.size.height)
                            .scaleEffect(CoverZoom.scale)
                            .clipped()
                            .opacity(index == shown || index == under ? 1 : 0)
                            .zIndex(index == shown ? 2 : index == under ? 1 : 0)
                        }
                    }
                }
                // A touch bigger than the square, so it can drift in it.
                .padding(.horizontal, -Parallax.side)
                .padding(.vertical, -Parallax.top)
                .parallax()
            }
        }
        .clipped()
        .onAppear { onScreen = true }
        .onDisappear { onScreen = false }
        .onScrollVisibilityChange(threshold: 0.05) { onScreen = $0 }
        .onChange(of: slides.map(\.id)) {
            shown = 0
            under = nil
        }
        .task(id: running) {
            guard running else { return }
            while !Task.isCancelled {
                try? await Task.sleep(for: Self.hold)
                guard !Task.isCancelled, slides.count > 1 else { return }
                under = shown
                withAnimation(.easeInOut(duration: Self.fade)) {
                    shown = (shown + 1) % slides.count
                }
                try? await Task.sleep(for: .seconds(Self.fade))
                under = nil
            }
        }
        .accessibilityHidden(true)
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
            CardCaption {
                Text(playlist.name)
                    .font(.serif(16, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(2)
                HStack(spacing: 4) {
                    if let icon = playlist.kind.icon {
                        Image(systemName: icon).font(.caption2)
                    }
                    Text(playlist.countText).layoutPriority(1)
                    Spacer(minLength: 6)
                    if let owner = sharedBy {
                        Label(owner, systemImage: "person.2")
                            .font(.caption2)
                            .lineLimit(1)
                    } else if playlist.isMine, playlist.shared == true {
                        Image(systemName: "person.2")
                            .font(.caption2)
                            .accessibilityLabel("Wspólna")
                    }
                }
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
            }
        }
    }

    /// Right of the count: whose it is when someone else shares it with the
    /// household; my own shared ones get the two-people icon alone (no
    /// "Wspólna" text), my private ones nothing.
    private var sharedBy: String? {
        if !playlist.isMine, let owner = playlist.ownerName, !owner.isEmpty { return owner }
        return nil
    }
}

/// The name and count under a card in the playlists grid, always as tall as
/// a two-line name plus the count: every card in the grid has one height, so
/// the lazy grid does not jump when rows load while scrolling.
struct CardCaption<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        ZStack(alignment: .topLeading) {
            VStack(alignment: .leading, spacing: 3) {
                Text("A\nA").font(.serif(16, weight: .semibold))
                Text("A").font(.caption)
            }
            .hidden()
            .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 3) {
                content
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

/// "Propozycje" first among the collections: the rotation the server picks
/// in Discover, marked with sparkles; it can't be edited or deleted.
struct SuggestionsCard: View {
    let works: [RemoteItem]
    var subtitle = "z „Dziś dla Ciebie”"
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
                        .foregroundStyle(Theme.inkSoft)
                        .frame(width: 30, height: 30)
                        .background(Theme.paper.opacity(0.85), in: Circle())
                        .padding(8)
                }
                .shadow(color: .black.opacity(0.12), radius: 10, y: 6)
            CardCaption {
                Text("Propozycje dnia")
                    .font(.serif(16, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityHint("Otwiera Propozycje dnia; przytrzymaj, by pokazać je na ramce")
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
                                .scaleEffect(CoverZoom.scale)
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

/// "Ukryte", the last card in Playlisty: the works hidden with "Ukryj
/// dzieło" behind frosted glass: their colours show through, the details
/// don't. A sticker with a crossed-out eye in the corner.
struct HiddenCard: View {
    let items: [ItemSummary]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            FrostedCover(itemIDs: items.prefix(4).map(\.id))
                .aspectRatio(1, contentMode: .fit)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(alignment: .bottomTrailing) {
                    // A drop of the same glass, not a paper sticker.
                    Image(systemName: "eye.slash")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(Theme.inkSoft)
                        .frame(width: 30, height: 30)
                        .glassEffect(.regular, in: .circle)
                        .padding(9)
                }
                .shadow(color: .black.opacity(0.12), radius: 10, y: 6)
            CardCaption {
                Text("Ukryte")
                    .font(.serif(16, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                Text(items.isEmpty ? "brak" : Names.works(items.count))
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityHint("Otwiera ukryte dzieła, które można przywrócić")
    }
}

/// A collage behind misted glass that breathes: blurred as one picture,
/// it drifts gently behind the pane (aside, nearer, a little turned) while a
/// soft patch of light wanders over it, under the system's own haze
/// (`ultraThinMaterial`, as iOS mists what lies behind it); no cream sheet
/// or grain any more (Mateusz 2026-11-07: "bez tego mrożenia"). Turned in the hand, the collage also slides under the pane, as the
/// study of the day's picture does (`parallax()`), and a streak of gloss
/// crosses the glass. No glass layer over the whole card: its rim lit the
/// top and bottom edges as white bands (Mateusz 2026-11-07). Off screen or
/// with Reduce Motion it stands still. With no works, the bare haze on the mat.
struct FrostedCover: View {
    let itemIDs: [String]
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var onScreen = false

    var body: some View {
        // Flattened first: a blur on the collage itself falls on each
        // picture alone and leaves the seams sharp. Built once, outside the
        // timeline, so only its place changes frame by frame.
        let collage = Collage(itemIDs: itemIDs)
            .drawingGroup()
            .blur(radius: 6, opaque: true)
        let still = itemIDs.isEmpty || reduceMotion || !onScreen
        TimelineView(.animation(minimumInterval: 1.0 / 30, paused: still)) { context in
            let drift = CoverDrift(at: still ? 0 : context.date.timeIntervalSinceReferenceDate)
            ZStack {
                Theme.mat
                if !itemIDs.isEmpty {
                    GeometryReader { geo in
                        collage
                            // Big enough that, moved and turned, it still
                            // covers the pane to its corners.
                            .scaleEffect(1.3 * drift.scale)
                            .rotationEffect(.degrees(drift.turn))
                            .offset(x: geo.size.width * drift.x, y: geo.size.height * drift.y)
                            .parallax()
                    }
                    RadialGradient(
                        colors: [.white.opacity(0.3), .white.opacity(0)],
                        center: drift.light,
                        startRadius: 0,
                        endRadius: 90
                    )
                    .blendMode(.softLight)
                }
                // The collage is only pre-softened; the haze blurs it the
                // rest of the way, and lightens or darkens with the scheme.
                Rectangle().fill(.ultraThinMaterial)
                if !itemIDs.isEmpty { GlassSheen() }
            }
        }
        .onAppear { onScreen = true }
        .onDisappear { onScreen = false }
        .accessibilityHidden(true)
    }
}

/// Where the collage behind the glass is at a moment: a few slow, small sines
/// with periods that never line up, so the drift does not visibly repeat;
/// one sweep takes half a minute (Mateusz 2026-11-07: gentler than the sketch).
struct CoverDrift {
    var x: CGFloat
    var y: CGFloat
    var scale: CGFloat
    var turn: Double
    var light: UnitPoint

    init(at time: TimeInterval) {
        func wave(_ period: Double, _ shift: Double = 0) -> CGFloat {
            CGFloat(sin(2 * .pi * time / period + shift))
        }
        x = 0.022 * wave(35)
        y = 0.02 * wave(43, 1)
        scale = 1 + 0.018 * (1 + wave(29, 2))
        turn = 0.8 * Double(wave(47, 0.5))
        light = UnitPoint(x: 0.45 + 0.2 * wave(26), y: 0.4 + 0.2 * wave(32, 1.3))
    }
}

/// A streak of gloss across the glass that runs with the phone's turn
/// (`Tilt`, started by the collage's `parallax()`) and fades out once the
/// phone is held still, so a card at rest has none.
private struct GlassSheen: View {
    var body: some View {
        let tilt = Tilt.shared
        let middle = 0.5 + 0.3 * tilt.x - 0.1 * tilt.y
        let strength = 0.4 * min(1, 1.4 * max(abs(tilt.x), abs(tilt.y)))
        LinearGradient(
            stops: [
                .init(color: .white.opacity(0), location: middle - 0.16),
                .init(color: .white.opacity(0.4), location: middle - 0.02),
                .init(color: .white.opacity(0.12), location: middle + 0.04),
                .init(color: .white.opacity(0), location: middle + 0.15),
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        .blendMode(.softLight)
        .opacity(strength)
        .allowsHitTesting(false)
    }
}

/// A held card, laid on its side: the cover on the left, the name and count
/// on the right, so the menu comes straight under it (Mateusz 2026-11-09:
/// the grid card's menu hung under its caption, far from the cover).
struct CardMenuPreview<Cover: View, Details: View>: View {
    let title: String
    @ViewBuilder let cover: Cover
    @ViewBuilder let details: Details

    var body: some View {
        HStack(alignment: .center, spacing: 14) {
            cover
                .frame(width: 112, height: 112)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            VStack(alignment: .leading, spacing: 5) {
                Text(title)
                    .font(.serif(19, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
                details
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(12)
        .frame(width: 320)
        .background(Theme.paper, in: .rect)  // a card, not a page
    }
}

extension CardMenuPreview where Details == Text {
    init(title: String, subtitle: String, @ViewBuilder cover: () -> Cover) {
        self.title = title
        self.cover = cover()
        details = Text(subtitle)
    }
}

/// A playlist's card while held: `CardMenuPreview` with its collage, count
/// and whose it is.
struct PlaylistMenuPreview: View {
    let playlist: PlaylistSummary

    var body: some View {
        CardMenuPreview(title: playlist.name) {
            Collage(itemIDs: playlist.coverItemIds, title: playlist.name)
        } details: {
            HStack(spacing: 4) {
                if let icon = playlist.kind.icon {
                    Image(systemName: icon).font(.caption2)
                }
                Text(playlist.countText)
                if playlist.isMine, playlist.shared == true {
                    // As on the card: my shared ones get the icon alone.
                    Image(systemName: "person.2")
                        .font(.caption2)
                        .padding(.leading, 4)
                        .accessibilityLabel("Wspólna")
                }
            }
            if !playlist.isMine, let owner = playlist.ownerName, !owner.isEmpty {
                Label(owner, systemImage: "person.2").font(.caption2)
            }
        }
    }
}

/// Human description of smart rules as chips.
struct RulesSummary: View {
    @Environment(AppModel.self) private var model
    let rules: PlaylistRules

    var body: some View {
        FlowLayout(spacing: 6) {
            ForEach(rules.artists, id: \.self) { TagLabel(text: Names.artist($0)) }
            ForEach(rules.styles, id: \.self) { TagLabel(text: $0) }
            ForEach(rules.subjects, id: \.self) { TagLabel(text: "#\($0)") }
            ForEach(rules.colors, id: \.self) { TagLabel(text: ColorTag.name($0), colorTag: $0) }
            ForEach(SearchPhrases.tokens(rules.query), id: \.self) { TagLabel(text: "„\($0)”") }
            if let from = rules.yearFrom { TagLabel(text: "od \(String(from))") }
            if let to = rules.yearTo { TagLabel(text: "do \(String(to))") }
            if rules.favoritesOnly { TagLabel(text: "♥ ulubione") }
            ForEach(rules.sources, id: \.self) { TagLabel(text: Names.source($0)) }
            ForEach(rules.excludeSources, id: \.self) { TagLabel(text: "bez \(Names.source($0))") }
            ForEach(rules.places, id: \.self) { TagLabel(text: model.placeName($0)) }
            ForEach(rules.excludePlaces, id: \.self) { TagLabel(text: "bez \(model.placeName($0))") }
        }
        .task { if !rules.places.isEmpty || !rules.excludePlaces.isEmpty { await model.loadPlaceNames() } }
    }
}
