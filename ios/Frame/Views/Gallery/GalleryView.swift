import CoreImage
import SwiftUI

/// "Galeria", the first tab (Mateusz 2026-11-23): works one after another on
/// the whole screen, cut to fill it. A swipe up brings the next, down the one
/// before; the order is the person's own (`GET /api/gallery`: their hearts,
/// works like them, new ones). Cut to the screen, the work has only the
/// glass heart in its top corner; a tap draws it back to the whole of it
/// on its own colour, with its caption and the tab bar (Mateusz 2026-11-23
/// 17:42: "Jednak bez widocznego tytułu i paska menu. Samo serduszko. Pasek
/// menu, autor i tytuł po kliknięciu"), and another cuts it to the screen
/// again. The caption opens the work's card; a double tap gives a heart,
/// red pouring into the corner's; a hold opens the work's menu.
struct GalleryView: View {
    @Environment(AppModel.self) private var model
    /// The works not seen yet when the app was last left: shown at once on
    /// the next launch while the server is asked for more (Mateusz
    /// 2026-11-23: "czarny ekran zaraz po otwarciu").
    @State private var works: [RemoteItem] = GalleryView.remembered()
    @State private var position: String?
    /// The work shown whole (tapped), till the next one or another tap.
    @State private var whole: String?
    @State private var loading = false
    @State private var failed = false
    @State private var path: [String] = []
    /// Double taps given, for the corner heart's flash.
    @State private var flashes = 0

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
                    if let shown, whole == shown.id {
                        GalleryCaption(work: shown) { open(shown) }
                            .id(shown.id)
                            .transition(.opacity)
                    }
                }
                .overlay(alignment: .topTrailing) {
                    // Its own for each work: swiped to a work given a heart
                    // before, the red is there already, not pouring in.
                    if let shown { heartButton(shown).id(shown.id) }
                }
                .overlay {
                    if works.isEmpty { emptyState }
                }
                .animation(.easeInOut(duration: 0.2), value: shown?.id)
                .toolbarVisibility(.hidden, for: .navigationBar)
                .toolbarVisibility(whole != nil || !path.isEmpty ? .visible : .hidden, for: .tabBar)
                .statusBarHidden(whole == nil)
                .navigationDestination(for: String.self) { id in
                    ItemDetailView(itemID: id)
                }
        }
        .task { if works.count < Self.batch { await more() } }
        .onChange(of: position) { _, id in
            if whole != id { whole = nil }
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
                    GalleryPage(work: work, current: work.id == shown?.id, whole: whole == work.id)
                        .containerRelativeFrame([.horizontal, .vertical])
                        .contentShape(Rectangle())
                        .onTapGesture(count: 2) { heart(work) }
                        .onTapGesture {
                            // Quick (17:42: "szybciej i dynamiczniej").
                            withAnimation(.spring(duration: 0.32, bounce: 0.18)) {
                                whole = whole == work.id ? nil : work.id
                            }
                        }
                        .contextMenu { menu(work) } preview: {
                            // Drawn apart from the page: `ArtImage` needs the
                            // model (without it the hold crashed the app,
                            // Mateusz 2026-11-23 16:41).
                            ArtImage(ref: .thumb(work.id), contentMode: .fit)
                                .frame(width: 280)
                                .environment(model)
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

    /// The heart as on the tiles' corners (Mateusz 2026-11-23 16:32:
    /// "Szklane serduszko - jak w narożnikach miniatur"), lighting up on a
    /// double tap (16:41: "rozbłysk, wypełnienie czerwienią").
    private func heartButton(_ work: RemoteItem) -> some View {
        let on = model.liked(work.summary)
        return Button {
            Task { await model.like(work.summary, !on) }
        } label: {
            GalleryHeart(on: on, flashes: flashes)
                .padding(10)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .sensoryFeedback(.impact(weight: .light), trigger: on)
        .accessibilityLabel(on ? "Usuń z ulubionych" : "Dodaj do ulubionych")
        .padding(.trailing, Theme.gutter - 10)
        .padding(.top, 2)
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
        flashes += 1
    }

    private func open(_ work: RemoteItem) {
        ItemPeeks.remember(work.summary, thumb: .thumb(work.id))
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
/// przejście"). It starts a little closer and draws back, drifting a
/// little sideways.
private struct GalleryPage: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let work: RemoteItem
    /// On screen now: it draws back and drifts a little.
    var current = false
    /// Tapped: drawn back to the whole of it, above the caption.
    var whole = false

    @State private var thumb: UIImage?
    @State private var full: UIImage?
    @State private var focus: UnitPoint?
    /// The full picture over the thumbnail, 1 once it is in.
    @State private var fullShown: Double = 1
    /// The colours of the work's edges stretched out and blurred, for
    /// behind the whole of it (`Glow`); made when it is first tapped.
    @State private var glow: UIImage?
    /// How far the work has drifted from where it was cut (points).
    @State private var pan: CGFloat = 0
    /// Each work comes a little closer and slowly draws back while it is
    /// shown (Mateusz 2026-11-23 14:55 UTC: "zawsze zaczynaj od przybliżenia
    /// i oddalaj"), drifting a little to one side or the other as it does
    /// (17:01: "Jednak bez ruchu pod wpływem żyroskopu. Tylko oddalenie po
    /// startowym zoomie i bardzo delikatny ruch w bok (kierunek zmienny)").
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
                    let place = whole ? Whole(picture: shown.size, box: geo.size, safe: geo.safeAreaInsets) : nil
                    if let place, let glow {
                        Glow(edges: glow, place: place)
                            .transition(.opacity)
                    }
                    ZStack {
                        if let thumb { picture(thumb, layout, place) }
                        if let full { picture(full, layout, place).opacity(fullShown) }
                    }
                    .scaleEffect(reduceMotion || whole ? 1 : zoom, anchor: layout.anchor)
                    .offset(x: whole ? 0 : pan)
                    .frame(width: geo.size.width, height: geo.size.height)
                    .clipped()
                    .transition(.opacity)
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
            .task(id: current && geo.size.width > 0) { await drawBack(geo.size) }
        }
        .background(whole ? behind : placeholder)
        .task(id: work.id) { await load() }
        .task(id: whole) {
            guard whole, glow == nil, let picture = thumb ?? full else { return }
            let made = await Task.detached(priority: .userInitiated) { Glow.edges(of: picture) }.value
            withAnimation(.easeOut(duration: 0.25)) { glow = made }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(work.item.displayTitle)
    }

    /// Behind the whole work: its own main colour, quiet and dark
    /// (Mateusz 2026-11-23 17:42: "Tło za dziełem nie czarne, tylko
    /// wypełnione stonowaną barwą dzieła").
    private var behind: Color {
        let hex = work.item.colors.first?.hex ?? ""
        return Self.toned(UIColor(Color(hexString: hex) ?? .black))
    }

    static func toned(_ color: UIColor) -> Color {
        var hue: CGFloat = 0, saturation: CGFloat = 0, brightness: CGFloat = 0, alpha: CGFloat = 0
        color.getHue(&hue, saturation: &saturation, brightness: &brightness, alpha: &alpha)
        return Color(hue: hue, saturation: min(saturation * 0.7, 0.4), brightness: 0.2)
    }

    /// The work's own main colour, dimmed, while its picture comes.
    private var placeholder: Color {
        let hex = work.item.colors.first?.hex ?? ""
        return (Color(hexString: hex) ?? .black).opacity(0.35)
    }

    private func picture(_ image: UIImage, _ layout: Fill, _ place: Whole?) -> some View {
        Image(uiImage: image)
            .resizable()
            .interpolation(.high)
            .frame(width: place?.size.width ?? layout.size.width, height: place?.size.height ?? layout.size.height)
            .offset(place?.offset ?? layout.offset)
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

    private func drawBack(_ box: CGSize) async {
        guard current else {
            // Off the screen by then: closer again for the next time.
            try? await Task.sleep(for: .seconds(1))
            guard !Task.isCancelled else { return }
            var quiet = Transaction()
            quiet.disablesAnimations = true
            withTransaction(quiet) {
                zoom = Self.closer
                pan = 0
            }
            return
        }
        guard !reduceMotion else { return }
        withAnimation(.easeOut(duration: Self.drawBack)) { zoom = 1 }
        // The picture comes a moment after the page: the drift once it can
        // be cut, as far as its edges allow.
        while !Task.isCancelled, full ?? thumb == nil || focus == nil {
            try? await Task.sleep(for: .milliseconds(100))
        }
        guard !Task.isCancelled, let shown = full ?? thumb, let focus else { return }
        let layout = Fill(picture: shown.size, box: box, focus: focus)
        let low = -layout.room.width - layout.offset.width, high = layout.room.width - layout.offset.width
        let way: CGFloat = Bool.random() ? 1 : -1
        let to = min(max(way * Self.drift, low), high)
        withAnimation(.easeInOut(duration: Self.drawBack)) { pan = to }
    }

    /// How far a work drifts sideways while it draws back (points), at most.
    static let drift: CGFloat = 22
}

/// A tapped work drawn back to the whole of it (Mateusz 2026-11-23 16:32:
/// "Kliknięcie w dzieło - zmniejsza i pokazuje je w całości"): between the
/// status bar and the caption, a little in from the sides, on the dark.
private struct Whole {
    let size: CGSize
    let offset: CGSize

    /// The caption's share of the screen's height, and the margins.
    static let caption: CGFloat = 0.25
    static let side: CGFloat = 20
    static let gap: CGFloat = 12

    init(picture: CGSize, box: CGSize, safe: EdgeInsets) {
        // The pages ignore the safe area: the status bar's height as least.
        let top = max(safe.top, 59) + Self.gap
        let bottom = box.height * Self.caption
        let room = CGSize(width: box.width - Self.side * 2, height: max(box.height - top - bottom - Self.gap, 1))
        let scale = min(room.width / max(picture.width, 1), room.height / max(picture.height, 1))
        size = CGSize(width: picture.width * scale, height: picture.height * scale)
        offset = CGSize(width: 0, height: (top - bottom) / 2)
    }
}

/// Behind the whole work, the colours of its edges flowing out and
/// fading into its own quiet colour (Mateusz 2026-11-23 17:53: "rozmyte
/// ale od krawędzi. Takie łuny koloru"): only what is on each edge, the
/// edge's own pixels drawn outwards (17:55: "na krawędzi nie ma włosów.
/// Musimy brać kolor który faktycznie jest na krawędzi").
private struct Glow: View {
    let edges: UIImage
    let place: Whole

    /// How far the edges are drawn out on each side, as a share of the
    /// work's longer side; and their blur, as a share of it too.
    nonisolated static let reach: CGFloat = 0.6
    nonisolated static let softness: CGFloat = 0.05
    nonisolated(unsafe) private static let context = CIContext(options: [.cacheIntermediates: false])

    /// The picture with its edges drawn out by `reach` and blurred; the
    /// work itself sits in its middle.
    nonisolated static func edges(of picture: UIImage) -> UIImage? {
        guard let cg = picture.cgImage else { return nil }
        // Small is enough for a blur this wide.
        let long = CGFloat(max(cg.width, cg.height))
        let scale = min(1, 200 / long)
        let small = CIImage(cgImage: cg).transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        let extent = small.extent
        let pad = max(extent.width, extent.height) * reach
        let out = small.clampedToExtent()
            .applyingGaussianBlur(sigma: Double(max(extent.width, extent.height) * softness))
            .cropped(to: extent.insetBy(dx: -pad, dy: -pad))
        guard let made = context.createCGImage(out, from: out.extent) else { return nil }
        return UIImage(cgImage: made)
    }

    var body: some View {
        // The work's share of the made picture: 1 / (1 + 2 * reach * long / side).
        let long = max(place.size.width, place.size.height)
        let pad = long * Self.reach
        let size = CGSize(width: place.size.width + pad * 2, height: place.size.height + pad * 2)
        Image(uiImage: edges)
            .resizable()
            .frame(width: size.width, height: size.height)
            .mask {
                RadialGradient(
                    colors: [.white, .white.opacity(0.55), .clear],
                    center: .center, startRadius: long * 0.5, endRadius: long * 0.5 + pad
                )
            }
            .opacity(0.9)
            .offset(place.offset)
            .allowsHitTesting(false)
    }
}

/// The corner's glass heart, as on the tiles (`HeartMark`). Given, red
/// pours into it from the bottom with a little swell; no flash around it
/// (Mateusz 2026-11-23 17:42: "bez tego wielkiego rozbłysku na zewnątrz …
/// Wlanie się czerwieni wewnątrz może być bardziej efektowne, żywe").
private struct GalleryHeart: View {
    let on: Bool
    let flashes: Int
    @State private var level: CGFloat = 0

    private static let size: CGFloat = 26
    private static let red = Color(red: 0xD2 / 255, green: 0x46 / 255, blue: 0x3A / 255)

    var body: some View {
        HeartMark(on: false, size: Self.size)
            .overlay {
                // Red rising inside the glass, its top a little slanted.
                HeartShape()
                    .fill(
                        LinearGradient(
                            colors: [Self.red.opacity(0.95), Self.red.opacity(0.75)],
                            startPoint: .bottom, endPoint: .top
                        )
                    )
                    .mask(alignment: .bottom) {
                        GeometryReader { geo in
                            Rectangle()
                                .frame(height: geo.size.height * 1.3 * level)
                                .rotationEffect(.degrees(Double(1 - level) * 14))
                                .frame(maxHeight: .infinity, alignment: .bottom)
                        }
                    }
                    .padding(1)
            }
            .keyframeAnimator(initialValue: CGFloat(1), trigger: flashes) { heart, scale in
                heart.scaleEffect(scale)
            } keyframes: { _ in
                SpringKeyframe(1.18, duration: 0.15, spring: .snappy)
                SpringKeyframe(1, duration: 0.4, spring: .bouncy)
            }
            .onAppear { level = on ? 1 : 0 }
            .onChange(of: on) { _, now in
                if now {
                    level = 0
                    withAnimation(.spring(duration: 0.55, bounce: 0.35)) { level = 1 }
                } else {
                    withAnimation(.easeIn(duration: 0.25)) { level = 0 }
                }
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

/// The work's caption laid on its lower part (Mateusz 2026-11-23, variant 2:
/// no card, the text on a shade): the museum, the title with its year, the
/// artist and their nationality and years, as on the work's card. Tapped:
/// the card. The Polish texts are asked for once the work has stayed a moment.
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
        // Always shown now: asked for only once the work has stayed a moment,
        // not for each one swiped past.
        guard polish == nil, item.kind == .artwork else { return }
        try? await Task.sleep(for: .seconds(1.5))
        guard !Task.isCancelled,
              let view = try? await model.backend.polish(itemID: work.id, wait: 0, early: true),
              let text = view.text
        else { return }
        ItemPeeks.keep(text, for: work.id)
        withAnimation(.easeInOut(duration: 0.4)) { polish = text }
    }
}
