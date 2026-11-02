import SwiftUI

/// "Tytuł w oryginale": a Polish title, held for a moment, turns into the
/// museum's own and stays so once the finger lifts (held, the finger
/// covered the very title it showed); held again, it is Polish again.
/// A light tap of the haptics each way; the titles fade like the Polish
/// one does as it arrives. A new picture or card starts Polish. A quick
/// tap keeps doing what it did (Teraz: opens the card).
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
                withAnimation(Self.fade) { peeking.toggle() }
            }
            .sensoryFeedback(.impact(weight: .light), trigger: peeking)
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
