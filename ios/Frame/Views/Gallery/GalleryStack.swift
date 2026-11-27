import SwiftUI

/// Galeria's works lie as a stack of cards: the one shown ends a little
/// above the screen's foot, its bottom corners round, a faint light line on
/// its edge, and the next work's edge lies under it, dark and blurred
/// (Mateusz 2026-11-27, variant A5 of the sketches: Galeria's whole screen
/// and a work's full screen from its card looked the same, so a finger
/// tried to look about the work sideways in Galeria; "jasna linia cienka
/// jak w A3a, ale mniej intensywna i zanikająca gradientem ku górze …
/// Cień i plama pod spodem jak w A3c", no nudge on entering).
struct StackedPage: ViewModifier {
    /// Cut as a card: not under the grid, nor with the whole work held,
    /// where the page is to be the screen as its tile and its whole are.
    var on: Bool
    /// The work under this one.
    var under: RemoteItem?
    /// The work under it shows: this page is shown and still.
    var showsUnder: Bool

    /// How much of the screen's height the next work's edge takes (points;
    /// 2% of a 874-point screen, Mateusz 12:55: "może wystarczy 3%").
    static let peek: CGFloat = 17
    /// How far in from the screen's sides the work under lies.
    static let underInset: CGFloat = 18
    /// The light line's white at its brightest, on the card's foot.
    static let edge: Double = 0.27
    /// How far up the card's sides the line goes before it is gone.
    static let edgeRise: CGFloat = 87

    func body(content: Content) -> some View {
        GeometryReader { geo in
            let screen = ScreenCorner.radius(of: geo.size)
            let corner = max(screen - Self.peek, 20)
            let cut = on ? Self.peek : 0
            ZStack(alignment: .top) {
                Color.black
                if let under, on, showsUnder {
                    UnderCard(work: under, corner: max(screen - Self.underInset, 20), cardCorner: corner)
                        .padding(.horizontal, Self.underInset)
                        .transition(.opacity)
                }
                content
                    .mask(alignment: .top) {
                        UnevenRoundedRectangle(
                            bottomLeadingRadius: on ? corner : 0, bottomTrailingRadius: on ? corner : 0,
                            style: .continuous
                        )
                        .frame(height: geo.size.height - cut)
                    }
                if on {
                    UnevenRoundedRectangle(bottomLeadingRadius: corner, bottomTrailingRadius: corner, style: .continuous)
                        .strokeBorder(line(height: geo.size.height - cut), lineWidth: 1)
                        .frame(height: geo.size.height - cut)
                        .allowsHitTesting(false)
                        .transition(.opacity)
                }
            }
            .frame(width: geo.size.width, height: geo.size.height, alignment: .top)
        }
        .animation(.easeInOut(duration: 0.25), value: on)
        .animation(.easeInOut(duration: 0.25), value: showsUnder)
    }

    /// Brightest on the card's foot, gone `edgeRise` up its sides.
    private func line(height: CGFloat) -> LinearGradient {
        let from = 1 - min(Self.edgeRise / max(height, 1), 1)
        return LinearGradient(
            stops: [
                .init(color: .white.opacity(0), location: from),
                .init(color: .white.opacity(Self.edge * 0.33), location: from + (1 - from) * 0.5),
                .init(color: .white.opacity(Self.edge), location: 1),
            ],
            startPoint: .top, endPoint: .bottom
        )
    }
}

/// The next work under the one shown: its thumbnail blurred and darkened
/// to a patch of its colours, the card above casting its shadow on it.
private struct UnderCard: View {
    @Environment(AppModel.self) private var model
    let work: RemoteItem
    let corner: CGFloat
    let cardCorner: CGFloat
    @State private var picture: UIImage?

    /// As a page's thumbnail (`GalleryPage.thumbPixel`): the one the page
    /// below has asked for already.
    private static let pixel: CGFloat = 900

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .top) {
                Group {
                    if let picture {
                        Image(uiImage: picture)
                            .resizable()
                            .scaledToFill()
                            .frame(width: geo.size.width, height: geo.size.height)
                            .blur(radius: 9, opaque: true)
                    } else {
                        Color(white: 0.12)
                    }
                }
                .overlay(Color.black.opacity(0.65))
                // The card above's shadow on it.
                UnevenRoundedRectangle(
                    bottomLeadingRadius: cardCorner, bottomTrailingRadius: cardCorner, style: .continuous
                )
                .fill(.black.opacity(0.8))
                .frame(width: geo.size.width + 2 * StackedPage.underInset,
                       height: geo.size.height - StackedPage.peek)
                .offset(y: 5)
                .blur(radius: 5)
            }
            .frame(width: geo.size.width, height: geo.size.height)
            .clipShape(UnevenRoundedRectangle(
                bottomLeadingRadius: corner, bottomTrailingRadius: corner, style: .continuous
            ))
        }
        .allowsHitTesting(false)
        .task(id: work.id) {
            guard let request = GalleryView.thumb(of: work.item, model.backend) else { return }
            if let kept = ImageLoader.inMemory(for: request, maxPixel: Self.pixel) {
                picture = kept
                return
            }
            let loaded = try? await ImageLoader.shared.image(for: request, maxPixel: Self.pixel)
            guard !Task.isCancelled, let loaded else { return }
            withAnimation(.easeOut(duration: 0.3)) { picture = loaded }
        }
    }
}
