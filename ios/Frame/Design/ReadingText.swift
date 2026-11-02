import SwiftUI
import UIKit

/// A long paragraph to read in full ("O dziele" on a work's card), laid out
/// by UIKit.
///
/// SwiftUI's `Text` sometimes measures a long paragraph a line or more
/// short on iOS 17 and later and cuts its end with "…", inside a
/// `ScrollView` and with `fixedSize` too (Apple feedback FB17223576 and
/// FB22577211): a work's description ended mid-word ("W lewym dolnym
/// ro…") with no way to read the rest. A `UITextView` measures what it
/// draws, and also lets a part of the text be selected and copied.
///
/// With `lines`, a shortened text: the whole sentences that fit in that
/// many lines (`SentenceClip`), ending on a full stop, not mid-word.
struct ReadingText: UIViewRepresentable {
    let text: String
    var size: CGFloat = 17
    var lineSpacing: CGFloat = 5
    var color: Color = Theme.ink.opacity(0.9)
    /// Shortened to whole sentences in about this many lines; nil: all of it.
    var lines: Int?
    /// Read so that a switch between light and dark updates the view.
    @Environment(\.colorScheme) private var colorScheme

    func makeUIView(context: Context) -> UITextView {
        // Shortened: TextKit 1, as SentenceClip counts the lines.
        let view = lines == nil ? UITextView() : UITextView(usingTextLayoutManager: false)
        view.isEditable = false
        view.isSelectable = true
        view.isScrollEnabled = false
        view.dataDetectorTypes = []
        view.backgroundColor = .clear
        view.textContainerInset = .zero
        view.textContainer.lineFragmentPadding = 0
        view.adjustsFontForContentSizeCategory = false
        view.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        return view
    }

    func updateUIView(_ view: UITextView, context: Context) {
        // Colours resolved here, so light and dark follow the page.
        let environment = context.environment
        let ink = UIColor(cgColor: color.resolve(in: environment).cgColor)
        view.tintColor = UIColor(cgColor: Theme.ink.resolve(in: environment).cgColor)
        let shown = Shown(text: text, size: size, lineSpacing: lineSpacing, ink: ink, lines: lines)
        let before = context.coordinator.shown
        guard before != shown else { return }
        context.coordinator.shown = shown
        let base = UIFont.systemFont(ofSize: size)
        let font = base.fontDescriptor.withDesign(.serif).map { UIFont(descriptor: $0, size: size) } ?? base
        let paragraph = NSMutableParagraphStyle()
        paragraph.lineSpacing = lineSpacing
        let attributed = NSAttributedString(
            string: text,
            attributes: [.font: font, .foregroundColor: ink, .paragraphStyle: paragraph]
        )
        let coordinator = context.coordinator
        coordinator.full = attributed
        coordinator.cut = nil
        let clip = coordinator.clip(lines: lines)
        let transaction = context.transaction
        if let before, before.text != text, transaction.animation != nil, !transaction.disablesAnimations {
            // Another text in an animated change (the Polish one arriving,
            // "Pokaż oryginał"): it fades in over the one before.
            UIView.transition(
                with: view, duration: 0.5, options: [.transitionCrossDissolve, .allowUserInteraction],
                animations: { coordinator.show(clip, in: view) }
            )
        } else {
            coordinator.show(clip, in: view)
        }
        view.invalidateIntrinsicContentSize()
    }

    func sizeThatFits(_ proposal: ProposedViewSize, uiView: UITextView, context: Context) -> CGSize? {
        guard let width = proposal.width, width.isFinite, width > 0 else { return nil }
        if lines != nil {
            // The sentences that fit depend on the width, known only here.
            let coordinator = context.coordinator
            if coordinator.width != width {
                coordinator.width = width
                coordinator.cut = nil
            }
            let clip = coordinator.clip(lines: lines)
            if coordinator.shownClip != clip { coordinator.show(clip, in: uiView) }
        }
        let fitted = uiView.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude))
        return CGSize(width: width, height: ceil(fitted.height))
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    /// What the view shows: set again only when it changes, so a selection
    /// stays while the card updates around it.
    struct Shown: Equatable {
        var text: String
        var size: CGFloat
        var lineSpacing: CGFloat
        var ink: UIColor
        var lines: Int?
    }

    final class Coordinator {
        var shown: Shown?
        /// The whole text, and for a shortened one its last width and cut.
        var full = NSAttributedString()
        var width: CGFloat?
        var cut: SentenceClip.Clip?
        /// What the view was given last, so a selection stays across layouts.
        var shownClip: SentenceClip.Clip?

        func clip(lines: Int?) -> SentenceClip.Clip {
            guard let lines else { return SentenceClip.Clip(text: full, lines: 0) }
            // Width not known yet: cut as before until it is.
            guard let width else { return SentenceClip.Clip(text: full, lines: lines) }
            if let cut { return cut }
            let made = SentenceClip.clip(full, width: width, lines: lines)
            cut = made
            return made
        }

        func show(_ clip: SentenceClip.Clip, in view: UITextView) {
            shownClip = clip
            view.textContainer.maximumNumberOfLines = clip.lines
            view.textContainer.lineBreakMode = clip.lines > 0 ? .byTruncatingTail : .byWordWrapping
            view.attributedText = clip.text
        }
    }
}
