import SwiftUI

/// A picture on its way to the frame: what is happening now, how far along
/// it is, and the three parts (processing, loading, displaying).
struct DisplayProgressBar: View {
    let progress: DisplayProgress
    /// One line and the bar, for the other tabs.
    var compact = false

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 7 : 10) {
            HStack(alignment: .center, spacing: compact ? 11 : 8) {
                if let mark {
                    NoticeMark(kind: mark)
                } else if compact {
                    ProgressView()
                        .controlSize(.small)
                        .tint(Theme.ink)
                        .opacity(0.6)
                        .frame(width: 22, height: 22)
                }
                Text(progress.stageLabel)
                    .font(compact ? .subheadline.weight(.semibold) : .footnote.weight(.semibold))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(1)
                    .contentTransition(.opacity)
                Spacer(minLength: 8)
                // Who changed the picture: the schedule or the app.
                if let origin = progress.origin {
                    Image(systemName: origin == "schedule" ? "clock" : "iphone")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(Theme.ink)
                }
            }
            bar
            if !compact {
                phases
                if let message = progress.message, progress.isFailed || progress.isWaiting {
                    Text(message)
                        .font(.caption)
                        .foregroundStyle(Theme.glassInk)
                        .lineLimit(2)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, compact ? 13 : 14)
        .modifier(BarGlass(compact: compact))
        .animation(.easeInOut(duration: 0.3), value: progress.stage)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(progress.origin == "schedule" ? "Harmonogram: \(progress.stageLabel)" : progress.stageLabel)
        .accessibilityValue("\(Int((progress.fraction * 100).rounded())) %")
    }

    /// Ended or held up: said by the same soft disc as the cards'.
    private var mark: Notice.Kind? {
        if progress.isFailed { return .error }
        if progress.isWaiting { return .warning }
        if progress.isDone { return .done }
        return nil
    }

    private var bar: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(Theme.ink.opacity(0.1))
                Capsule()
                    .fill(Theme.ink)
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

/// Among the cards it lifts off the pictures like them; under the picture
/// on "Teraz" it lies on paper, with only the hairline.
private struct BarGlass: ViewModifier {
    let compact: Bool

    func body(content: Content) -> some View {
        if compact {
            content.noticeGlass()
        } else {
            content
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: Theme.corner, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: Theme.corner, style: .continuous)
                        .strokeBorder(Theme.hairline.opacity(0.6))
                )
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
