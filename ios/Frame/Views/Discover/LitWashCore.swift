import Foundation

// The colour bar of a wash drawing on tinted paper, or one heightened
// with white (Mateusz 2026-11-15 21:36, of Théodore Géricault's „Turecki
// jeździec w walce”, Art Institute of Chicago, "brush and brown wash,
// heightened with white gouache over black chalk, with blue wash on brown
// laid paper", shown as grey washes on a cream paper under a pen's
// hatching: „Czy możemy naszym paskiem objąć także takie przypadki?
// Zwłaszcza brakuje bieli.”). Of a random 6000 of the library's works
// some 75 are washes of ink on a blue, grey or brown paper or heightened
// with white; all were given the cream paper of `WashStrip`, and none
// its white.

/// A wash drawing on its own paper: the paper as the work shows it
/// (`parts`), the drawing under the washes in its loose lines (black
/// chalk, a pen), the washes laid over them from the lightest, each to
/// the bar's end, a colour off the ink's tones (a blue wash in the sky)
/// in its own place only; last the white gouache that heightens it, an
/// opaque stroke over its own place at the bar's light end.
final class LitWashStrip: PaintPainter, @unchecked Sendable {
    let wide: Int
    let high: Int
    let length: Double
    /// When the last of its paint is down.
    let last: Double

    private let lines: LineStrip
    private let width: Double
    private let seed: Double
    /// Each wash: where along the bar it begins and ends, its glaze, when it begins.
    private let washes: [(from: Double, to: Double, glaze: [Float], at: Double)]
    /// Each stroke of white: its stroke, its colour, when it begins and how long it takes.
    private let whites: [(stroke: GouacheStroke, rgb: [Float], at: Double, takes: Double)]
    private var made: (much: [[Float]], white: [(left: Int, right: Int, cover: [Float], shade: [Float])])?
    private var whole: PaintFrame?

    /// How much of what the paper's tone asks the drawing's lines cover:
    /// loose lines under the washes, a pen's a little fewer than chalk's.
    static func thin(_ tool: LineTool) -> Double { tool == .pen ? 0.75 : 0.9 }
    /// How much lighter than the paper the lines take it: few of them.
    static let bare = 0.07
    /// A tone this much lighter than the paper is white laid on it.
    static let above = 0.05
    /// The lights a drawing heightened with white has when its colours
    /// hold none: a share of the bar and the gouache's white.
    static let lights = (share: 0.1, white: [246.0, 244, 236])
    /// When the washes begin (a part of the lines' time), how long after
    /// one the next, how long the brush takes along the bar; how long
    /// after the last wash the white begins, and how long its stroke takes.
    static let times = (from: 0.45, apart: 0.3, sweeps: 0.45, white: 0.2, stroke: 0.32)

    /// The work's colours as the drawing has them: its paper (the lightest
    /// colour that is no white gouache, `gouache`), the white laid on it
    /// (what is a white and lighter than the paper; `lit` and none: white
    /// at `lights.share`) and its washes, lightest first, with whether each
    /// is a colour of its own off the ink's tones (`PrintPaint.patches`).
    static func parts(_ shares: [PaintShare], lit: Bool) -> (paper: PaintShare, whites: [PaintShare], washes: [(share: PaintShare, own: Bool)]) {
        let fallback = PaintShare(rgb: InkStrip.paper, weight: 1)
        guard !shares.isEmpty else { return (fallback, [], []) }
        let light = shares.map { PrintPaint.lightness($0.rgb) }
        let large = shares.indices.filter { !shares[$0].accent }
        let pool = large.isEmpty ? Array(shares.indices) : large
        // The lightest that is no white gouache: the washes only darken it.
        let sheets = pool.filter { !gouache(shares[$0].rgb) }
        let paperAt = sheets.max { light[$0] < light[$1] } ?? pool.max { light[$0] < light[$1] } ?? 0
        let paper = shares[paperAt], over = max(light[paperAt] + above, 0.8)
        var whites = shares.indices.filter { $0 != paperAt && light[$0] > over }.sorted { light[$0] > light[$1] }.map { shares[$0] }
        if lit, whites.isEmpty, light[paperAt] < 0.9 {
            let total = shares.reduce(0) { $0 + $1.weight }
            whites = [PaintShare(rgb: lights.white, weight: total * lights.share / (1 - lights.share))]
        }
        let off = PrintPaint.patches(shares) ?? shares.map { _ in false }
        let rest = shares.indices.filter { $0 != paperAt && light[$0] <= over }.sorted { light[$0] > light[$1] }
        // A wash of its own colour is a cool one on the warm ink's paper (a
        // blue sky); a warmer brown is the ink's still, run over the rest.
        let warmth = PrintPaint.lab(paper.rgb).b
        return (paper, whites, rest.map { (shares[$0], off[$0] && PrintPaint.lab(shares[$0].rgb).b < warmth - 0.02) })
    }

