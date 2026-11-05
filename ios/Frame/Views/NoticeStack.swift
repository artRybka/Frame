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

/// One card, in the look of `DisplayProgressBar`: frosted glass, ink type
/// large and dark enough to read over any picture, the kind in a small soft
/// disc, and an edge and shadow that lift it off the pictures below.
struct NoticeCard: View {
    let notice: Notice
    var close: () -> Void = {}

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .center, spacing: 11) {
                icon
                    .frame(width: 22, height: 22)
                VStack(alignment: .leading, spacing: 3) {
                    Text(notice.title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(Theme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                        .contentTransition(.opacity)
                    if let detail = notice.detail {
                        Text(detail)
                            .font(.footnote)
                            .foregroundStyle(Theme.glassInk)
                            .lineLimit(4)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                Spacer(minLength: 8)
                trailing
            }
            // A bar only when the share done is known; otherwise the spinner says it all.
            if let fraction = notice.fraction {
                NoticeBar(fraction: fraction)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 13)
        .frame(maxWidth: .infinity, alignment: .leading)
        .noticeGlass()
        .animation(.easeInOut(duration: 0.3), value: notice.kind)
        .contentShape(Rectangle())
        .onTapGesture {
            if let action = notice.action {
                close()
                action.run()
            } else if notice.kind.transient {
                close()
            }
        }
        .gesture(
            DragGesture(minimumDistance: 12).onEnded { drag in
                if notice.kind != .working, drag.translation.height > 24 { close() }
            }
        )
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(notice.action == nil ? [] : .isButton)
        .accessibilityAction {
            guard let action = notice.action else { return }
            close()
            action.run()
        }
        .accessibilityAction(named: "Zamknij") { if notice.kind != .working { close() } }
    }

    @ViewBuilder private var icon: some View {
        switch notice.kind {
        case .working:
            ProgressView()
                .controlSize(.small)
                .tint(Theme.ink)
                .opacity(0.6)
        case .done: NoticeMark(kind: .done)
        case .info: NoticeMark(kind: .info)
        case .warning: NoticeMark(kind: .warning)
        case .error: NoticeMark(kind: .error)
        }
    }

    @ViewBuilder private var trailing: some View {
        switch notice.kind {
        case .working:
            Text(notice.count ?? "")
                .font(.footnote.weight(.medium).monospacedDigit())
                .foregroundStyle(Theme.glassInk)
        case _ where notice.action != nil:
            HStack(spacing: 10) {
                Text(notice.action?.label ?? "")
                    .font(.caption2.weight(.semibold))
                    .tracking(LabelButton.tracking)
                    .textCase(.uppercase)
                    .foregroundStyle(Theme.paper)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(LabelButton.shape.fill(Theme.ink))
                closeButton
            }
        case .warning, .error:
            closeButton
        case .done, .info:
            EmptyView()
        }
    }

    private var closeButton: some View {
        Button(action: close) {
            Image(systemName: "xmark")
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(Theme.ink)
                .frame(width: 24, height: 24)
                .background(Theme.ink.opacity(0.08), in: Circle())
                .padding(6)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(-6)
        .accessibilityLabel("Zamknij")
    }
}

/// The kind of a card: its glyph in paper on a small disc of soft colour.
struct NoticeMark: View {
    let kind: Notice.Kind
    /// Another glyph on the kind's disc (a clock for a picture that waits).
    var symbol: String? = nil

    var body: some View {
        Image(systemName: symbol ?? glyph)
            .font(.system(size: 10, weight: .heavy))
            .foregroundStyle(Theme.paper)
            .frame(width: 20, height: 20)
            .background(color, in: Circle())
            .transition(.scale.combined(with: .opacity))
    }

    private var glyph: String {
        switch kind {
        case .done: "checkmark"
        case .info: "info"
        case .warning: "exclamationmark"
        case .error, .working: "xmark"
        }
    }

    private var color: Color {
        switch kind {
        case .done: Theme.markGood
        case .info, .working: Theme.markInfo
        case .warning: Theme.markWarn
        case .error: Theme.markBad
        }
    }
}

extension View {
    /// The cards' and the send bar's frosted glass, with a light inner edge
    /// and a soft shadow, so they stand off busy pictures below.
    func noticeGlass() -> some View { modifier(NoticeGlass()) }
}

private struct NoticeGlass: ViewModifier {
    @Environment(\.colorScheme) private var scheme

    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: Theme.corner, style: .continuous)
        let dark = scheme == .dark
        return content
            .background(.ultraThinMaterial, in: shape)
            .overlay(shape.strokeBorder(Color.white.opacity(dark ? 0.14 : 0.5), lineWidth: 1))
            .overlay(shape.stroke(Color.black.opacity(dark ? 0.5 : 0.12), lineWidth: 0.5))
            .shadow(color: .black.opacity(dark ? 0.4 : 0.15), radius: 11, y: 7)
    }
}

/// The card's bar, filled as far as the work is.
private struct NoticeBar: View {
    let fraction: Double

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(Theme.ink.opacity(0.1))
                Capsule()
                    .fill(Theme.ink)
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
