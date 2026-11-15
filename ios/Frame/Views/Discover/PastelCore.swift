import Foundation

// Pastel's own bar (Mateusz 2026-11-15 09:39, of Wyspiański's „Śpiące
// dziecko na poduszce”: „Czy pastel mógłby mieć bardziej adekwatny pasek
// koloru? Teraz wygląda jak kredka”). Sketches 42–45; 10:07: „Może każdy
// kolor powinien zawierać trochę miękkiego, trochę bokiem i trochę
// kreski?”; 10:18: „Spokojniej. Diagonalnie”; 10:25: „skosy na całą
// wysokość paska … gdy mamy np. Błękit, to jego segment składa się z
// części rozmazanej, rysowanej bokiem i części kreska”; 10:51: G1b. Each
// colour's place along the bar in three parts from the left: rubbed in
// with a finger, laid with the stick's side in diagonals the bar's whole
// height, drawn with its tip in lines on the same diagonal. Crayon and
// chalk keep their hatching (`DryPlan`).

/// What the pastel's bar and swatches share: the paper's tooth, the
/// stick's strokes and lines, and the picture they are laid in.
enum Pastel {
    /// The diagonals' slant from the bar's length, in degrees: they go up to the right.
    static let slant = 35.0
    /// How much of a colour's place is rubbed, and laid with the side; the rest is lines.
    static let parts = (rubbed: 0.45, side: 0.33)
    /// How far apart the side's strokes are, and the lines (points); at most this many lines.
    static let sideGap = 6.5, lineGap = 5.0, lines = 3
    /// How far a finger spreads the powder where it rubs, and elsewhere (points, along and across).
    static let rubbed = 1.7, touched = 0.7
    /// On the dark page the stick is pressed harder: its paper's hollows
    /// would show the black page, and the bar reads dirty.
    static let darker = 0.12
    /// Pastel is pigment in white chalk: a touch lighter and duller than the paint.
    static let chalk: [Double] = [237, 232, 222]

    static func chalky(_ rgb: [Double], _ k: Double) -> [Double] { zip(rgb, chalk).map { $0 * (1 - k) + $1 * k } }

    /// The same pastel a little lighter (`k` > 0) or darker: sticks of one colour come in tints.
    static func shade(_ rgb: [Double], _ k: Double) -> [Double] {
        rgb.map { k > 0 ? $0 + (255 - $0) * k : $0 * (1 + k) }
    }

    /// The paper's tooth at a point: high where the stick touches, 0…1.
    /// `fine`: the grain alone, without the felt's larger lumps.
    static func tooth(_ x: Double, _ y: Double, _ seed: Double, fine: Bool = false) -> Double {
        let a = Paint.noise(x / 0.9, y / 0.9, 81 + seed), b = Paint.noise(x / 1.8, y / 1.8, 82 + seed)
        let small = spread(0.5 * a + 0.5 * b, 0.8)
        if fine { return small }
        let felt = 0.35 * Paint.noise(x / 1.0, y / 1.0, 83 + seed) + 0.42 * Paint.noise(x / 1.9, y / 1.9, 84 + seed)
            + 0.23 * Paint.noise(x / 5.7, y / 5.7, 85 + seed)
        return spread(0.6 * small + 0.4 * spread(felt, 0.95), 1.4)
    }

    /// Smooth noise about 0, as far from it as the sketch's was (`Paint.noise`
    /// strays twice as far from its middle as the sketch's blurred noise).
    static func wobble(_ x: Double, _ y: Double, _ seed: Double) -> Double { (Paint.noise(x, y, seed) - 0.5) * 0.55 }

    /// Noise of 0.5 on average pulled apart to fill 0…1 as the sketch's did.
    static func spread(_ v: Double, _ k: Double) -> Double { min(1, max(0, 0.5 + (v - 0.5) * k)) }

    /// What the stick leaves: where the tooth stands higher than what the pressure does not reach.
    static func deposit(_ pressure: Double, tooth: Double, soft: Double) -> Double {
        pressure > 0.01 ? Paint.step(1 - pressure - soft, 1 - pressure + soft, tooth) : 0
    }

