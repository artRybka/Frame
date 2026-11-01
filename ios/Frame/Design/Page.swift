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

    /// The paper with a picture's colours glowing at the top: Teraz,
    /// Odkrywaj (the study of the day) and Playlisty (what the frame shows).
    /// `lift` is how far the page is scrolled (`glowLift`): the glow goes up
    /// with what it belongs to, and stays put when the page is pulled down.
    /// `colours`: how many of `swatches` glow (a picture's first three; a
    /// playlist's cover sends one per work).
    func paperPage(glow swatches: [ColorSwatch], lift: CGFloat = 0, colours: Int = 3) -> some View {
        frame(maxWidth: .infinity, maxHeight: .infinity)
            .background {
                PaperGlowBackground(swatches: Array(swatches.prefix(colours)), lift: lift)
                    .allowsHitTesting(false)
            }
    }

    /// Keeps `lift` at how far this ScrollView is scrolled, for
    /// `paperPage(glow:lift:)`. Clamped, so scrolling past the glow redraws nothing.
    func glowLift(_ lift: Binding<CGFloat>) -> some View {
        onScrollGeometryChange(for: CGFloat.self) { geometry in
            min(max(geometry.contentOffset.y + geometry.contentInsets.top, 0), PageGlow.height)
        } action: { _, offset in
            lift.wrappedValue = offset
        }
    }
}

enum PageGlow {
    /// Opacity of the colours at the top (1.57.0 had 0.38 under a paper
    /// veil, 1.58.2 0.6: too faint, then too strong).
    static let strength = 0.48
    /// From the top of the screen (under the bars) to where the glow is
    /// gone: about the first card under the title (1.58.2 had 900, 1.59 760,
    /// both too spread out).
    static let height: CGFloat = 520
    /// How much the colours are smeared (Teraz had 60 on the whole screen).
    static let blur: CGFloat = 40
    /// How the glow thins out downwards: no step anywhere, nothing left at the end.
    static let fade: [Gradient.Stop] = [
        .init(color: .black, location: 0),
        .init(color: .black.opacity(0.8), location: 0.3),
        .init(color: .black.opacity(0.4), location: 0.58),
        .init(color: .black.opacity(0.12), location: 0.8),
        .init(color: .black.opacity(0.02), location: 0.93),
        .init(color: .clear, location: 1),
    ]
}

/// The paper and the glow over the whole screen, under the bars.
struct PaperGlowBackground: View {
    /// A picture's first three colours glow (`paperPage` may let more through).
    let swatches: [ColorSwatch]
    var lift: CGFloat = 0

    var body: some View {
        ZStack(alignment: .top) {
            Theme.paper
            PageGlowLayer(swatches: swatches)
                .frame(height: PageGlow.height)
                .offset(y: -max(0, lift))
                .animation(.easeInOut(duration: 0.8), value: swatches)
        }
        .ignoresSafeArea()
    }
}

/// The picture's colours, blurred and fading out downwards. The fade is a
/// mask over the whole layer, not a paper veil: the blur bleeds past the
/// layer's bottom, and under a veil that bleed showed as a hard edge.
private struct PageGlowLayer: View {
    let swatches: [ColorSwatch]

    var body: some View {
        let colors = swatches.prefix(4).compactMap { Color(hexString: $0.hex) }
        if !colors.isEmpty {
            LinearGradient(colors: colors.map { $0.opacity(PageGlow.strength) }, startPoint: .top, endPoint: .bottom)
                // Wider and taller than the layer, so the blur does not pale its sides and top.
                .padding(.horizontal, -90)
                .padding(.top, -90)
                .blur(radius: PageGlow.blur)
                .mask(LinearGradient(stops: PageGlow.fade, startPoint: .top, endPoint: .bottom))
        }
    }
}

extension PageGlow {
    @MainActor private static var fromThumbs: [String: [ColorSwatch]] = [:]

    /// The colours of a picture's thumbnail already in memory (the tile's it
    /// was opened from), top, middle and bottom: the glow from the first
    /// frame when the work's own colours are not known yet. Empty when the
    /// thumbnail is not in memory.
    @MainActor
    static func colours(of ref: ImageRef, backend: any FrameBackend, maxPixel: CGFloat = 700) -> [ColorSwatch] {
        guard let request = backend.request(for: ref), let key = request.url?.absoluteString else { return [] }
        if let known = fromThumbs[key] { return known }
        guard let image = ImageLoader.inMemory(for: request, maxPixel: maxPixel)?.cgImage else { return [] }
        let found = bands(of: image)
        if fromThumbs.count > 200 { fromThumbs.removeAll() }
        fromThumbs[key] = found
        return found
    }

    /// The average colour of the picture's top, middle and bottom thirds.
    private static func bands(of image: CGImage) -> [ColorSwatch] {
        let width = 8, height = 24
        var pixels = [UInt8](repeating: 0, count: width * height * 4)
        let drawn = pixels.withUnsafeMutableBytes { buffer -> Bool in
            guard let context = CGContext(
                data: buffer.baseAddress, width: width, height: height, bitsPerComponent: 8,
                bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
            ) else { return false }
            context.interpolationQuality = .medium
            context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
        guard drawn else { return [] }
        let rows = height / 3
        return (0 ..< 3).map { band in
            var sum = [0, 0, 0]
            for y in band * rows ..< (band + 1) * rows {
                for x in 0 ..< width {
                    let at = (y * width + x) * 4
                    for c in 0 ..< 3 { sum[c] += Int(pixels[at + c]) }
                }
            }
            let count = rows * width
            let hex = sum.map { String(format: "%02X", $0 / count) }.joined()
            return ColorSwatch(hex: "#" + hex, weight: 1.0 / 3)
        }
    }
}
