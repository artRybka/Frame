import Foundation

// The colour bar of a drawing on tinted paper, or one heightened with
// white (Mateusz 2026-11-15 17:08, of Daniel Huntington's „Pani Sheppard
// Gandy w pozycji siedzącej”, „graphite, black crayon, brown crayon and
// white chalk on blue paper”, shown as grey crayon hatched over the whole
// bar: „Kolejny nietypowy przykład paska koloru.”). Of a random 6000 of
// the library's works about 130 are drawn in chalk, pencil or charcoal on
// a blue, grey, brown or green paper, nearly half of them heightened with
// white, and some twenty in black, red and white chalk; all were given
// the stick's hatching of every colour, the paper and the lights among
// them, or a pencil's lines on a cream paper.

/// A drawing on tinted paper: the paper as it is, its colour bare where
/// its share of the bar is, the drawing's loose lines all along and
/// denser as its tones darken (`LineStrip` on that paper); what is
/// lighter than the paper is white chalk laid in strokes the other way,
/// a colour off the paper's and the drawing's (red chalk, brown crayon)
/// that colour's chalk. Lightest to darkest, as the pencil's bar.
final class TonedStrip: PaintPainter, @unchecked Sendable {
    let wide: Int
    let high: Int
    let length: Double
    /// When the last of the chalk and the lines is down.
    let last: Double

    private let lines: LineStrip
    private let strokes: [LineStroke]
    /// Each stroke's stick's colour, `sticks[stroke.layer]`, and the part of the bar it keeps to.
    private let sticks: [[Float]]
    private let spans: [(from: Double, to: Double)]
    private let width: Double
    private let seed: Double
    private var whole: PaintFrame?
    private var tooth: [Float] = []
    private var keeps: [[Float]] = []
    private var laid: [[Float]] = []
    private var down = 0

    /// How much of what the drawing's tones ask its lines cover: a
    /// drawing's loose lines, not a print's hatching.
    static let thin = 0.8
    /// How much lighter than the paper the paper and the chalk are taken
    /// for the lines: the paper is bare for the most part, a few loose
    /// lines over it.
    static let bare = 0.07
    /// How far beyond the paper a stick's colour is from what the eye
    /// takes of its strokes on the paper: chalk is laid open, the paper
    /// between its strokes.
    static let lift = 1.9
    /// How much of its part of the bar the chalk covers.
    static let covers = 0.6
    /// The lights a drawing heightened with white has, when its colours
    /// hold none lighter than its paper: a share of the bar, and the
    /// chalk's white.
    static let lights = (share: 0.12, white: [247.0, 245, 236])
    /// When the chalk begins, as a part of the lines' time, and how long
    /// after the lines it may end.
    static let chalk = (from: 0.4, after: 0.3)
    /// The chalk's breadth and the softness of its edge (points), its
    /// directions (degrees from the bar's length: across the pencil's),
    /// how unevenly it is spaced and leans.
    static let stick = (wide: 1.7, soft: 0.75, sets: [116.0, 132], loose: 0.35, lean: 6.0)

