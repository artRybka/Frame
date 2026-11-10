import SwiftUI
import UIKit

/// A work's fragments (the museum's photographs of a scroll's parts, a
/// Commons tile set; Mateusz 2026-11-09): sharp where the whole, fit into
/// the frame, is not. Each is a work of its own: a tap opens its card.

/// Loads them once per work, for the card and the study.
@MainActor
enum Fragments {
    /// Answers kept while the app runs, by the id asked about.
    private static var known: [String: FragmentsView] = [:]

    static func cached(_ itemID: String) -> FragmentsView? { known[itemID] }

    static func load(_ itemID: String, backend: any FrameBackend) async -> FragmentsView? {
        if let view = known[itemID] { return view }
        guard let view = try? await backend.fragments(itemID: itemID) else { return nil }
        if known.count > 300 { known.removeAll() }
        known[itemID] = view
        // Their cards open filled from the first frame.
        for fragment in view.fragments { ItemPeeks.keep(fragment.item) }
        if let whole = view.whole { ItemPeeks.keep(whole.item) }
        return view
    }

    /// Those of the picture shown (a Commons copy standing in for the work
    /// brings its tile set), else the work's own.
    static func load(shownWith item: Item, backend: any FrameBackend) async -> FragmentsView? {
        let shown = item.fragmentsID
        if shown != item.id, let view = await load(shown, backend: backend), !view.fragments.isEmpty {
            return view
        }
        return await load(item.id, backend: backend)
    }

    /// How far the full screen zooms into the work's tile set on this
    /// screen ("17×" on its card); nil without one.
    static func depth(_ view: FragmentsView?, scale: CGFloat) -> Int? {
        guard let view, view.tiled else { return nil }
        let screen = UIApplication.shared.connectedScenes
            .compactMap { ($0 as? UIWindowScene)?.screen.bounds.size }
            .first ?? CGSize(width: 393, height: 852)
        return ZoomTile.depth(of: view, screen: screen, scale: scale)
    }

    /// The title without the server's "(fragment 5/14)": the card says it
    /// on a tag of its own.
    static func title(_ title: String) -> String {
        guard let range = title.range(
            of: #"\s*\((fragment|fragmenty?)\s*\d+\s*(/|z)\s*\d+\)\s*$"#,
            options: [.regularExpression, .caseInsensitive]
        ) else { return title }
        return String(title[..<range.lowerBound])
    }

    /// "Fragment 5 z 14".
    static func label(_ item: Item) -> String? {
        guard item.isFragment, let part = item.part, let parts = item.parts, parts > 0 else { return nil }
        return "Fragment \(part) z \(parts)"
    }
}

/// One row of small fragments scrolled sideways, numbered; the one whose
/// card this is (`current`) outlined and scrolled into view.
struct FragmentStrip: View {
    let fragments: [RemoteItem]
    var current: String?
    var height: CGFloat = 78

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 8) {
                    ForEach(Array(fragments.enumerated()), id: \.element.id) { index, fragment in
                        let isCurrent = fragment.id == current
                        NavigationLink(value: fragment.id) {
                            VStack(alignment: .leading, spacing: 4) {
                                ArtImage(
                                    ref: fragment.thumb,
                                    placeholder: fragment.item.placeholderColor,
                                    maxPixel: 500
                                )
                                .frame(width: height * shape(fragment), height: height)
                                .clipShape(RoundedRectangle(cornerRadius: 3, style: .continuous))
                                .overlay {
                                    if isCurrent {
                                        RoundedRectangle(cornerRadius: 5, style: .continuous)
                                            .stroke(Theme.vermilion, lineWidth: 2.5)
                                            .padding(-3)
                                    }
                                }
                                Text(isCurrent ? "\(index + 1) · ten" : "\(index + 1)")
                                    .font(.caption2.weight(isCurrent ? .semibold : .regular))
                                    .foregroundStyle(isCurrent ? Theme.vermilion : Theme.inkSoft)
                            }
                            .padding(.top, 3)
                        }
                        .buttonStyle(.plain)
                        .disabled(isCurrent)
                        .id(fragment.id)
                        .accessibilityLabel("Fragment \(index + 1) z \(fragments.count)")
                    }
                }
                .padding(.horizontal, 3)
                .scrollTargetLayout()
            }
            .scrollTargetBehavior(.viewAligned)
            .scrollClipDisabled()
            .onAppear {
                if let current { proxy.scrollTo(current, anchor: .leading) }
            }
        }
    }

    /// Width / height, kept between a tall tile and a long strip.
    private func shape(_ fragment: RemoteItem) -> CGFloat {
        CGFloat(max(0.6, min(3.0, fragment.summary.aspectRatio)))
    }
}

/// On a fragment's card: the whole work it is part of, a tap away.
struct WholeWorkLink: View {
    let whole: RemoteItem

    var body: some View {
        NavigationLink(value: whole.id) {
            HStack(spacing: 12) {
                ArtImage(ref: whole.thumb, placeholder: whole.item.placeholderColor, maxPixel: 600)
                    .frame(width: 120, height: max(8, min(60, 120 / CGFloat(max(whole.summary.aspectRatio, 0.5)))))
                    .clipShape(RoundedRectangle(cornerRadius: 2, style: .continuous))
                VStack(alignment: .leading, spacing: 2) {
                    Text("Całe dzieło")
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(Theme.ink)
                    Text(Fragments.title(whole.item.title))
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .lineLimit(1)
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(Theme.inkSoft)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(Theme.card, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(Theme.hairline))
        }
        .buttonStyle(.plain)
    }
}
