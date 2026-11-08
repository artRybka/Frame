import SwiftUI

/// The Temat sheet's small drawings (PLAN 3.3zzz58): one for each subject,
/// drawn in a black line with at most one colour, on a 24-point grid like
/// `GroupMark`. The paths are in `TopicArtData.swift`.
enum TopicArt {
    /// The drawing's line: always black, also in the dark, where it sits on
    /// a cream disc (a light line on a dark chip lost the drawings).
    static let line = Color(hex: 0x1D1B18)
    /// The disc under a drawing on a dark chip.
    static let cream = Color(hex: 0xF5F1EA)
    /// The line's width on the 24-point grid.
    static let lineWidth: CGFloat = 1.3
    /// White parts (the figure in Portret).
    static let white = Color.white

    struct Drawing {
        let tint: Tint?
        let layers: [Layer]
    }

    struct Layer {
        enum Paint: Equatable {
            /// Filled with the drawing's colour.
            case tint
            /// Filled white.
            case white
            /// Filled black (music notes, dots).
            case ink
            /// A black line, `width` times the drawing's line.
            case stroke(CGFloat, butt: Bool = false)

            static let line = Paint.stroke(1)
        }

        let paint: Paint
        let path: Path
        var evenOdd = false

        init(_ paint: Paint, _ data: String, evenOdd: Bool = false) {
            self.paint = paint
            path = TopicArt.path(data)
            self.evenOdd = evenOdd
        }
    }

    /// The drawing for a subject key ("subject:sea" or "sea").
    static func drawing(_ key: String) -> Drawing? {
        drawings[key.hasPrefix("subject:") ? String(key.dropFirst(8)) : key]
    }

    /// Reads the generated path data: absolute `M`, `L`, `C` and `Z`.
    static func path(_ data: String) -> Path {
        var path = Path()
        var numbers: [CGFloat] = []
        var command: Character = " "
        func flush() {
            switch command {
            case "M" where numbers.count >= 2:
                path.move(to: CGPoint(x: numbers[0], y: numbers[1]))
            case "L" where numbers.count >= 2:
                path.addLine(to: CGPoint(x: numbers[0], y: numbers[1]))
            case "C" where numbers.count >= 6:
                path.addCurve(
                    to: CGPoint(x: numbers[4], y: numbers[5]),
                    control1: CGPoint(x: numbers[0], y: numbers[1]),
                    control2: CGPoint(x: numbers[2], y: numbers[3])
                )
            case "Z":
                path.closeSubpath()
            default:
                break
            }
            numbers.removeAll(keepingCapacity: true)
        }
        for word in data.split(separator: " ") {
            var text = Substring(word)
            if let first = text.first, first.isLetter {
                flush()
                command = first
                text = text.dropFirst()
                if command == "Z" {
                    flush()
                    command = " "
                }
            }
            if let value = Double(text) { numbers.append(CGFloat(value)) }
        }
        flush()
        return path
    }
}

/// A subject's drawing at any size.
struct TopicMark: View {
    let drawing: TopicArt.Drawing

    var body: some View {
        Canvas { context, size in
            let scale = min(size.width, size.height) / 24
            context.translateBy(x: (size.width - 24 * scale) / 2, y: (size.height - 24 * scale) / 2)
            context.scaleBy(x: scale, y: scale)
            for layer in drawing.layers {
                let style = FillStyle(eoFill: layer.evenOdd)
                switch layer.paint {
                case .tint:
                    if let tint = drawing.tint { context.fill(layer.path, with: .color(tint.color), style: style) }
                case .white:
                    context.fill(layer.path, with: .color(TopicArt.white), style: style)
                case .ink:
                    context.fill(layer.path, with: .color(TopicArt.line), style: style)
                case let .stroke(width, butt):
                    context.stroke(
                        layer.path,
                        with: .color(TopicArt.line),
                        style: StrokeStyle(
                            lineWidth: TopicArt.lineWidth * width, lineCap: butt ? .butt : .round, lineJoin: .round
                        )
                    )
                }
            }
        }
        .accessibilityHidden(true)
    }
}

/// A Temat chip: the subject's drawing before its name. The line stays
/// black; where the chip is dark (picked in the light, not picked in the
/// dark) the drawing sits on a cream disc.
struct TopicChip: View {
    let drawing: TopicArt.Drawing
    let title: String
    var selected = false
    var action: () -> Void

    @Environment(\.colorScheme) private var scheme
    @ScaledMetric(relativeTo: .subheadline) private var side: CGFloat = 20

    /// Whether the chip behind the drawing is dark.
    static func onDisc(selected: Bool, dark: Bool) -> Bool { selected != dark }

    var body: some View {
        let disc = Self.onDisc(selected: selected, dark: scheme == .dark)
        Button(action: action) {
            HStack(spacing: 5) {
                Group {
                    if disc {
                        TopicMark(drawing: drawing)
                            .frame(width: side * 0.85, height: side * 0.85)
                            .frame(width: side * 1.2, height: side * 1.2)
                            .background(TopicArt.cream, in: Circle())
                    } else {
                        TopicMark(drawing: drawing)
                            .frame(width: side, height: side)
                            .padding(side * 0.1)
                    }
                }
                Text(title).font(.subheadline.weight(.medium))
            }
            .padding(.leading, 5)
            .padding(.trailing, 12)
            .padding(.vertical, 5)
            .foregroundStyle(selected ? Theme.paper : Theme.ink)
            .background(selected ? Theme.ink : Theme.card, in: Capsule())
            .overlay(Capsule().strokeBorder(selected ? .clear : Theme.hairline))
        }
        .buttonStyle(.plain)
        .sensoryFeedback(.selection, trigger: selected)
    }
}
