import Foundation

// "Kolor i światło" for what is printed or drawn, not painted (sketch 35;
// Mateusz 2026-11-12 07:26: „dla rycin, rysunków, grafik, plakatów
// chciałbym opracować inny wygląd paska kolorów. Ten teraz w żaden sposób
// nie ma sensu”, 07:55: „Wdrażamy oba. Jest super.”). Two looks, each
// made with the work's own means:
//
// - a work of one colour (an engraving, a drawing in pen or pencil) has no
//   colours to show, only paper and ink: its bar is a scale of its tones,
//   lightest to darkest, each as wide as its share and each made the way
//   the work makes it, by how close the lines are (`LineStrip`);
// - a print in colours (a colour woodcut, a lithograph, a poster) is flat
//   inks laid one after another: its bar is their impressions on paper, a
//   little out of register (`InkStrip`).
//
// Pure Swift like `PaintCore.swift`; `PaintedColour.swift` puts it on the
// page.

/// What a work of one colour is drawn with.
enum LineTool: Sendable {
    /// The engraver's burin, the etcher's needle: even lines that swell
    /// and thin, inside a plate's mark.
    case burin
    /// A pen and brown ink: a freer hand.
    case pen
    /// Pencil, charcoal, lithographic crayon: soft lines that catch the
    /// paper's tooth.
    case pencil

    /// The line's width, the directions it is laid in (degrees from the
    /// bar's length) and how dark one direction alone may get, how
    /// unevenly it is spaced and leans, how much it bows and how far it
    /// runs over the bar's edge, how soft its edge is (points), and the
    /// black it is drawn in.
    var hand: (wide: Double, sets: [Double], most: [Double], loose: Double, lean: Double, bow: Double, over: Double, soft: Double,
               black: [Double]) {
        switch self {
        case .burin: (0.78, [62, 118, 36], [0.36, 0.36, 0.6], 0.10, 1.2, 0.5, 0.9, 0.35, [22, 19, 15])
        case .pen: (0.95, [58, 124, 84], [0.34, 0.34, 0.6], 0.28, 5.0, 1.3, 1.8, 0.35, [58, 36, 20])
        case .pencil: (1.25, [66, 112, 40], [0.5, 0.5, 0.7], 0.30, 4.0, 1.0, 1.6, 0.6, [52, 52, 56])
        }
    }
}

/// What the two looks share: the piece of paper they are on.
enum PrintPaint {
    /// Pixels to a point: a hatched line is under a point wide, and at
    /// two it would be a smear.
    static let scale = 3
    /// How far the paper goes on past the bar's ends, and over and under it.
    static let margin = (side: 7.0, over: 5.0)
    /// How long the paper takes to be there.
    static let appear = 0.25

