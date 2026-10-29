import SwiftUI
import UIKit

/// How the old picture goes over to the new one while the panel redraws.
enum SwapStyle {
    /// Fine squares in a scattered order, each for a moment in ink.
    case pixels
    /// Dots of the six inks scatter over the old picture, then settle into
    /// the new one: as the e-paper itself draws it.
    case raster
    /// The same raster, as a wave from the top.
    case rasterWave
}

/// The frame redrawing its e-paper, laid over the picture it still shows.
/// Nothing blinks as a whole; `progress` (0…1) moves with the bar.
struct FrameSwap: View, Animatable {
    /// The new picture, cut for the swap; nil while it loads.
    let plan: SwapPlan?
    var progress: Double

    var animatableData: Double {
        get { progress }
        set { progress = newValue }
    }

    var body: some View {
        ZStack {
            if let plan {
                if let ink = plan.ink(at: progress) {
                    Image(decorative: ink, scale: 1)
                        .resizable()
                        .interpolation(.none)
                }
                if plan.style == .raster {
                    Image(uiImage: plan.image)
                        .resizable()
                        .opacity(plan.settled(at: progress))
                } else if let mask = plan.settledMask(at: progress) {
                    Image(uiImage: plan.image)
                        .resizable()
                        .mask {
                            Image(decorative: mask, scale: 1)
                                .resizable()
                                .interpolation(.none)
                        }
                }
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

/// The new picture cut into a grid for the swap: the colour of each cell in
/// the panel's inks, and when each cell goes over.
struct SwapPlan {
    let style: SwapStyle
    let image: UIImage
    let columns: Int
    let rows: Int
    /// RGBA of each cell, in the inks.
    private let inks: [UInt8]
    /// When each cell turns to ink, and (`rasterWave`) when it settles.
    private let starts: [Double]
    private let settles: [Double]

    /// The six inks of Spectra 6 as they look on the panel.
    static let palette: [SIMD3<Float>] = [
        [27, 27, 29], [232, 230, 223], [230, 200, 30], [184, 50, 42], [42, 79, 156], [60, 107, 69],
    ]

    /// The part of the swap a square spends in ink (`pixels`).
    static let flip = 0.15
    /// The raster has scattered in by then, and settles after (`raster`).
    static let scattered = 0.55

    init?(image: UIImage, portrait: Bool, style: SwapStyle) {
        // Squares of ~3 pt on the phone; raster dots of ~1.6 pt.
        let across = style == .pixels ? 90 : 180
        let along = across * 16 / 9
        let columns = portrait ? across : along
        let rows = portrait ? along : across
        guard let pixels = Self.downsample(image, columns: columns, rows: rows) else { return nil }
        self.style = style
        self.image = image
        self.columns = columns
        self.rows = rows
        inks = style == .pixels ? Self.nearest(pixels) : Self.dither(pixels, columns: columns, rows: rows)
        var starts: [Double] = []
        var settles: [Double] = []
        starts.reserveCapacity(columns * rows)
        for index in 0 ..< columns * rows {
            let noise = Self.hash(index), noise2 = Self.hash(index &+ 0x5151_5151)
            let down = Double(index / columns) / Double(rows)
            switch style {
            case .pixels: starts.append(noise * (1 - Self.flip))
            case .raster: starts.append(noise * Self.scattered)
            case .rasterWave:
                starts.append(down * 0.45 + noise * 0.1)
                settles.append(0.5 + down * 0.38 + noise2 * 0.1)
            }
        }
        self.starts = starts
        self.settles = settles
    }

    /// The cells in ink at `t`; clear elsewhere.
    func ink(at t: Double) -> CGImage? {
        var bytes = [UInt8](repeating: 0, count: columns * rows * 4)
        var any = false
        for index in 0 ..< columns * rows {
            let start = starts[index]
            let inInk = style == .pixels ? t >= start && t < start + Self.flip : t >= start
            guard inInk else { continue }
            any = true
            for byte in 0 ..< 4 { bytes[index * 4 + byte] = inks[index * 4 + byte] }
        }
        return any ? Self.cgImage(bytes, columns: columns, rows: rows) : nil
    }

    /// `raster`: how much of the new picture covers the dots, 0…1.
    func settled(at t: Double) -> Double {
        let x = min(max((t - Self.scattered) / (1 - Self.scattered), 0), 1)
        return x * x * (3 - 2 * x)
    }

    /// `pixels`, `rasterWave`: where the new picture shows, as alpha.
    func settledMask(at t: Double) -> CGImage? {
        var bytes = [UInt8](repeating: 0, count: columns * rows * 4)
        var any = false
        for index in 0 ..< columns * rows {
            let alpha: Double
            if style == .pixels {
                alpha = t >= starts[index] + Self.flip ? 1 : 0
            } else {
                alpha = min(max((t - settles[index]) / 0.12, 0), 1)
            }
            guard alpha > 0 else { continue }
            any = true
            let value = UInt8(alpha * 255)
            for byte in 0 ..< 4 { bytes[index * 4 + byte] = value }  // white, premultiplied
        }
        return any ? Self.cgImage(bytes, columns: columns, rows: rows) : nil
    }

    // MARK: Making the grid

    /// When a cell goes over, 0…1: scattered, but the same on every frame
    /// of the animation (a fixed hash, not a random draw).
    private static func hash(_ index: Int) -> Double {
        var x = UInt64(truncatingIfNeeded: index) &+ 0x9E37_79B9_7F4A_7C15
        x = (x ^ (x >> 30)) &* 0xBF58_476D_1CE4_E5B9
        x = (x ^ (x >> 27)) &* 0x94D0_49BB_1331_11EB
        x ^= x >> 31
        return Double(x % 10000) / 10000
    }

    /// The picture as one RGB colour per cell.
    private static func downsample(_ image: UIImage, columns: Int, rows: Int) -> [SIMD3<Float>]? {
        guard let cgImage = image.cgImage,
              let context = CGContext(
                  data: nil, width: columns, height: rows, bitsPerComponent: 8, bytesPerRow: columns * 4,
                  space: CGColorSpaceCreateDeviceRGB(),
                  bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
              )
        else { return nil }
        context.interpolationQuality = .high
        context.draw(cgImage, in: CGRect(x: 0, y: 0, width: columns, height: rows))
        guard let data = context.data else { return nil }
        let bytes = data.bindMemory(to: UInt8.self, capacity: columns * rows * 4)
        return (0 ..< columns * rows).map { index in
            SIMD3(Float(bytes[index * 4]), Float(bytes[index * 4 + 1]), Float(bytes[index * 4 + 2]))
        }
    }

    private static func closest(_ colour: SIMD3<Float>) -> SIMD3<Float> {
        let weights = SIMD3<Float>(2, 4, 3)
        return palette.min { lhs, rhs in
            ((lhs - colour) * (lhs - colour) * weights).sum() < ((rhs - colour) * (rhs - colour) * weights).sum()
        } ?? palette[0]
    }

    private static func rgba(_ colours: [SIMD3<Float>]) -> [UInt8] {
        colours.flatMap { [UInt8($0.x), UInt8($0.y), UInt8($0.z), 255] }
    }

    private static func nearest(_ pixels: [SIMD3<Float>]) -> [UInt8] {
        rgba(pixels.map(closest))
    }

    /// Floyd–Steinberg in the six inks.
    private static func dither(_ pixels: [SIMD3<Float>], columns: Int, rows: Int) -> [UInt8] {
        var work = pixels
        var out = [SIMD3<Float>](repeating: .zero, count: pixels.count)
        for y in 0 ..< rows {
            for x in 0 ..< columns {
                let index = y * columns + x
                let ink = closest(work[index])
                out[index] = ink
                let error = work[index] - ink
                if x + 1 < columns { work[index + 1] += error * (7 / 16) }
                if y + 1 < rows {
                    if x > 0 { work[index + columns - 1] += error * (3 / 16) }
                    work[index + columns] += error * (5 / 16)
                    if x + 1 < columns { work[index + columns + 1] += error * (1 / 16) }
                }
            }
        }
        return rgba(out)
    }

    private static func cgImage(_ bytes: [UInt8], columns: Int, rows: Int) -> CGImage? {
        guard let provider = CGDataProvider(data: Data(bytes) as CFData) else { return nil }
        return CGImage(
            width: columns, height: rows, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: columns * 4,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue),
            provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent
        )
    }
}
