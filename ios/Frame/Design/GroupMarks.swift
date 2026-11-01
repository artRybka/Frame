import SwiftUI

/// The marks of the search's groups wherever the app shows them: the group
/// buttons in Szukaj and the playlist editor, the suggestions while typing,
/// the museum lists and the museum under a picture. Epoka, Styl, Temat and
/// Muzeum are drawn here in one thin round line like Technika's system
/// symbol (`scribble.variable`), which the system's calendar, palette and
/// columns, with their dots and double lines, never matched. Kolor is three
/// ink dots. Any other kind shows its system symbol (`SearchToken.icon`).
struct GroupMark: View {
    /// The chip's kind: "period", "style", "subject", "museum", "color"…
    let kind: String
    /// The system symbol for a kind that isn't drawn here; by default the
    /// chip's own (`SearchToken.icon`).
    var symbol: String?
    /// Thicker line, for a picked (semibold) group.
    var bold = false
    /// The drawn mark's box at the default text size, in points.
    var side: CGFloat = 15

    @ScaledMetric(relativeTo: .subheadline) private var scale: CGFloat = 1

    var body: some View {
        if let shape = Mark(kind: kind) {
            let size = side * scale
            MarkShape(mark: shape)
                .stroke(style: StrokeStyle(lineWidth: size * (bold ? 0.11 : 0.085), lineCap: .round, lineJoin: .round))
                .frame(width: size, height: size)
                .accessibilityHidden(true)
        } else if kind == "color" {
            InkDots()
        } else {
            Image(systemName: symbol ?? SearchToken(kind: kind, key: "", name: "").icon)
        }
    }

    enum Mark {
        case calendar, palette, landscape, museum

        init?(kind: String) {
            switch kind {
            case "period": self = .calendar
            case "style", "legacy-style": self = .palette
            case "subject", "legacy-subject": self = .landscape
            case "museum": self = .museum
            default: return nil
            }
        }
    }

    /// The marks on a 24-point grid (the sketch in the project files,
    /// `ikonki-grup/szkic-3.html`), stroked by `GroupMark`.
    struct MarkShape: Shape {
        let mark: Mark

        func path(in rect: CGRect) -> Path {
            let unit = min(rect.width, rect.height) / 24
            let origin = CGPoint(x: rect.midX - 12 * unit, y: rect.midY - 12 * unit)
            func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
                CGPoint(x: origin.x + x * unit, y: origin.y + y * unit)
            }
            func box(_ x: CGFloat, _ y: CGFloat, _ width: CGFloat, _ height: CGFloat) -> CGRect {
                CGRect(origin: p(x, y), size: CGSize(width: width * unit, height: height * unit))
            }
            func dot(_ x: CGFloat, _ y: CGFloat, _ radius: CGFloat) -> CGRect {
                box(x - radius, y - radius, radius * 2, radius * 2)
            }
            var path = Path()
            switch mark {
            case .calendar:
                // A page with its two rings, no days.
                path.addRoundedRect(in: box(4, 5.5, 16, 14.5), cornerSize: CGSize(width: 3 * unit, height: 3 * unit))
                path.move(to: p(9, 3.5))
                path.addLine(to: p(9, 7.5))
                path.move(to: p(15, 3.5))
                path.addLine(to: p(15, 7.5))
            case .palette:
                // The palette's outline (left half a circle, the thumb's
                // notch on the right) and three dabs of paint.
                path.move(to: p(12, 3.5))
                path.addArc(
                    center: p(12, 12), radius: 8.5 * unit, startAngle: .degrees(270), endAngle: .degrees(90),
                    clockwise: true
                )
                path.addCurve(to: p(14, 18.7), control1: p(13.5, 20.5), control2: p(14, 19.6))
                path.addCurve(to: p(13, 16.3), control1: p(14, 17.6), control2: p(13, 17.3))
                path.addCurve(to: p(14.8, 14.8), control1: p(13, 15.4), control2: p(13.8, 14.8))
                path.addLine(to: p(16.9, 14.8))
                path.addCurve(to: p(20.5, 10.9), control1: p(19.2, 14.8), control2: p(20.5, 13))
                path.addCurve(to: p(12, 3.5), control1: p(20.5, 6.7), control2: p(16.7, 3.5))
                path.closeSubpath()
                path.addEllipse(in: dot(8.3, 10.5, 0.9))
                path.addEllipse(in: dot(12.3, 7.6, 0.9))
                path.addEllipse(in: dot(16.3, 10, 0.9))
            case .landscape:
                // A picture: frame, two hills and the sun.
                path.addRoundedRect(in: box(4, 5, 16, 15), cornerSize: CGSize(width: 3 * unit, height: 3 * unit))
                path.move(to: p(4.8, 18.5))
                path.addLine(to: p(9.5, 12.5))
                path.addLine(to: p(12.5, 16))
                path.addLine(to: p(14.5, 14))
                path.addLine(to: p(19.3, 19))
                path.addEllipse(in: dot(15.5, 9, 1.4))
            case .museum:
                // An open roof over three columns and the step.
                path.move(to: p(4, 9.5))
                path.addLine(to: p(12, 4.5))
                path.addLine(to: p(20, 9.5))
                for x: CGFloat in [7, 12, 17] {
                    path.move(to: p(x, 12))
                    path.addLine(to: p(x, 18))
                }
                path.move(to: p(4, 20.5))
                path.addLine(to: p(20, 20.5))
            }
            return path
        }
    }
}

/// Kolor's mark: three of the frame's inks (blue, red, yellow) as dots, the
/// way the app's icon has its squares.
struct InkDots: View {
    var body: some View {
        let size: CGFloat = 7
        VStack(spacing: -1.5) {
            HStack(spacing: -1.5) {
                Circle().fill(Theme.iconSquares[2]).frame(width: size, height: size)
                Circle().fill(Theme.iconSquares[0]).frame(width: size, height: size)
            }
            Circle().fill(Theme.iconSquares[1]).frame(width: size, height: size)
        }
        .accessibilityHidden(true)
    }
}