    /// A colour as the eye takes it (OKLab): how light, 0…1, and its
    /// tint, green to red and blue to yellow.
    static func lab(_ rgb: [Double]) -> (light: Double, a: Double, b: Double) {
        let linear = rgb.map { value -> Double in
            let v = value / 255
            return v <= 0.04045 ? v / 12.92 : pow((v + 0.055) / 1.055, 2.4)
        }
        let l = cbrt(0.4122214708 * linear[0] + 0.5363325363 * linear[1] + 0.0514459929 * linear[2])
        let m = cbrt(0.2119034982 * linear[0] + 0.6806995451 * linear[1] + 0.1073969566 * linear[2])
        let s = cbrt(0.0883024619 * linear[0] + 0.2817188376 * linear[1] + 0.6299787005 * linear[2])
        return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
                0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)
    }

    /// How light a colour looks, 0…1.
    static func lightness(_ rgb: [Double]) -> Double { lab(rgb).light }

    /// Whether a work's colours are one colour's tones (black on its
    /// paper, sepia, a grey scale): none of them vivid, and those with a
    /// tint all of one hue. The server's "monochrome" looks at the whole
    /// picture and misses about a fifth of such works (a yellowed sheet,
    /// a mount); the bar shows these colours, so it goes by them too.
    static func oneColour(_ colours: [[Double]]) -> Bool {
        let tinted = colours.map(lab).filter { ($0.a * $0.a + $0.b * $0.b).squareRoot() >= faint }
        guard !tinted.isEmpty else { return true }
        if tinted.contains(where: { ($0.a * $0.a + $0.b * $0.b).squareRoot() > vivid }) { return false }
        let hue = atan2(tinted.reduce(0) { $0 + $1.b }, tinted.reduce(0) { $0 + $1.a })
        return tinted.allSatisfy { colour in
            var away = abs(atan2(colour.b, colour.a) - hue)
            if away > Double.pi { away = 2 * Double.pi - away }
            return away <= hues * Double.pi / 180
        }
    }

    /// A colour fainter than this has no hue to speak of; one stronger
    /// than `vivid` is a colour of its own; how far (degrees) one hue's
    /// tones lie apart.
    static let faint = 0.03, vivid = 0.12, hues = 35.0

    static func mixed(_ a: [Double], _ b: [Double], _ much: Double) -> [Double] {
        zip(a, b).map { $0 + ($1 - $0) * much }
    }

    /// A picture's size in pixels for a bar `width` points wide.
    static func size(width: Double) -> (wide: Int, high: Int) {
        (Int((width + 2 * Paint.pad).rounded()) * scale, Int(Paint.bar + 2 * Paint.pad) * scale)
    }

    /// The paper: its colour and how much of it is there, a pixel each.
    struct Sheet: Sendable {
        var red: [Float], green: [Float], blue: [Float], cover: [Float]
    }

    /// A piece of `paper` under a bar `width` wide: a little uneven at
    /// its edge and in its tone; with a `plate`, the mark the plate
    /// pressed into it, lit from the upper left.
    static func sheet(paper: [Double], width: Double, seed: Double, plate: Bool) -> Sheet {
        let (wide, high) = size(width: width)
        return sheet(paper: paper, wide: wide, high: high, origin: Paint.pad, left: -margin.side, right: width + margin.side,
                     top: -margin.over, bottom: Paint.bar + margin.over, seed: seed, plate: plate ? width : nil)
    }

    /// The piece of paper under one paint's swatch.
    static func slip(paper: [Double], seed: Double) -> Sheet {
        let side = Int(2 * Paint.half) * scale
        return sheet(paper: paper, wide: side, high: side, origin: Paint.half, left: -slipHalf, right: slipHalf, top: -slipHalf,
                     bottom: slipHalf, seed: seed, plate: nil)
    }

    /// Half the side of a swatch's piece of paper, and of what is drawn or printed on it.
    static let slipHalf = 12.5, markHalf = 9.0

    /// A piece of `paper` from `left`…`right` and `top`…`bottom` (points
    /// from `origin` in from the picture's corner); `plate`: the width of
    /// the plate pressed into it where the bar is.
    static func sheet(paper: [Double], wide: Int, high: Int, origin: Double, left: Double, right: Double, top: Double, bottom: Double,
                      seed: Double, plate: Double?) -> Sheet {
        let n = wide * high, S = Double(scale), H = Paint.bar
        var out = Sheet(red: [Float](repeating: 0, count: n), green: [Float](repeating: 0, count: n),
                        blue: [Float](repeating: 0, count: n), cover: [Float](repeating: 0, count: n))
        for k in 0..<n {
            let x = (Double(k % wide) + 0.5) / S - origin, y = (Double(k / wide) + 0.5) / S - origin
            let edge = min(min(x - left, right - x), min(y - top, bottom - y))
            if edge < -2.5 { continue }
            let ragged = 2.2 * (Paint.noise(x / 5, y / 5, 61 + seed) - 0.5) + 0.8 * (Paint.noise(x / 1.6, y / 1.6, 62 + seed) - 0.5)
            let cover = min(1, max(0, (edge + ragged) * 1.6 + 0.5))
            if cover <= 0 { continue }
            var tone = 1 - 0.035 * (Paint.noise(x / 0.5, y / 0.5, 63 + seed) - 0.5) - 0.03 * (Paint.noise(x / 7, y / 7, 64 + seed) - 0.5)
            if let plate {
                let fromLeft = x, fromTop = y + 1.5, fromRight = plate - x, fromBottom = H + 1.5 - y
                let near = min(min(fromLeft, fromRight), min(fromTop, fromBottom))
                let mark = exp(-(near / 0.55) * (near / 0.55))
                let lit: Double = min(fromLeft, fromTop) < min(fromRight, fromBottom) ? -1 : 1
                tone *= 1 + 0.09 * mark * lit
                tone *= 1 - 0.018 * min(1, max(0, near * 2))
            }
            out.red[k] = Float(paper[0] * tone)
            out.green[k] = Float(paper[1] * tone)
            out.blue[k] = Float(paper[2] * tone)
            out.cover[k] = Float(cover)
        }
        return out
    }
}

// MARK: - A scale of tones in lines

/// One line of the hatching: from `a` to `b` in the bar's points (x along
/// it from its left end, y down from its top), bowed a little, widest in
/// its middle.
struct LineStroke: Sendable {
    var ax: Double, ay: Double, bx: Double, by: Double
    var bow: Double
    var wide: Double
    /// Which direction's lines it is one of.
    var layer: Int
    /// When it is begun, seconds after the bar is.
    var at: Double

