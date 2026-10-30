import SwiftUI
import UIKit

/// The cards and, away from "Teraz", the bar following a picture to the
/// frame: at the bottom, above the tab bar.
struct NoticeStack: View {
    @Environment(AppModel.self) private var model
    /// Where the cards are, in the window: touches elsewhere go through.
    var reportFrame: (CGRect) -> Void = { _ in }

    private var sendBar: DisplayProgress? {
        model.notices.nowTabOpen ? nil : model.displayProgress
    }

    var body: some View {
        VStack(spacing: 8) {
            ForEach(model.notices.items) { notice in
                NoticeCard(notice: notice) { model.notices.close(notice.id) }
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
            if let progress = sendBar {
                DisplayProgressBar(progress: progress, compact: true)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .padding(.horizontal, 16)
        .background {
            GeometryReader { geo in
                Color.clear.onChange(of: geo.frame(in: .global), initial: true) { _, frame in
                    reportFrame(frame)
                }
            }
        }
        .padding(.bottom, 58)  // above the tab bar
        .frame(maxHeight: .infinity, alignment: .bottom)
        .animation(.snappy, value: model.notices.items)
        .animation(.easeInOut, value: model.displayProgress == nil)
        .animation(.easeInOut, value: model.notices.nowTabOpen)
    }
}

/// One card, in the look of `DisplayProgressBar`.
struct NoticeCard: View {
    let notice: Notice
    var close: () -> Void = {}

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(alignment: .top, spacing: 8) {
                icon
                    .frame(width: 16, height: 18)
                VStack(alignment: .leading, spacing: 2) {
                    Text(notice.title)
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(Theme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                        .contentTransition(.opacity)
                    if let detail = notice.detail {
                        Text(detail)
                            .font(.caption)
                            .foregroundStyle(Theme.inkSoft)
                            .lineLimit(4)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                Spacer(minLength: 8)
                trailing
            }
            // A bar only when the share done is known; otherwise the spinner says it all.
            if let fraction = notice.fraction {
                NoticeBar(fraction: fraction, tint: tint)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 11)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: Theme.corner, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: Theme.corner, style: .continuous)
                .strokeBorder(Theme.hairline.opacity(0.6))
        )
        .shadow(color: .black.opacity(0.08), radius: 10, y: 4)
        .animation(.easeInOut(duration: 0.3), value: notice.kind)
        .contentShape(Rectangle())
        .onTapGesture { if notice.kind.transient { close() } }
        .gesture(
            DragGesture(minimumDistance: 12).onEnded { drag in
                if notice.kind != .working, drag.translation.height > 24 { close() }
            }
        )
        .accessibilityElement(children: .combine)
        .accessibilityAction(named: "Zamknij") { if notice.kind != .working { close() } }
    }

    private var tint: Color {
        switch notice.kind {
        case .working: Theme.vermilion
        case .done: Theme.good
        case .info: Theme.accent
        case .warning: Theme.warn
        case .error: Theme.bad
        }
    }

    @ViewBuilder private var icon: some View {
        switch notice.kind {
        case .working:
            ProgressView()
                .controlSize(.mini)
                .tint(Theme.vermilion)
        case .done: symbol("checkmark.circle.fill")
        case .info: symbol("info.circle.fill")
        case .warning: symbol("exclamationmark.circle.fill")
        case .error: symbol("xmark.circle.fill")
        }
    }

    private func symbol(_ name: String) -> some View {
        Image(systemName: name)
            .font(.footnote)
            .foregroundStyle(tint)
            .transition(.scale.combined(with: .opacity))
    }

    @ViewBuilder private var trailing: some View {
        switch notice.kind {
        case .working:
            Text(notice.count ?? "")
                .font(.caption.weight(.medium).monospacedDigit())
                .foregroundStyle(Theme.inkSoft)
                .padding(.top, 1)
        case .warning, .error:
            Button(action: close) {
                Image(systemName: "xmark")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Theme.inkSoft)
                    .padding(6)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .padding(-6)
            .accessibilityLabel("Zamknij")
        case .done, .info:
            EmptyView()
        }
    }
}

/// The card's bar, filled as far as the work is.
private struct NoticeBar: View {
    let fraction: Double
    let tint: Color

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(Theme.ink.opacity(0.1))
                Capsule()
                    .fill(tint)
                    .frame(width: max(6, geo.size.width * fraction))
            }
        }
        .frame(height: 6)
        .animation(.linear(duration: 0.6), value: fraction)
    }
}

