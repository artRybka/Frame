import Foundation

// A woodcut or a linocut in black (Mateusz 2026-11-14 20:09, of sketch 41:
// „Drzeworyt C”): a block of ink that the cutter's gouge has cut its
// lighter tones out of. Its lines were thin all over in sketch 40, and he
// wanted the paper to show in larger places too (19:46: „może zrób
// większe wycięcia - czyli poza kreskami jeszcze 1 czy 2 wielksze
// pozostałości papieru”): two clearings, each cut as the cutter does it,
// in gouge strokes side by side with thin ridges of wood standing
// between them.

/// One cut of the gouge: a lens, pointed at both ends, from `top` to
/// `bottom` (points), its middle at `x` at the top and leaning `lean`
/// along the bar by the bottom.
struct GougeCut: Sendable {
    var x: Double, top: Double, bottom: Double, wide: Double, lean: Double

    /// How much of a point the cut takes away, 0…1, a pixel `pixel` points wide.
    func cut(_ px: Double, _ py: Double, pixel: Double) -> Double {
        guard py > top, py < bottom, bottom > top else { return 0 }
        let t = (py - top) / (bottom - top)
        let half = wide / 2 * pow(sin(Double.pi * t), 0.6)
        let away = abs(px - (x + lean * t))
        return min(1, max(0, (half - away) / pixel + 0.5))
    }

    /// The points along the bar it may reach.
    var reach: ClosedRange<Double> { (min(x, x + lean) - wide)...(max(x, x + lean) + wide) }
}

/// The bar of a woodcut or a linocut in black: its lightest tone the
/// paper, left bare where the block ends; the block's ink over the rest,
/// as dark as its darkest tone, with the gouge's cuts in it as many and as
/// wide as leave each tone's black, and two clearings: one in the
/// lighter tones, a smaller one in the dark. It is printed in one pull of
/// the baren, from the left.
final class WoodcutStrip: PaintPainter, @unchecked Sendable {
    let wide: Int
    let high: Int
    let length: Double
    let last: Double
    /// Where the block begins along the bar.
    let start: Double
    let cuts: [GougeCut]
    /// The two clearings: their middles and half sizes (points).
    let clearings: [(x: Double, y: Double, rx: Double, ry: Double)]

    private let width: Double
    private let seed: Double
    private let paper: [Double]
    private let ink: [Float]
    private let count: Int
    private var made: (sheet: PrintPaint.Sheet, much: [Float])?
    private var whole: PaintFrame?

    /// How far apart the gouge's lines are; how dark of the way from the
    /// paper to the ink a tone may be and still be among the lighter ones.
    static let pitch = 3.2, lighter = 0.75
    /// How much narrower than its share of a clearing a gouge stroke in it
    /// is: the rest stands as thin ridges of wood (sketch 41's „C”).
    static let ridge = 0.78

    /// How long the block takes to be printed, of `count` tones: the
    /// baren's pull along it.
    static func time(_ count: Int) -> Double {
        count > 0 ? PrintPaint.appear + 0.4 + 0.12 * Double(count) : 0
    }

    init(shares: [PaintShare], width: Double, seed: Int) {
        self.width = width
        self.seed = Double(seed)
        count = shares.count
        (wide, high) = PrintPaint.size(width: width)
        let H = Paint.bar
        let tones = shares.sorted { PrintPaint.lightness($0.rgb) > PrintPaint.lightness($1.rgb) }
        let lightest = tones.first?.rgb ?? [240, 232, 212], darkest = tones.last?.rgb ?? [26, 24, 22]
        paper = PrintPaint.mixed(lightest, [243, 235, 216], 0.5)
        ink = darkest.map { Float($0 * 0.55) }
        let spans = Paint.spans(tones, width: width)
        let lp = Brush.luminance(lightest), lk = Brush.luminance(darkest.map { $0 * 0.55 })
        func cover(_ rgb: [Double]) -> Double { (lp - Brush.luminance(rgb)) / max(lp - lk, 0.05) }
        // A lightest tone that is near white is the paper, where the block ends.
        let start = tones.count > 1 && lp > 0.7 ? spans[1].0 : 0
        self.start = start
        var random = PaintRandom(seed + 113)
        func between(_ a: Double, _ b: Double) -> Double { a + (b - a) * random.next() }
        let light = tones.indices.filter { spans[$0].1 > start && cover(tones[$0].rgb) < Self.lighter }
        let lx0 = start, lx1 = light.last.map { spans[$0].1 } ?? min(width, start + 40)
        let first = (x: lx0 + (lx1 - lx0) * 0.4, y: H * 0.5, rx: max(6, (lx1 - lx0) * 0.3), ry: H * 0.36)
        let second = (x: lx1 + (width - lx1) * 0.55, y: H * 0.48, rx: 10.0, ry: H * 0.3)
        let clearings = [first, second].filter { $0.x - $0.rx > start - 2 && $0.x + $0.rx < width + 2 }
        self.clearings = clearings
        var cuts = [GougeCut]()
        for clearing in clearings {
            let n = max(4, Int(clearing.rx * 2 / 3.4)), lean = between(-0.5, 0.5)
            for k in 0..<n {
                let x = clearing.x - clearing.rx + (Double(k) + 0.5) * 2 * clearing.rx / Double(n) + between(-0.6, 0.6)
                let off = (x - clearing.x) / clearing.rx
                let reach = clearing.ry * (1 - 0.55 * off * off) * between(0.85, 1.25)
                let wide = 2 * clearing.rx / Double(n) * Self.ridge * between(0.9, 1.15)
                cuts.append(GougeCut(x: x, top: clearing.y - reach * 1.6, bottom: clearing.y + reach * 1.6, wide: wide,
                                     lean: lean * 6 + between(-1, 1)))
            }
        }
        // Between them the gouge's lines, as many and as wide as leave each tone's black.
        for (k, tone) in tones.enumerated() where spans[k].1 > start {
            let dark = min(1, max(0.2, cover(tone.rgb)))
            if dark > 0.96 { continue }
            var x = max(spans[k].0, start) + between(0, Self.pitch)
            while x < spans[k].1 {
                let wide = Self.pitch * (1 - dark) * between(0.75, 1.25) * 1.2
                var top = between(-1, 4), bottom = H - between(-1, 4)
                if random.next() < 0.35 {
                    if random.next() < 0.5 { bottom = top + between(8, 16) } else { top = bottom - between(8, 16) }
                }
                cuts.append(GougeCut(x: x, top: top, bottom: bottom, wide: wide, lean: between(-2.5, 2.5)))
                x += Self.pitch * between(0.85, 1.15)
            }
        }
        self.cuts = cuts
        last = Self.time(shares.count)
        length = last
    }

