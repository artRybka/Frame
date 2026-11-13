import CoreGraphics
import SwiftUI

// "Kolor i światło" painted in the work's own technique (Mateusz
// 2026-11-11 11:09): the palette bar and each paint's swatch, in oil, in
// watercolour or in pastel (`PaintCore.swift` is the paint; this file
// puts it on the page and gives it its time). What is drawn or printed
// has its own (2026-11-12 07:26, `PrintCore.swift`): a scale of tones in
// lines, or a colour print's inks; a photograph a gradient under grain.
// A work whose technique says nothing keeps the flat bar and the plain
// round swatches; a sculpture has no bar (10:47).

extension Paint {
    /// CI screenshots: "-paintRelief 0.3" gives every work's oil paint that height.
    static let forcedRelief: Double? = UserDefaults.standard.object(forKey: "paintRelief") == nil
        ? nil : UserDefaults.standard.double(forKey: "paintRelief")

    /// How high this work's oil paint stands (`Paint.relief(year:styles:medium:)`).
    static func relief(_ item: Item) -> Double {
        forcedRelief ?? relief(year: item.year, styles: item.styles, medium: item.medium)
    }
}

extension ContourLine {
    /// The work's drawn contour as the server found it (`Item.contour`).
    init?(_ item: Item) {
        guard let found = item.contour else { return nil }
        self.init(hex: found.hex, length: found.length, width: found.width)
    }
}

extension PaintStyle {
    /// CI screenshots: "-paintStyle oil" paints every work that way.
    static let forced: PaintStyle? = UserDefaults.standard.string(forKey: "paintStyle").flatMap(PaintStyle.init(rawValue:))

    /// How this work's colours are painted, drawn or printed; nil: flat.
    static func of(_ item: Item) -> PaintStyle? {
        if let forced { return forced }
        // The household's own photographs.
        if item.kind == .photo { return .photo }
        let colours = item.colors.compactMap { Paint.rgb($0.hex) }
        // One colour's tones for the most part: a patch of colour or two
        // beside them is printed on the scale of tones, not a reason for
        // a bar of inks (Mateusz 2026-11-12 11:35: „jeżeli pojawią się
        // plama barwna, to nasza skala koloru musi ją uwzględniać”).
        let shares = item.colors.compactMap { swatch in
            Paint.rgb(swatch.hex).map { PaintShare(rgb: $0, weight: max(swatch.weight, 0), accent: swatch.accent ?? false) }
        }
        return of(medium: item.medium, classification: item.classification,
                  mono: item.colorTags.contains("monochrome") || (!shares.isEmpty && PrintPaint.mostlyOne(shares)), warm: warm(colours))
    }

    /// A sculpture: no bar of colours.
    static func sculpted(_ item: Item) -> Bool {
        forced == nil && item.kind != .photo && sculpted(medium: item.medium, classification: item.classification)
    }

    /// Whether the darkest of a work's colours is a brown: of a drawing
    /// that names no tool, that it is in a pen's brown ink.
    static func warm(_ colours: [[Double]]) -> Bool {
        guard let darkest = colours.min(by: { PrintPaint.lightness($0) < PrintPaint.lightness($1) }) else { return false }
        return darkest[0] - darkest[2] > 20
    }
}

extension PaintFrame {
    /// The picture for the screen.
    var image: CGImage? {
        guard wide > 0, high > 0, let provider = CGDataProvider(data: Data(bytes) as CFData) else { return nil }
        return CGImage(width: wide, height: high, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: wide * 4,
                       space: PaintJob.space, bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.last.rawValue),
                       provider: provider, decode: nil, shouldInterpolate: true, intent: .defaultIntent)
    }
}

/// Something to paint on the page: how big it is, how long it takes and
/// its picture at any moment. The picture is asked off the main thread,
/// one at a time.
struct PaintJob: @unchecked Sendable {
    /// Its size in points.
    let size: CGSize
    let length: Double
    let image: (Double) -> CGImage?

    static let space = CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB()

    /// `scale`: the painter's pixels to a point.
    private init(_ painter: PaintPainter, scale: Int = Paint.scale) {
        size = CGSize(width: CGFloat(painter.wide) / CGFloat(scale), height: CGFloat(painter.high) / CGFloat(scale))
        length = painter.length
        image = { painter.frame(age: $0).image }
    }