    /// As much of it as is drawn `part` of the way, into `layer`: how
    /// much of each pixel it covers, never less than is there. `origin`:
    /// how far the picture's corner is up and left of the points' zero.
    func draw(part: Double, into layer: inout [Float], wide pixels: Int, high: Int, origin: Double, soft: Double) {
        let S = Double(PrintPaint.scale), dx = bx - ax, dy = by - ay
        let long = (dx * dx + dy * dy).squareRoot()
        guard long > 0.01, abs(dy) > 0.2 * long, part > 0 else { return }
        let across = abs(dy) / long, nx = -dy / long, spread = soft * 2.0.squareRoot()
        let endY = ay + dy * min(1, part)
        let first = max(0, Int(((min(ay, endY) + origin) * S).rounded(.down)))
        let lastRow = min(high - 1, Int(((max(ay, endY) + origin) * S).rounded(.up)))
        guard first <= lastRow else { return }
        for j in first...lastRow {
            let y = (Double(j) + 0.5) / S - origin, u = (y - ay) / dy
            if u < 0 || u > part || u > 1 { continue }
            let swell = pow(sin(Double.pi * u), 0.45)
            let half = max(0.12, self.wide * (0.25 + 0.75 * swell)) / 2
            let cx = ax + dx * u + nx * bow * sin(Double.pi * u)
            let reach = (half + 2.5 * soft) / across
            let from = max(0, Int(((cx - reach + origin) * S).rounded(.down))), to = min(pixels - 1, Int(((cx + reach + origin) * S).rounded(.up)))
            if from > to { continue }
            for i in from...to {
                let x = (Double(i) + 0.5) / S - origin
                // The line with its edge gone soft: as much of it as lies within `soft` of here.
                let away = abs(x - cx) * across
                let cover = 0.5 * (erf((half - away) / spread) + erf((half + away) / spread))
                if cover <= 0.004 { continue }
                let q = j * pixels + i
                layer[q] = max(layer[q], Float(cover))
            }
        }
    }
}

/// The bar of a work of one colour: a scale of its tones, lightest to
/// darkest, each as wide as its share of the work, made by lines: far
/// apart for a light tone, crossed for a darker one, crossed again for the
/// darkest. On a piece of the work's paper, in the work's ink, drawn line
/// after line.
final class LineStrip: PaintPainter, @unchecked Sendable {
    let wide: Int
    let high: Int
    let length: Double
    /// When the last line is down.
    let last: Double
    let plan: Plan

    private let tool: LineTool
    private let width: Double
    private let seed: Double
    private var sheet: PrintPaint.Sheet?
    /// The paper's tooth, which a soft point does not reach the bottom of.
    private var tooth: [Float] = []
    /// The lines that are down, a picture for each direction, and how many they are.
    private var laid: [[Float]] = []
    private var down = 0
    private var whole: PaintFrame?

    /// How long a line takes, and the breath before the lines are
    /// crossed, in lines.
    static let takes = 0.14, breath = 14.0

    /// How long the lines of `count` tones take: the same for every work
    /// of as many, however close its lines are.
    static func time(_ count: Int) -> Double {
        count > 0 ? PrintPaint.appear + 1.0 + 0.22 * Double(count) + takes : 0
    }

    /// A tone: its place along the bar and how much of the paper its lines cover.
    struct Tone: Sendable {
        var from: Double, to: Double
        var cover: Double
        /// Which of the work's colours it is.
        var colour: Int
    }

    struct Plan: Sendable {
        var tones: [Tone]
        var strokes: [LineStroke]
        var paper: [Double], ink: [Double]
        /// When the last line is down.
        var last: Double

        /// How dark the bar is to be at `x`: a tone goes over into the next within a few points.
        func cover(at x: Double) -> Double {
            let soft = 7.0
            for (k, tone) in tones.enumerated() where x < tone.to || k == tones.count - 1 {
                var cover = tone.cover
                if k > 0, x - tone.from < soft {
                    cover = tones[k - 1].cover + (tone.cover - tones[k - 1].cover) * Paint.ease(0.5 + 0.5 * (x - tone.from) / soft)
                }
                if k < tones.count - 1, tone.to - x < soft {
                    cover = tone.cover + (tones[k + 1].cover - tone.cover) * Paint.ease(0.5 - 0.5 * (tone.to - x) / soft)
                }
                return cover
            }
            return tones.last?.cover ?? 0
        }
    }

