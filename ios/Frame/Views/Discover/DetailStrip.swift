import SwiftUI

/// A work's details (Mateusz 2026-11-11): pictures of a part of it that the
/// server keeps apart from the catalogue as copies (Commons' file of the
/// drummer from "The Night Watch", a detail found inside another copy's
/// picture). On the work's card they come for free: a row to swipe, a tap
/// opens the detail on the whole screen.

/// Loads them once per work while the app runs.
@MainActor
enum Details {
    private static var known: [String: DetailsView] = [:]

    static func cached(_ itemID: String) -> DetailsView? { known[itemID] }

    static func load(_ itemID: String, backend: any FrameBackend) async -> DetailsView? {
        if let view = known[itemID] { return view }
        guard let view = try? await backend.details(itemID: itemID) else { return nil }
        if known.count > 300 { known.removeAll() }
        known[itemID] = view
        if let whole = view.whole { ItemPeeks.keep(whole.item) }
        return view
    }
}

/// One row of details scrolled sideways; a tap opens one on the whole
/// screen, grown out of its thumbnail.
struct DetailStrip: View {
    let details: [RemoteItem]
    var height: CGFloat = 96
    @State private var opened: Item?
    @Namespace private var zoomSpace

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(alignment: .top, spacing: 8) {
                ForEach(details) { detail in
                    Button {
                        opened = detail.item
                    } label: {
                        ArtImage(
                            ref: detail.thumb,
                            placeholder: detail.item.placeholderColor,
                            maxPixel: 500
                        )
                        .frame(width: height * shape(detail), height: height)
                        .clipShape(RoundedRectangle(cornerRadius: 3, style: .continuous))
                        .matchedTransitionSource(id: detail.id, in: zoomSpace) {
                            $0.clipShape(RoundedRectangle(cornerRadius: 3, style: .continuous))
                        }
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(detail.item.displayTitle.isEmpty ? "Detal" : detail.item.displayTitle)
                    .accessibilityHint(Text("Otwiera detal na całym ekranie"))
                }
            }
            .padding(.horizontal, 3)
            .scrollTargetLayout()
        }
        .scrollTargetBehavior(.viewAligned)
        .scrollClipDisabled()
        .fullScreenCover(item: $opened) { item in
            OriginalViewer(item: item)
                .navigationTransition(.zoom(sourceID: item.id, in: zoomSpace))
        }
    }

    /// Width / height, kept between a tall cut and a long strip.
    private func shape(_ detail: RemoteItem) -> CGFloat {
        CGFloat(max(0.6, min(2.2, detail.summary.aspectRatio)))
    }
}
