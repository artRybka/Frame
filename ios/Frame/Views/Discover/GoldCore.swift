import Foundation

// Gold on the bar that answers the phone's turn (Mateusz 2026-11-14 19:46:
// „Złoto - nie podobają mi się ‚płatki’ i czerwone kropki na krawędzi. A
// może wykorzystać żyroskop i złoto może faktycznie się mienić?”; 20:09,
// of sketch 41: „Złoto super.”). Of a work whose medium names gold, the
// colour of its picture that is the gold is laid over the bar in gold: a
// soft light travels along it as the phone turns (burnished leaf), and in
// gold paint (shell gold) its flakes catch the light each at its own
// angle. Held still it settles; with "Ogranicz ruch" it stands as held
// straight.

enum Gold {
    /// Beaten leaf, burnished: one soft light along it. Shell gold
    /// (powdered, in gum): the same, and its flakes glint.
    enum Kind: Sendable { case leaf, shell }

    /// Where the gold lies on a bar `width` wide and how it is laid.
    struct Place: Sendable, Equatable {
        var from: Double, to: Double
        var kind: Kind
    }

    /// Whether a work's medium names gold, and how it is laid, for the
    /// styles that are painted (oil and tempera, watercolour, gouache);
    /// nil for any other (a print's or a drawing's gold is not looked for).
    static func kind(medium: String, style: PaintStyle?) -> Kind? {
        guard let style, [.oil, .water, .gouache].contains(style) else { return nil }
        let words = PaintStyle.words(medium)
        guard words.contains(where: { word in named.contains(where: word.hasPrefix) || word == "oro" }) else { return nil }
        if words.contains(where: { word in leaves.contains(where: word.hasPrefix) }) { return .leaf }
        if words.contains(where: { word in paints.contains(where: word.hasPrefix) }) { return .shell }
        // A miniature's gold is painted; a panel's, laid in leaf.
        return style == .oil ? .leaf : .shell
    }

    /// Gold, in the museums' languages.
    private static let named = ["gold", "zlot", "zloc", "dore", "dorur", "goud", "vergold", "gilt", "gild", "guld", "pozlot", "pozlac"]
    /// Laid in leaf, and painted.
    private static let leaves = ["leaf", "platk", "blatt", "feuille", "blad", "gild", "gilt", "zlocon", "pozlac", "pozlot", "vergold", "kinji",
                                 "kinpaku"]
    private static let paints = ["paint", "shell", "powder", "farb", "ink", "tusz", "muschel", "poudre", "verf"]

    /// Which of the colours is the gold: a warm yellow of some strength
    /// and middling light, no accent (an accent is a touch on top of the
    /// bar, too small for gold to show); of several, the strongest.
    static func colour(_ shares: [PaintShare]) -> Int? {
        let found = shares.indices.filter { index in
            guard !shares[index].accent else { return false }
            let lab = PrintPaint.lab(shares[index].rgb), chroma = (lab.a * lab.a + lab.b * lab.b).squareRoot()
            let hue = atan2(lab.b, lab.a) * 180 / Double.pi
            return hue >= 55 && hue <= 100 && chroma >= 0.06 && lab.light >= 0.45 && lab.light <= 0.9
        }
        return found.max { chroma(shares[$0].rgb) < chroma(shares[$1].rgb) }
    }

    private static func chroma(_ rgb: [Double]) -> Double {
        let lab = PrintPaint.lab(rgb)
        return (lab.a * lab.a + lab.b * lab.b).squareRoot()
    }

    /// Where the gold colour lies on a bar of `style`, `width` wide.
    static func place(_ shares: [PaintShare], style: PaintStyle, width: Double, kind: Kind) -> Place? {
        guard let index = colour(shares) else { return nil }
        let accent = Paint.accents(shares)
        switch style {
        case .oil:
            // The oil's pulls lie along the bar by the shares of the colours that are no touches.
            if accent[index] { return nil }
            let mains = shares.indices.filter { !accent[$0] }
            let ground = max(mains.reduce(0) { $0 + shares[$1].weight }, 0.000_001), room = width - 6
            var x = 0.0
            for i in mains {
                let long = room * shares[i].weight / ground
                if i == index { return Place(from: x, to: x + long, kind: kind) }
                x += long
            }
            return nil
        case .water:
            if accent[index] { return nil }
            let mains = shares.indices.filter { !accent[$0] }
            guard let k = mains.firstIndex(of: index) else { return nil }
            let span = Paint.spans(mains.map { shares[$0] }, width: width)[k]
            return Place(from: span.0, to: span.1, kind: kind)
        default:
            let span = Paint.spans(shares, width: width)[index]
            return Place(from: span.0 - 1, to: span.1 + 1, kind: kind)
        }
    }
}

