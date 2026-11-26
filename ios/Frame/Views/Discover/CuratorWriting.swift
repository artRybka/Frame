import SwiftUI

/// "O dziele" of a work whose curator's note is still being written: faint
/// lines that write themselves one after another, as a pen would, where the
/// note will stand, from the card's first frame (Mateusz 2026-11-26: „od
/// początku musimy sygnalizować jego pisanie”; a spinner came only after
/// the first long wait).
struct CuratorWriting: View {
    @Environment(\.accessibilityReduceMotion) private var still

    /// The lines' lengths, as a paragraph's: the last one short.
    private static let lines: [CGFloat] = [1, 0.93, 0.97, 0.58]
    /// Seconds a line takes, and the pause before the page starts again.
    private static let stroke = 1.1
    private static let rest = 1.4
    private static let height: CGFloat = 9
    private static let gap: CGFloat = 13

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            TimelineView(.animation(paused: still)) { context in
                let at = context.date.timeIntervalSinceReferenceDate
                VStack(alignment: .leading, spacing: Self.gap) {
                    ForEach(Self.lines.indices, id: \.self) { index in
                        line(index, drawn: still ? 1 : drawn(index, at: at), fade: still ? 1 : fade(at: at))
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityHidden(true)
            Label {
                Text(bound: "Kurator pisze notkę o tym dziele…")
            } icon: {
                Image(systemName: "pencil.line")
                    .symbolEffect(.pulse, options: .repeating, isActive: !still)
            }
            .font(.footnote)
            .foregroundStyle(Theme.inkSoft)
        }
    }

    private func line(_ index: Int, drawn: CGFloat, fade: Double) -> some View {
        GeometryReader { box in
            let full = box.size.width * Self.lines[index]
            ZStack(alignment: .leading) {
                Capsule().fill(Theme.hairline.opacity(0.8))
                    .frame(width: full)
                Capsule().fill(Theme.inkSoft.opacity(0.42 * fade))
                    .frame(width: full * drawn)
            }
        }
        .frame(height: Self.height)
    }

    private static var cycle: Double { Double(lines.count) * stroke + rest }

    /// How much of a line is written at this moment of the cycle.
    private func drawn(_ index: Int, at time: TimeInterval) -> CGFloat {
        let t = time.truncatingRemainder(dividingBy: Self.cycle) - Double(index) * Self.stroke
        let p = min(max(t / Self.stroke, 0), 1)
        return CGFloat(p * p * (3 - 2 * p))  // a hand's ease: slow start, slow end
    }

    /// The written lines fade away at the end of the pause, and the page
    /// starts again.
    private func fade(at time: TimeInterval) -> Double {
        let t = time.truncatingRemainder(dividingBy: Self.cycle)
        let out = Self.cycle - 0.5
        return t < out ? 1 : max(0, 1 - (t - out) / 0.5)
    }
}
