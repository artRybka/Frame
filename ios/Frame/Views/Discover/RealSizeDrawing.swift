import SwiftUI

/// "Rozmiar obrazu" (Mateusz 2026-11-02/03): the work at its real size on
/// the left, at the column's edge, and beside it for scale always the same
/// man, the dark silhouette Mateusz chose, 180 cm, his height pencilled
/// beside him. One scale. A smaller work hangs as in a museum: his eye line
/// (168 cm) crosses it two thirds of the way up; a work that would then
/// hang lower than 60 cm above the floor stands on the floor, the line of
/// his right foot. No floor line, no eye line: the work, the man and the
/// measures only.
///
/// The scale (Mateusz 2026-11-03 15:29, "przy małych dziełach pokazuj
/// znacznie większy obraz i postać"; 19:36, "albo ucięta w pasie, albo
/// pełna od stóp"): the whole man and the work in the drawing's 250 points
/// as a rule; when that leaves the work's longer side under 120 points,
/// only his bust, cut just under his jacket on a pencil line across the
/// screen, his height by a tick at his head, with the work as large as
/// that and the column's width allow. Never anything in between. The
/// drawing is as tall as what is on it, with no room left under it.
struct RealSizeDrawing: View {
    let work: RemoteItem
    /// Centimetres.
    let height: Double
    let width: Double
    /// The page's column, the drawing's width.
    let column: CGFloat

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

    /// Where everything goes, in points from the drawing's top left corner.
    struct Plan: Equatable {
        /// Points per centimetre.
        var scale: CGFloat
        var picture: CGRect
        /// The man's 180 cm, head to the sole of his right foot.
        var man: CGRect
        /// He is taller than the drawing: cut off at `cut`.
        var cropped: Bool
        /// Where he is cut off, when he is.
        var cut: CGFloat
        /// The drawing's height.
        var height: CGFloat
    }

    /// The drawing's height for his whole figure, or its window when he is
    /// cropped.
    static let room: CGFloat = 250
    private static let top: CGFloat = 10
    /// The work's longer side, at least, when the width allows.
    static let smallest: CGFloat = 120
    /// Where he is cut as a bust: just under his jacket, 750 of the
    /// asset's units down (Mateusz 2026-11-03 19:36: cut at the waist,
    /// under the jacket, or whole from his feet, nothing in between).
    static let waist = 180 - 180 * 750 / manUnits
    /// The least room between the work's foot and the cut, for its width.
    private static let underRoom: CGFloat = 32
    private static let gap: CGFloat = 66
    /// How far the line he is cut on runs past the column: to the screen's
    /// edges, where the scroll view clips it.
    private static let overrun: CGFloat = 2000
    /// Just right of his cap, across his width, where the tick by his head
    /// starts.
    private static let headRight: CGFloat = 0.66
    /// His pencilled height needs room on his right.
    private static let labelRoom: CGFloat = 56
    /// The width's line and its pencilled number under the work.
    private static let widthLabel: CGFloat = 9 + 6 + 24

    static func plan(height: Double, width: Double, column: CGFloat) -> Plan {
        let h = CGFloat(height), w = CGFloat(width)
        let lift = CGFloat(Self.lift(for: height))
        let manH = CGFloat(manHeight), manW = CGFloat(manWidth)
        let tallest = max(manH, lift + h)
        let across = max(0.01, (column - gap - labelRoom) / (w + manW))
        let whole = min(room / tallest, across)
        let wanted = smallest / max(h, w, 1)
        // A bust when the whole man leaves the work too small, the work
        // hangs above his waist with room for its width under it, and the
        // bust brings it noticeably closer.
        let waist = CGFloat(Self.waist)
        let bust = min(across, room / (tallest - waist))
        let cropped = wanted > whole && bust > whole * 1.15 && (lift - waist) * bust >= underRoom
        let scale = cropped ? bust : whole
        // Centimetres above the floor to points down from the drawing's top.
        func y(_ cm: CGFloat) -> CGFloat { top + (tallest - cm) * scale }
        let picture = CGRect(x: 0, y: y(lift + h), width: w * scale, height: h * scale)
        let man = CGRect(x: picture.maxX + gap, y: y(manH), width: manW * scale, height: manH * scale)
        let underWork = picture.maxY + widthLabel
        let feet = y(0) + manH * (CGFloat(manOverhang) - 1) * scale
        let cut = y(waist)
        let height = cropped ? max(cut + 1, underWork) : max(feet, underWork)
        return Plan(scale: scale, picture: picture, man: man, cropped: cropped, cut: cut, height: ceil(height))
    }

    var body: some View {
        let plan = Self.plan(height: height, width: width, column: column)
        drawing(plan)
            .frame(width: column, height: plan.height, alignment: .topLeading)
            .accessibilityElement()
            .accessibilityLabel(
                Text(
                    "Rozmiar obrazu: \(Self.length(height)) wysokości, \(Self.length(width)) szerokości, obok sylwetka człowieka, 180 cm"
                )
            )
    }

    private func drawing(_ plan: Plan) -> some View {
        let picture = plan.picture, man = plan.man
        let heightX = picture.maxX + 10
        let widthY = picture.maxY + 9
        let pencil = Theme.ink.opacity(0.8)
        return ZStack(alignment: .topLeading) {
            // Holds the drawing's corner at (0, 0) for the parts placed by offset.
            Color.clear.frame(width: column, height: plan.height)
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

            if plan.cropped {
                // Cut straight across: he ends on a pencil line running the
                // screen's whole width, and his height is written by a short
                // tick at the top of his head (Mateusz 2026-11-03 16:18, "C";
                // 19:05, his sketch).
                let cut = plan.cut
                ZStack(alignment: .topLeading) {
                    Color.clear.frame(width: column, height: cut)
                    figure(man)
                }
                .frame(width: column, height: cut, alignment: .topLeading)
                .clipped()
                Path { path in
                    path.move(to: CGPoint(x: -Self.overrun, y: cut))
                    path.addLine(to: CGPoint(x: column + Self.overrun, y: cut))
                }
                .stroke(pencil, style: StrokeStyle(lineWidth: 1.2, lineCap: .round))
                .frame(width: column, height: plan.height)
                let tick = man.minX + Self.headRight * man.width
                Path { path in
                    path.move(to: CGPoint(x: tick, y: man.minY))
                    path.addLine(to: CGPoint(x: tick + 30, y: man.minY))
                }
                .stroke(pencil, style: StrokeStyle(lineWidth: 1.2, lineCap: .round))
                .frame(width: column, height: plan.height)
                pencilled("180 cm")
                    .alignmentGuide(.leading) { _ in -(tick + 36) }
                    .alignmentGuide(.top) { d in -(man.minY - d.height / 2) }
            } else {
                figure(man)
                Dimension(from: CGPoint(x: man.maxX + 8, y: man.minY), to: CGPoint(x: man.maxX + 8, y: man.maxY))
                    .stroke(pencil, style: StrokeStyle(lineWidth: 1.2, lineCap: .round))
                pencilled("180 cm")
                    .alignmentGuide(.leading) { _ in -(man.maxX + 14) }
                    .alignmentGuide(.top) { d in -(man.midY - d.height / 2) }
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
    }

    /// The silhouette at `man`, his 180 cm.
    private func figure(_ man: CGRect) -> some View {
        Image("ScaleFigure")
            .renderingMode(.template)
            .resizable()
            .foregroundStyle(Theme.ink.opacity(0.88))
            .frame(width: man.width, height: man.height * Self.manOverhang)
            .offset(x: man.minX, y: man.minY)
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
