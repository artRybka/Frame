import SwiftUI

/// "Rozmiar obrazu" (Mateusz 2026-11-02/03): the work at its real size on
/// the left, at the column's edge, and beside it for scale a sheet of A4
/// paper, white, with a shadow and a curled corner, "A4" printed on it in
/// thin dark grey; for a work over 1.3 m a man's dark silhouette, 180 cm,
/// his height pencilled beside him (Mateusz's drawing, 2026-11-03). One
/// scale, both standing on the work's bottom edge. A sheet lower than the pencilled
/// height stands a little past its line, under its figures; else past
/// them.
struct RealSizeDrawing: View {
    let work: RemoteItem
    /// Centimetres.
    let height: Double
    let width: Double

    /// What stands beside the work, in centimetres.
    enum Reference {
        case sheet
        case figure

        static let sheetSize = CGSize(width: 21, height: 29.7)
        /// The silhouette's own bounds (the asset is cropped to them), 180 cm.
        static let figureSize = CGSize(width: 180 * 427.79 / 1453.49, height: 180)
        /// Works higher than this get the figure.
        static let figureFrom = 130.0

        init(height: Double) {
            self = height > Self.figureFrom ? .figure : .sheet
        }

        var size: CGSize { self == .sheet ? Self.sheetSize : Self.figureSize }
        var spoken: String { self == .sheet ? "kartka A4" : "sylwetka człowieka, 180 cm" }
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
                "Rozmiar obrazu: \(Self.length(height)) wysokości, \(Self.length(width)) szerokości, obok \(Reference(height: height).spoken)"
            )
        )
    }

    private func drawing(width column: CGFloat) -> some View {
        let reference = Reference(height: height)
        let refW = reference.size.width, refH = reference.size.height
        let h = CGFloat(height), w = CGFloat(width)
        let gap: CGFloat = h >= 100 ? 66 : 54
        let room = Self.drawingHeight - Self.top - Self.bottom
        // The figure's pencilled height needs room on its right.
        let labelRoom: CGFloat = reference == .figure ? 56 : 0
        let scale = min(room / max(refH, h), (column - gap - labelRoom) / (refW + w))
        // Both stand on one line, the work's bottom edge (Mateusz 2026-11-03).
        let base = Self.top + room
        let picture = CGRect(x: 0, y: base - h * scale, width: w * scale, height: h * scale)
        let heightX = picture.maxX + 10
        let widthY = picture.maxY + 9
        let refTop = base - refH * scale
        // Under the pencilled height (its figures about the middle): close by.
        let close = refTop > picture.midY + 12
        let ref = CGRect(
            x: close ? heightX + 24 : picture.maxX + gap, y: refTop,
            width: refW * scale, height: refH * scale
        )
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

            switch reference {
            case .sheet:
                PaperSheet()
                    .frame(width: ref.width, height: ref.height)
                    .offset(x: ref.minX, y: ref.minY)
            case .figure:
                Image("ScaleFigure")
                    .renderingMode(.template)
                    .resizable()
                    .foregroundStyle(Theme.ink.opacity(0.88))
                    .frame(width: ref.width, height: ref.height)
                    .offset(x: ref.minX, y: ref.minY)
                Dimension(from: CGPoint(x: ref.maxX + 8, y: ref.minY), to: CGPoint(x: ref.maxX + 8, y: ref.maxY))
                    .stroke(pencil, style: StrokeStyle(lineWidth: 1.2, lineCap: .round))
                pencilled("180 cm")
                    .alignmentGuide(.leading) { _ in -(ref.maxX + 14) }
                    .alignmentGuide(.top) { d in -(ref.midY - d.height / 2) }
            }

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

/// White paper, a little dimmed in the dark style.
private enum Paper {
    static let light = Color(light: 0xFFFFFF, dark: 0xECE8E1)
    static let shade = Color(light: 0xEFEBE4, dark: 0xD6D1C8)
    static let curl = Color(light: 0xE2DCD2, dark: 0xC9C3B9)
    /// What is printed on it: thin dark grey (Mateusz 2026-11-03).
    static let print = Color(light: 0x7D776F, dark: 0x7D776F)
    static let fill = LinearGradient(colors: [light, shade], startPoint: .topLeading, endPoint: .bottomTrailing)
}

/// A sheet of paper, upright, its lower right corner curled up a little.
private struct PaperSheet: View {
    var body: some View {
        GeometryReader { geometry in
            let size = geometry.size
            let corner = min(size.width, size.height) * 0.12
            ZStack(alignment: .topLeading) {
                SheetOutline(corner: corner)
                    .fill(Paper.fill)
                    .overlay(SheetOutline(corner: corner).stroke(.black.opacity(0.1), lineWidth: 0.5))
                    .shadow(color: .black.opacity(0.22), radius: 3, y: 2)
                Curl(corner: corner)
                    .fill(LinearGradient(colors: [Paper.curl, Paper.light], startPoint: .topLeading, endPoint: .bottomTrailing))
                    .overlay(Curl(corner: corner).stroke(.black.opacity(0.08), lineWidth: 0.5))
                if size.width >= 14 {
                    Text("A4")
                        .font(.system(size: size.width * 0.3, weight: .light))
                        .foregroundStyle(Paper.print)
                        .frame(width: size.width, height: size.height)
                }
            }
        }
    }
}

private struct SheetOutline: Shape {
    let corner: CGFloat

    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: rect.origin)
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY - corner))
        path.addLine(to: CGPoint(x: rect.maxX - corner, y: rect.maxY))
        path.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
        path.closeSubpath()
        return path
    }
}

/// The curled corner: the paper's back, folded over.
private struct Curl: Shape {
    let corner: CGFloat

    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.maxX, y: rect.maxY - corner))
        path.addLine(to: CGPoint(x: rect.maxX - corner, y: rect.maxY - corner))
        path.addLine(to: CGPoint(x: rect.maxX - corner, y: rect.maxY))
        path.closeSubpath()
        return path
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
