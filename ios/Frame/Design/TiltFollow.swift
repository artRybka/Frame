import SwiftUI

extension View {
    /// Keeps the gyroscope (`Tilt`) running while this view is on screen,
    /// for a gloss that runs with the phone's turn (`GlassSheen`) where no
    /// `parallax()` starts it. Off with Reduce Motion and in Low Power Mode.
    func followsTilt() -> some View {
        modifier(TiltFollow())
    }
}

private struct TiltFollow: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var phase

    private var turning: Bool { !reduceMotion && phase == .active }

    func body(content: Content) -> some View {
        content.task(id: turning) {
            guard turning, !ProcessInfo.processInfo.isLowPowerModeEnabled else { return }
            Tilt.shared.start()
            // Until the view leaves the screen or the app the foreground.
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(3600))
            }
            Tilt.shared.stop()
        }
    }
}

/// The shadow a card casts when its top stands off the page towards you: a
/// trapezoid behind the whole card, past its sides by `spread` at the top
/// and as wide as the card at the bottom ("Pod lupą", Mateusz 2026-11-11,
/// sheet pod-lupa-kafelki/szkic-cien-3).
struct LiftShadow: Shape {
    var spread: CGFloat = 7

    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.minX - spread, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX + spread, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
        path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
        path.closeSubpath()
        return path
    }
}
