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
    /// "Teraz", over the first screen. `lift` is how far the page is
    /// scrolled: the glow goes up with what it belongs to, and stays put
    /// when the page is pulled down.
    func paperPage(glow swatches: [ColorSwatch], lift: CGFloat = 0) -> some View {
        frame(maxWidth: .infinity, maxHeight: .infinity)
            .background {
                ZStack(alignment: .top) {
                    Theme.paper
                    PageGlowLayer(swatches: swatches)
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
    /// Opacity of the colours at the top ("Teraz" has 0.45, under a paper veil).
    static let strength = 0.6
    /// From the top of the screen (under the bars) to where the glow is gone.
    static let height: CGFloat = 900
    /// How the glow thins out downwards: no step anywhere, nothing left at the end.
    static let fade: [Gradient.Stop] = [
        .init(color: .black, location: 0),
        .init(color: .black.opacity(0.9), location: 0.25),
        .init(color: .black.opacity(0.6), location: 0.5),
        .init(color: .black.opacity(0.28), location: 0.72),
        .init(color: .black.opacity(0.08), location: 0.9),
        .init(color: .clear, location: 1),
    ]
}

/// The picture's colours, blurred and fading out downwards. The fade is a
/// mask over the whole layer, not a paper veil: the blur bleeds past the
/// layer's bottom, and under a veil that bleed showed as a hard edge.
private struct PageGlowLayer: View {
    let swatches: [ColorSwatch]

    var body: some View {
        let colors = swatches.prefix(3).compactMap { Color(hexString: $0.hex) }
        if !colors.isEmpty {
            LinearGradient(colors: colors.map { $0.opacity(PageGlow.strength) }, startPoint: .top, endPoint: .bottom)
                // Wider and taller than the layer, so the blur does not pale its sides and top.
                .padding(.horizontal, -90)
                .padding(.top, -90)
                .blur(radius: 60)
                .mask(LinearGradient(stops: PageGlow.fade, startPoint: .top, endPoint: .bottom))
        }
    }
}
