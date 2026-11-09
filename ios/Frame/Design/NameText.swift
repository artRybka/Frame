import SwiftUI
import UIKit

/// A short line that must show whole, such as the artist's name under a
/// work's title ("Piotr Mondrian"), laid out by UIKit.
///
/// SwiftUI's `Text` in the serif face sometimes measures itself a hair
/// narrower than it draws (as `ReadingText` notes, FB17223576): a one-line
/// name then lost its end to "…" ("Piotr Mondri…", Mateusz 2026-11-10)
/// with half the line empty beside it. A `UILabel` draws in the size it
/// measured, and a name too long for the line wraps instead.
struct NameText: UIViewRepresentable {
    let text: String
    var size: CGFloat = 19
    var weight: UIFont.Weight = .regular
    var color: Color = Theme.ink
    /// Read so that a switch between light and dark updates the label.
    @Environment(\.colorScheme) private var colorScheme

    func makeUIView(context: Context) -> UILabel {
        let label = UILabel()
        label.numberOfLines = 0
        label.lineBreakMode = .byWordWrapping
        label.adjustsFontForContentSizeCategory = false
        label.backgroundColor = .clear
        // Holds (the artist's search) are SwiftUI's, over the label.
        label.isUserInteractionEnabled = false
        label.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        return label
    }

    func updateUIView(_ label: UILabel, context: Context) {
        let base = UIFont.systemFont(ofSize: size, weight: weight)
        label.font = base.fontDescriptor.withDesign(.serif).map { UIFont(descriptor: $0, size: size) } ?? base
        label.textColor = UIColor(cgColor: color.resolve(in: context.environment).cgColor)
        label.text = text
        label.invalidateIntrinsicContentSize()
    }

    func sizeThatFits(_ proposal: ProposedViewSize, uiView: UILabel, context: Context) -> CGSize? {
        let width = proposal.width.flatMap { $0.isFinite && $0 > 0 ? $0 : nil } ?? .greatestFiniteMagnitude
        let fitted = uiView.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude))
        // Its own width (a hold answers on the name, not beside it), never
        // wider than offered; rounded up so nothing is cut.
        return CGSize(width: min(ceil(fitted.width), width), height: ceil(fitted.height))
    }
}