    /// The pixels a pastel picture is painted in: premultiplied colour and how much is there.
    struct Canvas: Sendable {
        let wide: Int, high: Int
        /// Points in from the picture's upper left corner to its origin.
        let origin: Double
        var red: [Float], green: [Float], blue: [Float], cover: [Float]

        init(wide: Int, high: Int, origin: Double) {
            self.wide = wide
            self.high = high
            self.origin = origin
            let n = wide * high
            red = [Float](repeating: 0, count: n)
            green = red
            blue = red
            cover = red
        }

        /// A pixel's middle in points from the origin.
        func point(_ k: Int) -> (x: Double, y: Double) {
            let S = Double(Paint.scale)
            return ((Double(k % wide) + 0.5) / S - origin, (Double(k / wide) + 0.5) / S - origin)
        }

        /// `rgb` laid over what is there, `much` of it.
        mutating func put(_ rgb: [Double], _ much: Float, at k: Int) {
            guard much > 0 else { return }
            let a = min(1, much), keep = 1 - a
            red[k] = red[k] * keep + Float(rgb[0]) * a
            green[k] = green[k] * keep + Float(rgb[1]) * a
            blue[k] = blue[k] * keep + Float(rgb[2]) * a
            cover[k] = cover[k] * keep + a
        }

        /// Spread by a finger: a blur `along` points along the bar and `across` it.
        mutating func rub(along: Double, across: Double) {
            for c in 0..<4 {
                var channel = c == 0 ? red : c == 1 ? green : c == 2 ? blue : cover
                Pastel.blur(&channel, wide: wide, high: high, sx: along * Double(Paint.scale), sy: across * Double(Paint.scale))
                switch c {
                case 0: red = channel
                case 1: green = channel
                case 2: blue = channel
                default: cover = channel
                }
            }
        }

        /// Pressed into the tooth: more of the powder stays, never more than all.
        mutating func fill(_ k: Float) {
            for q in cover.indices where cover[q] > 0 {
                let f = min(k, 1 / max(cover[q], 0.0001))
                red[q] *= f
                green[q] *= f
                blue[q] *= f
                cover[q] *= f
            }
        }

        /// The tooth's hollows show through again: `keep`, how much of them the powder fills.
        mutating func grain(_ keep: Double, seed: Double) {
            for q in cover.indices where cover[q] > 0 {
                let p = point(q)
                let g = Float(keep + (1 - keep) * Paint.step(0.15, 0.75, Pastel.tooth(p.x, p.y, seed, fine: true)))
                red[q] *= g
                green[q] *= g
                blue[q] *= g
                cover[q] *= g
            }
        }
    }

    /// A Gaussian blur of a picture's channel, `sx` and `sy` pixels.
    static func blur(_ values: inout [Float], wide: Int, high: Int, sx: Double, sy: Double) {
        func kernel(_ sigma: Double) -> [Float] {
            let r = max(1, Int(3 * sigma))
            let k = (-r...r).map { Float(exp(-Double($0 * $0) / (2 * sigma * sigma))) }
            let sum = k.reduce(0, +)
            return k.map { $0 / sum }
        }
        if sx > 0.01 {
            let k = kernel(sx), r = k.count / 2
            var out = values
            for y in 0..<high {
                let row = y * wide
                for x in 0..<wide {
                    var sum: Float = 0
                    for (i, w) in k.enumerated() {
                        sum += values[row + min(wide - 1, max(0, x + i - r))] * w
                    }
                    out[row + x] = sum
                }
            }
            values = out
        }
        if sy > 0.01 {
            let k = kernel(sy), r = k.count / 2
            var out = values
            for y in 0..<high {
                for x in 0..<wide {
                    var sum: Float = 0
                    for (i, w) in k.enumerated() {
                        sum += values[min(high - 1, max(0, y + i - r)) * wide + x] * w
                    }
                    out[y * wide + x] = sum
                }
            }
            values = out
        }
    }

