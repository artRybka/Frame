import SwiftUI

/// Galeria drawn back to the works coming, when they are swiped past
/// faster than they can be looked at (Mateusz 2026-11-24 08:52: "A, ale
/// bez tekstu u góry … na pełnym ekranie [siatka z kadrami], na całym
/// dziele raczej jak siatka przy szukaj"): the cut works as close tiles,
/// the whole ones as Szukaj's cards. A tap goes back to that work.
struct GalleryGrid: View {
    let works: [RemoteItem]
    /// The work shown when the grid came: outlined.
    let from: String?
    /// Whole works (Szukaj's cards) or cut ones (tiles).
    let whole: Bool
    /// Where each work lies on the screen, for the way back into it. A box,
    /// not state: kept while scrolling without drawing anything again.
    let frames: GridFrames
    @Binding var scroll: ScrollPosition
    let pick: (RemoteItem) -> Void
    /// Asked for when the grid comes near its end: well ahead (10:48:
    /// "Musi to robić ze zdecydowanie większym zapasem").
    let more: () -> Void

    static let columns = 3
    static let gap: CGFloat = 6
    /// A tile's height in its widths.
    static let tall: CGFloat = 1.3
    static let top: CGFloat = 8
    /// How near the end more works are asked for (tiles).
    static let ahead = 24

    var body: some View {
        ScrollView {
            Group {
                if whole { cards } else { tiles }
            }
            .padding(.top, Self.top)
            .padding(.bottom, 24)
        }
        .scrollPosition($scroll)
        .scrollIndicators(.hidden)
    }

    /// Plain tiles, each its fixed shape and cut about the middle: nothing
    /// in them moves once they are laid out (10:48: "siatka nie może skakać
    /// i przeskakiwać - musi być ułożona").
    private var tiles: some View {
        LazyVGrid(
            columns: Array(repeating: GridItem(.flexible(), spacing: Self.gap), count: Self.columns),
            spacing: Self.gap
        ) {
            ForEach(Array(works.enumerated()), id: \.element.id) { index, work in
                Button { pick(work) } label: {
                    Color.clear
                        .aspectRatio(1 / Self.tall, contentMode: .fit)
                        .overlay {
                            ArtImage(
                                ref: .thumb(work.id), placeholder: work.summary.placeholderColor,
                                maxPixel: GalleryView.gridPixel
                            )
                        }
                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                        .overlay {
                            if work.id == from {
                                RoundedRectangle(cornerRadius: 8, style: .continuous)
                                    .strokeBorder(Theme.paper, lineWidth: 2)
                                    .padding(-3)
                            }
                        }
                }
                .buttonStyle(.plain)
                .modifier(Placed(id: work.id, frames: frames))
                .onAppear { if index >= works.count - Self.ahead { more() } }
            }
        }
        .padding(.horizontal, Theme.gutter)
    }

    private var cards: some View {
        let ids = Dictionary(works.enumerated().map { ($1.id, $0) }, uniquingKeysWith: { first, _ in first })
        return MasonryGrid(items: works.map(\.summary)) { summary in
            Button {
                if let work = works.first(where: { $0.id == summary.id }) { pick(work) }
            } label: {
                ArtCard(item: summary, ref: .thumb(summary.id), showsFavorite: false)
            }
            .buttonStyle(.plain)
            .modifier(Placed(id: summary.id, frames: frames))
            .onAppear { if (ids[summary.id] ?? 0) >= works.count - Self.ahead { more() } }
        }
        .padding(.horizontal, Theme.gutter)
    }
}

/// Where the grid's works lie on the screen.
@MainActor final class GridFrames {
    var frames: [String: CGRect] = [:]
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
/// picked: grown about that work's place, so the work seems to shrink into
/// its tile and to grow out of it again.
struct GridZoom: ViewModifier {
    let scale: CGFloat
    let anchor: UnitPoint
    let opacity: Double

    func body(content: Content) -> some View {
        content
            .scaleEffect(scale, anchor: anchor)
            .opacity(opacity)
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
