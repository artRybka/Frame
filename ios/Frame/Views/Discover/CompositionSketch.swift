import SwiftUI

/// One take on the composition: the picture as it is, in full colour, the
/// marks drawn over it in pencil with a paper-coloured edge (so they read on
/// dark and light parts alike) and a number beside each, and their labels
/// under the picture in two columns, all hand-written: a title and a line
/// under it. A tap on the picture hides the marks, another brings them back
/// (no sign for it on the picture).
struct CompositionSketch: View {
    let item: RemoteItem
    let aspect: CGFloat
    let take: DailyWork.Take
    /// The text block's width: the picture takes all of it, the same in
    /// every take (nil: as wide as the column lets it).
    var width: CGFloat? = nil
    @State private var bare = false

    /// A mark with a label, by its number on the picture.
    struct Labelled: Identifiable {
        let number: Int
        let mark: DailyWork.Mark
        var id: Int { number }
    }

    var body: some View {
        let labelled = Self.labelled(take.marks)
        VStack(spacing: 14) {
            picture(labelled)
            if !labelled.isEmpty {
                LazyVGrid(
                    columns: [GridItem(.flexible(), spacing: 14, alignment: .topLeading), GridItem(.flexible(), alignment: .topLeading)],
                    alignment: .leading,
                    spacing: 12
                ) {
                    ForEach(labelled) { label($0) }
                }
            }
        }
    }

    private let pencil = Pencil.lead
    private let paper = Pencil.paper

    /// The picture's box: the whole given width, as tall as its shape makes it.
    @ViewBuilder
    private var box: some View {
        if let width, width > 0 {
            Color.clear.frame(width: width, height: width / aspect)
        } else {
            Color.clear.frame(maxWidth: .infinity).aspectRatio(aspect, contentMode: .fit)
        }
    }

    private func picture(_ labelled: [Labelled]) -> some View {
        box
            .overlay {
                ArtImage(
                    ref: item.inLibrary ? .image(item.id) : item.thumb,
                    fallback: .thumb(item.id),
                    placeholder: item.item.placeholderColor,
                    maxPixel: 1600
                )
            }
            .overlay {
                Canvas { context, size in draw(in: &context, size: size, labelled: labelled) }
                    .shadow(color: .black.opacity(0.3), radius: 1.5, y: 0.5)
                    .opacity(bare ? 0 : 1)
                    .allowsHitTesting(false)
            }
            .clipShape(RoundedRectangle(cornerRadius: 3, style: .continuous))
            .contentShape(Rectangle())
            .onTapGesture {
                withAnimation(.easeInOut(duration: 0.25)) { bare.toggle() }
            }
            .sensoryFeedback(.selection, trigger: bare)
            .accessibilityAddTraits(.isButton)
            .accessibilityHint(bare ? "Pokazuje ślady analizy" : "Pokazuje sam obraz")
            .frame(maxWidth: .infinity)
    }

    /// Each stroke twice: a wider paper-coloured one under it, then the
    /// pencil; the grid fainter, the numbers on paper discs (`Pencil.badge`).
    private func draw(in context: inout GraphicsContext, size: CGSize, labelled: [Labelled]) {
        for (index, line) in Pencil.grid(take.grid, in: size).enumerated() {
            let path = Pencil.stroke(line, width: 1, seed: 90 + index, start: 0.05, end: 0.05)
            context.stroke(path, with: .color(paper.opacity(0.7)), lineWidth: 1.6)
            context.fill(path, with: .color(pencil.opacity(0.75)))
        }
        for (index, mark) in take.marks.enumerated() {
            let paths = Pencil.paths(for: mark, in: size, seed: index * 7 + 1)
            for path in paths {
                context.stroke(path, with: .color(paper), style: StrokeStyle(lineWidth: 3.2, lineCap: .round, lineJoin: .round))
            }
            for path in paths {
                context.fill(path, with: .color(pencil))
            }
        }
        for entry in labelled {
            Pencil.badge(entry.number, at: Pencil.numberSpot(for: entry.mark, in: size), in: &context)
        }
    }