    /// What each of a work's colours is in the drawing: the paper (the
    /// greatest of them that is no accent), a stick's (lighter than the
    /// paper: white chalk; off the line from the paper to the drawing's
    /// darkest, a colour of its own: red chalk, a brown crayon) or a tone
    /// of the drawing's lines. `lit`: the drawing is heightened with
    /// white, and when none of its colours is lighter than its paper,
    /// white chalk is added at `lights.share`. The colours to draw (with
    /// that white added), the paper, how light each is to be taken for
    /// the lines (a stick's as light as the paper) and each stick's colour.
    static func parts(_ shares: [PaintShare], lit: Bool) -> (shares: [PaintShare], paper: [Double], shades: [Double], sticks: [Int: [Double]]) {
        guard !shares.isEmpty else { return ([], [243, 235, 216], [], [:]) }
        let large = shares.indices.filter { !shares[$0].accent }
        let pool = large.isEmpty ? Array(shares.indices) : large
        let paperAt = pool.max { shares[$0].weight < shares[$1].weight } ?? 0
        let labs = shares.map { PrintPaint.lab($0.rgb) }
        let darkAt = pool.min { labs[$0].light < labs[$1].light } ?? paperAt
        // The drawing's tones lie between the paper and a black or a grey
        // as dark as its darkest: red chalk is no tone though it is the darkest.
        let paper = shares[paperAt].rgb, from = labs[paperAt], to = (light: labs[darkAt].light, a: 0.0, b: 0.0)
        var all = shares, shades = labs.map(\.light), sticks = [Int: [Double]]()
        for index in shares.indices where index != paperAt {
            let colour = labs[index]
            let part = from.light > to.light ? min(1, max(0, (from.light - colour.light) / (from.light - to.light))) : 0
            let a = colour.a - (from.a + (to.a - from.a) * part), b = colour.b - (from.b + (to.b - from.b) * part)
            let away = (a * a + b * b).squareRoot(), chroma = (colour.a * colour.a + colour.b * colour.b).squareRoot()
            if colour.light > from.light + 0.02 || (away > PrintPaint.apart && chroma > PrintPaint.faint) {
                sticks[index] = PrintPaint.mixed(paper, shares[index].rgb, lift).map { min(255, max(0, $0)) }
                shades[index] = from.light + bare
            }
        }
        shades[paperAt] = from.light + bare
        let lighter = sticks.keys.contains { labs[$0].light > from.light + 0.02 }
        if lit, !lighter {
            let total = shares.reduce(0) { $0 + $1.weight }
            let white = PrintPaint.mixed(paper, lights.white, 1 / lift)
            all.append(PaintShare(rgb: white, weight: total * lights.share / (1 - lights.share)))
            shades.append(from.light + bare)
            sticks[all.count - 1] = lights.white
        }
        return (all, paper, shades, sticks)
    }

    static func time(_ shares: [PaintShare], lit: Bool) -> Double {
        guard !shares.isEmpty else { return 0 }
        let (all, _, _, sticks) = parts(shares, lit: lit)
        let drawn = LineStrip.time(all.count)
        return sticks.isEmpty ? drawn : drawn + chalk.after + LineStrip.takes
    }

    init(shares: [PaintShare], width: Double, seed: Int, lit: Bool) {
        let (all, paper, shades, sticks) = Self.parts(shares, lit: lit)
        lines = LineStrip(shares: all, width: width, seed: seed, tool: .pencil, thin: Self.thin, paper: paper, shades: shades,
                          laid: true)
        (wide, high) = (lines.wide, lines.high)
        self.width = width
        self.seed = Double(seed)
        // Each stick's strokes over its colour's part of the bar.
        let H = Paint.bar, stick = Self.stick
        var random = PaintRandom(seed + 333), strokes = [LineStroke](), colours = [[Float]](), spans = [(from: Double, to: Double)]()
        for tone in lines.plan.tones {
            guard let rgb = sticks[tone.colour] else { continue }
            let layer = colours.count
            colours.append(rgb.map { Float($0) })
            spans.append((tone.from, tone.to))
            for degrees in stick.sets {
                // Two directions together cover as much as `covers`.
                let cover = 1 - (1 - Self.covers).squareRoot()
                var x = tone.from - 8
                while x < tone.to + 8 {
                    let angle = (degrees + stick.lean * (random.next() * 2 - 1)) * Double.pi / 180, slope = cos(angle) / sin(angle)
                    let y1 = -1.2 * random.next() + H * 0.12 * random.next(), y2 = H + 1.2 * random.next() - H * 0.12 * random.next()
                    let middle = x
                    strokes.append(LineStroke(ax: middle - (y1 - H / 2) * slope, ay: y1, bx: middle - (y2 - H / 2) * slope, by: y2,
                                              bow: 1.2 * (random.next() * 2 - 1), wide: stick.wide * (0.75 + 0.5 * random.next()),
                                              layer: layer, at: 0))
                    x += stick.wide * 0.8 / cover / max(0.35, abs(sin(angle))) * (1 + stick.loose * (random.next() * 2 - 1))
                }
            }
        }
        // One stroke after another, from a part of the way through the lines to a little after them.
        let begun = lines.length * Self.chalk.from, ended = lines.length + Self.chalk.after
        for k in strokes.indices {
            strokes[k].at = begun + (ended - begun) * Double(k) / Double(max(1, strokes.count - 1))
        }
        self.strokes = strokes
        self.sticks = colours
        self.spans = spans
        last = strokes.isEmpty ? lines.last : max(lines.last, ended + LineStrip.takes)
        length = strokes.isEmpty ? lines.length : max(lines.length, ended + LineStrip.takes)
    }