    /// The tones and lines of a bar `width` wide. The work's colours are
    /// mixtures of its paper and its ink: the paper is taken as lighter
    /// than the lightest of them, the ink as darker than the darkest.
    static func plan(_ shares: [PaintShare], width: Double, seed: Int, tool: LineTool) -> Plan {
        guard !shares.isEmpty else { return Plan(tones: [], strokes: [], paper: [243, 235, 216], ink: tool.hand.black, last: 0) }
        let hand = tool.hand, H = Paint.bar
        let light = shares.map { PrintPaint.lightness($0.rgb) }
        let order = shares.indices.sorted { light[$0] > light[$1] }
        let paper = PrintPaint.mixed(shares[order[0]].rgb, [243, 235, 216], 0.82)
        let ink = PrintPaint.mixed(shares[order[order.count - 1]].rgb, hand.black, 0.8)
        let top = min(0.97, light[order[0]] + 0.13), bottom = min(light[order[order.count - 1]] - 0.16, 0.24)
        let spans = Paint.spans(order.map { shares[$0] }, width: width)
        let tones = order.enumerated().map { k, i in
            Tone(from: spans[k].0, to: spans[k].1, cover: min(0.93, max(0.05, (top - light[i]) / (top - bottom))), colour: i)
        }
        var plan = Plan(tones: tones, strokes: [], paper: paper, ink: ink, last: 0)
        var random = PaintRandom(seed + 91), at = 0.0
        for (k, degrees) in hand.sets.enumerated() {
            // What this direction's lines are to cover, the ones before it having covered what they can.
            func share(_ x: Double) -> Double {
                let want = plan.cover(at: x)
                var left = 1.0, mine = 0.0
                for j in 0...k {
                    mine = min(max(left > 0.000_001 ? 1 - (1 - want) / left : 0, 0), hand.most[j])
                    left *= 1 - mine
                }
                return mine
            }
            var x = -16.0, any = false
            while x < width + 16 {
                let cover = share(min(max(x, 0), width))
                if cover < 0.03 {
                    x += 2
                    continue
                }
                let wide = hand.wide * (0.72 + 0.5 * random.next()) * (0.8 + 0.35 * min(1, cover / 0.3))
                let angle = (degrees + hand.lean * (random.next() * 2 - 1)) * Double.pi / 180
                // A faint tone's lines are short ones.
                let reach = min(1, cover / 0.07)
                let y1 = -hand.over * random.next() + (1 - reach) * H * 0.3 * random.next()
                let y2 = H + hand.over * random.next() - (1 - reach) * H * 0.3 * random.next()
                let slope = cos(angle) / sin(angle)
                var stroke = LineStroke(ax: x - (y1 - H / 2) * slope, ay: y1, bx: x - (y2 - H / 2) * slope, by: y2,
                                        bow: hand.bow * (random.next() * 2 - 1), wide: wide, layer: k, at: at)
                // The pencil goes down and comes back up.
                if tool == .pencil, plan.strokes.count % 2 == 1 {
                    (stroke.ax, stroke.ay, stroke.bx, stroke.by) = (stroke.bx, stroke.by, stroke.ax, stroke.ay)
                }
                plan.strokes.append(stroke)
                any = true
                at += 1
                x += wide * 0.8 / cover / max(0.35, abs(sin(angle))) * (1 + hand.loose * (random.next() * 2 - 1))
            }
            if any { at += breath }
        }
        // One line after another, the last begun in time to be down at the bar's time.
        plan.last = time(shares.count)
        let span = max(1, plan.strokes.last?.at ?? 1), draws = plan.last - takes - PrintPaint.appear
        for k in plan.strokes.indices { plan.strokes[k].at = PrintPaint.appear + plan.strokes[k].at / span * draws }
        return plan
    }

    init(shares: [PaintShare], width: Double, seed: Int, tool: LineTool) {
        self.tool = tool
        self.width = width
        self.seed = Double(seed)
        plan = Self.plan(shares, width: width, seed: seed, tool: tool)
        (wide, high) = PrintPaint.size(width: width)
        last = plan.last
        length = plan.last
    }

    private func prepare() -> PrintPaint.Sheet {
        if let sheet { return sheet }
        let made = PrintPaint.sheet(paper: plan.paper, width: width, seed: seed, plate: tool == .burin)
        sheet = made
        if tool == .pencil {
            let S = Double(PrintPaint.scale)
            tooth = (0..<(wide * high)).map { q in
                Float(0.42 + 0.5 * Paint.noise(Double(q % wide) / S / 0.45, Double(q / wide) / S / 0.45, 71 + seed))
            }
        }
        return made
    }