    /// A neutral near white: the gouache, not a sheet (Géricault's #e7e8e0).
    static func gouache(_ rgb: [Double]) -> Bool {
        let lab = PrintPaint.lab(rgb)
        return lab.light > 0.9 && (lab.a * lab.a + lab.b * lab.b).squareRoot() < 0.025
    }

    static func time(_ shares: [PaintShare], width: Double, lit: Bool) -> Double {
        guard !shares.isEmpty else { return 0 }
        return layout(shares, width: width, seed: 0, lit: lit).last
    }

    /// The bar's plan: its paper, each wash (where along the bar it
    /// begins and ends, its glaze, when it begins), each stroke of white
    /// (its stroke, its colour, when it begins, how long it takes) and when
    /// the last is down, the drawing's lines taking `LineStrip.time(1)`.
    static func layout(_ shares: [PaintShare], width: Double, seed: Int, lit: Bool)
        -> (paper: [Double], washes: [(from: Double, to: Double, glaze: [Float], at: Double)],
            whites: [(stroke: GouacheStroke, rgb: [Float], at: Double, takes: Double)], last: Double) {
        let (paper, whites, washes) = parts(shares, lit: lit)
        let drawn = LineStrip.time(1), begun = drawn * times.from
        // Along the bar, lightest first: the white, the bare paper, the washes.
        let spans = Paint.spans(whites + [paper] + washes.map(\.share), width: width)
        var under = paper.rgb, list = [(from: Double, to: Double, glaze: [Float], at: Double)]()
        for (k, wash) in washes.enumerated() {
            let span = spans[whites.count + 1 + k]
            // A colour of its own lies in its place; a tone of the ink runs on to the bar's end, over the ones before.
            let glaze = Brush.glaze(wash.share.rgb, over: wash.own ? paper.rgb : under).map { Float($0) }
            list.append((span.0, wash.own ? span.1 : width + 3, glaze, begun + Double(k) * times.apart))
            if !wash.own { under = wash.share.rgb }
        }
        let washed = washes.isEmpty ? begun : begun + Double(washes.count - 1) * times.apart + times.sweeps
        // The white last, a stroke of opaque gouache over its own place at the
        // bar's light end (Mateusz 2026-11-15 22:07, of touches of the brush
        // over the lighter part: „A: biel na jasnym końcu”).
        let H = Paint.bar
        let strokes = whites.indices.map { index -> (stroke: GouacheStroke, rgb: [Float], at: Double, takes: Double) in
            let span = spans[index]
            let stroke = GouacheStroke(from: span.0, to: span.1, top: 0.5, bottom: H - 0.5, dry: span.1 - 3,
                                       seed: Double(seed) + 23 * Double(index))
            return (stroke, whites[index].rgb.map { Float($0) }, washed + times.white + Double(index) * times.apart, times.stroke)
        }
        let last = max(drawn, washes.isEmpty ? drawn : washed, strokes.map { $0.at + $0.takes }.max() ?? 0)
        return (paper.rgb, list, strokes, last)
    }

    init(shares: [PaintShare], width: Double, seed: Int, lit: Bool, tool: LineTool) {
        let plan = Self.layout(shares, width: width, seed: seed, lit: lit)
        self.width = width
        self.seed = Double(seed)
        let light = PrintPaint.lightness(plan.paper)
        lines = LineStrip(shares: [PaintShare(rgb: plan.paper, weight: 1)], width: width, seed: seed, tool: tool, thin: Self.thin(tool),
                          paper: plan.paper, shades: [light + Self.bare], laid: true)
        (wide, high) = (lines.wide, lines.high)
        washes = plan.washes
        whites = plan.whites
        last = max(lines.last, plan.last)
        length = last
    }