    /// One stroke of the stick's side: a band from `from` to `to`, `wide`
    /// points across, lighter at its ends and at the stick's edge, streaked
    /// along its way by the stick's grit (sketch 42's `stroke_mask`).
    struct Stroke: Sendable {
        var from: (x: Double, y: Double), to: (x: Double, y: Double)
        var wide: Double
        var taper: Double
        var bend: Double
        var seed: Double

        var box: (left: Double, top: Double, right: Double, bottom: Double) {
            let r = wide / 2 + abs(bend) + 1.5
            return (min(from.x, to.x) - r, min(from.y, to.y) - r, max(from.x, to.x) + r, max(from.y, to.y) + r)
        }

        /// How much of the stroke is at a point, how hard it is pressed
        /// there, and how far along it the point is (0…1).
        func at(_ x: Double, _ y: Double) -> (much: Double, pressure: Double, along: Double) {
            let dx = to.x - from.x, dy = to.y - from.y, long = max(0.000_001, hypot(dx, dy))
            let ux = dx / long, uy = dy / long
            let u = ((x - from.x) * ux + (y - from.y) * uy) / long
            let v = (-(x - from.x) * uy + (y - from.y) * ux) - bend * sin(Double.pi * min(1, max(0, u)))
            let edge = Pastel.wobble(x / 3.3, y / 3.3, seed) * wide * 0.35
            let across = Paint.step(-0.6, 0.6, wide / 2 - abs(v) + edge)
            guard across > 0 else { return (0, 0, u) }
            let tail = Pastel.wobble(x / 2.2, y / 2.2, seed + 1) * 0.15
            let along = Paint.step(0, taper, u) * Paint.step(0, taper * 0.6, 1 - u + tail)
            let pressure = 0.55 + 0.45 * sqrt(sin(Double.pi * min(1, max(0, u))))
            // The grit's streaks run along the stroke.
            let streaks = 0.5 + Pastel.wobble(u * long / 8.8, v / 0.55, seed + 2)
            return (across * along, pressure * (0.75 + 0.25 * streaks), u)
        }
    }

    /// A line of the tip through three points: tapering in and out, its
    /// width and pressure changing along it, broken where the tooth's
    /// hollows are.
    struct Line: Sendable {
        var points: [(x: Double, y: Double)]
        var wide: Double
        var pressure: Double
        var seed: Double

        /// Its middle, a point each third of a point along it.
        var path: [(x: Double, y: Double)] {
            let a = points[0], b = points[1], c = points[2]
            let long = hypot(b.x - a.x, b.y - a.y) + hypot(c.x - b.x, c.y - b.y)
            let n = max(24, Int(long * 3))
            // A curve through the three: a quadratic whose middle passes through `b`.
            let m = (x: 2 * b.x - (a.x + c.x) / 2, y: 2 * b.y - (a.y + c.y) / 2)
            return (0...n).map { i in
                let t = Double(i) / Double(n), s = 1 - t
                return (s * s * a.x + 2 * s * t * m.x + t * t * c.x, s * s * a.y + 2 * s * t * m.y + t * t * c.y)
            }
        }

        var box: (left: Double, top: Double, right: Double, bottom: Double) {
            let xs = points.map(\.x), ys = points.map(\.y), r = wide + 1.5
            return (xs.min()! - r, ys.min()! - r, xs.max()! + r, ys.max()! + r)
        }

        /// Its widths along it, a few knots to go between.
        func widths() -> [Double] {
            var random = PaintRandom(Int(seed) * 7 + 3)
            return (0..<7).map { _ in 0.75 + 0.5 * random.next() }
        }
    }

