import SwiftUI

/// "Tytuł w oryginale": a Polish title, held for a moment, shows the
/// museum's own for as long as the finger stays, with a light tap of the
/// haptics, fading both ways like the Polish title does as it arrives.
/// A quick tap keeps doing what it did (Teraz: opens the card). Nothing
/// on screen tells about it.
struct TitlePeek: ViewModifier {
    /// There is another title to show: without one, holding does nothing.
    let enabled: Bool
    @Binding var peeking: Bool
    var onTap: (() -> Void)?

    static var fade: Animation { .easeInOut(duration: 0.35) }

    func body(content: Content) -> some View {
        content
            .contentShape(Rectangle())
            // Before the long press, or the hold would never start.
            .onTapGesture { onTap?() }
            .onLongPressGesture(minimumDuration: 0.3, maximumDistance: 24) {
                guard enabled else { return }
                withAnimation(Self.fade) { peeking = true }
            } onPressingChanged: { pressing in
                guard !pressing, peeking else { return }
                withAnimation(Self.fade) { peeking = false }
            }
            .sensoryFeedback(.impact(weight: .light), trigger: peeking) { _, now in now }
            // VoiceOver cannot hold: the action switches until asked back.
            .accessibilityActions {
                if enabled {
                    Button(peeking ? "Pokaż tytuł po polsku" : "Pokaż tytuł oryginalny") {
                        withAnimation(Self.fade) { peeking.toggle() }
                    }
                }
            }
            .onChange(of: enabled) { _, now in
                if !now { peeking = false }
            }
    }
}

extension View {
    /// See `TitlePeek`.
    func titlePeek(enabled: Bool, peeking: Binding<Bool>, onTap: (() -> Void)? = nil) -> some View {
        modifier(TitlePeek(enabled: enabled, peeking: peeking, onTap: onTap))
    }
}

/// The quiet line under a held title: where it comes from.
struct TitlePeekNote: View {
    let source: String

    var body: some View {
        Text(Self.text(source))
            .font(.caption)
            .foregroundStyle(Theme.inkSoft)
            .transition(.opacity)
    }

    /// Commons, Europeana, Openverse and WikiArt are not museums.
    static func text(_ source: String) -> String {
        ["wmc", "europeana", "openverse", "wikiart"].contains(source)
            ? "Tytuł ze źródła, \(Names.source(source))"
            : "Tytuł z muzeum"
    }

    /// The title the hold shows: the source's, when it differs from the
    /// Polish one on screen.
    static func original(_ title: String, shown: String) -> String? {
        let title = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty, title.caseInsensitiveCompare(shown) != .orderedSame else { return nil }
        return title
    }
}
