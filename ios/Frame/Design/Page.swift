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

    /// The paper with a picture's colours glowing at the top, as behind
    /// "Teraz" but lighter and only on the first screen. `lift` is how far
    /// the page is scrolled: the glow goes up with what it belongs to, and
    /// stays put when the page is pulled down.
    func paperPage(glow swatches: [ColorSwatch], lift: CGFloat = 0) -> some View {
        frame(maxWidth: .infinity, maxHeight: .infinity)
            .background {
                ZStack(alignment: .top) {
                    Theme.paper
                    PaperGlow(swatches: swatches, strength: PageGlow.strength)
                        .frame(height: PageGlow.height)
                        .offset(y: -max(0, lift))
                        .animation(.easeInOut(duration: 0.8), value: swatches)
                }
                .ignoresSafeArea()
                .allowsHitTesting(false)
            }
    }
}

enum PageGlow {
    /// "Teraz" has 0.45 on the whole screen; a page with a title and a list is busier.
    static let strength = 0.38
    /// From the top of the screen (under the bars): the title and the first card.
    static let height: CGFloat = 640
}
