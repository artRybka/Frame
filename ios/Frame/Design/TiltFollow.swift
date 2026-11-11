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

/// The shadow of a card whose top edge stands off the page, as a light
/// touch: a narrow sliver past each side, widest at the top corners and
/// down to nothing lower on the picture ("Pod lupą", Mateusz 2026-11-11:
/// "Mgiełka", sheet pod-lupa-kafelki/szkic-cien-2; the first, wide wedge
/// ran into one patch).
struct LiftEdges: Shape {
    /// How far past the card's sides it reaches at the top.
    var spread: CGFloat = 2.8

    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.minX - spread, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.minX + 0.5, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.minX + 0.5, y: rect.maxY))
        path.closeSubpath()
        path.move(to: CGPoint(x: rect.maxX + spread, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX - 0.5, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX - 0.5, y: rect.maxY))
        path.closeSubpath()
        return path
    }
}