    /// How much of `line` covers each pixel of `canvas` in its box, and
    /// how far along it (0…1) each is.
    static func lay(_ line: Line, on canvas: Canvas, darker: Double) -> [(k: Int, much: Float, along: Float)] {
        let path = line.path, box = line.box, S = Double(Paint.scale), knots = line.widths()
        let left = max(0, Int((box.left + canvas.origin) * S)), right = min(canvas.wide - 1, Int((box.right + canvas.origin) * S))
        let top = max(0, Int((box.top + canvas.origin) * S)), bottom = min(canvas.high - 1, Int((box.bottom + canvas.origin) * S))
        guard left <= right, top <= bottom else { return [] }
        var out = [(k: Int, much: Float, along: Float)]()
        for j in top...bottom {
            for i in left...right {
                let k = j * canvas.wide + i, p = canvas.point(k)
                var best = Double.infinity, at = 0
                for (n, q) in path.enumerated() {
                    let d = (p.x - q.x) * (p.x - q.x) + (p.y - q.y) * (p.y - q.y)
                    if d < best {
                        best = d
                        at = n
                    }
                }
                let along = Double(at) / Double(max(1, path.count - 1))
                let swell = pow(sin(Double.pi * along), 0.55)
                let f = along * Double(knots.count - 1), i0 = min(knots.count - 2, Int(f))
                let vary = knots[i0] + (knots[i0 + 1] - knots[i0]) * (f - Double(i0))
                let half = line.wide * swell * vary / 2
                let m = Paint.step(-0.3, 0.3, half - sqrt(best))
                guard m > 0 else { continue }
                let press = line.pressure * (0.75 + 0.25 * swell) + 0.12 * Pastel.wobble(p.x / 3.3, p.y / 3.3, line.seed)
                let much = m * deposit(press + darker, tooth: tooth(p.x, p.y, line.seed), soft: 0.1)
                if much > 0.002 { out.append((k, Float(much), Float(along))) }
            }
        }
        return out
    }

    /// How much of `stroke` covers each pixel of `canvas` in its box,
    /// pressed `press` hard, and how far along it each is.
    static func lay(_ stroke: Stroke, on canvas: Canvas, press: Double, soft: Double, darker: Double) -> [(k: Int, much: Float, along: Float)] {
        let box = stroke.box, S = Double(Paint.scale)
        let left = max(0, Int((box.left + canvas.origin) * S)), right = min(canvas.wide - 1, Int((box.right + canvas.origin) * S))
        let top = max(0, Int((box.top + canvas.origin) * S)), bottom = min(canvas.high - 1, Int((box.bottom + canvas.origin) * S))
        guard left <= right, top <= bottom else { return [] }
        var out = [(k: Int, much: Float, along: Float)]()
        for j in top...bottom {
            for i in left...right {
                let k = j * canvas.wide + i, p = canvas.point(k)
                let at = stroke.at(p.x, p.y)
                guard at.much > 0 else { continue }
                let much = at.much * deposit(press * at.pressure + darker, tooth: tooth(p.x, p.y, stroke.seed), soft: soft)
                if much > 0.002 { out.append((k, Float(much), Float(min(1, max(0, at.along))))) }
            }
        }
        return out
    }

    /// A mark laid on the picture: its colour, what it covers and when it is made.
    struct Mark: Sendable {
        var rgb: [Double]
        var laid: [(k: Int, much: Float, along: Float)]
        /// When the stick comes down and how long the mark takes.
        var at: Double
        var takes: Double
    }

    /// The picture at `age`: the ground shown as far as `shown(x, y)` says
    /// (0…1 for a point), the marks over it as far as they are made.
    static func frame(ground: Canvas, shown: (Double, Double) -> Double, marks: [Mark], age: Double) -> PaintFrame {
        var canvas = ground
        for k in canvas.cover.indices where canvas.cover[k] > 0 {
            let p = canvas.point(k), s = Float(shown(p.x, p.y))
            canvas.red[k] *= s
            canvas.green[k] *= s
            canvas.blue[k] *= s
            canvas.cover[k] *= s
        }
        for mark in marks where age > mark.at {
            let made = Float(min(1.2, (age - mark.at) / mark.takes))
            for (k, much, along) in mark.laid {
                let reached = min(1, max(0, (made - along) * 8))
                canvas.put(mark.rgb, much * reached, at: k)
            }
        }
        var out = PaintFrame(wide: canvas.wide, high: canvas.high)
        for k in canvas.cover.indices where canvas.cover[k] > 0.002 {
            let a = Double(canvas.cover[k]), q = 4 * k
            out.bytes[q] = Paint.byte(Double(canvas.red[k]) / a)
            out.bytes[q + 1] = Paint.byte(Double(canvas.green[k]) / a)
            out.bytes[q + 2] = Paint.byte(Double(canvas.blue[k]) / a)
            out.bytes[q + 3] = Paint.byte(255 * a)
        }
        return out
    }
}

