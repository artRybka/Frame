import SwiftUI

/// How a work's card comes in from Galeria, with no slide of its own
/// (Mateusz 2026-11-24 07:36): from the whole work, held there, the work
/// moves up to its place on the card and the rest of the card rides up
/// from under it ("dzieło podsuwa się do góry na miejsce w karcie dzieła i
/// pojawia się reszta treści"; 18:51: "pociągnięcie w górę otwiera płynnie
/// kartę dzieła"). Where the work's place there is not known, the card's
/// work surfaces instead.
enum CardArrival {
    struct Pending {
        /// Where the whole work lay on the screen; nil from the cut one.
        let from: CGRect?
        /// Where it lies there with no finger drawing it up: the card
        /// drawn down brings the work back to this (`CardLeave`).
        var rest: CGRect?
        /// Galeria's ground behind it, fading into the card's paper.
        let ground: Color
        /// Back to Galeria without the pop's slide: the card melts into
        /// the work cut to the screen (Mateusz 2026-11-25; the whole work
        /// it came from is there only under a finger). `whole`: the card
        /// has been drawn down to the whole work as Galeria shows it, and
        /// Galeria goes on from there.
        var back: (@MainActor (_ whole: Bool) -> Void)?
    }

    /// Left by Galeria for the card it is about to open, taken by the card.
    @MainActor static var pending: [String: Pending] = [:]

    /// The work's way to its place.
    static let move = Animation.spring(duration: 0.42, bounce: 0)
    /// The card's work surfacing, as the whole one does in Galeria.
    static let surface = Animation.easeOut(duration: 0.22)
    /// The rest of the card, once the work is on its way.
    static func rest(_ pending: Pending) -> Animation {
        pending.from == nil ? .easeOut(duration: 0.3).delay(0.08) : .easeOut(duration: 0.22)
    }
    /// Galeria's ground giving way to the paper.
    static let ground = Animation.easeInOut(duration: 0.4)
}

/// The card that came from the whole work, drawn down from its top: it
/// goes back to the whole work as Galeria shows it, and let go there,
/// Galeria goes on to the work cut to the screen (Mateusz 2026-11-25
/// 18:12: "chciałabym móc wrócić do poprzedniego widoku przeciągając kartę
/// dzieła w dół (to naturalny odruch) - najlepiej jeżeli najpierw dociągnie
/// do widoku całego dzieła a po puszczeniu wróci na pełny ekran").
///
/// The finger is the scroll view's own: how far the card is drawn past
/// its top is how far back it has gone. The card does not give under the
/// finger as a list does (`CardHeld`); its work goes to where the whole
/// work lies, its head with it, the rest fades (`LeftBehind`) and
/// Galeria's ground and glow come back. Only its small modifiers read
/// this, never the card's body: a frame of the finger is a few numbers.
@MainActor @Observable final class CardLeave {
    /// How far the card is drawn down past its top by a finger (points).
    private(set) var down: CGFloat = 0
    /// Let go far enough: all the way back, whatever the scroll does now.
    var gone = false
    /// Times it has been drawn all the way: the phone taps.
    private(set) var reached = 0

    /// A finger lies on the card's scroll.
    @ObservationIgnored var touching = false
    /// Drawn down by a finger (not thrown against its top) till it is
    /// back at its top.
    @ObservationIgnored private(set) var on = false
    @ObservationIgnored private var there = false
    /// Where the card's work lies, for the way back from it.
    @ObservationIgnored var home: CGRect?

    /// Points past the top for the whole of the way: some 125 of a
    /// finger's, the scroll giving less and less.
    static let reach: CGFloat = 64
    /// The share of the way from which letting go is going back.
    static let enough: CGFloat = 0.6

    /// 0 the card … 1 the whole work as Galeria shows it.
    var share: CGFloat { gone ? 1 : min(max(down / Self.reach, 0), 1) }

    /// The scroll is `over` points past its top.
    func scrolled(over: CGFloat) {
        guard over > 0.25 else {
            on = false
            there = false
            if down != 0 { down = 0 }
            return
        }
        if !on {
            guard touching else { return }
            on = true
        }
        down = over
        if over >= Self.reach, !there {
            there = true
            reached += 1
        } else if over < Self.reach * 0.85 {
            there = false
        }
        GalleryLog.trace("card drawn down \(Int(over)) pt: \(Int((share * 100).rounded()))% of the way back")
    }
}