    /// The number on the same badge as on the picture, and beside it the
    /// title with its line under it: the line starts where the title does,
    /// not under the number.
    private func label(_ entry: Labelled) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 5) {
            Canvas { context, size in
                Pencil.badge(entry.number, at: CGPoint(x: size.width / 2, y: size.height / 2), in: &context)
            }
            .frame(width: 22, height: 22)
            .shadow(color: .black.opacity(0.22), radius: 1.2, y: 0.5)
            .alignmentGuide(.firstTextBaseline) { $0[VerticalAlignment.center] + 5 }
            .accessibilityHidden(true)
            // The hand-written face has tall lines: the note sits close
            // under its title, and its own lines close together, as
            // written by hand.
            VStack(alignment: .leading, spacing: -7) {
                Text(entry.mark.title)
                    .font(.hand(21))
                    .lineLimit(2)
                    .minimumScaleFactor(0.8)
                if !entry.mark.text.isEmpty {
                    HandLines(text: entry.mark.text, size: 18)
                        .foregroundStyle(Theme.inkSoft)
                }
            }
        }
        .foregroundStyle(Theme.ink)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// The marks with a title, numbered in the order the model gave them
    /// (the eye's path): untitled marks are drawn, not labelled.
    static func labelled(_ marks: [DailyWork.Mark]) -> [Labelled] {
        marks.filter { !$0.title.isEmpty }.enumerated().map { Labelled(number: $0.offset + 1, mark: $0.element) }
    }
}

extension DailyWork.Mark {
    /// Where a remark about the mark points, as the server has it: a
    /// loop's centre, the middle of a rect or triangle, a spiral's eye, a
    /// path's middle point.
    var anchor: DailyWork.Spot {
        guard let first = points.first else { return DailyWork.Spot(x: 0.5, y: 0.5) }
        switch shape {
        case "loop": return first
        case "rect" where points.count == 2:
            return DailyWork.Spot(x: (points[0].x + points[1].x) / 2, y: (points[0].y + points[1].y) / 2)
        case "triangle" where points.count == 3:
            return DailyWork.Spot(x: points.map(\.x).reduce(0, +) / 3, y: points.map(\.y).reduce(0, +) / 3)
        case "spiral": return points[points.count - 1]
        default: return points[points.count / 2]
        }
    }
}

/// Hand-written text wrapped word by word, its lines closer together than
/// the face's own: Caveat's lines are tall (1.26 em) for its small letters,
/// and SwiftUI's `Text` cannot tighten them (negative line spacing does
/// nothing), so a wrapped note looked double-spaced.
struct HandLines: View {
    let text: String
    let size: CGFloat

    var body: some View {
        let words = text.split(whereSeparator: \.isWhitespace).map(String.init)
        // Caveat's space is 0.242 em; a line every 0.95 em, as close as the
        // note sits under its title.
        WordFlow(space: size * 0.242, pitch: size * 0.95) {
            ForEach(words.indices, id: \.self) { index in
                Text(words[index]).font(.hand(size))
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(text)
    }
}

/// Words laid out like a paragraph: as many as fit on a line, then the
/// next line `pitch` below (less than a word's own height, so the lines'
/// frames overlap; they have no background).
struct WordFlow: Layout {
    let space: CGFloat
    let pitch: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let placed = place(subviews, width: proposal.width ?? .infinity)
        guard let last = placed.last else { return .zero }
        let width = placed.map { $0.origin.x + $0.size.width }.max() ?? 0
        return CGSize(width: width, height: last.origin.y + last.size.height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        for (subview, frame) in zip(subviews, place(subviews, width: bounds.width)) {
            subview.place(
                at: CGPoint(x: bounds.minX + frame.origin.x, y: bounds.minY + frame.origin.y),
                anchor: .topLeading,
                proposal: ProposedViewSize(frame.size)
            )
        }
    }

    /// Each word's frame: on the line while it fits, else at the start of
    /// the next (a word wider than the line gets a line of its own).
    private func place(_ subviews: Subviews, width: CGFloat) -> [CGRect] {
        var frames: [CGRect] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > 0, x + space + size.width > width {
                x = 0
                y += pitch
            }
            if x > 0 { x += space }
            frames.append(CGRect(origin: CGPoint(x: x, y: y), size: size))
            x += size.width
        }
        return frames
    }
}

/// Pencil marks as filled outlines: strokes thin at both ends and a little
/// uneven, loops that overshoot where they close, arrowheads of two
/// strokes. The same seed draws the same mark every time.
enum Pencil {
    /// Pencil and the paper edge around it, the same over any picture.
    static let lead = Color(hex: 0x2E2A25)
    static let paper = Color(hex: 0xFBF8F2)

