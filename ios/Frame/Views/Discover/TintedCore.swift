import Foundation

// The colour bar of a drawing with watercolour (pencil, charcoal, chalk or
// pen with watercolour; sketch 49 B, Mateusz 2026-11-15 16:42). Of a
// random 6000 of the library's works about one in twenty is such a
// drawing; before, the first paint its medium named was all the bar
// showed: a watercolour wash of the paper, the drawing nowhere.

/// A drawing with watercolour: as much of the bar as the sheet is bare
/// paper stays paper, the drawing's loose lines on it all along (a
/// pencil's or a pen's, `LineStrip` thinned); the rest of the work's
/// colours are watercolour (`WaterStrip`) laid over the lines from where
/// the paper's share ends, lightest to darkest, the lines showing
/// through; each accent a drop of watercolour on the clean paper. A sheet
/// that is mostly drawing (Stażewski's sketchbook) is mostly paper and
/// lines, a watercolour over a drawing mostly washes.
final class TintedStrip: PaintPainter, @unchecked Sendable {
    let wide: Int
    let high: Int
    let length: Double
    /// When the last of its paint is down.
    let last: Double

    private let lines: LineStrip
    /// Each piece of watercolour: its painter, where its bar's left end
    /// lies along this bar (points) and when it begins.
    private let pieces: [(painter: WaterStrip, at: Double, from: Double)]
    private var whole: PaintFrame?

    /// How much of what the drawing's tone asks its lines cover: loose lines.
    static let thin = 0.75
    /// How much of the watercolour is there where it is laid: the lines and the paper show a little.
    static let strength = 0.92
    /// When the watercolour begins, as a part of the lines' time; how long
    /// after it the first drop comes, and how far apart the drops are.
    static let washes = (from: 0.55, drops: 0.3, apart: 0.25)
    /// A drop's length along the bar: its share of the bar, no less than
    /// a drop the eye finds and no more than a patch.
    static let drop = (least: 21.0, most: 60.0)

    /// The work's paper (the lightest of its colours that is no accent),
    /// its washes (the other colours that are no accents: one colour's
    /// tones lightest to darkest, then the colours off them, `PrintPaint.patches`)
    /// and its accents.
    static func split(_ shares: [PaintShare]) -> (paper: PaintShare?, washes: [PaintShare], drops: [PaintShare]) {
        let large = shares.indices.filter { !shares[$0].accent }
        guard let paper = large.max(by: { PrintPaint.lightness(shares[$0].rgb) < PrintPaint.lightness(shares[$1].rgb) }) else {
            return (nil, [], shares)
        }
        let off = PrintPaint.patches(shares) ?? shares.map { _ in false }
        let rest = large.filter { $0 != paper }.sorted { PrintPaint.lightness(shares[$0].rgb) > PrintPaint.lightness(shares[$1].rgb) }
        let washes = rest.filter { !off[$0] } + rest.filter { off[$0] }
        return (shares[paper], washes.map { shares[$0] }, shares.filter(\.accent))
    }

    /// Where along a bar `width` wide the washes lie (their bar's left end
    /// and its width), and each drop (its left end and length).
    static func places(_ shares: [PaintShare], width: Double) -> (washes: (at: Double, width: Double)?, drops: [(at: Double, long: Double)]) {
        let (paper, washes, drops) = split(shares)
        let total = max(shares.reduce(0) { $0 + $1.weight }, 0.000_001)
        let paperEnd = width * (paper?.weight ?? 0) / total
        var laid: (at: Double, width: Double)?
        if !washes.isEmpty {
            let long = min(width, max(width - paperEnd, 16 * Double(washes.count)))
            laid = (width - long, long)
        }
        // On the paper's part, evenly; under a short one, over the first washes.
        let from = 8.0, to = max(50, min(width, paperEnd) - 6)
        let placed = drops.enumerated().map { index, share -> (at: Double, long: Double) in
            let long = min(drop.most, max(drop.least, width * share.weight / total))
            let middle = from + (to - from) * (Double(index) + 0.5) / Double(drops.count)
            return (middle - long / 2, long)
        }
        return (laid, placed)
    }

