import SwiftUI

/// A picture on its way to the frame: what is happening now, how far along
/// it is, and the three parts (processing, loading, displaying).
struct DisplayProgressBar: View {
    let progress: DisplayProgress
    /// One line and the bar, for the other tabs.
    var compact = false

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 7 : 10) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                if progress.isDone {
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(Theme.good)
                }
                Text(progress.stageLabel)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(1)
                    .contentTransition(.opacity)
                Spacer(minLength: 8)
                // Who changed the picture: the schedule or the app.
                if let origin = progress.origin {
                    Image(systemName: origin == "schedule" ? "clock" : "iphone")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(origin == "schedule" ? Theme.accent : Theme.vermilion)
                }
            }
            bar
            if !compact {
                phases
                if let message = progress.message, progress.isFailed || progress.isWaiting {
                    Text(message)
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .lineLimit(2)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, compact ? 11 : 14)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: Theme.corner, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: Theme.corner, style: .continuous)
                .strokeBorder(Theme.hairline.opacity(0.6))
        )
        .animation(.easeInOut(duration: 0.3), value: progress.stage)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(progress.origin == "schedule" ? "Harmonogram: \(progress.stageLabel)" : progress.stageLabel)
        .accessibilityValue("\(Int((progress.fraction * 100).rounded())) %")
    }

    private var tint: Color {
        if progress.isFailed { return Theme.bad }
        if progress.isWaiting { return Theme.warn }
        if progress.isDone { return Theme.good }
        return Theme.vermilion
    }

    private var bar: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(Theme.ink.opacity(0.1))
                Capsule()
                    .fill(tint)
                    .frame(width: max(6, geo.size.width * min(max(progress.fraction, 0), 1)))
            }
        }
        .frame(height: 6)
        // The server is asked once a second, on the beat: glide from one
        // answer to the next in that second, so the bar never stops between.
        .animation(.linear(duration: 1), value: progress.fraction)
    }

    private var phases: some View {
        HStack(spacing: 0) {
            ForEach(Array(DisplayProgress.phases.enumerated()), id: \.offset) { index, phase in
                if index > 0 { Spacer(minLength: 6) }
                let current = progress.phaseIndex
                let done = current.map { index < $0 } ?? false
                let now = current == index && progress.active
                HStack(spacing: 4) {
                    Image(systemName: done ? "checkmark" : now ? "circle.fill" : "circle")
                        .font(.system(size: done ? 9 : 6, weight: .bold))
                    Text(phase.label)
                }
                .font(.caption.weight(now ? .semibold : .regular))
                .foregroundStyle(now ? Theme.ink : done ? Theme.inkSoft : Theme.inkSoft.opacity(0.55))
            }
        }
    }
}

#Preview {
    VStack(spacing: 16) {
        DisplayProgressBar(
            progress: DisplayProgress(
                stage: "downloading", phase: "loading", active: true, title: "Fala",
                fraction: 0.38
            )
        )
        DisplayProgressBar(
            progress: DisplayProgress(stage: "refreshing", phase: "displaying", active: true,
                                      title: "Fala", fraction: 0.7),
            compact: true
        )
        DisplayProgressBar(progress: DisplayProgress(stage: "done", active: false, title: "Fala", fraction: 1))
    }
    .padding()
    .paperPage()
}