// MARK: Window

/// The cards live in a window of their own above the app's, so they show
/// over sheets too. Touches outside the cards go through to the app.
final class NoticeWindow: UIWindow {
    var cardFrame: CGRect = .zero

    override func hitTest(_ point: CGPoint, with event: UIEvent?) -> UIView? {
        guard cardFrame.height > 0, cardFrame.contains(point) else { return nil }
        return super.hitTest(point, with: event)
    }
}

/// Lets the app below say how the status bar looks: the notice window
/// must not change it (a picture's full screen hides it).
private final class NoticeHost: UIHostingController<AnyView> {
    weak var below: UIWindow?

    private var top: UIViewController? {
        var controller = below?.rootViewController
        while let presented = controller?.presentedViewController, !presented.isBeingDismissed {
            controller = presented
        }
        return controller?.childForStatusBarHidden ?? controller
    }

    override var prefersStatusBarHidden: Bool { top?.prefersStatusBarHidden ?? false }
    override var preferredStatusBarStyle: UIStatusBarStyle { top?.preferredStatusBarStyle ?? .default }
}

/// Puts the notice window over the scene RootView is in; it is shown only
/// while there is something on it.
struct NoticeWindowInstaller: UIViewRepresentable {
    let model: AppModel

    func makeUIView(context: Context) -> Anchor {
        Anchor(model: model)
    }

    func updateUIView(_ view: Anchor, context: Context) {}

    final class Anchor: UIView {
        private let model: AppModel
        private var overlay: NoticeWindow?
        private var hiding: Task<Void, Never>?

        init(model: AppModel) {
            self.model = model
            super.init(frame: .zero)
            isUserInteractionEnabled = false
        }

        @available(*, unavailable)
        required init?(coder: NSCoder) { fatalError() }

        override func didMoveToWindow() {
            super.didMoveToWindow()
            guard overlay == nil, let main = window, let scene = main.windowScene else { return }
            let overlay = NoticeWindow(windowScene: scene)
            let host = NoticeHost(
                rootView: AnyView(
                    NoticeStack { [weak overlay] frame in overlay?.cardFrame = frame }
                        .environment(model)
                )
            )
            host.below = main
            host.view.backgroundColor = .clear
            overlay.rootViewController = host
            overlay.windowLevel = UIWindow.Level(rawValue: UIWindow.Level.normal.rawValue + 1)
            overlay.backgroundColor = .clear
            overlay.isHidden = true
            self.overlay = overlay
            watch()
        }

        private func watch() {
            let shown = withObservationTracking {
                !model.notices.items.isEmpty || (!model.notices.nowTabOpen && model.displayProgress != nil)
            } onChange: { [weak self] in
                Task { @MainActor in self?.watch() }
            }
            show(shown)
        }

        /// Hidden while empty, so it never stands between the app and the
        /// status bar; a moment late, for the last card to slide away.
        private func show(_ shown: Bool) {
            hiding?.cancel()
            guard let overlay else { return }
            if shown {
                overlay.isHidden = false
                overlay.rootViewController?.setNeedsStatusBarAppearanceUpdate()
            } else {
                hiding = Task { @MainActor [weak overlay] in
                    try? await Task.sleep(for: .seconds(0.6))
                    guard !Task.isCancelled else { return }
                    overlay?.isHidden = true
                }
            }
        }
    }
}