    static func time(_ shares: [PaintShare], width: Double) -> Double {
        guard !shares.isEmpty else { return 0 }
        let (_, washes, drops) = split(shares)
        let begun = LineStrip.time(1) * Self.washes.from
        var last = LineStrip.time(1)
        if !washes.isEmpty, let laid = places(shares, width: width).washes {
            last = max(last, begun + WaterStrip.time(washes.map(\.plain), width: laid.width))
        }
        for (index, share) in drops.enumerated() {
            let long = places(shares, width: width).drops[index].long
            last = max(last, begun + Self.washes.drops + Self.washes.apart * Double(index) + WaterStrip.time([share.plain], width: long))
        }
        return last
    }

    init(shares: [PaintShare], width: Double, seed: Int, tool: LineTool) {
        let (paper, washes, drops) = Self.split(shares)
        // The drawing's lines are of the paper's tone: as loose all along.
        lines = LineStrip(shares: [PaintShare(rgb: paper?.rgb ?? [243, 235, 216], weight: 1)], width: width, seed: seed, tool: tool,
                          thin: Self.thin)
        (wide, high) = (lines.wide, lines.high)
        let placed = Self.places(shares, width: width)
        let begun = lines.length * Self.washes.from
        var pieces = [(painter: WaterStrip, at: Double, from: Double)]()
        if let laid = placed.washes {
            pieces.append((WaterStrip(shares: washes.map(\.plain), width: laid.width, seed: seed + 20), laid.at, begun))
        }
        for (index, share) in drops.enumerated() {
            let place = placed.drops[index]
            pieces.append((WaterStrip(shares: [share.plain], width: place.long, seed: seed + 40 + 3 * index), place.at,
                           begun + Self.washes.drops + Self.washes.apart * Double(index)))
        }
        self.pieces = pieces
        last = max(lines.last, pieces.map { $0.from + $0.painter.last }.max() ?? 0)
        length = max(lines.length, pieces.map { $0.from + $0.painter.length }.max() ?? 0)
    }

    func frame(age: Double) -> PaintFrame {
        if age >= length, let whole { return whole }
        var out = lines.frame(age: min(age, lines.length))
        let paper = lines.plan.paper
        for piece in pieces where age > piece.from {
            Self.lay(piece.painter.frame(age: min(age - piece.from, piece.painter.length)), at: piece.at, on: &out, paper: paper)
        }
        if age >= length { whole = out }
        return out
    }

    /// A piece of watercolour (`Paint.scale` pixels to a point, its bar's
    /// left end at `at` points along this one) laid on `out`
    /// (`PrintPaint.scale`) as a glaze: what is under it shows through,
    /// darkened by it as it darkens the paper.
    static func lay(_ piece: PaintFrame, at: Double, on out: inout PaintFrame, paper: [Double]) {
        let S = Double(PrintPaint.scale), s = Double(Paint.scale), pad = Paint.pad
        let left = max(0, Int(((at - pad) + pad) * S)), right = min(out.wide - 1, Int((at + Double(piece.wide) / s - pad + pad) * S))
        guard left <= right else { return }
        let under = paper.map { max($0, 12) }
        for j in 0..<out.high {
            let v = ((Double(j) + 0.5) / S) * s - 0.5
            let y0 = Int(floor(v)), fy = v - floor(v)
            guard y0 >= -1, y0 < piece.high else { continue }
            for i in left...right {
                let u = ((Double(i) + 0.5) / S - at) * s - 0.5
                let x0 = Int(floor(u)), fx = u - floor(u)
                guard x0 >= -1, x0 < piece.wide else { continue }
                // Its colour, weighed by how much of it is there, and how much, between four pixels.
                var much = 0.0, rgb = [0.0, 0.0, 0.0]
                for (dx, dy, w) in [(0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)] {
                    let x = x0 + dx, y = y0 + dy
                    guard x >= 0, y >= 0, x < piece.wide, y < piece.high, w > 0 else { continue }
                    let q = 4 * (y * piece.wide + x), a = Double(piece.bytes[q + 3]) / 255 * w
                    if a <= 0 { continue }
                    much += a
                    for c in 0..<3 { rgb[c] += Double(piece.bytes[q + c]) * a }
                }
                if much <= 0.002 { continue }
                let laid = min(1, much) * strength, q = 4 * (j * out.wide + i)
                for c in 0..<3 {
                    let glaze = min(1, rgb[c] / much / under[c])
                    out.bytes[q + c] = Paint.byte(Double(out.bytes[q + c]) * (1 - laid + laid * glaze))
                }
            }
        }
    }
}

extension PaintShare {
    /// The colour as one of a watercolour's washes, not an accent.
    var plain: PaintShare { PaintShare(rgb: rgb, weight: weight) }
}