/// The gold laid over its place on the bar, for any turn of the phone:
/// a picture of just that place and a little round it, at the prints'
/// pixels, made anew as the phone turns (`image(tilt:)`, a few thousand
/// pixels).
final class GoldLeaf: @unchecked Sendable {
    let place: Gold.Place
    /// The picture's size in pixels and where its upper left corner lies, in the bar's points.
    let wide: Int
    let high: Int
    let origin: (x: Double, y: Double)

    private let seed: Double
    /// What does not change with the turn: how much of the gold is at a
    /// pixel, its tone's slow and fine unevenness.
    private var fixed: (cover: [Float], tone: [Float], fine: [Float])?
    /// Shell gold's flakes: each one's angle, and for each pixel the
    /// flakes whose light reaches it and how much (from `reach[k]` to
    /// `reach[k + 1]` in `flake` and `near`).
    private var flakes: (angle: [Double], reach: [Int32], flake: [Int32], near: [Float])?
    private var kept: (tilt: Int, frame: PaintFrame)?
    /// The contour where it runs over the gold's picture.
    private var line: (rgb: [Float], alpha: [Float])??

    private func lined() -> (rgb: [Float], alpha: [Float])? {
        if let line { return line }
        guard let drawn = bed?.line else {
            line = .some(nil)
            return nil
        }
        let S = Double(PrintPaint.scale)
        var rgb = [Float](repeating: 0, count: 3 * wide * high), alpha = [Float](repeating: 0, count: wide * high)
        for k in 0..<(wide * high) {
            let seen = GoldBed.sample(drawn, origin.x + (Double(k % wide) + 0.5) / S, origin.y + (Double(k / wide) + 0.5) / S)
            alpha[k] = Float(seen.alpha)
            rgb[3 * k] = Float(seen.rgb[0])
            rgb[3 * k + 1] = Float(seen.rgb[1])
            rgb[3 * k + 2] = Float(seen.rgb[2])
        }
        line = .some((rgb, alpha))
        return (rgb, alpha)
    }

    /// The gold from its shadow to its light, 0…1 each.
    static let deep = [0.50, 0.37, 0.13], middle = [0.76, 0.58, 0.24], pale = [0.97, 0.88, 0.58]
    /// What a flake's glint is: its colour, how near the turn must be to
    /// its own angle, how close the flakes lie (points).
    static let glint = [1.0, 0.96, 0.82], sharp = 0.18, cell = 1.05

    /// The bar under it, when the gold is one of its paints (Mateusz
    /// 2026-11-15 00:27: „czy ono zasłania pasek koloru czy jest jego
    /// elementem? … Jeżeli jest elementem - to trzeba go dać do wysokości
    /// paska? Nawet chyba pod czarna linia konturu”): the gold takes the
    /// shape of its paint (an oil's pulls, a watercolour's wash), and the
    /// contour drawn round the paint goes over it.
    private let bed: GoldBed?

    init(place: Gold.Place, seed: Int, bed: GoldBed? = nil) {
        self.place = place
        self.seed = Double(seed)
        self.bed = bed
        let S = Double(PrintPaint.scale)
        origin = (place.from - 2, -5)
        wide = Int(((place.to - place.from) + 4) * S)
        high = Int((Paint.bar + 10) * S)
    }

    /// Makes now what the first turn would: off the main thread, before it is shown.
    func ready() {
        _ = prepare()
        _ = lined()
        if place.kind == .shell { _ = scatter() }
    }

