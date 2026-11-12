import SwiftUI
import UIKit

/// One take on the composition, drawn as a study sheet: the picture's field
/// in stains of its colours with a pen sketch over them (made by the server,
/// on the page's own colour), ruled with a thin frame and the grid in
/// graphite, the marks over it in a draughtsman's coloured pencil, red or
/// blue, whichever stands out from the picture, with a number beside each;
/// their labels under the sheet in two columns, hand-written: a title and a
/// line under it. A tap shows the picture itself under the marks, another
/// brings the sheet back (no sign for it on the sheet).
///
/// A server from before the sheet (no `sheet`), or a sheet that would not
/// load: the picture as it is, the marks in pencil with a paper-coloured
/// edge, and a tap hides them.
struct CompositionSketch: View {
    @Environment(AppModel.self) private var model
    @Environment(\.colorScheme) private var scheme
    let item: RemoteItem
    /// The whole picture's shape (the sheet shows its field).
    let aspect: CGFloat
    let take: DailyWork.Take
    /// Server path of the take's study sheet ("" when it has none).
    var sheet: String = ""
    /// The text block's width: the picture takes all of it, the same in
    /// every take (nil: as wide as the column lets it).
    var width: CGFloat? = nil
    @State private var bare = LaunchRoute.compositionBare
    /// The pencil picked for each sheet that loaded.
    @State private var crayons: [ImageRef: Crayon] = [:]
    /// The sheet that would not load: the marks go on the picture.
    @State private var failed: ImageRef?

    /// A mark with a label, by its number on the picture.
    struct Labelled: Identifiable {
        let number: Int
        let mark: DailyWork.Mark
        var id: Int { number }
    }

    /// The sheet for the page's colour now.
    private var sheetRef: ImageRef? {
        sheet.isEmpty ? nil : .path(sheet + (scheme == .dark ? "&dark=1" : ""))
    }

    var body: some View {
        let ref = sheetRef.flatMap { $0 == failed ? nil : $0 }
        let marks = ref == nil ? take.marks : take.marksInField
        let labelled = Self.labelled(marks)
        let crayon = ref.flatMap { crayons[$0] }
        VStack(spacing: 14) {
            if let ref {
                sheetPicture(ref, marks: marks, labelled: labelled, crayon: crayon)
            } else {
                picture(labelled)
            }
            if !labelled.isEmpty {
                LazyVGrid(
                    columns: [GridItem(.flexible(), spacing: 14, alignment: .topLeading), GridItem(.flexible(), alignment: .topLeading)],
                    alignment: .leading,
                    spacing: 12
                ) {
                    ForEach(labelled) { entry in
                        label(entry, ink: ref == nil ? nil : (crayon?.color(for: entry.mark, dark: scheme == .dark) ?? Theme.inkSoft))
                    }
                }
            }
        }
        .animation(.easeOut(duration: 0.3), value: crayon)
    }

    private let pencil = Pencil.lead
    private let paper = Pencil.paper

    /// A box of the given shape: the whole given width, as tall as the
    /// shape makes it.
    @ViewBuilder
    private func box(_ aspect: CGFloat) -> some View {
        if let width, width > 0 {
            Color.clear.frame(width: width, height: width / aspect)
        } else {
            Color.clear.frame(maxWidth: .infinity).aspectRatio(aspect, contentMode: .fit)
        }
    }

    private var pictureRef: ImageRef { item.inLibrary ? item.item.originalRef : item.thumb }

    // MARK: The study sheet

    /// The field's shape: the picture's, cut to its field.
    private var fieldAspect: CGFloat {
        let field = take.shownField
        return aspect * CGFloat(field.w / field.h)
    }

