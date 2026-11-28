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
    /// A card with the next work's edge under it: not under the grid,
    /// where the pages lie as tiles.
    var on: Bool
    /// Lying on the stack: a page below the screen's top lies under the
    /// one shown (not under the grid, where pages lie as tiles).
    var stacked: Bool

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
    /// Parts of the stack left out, to find what a swipe's frames cost
    /// (`-galleryStackOff N`, the probe's; 0 in the app): 1 the pages
    /// below kept under, 2 the pages laid over one another, 4 the shade,
    /// 8 the thumbnail behind, 32 only the next page kept under (not the
    /// one after), 64 the line and the shadow, 128 the shade cut round as
    /// the card (a plain rectangle otherwise).
    nonisolated static let off = UserDefaults.standard.integer(forKey: "galleryStackOff")
    nonisolated static func left(_ part: Int) -> Bool { off & part != 0 }
    /// How far in the card pressed goes, all round (`GalleryPage`'s).
    nonisolated static let pressedInset: CGFloat = 12

    // Nothing here knows of a press or of the whole work: what a page
    // looks like then is the page's own, drawn from two numbers
    // (`GalleryPage`, `CardScene`). This only lays the pages on the stack.
    // (Till 1.145.417 the page was cut as a card here, uncut for the whole
    // work, and the next work's edge laid over it and taken off again by
    // tasks with waits of their own: three clocks for one picture, and
    // every seam between them was seen at some time; Mateusz 2026-11-28
    // 10:32: "Nie może być jakiś przeskoków, zostających ramek, mignięć
    // i przesunięć".)
    func body(content: Content) -> some View {
        let foot = on ? Self.peek : 0
        let stacks = stacked
        // The page laid on the stack by itself (`lies`), and over it its
        // shade, laid the same way: each knows how far down it lies.
        // Nothing masked, blurred or filtered: each of those made every
        // page on the screen an offscreen pass in every frame of a swipe
        // (runs 6, 8, 9: 34 to 48 ms a frame against 17).
        return ZStack(alignment: .top) {
            content
                .visualEffect { content, proxy in
                    let lies = stacks ? Self.lies(proxy, foot: foot) : (scale: CGFloat(1), y: CGFloat(0))
                    return content.scaleEffect(lies.scale, anchor: .top).offset(y: lies.y)
                }
            // Dark as it lies under the card shown, itself once it is the
            // screen: a plain black layer over it.
            if stacks, !Self.left(4) {
                GeometryReader { geo in
                    if Self.left(128) {
                        CardCut(foot: foot, corner: Self.corner(geo.size)).fill(.black)
                    } else {
                        Color.black.frame(height: geo.size.height - foot)
                            .frame(width: geo.size.width, height: geo.size.height, alignment: .top)
                    }
                }
                .visualEffect { content, proxy in
                    let lies = Self.lies(proxy, foot: foot)
                    return content
                        .scaleEffect(lies.scale, anchor: .top).offset(y: lies.y)
                        .opacity(Self.dark * Self.under(proxy))
                }
                .allowsHitTesting(false)
            }
        }
        .animation(.easeInOut(duration: 0.25), value: on)
    }

    /// The card's bottom corners, round with the screen's.
    nonisolated static func corner(_ size: CGSize) -> CGFloat { max(ScreenCorner.radius(of: size) - peek, 20) }

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
        let reach = left(32) ? size.height + 1 : 2 * size.height
        guard !left(1), size.height > 0, top > 0, top < reach else { return (1, 0) }
        let down = min(top / size.height, 1)
        let scale = 1 - 2 * underInset / max(size.width, 1) * down
        let at = size.height - foot * (1 - down) - scale * (size.height - foot)
        return (scale, at - top)
    }
}

