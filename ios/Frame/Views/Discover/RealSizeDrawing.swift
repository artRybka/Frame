import SwiftUI

/// "Rozmiar obrazu" (Mateusz 2026-11-02/03): the work at its real size on
/// the left, at the column's edge, and a carpenter's folding rule standing
/// on its right for scale (20 cm, 50 cm, 1 m or 2 m, the longest no more
/// than a tenth above the work's height), its length pencilled under it;
/// one scale, both standing on the work's bottom edge. The
/// work's height and width are pencilled on the drawing; nothing else: no
/// person, no sentence, no scale.
struct RealSizeDrawing: View {
    let work: RemoteItem
    /// Centimetres.
    let height: Double
    let width: Double

    /// The rule's lengths, in centimetres, and its width.
    static let ruleLengths: [Double] = [20, 50, 100, 200]
    static let ruleWidth = 1.7

    /// The rule for a work ``height`` centimetres high.
    static func ruleLength(for height: Double) -> Double {
        ruleLengths.last { $0 <= max(height * 1.1, ruleLengths[0]) } ?? ruleLengths[0]
    }

    private static let drawingHeight: CGFloat = 230
    private static let top: CGFloat = 10
    private static let bottom: CGFloat = 34

    var body: some View {
        GeometryReader { geometry in
            drawing(width: geometry.size.width)
        }
        .frame(height: Self.drawingHeight)
        .accessibilityElement()
        .accessibilityLabel(Text("Rozmiar obrazu: \(Self.length(height)) wysokości, \(Self.length(width)) szerokości, obok miarka \(Self.length(Self.ruleLength(for: height)))"))
    }

    private func drawing(width column: CGFloat) -> some View {
        let rule = CGFloat(Self.ruleLength(for: height))
        let h = CGFloat(height), w = CGFloat(width)
        let gap: CGFloat = h >= 100 ? 66 : 54
        let room = Self.drawingHeight - Self.top - Self.bottom
        let scale = min(room / max(rule, h), (column - gap - 9) / w)
        // Both stand on one line, the work's bottom edge (Mateusz 2026-11-03).
        let base = Self.top + room
        let picture = CGRect(x: 0, y: base - h * scale, width: w * scale, height: h * scale)
        let ruler = CGRect(
            x: picture.maxX + gap, y: base - rule * scale,
            width: max(CGFloat(Self.ruleWidth) * scale, 9), height: rule * scale
        )
        let pencil = Theme.ink.opacity(0.8)
        let heightX = picture.maxX + 10
        let widthY = picture.maxY + 9
        return ZStack(alignment: .topLeading) {
            // Holds the drawing's corner at (0, 0) for the parts placed by offset.
            Color.clear.frame(width: column, height: Self.drawingHeight)
            ArtImage(
                ref: work.thumb,
                fallback: work.thumbFallback,
                placeholder: work.item.placeholderColor,
                maxPixel: 700
            )
            .frame(width: picture.width, height: picture.height)
            .clipped()
            .shadow(color: .black.opacity(0.22), radius: 5, y: 5)
            .offset(x: picture.minX, y: picture.minY)

            FoldingRule(length: Double(rule))
                .frame(width: ruler.width, height: ruler.height)
                .shadow(color: .black.opacity(0.2), radius: 1.5, y: 1)
                .offset(x: ruler.minX, y: ruler.minY)
            Text(Self.length(Double(rule)))
                .font(.hand(15))
                .foregroundStyle(Theme.inkSoft)
                .fixedSize()
                .alignmentGuide(.leading) { d in -min(ruler.midX - d.width / 2, column - d.width) }
                .alignmentGuide(.top) { _ in -(widthY + 7) }

            Dimension(from: CGPoint(x: heightX, y: picture.minY), to: CGPoint(x: heightX, y: picture.maxY))
                .stroke(pencil, style: StrokeStyle(lineWidth: 1.2, lineCap: .round))
            Dimension(from: CGPoint(x: picture.minX, y: widthY), to: CGPoint(x: picture.maxX, y: widthY))
                .stroke(pencil, style: StrokeStyle(lineWidth: 1.2, lineCap: .round))
            pencilled(height >= 100 ? Self.length(height) : Self.number(height))
                .alignmentGuide(.leading) { _ in -(heightX + 6) }
                .alignmentGuide(.top) { d in -(picture.midY - d.height / 2) }
            pencilled(Self.length(width))
                .alignmentGuide(.leading) { d in -(picture.midX - d.width / 2) }
                .alignmentGuide(.top) { _ in -(widthY + 6) }
        }
        .frame(width: column, height: Self.drawingHeight, alignment: .topLeading)
    }

