import SwiftUI

/// "Rozmiar obrazu" (Mateusz 2026-11-02/03): the work at its real size on
/// the left, at the column's edge, and beside it for scale always the same
/// man, the dark silhouette Mateusz chose, 180 cm, his height pencilled
/// beside him. One scale. A smaller work hangs as in a museum: his eye line
/// (168 cm) crosses it two thirds of the way up; a work that would then
/// hang lower than 60 cm above the floor stands on the floor, the line of
/// his right foot. No floor line, no eye line: the work, the man and the
/// measures only.
struct RealSizeDrawing: View {
    let work: RemoteItem
    /// Centimetres.
    let height: Double
    let width: Double

    /// The silhouette (the asset is cropped to its outline, 1453.49 units
    /// high): 180 cm from the top of his head to the sole of his right foot,
    /// the one further back, 1421.2 units down (Mateusz 2026-11-03); his left
    /// foot, nearer, reaches a little below the floor he stands on.
    static let manUnits = 1421.2
    static let manHeight = 180.0
    static let manWidth = 180 * 427.79 / manUnits
    /// The asset's whole height over the 180 cm he is measured to.
    static let manOverhang = 1453.49 / manUnits
    /// His eyes, above the floor.
    static let eyeHeight = 168.0
    /// How high above the floor a hanging work's bottom edge must stay.
    static let clearance = 60.0

    /// How high above the floor the work's bottom edge is: two thirds of it
    /// under his eye line, else on the floor.
    static func lift(for height: Double) -> Double {
        let hung = eyeHeight - height * 2 / 3
        return hung >= clearance ? hung : 0
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
        .accessibilityLabel(
            Text(
                "Rozmiar obrazu: \(Self.length(height)) wysokości, \(Self.length(width)) szerokości, obok sylwetka człowieka, 180 cm"
            )
        )
    }

    private func drawing(width column: CGFloat) -> some View {
        let h = CGFloat(height), w = CGFloat(width)
        let lift = CGFloat(Self.lift(for: height))
        let manH = CGFloat(Self.manHeight), manW = CGFloat(Self.manWidth)
        let tallest = max(manH, lift + h)
        let gap: CGFloat = 66
        // His pencilled height needs room on his right.
        let labelRoom: CGFloat = 56
        let room = Self.drawingHeight - Self.top - Self.bottom
        let scale = min(room / tallest, (column - gap - labelRoom) / (w + manW))
        let floor = Self.top + tallest * scale
        let picture = CGRect(x: 0, y: floor - (lift + h) * scale, width: w * scale, height: h * scale)
        let man = CGRect(x: picture.maxX + gap, y: floor - manH * scale, width: manW * scale, height: manH * scale)
        let heightX = picture.maxX + 10
        let widthY = picture.maxY + 9
        let pencil = Theme.ink.opacity(0.8)
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

            Image("ScaleFigure")
                .renderingMode(.template)
                .resizable()
                .foregroundStyle(Theme.ink.opacity(0.88))
                .frame(width: man.width, height: man.height * Self.manOverhang)
                .offset(x: man.minX, y: man.minY)
            Dimension(from: CGPoint(x: man.maxX + 8, y: man.minY), to: CGPoint(x: man.maxX + 8, y: man.maxY))
                .stroke(pencil, style: StrokeStyle(lineWidth: 1.2, lineCap: .round))
            pencilled("180 cm")
                .alignmentGuide(.leading) { _ in -(man.maxX + 14) }
                .alignmentGuide(.top) { d in -(man.midY - d.height / 2) }

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
