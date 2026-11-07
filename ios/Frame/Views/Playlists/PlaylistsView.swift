import SwiftUI
import UIKit

/// Playlists: what the frame presents now and all collections, smart and manual.
struct PlaylistsView: View {
    @Environment(AppModel.self) private var model
    @State private var editing: Playlist?
    @State private var path = NavigationPath()
    /// The playlist whose deletion waits for a yes.
    @State private var deleting: PlaylistSummary?
    /// How far the page is scrolled, for the glow of the card on top.
    @State private var scrolled: CGFloat = 0

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

    /// The collections as the server lists them, with my "Ulubione" first,
    /// next to "Propozycje".
    private var ordered: [PlaylistSummary] {
        guard let index = model.playlists.firstIndex(where: { $0.isFavorites && $0.isMine }) else {
            return model.playlists
        }
        var list = model.playlists
        list.insert(list.remove(at: index), at: 0)
        return list
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
                            NowPlayingCard(title: "Propozycje", subtitle: "dobór z Odkrywaj") {
                                SuggestionsCover(works: model.suggestionCover)
                            }
                        }
                        .buttonStyle(.plain)
                    }
                    // Every card is as tall as the others (`CardCaption`): rows of
                    // different heights made the lazy grid jump while scrolling.
                    LazyVGrid(columns: Self.columns, spacing: 22) {
                        NavigationLink(value: SuggestionsRoute()) {
                            SuggestionsCard(works: model.suggestionCover, isActive: suggestionsActive)
                        }
                        .buttonStyle(.plain)
                        .contextMenu { suggestionsMenu }
                        ForEach(ordered) { playlist in
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
                        // Last: the works hidden with "Ukryj dzieło".
                        NavigationLink(value: HiddenRoute()) {
                            HiddenCard(items: model.hidden)
                        }
                        .buttonStyle(.plain)
                    }
                }
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

/// Opens Propozycje within Playlisty, pushed like a playlist.
struct SuggestionsRoute: Hashable {}

/// Opens "Ukryte" within Playlisty.
struct HiddenRoute: Hashable {}

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
        .paperPage()
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
/// the cover's four works as a 2×2 square flush with the card's left edge,
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

extension NowPlayingCard where Cover == Collage {
    init(playlist: PlaylistSummary, opens: Bool = true) {
        self.init(title: playlist.name, subtitle: playlist.countText, opens: opens) {
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

/// A collage behind frosted glass that breathes: blurred as one picture,
/// it drifts gently behind the pane (aside, nearer, a little turned) while a
/// soft patch of light wanders over it, under a thin cream sheet with a fine
/// grain. Turned in the hand, the collage also slides under the pane, as the
/// study of the day's picture does (`parallax()`), and a streak of gloss
/// crosses the glass. No glass layer over the whole card: its rim lit the
/// top and bottom edges as white bands (Mateusz 2026-11-07). Off screen or
/// with Reduce Motion it stands still. With no works, the bare frosted sheet
/// on the mat.
struct FrostedCover: View {
    let itemIDs: [String]
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var onScreen = false

    var body: some View {
        // Flattened first: a blur on the collage itself falls on each
        // picture alone and leaves the seams sharp. Built once, outside the
        // timeline, so only its place changes frame by frame.
        let collage = Collage(itemIDs: itemIDs)
            .saturation(0.95)
            .drawingGroup()
            .blur(radius: 10, opaque: true)
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
                Theme.paper.opacity(0.26)
                Image(uiImage: FrostGrain.tile)
                    .resizable(resizingMode: .tile)
                    .interpolation(.none)
                    .blendMode(.overlay)
                    .opacity(0.2)
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
        let strength = 0.6 * min(1, 1.4 * max(abs(tilt.x), abs(tilt.y)))
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

/// Grey noise around mid-grey, tiled over a picture in overlay mode: it
/// lightens and darkens point by point without tinting, like the grain of
/// sandblasted glass. Seeded, so every card has the same grain.
enum FrostGrain {
    static let tile: UIImage = {
        let side = 128
        var state: UInt64 = 0x9E37_79B9_7F4A_7C15
        let pixels = (0 ..< side * side).map { _ -> UInt8 in
            // xorshift64*: cheap and the same on every launch.
            state ^= state >> 12
            state ^= state << 25
            state ^= state >> 27
            let value = (state &* 0x2545_F491_4F6C_DD1D) >> 56
            return UInt8(68 + value * 120 / 255)
        }
        guard
            let provider = CGDataProvider(data: Data(pixels) as CFData),
            let image = CGImage(
                width: side,
                height: side,
                bitsPerComponent: 8,
                bitsPerPixel: 8,
                bytesPerRow: side,
                space: CGColorSpaceCreateDeviceGray(),
                bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.none.rawValue),
                provider: provider,
                decode: nil,
                shouldInterpolate: false,
                intent: .defaultIntent
            )
        else { return UIImage() }
        return UIImage(cgImage: image, scale: 2, orientation: .up)
    }()
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
            CardCaption {}
        }
    }
}

/// Human description of smart rules as chips.
struct RulesSummary: View {
    let rules: PlaylistRules

    var body: some View {
        FlowLayout(spacing: 6) {
            ForEach(rules.artists, id: \.self) { TagLabel(text: Names.artist($0)) }
            ForEach(rules.styles, id: \.self) { TagLabel(text: $0) }
            ForEach(rules.subjects, id: \.self) { TagLabel(text: "#\($0)") }
            ForEach(rules.colors, id: \.self) { TagLabel(text: ColorTag.name($0), colorTag: $0) }
            if !rules.query.isEmpty { TagLabel(text: "„\(rules.query)”") }
            if let from = rules.yearFrom { TagLabel(text: "od \(String(from))") }
            if let to = rules.yearTo { TagLabel(text: "do \(String(to))") }
            if rules.favoritesOnly { TagLabel(text: "♥ ulubione") }
            ForEach(rules.sources, id: \.self) { TagLabel(text: Names.source($0)) }
            ForEach(rules.excludeSources, id: \.self) { TagLabel(text: "bez \(Names.source($0))") }
        }
    }
}