    private init(size: CGSize, length: Double, image: @escaping (Double) -> CGImage?) {
        self.size = size
        self.length = length
        self.image = image
    }

    /// The palette bar, `width` points wide.
    /// `relief`: how high an oil paint stands (`Paint.relief`).
    /// `contour`: the work's drawn contour, round a painted bar's paint.
    static func strip(_ style: PaintStyle, shares: [PaintShare], width: Double, seed: Int, dark: Bool,
                      relief: Double = Paint.calm.plain, contour: ContourLine? = nil) -> PaintJob {
        let line = contour.flatMap { ContourLine.draws(in: style) ? $0 : nil }
        func painted(_ painter: PaintPainter) -> PaintJob {
            guard let line else { return PaintJob(painter) }
            return PaintJob(ContouredStrip(painter, line: line, style: style, seed: seed, dark: dark))
        }
        switch style {
        case .oil: return painted(OilStrip(shares: shares, width: width, seed: seed, dark: dark, relief: relief))
        case .water: return painted(WaterStrip(shares: shares, width: width, seed: seed))
        case .dry:
            let strip = DryStrip(shares: shares, width: width, seed: seed)
            guard let line else { return PaintJob(size: strip.size, length: strip.plan.length) { strip.image(age: $0) } }
            let drawn = DryContour(strip: strip, line: line, seed: seed, dark: dark)
            return PaintJob(size: strip.size, length: drawn.length) { drawn.image(age: $0) }
        case .burin, .pen, .pencil:
            return PaintJob(LineStrip(shares: shares, width: width, seed: seed, tool: style.tool ?? .burin), scale: PrintPaint.scale)
        case .woodblock, .litho:
            return PaintJob(InkStrip(shares: shares, width: width, seed: seed, press: style.press ?? .wood), scale: PrintPaint.scale)
        case .photo:
            return PaintJob(PhotoStrip(shares: shares, width: width, seed: seed), scale: PrintPaint.scale)
        }
    }

    /// One paint's swatch.
    static func swatch(_ style: PaintStyle, rgb: [Double], index: Int, seed: Int, dark: Bool,
                       relief: Double = Paint.calm.plain) -> PaintJob {
        switch style {
        case .oil: return PaintJob(OilStrip(touch: rgb, index: index, seed: seed, dark: dark, relief: relief))
        case .water: return PaintJob(WaterDab(rgb: rgb, index: index, seed: seed))
        case .dry:
            let scribble = DryScribble(rgb: rgb, index: index, seed: seed)
            return PaintJob(size: scribble.size, length: DryScribble.length) { scribble.image(age: $0) }
        case .burin, .pen, .pencil:
            return PaintJob(LinePatch(rgb: rgb, index: index, seed: seed, tool: style.tool ?? .burin), scale: PrintPaint.scale)
        case .woodblock, .litho:
            return PaintJob(InkStamp(rgb: rgb, index: index, seed: seed, press: style.press ?? .wood), scale: PrintPaint.scale)
        case .photo:
            return PaintJob(PhotoChip(rgb: rgb, index: index, seed: seed), scale: PrintPaint.scale)
        }
    }
}

/// What the stick's strokes are drawn on and rubbed into the paper's
/// tooth with.
private enum DryCanvas {
    /// A picture `wide` by `high` pixels to draw on in points, from
    /// `origin` points in from its upper left corner, down the page.
    static func context(wide: Int, high: Int, origin: Double) -> CGContext? {
        guard let context = CGContext(data: nil, width: wide, height: high, bitsPerComponent: 8, bytesPerRow: 0,
                                      space: PaintJob.space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
        context.saveGState()
        context.translateBy(x: 0, y: CGFloat(high))
        context.scaleBy(x: CGFloat(Paint.scale), y: -CGFloat(Paint.scale))
        context.translateBy(x: origin, y: origin)
        context.setLineCap(.round)
        context.setLineJoin(.round)
        return context
    }

    /// The paper's tooth as a picture that is only there or not.
    /// `open`: how much of the tooth is left open (under a stick
    /// pressed hard, less).
    static func tooth(wide: Int, high: Int, seed: Int, open: Double = 1) -> CGImage? {
        let grain = DryPlan.tooth(wide: wide, high: high, seed: seed)
        var bytes = [UInt8](repeating: 0, count: wide * high * 4)
        for k in grain.indices { bytes[4 * k + 3] = Paint.byte(255 - open * (255 - Double(grain[k]))) }
        guard let provider = CGDataProvider(data: Data(bytes) as CFData) else { return nil }
        return CGImage(width: wide, height: high, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: wide * 4,
                       space: PaintJob.space, bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue),
                       provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent)
    }