/// What a Galeria page looks like pressed and on the way to the whole
/// work, from two numbers and nothing else: `press` (0 at rest, 1 pressed
/// in) and `way` (0 the card, 1 the whole work). Whatever is seen then is
/// drawn by these in every frame: nothing has a clock of its own, so
/// nothing can come early, stay behind or go in one frame.
enum CardScene {
    static func unit(_ x: CGFloat) -> CGFloat { min(max(x, 0), 1) }
    /// 0 up to `from`, 1 from `to`, smooth between.
    static func step(_ from: CGFloat, _ to: CGFloat, _ x: CGFloat) -> CGFloat {
        let t = unit((x - from) / max(to - from, 0.0001))
        return t * t * (3 - 2 * t)
    }

    /// Black over all that lies behind the card (the next work's edge,
    /// the page under it): in with the press, and there all the way to the
    /// whole work; back, the next work's edge comes out of it over the
    /// last third.
    static func black(_ press: CGFloat, _ way: CGFloat) -> CGFloat { max(unit(press), unit(way * 3)) }
    /// The page's glow over that black, the whole screen as one: from the
    /// first frame the work draws back, there before it is the whole.
    static func glow(_ way: CGFloat) -> CGFloat { step(0, 0.75, way) }
    /// The card's line and its shadow: gone early on the way.
    static func edge(_ way: CGFloat) -> CGFloat { 1 - step(0, 0.2, way) }
    /// The title low on the card: gone as the way starts, back at its end.
    static func caption(_ way: CGFloat) -> CGFloat { 1 - step(0, 0.15, way) }
    /// The whole work's own shadow.
    static func shadow(_ way: CGFloat) -> CGFloat { step(0.3, 1, way) }
    /// The card's head under the whole work: once the glow is there.
    static func head(_ way: CGFloat) -> CGFloat { step(0.6, 1, way) }
}

/// A layer of the scene: as much of it as `look` says at this `press` and
/// this `way`, in every frame of whatever animates the two.
struct Scened: ViewModifier, Animatable {
    var press: CGFloat
    var way: CGFloat
    let look: (CGFloat, CGFloat) -> CGFloat
    /// Points down while not there (the head comes up a little).
    var drop: CGFloat = 0

    var animatableData: AnimatablePair<CGFloat, CGFloat> {
        get { AnimatablePair(press, way) }
        set {
            press = newValue.first
            way = newValue.second
        }
    }

    func body(content: Content) -> some View {
        let there = CardScene.unit(look(press, way))
        content
            .opacity(there)
            .offset(y: drop * (1 - there))
    }
}

/// The card's light line on its foot and its shadow on what lies under
/// it; pressed, in with the card, and gone on the way to the whole work.
struct CardEdge: View, Animatable {
    var press: CGFloat
    var way: CGFloat
    let size: CGSize

    var animatableData: AnimatablePair<CGFloat, CGFloat> {
        get { AnimatablePair(press, way) }
        set {
            press = newValue.first
            way = newValue.second
        }
    }

    var body: some View {
        let inset = StackedPage.pressedInset * CardScene.unit(press)
        let wide = max(size.width - 2 * inset, 1)
        let tall = max(size.height - StackedPage.peek - 2 * inset, 1)
        let corner = max(StackedPage.corner(size) - inset, 8)
        ZStack {
            // Round its corners too (22:41: "Cień pod aktywnym dziełem się
            // urywa, jest płaskim paskiem"): plain strokes, never a blur.
            FootShadow(corner: corner)
            FootLine(corner: corner, rise: StackedPage.edgeRise, edge: StackedPage.edge)
        }
        .frame(width: wide, height: tall)
        .offset(x: inset, y: inset)
        .frame(width: size.width, height: size.height, alignment: .topLeading)
        .opacity(CardScene.edge(way))
        .allowsHitTesting(false)
    }
}

/// The card's line, drawn cheaply: a gradient stroked along a rounded
/// border cost a swipe half its frames (the probe's run 10, 50 ms against
/// 17 ms without it), so the foot and its corners are one plain stroke
/// and the sides two thin filled strips that fade up.
struct FootLine: View {
    let corner: CGFloat
    let rise: CGFloat
    let edge: Double