    private func prepare() -> (cover: [Float], tone: [Float], fine: [Float]) {
        if let fixed { return fixed }
        let S = Double(PrintPaint.scale), n = wide * high, s = seed
        var cover = [Float](repeating: 0, count: n), tone = [Float](repeating: 0, count: n), fine = [Float](repeating: 0, count: n)
        for k in 0..<n {
            let x = origin.x + (Double(k % wide) + 0.5) / S, y = origin.y + (Double(k / wide) + 0.5) / S
            let along = min(x - place.from + 1.0 * (Paint.noise(x / 3, y / 3, 94 + s) - 0.5), place.to - x + 1.0 * (Paint.noise(x / 3, y / 3, 95 + s) - 0.5))
            if let paint = bed?.paint {
                // As high as its paint, in the paint's own shape.
                cover[k] = Float(min(1, max(0, along * 3 + 0.5)) * GoldBed.sample(paint, x, y).alpha)
            } else {
                let edge = min(along, min(y + 0.3, Paint.bar + 0.3 - y))
                cover[k] = Float(min(1, max(0, edge * 3 + 0.5)))
            }
            tone[k] = Float(Paint.noise(x / 12, y / 12, 90 + s))
            var grain = 0.96 + 0.08 * Paint.noise(x / 0.9, y / 0.9, 91 + s)
            // Shell gold is a powder: a little rougher.
            if place.kind == .shell, Paint.noise(x / 0.6, y / 0.6, 99 + s) > 0.5 { grain *= 0.94 }
            fine[k] = Float(grain)
        }
        fixed = (cover, tone, fine)
        return (cover, tone, fine)
    }

    /// The gold with the phone turned `tilt` (-1…1 along the bar).
    func frame(tilt: Double) -> PaintFrame {
        let step = Int((max(-1, min(1, tilt)) * 100).rounded())
        if let kept, kept.tilt == step { return kept.frame }
        let tilt = Double(step) / 100
        let (cover, tone, fine) = prepare()
        var out = PaintFrame(wide: wide, high: high)
        let S = Double(PrintPaint.scale), long = place.to - place.from, H = Paint.bar
        // The light: a broad soft band, a little aslant, that travels along the gold as the phone turns.
        let centre = (place.from + place.to) / 2 + tilt * long * 0.75, spread = long * 0.28 + 8
        // How much each flake catches the light at this turn.
        let shining = place.kind == .shell ? scatter() : nil
        let caught = shining?.angle.map { angle -> Float in
            let turn = (tilt - angle) / Self.sharp
            return turn * turn > 9 ? 0 : Float(exp(-turn * turn))
        } ?? []
        for k in 0..<(wide * high) where cover[k] > 0 {
            let x = origin.x + (Double(k % wide) + 0.5) / S, y = origin.y + (Double(k / wide) + 0.5) / S
            let off = (x - centre - 0.25 * (y - H / 2)) / spread
            let light = min(1, max(0, 0.3 + 0.18 * (Double(tone[k]) - 0.5) + 0.62 * exp(-off * off)))
            let (dim, bright, part) = light < 0.5 ? (Self.deep, Self.middle, light / 0.5) : (Self.middle, Self.pale, (light - 0.5) / 0.5)
            let grain = Double(fine[k])
            var red = (dim[0] + (bright[0] - dim[0]) * part) * grain
            var green = (dim[1] + (bright[1] - dim[1]) * part) * grain
            var blue = (dim[2] + (bright[2] - dim[2]) * part) * grain
            if let shining {
                var sum: Float = 0
                for f in Int(shining.reach[k])..<Int(shining.reach[k + 1]) { sum += shining.near[f] * caught[Int(shining.flake[f])] }
                let shine = min(1, Double(sum) * 0.25) * 0.85
                if shine > 0 {
                    red += (Self.glint[0] - red) * shine
                    green += (Self.glint[1] - green) * shine
                    blue += (Self.glint[2] - blue) * shine
                }
            }
            let q = 4 * k
            out.bytes[q] = Paint.byte(255 * red)
            out.bytes[q + 1] = Paint.byte(255 * green)
            out.bytes[q + 2] = Paint.byte(255 * blue)
            out.bytes[q + 3] = Paint.byte(255 * Double(cover[k]))
        }
        // The contour over the gold, where it runs.
        if let line = lined() {
            for k in 0..<(wide * high) {
                let a = Double(line.alpha[k])
                if a <= 0.003 { continue }
                let q = 4 * k, below = Double(out.bytes[q + 3]) / 255, all = a + below * (1 - a)
                for c in 0..<3 {
                    let was = Double(out.bytes[q + c])
                    out.bytes[q + c] = Paint.byte((Double(line.rgb[3 * k + c]) * a + was * below * (1 - a)) / max(all, 0.0001))
                }
                out.bytes[q + 3] = Paint.byte(255 * all)
            }
        }
        kept = (step, out)
        return out
    }