    /// What is drawn stays only where the paper's tooth took it.
    static func rubbed(_ context: CGContext, tooth: CGImage?, wide: Int, high: Int) -> CGImage? {
        context.restoreGState()
        if let tooth {
            context.setAlpha(1)
            context.setBlendMode(.destinationIn)
            context.draw(tooth, in: CGRect(x: 0, y: 0, width: wide, height: high))
        }
        return context.makeImage()
    }

    static func colour(_ rgb: [Double]) -> CGColor {
        CGColor(colorSpace: PaintJob.space, components: [CGFloat(rgb[0] / 255), CGFloat(rgb[1] / 255), CGFloat(rgb[2] / 255), 1])
            ?? CGColor(gray: 0.5, alpha: 1)
    }
}

extension PaintFrame {
    /// A picture's pixels, not multiplied by how much is there.
    init?(_ image: CGImage) {
        let wide = image.width, high = image.height
        guard let context = CGContext(data: nil, width: wide, height: high, bitsPerComponent: 8, bytesPerRow: wide * 4,
                                      space: PaintJob.space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue),
              let data = context.data else { return nil }
        context.draw(image, in: CGRect(x: 0, y: 0, width: wide, height: high))
        self.init(wide: wide, high: high)
        let raw = data.bindMemory(to: UInt8.self, capacity: wide * high * 4)
        for q in 0..<(wide * high) {
            let a = Double(raw[4 * q + 3])
            bytes[4 * q + 3] = raw[4 * q + 3]
            guard a > 0 else { continue }
            for k in 0..<3 { bytes[4 * q + k] = Paint.byte(Double(raw[4 * q + k]) * 255 / a) }
        }
    }
}

/// A pastel bar and its contour drawn round it in the same stick, once
/// its hatching is done (`ContourStroke`).
final class DryContour: @unchecked Sendable {
    let strip: DryStrip
    let line: ContourLine
    let seed: Int
    let dark: Bool
    let length: Double
    private var stroke: ContourStroke??

    init(strip: DryStrip, line: ContourLine, seed: Int, dark: Bool) {
        self.strip = strip
        self.line = line
        self.seed = seed
        self.dark = dark
        length = strip.plan.length + ContourLine.draws
    }

    func image(age: Double) -> CGImage? {
        let begins = strip.plan.length
        guard age > begins, let bar = strip.image(age: begins), var frame = PaintFrame(bar) else { return strip.image(age: age) }
        if stroke == nil {
            // Hatching leaves the paper's hollows bare: where the paint is
            // is told from a little round each pixel.
            let wide = frame.wide, high = frame.high, r = 3
            var near = [Double](repeating: 0, count: wide * high)
            for y in 0..<high {
                for x in 0..<wide {
                    var sum = 0.0, n = 0.0
                    for dy in stride(from: -r, through: r, by: 2) {
                        for dx in stride(from: -r, through: r, by: 2) {
                            sum += frame.cover(x + dx, y + dy)
                            n += 1
                        }
                    }
                    near[y * wide + x] = sum / n
                }
            }
            stroke = .some(ContourStroke(bar: { near[$1 * wide + $0] * 1.4 }, wide: wide, high: high, line: line, style: .dry,
                                         seed: seed, inside: dark))
        }
        if case let .some(.some(stroke)) = stroke {
            stroke.draw(on: &frame, progress: min(1, (age - begins) / ContourLine.draws), seed: seed)
        }
        return frame.image
    }
}

/// The palette bar hatched with a stick of pastel (`DryPlan`).
final class DryStrip: @unchecked Sendable {
    let plan: DryPlan
    let wide: Int
    let high: Int

    private let colours: [CGColor]
    private let seed: Int
    private var tooth: CGImage?
    /// The tooth under the strokes pressed hard.
    private var filled: CGImage?

    var size: CGSize { CGSize(width: CGFloat(wide) / CGFloat(Paint.scale), height: CGFloat(high) / CGFloat(Paint.scale)) }

    init(shares: [PaintShare], width: Double, seed: Int) {
        plan = DryPlan(shares: shares, width: width, seed: seed)
        wide = Int((width + 2 * Paint.pad).rounded()) * Paint.scale
        high = Int(Paint.bar + 2 * Paint.pad) * Paint.scale
        colours = shares.map { DryCanvas.colour($0.rgb) }
        self.seed = seed
    }

