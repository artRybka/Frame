import SwiftUI
import UIKit

/// Galeria drawn back to the works coming, when they are swiped past
/// faster than they can be looked at (Mateusz 2026-11-24 08:52: "A, ale
/// bez tekstu u góry … na pełnym ekranie [siatka z kadrami], na całym
/// dziele raczej jak siatka przy szukaj"): the cut works as small screens,
/// the whole ones as Szukaj's cards. A tap goes back to that work. Above
/// the work shown, the works seen before it (14:26: "fajnie gdyby siatkę
/// dało się 'cofnąć' - pokazać miniatury poprzednio pokazywanych dzieł").
struct GalleryGrid: View {
    /// The works seen before, oldest first, above the line.
    let before: [RemoteItem]
    /// The works from the line on: the work shown among the first.
    let works: [RemoteItem]
    /// Whole works (Szukaj's cards) or cut ones (tiles).
    let whole: Bool
    /// Where each work lies on the screen, for the way back into it. A box,
    /// not state: kept while scrolling without drawing anything again.
    let frames: GridFrames
    /// The thumbnails fetched ahead, held here and not only in the loader's
    /// memory, where the full pictures pushed them out (14:06: "Zapas
    /// miniatur nie działa na siatce pełnego ekranu").
    let stock: GridStock
    /// A tile's height in its widths: the screen's (14:26: "dzieła powinny
    /// być w proporcji ekranu i lekko przybliżone").
    let tall: CGFloat
    /// Set once the grid lies where it is to be: it flows from then on.
    let going: Bool
    /// How fast the works were swiped when the grid came (points a
    /// second; less than 0 back up, into the works seen before): it flows
    /// on as fast and slows as a flicked list does (14:06: "Prędkość
    /// powinna być zgodna z ostatnim machnięciem").
    let speed: CGFloat
    let pick: (RemoteItem) -> Void
    /// Asked for when the grid comes near its end: well ahead (10:48:
    /// "Musi to robić ze zdecydowanie większym zapasem"; 14:06: "Powinien
    /// być też większy - teraz ściana szybko się kończy").
    let more: () -> Void

    @State private var scroll = ScrollPosition(edge: .top)
    @State private var coast = Coast()