    func frame(age: Double) -> PaintFrame {
        if age >= length, let whole { return whole }
        var out = PaintFrame(wide: wide, high: high)
        guard age > 0, !plan.tones.isEmpty else { return out }
        let sheet = prepare(), n = wide * high, S = Double(PrintPaint.scale), pad = Paint.pad, hand = tool.hand
        // The lines that are down stay down: only those begun since are drawn again.
        let done = plan.strokes.prefix { $0.at + Self.takes <= age }.count
        if laid.isEmpty || done < down {
            laid = hand.sets.map { _ in [Float](repeating: 0, count: n) }
            down = 0
        }
        for stroke in plan.strokes[down..<done] {
            stroke.draw(part: 1, into: &laid[stroke.layer], wide: wide, high: high, origin: pad, soft: hand.soft)
        }
        down = done
        var layers = laid
        for stroke in plan.strokes[done...] {
            if stroke.at >= age { break }
            stroke.draw(part: (age - stroke.at) / Self.takes, into: &layers[stroke.layer], wide: wide, high: high, origin: pad, soft: hand.soft)
        }
        let shown = Float(Paint.ease(age / PrintPaint.appear))
        let firstRow = max(0, Int((pad - 4) * S)), lastRow = min(high - 1, Int((pad + Paint.bar + 4) * S))
        // The lines keep to the bar's length; a pencil's rub off a little into the paper between them.
        var keep = [Float](repeating: 0, count: wide), rub = [Float](repeating: 0, count: wide)
        let far = min(1, age / max(0.001, last))
        for i in 0..<wide {
            let x = (Double(i) + 0.5) / S - pad
            keep[i] = Float(min(1, max(0, (x + 1) * 1.5)) * min(1, max(0, (width + 1 - x) * 1.5)))
            if tool == .pencil, x >= 0, x <= width { rub[i] = Float(0.09 * plan.cover(at: x) * far) }
        }
        let strength: Float = tool == .pen ? 0.92 : 1
        let ink = plan.ink.map { Float($0) }
        for j in 0..<high {
            let lined = j >= firstRow && j <= lastRow
            let y = (Double(j) + 0.5) / S - pad
            let inside: Float = y >= 0 && y <= Paint.bar ? 1 : 0
            for i in 0..<wide {
                let k = j * wide + i
                let cover = sheet.cover[k]
                if cover <= 0 { continue }
                var red = sheet.red[k], green = sheet.green[k], blue = sheet.blue[k]
                if lined {
                    var bare: Float = 1
                    let grain: Float = tooth.isEmpty ? 1 : tooth[k]
                    for layer in layers { bare *= 1 - layer[k] * keep[i] * strength * grain }
                    let dark = min(1, 1 - bare + rub[i] * inside)
                    if dark > 0 {
                        red += (ink[0] - red) * dark
                        green += (ink[1] - green) * dark
                        blue += (ink[2] - blue) * dark
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

/// One paint's swatch for a work of lines: a slip of paper hatched and
/// crossed in that paint, with the work's tool.
final class LinePatch: PaintPainter, @unchecked Sendable {
    let wide = Int(2 * Paint.half) * PrintPaint.scale
    let high = Int(2 * Paint.half) * PrintPaint.scale
    let length: Double
    let strokes: [LineStroke]

    private let rgb: [Double]
    private let tool: LineTool
    private let seed: Double
    private var sheet: PrintPaint.Sheet?

    /// The paper drawn on, and how long after one line the next is begun.
    static let paper = [243.0, 235, 216], apart = 0.03

    init(rgb: [Double], index: Int, seed: Int, tool: LineTool) {
        self.rgb = rgb
        self.tool = tool
        self.seed = Double(seed + 3 * index)
        let hand = tool.hand, half = PrintPaint.markHalf
        var random = PaintRandom(seed + 500 + index), strokes = [LineStroke](), at = PrintPaint.appear
        for (k, degrees) in hand.sets.prefix(2).enumerated() {
            var x = -half - 5
            while x < half + 5 {
                let angle = (degrees + hand.lean * (random.next() * 2 - 1)) * Double.pi / 180, slope = cos(angle) / sin(angle)
                let y1 = -half - hand.over * random.next(), y2 = half + hand.over * random.next()
                var stroke = LineStroke(ax: x - y1 * slope, ay: y1, bx: x - y2 * slope, by: y2, bow: hand.bow * (random.next() * 2 - 1),
                                        wide: hand.wide * (0.9 + 0.5 * random.next()), layer: k, at: at)
                if tool == .pencil, strokes.count % 2 == 1 {
                    (stroke.ax, stroke.ay, stroke.bx, stroke.by) = (stroke.bx, stroke.by, stroke.ax, stroke.ay)
                }
                strokes.append(stroke)
                at += Self.apart
                x += (k == 0 ? 2.4 : 3.6) * (1 + hand.loose * (random.next() * 2 - 1))
            }
        }
        self.strokes = strokes
        length = (strokes.last?.at ?? 0) + LineStrip.takes
    }

    func frame(age: Double) -> PaintFrame {
        var out = PaintFrame(wide: wide, high: high)
        guard age > 0 else { return out }
        let paper = sheet ?? PrintPaint.slip(paper: Self.paper, seed: seed)
        sheet = paper
        let n = wide * high, S = Double(PrintPaint.scale), hand = tool.hand, half = PrintPaint.markHalf
        var layers = [[Float](repeating: 0, count: n), [Float](repeating: 0, count: n)]
        for stroke in strokes {
            if stroke.at >= age { break }
            stroke.draw(part: (age - stroke.at) / LineStrip.takes, into: &layers[stroke.layer], wide: wide, high: high,
                        origin: Paint.half, soft: hand.soft)
        }
        let shown = Paint.ease(age / PrintPaint.appear)
        let ink = PrintPaint.mixed(rgb, hand.black, 0.25)
        for k in 0..<n where paper.cover[k] > 0 {
            let x = (Double(k % wide) + 0.5) / S - Paint.half, y = (Double(k / wide) + 0.5) / S - Paint.half
            let keep = Float(min(1, max(0, (half + 0.8 - abs(x)) * 1.5)))
            // A paint's colour is to be told: the soft point is pressed harder here than along the bar.
            let grain: Float = tool == .pencil ? Float(0.58 + 0.42 * Paint.noise(x / 0.45, y / 0.45, 71 + seed)) : 1
            var bare: Float = 1
            for layer in layers { bare *= 1 - layer[k] * keep * grain }
            let dark = Double(1 - bare), q = 4 * k
            out.bytes[q] = Paint.byte(Double(paper.red[k]) + (ink[0] - Double(paper.red[k])) * dark)
            out.bytes[q + 1] = Paint.byte(Double(paper.green[k]) + (ink[1] - Double(paper.green[k])) * dark)
            out.bytes[q + 2] = Paint.byte(Double(paper.blue[k]) + (ink[2] - Double(paper.blue[k])) * dark)
            out.bytes[q + 3] = Paint.byte(255 * Double(paper.cover[k]) * shown)
        }
        return out
    }
}

// MARK: - A colour print's inks

/// What a colour print is printed from.
enum InkPress: Sendable {
    /// Blocks of wood: an even edge, the wood's grain in the ink.
    case wood
    /// The stone: the crayon's grain where the ink thins, and the
    /// printer's register marks.
    case stone
}

/// A block's impression: the ink a point takes from a block pressed on
/// this much of the paper (points from the bar's upper left corner).
private struct InkBlock {
    var left: Double, right: Double, top: Double, bottom: Double
    var seed: Double

    /// How far the ink goes over its place at each end.
    static let over = 1.3

    func ink(_ x: Double, _ y: Double, press: InkPress) -> Double {
        let ragged = 1.3 * (Paint.noise(x / 3.5, y / 3.5, 81 + seed) - 0.5) + 0.7 * (Paint.noise(x / 0.9, y / 0.9, 82 + seed) - 0.5)
        let inside = min(min(x - left, right - x), min(y - top, bottom - y)) + ragged
        if inside < -1 { return 0 }
        switch press {
        case .wood:
            // Not laid evenly: the baren's passes, the wood's grain, a thin place here and there.
            let even = 0.86 + 0.14 * Paint.noise(x / 9, y / 9, 83 + seed)
            let pore = Paint.noise(x / 0.7, y / 0.7, 84 + seed) > 0.78 ? 1 - 0.10 * Paint.noise(x / 2, y / 2, 85 + seed) : 1
            let grain = 1 - 0.07 * abs(sin(y * 2.3 + 6 * Paint.noise(x / 30, y / 30, 86 + seed)))
            return min(1, max(0, inside * 2.2 + 0.5)) * even * pore * grain * 0.96
        case .stone:
            // The crayon's grain on the stone: the ink breaks up towards its edge.
            let edge = min(1, max(0, inside / 2.6))
            let speck = Paint.noise(x / 0.33, y / 0.33, 87 + seed)
            return min(1, max(0, inside * 1.2 + 0.5)) * (speck > 0.30 + 0.5 * edge ? 0.35 + 0.6 * edge : 1)
                * (0.9 + 0.1 * Paint.noise(x / 9, y / 9, 83 + seed))
        }
    }
}

/// The bar of a print in colours: each colour a flat impression of ink on
/// the paper, as wide as its share of the work, pressed one after
/// another; a little out of register, so that two lie over each other
/// here (darker: the inks are not opaque) and the paper shows there.
final class InkStrip: PaintPainter, @unchecked Sendable {
    let wide: Int
    let high: Int
    let length: Double
    /// When the last ink is down.
    let last: Double
    /// Each colour's place along the bar and how far out of register it is.
    let places: [(from: Double, to: Double, shift: (x: Double, y: Double))]

    private let shares: [PaintShare]
    private let press: InkPress
    private let width: Double
    private let seed: Double
    private var sheet: PrintPaint.Sheet?
    /// Each ink where it lies: the pixels it may reach and how much of it each takes.
    private var inks: [(left: Int, right: Int, top: Int, bottom: Int, much: [Float])] = []
    private var whole: PaintFrame?

    /// How long after one impression the next is made, and how long one takes to be there.
    static let apart = 0.34, takes = 0.26
    /// The paper printed on.
    static let paper = [240.0, 232, 212]
    /// How much of what is under an ink shows through it.
    static let sheer = 0.55

    /// How long the inks of `count` colours take.
    static func time(_ count: Int) -> Double {
        count > 0 ? PrintPaint.appear + Double(count - 1) * apart + takes : 0
    }

    init(shares: [PaintShare], width: Double, seed: Int, press: InkPress) {
        self.shares = shares
        self.press = press
        self.width = width
        self.seed = Double(seed)
        (wide, high) = PrintPaint.size(width: width)
        var random = PaintRandom(seed + 57)
        places = Paint.spans(shares, width: width).map { span in
            (span.0, span.1, (1.7 * (random.next() * 2 - 1), 1.6 * (random.next() * 2 - 1)))
        }
        last = Self.time(shares.count)
        length = last
    }

    private func prepare() -> PrintPaint.Sheet {
        if let sheet { return sheet }
        var made = PrintPaint.sheet(paper: Self.paper, width: width, seed: seed, plate: false)
        let S = Double(PrintPaint.scale), pad = Paint.pad
        if press == .stone {
            // The printer's register marks at the bar's ends: a cross in a ring.
            let reach = 2.3, hair = 0.16
            for centre in [-3.6, width + 3.6] {
                let from = max(0, Int((centre - reach - 1 + pad) * S)), to = min(wide - 1, Int((centre + reach + 1 + pad) * S))
                for j in max(0, Int((Paint.bar / 2 - reach - 1 + pad) * S))...min(high - 1, Int((Paint.bar / 2 + reach + 1 + pad) * S)) {
                    for i in from...to {
                        let x = (Double(i) + 0.5) / S - pad - centre, y = (Double(j) + 0.5) / S - pad - Paint.bar / 2
                        let ring = abs((x * x + y * y).squareRoot() - reach * 0.6)
                        let cross = abs(x) <= reach && abs(y) <= reach ? min(abs(x), abs(y)) : 9
                        let mark = Float(0.75 * min(1, max(0, (hair - min(ring, cross)) * S + 0.5)))
                        if mark <= 0 { continue }
                        let k = j * wide + i
                        made.red[k] += (40 - made.red[k]) * mark
                        made.green[k] += (36 - made.green[k]) * mark
                        made.blue[k] += (32 - made.blue[k]) * mark
                    }
                }
            }
        }
        inks = places.enumerated().map { index, place in
            let block = InkBlock(left: place.from - InkBlock.over + place.shift.x, right: place.to + InkBlock.over + place.shift.x,
                                 top: place.shift.y, bottom: Paint.bar + place.shift.y, seed: seed + 13 * Double(index))
            let left = max(0, Int((place.from + place.shift.x - 4 + pad) * S)), right = min(wide - 1, Int((place.to + place.shift.x + 4 + pad) * S))
            let top = max(0, Int((place.shift.y - 3 + pad) * S)), bottom = min(high - 1, Int((Paint.bar + place.shift.y + 3 + pad) * S))
            var much = [Float]()
            much.reserveCapacity(max(0, right - left + 1) * max(0, bottom - top + 1))
            if left <= right, top <= bottom {
                for j in top...bottom {
                    for i in left...right {
                        much.append(Float(block.ink((Double(i) + 0.5) / S - pad, (Double(j) + 0.5) / S - pad, press: press)))
                    }
                }
            }
            return (left, right, top, bottom, much)
        }
        sheet = made
        return made
    }

    func frame(age: Double) -> PaintFrame {
        if age >= length, let whole { return whole }
        var out = PaintFrame(wide: wide, high: high)
        guard age > 0, !shares.isEmpty else { return out }
        var paper = prepare()
        let sheer = Float(Self.sheer)
        for (index, ink) in inks.enumerated() {
            let there = Float(Paint.ease((age - PrintPaint.appear - Double(index) * Self.apart) / Self.takes))
            if there <= 0 || ink.left > ink.right || ink.top > ink.bottom { continue }
            let colour = shares[index].rgb.map { Float($0) }
            var q = 0
            for j in ink.top...ink.bottom {
                for i in ink.left...ink.right {
                    let much = ink.much[q] * there
                    q += 1
                    if much <= 0 { continue }
                    let k = j * wide + i
                    paper.red[k] += (paper.red[k] * colour[0] / 255 * sheer + colour[0] * (1 - sheer) - paper.red[k]) * much
                    paper.green[k] += (paper.green[k] * colour[1] / 255 * sheer + colour[1] * (1 - sheer) - paper.green[k]) * much
                    paper.blue[k] += (paper.blue[k] * colour[2] / 255 * sheer + colour[2] * (1 - sheer) - paper.blue[k]) * much
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

/// One paint's swatch for a colour print: a slip of paper with a small
/// impression of that ink.
final class InkStamp: PaintPainter, @unchecked Sendable {
    let wide = Int(2 * Paint.half) * PrintPaint.scale
    let high = Int(2 * Paint.half) * PrintPaint.scale
    let length = PrintPaint.appear + InkStrip.takes

    private let rgb: [Double]
    private let press: InkPress
    private let seed: Double
    private var made: (paper: PrintPaint.Sheet, much: [Float])?

    init(rgb: [Double], index: Int, seed: Int, press: InkPress) {
        self.rgb = rgb
        self.press = press
        self.seed = Double(seed + 3 * index)
    }

    func frame(age: Double) -> PaintFrame {
        var out = PaintFrame(wide: wide, high: high)
        guard age > 0 else { return out }
        let S = Double(PrintPaint.scale), half = PrintPaint.markHalf
        if made == nil {
            let block = InkBlock(left: -half, right: half, top: -half, bottom: half, seed: seed)
            made = (PrintPaint.slip(paper: InkStrip.paper, seed: seed), (0..<(wide * high)).map { k in
                let x = (Double(k % wide) + 0.5) / S - Paint.half, y = (Double(k / wide) + 0.5) / S - Paint.half
                return abs(x) > half + 2 || abs(y) > half + 2 ? 0 : Float(block.ink(x, y, press: press))
            })
        }
        guard let made else { return out }
        let there = Paint.ease((age - PrintPaint.appear) / InkStrip.takes), shown = Paint.ease(age / PrintPaint.appear)
        for k in 0..<(wide * high) where made.paper.cover[k] > 0 {
            let much = Double(made.much[k]) * there, q = 4 * k
            for (c, under) in [made.paper.red[k], made.paper.green[k], made.paper.blue[k]].enumerated() {
                let under = Double(under)
                out.bytes[q + c] = Paint.byte(under + (under * rgb[c] / 255 * InkStrip.sheer + rgb[c] * (1 - InkStrip.sheer) - under) * much)
            }
            out.bytes[q + 3] = Paint.byte(255 * Double(made.paper.cover[k]) * shown)
        }
        return out
    }
}

// MARK: - A photograph's tones

/// The bar of a photograph (Mateusz 2026-11-12 10:47: „fotografia -
/// gradientowy pasek z lekkim ziarnem”): its tones from the darkest to
/// the lightest, as a histogram has them, going over into each other
/// without a seam, each about as wide as its share, under the grain of
/// the film.
final class PhotoStrip: PaintPainter, @unchecked Sendable {
    let wide: Int
    let high: Int
    let length = PrintPaint.appear
    /// The tones' places: where along the bar each is itself.
    let stops: [(at: Double, rgb: [Double])]

    private let width: Double
    private let seed: Double
    private var whole: PaintFrame?

    /// How round the bar's corners are, and how strong the grain is.
    static let corner = 3.0, grain = 0.1

    init(shares: [PaintShare], width: Double, seed: Int) {
        self.width = width
        self.seed = Double(seed)
        (wide, high) = PrintPaint.size(width: width)
        let order = shares.sorted { PrintPaint.lightness($0.rgb) < PrintPaint.lightness($1.rgb) }
        stops = zip(order, Paint.spans(order, width: width)).map { (($1.0 + $1.1) / 2, $0.rgb) }
    }

    /// The tone at `x` along the bar.
    func tone(at x: Double) -> [Double] {
        guard let first = stops.first, let last = stops.last else { return [0, 0, 0] }
        if x <= first.at { return first.rgb }
        for (a, b) in zip(stops, stops.dropFirst()) where x < b.at {
            let part = (x - a.at) / max(0.001, b.at - a.at)
            // Not a straight ramp: a tone holds a little about its own place.
            return PrintPaint.mixed(a.rgb, b.rgb, 0.6 * part + 0.4 * Paint.ease(part))
        }
        return last.rgb
    }

    func frame(age: Double) -> PaintFrame {
        if age >= length, let whole { return whole }
        var out = PaintFrame(wide: wide, high: high)
        guard age > 0, !stops.isEmpty else { return out }
        let S = Double(PrintPaint.scale), pad = Paint.pad, shown = Paint.ease(age / length), r = Self.corner
        let tones = (0..<wide).map { tone(at: (Double($0) + 0.5) / S - pad) }
        for j in max(0, Int((pad - 1) * S))...min(high - 1, Int((pad + Paint.bar + 1) * S)) {
            let y = (Double(j) + 0.5) / S - pad
            for i in max(0, Int((pad - 1) * S))...min(wide - 1, Int((pad + width + 1) * S)) {
                let x = (Double(i) + 0.5) / S - pad
                let qx = abs(x - width / 2) - width / 2 + r, qy = abs(y - Paint.bar / 2) - Paint.bar / 2 + r
                let away = (max(qx, 0) * max(qx, 0) + max(qy, 0) * max(qy, 0)).squareRoot() + min(max(qx, qy), 0) - r
                let cover = min(1, max(0, 0.5 - away * S))
                if cover <= 0 { continue }
                // The film's grain: fine, a little clumped, the same in all three colours.
                let speck = 0.6 * Paint.noise(x / 0.4, y / 0.4, 91 + seed) + 0.4 * Paint.noise(x / 1.1, y / 1.1, 92 + seed)
                let lit = 1 + Self.grain * 2 * (speck - 0.5)
                let q = 4 * (j * wide + i)
                out.bytes[q] = Paint.byte(tones[i][0] * lit)
                out.bytes[q + 1] = Paint.byte(tones[i][1] * lit)
                out.bytes[q + 2] = Paint.byte(tones[i][2] * lit)
                out.bytes[q + 3] = Paint.byte(255 * cover * shown)
            }
        }
        if age >= length { whole = out }
        return out
    }
}

/// One colour's swatch for a photograph: a small print of that tone,
/// with the same grain.
final class PhotoChip: PaintPainter, @unchecked Sendable {
    let wide = Int(2 * Paint.half) * PrintPaint.scale
    let high = Int(2 * Paint.half) * PrintPaint.scale
    let length = PrintPaint.appear

    private let rgb: [Double]
    private let seed: Double

    init(rgb: [Double], index: Int, seed: Int) {
        self.rgb = rgb
        self.seed = Double(seed + 3 * index)
    }

    func frame(age: Double) -> PaintFrame {
        var out = PaintFrame(wide: wide, high: high)
        guard age > 0 else { return out }
        let S = Double(PrintPaint.scale), half = PrintPaint.markHalf, r = PhotoStrip.corner, shown = Paint.ease(age / length)
        for k in 0..<(wide * high) {
            let x = (Double(k % wide) + 0.5) / S - Paint.half, y = (Double(k / wide) + 0.5) / S - Paint.half
            let qx = abs(x) - half + r, qy = abs(y) - half + r
            let away = (max(qx, 0) * max(qx, 0) + max(qy, 0) * max(qy, 0)).squareRoot() + min(max(qx, qy), 0) - r
            let cover = min(1, max(0, 0.5 - away * S))
            if cover <= 0 { continue }
            let speck = 0.6 * Paint.noise(x / 0.4, y / 0.4, 91 + seed) + 0.4 * Paint.noise(x / 1.1, y / 1.1, 92 + seed)
            let lit = 1 + PhotoStrip.grain * 2 * (speck - 0.5), q = 4 * k
            out.bytes[q] = Paint.byte(rgb[0] * lit)
            out.bytes[q + 1] = Paint.byte(rgb[1] * lit)
            out.bytes[q + 2] = Paint.byte(rgb[2] * lit)
            out.bytes[q + 3] = Paint.byte(255 * cover * shown)
        }
        return out
    }
}
