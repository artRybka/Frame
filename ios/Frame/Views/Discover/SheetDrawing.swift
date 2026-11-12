import SwiftUI

/// The study sheet laid down before the reader, as if made now: the pen
/// first, stroke after stroke along the lines the server drew it by, then
/// the stains coming up under it and the pen shading the dark parts, then
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
///
/// With `bleed` the two pictures are wider than the field by that much of
/// its width on each side (the page's margin, where a stain runs out and a
/// stroke goes on past the frame): the view is laid that much wider than
/// the frame, and the masks know where the field lies in it.
struct SheetLayers: View {
    let wash: ImageRef
    let pen: ImageRef
    let strokes: [DailyWork.Stroke]
    /// Both pictures are here.
    let ready: Bool
    let maxPixel: CGFloat
    /// How much wider than the field the pictures are on each side (of the
    /// field's width); 0: they are the field.
    var bleed: CGFloat = 0
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
                    clocked { canvas, time, size in
                        SheetPlan.washMask(in: &canvas, size: size, time: time ?? SheetPlan.whole, bleed: bleed)
                    }
                }
            ArtImage(ref: pen, placeholder: .clear, maxPixel: maxPixel)
                .mask {
                    clocked { canvas, time, size in
                        guard let time else {
                            canvas.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.black))
                            return
                        }
                        SheetPlan.penMask(in: &canvas, size: size, time: time, strokes: strokes, bleed: bleed)
                    }
                }
                .opacity(SheetPlan.penShare)
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
    /// time has it; no time (nil) once all of it is drawn (and with Reduce
    /// Motion).
    private func clocked(_ draw: @escaping (inout GraphicsContext, Double?, CGSize) -> Void) -> some View {
        TimelineView(.animation(paused: start == nil || settled)) { context in
            let time = elapsed(context.date)
            Canvas { canvas, size in
                let now: Double? = (time ?? SheetPlan.whole) < SheetPlan.whole ? time : nil
                draw(&canvas, now, size)
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
    /// How much of the pen's ink the sheet keeps: the sketch lies under the
    /// marks and is weaker than they are (Mateusz 2026-11-12 11:31: "szkic
    /// pod spodem słabszy, a linie kredą - ciut mocniejsze i grubsze niż
    /// rysunek teraz").
    static let penShare = 0.6
    /// The pen's strokes, one after another at one speed.
    static let pen = 1.5
    /// The least a stroke takes, however short.
    static let dash = 0.14
    /// The stains come up from here on, for this long.
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

    /// How near a side (of the field's width) a stroke ends that may go on
    /// past the frame, and how much of its way must lead out of it (the
    /// server's `PAST_NEAR`, `PAST_HEADING`, a little wider: the mask may
    /// follow a stroke that did not go on, never miss one that did).
    static let pastNear: CGFloat = 0.05
    static let pastHeading: CGFloat = 0.3

    /// Where the field lies in a picture that is wider than it by `bleed`
    /// of its width on each side.
    static func field(in size: CGSize, bleed: CGFloat) -> CGRect {
        let side = size.width * bleed / (1 + 2 * bleed)
        return CGRect(x: side, y: 0, width: size.width - 2 * side, height: size.height)
    }

    /// A stroke's line on a sheet whose field is this.
    static func line(_ stroke: DailyWork.Stroke, in size: CGSize) -> [CGPoint] {
        line(stroke, in: CGRect(origin: .zero, size: size), margin: 0)
    }

    /// A stroke's line on a sheet whose field lies here, with `margin`
    /// beside it: an end at a side that heads out of the field is carried
    /// on over the margin, where the server's pen may have gone on.
    static func line(_ stroke: DailyWork.Stroke, in field: CGRect, margin: CGFloat) -> [CGPoint] {
        var points = stroke.points.map { spot in
            CGPoint(x: field.minX + CGFloat(spot.x) * field.width, y: field.minY + CGFloat(spot.y) * field.height)
        }
        guard points.count > 1 else { return [] }
        if stroke.closed == true, let first = points.first {
            points.append(first)
        } else if margin > 0 {
            if let tip = past(points[0], from: points[1], field: field, margin: margin) { points.insert(tip, at: 0) }
            if let tip = past(points[points.count - 1], from: points[points.count - 2], field: field, margin: margin) { points.append(tip) }
        }
        return stroke.sharp == true ? points : Pencil.smooth(points, samples: 8)
    }

    /// Where a stroke that ends at `end`, coming from `before`, would be
    /// at the margin's far side; nil when it does not end at a side
    /// heading out.
    static func past(_ end: CGPoint, from before: CGPoint, field: CGRect, margin: CGFloat) -> CGPoint? {
        let way = CGPoint(x: end.x - before.x, y: end.y - before.y)
        let long = hypot(way.x, way.y)
        guard long > 0 else { return nil }
        let across = way.x / long
        let left = end.x <= field.minX + pastNear * field.width && across < -pastHeading
        let right = end.x >= field.maxX - pastNear * field.width && across > pastHeading
        guard left || right else { return nil }
        let gap = left ? end.x - field.minX : field.maxX - end.x
        let run = min((gap + margin) / abs(across), 2.2 * margin)
        return CGPoint(x: end.x + way.x / long * run, y: end.y + way.y / long * run)
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
    static func penMask(in context: inout GraphicsContext, size: CGSize, time: Double, strokes: [DailyWork.Stroke], bleed: CGFloat = 0) {
        let frame = field(in: size, bleed: bleed)
        let lines = strokes.map { line($0, in: frame, margin: frame.minX) }.filter { $0.count > 1 }
        let timing = spans(lines.map { length($0) })
        let style = StrokeStyle(lineWidth: nib(in: frame.size), lineCap: .round, lineJoin: .round)
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

    /// How much of the stains shows at `time` (0…1): they come all over
    /// the sheet at once, slowly at first and at the end. Mateusz
    /// 2026-11-12 10:54, of the stains that spread from places: "akwarela
    /// niech płynnie wchodzi po całości, a nie 'rozlewa się'".
    static func washShown(at time: Double) -> Double {
        let part = min(1, max(0, (time - washFrom) / wash))
        return part * part * (3 - 2 * part)
    }

    /// How much of the margin beside the field (from its far side) the
    /// stains thin out over: where the screen is wider than the phone's, a
    /// stain that runs out ends softly, not at the picture's cut edge.
    static let washFade: CGFloat = 0.2

    /// The stains at `time`: the whole of them, as far as they show; with
    /// a margin beside the field, thinning to nothing at its far side.
    static func washMask(in context: inout GraphicsContext, size: CGSize, time: Double, bleed: CGFloat = 0) {
        let shown = washShown(at: time)
        guard shown > 0 else { return }
        let whole = Path(CGRect(origin: .zero, size: size))
        let side = field(in: size, bleed: bleed).minX
        guard side > 0, size.width > 0 else {
            context.fill(whole, with: .color(.black.opacity(shown)))
            return
        }
        let soft = washFade * side / size.width
        let stops = [
            Gradient.Stop(color: .clear, location: 0),
            Gradient.Stop(color: .black.opacity(shown), location: soft),
            Gradient.Stop(color: .black.opacity(shown), location: 1 - soft),
            Gradient.Stop(color: .clear, location: 1),
        ]
        context.fill(whole, with: .linearGradient(Gradient(stops: stops), startPoint: .zero, endPoint: CGPoint(x: size.width, y: 0)))
    }
}