/// The palette bar in pastel (sketch 45, G1b): the colours side by side
/// along it, each in three parts from its left: rubbed in, laid with the
/// side in diagonals, drawn with the tip; the accents on top, each a
/// rubbed smudge, two strokes of the side and a line, on the same
/// diagonal. Painted from the left, the side's strokes and the lines
/// following the ground.
final class PastelStrip: PaintPainter, @unchecked Sendable {
    let wide: Int
    let high: Int
    let length: Double

    private let shares: [PaintShare]
    private let width: Double
    private let seed: Int
    private let dark: Bool
    /// How long the ground takes along the bar.
    let sweep: Double
    private var made: (ground: Pastel.Canvas, marks: [Pastel.Mark])?
    private var whole: PaintFrame?

    /// How long the ground takes along the whole bar; how long after the
    /// ground reaches a place its side and its lines come; how long one
    /// stroke and one line take; how far apart the accents come.
    static let sides = 0.2, lines = 0.38, stroke = 0.07, line = 0.09, accents = 0.15

    /// How long the ground takes along the bar, of `count` colours side by side.
    static func sweep(_ count: Int) -> Double { 0.45 + 0.1 * Double(count) }

    /// How long the pastel takes over `shares`.
    static func time(_ shares: [PaintShare], width: Double) -> Double {
        guard !shares.isEmpty else { return 0 }
        let small = Paint.accents(shares).filter { $0 }.count
        return sweep(shares.count - small) + lines + line + 0.15 + Double(small) * accents + 0.2
    }

    /// Each colour's place along the bar in its three parts: where it
    /// begins, where its rubbed part ends, where the side's ends, where it
    /// ends (its lines between the last two). The accents have none.
    static func parts(_ shares: [PaintShare], width: Double) -> [(from: Double, rubbed: Double, side: Double, to: Double)] {
        let accent = Paint.accents(shares)
        return Paint.spans(shares.indices.filter { !accent[$0] }.map { shares[$0] }, width: width).map { span in
            let w = span.1 - span.0, a = span.0 + w * Pastel.parts.rubbed
            return (span.0, a, a + w * Pastel.parts.side, span.1)
        }
    }

    init(shares: [PaintShare], width: Double, seed: Int, dark: Bool = false) {
        self.shares = shares
        self.width = width
        self.seed = seed
        self.dark = dark
        wide = Int((width + 2 * Paint.pad).rounded()) * Paint.scale
        high = Int(Paint.bar + 2 * Paint.pad) * Paint.scale
        length = Self.time(shares, width: width)
        sweep = Self.sweep(shares.count - Paint.accents(shares).filter { $0 }.count)
    }

    /// When the ground reaches `x` along the bar.
    private func reached(_ x: Double) -> Double { sweep * min(1, max(0, (x + 6) / (width + 12))) }

