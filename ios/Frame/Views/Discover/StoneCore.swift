import Foundation

// A lithograph of one colour (Mateusz 2026-11-15 14:50, of Géricault's
// „Konie jadące na jarmark”, Met, drawn in a pencil's hatching: „Czy to
// właściwy pasek koloru dla litografii?”; 15:03, of sketch 46: „A”). A
// lithograph is drawn with a greasy crayon on a stone ground with sand: the
// crayon takes only the tops of the grain, so the print has no lines, only
// soft grained tones, from a sparse dust of specks to a velvet black with
// pin-points of paper. Each tone the grain caught as much as the tone asks,
// the tones going over into one another, a faint trace of the crayon's
// passes on one diagonal under the grain.

/// The bar of a lithograph of one colour: its tones, lightest to darkest,
/// each as wide as its share (`LineStrip.plan`: the same tones, paper and
/// patches of colour as a work of lines), made by the stone's grain. The
/// grain comes out in passes of the crayon from the light end to the dark.
final class StoneStrip: PaintPainter, @unchecked Sendable {
    let wide: Int
    let high: Int
    let length: Double

    /// The tones and patches of colour, and the paper with them printed.
    private let lines: LineStrip
    private let width: Double
    private let seed: Double
    private let ink: [Float]
    private var made: (cover: [Float], grain: [Float], edge: [Float], along: [Float])?
    private var whole: PaintFrame?

    /// The diagonal of the crayon's passes (degrees from the bar's length,
    /// rising to the right); how much they move a tone; how far the grain's
    /// tones go into one another at a speck's edge; how much of a tone is a
    /// faint film between the specks; how long (points) the passes take to
    /// fill a place in.
    static let lean = 62.0, passes = 0.12, soft = 0.14, film = 0.12, front = 26.0
    /// Lithographic ink: a warm black, the work's darkest mixed into it.
    static let black = [30.0, 27, 24]

    /// How long the grain takes to come out, of `count` tones.
    static func time(_ count: Int) -> Double {
        count > 0 ? PrintPaint.appear + 0.9 + 0.15 * Double(count) : 0
    }

    init(shares: [PaintShare], width: Double, seed: Int) {
        self.width = width
        self.seed = Double(seed)
        let lines = LineStrip(shares: shares, width: width, seed: seed, tool: .pen)
        self.lines = lines
        wide = lines.wide
        high = lines.high
        let tonal = lines.plan.tones.filter { !$0.patch }
        let darkest = (tonal.last ?? lines.plan.tones.last).map { lines.plan.colours[$0.colour] } ?? Self.black
        ink = PrintPaint.mixed(darkest, Self.black, 0.8).map { Float($0) }
        length = Self.time(shares.count)
    }

