import SwiftUI
import UIKit

/// Galeria's other view (Mateusz 2026-11-24 18:31: "przejście w siatkę z
/// pełnego ekranu niech będzie siatką miniatur"): the works as small
/// screens, three to a row from edge to edge, the works seen above the
/// one shown and the works coming below it. A tap goes into that work.
///
/// Every tile lies where `GridMetrics` says, to the pixel, and only the
/// rows about the screen are there at all: the way between a page and its
/// tile is reckoned, not measured (10:48: "siatka nie może skakać i
/// przeskakiwać - musi być ułożona"). It is laid out for some rows above
/// the screen's top too (`GridMetrics.rowsAbove`).
struct GalleryGrid: View {
    /// Empty cells before the first work: the work shown lies in the
    /// middle column.
    let lead: Int
    let works: [RemoteItem]
    let metrics: GridMetrics
    /// How far it is scrolled when it comes.
    let start: CGFloat
    /// The thumbnails fetched ahead, held here and not only in the loader's
    /// memory, where the full pictures pushed them out (14:06: "Zapas
    /// miniatur nie działa na siatce pełnego ekranu").
    let stock: GridStock
    let track: GridTrack
    /// Fingers spread on a tile: no scrolling meanwhile.
    let locked: Bool
    let pick: (RemoteItem) -> Void
    /// Asked for when the grid comes near its end: well ahead (10:48:
    /// "Musi to robić ze zdecydowanie większym zapasem").
    let more: () -> Void

    @State private var scroll = ScrollPosition(edge: .top)
    /// The row at the screen's top.
    @State private var row: Int
    /// Scrolled to `start`: shown from then on.
    @State private var set = false

    /// Places past the last work come, while the next are on their way.
    static let waiting = 24
    /// How near the end more works are asked for.
    static let ahead = 80
    /// Room under the last row, for the tab bar.
    static let foot: CGFloat = 140

    init(
        lead: Int, works: [RemoteItem], metrics: GridMetrics, start: CGFloat, stock: GridStock, track: GridTrack,
        locked: Bool, pick: @escaping (RemoteItem) -> Void, more: @escaping () -> Void
    ) {
        self.lead = lead
        self.works = works
        self.metrics = metrics
        self.start = start
        self.stock = stock
        self.track = track
        self.locked = locked
        self.pick = pick
        self.more = more
        _row = State(initialValue: Int(max(start, 0) / max(metrics.pitch, 1)))
    }

    private struct Cell: Identifiable {
        let id: String
        let n: Int
        let work: RemoteItem?
    }

    private var cells: Int { lead + works.count + Self.waiting }

    /// The cells of the rows about the screen.
    private var shown: [Cell] {
        let columns = GridMetrics.columns
        let below = Int((metrics.area.height / max(metrics.pitch, 1)).rounded(.up)) + 1
        let first = max(row - GridMetrics.rowsAbove - 1, 0) * columns
        let last = min((row + below + 1) * columns, cells)
        guard first < last else { return [] }
        return (first ..< last).map { n in
            let at = n - lead
            if at >= 0, at < works.count { return Cell(id: works[at].id, n: n, work: works[at]) }
            return Cell(id: at < 0 ? "lead.\(n)" : "waiting.\(at - works.count)", n: n, work: nil)
        }
    }

    var body: some View {
        let above = metrics.above
        let rows = (cells + GridMetrics.columns - 1) / GridMetrics.columns
        ScrollView {
            ZStack(alignment: .topLeading) {
                ForEach(shown) { cell in tile(cell) }
            }
            .frame(
                width: metrics.area.width, height: above + CGFloat(rows) * metrics.pitch + Self.foot,
                alignment: .topLeading
            )
        }
        .scrollPosition($scroll)
        .scrollIndicators(.hidden)
        .scrollDisabled(locked)
        .onScrollGeometryChange(for: CGFloat.self) { $0.contentOffset.y } action: { _, y in
            track.offset = y
            if !set, abs(y - start) < 1 {
                set = true
                track.ready = true
            }
        }
        .onScrollGeometryChange(for: Int.self) { Int(max($0.contentOffset.y, 0) / max(metrics.pitch, 1)) } action: { _, now in
            row = now
            if (now + 6) * GridMetrics.columns >= lead + works.count - Self.ahead { more() }
        }
        .onScrollGeometryChange(for: CGFloat.self) { $0.contentSize.height - $0.containerSize.height } action: { _, most in
            track.most = max(most, 0)
        }
        // A finger on the grid: the flow from the swipe stops.
        .onScrollPhaseChange { _, phase in
            if phase == .interacting { track.touched?() }
        }
        .onAppear {
            track.scroll = { y in scroll.scrollTo(y: y) }
            var quiet = Transaction(animation: nil)
            quiet.disablesAnimations = true
            withTransaction(quiet) { scroll.scrollTo(y: start) }
            if start < 1 {
                set = true
                track.ready = true
            }
            if works.count < Self.ahead { more() }
        }
        .onDisappear { track.scroll = nil }
        .task {
            // Shown whatever comes of the scroll to `start`.
            try? await Task.sleep(for: .milliseconds(300))
            guard !set else { return }
            GalleryLog.note("grid never reached \(Int(start)), at \(Int(track.offset))")
            set = true
            track.ready = true
        }
        .opacity(set ? 1 : 0)
        // Laid out for the rows above the screen's top as well.
        .padding(.top, -above)
    }