    private func prepare() -> (much: [[Float]], white: [(left: Int, right: Int, cover: [Float], shade: [Float])]) {
        if let made { return made }
        let S = Double(PrintPaint.scale), pad = Paint.pad, H = Paint.bar, rows = Brush.rows(high: high)
        let much = washes.enumerated().map { index, wash -> [Float] in
            let s = seed + 17 * Double(index)
            var much = [Float](repeating: 0, count: rows.count * wide)
            for j in rows {
                let y = (Double(j) + 0.5) / S - pad
                for i in 0..<wide {
                    let x = (Double(i) + 0.5) / S - pad
                    if x < wash.from - 8 || x > wash.to + 8 { continue }
                    // The wash's edge: its ends wander, its top and bottom keep near the bar's.
                    let broad: Double = 9 * (Paint.noise(x / 7, y / 7, 10 + s) - 0.5)
                    let fine: Double = 2 * (Paint.noise(x / 1.4, y / 1.4, 20 + s) - 0.5)
                    let top: Double = 3.6 * (Paint.noise(x / 9, 0.3, 30 + s) - 0.5)
                    let bottom: Double = 3.6 * (Paint.noise(x / 9, 4.7, 31 + s) - 0.5)
                    let tail: Double = 6 * (Paint.noise(0.5, y / 6, 35 + s) - 0.5)
                    let along: Double = min(x - wash.from + broad + fine, wash.to - x + tail)
                    let edge: Double = min(along, min(y - 1 + top, H - 1 - y + bottom))
                    let inside: Double = min(1, max(0, edge * 1.5 + 0.5))
                    if inside <= 0 { continue }
                    // Pigment gathers at the drying edge, settles in the paper's grain, blooms where the water stood.
                    let rim: Double = exp(-max(edge, 0) / 1.1) * inside
                    let grain: Double = 0.9 + 0.2 * Paint.noise(x / 0.6, y / 0.6, 40 + s)
                    let bloom: Double = Paint.noise(x / 9, y / 9, 50 + s)
                    let laid: Double = inside * (0.7 + 0.45 * bloom) * grain + 0.45 * rim
                    much[(j - rows.lowerBound) * wide + i] = Float(min(1.2, laid))
                }
            }
            return much
        }
        let white = whites.map { touch -> (left: Int, right: Int, cover: [Float], shade: [Float]) in
            let stroke = touch.stroke
            let left = max(0, Int((stroke.from - 6 + pad) * S)), right = min(wide - 1, Int((stroke.to + 7 + pad) * S))
            let count = max(0, right - left + 1) * rows.count
            var cover = [Float](repeating: 0, count: count), shade = [Float](repeating: 1, count: count)
            guard left <= right else { return (left, right, cover, shade) }
            var q = 0
            for j in rows {
                let y = (Double(j) + 0.5) / S - pad
                for i in left...right {
                    let paint = stroke.paint((Double(i) + 0.5) / S - pad, y)
                    cover[q] = Float(paint.cover)
                    shade[q] = Float(paint.shade)
                    q += 1
                }
            }
            return (left, right, cover, shade)
        }
        made = (much, white)
        return (much, white)
    }

    func frame(age: Double) -> PaintFrame {
        if age >= length, let whole { return whole }
        var out = lines.frame(age: min(age, lines.length))
        guard age > (washes.first?.at ?? whites.first?.at ?? .infinity) else { return out }
        let (much, white) = prepare()
        let S = Double(PrintPaint.scale), pad = Paint.pad, rows = Brush.rows(high: high)
        for (index, wash) in washes.enumerated() where age > wash.at {
            // As far as the brush has taken it along the bar.
            let front = wash.from - 6 + (wash.to + 12 - wash.from) * Paint.ease((age - wash.at) / Self.times.sweeps)
            let laidOn = much[index], glaze = wash.glaze
            for j in rows {
                for i in 0..<wide {
                    let k = j * wide + i, q = 4 * k
                    guard out.bytes[q + 3] > 0 else { continue }
                    let x = (Double(i) + 0.5) / S - pad
                    let laid = laidOn[(j - rows.lowerBound) * wide + i] * Float(min(1, max(0, (front - x) / 5)))
                    if laid <= 0 { continue }
                    for c in 0..<3 {
                        out.bytes[q + c] = Paint.byte(Double(Float(out.bytes[q + c]) * max(0, 1 - laid + laid * glaze[c])))
                    }
                }
            }
        }
        for (index, touch) in whites.enumerated() where age > touch.at {
            let at = white[index], stroke = touch.stroke
            guard at.left <= at.right else { continue }
            // The brush's tip along its stroke.
            let tip = stroke.from - 3 + (stroke.to + 9 - stroke.from) * Paint.ease((age - touch.at) / touch.takes)
            var q = 0
            for j in rows {
                for i in at.left...at.right {
                    defer { q += 1 }
                    let x = (Double(i) + 0.5) / S - pad
                    let paint = Double(at.cover[q]) * min(1, max(0, (tip - x) * 0.6))
                    let k = j * wide + i, p = 4 * k
                    guard paint > 0, out.bytes[p + 3] > 0 else { continue }
                    for c in 0..<3 {
                        let under = Double(out.bytes[p + c])
                        out.bytes[p + c] = Paint.byte(under + (min(255, Double(touch.rgb[c] * at.shade[q])) - under) * paint * 0.96)
                    }
                }
            }
        }
        if age >= length { whole = out }
        return out
    }
}