    /// The hatching, and over it the accents: pressed hard, they fill
    /// the paper's tooth, so they are drawn apart and rubbed less.
    func image(age: Double) -> CGImage? {
        if tooth == nil { tooth = DryCanvas.tooth(wide: wide, high: high, seed: seed) }
        let soft = drawn(age: age, press: false, tooth: tooth)
        guard plan.strokes.contains(where: { $0.press && plan.made($0, age: age) > 0 }) else { return soft }
        if filled == nil { filled = DryCanvas.tooth(wide: wide, high: high, seed: seed, open: DryPlan.pressed) }
        guard let soft, let hard = drawn(age: age, press: true, tooth: filled),
              let both = CGContext(data: nil, width: wide, height: high, bitsPerComponent: 8, bytesPerRow: 0,
                                   space: PaintJob.space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return soft }
        let all = CGRect(x: 0, y: 0, width: wide, height: high)
        both.draw(soft, in: all)
        both.draw(hard, in: all)
        return both.makeImage()
    }

    /// The strokes pressed hard, or the others, as far as they are made at `age`.
    private func drawn(age: Double, press: Bool, tooth: CGImage?) -> CGImage? {
        guard let context = DryCanvas.context(wide: wide, high: high, origin: Paint.pad) else { return nil }
        for stroke in plan.strokes where stroke.press == press {
            let made = plan.made(stroke, age: age)
            if made <= 0 { continue }
            context.setAlpha(stroke.alpha)
            context.setStrokeColor(colours[stroke.colour])
            context.setLineWidth(stroke.wide)
            context.move(to: CGPoint(x: stroke.from.x, y: stroke.from.y))
            if made >= 1 {
                context.addQuadCurve(to: CGPoint(x: stroke.to.x, y: stroke.to.y),
                                     control: CGPoint(x: (stroke.from.x + stroke.to.x) / 2 + stroke.bow, y: (stroke.from.y + stroke.to.y) / 2))
            } else {
                context.addLine(to: CGPoint(x: stroke.from.x + (stroke.to.x - stroke.from.x) * made,
                                            y: stroke.from.y + (stroke.to.y - stroke.from.y) * made))
            }
            context.strokePath()
        }
        return DryCanvas.rubbed(context, tooth: tooth, wide: wide, high: high)
    }
}

/// One paint as a short scribble of the stick.
final class DryScribble: @unchecked Sendable {
    static let length = 1.2

    let wide = Int(2 * Paint.half) * Paint.scale
    let high = Int(2 * Paint.half) * Paint.scale

    private let colour: CGColor
    private let points: [(x: Double, y: Double)]
    private let seed: Int
    private var tooth: CGImage?

    var size: CGSize { CGSize(width: 2 * Paint.half, height: 2 * Paint.half) }

    init(rgb: [Double], index: Int, seed: Int) {
        colour = DryCanvas.colour(rgb)
        points = DryPlan.scribble(index: index, seed: seed)
        self.seed = seed + 7 + index
    }

    func image(age: Double) -> CGImage? {
        guard let context = DryCanvas.context(wide: wide, high: high, origin: Paint.half) else { return nil }
        if tooth == nil { tooth = DryCanvas.tooth(wide: wide, high: high, seed: seed) }
        let age = min(Self.length, age), turns = points.count - 1
        if age > 0, turns > 0 {
            let done = min(1, age / 0.45) * Double(turns)
            context.setAlpha(0.85)
            context.setStrokeColor(colour)
            context.setLineWidth(3.4)
            context.move(to: CGPoint(x: points[0].x, y: points[0].y))
            for q in 1...turns {
                let k = min(1, done - Double(q - 1))
                if k <= 0 { break }
                context.addLine(to: CGPoint(x: points[q - 1].x + (points[q].x - points[q - 1].x) * k,
                                            y: points[q - 1].y + (points[q].y - points[q - 1].y) * k))
            }
            context.strokePath()
        }
        return DryCanvas.rubbed(context, tooth: tooth, wide: wide, high: high)
    }
}

/// Keeps what is being painted while the page is drawn again and again:
/// a painter is made once for what it paints.
final class PaintJobs {
    private var kept: (key: String, job: PaintJob)?

