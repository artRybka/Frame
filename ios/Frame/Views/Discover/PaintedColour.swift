import CoreGraphics
import SwiftUI

// "Kolor i światło" painted in the work's own technique (Mateusz
// 2026-11-11 11:09): the palette bar and each paint's swatch, in oil, in
// watercolour or in pastel (`PaintCore.swift` is the paint; this file
// puts it on the page and gives it its time). A work in any other
// technique keeps the flat bar and the plain round swatches.

extension PaintStyle {
    /// CI screenshots: "-paintStyle oil" paints every work that way.
    static let forced: PaintStyle? = UserDefaults.standard.string(forKey: "paintStyle").flatMap(PaintStyle.init(rawValue:))

    /// How this work's colours are painted; nil: flat.
    static func of(_ item: Item) -> PaintStyle? {
        forced ?? of(medium: item.medium, classification: item.classification)
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

    private init(_ painter: PaintPainter) {
        size = CGSize(width: CGFloat(painter.wide) / CGFloat(Paint.scale), height: CGFloat(painter.high) / CGFloat(Paint.scale))
        length = painter.length
        image = { painter.frame(age: $0).image }
    }

    private init(size: CGSize, length: Double, image: @escaping (Double) -> CGImage?) {
        self.size = size
        self.length = length
        self.image = image
    }

    /// The palette bar, `width` points wide.
    static func strip(_ style: PaintStyle, shares: [PaintShare], width: Double, seed: Int, dark: Bool) -> PaintJob {
        switch style {
        case .oil: return PaintJob(OilStrip(shares: shares, width: width, seed: seed, dark: dark))
        case .water: return PaintJob(WaterStrip(shares: shares, width: width, seed: seed))
        case .dry:
            let strip = DryStrip(shares: shares, width: width, seed: seed)
            return PaintJob(size: strip.size, length: strip.plan.length) { strip.image(age: $0) }
        }
    }

    /// One paint's swatch.
    static func swatch(_ style: PaintStyle, rgb: [Double], sure: Bool, index: Int, seed: Int, dark: Bool) -> PaintJob {
        switch style {
        case .oil: return PaintJob(OilStrip(touch: rgb, sure: sure, index: index, seed: seed, dark: dark))
        case .water: return PaintJob(WaterDab(rgb: rgb, sure: sure, index: index, seed: seed))
        case .dry:
            let scribble = DryScribble(rgb: rgb, sure: sure, index: index, seed: seed)
            return PaintJob(size: scribble.size, length: DryScribble.length) { scribble.image(age: $0) }
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
    static func tooth(wide: Int, high: Int, seed: Int) -> CGImage? {
        let grain = DryPlan.tooth(wide: wide, high: high, seed: seed)
        var bytes = [UInt8](repeating: 0, count: wide * high * 4)
        for k in grain.indices { bytes[4 * k + 3] = grain[k] }
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

/// The palette bar hatched with a stick of pastel (`DryPlan`).
final class DryStrip: @unchecked Sendable {
    let plan: DryPlan
    let wide: Int
    let high: Int

    private let colours: [CGColor]
    private let seed: Int
    private var tooth: CGImage?

    var size: CGSize { CGSize(width: CGFloat(wide) / CGFloat(Paint.scale), height: CGFloat(high) / CGFloat(Paint.scale)) }

    init(shares: [PaintShare], width: Double, seed: Int) {
        plan = DryPlan(shares: shares, width: width, seed: seed)
        wide = Int((width + 2 * Paint.pad).rounded()) * Paint.scale
        high = Int(Paint.bar + 2 * Paint.pad) * Paint.scale
        colours = shares.map { DryCanvas.colour($0.rgb) }
        self.seed = seed
    }

    func image(age: Double) -> CGImage? {
        guard let context = DryCanvas.context(wide: wide, high: high, origin: Paint.pad) else { return nil }
        if tooth == nil { tooth = DryCanvas.tooth(wide: wide, high: high, seed: seed) }
        for stroke in plan.strokes {
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

/// One paint as a short scribble of the stick. `sure` false: the same
/// close hatching on a narrower patch, a touch lighter in the hand.
final class DryScribble: @unchecked Sendable {
    static let length = 1.2

    let wide = Int(2 * Paint.half) * Paint.scale
    let high = Int(2 * Paint.half) * Paint.scale

    private let colour: CGColor
    private let sure: Bool
    private let points: [(x: Double, y: Double)]
    private let seed: Int
    private var tooth: CGImage?

    var size: CGSize { CGSize(width: 2 * Paint.half, height: 2 * Paint.half) }

    init(rgb: [Double], sure: Bool, index: Int, seed: Int) {
        colour = DryCanvas.colour(rgb)
        self.sure = sure
        points = DryPlan.scribble(sure: sure, index: index, seed: seed)
        self.seed = seed + 7 + index
    }

    func image(age: Double) -> CGImage? {
        guard let context = DryCanvas.context(wide: wide, high: high, origin: Paint.half) else { return nil }
        if tooth == nil { tooth = DryCanvas.tooth(wide: wide, high: high, seed: seed) }
        let age = min(Self.length, age), turns = points.count - 1
        if age > 0, turns > 0 {
            let done = min(1, age / 0.45) * Double(turns)
            context.setAlpha(sure ? 0.85 : 0.76)
            context.setStrokeColor(colour)
            context.setLineWidth(sure ? 3.4 : 3.1)
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
/// "Ogranicz ruch" it is there at once, finished.
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
                return bounds.maxY >= foot + Self.clear && bounds.minY <= foot
            } action: { seen = $0 }
            .background {
                TimelineView(.animation(minimumInterval: 1.0 / 30, paused: finished || (start == nil && !(seen && after != nil)))) { context in
                    Color.clear.onChange(of: context.date) { _, now in tick(now) }
                }
            }
            .allowsHitTesting(false)
            .accessibilityHidden(true)
    }

    private func tick(_ now: Date) {
        guard !busy, !finished else { return }
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

/// The work's colours as a bar painted in its technique, each colour as
/// wide as its share of the picture.
struct PaintedStrip: View {
    let swatches: [ColorSwatch]
    let style: PaintStyle
    let seed: Int
    /// Told when the first stroke begins.
    var began: (Date) -> Void = { _ in }

    @State private var width: CGFloat = 0
    @State private var jobs = PaintJobs()
    @Environment(\.colorScheme) private var scheme

    /// More colours than this are no bar any more, only specks.
    static let most = 8

    /// The colours it paints: those it can read, the first `most`.
    static func shares(_ swatches: [ColorSwatch]) -> [PaintShare] {
        swatches.compactMap { swatch in
            guard let rgb = Paint.rgb(swatch.hex), swatch.weight > 0 else { return nil }
            return PaintShare(rgb: rgb, weight: swatch.weight)
        }
        .prefix(most).map { $0 }
    }

    var body: some View {
        let shares = Self.shares(swatches)
        Color.clear
            .frame(maxWidth: .infinity)
            .frame(height: Paint.bar)
            .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { width = $0 }
            .overlay {
                if width > 40, !shares.isEmpty {
                    let dark = scheme == .dark, wide = Double(width.rounded())
                    let key = "\(style.rawValue)|\(Int(wide))|\(dark)|\(seed)|" + shares.map { "\($0.rgb)\($0.weight)" }.joined(separator: ",")
                    Painted(job: jobs.job(key) { PaintJob.strip(style, shares: shares, width: wide, seed: seed, dark: dark) },
                            key: key, after: .distantPast, began: began)
                }
            }
    }
}

/// One paint's swatch painted in the work's technique, in the place of
/// the plain round one.
struct PaintedSwatch: View {
    let hex: String
    let sure: Bool
    let index: Int
    let style: PaintStyle
    let seed: Int
    /// When it may begin; nil: the bar has not begun yet.
    let after: Date?
    /// How long after the bar's first stroke that is.
    var lead: Double = 0

    @State private var jobs = PaintJobs()
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        Color.clear
            .frame(width: Paint.swatch, height: Paint.swatch)
            .overlay {
                if let rgb = Paint.rgb(hex) {
                    let dark = scheme == .dark
                    let key = "\(style.rawValue)|\(hex)|\(sure)|\(index)|\(dark)|\(seed)"
                    Painted(job: jobs.job(key) { PaintJob.swatch(style, rgb: rgb, sure: sure, index: index, seed: seed, dark: dark) },
                            key: key, after: after, lead: lead)
                } else {
                    Circle().fill(Theme.mat)
                }
            }
    }
}