    /// For each pixel of the bar's rows: how dark the crayon is to make it,
    /// the stone's grain there (its rank, 0…1: a tone `c` takes the
    /// highest `c` of it), where the crayon stops at the bar's edge, and
    /// its place along the passes' diagonal.
    private func prepare() -> (cover: [Float], grain: [Float], edge: [Float], along: [Float]) {
        if let made { return made }
        let S = Double(PrintPaint.scale), pad = Paint.pad, H = Paint.bar, rows = Brush.rows(high: high), s = seed
        let n = rows.count * wide
        var cover = [Float](repeating: 0, count: n), raw = [Double](repeating: 0, count: n)
        var edge = [Float](repeating: 0, count: n), along = [Float](repeating: 0, count: n)
        let angle = Self.lean * Double.pi / 180, ux = cos(angle), uy = -sin(angle), run = 1 / tan(angle)
        var plain = [Double](repeating: 0, count: wide)
        for i in 0..<wide { plain[i] = lines.plan.cover(at: min(max((Double(i) + 0.5) / S - pad, 0), width)) }
        for j in rows {
            let y = (Double(j) + 0.5) / S - pad
            for i in 0..<wide {
                let x = (Double(i) + 0.5) / S - pad, q = (j - rows.lowerBound) * wide + i
                // The sand-ground stone: a fine even tooth, a little coarser here and there.
                raw[q] = 0.45 * Paint.noise(x / 0.35, y / 0.35, 141 + s) + 0.4 * Paint.noise(x / 0.8, y / 0.8, 142 + s)
                    + 0.15 * Paint.noise(x / 3.5, y / 3.5, 143 + s)
                // The crayon's passes: streaks along the diagonal, felt less in the dark.
                let u = x * ux + y * uy, v = -x * uy + y * ux
                let pass = Paint.noise(u / 12.5, v / 2.2, 144 + s)
                let c = plain[i]
                cover[q] = Float(min(0.97, max(0, c + Self.passes * (pass - 0.5) * 2 * (1 - 0.6 * c))))
                // Where the crayon stops: the bar's edges, a little ragged, never ruled.
                let wob = (Paint.noise(x / 6, y / 6, 145 + s) - 0.5) * 0.6 + (Paint.noise(x / 1.5, y / 1.5, 146 + s) - 0.5) * 0.2
                let wob2 = (Paint.noise(x / 6, y / 6, 147 + s) - 0.5) * 0.6
                let inside = min(min(x + wob, width - x + wob2), min(y + 0.4 * wob2, H - y + 0.4 * wob))
                edge[q] = Float(Paint.step(-0.45, 0.45, inside))
                along[q] = Float(x - (H / 2 - y) * run)
            }
        }
        // The grain by rank, so a tone covers as much of it as it asks, however the noise is spread.
        var grain = [Float](repeating: 0, count: n)
        let order = raw.indices.sorted { raw[$0] < raw[$1] }
        let unit: Float = n > 1 ? 1 / Float(n - 1) : 0
        for (rank, q) in order.enumerated() { grain[q] = Float(rank) * unit }
        let ready = (cover: cover, grain: grain, edge: edge, along: along)
        made = ready
        return ready
    }

    /// How much of the work's ink the crayon leaves at a pixel for a tone
    /// `c` on grain `g`: the grain's tops caught, a faint film between.
    static func caught(_ c: Float, grain g: Float) -> Float {
        let soft = Float(Self.soft)
        let t = min(1, max(0, (g - (1 - c - soft)) / (2 * soft)))
        return Float(Self.film) * c + 0.86 * t * t * (3 - 2 * t)
    }

    func frame(age: Double) -> PaintFrame {
        if age >= length, let whole { return whole }
        var out = PaintFrame(wide: wide, high: high)
        guard age > 0, !lines.plan.tones.isEmpty else { return out }
        let sheet = lines.paper(age: age), (cover, grain, edge, along) = prepare()
        let rows = Brush.rows(high: high)
        // The passes go from the light end to the dark, a place filling in as they go over it.
        let done = min(1, max(0, (age - PrintPaint.appear) / (length - PrintPaint.appear)))
        let reach = Float(-Self.front + (width + 2 * Self.front) * Paint.ease(done)), front = Float(Self.front)
        let shown = Float(Paint.ease(age / PrintPaint.appear))
        for j in 0..<high {
            let drawn = rows.contains(j) && done > 0
            for i in 0..<wide {
                let k = j * wide + i
                let paper = sheet.cover[k]
                if paper <= 0 { continue }
                var red = sheet.red[k], green = sheet.green[k], blue = sheet.blue[k]
                if drawn {
                    let q = (j - rows.lowerBound) * wide + i
                    let there = min(1, max(0, (reach - along[q]) / front))
                    let dark = edge[q] > 0 && there > 0 ? Self.caught(cover[q] * there * there * (3 - 2 * there), grain: grain[q]) * edge[q] : 0
                    if dark > 0 {
                        red += (ink[0] - red) * dark
                        green += (ink[1] - green) * dark
                        blue += (ink[2] - blue) * dark
                    }
                }
                let o = 4 * k
                out.bytes[o] = Paint.byte(Double(red))
                out.bytes[o + 1] = Paint.byte(Double(green))
                out.bytes[o + 2] = Paint.byte(Double(blue))
                out.bytes[o + 3] = Paint.byte(Double(255 * paper * shown))
            }
        }
        if age >= length { whole = out }
        return out
    }
}
