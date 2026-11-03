import SwiftUI

/// The artist's life as a thin line, after the note in "O autorze"
/// (Mateusz 2026-11-02/03): born at the left end, died at the right; this
/// work in vermilion, their other works on the page as small grey dots,
/// the moments of their life as rings. Nothing is written on the line but
/// the two years: under it a legend lists every mark in the order of the
/// years, each with its own mark, its year and what it is (this work by its
/// title).
struct LifeLine: View {
    /// A work on the line: its year and title.
    struct Work: Hashable {
        var year: Int
        var title: String
    }

    let born: Int
    let died: Int
    /// This work, when its year is known.
    let work: Work?
    /// Their other works shown on the page.
    let others: [Work]
    let milestones: [DailyWork.Milestone]

    private static let inset: CGFloat = 6
    private static let lineY: CGFloat = 8
    private static let height: CGFloat = 30

    private enum Mark: Hashable {
        case work, other, moment
    }

    private struct Entry: Hashable {
        var year: Int
        var mark: Mark
        var text: String
    }

    /// Everything on the line, by year; on the same year this work first.
    private var entries: [Entry] {
        var all = milestones.map { Entry(year: $0.year, mark: .moment, text: $0.text) }
        all += uniqueOthers.map { Entry(year: $0.year, mark: .other, text: $0.title) }
        if let work { all.append(Entry(year: work.year, mark: .work, text: work.title)) }
        let order: [Mark: Int] = [.work: 0, .moment: 1, .other: 2]
        return all.sorted { ($0.year, order[$0.mark]!) < ($1.year, order[$1.mark]!) }
    }

    private var uniqueOthers: [Work] {
        var seen = Set<Work>()
        return others.filter { $0.year >= born - 5 && $0.year <= died + 5 && seen.insert($0).inserted }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            GeometryReader { geometry in
                line(width: geometry.size.width)
            }
            .frame(height: Self.height)
            .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 6) {
                ForEach(entries, id: \.self) { entry in
                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                        marker(entry.mark)
                            .frame(width: 14, height: 14)
                            .alignmentGuide(.firstTextBaseline) { d in d[VerticalAlignment.center] + 5 }
                        Text(String(entry.year))
                            .font(.caption.weight(.bold))
                            .monospacedDigit()
                            .foregroundStyle(entry.mark == .work ? Theme.vermilion : Theme.inkSoft)
                        Text(entry.text)
                            .font(.serif(15, weight: entry.mark == .work ? .semibold : .regular))
                            .italic(entry.mark != .moment)
                            .foregroundStyle(entry.mark == .other ? Theme.inkSoft : Theme.ink.opacity(0.9))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .accessibilityElement(children: .combine)
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text("Życie artysty, \(String(born))–\(String(died))"))
    }

    @ViewBuilder
    private func marker(_ mark: Mark) -> some View {
        switch mark {
        case .work:
            Circle().fill(Theme.vermilion).frame(width: 12, height: 12)
        case .other:
            Circle().fill(Theme.inkSoft.opacity(0.55)).frame(width: 7, height: 7)
        case .moment:
            Circle()
                .fill(Theme.paper)
                .overlay(Circle().strokeBorder(Theme.inkSoft, lineWidth: 1.5))
                .frame(width: 10, height: 10)
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
            ForEach(Array(Set(uniqueOthers.map(\.year))).sorted(), id: \.self) { year in
                marker(.other).position(x: x(year, in: width), y: y)
            }
            ForEach(milestones, id: \.year) { moment in
                marker(.moment).position(x: x(moment.year, in: width), y: y)
            }
            if let work {
                Circle()
                    .fill(Theme.vermilion)
                    .frame(width: 13, height: 13)
                    .position(x: x(work.year, in: width), y: y)
            }
            Text(String(born))
                .font(.caption2)
                .monospacedDigit()
                .foregroundStyle(Theme.inkSoft)
                .fixedSize()
                .position(x: Self.inset + 14, y: y + 15)
            Text(String(died))
                .font(.caption2)
                .monospacedDigit()
                .foregroundStyle(Theme.inkSoft)
                .fixedSize()
                .position(x: width - Self.inset - 14, y: y + 15)
        }
        .frame(width: width, height: Self.height)
    }
}