    func job(_ key: String, make: () -> PaintJob) -> PaintJob {
        if let kept, kept.key == key { return kept.job }
        let job = make()
        kept = (key, job)
        return job
    }
}

/// A painting on the page, painted while it is looked at: it begins when
/// it is on the screen and `after` has come, and goes on to its end. With
/// "Ogranicz ruch" it is there at once, finished; so it is when asked
/// `whole` (the work's card: Mateusz 2026-11-12 10:47: „bez ruchu, od razu
/// gotowy”).
struct Painted: View {
    let job: PaintJob
    /// What it paints: a new one is painted at the age the old one had.
    let key: String
    /// Not before this; nil: not yet.
    let after: Date?
    /// Told once, when it begins.
    var began: (Date) -> Void = { _ in }
    /// How long after the first of its section it is due (a held
    /// screenshot shows the whole section at one moment).
    var lead: Double = 0
    /// How far over the bottom of what the bars leave of the screen its
    /// foot is when it begins; under 0: that far under it still.
    var over: CGFloat = Painted.clear
    /// Not painted while looked at: there finished.
    var whole = false

    @State private var image: CGImage?
    @State private var shown: String?
    @State private var start: Date?
    @State private var seen = false
    @State private var settled = false
    @State private var busy = false
    @Environment(\.accessibilityReduceMotion) private var still

    /// CI screenshots: "-paintAge 1.3" holds every painting as it is that
    /// long after it began.
    static let held: Double? = UserDefaults.standard.object(forKey: "paintAge") == nil
        ? nil : UserDefaults.standard.double(forKey: "paintAge")
    /// It begins with its foot this far over the bottom of what the bars
    /// leave of the screen: under that the tab bar is in the way.
    static let clear: CGFloat = 24

    private var finished: Bool { settled && shown == key }

    var body: some View {
        Color.clear
            .frame(width: job.size.width, height: job.size.height)
            .overlay {
                if let image {
                    Image(decorative: image, scale: CGFloat(Paint.scale))
                        .resizable()
                        .interpolation(.high)
                }
            }
            .onGeometryChange(for: Bool.self) { proxy in
                guard let bounds = proxy.bounds(of: .scrollView) else { return true }
                let foot = proxy.size.height - Paint.pad
                return bounds.maxY >= foot + over && bounds.minY <= foot
            } action: { seen = $0 }
            .background {
                TimelineView(.animation(minimumInterval: 1.0 / 30, paused: whole || finished || (start == nil && !(seen && after != nil)))) { context in
                    Color.clear.onChange(of: context.date) { _, now in tick(now) }
                }
            }
            .task(id: whole ? key : "") {
                guard whole else { return }
                let job = self.job, key = self.key
                let made = await Task.detached(priority: .userInitiated) { job.image(job.length) }.value
                guard !Task.isCancelled else { return }
                image = made
                shown = key
                settled = true
            }
            .allowsHitTesting(false)
            .accessibilityHidden(true)
    }

    private func tick(_ now: Date) {
        guard !busy, !finished, !whole else { return }
        if start == nil {
            guard seen, let after, now >= after else { return }
            start = now
            began(now)
        }
        guard let start else { return }
        let age = Self.held.map { $0 - lead } ?? (still ? job.length : now.timeIntervalSince(start))
        let last = Self.held != nil || age >= job.length
        let job = self.job, key = self.key
        busy = true
        Task.detached(priority: .userInitiated) {
            let made = job.image(min(age, job.length))
            await MainActor.run {
                image = made
                shown = key
                settled = last
                busy = false
            }
        }
    }
}

/// The work's colours as a bar painted, drawn or printed in its
/// technique, each colour as wide as its share of the picture.
struct PaintedStrip: View {
    let swatches: [ColorSwatch]
    let style: PaintStyle
    let seed: Int
    /// Told when the first stroke begins, and how long the bar's paint
    /// takes from then.
    var began: (Date, Double) -> Void = { _, _ in }
    /// There finished, not painted while looked at.
    var whole = false
    /// How high an oil paint stands (`Paint.relief`).
    var relief = Paint.calm.plain
    /// Shown this much smaller than the bar of a work's card (the Teraz
    /// tab's narrow one): painted for a place that much wider, so the
    /// strokes are as much finer as the bar is lower.
    var slim: CGFloat = 1
    /// The work's drawn contour (`Item.contour`), round the paint.
    var contour: ContourLine?