/// The card stays where it is under a finger that draws it down: what it
/// does then is its way back (`CardLeave`), not a list's give.
struct CardHeld: ViewModifier {
    let leave: CardLeave?

    func body(content: Content) -> some View {
        content.offset(y: -(leave?.down ?? 0))
    }
}

/// What of the card Galeria's whole work has not: gone by the time the
/// card is drawn back to it.
struct LeftBehind: ViewModifier {
    let leave: CardLeave?

    func body(content: Content) -> some View {
        content.opacity(1 - Double(leave?.share ?? 0))
    }
}

/// What of Galeria the card came over (its ground, its glow): there while
/// the card comes (`shown`), and again as the card is drawn back.
struct BroughtBack: ViewModifier {
    let leave: CardLeave?
    let shown: Bool
    var strength: Double = 1

    func body(content: Content) -> some View {
        content
            .opacity(strength * max(shown ? 1 : 0, Double(leave?.share ?? 0)))
            .animation(CardArrival.ground, value: shown)
    }
}

/// The card's picture on its way from Galeria: drawn where the whole work
/// lay (or a little small and clear, from the cut one) till `arrived`.
/// `home` is where it lies on the card, measured outside the move. Drawn
/// down again (`leave`), it goes to where the whole work rests there.
struct ArrivingPicture: ViewModifier {
    let pending: CardArrival.Pending?
    let arrived: Bool
    let home: CGRect?
    var leave: CardLeave?
    let measured: (CGRect) -> Void
    @Environment(\.colorScheme) private var scheme

    func body(content: Content) -> some View {
        let back = leave?.share ?? 0
        content
            .scaleEffect(scale * smaller(back))
            .offset(offset)
            .offset(fall(back))
            .opacity(opacity)
            // Over the work at its place on the card, the chevron Galeria
            // has over the whole work turned round: a pull down takes the
            // card back there (Mateusz 2026-11-25 21:54: "W drugą stronę
            // (z karty dzieła) trzeba w tym miejscu nad dziełem dać
            // strzałkę w dół"). The card's own, close over the work and
            // under the bar's buttons (in the bar it lay against them);
            // there once the work is, gone as the card goes back.
            .overlay(alignment: .top) {
                if leave != nil {
                    CardChevron(light: scheme == .light, down: true)
                        .offset(y: -(CardChevron.overCard + CardChevron.height / 2))
                        .opacity(arrived ? 1 - Double(back) : 0)
                        .animation(.easeOut(duration: 0.25), value: arrived)
                        .allowsHitTesting(false)
                }
            }
            .background {
                Color.clear
                    .onGeometryChange(for: CGRect.self) { $0.frame(in: .global) } action: { lies in
                        leave?.home = lies
                        measured(lies)
                    }
            }
    }

    /// Drawn back by `back` of the way: how small, and how far from its
    /// place here. (Its place is measured under `CardHeld`, where the
    /// finger does not move it.)
    private func smaller(_ back: CGFloat) -> CGFloat {
        guard back > 0, let rest = pending?.rest, let lies = leave?.home, lies.width > 0 else { return 1 }
        return 1 + (rest.width / lies.width - 1) * back
    }

    private func fall(_ back: CGFloat) -> CGSize {
        guard back > 0, let rest = pending?.rest, let lies = leave?.home else { return .zero }
        return CGSize(width: (rest.midX - lies.midX) * back, height: (rest.midY - lies.midY) * back)
    }

    private var away: Bool { pending != nil && !arrived }

    private var scale: CGFloat {
        guard away, let pending else { return 1 }
        guard let from = pending.from else { return 0.96 }
        guard let home, home.width > 0 else { return 1 }
        return from.width / home.width
    }

    private var offset: CGSize {
        guard away, let from = pending?.from, let home else { return .zero }
        return CGSize(width: from.midX - home.midX, height: from.midY - home.midY)
    }

    private var opacity: Double {
        guard away else { return 1 }
        // From the cut work it surfaces; from the whole one it waits only
        // for its place to be known.
        return pending?.from == nil || home == nil ? 0 : 1
    }
}
