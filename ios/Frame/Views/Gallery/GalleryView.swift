import SwiftUI

/// "Galeria", the first tab (Mateusz 2026-11-23): works one after another on
/// the whole screen, cut to fill it. A swipe up brings the next, down the one
/// before; the order is the person's own (`GET /api/gallery`: their hearts,
/// works like them, new ones). A tap shows the work's caption on it, a glass
/// heart in the top corner and the tab bar; another tap takes them away. The caption opens the
/// work's card; a double tap gives a heart; a hold opens the work's menu.
struct GalleryView: View {
    @Environment(AppModel.self) private var model
    /// The works not seen yet when the app was last left: shown at once on
    /// the next launch while the server is asked for more (Mateusz
    /// 2026-11-23: "czarny ekran zaraz po otwarciu").
    @State private var works: [RemoteItem] = GalleryView.remembered()
    @State private var position: String?
    @State private var chrome = LaunchRoute.screen == "gallery-caption"
    @State private var loading = false
    @State private var failed = false
    @State private var path: [String] = []
    /// The heart that blooms where a double tap gave one.
    @State private var bloom: String?

    /// Works asked for at once, and how near the end the next are asked for.
    private static let batch = 12
    private static let ahead = 4

    private var shown: RemoteItem? {
        works.first { $0.id == position } ?? works.first
    }

    var body: some View {
        NavigationStack(path: $path) {
            pages
                .background(Color.black)
                .overlay(alignment: .bottom) {
                    if chrome, let shown {
                        GalleryCaption(work: shown) { open(shown) }
                            .transition(.opacity)
                    }
                }
                .overlay(alignment: .topTrailing) {
                    if chrome, let shown { heartButton(shown).transition(.opacity) }
                }
                .overlay {
                    if works.isEmpty { emptyState }
                }
                .animation(.easeInOut(duration: 0.2), value: chrome)
                .toolbarVisibility(.hidden, for: .navigationBar)
                .toolbarVisibility(chrome ? .visible : .hidden, for: .tabBar)
                .statusBarHidden(!chrome)
                .navigationDestination(for: String.self) { id in
                    ItemDetailView(itemID: id)
                }
        }
        .task { if works.count < Self.batch { await more() } }
        .onChange(of: position) { _, id in
            guard let id, let index = works.firstIndex(where: { $0.id == id }) else { return }
            Self.remember(Array(works.dropFirst(index + 1)))
            if index >= works.count - Self.ahead { Task { await more() } }
        }
        // Hearts given here change what comes next: a fresh batch is asked
        // for when the library changes, after the works not seen yet.
    }

    private var pages: some View {
        ScrollView(.vertical) {
            LazyVStack(spacing: 0) {
                ForEach(works) { work in
                    GalleryPage(work: work, current: work.id == shown?.id, bloom: bloom == work.id)
                        .containerRelativeFrame([.horizontal, .vertical])
                        .contentShape(Rectangle())
                        .onTapGesture(count: 2) { heart(work) }
                        .onTapGesture { chrome.toggle() }
                        .contextMenu { menu(work) } preview: {
                            ArtImage(ref: .thumb(work.id), contentMode: .fit)
                                .frame(width: 280)
                        }
                        .id(work.id)
                }
            }
            .scrollTargetLayout()
        }
        .scrollTargetBehavior(.paging)
        .scrollPosition(id: $position)
        .scrollIndicators(.hidden)
        .ignoresSafeArea()
    }

    private var emptyState: some View {
        VStack(spacing: 14) {
            if failed {
                Text(bound: "Nie udało się wczytać dzieł.")
                    .foregroundStyle(.white.opacity(0.8))
                Button("Spróbuj ponownie", systemImage: "arrow.clockwise") {
                    Task { await more() }
                }
                .buttonStyle(.glass)
            } else {
                ProgressView().tint(.white)
            }
        }
    }

    private func heartButton(_ work: RemoteItem) -> some View {
        let on = model.liked(work.summary)
        return Button {
            Task { await model.like(work.summary, !on) }
        } label: {
            Image(systemName: on ? "heart.fill" : "heart")
                .font(.title3.weight(.medium))
                .foregroundStyle(on ? Theme.heart : .white)
                .frame(width: 30, height: 30)
                .contentTransition(.symbolEffect(.replace))
        }
        .buttonStyle(.glass)
        .buttonBorderShape(.circle)
        .environment(\.colorScheme, .dark)
        .accessibilityLabel(on ? "Usuń z ulubionych" : "Dodaj do ulubionych")
        .padding(.trailing, Theme.gutter)
        .padding(.top, 4)
    }