    /// The sheet with the marks over it. The frame and the grid run a
    /// little past the field's corners, as ruled by hand, and the
    /// picture's great lines further (`Pencil.overflow`): room is made
    /// above and below for them, at the sides they run into the gutter.
    private func sheetPicture(_ ref: ImageRef, marks: [DailyWork.Mark], labelled: [Labelled], crayon: Crayon?) -> some View {
        let room = sheetRoom(marks)
        let dark = scheme == .dark
        return box(fieldAspect)
            .overlay {
                ArtImage(ref: ref, placeholder: .clear, maxPixel: Self.sheetPixels)
                    .environment(\.artImageLoaded) { loaded in sheetLoaded(loaded) }
                    .opacity(bare ? 0 : 1)
            }
            .overlay {
                // The picture itself, cut to the field: only once asked for.
                if bare { fieldOfPicture.transition(.opacity) }
            }
            .overlay {
                Canvas { context, size in
                    let field = Self.pictureRect(in: size, room: room)
                    context.translateBy(x: field.minX, y: field.minY)
                    drawSheet(in: &context, size: field.size, marks: marks, labelled: labelled, crayon: crayon, dark: dark)
                }
                .padding(EdgeInsets(top: -room.top, leading: -room.leading, bottom: -room.bottom, trailing: -room.trailing))
                .allowsHitTesting(false)
            }
            .contentShape(Rectangle())
            .onTapGesture {
                withAnimation(.easeInOut(duration: 0.3)) { bare.toggle() }
            }
            .sensoryFeedback(.selection, trigger: bare)
            .accessibilityAddTraits(.isButton)
            .accessibilityHint(bare ? "Pokazuje arkusz analizy" : "Pokazuje obraz pod śladami analizy")
            .padding(.top, room.top)
            .padding(.bottom, room.bottom)
            .frame(maxWidth: .infinity)
            .task(id: ref) {
                // A sheet already in memory has its pencil at once.
                if let image = sheetInMemory(ref) { pick(ref, image) }
            }
    }

    /// The picture cut to the field the sheet shows.
    private var fieldOfPicture: some View {
        GeometryReader { geometry in
            let field = take.shownField
            let whole = CGSize(width: geometry.size.width / field.w, height: geometry.size.height / field.h)
            ArtImage(ref: pictureRef, fallback: .thumb(item.id), placeholder: item.item.placeholderColor, maxPixel: 1600)
                .frame(width: whole.width, height: whole.height)
                .offset(x: -field.x * whole.width, y: -field.y * whole.height)
        }
        .clipped()
    }

    /// The sheet is here, or was given up on: with it the pencil that
    /// stands out from its colours is picked; without it the marks go on
    /// the picture, as before the sheet.
    private func sheetLoaded(_ ref: ImageRef) {
        guard ref == sheetRef else { return }
        if let image = sheetInMemory(ref) {
            pick(ref, image)
        } else {
            failed = ref
        }
    }

    private func sheetInMemory(_ ref: ImageRef) -> UIImage? {
        model.backend.request(for: ref).flatMap { ImageLoader.inMemory(for: $0, maxPixel: Self.sheetPixels) }
    }

    private func pick(_ ref: ImageRef, _ image: UIImage) {
        guard crayons[ref] == nil else { return }
        crayons[ref] = Crayon.pick(for: image, dark: scheme == .dark)
    }

    private static let sheetPixels: CGFloat = 1600

    /// Room around the field for what runs past it: the frame's and the
    /// grid's ends always, the marks' as far as they reach.
    private func sheetRoom(_ marks: [DailyWork.Mark]) -> EdgeInsets {
        let least = Pencil.reach + 2
        guard let width, width > 0, fieldAspect > 0 else {
            return EdgeInsets(top: least, leading: least, bottom: least, trailing: least)
        }
        let size = CGSize(width: width, height: width / fieldAspect)
        let marks = Pencil.overflow(of: marks, in: size, weight: Pencil.crayonWeight)
        return EdgeInsets(
            top: max(marks.top, least), leading: max(marks.leading, least),
            bottom: max(marks.bottom, least), trailing: max(marks.trailing, least)
        )
    }