    /// The block's ink at each pixel of the bar's rows, 0…1.
    private func prepare() -> (sheet: PrintPaint.Sheet, much: [Float]) {
        if let made { return made }
        let sheet = PrintPaint.sheet(paper: paper, width: width, seed: seed, plate: false)
        let S = Double(PrintPaint.scale), pad = Paint.pad, H = Paint.bar, rows = Brush.rows(high: high), pixel = 1 / S
        var cut = [Float](repeating: 0, count: rows.count * wide)
        for gouge in cuts {
            let left = max(0, Int((gouge.reach.lowerBound + pad) * S)), right = min(wide - 1, Int((gouge.reach.upperBound + pad) * S) + 1)
            guard left <= right else { continue }
            for j in rows {
                let y = (Double(j) + 0.5) / S - pad
                if y <= gouge.top || y >= gouge.bottom { continue }
                for i in left...right {
                    let away = Float(gouge.cut((Double(i) + 0.5) / S - pad, y, pixel: pixel))
                    let q = (j - rows.lowerBound) * wide + i
                    if away > cut[q] { cut[q] = away }
                }
            }
        }
        var much = [Float](repeating: 0, count: rows.count * wide)
        for j in rows {
            let y = (Double(j) + 0.5) / S - pad
            for i in 0..<wide {
                let x = (Double(i) + 0.5) / S - pad
                if x < start - 3 || x > width + 2 { continue }
                // The block's edge, a little uneven; the wood's grain and pores in the ink.
                let side = min(x - start + 1.6 * (Paint.noise(x / 2, y / 2, 71 + seed) - 0.5), width - x)
                let edge = min(side, min(y, H - y)) * 2.2 + 0.5 + (Paint.noise(x / 0.8, y / 0.8, 72 + seed) - 0.5)
                let block = min(1, max(0, edge))
                if block <= 0 { continue }
                let pore = Paint.noise(x / 0.45, y / 0.45, 73 + seed) > 0.8 ? 0.14 : 0
                let grain = 0.08 * abs(sin(x * 0.15 + y * 2.2 + 5 * Paint.noise(x / 12, y / 12, 74 + seed)))
                let q = (j - rows.lowerBound) * wide + i
                much[q] = Float(block * (1 - pore - grain)) * (1 - cut[q])
            }
        }
        made = (sheet, much)
        return (sheet, much)
    }

    func frame(age: Double) -> PaintFrame {
        if age >= length, let whole { return whole }
        var out = PaintFrame(wide: wide, high: high)
        guard age > 0, count > 0 else { return out }
        let (sheet, much) = prepare()
        let S = Double(PrintPaint.scale), pad = Paint.pad, rows = Brush.rows(high: high)
        let pulled = (age - PrintPaint.appear) / (length - PrintPaint.appear)
        let front = start - 6 + (width - start + 12) * Paint.ease(pulled)
        let shown = Float(Paint.ease(age / PrintPaint.appear))
        for j in 0..<high {
            let printed = rows.contains(j) && pulled > 0
            for i in 0..<wide {
                let k = j * wide + i
                let cover = sheet.cover[k]
                if cover <= 0 { continue }
                var red = sheet.red[k], green = sheet.green[k], blue = sheet.blue[k]
                if printed {
                    let x = (Double(i) + 0.5) / S - pad
                    let inked = much[(j - rows.lowerBound) * wide + i] * Float(min(1, max(0, (front - x) / 6)))
                    if inked > 0 {
                        red += (ink[0] - red) * inked
                        green += (ink[1] - green) * inked
                        blue += (ink[2] - blue) * inked
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
