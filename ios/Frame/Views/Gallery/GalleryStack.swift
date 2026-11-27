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
    /// The next work, whose edge lies under the card: drawn over the
    /// page's glow while the one melts into the other (`covered`).
    var below: RemoteItem? = nil
    /// The page shown: only its card has the edge laid ready over its
    /// glow (on every page of the stack, a swipe lost frames, run 16).
    var shown = false

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
    /// below kept under, 2 the pages laid over one another, 4 the shade
    /// and the line, 8 the thumbnail behind, 16 the cut, 32 only the next
    /// page kept under (not the one after), 64 the line, 128 the shade cut
    /// round as the card (a plain rectangle otherwise), 256 the old line
    /// (a gradient stroked round the border).
    nonisolated static let off = UserDefaults.standard.integer(forKey: "galleryStackOff")
    nonisolated static func left(_ part: Int) -> Bool { off & part != 0 }
    /// How far in the card pressed goes, all round (`GalleryPage`'s).
    nonisolated static let pressedInset: CGFloat = 12

    /// The foot of the screen is the page's (its glow), not the next
    /// work's: from the press, and after the whole work is let go till it
    /// is the card again. The card itself is cut as soon as it is one
    /// (18:47: "Przy powrocie z całego dzieła do pełnego ekranu też pasek
    /// u dołu powinien być od razu"; before, the cut waited 0.55 s).
    @State private var flooded = false
    @State private var wasWhole = false
    /// Flooded, how much the next work's edge still lies over the glow:
    /// the page is uncut at once and the edge fades into the glow, and
    /// back (Mateusz 2026-11-27 22:41: "Tło łuny powinno delikatnie
    /// przenikać i pojawiać się płynnie"; the cut drawn down, the glow
    /// had come out from behind the card, sharp).
    @State private var covered: Double = 1
    /// Seconds the next work's edge takes to melt into the glow, and back.
    nonisolated static let melt: Double = 0.3
    nonisolated static let unmelt: Double = 0.35

    func body(content: Content) -> some View {
        let card = on
        let foot = card ? Self.peek : 0
        let stacks = stacked
        let flood = flooded
        // Cut above the next work's edge; flooded, down to the screen's
        // foot, the page's glow coming over that edge as the card goes in.
        let cut = card && !flood ? Self.peek : 0
        // The page, and over it its shade and its line: each laid on the
        // stack by itself (`lies`), so each knows how far down it lies.
        // Measured inside the page moved, the shade read where the page was
        // drawn, near the top, and the work under was hardly dark (the
        // film of run 4: the edge at 80% of its brightness, not 35%).
        // Clipped by a shape, never masked, and its shadow a gradient, not
        // a blur: masked and blurred, each page on the screen was drawn
        // off the screen in every frame and swipes ran at half the frames
        // (run 6: 36 ms a frame against 17 before the stack; Mateusz
        // 2026-11-27 18:47: "nie jest płynna. Odrobinę skacze?").
        // One layer, laid on the stack by itself (`lies`) and shaded there
        // by how far down it lies. A shade and a line each laid on the
        // stack beside it, each changing in every frame, halved a swipe's
        // frames (run 8: 34 ms a frame with them, 17 without).
        return ZStack(alignment: .top) {
        GeometryReader { geo in
            let tall = geo.size.height - foot
            ZStack(alignment: .top) {
                content
                    .clipShape(CardCut(foot: Self.left(16) ? 0 : cut, corner: Self.corner(geo.size)))
                // What lies under the card while it is flooded: the next
                // work's edge, melting into the glow (`covered`).
                // Always there on the card, unseen but flooded: laid in when
                // the press came, it was gone again a frame later (run 15).
                if stacks, shown, card || held {
                    under(geo.size)
                        .opacity(flood ? covered : 0)
                        .allowsHitTesting(false)
                }
                // Its shadow on the card under it, round its corners too
                // (22:41: "Cień pod aktywnym dziełem się urywa, jest płaskim
                // paskiem"): plain strokes of its foot, each lower and
                // fainter, never a blur (a pass off the screen each frame).
                if card, stacks {
                    // Pressed, in with the card, as its line goes.
                    let inset = pressed ? Self.pressedInset : 0
                    FootShadow(corner: max(Self.corner(geo.size) - inset, 8))
                        .frame(width: geo.size.width - 2 * inset, height: tall - 2 * inset)
                        .offset(x: inset, y: inset)
                        .frame(width: geo.size.width, height: geo.size.height, alignment: .topLeading)
                        .opacity(flood ? covered : 1)
                        .allowsHitTesting(false)
                        .transition(.opacity)
                }
                // The light line; pressed, in with the card; not on the
                // glow before the work let go is back there (run 6: a line
                // at the card's size on the empty glow). Under the card
                // shown, dark with the rest of its page.
                if !Self.left(64) {
                    let inset = pressed || !card ? Self.pressedInset : 0
                    let high = tall - 2 * inset
                    let corner = max(Self.corner(geo.size) - inset, 8)
                    Group {
                        if Self.left(256) {
                            UnevenRoundedRectangle(bottomLeadingRadius: corner, bottomTrailingRadius: corner, style: .continuous)
                                .strokeBorder(line(height: high), lineWidth: 1)
                        } else {
                            FootLine(corner: corner, rise: Self.edgeRise, edge: Self.edge)
                        }
                    }
                        .frame(width: geo.size.width - 2 * inset, height: high)
                        .offset(x: inset, y: inset)
                        .frame(width: geo.size.width, height: geo.size.height, alignment: .topLeading)
                        // Gone with the way to the whole work as it starts,
                        // back as the card is (22:41: it stayed on the
                        // way, then went from one frame to the next).
                        .opacity(!card || (flood && !held) ? 0 : 1)
                        .animation(.easeOut(duration: card ? 0.3 : 0.12), value: card)
                        .allowsHitTesting(false)
                }
            }
            .frame(width: geo.size.width, height: geo.size.height, alignment: .top)
        }
        .visualEffect { content, proxy in
            let lies = stacks ? Self.lies(proxy, foot: foot) : (scale: CGFloat(1), y: CGFloat(0))
            return content.scaleEffect(lies.scale, anchor: .top).offset(y: lies.y)
        }
        // Dark as it lies under the card shown, itself once it is the
        // screen: a plain black layer over it, laid on the stack by itself
        // so that it knows how far down the page lies (measured inside the
        // page moved, it read where the page was drawn). Not a filter on
        // the page: a contrast and a brightness, even at none, made every
        // page an offscreen pass (run 9: 48 ms a frame).
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
        .opacity(hidden ? 0 : 1)
        .animation(.easeInOut(duration: HoldPull.press), value: pressed)
        .animation(.easeInOut(duration: HoldPull.press), value: hidden)
        .animation(.easeInOut(duration: 0.25), value: card)
        .animation(.easeInOut(duration: HoldPull.press), value: held)
        .onChange(of: on) { _, now in if !now, held { wasWhole = true } }
        .task(id: held) {
            var quiet = Transaction()
            quiet.disablesAnimations = true
            if held {
                // Uncut at once, the next work's edge drawn over the glow
                // where it was, then melting into it.
                if !flooded {
                    withTransaction(quiet) { flooded = true; covered = 1 }
                    // Laid first, then melted: changed in the same update
                    // it came in, it came already melted (run 14: the edge
                    // gone in a tenth of a second, not in 0.45).
                    try? await Task.sleep(for: .milliseconds(20))
                    guard !Task.isCancelled else { return }
                }
                withAnimation(.easeOut(duration: Self.melt)) { covered = 0 }
                return
            }
            guard flooded else { return }
            // Let go of the whole work: the glow till it is the card again.
            if wasWhole { try? await Task.sleep(for: .seconds(Self.after)) }
            guard !Task.isCancelled else { return }
            wasWhole = false
            withAnimation(.easeInOut(duration: Self.unmelt)) { covered = 1 }
            try? await Task.sleep(for: .seconds(Self.unmelt))
            guard !Task.isCancelled else { return }
            withTransaction(quiet) { flooded = false }
        }
    }

    /// The next work's edge as it lies under the card, on the screen's
    /// ground (what is seen beside it), to lie over the page uncut.
    private func under(_ size: CGSize) -> some View {
        ZStack(alignment: .bottom) {
            Color.black.frame(height: Self.peek + 2)
            if let below { StackUnder(work: below) }
        }
        .frame(width: size.width, height: size.height, alignment: .bottom)
        // Only the edge: the work under lies whole behind the card, and
        // over the page it darkened all of it (run 14, back from the whole
        // work: the screen at 62 against 141 for a third of a second).
        .clipShape(OffCard(foot: Self.peek, corner: Self.corner(size)), style: FillStyle(eoFill: true))
    }

    /// The card's bottom corners, round with the screen's.
    static func corner(_ size: CGSize) -> CGFloat { max(ScreenCorner.radius(of: size) - peek, 20) }

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
        let reach = left(32) ? size.height + 1 : 2 * size.height
        guard !left(1), size.height > 0, top > 0, top < reach else { return (1, 0) }
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

/// All of a page but its card (filled even-odd): what the card's cut
/// leaves of the screen, the round corners' sides with the foot (run 16:
/// a band with a straight top, the glow light beside the corners above it).
struct OffCard: Shape {
    let foot: CGFloat
    let corner: CGFloat

    func path(in rect: CGRect) -> Path {
        var path = Path(rect)
        path.addPath(CardCut(foot: foot, corner: corner).path(in: rect))
        return path
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
            .overlay(alignment: .bottom) {
                // The page's caption gradient, as its page has it (every
                // page has its caption now): the edge was lighter than the
                // page's own (run 15: 35 against 13).
                LinearGradient(
                    stops: [
                        .init(color: .black.opacity(0), location: 0),
                        .init(color: .black.opacity(0.55), location: 0.45),
                        .init(color: .black.opacity(0.8), location: 1),
                    ],
                    startPoint: .top, endPoint: .bottom
                )
                .frame(height: 190)
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
