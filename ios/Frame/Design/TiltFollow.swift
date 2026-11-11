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

extension View {
    /// A card standing a little over the page: it shifts with the phone's
    /// turn (`Tilt`) and the shadow it casts on the page shifts the other
    /// way ("Pod lupą", Mateusz 2026-11-11). Still with Reduce Motion.
    func liftedCard(cornerRadius: CGFloat) -> some View {
        modifier(LiftedCard(radius: cornerRadius))
    }
}

private struct LiftedCard: ViewModifier {
    let radius: CGFloat
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorScheme) private var scheme

    /// How far the card moves at a full turn (Mateusz 2026-11-11: 2 pt,
    /// was 2.5; shadow lighter and sharper, was 0.14 at blur 5).
    static let shift: CGFloat = 2
    /// How far its shadow on the page moves the other way.
    static let cast: CGFloat = 2
    /// How far the shadow is smaller than the card on each side: at rest,
    /// held straight, it lies under the card and the card looks like any
    /// other; it shows only as the phone turns (Mateusz 2026-11-11 13:53).
    static let inset: CGFloat = 2.5

    func body(content: Content) -> some View {
        let tilt = Tilt.shared
        let x = reduceMotion ? 0 : CGFloat(tilt.x)
        let y = reduceMotion ? 0 : CGFloat(tilt.y)
        content
            .background {
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .fill(.black.opacity(scheme == .dark ? 0.32 : 0.09))
                    .padding(Self.inset)
                    .blur(radius: 3)
                    // Moved with the card below, so back by both.
                    .offset(x: -x * (Self.shift + Self.cast), y: -y * (Self.shift + Self.cast))
            }
            .offset(x: x * Self.shift, y: y * Self.shift)
            .followsTilt()
    }
}
