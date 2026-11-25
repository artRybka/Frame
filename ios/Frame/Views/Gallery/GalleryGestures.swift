import SwiftUI
import UIKit

// UIKit's gestures, beside the pages' scroll and never holding it back
// (Mateusz 2026-11-24 14:06: "nie łapie machnięcia palca": SwiftUI's own
// drag and hold on the pages held the scroll back now and then).

/// A swipe from left to right, told apart from the scroll at once and
/// never in its way: the card's way back to Galeria.
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

/// A swipe down that starts in the screen's upper part: the work draws
/// back into the grid under the finger (Mateusz 2026-11-24 19:12:
/// "machnięcie w dół … niech wchodzi w siatkę dzieł"; 19:28: from the
/// upper part only, lower down it is the work before as ever). Where the
/// upper part ends is `SwipeZone`'s line; every swipe up tells it where
/// the thumb starts. The pages' own scroll waits for this one to say no,
/// so a swipe it takes never moves the pages.
struct DownSwipe: UIGestureRecognizerRepresentable {
    /// Off while the grid is up: its own scroll is not to wait for this.
    var on = true
    let began: () -> Void
    /// How far the finger has gone down (points).
    let changed: (CGFloat) -> Void
    /// Let go: how far it went and how fast it was going (points a second).
    let ended: (_ move: CGFloat, _ speed: CGFloat) -> Void

    func makeCoordinator(converter: CoordinateSpaceConverter) -> Coordinator { Coordinator() }

    func makeUIGestureRecognizer(context: Context) -> UIPanGestureRecognizer {
        let pan = UIPanGestureRecognizer()
        pan.delegate = context.coordinator
        pan.cancelsTouchesInView = false
        pan.maximumNumberOfTouches = 1
        pan.isEnabled = on
        return pan
    }

    func updateUIGestureRecognizer(_ recognizer: UIPanGestureRecognizer, context: Context) {
        if recognizer.isEnabled != on { recognizer.isEnabled = on }
    }

    func handleUIGestureRecognizerAction(_ recognizer: UIPanGestureRecognizer, context: Context) {
        let move = recognizer.translation(in: recognizer.view).y
        switch recognizer.state {
        case .began:
            began()
        case .changed:
            changed(move)
        case .ended:
            ended(move, recognizer.velocity(in: recognizer.view).y)
        case .cancelled, .failed:
            ended(0, 0)
        default:
            break
        }
    }

    @MainActor final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        func gestureRecognizerShouldBegin(_ recognizer: UIGestureRecognizer) -> Bool {
            guard let pan = recognizer as? UIPanGestureRecognizer,
                  let height = pan.view?.window?.bounds.height, height > 0
            else { return false }
            let speed = pan.velocity(in: nil)
            guard abs(speed.y) > abs(speed.x) * 1.5 else { return false }
            let start = pan.location(in: nil).y - pan.translation(in: nil).y
            let share = Double(start / height)
            if speed.y < 0 {
                // A swipe up, the pages' own: where the thumb starts.
                SwipeZone.note(share)
                return false
            }
            return share < SwipeZone.current
        }

        func gestureRecognizer(
            _ recognizer: UIGestureRecognizer, shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer
        ) -> Bool { true }

        /// The pages' scroll waits till this one has said no.
        func gestureRecognizer(
            _ recognizer: UIGestureRecognizer, shouldBeRequiredToFailBy other: UIGestureRecognizer
        ) -> Bool {
            other is UIPanGestureRecognizer && other.view is UIScrollView
        }
    }
}

/// Two fingers drawn together or spread (Mateusz 2026-11-24 18:51: "Ale
/// zachowany oddalenie przez szczypnięcie palcami?"): on a work, back to
/// the grid; on a tile in the grid, into that work.
struct GalleryPinch: UIGestureRecognizerRepresentable {
    var on = true
    /// Where the fingers are, on the screen.
    let began: (CGPoint) -> Void
    /// How far apart the fingers are, of what they were at first.
    let changed: (CGFloat) -> Void
    /// Let go: the same, and how fast it was changing (a second).
    let ended: (_ scale: CGFloat, _ speed: CGFloat) -> Void

    func makeCoordinator(converter: CoordinateSpaceConverter) -> Coordinator { Coordinator() }

    func makeUIGestureRecognizer(context: Context) -> UIPinchGestureRecognizer {
        let pinch = UIPinchGestureRecognizer()
        pinch.delegate = context.coordinator
        pinch.cancelsTouchesInView = false
        pinch.isEnabled = on
        return pinch
    }

    func updateUIGestureRecognizer(_ recognizer: UIPinchGestureRecognizer, context: Context) {
        if recognizer.isEnabled != on { recognizer.isEnabled = on }
    }

    func handleUIGestureRecognizerAction(_ recognizer: UIPinchGestureRecognizer, context: Context) {
        switch recognizer.state {
        case .began:
            began(recognizer.location(in: nil))
        case .changed:
            changed(recognizer.scale)
        case .ended:
            ended(recognizer.scale, recognizer.velocity)
        case .cancelled, .failed:
            ended(1, 0)
        default:
            break
        }
    }

    @MainActor final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        func gestureRecognizer(
            _ recognizer: UIGestureRecognizer, shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer
        ) -> Bool { true }
    }
}

/// A hold, and the finger then drawn up without lifting (Mateusz
/// 2026-11-24 18:51: "Podoba mi się koncept z całym dziełem po
/// przytrzymaniu … po przytrzymaniu … pociągnięcie w górę otwiera płynnie
/// kartę dzieła"). A finger that moves before the hold is a scroll, not
/// a hold.
struct HoldPull: UIGestureRecognizerRepresentable {
    var on = true
    let began: () -> Void
    /// How far up from where it was held the finger is now (points).
    let moved: (CGFloat) -> Void
    let ended: () -> Void

    func makeCoordinator(converter: CoordinateSpaceConverter) -> Coordinator { Coordinator() }

    func makeUIGestureRecognizer(context: Context) -> UILongPressGestureRecognizer {
        let hold = UILongPressGestureRecognizer()
        hold.minimumPressDuration = 0.35
        hold.allowableMovement = 10
        hold.cancelsTouchesInView = false
        hold.delegate = context.coordinator
        hold.isEnabled = on
        return hold
    }

    func updateUIGestureRecognizer(_ recognizer: UILongPressGestureRecognizer, context: Context) {
        if recognizer.isEnabled != on { recognizer.isEnabled = on }
    }

    func handleUIGestureRecognizerAction(_ recognizer: UILongPressGestureRecognizer, context: Context) {
        let y = recognizer.location(in: nil).y
        switch recognizer.state {
        case .began:
            context.coordinator.start = y
            began()
        case .changed:
            moved(context.coordinator.start - y)
        case .ended, .cancelled, .failed:
            ended()
        default:
            break
        }
    }

    @MainActor final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        var start: CGFloat = 0

        func gestureRecognizer(
            _ recognizer: UIGestureRecognizer, shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer
        ) -> Bool { true }
    }
}