    private func prepare() -> (ground: Pastel.Canvas, marks: [Pastel.Mark]) {
        if let made { return made }
        let H = Paint.bar, s = Double(seed), boost = dark ? Pastel.darker : 0
        let accent = Paint.accents(shares)
        let mains = shares.indices.filter { !accent[$0] }, small = shares.indices.filter { accent[$0] }
        let spans = Paint.spans(mains.map { shares[$0] }, width: width)
        var random = PaintRandom(seed + 61)
        // 1. The ground in every colour, the side laid broad along the bar.
        var ground = Pastel.Canvas(wide: wide, high: high, origin: Paint.pad)
        for (n, i) in mains.enumerated() {
            let c = Pastel.chalky(shares[i].rgb, 0.06)
            let x0 = spans[n].0, x1 = spans[n].1
            let a0 = x0 - (n > 0 ? 6 : 0.5), a1 = x1 + (n < mains.count - 1 ? 6 : 0.5)
            let k = max(2, Int((a1 - a0) / 20))
            for q in 0..<k {
                let cx = a0 + (a1 - a0) * (Double(q) + 0.5) / Double(k) + 6 * (random.next() - 0.5)
                let half = (a1 - a0) / Double(k) * 0.72 + 5
                let stroke = Pastel.Stroke(from: (cx - half, H / 2 + 4 * (random.next() - 0.5)), to: (cx + half, H / 2 + 4 * (random.next() - 0.5)),
                                           wide: H + 2, taper: 0.1, bend: 0, seed: s + 10 * Double(n) + Double(q))
                for laid in Pastel.lay(stroke, on: ground, press: 0.72, soft: 0.16, darker: boost) {
                    ground.put(c, laid.much * 0.95, at: laid.k)
                }
            }
        }
        // Rubbed hard in each colour's first part, lightly elsewhere.
        var hard = ground
        hard.rub(along: Pastel.rubbed, across: Pastel.rubbed * 0.7)
        hard.fill(1.45)
        hard.grain(0.74 + boost, seed: s)
        ground.rub(along: Pastel.touched, across: Pastel.touched * 0.7)
        ground.fill(1.35)
        ground.grain(0.68 + boost, seed: s)
        let parts = Self.parts(shares, width: width)
        for k in ground.cover.indices where ground.cover[k] > 0 || hard.cover[k] > 0 {
            let x = ground.point(k).x
            var soft = 0.0
            for part in parts { soft = max(soft, Paint.step(part.from - 4, part.from + 2, x) * (1 - Paint.step(part.rubbed - 3, part.rubbed + 5, x))) }
            let a = Float(soft), b = Float((1 - soft) * 0.92)
            ground.red[k] = hard.red[k] * a + ground.red[k] * b
            ground.green[k] = hard.green[k] * a + ground.green[k] * b
            ground.blue[k] = hard.blue[k] * a + ground.blue[k] * b
            ground.cover[k] = hard.cover[k] * a + ground.cover[k] * b
        }
        var marks = [Pastel.Mark]()
        let slant = Pastel.slant * Double.pi / 180
        // 2. The side's part: diagonals of the stick's side, the bar's whole height.
        for (n, i) in mains.enumerated() {
            let c = Pastel.chalky(shares[i].rgb, 0.04), part = parts[n]
            let count = max(2, Int(((part.side - part.rubbed) / Pastel.sideGap).rounded()))
            for q in 0..<count {
                let t = slant + (5 * (random.next() - 0.5)) * Double.pi / 180
                let r = (H + 1) / tan(t) / 2
                let cx = min(part.rubbed + (part.side - part.rubbed) * (Double(q) + 0.5) / Double(count) + 2.4 * (random.next() - 0.5),
                             width - r - 1.5)
                let stroke = Pastel.Stroke(from: (cx - r, H + 0.8), to: (cx + r, -0.8), wide: 5 + 1.2 * random.next(), taper: 0.12,
                                           bend: 0.6 * (random.next() - 0.5), seed: s + 700 + 17 * Double(n) + Double(q))
                let tint = [-0.06, 0, 0.06][Int(random.next() * 2.999)]
                let press = 0.84 + 0.08 * random.next() - boost * 0.8
                let laid = Pastel.lay(stroke, on: ground, press: press, soft: 0.1, darker: boost)
                marks.append(Pastel.Mark(rgb: Pastel.shade(c, tint), laid: laid, at: reached(cx) + Self.sides + Self.stroke * Double(q) * 0.5,
                                         takes: Self.stroke))
            }
        }
        // 3. The lines' part: two or three lines of the tip on the same diagonal.
        for (n, i) in mains.enumerated() {
            let c = shares[i].rgb, part = parts[n]
            let light = (c[0] + c[1] + c[2]) / 3 > 0.55 * 255
            let ink = Pastel.shade(c, light ? -0.2 : 0.22)
            let count = min(Pastel.lines, max(2, Int(((part.to - part.side) / Pastel.lineGap).rounded())))
            for q in 0..<count {
                let t = slant + (4 * (random.next() - 0.5)) * Double.pi / 180
                let r = (H - 1) / tan(t) / 2, bow = 0.8 * (random.next() - 0.5)
                let cx = min(part.side + (part.to - part.side) * (Double(q) + 0.5) / Double(count) + 1.6 * (random.next() - 0.5),
                             width - r - 1 - 2.2 * Double(count - 1 - q))
                let line = Pastel.Line(points: [(cx - r, H - 0.5), (cx + bow, H / 2 + bow), (cx + r, 0.5)], wide: 1.6 + 0.5 * random.next(),
                                       pressure: 0.7, seed: s + 900 + 5 * Double(n) + Double(q))
                marks.append(Pastel.Mark(rgb: ink, laid: Pastel.lay(line, on: ground, darker: boost),
                                         at: reached(cx) + Self.lines + Self.line * Double(q) * 0.5, takes: Self.line))
            }
        }
        // The accents, last: on the same diagonal, where `Paint.spots` puts them.
        let total = max(shares.reduce(0) { $0 + $1.weight }, 0.000_001)
        let longs = small.map { 16 + 8 * min(1, width * shares[$0].weight / total / Paint.touch) }
        let spots = Paint.spots(longs.map { $0 + 6 }, width: width, seams: spans.dropFirst().map(\.0), random: &random)
        for (n, i) in small.enumerated() {
            let c = shares[i].rgb, x = spots[n], yc = H * 0.54, at = sweep + Self.lines + 0.15 + Double(n) * Self.accents
            marks.append(contentsOf: Self.accent(c, x: x, y: yc, on: ground, at: at, seed: s + 100 + 7 * Double(n), darker: boost))
        }
        made = (ground, marks)
        return (ground, marks)
    }