    @ViewBuilder
    private func menu(_ work: RemoteItem) -> some View {
        Button("Otwórz kartę dzieła", systemImage: "info.circle") { open(work) }
        let on = model.liked(work.summary)
        Button(on ? "Usuń z ulubionych" : "Dodaj do ulubionych", systemImage: on ? "heart.slash" : "heart") {
            Task { await model.like(work.summary, !on) }
        }
        if !model.isGuest {  // a guest sends nothing to the frame
            Button("Pokaż na ramce", systemImage: "photo") {
                Task { _ = await model.show(itemID: work.id, hold: .untilNextChange) }
            }
            Button("Dodaj do kolejki", systemImage: "text.line.first.and.arrowtriangle.forward") {
                Task { await model.queueNext(itemID: work.id) }
            }
        }
    }

    private func heart(_ work: RemoteItem) {
        let summary = work.summary
        if !model.liked(summary) { Task { await model.like(summary, true) } }
        bloom = work.id
        Task {
            try? await Task.sleep(for: .milliseconds(900))
            if bloom == work.id { bloom = nil }
        }
    }

    private func open(_ work: RemoteItem) {
        ItemPeeks.remember(work.summary, thumb: .thumb(work.id))
        chrome = true  // the tab bar under the card, as elsewhere
        path.append(work.id)
    }

    private static let rememberedKey = "gallery.next"
    private static let rememberedMost = 24

    /// The works left to see, kept for the next launch (CI screenshots
    /// start from the demo's own order).
    private static func remembered() -> [RemoteItem] {
        guard LaunchRoute.screen.isEmpty,
              let data = UserDefaults.standard.data(forKey: rememberedKey),
              let works = try? JSONDecoder().decode([RemoteItem].self, from: data)
        else { return [] }
        return works
    }

    private static func remember(_ works: [RemoteItem]) {
        guard let data = try? JSONEncoder().encode(Array(works.prefix(rememberedMost))) else { return }
        UserDefaults.standard.set(data, forKey: rememberedKey)
    }

    private func more() async {
        guard !loading else { return }
        loading = true
        defer { loading = false }
        do {
            let next = try await model.backend.gallery(count: Self.batch)
            failed = false
            let have = Set(works.map(\.id))
            works += next.filter { !have.contains($0.id) }
            if position == nil { position = works.first?.id }
            let at = works.firstIndex { $0.id == position } ?? 0
            Self.remember(Array(works.dropFirst(at + 1)))
        } catch {
            failed = works.isEmpty
        }
    }
}