    static let columns = 3
    static let gap: CGFloat = 6
    static let top: CGFloat = 8
    /// The whole works' cards: two columns, this far apart (`MasonryGrid`).
    static let cardGap: CGFloat = 16
    /// How near the end more works are asked for (tiles).
    static let ahead = 60
    /// The line between the works seen and those coming.
    static let line = "gallery.grid.line"

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(spacing: 0) {
                    if !before.isEmpty {
                        if whole { seenCards } else { tiles(before, ahead: false) }
                    }
                    Color.clear
                        .frame(height: before.isEmpty ? 0 : (whole ? Self.cardGap : Self.gap))
                        .id(Self.line)
                    if whole { cards } else { tiles(works, ahead: true) }
                }
                .padding(.top, Self.top)
                .padding(.bottom, 24)
            }
            .scrollPosition($scroll)
            .scrollIndicators(.hidden)
            .onScrollGeometryChange(for: CGFloat.self) { $0.contentOffset.y } action: { _, y in
                frames.offset = y
            }
            .onScrollGeometryChange(for: CGFloat.self) { $0.contentSize.height - $0.containerSize.height } action: { _, most in
                frames.most = max(most, 0)
            }
            // A finger on the grid: the flow from the swipe stops.
            .onScrollPhaseChange { _, phase in
                if phase == .interacting { coast.stop() }
            }
            .onAppear {
                var quiet = Transaction(animation: nil)
                quiet.disablesAnimations = true
                withTransaction(quiet) { proxy.scrollTo(Self.line, anchor: .top) }
            }
            .onChange(of: going) { _, now in if now { flowOn() } }
            .onDisappear { coast.stop() }
        }
    }

    /// The flick's slowing: a flicked list's (`UIScrollView`'s usual), so
    /// far as the speed carries it, at least a little.
    static let slowing: CGFloat = 0.5
    static let least: CGFloat = 700
    static let most: CGFloat = 7000

    private func flowOn() {
        let way: CGFloat = speed < 0 ? -1 : 1
        let speed = min(max(abs(speed), Self.least), Self.most) * way
        let slowing = Self.slowing
        let frames = frames
        let from = frames.offset
        coast.run { seconds in
            let t = CGFloat(seconds)
            let y = from + speed * slowing * (1 - exp(-t / slowing))
            scroll.scrollTo(y: min(max(y, 0), frames.most))
            return t < slowing * 6
        }
    }

    /// Small screens, each the screen's shape and cut as the page cuts it,
    /// a little closer (14:26): nothing in them moves once they are laid
    /// out (10:48: "siatka nie może skakać i przeskakiwać - musi być
    /// ułożona"). No outline round the work shown (14:26).
    private func tiles(_ some: [RemoteItem], ahead: Bool) -> some View {
        LazyVGrid(
            columns: Array(repeating: GridItem(.flexible(), spacing: Self.gap), count: Self.columns),
            spacing: Self.gap
        ) {
            ForEach(Array(some.enumerated()), id: \.element.id) { index, work in
                Button { coast.stop(); pick(work) } label: {
                    Color.clear
                        .aspectRatio(1 / tall, contentMode: .fit)
                        .overlay { GridPicture(work: work, stock: stock, screen: true) }
                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                }
                .buttonStyle(.plain)
                .modifier(Placed(id: work.id, frames: frames))
                .onAppear { if ahead, index >= some.count - Self.ahead { more() } }
            }
        }
        .padding(.horizontal, Theme.gutter)
    }

    private var cards: some View {
        let ids = Dictionary(works.enumerated().map { ($1.id, $0) }, uniquingKeysWith: { first, _ in first })
        let byID = Dictionary(works.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        return MasonryGrid(items: works.map(\.summary), spacing: Self.cardGap) { summary in
            if let work = byID[summary.id] {
                card(work)
                    .onAppear { if (ids[summary.id] ?? 0) >= works.count - Self.ahead { more() } }
            }
        }
        .padding(.horizontal, Theme.gutter)
    }

    /// The whole works seen before: laid out at once, not lazily, so the
    /// line under them lies where it is to be from the first frame and
    /// nothing moves above it as they come into view.
    private var seenCards: some View {
        var columns: [[RemoteItem]] = [[], []]
        var heights: [CGFloat] = [0, 0]
        for work in before {
            let side = heights[0] <= heights[1] ? 0 : 1
            columns[side].append(work)
            heights[side] += 1 / Self.cardAspect(work) + 0.3
        }
        return HStack(alignment: .top, spacing: Self.cardGap) {
            ForEach(0 ..< 2, id: \.self) { side in
                VStack(spacing: Self.cardGap) {
                    ForEach(columns[side], id: \.id) { card($0) }
                }
                .frame(maxWidth: .infinity, alignment: .top)
            }
        }
        .padding(.horizontal, Theme.gutter)
    }

    private func card(_ work: RemoteItem) -> some View {
        Button { coast.stop(); pick(work) } label: {
            GridCard(work: work, stock: stock, frames: frames)
        }
        .buttonStyle(.plain)
    }

    /// A whole work's card's picture shape, as `MasonryGrid` gives it.
    static func cardAspect(_ work: RemoteItem) -> CGFloat {
        CGFloat(min(max(work.summary.aspectRatio, 0.45), 2.2))
    }
}

/// A work's thumbnail in the grid: from the stock at once when it was
/// fetched ahead, else fetched now and kept there. As a small screen, cut
/// about the point its page is cut about and a little closer, as the page
/// starts (`Fill`, `GalleryView.closer`).
private struct GridPicture: View {
    @Environment(AppModel.self) private var model
    let work: RemoteItem
    let stock: GridStock
    var screen = false
    @State private var image: UIImage?
    @State private var focus: UnitPoint

    init(work: RemoteItem, stock: GridStock, screen: Bool = false) {
        self.work = work
        self.stock = stock
        self.screen = screen
        _image = State(initialValue: stock.images[work.id])
        _focus = State(initialValue: stock.focus[work.id] ?? .center)
    }

    var body: some View {
        ZStack {
            Rectangle().fill(work.summary.placeholderColor.gradient)
            if let image {
                Group {
                    if screen {
                        GeometryReader { geo in
                            let layout = Fill(picture: image.size, box: geo.size, focus: focus)
                            ZStack {
                                Image(uiImage: image)
                                    .resizable()
                                    .frame(width: layout.size.width, height: layout.size.height)
                                    .offset(layout.offset)
                            }
                            .scaleEffect(GalleryView.closer, anchor: layout.anchor)
                            .frame(width: geo.size.width, height: geo.size.height)
                        }
                    } else {
                        Image(uiImage: image)
                            .resizable()
                            .scaledToFill()
                    }
                }
                .transition(.opacity)
            }
        }
        .task(id: work.id) {
            guard image == nil, let request = model.backend.request(for: .thumb(work.id)) else { return }
            guard let got = try? await ImageLoader.shared.image(for: request, maxPixel: GalleryView.gridPixel) else { return }
            let point = await SubjectFocus.shared.point(in: got, key: ImageLoader.pictureKey(request), subject: true)
            stock.images[work.id] = got
            stock.focus[work.id] = point
            focus = point
            withAnimation(.easeOut(duration: 0.2)) { image = got }
        }
    }
}

