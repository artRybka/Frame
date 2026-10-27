import SwiftUI

/// How far a scroll view's content is pulled up past its end, and whether a
/// finger is on it. Kept apart from the views that show the content, so
/// that only the end of the list redraws while it is pulled.
@Observable
final class EndPull {
    var distance: CGFloat = 0
    var dragging = false
}

extension View {
    /// Tells `pull` how far this scroll view is pulled past its end (from
    /// iOS 18; before that the end of the list takes a tap).
    func readsEndPull(_ pull: EndPull) -> some View {
        modifier(EndPullReader(pull: pull))
    }
}

private struct EndPullReader: ViewModifier {
    let pull: EndPull

    func body(content: Content) -> some View {
        if #available(iOS 18, *) {
            content
                .onScrollGeometryChange(for: CGFloat.self) { geometry in
                    // Where the offset rests at the end (at the top while
                    // the content is shorter than the scroll view).
                    let end = max(
                        geometry.contentSize.height + geometry.contentInsets.bottom - geometry.containerSize.height,
                        -geometry.contentInsets.top
                    )
                    return max(0, (geometry.contentOffset.y - end).rounded())
                } action: { _, distance in
                    pull.distance = distance
                }
                .onScrollPhaseChange { _, phase in
                    pull.dragging = phase == .interacting
                }
        } else {
            content
        }
    }
}

/// The end of a list that goes on: the icon's squares at play, and pulling
/// the list up past them asks for more (as does a tap).
struct PullForMore: View {
    let loading: Bool
    let action: () -> Void
    @Environment(EndPull.self) private var pull: EndPull?
    /// Set again once the pull lets go, so one pull asks once.
    @State private var armed = true
    @State private var asked = 0

    /// How far to pull past the end.
    static let threshold: CGFloat = 64

    private static var hint: String {
        if #available(iOS 18, *) { return "Przeciągnij po więcej" }
        return "Stuknij po więcej"
    }

    var body: some View {
        let distance = pull?.distance ?? 0
        VStack(spacing: 2) {
            SquaresAnimation(inScreenMiddle: false, tapForNext: false)
                .frame(height: 96)
                .frame(maxWidth: .infinity)
            Text(loading ? "Doczytuję…" : Self.hint)
                .font(.footnote)
                .foregroundStyle(Theme.inkSoft)
        }
        .padding(.bottom, 8)
        .contentShape(Rectangle())
        .onTapGesture(perform: ask)
        .onChange(of: distance) { _, distance in
            if distance < 8 {
                armed = true
            } else if distance >= Self.threshold, armed, pull?.dragging == true {
                armed = false
                ask()
            }
        }
        .sensoryFeedback(.impact(weight: .light), trigger: asked)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(loading ? "Doczytuję" : "Więcej")
        .accessibilityAddTraits(.isButton)
        .accessibilityAction { ask() }
    }

    private func ask() {
        guard !loading else { return }
        asked += 1
        action()
    }
}
