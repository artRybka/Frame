import SwiftUI
import UIKit

// UIKit's gestures, beside the pages' scroll and never holding it back
// (Mateusz 2026-11-24 14:06: "nie łapie machnięcia palca": SwiftUI's own
// drag and hold on the pages held the scroll back now and then).

/// A swipe from left to right, told apart from the scroll at once and
/// never in its way: the card's way back to Galeria. `leftward`, the
/// other way: Galeria's own way out to Odkrywaj, taken under the finger
/// as soon as it has gone far enough, not when it lifts.
struct SideSwipe: UIGestureRecognizerRepresentable {
    /// Only from the screen's edge it goes away from: the left one for a
    /// swipe rightward (the card's way back, Galeria's grid), the right one
    /// for a swipe leftward.
    var fromEdge = false
    var leftward = false
    var on = true
    let action: () -> Void

    /// How far the finger goes before a swipe is one (points).
    static let far: CGFloat = 50

    func makeCoordinator(converter: CoordinateSpaceConverter) -> Coordinator {
        Coordinator(fromEdge: fromEdge, leftward: leftward)
    }

    func makeUIGestureRecognizer(context: Context) -> UIPanGestureRecognizer {
        let pan = UIPanGestureRecognizer()
        pan.delegate = context.coordinator
        pan.cancelsTouchesInView = false
        pan.isEnabled = on
        return pan
    }

    func updateUIGestureRecognizer(_ recognizer: UIPanGestureRecognizer, context: Context) {
        if recognizer.isEnabled != on { recognizer.isEnabled = on }
    }

    func handleUIGestureRecognizerAction(_ recognizer: UIPanGestureRecognizer, context: Context) {
        let move = recognizer.translation(in: recognizer.view)
        let speed = recognizer.velocity(in: recognizer.view)
        let along = leftward ? -move.x : move.x, pace = leftward ? -speed.x : speed.x
        let sideways = along > abs(move.y) * 1.5
        if leftward {
            let coordinator = context.coordinator
            switch recognizer.state {
            case .began: coordinator.taken = false
            case .changed:
                guard !coordinator.taken, along > Self.far, sideways else { return }
                coordinator.taken = true
                action()
            case .ended:
                guard !coordinator.taken, pace > 500, along > 16, sideways else { return }
                coordinator.taken = true
                action()
            default: break
            }
            return
        }
        guard recognizer.state == .ended else { return }
        guard along > Self.far || pace > 500, sideways else { return }
        action()
    }

    @MainActor final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        /// How far in from the screen's edge a swipe from it may start.
        static let edge: CGFloat = 44
        let fromEdge: Bool
        let leftward: Bool
        /// This swipe has done what it does.
        var taken = false

        init(fromEdge: Bool, leftward: Bool) {
            self.fromEdge = fromEdge
            self.leftward = leftward
        }