    /// A mark's number: on a paper disc in a pencil ring drawn by hand, the
    /// same on the picture and in the legend under it (the ring's seed is
    /// the number, so number 2 has the same ring in both).
    static func badge(_ number: Int, at spot: CGPoint, in context: inout GraphicsContext) {
        context.fill(Path(ellipseIn: CGRect(x: spot.x - 9.5, y: spot.y - 9.5, width: 19, height: 19)), with: .color(paper))
        context.fill(loop(center: spot, rx: 8.5, ry: 8, width: 1.4, seed: 40 + number), with: .color(lead))
        context.draw(
            Text("\(number)").font(.system(size: 10.5, weight: .bold)).foregroundStyle(lead),
            at: spot
        )
    }

    static func paths(for mark: DailyWork.Mark, in size: CGSize, seed: Int) -> [Path] {
        let points = mark.points.map { CGPoint(x: $0.x * size.width, y: $0.y * size.height) }
        guard let first = points.first else { return [] }
        switch mark.shape {
        case "loop":
            let corner = points.count > 1 ? points[1] : first
            let rx = max(abs(corner.x - first.x), 8)
            let ry = max(abs(corner.y - first.y), 8)
            return [loop(center: first, rx: rx, ry: ry, width: 2.4, seed: seed)]
        case "triangle" where points.count == 3:
            return (0..<3).map { side(points[$0], points[($0 + 1) % 3], width: 2, seed: seed + $0) }
        case "rect" where points.count == 2:
            let (a, b) = (points[0], points[1])
            let corners = [a, CGPoint(x: b.x, y: a.y), b, CGPoint(x: a.x, y: b.y)]
            return (0..<4).map { side(corners[$0], corners[($0 + 1) % 4], width: 1.6, seed: seed + $0) }
        case "underline" where points.count >= 2:
            return [stroke(wave(from: first, to: points[points.count - 1]), width: 2.2, seed: seed)]
        case "spiral" where points.count == 3:
            let line = spiral(start: points[0], through: points[1], eye: points[2])
            return line.count >= 2 ? [stroke(line, width: 2.2, seed: seed, start: 0.04, end: 0.3)] : []
        case "rhythm" where points.count >= 2:
            // A light line through the repeated things, a beat across it at each.
            let line = stroke(points, width: 1.6, seed: seed, start: 0.08, end: 0.08)
            return [line] + points.enumerated().map { index, point in
                beat(at: point, along: points, index: index, seed: seed + index)
            }
        case "arrow" where points.count >= 2:
            let line = smooth(points)
            let tip = line[line.count - 1]
            let from = line[max(0, line.count - 6)]
            return [stroke(points, width: 2.6, seed: seed)] + head(tip: tip, from: from, width: 2.3, size: 10)
        default:
            return points.count >= 2 ? [stroke(points, width: 2.2, seed: seed)] : []
        }
    }

