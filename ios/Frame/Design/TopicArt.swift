import SwiftUI

/// The Temat sheet's small drawings (PLAN 3.3zzz59): one for each subject,
/// drawn in a black line with at most one colour, on a 24-point grid like
/// `GroupMark`. The paths are in `TopicArtData.swift`. The colour is a
/// watercolour wash (PLAN 3.3zzz62): a picture under the line
/// (`topic-wash-<key>` in the assets) that spills past it, pale in the
/// middle with pigment pooled unevenly at a crisp edge.
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
    /// How far a wash picture reaches past the 24-point grid on each side.
    static let washMargin: CGFloat = 4

    /// The sheet's groups, in order (Mateusz's pick of 2026-11-08 22:17).
    static let groups: [(title: String, keys: [String])] = [
        ("Krajobraz", ["landscape", "sea", "ships", "rivers", "mountains", "winter", "night", "sky", "trees", "gardens"]),
        ("Przyroda", ["flowers", "botany", "birds", "animals", "still-life"]),
        ("Ludzie", ["portrait", "women", "children", "music-dance", "theatre"]),
        ("Życie i miejsca", ["everyday", "work", "city", "architecture", "interior"]),
        ("Opowieści", ["mythology", "religion", "history", "hunting"]),
    ]

    /// The wash picture's asset name for a drawing with a colour.
    static func washAsset(_ key: String) -> String? {
        let key = key.hasPrefix("subject:") ? String(key.dropFirst(8)) : key
        return drawings[key]?.tint == nil ? nil : "topic-wash-\(key)"
    }

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

/// A subject's drawing at any size. With `wash` its colour is the
/// watercolour picture under the line rather than a flat fill.
struct TopicMark: View {
    let drawing: TopicArt.Drawing
    var wash: String?

    var body: some View {
        GeometryReader { geometry in
            let side = min(geometry.size.width, geometry.size.height)
            let reach = side * (24 + 2 * TopicArt.washMargin) / 24
            ZStack {
                if let wash {
                    Image(wash)
                        .resizable()
                        .interpolation(.high)
                        .frame(width: reach, height: reach)
                }
                lines
            }
            .frame(width: geometry.size.width, height: geometry.size.height)
        }
        .accessibilityHidden(true)
    }

    private var lines: some View {
        Canvas { context, size in
            let scale = min(size.width, size.height) / 24
            context.translateBy(x: (size.width - 24 * scale) / 2, y: (size.height - 24 * scale) / 2)
            context.scaleBy(x: scale, y: scale)
            for layer in drawing.layers {
                let style = FillStyle(eoFill: layer.evenOdd)
                switch layer.paint {
                case .tint:
                    if wash == nil, let tint = drawing.tint {
                        context.fill(layer.path, with: .color(tint.color), style: style)
                    }
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
    }
}

/// A row of the Temat sheet's list (PLAN 3.3zzz62): the subject's drawing
/// in its watercolour, the name, and a tick when picked, over a hairline.
/// The line stays black; in the dark the drawing sits on a cream disc that
/// holds the wash.
struct TopicRow: View {
    let drawing: TopicArt.Drawing?
    var wash: String?
    let title: String
    var selected = false
    var action: () -> Void

    @Environment(\.colorScheme) private var scheme
    @ScaledMetric(relativeTo: .subheadline) private var side: CGFloat = 28

    var body: some View {
        Button(action: action) {
            HStack(spacing: 9) {
                mark
                Text(title)
                    .font(.subheadline.weight(selected ? .semibold : .regular))
                    .lineLimit(2)
                    .minimumScaleFactor(0.85)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "checkmark")
                    .font(.footnote.weight(.bold))
                    .opacity(selected ? 1 : 0)
            }
            .foregroundStyle(Theme.ink)
            .padding(.horizontal, 2)
            .frame(minHeight: 42)
            .overlay(alignment: .bottom) { Rectangle().fill(Theme.hairline).frame(height: 1) }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(title)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .sensoryFeedback(.selection, trigger: selected)
    }

    @ViewBuilder private var mark: some View {
        if let drawing {
            if scheme == .dark {
                TopicMark(drawing: drawing, wash: wash)
                    .frame(width: side * 0.82, height: side * 0.82)
                    .frame(width: side, height: side)
                    .background(TopicArt.cream)
                    .clipShape(Circle())
            } else {
                TopicMark(drawing: drawing, wash: wash)
                    .frame(width: side, height: side)
            }
        } else {
            Color.clear.frame(width: side, height: side)
        }
    }
}