    /// A small screen, cut as the page cuts it; past the last work, a
    /// place in the last works' colours, not the black (14:32:
    /// "placeholdery w kolorze kolejnych miniatur").
    @ViewBuilder
    private func tile(_ cell: Cell) -> some View {
        let rect = metrics.cell(cell.n)
        Group {
            if let work = cell.work {
                Button {
                    track.touched?()
                    pick(work)
                } label: {
                    GridPicture(work: work, stock: stock)
                        .frame(width: rect.width, height: rect.height)
                        .clipped()
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(work.item.displayTitle)
            } else if cell.n >= lead {
                Rectangle().fill(waitingColour(cell.n).gradient)
            } else {
                Color.clear
            }
        }
        .frame(width: rect.width, height: rect.height)
        .offset(x: rect.minX, y: metrics.above + rect.minY)
    }

    private func waitingColour(_ index: Int) -> Color {
        let colours = works.suffix(12).flatMap { $0.item.colors.prefix(2) }.compactMap { Color(hexString: $0.hex) }
        guard !colours.isEmpty else { return Theme.mat.opacity(0.55) }
        return colours[(index * 7) % colours.count].opacity(0.55)
    }
}

/// A work's thumbnail in the grid: from the stock at once when it was
/// fetched ahead, else fetched now and kept there. Cut about the point its
/// page is cut about and a little closer, as the page starts (`Fill`,
/// `GalleryView.closer`): the tile is its page, small.
private struct GridPicture: View {
    @Environment(AppModel.self) private var model
    let work: RemoteItem
    let stock: GridStock
    @State private var image: UIImage?
    @State private var focus: UnitPoint

    init(work: RemoteItem, stock: GridStock) {
        self.work = work
        self.stock = stock
        _image = State(initialValue: stock.images[work.id])
        _focus = State(initialValue: stock.focus[work.id] ?? .center)
    }

    var body: some View {
        ZStack {
            Rectangle().fill(work.summary.placeholderColor.gradient)
            if let image {
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
                .transition(.opacity)
            }
        }
        .task(id: work.id) {
            guard image == nil, let request = model.backend.request(for: .thumb(work.id)) else { return }
            // Asked again when it does not come: a tile left empty stayed
            // so for as long as it was on the screen.
            var loaded: UIImage?
            let asked = ContinuousClock.now
            for attempt in 0 ..< 3 where loaded == nil && !Task.isCancelled {
                if attempt > 0 { try? await Task.sleep(for: .seconds(Double(attempt) * 1.5)) }
                do {
                    loaded = try await ImageLoader.shared.image(for: request, maxPixel: GalleryView.gridPixel)
                } catch {
                    if !Task.isCancelled { GalleryLog.note("tile \(work.id): no picture, \(error)") }
                }
            }
            guard let got = loaded, !Task.isCancelled else { return }
            let waited = (ContinuousClock.now - asked) / .seconds(1)
            if waited > 2 { GalleryLog.note("tile \(work.id): its picture after \(Int(waited)) s") }
            let point = await SubjectFocus.shared.point(in: got, key: ImageLoader.pictureKey(request), subject: true)
            stock.images[work.id] = got
            stock.focus[work.id] = point
            focus = point
            withAnimation(.easeOut(duration: 0.2)) { image = got }
        }
    }
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

/// How far the grid is scrolled and can be, and the way to scroll it:
/// kept beside it without drawing anything again.
@MainActor final class GridTrack {
    var offset: CGFloat = 0
    var most: CGFloat = .infinity
    /// It lies where it was to come.
    var ready = false
    var scroll: ((CGFloat) -> Void)?
    /// A finger on it.
    var touched: (() -> Void)?
}