    /// Where a mark's number goes: beside a loop's upper right, inside a
    /// rect's corner, over a triangle's top, before an underline, above a
    /// line's end or an arrow's middle, beside a spiral's eye; always inside
    /// the picture.
    static func numberSpot(for mark: DailyWork.Mark, in size: CGSize) -> CGPoint {
        let points = mark.points.map { CGPoint(x: $0.x * size.width, y: $0.y * size.height) }
        guard let first = points.first else { return CGPoint(x: size.width / 2, y: size.height / 2) }
        var spot: CGPoint
        switch mark.shape {
        case "loop":
            let corner = points.count > 1 ? points[1] : first
            let rx = max(abs(corner.x - first.x), 8)
            let ry = max(abs(corner.y - first.y), 8)
            spot = CGPoint(x: first.x + rx * 0.72 + 9, y: first.y - ry * 0.72 - 9)
        case "rect":
            spot = CGPoint(x: points.map(\.x).min()! + 12, y: points.map(\.y).min()! + 12)
        case "triangle":
            let top = points.min { $0.y < $1.y }!
            spot = CGPoint(x: top.x + 13, y: top.y - 6)
        case "spiral":
            let eye = points[points.count - 1]
            spot = CGPoint(x: eye.x + 14, y: eye.y - 14)
        case "underline":
            let start = points.min { $0.x < $1.x }!
            spot = CGPoint(x: start.x - 14, y: start.y)
        case "line":
            let end = points[points.count - 1]
            spot = CGPoint(x: end.x - 4, y: end.y - 14)
        default:
            let middle = points[points.count / 2]
            spot = CGPoint(x: middle.x, y: middle.y - 15)
        }
        let margin: CGFloat = 11
        spot.x = min(max(spot.x, margin), max(size.width - margin, margin))
        spot.y = min(max(spot.y, margin), max(size.height - margin, margin))
        return spot
    }

    /// The grid under a take: lines at the golden section, thirds (3×3),
    /// halves (2×2), thirds across and halves down (3×2) or the other way
    /// round (2×3), each a faint ruled stroke across the picture.
    static func grid(_ grid: String, in size: CGSize) -> [[CGPoint]] {
        let across: [CGFloat], down: [CGFloat]
        switch grid {
        case "golden": (across, down) = ([0.382, 0.618], [0.382, 0.618])
        case "thirds": (across, down) = ([1 / 3, 2 / 3], [1 / 3, 2 / 3])
        case "halves": (across, down) = ([0.5], [0.5])
        case "3x2": (across, down) = ([1 / 3, 2 / 3], [0.5])
        case "2x3": (across, down) = ([0.5], [1 / 3, 2 / 3])
        default: return []
        }
        return across.map { cut in
            [CGPoint(x: cut * size.width, y: size.height * 0.01), CGPoint(x: cut * size.width, y: size.height * 0.99)]
        } + down.map { cut in
            [CGPoint(x: size.width * 0.01, y: cut * size.height), CGPoint(x: size.width * 0.99, y: cut * size.height)]
        }
    }

    /// A golden spiral from `start` into its `eye`, turning the way `through`
    /// lies from the line between them: every quarter turn its radius shrinks
    /// by φ, as the server draws it (`ai/sketch.py`).
    static func spiral(start: CGPoint, through: CGPoint, eye: CGPoint) -> [CGPoint] {
        let dx = start.x - eye.x, dy = start.y - eye.y
        let radius = hypot(dx, dy)
        guard radius > 2 else { return [] }
        let cross = dx * (through.y - eye.y) - dy * (through.x - eye.x)
        let turn: CGFloat = cross < 0 ? -1 : 1
        let angle = atan2(dy, dx)
        let growth = log((1 + sqrt(5)) / 2) / (.pi / 2)
        let end = log(radius / 1.5) / growth
        let steps = max(Int(end / (.pi / 12)), 2)
        return (0...steps).map { step in
            let theta = end * CGFloat(step) / CGFloat(steps)
            let r = radius * exp(-growth * theta)
            return CGPoint(x: eye.x + r * cos(angle + turn * theta), y: eye.y + r * sin(angle + turn * theta))
        }
    }

