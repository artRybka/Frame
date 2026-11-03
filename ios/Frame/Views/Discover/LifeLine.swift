import SwiftUI

/// The artist's life as a thin line under their name ("O autorze"; Mateusz
/// 2026-11-02): born at the left end, died at the right, their other works
/// shown on the page as small dots, this one in vermilion with "to dzieło"
/// over it, and the moments of their life as rings on the line, each listed
/// under it with its year. At a glance: an early work, or a late one.
struct LifeLine: View {
    let born: Int
    let died: Int
    /// The work's year.
    let work: Int?
    /// The years of their other works on the page.
    let others: [Int]
    let milestones: [DailyWork.Milestone]

    private static let inset: CGFloat = 6
    private static let lineY: CGFloat = 24
    private static let height: CGFloat = 46

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            GeometryReader { geometry in
                line(width: geometry.size.width)
            }
            .frame(height: Self.height)
            .accessibilityElement()
            .accessibilityLabel(Text(spoken))
            if !milestones.isEmpty {
                VStack(alignment: .leading, spacing: 5) {
                    ForEach(milestones, id: \.year) { moment in
                        HStack(alignment: .firstTextBaseline, spacing: 10) {
                            Text(String(moment.year))
                                .font(.caption.weight(.bold))
                                .monospacedDigit()
                                .foregroundStyle(Theme.inkSoft)
                            Text(moment.text)
                                .font(.serif(15))
                                .foregroundStyle(Theme.ink.opacity(0.9))
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
        }
    }

    private func x(_ year: Int, in width: CGFloat) -> CGFloat {
        let span = CGFloat(max(died - born, 1))
        let t = min(max(CGFloat(year - born) / span, 0), 1)
        return Self.inset + t * (width - 2 * Self.inset)
    }

    private func line(width: CGFloat) -> some View {
        let y = Self.lineY
        return ZStack(alignment: .topLeading) {
            Capsule()
                .fill(Theme.hairline)
                .frame(width: max(width - 2 * Self.inset, 0), height: 2)
                .position(x: width / 2, y: y)
            ForEach(Array(Set(others)).sorted(), id: \.self) { year in
                Circle()
                    .fill(Theme.inkSoft.opacity(0.55))
                    .frame(width: 7, height: 7)
                    .position(x: x(year, in: width), y: y)
            }
            ForEach(milestones, id: \.year) { moment in
                Circle()
                    .fill(Theme.paper)
                    .overlay(Circle().strokeBorder(Theme.inkSoft, lineWidth: 1.5))
                    .frame(width: 10, height: 10)
                    .position(x: x(moment.year, in: width), y: y)
            }
            if let work {
                let at = x(work, in: width)
                Circle()
                    .fill(Theme.vermilion)
                    .frame(width: 13, height: 13)
                    .position(x: at, y: y)
                Text("to dzieło")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(Theme.vermilion)
                    .fixedSize()
                    .position(x: min(max(at, 28), width - 28), y: y - 17)
            }
            Text(String(born))
                .font(.caption2)
                .monospacedDigit()
                .foregroundStyle(Theme.inkSoft)
                .fixedSize()
                .position(x: Self.inset + 14, y: y + 16)
            Text(String(died))
                .font(.caption2)
                .monospacedDigit()
                .foregroundStyle(Theme.inkSoft)
                .fixedSize()
                .position(x: width - Self.inset - 14, y: y + 16)
        }
        .frame(width: width, height: Self.height)
    }

    private var spoken: String {
        var parts = ["Życie artysty, \(born)–\(died)"]
        if let work { parts.append("to dzieło: \(work)") }
        return parts.joined(separator: ", ")
    }
}
