import SwiftUI

/// A press that answers as it starts: a light tap of the haptics and the
/// text growing a little while the finger stays; held long enough, `action`
/// runs with a firmer tap and the text settles back. A quick tap does
/// `onTap`. Used by "Tytuł w oryginale" and the artist's name (held: their
/// other works on Szukaj).
struct PressHold: ViewModifier {
    var enabled = true
    var onTap: (() -> Void)?
    let action: () -> Void

    @State private var pressed = false
    @State private var starting: Task<Void, Never>?
    @State private var fired = 0

    /// How long the finger stays before `action`.
    static let hold = 0.35
    /// A touch shorter than this (a tap, a scroll starting) shows nothing.
    private static let settle = 0.08

    func body(content: Content) -> some View {
        content
            .scaleEffect(pressed ? 1.05 : 1, anchor: .leading)
            .contentShape(Rectangle())
            // Before the long press, or the hold would never start.
            .onTapGesture { onTap?() }
            .onLongPressGesture(minimumDuration: Self.hold, maximumDistance: 24) {
                guard enabled else { return }
                fired += 1
                action()
            } onPressingChanged: { pressing in
                starting?.cancel()
                if pressing, enabled {
                    starting = Task { @MainActor in
                        try? await Task.sleep(for: .seconds(Self.settle))
                        guard !Task.isCancelled else { return }
                        withAnimation(.easeOut(duration: Self.hold - Self.settle)) { pressed = true }
                    }
                } else if pressed {
                    withAnimation(.spring(duration: 0.3, bounce: 0.35)) { pressed = false }
                }
            }
            .sensoryFeedback(.impact(weight: .light), trigger: pressed) { _, now in now }
            .sensoryFeedback(.impact(weight: .medium), trigger: fired)
    }
}

extension View {
    /// See `PressHold`.
    func pressHold(enabled: Bool = true, onTap: (() -> Void)? = nil, action: @escaping () -> Void) -> some View {
        modifier(PressHold(enabled: enabled, onTap: onTap, action: action))
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

enum OriginalTitle {
    /// The title a hold shows: the source's, when it differs from the
    /// Polish one on screen.
    static func of(_ title: String, shown: String) -> String? {
        let title = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty, title.caseInsensitiveCompare(shown) != .orderedSame else { return nil }
        return title
    }
}