    /// The frame and the grid ruled in graphite; then the marks in the
    /// coloured pencil, the wash wiped off under each (a soft edge of the
    /// page's colour, so the pencil reads on any stain and on the picture
    /// itself); a returning colour's rings and broken line in the pencil's
    /// other end; the numbers on a dab of the page's colour. No marks before
    /// the sheet is here: the pencil is picked from its colours.
    private func drawSheet(
        in context: inout GraphicsContext, size: CGSize,
        marks: [DailyWork.Mark], labelled: [Labelled], crayon: Crayon?, dark: Bool
    ) {
        let graphite = Theme.ink.opacity(dark ? 0.5 : 0.55)
        let corners = [CGPoint.zero, CGPoint(x: size.width, y: 0), CGPoint(x: size.width, y: size.height), CGPoint(x: 0, y: size.height)]
        for index in 0..<4 {
            let path = Pencil.ruled(corners[index], corners[(index + 1) % 4], over: Pencil.reach, width: 0.9, seed: 70 + index)
            context.fill(path, with: .color(graphite))
        }
        for (index, line) in Pencil.grid(take.grid, in: size).enumerated() {
            let path = Pencil.ruled(line[0], line[1], over: Pencil.reach, width: 0.9, seed: 90 + index)
            context.fill(path, with: .color(graphite))
        }
        guard let crayon else { return }
        let weight = Pencil.crayonWeight
        let drawn: [(mark: DailyWork.Mark, paths: [Path])] = marks.enumerated().map { index, mark in
            (mark: mark, paths: Pencil.paths(for: mark, in: size, seed: index * 7 + 1, weight: weight))
        }
        var wiped = context
        wiped.opacity = 0.72
        wiped.addFilter(.blur(radius: 0.7))
        wiped.drawLayer { layer in
            for entry in drawn {
                for path in entry.paths {
                    layer.stroke(path, with: .color(Theme.paper), style: StrokeStyle(lineWidth: 3.4, lineCap: .round, lineJoin: .round))
                    layer.fill(path, with: .color(Theme.paper))
                }
            }
        }
        for entry in drawn {
            let colour = crayon.color(for: entry.mark, dark: dark).opacity(0.96)
            for path in entry.paths {
                context.fill(path, with: .color(colour))
            }
        }
        let spots = Pencil.numberSpots(for: labelled.map(\.mark), in: size)
        for (entry, spot) in zip(labelled, spots) {
            Pencil.badge(entry.number, at: spot, in: &context, ink: crayon.color(for: entry.mark, dark: dark), paper: Theme.paper.opacity(0.94))
        }
    }

    // MARK: The picture itself (before the sheet)

    /// The picture with the marks over it. The picture's great lines may
    /// run on past its edges (Mateusz 2026-11-02): there they go on in the
    /// page's ink over its background, room made above and below for them;
    /// at the sides they run to the screen's edge.
    private func picture(_ labelled: [Labelled]) -> some View {
        let room = overflow
        return box(aspect)
            .overlay {
                ArtImage(
                    ref: pictureRef,
                    fallback: .thumb(item.id),
                    placeholder: item.item.placeholderColor,
                    maxPixel: 1600
                )
            }
            .clipShape(RoundedRectangle(cornerRadius: Self.corner, style: .continuous))
            .overlay {
                ZStack {
                    Canvas { context, size in drawOutside(in: &context, size: size, room: room) }
                    Canvas { context, size in
                        let picture = Self.pictureRect(in: size, room: room)
                        context.clip(to: Path(roundedRect: picture, cornerRadius: Self.corner, style: .continuous))
                        context.translateBy(x: picture.minX, y: picture.minY)
                        draw(in: &context, size: picture.size, labelled: labelled)
                    }
                    .shadow(color: .black.opacity(0.3), radius: 1.5, y: 0.5)
                }
                .padding(EdgeInsets(top: -room.top, leading: -room.leading, bottom: -room.bottom, trailing: -room.trailing))
                .opacity(bare ? 0 : 1)
                .allowsHitTesting(false)
            }
            .contentShape(Rectangle())
            .onTapGesture {
                withAnimation(.easeInOut(duration: 0.25)) { bare.toggle() }
            }
            .sensoryFeedback(.selection, trigger: bare)
            .accessibilityAddTraits(.isButton)
            .accessibilityHint(bare ? "Pokazuje ślady analizy" : "Pokazuje sam obraz")
            .padding(.top, room.top)
            .padding(.bottom, room.bottom)
            .frame(maxWidth: .infinity)
    }

    private static let corner: CGFloat = 3

    /// The field's place in the picture of `size`: where the grid goes.
    private func fieldRect(in size: CGSize) -> CGRect {
        let field = take.shownField
        return CGRect(x: field.x * size.width, y: field.y * size.height, width: field.w * size.width, height: field.h * size.height)
    }

