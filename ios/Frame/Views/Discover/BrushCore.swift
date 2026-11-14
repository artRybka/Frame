import Foundation

// Three looks of sketch 40 (Mateusz 2026-11-14 19:29: „Tak, przygotuj
// szkice dla 1,2,3,5 i złotego akcentu”), taken as he saw them: of the
// sheet he named only the gold and the woodcut as wrong (19:46). A drawing
// in washes of ink (`WashStrip`), a painting in gouache (`GouacheStrip`),
// a print coloured by hand (`HandColouredStrip`). All on paper, at the
// pixels of the prints (`PrintPaint.scale`).

/// What the brush's looks share.
enum Brush {
    /// How light a colour is to the eye's sensor, 0…1 (for how much of a
    /// pen's line is in a pixel).
    static func luminance(_ rgb: [Double]) -> Double { (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255 }

    /// The rows of a bar's picture the brush reaches: a few points over and under the bar.
    static func rows(high: Int) -> Range<Int> {
        let S = Double(PrintPaint.scale)
        return max(0, Int((Paint.pad - 5) * S))..<min(high, Int((Paint.pad + Paint.bar + 5) * S) + 1)
    }

    /// The colour that, laid as a glaze over `under`, makes `rgb`: a
    /// wash darkens what it is laid on, each channel by its own part.
    static func glaze(_ rgb: [Double], over under: [Double]) -> [Double] {
        zip(rgb, under).map { min(1, $0 / max($1, 12)) }
    }
}

// MARK: - Washes of ink

/// A drawing in washes of ink (lavis, „lawowanie”): the colours are one
/// ink thinned with water to its tones, laid with the brush one over
/// another from the lightest; each wash runs from its own place to the
/// bar's end, so the darkest place has all of them, and the pigment
/// gathers where it dried, at its edge. Over the darker half the pen's
/// lines, in the darkest ink.
final class WashStrip: PaintPainter, @unchecked Sendable {
    let wide: Int
    let high: Int
    let length: Double
    /// When the last wash is laid, and the pen begins.
    let last: Double

    /// The work's colours, the lightest first.
    private let tones: [PaintShare]
    private let width: Double
    private let seed: Double
    private let paper: [Double]
    /// Each wash: where along the bar it begins and the glaze it lays;
    /// nil for the lightest tone when it is the paper's own.
    private let washes: [(from: Double, glaze: [Float])?]
    private let pen: LineStrip
    /// Where along the bar the pen's lines begin, and their ink.
    private let penFrom: Double
    private let ink: [Float]
    private var made: (sheet: PrintPaint.Sheet, much: [[Float]])?
    private var whole: PaintFrame?

    /// How long after one wash the next is laid, how long the brush takes
    /// along the bar, how much later than the last wash the pen begins.
    static let apart = 0.3, sweeps = 0.45, then = 0.3
    /// A lightest tone this light is the paper, with no wash of its own.
    static let bare = 0.86

    /// When the pen begins, of `count` tones.
    static func penAt(_ count: Int) -> Double { PrintPaint.appear + Double(max(0, count - 1)) * apart + then }

    /// The tones the pen's lines are drawn after: the one ink's, not a patch of colour beside them.
    static func penTones(_ shares: [PaintShare]) -> [PaintShare] {
        let off = PrintPaint.patches(shares) ?? shares.map { _ in false }
        let tones = shares.indices.filter { !off[$0] }.map { shares[$0] }
        return tones.isEmpty ? shares : tones
    }

    /// How long the washes and the pen take over `shares`.
    static func time(_ shares: [PaintShare]) -> Double {
        guard !shares.isEmpty else { return 0 }
        let washes = PrintPaint.appear + Double(shares.count - 1) * apart + sweeps
        return max(washes, penAt(shares.count) + LineStrip.time(penTones(shares).count) - PrintPaint.appear)
    }

