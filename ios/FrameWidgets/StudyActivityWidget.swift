import ActivityKit
import SwiftUI
import WidgetKit

/// A study of a work being written, on the Lock Screen and in the Dynamic
/// Island: what Claude does now, a bar that moves on by itself towards the
/// end the server expects, its four steps as on the app's card, and at the
/// end "Gotowe", which opens the study when tapped.
struct StudyActivityWidget: Widget {
    typealias State = StudyActivityAttributes.ContentState

    var body: some WidgetConfiguration {
        ActivityConfiguration(for: StudyActivityAttributes.self) { context in
            StudyLockScreenCard(
                title: context.attributes.title, picture: context.attributes.picture,
                state: context.state, stale: context.isStale
            )
                .activityBackgroundTint(Palette.paper)
                .activitySystemActionForegroundColor(Palette.ink)
                .widgetURL(context.state.isReady ? context.attributes.url : nil)
        } dynamicIsland: { context in
            let state = context.state
            return DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    ActivityThumb(data: context.attributes.picture, height: 40, ground: .black) {
                        StudyMark(state: state, island: true)
                    }
                    .font(.title2)
                    .padding(.leading, 4)
                }
                DynamicIslandExpandedRegion(.center) {
                    Text(StudyText.title(context.attributes.title))
                        .font(.subheadline.weight(.semibold))
                        .lineLimit(1)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(StudyText.line(state, stale: context.isStale))
                            .font(.footnote)
                            .foregroundStyle(.white.opacity(0.75))
                            .lineLimit(2)
                        StudyBar(state: state, ink: .white, soft: .white.opacity(0.6))
                        StudySteps(state: state, on: .white, off: .white.opacity(0.45))
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 4)
                }
            } compactLeading: {
                ActivityPictureOnly(
                    data: context.attributes.picture, height: 22,
                    fallback: "sparkles", tint: StudyText.islandTint(state)
                )
            } compactTrailing: {
                StudyCompact(state: state)
            } minimal: {
                StudyMark(state: state, island: true)
            }
            .keylineTint(StudyText.islandTint(state))
            // Ready: a tap opens the study; until then just the app.
            .widgetURL(state.isReady ? context.attributes.url : nil)
        }
    }
}

/// The Lock Screen card: the work, what goes on, the bar and the four steps.
private struct StudyLockScreenCard: View {
    let title: String
    let picture: Data?
    let state: StudyActivityAttributes.ContentState
    let stale: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: picture == nil ? .firstTextBaseline : .center, spacing: picture == nil ? 8 : 12) {
                ActivityThumb(data: picture, height: 44) {
                    StudyMark(state: state, island: false)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(StudyText.title(title))
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(Palette.ink)
                        .lineLimit(1)
                    Text(StudyText.line(state, stale: stale))
                        .font(.footnote)
                        .foregroundStyle(Palette.inkSoft)
                        .lineLimit(2)
                }
                Spacer(minLength: 0)
            }
            StudyBar(state: state, ink: Palette.ink, soft: Palette.inkSoft)
            StudySteps(state: state, on: Palette.ink, off: Palette.inkSoft)
        }
        .padding(16)
    }
}

/// The steps: done ones ticked, the one under way in bold.
private struct StudySteps: View {
    let state: StudyActivityAttributes.ContentState
    let on: Color
    let off: Color

    var body: some View {
        HStack(spacing: 0) {
            ForEach(Array(StudyActivityAttributes.ContentState.steps.enumerated()), id: \.offset) { index, step in
                if index > 0 { Spacer(minLength: 6) }
                let current = state.stepIndex
                let done = current.map { index < $0 } ?? false
                let now = current == index && state.isActive
                HStack(spacing: 4) {
                    Image(systemName: done ? "checkmark" : now ? "circle.fill" : "circle")
                        .font(.system(size: done ? 9 : 6, weight: .bold))
                    Text(step.label)
                }
                .font(.caption2.weight(now ? .semibold : .regular))
                .foregroundStyle(now ? on : done ? off : off.opacity(0.55))
            }
        }
    }
}

/// The bar while Claude writes it: it fills by itself towards the end the
/// server expects (moved on at each push), the time since it began under
/// it on the left and the whole, about, on the right. Nothing while it
/// waits, nor from a server before 1.118.0.
private struct StudyBar: View {
    let state: StudyActivityAttributes.ContentState
    let ink: Color
    let soft: Color

    var body: some View {
        if let range = state.timerRange {
            VStack(spacing: 4) {
                ProgressView(timerInterval: range, countsDown: false) {
                    EmptyView()
                } currentValueLabel: {
                    EmptyView()
                }
                .progressViewStyle(.linear)
                .tint(ink)
                HStack {
                    Text(range.lowerBound, style: .timer)
                        .monospacedDigit()
                    Spacer(minLength: 8)
                    if let whole = state.aboutWhole { Text(whole) }
                }
                .font(.caption2)
                .foregroundStyle(soft)
            }
        }
    }
}

/// The AI sparkles while it is written, then the result.
private struct StudyMark: View {
    let state: StudyActivityAttributes.ContentState
    let island: Bool

    var body: some View {
        Image(systemName: state.isReady ? "checkmark.circle.fill" : state.isFailed ? "xmark.circle.fill" : "sparkles")
            .foregroundStyle(island ? StudyText.islandTint(state) : StudyText.tint(state))
    }
}

/// The island's trailing mark: a ring filling towards the expected end,
/// the step (1/4 …) without one, or the result.
private struct StudyCompact: View {
    let state: StudyActivityAttributes.ContentState

    var body: some View {
        if let range = state.timerRange {
            ProgressView(timerInterval: range, countsDown: false) {
                EmptyView()
            } currentValueLabel: {
                EmptyView()
            }
            .progressViewStyle(.circular)
            .tint(StudyText.islandTint(state))
            .frame(width: 20, height: 20)
        } else if state.isActive {
            Text(state.stepIndex.map { "\($0 + 1)/\(StudyActivityAttributes.ContentState.steps.count)" } ?? "…")
                .font(.caption2.weight(.semibold).monospacedDigit())
                .foregroundStyle(StudyText.islandTint(state))
        } else {
            StudyMark(state: state, island: true)
        }
    }
}

private enum StudyText {
    static func title(_ title: String) -> String {
        title.isEmpty ? "Studium dzieła" : "Studium: „\(title)”"
    }

    static func line(_ state: StudyActivityAttributes.ContentState, stale: Bool) -> String {
        if stale, state.isActive { return "Otwórz aplikację, żeby sprawdzić, jak idzie" }
        return state.line
    }

    /// Ink (white in the dark) while under way, green once ready, as the
    /// send card.
    static func tint(_ state: StudyActivityAttributes.ContentState) -> Color {
        state.isReady ? Palette.good : Palette.ink
    }

    /// The island is always black: white, green once ready.
    static func islandTint(_ state: StudyActivityAttributes.ContentState) -> Color {
        state.isReady ? Color(hex: 0x7CC49A) : .white
    }
}