/// One work on the whole screen, cut to fill it around what draws the eye.
/// The thumbnail comes first; the full picture fades in over it, cut around
/// the same point so nothing moves (Mateusz 2026-11-23: "mignięcie/
/// przesunięcie"; a focus pull "wygląda źle, zróbmy jednak delikatne
/// przejście"). A work much wider than the screen moves across very slowly
/// as the phone is turned (`Pan`).
private struct GalleryPage: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let work: RemoteItem
    /// On screen now: a wide work follows the phone's turn.
    var current = false
    var bloom = false

    @State private var thumb: UIImage?
    @State private var full: UIImage?
    @State private var focus: UnitPoint?
    /// The full picture over the thumbnail, 1 once it is in.
    @State private var fullShown: Double = 1
    /// How far a wide work has moved from where it was cut (points).
    @State private var pan: CGFloat = 0
    /// Each work comes a little closer and slowly draws back while it is
    /// shown (Mateusz 2026-11-23 14:55 UTC: "zawsze zaczynaj od przybliżenia
    /// i oddalaj"); the move sideways is the turn's alone (`follow`).
    @State private var zoom: CGFloat = GalleryPage.closer
    static let closer: CGFloat = 1.06
    /// Seconds to draw back from `closer` to the whole picture.
    static let drawBack: Double = 20

    private static let thumbPixel: CGFloat = 900
    private static let fullPixel: CGFloat = 2800

    var body: some View {
        GeometryReader { geo in
            ZStack {
                if let shown = full ?? thumb, let focus {
                    let layout = Fill(picture: shown.size, box: geo.size, focus: focus)
                    ZStack {
                        if let thumb { picture(thumb, layout) }
                        if let full { picture(full, layout).opacity(fullShown) }
                    }
                    .scaleEffect(reduceMotion ? 1 : zoom, anchor: layout.anchor)
                    .offset(x: layout.wide ? pan : 0)
                    .frame(width: geo.size.width, height: geo.size.height)
                    .clipped()
                    .transition(.opacity)
                }
                if bloom {
                    Image(systemName: "heart.fill")
                        .font(.system(size: 96))
                        .foregroundStyle(.white.opacity(0.92))
                        .shadow(color: .black.opacity(0.35), radius: 12)
                        .transition(.scale(scale: 0.4).combined(with: .opacity))
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
            .task(id: geo.size.width > 0 && current && !reduceMotion) { await follow(geo.size) }
            .task(id: current) { await drawBack() }
        }
        .background(placeholder)
        .animation(.spring(duration: 0.35), value: bloom)
        .task(id: work.id) { await load() }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(work.item.displayTitle)
    }

    /// The work's own main colour, dimmed, while its picture comes.
    private var placeholder: Color {
        let hex = work.item.colors.first?.hex ?? ""
        return (Color(hexString: hex) ?? .black).opacity(0.35)
    }

    private func picture(_ image: UIImage, _ layout: Fill) -> some View {
        Image(uiImage: image)
            .resizable()
            .interpolation(.high)
            .frame(width: layout.size.width, height: layout.size.height)
            .offset(layout.offset)
    }

    private func load() async {
        guard let thumbRequest = model.backend.request(for: .thumb(work.id)),
              let fullRequest = model.backend.request(for: .image(work.id))
        else { return }
        // In memory already (seen a moment ago): from the first frame.
        if let image = ImageLoader.inMemory(for: fullRequest, maxPixel: Self.fullPixel) {
            await settle(image, key: ImageLoader.pictureKey(fullRequest))
            full = image
            return
        }
        if let image = ImageLoader.inMemory(for: thumbRequest, maxPixel: Self.thumbPixel) {
            await settle(image, key: ImageLoader.pictureKey(thumbRequest))
            thumb = image
        } else if let image = try? await ImageLoader.shared.image(for: thumbRequest, maxPixel: Self.thumbPixel) {
            await settle(image, key: ImageLoader.pictureKey(thumbRequest))
            withAnimation(.easeOut(duration: 0.3)) { thumb = image }
        }
        guard !Task.isCancelled,
              let image = try? await ImageLoader.shared.image(
                  for: fullRequest, maxPixel: Self.fullPixel, priority: current ? .high : .normal
              ),
              !Task.isCancelled
        else { return }
        await settle(image, key: ImageLoader.pictureKey(fullRequest))
        guard thumb != nil else {
            withAnimation(.easeOut(duration: 0.3)) { full = image }
            return
        }
        // Over the thumbnail, gently.
        fullShown = 0
        full = image
        withAnimation(.easeInOut(duration: 0.7)) { fullShown = 1 }
    }

    /// The point the picture is cut around: found once, on whichever
    /// picture comes first, and kept for the other.
    private func settle(_ image: UIImage, key: String) async {
        guard focus == nil else { return }
        focus = await SubjectFocus.shared.point(in: image, key: key, subject: true)
    }

    /// A wide work moves only once the phone is turned, the way it was
    /// turned, and on very slowly after (Mateusz 2026-11-23: "zdecydowanie
    /// zbyt szybka. to musi być minimalny ruch. Ruch niech startuje pod
    /// żyroskopem - to on nadaje kierunek i ew przyspiesza animację").
    private func drawBack() async {
        guard current else {
            // Off the screen by then: closer again for the next time.
            try? await Task.sleep(for: .seconds(1))
            guard !Task.isCancelled else { return }
            var quiet = Transaction()
            quiet.disablesAnimations = true
            withTransaction(quiet) { zoom = Self.closer }
            return
        }
        withAnimation(.easeOut(duration: Self.drawBack)) { zoom = 1 }
    }

    private func follow(_ box: CGSize) async {
        guard current, !reduceMotion, !ProcessInfo.processInfo.isLowPowerModeEnabled else { return }
        let tilt = Tilt.shared
        tilt.start()
        defer { tilt.stop() }
        var pace = Pan()
        let step = 1.0 / 30
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(step))
            guard let shown = full ?? thumb, let focus else { continue }
            let layout = Fill(picture: shown.size, box: box, focus: focus)
            guard layout.wide else { continue }
            // Where the picture may lie: +room shows its left edge.
            let room = layout.room.width
            let low = -room - layout.offset.width, high = room - layout.offset.width
            let next = min(max(pan + pace.advance(tilt: tilt.x, by: step), low), high)
            if next != pan { pan = next }
            if next == low || next == high { pace.stopped() }
        }
    }
}

/// A picture cut to fill a box around `focus`: its size and where it lies.
private struct Fill {
    let size: CGSize
    let offset: CGSize
    /// How far it can move either way and still fill the box.
    let room: CGSize
    let focus: UnitPoint

    init(picture: CGSize, box: CGSize, focus: UnitPoint) {
        let scale = max(box.width / max(picture.width, 1), box.height / max(picture.height, 1))
        size = CGSize(width: picture.width * scale, height: picture.height * scale)
        room = CGSize(width: max(size.width - box.width, 0) / 2, height: max(size.height - box.height, 0) / 2)
        offset = CGSize(
            width: min(max((0.5 - focus.x) * size.width, -room.width), room.width),
            height: min(max((0.5 - focus.y) * size.height, -room.height), room.height)
        )
        self.focus = focus
    }