    /// A pen stroke through the points: a filled outline, thin at both ends
    /// (`start` and `end` are the fractions it takes to reach full width).
    static func stroke(_ points: [CGPoint], width: CGFloat, seed: Int, start: CGFloat = 0.25, end: CGFloat = 0.25) -> Path {
        let line = smooth(points)
        guard line.count > 1 else { return Path() }
        var lengths: [CGFloat] = [0]
        for index in 1..<line.count {
            lengths.append(lengths[index - 1] + hypot(line[index].x - line[index - 1].x, line[index].y - line[index - 1].y))
        }
        let total = max(lengths[lengths.count - 1], 1)
        let phase = CGFloat(Jitter.random(seed) * 6)
        var left: [CGPoint] = []
        var right: [CGPoint] = []
        for index in line.indices {
            let t = lengths[index] / total
            let a = start > 0 ? min(1, t / start) : 1
            let b = end > 0 ? min(1, (1 - t) / end) : 1
            let wobble = 1 + 0.12 * sin(CGFloat(index) * 0.35 + phase)
            let half = width * (0.25 + 0.75 * pow(max(min(a, b), 0), 0.7)) * wobble / 2
            let before = line[max(index - 1, 0)]
            let after = line[min(index + 1, line.count - 1)]
            let dx = after.x - before.x
            let dy = after.y - before.y
            let length = max(hypot(dx, dy), 0.0001)
            let normal = CGPoint(x: -dy / length * half, y: dx / length * half)
            left.append(CGPoint(x: line[index].x + normal.x, y: line[index].y + normal.y))
            right.append(CGPoint(x: line[index].x - normal.x, y: line[index].y - normal.y))
        }
        var path = Path()
        path.addLines(left + right.reversed())
        path.closeSubpath()
        return path
    }

    /// A loop drawn in one go: it starts lower left, goes round a little more
    /// than once and widens as it goes, so the ends do not meet.
    static func loop(center: CGPoint, rx: CGFloat, ry: CGFloat, width: CGFloat, seed: Int) -> Path {
        var jitter = Jitter(seed: seed)
        let start = 190 + jitter.next() * 40
        let points = (0..<24).map { index -> CGPoint in
            let angle = (start + 380 * Double(index) / 23) * .pi / 180
            let k = 1 + 0.04 * sin(Double(index) * 0.8) + 0.07 * Double(index) / 23
            return CGPoint(x: center.x + rx * k * cos(angle), y: center.y + ry * k * sin(angle))
        }
        return stroke(points, width: width, seed: seed, start: 0.12, end: 0.3)
    }

    /// A beat of a rhythm: a short stroke across the line at one of its
    /// points, a little longer at the first.
    static func beat(at point: CGPoint, along points: [CGPoint], index: Int, seed: Int) -> Path {
        let before = points[max(index - 1, 0)]
        let after = points[min(index + 1, points.count - 1)]
        let dx = after.x - before.x
        let dy = after.y - before.y
        let length = max(hypot(dx, dy), 0.0001)
        let half: CGFloat = index == 0 ? 8 : 6
        let normal = CGPoint(x: -dy / length * half, y: dx / length * half)
        return stroke(
            [CGPoint(x: point.x - normal.x, y: point.y - normal.y), CGPoint(x: point.x + normal.x, y: point.y + normal.y)],
            width: 2.6, seed: seed, start: 0.15, end: 0.15
        )
    }

