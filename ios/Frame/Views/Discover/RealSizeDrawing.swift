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
/// znacznie większy obraz i postać"): the work's longer side gets at least
/// 120 points, as far as the column's width allows, but never so close that
/// less than 80 cm of him shows from the head down. When he is then taller
/// than the drawing, his legs and his height line fade out at its foot.
/// A work beside which the whole man fits anyway is drawn as before. The
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
        /// He is taller than the drawing: his legs fade out at its foot.
        var cropped: Bool
        /// The drawing's height.
        var height: CGFloat
    }

    /// The drawing's height for his whole figure, or its window when he is
    /// cropped.
    static let room: CGFloat = 250
    private static let top: CGFloat = 10
    /// The work's longer side, at least, when the width allows.
    static let smallest: CGFloat = 120
    /// The least of him shown, from the top of his head.
    static let leastOfHim: CGFloat = 80
    private static let gap: CGFloat = 66
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
        let scale = min(across, max(whole, min(wanted, room / leastOfHim)))
        // Centimetres above the floor to points down from the drawing's top.
        func y(_ cm: CGFloat) -> CGFloat { top + (tallest - cm) * scale }
        let picture = CGRect(x: 0, y: y(lift + h), width: w * scale, height: h * scale)
        let man = CGRect(x: picture.maxX + gap, y: y(manH), width: manW * scale, height: manH * scale)
        let cropped = manH * scale > room + 0.5
        let underWork = picture.maxY + widthLabel
        let feet = y(0) + manH * (CGFloat(manOverhang) - 1) * scale
        let height = cropped ? max(top + room, underWork) : max(feet, underWork)
        return Plan(scale: scale, picture: picture, man: man, cropped: cropped, height: ceil(height))
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
        // Cropped, his height line runs down to the drawing's foot, fading.
        let lineEnd = plan.cropped ? plan.height : man.maxY
        let fade: CGFloat = 70
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

            ZStack(alignment: .topLeading) {
                Color.clear.frame(width: column, height: plan.height)
                Image("ScaleFigure")
                    .renderingMode(.template)
                    .resizable()
                    .foregroundStyle(Theme.ink.opacity(0.88))
                    .frame(width: man.width, height: man.height * Self.manOverhang)
                    .offset(x: man.minX, y: man.minY)
                Dimension(
                    from: CGPoint(x: man.maxX + 8, y: man.minY),
                    to: CGPoint(x: man.maxX + 8, y: lineEnd),
                    ticks: plan.cropped ? .start : .both
                )
                .stroke(pencil, style: StrokeStyle(lineWidth: 1.2, lineCap: .round))
            }
            .frame(width: column, height: plan.height, alignment: .topLeading)
            .clipped()
            .mask {
                if plan.cropped {
                    LinearGradient(
                        stops: [
                            .init(color: .black, location: 0),
                            .init(color: .black, location: max(0, (plan.height - fade) / plan.height)),
                            .init(color: .clear, location: 1),
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                } else {
                    Color.black
                }
            }
            pencilled("180 cm")
                .alignmentGuide(.leading) { _ in -(man.maxX + 14) }
                .alignmentGuide(.top) { d in
                    -((plan.cropped ? man.minY + 0.42 * (plan.height - man.minY) : man.midY) - d.height / 2)
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

/// A pencil dimension line with a short tick at each end (or only at its
/// start, when it runs on out of the drawing).
private struct Dimension: Shape {
    enum Ticks { case both, start }
    let from: CGPoint
    let to: CGPoint
    var ticks: Ticks = .both

    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: from)
        path.addLine(to: to)
        let tick: CGFloat = 4
        let vertical = from.x == to.x
        for end in ticks == .both ? [from, to] : [from] {
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
