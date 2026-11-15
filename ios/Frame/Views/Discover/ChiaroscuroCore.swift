import Foundation

// The colour bar of a chiaroscuro woodcut (Mateusz 2026-11-15 21:50, of a
// print after Veronese, „drzeworyt, czterema płytami (chiaroscuro)”, in
// browns from the darkest to the paper's white, shown as a black woodcut's
// block cut in white lines). Such a print is pulled from several blocks
// of one colour's tones, the lightest first, each over the ones before;
// its lights are the paper, cut out of the tone blocks, and its drawing
// the key block's, the darkest.

/// A chiaroscuro woodcut: the paper bare at the bar's light end (its
/// lights; as much as the work shows, or `lights` of the bar when its
/// colours hold no paper), each tone a block of flat ink with the wood's
/// grain printed from its place to the bar's end over the lighter ones,
/// so each place has its tone; a few cuts in each block's beginning
/// where the one under it shows, and the key block, the darkest, cut in
/// the gouge's lines.
final class ChiaroscuroStrip: PaintPainter, @unchecked Sendable {
    let wide: Int
    let high: Int
    let length: Double
    let last: Double

    private let width: Double
    private let seed: Double
    private let paper: [Double]
    /// Each block: where it begins, its ink (a glaze over what is under
    /// it), how far out of register it is, its gouge cuts.
    private let blocks: [(from: Double, ink: [Float], shift: (x: Double, y: Double), cuts: [GougeCut])]
    /// The key block's lines and its ink.
    private let lines: [GougeCut]
    private let keyInk: [Float]
    private var made: (sheet: PrintPaint.Sheet, much: [[Float]], key: [Float])?
    private var whole: PaintFrame?

    /// How long after one block the next is printed, and how long one takes.
    static let apart = 0.34, takes = 0.26
    /// The paper's share of the bar when the work's colours hold none
    /// lighter than its lightest tone block.
    static let lights = 0.1
    /// How much of the tone blocks' places the key block's lines cover.
    static let sparse = 0.09
    /// How far out of register a block may be (points).
    static let register = (x: 0.5, y: 0.35)

    /// The paper and the tones, lightest first: the lightest colour is the
    /// paper when it is near white; otherwise a paper is added at `lights`.
    static func tones(_ shares: [PaintShare]) -> (paper: PaintShare, blocks: [PaintShare]) {
        let sorted = shares.sorted { PrintPaint.lightness($0.rgb) > PrintPaint.lightness($1.rgb) }
        guard let lightest = sorted.first else { return (PaintShare(rgb: InkStrip.paper, weight: 1), []) }
        if sorted.count > 1, Brush.luminance(lightest.rgb) > 0.7 {
            return (PaintShare(rgb: PrintPaint.mixed(lightest.rgb, InkStrip.paper, 0.3), weight: lightest.weight), Array(sorted.dropFirst()))
        }
        let total = shares.reduce(0) { $0 + $1.weight }
        return (PaintShare(rgb: InkStrip.paper, weight: total * lights / (1 - lights)), sorted)
    }

    static func time(_ shares: [PaintShare]) -> Double {
        let count = tones(shares).blocks.count
        return count > 0 ? PrintPaint.appear + Double(count - 1) * apart + takes : 0
    }

    init(shares: [PaintShare], width: Double, seed: Int) {
        self.width = width
        self.seed = Double(seed)
        (wide, high) = PrintPaint.size(width: width)
        let (paper, tones) = Self.tones(shares)
        self.paper = paper.rgb
        let spans = Paint.spans([paper] + tones, width: width), H = Paint.bar
        var random = PaintRandom(seed + 131)
        func between(_ a: Double, _ b: Double) -> Double { a + (b - a) * random.next() }
        var under = paper.rgb, blocks = [(from: Double, ink: [Float], shift: (x: Double, y: Double), cuts: [GougeCut])]()
        // The darkest tone is the key block's: its lines, not a block of its own.
        let keyed = tones.count > 1
        for (k, tone) in tones.enumerated() where !(keyed && k == tones.count - 1) {
            let from = spans[k + 1].0, to = spans[k + 1].1
            // A few lights cut out of the block's beginning: the block under it shows there.
            var cuts = [GougeCut]()
            let n = 2 + Int(random.next() * 2)
            for c in 0..<n {
                let x = from + 3 + (min(to, from + 26) - from - 6) * (Double(c) + between(0.2, 0.8)) / Double(n)
                let top = between(1, 9), bottom = top + between(9, 16)
                cuts.append(GougeCut(x: x, top: top, bottom: bottom, wide: between(1.6, 3.2), lean: between(-4, 4)))
            }
            let ink = Brush.glaze(tone.rgb, over: under).map { Float($0) }
            blocks.append((from, ink, (Self.register.x * (random.next() * 2 - 1), Self.register.y * (random.next() * 2 - 1)), cuts))
            under = tone.rgb
        }
        // The key block's lines: sparse over the tone blocks, as dense over
        // the darkest tone's place as make it as dark.
        var lines = [GougeCut]()
        if keyed, let darkest = tones.last {
            let key = darkest.rgb.map { $0 * 0.5 }
            let lu = Brush.luminance(under), lk = Brush.luminance(key)
            let dense = min(0.85, max(0.25, (lu - Brush.luminance(darkest.rgb)) / max(lu - lk, 0.05)))
            let keyFrom = spans[tones.count].0
            var x = spans[1].0 + between(0, 4)
            while x < width {
                let cover = x < keyFrom ? Self.sparse : dense
                let wide = between(0.7, 1.3)
                var top = between(-1, 4), bottom = H - between(-1, 4)
                if random.next() < 0.45 {
                    if random.next() < 0.5 { bottom = top + between(6, 14) } else { top = bottom - between(6, 14) }
                }
                lines.append(GougeCut(x: x, top: top, bottom: bottom, wide: wide * 1.6, lean: between(-3, 3)))
                x += wide / cover * between(0.8, 1.2)
            }
            keyInk = key.map { Float($0) }
        } else {
            keyInk = [0, 0, 0]
        }
        self.lines = lines
        self.blocks = blocks
        last = Self.time(shares)
        length = last
    }

