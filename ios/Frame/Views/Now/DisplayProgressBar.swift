import SwiftUI

/// A picture on its way to the frame: which one, what is happening now, and
/// how far along each of its three parts (preparing, sending, drawing) is.
struct DisplayProgressBar: View {
    let progress: DisplayProgress
    /// One line and the bar, for the other tabs.
    var compact = false
    /// "Teraz": the picture on its way, for the thumbnail at the front.
    var picture: ImageRef? = nil
    /// Its title as "Teraz" says it (Polish when written); else the server's.
    var title: String? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 7 : 10) {
            if compact { compactHeader } else { header }
            if compact {
                bar
            } else if !progress.isDone {
                segments
                phases
            }
            if !compact, let message = progress.message, progress.isFailed || progress.isWaiting {
                Text(message)
                    .font(.caption)
                    .foregroundStyle(Theme.glassInk)
                    .lineLimit(2)
            }
        }
        .padding(.horizontal, compact ? 16 : 12)
        .padding(.vertical, compact ? 13 : 11)
        .modifier(BarGlass(compact: compact))
        .animation(.easeInOut(duration: 0.3), value: progress.stage)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityText)
        .accessibilityValue("\(Int((progress.fraction * 100).rounded())) %")
    }

    private var shownTitle: String {
        let given = title?.trimmingCharacters(in: .whitespaces) ?? ""
        return given.isEmpty ? progress.title : given
    }

    private var accessibilityText: String {
        let what = shownTitle.isEmpty ? progress.stageLabel : "\(shownTitle): \(progress.stageLabel)"
        return progress.origin == "schedule" ? "Harmonogram: \(what)" : what
    }

    /// The picture on its way, named: thumbnail, title, and under it what
    /// is happening now.
    private var header: some View {
        HStack(alignment: .center, spacing: 11) {
            if let picture {
                ArtImage(ref: picture, maxPixel: 160)
                    .frame(width: 42, height: 42)
                    .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 7, style: .continuous)
                            .strokeBorder(Theme.hairline.opacity(0.6), lineWidth: 0.5)
                    )
                    .accessibilityHidden(true)
            }
            VStack(alignment: .leading, spacing: 2) {
                if !shownTitle.isEmpty {
                    Text(shownTitle)
                        .font(.serif(17, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                        .lineLimit(1)
                }
                HStack(spacing: 6) {
                    if let mark {
                        NoticeMark(kind: mark, symbol: progress.isWaiting ? "clock" : nil)
                            .scaleEffect(0.8)
                            .frame(width: 16, height: 16)
                    }
                    Text(progress.stageLabel)
                        .font(shownTitle.isEmpty ? .footnote.weight(.semibold) : .footnote)
                        .foregroundStyle(shownTitle.isEmpty ? Theme.ink : Theme.inkSoft)
                        .lineLimit(1)
                        .contentTransition(.opacity)
                }
            }
            Spacer(minLength: 8)
            origin
        }
    }

    private var compactHeader: some View {
        HStack(alignment: .center, spacing: 11) {
            if let mark {
                // Waiting for the frame's wake is no warning: a clock.
                NoticeMark(kind: mark, symbol: progress.isWaiting ? "clock" : nil)
            } else {
                ProgressView()
                    .controlSize(.small)
                    .tint(Theme.ink)
                    .opacity(0.6)
                    .frame(width: 22, height: 22)
            }
            Text(progress.stageLabel)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(Theme.ink)
                .lineLimit(1)
                .contentTransition(.opacity)
            Spacer(minLength: 8)
            origin
        }
    }

    /// Who changed the picture: the schedule or the app.
    @ViewBuilder private var origin: some View {
        if let origin = progress.origin {
            Image(systemName: origin == "schedule" ? "clock" : "iphone")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(Theme.inkSoft)
        }
    }

    /// Ended or held up: said by the same soft disc as the cards'.
    private var mark: Notice.Kind? {
        if progress.isFailed { return .error }
        if progress.isWaiting { return .info }
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

    /// One part per phase, each filling on its own; a failed one in red.
    private var segments: some View {
        HStack(spacing: 4) {
            ForEach(Array(DisplayProgress.phases.indices), id: \.self) { index in
                let fill = progress.phaseFill(index)
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule().fill(Theme.ink.opacity(0.1))
                        if fill > 0 {
                            Capsule()
                                .fill(progress.isFailed && index == progress.phaseIndex ? Theme.bad : Theme.ink)
                                .frame(width: max(5, geo.size.width * fill))
                        }
                    }
                }
                .frame(height: 5)
                .animation(.linear(duration: 1), value: fill)
            }
        }
    }

    private var phases: some View {
        HStack(spacing: 4) {
            ForEach(Array(DisplayProgress.phases.enumerated()), id: \.offset) { index, phase in
                let current = progress.phaseIndex
                let done = current.map { index < $0 } ?? false
                let now = current == index && progress.active
                HStack(spacing: 3) {
                    if done {
                        Image(systemName: "checkmark")
                            .font(.system(size: 8, weight: .bold))
                    }
                    Text(phase.label)
                        .lineLimit(1)
                        .minimumScaleFactor(0.85)
                }
                .font(.caption.weight(now ? .semibold : .regular))
                .foregroundStyle(now ? Theme.ink : done ? Theme.inkSoft : Theme.inkSoft.opacity(0.55))
                .frame(maxWidth: .infinity, alignment: .leading)
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
                fraction: 0.38, phaseFraction: 0.4
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