    /// An accent: a small rubbed smudge, two strokes of the side and a line, on the diagonal.
    static func accent(_ c: [Double], x: Double, y yc: Double, on canvas: Pastel.Canvas, at: Double, seed s: Double, darker: Double,
                       size: Double = 1) -> [Pastel.Mark] {
        let t = Pastel.slant * Double.pi / 180, hx = 8.5 * size * cos(t), hy = 8.5 * size * sin(t)
        // The smudge, rubbed on its own.
        var smudge = Pastel.Canvas(wide: canvas.wide, high: canvas.high, origin: canvas.origin)
        let S = Double(Paint.scale), reach = 16 * size
        let left = max(0, Int((x - reach + canvas.origin) * S)), right = min(canvas.wide - 1, Int((x + reach + canvas.origin) * S))
        let top = max(0, Int((yc - reach + canvas.origin) * S)), bottom = min(canvas.high - 1, Int((yc + reach + canvas.origin) * S))
        var keys = [Int]()
        if left <= right, top <= bottom {
            let sc = Pastel.chalky(c, 0.08)
            for j in top...bottom {
                for i in left...right {
                    let k = j * canvas.wide + i, p = canvas.point(k)
                    let u = (p.x - x) * cos(-t) + (p.y - yc) * sin(-t), v = -(p.x - x) * sin(-t) + (p.y - yc) * cos(-t)
                    let r = hypot(u / (9 * size), v / (6 * size)) + Pastel.wobble(p.x / 2.6, p.y / 2.6, s) * 0.7
                    let much = Paint.step(-0.25, 0.25, 1 - r) * Pastel.deposit(0.5 + darker, tooth: Pastel.tooth(p.x, p.y, s), soft: 0.12)
                    smudge.put(sc, Float(much), at: k)
                    keys.append(k)
                }
            }
            smudge.rub(along: 0.6, across: 0.5)
            smudge.fill(1.1)
            smudge.grain(0.7 + darker, seed: s)
        }
        // A smudge is one colour: what it covers, at 0.6.
        let smudgeLaid = keys.compactMap { k -> (k: Int, much: Float, along: Float)? in
            smudge.cover[k] > 0.002 ? (k, smudge.cover[k] * 0.6, 0) : nil
        }
        var marks = [Pastel.Mark(rgb: Pastel.chalky(c, 0.08), laid: smudgeLaid, at: at, takes: 0.12)]
        for (q, dx) in [-2.2, 2.2].enumerated() {
            let stroke = Pastel.Stroke(from: (x - hx + dx * size, yc + hy), to: (x + hx + dx * size, yc - hy), wide: 6.5 * size, taper: 0.25,
                                       bend: 0.3, seed: s + 50 + Double(q))
            marks.append(Pastel.Mark(rgb: Pastel.chalky(c, 0.02), laid: Pastel.lay(stroke, on: canvas, press: 0.72, soft: 0.1, darker: darker),
                                     at: at + 0.06 + 0.05 * Double(q), takes: 0.07))
        }
        let line = Pastel.Line(points: [(x - hx * 0.95 + 0.5, yc + hy * 0.95), (x + 0.5, yc), (x + hx * 0.95 + 0.5, yc - hy * 0.95)],
                               wide: 2 * min(1, size + 0.15), pressure: 0.66, seed: s + 60)
        marks.append(Pastel.Mark(rgb: Pastel.shade(c, -0.15), laid: Pastel.lay(line, on: canvas, darker: darker), at: at + 0.18, takes: 0.08))
        return marks
    }