    /// Each stroke twice: a wider paper-coloured one under it, then the
    /// pencil; the grid fainter, the numbers on paper discs (`Pencil.badge`).
    private func draw(in context: inout GraphicsContext, size: CGSize, labelled: [Labelled]) {
        let field = fieldRect(in: size)
        for (index, line) in Pencil.grid(take.grid, in: field.size).enumerated() {
            let moved = line.map { CGPoint(x: $0.x + field.minX, y: $0.y + field.minY) }
            let path = Pencil.stroke(moved, width: 1, seed: 90 + index, start: 0.05, end: 0.05)
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

    /// How far the marks run past the picture's edges, in points: nothing
    /// before the picture's size is known.
    private var overflow: EdgeInsets {
        guard let width, width > 0, aspect > 0 else { return EdgeInsets() }
        return Pencil.overflow(of: take.marks, in: CGSize(width: width, height: width / aspect))
    }

    /// The picture's place in a canvas grown by `room` on each side.
    private static func pictureRect(in size: CGSize, room: EdgeInsets) -> CGRect {
        CGRect(
            x: room.leading, y: room.top,
            width: max(size.width - room.leading - room.trailing, 1),
            height: max(size.height - room.top - room.bottom, 1)
        )
    }

    /// The marks' parts beyond the picture: plain strokes in the page's ink
    /// (dark on the light page, light on the dark one), no paper edge.
    private func drawOutside(in context: inout GraphicsContext, size: CGSize, room: EdgeInsets) {
        guard room.top + room.bottom + room.leading + room.trailing > 0 else { return }
        let picture = Self.pictureRect(in: size, room: room)
        var outside = Path(CGRect(origin: .zero, size: size))
        outside.addRoundedRect(in: picture, cornerSize: CGSize(width: Self.corner, height: Self.corner), style: .continuous)
        context.clip(to: outside, style: FillStyle(eoFill: true))
        context.translateBy(x: picture.minX, y: picture.minY)
        for (index, mark) in take.marks.enumerated() {
            for path in Pencil.paths(for: mark, in: picture.size, seed: index * 7 + 1) {
                context.fill(path, with: .color(Theme.ink.opacity(0.85)))
            }
        }
    }

    // MARK: The notes

    /// The number on the same badge as on the picture, and beside it the
    /// title with its line under it: the line starts where the title does,
    /// not under the number. `ink`: the coloured pencil the mark is drawn
    /// in on the sheet (nil: the lead pencil on its paper disc).
    private func label(_ entry: Labelled, ink: Color?) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 5) {
            Canvas { context, size in
                let spot = CGPoint(x: size.width / 2, y: size.height / 2)
                if let ink {
                    Pencil.badge(entry.number, at: spot, in: &context, ink: ink, paper: .clear)
                } else {
                    Pencil.badge(entry.number, at: spot, in: &context)
                }
            }
            .frame(width: 22, height: 22)
            .shadow(color: .black.opacity(ink == nil ? 0.22 : 0), radius: 1.2, y: 0.5)
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

/// The two ends of a draughtsman's pencil. The one farther from the
/// picture's colours draws the marks; the other one what only answers
/// across the picture (a colour that returns), so it is not read as a line
/// that runs there.
enum Crayon: Hashable, Sendable {
    case red, blue

    var other: Crayon { self == .red ? .blue : .red }

    /// Deeper on the light page, lighter on the dark one.
    func rgb(dark: Bool) -> SIMD3<Double> {
        switch (self, dark) {
        case (.red, false): SIMD3<Double>(196, 36, 24) / 255
        case (.blue, false): SIMD3<Double>(18, 56, 168) / 255
        case (.red, true): SIMD3<Double>(255, 112, 92) / 255
        case (.blue, true): SIMD3<Double>(120, 168, 255) / 255
        }
    }

    func color(dark: Bool) -> Color {
        let rgb = rgb(dark: dark)
        return Color(.sRGB, red: rgb.x, green: rgb.y, blue: rgb.z)
    }

    /// The pencil a mark is drawn in when this one draws the marks.
    func color(for mark: DailyWork.Mark, dark: Bool) -> Color {
        (mark.shape == "echo" ? other : self).color(dark: dark)
    }

    /// The pencil that reads best over these colours (sRGB, 0…1): the one
    /// whose nearest fifth of them is farther from it, measured in Lab.
    static func pick(over colours: [SIMD3<Double>], dark: Bool) -> Crayon {
        func score(_ crayon: Crayon) -> Double {
            let own = lab(crayon.rgb(dark: dark))
            let distances = colours.map { colour -> Double in
                let d = lab(colour) - own
                return (d * d).sum().squareRoot()
            }.sorted()
            return distances.isEmpty ? 0 : distances[distances.count / 5]
        }
        return score(.blue) > score(.red) ? .blue : .red
    }

    /// The pencil for a sheet: picked over its colours, 32 by 32.
    static func pick(for image: UIImage, dark: Bool) -> Crayon {
        pick(over: colours(of: image), dark: dark)
    }

    /// The picture's colours, a small grid of them.
    static func colours(of image: UIImage, side: Int = 32) -> [SIMD3<Double>] {
        guard let source = image.cgImage, let space = CGColorSpace(name: CGColorSpace.sRGB) else { return [] }
        var bytes = [UInt8](repeating: 0, count: side * side * 4)
        let drawn = bytes.withUnsafeMutableBytes { buffer -> Bool in
            guard let context = CGContext(
                data: buffer.baseAddress, width: side, height: side, bitsPerComponent: 8, bytesPerRow: side * 4,
                space: space, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
            ) else { return false }
            context.interpolationQuality = .medium
            context.draw(source, in: CGRect(x: 0, y: 0, width: side, height: side))
            return true
        }
        guard drawn else { return [] }
        return (0..<(side * side)).map { index in
            SIMD3<Double>(Double(bytes[index * 4]), Double(bytes[index * 4 + 1]), Double(bytes[index * 4 + 2])) / 255
        }
    }

    /// CIE Lab (D65) of an sRGB colour.
    static func lab(_ rgb: SIMD3<Double>) -> SIMD3<Double> {
        func linear(_ value: Double) -> Double {
            value <= 0.04045 ? value / 12.92 : pow((value + 0.055) / 1.055, 2.4)
        }
        let (r, g, b) = (linear(rgb.x), linear(rgb.y), linear(rgb.z))
        let x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
        let y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
        let z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883
        func f(_ t: Double) -> Double { t > 0.008856 ? cbrt(t) : 7.787 * t + 16.0 / 116 }
        return SIMD3<Double>(116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z)))
    }
}

extension DailyWork.Mark {
    /// Where a remark about the mark points, as the server has it: a
    /// loop's centre, the middle of a rect or triangle, a spiral's eye, a
    /// vanishing point, a rhythm's middle beat, a path's middle point.
    var anchor: DailyWork.Spot {
        guard let first = points.first else { return DailyWork.Spot(x: 0.5, y: 0.5) }
        switch shape {
        case "loop", "rays": return first
        case "rhythm" where points.count >= 2:
            let start = 2 * (points.count / 4)
            let (a, b) = (points[start], points[start + 1])
            return DailyWork.Spot(x: (a.x + b.x) / 2, y: (a.y + b.y) / 2)
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
    /// How much heavier the coloured pencil of the study sheet is than the
    /// lead pencil on the picture (Mateusz 2026-11-11: "trochę mocniej dla
    /// większej czytelności").
    static let crayonWeight: CGFloat = 1.3
    /// How far the sheet's frame and grid run past the field's corners.
    static let reach: CGFloat = 6

    /// A mark's number: on a paper disc in a pencil ring drawn by hand, the
    /// same on the picture and in the legend under it (the ring's seed is
    /// the number, so number 2 has the same ring in both). On the study
    /// sheet the ring and the number are in the mark's coloured pencil, on
    /// a dab of the page's colour.
    static func badge(
        _ number: Int, at spot: CGPoint, in context: inout GraphicsContext,
        ink: Color = lead, paper: Color = paper
    ) {
        context.fill(Path(ellipseIn: CGRect(x: spot.x - 9.5, y: spot.y - 9.5, width: 19, height: 19)), with: .color(paper))
        context.fill(loop(center: spot, rx: 8.5, ry: 8, width: 1.4, seed: 40 + number), with: .color(ink))
        context.draw(
            Text("\(number)").font(.system(size: 10.5, weight: .bold)).foregroundStyle(ink),
            at: spot
        )
    }

    /// The radius of the small ring at each of an echo's places, as the
    /// server measures it (`ai/sketch.py` ECHO_RING).
    static func echoRing(in size: CGSize) -> CGFloat {
        max(size.width, size.height) * 0.03
    }

    /// The broken, slightly bowed line from each of an echo's rings to the
    /// next: its dashes, as the server draws them (`ai/sketch.py`).
    static func echoDashes(_ points: [CGPoint], in size: CGSize) -> [[CGPoint]] {
        let longer = max(size.width, size.height)
        let gap = echoRing(in: size) + longer * 0.005
        var found: [[CGPoint]] = []
        for (a, b) in zip(points, points.dropFirst()) {
            let length = hypot(b.x - a.x, b.y - a.y)
            let span = length - 2 * gap
            guard span > 0 else { continue }
            let (ux, uy) = ((b.x - a.x) / length, (b.y - a.y) / length)
            let bow = 0.07 * length
            let count = max(Int(span / (longer * 0.023)), 2)
            for k in 0..<count {
                found.append([CGFloat(k), CGFloat(k) + 0.275, CGFloat(k) + 0.55].map { step in
                    let d = gap + step / CGFloat(count) * span
                    let lift = bow * sin(.pi * d / length)
                    return CGPoint(x: a.x + ux * d + uy * lift, y: a.y + uy * d - ux * lift)
                })
            }
        }
        return found
    }

    /// A mark's strokes in a picture of `size`. `weight`: how much heavier
    /// than the lead pencil (the sheet's coloured pencil).
    static func paths(for mark: DailyWork.Mark, in size: CGSize, seed: Int, weight: CGFloat = 1) -> [Path] {
        paths(for: mark, in: size, seed: seed, pen: Pen(weight: weight))
    }

    /// How heavy the pencil is: every stroke's width times it.
    struct Pen {
        let weight: CGFloat
        func callAsFunction(_ width: CGFloat) -> CGFloat { width * weight }
    }

    private static func paths(for mark: DailyWork.Mark, in size: CGSize, seed: Int, pen: Pen) -> [Path] {
        let points = mark.points.map { CGPoint(x: $0.x * size.width, y: $0.y * size.height) }
        guard let first = points.first else { return [] }
        switch mark.shape {
        case "echo" where points.count >= 2:
            // Places that answer each other: a small ring at each and a
            // broken line between them, which nobody reads as an edge.
            let radius = echoRing(in: size)
            return points.enumerated().map { index, point in
                loop(center: point, rx: radius, ry: radius, width: pen(1.7), seed: seed + index)
            } + echoDashes(points, in: size).enumerated().map { index, dash in
                stroke(dash, width: pen(1.6), seed: seed + 10 + index, start: 0.2, end: 0.2)
            }
        case "loop":
            let corner = points.count > 1 ? points[1] : first
            let rx = max(abs(corner.x - first.x), 8)
            let ry = max(abs(corner.y - first.y), 8)
            return [loop(center: first, rx: rx, ry: ry, width: pen(2.4), seed: seed)]
        case "triangle" where points.count == 3:
            return (0..<3).map { side(points[$0], points[($0 + 1) % 3], width: pen(2), seed: seed + $0) }
        case "rect" where points.count == 2:
            let (a, b) = (points[0], points[1])
            let corners = [a, CGPoint(x: b.x, y: a.y), b, CGPoint(x: a.x, y: b.y)]
            return (0..<4).map { side(corners[$0], corners[($0 + 1) % 4], width: pen(1.6), seed: seed + $0) }
        case "underline" where points.count >= 2:
            return [stroke(wave(from: first, to: points[points.count - 1]), width: pen(2.2), seed: seed)]
        case "spiral" where points.count == 3:
            let line = spiral(start: points[0], through: points[1], eye: points[2])
            return line.count >= 2 ? [stroke(line, width: pen(2.2), seed: seed, start: 0.04, end: 0.3)] : []
        case "rhythm" where points.count >= 4:
            // A stroke along each repeated form, all parallel, no line between them.
            return beats(points).enumerated().map { index, beat in
                stroke(beat, width: pen(2.3), seed: seed + index, start: 0.14, end: 0.14)
            }
        case "rays" where points.count >= 3:
            // Each ray from its far end into the vanishing point, thinning as it goes.
            let eye = points[0]
            return points.dropFirst().enumerated().map { index, end in
                stroke([end, eye], width: pen(1.9), seed: seed + index, start: 0.05, end: 0.45)
            }
        case "motion" where points.count >= 2:
            // A sweeping arrow, two speed lines trailing beside its start.
            let line = smooth(points)
            let tip = line[line.count - 1]
            let from = line[max(0, line.count - 6)]
            return [stroke(points, width: pen(3), seed: seed, start: 0.02, end: 0.08)]
                + speedLines(line, gap: 6.5).enumerated().map { index, trail in
                    stroke(trail, width: pen(1.5), seed: seed + 3 + index, start: 0.3, end: 0.3)
                }
                + head(tip: tip, from: from, width: pen(2.6), size: 13)
        case "arrow" where points.count >= 2:
            let pieces = corners(points)
            let line = smooth(pieces[pieces.count - 1])
            let tip = line[line.count - 1]
            let from = line[max(0, line.count - 6)]
            return pieces.enumerated().map { stroke($1, width: pen(2.6), seed: seed + $0) }
                + head(tip: tip, from: from, width: pen(2.3), size: 10)
        default:
            // A wedge's or a zigzag's corners stay sharp: a curve through
            // them swung wide into a hairpin (Nighthawks, Mateusz 2026-11-02).
            return points.count >= 2
                ? corners(points).enumerated().map { stroke($1, width: pen(2.2), seed: seed + $0) } : []
        }
    }

    /// How far the marks drawn in a picture of `size` run past its edges,
    /// in points: the picture's great lines (a triangle's apex up in the
    /// sky, a vanishing point above it) reach at most half a side out, as
    /// the server lets them (`ai/daily.py` REACH).
    static func overflow(of marks: [DailyWork.Mark], in size: CGSize, weight: CGFloat = 1) -> EdgeInsets {
        var bounds = CGRect(origin: .zero, size: size)
        for (index, mark) in marks.enumerated() {
            for path in paths(for: mark, in: size, seed: index * 7 + 1, weight: weight) where !path.isEmpty {
                bounds = bounds.union(path.boundingRect)
            }
        }
        func out(_ beyond: CGFloat, _ side: CGFloat) -> CGFloat {
            beyond > 0.5 ? min(beyond + 2, side * 0.5 + 4).rounded(.up) : 0
        }
        return EdgeInsets(
            top: out(-bounds.minY, size.height),
            leading: out(-bounds.minX, size.width),
            bottom: out(bounds.maxY - size.height, size.height),
            trailing: out(bounds.maxX - size.width, size.width)
        )
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
        case "rhythm" where points.count >= 4:
            let first = beats(points)[0]
            let top = first.min { $0.y < $1.y }!
            spot = CGPoint(x: top.x, y: top.y - 13)
        case "rays" where points.count >= 2:
            let end = points[1]
            spot = CGPoint(x: end.x + 12, y: end.y + 12)
        case "motion":
            spot = CGPoint(x: first.x + 4, y: first.y - 15)
        case "echo":
            let radius = echoRing(in: size)
            spot = CGPoint(x: first.x + radius + 8, y: first.y - radius - 4)
        default:
            let middle = points[points.count / 2]
            spot = CGPoint(x: middle.x, y: middle.y - 15)
        }
        let margin: CGFloat = 11
        spot.x = min(max(spot.x, margin), max(size.width - margin, margin))
        spot.y = min(max(spot.y, margin), max(size.height - margin, margin))
        return spot
    }

    /// The marks' numbers on the study sheet: each at its own spot
    /// (`numberSpot`), moved a step aside where another number already
    /// sits, so two never lie on each other.
    static func numberSpots(for marks: [DailyWork.Mark], in size: CGSize) -> [CGPoint] {
        let margin: CGFloat = 11
        let step: CGFloat = 23
        var taken: [CGPoint] = []
        for mark in marks {
            let spot = numberSpot(for: mark, in: size)
            let tried = [(0, 0), (1, 0), (0, 1), (-1, 0), (0, -1)].map { dx, dy in
                CGPoint(
                    x: min(max(spot.x + CGFloat(dx) * step, margin), max(size.width - margin, margin)),
                    y: min(max(spot.y + CGFloat(dy) * step, margin), max(size.height - margin, margin))
                )
            }
            let free = tried.first { candidate in
                taken.allSatisfy { hypot($0.x - candidate.x, $0.y - candidate.y) > 21 }
            }
            taken.append(free ?? tried[0])
        }
        return taken
    }

    /// A line ruled in graphite from `a` to `b` and `over` past both ends,
    /// barely bent: the sheet's frame and its grid.
    static func ruled(_ a: CGPoint, _ b: CGPoint, over: CGFloat, width: CGFloat, seed: Int) -> Path {
        let length = max(hypot(b.x - a.x, b.y - a.y), 0.0001)
        let (ux, uy) = ((b.x - a.x) / length, (b.y - a.y) / length)
        let bend = CGFloat(Jitter.random(seed) - 0.5) * 0.8
        return stroke(
            [
                CGPoint(x: a.x - ux * over, y: a.y - uy * over),
                CGPoint(x: (a.x + b.x) / 2 - uy * bend, y: (a.y + b.y) / 2 + ux * bend),
                CGPoint(x: b.x + ux * over, y: b.y + uy * over),
            ],
            width: width, seed: seed, start: 0.03, end: 0.03
        )
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

    /// A rhythm's beats: the points in pairs (a repeated form's foot and
    /// top), each made a stroke through the pair's middle, all parallel to
    /// their common direction and a fifth longer than the form, as the
    /// server draws them (`ai/sketch.py`).
    static func beats(_ points: [CGPoint]) -> [[CGPoint]] {
        let pairs = stride(from: 0, to: points.count - 1, by: 2).map { (points[$0], points[$0 + 1]) }
        var ux: CGFloat = 0
        var uy: CGFloat = 0
        for (a, b) in pairs {
            var dx = b.x - a.x
            var dy = b.y - a.y
            if dy < 0 || (dy == 0 && dx < 0) { (dx, dy) = (-dx, -dy) }
            let length = max(hypot(dx, dy), 0.0001)
            ux += dx / length
            uy += dy / length
        }
        let norm = max(hypot(ux, uy), 0.0001)
        (ux, uy) = (ux / norm, uy / norm)
        return pairs.map { pair in
            let (a, b) = pair
            let middle = CGPoint(x: (a.x + b.x) / 2, y: (a.y + b.y) / 2)
            let half = hypot(b.x - a.x, b.y - a.y) / 2 * 1.2
            return [
                CGPoint(x: middle.x - ux * half, y: middle.y - uy * half),
                CGPoint(x: middle.x + ux * half, y: middle.y + uy * half),
            ]
        }
    }

    /// Two short strokes beside the start of a movement's path, one on each
    /// side, trailing it like the lines behind something moving fast.
    static func speedLines(_ path: [CGPoint], gap: CGFloat) -> [[CGPoint]] {
        let sides: [(side: CGFloat, from: Double, to: Double)] = [(1, 0, 0.42), (-1, 0.08, 0.34)]
        return sides.compactMap { entry -> [CGPoint]? in
            let side = entry.side
            let first = Int(Double(path.count) * entry.from)
            let last = min(max(Int(Double(path.count) * entry.to), first + 2), path.count)
            guard last - first >= 2 else { return nil }
            return (first..<last).map { index in
                let before = path[max(index - 1, 0)]
                let after = path[min(index + 1, path.count - 1)]
                let length = max(hypot(after.x - before.x, after.y - before.y), 0.0001)
                let normal = CGPoint(x: -(after.y - before.y) / length, y: (after.x - before.x) / length)
                return CGPoint(x: path[index].x + side * gap * normal.x, y: path[index].y + side * gap * normal.y)
            }
        }
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

    /// The points cut where the line turns sharply (more than `limit`
    /// degrees), each piece to be drawn on its own: a curve keeps its gentle
    /// bends, a wedge or a zigzag its corners. Neighbouring pieces share the
    /// corner point.
    static func corners(_ points: [CGPoint], limit: CGFloat = 35) -> [[CGPoint]] {
        guard points.count > 2 else { return [points] }
        var pieces: [[CGPoint]] = [[points[0]]]
        for index in 1..<points.count {
            pieces[pieces.count - 1].append(points[index])
            guard index < points.count - 1 else { break }
            let (a, b, c) = (points[index - 1], points[index], points[index + 1])
            let turn = abs(atan2(c.y - b.y, c.x - b.x) - atan2(b.y - a.y, b.x - a.x))
            let degrees = min(turn, 2 * .pi - turn) * 180 / .pi
            if degrees > limit { pieces.append([b]) }
        }
        return pieces
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
