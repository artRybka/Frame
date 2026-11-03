import SwiftUI

/// The artist's life as a line, after the note in "O autorze" (Mateusz
/// 2026-11-03: "czytelna i jednoznaczna"): a ruler running to both edges of
/// the screen, upright ticks at the birth and the death with "ur." and
/// "zm." and their years under them; this work as a vermilion dot; the
/// moments of their life and one or two historical events of their time
/// as numbered rings, in one numbering by year, the events in grey. Marks
/// too close to sit at their years are moved apart just enough not to
/// overlap. Under it a legend in the order of the years: each mark as on
/// the line, its year and what it is (this work by its title in vermilion,
/// the events in grey).
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
    /// Centre to centre, at least, of two marks on the line.
    private static let spacing: CGFloat = markSize + 3
    /// How far the line runs on past the ends: to the screen's edges, where
    /// the scroll view clips it.
    private static let overrun: CGFloat = 2000

    private enum Mark: Hashable {
        case work
        /// A moment of their life (``event`` false) or of history, and its
        /// number among them all.
        case numbered(Int, event: Bool)
    }

    private struct Entry: Hashable {
        var year: Int
        var mark: Mark
        var text: String
    }

    /// Everything on the line, by year; on the same year this work first,
    /// then their life, then history. One numbering for the moments and
    /// the events.
    private var entries: [Entry] {
        var dated: [(year: Int, rank: Int, text: String)] = []
        dated += milestones.map { (year: $0.year, rank: 1, text: $0.text) }
        dated += events.prefix(3).map { (year: $0.year, rank: 2, text: $0.text) }
        dated.sort { ($0.year, $0.rank) < ($1.year, $1.rank) }
        var all = dated.enumerated().map { index, entry in
            Entry(year: entry.year, mark: .numbered(index + 1, event: entry.rank == 2), text: entry.text)
        }
        if let work {
            let at = all.firstIndex { $0.year >= work.year } ?? all.count
            all.insert(Entry(year: work.year, mark: .work, text: work.title), at: at)
        }
        return all
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
                            .foregroundStyle(Self.yearColour(entry.mark))
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

    private static func yearColour(_ mark: Mark) -> Color {
        switch mark {
        case .work: Theme.vermilion
        case .numbered(_, let event): event ? Theme.inkSoft.opacity(0.75) : Theme.inkSoft
        }
    }

    private func legendText(_ entry: Entry) -> Text {
        switch entry.mark {
        case .work:
            Text(entry.text).font(.serif(15)).foregroundStyle(Theme.vermilion)
        case .numbered(_, let event):
            Text(entry.text).font(.serif(15)).foregroundStyle(event ? Theme.inkSoft : Theme.ink.opacity(0.9))
        }
    }

    /// The mark as on the line: the work's dot, a numbered ring (grey for
    /// history).
    @ViewBuilder
    private func marker(_ mark: Mark) -> some View {
        switch mark {
        case .work:
            // As big as the numbered rings (Mateusz 2026-11-03).
            Circle().fill(Theme.vermilion).frame(width: Self.markSize, height: Self.markSize)
        case .numbered(let number, let event):
            let colour = event ? Theme.inkSoft.opacity(0.7) : Theme.ink.opacity(0.75)
            Circle()
                .fill(Theme.paper)
                .overlay(Circle().strokeBorder(colour, lineWidth: 1.3))
                .overlay(
                    Text(String(number))
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(event ? Theme.inkSoft : Theme.ink)
                )
                .frame(width: Self.markSize, height: Self.markSize)
        }
    }

    /// Where each mark sits: at its year, unless that is too close to its
    /// neighbours; then a run of marks too close together is spread evenly
    /// around their years' middle, as little as keeps them apart, and kept
    /// off the ends.
    private func places(in width: CGFloat) -> [CGFloat] {
        let wanted = entries.map { x($0.year, in: width) }
        guard !wanted.isEmpty else { return [] }
        let gap = Self.spacing
        let low = Self.inset + gap / 2, high = width - Self.inset - gap / 2
        // Runs of marks, each as (first index, count, centre).
        var runs: [(first: Int, count: Int, centre: CGFloat)] = []
        func start(_ run: (first: Int, count: Int, centre: CGFloat)) -> CGFloat {
            let half = CGFloat(run.count - 1) * gap / 2
            return min(max(run.centre - half, low), max(high - 2 * half, low))
        }
        for (index, at) in wanted.enumerated() {
            runs.append((index, 1, at))
            // Merge with the run before while they overlap.
            while runs.count > 1 {
                let last = runs[runs.count - 1], before = runs[runs.count - 2]
                let beforeEnd = start(before) + CGFloat(before.count - 1) * gap
                guard start(last) - beforeEnd < gap else { break }
                let count = before.count + last.count
                let mean = wanted[before.first..<(before.first + count)].reduce(0, +) / CGFloat(count)
                runs.removeLast(2)
                runs.append((before.first, count, mean))
            }
        }
        var placed: [CGFloat] = []
        for run in runs {
            let first = start(run)
            placed += (0..<run.count).map { first + CGFloat($0) * gap }
        }
        return placed
    }

    private func x(_ year: Int, in width: CGFloat) -> CGFloat {
        let span = CGFloat(max(died - born, 1))
        let t = min(max(CGFloat(year - born) / span, 0), 1)
        return Self.inset + t * (width - 2 * Self.inset)
    }

    private func line(width: CGFloat) -> some View {
        let y = Self.lineY
        let placed = places(in: width)
        return ZStack(alignment: .topLeading) {
            // Past the birth and the death to the screen's edges.
            Rectangle()
                .fill(Theme.inkSoft.opacity(0.45))
                .frame(width: width + 2 * Self.overrun, height: 2)
                .position(x: width / 2, y: y)
            // The two ends: short upright ticks, as on a ruler.
            ForEach([born, died], id: \.self) { year in
                Capsule()
                    .fill(Theme.inkSoft)
                    .frame(width: 2, height: 10)
                    .position(x: x(year, in: width), y: y)
            }
            ForEach(Array(entries.enumerated()), id: \.element) { index, entry in
                marker(entry.mark).position(x: placed[index], y: y)
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