    func frame(age: Double) -> PaintFrame {
        if age >= length, let whole { return whole }
        var out = lines.frame(age: min(age, lines.length))
        guard !strokes.isEmpty, age > strokes[0].at else { return out }
        let S = Double(PrintPaint.scale), pad = Paint.pad, n = wide * high
        if tooth.isEmpty {
            // Chalk catches the paper's tooth: the tops of its grain.
            tooth = (0..<n).map { q in
                let v = Paint.noise(Double(q % wide) / S / 0.4, Double(q / wide) / S / 0.4, 171 + seed)
                return Float(min(1, max(0, 0.15 + 1.1 * v)))
            }
        }
        let done = strokes.prefix { $0.at + LineStrip.takes <= age }.count
        if laid.isEmpty || done < down {
            laid = sticks.map { _ in [Float](repeating: 0, count: n) }
            down = 0
        }
        for stroke in strokes[down..<done] {
            stroke.draw(part: 1, into: &laid[stroke.layer], wide: wide, high: high, origin: pad, soft: Self.stick.soft)
        }
        down = done
        var layers = laid
        for stroke in strokes[done...] {
            if stroke.at >= age { break }
            stroke.draw(part: (age - stroke.at) / LineStrip.takes, into: &layers[stroke.layer], wide: wide, high: high, origin: pad,
                        soft: Self.stick.soft)
        }
        if keeps.isEmpty {
            // The chalk keeps to its colour's part of the bar, its ends a little ragged, and to the bar's ends.
            for (index, span) in spans.enumerated() {
                var keep = [Float](repeating: 0, count: n)
                for k in 0..<n {
                    let x = (Double(k % wide) + 0.5) / S - pad, y = (Double(k / wide) + 0.5) / S - pad
                    guard x > span.from - 4, x < span.to + 4 else { continue }
                    let ragged = 2.5 * (Paint.noise(x / 3, y / 3, 181 + seed + Double(index)) - 0.5)
                    let inside: Double = min(x - span.from, span.to - x) + ragged
                    let ends: Double = min(1, max(0, (x + 0.5) * 1.5)) * min(1, max(0, (width + 0.5 - x) * 1.5))
                    keep[k] = Float(min(1, max(0, inside * 0.6 + 0.5)) * ends)
                }
                keeps.append(keep)
            }
        }
        for (index, layer) in layers.enumerated() {
            let rgb = sticks[index], keep = keeps[index]
            for k in 0..<n where layer[k] > 0 && keep[k] > 0 && out.bytes[4 * k + 3] > 0 {
                let much = Double(layer[k] * tooth[k] * keep[k] * 0.95), q = 4 * k
                for c in 0..<3 {
                    let under = Double(out.bytes[q + c])
                    out.bytes[q + c] = Paint.byte(under + (Double(rgb[c]) - under) * much)
                }
            }
        }
        if age >= length { whole = out }
        return out
    }
}