    init(shares: [PaintShare], width: Double, seed: Int) {
        let tones = shares.sorted { PrintPaint.lightness($0.rgb) > PrintPaint.lightness($1.rgb) }
        self.tones = tones
        self.width = width
        self.seed = Double(seed)
        (wide, high) = PrintPaint.size(width: width)
        let bare = tones.first.map { PrintPaint.lightness($0.rgb) > Self.bare } ?? false
        let paper = bare ? tones[0].rgb : InkStrip.paper
        self.paper = paper
        let spans = Paint.spans(tones, width: width)
        var under = paper
        washes = tones.enumerated().map { index, tone in
            if index == 0, bare { return nil }
            defer { under = tone.rgb }
            return (spans[index].0, Brush.glaze(tone.rgb, over: under).map { Float($0) })
        }
        pen = LineStrip(shares: Self.penTones(shares), width: width, seed: seed, tool: .pen)
        penFrom = spans.isEmpty ? 0 : spans[tones.count / 2].0
        ink = (tones.last?.rgb ?? [40, 34, 30]).map { Float($0 * 0.8) }
        last = Self.penAt(tones.count)
        length = Self.time(shares)
    }

    private func prepare() -> (sheet: PrintPaint.Sheet, much: [[Float]]) {
        if let made { return made }
        let sheet = PrintPaint.sheet(paper: paper, width: width, seed: seed, plate: false)
        let S = Double(PrintPaint.scale), pad = Paint.pad, H = Paint.bar, rows = Brush.rows(high: high)
        let much = washes.enumerated().map { index, wash -> [Float] in
            guard let wash else { return [] }
            let s = seed + 17 * Double(index)
            var much = [Float](repeating: 0, count: rows.count * wide)
            for j in rows {
                let y = (Double(j) + 0.5) / S - pad
                for i in 0..<wide {
                    let x = (Double(i) + 0.5) / S - pad
                    if x < wash.from - 8 { continue }
                    // The wash's edge: its beginning wanders, its top and bottom keep near the bar's.
                    let broad: Double = 9 * (Paint.noise(x / 7, y / 7, 10 + s) - 0.5)
                    let fine: Double = 2 * (Paint.noise(x / 1.4, y / 1.4, 20 + s) - 0.5)
                    let top: Double = 3.6 * (Paint.noise(x / 9, 0.3, 30 + s) - 0.5)
                    let bottom: Double = 3.6 * (Paint.noise(x / 9, 4.7, 31 + s) - 0.5)
                    let along: Double = min(x - wash.from + broad + fine, width + 3 - x)
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
        made = (sheet, much)
        return (sheet, much)
    }

    func frame(age: Double) -> PaintFrame {
        if age >= length, let whole { return whole }
        var out = PaintFrame(wide: wide, high: high)
        guard age > 0, !tones.isEmpty else { return out }
        let (sheet, much) = prepare()
        let S = Double(PrintPaint.scale), pad = Paint.pad, rows = Brush.rows(high: high)
        // Each wash as far as the brush has taken it along the bar.
        let fronts: [Double?] = washes.enumerated().map { index, wash in
            guard let wash else { return nil }
            let begun = age - PrintPaint.appear - Double(index) * Self.apart
            guard begun > 0 else { return nil }
            return wash.from - 6 + (width + 12 - wash.from) * Paint.ease(begun / Self.sweeps)
        }
        let penAge = age - last + PrintPaint.appear
        let lines = penAge > PrintPaint.appear ? pen.frame(age: penAge) : nil
        let blank = Brush.luminance(pen.plan.paper), full = max(0.05, blank - Brush.luminance(pen.plan.ink))
        var keep = [Float](repeating: 0, count: wide)
        for i in 0..<wide { keep[i] = Float(min(1, max(0, ((Double(i) + 0.5) / S - pad - penFrom) / 25))) }
        let shown = Float(Paint.ease(age / PrintPaint.appear))
        for j in 0..<high {
            let wet = rows.contains(j)
            for i in 0..<wide {
                let k = j * wide + i
                let cover = sheet.cover[k]
                if cover <= 0 { continue }
                var red = sheet.red[k], green = sheet.green[k], blue = sheet.blue[k]
                if wet {
                    let x = (Double(i) + 0.5) / S - pad, q = (j - rows.lowerBound) * wide + i
                    for (index, front) in fronts.enumerated() {
                        guard let front, let glaze = washes[index]?.glaze else { continue }
                        let laid = much[index][q] * Float(min(1, max(0, (front - x) / 5)))
                        if laid <= 0 { continue }
                        red *= max(0, 1 - laid + laid * glaze[0])
                        green *= max(0, 1 - laid + laid * glaze[1])
                        blue *= max(0, 1 - laid + laid * glaze[2])
                    }
                    if let lines, keep[i] > 0 {
                        let seen = lines.colour(i, j)
                        let dark = (blank - Brush.luminance([seen.red, seen.green, seen.blue])) / full
                        let line = keep[i] * 0.85 * Float(min(1, max(0, (dark - 0.08) / 0.92)))
                        if line > 0 {
                            red += (ink[0] - red) * line
                            green += (ink[1] - green) * line
                            blue += (ink[2] - blue) * line
                        }
                    }
                }
                let q = 4 * k
                out.bytes[q] = Paint.byte(Double(red))
                out.bytes[q + 1] = Paint.byte(Double(green))
                out.bytes[q + 2] = Paint.byte(Double(blue))
                out.bytes[q + 3] = Paint.byte(Double(255 * cover * shown))
            }
        }
        if age >= length { whole = out }
        return out
    }
}

// MARK: - Gouache

/// A stroke of gouache: opaque matte paint laid along the bar, its top
/// and bottom wandering a little, the brush's strokes in it as bands a
/// shade lighter and darker, the paint's chalky skin; towards its end
/// the brush runs dry and leaves streaks of its bristles.
struct GouacheStroke: Sendable {
    /// Where the brush comes down and lifts, and the paint's top and bottom (points).
    var from: Double, to: Double, top: Double, bottom: Double
    /// From here on the brush runs dry.
    var dry: Double
    var seed: Double

    /// How much of the paint covers a point, and how much lighter or darker it is there.
    func paint(_ x: Double, _ y: Double) -> (cover: Double, shade: Double) {
        let s = seed
        let lead = from - 1.6 + 1.8 * (Paint.noise(0.5, y / 4, 64 + s) - 0.5)
        let tail = to + 2.5 + 1.8 * (Paint.noise(0.5, y / 4, 65 + s) - 0.5)
        let over = top - 0.2 + 1.2 * (Paint.noise(x / 24, 0.5, 62 + s) - 0.5) + 0.3 * (Paint.noise(x / 2, 0.5, 70 + s) - 0.5)
        let under = bottom + 0.2 + 1.2 * (Paint.noise(x / 24, 2.5, 63 + s) - 0.5) + 0.3 * (Paint.noise(x / 2, 2.5, 71 + s) - 0.5)
        let edge = min(min(x - lead, tail - x), min(y - over, under - y))
        var cover = min(1, max(0, edge * 2.5 + 0.5))
        if cover <= 0 { return (0, 1) }
        if x > dry {
            // The bristles: streaks along the stroke, fewer as it runs out of paint.
            let left = min(1, max(0, (tail - x) / 4.5))
            let bristle = 0.6 * Paint.noise(x / 8, y / 0.32, 60 + s) + 0.4 * Paint.noise(x / 20, y / 1.1, 61 + s)
            let gate = (1 - left) * 0.75 + 0.05
            cover *= 0.9 * Paint.step(gate - 0.05, gate + 0.05, bristle) + 0.1 * left
        }
        let band = Paint.noise(0.5, y / 1.4, 68 + s), sweep = Paint.noise(x / 20, y / 20, 69 + s)
        let shade = 1 + 0.035 * (Paint.noise(x / 0.5, y / 0.5, 66 + s) - 0.5) + 0.05 * (Paint.noise(x / 5, y / 5, 67 + s) - 0.5)
            + 0.06 * (band - 0.5) * (0.6 + 0.8 * sweep)
        return (cover, shade)
    }
}

/// A painting in gouache (bodycolour): each colour a stroke of opaque
/// matte paint as wide as its share, laid one after another from the
/// left, each a little over the one before; the paper shows only where a
/// stroke ran dry.
final class GouacheStrip: PaintPainter, @unchecked Sendable {
    let wide: Int
    let high: Int
    let length: Double
    let last: Double

    private let shares: [PaintShare]
    private let strokes: [GouacheStroke]
    private let width: Double
    private let seed: Double
    /// Each stroke where it lies: the pixels it may reach, how much of its paint each takes and how light.
    private var made: (sheet: PrintPaint.Sheet, laid: [(left: Int, right: Int, cover: [Float], shade: [Float])])?
    private var whole: PaintFrame?

    /// How long after one stroke the next begins, and how long one takes along the bar.
    static let apart = 0.3, takes = 0.32

    static func time(_ count: Int) -> Double {
        count > 0 ? PrintPaint.appear + Double(count - 1) * apart + takes : 0
    }

    init(shares: [PaintShare], width: Double, seed: Int) {
        self.shares = shares
        self.width = width
        self.seed = Double(seed)
        (wide, high) = PrintPaint.size(width: width)
        let spans = Paint.spans(shares, width: width)
        strokes = spans.enumerated().map { index, span in
            GouacheStroke(from: span.0, to: span.1, top: 0, bottom: Paint.bar, dry: span.1 - (index == spans.count - 1 ? 6 : 3),
                          seed: Double(seed) + 11 * Double(index))
        }
        last = Self.time(shares.count)
        length = last
    }

    private func prepare() -> (sheet: PrintPaint.Sheet, laid: [(left: Int, right: Int, cover: [Float], shade: [Float])]) {
        if let made { return made }
        let sheet = PrintPaint.sheet(paper: InkStrip.paper, width: width, seed: seed, plate: false)
        let S = Double(PrintPaint.scale), pad = Paint.pad, rows = Brush.rows(high: high)
        let laid = strokes.map { stroke -> (left: Int, right: Int, cover: [Float], shade: [Float]) in
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
        made = (sheet, laid)
        return (sheet, laid)
    }

    func frame(age: Double) -> PaintFrame {
        if age >= length, let whole { return whole }
        var out = PaintFrame(wide: wide, high: high)
        guard age > 0, !shares.isEmpty else { return out }
        var (paper, laid) = prepare()
        let S = Double(PrintPaint.scale), pad = Paint.pad, rows = Brush.rows(high: high)
        for (index, stroke) in strokes.enumerated() {
            let begun = age - PrintPaint.appear - Double(index) * Self.apart
            guard begun > 0, laid[index].left <= laid[index].right else { continue }
            // The brush's tip along the bar.
            let tip = stroke.from - 3 + (stroke.to + 9 - stroke.from) * Paint.ease(begun / Self.takes)
            let colour = shares[index].rgb.map { Float($0) }, at = laid[index]
            var q = 0
            for j in rows {
                for i in at.left...at.right {
                    defer { q += 1 }
                    let x = (Double(i) + 0.5) / S - pad
                    let much = at.cover[q] * Float(min(1, max(0, (tip - x) * 0.6)))
                    if much <= 0 { continue }
                    let k = j * wide + i, shade = at.shade[q]
                    paper.red[k] += (min(255, colour[0] * shade) - paper.red[k]) * much
                    paper.green[k] += (min(255, colour[1] * shade) - paper.green[k]) * much
                    paper.blue[k] += (min(255, colour[2] * shade) - paper.blue[k]) * much
                }
            }
        }
        let shown = Float(Paint.ease(age / PrintPaint.appear))
        for k in 0..<(wide * high) where paper.cover[k] > 0 {
            let q = 4 * k
            out.bytes[q] = Paint.byte(Double(paper.red[k]))
            out.bytes[q + 1] = Paint.byte(Double(paper.green[k]))
            out.bytes[q + 2] = Paint.byte(Double(paper.blue[k]))
            out.bytes[q + 3] = Paint.byte(Double(255 * paper.cover[k] * shown))
        }
        if age >= length { whole = out }
        return out
    }
}

/// One paint's swatch in gouache: a slip of paper with a short stroke of it.
final class GouacheDab: PaintPainter, @unchecked Sendable {
    let wide = Int(2 * Paint.half) * PrintPaint.scale
    let high = Int(2 * Paint.half) * PrintPaint.scale
    let length = PrintPaint.appear + GouacheStrip.takes

    private let rgb: [Double]
    private let stroke: GouacheStroke
    private let seed: Double
    private var made: (paper: PrintPaint.Sheet, cover: [Float], shade: [Float])?

    init(rgb: [Double], index: Int, seed: Int) {
        self.rgb = rgb
        self.seed = Double(seed + 3 * index)
        let half = PrintPaint.markHalf
        stroke = GouacheStroke(from: -half + 1.6, to: half - 3.5, top: -half + 2, bottom: half - 2, dry: half - 6.5,
                               seed: Double(seed + 3 * index))
    }

    func frame(age: Double) -> PaintFrame {
        var out = PaintFrame(wide: wide, high: high)
        guard age > 0 else { return out }
        let S = Double(PrintPaint.scale)
        if made == nil {
            var cover = [Float](repeating: 0, count: wide * high), shade = [Float](repeating: 1, count: wide * high)
            for k in 0..<(wide * high) {
                let paint = stroke.paint((Double(k % wide) + 0.5) / S - Paint.half, (Double(k / wide) + 0.5) / S - Paint.half)
                cover[k] = Float(paint.cover)
                shade[k] = Float(paint.shade)
            }
            made = (PrintPaint.slip(paper: InkStrip.paper, seed: seed), cover, shade)
        }
        guard let made else { return out }
        let begun = (age - PrintPaint.appear) / GouacheStrip.takes, shown = Paint.ease(age / PrintPaint.appear)
        let tip = stroke.from - 3 + (stroke.to + 9 - stroke.from) * Paint.ease(begun)
        for k in 0..<(wide * high) where made.paper.cover[k] > 0 {
            let x = (Double(k % wide) + 0.5) / S - Paint.half
            let much = begun > 0 ? Double(made.cover[k]) * min(1, max(0, (tip - x) * 0.6)) : 0, q = 4 * k
            for (c, under) in [made.paper.red[k], made.paper.green[k], made.paper.blue[k]].enumerated() {
                let under = Double(under)
                out.bytes[q + c] = Paint.byte(under + (min(255, rgb[c] * Double(made.shade[k])) - under) * much)
            }
            out.bytes[q + 3] = Paint.byte(255 * Double(made.paper.cover[k]) * shown)
        }
        return out
    }
}

// MARK: - A print coloured by hand

/// A print coloured by hand: the engraver's lines in the scale of its
/// one ink's tones (`LineStrip`), and over them, once printed, the
/// colours laid loosely with a brush in thin washes, side by side along
/// the bar, each as wide as its share of the colour, not keeping to the
/// lines, the pigment gathered at their edges.
final class HandColouredStrip: PaintPainter, @unchecked Sendable {
    let wide: Int
    let high: Int
    let length: Double
    let last: Double

    private let lines: LineStrip
    /// Each colour: from where to where along the bar, and the glaze it lays on the paper.
    private let colours: [(from: Double, to: Double, glaze: [Float])]
    private let seed: Double
    private var much: [[Float]]?
    private var whole: PaintFrame?

    /// How long after the lines the first colour is laid, how far apart the colours are, how long one takes.
    static let after = 0.15, apart = 0.25, takes = 0.4

    /// The tones of the print's one ink and the colours laid on it by
    /// hand (`PrintPaint.patches`); of a work with no tones its darkest
    /// colour is the ink.
    static func split(_ shares: [PaintShare]) -> (tones: [PaintShare], colours: [PaintShare]) {
        guard !shares.isEmpty else { return ([], []) }
        let off = PrintPaint.patches(shares) ?? shares.map { _ in true }
        var tones = shares.indices.filter { !off[$0] }
        if tones.isEmpty, let darkest = shares.indices.min(by: { PrintPaint.lightness(shares[$0].rgb) < PrintPaint.lightness(shares[$1].rgb) }) {
            tones = [darkest]
        }
        return (tones.map { shares[$0] }, shares.indices.filter { !tones.contains($0) }.map { shares[$0] })
    }

    static func time(_ shares: [PaintShare]) -> Double {
        let (tones, colours) = split(shares)
        guard !tones.isEmpty else { return 0 }
        let printed = LineStrip.time(tones.count)
        return colours.isEmpty ? printed : printed + after + Double(colours.count - 1) * apart + takes
    }

    init(shares: [PaintShare], width: Double, seed: Int) {
        let (tones, colours) = Self.split(shares)
        self.seed = Double(seed)
        lines = LineStrip(shares: tones, width: width, seed: seed, tool: .burin)
        (wide, high) = (lines.wide, lines.high)
        let total = max(colours.reduce(0) { $0 + $1.weight }, 0.000_001), paper = lines.plan.paper
        var x = 8.0
        self.colours = colours.map { colour in
            let long = (width - 16) * colour.weight / total
            defer { x += long }
            return (x, x + long, Brush.glaze(colour.rgb, over: paper).map { Float($0) })
        }
        last = Self.time(shares)
        length = last
    }

    private func prepare() -> [[Float]] {
        if let much { return much }
        let S = Double(PrintPaint.scale), pad = Paint.pad, H = Paint.bar, rows = Brush.rows(high: high)
        let made = colours.enumerated().map { index, colour -> [Float] in
            let s = seed + 7 * Double(index)
            var much = [Float](repeating: 0, count: rows.count * wide)
            for j in rows {
                let y = (Double(j) + 0.5) / S - pad
                for i in 0..<wide {
                    let x = (Double(i) + 0.5) / S - pad
                    if x < colour.from - 12 || x > colour.to + 12 { continue }
                    // Not kept to the lines: the brush's edge wanders over them.
                    let begins = x - colour.from + 9 * (Paint.noise(x / 7, y / 7, 80 + s) - 0.5)
                    let ends = colour.to - x + 9 * (Paint.noise(x / 7, y / 7, 81 + s) - 0.5)
                    let over = y - 2.5 + 5 * (Paint.noise(x / 8, y / 8, 82 + s) - 0.5)
                    let under = H - 2.5 - y + 5 * (Paint.noise(x / 8, y / 8, 83 + s) - 0.5)
                    let edge = min(min(begins, ends), min(over, under))
                    let inside = min(1, max(0, edge * 1.2 + 0.5))
                    if inside <= 0 { continue }
                    let thin = 0.45 + 0.5 * Paint.noise(x / 9, y / 9, 84 + s)
                    let rim = exp(-max(edge, 0)) * inside
                    much[(j - rows.lowerBound) * wide + i] = Float(min(1, inside * thin * 0.9 + 0.3 * rim))
                }
            }
            return much
        }
        much = made
        return made
    }

    func frame(age: Double) -> PaintFrame {
        if age >= length, let whole { return whole }
        var out = lines.frame(age: min(age, lines.length))
        let laidFrom = lines.length + Self.after
        guard age > laidFrom, !colours.isEmpty else { return out }
        let much = prepare(), S = Double(PrintPaint.scale), pad = Paint.pad, rows = Brush.rows(high: high)
        for (index, colour) in colours.enumerated() {
            let begun = age - laidFrom - Double(index) * Self.apart
            guard begun > 0 else { continue }
            let tip = colour.from - 12 + (colour.to - colour.from + 24) * Paint.ease(begun / Self.takes)
            for j in rows {
                for i in 0..<wide {
                    let m = much[index][(j - rows.lowerBound) * wide + i]
                    if m <= 0 { continue }
                    let x = (Double(i) + 0.5) / S - pad
                    let laid = Double(m) * min(1, max(0, (tip - x) / 5))
                    if laid <= 0 { continue }
                    let q = 4 * (j * wide + i)
                    for c in 0..<3 {
                        out.bytes[q + c] = Paint.byte(Double(out.bytes[q + c]) * (1 - laid + laid * Double(colour.glaze[c])))
                    }
                }
            }
        }
        if age >= length { whole = out }
        return out
    }
}