        func gestureRecognizerShouldBegin(_ recognizer: UIGestureRecognizer) -> Bool {
            guard let pan = recognizer as? UIPanGestureRecognizer else { return false }
            let speed = pan.velocity(in: pan.view)
            if fromEdge {
                // From the edge the swipe goes away from: the left one for
                // a swipe rightward, the right one for a swipe leftward.
                let start = pan.location(in: pan.view).x - pan.translation(in: pan.view).x
                let width = pan.view?.bounds.width ?? 0
                if leftward ? start < width - Self.edge : start > Self.edge { return false }
            }
            let along = leftward ? -speed.x : speed.x
            return along > 0 && along > abs(speed.y) * 1.5
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
///
/// The phone taps on the way to the hold, faster and faster, and hard
/// when the whole work comes (2026-11-25: "Gdy przytrzymuję ekran, to
/// zaczynaj coraz szybciej stukać i przy przejściu na widok całego dzieła
/// mocne stuknięcie"): the finger has lain `touch` seconds by the first
/// tap, and `taps` say how long after the one before each comes; the
/// hold `last` seconds after the last of them.
struct HoldPull: UIGestureRecognizerRepresentable {
    var on = true
    /// A hold can begin now: asked before the first tap and before the hold.
    let ready: () -> Bool
    /// The finger lies and the taps have begun (true), till it lifts or
    /// moves off (false): what it lies on is seen to sink in meanwhile.
    var pressing: (Bool) -> Void = { _ in }
    let began: () -> Void
    /// How far up from where it was held the finger is now (points).
    let moved: (CGFloat) -> Void
    let ended: () -> Void

    /// Longer than a finger rests before it swipes: a swipe gives no tap.
    static let touch = 0.14
    static let taps: [Double] = [0, 0.09, 0.075, 0.06, 0.05, 0.04]
    static let last = 0.03
    /// Seconds from the first tap to the hold.
    static let press = taps.reduce(0, +) + last
    /// How far a finger may stray before the hold and still be holding.
    static let stray: CGFloat = 10

    func makeCoordinator(converter: CoordinateSpaceConverter) -> Coordinator { Coordinator() }

    func makeUIGestureRecognizer(context: Context) -> UILongPressGestureRecognizer {
        let hold = UILongPressGestureRecognizer()
        hold.minimumPressDuration = Self.touch
        hold.allowableMovement = Self.stray
        hold.cancelsTouchesInView = false
        hold.delegate = context.coordinator
        hold.isEnabled = on
        return hold
    }

    func updateUIGestureRecognizer(_ recognizer: UILongPressGestureRecognizer, context: Context) {
        if recognizer.isEnabled != on { recognizer.isEnabled = on }
    }

    func handleUIGestureRecognizerAction(_ recognizer: UILongPressGestureRecognizer, context: Context) {
        let coordinator = context.coordinator
        let at = recognizer.location(in: nil)
        switch recognizer.state {
        case .began:
            coordinator.stop()
            if coordinator.pressing { pressing(false) }
            coordinator.pressing = false
            coordinator.origin = at
            guard ready() else { return }
            coordinator.pressing = true
            pressing(true)
            coordinator.soft.prepare()
            coordinator.hard.prepare()
            coordinator.towards = Task { @MainActor in
                for (n, wait) in Self.taps.enumerated() {
                    if wait > 0 { try? await Task.sleep(for: .seconds(wait)) }
                    guard !Task.isCancelled else { return }
                    coordinator.soft.impactOccurred(intensity: 0.35 + 0.1 * CGFloat(n))
                    GalleryLog.trace("hold: tap \(n + 1)")
                }
                try? await Task.sleep(for: .seconds(Self.last))
                guard !Task.isCancelled, ready() else { return }
                coordinator.towards = nil
                coordinator.held = true
                coordinator.start = recognizer.location(in: nil).y
                coordinator.hard.impactOccurred(intensity: 1)
                began()
            }
        case .changed:
            if coordinator.held {
                moved(coordinator.start - at.y)
            } else if hypot(at.x - coordinator.origin.x, at.y - coordinator.origin.y) > Self.stray {
                // It moved before the hold: a scroll, and no more taps.
                coordinator.stop()
                if coordinator.pressing { pressing(false) }
                coordinator.pressing = false
            }
        case .ended, .cancelled, .failed:
            let held = coordinator.held
            coordinator.stop()
            if held { ended() }
            if coordinator.pressing { pressing(false) }
            coordinator.pressing = false
        default:
            break
        }
    }

    @MainActor final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        /// Where the finger was when the hold began, and where it first lay.
        var start: CGFloat = 0
        var origin = CGPoint.zero
        var held = false
        /// The finger lies, said so (`HoldPull.pressing`).
        var pressing = false
        /// The taps on the way to the hold.
        var towards: Task<Void, Never>?
        let soft = UIImpactFeedbackGenerator(style: .light)
        let hard = UIImpactFeedbackGenerator(style: .heavy)

        func stop() {
            towards?.cancel()
            towards = nil
            held = false
        }

        func gestureRecognizer(
            _ recognizer: UIGestureRecognizer, shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer
        ) -> Bool { true }
    }
}