    @State private var width: CGFloat = 0
    @State private var jobs = PaintJobs()
    @Environment(\.colorScheme) private var scheme

    /// More colours than this are no bar any more, only specks.
    static let most = 8

    /// CI screenshots: "-paintColours 918d78:0.28/4c4a3c:0.26" are the
    /// colours of every work's bar (an engraving's, for an engraving's
    /// bar); "9cabac:0.07:a" is an accent.
    static let forced: [PaintShare] = (UserDefaults.standard.string(forKey: "paintColours") ?? "").split(separator: "/").compactMap { part in
        let bits = part.split(separator: ":")
        guard bits.count >= 2, let rgb = Paint.rgb(String(bits[0])), let weight = Double(bits[1]), weight > 0 else { return nil }
        return PaintShare(rgb: rgb, weight: weight, accent: bits.count > 2)
    }

    /// CI screenshots: "-paintContour 2d1e1d:3.4:1.17" is every work's
    /// contour (colour, length, width as the server gives them).
    static let forcedContour: ContourLine? = UserDefaults.standard.string(forKey: "paintContour").flatMap { text in
        let bits = text.split(separator: ":")
        guard bits.count == 3, let length = Double(bits[1]), let width = Double(bits[2]) else { return nil }
        return ContourLine(hex: String(bits[0]), length: length, width: width)
    }

    /// The colours it paints: those it can read, the first `most`.
    static func shares(_ swatches: [ColorSwatch]) -> [PaintShare] {
        if !forced.isEmpty { return forced }
        return swatches.compactMap { swatch in
            guard let rgb = Paint.rgb(swatch.hex), swatch.weight > 0 else { return nil }
            return PaintShare(rgb: rgb, weight: swatch.weight, accent: swatch.accent ?? false)
        }
        .prefix(most).map { $0 }
    }

    var body: some View {
        let shares = Self.shares(swatches)
        Color.clear
            .frame(maxWidth: .infinity)
            .frame(height: Paint.bar * slim)
            .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { width = $0 }
            .overlay {
                if width > 40, !shares.isEmpty {
                    let dark = scheme == .dark, wide = Double((width / slim).rounded())
                    let line = Self.forcedContour ?? contour
                    let key = "\(style.rawValue)|\(Int(wide))|\(dark)|\(seed)|\(relief)|"
                        + shares.map { "\($0.rgb)\($0.weight)" }.joined(separator: ",")
                        + (line.map { "|\($0.rgb)\($0.length)\($0.width)" } ?? "")
                    let takes = style.barTime(shares, width: wide)
                    Painted(job: jobs.job(key) {
                        PaintJob.strip(style, shares: shares, width: wide, seed: seed, dark: dark, relief: relief, contour: line)
                    },
                            key: key, after: .distantPast, began: { began($0, takes) }, whole: whole)
                        .scaleEffect(slim)
                }
            }
    }
}

/// One paint's swatch painted in the work's technique, in the place of
/// the plain round one. The same for a paint the sources name and for a
/// likely one (Mateusz 2026-11-11 18:39: „zawsze duże (nawet gdy
/// niepewne)”).
struct PaintedSwatch: View {
    let hex: String
    let index: Int
    let style: PaintStyle
    let seed: Int
    /// When it may begin; nil: the bar has not begun yet.
    let after: Date?
    /// How long after the bar's first stroke that is.
    var lead: Double = 0
    /// How high an oil paint stands (`Paint.relief`).
    var relief = Paint.calm.plain

    /// It begins as its top comes over the bottom of what the bars leave
    /// of the screen, not once the whole of it is well over it: beside
    /// its paint's name it is there already (18:39: „muszą się pojawiać
    /// trochę wcześniej”).
    static let over = -CGFloat(Paint.swatch)

    @State private var jobs = PaintJobs()
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        Color.clear
            .frame(width: Paint.swatch, height: Paint.swatch)
            .overlay {
                if let rgb = Paint.rgb(hex) {
                    let dark = scheme == .dark
                    let key = "\(style.rawValue)|\(hex)|\(index)|\(dark)|\(seed)|\(relief)"
                    Painted(job: jobs.job(key) { PaintJob.swatch(style, rgb: rgb, index: index, seed: seed, dark: dark, relief: relief) },
                            key: key, after: after, lead: lead, over: Self.over)
                } else {
                    Circle().fill(Theme.mat)
                }
            }
    }
}