    /// The flakes: one in each `cell`, somewhere in it, catching the
    /// light when the phone is turned near its own angle; its light a
    /// speck blurred over about half a point.
    private func scatter() -> (angle: [Double], reach: [Int32], flake: [Int32], near: [Float]) {
        if let flakes { return flakes }
        let S = Double(PrintPaint.scale), cell = Self.cell
        let gx0 = (origin.x / cell).rounded(.down) - 1, gy0 = (origin.y / cell).rounded(.down) - 1
        let columns = Int((Double(wide) / S / cell).rounded(.up)) + 3, rows = Int((Double(high) / S / cell).rounded(.up)) + 3
        var angle = [Double](), spot = [(x: Double, y: Double)]()
        for row in 0..<rows {
            for column in 0..<columns {
                let gx = gx0 + Double(column), gy = gy0 + Double(row)
                angle.append(-1.2 + 2.4 * Paint.hash(gx, gy, 96 + seed))
                spot.append(((gx + Paint.hash(gx, gy, 97 + seed)) * cell, (gy + Paint.hash(gx, gy, 98 + seed)) * cell))
            }
        }
        var reach: [Int32] = [0], flake = [Int32](), near = [Float]()
        for k in 0..<(wide * high) {
            let x = origin.x + (Double(k % wide) + 0.5) / S, y = origin.y + (Double(k / wide) + 0.5) / S
            let cx = Int((x / cell).rounded(.down) - gx0), cy = Int((y / cell).rounded(.down) - gy0)
            for row in max(0, cy - 1)...min(rows - 1, cy + 1) {
                for column in max(0, cx - 1)...min(columns - 1, cx + 1) {
                    let f = row * columns + column, dx = x - spot[f].x, dy = y - spot[f].y
                    let much = exp(-(dx * dx + dy * dy) / (2 * 0.5 * 0.5))
                    if much < 0.01 { continue }
                    flake.append(Int32(f))
                    near.append(Float(much))
                }
            }
            reach.append(Int32(flake.count))
        }
        flakes = (angle, reach, flake, near)
        return (angle, reach, flake, near)
    }
}

/// The bar a gold lies in: its paint, finished, and the contour drawn
/// round it alone; both in the bar's picture's pixels, whatever its scale.
struct GoldBed: @unchecked Sendable {
    var paint: PaintFrame?
    var line: PaintFrame?

    /// Made anew from a bar's painter of its own (not the one on the page, which paints elsewhere meanwhile).
    static func of(_ painter: PaintPainter) -> GoldBed {
        let contoured = painter as? ContouredStrip, inner = contoured?.inner ?? painter
        // An oil's paint as it is down, before the paper round it soaks its oil up: the gold lies on the paint, not on the stain.
        let paint = (inner as? OilStrip).map { $0.frame(age: $0.last + 0.05) } ?? inner.frame(age: inner.length)
        return GoldBed(paint: paint, line: contoured?.lineAlone())
    }

    /// A frame's colour (0…255) and how much is there at a point of the bar (points from its upper left corner), between its pixels.
    static func sample(_ frame: PaintFrame, _ x: Double, _ y: Double) -> (rgb: [Double], alpha: Double) {
        let scale = Double(frame.high) / (Paint.bar + 2 * Paint.pad)
        let fx = (x + Paint.pad) * scale - 0.5, fy = (y + Paint.pad) * scale - 0.5
        let i = Int(fx.rounded(.down)), j = Int(fy.rounded(.down)), u = fx - Double(i), v = fy - Double(j)
        var rgb = [0.0, 0.0, 0.0], alpha = 0.0
        for (di, dj, w) in [(0, 0, (1 - u) * (1 - v)), (1, 0, u * (1 - v)), (0, 1, (1 - u) * v), (1, 1, u * v)] where w > 0 {
            let a = frame.cover(i + di, j + dj)
            if a <= 0 { continue }
            let c = frame.colour(i + di, j + dj)
            rgb[0] += c.red * a * w
            rgb[1] += c.green * a * w
            rgb[2] += c.blue * a * w
            alpha += a * w
        }
        return alpha > 0 ? (rgb.map { $0 / alpha }, alpha) : ([0, 0, 0], 0)
    }
}