    private func pencilled(_ text: String) -> some View {
        Text(text)
            .font(.hand(17))
            .foregroundStyle(Theme.ink)
            .fixedSize()
    }

    /// "45,7".
    static func number(_ value: Double) -> String {
        let text = String(format: "%.1f", value).replacingOccurrences(of: ".", with: ",")
        return text.hasSuffix(",0") ? String(text.dropLast(2)) : text
    }

    /// "40,6 cm", "1,14 m".
    static func length(_ cm: Double) -> String {
        guard cm >= 100 else { return "\(number(cm)) cm" }
        var text = String(format: "%.2f", cm / 100).replacingOccurrences(of: ".", with: ",")
        while text.hasSuffix("0") { text.removeLast() }
        if text.hasSuffix(",") { text.removeLast() }
        return "\(text) m"
    }
}

/// A carpenter's folding rule, unfolded and standing: yellow, black marks
/// every centimetre (every 5 or 10 when they would crowd), a darker joint
/// every 20 cm, the number of each 10 cm when there is room for it.
private struct FoldingRule: View {
    /// Centimetres.
    let length: Double

    private static let yellow = Color(red: 0.91, green: 0.78, blue: 0.29)
    private static let edge = Color(red: 0.72, green: 0.59, blue: 0.16)
    private static let joint = Color(red: 0.61, green: 0.49, blue: 0.13)
    private static let mark = Color(red: 0.11, green: 0.11, blue: 0.09)

    var body: some View {
        Canvas { context, size in
            let shape = Path(roundedRect: CGRect(origin: .zero, size: size), cornerRadius: min(size.width * 0.12, 1.2))
            context.fill(shape, with: .color(Self.yellow))
            context.stroke(shape, with: .color(Self.edge), lineWidth: 0.5)
            let perCm = size.height / length
            let step = perCm >= 2.2 ? 1 : perCm * 5 >= 2.2 ? 5 : 10
            let numbers = perCm * 10 >= 9 && size.width >= 7
            var cm = step
            while Double(cm) < length {
                let y = size.height - CGFloat(cm) * perCm
                let tenth = cm % 10 == 0, fifth = cm % 5 == 0
                let tick = size.width * (tenth ? 0.55 : fifth ? 0.4 : 0.25)
                var line = Path()
                line.move(to: CGPoint(x: 0, y: y))
                line.addLine(to: CGPoint(x: tick, y: y))
                context.stroke(line, with: .color(Self.mark), lineWidth: tenth ? 0.8 : 0.5)
                if cm % 20 == 0 {
                    var joint = Path()
                    joint.move(to: CGPoint(x: 0, y: y))
                    joint.addLine(to: CGPoint(x: size.width, y: y))
                    context.stroke(joint, with: .color(Self.joint), lineWidth: 0.6)
                }
                if tenth && numbers {
                    context.draw(
                        Text(String(cm))
                            .font(.system(size: min(7, size.width * 0.55), weight: .semibold))
                            .foregroundStyle(Self.mark),
                        at: CGPoint(x: size.width - 1, y: y),
                        anchor: .trailing
                    )
                }
                cm += step
            }
        }
    }
}

/// A pencil dimension line with a short tick at each end.
private struct Dimension: Shape {
    let from: CGPoint
    let to: CGPoint

    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: from)
        path.addLine(to: to)
        let tick: CGFloat = 4
        let vertical = from.x == to.x
        for end in [from, to] {
            if vertical {
                path.move(to: CGPoint(x: end.x - tick, y: end.y))
                path.addLine(to: CGPoint(x: end.x + tick, y: end.y))
            } else {
                path.move(to: CGPoint(x: end.x, y: end.y - tick))
                path.addLine(to: CGPoint(x: end.x, y: end.y + tick))
            }
        }
        return path
    }
}
