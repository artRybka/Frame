import CoreImage
import SwiftUI

/// "Galeria", the first tab (Mateusz 2026-11-23): works one after another on
/// the whole screen, cut to fill it. A swipe up brings the next, down the one
/// before; the order is the person's own (`GET /api/gallery`: their hearts,
/// works like them, new ones).
///
/// Two views and no more (2026-11-24 18:31: "Zrezygnujmy chyba z widoku
/// „całego dzieła”, bo wprowadza zamieszanie"): the work on the whole
/// screen, with its title, its artist and the glass heart, and the grid of
/// small screens (`GalleryGrid`), the works seen above the one shown and
/// the works coming below. The grid has the tab bar: it is the way out of
/// the whole screen. Between the two the work only shrinks into its tile or
/// grows out of it (`GalleryCamera`).
///
/// To the grid: a quick run of swipes (the work draws back while still on
/// its way, `sweep`), a swipe down from the screen's upper part
/// (`SwipeZone`; lower down it is the work before), or two fingers drawn
/// together. Back: a tap on a tile, or two fingers spread on it. A tap on
/// the work does nothing; two give a heart (19:12, 18:51). A hold shows
/// the whole work on its own colours while the finger lies, and the finger
/// drawn up from there opens the work's card (18:51).
struct GalleryView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.colorScheme) private var scheme
    @Environment(\.displayScale) private var displayScale
    /// The works not seen yet when the app was last left: shown at once on
    /// the next launch while the server is asked for more (Mateusz
    /// 2026-11-23: "czarny ekran zaraz po otwarciu").
    @State private var works: [RemoteItem] = GalleryView.remembered()
    @State private var position: String?
    @State private var loading = false
    @State private var failed = false
    @State private var path: [String] = []
    /// The grid under the pages (`grid`), and at rest with the pages gone
    /// into it (`gridOpen`): the tab bar is there then.
    @State private var grid = false
    @State private var gridOpen = false
    /// The tab bar and the status bar, the grid's own: there from the
    /// moment the work is let go into the grid, and never brought in by an
    /// animation (the bar's shade then flew down the screen to its place;
    /// the film of 2026-11-24).
    @State private var bars = false
    /// The first work in the grid, the empty cells before it, and how far
    /// the grid is scrolled when it comes (`layGrid`).
    @State private var gridFirst = 0
    @State private var gridLead = 0
    @State private var gridStart: CGFloat = 0
    /// Fingers spread on a tile: the grid does not scroll meanwhile.
    @State private var gridLocked = false
    /// The pages drawn over the grid: on the way out of a work always, on
    /// the way into one once its page has its picture.
    @State private var windowShown = true
    /// The work the grid is going back into, and the page last ready.
    @State private var returning: String?
    @State private var readyPage: String?
    /// What moves the camera now.
    @State private var hand = Hand.idle
    /// A gesture of Galeria's own under way: the pages' scroll gives way.
    @State private var pulling = false
    @State private var heartShown = true
    /// The work a finger lies on, on its way to the hold: pressed in a
    /// little (`GalleryPage.pressedIn`).
    @State private var pressed: String?
    @State private var camera = GalleryCamera()
    @State private var coast = Coast()
    @State private var track = GridTrack()
    @State private var stock = GridStock()
    /// How fast the pages are swiped, for the grid to flow on as fast.
    @State private var flow = SwipeFlow()
    @State private var run = SwipeRun()
    /// The screen.
    @State private var area = CGRect.zero
    /// The work held: shown whole while the finger lies (and while its
    /// card, opened from there, is up).
    @State private var peek: String?
    @State private var pull = GalleryPull()
    /// The held work's card opened by the finger drawn up.
    @State private var engaged = false
    /// The phone's taps: the hold, the card.
    @State private var ticks = 0
    /// The end page's glow over the first new work as it fades away.
    @State private var surfacing = false
    /// Double taps given, for the corner heart's flash.
    @State private var flashes = 0
    /// The works ahead being cut down to the work, one at a time.
    @State private var cutting: Task<Void, Never>?
    /// Works looked at for a cut here since the app started.
    @MainActor private static var looked: Set<String> = []
    /// Works cut down here, whose pictures Galeria has had anew already.
    @State private var cutHere: Set<String> = []
    /// Scrolled to the work it starts with (`begin`): shown from then on.
    @State private var begun = false

    private enum Hand {
        /// `gone`: on its way to the grid with no finger's say any more
        /// (drawn all the way while the finger still lies, or asked for
        /// by the grid's button).
        case idle, sweep, swipe, gone, pinch, spread, back
    }

    /// Works asked for at once, and how near the end the next are asked for.
    /// Asked for well before the end (Mateusz 2026-11-24: "niech aplikacja
    /// wcześniej prosi o kolejne"), so the end is seldom reached, and the
    /// grid has its thumbnails when it first comes (2026-11-25: "Na start
    /// mogłoby być ciut więcej gotowych miniatur").
    private static let batch = 24
    private static let ahead = 30
    /// Works had ahead, their thumbnails fetched, a moment after Galeria
    /// starts: the grid's first screens.
    private static let early = 54
    /// The page after the last work, while more are on their way.
    static let endID = "gallery.end"

    private var shown: RemoteItem? {
        if position == Self.endID { return nil }
        return works.first { $0.id == position } ?? works.first
    }

    private var shownIndex: Int? {
        guard position != Self.endID, !works.isEmpty else { return nil }
        return works.firstIndex { $0.id == position } ?? 0
    }

    /// The glow the end page and a work coming out of it are made of: the
    /// last works' colours.
    private var endColours: [Color] {
        works.suffix(4).compactMap { $0.item.colors.first?.hex }.compactMap { Color(hexString: $0) }
    }

    private var metrics: GridMetrics { GridMetrics(area: area.size, scale: displayScale) }

    /// The screen's own edges (the status bar, the home indicator),
    /// whatever bars are shown: the pages are laid out by these, so nothing
    /// on them moves when the tab bar comes or goes.
    private static var insets: EdgeInsets {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        let window = scenes.first?.keyWindow ?? scenes.first?.windows.first
        guard let insets = window?.safeAreaInsets else { return EdgeInsets(top: 59, leading: 0, bottom: 34, trailing: 0) }
        return EdgeInsets(top: insets.top, leading: 0, bottom: insets.bottom, trailing: 0)
    }

    var body: some View {
        NavigationStack(path: $path) {
            ZStack {
                Color.black
                if grid { wall }
                pages
            }
            // All of it on the whole screen, set before the safe area is
            // let go of: set after it, a shape is only as large as the safe
            // area (Mateusz 2026-11-24 17:23: "Czarne paski od góry i dołu").
            .onGeometryChange(for: CGRect.self) { $0.frame(in: .global) } action: { area = $0 }
            .ignoresSafeArea()
            .overlay(alignment: .topTrailing) {
                // Its own for each work: swiped to a work given a heart
                // before, the red is there already, not pouring in.
                if let shown, heartShown { heartButton(shown).id(shown.id).transition(.opacity) }
            }
            .overlay(alignment: .topLeading) {
                if shown != nil, heartShown, peek == nil { gridButton.transition(.opacity) }
            }
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
            .sensoryFeedback(.impact(weight: .medium), trigger: ticks)
            .toolbarVisibility(.hidden, for: .navigationBar)
            .toolbarVisibility(bars || !path.isEmpty ? .visible : .hidden, for: .tabBar)
            .statusBarHidden(!bars)
            .navigationDestination(for: String.self) { id in
                ItemDetailView(itemID: id)
            }
        }
        .task {
            // Those kept from the last launch: their thumbnails too.
            prefetch(works)
            // With works kept from before, at once: no black screen while
            // the server is asked for more.
            if works.count > Self.above { await begin() }
            if works.count < Self.batch { await more() }
            await begin()
            await staged()
        }
        .task {
            // After the first work's own pictures: the grid's first screens.
            try? await Task.sleep(for: .seconds(1.5))
            for _ in 0 ..< 3 where !Task.isCancelled && works.count - (shownIndex ?? 0) < Self.early {
                if loading { try? await Task.sleep(for: .milliseconds(300)) }
                await more()
            }
        }
        .onChange(of: model.pictureChanges) { before, now in
            // A work's picture made anew elsewhere (cut down on its card):
            // Galeria's own is had anew too.
            for (id, count) in now where before[id] != count { repictured(id) }
        }
        .onChange(of: path) { _, now in
            // Back from the card: the work held there is cut to the screen
            // again, as when a finger lets it go.
            guard now.isEmpty, peek != nil else { return }
            engaged = false
            pulling = false
            withAnimation(GalleryPage.fromWhole) {
                peek = nil
                pull.up = 0
            }
        }
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
            if begun { remember() }
            if index >= works.count - Self.ahead { Task { await more() } }
            cutAhead()
        }
        // Hearts given here change what comes next: a fresh batch is asked
        // for when the library changes, after the works not seen yet.
    }

    private var pages: some View {
        let insets = Self.insets
        return ScrollView(.vertical) {
            LazyVStack(spacing: 0) {
                ForEach(Array(works.enumerated()), id: \.element.id) { index, work in
                    page(work, at: index, insets: insets)
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
        .onScrollGeometryChange(for: CGFloat.self) { $0.contentOffset.y } action: { _, y in scrolled(y) }
        .onScrollGeometryChange(for: CGFloat.self) { $0.contentSize.height } action: { _, tall in flow.tall = tall }
        .onScrollGeometryChange(for: [CGFloat].self) {
            [$0.contentInsets.top, $0.contentInsets.bottom, $0.containerSize.height]
        } action: { _, now in
            GalleryLog.trace("pages' insets \(Int(now[0])) and \(Int(now[1])), \(Int(now[2])) tall")
        }
        .onScrollPhaseChange { _, phase in GalleryLog.trace("pages' scroll \(phase)") }
        .onChange(of: bars) { _, now in GalleryLog.trace("bars \(now ? "come" : "go")") }
        .scrollIndicators(.hidden)
        .modifier(WindowZoom(camera: camera))
        .opacity(windowShown && begun ? 1 : 0)
        // Not by `grid`: it comes while a finger of the pages' own is still
        // down (the swipe down, the pinch), and that gesture is to go on.
        .allowsHitTesting(!gridOpen && returning == nil)
    }

    private func page(_ work: RemoteItem, at index: Int, insets: EdgeInsets) -> some View {
        GalleryPage(
            work: work, current: work.id == shown?.id, whole: peek == work.id, pressed: pressed == work.id, still: grid,
            insets: insets, pull: pull, stock: stock,
            above: index > 0 ? works[index - 1] : nil,
            below: index + 1 < works.count ? works[index + 1] : nil,
            ready: { pageReady(work.id) }
        )
        .containerRelativeFrame([.horizontal, .vertical])
        .contentShape(Rectangle())
        // One tap does nothing; two give a heart (Mateusz 2026-11-24
        // 19:12: "pojedyncze kliknięcie na pełnym ekranie nie robi nic").
        .onTapGesture(count: 2) { heart(work) }
        // UIKit's gestures, beside the scroll, never holding it back
        // (14:06: "nie łapie machnięcia palca").
        .gesture(DownSwipe(
            on: !gridOpen,
            began: { drawBack(.swipe) },
            changed: { dragged($0) },
            ended: { move, speed in dropped(move, speed) }
        ))
        .gesture(GalleryPinch(
            on: !gridOpen,
            began: { _ in drawBack(.pinch) },
            changed: { pinched($0) },
            ended: { scale, speed in unpinched(scale, speed) }
        ))
        .gesture(HoldPull(
            on: !grid, ready: { canHold },
            pressing: { pressed = $0 ? work.id : nil },
            began: { hold() }, moved: { held($0) }, ended: { letGo() }
        ))
        .id(work.id)
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

    /// The grid's button, glass as the heart across from it.
    private var gridButton: some View {
        Button {
            showGrid()
        } label: {
            GridMark()
                .shadow(color: .black.opacity(0.18), radius: 3, y: 1)
                // The circle's middle as high as the heart's.
                .padding(.horizontal, 10)
                .padding(.vertical, 3)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Pokaż siatkę")
        .padding(.leading, Theme.gutter - 10)
        .padding(.top, 2)
    }

    private func heart(_ work: RemoteItem) {
        guard !grid else { return }
        let summary = work.summary
        if !model.liked(summary) { Task { await model.like(summary, true) } }
        flashes += 1
    }

    /// A change with no animation at all.
    private static var quiet: Transaction {
        var quiet = Transaction(animation: nil)
        quiet.disablesAnimations = true
        return quiet
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
    /// Works seen before, above the one shown, at most.
    nonisolated static let seen = 61

    /// How many of the works before the one at `index` the grid shows
    /// above it: so many that its first row is full and the work lies in
    /// the middle column, with no empty squares before the first (Mateusz
    /// 2026-11-25: "Gdy oddalę do siatki, a jestem na początku
    /// przeglądania, to widać puste kwadraty"). One or two of the oldest
    /// are left out for it: Galeria starts with two works above the first
    /// shown (`begin`), so those are never ones just looked at. The very
    /// first work of all has none above and lies in the left column.
    nonisolated static func history(before index: Int) -> Int {
        guard index > 0 else { return 0 }
        let most = min(index, seen)
        return most - (most - 1) % GridMetrics.columns
    }

    private var wall: some View {
        GalleryGrid(
            lead: gridLead, works: Array(works.dropFirst(gridFirst)), metrics: metrics, start: gridStart,
            stock: stock, track: track, locked: gridLocked,
            pick: { closeGrid(on: $0) },
            more: { Task { await more(count: Self.gridBatch) } }
        )
        .gesture(GalleryPinch(
            began: { spread(at: $0) },
            changed: { spreading($0) },
            ended: { scale, speed in spreadEnded(scale, speed) }
        ))
        .modifier(WallZoom(camera: camera))
        .allowsHitTesting(gridOpen || hand == .spread)
        .transition(.identity)
    }

    /// The grid laid out under the pages, unseen yet: the work at `index`
    /// in its middle column, its row's top `top` points below the screen's
    /// (above it, when less than 0), the works seen before it above. The
    /// camera stands on the page still. Gives how far the grid is scrolled
    /// when it lies so.
    @discardableResult
    private func layGrid(at index: Int, top: CGFloat) -> CGFloat {
        let metrics = metrics
        // The work in the middle column, a full row before it (`history`).
        let seen = Self.history(before: index)
        let lead = 0
        let cell = metrics.cell(lead + seen)
        // The grid cannot lie lower than its own first row at the top.
        let top = min(top, cell.minY)
        coast.stop()
        track.ready = false
        track.touched = { [coast] in coast.stop() }
        camera.screen = area
        camera.tile = CGRect(x: area.minX + cell.minX, y: area.minY + top, width: cell.width, height: cell.height)
        camera.pose(0)
        camera.on = true
        withTransaction(Self.quiet) {
            gridFirst = index - seen
            gridLead = lead
            gridStart = cell.minY - top
            windowShown = true
            returning = nil
            grid = true
        }
        withAnimation(.easeOut(duration: 0.15)) { heartShown = false }
        stockFor(index)
        GalleryLog.note("grid laid at \(index): top \(Int(top)), start \(Int(cell.minY - top)), lead \(lead)")
        return cell.minY - top
    }

    /// The work's tile where the grid has it now.
    private func tile(of index: Int) -> CGRect {
        let cell = metrics.cell(gridLead + index - gridFirst)
        return CGRect(
            x: area.minX + cell.minX, y: area.minY + cell.minY - track.offset, width: cell.width, height: cell.height
        )
    }

    // MARK: A quick run of swipes

    /// How the grid flows on after the swipes: as a flicked list slows
    /// (`UIScrollView`'s usual), so far as the speed carries it, at least a
    /// little (Mateusz 2026-11-24 14:06: "Prędkość powinna być zgodna z
    /// ostatnim machnięciem. Nawet kosztem kilku dzieł").
    static let slowing: CGFloat = 0.5
    static let least: CGFloat = 700
    /// Seconds the work takes to shrink into its tile, on its way.
    static let sweepZoom: CGFloat = 0.6

    /// Swiped past too fast to look: the work coming in draws back while it
    /// is still on its way up, and the wall of works flows on upwards as
    /// fast as the swipes went, slowing (Mateusz 2026-11-24 19:12: "wolałem
    /// rozwiązanie z oddaleniem"; the film of 19:20, "oddala się już w
    /// biegu i ściana płynie dalej w górę"). The work's top edge keeps the
    /// one motion throughout: the page's own at first, the grid's scroll
    /// once the work is a tile. It is past the screen's top by then, the
    /// works coming under it.
    private func sweep(to index: Int) {
        guard hand == .idle, !grid, works.indices.contains(index), area.height > 0 else { return }
        let height = area.height, slowing = Self.slowing, zoom = Self.sweepZoom
        // Points gone after `t` seconds, for each point a second at first.
        let gone = { (t: CGFloat) in slowing * (1 - exp(-t / slowing)) }
        let metrics = metrics
        // No faster than the grid is laid out for above the screen.
        let most = (metrics.above - metrics.pitch * 0.5) / gone(zoom)
        let fast = min(max(flow.speed, Self.least), max(most, Self.least))
        let left = max(CGFloat(index) * height - flow.y, 0)
        hand = .sweep
        let laid = layGrid(at: index, top: left - fast * gone(zoom))
        let screen = area, id = works[index].id
        GalleryLog.note("sweep to \(index): speed \(Int(flow.speed)) taken as \(Int(fast)), \(Int(left)) left")
        var began: CFTimeInterval?
        var from: CGFloat = 0
        var swift = fast
        var tile = camera.tile
        var start = laid
        var settled = false
        coast.run { seconds in
            // Till the grid lies where it is to: a frame or two, no more
            // (the work is on its way; it draws back over the black then,
            // towards where the grid is to lie).
            guard let began0 = began ?? (track.ready || seconds > 0.05 ? seconds : nil) else { return true }
            if began == nil {
                began = began0
                // With the work's first step back, not over it while it waits.
                withTransaction(Self.quiet) { bars = true }
                if track.ready {
                    // Where the grid really is.
                    start = track.offset
                    tile = self.tile(of: index)
                    camera.tile = tile
                }
                // The page by now.
                from = max(CGFloat(index) * height - flow.y, 0)
                swift = (from - (tile.minY - screen.minY)) / gone(zoom)
                GalleryLog.note(
                    "sweep began after \(Int(seconds * 1000)) ms, grid \(track.ready ? "ready" : "to come"): "
                        + "\(Int(from)) left, tile at \(Int(tile.minY))"
                )
            }
            let t = CGFloat(seconds - began0)
            if t < zoom {
                let inner = max(CGFloat(index) * height - flow.y, 0)
                let width = screen.width * pow(tile.width / screen.width, GalleryCamera.ease(t / zoom))
                let scale = width / screen.width
                let hero = CGRect(
                    x: screen.midX - width / 2, y: screen.minY + from - swift * gone(t),
                    width: width, height: screen.height * scale
                )
                camera.hero = hero
                camera.window = hero.offsetBy(dx: 0, dy: -inner * scale)
                GalleryLog.trace("sweep \(Int(t * 1000)) ms: top \(Int(hero.minY)), wide \(Int(width)), page \(Int(inner)) left")
                return true
            }
            if !settled {
                settled = true
                GalleryLog.note("sweep settled: \(Int(max(CGFloat(index) * height - flow.y, 0))) of the page left")
                gridSettled(on: id)
                Task { await stockUp(from: index) }
            }
            let to = min(max(start + swift * (gone(t) - gone(zoom)), 0), track.most)
            // Where the tile is now, and where the scroll was a frame ago.
            GalleryLog.trace(
                "sweep \(Int(t * 1000)) ms: top \(Int(tile.minY - (to - start))), grid at \(Int(track.offset)) to \(Int(to))"
            )
            track.scroll?(to)
            return t < slowing * 6
        }
    }

    /// The pages' scroll moved: its speed is kept, and a quick run of
    /// swipes down the works brings the grid.
    private func scrolled(_ y: CGFloat) {
        flow.note(y)
        if grid || camera.on { GalleryLog.trace("pages at \(Int(y))") }
        if returning != nil { showWindow() }
        guard !grid, hand == .idle, peek == nil, path.isEmpty else { return }
        guard let index = run.scrolled(to: y, height: area.height), works.indices.contains(index) else { return }
        sweep(to: index)
    }

    // MARK: Drawn back by hand

    /// How far a finger goes down for the whole way to the tile, and how
    /// much of the finger's way the work follows. The finger takes the
    /// work all the way, evenly: at the way's end the grid is there under
    /// it, and let go before, the work goes on as fast as the finger went
    /// (Mateusz 2026-11-25 00:39: it "jakby zatrzymuje skalowanie w
    /// połowie … pomaga tylko puszczenie palca", the work stopped at 30%
    /// and waited for the finger to lift; 07:09, of the work going the
    /// rest by itself from there: "nadal nie jest płynne. Mniej więcej w
    /// połowie „wskakuje”").
    static let swipeFull: CGFloat = 300
    static let swipeFollow: CGFloat = 0.35
    /// The slowest the work goes on once let go (of the way, a second),
    /// and the seconds that may take.
    static let swipeSlowest: CGFloat = 2.5
    static let swipeSeconds: ClosedRange<Double> = 0.2 ... 0.45
    /// How the work slows once let go (`GalleryCamera.out`'s power): it
    /// starts `swipePower` times as fast as it goes on average.
    static let swipePower: CGFloat = 3
    /// Seconds from the finger's letting go to the grid (Mateusz
    /// 2026-11-24 19:12: "przejście do siatki - A, może odrobinę wolniej").
    static let toGrid = 0.42
    /// How much smaller the fingers' span for the whole way to the tile,
    /// and how much larger for the whole way out of one.
    static let pinchFull: CGFloat = 0.6
    static let spreadFull: CGFloat = 1.5

    /// A swipe down from the upper part, or two fingers drawn together:
    /// the work shown starts back into its tile, in the middle of the
    /// screen, the works seen above it.
    private func drawBack(_ way: Hand) {
        guard hand == .idle, !grid, peek == nil, path.isEmpty, area.height > 0, let index = shownIndex else { return }
        hand = way
        pulling = true
        layGrid(at: index, top: metrics.pitch)
        GalleryLog.note("drawn back by \(way) at \(index)")
    }

    private func dragged(_ move: CGFloat) {
        guard hand == .swipe else { return }
        let z = min(max(move / Self.swipeFull, 0), 1)
        camera.pose(z, drop: max(move, 0) * Self.swipeFollow * (1 - z))
        GalleryLog.trace("drawn \(Int(move)): \(Int(z * 100))% of the way")
        guard z >= 1 else { return }
        // All the way, the finger still down: the grid, with no step.
        hand = .gone
        GalleryLog.note("drawn all the way: the grid under the finger")
        gridSettled(on: shown?.id)
    }

    /// Let go on the way: on to the grid, or back when the finger had
    /// hardly moved or was going back up; as fast at first as the finger
    /// went, so letting go is no step either.
    private func dropped(_ move: CGFloat, _ speed: CGFloat) {
        guard hand == .swipe else { return }
        let toGrid = speed > 250 || (move > 40 && speed > -250)
        let left = max(toGrid ? 1 - camera.z : camera.z, 0.05)
        let pace = max(abs(speed) / Self.swipeFull, Self.swipeSlowest)
        let seconds = min(
            max(Double(Self.swipePower * left / pace), Self.swipeSeconds.lowerBound), Self.swipeSeconds.upperBound
        )
        GalleryLog.note(
            "let go at \(Int(camera.z * 100))%, \(Int(speed)) pt/s: "
                + "\(toGrid ? "the grid" : "back") in \(Int(seconds * 1000)) ms"
        )
        settle(toGrid: toGrid, lasting: seconds, curve: { GalleryCamera.out($0, power: Self.swipePower) })
    }

    /// The grid by its own button on the page's corner (Mateusz 2026-11-25
    /// 07:09: "szklaną ikonkę pokazania siatki - kolejny sposób na wejście
    /// w siatkę 3x3"): as a swipe down from the top, by itself.
    private func showGrid() {
        guard hand == .idle, !grid else { return }
        drawBack(.gone)
        guard hand == .gone else { return }
        ticks += 1
        settle(toGrid: true, seconds: Self.toGrid, curve: { GalleryCamera.ease($0) })
    }

    private func pinched(_ scale: CGFloat) {
        guard hand == .pinch else { return }
        camera.pose((1 - scale) / Self.pinchFull)
    }

    private func unpinched(_ scale: CGFloat, _ speed: CGFloat) {
        guard hand == .pinch else { return }
        settle(toGrid: camera.z > 0.3 || speed < -0.6, seconds: 0.32)
    }

    /// Two fingers spread on a tile: that work grows out of it.
    private func spread(at point: CGPoint) {
        guard hand == .idle, grid, gridOpen, returning == nil else { return }
        let inGrid = CGPoint(x: point.x - area.minX, y: point.y - area.minY + track.offset)
        guard let n = metrics.index(at: inGrid), n >= gridLead, works.indices.contains(gridFirst + n - gridLead),
              aim(works[gridFirst + n - gridLead])
        else { return }
        hand = .spread
        gridLocked = true
    }

    private func spreading(_ scale: CGFloat) {
        guard hand == .spread else { return }
        camera.pose(1 - (scale - 1) / Self.spreadFull)
    }

    private func spreadEnded(_ scale: CGFloat, _ speed: CGFloat) {
        guard hand == .spread else { return }
        settle(toGrid: camera.z > 0.7 && speed < 0.8, seconds: 0.32)
    }

    /// The camera the rest of its way, to the tile or to the page.
    /// `seconds` for the whole way, less for a part of it; `lasting`:
    /// just that long.
    private func settle(
        toGrid: Bool, seconds: Double = 0, lasting: Double? = nil,
        curve: @escaping (CGFloat) -> CGFloat = { GalleryCamera.out($0) }
    ) {
        let from = camera.z, drop = camera.drop
        let to: CGFloat = toGrid ? 1 : 0
        let seconds = lasting ?? seconds * Double(max(abs(to - from), 0.4))
        let id = returning ?? shown?.id
        if toGrid { withTransaction(Self.quiet) { bars = true } }
        coast.run { now in
            let t = min(CGFloat(now / seconds), 1)
            let done = curve(t)
            camera.pose(from + (to - from) * done, drop: drop * (1 - done))
            if !toGrid {
                GalleryLog.trace(
                    "to the page \(Int(now * 1000)) ms: pages at \(Int(flow.y)), \(lies(at: id) ? "there" : "not there"), "
                        + "window \(windowShown ? "shown" : "hidden")"
                )
            }
            guard t >= 1 else { return true }
            if toGrid { gridSettled(on: id) } else { pageSettled() }
            return false
        }
    }

    /// The work is its tile: the pages go, the grid is all there is, with
    /// the tab bar.
    private func gridSettled(on id: String?) {
        camera.pose(1)
        withTransaction(Self.quiet) {
            windowShown = false
            bars = true
            if let id, position != id, hand == .sweep { position = id }
        }
        hand = .idle
        pulling = false
        gridLocked = false
        returning = nil
        gridOpen = true
        GalleryLog.note("grid open at \(Int(track.offset))")
    }

    /// The work fills the screen: the grid goes, once the page has its own
    /// picture (a moment more at most, the tile grown large meanwhile).
    private func pageSettled() {
        let id = returning
        Task { @MainActor in
            if let id {
                let until = ContinuousClock.now + .milliseconds(600)
                while readyPage != id || !lies(at: id), ContinuousClock.now < until {
                    try? await Task.sleep(for: .milliseconds(16))
                }
                GalleryLog.trace("pages at \(Int(flow.y)), \(lies(at: id) ? "there" : "not there")")
            }
            withTransaction(Self.quiet) {
                windowShown = true
                gridOpen = false
                bars = false
                returning = nil
            }
            // Not quietly: the page's caption comes back in gently.
            grid = false
            camera.on = false
            hand = .idle
            pulling = false
            gridLocked = false
            run.reset(at: shownIndex ?? 0)
            withAnimation(.easeOut(duration: 0.25)) { heartShown = true }
            GalleryLog.note("page settled\(id == nil ? "" : readyPage == id ? ", ready" : ", not ready")")
        }
    }

    /// A tile tapped: it grows to the whole screen at once, its page under
    /// it by the end (Mateusz 2026-11-24 17:23: "Powrót z siatki … bardzo
    /// skacze"; nothing is waited for before it moves now).
    private func closeGrid(on work: RemoteItem) {
        guard hand == .idle, grid, gridOpen, returning == nil, aim(work) else { return }
        hand = .back
        settle(toGrid: false, seconds: 0.36, curve: { GalleryCamera.ease($0) })
    }

    /// The camera set on a work's tile, its page put under it: shown as
    /// soon as it has its picture.
    private func aim(_ work: RemoteItem) -> Bool {
        guard let index = works.firstIndex(where: { $0.id == work.id }), index >= gridFirst, area.width > 0
        else { return false }
        coast.stop()
        camera.screen = area
        camera.tile = tile(of: index)
        camera.pose(1)
        camera.on = true
        returning = work.id
        withTransaction(Self.quiet) {
            windowShown = readyPage == work.id && position == work.id && lies(at: work.id)
            position = work.id
        }
        gridOpen = false
        withAnimation(GalleryPage.toWhole) { bars = false }
        GalleryLog.note("aimed at \(index), tile at \(Int(camera.tile.minY)), page \(windowShown ? "ready" : "to come")")
        return true
    }

    /// A page has its picture and the point it is cut about.
    private func pageReady(_ id: String) {
        readyPage = id
        showWindow()
    }

    /// The pages seen over the tile that grows: once the page aimed at has
    /// its picture and the pages lie at it (far down the works they take
    /// a moment to get there, and were seen on their way: the fifth film
    /// of 2026-11-24).
    private func showWindow() {
        guard let id = returning, !windowShown, readyPage == id, lies(at: id) else { return }
        withAnimation(.easeOut(duration: 0.1)) { windowShown = true }
    }

    /// The pages are scrolled to this work's own.
    private func lies(at id: String?) -> Bool {
        guard let id, area.height > 0, let index = works.firstIndex(where: { $0.id == id }) else { return false }
        return abs(flow.y - CGFloat(index) * area.height) < 1
    }

    // MARK: The grid's stock

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
        guard !works.isEmpty else { return }
        let at = min(at, works.count - 1)
        let kept = works[max(at - Self.seen - 3, 0) ..< min(at + Self.gridReady + 60, works.count)]
        stock.keep(Set(kept.map(\.id)))
        prefetch(works.dropFirst(at).prefix(Self.gridReady))
        prefetch(works[max(at - Self.seen, 0) ..< at].reversed())
    }

    /// Thumbnails fetched before they are shown, at the grid's size, six at
    /// a time, and held in the grid's stock.
    private func prefetch(_ some: some Sequence<RemoteItem>) {
        let kept = stock
        let jobs = some.filter { kept.images[$0.id] == nil }
            .compactMap { work in Self.thumb(of: work.item, model.backend).map { (work.id, $0) } }
        guard !jobs.isEmpty else { return }
        // A thumbnail asked for before its work was cut is not kept.
        let made = Dictionary(jobs.map { ($0.0, kept.made[$0.0] ?? 0) }) { first, _ in first }
        let pixel = Self.gridPixel
        Task(priority: .utility) {
            await withTaskGroup(of: (String, UIImage?, UnitPoint).self) { group in
                var next = jobs.makeIterator()
                for _ in 0 ..< 6 {
                    if case let (id, request)? = next.next() { group.addTask { await Self.fetch(id, request, pixel) } }
                }
                while case let (done, image, focus)? = await group.next() {
                    if let image, kept.made[done] ?? 0 == made[done] {
                        kept.images[done] = image
                        // Its page's, where that found one first.
                        if kept.focus[done] == nil { kept.focus[done] = focus }
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
        // After the pictures on the screen, and waited for: the stock keeps
        // the point the page will cut it about, never a guess.
        let focus = await SubjectFocus.shared.point(
            in: image, key: ImageLoader.pictureKey(request), subject: true, patience: 30, ahead: false
        )
        return (id, image, focus)
    }

    // MARK: The whole work, and its card

    /// How far up the finger is drawn from the hold for the card.
    static let cardPull: CGFloat = 70

    /// Held: the whole work is shown on its own colours while the finger
    /// lies (Mateusz 2026-11-24 18:51: "Podoba mi się koncept z całym
    /// dziełem po przytrzymaniu. Można dodać do tego haptyke - stukanie").
    /// The phone's taps on the way to it and the hard one with it are the
    /// gesture's own (`HoldPull`).
    private func hold() {
        guard hand == .idle, !grid, path.isEmpty, peek == nil, let shown else { return }
        pulling = true
        engaged = false
        pull.up = 0
        withAnimation(GalleryPage.toWhole) { peek = shown.id }
        GalleryLog.note("held")
    }

    /// A hold can begin: the phone taps towards it only then (`HoldPull`).
    private var canHold: Bool { hand == .idle && !grid && path.isEmpty && peek == nil && shown != nil }

    /// The finger drawn up from the hold: the work follows a little, and
    /// far enough the phone taps again and the work's card comes out from
    /// under it (18:51: "po przytrzymaniu … pociągnięcie w górę otwiera
    /// płynnie kartę dzieła").
    private func held(_ up: CGFloat) {
        guard let id = peek, !engaged else { return }
        pull.up = max(up, 0)
        guard up > Self.cardPull, let work = works.first(where: { $0.id == id }) else { return }
        engaged = true
        ticks += 1
        GalleryLog.note("pulled up \(Int(up)): the card")
        open(work)
    }

    /// The finger lifted: cut to the screen again, unless the card came.
    private func letGo() {
        guard peek != nil, !engaged else { return }
        pulling = false
        withAnimation(GalleryPage.fromWhole) {
            peek = nil
            pull.up = 0
        }
        GalleryLog.note("let go")
    }

    /// The card without the push's slide: it takes the work from where it
    /// lies here (Mateusz 2026-11-24 07:36: "dzieło podsuwa się do góry na
    /// miejsce w karcie dzieła i pojawia się reszta treści"), as wide
    /// there as here, and the rest of the card rides up from under it.
    private func open(_ work: RemoteItem) {
        ItemPeeks.remember(work.summary, thumb: .thumb(work.id))
        let from = GalleryPage.spots[work.id]?.offsetBy(dx: 0, dy: -GalleryPull.lift(pull.up))
        // The way back: the card melts into the work cut to the screen,
        // which is there under it already (Mateusz 2026-11-25: "Powrót z
        // karty dzieła do pełnego ekranu źle wygląda - jest jakiś skok":
        // the work went back to where it was held, the card's head under
        // it for a moment, and all of that gave way to the cut work).
        CardArrival.pending[work.id] = CardArrival.Pending(
            from: from, ground: GalleryPage.ground(of: work, light: scheme == .light),
            rest: GalleryPage.spots[work.id],
            back: { whole in
                if whole {
                    // The card drawn down (`CardLeave`) is the whole work
                    // as it rests here by now, on the same ground and
                    // glow: the card is gone from over it with nothing
                    // moving but the bars, and the work grows to the
                    // screen as when a finger lets it go (`path`'s change
                    // above).
                    GalleryLog.note("back from the card, drawn down: the whole work, and closer from there")
                    Self.melt(bars: true)
                    withTransaction(Self.quiet) {
                        engaged = false
                        pulling = false
                        pull.up = 0
                        if !path.isEmpty { path.removeLast() }
                    }
                    return
                }
                GalleryLog.note("back from the card: it melts into the work")
                Self.melt()
                withTransaction(Self.quiet) {
                    engaged = false
                    pulling = false
                    peek = nil
                    pull.up = 0
                    if !path.isEmpty { path.removeLast() }
                }
            }
        )
        withTransaction(Self.quiet) { path.append(work.id) }
    }

    /// What is on the screen now fades off what comes under it with the
    /// next change: the screen as it is, laid over the window and let go.
    /// `bars`: only its top and its foot, where the card's bars are (what
    /// lies between them is the same under it, and is to be seen moving at
    /// once).
    private static func melt(seconds: Double = 0.32, bars: Bool = false) {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        guard let window = scenes.first?.keyWindow ?? scenes.first?.windows.first else { return }
        var pieces: [UIView] = []
        if bars {
            let all = window.bounds, insets = window.safeAreaInsets
            let top = CGRect(x: 0, y: 0, width: all.width, height: insets.top + 56)
            let foot = CGRect(x: 0, y: all.height - insets.bottom - 70, width: all.width, height: insets.bottom + 70)
            for part in [top, foot] {
                guard let was = window.resizableSnapshotView(from: part, afterScreenUpdates: false, withCapInsets: .zero)
                else { continue }
                was.frame = part
                pieces.append(was)
            }
        } else if let was = window.snapshotView(afterScreenUpdates: false) {
            pieces.append(was)
        }
        for was in pieces {
            was.isUserInteractionEnabled = false
            window.addSubview(was)
        }
        UIView.animate(withDuration: seconds, delay: 0.03, options: [.curveEaseInOut]) {
            for was in pieces { was.alpha = 0 }
        } completion: { _ in
            for was in pieces { was.removeFromSuperview() }
        }
    }

    // MARK: Staged

    /// CI screenshots and the simulator's probe: `-screen gallery-grid`
    /// opens the grid, `-screen gallery-whole` holds the work, and
    /// `-gallerySweep YES` swipes through the works by itself, quickly.
    private func staged() async {
        let sweeps = UserDefaults.standard.bool(forKey: "gallerySweep")
        guard sweeps || ["gallery-grid", "gallery-whole"].contains(LaunchRoute.screen) else { return }
        try? await Task.sleep(for: .seconds(4))
        guard works.count > 12 else { return }
        if sweeps {
            for index in 1 ... 10 where !grid {
                withAnimation(.easeOut(duration: 0.26)) { position = works[index].id }
                try? await Task.sleep(for: .milliseconds(360))
            }
            return
        }
        withTransaction(Self.quiet) { position = works[5].id }
        try? await Task.sleep(for: .seconds(2))
        if LaunchRoute.screen == "gallery-whole" {
            hold()
        } else {
            drawBack(.swipe)
            dropped(100, 0)
        }
    }

    // MARK: The works

    private static let rememberedKey = "gallery.next"
    private static let rememberedSeenKey = "gallery.next.seen"
    private static let rememberedMost = 24
    /// Works above the one Galeria starts with: the last looked at before
    /// (the first of a batch, the first time), so the grid has a full row
    /// above from the start (`history`).
    private static let above = 2

    /// The works left to see, after the last ones looked at (`remember`),
    /// kept for the next launch (CI screenshots start from the demo's own
    /// order).
    private static func remembered() -> [RemoteItem] {
        guard LaunchRoute.screen.isEmpty,
              let data = UserDefaults.standard.data(forKey: rememberedKey),
              let works = try? JSONDecoder().decode([RemoteItem].self, from: data)
        else { return [] }
        return works
    }

    /// The works from the one before the one shown on: those two were
    /// looked at and lie above the first the next launch starts with.
    private func remember() {
        guard !works.isEmpty else { return }
        let at = works.firstIndex { $0.id == position } ?? 0
        let from = max(at - (Self.above - 1), 0)
        let kept = Array(works[from...].prefix(Self.rememberedMost + Self.above))
        guard let data = try? JSONEncoder().encode(kept) else { return }
        UserDefaults.standard.set(data, forKey: Self.rememberedKey)
        UserDefaults.standard.set(at - from + 1, forKey: Self.rememberedSeenKey)
    }

    /// Galeria starts with the first work not looked at yet, the last ones
    /// looked at above it; of a first batch, two are put above. A list
    /// kept by an app from before this (no count with it) is all works to
    /// see: two of them go above as well.
    ///
    /// The pages are laid out first, and the work is seen to lie on the
    /// screen before Galeria shows: a scroll asked for while the pages
    /// were still coming was lost (the probe of 2026-11-25 began on the
    /// first work, with no caption and another's heart: the pages lay at
    /// the first, Galeria held the third).
    private func begin() async {
        guard !begun else { return }
        defer { begun = true }
        guard works.count > 1 else { return }
        let kept = UserDefaults.standard.object(forKey: Self.rememberedSeenKey) as? Int
        let seen = LaunchRoute.screen.isEmpty ? kept ?? Self.above : Self.above
        let at = min(max(seen, 0), Self.above, works.count - 1)
        let id = works[at].id
        run.reset(at: at)
        guard at > 0 else {
            withTransaction(Self.quiet) { position = id }
            GalleryLog.note("begins at 0 of \(works.count)")
            return
        }
        for _ in 0 ..< 60 where !(area.height > 0 && flow.tall >= CGFloat(at + 1) * area.height - 1) {
            try? await Task.sleep(for: .milliseconds(25))
        }
        withTransaction(Self.quiet) { position = id }
        var asked = 1
        for _ in 0 ..< 20 {
            try? await Task.sleep(for: .milliseconds(30))
            guard position == id, !lies(at: id) else { break }
            // Asked again, by way of the work before: the same id set
            // twice is no change, and no scroll.
            withTransaction(Self.quiet) { position = works[at - 1].id }
            try? await Task.sleep(for: .milliseconds(16))
            withTransaction(Self.quiet) { position = id }
            asked += 1
        }
        GalleryLog.note(
            "begins at \(at) of \(works.count), asked \(asked == 1 ? "once" : "\(asked) times")"
                + (lies(at: id) ? "" : ", not there")
        )
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
                withTransaction(Self.quiet) { position = first.id }
                Task {
                    try? await Task.sleep(for: .seconds(0.35))
                    withAnimation(.easeOut(duration: 0.8)) { surfacing = false }
                }
            }
            if position == nil { position = works.first?.id }
            if begun { remember() }
            cutAhead()
        } catch {
            failed = works.isEmpty
        }
    }

    /// The works coming next cut down to the work in the background, as the
    /// card does when it opens (Mateusz 2026-11-23 21:41: "Dzieła idące na
    /// Galerię kadruj w tle (usuwaj zbędne tło)"): the server looks first,
    /// then, on the owner's phone, its own model. Not the one shown: what
    /// is looked at does not change (`GalleryPage`).
    private func cutAhead() {
        guard cutting == nil else { return }
        cutting = Task {
            defer { cutting = nil }
            while !Task.isCancelled {
                let at = works.firstIndex { $0.id == position } ?? 0
                guard let next = works.dropFirst(at + 1).first(where: { !Self.looked.contains($0.id) }) else { return }
                Self.looked.insert(next.id)
                guard let cut = await cutDown(next.item) else { continue }
                cutHere.insert(cut.id)
                // The lists' and the card's pictures of it, from before.
                model.cardShows(cut, changed: true)
                taken(cut)
            }
        }
    }

    /// A work as it is now, its picture another than Galeria had (cut down
    /// to the work, mostly): the thumbnail and the glow made of the old
    /// one go, and its page and its tile have theirs anew, by the
    /// picture's own address (`thumb(of:)`). Before, the thumbnail fetched
    /// ahead was of the museum's whole photograph and the full picture
    /// that came over it of the work cut down, laid out as one (Mateusz
    /// 2026-11-25: "przy podmianie z miniatury na pełne dzieło … przeskok,
    /// jakby dzieło zmieniało proporcje i zoom").
    private func taken(_ item: Item) {
        guard let index = works.firstIndex(where: { $0.id == item.id }),
              works[index].item.pictureVersion != item.pictureVersion
        else { return }
        works[index].item = item
        stock.drop(item.id)
        Glow.forget(item.id)
        prefetch([works[index]])
        if begun { remember() }
        GalleryLog.note("work \(item.id): another picture, had anew")
    }

    /// A work's picture changed, not by Galeria: asked how it is now.
    private func repictured(_ id: String) {
        if cutHere.remove(id) != nil { return }
        guard works.contains(where: { $0.id == id }) else { return }
        Task {
            guard let fresh = try? await model.backend.item(id: id) else { return }
            taken(fresh)
        }
    }

    /// A work's thumbnail and its picture, by what they are of: the copy
    /// and the cut are in the address (`Item.pictureVersion`), so one kept
    /// from before the work was cut down is never taken for the one after.
    static func thumb(of item: Item, _ backend: any FrameBackend) -> URLRequest? {
        guard var request = backend.request(for: .thumb(item.id)) else { return nil }
        let version = item.pictureVersion
        guard !version.isEmpty, let url = request.url, url.path.hasSuffix("/thumb"),
              var parts = URLComponents(url: url, resolvingAgainstBaseURL: false)
        else { return request }
        parts.queryItems = (parts.queryItems ?? []) + [URLQueryItem(name: "v", value: version)]
        request.url = parts.url ?? url
        return request
    }

    static func picture(of item: Item, _ backend: any FrameBackend) -> URLRequest? {
        backend.request(for: item.originalRef)
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
/// little sideways. Held, the whole of it on its own colours.
private struct GalleryPage: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorScheme) private var scheme
    let work: RemoteItem
    /// On screen now: it draws back and drifts a little.
    var current = false
    /// Held: the whole of it, the head of its card under it (Mateusz
    /// 2026-11-24 18:51, 19:12).
    var whole = false
    /// A finger lies on it, the phone tapping towards the hold: it sinks
    /// in a little, as a thing that can be pressed (Mateusz 2026-11-25
    /// 07:09: "delikatne, stopniowe pomniejszenie dzieła, sugestie że da
    /// się je wcisnąć").
    var pressed = false
    /// The grid is up: cut as its tile is, no closer and no further, and
    /// no caption, so the two are one picture on the way between them.
    var still = false
    /// The screen's own edges (`GalleryView.insets`).
    var insets = EdgeInsets()
    /// How far the finger that holds it has been drawn up.
    let pull: GalleryPull
    /// The grid's thumbnails and the points they are cut about: a page
    /// starts as its tile, with the tile's picture and about its point,
    /// and what it finds first is its tile's (the film of 2026-11-24: a
    /// page that had waited for its own was empty for a moment after its
    /// tile had grown, and then cut about another point).
    let stock: GridStock
    /// The works before and after it, whose grounds its own flows into at
    /// its top and foot (Mateusz 2026-11-24: "na łączeniu tła przy
    /// przewijaniu widać ostrą krawędź. Zróbmy tam płynne przejście").
    var above: RemoteItem?
    var below: RemoteItem?
    /// It is shown and has its picture and the point it is cut about.
    var ready: () -> Void = {}

    @State private var thumb: UIImage?
    @State private var full: UIImage?
    @State private var polish: PolishText?
    /// The card's head under the whole work, as tall as it is.
    @State private var headHeight = Whole.headGuess
    @State private var focus: UnitPoint?
    /// The full picture over the thumbnail, 1 once it is in.
    @State private var fullShown: Double = 1
    /// A picture of another shape than the one that came after it (the
    /// museum's whole photograph, the work cut down since), with the point
    /// it was cut about: it fades under the new one, each laid out as
    /// itself, never drawn to the other's shape (`arrived`).
    @State private var stale: (picture: UIImage, focus: UnitPoint)?
    /// Which picture of the work this page has (`Item.pictureVersion`),
    /// and the times it has had another since.
    @State private var had: String?
    @State private var anew = 0
    /// The sign under the whole work, up for a moment (`CardSign`).
    @State private var nudged = false
    /// The colours of the work's edges stretched far out and blurred, for
    /// behind the whole of it (`Glow`); made while it is shown.
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
    /// How small the work pressed is of itself, and how round its corners
    /// then (points): the screen's own, about.
    static let pressedIn: CGFloat = 0.955
    static let pressedCorner: CGFloat = 44
    /// The whole work's corners (points).
    static let wholeCorner: CGFloat = 8
    /// Seconds from the work held to the whole of it, and from the whole
    /// work let go to the work cut to the screen again (Mateusz 2026-11-25
    /// 12:21: "Powrót po puszczeniu podglądu całego dzieła - wolniej,
    /// płynniej - teraz jest zbyt agresywnie"; it took a fifth of a second
    /// and sprang).
    static let out: Double = 0.42
    static let back: Double = 0.5
    /// Seconds to draw back from `closer` to the whole picture.
    static let drawBack: Double = 20

    static let thumbPixel: CGFloat = 900
    /// The size the work's card asks its first picture at (`ItemDetailView`).
    static let cardPixel: CGFloat = 700
    private static let fullPixel: CGFloat = 2800

    /// Where the whole work lies on the screen, for its card to take it
    /// from there (`CardArrival`).
    @MainActor static var spots: [String: CGRect] = [:]

    var body: some View {
        GeometryReader { geo in
            ZStack {
                if let shown = full ?? thumb, let focus {
                    let layout = Fill(picture: shown.size, box: geo.size, focus: focus)
                    let place = Whole(picture: shown.size, box: geo.size, insets: insets, head: headHeight)
                    // One picture, drawn back from the screen it is cut
                    // to till the whole of it is seen, and closer again
                    // (Mateusz 2026-11-25 14:21: "płynnie - przejście od
                    // zoomu do pełnego i na odwrót (bez skoku
                    // i przenikania)"; `Lens`, `Window`). Its glow lies
                    // under it from the first tap and is only uncovered.
                    // Before, two pictures and one melting into the other
                    // (2026-11-23 20:14, "Rozpływ w łunę").
                    glowLayer(place, geo)
                    shade(layout, place, geo)
                    cut(layout, place, geo)
                    headLayer(place, geo)
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
            .task(id: Drift(current: current, still: still, sized: geo.size.width > 0)) { await drawBack(geo.size) }
        }
        .background {
            ZStack {
                placeholder
                ground.opacity(lit ? 1 : 0)
                    .animation(lit ? nil : Self.unlit, value: lit)
            }
            .ignoresSafeArea()
        }
        .task(id: Had(id: work.id, anew: anew)) { await load() }
        .onChange(of: Recut(version: work.item.pictureVersion, current: current), initial: true) { _, now in
            // The work has another picture (cut down since this page came):
            // had anew, but never under his eyes (Mateusz 2026-11-25: the
            // cut "odbywa się w trakcie i daje efekt na ekranie, a nie
            // przed wejściem dzieła na podgląd"). The one looked at stays
            // as it is till it is left.
            guard let before = had else { had = now.version; return }
            guard now.version != before, !now.current else { return }
            had = now.version
            anew += 1
        }
        .task(id: current) { if current { await loadPolish() } }
        .task(id: whole && current) { await nudge() }
        .task(id: current ? thumb.map { ObjectIdentifier($0) } : nil) {
            // Its card opens with this thumbnail, asked for at the plain
            // address: there in memory, whatever address it came from here.
            guard current, let thumb, let request = model.backend.request(for: .thumb(work.id)) else { return }
            await ImageLoader.shared.remember(thumb, for: request, maxPixel: Self.cardPixel)
        }
        // Made while the work is shown, before any hold: ready for it.
        .task(id: GlowOf(on: current || whole, picture: (thumb ?? full).map { ObjectIdentifier($0) })) {
            guard current || whole, glow == nil, let picture = thumb ?? full else { return }
            if let made = Glow.wide[work.id] { glow = made; return }
            let made = await Task.detached(priority: .utility) {
                (Glow.edges(of: picture, reach: Glow.far, hold: Glow.farHold), Glow.edges(of: picture))
            }.value
            glow = made.0
            Glow.keep(wide: made.0, near: made.1, for: work.id)
        }
        .onChange(of: Shown(current: current, loaded: (full ?? thumb) != nil && focus != nil), initial: true) { _, now in
            if now.current, now.loaded { ready() }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(work.item.displayTitle)
    }

    private struct Drift: Equatable {
        let current: Bool
        let still: Bool
        let sized: Bool
    }

    /// The glow is made of the picture the page has, again of another.
    private struct GlowOf: Hashable {
        let on: Bool
        let picture: ObjectIdentifier?
    }

    private struct Had: Equatable {
        let id: String
        let anew: Int
    }

    private struct Recut: Equatable {
        let version: String
        let current: Bool
    }

    private struct Shown: Equatable {
        let current: Bool
        let loaded: Bool
    }

    /// Pressed in: under a finger on its way to the hold, and held.
    private var sunk: Bool { (pressed || whole) && !reduceMotion }

    /// What lies under the work is there: from the first tap, behind the
    /// work that still covers it, till the work covers it again.
    private var lit: Bool { pressed || whole }
    /// Gone at once, once the work is back over it.
    private static let unlit = Animation.linear(duration: 0.01).delay(back + 0.1)

    /// The way out to the whole work and the way back: no spring in
    /// either, nothing fading.
    private static let outWay = Animation.smooth(duration: out)
    private static let backWay = Animation.smooth(duration: back)

    /// The work cut to the screen, its title and artist low on it; held,
    /// the same picture drawn back to the whole of it.
    private func cut(_ layout: Fill, _ place: Whole, _ geo: GeometryProxy) -> some View {
        let sink = sunk ? Self.pressedIn : 1
        let way: CGFloat = whole ? 1 : 0
        // The whole work's corners, rounded a little as on its card (Mateusz
        // 2026-11-23 22:08: "Narożniki dzieła odrobinę zaokrąglone"): the
        // picture's own, as large here as they are small once it is whole.
        let corner = whole ? Self.wholeCorner / Lens.smaller(layout, place) : 0
        return ZStack {
            if let stale {
                let own = Fill(picture: stale.picture.size, box: geo.size, focus: stale.focus)
                picture(stale.picture, size: own.size, offset: own.offset)
                    .scaleEffect(zoom, anchor: own.anchor)
                    .offset(x: pan)
                    .scaleEffect(sink)
                    .opacity(whole ? 0 : 1)
            }
            ZStack {
                if let thumb { picture(thumb, size: layout.size, offset: layout.offset, corner: corner) }
                if let full { picture(full, size: layout.size, offset: layout.offset, corner: corner).opacity(fullShown) }
            }
            // Two effects, never one: what a finger does (`Lens`) has
            // numbers of its own to animate, and the slow draw-back under
            // it goes on as it went (`Nearer`).
            .modifier(
                Nearer(zoom: zoom, pan: pan, fade: way, anchor: layout.anchor, traced: pressed && !whole)
                    .ignoredByLayout()
            )
            .modifier(Lens(sink: sink, way: way, layout: layout, place: place).ignoredByLayout())
            if current {
                // Gone before the work has drawn back from under it (its
                // shade lay on the glow for two frames of the probe's
                // film), there again once the work is back.
                caption(geo)
                    .opacity(still || whole ? 0 : 1)
                    .animation(still ? .easeOut(duration: 0.12) : .easeOut(duration: 0.3), value: still)
                    .animation(whole ? .easeOut(duration: 0.07) : .easeOut(duration: 0.2).delay(Self.back * 0.75), value: whole)
                    .scaleEffect(sink)
            }
        }
        .frame(width: geo.size.width, height: geo.size.height)
        // Seen through a window: the screen, pressed in and its corners
        // rounded while the finger lies and the phone taps, and so till
        // the work is let go. The picture draws back inside it, and its
        // own edges come into it one after another.
        .clipShape(Window(sink: sink, corner: sunk ? Self.pressedCorner : 0))
        // Let go before the hold, the page springs back out; to the whole
        // work and back from it, all of it goes as one.
        .transaction(value: whole) { $0.animation = whole ? Self.outWay : Self.backWay }
        .animation(sunk ? .easeInOut(duration: HoldPull.press) : .spring(duration: 0.32, bounce: 0.3), value: sunk)
        .modifier(PulledUp(pull: pull, on: whole))
    }

    /// The whole work's faint shadow (2026-11-23 21:41: "cień za dziełem
    /// znacznie słabszy"): under the picture and going with it, there as
    /// the work draws back and gone as soon as it is let go. (It goes
    /// without the draw-back and the drift, a point or two off on the
    /// way: every frame of those would be a frame of this.)
    private func shade(_ layout: Fill, _ place: Whole, _ geo: GeometryProxy) -> some View {
        let smaller = Lens.smaller(layout, place)
        return RoundedRectangle(cornerRadius: Self.wholeCorner / smaller, style: .continuous)
            .fill(.black.opacity(0.14))
            .frame(width: layout.size.width, height: layout.size.height)
            .blur(radius: 8 / smaller)
            .offset(x: layout.offset.width, y: layout.offset.height + 3 / smaller)
            .modifier(
                Lens(
                    sink: sunk ? Self.pressedIn : 1, way: whole ? 1 : 0,
                    layout: layout, place: place, traced: false
                ).ignoredByLayout()
            )
            .transaction(value: whole) { $0.animation = whole ? Self.outWay : Self.backWay }
            .animation(sunk ? .easeInOut(duration: HoldPull.press) : .spring(duration: 0.32, bounce: 0.3), value: sunk)
            .frame(width: geo.size.width, height: geo.size.height)
            .opacity(whole ? 1 : 0)
            .animation(whole ? Self.outWay : .easeOut(duration: 0.12), value: whole)
            .modifier(PulledUp(pull: pull, on: whole))
            .allowsHitTesting(false)
    }

    /// The colours of the whole work's edges, the screen full of them
    /// (Mateusz 2026-11-24 19:12: "łuna zdecydowanie szersza, pełniej
    /// wypełniająca ekran").
    private func glowLayer(_ place: Whole, _ geo: GeometryProxy) -> some View {
        ZStack {
            if let glow {
                Glow(edges: glow, size: place.size, offset: place.offset, spread: Glow.far)
                    // On paper, paler (2026-11-23 21:43: "Podkład jasny w
                    // trybie jasnym i ciemny w trybie ciemnym").
                    .opacity(scheme == .light ? 0.62 : 1)
            }
        }
        .frame(width: geo.size.width, height: geo.size.height)
        .modifier(PulledUp(pull: pull, on: whole))
        .opacity(lit ? 1 : 0)
        .animation(lit ? nil : Self.unlit, value: lit)
    }

    /// Under the whole work, the sign that a pull up brings its card and
    /// the card's head where the card has it: they come once the work is
    /// nearly there, and go before it leaves.
    private func headLayer(_ place: Whole, _ geo: GeometryProxy) -> some View {
        let lies = spot(place, geo)
        return ZStack {
            if current {
                sign(place, geo)
                head(place, geo)
            }
        }
        .frame(width: geo.size.width, height: geo.size.height)
        .modifier(PulledUp(pull: pull, on: whole))
        .offset(y: whole ? 0 : 10)
        .opacity(whole ? 1 : 0)
        .animation(whole ? .easeOut(duration: 0.26).delay(Self.out * 0.55) : .easeIn(duration: 0.12), value: whole)
        .allowsHitTesting(false)
        .onChange(of: current ? lies : CGRect.null, initial: true) { _, rect in
            guard !rect.isNull else { return }
            if Self.spots.count > 200 { Self.spots.removeAll() }
            Self.spots[work.id] = rect
        }
    }

    private func spot(_ place: Whole, _ geo: GeometryProxy) -> CGRect {
        let frame = geo.frame(in: .global)
        return CGRect(
            x: frame.midX + place.offset.width - place.size.width / 2,
            y: frame.midY + place.offset.height - place.size.height / 2,
            width: place.size.width, height: place.size.height
        )
    }

    /// The title and the artist, low on the cut work, on a shade (Mateusz
    /// 2026-11-23 18:20: "Na pełnym ekranie pokazuj także tytuł i autora").
    private func caption(_ geo: GeometryProxy) -> some View {
        GalleryCaption(work: work, polish: polish)
            .padding(.bottom, max(insets.bottom, 34))
            .frame(width: geo.size.width, height: geo.size.height, alignment: .bottom)
    }

    /// The head of the work's card under the whole work (Mateusz
    /// 2026-11-24 19:12: no "KARTA DZIEŁA"; the card's own beginning says
    /// what a pull up brings). It follows the sign a little when that
    /// goes up.
    private func head(_ place: Whole, _ geo: GeometryProxy) -> some View {
        let top = geo.size.height / 2 + place.offset.height + place.size.height / 2 + Whole.head
        return GalleryHead(work: work, polish: polish)
            .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { height in
                if abs(height - headHeight) > 0.5 { headHeight = height }
            }
            .padding(.horizontal, Theme.gutter)
            .padding(.top, top)
            .frame(width: geo.size.width, height: geo.size.height, alignment: .top)
            .offset(y: nudged ? -CardSign.follow : 0)
    }

    /// The sign that a pull up brings the card: a short bar between the
    /// work and the card's head, which goes up a little now and then and
    /// comes back (Mateusz 2026-11-25: "potrzebny jest jednak jakiś sygnał
    /// / znacznik o możliwości wejścia w kartę dzieła … może belka, która
    /// delikatnie podciąga się do góry i daje znać?").
    private func sign(_ place: Whole, _ geo: GeometryProxy) -> some View {
        let top = geo.size.height / 2 + place.offset.height + place.size.height / 2 + CardSign.below
        return CardSign(pull: pull, up: nudged, light: scheme == .light)
            .padding(.top, top)
            .frame(width: geo.size.width, height: geo.size.height, alignment: .top)
    }

    /// The sign's small way up and back while the work is held: after a
    /// moment, then every few seconds.
    private func nudge() async {
        guard whole, current, !reduceMotion else {
            nudged = false
            return
        }
        try? await Task.sleep(for: .milliseconds(650))
        while !Task.isCancelled {
            withAnimation(.easeOut(duration: 0.45)) { nudged = true }
            try? await Task.sleep(for: .milliseconds(600))
            guard !Task.isCancelled else { break }
            withAnimation(.easeInOut(duration: 0.8)) { nudged = false }
            try? await Task.sleep(for: .milliseconds(2000))
        }
        nudged = false
    }

    /// Behind the whole work: its own main colour, quiet and dark
    /// (Mateusz 2026-11-23 17:42: "Tło za dziełem nie czarne, tylko
    /// wypełnione stonowaną barwą dzieła").
    /// In light mode a paper in the work's colour, light and nearly grey
    /// (Mateusz 2026-11-23 21:43: "Podkład jasny w trybie jasnym i ciemny w
    /// trybie ciemnym").
    private var behind: Color { Self.ground(of: work, light: scheme == .light) }

    static func ground(of work: RemoteItem, light: Bool) -> Color {
        let hex = work.item.colors.first?.hex ?? ""
        return toned(UIColor(Color(hexString: hex) ?? .black), light: light)
    }

    /// Its own ground, meeting each neighbour's halfway at the seam: both
    /// pages are the same colour there, so scrolling shows no edge.
    private var ground: LinearGradient {
        let own = behind
        let light = scheme == .light
        let top = above.map { own.mix(with: Self.ground(of: $0, light: light), by: 0.5) } ?? own
        let foot = below.map { own.mix(with: Self.ground(of: $0, light: light), by: 0.5) } ?? own
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

    private func picture(_ image: UIImage, size: CGSize, offset: CGSize, corner: CGFloat = 0) -> some View {
        Image(uiImage: image)
            .resizable()
            .interpolation(.high)
            .frame(width: size.width, height: size.height)
            .clipShape(RoundedRectangle(cornerRadius: corner, style: .continuous))
            .offset(offset)
    }

    /// The caption's Polish texts: asked for once the work has stayed a
    /// moment, not for each one swiped past; one for both its captions.
    private func loadPolish() async {
        polish = ItemPeeks.polish[work.id]
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
        guard let thumbRequest = GalleryView.thumb(of: work.item, model.backend),
              let fullRequest = GalleryView.picture(of: work.item, model.backend)
        else { return }
        // Had anew (`anew`): what it has stays till the new one is here.
        let again = thumb != nil || full != nil
        if !again {
            if focus == nil, let point = stock.focus[work.id] { focus = point }
            // Born under the grid: its tile's own picture till a larger comes.
            if still, focus != nil, let image = stock.images[work.id] { thumb = image }
        }
        // In memory already (seen a moment ago): from the first frame.
        if let image = ImageLoader.inMemory(for: fullRequest, maxPixel: Self.fullPixel) {
            let point = await cutPoint(of: image, key: ImageLoader.pictureKey(fullRequest), anew: again)
            guard !Task.isCancelled else { return }
            put(full: image, about: point)
            return
        }
        var small = ImageLoader.inMemory(for: thumbRequest, maxPixel: Self.thumbPixel)
        let waited = small == nil
        if small == nil {
            small = try? await ImageLoader.shared.image(
                for: thumbRequest, maxPixel: Self.thumbPixel, priority: current ? .high : .normal
            )
        }
        guard !Task.isCancelled else { return }
        if let image = small, UserDefaults.standard.bool(forKey: "galleryStale") { small = Self.narrowed(image) }
        if let image = small {
            let point = await cutPoint(of: image, key: ImageLoader.pictureKey(thumbRequest), anew: again)
            guard !Task.isCancelled else { return }
            if again {
                put(thumb: image, about: point)
            } else {
                // In the grid it is to be there at once, under its tile; over
                // its tile's own picture, too.
                withAnimation(still || thumb != nil || !waited ? nil : .easeOut(duration: 0.3)) { thumb = image }
            }
        }
        guard !Task.isCancelled,
              let image = try? await ImageLoader.shared.image(
                  for: fullRequest, maxPixel: Self.fullPixel, priority: current ? .high : .normal
              ),
              !Task.isCancelled
        else { return }
        guard let under = thumb else {
            _ = await cutPoint(of: image, key: ImageLoader.pictureKey(fullRequest), anew: false)
            guard !Task.isCancelled else { return }
            withAnimation(.easeOut(duration: 0.3)) { full = image }
            return
        }
        guard Self.same(under.size, image.size) else {
            await arrived(image, over: under, key: ImageLoader.pictureKey(fullRequest))
            return
        }
        // Over the thumbnail, gently.
        fullShown = 0
        full = image
        withAnimation(.easeInOut(duration: 0.7)) { fullShown = 1 }
    }

    /// The probe's (`-galleryStale YES`): a thumbnail of another shape than
    /// the full picture, as one kept from before its work was cut down.
    private static func narrowed(_ image: UIImage) -> UIImage {
        guard let whole = image.cgImage else { return image }
        let part = CGRect(
            x: CGFloat(whole.width) * 0.15, y: 0, width: CGFloat(whole.width) * 0.7, height: CGFloat(whole.height)
        ).integral
        guard let cut = whole.cropping(to: part) else { return image }
        return UIImage(cgImage: cut, scale: image.scale, orientation: image.imageOrientation)
    }

    /// Two pictures of one shape: one cut of the work, to be laid out as
    /// one. A thumbnail's sides are whole pixels, no more than that apart.
    static func same(_ one: CGSize, _ other: CGSize) -> Bool {
        guard one.height > 0, other.height > 0 else { return false }
        let ratio = (one.width / one.height) / (other.width / other.height)
        return abs(ratio - 1) < 0.02
    }

    /// The full picture came in another shape than the thumbnail under it:
    /// the thumbnail was of the work before it was cut down (kept from
    /// then, or the cut made between the two). Drawn to the full one's
    /// shape, the work seemed to change its proportions and jump (Mateusz
    /// 2026-11-25). Off the screen the thumbnail simply goes; looked at,
    /// it fades under the new one, each as itself.
    private func arrived(_ image: UIImage, over under: UIImage, key: String) async {
        let point = await SubjectFocus.shared.point(in: image, key: key, subject: true)
        guard !Task.isCancelled else { return }
        GalleryLog.note("page \(work.id): its full picture is of another shape than its thumbnail")
        stock.drop(work.id)
        Glow.forget(work.id)
        // The thumbnails kept of it are of the old picture, here and in
        // the lists; Galeria asks how the work is now (`repictured`).
        model.pictureSeen(work.id, copy: work.item.pictureVersion, changed: true)
        guard current, let was = focus else {
            put(full: image, about: point)
            return
        }
        var quiet = Transaction(animation: nil)
        quiet.disablesAnimations = true
        withTransaction(quiet) {
            stale = (under, was)
            thumb = nil
            focus = point
            fullShown = 0
            full = image
            glow = nil
        }
        stock.focus[work.id] = point
        withAnimation(.easeInOut(duration: 0.7)) { fullShown = 1 }
        try? await Task.sleep(for: .milliseconds(750))
        stale = nil
    }

    /// The page's pictures given way to others at once: the work's
    /// picture as it is now.
    private func put(thumb small: UIImage? = nil, full large: UIImage? = nil, about point: UnitPoint) {
        var quiet = Transaction(animation: nil)
        quiet.disablesAnimations = true
        withTransaction(quiet) {
            stale = nil
            thumb = small
            full = large
            fullShown = 1
            focus = point
            glow = nil
        }
        if stock.focus[work.id] == nil { stock.focus[work.id] = point }
    }

    /// The point a picture is cut around: found once, on whichever picture
    /// comes first, and kept for the other; its tile's, where that was
    /// found meanwhile. `anew`: of the work's new picture, whatever the
    /// page had.
    private func cutPoint(of image: UIImage, key: String, anew: Bool) async -> UnitPoint {
        if !anew, let focus { return focus }
        let found = await SubjectFocus.shared.point(in: image, key: key, subject: true)
        if !anew, let focus { return focus }
        let point = stock.focus[work.id] ?? found
        stock.focus[work.id] = point
        if !anew { focus = point }
        return point
    }

    private func drawBack(_ box: CGSize) async {
        if still {
            // As its tile is cut: the one shown gets there on its way into
            // the tile, the others are there before they are seen.
            if current {
                withAnimation(.easeOut(duration: 0.3)) {
                    zoom = Self.closer
                    pan = 0
                }
            } else {
                rest()
            }
            return
        }
        guard current else {
            // Off the screen by then: closer again for the next time.
            try? await Task.sleep(for: .seconds(1))
            guard !Task.isCancelled else { return }
            rest()
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

    /// Closer and undrifted, at once.
    private func rest() {
        var quiet = Transaction(animation: nil)
        quiet.disablesAnimations = true
        withTransaction(quiet) {
            zoom = Self.closer
            pan = 0
        }
    }

    /// To the whole work and back, for what has no timing of its own; all
    /// of it quick (Mateusz 2026-11-24: "Przejście … szybsze").
    static let toWhole = Animation.easeInOut(duration: 0.25)
    /// Back from it, for the same: as calm as the page's own way (`back`).
    static let fromWhole = Animation.easeInOut(duration: back * 0.8)

    /// How far a work drifts sideways while it draws back (points), at most.
    static let drift: CGFloat = 22
}

/// The work's one picture on its way between the two ways it is seen:
/// cut to the screen (pressed in about the screen's middle) and the whole
/// of it where it lies when held. The draw-back and the drift it is shown
/// with are under this one (`Nearer`), and are left behind by the way's end.
///
/// It grows smaller by the same share with every step of the way, about
/// the screen's middle, and what is left of the way (to the side, when it
/// is cut off its middle; up to its place) is gone evenly beside that.
/// Laid out as a share of the way from the one frame to the other, a work
/// cut far to one side was set straight in the first tenth of a second and
/// only then seen to draw back (Mateusz 2026-11-25 16:10: "„naprostowanie”
/// przy wejściu w całe dzieło odbywa się na początku animacji i nie
/// wygląda to dobrze").
private struct Lens: GeometryEffect {
    /// How small the page pressed is of itself.
    var sink: CGFloat
    /// From the work cut to the screen (0) to the whole of it (1).
    var way: CGFloat
    let layout: Fill
    let place: Whole
    /// The probe's trace of the way is this one's.
    var traced = true

    /// How small the whole work is of the work cut to the screen.
    static func smaller(_ layout: Fill, _ place: Whole) -> CGFloat {
        max(place.size.width / max(layout.size.width, 1), 0.01)
    }

    var animatableData: AnimatablePair<CGFloat, CGFloat> {
        get { AnimatablePair(sink, way) }
        set {
            sink = newValue.first
            way = newValue.second
        }
    }

    /// `size`: the picture's own frame, centred on the page, the picture
    /// drawn `layout.offset` off it.
    func effectValue(size: CGSize) -> ProjectionTransform {
        let middle = CGPoint(x: size.width / 2, y: size.height / 2)
        let cutScale = max(sink, 0.01)
        let cutX = middle.x * (1 - sink)
        let cutY = middle.y * (1 - sink)
        let wholeScale = Self.smaller(layout, place)
        let wholeX = middle.x + place.offset.width - place.size.width / 2 - wholeScale * layout.offset.width
        let wholeY = middle.y + place.offset.height - place.size.height / 2 - wholeScale * layout.offset.height
        // Smaller about the screen's middle, by `share` so far of `all`.
        let all = wholeScale / cutScale
        let share = pow(all, way)
        let scale = cutScale * share
        let x = middle.x * (1 - share) + cutX * share + way * (wholeX - middle.x * (1 - all) - cutX * all)
        let y = middle.y * (1 - share) + cutY * share + way * (wholeY - middle.y * (1 - all) - cutY * all)
        if traced, way > 0.002, way < 0.998, Thread.isMainThread {
            // The probe's: every frame of the way, to be read beside its film.
            let gone = Int((way * 100).rounded()), across = Int((scale * layout.size.width).rounded())
            let lies = Int((x + scale * (layout.offset.width + size.width / 2) - middle.x).rounded())
            MainActor.assumeIsolated {
                GalleryLog.trace("whole work: \(gone)% of the way, \(across) pt across, \(lies) pt off the middle")
            }
        }
        return ProjectionTransform(CGAffineTransform(a: scale, b: 0, c: 0, d: scale, tx: x, ty: y))
    }
}

/// The work shown a little closer, about the point it is cut around, and
/// drifted to one side: its slow draw-back, under `Lens`, and none of it
/// left once the whole work is seen (`fade`).
///
/// An effect of its own, with numbers of its own. As part of `Lens`, the
/// twenty seconds of it were finished in the third of a second a finger
/// takes to press the page in: the press animated all of that effect's
/// numbers to where they were going, these among them, and the work went
/// some twenty points to the side and a twentieth smaller before it set
/// off for the whole of it (Mateusz 2026-11-25 18:08: "Praktycznie przy
/// każdym dziele przy przytrzymaniu palca najpierw szuka środka a potem
/// zmniejsza"; measured on his film, frame by frame). A press changes
/// nothing here, and the draw-back goes on under it as it went.
private struct Nearer: GeometryEffect {
    var zoom: CGFloat
    var pan: CGFloat
    /// 0 all of it … 1 none (the whole work).
    var fade: CGFloat
    let anchor: UnitPoint
    /// The probe's: under a finger, every frame of it.
    var traced = false

    var animatableData: AnimatablePair<AnimatablePair<CGFloat, CGFloat>, CGFloat> {
        get { AnimatablePair(AnimatablePair(zoom, pan), fade) }
        set {
            zoom = newValue.first.first
            pan = newValue.first.second
            fade = newValue.second
        }
    }

    func effectValue(size: CGSize) -> ProjectionTransform {
        let left = 1 - min(max(fade, 0), 1)
        let scale = max(1 + (zoom - 1) * left, 0.01)
        let across = pan * left
        if traced, Thread.isMainThread {
            let closer = String(format: "%.4f", scale), aside = String(format: "%.1f", across)
            MainActor.assumeIsolated {
                GalleryLog.trace("under the finger: \(closer) closer, \(aside) pt aside")
            }
        }
        return ProjectionTransform(CGAffineTransform(
            a: scale, b: 0, c: 0, d: scale,
            tx: anchor.x * size.width * (1 - scale) + across, ty: anchor.y * size.height * (1 - scale)
        ))
    }
}

/// What of the page the work is seen through: all of it, pressed in a
/// little and its corners rounded while a finger lies on it and while the
/// work is held.
private struct Window: Shape {
    var sink: CGFloat
    var corner: CGFloat

    var animatableData: AnimatablePair<CGFloat, CGFloat> {
        get { AnimatablePair(sink, corner) }
        set {
            sink = newValue.first
            corner = newValue.second
        }
    }

    func path(in rect: CGRect) -> Path {
        Path(
            roundedRect: rect.insetBy(dx: rect.width * (1 - sink) / 2, dy: rect.height * (1 - sink) / 2),
            cornerRadius: corner, style: .continuous
        )
    }
}

/// How far the finger that holds a work has been drawn up: the whole work
/// follows a little, and far enough its card comes (`GalleryView.held`).
@MainActor @Observable final class GalleryPull {
    var up: CGFloat = 0

    /// How far the work goes up for a finger drawn `up`.
    nonisolated static func lift(_ up: CGFloat) -> CGFloat { min(max(up, 0), 160) * 0.55 }
}

/// The sign under the whole work that a pull up brings its card: a short
/// bar, which goes up a little now and then (`GalleryPage.nudge`) and is
/// gone by the time the finger has drawn the card out.
private struct CardSign: View {
    let pull: GalleryPull
    let up: Bool
    let light: Bool

    /// From the work's foot down to the bar.
    static let below: CGFloat = 28
    /// How far it goes up, and the card's head after it.
    static let rise: CGFloat = 9
    static let follow: CGFloat = 5

    var body: some View {
        Capsule()
            .fill((light ? Color.black : Color.white).opacity(up ? (light ? 0.5 : 0.75) : (light ? 0.32 : 0.5)))
            .frame(width: 40, height: 5)
            .offset(y: up ? -Self.rise : 0)
            .opacity(1 - min(max(pull.up / GalleryView.cardPull, 0), 1))
            .accessibilityHidden(true)
    }
}

private struct PulledUp: ViewModifier {
    let pull: GalleryPull
    let on: Bool

    func body(content: Content) -> some View {
        content.offset(y: on ? -GalleryPull.lift(pull.up) : 0)
    }
}

/// The whole work while it is held (Mateusz 2026-11-24 18:51): as wide
/// and at most as tall as on its card, so on the way to the card it only
/// rides up to its place there, with room under it for the card's head.
private struct Whole {
    let size: CGSize
    let offset: CGSize

    static let side = Theme.gutter
    static let gap: CGFloat = 12
    /// From the work down to the card's head: as on the card, where the
    /// switch between the work and the frame lies between them.
    static let head: CGFloat = 68
    /// The head's height before it is measured: the museum, one line of
    /// title, the artist.
    static let headGuess: CGFloat = 96
    /// The card's picture is no taller (`PictureBox`).
    static let tallest: CGFloat = 460
    static let foot: CGFloat = 20
    /// Where the work and its head stand in the room they leave: this
    /// share of it above them, the rest below.
    static let lower: CGFloat = 0.45

    init(picture: CGSize, box: CGSize, insets: EdgeInsets, head: CGFloat) {
        let top = max(insets.top, 20) + Self.gap
        let bottom = max(insets.bottom, 20) + Self.foot + head + Self.head
        let free = max(box.height - top - bottom, 1)
        let room = CGSize(width: max(box.width - Self.side * 2, 1), height: min(free, Self.tallest))
        let scale = min(room.width / max(picture.width, 1), room.height / max(picture.height, 1))
        size = CGSize(width: picture.width * scale, height: picture.height * scale)
        let y = top + (free - size.height) * Self.lower
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
    /// How far out `edges` was made (`reach`, or `far`).
    var spread: CGFloat = Glow.reach

    /// How far the edges are drawn out on each side, as a share of the
    /// work's longer side; and their blur, as a share of it too.
    nonisolated static let reach: CGFloat = 0.6
    nonisolated static let softness: CGFloat = 0.12
    /// Behind the work held in Galeria: far out, the screen full of it,
    /// and fading only far from the work (Mateusz 2026-11-24 19:12: "łuna
    /// zdecydowanie szersza, pełniej wypełniająca ekran").
    nonisolated static let far: CGFloat = 1.4
    nonisolated static let farHold: CGFloat = 0.75
    nonisolated(unsafe) private static let context = CIContext(options: [.cacheIntermediates: false])
    /// Made in Galeria, kept for the work's card, which shows the same
    /// glow behind it (Mateusz 2026-11-24 07:36); and the far one, which
    /// the card coming from Galeria lets fade.
    @MainActor static var kept: [String: UIImage] = [:]
    @MainActor static var wide: [String: UIImage] = [:]

    /// The work has another picture: the glows of the old one go.
    @MainActor static func forget(_ id: String) {
        wide[id] = nil
        kept[id] = nil
    }

    @MainActor static func keep(wide far: UIImage?, near: UIImage?, for id: String) {
        if wide.count > 40 { wide.removeAll() }
        if kept.count > 200 { kept.removeAll() }
        if let far { wide[id] = far }
        if let near, kept[id] == nil { kept[id] = near }
    }

    /// The picture with its edges drawn out by `reach` and blurred; the
    /// work itself sits in its middle. It fades out from `hold` of the
    /// way out on.
    nonisolated static func edges(of picture: UIImage, reach: CGFloat = Glow.reach, hold: CGFloat = 0.45) -> UIImage? {
        guard let cg = picture.cgImage else { return nil }
        // Small is enough for a blur this wide.
        let long = CGFloat(max(cg.width, cg.height))
        let scale = min(1, 200 / long)
        // On whole pixels: where the small picture ended within a pixel,
        // its last row was clear, and drawn out it left that whole side
        // (the top of a wide work, the right of a tall one) without glow.
        let extent = CGRect(
            x: 0, y: 0,
            width: max((CGFloat(cg.width) * scale).rounded(.down), 1),
            height: max((CGFloat(cg.height) * scale).rounded(.down), 1)
        )
        let small = CIImage(cgImage: cg)
            .transformed(by: CGAffineTransform(
                scaleX: (extent.width + 0.01) / CGFloat(cg.width), y: (extent.height + 0.01) / CGFloat(cg.height)
            ))
            .cropped(to: extent)
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
            .cropped(to: extent.insetBy(dx: -pad * hold, dy: -pad * hold))
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
        let pad = long * spread
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
/// Nine small white squares in a circle of the heart's clear glass: the
/// grid's button on the page's other corner (Mateusz 2026-11-25 12:21:
/// "Ikonka 9 kwadracików - zamień na w kółku").
private struct GridMark: View {
    /// The circle across, and the nine squares in it (points).
    static let size: CGFloat = 40
    private static let squares: CGFloat = 17

    var body: some View {
        GridShape()
            .fill(.white.opacity(0.94))
            .frame(width: Self.squares, height: Self.squares)
            // Seen on a white sky too.
            .shadow(color: .black.opacity(0.22), radius: 1.5, y: 0.5)
            .frame(width: Self.size, height: Self.size)
            .glassEffect(Glass.clear.interactive(), in: Circle())
            // The same glass in dark mode as in light, as the heart's.
            .environment(\.colorScheme, .light)
    }
}

/// Three rows of three squares, their corners rounded a little.
private struct GridShape: Shape {
    /// The gap between two squares, of a square's side.
    private static let gap: CGFloat = 0.3

    func path(in rect: CGRect) -> Path {
        let columns = CGFloat(GridMetrics.columns)
        let side = min(rect.width, rect.height) / (columns + (columns - 1) * Self.gap)
        let pitch = side * (1 + Self.gap)
        var path = Path()
        for row in 0 ..< GridMetrics.columns {
            for column in 0 ..< GridMetrics.columns {
                let square = CGRect(
                    x: rect.minX + CGFloat(column) * pitch, y: rect.minY + CGFloat(row) * pitch, width: side, height: side
                )
                path.addRoundedRect(in: square, cornerSize: CGSize(width: side * 0.28, height: side * 0.28))
            }
        }
        return path
    }
}

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

/// The work's caption on the cut work: its title and its artist, low on
/// it, on a shade (Mateusz 2026-11-23, variant 2: no card, the text on a
/// shade; 22:08: "bez nazwy muzeum, daty, narodowości i okresu życia").
/// The Polish texts are asked for once the work has stayed a moment.
private struct GalleryCaption: View {
    let work: RemoteItem
    /// Its Polish texts, once the page has them.
    let polish: PolishText?

    private var item: Item { work.item }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(bound: title)
                .font(.serif(26, weight: .semibold))
                .foregroundStyle(Theme.ink)
                .fixedSize(horizontal: false, vertical: true)
                .lineLimit(3)
            if !item.artist.isEmpty {
                Text(bound: Names.artist(item.artist))
                    .font(.serif(19))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
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
            .padding(.bottom, -140)  // to the screen's foot
            .allowsHitTesting(false)
        }
        // Light text on the shade in both modes.
        .environment(\.colorScheme, .dark)
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

/// The head of the work's card, as the card itself shows it while it
/// loads (`ItemDetailView.peekTitle`): the museum, the title with its
/// year, the artist. Under the whole work while it is held: what a pull
/// up brings (Mateusz 2026-11-24 19:12, variant A).
private struct GalleryHead: View {
    let work: RemoteItem
    let polish: PolishText?

    var body: some View {
        let summary = work.summary
        // The museum the work is in; a source that only gathers pictures
        // (Commons) is no museum.
        let held = summary.isOwnWork ? Names.ownCollection(summary.own?.hangs)
            : summary.kind == .artwork ? summary.heldBy ?? Names.source(summary.source)
            : Names.source(summary.source)
        let title = nonEmpty(polish?.title) ?? (summary.shownTitle.isEmpty ? "Bez tytułu" : summary.shownTitle)
        VStack(alignment: .leading, spacing: 6) {
            if !held.isEmpty {
                Eyebrow(held, color: Theme.vermilion)
            }
            TitleWithYear(
                title: title,
                date: summary.kind == .photo ? "" : nonEmpty(polish?.date) ?? summary.dateText,
                font: .serif(30, weight: .semibold),
                lowSide: summary.lowSide,
                restored: summary.restored == true,
                cropped: summary.isCropped,
                cleaned: summary.isCleaned
            )
            .fixedSize(horizontal: false, vertical: true)
            if !summary.artist.isEmpty {
                NameText(text: Names.artist(summary.artist))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
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

