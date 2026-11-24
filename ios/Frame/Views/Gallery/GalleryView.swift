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
    /// The works shown whole (tapped), kept from one work to the next till
    /// another tap (Mateusz 2026-11-24: "przewijając do kolejnego zostawiaj
    /// ekran całego dzieła").
    @State private var whole = false
    @State private var loading = false
    @State private var failed = false
    @State private var path: [String] = []
    /// Swiped past too fast: the works coming as a grid (`GalleryGrid`).
    /// `grid` while it is there at all, `gridOpen` once it has grown out of
    /// the work (and till it goes back into one), `gridGoing` once it lies
    /// where it is to be and flows on.
    @State private var grid = false
    @State private var gridOpen = false
    @State private var gridGoing = false
    /// The first of the works seen before, shown above the line.
    @State private var gridBefore = 0
    /// A long drag from left to right, as a share of the screen's width:
    /// the work shrinks as it goes, and the grid of the works seen comes
    /// (14:26: "długie przeciągnięcie (nie krótkie machnięcie) wstecz to
    /// dzieło się zmniejsza i przechodzę do siatki (historii tego co było)").
    @State private var pull: CGFloat = 0
    /// A slow drag down under way: the scroll gives way to it.
    @State private var pulling = false
    @State private var speed = SwipeSpeed()
    @State private var gridFrames = GridFrames()
    @State private var stock = GridStock()
    /// How fast the pages were swiped, for the grid to flow on as fast.
    @State private var flow = SwipeFlow()
    @State private var gridSpeed: CGFloat = 0
    /// Where the grid's content starts below its top (the status bar).
    @State private var gridInset: CGFloat = 0
    /// The first work in the grid: the one before the work shown, on the
    /// cut works, so that one lands in the middle of the top row.
    @State private var gridStart = 0
    /// How the grid and the pages meet: the work's tile in the grid
    /// (`gridAnchor`, its middle in the grid's frame) lies, grown
    /// `gridScale` times and moved by `gridShift`, where the work lies on
    /// its page (`pageMask`, in the pages' frame; `pageAnchor` its middle),
    /// and the page shrinks and moves (`pageShift`) into the tile.
    @State private var gridAnchor = UnitPoint.topLeading
    @State private var gridShift = CGSize.zero
    @State private var pageAnchor = UnitPoint.center
    @State private var pageShift = CGSize.zero
    @State private var pageMask = CGRect.zero
    @State private var gridScale: CGFloat = 3
    @State private var gridArea: CGRect = .zero
    @State private var pagesArea: CGRect = .zero
    /// The end page's glow over the first new work as it fades away.
    @State private var surfacing = false
    /// The cut work whose card is opening (`GalleryPage.leaving`).
    @State private var leaving: String?
    /// Double taps given, for the corner heart's flash.
    @State private var flashes = 0
    /// The works ahead being cut down to the work, one at a time.
    @State private var cutting: Task<Void, Never>?
    /// Works looked at for a cut here since the app started.
    @MainActor private static var looked: Set<String> = []

    /// Works asked for at once, and how near the end the next are asked for.
    /// Asked for well before the end (Mateusz 2026-11-24: "niech aplikacja
    /// wcześniej prosi o kolejne"), so the end is seldom reached.
    private static let batch = 16
    private static let ahead = 8
    /// The page after the last work, while more are on their way.
    static let endID = "gallery.end"

    private var shown: RemoteItem? {
        if position == Self.endID { return nil }
        return works.first { $0.id == position } ?? works.first
    }

    /// The glow the end page and a work coming out of it are made of: the
    /// last works' colours.
    private var endColours: [Color] {
        works.suffix(4).compactMap { $0.item.colors.first?.hex }.compactMap { Color(hexString: $0) }
    }

    var body: some View {
        NavigationStack(path: $path) {
            pages
                .background(Color.black)
                .onGeometryChange(for: CGRect.self) { $0.frame(in: .global) } action: { pagesArea = $0 }
                .clipShape(RoundedRectangle(cornerRadius: pull > 0 ? 24 * pull : 0, style: .continuous))
                .scaleEffect(1 - Self.pullShrink * pull)
                .offset(y: pull * pagesArea.height * Self.pullFollow)
                // Drawn back with the grid, into the work's tile (Mateusz
                // 2026-11-24 10:48: "musi skalować (jakby oddalać i płynnie
                // przechodzić z pełnego dzieła do siatki"): cut to the
                // tile's shape, and its middle to the tile's.
                .mask(alignment: .topLeading) {
                    let shape = gridOpen ? pageMask : wholeMask
                    RoundedRectangle(cornerRadius: gridOpen ? 6 * gridScale : 0, style: .continuous)
                        .frame(width: shape.width, height: shape.height)
                        .offset(x: shape.minX, y: shape.minY)
                }
                .scaleEffect(gridOpen ? 1 / gridScale : 1, anchor: pageAnchor)
                .offset(gridOpen ? pageShift : .zero)
                .opacity(gridOpen ? 0 : 1)
                .overlay(alignment: .topTrailing) {
                    // Its own for each work: swiped to a work given a heart
                    // before, the red is there already, not pouring in.
                    if let shown, !grid { heartButton(shown).id(shown.id) }
                }
                .overlay { gridLayer }
                .overlay {
                    if works.isEmpty { emptyState }
                }
                .overlay {
                    // The first of the new works coming out of the glow.
                    if surfacing {
                        GalleryWaiting(colours: endColours)
                            .ignoresSafeArea()
                            .allowsHitTesting(false)
                            .transition(.opacity)
                    }
                }
                .animation(.easeInOut(duration: 0.2), value: shown?.id)
                .toolbarVisibility(.hidden, for: .navigationBar)
                .toolbarVisibility(whole || !path.isEmpty ? .visible : .hidden, for: .tabBar)
                .statusBarHidden(!whole)
                .navigationDestination(for: String.self) { id in
                    ItemDetailView(itemID: id)
                }
        }
        .task { if works.count < Self.batch { await more() } }
        .onChange(of: path) { _, now in if now.isEmpty { leaving = nil } }
        .task(id: position == Self.endID) {
            // On the end page: asked again till the works come.
            while position == Self.endID, !Task.isCancelled {
                await more()
                guard position == Self.endID else { return }
                try? await Task.sleep(for: .seconds(4))
            }
        }
        .onChange(of: position) { _, id in
            guard let id, let index = works.firstIndex(where: { $0.id == id }) else { return }
            if !grid, pull == 0, path.isEmpty, speed.reached() { openGrid() }
            Self.remember(Array(works.dropFirst(index + 1)))
            if index >= works.count - Self.ahead { Task { await more() } }
            cutAhead()
        }
        // Hearts given here change what comes next: a fresh batch is asked
        // for when the library changes, after the works not seen yet.
    }

    private var pages: some View {
        ScrollView(.vertical) {
            LazyVStack(spacing: 0) {
                ForEach(Array(works.enumerated()), id: \.element.id) { index, work in
                    GalleryPage(
                        work: work, current: work.id == shown?.id, whole: whole,
                        above: index > 0 ? works[index - 1] : nil,
                        below: index + 1 < works.count ? works[index + 1] : nil,
                        leaving: leaving == work.id,
                        flip: { flip(work) }, open: { open(work) }
                    )
                        .containerRelativeFrame([.horizontal, .vertical])
                        .contentShape(Rectangle())
                        .onTapGesture(count: 2) { heart(work) }
                        .onTapGesture { flip(work) }
                        // UIKit's gestures, beside the scroll, never holding
                        // it back (14:06: "nie łapie machnięcia palca").
                        // A slow drag down: the work shrinks and the grid of
                        // the works seen comes (16:29; no swipe to the right
                        // any more: "Machniecie w prawo w ogóle zlikwidujmy").
                        .gesture(PullDown(
                            began: { pulling = !grid },
                            changed: { move in pulled(move) },
                            ended: { move in released(move) }
                        ))
                        // A hold shows the whole work (2026-11-23 21:41: "Do
                        // ekranu całego dzieła wchodzi także przytrzymanie").
                        .gesture(GalleryHold {
                            guard !whole else { return }
                            flip(work)
                        })
                        .sensoryFeedback(.impact(weight: .light), trigger: whole)
                        .id(work.id)
                }
                // At the end of what came, only the glow, flowing, till the
                // next works are here (Mateusz 2026-11-24: "łuny … tańczą
                // organicznie"; "Bez kwadracików i tekstu - sama łuna").
                if !works.isEmpty {
                    GalleryWaiting(colours: endColours)
                        .containerRelativeFrame([.horizontal, .vertical])
                        .id(Self.endID)
                }
            }
            .scrollTargetLayout()
        }
        .scrollTargetBehavior(.paging)
        .scrollPosition(id: $position)
        .scrollDisabled(pulling || grid)
        .onScrollGeometryChange(for: CGFloat.self) { $0.contentOffset.y } action: { _, y in flow.note(y) }
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
                // Seen on the light paper too.
                .shadow(color: .black.opacity(0.18), radius: 3, y: 1)
                .padding(10)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .sensoryFeedback(.impact(weight: .light), trigger: on)
        .accessibilityLabel(on ? "Usuń z ulubionych" : "Dodaj do ulubionych")
        .padding(.trailing, Theme.gutter - 10)
        .padding(.top, 2)
    }

    /// The works whole, or cut to the screen again: a tap on it or on its
    /// title or a hold to see it whole (Mateusz
    /// 2026-11-23 21:41, 2026-11-24).
    private func flip(_ work: RemoteItem) {
        // The page melts one into the other with its own timings
        // (`GalleryPage`); this is the rest's.
        withAnimation(GalleryPage.toWhole) {
            whole.toggle()
        }
    }

    // MARK: The grid

    /// How much closer a work starts on its page than the whole of it, and
    /// its tile in the grid with it.
    static let closer: CGFloat = 1.06

    /// The thumbnails' size in the grid, also fetched ahead.
    static let gridPixel: CGFloat = 420
    /// Works the grid has ready ahead of the one shown when it comes
    /// (14:06: "Powinien być też większy - teraz ściana szybko się kończy").
    static let gridReady = 160
    /// Works asked for at once while the grid is up.
    static let gridBatch = 40

    private var gridLayer: some View {
        GeometryReader { geo in
            if grid {
                GalleryGrid(
                    before: Array(works[min(gridBefore, gridStart) ..< min(gridStart, works.count)]),
                    works: Array(works.dropFirst(gridStart)), whole: whole,
                    frames: gridFrames, stock: stock,
                    tall: pagesArea.width > 0 ? pagesArea.height / pagesArea.width : 2.17,
                    going: gridGoing, speed: gridSpeed,
                    pick: { closeGrid(on: $0) },
                    more: { Task { await more(count: Self.gridBatch) } }
                )
                .background((whole ? Theme.paper : Color.black).ignoresSafeArea())
                .modifier(
                    gridOpen
                        ? GridZoom(scale: 1, anchor: gridAnchor, shift: .zero, opacity: 1)
                        : GridZoom(scale: gridScale, anchor: gridAnchor, shift: gridShift, opacity: 0)
                )
                .allowsHitTesting(gridOpen)
                .transition(.identity)
            }
        }
        .onGeometryChange(for: CGRect.self) { $0.frame(in: .global) } action: { gridArea = $0 }
        .onGeometryChange(for: CGFloat.self) { $0.safeAreaInsets.top } action: { gridInset = $0 }
    }

    /// The pages' own shape, uncut.
    private var wholeMask: CGRect {
        guard pagesArea.width > 0 else { return CGRect(x: -4000, y: -4000, width: 8000, height: 8000) }
        return CGRect(origin: .zero, size: pagesArea.size)
    }

    private func unit(_ point: CGPoint, in area: CGRect) -> UnitPoint {
        UnitPoint(x: (point.x - area.minX) / max(area.width, 1), y: (point.y - area.minY) / max(area.height, 1))
    }

    /// Where a work lies on its page, on the screen: the cut work's middle
    /// in the tile's shape, or the whole work where its page puts it.
    private func place(of work: RemoteItem) -> CGRect {
        let box = pagesArea.size
        let middle = CGPoint(x: pagesArea.midX, y: pagesArea.midY)
        if whole {
            let aspect = CGFloat(max(work.summary.aspectRatio, 0.05))
            let place = Whole(
                picture: CGSize(width: aspect, height: 1), box: box,
                safe: GalleryPage.lastSafe, caption: GalleryPage.lastCaption
            )
            return CGRect(
                x: middle.x - place.size.width / 2, y: middle.y + place.offset.height - place.size.height / 2,
                width: place.size.width, height: place.size.height
            )
        }
        // The tile is the screen's shape: the whole page goes into it.
        return pagesArea
    }

    /// The grid and the pages set to meet: the work on its page (`place`)
    /// and its tile, each the other's size and in the other's place.
    private func meet(place: CGRect, tile: CGRect) {
        gridScale = max(place.width / max(tile.width, 1), 1.01)
        gridAnchor = unit(CGPoint(x: tile.midX, y: tile.midY), in: gridArea)
        gridShift = CGSize(width: place.midX - tile.midX, height: place.midY - tile.midY)
        pageAnchor = unit(CGPoint(x: place.midX, y: place.midY), in: pagesArea)
        pageShift = CGSize(width: tile.midX - place.midX, height: tile.midY - place.midY)
        pageMask = place.offsetBy(dx: -pagesArea.minX, dy: -pagesArea.minY)
    }

    /// The grid grows out of the work shown: the work draws back into its
    /// tile, in the middle of the top row (cut works) or at the head of
    /// the left column (whole ones), the works seen before above it, and
    /// the grid flows on as fast as the works were swiped, slowing as a
    /// flicked list does (Mateusz 2026-11-24 14:06: "rozpęd … powinien
    /// być większy. Teraz jakby stopuje. Prędkość powinna być zgodna z
    /// ostatnim machnięciem. Nawet kosztem kilku dzieł"). From a long
    /// drag back it flows back a little, into the works seen (14:26).
    /// The grid is laid out first, unseen, and the work goes into its tile
    /// where the tile really is.
    private func openGrid(back: Bool = false) {
        guard !grid, let at = works.firstIndex(where: { $0.id == position }) else { return }
        let id = works[at].id
        gridStart = !whole && at > 0 ? at - 1 : at
        gridBefore = max(gridStart - (whole ? Self.seenCards : Self.seenTiles), 0)
        gridSpeed = back ? -GalleryGrid.least : flow.recent
        gridFrames.frames = [:]
        gridScale = 1
        gridShift = .zero
        gridOpen = false
        gridGoing = false
        speed.reset()
        stockFor(at)
        let quiet = Self.quiet
        withTransaction(quiet) { grid = true }
        Task { @MainActor in
            // Laid out and set at the line: a few frames at most.
            for _ in 0 ..< 24 {
                try? await Task.sleep(for: .milliseconds(16))
                if let frame = gridFrames.frames[id], frame.width > 0, gridArea.intersects(frame) { break }
            }
            let tile = gridFrames.frames[id].flatMap { $0.width > 0 ? $0 : nil }
                ?? CGRect(x: gridArea.midX - 60, y: gridArea.minY + gridInset, width: 120, height: 120)
            withTransaction(quiet) { meet(place: place(of: works[at]), tile: tile) }
            await Task.yield()
            withAnimation(.smooth(duration: 0.45)) {
                gridOpen = true
                pull = 0
            }
            gridGoing = true
            await stockUp(from: at)
        }
    }

    /// Works seen before, above the line: tiles, cards.
    static let seenTiles = 60
    static let seenCards = 24

    /// Plenty of works ahead for the grid, their thumbnails fetched.
    private func stockUp(from at: Int) async {
        for _ in 0 ..< 8 where works.count - at < Self.gridReady {
            if loading { try? await Task.sleep(for: .milliseconds(200)) }
            await more(count: Self.gridBatch)
        }
        stockFor(at)
    }

    /// The thumbnails about the work shown kept, those ahead fetched.
    private func stockFor(_ at: Int) {
        let kept = works[max(at - Self.seenTiles - 3, 0) ..< min(at + Self.gridReady + 60, works.count)]
        stock.keep(Set(kept.map(\.id)))
        prefetch(works.dropFirst(at).prefix(Self.gridReady))
        prefetch(works[max(at - Self.seenTiles, 0) ..< at].reversed())
    }

    /// Thumbnails fetched before they are shown, at the grid's size, six at
    /// a time, and held in the grid's stock.
    private func prefetch(_ some: some Sequence<RemoteItem>) {
        let kept = stock
        let jobs = some.filter { kept.images[$0.id] == nil }
            .compactMap { work in model.backend.request(for: .thumb(work.id)).map { (work.id, $0) } }
        guard !jobs.isEmpty else { return }
        let pixel = Self.gridPixel
        Task(priority: .utility) {
            await withTaskGroup(of: (String, UIImage?, UnitPoint).self) { group in
                var next = jobs.makeIterator()
                for _ in 0 ..< 6 {
                    if case let (id, request)? = next.next() { group.addTask { await Self.fetch(id, request, pixel) } }
                }
                while case let (done, image, focus)? = await group.next() {
                    if let image {
                        kept.images[done] = image
                        kept.focus[done] = focus
                    }
                    if case let (id, request)? = next.next() { group.addTask { await Self.fetch(id, request, pixel) } }
                }
            }
        }
    }

    /// A thumbnail for the grid, and the point its page will cut it about
    /// (found on it once, kept under its address for the page too).
    nonisolated private static func fetch(
        _ id: String, _ request: URLRequest, _ pixel: CGFloat
    ) async -> (String, UIImage?, UnitPoint) {
        guard let image = try? await ImageLoader.shared.image(for: request, maxPixel: pixel) else {
            return (id, nil, .center)
        }
        let focus = await SubjectFocus.shared.point(in: image, key: ImageLoader.pictureKey(request), subject: true)
        return (id, image, focus)
    }

    /// Back to the work tapped: it is put in place under the grid, its
    /// picture made ready, and the grid grows about its tile till the tile
    /// lies where the work lies on its page, as large, and fades, the page
    /// growing out of the tile the same way (14:06: "Po powrocie z siatki
    /// … w obydwu wypadkach jest skok i przesunięcie dzieła").
    private func closeGrid(on work: RemoteItem) {
        guard grid, gridOpen else { return }
        gridGoing = false
        let quiet = Self.quiet
        withTransaction(quiet) {
            if let tile = gridFrames.frames[work.id], tile.width > 0 {
                meet(place: place(of: work), tile: tile)
            }
            position = work.id
        }
        speed.reset()
        Task { @MainActor in
            await ready(work)
            withAnimation(.smooth(duration: 0.45)) { gridOpen = false }
            try? await Task.sleep(for: .milliseconds(480))
            guard !gridOpen else { return }
            withTransaction(quiet) { grid = false }
        }
    }

    /// A change with no animation at all.
    private static var quiet: Transaction {
        var quiet = Transaction(animation: nil)
        quiet.disablesAnimations = true
        return quiet
    }

    // MARK: The long drag back

    /// How much smaller the work is at the end of the drag, and how far it
    /// follows the finger down (of the screen's height).
    static let pullShrink: CGFloat = 0.3
    static let pullFollow: CGFloat = 0.25
    /// How far the drag must go (of the screen's height) for the grid.
    static let pullFar: CGFloat = 0.25

    private func pulled(_ move: CGFloat) {
        guard pulling, !grid else { return }
        let height = max(pagesArea.height, 1)
        let share = min(max(move / height, 0), 1)
        let quiet = Self.quiet
        withTransaction(quiet) { pull = share }
    }

    /// The drag let go: far enough, the grid of the works seen; else the
    /// work grows back.
    private func released(_ move: CGFloat) {
        guard pulling else { return }
        pulling = false
        guard !grid else { return }
        if move > max(pagesArea.height, 1) * Self.pullFar {
            openGrid(back: true)
            return
        }
        withAnimation(.smooth(duration: 0.3)) { pull = 0 }
    }

    /// The work's page picture and the point it is cut around, in memory,
    /// waited for a little at most.
    private func ready(_ work: RemoteItem) async {
        guard let request = model.backend.request(for: .thumb(work.id)) else { return }
        let pixel = GalleryPage.thumbPixel
        let key = ImageLoader.pictureKey(request)
        Task { @MainActor in
            guard let image = try? await ImageLoader.shared.image(for: request, maxPixel: pixel, priority: .high)
            else { return }
            _ = await SubjectFocus.shared.point(in: image, key: key, subject: true)
        }
        let until = ContinuousClock.now + .milliseconds(600)
        while ContinuousClock.now < until {
            if ImageLoader.inMemory(for: request, maxPixel: pixel) != nil, SubjectFocus.known(key + "|subject") != nil {
                // A frame or two for the page to take them.
                try? await Task.sleep(for: .milliseconds(50))
                return
            }
            try? await Task.sleep(for: .milliseconds(25))
        }
    }

    private func heart(_ work: RemoteItem) {
        let summary = work.summary
        if !model.liked(summary) { Task { await model.like(summary, true) } }
        flashes += 1
    }

    /// The card without the push's slide: it takes the work from where it
    /// lies here (Mateusz 2026-11-24 07:36: "dzieło podsuwa się do góry na
    /// miejsce w karcie dzieła i pojawia się reszta treści"); from the cut
    /// work, which melts away first, as on the way to the whole one.
    private func open(_ work: RemoteItem) {
        ItemPeeks.remember(work.summary, thumb: .thumb(work.id))
        // The way back is the way in turned round (14:06: "Powrót z karty
        // dzieła do „całego dzieła” odwrócona animacją wejścia"): the card
        // takes its work back here, then leaves without a slide.
        CardArrival.pending[work.id]?.back = {
            var quiet = Transaction(animation: nil)
            quiet.disablesAnimations = true
            withTransaction(quiet) { if !path.isEmpty { path.removeLast() } }
        }
        let push = {
            var quiet = Transaction(animation: nil)
            quiet.disablesAnimations = true
            withTransaction(quiet) { path.append(work.id) }
        }
        guard !whole else { push(); return }
        withAnimation(.easeIn(duration: 0.16)) { leaving = work.id }
        Task {
            try? await Task.sleep(for: .seconds(0.14))
            push()
        }
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

    private func more(count: Int = GalleryView.batch) async {
        guard !loading else { return }
        loading = true
        defer { loading = false }
        do {
            let next = try await model.backend.gallery(count: count)
            failed = false
            let have = Set(works.map(\.id))
            let fresh = next.filter { !have.contains($0.id) }
            works += fresh
            // Ready for the grid well before it is needed.
            prefetch(fresh)
            // Waiting at the end: the first new one takes its place at once,
            // the glow fading off it.
            if position == Self.endID, let first = fresh.first {
                surfacing = true
                var quiet = Transaction(animation: nil)
                quiet.disablesAnimations = true
                withTransaction(quiet) { position = first.id }
                Task {
                    try? await Task.sleep(for: .seconds(0.35))
                    withAnimation(.easeOut(duration: 0.8)) { surfacing = false }
                }
            }
            if position == nil { position = works.first?.id }
            let at = works.firstIndex { $0.id == position } ?? 0
            Self.remember(Array(works.dropFirst(at + 1)))
            cutAhead()
        } catch {
            failed = works.isEmpty
        }
    }

    /// The works coming next cut down to the work in the background, as the
    /// card does when it opens (Mateusz 2026-11-23 21:41: "Dzieła idące na
    /// Galerię kadruj w tle (usuwaj zbędne tło)"): the server looks first,
    /// then, on the owner's phone, its own model. Not the one shown nor the
    /// next, whose pictures are on their way already.
    private func cutAhead() {
        guard cutting == nil else { return }
        cutting = Task {
            defer { cutting = nil }
            while !Task.isCancelled {
                let at = works.firstIndex { $0.id == position } ?? 0
                guard let next = works.dropFirst(at + 2).first(where: { !Self.looked.contains($0.id) }) else { return }
                Self.looked.insert(next.id)
                guard let cut = await cutDown(next.item) else { continue }
                if let index = works.firstIndex(where: { $0.id == next.id }) { works[index].item = cut }
            }
        }
    }

    /// The work as it is once cut, nil when nothing was cut.
    private func cutDown(_ item: Item) async -> Item? {
        guard item.kind == .artwork, ItemDetailView.canCut(item) else { return nil }
        guard model.isOwner, !item.isOwnWork,
              let found = try? await MuseumCrop.look(itemID: item.id, backend: model.backend),
              found.cut
        else { return nil }
        return found.item
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
    @Environment(\.colorScheme) private var scheme
    let work: RemoteItem
    /// On screen now: it draws back and drifts a little.
    var current = false
    /// Tapped: drawn back to the whole of it, the caption right under it.
    var whole = false
    /// The works before and after it, whose grounds its own flows into at
    /// its top and foot (Mateusz 2026-11-24: "na łączeniu tła przy
    /// przewijaniu widać ostrą krawędź. Zróbmy tam płynne przejście").
    var above: RemoteItem?
    var below: RemoteItem?
    /// Its card opening from the cut work: the work melts away as it does
    /// on the way to the whole one, and the card's surfaces out of it.
    var leaving = false
    /// The title tapped: the work whole, or cut again.
    var flip: () -> Void = {}
    /// "Karta dzieła" under the whole work's caption.
    var open: () -> Void = {}

    @State private var thumb: UIImage?
    @State private var full: UIImage?
    @State private var polish: PolishText?
    /// The whole work's caption as tall as it is, the work above it.
    @State private var captionHeight = Whole.captionGuess
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
    static let closer = GalleryView.closer
    /// Seconds to draw back from `closer` to the whole picture.
    static let drawBack: Double = 20

    static let thumbPixel: CGFloat = 900
    /// The whole work's room on the page as the shown one last had it,
    /// for where another work would lie (the way back from the grid).
    @MainActor static var lastSafe = EdgeInsets()
    @MainActor static var lastCaption = Whole.captionGuess
    private static let fullPixel: CGFloat = 2800

    var body: some View {
        GeometryReader { geo in
            ZStack {
                if let shown = full ?? thumb, let focus {
                    let layout = Fill(picture: shown.size, box: geo.size, focus: focus)
                    let place = Whole(picture: shown.size, box: geo.size, safe: geo.safeAreaInsets, caption: captionHeight)
                    // Two pictures, never one moved between them (Mateusz
                    // 2026-11-23 20:14: the scaling "nadal nie wygląda
                    // dobrze. Zaproponuj zupełnie inne rozwiązanie"; B,
                    // "Rozpływ w łunę"): the cut one melts into its glow, and
                    // the whole one surfaces out of it where it will stay.
                    ZStack {
                        ZStack {
                            if let thumb { picture(thumb, size: layout.size, offset: layout.offset) }
                            if let full { picture(full, size: layout.size, offset: layout.offset).opacity(fullShown) }
                        }
                        .scaleEffect(reduceMotion ? 1 : zoom, anchor: layout.anchor)
                        .offset(x: pan)
                        if current { caption(nil, geo) }
                    }
                    .frame(width: geo.size.width, height: geo.size.height)
                    .clipped()
                    .blur(radius: whole || leaving ? Self.melt : 0)
                    .opacity(whole || leaving ? 0 : 1)
                    .animation(whole ? .easeIn(duration: 0.16) : .easeOut(duration: 0.2).delay(0.05), value: whole)
                    .allowsHitTesting(!whole)
                    ZStack {
                        if let glow {
                            Glow(edges: glow, size: place.size, offset: place.offset)
                                // On paper, paler (21:43: "Podkład jasny w
                                // trybie jasnym i ciemny w trybie ciemnym").
                                .opacity(scheme == .light ? 0.62 : 1)
                        }
                    }
                    .frame(width: geo.size.width, height: geo.size.height)
                    .opacity(whole ? 1 : 0)
                    .animation(whole ? .easeOut(duration: 0.2) : .easeIn(duration: 0.14), value: whole)
                    ZStack {
                        ZStack {
                            if let thumb { picture(thumb, size: place.size, offset: place.offset, rounded: true) }
                            if let full { picture(full, size: place.size, offset: place.offset, rounded: true).opacity(fullShown) }
                        }
                        // Faint (21:41: "cień za dziełem znacznie słabszy").
                        .shadow(color: .black.opacity(0.14), radius: 8, y: 3)
                        if current { caption(place, geo) }
                    }
                    .frame(width: geo.size.width, height: geo.size.height)
                    .scaleEffect(whole ? 1 : 0.96, anchor: UnitPoint(x: 0.5, y: 0.5 + place.offset.height / max(geo.size.height, 1)))
                    .opacity(whole ? 1 : 0)
                    .animation(whole ? .easeOut(duration: 0.22).delay(0.07) : .easeIn(duration: 0.12), value: whole)
                    .allowsHitTesting(whole)
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
            .task(id: current && geo.size.width > 0) { await drawBack(geo.size) }
        }
        .background {
            ZStack {
                placeholder
                ground.opacity(whole || leaving ? 1 : 0)
                    .animation(.easeOut(duration: 0.16), value: leaving)
            }
            .ignoresSafeArea()
        }
        .task(id: work.id) { await load() }
        .task(id: current) { if current { await loadPolish() } }
        // Made while the work is shown, before any tap: ready for it.
        .task(id: (current || whole) && (thumb ?? full) != nil) {
            guard current || whole, glow == nil, let picture = thumb ?? full else { return }
            if let made = Glow.kept[work.id] { glow = made; return }
            glow = await Task.detached(priority: .utility) { Glow.edges(of: picture) }.value
            if let glow { Glow.kept[work.id] = glow }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(work.item.displayTitle)
    }

    /// The title and the artist always (Mateusz 2026-11-23 18:20: "Na
    /// pełnym ekranie pokazuj także tytuł i autora"): low on the cut work,
    /// on a shade; right under the whole one ("tytuł i autora przesuwaj
    /// bezpośrednio pod dzieło"), with the museum and the artist's years.
    /// Under the whole work it stands low too, above the tab bar (22:08:
    /// "Jednak na „całym dziele” tytuł, autor, guzik dajmy u dołu strony").
    private func caption(_ place: Whole?, _ geo: GeometryProxy) -> some View {
        let foot = max(geo.safeAreaInsets.bottom, 34) + (place == nil ? 0 : Whole.tabBar)
        let frame = geo.frame(in: .global)
        let from = place.map {
            CGRect(
                x: frame.midX + $0.offset.width - $0.size.width / 2,
                y: frame.midY + $0.offset.height - $0.size.height / 2,
                width: $0.size.width, height: $0.size.height
            )
        }
        let ground = behind
        let id = work.id
        return GalleryCaption(work: work, polish: polish, whole: place != nil, flip: flip) {
            // The card takes the work from here (`CardArrival`).
            CardArrival.pending[id] = CardArrival.Pending(from: from, ground: ground)
            open()
        }
            .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { height in
                guard place != nil else { return }
                GalleryPage.lastCaption = height
                if abs(height - captionHeight) > 0.5 { captionHeight = height }
            }
            .onAppear { GalleryPage.lastSafe = geo.safeAreaInsets }
            .padding(.bottom, foot)
            .frame(width: geo.size.width, height: geo.size.height, alignment: .bottom)
    }

    /// Behind the whole work: its own main colour, quiet and dark
    /// (Mateusz 2026-11-23 17:42: "Tło za dziełem nie czarne, tylko
    /// wypełnione stonowaną barwą dzieła").
    /// In light mode a paper in the work's colour, light and nearly grey
    /// (Mateusz 2026-11-23 21:43: "Podkład jasny w trybie jasnym i ciemny w
    /// trybie ciemnym").
    private var behind: Color { behind(work) }

    private func behind(_ other: RemoteItem) -> Color {
        let hex = other.item.colors.first?.hex ?? ""
        return Self.toned(UIColor(Color(hexString: hex) ?? .black), light: scheme == .light)
    }

    /// Its own ground, meeting each neighbour's halfway at the seam: both
    /// pages are the same colour there, so scrolling shows no edge.
    private var ground: LinearGradient {
        let own = behind
        let top = above.map { own.mix(with: behind($0), by: 0.5) } ?? own
        let foot = below.map { own.mix(with: behind($0), by: 0.5) } ?? own
        return LinearGradient(
            stops: [
                .init(color: top, location: 0),
                .init(color: own, location: Self.seam),
                .init(color: own, location: 1 - Self.seam),
                .init(color: foot, location: 1),
            ],
            startPoint: .top, endPoint: .bottom
        )
    }

    /// How much of the page's height, top and foot, its ground takes to
    /// turn into the halfway colour.
    static let seam: CGFloat = 0.3

    static func toned(_ color: UIColor, light: Bool = false) -> Color {
        var hue: CGFloat = 0, saturation: CGFloat = 0, brightness: CGFloat = 0, alpha: CGFloat = 0
        color.getHue(&hue, saturation: &saturation, brightness: &brightness, alpha: &alpha)
        if light { return Color(hue: hue, saturation: min(saturation * 0.25, 0.1), brightness: 0.93) }
        return Color(hue: hue, saturation: min(saturation * 0.7, 0.4), brightness: 0.2)
    }

    /// The work's own main colour, dimmed, while its picture comes.
    private var placeholder: Color {
        let hex = work.item.colors.first?.hex ?? ""
        return (Color(hexString: hex) ?? .black).opacity(0.35)
    }

    /// Rounded a little when whole, as on the work's card (Mateusz
    /// 2026-11-23 22:08: "Narożniki dzieła odrobinę zaokrąglone").
    private func picture(_ image: UIImage, size: CGSize, offset: CGSize, rounded: Bool = false) -> some View {
        Image(uiImage: image)
            .resizable()
            .interpolation(.high)
            .frame(width: size.width, height: size.height)
            .clipShape(RoundedRectangle(cornerRadius: rounded ? 8 : 0, style: .continuous))
            .offset(offset)
    }

    /// How far the cut work is blurred as it melts into its glow (points).
    static let melt: CGFloat = 36

    /// The caption's Polish texts: asked for once the work has stayed a
    /// moment, not for each one swiped past; one for both its captions.
    private func loadPolish() async {
        polish = ItemPeeks.polish[work.id]
        // Always shown now: asked for only once the work has stayed a moment,
        // not for each one swiped past.
        guard polish == nil, work.item.kind == .artwork else { return }
        try? await Task.sleep(for: .seconds(1.5))
        guard !Task.isCancelled,
              let view = try? await model.backend.polish(itemID: work.id, wait: 0, early: true),
              let text = view.text
        else { return }
        ItemPeeks.keep(text, for: work.id)
        withAnimation(.easeInOut(duration: 0.4)) { polish = text }
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

    /// To the whole work and back, for what has no timing of its own; all
    /// of it quicker (Mateusz 2026-11-24: "Przejście … szybsze")
    /// (the background, the tab bar).
    static let toWhole = Animation.easeInOut(duration: 0.25)

    /// How far a work drifts sideways while it draws back (points), at most.
    static let drift: CGFloat = 22
}

/// A tapped work drawn back to the whole of it (Mateusz 2026-11-23 16:32:
/// "Kliknięcie w dzieło - zmniejsza i pokazuje je w całości"): between the
/// status bar and the caption, a little in from the sides, on the dark.
private struct Whole {
    let size: CGSize
    let offset: CGSize

    /// The floating tab bar's height, the caption above it.
    static let tabBar: CGFloat = 62
    static let side: CGFloat = 20
    static let gap: CGFloat = 12
    /// Between the work and its title.
    static let aboveTitle: CGFloat = 22
    /// The caption's height before it is measured: one line of title, the
    /// artist and "Karta dzieła".
    static let captionGuess: CGFloat = 140
    /// Where a work lower than its room stands in it: this share of the room
    /// left over above it, the rest below (Mateusz 2026-11-23 22:37: "Dzieła
    /// które na to pozwalają - trochę niżej").
    static let lower: CGFloat = 0.64

    /// Between the status bar and the caption as tall as it is (22:37: "na
    /// pewno rezerwa od dołu jest zbyt duża"; it was 36% of the screen, made
    /// for the museum and the artist's years too).
    init(picture: CGSize, box: CGSize, safe: EdgeInsets, caption: CGFloat) {
        // The pages ignore the safe area: the status bar's height as least.
        let top = max(safe.top, 59) + Self.gap
        let bottom = max(safe.bottom, 34) + Self.tabBar + caption + Self.aboveTitle
        let room = CGSize(width: box.width - Self.side * 2, height: max(box.height - top - bottom, 1))
        let scale = min(room.width / max(picture.width, 1), room.height / max(picture.height, 1))
        size = CGSize(width: picture.width * scale, height: picture.height * scale)
        let y = top + (room.height - size.height) * Self.lower
        offset = CGSize(width: 0, height: y + size.height / 2 - box.height / 2)
    }
}

/// Behind the whole work, the colours of its edges flowing out and
/// fading into its own quiet colour (Mateusz 2026-11-23 17:53: "rozmyte
/// ale od krawędzi. Takie łuny koloru"): only what is on each edge, the
/// edge's own pixels drawn outwards (17:55: "na krawędzi nie ma włosów.
/// Musimy brać kolor który faktycznie jest na krawędzi").
struct Glow: View {
    let edges: UIImage
    /// Where the work lies: its size and its offset from the middle.
    let size: CGSize
    let offset: CGSize

    /// How far the edges are drawn out on each side, as a share of the
    /// work's longer side; and their blur, as a share of it too.
    nonisolated static let reach: CGFloat = 0.6
    nonisolated static let softness: CGFloat = 0.12
    nonisolated(unsafe) private static let context = CIContext(options: [.cacheIntermediates: false])
    /// Made in Galeria, kept for the work's card, which shows the same
    /// glow behind it (Mateusz 2026-11-24 07:36).
    @MainActor static var kept: [String: UIImage] = [:]

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
        let outer = extent.insetBy(dx: -pad, dy: -pad)
        let glow = small.clampedToExtent()
            .applyingGaussianBlur(sigma: Double(max(extent.width, extent.height) * softness))
            .cropped(to: outer)
        // Its fading out made with it, the same on every side and gone
        // well before its own edge: a fade laid over it in SwiftUI still
        // left an edge (Mateusz 2026-11-23 19:01 and 20:14, "Nadal widać
        // krawędź").
        let fade = CIImage(color: .white)
            .cropped(to: extent.insetBy(dx: -pad * 0.45, dy: -pad * 0.45))
            .applyingGaussianBlur(sigma: Double(pad / 6))
            .cropped(to: outer)
        let out = glow.applyingFilter("CIBlendWithMask", parameters: [
            kCIInputBackgroundImageKey: CIImage(color: .clear).cropped(to: outer),
            kCIInputMaskImageKey: fade,
        ])
        guard let made = context.createCGImage(out, from: outer) else { return nil }
        return UIImage(cgImage: made)
    }

    var body: some View {
        // The work's share of the made picture: 1 / (1 + 2 * reach * long / side).
        let long = max(size.width, size.height)
        let pad = long * Self.reach
        let whole = CGSize(width: size.width + pad * 2, height: size.height + pad * 2)
        Image(uiImage: edges)
            .resizable()
            .frame(width: whole.width, height: whole.height)
            .opacity(0.9)
            .offset(offset)
            .allowsHitTesting(false)
    }
}

/// The corner's glass heart, as on the tiles (`HeartMark`). Given, red
/// fills it from its middle outwards, quickly, and a brighter red lights
/// up for a moment along its edge, inside it; nothing around it (Mateusz
/// 2026-11-23 17:42: "bez tego wielkiego rozbłysku na zewnątrz"; 19:01:
/// "wypełnianie od środka a nie od dołu. Szybsze. Z lekkim, chwilowym
/// rozbłyskiem żywszą czerwienią wewnątrz serca, przy jego krawędzi").
private struct GalleryHeart: View {
    let on: Bool
    let flashes: Int
    @State private var level: CGFloat = 0
    /// Hearts given here, for the bright red at the edge for a moment.
    @State private var given = 0

    private static let size: CGFloat = 26
    private static let red = Color(red: 0xD2 / 255, green: 0x46 / 255, blue: 0x3A / 255)
    private static let bright = Color(red: 1, green: 0x3B / 255, blue: 0x30 / 255)

    var body: some View {
        HeartMark(on: false, size: Self.size)
            .overlay {
                ZStack {
                    // Red growing out from the middle of the glass.
                    HeartShape()
                        .fill(
                            RadialGradient(
                                colors: [Self.red.opacity(0.95), Self.red.opacity(0.8)],
                                center: .center, startRadius: 0, endRadius: Self.size * 0.6
                            )
                        )
                        .scaleEffect(level, anchor: UnitPoint(x: 0.5, y: 0.45))
                        .opacity(level > 0 ? 1 : 0)
                    // The flash: a livelier red along the inside of the
                    // edge, glowing into the middle (20:14: "Błysk serca
                    // mocniejszy").
                    ZStack {
                        HeartShape().fill(Self.bright.opacity(0.45))
                        HeartShape()
                            .stroke(Self.bright, lineWidth: 7)
                            .blur(radius: 2.5)
                        HeartShape()
                            .stroke(Color(red: 1, green: 0.55, blue: 0.5), lineWidth: 2)
                            .blur(radius: 0.8)
                    }
                    .mask(HeartShape())
                    .keyframeAnimator(initialValue: 0.0, trigger: given) { edge, shown in
                        edge.opacity(shown)
                    } keyframes: { _ in
                        LinearKeyframe(0, duration: 0.08)
                        CubicKeyframe(1, duration: 0.08)
                        LinearKeyframe(1, duration: 0.12)
                        CubicKeyframe(0, duration: 0.55)
                    }
                }
                .padding(1)
            }
            .keyframeAnimator(initialValue: CGFloat(1), trigger: flashes) { heart, scale in
                heart.scaleEffect(scale)
            } keyframes: { _ in
                SpringKeyframe(1.12, duration: 0.12, spring: .snappy)
                SpringKeyframe(1, duration: 0.3, spring: .bouncy)
            }
            .onAppear { level = on ? 1 : 0 }
            .onChange(of: on) { _, now in
                if now {
                    level = 0
                    withAnimation(.spring(duration: 0.28, bounce: 0.3)) { level = 1 }
                    given += 1
                } else {
                    withAnimation(.easeIn(duration: 0.2)) { level = 0 }
                }
            }
    }
}

/// A picture cut to fill a box around `focus`: its size and where it lies.
struct Fill {
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

/// The work's caption: on its lower part while it is cut (Mateusz 2026-11-23,
/// variant 2: no card, the text on a shade), right under it when it is whole: the museum, the title with its year, the
/// artist and their nationality and years, as on the work's card. Tapped:
/// the card. The Polish texts are asked for once the work has stayed a moment.
private struct GalleryCaption: View {
    @Environment(AppModel.self) private var model
    let work: RemoteItem
    /// Its Polish texts, once the page has them.
    let polish: PolishText?
    /// Under the whole work: with the museum and the artist's years, on
    /// the glow; over the cut one only the title and the artist, on a shade.
    var whole = false
    /// The title tapped: the work whole, or cut again (Mateusz 2026-11-23
    /// 21:41: "kliknięcie w tytuł także przenosi do całego dzieła … wraca
    /// na pełny ekran").
    let flip: () -> Void
    /// "Karta dzieła", under the whole work's caption (21:41).
    let open: () -> Void

    @Environment(\.colorScheme) private var scheme

    private var item: Item { work.item }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Button(action: flip) { words }
                .buttonStyle(.plain)
            // As the app's black buttons (21:43: "jak czarne guziki w
            // aplikacji"), on the cut work too (2026-11-24: "Na pełnym
            // ekranie także dodajmy guzik „karta dzieła”"), black there
            // whatever the phone's mode ("na pełnym ekranie guzik „karta
            // dzieła” czarny").
            // Only under the whole work after all (14:06: "Na pełnym
            // ekranie nie dajemy jednak guzika karta dzieła").
            if whole {
                Button(action: open) {
                    Label("Karta dzieła".bound, systemImage: "text.below.photo")
                }
                .buttonStyle(ActionButtonStyle(prominent: true, wide: false))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, Theme.gutter + 2)
        .padding(.top, whole ? 0 : 70)
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
            .padding(.bottom, -140)  // to the screen's foot
            .opacity(whole ? 0 : 1)
            .allowsHitTesting(false)
        }
        // Light text on the cut work's shade in both modes; under the whole
        // one, on its light or dark ground, as the phone is set.
        .environment(\.colorScheme, whole ? scheme : .dark)
    }

    private var words: some View {
            HStack(alignment: .center, spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    // Only the title and the artist, both ways (Mateusz
                    // 2026-11-23 22:08: "bez nazwy muzeum, daty, narodowości
                    // i okresu życia").
                    Text(bound: title)
                        .font(.serif(26, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                        .lineLimit(whole ? 2 : 3)
                    if !item.artist.isEmpty {
                        Text(bound: Names.artist(item.artist))
                            .font(.serif(19))
                            .foregroundStyle(Theme.ink)
                            .lineLimit(1)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .shadow(color: .black.opacity(whole && scheme == .dark ? 0.45 : 0), radius: 6, y: 1)
            .contentShape(Rectangle())
    }

    private var title: String {
        nonEmpty(polish?.title) ?? nonEmpty(work.titlePl)
            ?? (item.displayTitle.isEmpty ? "Bez tytułu" : item.displayTitle)
    }

    private func nonEmpty(_ text: String?) -> String? {
        guard let text, !text.isEmpty else { return nil }
        return text
    }
}

/// The glow alone, its colours drifting slowly into one another: the page
/// after the last work while more are on their way.
private struct GalleryWaiting: View {
    let colours: [Color]
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(paused: reduceMotion)) { context in
            let time = context.date.timeIntervalSinceReferenceDate
            Canvas { canvas, size in
                canvas.fill(Path(CGRect(origin: .zero, size: size)), with: .color(ground))
                canvas.addFilter(.blur(radius: size.width * 0.22))
                let spots = colours.isEmpty ? [Color.gray] : colours
                for (index, colour) in spots.enumerated() {
                    let i = Double(index)
                    // Each its own slow ways, none of them in step.
                    let a = time * (0.11 + 0.023 * i) + i * 1.7
                    let x = size.width * (0.5 + 0.28 * cos(a) + 0.08 * sin(a * 1.31 + i))
                    let y = size.height * (0.42 + 0.17 * sin(a * 0.83 + i * 2))
                    let r = size.width * (0.3 + 0.06 * sin(a * 1.7 + i))
                    let rect = CGRect(x: x - r, y: y - r * 1.2, width: r * 2, height: r * 2.4)
                    canvas.fill(Path(ellipseIn: rect), with: .color(colour.opacity(scheme == .light ? 0.45 : 0.7)))
                }
            }
        }
        .background(ground)
        .accessibilityHidden(true)
    }

    private var ground: Color {
        GalleryPage.toned(UIColor(colours.last ?? .black), light: scheme == .light)
    }
}
