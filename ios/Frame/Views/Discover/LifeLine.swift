import SwiftUI

/// The artist's life as a line, after the note in "O autorze" (Mateusz
/// 2026-11-03: "czytelna i jednoznaczna"): "ur." and the year at its left
/// end, "zm." and the year at its right; this work as a vermilion dot; the
/// moments of their life as numbered rings (1, 2, 3); one or two historical
/// events of their time as lettered squares (A, B). Under it a legend in the
/// order of the years: each mark as on the line, its year and what it is
/// (this work by its title, the events in grey).
struct LifeLine: View {
    /// This work: its year and title.
    struct Work: Hashable {
        var year: Int
        var title: String
    }

    let born: Int
    let died: Int
    /// This work, when its year is known.
    let work: Work?
    let milestones: [DailyWork.Milestone]
    let events: [DailyWork.Milestone]

    private static let inset: CGFloat = 10
    private static let lineY: CGFloat = 12
    private static let height: CGFloat = 40
    private static let markSize: CGFloat = 17

    private enum Mark: Hashable {
        case work
        case moment(Int)
        case event(Int)
    }

    private struct Entry: Hashable {
        var year: Int
        var mark: Mark
        var text: String
    }

    private static let letters = ["A", "B", "C"]

    /// Everything on the line, by year; on the same year this work first.
    private var entries: [Entry] {
        var all: [Entry] = []
        if let work { all.append(Entry(year: work.year, mark: .work, text: work.title)) }
        all += milestones.enumerated().map { Entry(year: $1.year, mark: .moment($0), text: $1.text) }
        all += events.prefix(Self.letters.count).enumerated().map {
            Entry(year: $1.year, mark: .event($0), text: $1.text)
        }
        func rank(_ mark: Mark) -> Int {
            switch mark {
            case .work: 0
            case .moment: 1
            case .event: 2
            }
        }
        return all.sorted { ($0.year, rank($0.mark)) < ($1.year, rank($1.mark)) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            GeometryReader { geometry in
                line(width: geometry.size.width)
            }
            .frame(height: Self.height)
            .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 7) {
                ForEach(entries, id: \.self) { entry in
                    HStack(alignment: .firstTextBaseline, spacing: 10) {
                        marker(entry.mark)
                            .frame(width: Self.markSize, height: Self.markSize)
                            .alignmentGuide(.firstTextBaseline) { d in d[VerticalAlignment.center] + 5 }
                        Text(String(entry.year))
                            .font(.caption.weight(.bold))
                            .monospacedDigit()
                            .foregroundStyle(entry.mark == .work ? Theme.vermilion : Theme.inkSoft)
                        legendText(entry)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .accessibilityElement(children: .combine)
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text("Życie artysty, \(String(born))–\(String(died))"))
    }

    private func legendText(_ entry: Entry) -> Text {
        switch entry.mark {
        case .work:
            Text(entry.text).font(.serif(15, weight: .semibold)).italic().foregroundStyle(Theme.ink)
        case .moment:
            Text(entry.text).font(.serif(15)).foregroundStyle(Theme.ink.opacity(0.9))
        case .event:
            Text(entry.text).font(.serif(15)).foregroundStyle(Theme.inkSoft)
        }
    }

    /// The mark as on the line: the work's dot, a moment's numbered ring,
    /// an event's lettered square.
    @ViewBuilder
    private func marker(_ mark: Mark) -> some View {
        switch mark {
        case .work:
            Circle().fill(Theme.vermilion).frame(width: 13, height: 13)
        case .moment(let index):
            Circle()
                .fill(Theme.paper)
                .overlay(Circle().strokeBorder(Theme.ink.opacity(0.75), lineWidth: 1.3))
                .overlay(
                    Text(String(index + 1))
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(Theme.ink)
                )
                .frame(width: Self.markSize, height: Self.markSize)
        case .event(let index):
            RoundedRectangle(cornerRadius: 3, style: .continuous)
                .fill(Theme.hairline)
                .overlay(
                    Text(Self.letters[index])
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(Theme.inkSoft)
                )
                .frame(width: Self.markSize - 1, height: Self.markSize - 1)
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
                .fill(Theme.inkSoft.opacity(0.45))
                .frame(width: max(width - 2 * Self.inset, 0), height: 2)
                .position(x: width / 2, y: y)
            // The two ends: short upright ticks, as on a ruler.
            ForEach([born, died], id: \.self) { year in
                Capsule()
                    .fill(Theme.inkSoft)
                    .frame(width: 2, height: 10)
                    .position(x: x(year, in: width), y: y)
            }
            ForEach(entries.filter { $0.mark != .work }, id: \.self) { entry in
                marker(entry.mark).position(x: x(entry.year, in: width), y: y)
            }
            if let work {
                marker(.work).position(x: x(work.year, in: width), y: y)
            }
            Text("ur. \(String(born))")
                .font(.caption2.weight(.semibold))
                .monospacedDigit()
                .foregroundStyle(Theme.inkSoft)
                .fixedSize()
                .alignmentGuide(.leading) { _ in -(Self.inset - 2) }
                .alignmentGuide(.top) { _ in -(y + 12) }
            Text("zm. \(String(died))")
                .font(.caption2.weight(.semibold))
                .monospacedDigit()
                .foregroundStyle(Theme.inkSoft)
                .fixedSize()
                .alignmentGuide(.leading) { d in -(width - Self.inset + 2 - d.width) }
                .alignmentGuide(.top) { _ in -(y + 12) }
        }
        .frame(width: width, height: Self.height, alignment: .topLeading)
    }
}