    /// Where `focus` is seen, as a point of the picture's own frame
    /// (`size`, centred on the box): the draw-back keeps it in place.
    var anchor: UnitPoint {
        let x = (focus.x - 0.5) * size.width + offset.width
        let y = (focus.y - 0.5) * size.height + offset.height
        return UnitPoint(
            x: min(max(0.5 + x / max(size.width, 1), 0), 1),
            y: min(max(0.5 + y / max(size.height, 1), 0), 1)
        )
    }

    /// Much wider than the box: a good part of it is cut off.
    var wide: Bool { room.width * 2 > size.width * 0.3 }
}

/// How a wide work moves with the phone's turn: still until it is turned;
/// then the way it was turned (turned right, the right part comes in), a
/// little faster while it is turned, and on very slowly after, until its
/// edge. Points a second.
private struct Pan {
    /// After a turn, the slow way on.
    static let creep: Double = 2.5
    /// The most a turn adds: still a slow move.
    static let turned: Double = 16
    /// A turn smaller than this is the hand's shake (`Tilt.x`, -1…1).
    static let still: Double = 0.12

    private var way: Double = 0
    private var speed: Double = 0

    mutating func advance(tilt: Double, by step: Double) -> CGFloat {
        if abs(tilt) > Self.still { way = tilt > 0 ? -1 : 1 }
        let along = way == 0 ? 0 : max(0, -tilt * way)
        let goal = way == 0 ? 0 : Self.creep + Self.turned * min(along, 1)
        // Speeds up within a second, slows down over a couple (Mateusz
        // 2026-11-23 15:50: "Trochę większa dynamika po przechyleniu").
        let ease = goal > speed ? 1.6 : 0.8
        speed += (goal - speed) * min(step * ease, 1)
        return CGFloat(way * speed * step)
    }

    mutating func stopped() {
        speed = 0
    }
}

/// The work's caption laid on its lower part (Mateusz 2026-11-23, variant 2:
/// no card, the text on a shade): the museum, the title with its year, the
/// artist and their nationality and years, as on the work's card. Tapped:
/// the card. The Polish texts are asked for only once the caption is shown.
private struct GalleryCaption: View {
    @Environment(AppModel.self) private var model
    let work: RemoteItem
    let open: () -> Void
    @State private var polish: PolishText?

    private var item: Item { work.item }

    var body: some View {
        Button(action: open) {
            HStack(alignment: .center, spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    let held = item.kind == .artwork ? item.heldBy ?? Names.source(item.source) : Names.source(item.source)
                    if !held.isEmpty { Eyebrow(held, color: Theme.vermilion) }
                    TitleWithYear(
                        title: title,
                        date: nonEmpty(polish?.date) ?? item.dateText,
                        font: .serif(26, weight: .semibold)
                    )
                    .fixedSize(horizontal: false, vertical: true)
                    .lineLimit(3)
                    VStack(alignment: .leading, spacing: 0) {
                        if !item.artist.isEmpty {
                            Text(bound: Names.artist(item.artist))
                                .font(.serif(19))
                                .foregroundStyle(Theme.ink)
                                .lineLimit(1)
                        }
                        let bio = nonEmpty(polish?.artistNote) ?? item.artistBio
                        if !bio.isEmpty {
                            Text(bound: bio).font(.subheadline).foregroundStyle(Theme.inkSoft).lineLimit(1)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.horizontal, Theme.gutter + 2)
            .padding(.top, 70)
            .padding(.bottom, 12)
            .background(alignment: .bottom) {
                LinearGradient(
                    stops: [
                        .init(color: .black.opacity(0), location: 0),
                        .init(color: .black.opacity(0.55), location: 0.45),
                        .init(color: .black.opacity(0.8), location: 1),
                    ],
                    startPoint: .top, endPoint: .bottom
                )
                .padding(.bottom, -140)  // under the tab bar too
                .allowsHitTesting(false)
            }
        }
        .buttonStyle(.plain)
        // Light text on the shade in both modes.
        .environment(\.colorScheme, .dark)
        .task(id: work.id) { await loadPolish() }
    }

    private var title: String {
        nonEmpty(polish?.title) ?? nonEmpty(work.titlePl)
            ?? (item.displayTitle.isEmpty ? "Bez tytułu" : item.displayTitle)
    }

    private func nonEmpty(_ text: String?) -> String? {
        guard let text, !text.isEmpty else { return nil }
        return text
    }

    private func loadPolish() async {
        polish = ItemPeeks.polish[work.id]
        guard polish == nil, item.kind == .artwork,
              let view = try? await model.backend.polish(itemID: work.id, wait: 0, early: true),
              let text = view.text
        else { return }
        ItemPeeks.keep(text, for: work.id)
        withAnimation(.easeInOut(duration: 0.4)) { polish = text }
    }
}