    var body: some View {
        GeometryReader { geo in
            let side = max(rise - corner, 0)
            ZStack(alignment: .bottom) {
                FootArc(corner: corner)
                    .stroke(.white.opacity(edge * 0.7), lineWidth: 1)
                HStack(spacing: 0) {
                    strip
                    Spacer(minLength: 0)
                    strip
                }
                .frame(height: side)
                .padding(.bottom, corner)
            }
            .frame(width: geo.size.width, height: geo.size.height, alignment: .bottom)
        }
    }

    private var strip: some View {
        Rectangle()
            .fill(LinearGradient(
                colors: [.white.opacity(0), .white.opacity(edge * 0.6)],
                startPoint: .top, endPoint: .bottom
            ))
            .frame(width: 1)
    }
}

/// The card's shadow on what lies under it: its foot stroked again and
/// again, each a little lower and fainter, so it is soft and goes round
/// the corners as the card does.
struct FootShadow: View {
    let corner: CGFloat
    static let steps = 12

    var body: some View {
        ZStack {
            ForEach(1 ... Self.steps, id: \.self) { step in
                let k = CGFloat(step)
                FootArc(corner: corner + k * 0.4)
                    .stroke(.black.opacity(0.15 * pow(1 - (k - 1) / CGFloat(Self.steps), 1.6)), lineWidth: 1.2)
                    .padding(.horizontal, -k * 0.4)
                    .offset(y: k * 0.7)
            }
        }
    }
}

/// The foot of a card: up its two bottom corners and along its bottom.
struct FootArc: Shape {
    var corner: CGFloat

    // Pressed, the corner goes in with the card, frame by frame (22:41:
    // the line "przeskakuje na narożnikach").
    var animatableData: CGFloat {
        get { corner }
        set { corner = newValue }
    }

    func path(in rect: CGRect) -> Path {
        let r = min(corner, rect.width / 2, rect.height)
        let x0 = rect.minX + 0.5, x1 = rect.maxX - 0.5, y1 = rect.maxY - 0.5
        var p = Path()
        p.move(to: CGPoint(x: x0, y: y1 - r))
        p.addArc(tangent1End: CGPoint(x: x0, y: y1), tangent2End: CGPoint(x: x0 + r, y: y1), radius: r)
        p.addLine(to: CGPoint(x: x1 - r, y: y1))
        p.addArc(tangent1End: CGPoint(x: x1, y: y1), tangent2End: CGPoint(x: x1, y: y1 - r), radius: r)
        return p
    }
}

/// A page cut as a card: the screen's corners at its top (the phone's
/// own), its foot `foot` above the screen's, its bottom corners round with
/// the screen's less that; none (all of the page) at a foot of 0.
struct CardCut: Shape {
    var foot: CGFloat
    let corner: CGFloat

    var animatableData: CGFloat {
        get { foot }
        set { foot = newValue }
    }

    func path(in rect: CGRect) -> Path {
        guard foot > 0.05 else { return Path(rect) }
        let share = min(foot / StackedPage.peek, 1)
        let round = max(corner * share, 0)
        return UnevenRoundedRectangle(bottomLeadingRadius: round, bottomTrailingRadius: round, style: .continuous)
            .path(in: CGRect(x: rect.minX, y: rect.minY, width: rect.width, height: max(rect.height - foot, 1)))
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

    /// What is in memory already, from the first frame: back from the
    /// grid the edge was black till its thumbnail came (the probe's run
    /// 12), though the grid had the work's tile all along.
    private var kept: UIImage? {
        guard let request = GalleryView.thumb(of: work.item, model.backend) else { return nil }
        return ImageLoader.inMemory(for: request, maxPixel: Self.pixel)
            ?? ImageLoader.inMemory(for: request, maxPixel: GalleryView.gridPixel)
    }

    var body: some View {
        GeometryReader { geo in
            let scale = 1 - 2 * StackedPage.underInset / max(geo.size.width, 1)
            let size = CGSize(width: geo.size.width * scale, height: (geo.size.height - StackedPage.peek) * scale)
            let corner = max(ScreenCorner.radius(of: geo.size) - StackedPage.peek, 20) * scale
            Group {
                if let picture = picture ?? kept {
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
            picture = nil
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