/// A whole work as in Szukaj: its picture, its title and artist.
private struct GridCard: View {
    let work: RemoteItem
    let stock: GridStock
    let frames: GridFrames

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Color.clear
                .aspectRatio(GalleryGrid.cardAspect(work), contentMode: .fit)
                .overlay { GridPicture(work: work, stock: stock) }
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                .shadow(color: .black.opacity(0.14), radius: 8, x: 0, y: 5)
                .modifier(Placed(id: work.id, frames: frames))
            VStack(alignment: .leading, spacing: 2) {
                Text(bound: work.summary.shownTitle.isEmpty ? "Bez tytułu" : work.summary.shownTitle)
                    .font(.serif(15, weight: .medium))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(2)
                Text(bound: ArtCard.byline(work.summary))
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .lineLimit(1)
            }
        }
    }
}

/// Where the grid's works lie on the screen, and how far it can scroll.
@MainActor final class GridFrames {
    var frames: [String: CGRect] = [:]
    var most: CGFloat = .infinity
    /// How far it is scrolled now.
    var offset: CGFloat = 0
}

/// The grid's thumbnails, fetched ahead.
@MainActor final class GridStock {
    var images: [String: UIImage] = [:]
    /// The point each is cut about, as its page cuts it.
    var focus: [String: UnitPoint] = [:]

    /// Only these kept: the works about the one shown.
    func keep(_ ids: Set<String>) {
        images = images.filter { ids.contains($0.key) }
        focus = focus.filter { ids.contains($0.key) }
    }
}

/// Keeps where a work lies on the screen.
private struct Placed: ViewModifier {
    let id: String
    let frames: GridFrames

    func body(content: Content) -> some View {
        content.onGeometryChange(for: CGRect.self) { $0.frame(in: .global) } action: { frames.frames[id] = $0 }
    }
}

/// The grid coming out of the work shown and going back into the one
/// picked: grown about that work's tile and moved so the tile lies where
/// the work lay, the same size, so the work seems to shrink into its tile
/// and to grow out of it again (14:06: "w obydwu wypadkach jest skok i
/// przesunięcie dzieła").
struct GridZoom: ViewModifier {
    let scale: CGFloat
    let anchor: UnitPoint
    let shift: CGSize
    let opacity: Double

    func body(content: Content) -> some View {
        content
            .scaleEffect(scale, anchor: anchor)
            .offset(shift)
            .opacity(opacity)
    }
}

/// How fast the pages were last swiped (points a second, down the works),
/// for the grid to flow on as fast (14:06: "Prędkość powinna być zgodna z
/// ostatnim machnięciem").
@MainActor final class SwipeFlow {
    private var samples: [(time: CFTimeInterval, speed: CGFloat)] = []
    private var last: (time: CFTimeInterval, y: CGFloat)?

    func note(_ y: CGFloat) {
        let now = CACurrentMediaTime()
        if let last, now - last.time > 0.001 {
            samples.append((now, (y - last.y) / CGFloat(now - last.time)))
            samples.removeAll { now - $0.time > Self.window }
        }
        last = (now, y)
    }

    /// The fastest of the last moments, down the works (0 the other way).
    var recent: CGFloat {
        let now = CACurrentMediaTime()
        return samples.filter { now - $0.time <= Self.window }.map(\.speed).max().map { max($0, 0) } ?? 0
    }

    private static let window: CFTimeInterval = 0.45
}

/// The grid flowing on after the swipe and slowing as a flicked list does,
/// a step each frame of the screen.
@MainActor final class Coast: NSObject {
    private var link: CADisplayLink?
    private var start: CFTimeInterval = 0
    private var step: ((CFTimeInterval) -> Bool)?

    /// `step` is given the seconds since the start; false ends it.
    func run(_ step: @escaping (CFTimeInterval) -> Bool) {
        stop()
        self.step = step
        start = CACurrentMediaTime()
        let link = CADisplayLink(target: self, selector: #selector(tick))
        link.preferredFrameRateRange = CAFrameRateRange(minimum: 60, maximum: 120, preferred: 120)
        link.add(to: .main, forMode: .common)
        self.link = link
    }

    func stop() {
        link?.invalidate()
        link = nil
        step = nil
    }

    @objc private func tick(_ link: CADisplayLink) {
        guard let step, step(link.targetTimestamp - start) else {
            stop()
            return
        }
    }
}

/// Telling swiping past from looking: so many works in a row, each left
/// this soon (Mateusz 2026-11-24 08:30: "nie pojedyncze dzieło tylko
/// serię"). Four works, each left within a second and a half: no work is
/// looked at that soon (12:06: "dzieła nie da się obejrzeć w 0,8 sekundy",
/// six under 0.8 s was too slow to come).
struct SwipeSpeed {
    static let run = 4
    static let quick: TimeInterval = 1.5

