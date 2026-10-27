import SwiftUI
import UIKit

/// The end of a list that goes on: the icon's squares at play, and pulling
/// the list up past them asks for more (as does a tap).
struct PullForMore: View {
    let loading: Bool
    let action: () -> Void
    @State private var asked = 0

    /// How far to pull the content past its end.
    static let threshold: CGFloat = 56

    var body: some View {
        VStack(spacing: 2) {
            SquaresAnimation(inScreenMiddle: false, tapForNext: false)
                .frame(height: 96)
                .frame(maxWidth: .infinity)
            Text(loading ? "Doczytuję…" : "Przeciągnij po więcej")
                .font(.footnote)
                .foregroundStyle(Theme.inkSoft)
        }
        .padding(.bottom, 8)
        .contentShape(Rectangle())
        .onTapGesture(perform: ask)
        .background(EndPullDetector(threshold: Self.threshold, onPull: ask))
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

/// Watches the scroll view the list is in, straight from UIKit: once per
/// drag, the finger pulling the content `threshold` points up past its end
/// calls `onPull`. (SwiftUI's own scroll geometry didn't report the pull on
/// the device.)
private struct EndPullDetector: UIViewRepresentable {
    let threshold: CGFloat
    let onPull: () -> Void

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> Probe {
        let probe = Probe()
        probe.isUserInteractionEnabled = false
        probe.coordinator = context.coordinator
        return probe
    }

    func updateUIView(_ probe: Probe, context: Context) {
        context.coordinator.threshold = threshold
        context.coordinator.onPull = onPull
    }

    static func dismantleUIView(_ probe: Probe, coordinator: Coordinator) {
        coordinator.watch(nil)
    }

    /// Finds the scroll view once it is in a window.
    final class Probe: UIView {
        weak var coordinator: Coordinator?

        override func didMoveToWindow() {
            super.didMoveToWindow()
            var view = window == nil ? nil : superview
            while let found = view, !(found is UIScrollView) { view = found.superview }
            coordinator?.watch(view as? UIScrollView)
        }
    }

    @MainActor
    final class Coordinator: NSObject {
        var threshold: CGFloat = 56
        var onPull: () -> Void = {}
        private weak var scrollView: UIScrollView?
        /// Set when a drag begins, so one drag asks once.
        private var armed = false

        func watch(_ scrollView: UIScrollView?) {
            guard scrollView !== self.scrollView else { return }
            self.scrollView?.panGestureRecognizer.removeTarget(self, action: #selector(panned))
            self.scrollView = scrollView
            scrollView?.panGestureRecognizer.addTarget(self, action: #selector(panned))
        }

        @objc private func panned(_ pan: UIPanGestureRecognizer) {
            guard let scrollView else { return }
            switch pan.state {
            case .began:
                armed = true
            case .changed:
                // Where the offset rests at the end (at the top while the
                // content is shorter than the scroll view).
                let insets = scrollView.adjustedContentInset
                let end = max(
                    scrollView.contentSize.height + insets.bottom - scrollView.bounds.height, -insets.top
                )
                if armed, scrollView.contentOffset.y - end >= threshold {
                    armed = false
                    onPull()
                }
            default:
                armed = false
            }
        }
    }
}
