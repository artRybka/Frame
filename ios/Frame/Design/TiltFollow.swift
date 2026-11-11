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