    /// An arrowhead: two short strokes back from the tip.
    static func head(tip: CGPoint, from: CGPoint, width: CGFloat, size: CGFloat) -> [Path] {
        let angle = atan2(tip.y - from.y, tip.x - from.x)
        return [CGFloat(2.55), -2.45].map { turn -> Path in
            let a = angle + turn
            let points = [
                tip,
                CGPoint(x: tip.x + size * 0.55 * cos(a) + 0.6, y: tip.y + size * 0.55 * sin(a)),
                CGPoint(x: tip.x + size * cos(a), y: tip.y + size * sin(a)),
            ]
            return stroke(points, width: width, seed: 1, start: 0.05, end: 0.6)
        }
    }

    /// A ruled side of a triangle or rect, a little past both corners.
    static func side(_ a: CGPoint, _ b: CGPoint, width: CGFloat, seed: Int) -> Path {
        let length = max(hypot(b.x - a.x, b.y - a.y), 0.0001)
        let over = CGPoint(x: (b.x - a.x) / length * 3, y: (b.y - a.y) / length * 3)
        let bend = CGFloat(Jitter.random(seed) - 0.5) * 1.2
        let middle = CGPoint(x: (a.x + b.x) / 2 - over.y / 3 * bend, y: (a.y + b.y) / 2 + over.x / 3 * bend)
        return stroke(
            [CGPoint(x: a.x - over.x, y: a.y - over.y), middle, CGPoint(x: b.x + over.x, y: b.y + over.y)],
            width: width, seed: seed, start: 0.1, end: 0.1
        )
    }

    /// An underline as a small wave from start to end.
    static func wave(from start: CGPoint, to end: CGPoint) -> [CGPoint] {
        let length = hypot(end.x - start.x, end.y - start.y)
        let steps = max(Int(length / 12.5), 3)
        let normal = CGPoint(x: -(end.y - start.y) / max(length, 0.0001), y: (end.x - start.x) / max(length, 0.0001))
        return (0...steps).map { step -> CGPoint in
            let t = CGFloat(step) / CGFloat(steps)
            let lift: CGFloat = step % 2 == 0 ? 0 : 3.5
            return CGPoint(
                x: start.x + (end.x - start.x) * t + normal.x * lift,
                y: start.y + (end.y - start.y) * t + normal.y * lift
            )
        }
    }

    /// A Catmull-Rom curve through the points, ten samples a segment.
    static func smooth(_ points: [CGPoint], samples: Int = 10) -> [CGPoint] {
        guard points.count > 1 else { return points }
        var out: [CGPoint] = []
        for index in 0..<(points.count - 1) {
            let p0 = points[max(index - 1, 0)]
            let p1 = points[index]
            let p2 = points[index + 1]
            let p3 = points[min(index + 2, points.count - 1)]
            for step in 0..<samples {
                let t = CGFloat(step) / CGFloat(samples)
                let t2 = t * t
                let t3 = t2 * t
                func axis(_ v0: CGFloat, _ v1: CGFloat, _ v2: CGFloat, _ v3: CGFloat) -> CGFloat {
                    0.5 * (2 * v1 + (v2 - v0) * t + (2 * v0 - 5 * v1 + 4 * v2 - v3) * t2 + (3 * v1 - v0 - 3 * v2 + v3) * t3)
                }
                out.append(CGPoint(x: axis(p0.x, p1.x, p2.x, p3.x), y: axis(p0.y, p1.y, p2.y, p3.y)))
            }
        }
        out.append(points[points.count - 1])
        return out
    }

    /// SplitMix64: the same marks for the same seed.
    struct Jitter {
        var state: UInt64

        init(seed: Int) { state = UInt64(truncatingIfNeeded: seed) &+ 0x9E37_79B9_7F4A_7C15 }

        static func random(_ seed: Int) -> Double {
            var jitter = Jitter(seed: seed)
            return jitter.next()
        }

        mutating func next() -> Double {
            state = state &+ 0x9E37_79B9_7F4A_7C15
            var z = state
            z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
            z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
            z ^= z >> 31
            return Double(z >> 11) / Double(1 << 53)
        }
    }
}
