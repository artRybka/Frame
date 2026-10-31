import SwiftUI

// A vertical ScrollView is only as wide as what it holds. While a page has
// nothing but a spinner (or an empty list) in it, the page and its paper
// were a narrow beige strip on white. Every scrolled page therefore puts
// its content on the whole width (`pageWidth()`) and its paper on the whole
// screen (`paperPage()`), whatever it holds yet; `PageLayoutTests` keeps
// new pages from going back to a bare `.background(Theme.paper)`.

extension View {
    /// A scrolled page's content, on the whole width from the first frame:
    /// the ScrollView (as wide as its content) and its scrolling are too.
    func pageWidth(alignment: Alignment = .leading) -> some View {
        frame(maxWidth: .infinity, alignment: alignment)
    }

    /// The paper behind a page (on the ScrollView), always the whole screen,
    /// also under the bars.
    func paperPage() -> some View {
        frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Theme.paper.ignoresSafeArea())
    }
}
