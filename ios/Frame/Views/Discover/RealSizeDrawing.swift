import SwiftUI

/// "Rozmiar obrazu" (Mateusz 2026-11-02/03): the work at its real size on
/// the left, at the column's edge, and beside it for scale a sheet of A4
/// paper, white, with a shadow and a curled corner, "A4" pencilled under
/// it; for a work over 1.3 m a standing figure cut out of the same paper,
/// 170 cm. One scale, both standing on the work's bottom edge. A sheet lower
/// than the pencilled height stands close, just past its line; else past
/// the height's figures.
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
        static let figureSize = CGSize(width: 46, height: 170)
        /// Works higher than this get the figure.
        static let figureFrom = 130.0

        init(height: Double) {
            self = height > Self.figureFrom ? .figure : .sheet
        }

        var size: CGSize { self == .sheet ? Self.sheetSize : Self.figureSize }
        var caption: String { self == .sheet ? "A4" : "170 cm" }
        var spoken: String { self == .sheet ? "kartka A4" : "postać, 170 cm" }
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
        let scale = min(room / max(refH, h), (column - gap) / (refW + w))
        // Both stand on one line, the work's bottom edge (Mateusz 2026-11-03).
        let base = Self.top + room
        let picture = CGRect(x: 0, y: base - h * scale, width: w * scale, height: h * scale)
        let heightX = picture.maxX + 10
        let widthY = picture.maxY + 9
        let refTop = base - refH * scale
        // Under the pencilled height (its figures about the middle): close by.
        let close = refTop > picture.midY + 12
        let ref = CGRect(
            x: close ? heightX + 9 : picture.maxX + gap, y: refTop,
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

            Group {
                switch reference {
                case .sheet: PaperSheet()
                case .figure: PaperFigure()
                }
            }
            .frame(width: ref.width, height: ref.height)
            .offset(x: ref.minX, y: ref.minY)

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
            Text(reference.caption)
                .font(.hand(15))
                .foregroundStyle(Theme.inkSoft)
                .fixedSize()
                .alignmentGuide(.leading) { d in -min(ref.midX - d.width / 2, column - d.width) }
                .alignmentGuide(.top) { _ in -(widthY + 7) }
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

/// A standing figure cut out of the same paper: no face, no detail.
private struct PaperFigure: View {
    var body: some View {
        FigureOutline()
            .fill(Paper.fill)
            .overlay(FigureOutline().stroke(.black.opacity(0.12), lineWidth: 0.5))
            .shadow(color: .black.opacity(0.22), radius: 3, y: 2)
    }
}

/// A person standing, arms down, drawn in a 46 × 170 box (centimetres).
private struct FigureOutline: Shape {
    func path(in rect: CGRect) -> Path {
        let sx = rect.width / 46, sy = rect.height / 170
        func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
            CGPoint(x: rect.minX + x * sx, y: rect.minY + y * sy)
        }
        var path = Path()
        path.move(to: p(23, 0))
        path.addCurve(to: p(32.5, 11), control1: p(29, 0), control2: p(32.5, 4.5))
        path.addCurve(to: p(26.5, 22.8), control1: p(32.5, 17), control2: p(29.5, 21.5))
        path.addLine(to: p(26.5, 26))
        path.addCurve(to: p(40.5, 31.5), control1: p(33, 27), control2: p(38.5, 28.5))
        path.addCurve(to: p(43.5, 62), control1: p(42.5, 35), control2: p(43, 48))
        path.addCurve(to: p(44, 94), control1: p(44, 75), control2: p(44.5, 88))
        path.addCurve(to: p(40, 94), control1: p(43.5, 97), control2: p(40.5, 97))
        path.addLine(to: p(37.5, 64))
        path.addLine(to: p(35.5, 60))
        path.addLine(to: p(35, 96))
        path.addLine(to: p(34.8, 166))
        path.addCurve(to: p(30.5, 170), control1: p(34.8, 169), control2: p(33, 170))
        path.addLine(to: p(26, 170))
        path.addCurve(to: p(24.6, 167.5), control1: p(25, 170), control2: p(24.6, 169))
        path.addLine(to: p(24, 104))
        path.addLine(to: p(22, 104))
        path.addLine(to: p(21.4, 167.5))
        path.addCurve(to: p(20, 170), control1: p(21.4, 169), control2: p(21, 170))
        path.addLine(to: p(15.5, 170))
        path.addCurve(to: p(11.2, 166), control1: p(13, 170), control2: p(11.2, 169))
        path.addLine(to: p(11, 96))
        path.addLine(to: p(10.5, 60))
        path.addLine(to: p(8.5, 64))
        path.addLine(to: p(6, 94))
        path.addCurve(to: p(2, 94), control1: p(5.5, 97), control2: p(2.5, 97))
        path.addCurve(to: p(2.5, 62), control1: p(1.5, 88), control2: p(2, 75))
        path.addCurve(to: p(5.5, 31.5), control1: p(3, 48), control2: p(3.5, 35))
        path.addCurve(to: p(19.5, 26), control1: p(7.5, 28.5), control2: p(13, 27))
        path.addLine(to: p(19.5, 22.8))
        path.addCurve(to: p(13.5, 11), control1: p(16.5, 21.5), control2: p(13.5, 17))
        path.addCurve(to: p(23, 0), control1: p(13.5, 4.5), control2: p(17, 0))
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
