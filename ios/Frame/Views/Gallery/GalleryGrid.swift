import SwiftUI

/// Galeria drawn back to the works coming, when they are swiped past
/// faster than they can be looked at (Mateusz 2026-11-24 08:52: "A, ale
/// bez tekstu u góry … na pełnym ekranie [siatka z kadrami], na całym
/// dziele raczej jak siatka przy szukaj"): the cut works as close tiles,
/// the whole ones as Szukaj's cards. A tap goes back to that work.
struct GalleryGrid: View {
    let works: [RemoteItem]
    /// The work shown when the grid came: first, outlined.
    let from: String?
    /// Whole works (Szukaj's cards) or cut ones (tiles).
    let whole: Bool
    /// Where each work lies on the screen, for the way back into it.
    @Binding var frames: [String: CGRect]
    let pick: (RemoteItem) -> Void
    let more: () -> Void

    static let columns = 3
    static let gap: CGFloat = 6
    /// A tile's height in its widths.
    static let tall: CGFloat = 1.3

    var body: some View {
        ScrollView {
            Group {
                if whole { cards } else { tiles }
            }
            .padding(.top, 8)
            .padding(.bottom, 24)
        }
        .scrollIndicators(.hidden)
    }

    private var tiles: some View {
        LazyVGrid(
            columns: Array(repeating: GridItem(.flexible(), spacing: Self.gap), count: Self.columns),
            spacing: Self.gap
        ) {
            ForEach(works) { work in
                Button { pick(work) } label: {
                    Color.clear
                        .aspectRatio(1 / Self.tall, contentMode: .fit)
                        .overlay {
                            ArtImage(
                                ref: .thumb(work.id), placeholder: work.summary.placeholderColor,
                                maxPixel: 500, subjectFocus: true
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
                .modifier(Placed(id: work.id, frames: $frames))
                .onAppear { if work.id == works.last?.id { more() } }
            }
        }
        .padding(.horizontal, Theme.gutter)
        .background(Color.black)
    }

    private var cards: some View {
        MasonryGrid(items: works.map(\.summary)) { summary in
            Button {
                if let work = works.first(where: { $0.id == summary.id }) { pick(work) }
            } label: {
                ArtCard(item: summary, ref: .thumb(summary.id), showsFavorite: false)
            }
            .buttonStyle(.plain)
            .modifier(Placed(id: summary.id, frames: $frames))
            .onAppear { if summary.id == works.last?.id { more() } }
        }
        .padding(.horizontal, Theme.gutter)
    }
}

/// Keeps where a work lies on the screen.
private struct Placed: ViewModifier {
    let id: String
    @Binding var frames: [String: CGRect]

    func body(content: Content) -> some View {
        content.onGeometryChange(for: CGRect.self) { $0.frame(in: .global) } action: { frames[id] = $0 }
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
/// serię").
struct SwipeSpeed {
    static let run = 6
    static let quick: TimeInterval = 0.8

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
