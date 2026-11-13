import SwiftUI
import UIKit

/// The study sheet on the dark page as a strip of paper torn across the
/// whole screen (Mateusz 2026-11-13 15:13, of four drawn proposals: "C.
/// Wydarty pas przez ekran"; he asked for it "realniej jak kartka papieru"
/// and "bez $$"): straight at the screen's sides, torn at the top and the
/// bottom, with the white of the torn fibre showing along the tear, the
/// paper's grain and a little light falling over it. The title and the
/// field are on the paper; the notes under it are written light on the
/// dark page. What runs out of the field (one wash, one line) reaches the
/// screen's edge again, as on the light page. All drawn here: nothing is
/// asked of the server or of a model.
enum TornPaper {
    /// How deep the tear wanders into the paper, in points.
    static let depth: CGFloat = 7
    /// How wide the torn fibre's white shows along the tear.
    static let coreLeast: CGFloat = 1.1
    static let coreMost: CGFloat = 3.4
    /// The torn fibre: lighter than the paper's face.
    static let fibre = Color(hex: 0xFBF8F2)
    /// The points between two corners of the tear.
    static let step: CGFloat = 1.5
    /// How much of the strip the paper's own room above and below the
    /// title and the field takes, past the tear.
    static let roomAbove: CGFloat = 22
    static let roomBelow: CGFloat = 18

    /// The tear's seed for a sheet: the same sheet tears the same way
    /// each time, another sheet another way.
    static func seed(_ sheet: String) -> Double { Double(Paint.seed(sheet)) * 3.7 }

    /// How far into the paper the tear reaches at `x` along one edge
    /// (0 … `depth`): a long wander, a shorter one and the fibres' fray.
    static func tear(at x: CGFloat, seed: Double) -> CGFloat {
        let x = Double(x)
        let wander = 0.5 * Paint.noise(x / 70, 0.5, seed) + 0.3 * Paint.noise(x / 19, 3.5, seed)
        let fray = 0.14 * Paint.noise(x / 6, 7.5, seed) + 0.06 * Paint.noise(x / 1.8, 11.5, seed)
        return depth * CGFloat(wander + fray)
    }

    /// How wide the torn fibre's white is at `x` (`coreLeast` … `coreMost`).
    static func core(at x: CGFloat, seed: Double) -> CGFloat {
        let x = Double(x)
        let share = 0.7 * Paint.noise(x / 24, 21.5, seed) + 0.3 * Paint.noise(x / 5, 25.5, seed)
        return coreLeast + (coreMost - coreLeast) * CGFloat(share)
    }

    /// The paper's grain as a tile (`grainSide` points square): how much
    /// darker it is at each place, in its alpha (fine scales only, so the
    /// tile's seams do not show).
    static let grainSide = 96
    static let grainScale = 2
    static let grain: CGImage? = {
        let side = grainSide * grainScale
        var bytes = [UInt8](repeating: 0, count: side * side * 4)
        for k in 0..<(side * side) {
            let x = (Double(k % side) + 0.5) / Double(grainScale), y = (Double(k / side) + 0.5) / Double(grainScale)
            let grain = 0.55 * Paint.noise(x / 0.6, y / 0.6, 311) + 0.3 * Paint.noise(x / 1.6, y / 1.6, 312)
                + 0.15 * Paint.noise(x / 3.2, y / 3.2, 313)
            bytes[4 * k + 3] = Paint.byte(255 * grain)
        }
        guard let provider = CGDataProvider(data: Data(bytes) as CFData),
              let space = CGColorSpace(name: CGColorSpace.sRGB)
        else { return nil }
        return CGImage(
            width: side, height: side, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: side * 4,
            space: space, bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue),
            provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent
        )
    }()
    /// How dark the grain is at its darkest.
    static let grainShare = 0.07
    /// How much the light falls off from the strip's top to its bottom.
    static let fall = 0.045
}

/// The strip's outline: straight at the sides (at the screen's edges),
/// torn at the top and the bottom. `face` is the paper's face, inside the
/// torn fibre's white; else the whole sheet with its fibre.
struct TornEdge: Shape {
    let seed: Double
    var face = false

    func path(in rect: CGRect) -> Path {
        let count = max(Int(rect.width / TornPaper.step), 2)
        func x(_ k: Int) -> CGFloat { rect.width * CGFloat(k) / CGFloat(count) }
        func top(_ x: CGFloat) -> CGFloat {
            rect.minY + TornPaper.tear(at: x, seed: seed) + (face ? TornPaper.core(at: x, seed: seed) : 0)
        }
        func bottom(_ x: CGFloat) -> CGFloat {
            let other = seed + 50
            return rect.maxY - TornPaper.tear(at: x, seed: other) - (face ? TornPaper.core(at: x, seed: other) : 0)
        }
        var path = Path()
        path.move(to: CGPoint(x: rect.minX, y: top(0)))
        for k in 1...count { path.addLine(to: CGPoint(x: rect.minX + x(k), y: top(x(k)))) }
        for k in stride(from: count, through: 0, by: -1) { path.addLine(to: CGPoint(x: rect.minX + x(k), y: bottom(x(k)))) }
        path.closeSubpath()
        return path
    }
}

/// The torn strip under its content: the content is widened by `reach`
/// on each side (to the screen's edges) and given the paper's room above
/// and below; it is cut at the tear.
struct TornSheet: ViewModifier {
    let seed: Double
    let reach: CGFloat

    func body(content: Content) -> some View {
        content
            .padding(.top, TornPaper.roomAbove)
            .padding(.bottom, TornPaper.roomBelow)
            .padding(.horizontal, reach)
            .background(DrawnSheet.paper)
            // The grain and the light over the paper and the study alike,
            // so the study's own paper and the strip's are one.
            .overlay {
                ZStack {
                    if let grain = TornPaper.grain {
                        Canvas { context, size in
                            context.opacity = TornPaper.grainShare
                            context.fill(
                                Path(CGRect(origin: .zero, size: size)),
                                with: .tiledImage(Image(decorative: grain, scale: CGFloat(TornPaper.grainScale)))
                            )
                        }
                    }
                    LinearGradient(
                        colors: [.clear, .black.opacity(TornPaper.fall)],
                        startPoint: .top, endPoint: .bottom
                    )
                }
                .blendMode(.multiply)
                .allowsHitTesting(false)
            }
            .clipShape(TornEdge(seed: seed, face: true))
            .background {
                TornEdge(seed: seed)
                    .fill(TornPaper.fibre)
                    .shadow(color: .black.opacity(0.55), radius: 5, y: 2)
            }
            .padding(.horizontal, -reach)
    }
}
