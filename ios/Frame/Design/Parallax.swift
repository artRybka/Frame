import CoreMotion
import SwiftUI

/// A picture that sits a little deeper than its card: it drifts as the
/// phone turns in the hand and lags behind as the page scrolls, inside a
/// window that clips it. For the study of the day on Odkrywaj, so it
/// stands out from the other cards (PLAN 3.3zzz33), and for the collage
/// behind the glass of the "Ukryte" card (`FrostedCover`, 3.3zzz35).
enum Parallax {
    /// How much bigger than its window the picture is, on each side. It
    /// never moves further than this, so no edge ever shows.
    static let side: CGFloat = 6
    static let top: CGFloat = 10
    /// The most the phone's turn moves it (1.118.2 had 11 and 7: far too
    /// much, Mateusz 2026-11-07, PLAN 3.3zzz36).
    static let tiltSide: CGFloat = 4
    static let tiltTop: CGFloat = 2.5
    /// Scrolled up, the picture moves down by this part of the way, up to
    /// what is left above and below once the turn has had its share
    /// (1.118.2: 0.12, up to 15 pt).
    static let lag: CGFloat = 0.05
    static var liftMost: CGFloat { top - tiltTop }
}

extension EnvironmentValues {
    /// How far the page holding a parallax picture is scrolled (from 0 at rest).
    @Entry var parallaxLift: CGFloat = 0
}

extension View {
    /// Moves a picture made `Parallax.side` / `.top` bigger than its
    /// clipped window with the phone's turn and the page's scroll. Still
    /// with Reduce Motion; without the turn in Low Power Mode.
    func parallax() -> some View {
        modifier(ParallaxShift())
    }
}

private struct ParallaxShift: ViewModifier {
    @Environment(\.parallaxLift) private var lift
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var phase

    private var turning: Bool { !reduceMotion && phase == .active }

    func body(content: Content) -> some View {
        let tilt = Tilt.shared
        let x = reduceMotion ? 0 : -tilt.x * Parallax.tiltSide
        let y = reduceMotion ? 0 : min(max(lift, 0) * Parallax.lag, Parallax.liftMost) - tilt.y * Parallax.tiltTop
        content
            .offset(x: x, y: y)
            .task(id: turning) {
                guard turning, !ProcessInfo.processInfo.isLowPowerModeEnabled else { return }
                tilt.start()
                // Until the tile leaves the screen or the app the foreground.
                while !Task.isCancelled {
                    try? await Task.sleep(for: .seconds(3600))
                }
                tilt.stop()
            }
    }
}

/// How the phone has just been turned, from -1 to 1 on each axis, easing
/// back to 0 within a couple of seconds once it is held still: any way of
/// holding it is the middle. The gyroscope runs only while a picture asks
/// for it; no permission is needed for device motion.
@MainActor @Observable
final class Tilt {
    static let shared = Tilt()

    /// Turned about the phone's long axis (right side away: positive).
    private(set) var x: Double = 0
    /// Tipped about its short axis (top towards you: positive).
    private(set) var y: Double = 0

    @ObservationIgnored private let manager = CMMotionManager()
    @ObservationIgnored private var users = 0
    @ObservationIgnored private var turnX: Double = 0
    @ObservationIgnored private var turnY: Double = 0

    /// Updates a second.
    private static let rate = 60.0
    /// Kept of the turn on each update: about two seconds to settle.
    private static let hold = 0.992
    /// Radians of turn that reach the edge.
    private static let reach = 0.2
    /// Followed of the new value on each update, so it glides.
    private static let glide = 0.2

    func start() {
        users += 1
        guard users == 1, manager.isDeviceMotionAvailable else { return }
        manager.deviceMotionUpdateInterval = 1 / Self.rate
        manager.startDeviceMotionUpdates(to: .main) { [weak self] motion, _ in
            guard let rotation = motion?.rotationRate else { return }
            let aboutX = rotation.x, aboutY = rotation.y
            MainActor.assumeIsolated { self?.turned(aboutX: aboutX, aboutY: aboutY) }
        }
    }

    func stop() {
        users = max(users - 1, 0)
        guard users == 0 else { return }
        manager.stopDeviceMotionUpdates()
        turnX = 0
        turnY = 0
        x = 0
        y = 0
    }

    private func turned(aboutX: Double, aboutY: Double) {
        let step = 1 / Self.rate
        let most = Self.reach * 1.5
        turnX = min(max((turnX + aboutY * step) * Self.hold, -most), most)
        turnY = min(max((turnY + aboutX * step) * Self.hold, -most), most)
        let toX = min(max(turnX / Self.reach, -1), 1)
        let toY = min(max(turnY / Self.reach, -1), 1)
        x += (toX - x) * Self.glide
        y += (toY - y) * Self.glide
    }
}
