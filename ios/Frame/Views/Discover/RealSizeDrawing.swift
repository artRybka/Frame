import SwiftUI

/// "Prawdziwy rozmiar" (Mateusz 2026-11-02/03): the work at its real size
/// on the left, at the column's edge, and the frame, empty, on its right
/// for scale; one scale, centres level, as if hung side by side. The work's
/// height and width are pencilled on the drawing; nothing else: no person,
/// no sentence, no scale.
struct RealSizeDrawing: View {
    let work: RemoteItem
    /// Centimetres.
    let height: Double
    let width: Double
    /// As the frame hangs.
    let portrait: Bool

    /// The EM32DX: its screen and the white moulding round it, in centimetres.
    static let screenLong = 70.8
    static let screenShort = 39.8
    static let moulding = 2.2

    private static let drawingHeight: CGFloat = 236
    private static let top: CGFloat = 10
    private static let bottom: CGFloat = 40

    var body: some View {
        GeometryReader { geometry in
            drawing(width: geometry.size.width)
        }
        .frame(height: Self.drawingHeight)
        .accessibilityElement()
        .accessibilityLabel(Text("Prawdziwy rozmiar: \(Self.length(height)) wysokości, \(Self.length(width)) szerokości, obok Twoja ramka"))
    }

    private var frameSize: CGSize {
        let screen = portrait
            ? CGSize(width: Self.screenShort, height: Self.screenLong)
            : CGSize(width: Self.screenLong, height: Self.screenShort)
        return CGSize(width: screen.width + 2 * Self.moulding, height: screen.height + 2 * Self.moulding)
    }

    private func drawing(width column: CGFloat) -> some View {
        let outer = frameSize
        let h = CGFloat(height), w = CGFloat(width)
        let gap: CGFloat = h >= 100 ? 66 : 54
        let room = Self.drawingHeight - Self.top - Self.bottom
        let scale = min(room / max(outer.height, h), (column - gap) / (outer.width + w))
        let middle = Self.top + room / 2
        let picture = CGRect(x: 0, y: middle - h * scale / 2, width: w * scale, height: h * scale)
        let frame = CGRect(
            x: picture.maxX + gap, y: middle - outer.height * scale / 2,
            width: outer.width * scale, height: outer.height * scale
        )
        let rim = Self.moulding * scale
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
            .overlay(Rectangle().strokeBorder(.black.opacity(0.35), lineWidth: 0.8))
            .shadow(color: .black.opacity(0.22), radius: 5, y: 5)
            .offset(x: picture.minX, y: picture.minY)

            Rectangle()
                .fill(Theme.moulding)
                .overlay(Rectangle().strokeBorder(Theme.mouldingEdge, lineWidth: 0.6))
                .shadow(color: .black.opacity(0.22), radius: 5, y: 5)
                .frame(width: frame.width, height: frame.height)
                .offset(x: frame.minX, y: frame.minY)
            Rectangle()
                .fill(Self.screen)
                .overlay(Rectangle().strokeBorder(.black.opacity(0.08), lineWidth: 0.5))
                .frame(width: max(frame.width - 2 * rim, 0), height: max(frame.height - 2 * rim, 0))
                .offset(x: frame.minX + rim, y: frame.minY + rim)

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
            pencilled("Twoja ramka")
                .opacity(0.75)
                .alignmentGuide(.leading) { d in -(min(frame.midX - d.width / 2, column - d.width)) }
                .alignmentGuide(.top) { _ in -(frame.maxY + 6) }
        }
        .frame(width: column, height: Self.drawingHeight, alignment: .topLeading)
    }

    private func pencilled(_ text: String) -> some View {
        Text(text)
            .font(.hand(17))
            .foregroundStyle(Theme.ink)
            .fixedSize()
    }

    /// The frame's screen, off: a light grey, darker than its moulding.
    private static let screen = Color(light: 0xE9E6E0, dark: 0xCFCAC1)

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
