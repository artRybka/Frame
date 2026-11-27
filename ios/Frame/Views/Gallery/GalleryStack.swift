import SwiftUI

/// Galeria's works lie as a stack of cards: the one shown ends a little
/// above the screen's foot, its bottom corners round, a faint light line on
/// its edge, and the next work's edge lies under it, dark (Mateusz
/// 2026-11-27, variant A5 of the sketches: Galeria's whole screen and a
/// work's full screen from its card looked the same, so a finger tried to
/// look about the work sideways in Galeria; "jasna linia cienka jak w A3a,
/// ale mniej intensywna i zanikająca gradientem ku górze … Cień i plama pod
/// spodem jak w A3c", no nudge on entering).
///
/// The stack is the pages themselves (16:36: "animacja przy przeciąganiu …
/// To chyba powinna być animacja stosu?"; "Kolejne dzieło przy odsłanianiu
/// nie może być rozmyte"): a page below the one shown does not come up from
/// the screen's foot but lies where it is, under it (`GalleryView` lays
/// the pages over one another, the first on top), a little narrower and
/// dark, and comes to the whole screen, sharp all the way, as the card
/// over it is taken off upwards. Back, the card above comes down over the
/// one shown, which goes under the same way.
struct StackedPage: ViewModifier {
    /// Cut as a card: not under the grid, nor with the whole work held,
    /// where the page is to be the screen as its tile and its whole are.
    var on: Bool
    /// Lying on the stack: a page below the screen's top lies under the
    /// one shown (not under the grid, where pages lie as tiles).
    var stacked: Bool
    /// Pressed: the card goes in by itself (`GalleryPage.pressedIn`), its
    /// line with it.
    var pressed: Bool
    /// Pressed or held: what lies round the card, the next work's edge
    /// under it too, is the page's glow (Mateusz 2026-11-27 18:47: "całe
    /// dzieło na froncie powinno się zmniejszać (wraz z krawędzią
    /// pseudo-ekranu) a pod spodem widoczny kawałek dzieła zalewać się
    /// łuną"), and stays so till the work let go has come back as the card.
    var held: Bool
    /// The card over this one is pressed or held: this one's edge under it
    /// is gone, not drawn in with it (16:36: "Wciśnięcie powinno dotyczyć
    /// tego co widać, a dolną część zanikać a nie jak teraz się skalować").
    var hidden: Bool

    /// How much of the screen's height the next work's edge takes (points;
    /// 2% of a 874-point screen, Mateusz 12:55: "może wystarczy 3%").
    nonisolated static let peek: CGFloat = 17
    /// How far in from the screen's sides the work under lies.
    nonisolated static let underInset: CGFloat = 18
    /// The light line's white at its brightest, on the card's foot.
    nonisolated static let edge: Double = 0.27
    /// How far up the card's sides the line goes before it is gone.
    nonisolated static let edgeRise: CGFloat = 87
    /// How dark the work under is.
    nonisolated static let dark: Double = 0.65
    /// How far in the card pressed goes, all round (`GalleryPage`'s).
    nonisolated static let pressedInset: CGFloat = 12

    /// The foot of the screen is the page's (its glow), not the next
    /// work's: from the press, and after the whole work is let go till it
    /// is the card again. The card itself is cut as soon as it is one
    /// (18:47: "Przy powrocie z całego dzieła do pełnego ekranu też pasek
    /// u dołu powinien być od razu"; before, the cut waited 0.55 s).
    @State private var flooded = false
    @State private var wasWhole = false

