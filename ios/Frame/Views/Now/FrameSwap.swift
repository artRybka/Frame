import SwiftUI
import UIKit

/// The frame redrawing its e-paper, laid over the picture it still shows:
/// small squares go over to the new picture one by one in a scattered
/// order, each for a moment in the six inks of the panel. Nothing blinks as
/// a whole; `progress` (0…1) moves with the bar.
struct FrameSwap: View, Animatable {
    /// The new picture; nil while it loads (nothing goes over yet).
    let image: UIImage?
    /// The new picture in the panel's inks, one colour per square.
    let inks: InkGrid?
    var progress: Double

    var animatableData: Double {
        get { progress }
        set { progress = newValue }
    }

    var body: some View {
        Canvas { context, size in
            guard let image, let inks else { return }
            let width = size.width / CGFloat(inks.columns)
            let height = size.height / CGFloat(inks.rows)
            var shown = Path()
            for row in 0 ..< inks.rows {
                for column in 0 ..< inks.columns {
                    let index = row * inks.columns + column
                    // Inset by a hair: neighbouring squares overlap, no seams.
                    let rect = CGRect(
                        x: CGFloat(column) * width, y: CGFloat(row) * height, width: width, height: height
                    ).insetBy(dx: -0.25, dy: -0.25)
                    let start = Self.start(index) * (1 - Self.flip)
                    if progress >= start + Self.flip {
                        shown.addRect(rect)
                    } else if progress >= start {
                        context.fill(Path(rect), with: .color(inks.colors[index]))
                    }
                }
            }
            context.clip(to: shown)
            context.draw(Image(uiImage: image), in: CGRect(origin: .zero, size: size))
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    /// The part of the swap each square spends in ink.
    static let flip = 0.18

    /// When a square starts going over, 0…1: scattered, but the same on
    /// every frame of the animation (a fixed hash, not a random draw).
    static func start(_ index: Int) -> Double {
        var x = UInt64(truncatingIfNeeded: index) &+ 0x9E37_79B9_7F4A_7C15
        x = (x ^ (x >> 30)) &* 0xBF58_476D_1CE4_E5B9
        x = (x ^ (x >> 27)) &* 0x94D0_49BB_1331_11EB
        x ^= x >> 31
        return Double(x % 10000) / 10000
    }
}

/// A picture cut into squares, each the ink of the panel nearest to it.
struct InkGrid: Equatable {
    let columns: Int
    let rows: Int
    let colors: [Color]

    /// The six inks of Spectra 6 as they look on the panel.
    static let inks: [(r: Double, g: Double, b: Double)] = [
        (27, 27, 29), (232, 230, 223), (230, 200, 30), (184, 50, 42), (42, 79, 156), (60, 107, 69),
    ]

    /// About 18 squares across a portrait frame, 32 across a landscape one.
    init?(image: UIImage, portrait: Bool) {
        let columns = portrait ? 18 : 32
        let rows = portrait ? 32 : 18
        guard let cgImage = image.cgImage,
              let context = CGContext(
                  data: nil, width: columns, height: rows, bitsPerComponent: 8, bytesPerRow: columns * 4,
                  space: CGColorSpaceCreateDeviceRGB(),
                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
              )
        else { return nil }
        context.interpolationQuality = .medium
        context.draw(cgImage, in: CGRect(x: 0, y: 0, width: columns, height: rows))
        guard let data = context.data else { return nil }
        let bytes = data.bindMemory(to: UInt8.self, capacity: columns * rows * 4)
        var colors: [Color] = []
        colors.reserveCapacity(columns * rows)
        for index in 0 ..< columns * rows {
            let r = Double(bytes[index * 4]), g = Double(bytes[index * 4 + 1]), b = Double(bytes[index * 4 + 2])
            let ink = Self.inks.min { lhs, rhs in
                Self.distance(lhs, r, g, b) < Self.distance(rhs, r, g, b)
            } ?? Self.inks[0]
            colors.append(Color(red: ink.r / 255, green: ink.g / 255, blue: ink.b / 255))
        }
        self.columns = columns
        self.rows = rows
        self.colors = colors
    }

    private static func distance(_ ink: (r: Double, g: Double, b: Double), _ r: Double, _ g: Double, _ b: Double) -> Double {
        let dr = ink.r - r, dg = ink.g - g, db = ink.b - b
        return 2 * dr * dr + 4 * dg * dg + 3 * db * db
    }
}
