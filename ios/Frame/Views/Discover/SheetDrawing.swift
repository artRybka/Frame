import SwiftUI

/// The study sheet laid down before the reader, as if made now: the pen
/// first, stroke after stroke along the lines the server drew it by, then
/// the stains spreading under it and the pen shading the dark parts, then
/// (told through `onMarks`) the chalk. Mateusz 2026-11-12, having waited
/// on an empty ruled sheet: "Czy mógłby pojawiać się szybciej? malować /
/// rysować się na żywo?".
///
/// The sheet comes as two pictures (`CompositionSketch`): the stains, and
/// what the pen drew with nothing around it. Each is shown through a mask
/// that grows with time (`SheetPlan`); nothing here draws the sheet itself.
/// It starts once both pictures are here and the sheet is on screen, and
/// runs once: a sheet seen again (the page's other colour, a take picked
/// again) is whole at once. With Reduce Motion it is whole from the start.
struct SheetLayers: View {
    let wash: ImageRef
    let pen: ImageRef
    let strokes: [DailyWork.Stroke]
    /// Both pictures are here.
    let ready: Bool
    let maxPixel: CGFloat
    /// The sheet is drawn far enough for the chalk to come.
    let onMarks: () -> Void

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    /// When the drawing began.
    @State private var start: Date?
    /// On screen (enough of it to watch).
    @State private var seen = false
    @State private var settled = false
    @State private var told = false

    var body: some View {
        ZStack {
            ArtImage(ref: wash, placeholder: .clear, maxPixel: maxPixel)
                .mask {
                    clocked { canvas, time, size in SheetPlan.washMask(in: &canvas, size: size, time: time) }
                }
            ArtImage(ref: pen, placeholder: .clear, maxPixel: maxPixel)
                .mask {
                    clocked { canvas, time, size in
                        SheetPlan.penMask(in: &canvas, size: size, time: time, strokes: strokes)
                    }
                }
        }
        .onGeometryChange(for: Bool.self) { proxy in
            // No scroll view around it: nothing to wait for.
            guard let shown = proxy.bounds(of: .scrollView) else { return true }
            let own = CGRect(origin: .zero, size: proxy.size)
            return shown.intersection(own).height >= min(own.height, shown.height) * SheetPlan.seenShare
        } action: { seen = $0 }
        .background {
            // Keeps time while the sheet is being drawn.
            TimelineView(.animation(paused: start == nil || settled)) { context in
                Color.clear.onChange(of: context.date) { _, now in tick(now) }
            }
        }
        .onChange(of: ready && seen, initial: true) { _, both in
            if both { begin() }
        }
    }

    /// One layer's mask: nothing before the drawing starts, then as far as
    /// time has it, all of it once drawn (and with Reduce Motion).
    private func clocked(_ draw: @escaping (inout GraphicsContext, Double, CGSize) -> Void) -> some View {
        TimelineView(.animation(paused: start == nil || settled)) { context in
            let time = elapsed(context.date)
            Canvas { canvas, size in
                guard let time, time < SheetPlan.whole else {
                    canvas.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black))
                    return
                }
                draw(&canvas, time, size)
            }
        }
    }

    /// Seconds into the drawing; nil when it is over or not to be shown
    /// (the mask is whole then). Before it starts, nothing is drawn yet.
    private func elapsed(_ now: Date) -> Double? {
        if let frozen = LaunchRoute.sheetDrawn { return frozen * SheetPlan.whole }
        if settled || reduceMotion { return nil }
        guard let start else { return 0 }
        return max(0, now.timeIntervalSince(start))
    }

    private func begin() {
        guard start == nil else { return }
        if reduceMotion {
            settled = true
            tell()
            return
        }
        if let frozen = LaunchRoute.sheetDrawn {
            if frozen * SheetPlan.whole >= SheetPlan.marksAt { tell() }
            return
        }
        start = Date()
    }

    private func tick(_ now: Date) {
        guard let start, !settled else { return }
        let time = now.timeIntervalSince(start)
        if time >= SheetPlan.marksAt { tell() }
        if time >= SheetPlan.whole { settled = true }
    }

    private func tell() {
        guard !told else { return }
        told = true
        onMarks()
    }
}

/// When each part of a study sheet is laid down, and the masks that show
/// that much of it. Seconds from the start of the drawing.
enum SheetPlan {
    /// The pen's strokes, one after another at one speed.
    static let pen = 1.5
    /// The least a stroke takes, however short.
    static let dash = 0.14
    /// The stains spread from here on, for this long.
    static let washFrom = 0.8
    static let wash = 1.7
    /// The pen shades the dark parts (and whatever of it the strokes left).
    static let hatchFrom = 1.6
    static let hatch = 0.8
    /// The chalk comes.
    static let marksAt = 2.5
    /// All of the sheet is there.
    static let whole = 2.7
    /// How much of the sheet has to be on screen for the drawing to start.
    static let seenShare = 0.35

    /// A stroke's line on a sheet of this size.
    static func line(_ stroke: DailyWork.Stroke, in size: CGSize) -> [CGPoint] {
        var points = stroke.points.map { CGPoint(x: $0.x * size.width, y: $0.y * size.height) }
        guard points.count > 1 else { return [] }
        if stroke.closed == true, let first = points.first { points.append(first) }
        return stroke.sharp == true ? points : Pencil.smooth(points, samples: 8)
    }