    func frame(age: Double) -> PaintFrame {
        if age >= length, let whole { return whole }
        guard age > 0, !shares.isEmpty else { return PaintFrame(wide: wide, high: high) }
        let (ground, marks) = prepare()
        let front = age / sweep * (width + 12) - 6
        // The stick's side going along: its front ragged, a little ahead at the bar's middle.
        let out = Pastel.frame(ground: ground, shown: { x, y in
            let edge = front - x + 2.5 * sin(Double.pi * min(1, max(0, y / Paint.bar))) + 8 * Pastel.wobble(y / 3, x / 9, Double(self.seed))
            return min(1, max(0, edge / 5))
        }, marks: marks, age: age)
        if age >= length { whole = out }
        return out
    }
}

/// One paint's swatch in pastel: a small patch of it in the bar's three
/// parts, a rubbed smudge, two diagonals of the side and a line.
final class PastelDab: PaintPainter, @unchecked Sendable {
    let wide = Int(2 * Paint.half) * Paint.scale
    let high = Int(2 * Paint.half) * Paint.scale
    static let length = 0.7
    var length: Double { Self.length }

    private let rgb: [Double]
    private let seed: Double
    private let dark: Bool
    private var marks: [Pastel.Mark]?
    private var whole: PaintFrame?

    init(rgb: [Double], index: Int, seed: Int, dark: Bool = false) {
        self.rgb = rgb
        self.seed = Double(seed + 7 * index)
        self.dark = dark
    }

    func frame(age: Double) -> PaintFrame {
        if age >= length, let whole { return whole }
        let empty = Pastel.Canvas(wide: wide, high: high, origin: Paint.half)
        guard age > 0 else { return PaintFrame(wide: wide, high: high) }
        if marks == nil {
            let boost = dark ? Pastel.darker : 0
            // The rubbed patch, then the side and the line over it, as on the bar.
            var all = PastelStrip.accent(rgb, x: -1, y: 0, on: empty, at: 0, seed: seed, darker: boost, size: 1.25)
            all[0].laid = all[0].laid.map { ($0.k, min(1, $0.much * 1.5), $0.along) }
            let t = Pastel.slant * Double.pi / 180, r = 6 / tan(t)
            for q in 0..<2 {
                let cx = 3 + 3.2 * Double(q)
                let line = Pastel.Line(points: [(cx - r, 6), (cx, 0), (cx + r, -6)], wide: 1.7, pressure: 0.7, seed: seed + 80 + Double(q))
                let light = (rgb[0] + rgb[1] + rgb[2]) / 3 > 0.55 * 255
                all.append(Pastel.Mark(rgb: Pastel.shade(rgb, light ? -0.2 : 0.22), laid: Pastel.lay(line, on: empty, darker: boost),
                                       at: 0.32 + 0.08 * Double(q), takes: 0.08))
            }
            marks = all
        }
        let out = Pastel.frame(ground: empty, shown: { _, _ in 1 }, marks: marks ?? [], age: age)
        if age >= length { whole = out }
        return out
    }
}
