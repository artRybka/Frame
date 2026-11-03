import SwiftUI

/// "Rozmiar obrazu" (Mateusz 2026-11-02/03): the work at its real size on
/// the left, at the column's edge, and a sheet of A4 paper on its right for
/// scale, "A4" printed on it in light grey; one scale, both standing on the
/// work's bottom edge. The
/// work's height and width are pencilled on the drawing; nothing else: no
/// person, no sentence, no scale.
struct RealSizeDrawing: View {
    let work: RemoteItem
    /// Centimetres.
    let height: Double
    let width: Double

    /// A sheet of A4, upright, in centimetres.
    static let sheetWidth = 21.0
    static let sheetHeight = 29.7

    private static let drawingHeight: CGFloat = 230
    private static let top: CGFloat = 10
    private static let bottom: CGFloat = 34

    var body: some View {
        GeometryReader { geometry in
            drawing(width: geometry.size.width)
        }
        .frame(height: Self.drawingHeight)
        .accessibilityElement()
        .accessibilityLabel(Text("Rozmiar obrazu: \(Self.length(height)) wysokości, \(Self.length(width)) szerokości, obok kartka A4"))
    }

    private func drawing(width column: CGFloat) -> some View {
        let sheetW = CGFloat(Self.sheetWidth), sheetH = CGFloat(Self.sheetHeight)
        let h = CGFloat(height), w = CGFloat(width)
        let gap: CGFloat = h >= 100 ? 66 : 54
        let room = Self.drawingHeight - Self.top - Self.bottom
        let scale = min(room / max(sheetH, h), (column - gap) / (sheetW + w))
        // Both stand on one line, the work's bottom edge (Mateusz 2026-11-03).
        let base = Self.top + room
        let picture = CGRect(x: 0, y: base - h * scale, width: w * scale, height: h * scale)
        let sheet = CGRect(
            x: picture.maxX + gap, y: base - sheetH * scale,
            width: sheetW * scale, height: sheetH * scale
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

            Rectangle()
                .fill(Self.paper)
                .overlay(Rectangle().strokeBorder(Theme.mouldingEdge, lineWidth: 0.6))
                .overlay {
                    if sheet.width >= 14 {
                        Text("A4")
                            .font(.system(size: sheet.width * 0.3, weight: .semibold))
                            .foregroundStyle(Self.print)
                    }
                }
                .shadow(color: .black.opacity(0.12), radius: 3, y: 2)
                .frame(width: sheet.width, height: sheet.height)
                .offset(x: sheet.minX, y: sheet.minY)

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

    /// White paper, a little dimmed in the dark style, and its light grey print.
    private static let paper = Color(light: 0xFFFFFF, dark: 0xE9E6E0)
    private static let print = Color(light: 0xD6D2CB, dark: 0xBDB8AF)

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
