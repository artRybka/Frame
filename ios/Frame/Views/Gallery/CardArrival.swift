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
        /// Galeria's ground behind it, fading into the card's paper.
        let ground: Color
        /// Back to Galeria without the pop's slide: the card melts into
        /// the work cut to the screen (Mateusz 2026-11-25; the whole work
        /// it came from is there only under a finger).
        var back: (@MainActor () -> Void)?
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

/// The card's picture on its way from Galeria: drawn where the whole work
/// lay (or a little small and clear, from the cut one) till `arrived`.
/// `home` is where it lies on the card, measured outside the move.
struct ArrivingPicture: ViewModifier {
    let pending: CardArrival.Pending?
    let arrived: Bool
    let home: CGRect?
    let measured: (CGRect) -> Void

    func body(content: Content) -> some View {
        content
            .scaleEffect(scale)
            .offset(offset)
            .opacity(opacity)
            .background {
                Color.clear
                    .onGeometryChange(for: CGRect.self) { $0.frame(in: .global) } action: { measured($0) }
            }
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