    static func length(_ line: [CGPoint]) -> CGFloat {
        zip(line, line.dropFirst()).reduce(0) { $0 + hypot($1.1.x - $1.0.x, $1.1.y - $1.0.y) }
    }

    /// When each stroke begins and how long it takes: in their order, the
    /// pen moving at one speed over all of them, a short one never quicker
    /// than `dash`.
    static func spans(_ lengths: [CGFloat]) -> [(from: Double, takes: Double)] {
        let total = Double(lengths.reduce(0, +))
        guard total > 0 else { return lengths.map { _ in (from: 0, takes: dash) } }
        var done = 0.0
        return lengths.map { length in
            let share = Double(length) / total
            let span = (from: pen * done, takes: max(dash, pen * share))
            done += share
            return span
        }
    }

    /// How much of a stroke is drawn at `time` (0…1).
    static func drawn(_ span: (from: Double, takes: Double), at time: Double) -> Double {
        min(1, max(0, (time - span.from) / span.takes))
    }

    /// How wide the mask follows a stroke: the pen's line with its wobble
    /// lies well inside.
    static func nib(in size: CGSize) -> CGFloat {
        max(12, 0.035 * max(size.width, size.height))
    }

    /// The pen's layer at `time`: along each stroke as far as it is drawn,
    /// then a slanted edge that goes over the sheet as the hand shades it.
    static func penMask(in context: inout GraphicsContext, size: CGSize, time: Double, strokes: [DailyWork.Stroke]) {
        let lines = strokes.map { line($0, in: size) }.filter { $0.count > 1 }
        let timing = spans(lines.map { length($0) })
        let style = StrokeStyle(lineWidth: nib(in: size), lineCap: .round, lineJoin: .round)
        for (line, span) in zip(lines, timing) {
            let part = drawn(span, at: time)
            guard part > 0 else { continue }
            var path = Path()
            path.addLines(line)
            context.stroke(part < 1 ? path.trimmedPath(from: 0, to: part) : path, with: .color(.black), style: style)
        }
        let shaded = min(1, max(0, (time - hatchFrom) / hatch))
        guard shaded > 0 else { return }
        // From the upper left to the lower right, a soft edge ahead of it.
        let soft = 0.18
        let edge = shaded * (1 + soft)
        let stops = [
            Gradient.Stop(color: .black, location: 0),
            Gradient.Stop(color: .black, location: min(1, max(0, edge - soft))),
            Gradient.Stop(color: .clear, location: min(1, max(0.001, edge))),
        ]
        context.fill(
            Path(CGRect(origin: .zero, size: size)),
            with: .linearGradient(Gradient(stops: stops), startPoint: .zero, endPoint: CGPoint(x: size.width, y: size.height))
        )
    }

    /// Where a stain starts to spread and when (of the wash's time, 0…1),
    /// on a sheet cut into cells of about a third of its short side; the
    /// same for the same sheet.
    static func blooms(in size: CGSize) -> [(centre: CGPoint, from: Double, reach: CGFloat)] {
        let cell = max(40, min(size.width, size.height) / 3)
        let columns = max(2, Int((size.width / cell).rounded())), rows = max(2, Int((size.height / cell).rounded()))
        let wide = size.width / CGFloat(columns), tall = size.height / CGFloat(rows)
        var out: [(centre: CGPoint, from: Double, reach: CGFloat)] = []
        for row in 0..<rows {
            for column in 0..<columns {
                let seed = row * 31 + column * 7
                let x = (CGFloat(column) + 0.25 + 0.5 * CGFloat(Pencil.Jitter.random(seed + 1))) * wide
                let y = (CGFloat(row) + 0.25 + 0.5 * CGFloat(Pencil.Jitter.random(seed + 2))) * tall
                // Each a little after its neighbour to the upper left, none in step.
                let along = Double(row + column) / Double(max(1, rows + columns - 2))
                let from = 0.45 * (0.7 * along + 0.3 * Pencil.Jitter.random(seed + 3))
                out.append((centre: CGPoint(x: x, y: y), from: from, reach: 1.15 * hypot(wide, tall)))
            }
        }
        return out
    }

    /// The stains at `time`: each spreading from its place with a soft
    /// edge, as paint runs into wet paper, until they are one.
    static func washMask(in context: inout GraphicsContext, size: CGSize, time: Double) {
        let spread = min(1, max(0, (time - washFrom) / wash))
        guard spread > 0 else { return }
        var soft = context
        soft.addFilter(.blur(radius: max(8, 0.035 * min(size.width, size.height))))
        soft.drawLayer { layer in
            for bloom in blooms(in: size) {
                let grown = min(1, max(0, (spread - bloom.from) / (1 - 0.45)))
                guard grown > 0 else { continue }
                // Quick at first, slowing as the paint thins out.
                let radius = bloom.reach * CGFloat(1 - pow(1 - grown, 2.2))
                layer.fill(
                    Path(ellipseIn: CGRect(x: bloom.centre.x - radius, y: bloom.centre.y - radius, width: 2 * radius, height: 2 * radius)),
                    with: .color(.black)
                )
            }
        }
    }
}