    private func prepare() -> (sheet: PrintPaint.Sheet, much: [[Float]], key: [Float]) {
        if let made { return made }
        let sheet = PrintPaint.sheet(paper: paper, width: width, seed: seed, plate: false)
        let S = Double(PrintPaint.scale), pad = Paint.pad, H = Paint.bar, rows = Brush.rows(high: high), pixel = 1 / S
        let much = blocks.enumerated().map { index, block -> [Float] in
            let s = seed + 13 * Double(index)
            var much = [Float](repeating: 0, count: rows.count * wide)
            for j in rows {
                let y = (Double(j) + 0.5) / S - pad - block.shift.y
                for i in 0..<wide {
                    let x = (Double(i) + 0.5) / S - pad - block.shift.x
                    if x < block.from - 3 || x > width + 3 { continue }
                    // The block's edge, a little uneven; not laid evenly: the baren's passes, the wood's grain, its pores.
                    let ragged = 1.3 * (Paint.noise(x / 3.5, y / 3.5, 81 + s) - 0.5) + 0.7 * (Paint.noise(x / 0.9, y / 0.9, 82 + s) - 0.5)
                    let inside = min(min(x - block.from, width + 1.3 - x), min(y, H - y)) + ragged
                    if inside < -1 { continue }
                    let even = 0.88 + 0.12 * Paint.noise(x / 9, y / 9, 83 + s)
                    let pore = Paint.noise(x / 0.7, y / 0.7, 84 + s) > 0.8 ? 0.88 : 1
                    let grain = 1 - 0.07 * abs(sin(y * 2.3 + 6 * Paint.noise(x / 30, y / 30, 86 + s)))
                    var cut = 0.0
                    for gouge in block.cuts where gouge.reach.contains(x) {
                        cut = max(cut, gouge.cut(x, y, pixel: pixel))
                    }
                    let edge: Double = min(1, max(0, inside * 2.2 + 0.5))
                    let ink: Double = edge * even * pore * grain
                    much[(j - rows.lowerBound) * wide + i] = Float(ink * (1 - cut))
                }
            }
            return much
        }
        // The key block's lines, a little out of register too.
        var key = [Float](repeating: 0, count: rows.count * wide)
        for line in lines {
            let left = max(0, Int((line.reach.lowerBound + pad) * S)), right = min(wide - 1, Int((line.reach.upperBound + pad) * S) + 1)
            guard left <= right else { continue }
            for j in rows {
                let y = (Double(j) + 0.5) / S - pad - 0.2
                if y <= line.top || y >= line.bottom { continue }
                for i in left...right {
                    let x = (Double(i) + 0.5) / S - pad
                    let ink = Float(line.cut(x, y, pixel: pixel) * (0.85 + 0.15 * Paint.noise(x / 0.8, y / 0.8, 97 + seed)))
                    let q = (j - rows.lowerBound) * wide + i
                    if ink > key[q] { key[q] = ink }
                }
            }
        }
        made = (sheet, much, key)
        return (sheet, much, key)
    }

    func frame(age: Double) -> PaintFrame {
        if age >= length, let whole { return whole }
        var out = PaintFrame(wide: wide, high: high)
        guard age > 0 else { return out }
        var (sheet, much, key) = prepare()
        let rows = Brush.rows(high: high)
        for (turn, block) in blocks.enumerated() {
            let there = Float(Paint.ease((age - PrintPaint.appear - Double(turn) * Self.apart) / Self.takes))
            if there <= 0 { continue }
            for j in rows {
                for i in 0..<wide {
                    let k = j * wide + i, laid = much[turn][(j - rows.lowerBound) * wide + i] * there
                    if laid <= 0 || sheet.cover[k] <= 0 { continue }
                    sheet.red[k] *= 1 - laid + laid * block.ink[0]
                    sheet.green[k] *= 1 - laid + laid * block.ink[1]
                    sheet.blue[k] *= 1 - laid + laid * block.ink[2]
                }
            }
        }
        let keyed = Float(Paint.ease((age - PrintPaint.appear - Double(blocks.count) * Self.apart) / Self.takes))
        if !lines.isEmpty, keyed > 0 {
            for j in rows {
                for i in 0..<wide {
                    let k = j * wide + i, laid = key[(j - rows.lowerBound) * wide + i] * keyed
                    if laid <= 0 || sheet.cover[k] <= 0 { continue }
                    sheet.red[k] += (keyInk[0] - sheet.red[k]) * laid
                    sheet.green[k] += (keyInk[1] - sheet.green[k]) * laid
                    sheet.blue[k] += (keyInk[2] - sheet.blue[k]) * laid
                }
            }
        }
        let shown = Float(Paint.ease(age / PrintPaint.appear))
        for k in 0..<(wide * high) {
            sheet.put(sheet.red[k], sheet.green[k], sheet.blue[k], at: k, shown: shown, into: &out)
        }
        if age >= length { whole = out }
        return out
    }
}
