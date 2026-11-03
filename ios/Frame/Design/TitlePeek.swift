import SwiftUI
import UIKit

/// A press that answers as it starts: haptic taps closer and closer,
/// and firmer, while the finger stays, and the text (or picture) growing a
/// touch; held long enough, `action` runs with a firm tap and it settles
/// back. A quick tap does `onTap`. Used by "Tytuł w oryginale", the
/// artist's name (held: their other works on Szukaj) and the picture
/// (held: the whole screen).
struct PressHold: ViewModifier {
    var enabled = true
    var grow: CGFloat = 1.02
    var anchor: UnitPoint = .leading
    var onTap: (() -> Void)?
    let action: () -> Void

    @State private var pressed = false
    @State private var rumbling: Task<Void, Never>?
    @State private var fired = 0

    /// How long the finger stays before `action`.
    static let hold = 0.5
    /// A touch shorter than this (a tap, a scroll starting) shows nothing.
    private static let settle = 0.08

    func body(content: Content) -> some View {
        content
            .scaleEffect(pressed ? grow : 1, anchor: anchor)
            .contentShape(Rectangle())
            // Before the long press, or the hold would never start.
            .onTapGesture { onTap?() }
            .onLongPressGesture(minimumDuration: Self.hold, maximumDistance: 24) {
                guard enabled else { return }
                stop()
                fired += 1
                action()
            } onPressingChanged: { pressing in
                if pressing, enabled { start() } else { stop() }
            }
            .sensoryFeedback(.impact(weight: .medium), trigger: fired)
            .onDisappear { rumbling?.cancel() }
    }

    private func start() {
        rumbling?.cancel()
        rumbling = Task { @MainActor in
            try? await Task.sleep(for: .seconds(Self.settle))
            guard !Task.isCancelled else { return }
            withAnimation(.easeIn(duration: Self.hold - Self.settle)) { pressed = true }
            await Self.rumble(for: Self.hold - Self.settle)
        }
    }

    private func stop() {
        rumbling?.cancel()
        rumbling = nil
        if pressed {
            withAnimation(.spring(duration: 0.3, bounce: 0.35)) { pressed = false }
        }
    }

    /// Light taps, from about 9 a second to 40, a little firmer each time,
    /// until `duration` is over or the press ends.
    @MainActor
    private static func rumble(for duration: Double) async {
        let generator = UIImpactFeedbackGenerator(style: .light)
        generator.prepare()
        let clock = ContinuousClock()
        let begun = clock.now
        while !Task.isCancelled {
            let done = (clock.now - begun) / .seconds(1)
            guard done < duration - 0.03 else { return }
            let progress = done / duration
            generator.impactOccurred(intensity: 0.35 + 0.55 * progress)
            try? await Task.sleep(for: .seconds(0.11 - 0.085 * progress))
        }
    }
}

extension View {
    /// See `PressHold`.
    func pressHold(
        enabled: Bool = true, grow: CGFloat = 1.02, anchor: UnitPoint = .leading,
        onTap: (() -> Void)? = nil, action: @escaping () -> Void
    ) -> some View {
        modifier(PressHold(enabled: enabled, grow: grow, anchor: anchor, onTap: onTap, action: action))
    }

    /// A picture that opens on the whole screen: a tap, or a hold that
    /// answers like a title does.
    func picturePress(enabled: Bool = true, open: @escaping () -> Void) -> some View {
        pressHold(enabled: enabled, grow: 1.05, anchor: .center, onTap: { if enabled { open() } }, action: open)
    }

    /// "Tytuł w oryginale": a Polish title, held, turns into the source's
    /// own and stays so once the finger lifts (held, the finger covered the
    /// very title it showed); held again, it is Polish again. The titles
    /// fade like the Polish one does as it arrives. A new picture, card or
    /// study starts Polish. Without another title, holding does nothing.
    func titlePeek(enabled: Bool, peeking: Binding<Bool>, onTap: (() -> Void)? = nil) -> some View {
        pressHold(enabled: enabled, onTap: onTap) {
            withAnimation(.easeInOut(duration: 0.35)) { peeking.wrappedValue.toggle() }
        }
        // VoiceOver cannot hold: an action instead.
        .accessibilityActions {
            if enabled {
                Button(peeking.wrappedValue ? "Pokaż tytuł po polsku" : "Pokaż tytuł oryginalny") {
                    withAnimation(.easeInOut(duration: 0.35)) { peeking.wrappedValue.toggle() }
                }
            }
        }
        .onChange(of: enabled) { _, now in
            if !now { peeking.wrappedValue = false }
        }
    }

    /// The artist's name: a tap or a hold searches their other works.
    func artistPress(_ search: @escaping () -> Void) -> some View {
        pressHold(onTap: search, action: search)
            .accessibilityAddTraits(.isButton)
            .accessibilityHint(Text("Szuka innych dzieł tego autora"))
            .accessibilityAction { search() }
    }
}

/// A Polish title the card opened with: a second after, a soft lighter
/// band passes over it once, left to right, a hint that it answers a hold
/// ("Tytuł w oryginale"). Not again while the card stays, nor with Reduce
/// Motion.
struct Glint: ViewModifier {
    let enabled: Bool

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    /// 0: the band is still off the title's left edge, 1: past its right.
    @State private var at: CGFloat = 0
    @State private var sweeping = false
    @State private var done = false

    static let delay = 1.0
    static let duration = 1.2
    /// How much of the title shows in the band's middle.
    static let dip = 0.45
    /// Half the band's width, in parts of the title's.
    static let half: CGFloat = 0.22

    /// The band's edges, in parts of the title's width, `at` along the way.
    static func band(at: CGFloat) -> (start: CGFloat, end: CGFloat) {
        let middle = -half + at * (1 + 2 * half)
        return (middle - half, middle + half)
    }

    func body(content: Content) -> some View {
        content
            .modifier(GlintMask(at: at, on: sweeping))
            .task {
                guard enabled, !done, !reduceMotion else { return }
                try? await Task.sleep(for: .seconds(Self.delay))
                guard !Task.isCancelled else { return }
                done = true
                sweeping = true
                withAnimation(.easeInOut(duration: Self.duration)) {
                    at = 1
                } completion: {
                    sweeping = false
                }
            }
    }
}

/// The band itself: the title fades a touch towards the paper under it.
private struct GlintMask: ViewModifier, Animatable {
    var at: CGFloat
    let on: Bool

    var animatableData: CGFloat {
        get { at }
        set { at = newValue }
    }

    func body(content: Content) -> some View {
        let band = Glint.band(at: at)
        content.mask {
            LinearGradient(
                stops: [
                    .init(color: .black, location: 0),
                    .init(color: .black.opacity(on ? Glint.dip : 1), location: 0.5),
                    .init(color: .black, location: 1),
                ],
                startPoint: UnitPoint(x: band.start, y: 0.5),
                endPoint: UnitPoint(x: band.end, y: 0.5)
            )
        }
    }
}

extension View {
    /// See `Glint`. `enabled` counts as the title first shows.
    func titleGlint(enabled: Bool) -> some View {
        modifier(Glint(enabled: enabled))
    }
}

enum OriginalTitle {
    /// The title a hold shows: the source's, when it differs from the
    /// Polish one on screen.
    static func of(_ title: String, shown: String) -> String? {
        let title = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty, title.caseInsensitiveCompare(shown) != .orderedSame else { return nil }
        return title
    }
}