    private var times: [Date] = []

    /// A work reached; true when the run is quick enough for the grid.
    mutating func reached(at now: Date = .now) -> Bool {
        times.append(now)
        if times.count > Self.run { times.removeFirst(times.count - Self.run) }
        guard times.count == Self.run else { return false }
        return zip(times, times.dropFirst()).allSatisfy { $1.timeIntervalSince($0) < Self.quick }
    }

    mutating func reset() { times = [] }
}

/// A swipe from left to right, told apart from the scroll at once and
/// never in its way (14:06: "Bywa ze zarówno na pełnym ekranie jak i całym
/// dziele nie łapie machnięcia palca": SwiftUI's own drag and hold on the
/// pages held the scroll back now and then).
struct SideSwipe: UIGestureRecognizerRepresentable {
    /// Only from the screen's left edge (the card's way back).
    var fromEdge = false
    let action: () -> Void

    func makeCoordinator(converter: CoordinateSpaceConverter) -> Coordinator {
        Coordinator(fromEdge: fromEdge)
    }

    func makeUIGestureRecognizer(context: Context) -> UIPanGestureRecognizer {
        let pan = UIPanGestureRecognizer()
        pan.delegate = context.coordinator
        pan.cancelsTouchesInView = false
        return pan
    }

    func handleUIGestureRecognizerAction(_ recognizer: UIPanGestureRecognizer, context: Context) {
        guard recognizer.state == .ended else { return }
        let move = recognizer.translation(in: recognizer.view)
        let speed = recognizer.velocity(in: recognizer.view)
        guard move.x > 50 || speed.x > 500, move.x > abs(move.y) * 1.5 else { return }
        action()
    }

    @MainActor final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        let fromEdge: Bool
        /// When the drag began (`SideDrag`).
        var began: CFTimeInterval = 0

        init(fromEdge: Bool) { self.fromEdge = fromEdge }

        func gestureRecognizerShouldBegin(_ recognizer: UIGestureRecognizer) -> Bool {
            guard let pan = recognizer as? UIPanGestureRecognizer else { return false }
            let speed = pan.velocity(in: pan.view)
            if fromEdge {
                let start = pan.location(in: pan.view).x - pan.translation(in: pan.view).x
                if start > 44 { return false }
            }
            return speed.x > 0 && speed.x > abs(speed.y) * 1.5
        }

        func gestureRecognizer(
            _ recognizer: UIGestureRecognizer, shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer
        ) -> Bool { true }
    }
}

/// A drag from left to right, beside the scroll: told as it goes, and
/// how far, how fast and how long once let go (a short swipe shows the
/// whole work, a long drag the grid of the works seen; 14:26).
struct SideDrag: UIGestureRecognizerRepresentable {
    let changed: (CGFloat) -> Void
    let ended: (_ move: CGFloat, _ speed: CGFloat, _ seconds: Double) -> Void

    func makeCoordinator(converter: CoordinateSpaceConverter) -> SideSwipe.Coordinator {
        SideSwipe.Coordinator(fromEdge: false)
    }

    func makeUIGestureRecognizer(context: Context) -> UIPanGestureRecognizer {
        let pan = UIPanGestureRecognizer()
        pan.delegate = context.coordinator
        pan.cancelsTouchesInView = false
        return pan
    }

    func handleUIGestureRecognizerAction(_ recognizer: UIPanGestureRecognizer, context: Context) {
        let move = recognizer.translation(in: recognizer.view).x
        switch recognizer.state {
        case .began:
            context.coordinator.began = CACurrentMediaTime()
        case .changed:
            changed(move)
        case .ended:
            ended(move, recognizer.velocity(in: recognizer.view).x, CACurrentMediaTime() - context.coordinator.began)
        case .cancelled, .failed:
            ended(0, 0, 0)
        default:
            break
        }
    }
}

/// A hold, beside the scroll: a finger that moves is a scroll, not a hold.
struct Hold: UIGestureRecognizerRepresentable {
    let action: () -> Void

    func makeCoordinator(converter: CoordinateSpaceConverter) -> Coordinator { Coordinator() }

    func makeUIGestureRecognizer(context: Context) -> UILongPressGestureRecognizer {
        let hold = UILongPressGestureRecognizer()
        hold.minimumPressDuration = 0.35
        hold.allowableMovement = 10
        hold.cancelsTouchesInView = false
        hold.delegate = context.coordinator
        return hold
    }

    func handleUIGestureRecognizerAction(_ recognizer: UILongPressGestureRecognizer, context: Context) {
        if recognizer.state == .began { action() }
    }

    @MainActor final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        func gestureRecognizer(
            _ recognizer: UIGestureRecognizer, shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer
        ) -> Bool { true }
    }
}