    func body(content: Content) -> some View {
        let card = on
        let foot = card ? Self.peek : 0
        let stacks = stacked
        let flood = flooded
        // The page, and over it its shade and its line: each laid on the
        // stack by itself (`lies`), so each knows how far down it lies.
        // Measured inside the page moved, the shade read where the page was
        // drawn, near the top, and the work under was hardly dark (the
        // film of run 4: the edge at 80% of its brightness, not 35%).
        return ZStack(alignment: .top) {
            GeometryReader { geo in
                let corner = Self.corner(geo.size)
                let tall = geo.size.height - foot
                ZStack(alignment: .top) {
                    // Its shadow on the card under it.
                    if card {
                        UnevenRoundedRectangle(bottomLeadingRadius: corner, bottomTrailingRadius: corner, style: .continuous)
                            .fill(.black.opacity(0.8))
                            .frame(height: tall)
                            .offset(y: 5)
                            .blur(radius: 5)
                            .opacity(flood ? 0 : 1)
                            .allowsHitTesting(false)
                            .transition(.opacity)
                    }
                    content
                        .mask(alignment: .top) {
                            ZStack(alignment: .top) {
                                UnevenRoundedRectangle(
                                    bottomLeadingRadius: card ? corner : 0, bottomTrailingRadius: card ? corner : 0,
                                    style: .continuous
                                )
                                .frame(height: tall)
                                // The screen's foot, its glow coming over
                                // the next work's edge.
                                Rectangle().opacity(flood ? 1 : 0)
                            }
                        }
                }
                .frame(width: geo.size.width, height: geo.size.height, alignment: .top)
            }
            .visualEffect { content, proxy in
                let lies = stacks ? Self.lies(proxy, foot: foot) : (scale: CGFloat(1), y: CGFloat(0))
                return content.scaleEffect(lies.scale, anchor: .top).offset(y: lies.y)
            }
            // Dark as it lies under the card shown, itself once it is the
            // screen.
            GeometryReader { geo in
                let corner = Self.corner(geo.size)
                UnevenRoundedRectangle(
                    bottomLeadingRadius: card ? corner : 0, bottomTrailingRadius: card ? corner : 0,
                    style: .continuous
                )
                .fill(.black)
                .frame(height: geo.size.height - foot)
                .frame(width: geo.size.width, height: geo.size.height, alignment: .top)
            }
            .visualEffect { content, proxy in
                let lies = stacks ? Self.lies(proxy, foot: foot) : (scale: CGFloat(1), y: CGFloat(0))
                return content
                    .scaleEffect(lies.scale, anchor: .top).offset(y: lies.y)
                    .opacity(stacks ? Self.dark * Self.under(proxy) : 0)
            }
            .allowsHitTesting(false)
            // The light line, only on the card on top.
            if card {
                GeometryReader { geo in
                    // Pressed, in with the card's window, all round
                    // (`GalleryPage.pressedInset`).
                    let inset = pressed ? Self.pressedInset : 0
                    let tall = geo.size.height - foot - 2 * inset
                    let corner = max(Self.corner(geo.size) - inset, 8)
                    UnevenRoundedRectangle(bottomLeadingRadius: corner, bottomTrailingRadius: corner, style: .continuous)
                        .strokeBorder(line(height: tall), lineWidth: 1)
                        .frame(width: geo.size.width - 2 * inset, height: tall)
                        .offset(x: inset, y: inset)
                        .frame(width: geo.size.width, height: geo.size.height, alignment: .topLeading)
                }
                .visualEffect { content, proxy in
                    let lies = stacks ? Self.lies(proxy, foot: foot) : (scale: CGFloat(1), y: CGFloat(0))
                    return content
                        .scaleEffect(lies.scale, anchor: .top).offset(y: lies.y)
                        .opacity(1 - Self.under(proxy))
                }
                .allowsHitTesting(false)
                .transition(.opacity)
            }
        }
        .opacity(hidden ? 0 : 1)
        .animation(.easeInOut(duration: HoldPull.press), value: pressed)
        .animation(.easeInOut(duration: HoldPull.press), value: hidden)
        .animation(.easeInOut(duration: 0.25), value: card)
        .onChange(of: on) { _, now in if !now, held { wasWhole = true } }
        .task(id: held) {
            if held {
                withAnimation(.easeInOut(duration: HoldPull.press)) { flooded = true }
                return
            }
            guard flooded else { return }
            // Let go of the whole work: the glow till it is the card again.
            if wasWhole { try? await Task.sleep(for: .seconds(Self.after)) }
            guard !Task.isCancelled else { return }
            wasWhole = false
            withAnimation(.easeOut(duration: 0.3)) { flooded = false }
        }
    }

    /// Seconds the glow stays at the screen's foot after the whole work
    /// is let go, the last of its way back (`GalleryPage.back`, 0.55 s)
    /// then the next work's edge coming out of it.
    static let after: Double = 0.35

    /// How far below the screen's top the page lies, of its height: 0 shown,
    /// 1 a whole page down (and under the one shown).
    nonisolated static func under(_ proxy: GeometryProxy) -> CGFloat {
        let top = proxy.frame(in: .scrollView).minY
        return min(max(top / max(proxy.size.height, 1), 0), 1)
    }

    /// Where a page below the screen's top is drawn: kept at the top, under
    /// the page above it, as small as the card under the one shown is
    /// (`underInset` in from the sides) and its card's foot on the
    /// screen's, `under` of the way from that to the whole screen. Two
    /// pages down, it waits there too, under the one that will be.
    nonisolated static func lies(_ proxy: GeometryProxy, foot: CGFloat) -> (scale: CGFloat, y: CGFloat) {
        let size = proxy.size
        let top = proxy.frame(in: .scrollView).minY
        guard size.height > 0, top > 0, top < 2 * size.height else { return (1, 0) }
        let down = min(top / size.height, 1)
        let scale = 1 - 2 * underInset / max(size.width, 1) * down
        let at = size.height - foot * (1 - down) - scale * (size.height - foot)
        return (scale, at - top)
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

/// The next work's edge under the one shown, should its page not be laid
/// out yet (a lazy stack lays out what is on the screen): its thumbnail
/// where that page lies under (`StackedPage.lies`), dark, behind all the
/// pages. The page itself covers it as soon as it is there.
struct StackUnder: View {
    @Environment(AppModel.self) private var model
    let work: RemoteItem
    @State private var picture: UIImage?

    /// As a page's thumbnail (`GalleryPage.thumbPixel`): the one the page
    /// below has asked for already.
    private static let pixel: CGFloat = 900

    var body: some View {
        GeometryReader { geo in
            let scale = 1 - 2 * StackedPage.underInset / max(geo.size.width, 1)
            let size = CGSize(width: geo.size.width * scale, height: (geo.size.height - StackedPage.peek) * scale)
            let corner = max(ScreenCorner.radius(of: geo.size) - StackedPage.peek, 20) * scale
            Group {
                if let picture {
                    Image(uiImage: picture)
                        .resizable()
                        .scaledToFill()
                        .frame(width: size.width, height: size.height)
                } else {
                    Color(white: 0.12)
                }
            }
            .overlay(Color.black.opacity(StackedPage.dark))
            .frame(width: size.width, height: size.height)
            .clipShape(UnevenRoundedRectangle(
                bottomLeadingRadius: corner, bottomTrailingRadius: corner, style: .continuous
            ))
            .position(x: geo.size.width / 2, y: geo.size.height - size.height / 2)
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
            picture = loaded
        }
    }
}
