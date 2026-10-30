import ActivityKit
import SwiftUI
import UIKit
import WidgetKit

@main
struct FrameWidgetsBundle: WidgetBundle {
    var body: some Widget {
        SendActivityWidget()
    }
}

/// A picture on its way to the frame, on the Lock Screen and in the Dynamic
/// Island: the same bar as in the app.
struct SendActivityWidget: Widget {
    typealias State = SendActivityAttributes.ContentState

    var body: some WidgetConfiguration {
        ActivityConfiguration(for: SendActivityAttributes.self) { context in
            LockScreenCard(title: context.attributes.title, state: context.state, stale: context.isStale)
                .activityBackgroundTint(Palette.paper)
                .activitySystemActionForegroundColor(Palette.ink)
        } dynamicIsland: { context in
            let state = context.state
            return DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Image(systemName: "photo.artframe")
                        .font(.title2)
                        .foregroundStyle(Palette.islandTint(state))
                        .padding(.leading, 4)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    TimeLeft(state: state)
                        .font(.callout.weight(.semibold).monospacedDigit())
                        .foregroundStyle(.white.opacity(0.8))
                        .padding(.trailing, 4)
                }
                DynamicIslandExpandedRegion(.center) {
                    Text(context.attributes.title.isEmpty ? "Obraz na ramkę" : "„\(context.attributes.title)”")
                        .font(.subheadline.weight(.semibold))
                        .lineLimit(1)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(Palette.line(state, stale: context.isStale))
                            .font(.footnote)
                            .foregroundStyle(.white.opacity(0.75))
                            .lineLimit(2)
                        if !state.isWaiting {
                            Bar(state: state, tint: Palette.islandTint(state), track: .white.opacity(0.2))
                        }
                    }
                    .padding(.horizontal, 4)
                }
            } compactLeading: {
                Image(systemName: "photo.artframe")
                    .foregroundStyle(Palette.islandTint(state))
            } compactTrailing: {
                CompactMark(state: state)
            } minimal: {
                CompactMark(state: state)
            }
            .keylineTint(Palette.islandTint(state))
        }
    }
}

/// The Lock Screen card: what goes on, the bar and its three parts.
private struct LockScreenCard: View {
    let title: String
    let state: SendActivityAttributes.ContentState
    let stale: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Image(systemName: icon)
                    .foregroundStyle(Palette.tint(state))
                VStack(alignment: .leading, spacing: 2) {
                    Text(title.isEmpty ? "Obraz na ramkę" : "„\(title)” na ramkę")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(Palette.ink)
                        .lineLimit(1)
                    Text(Palette.line(state, stale: stale))
                        .font(.footnote)
                        .foregroundStyle(Palette.inkSoft)
                        .lineLimit(2)
                }
                Spacer(minLength: 8)
                TimeLeft(state: state)
                    .font(.footnote.weight(.medium).monospacedDigit())
                    .foregroundStyle(Palette.inkSoft)
            }
            if !state.isWaiting {
                Bar(state: state, tint: Palette.tint(state), track: Palette.ink.opacity(0.1))
                phases
            }
        }
        .padding(16)
    }

    private var icon: String {
        if state.isDone { return "checkmark.circle.fill" }
        if state.isFailed { return "xmark.circle.fill" }
        if state.isWaiting { return "moon.zzz.fill" }
        return "photo.artframe"
    }

    private var phases: some View {
        HStack(spacing: 0) {
            ForEach(Array(SendActivityAttributes.ContentState.phases.enumerated()), id: \.offset) { index, phase in
                if index > 0 { Spacer(minLength: 6) }
                let current = state.phaseIndex
                let done = current.map { index < $0 } ?? false
                let now = current == index && state.isActive
                HStack(spacing: 4) {
                    Image(systemName: done ? "checkmark" : now ? "circle.fill" : "circle")
                        .font(.system(size: done ? 9 : 6, weight: .bold))
                    Text(phase.label)
                }
                .font(.caption2.weight(now ? .semibold : .regular))
                .foregroundStyle(now ? Palette.ink : done ? Palette.inkSoft : Palette.inkSoft.opacity(0.55))
            }
        }
    }
}

/// The bar: moving by itself towards the end the server expects, or
/// standing where it was last heard.
private struct Bar: View {
    let state: SendActivityAttributes.ContentState
    let tint: Color
    let track: Color

    var body: some View {
        if let range = state.timerRange {
            ProgressView(timerInterval: range, countsDown: false) {
                EmptyView()
            } currentValueLabel: {
                EmptyView()
            }
            .progressViewStyle(.linear)
            .tint(tint)
        } else {
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(track)
                    Capsule()
                        .fill(tint)
                        .frame(width: max(6, geo.size.width * min(max(state.fraction, 0), 1)))
                }
            }
            .frame(height: 6)
        }
    }
}

/// Time left while under way, nothing otherwise.
private struct TimeLeft: View {
    let state: SendActivityAttributes.ContentState

    var body: some View {
        if let range = state.timerRange {
            Text(timerInterval: range, countsDown: true)
                .multilineTextAlignment(.trailing)
                .frame(maxWidth: 56, alignment: .trailing)
        }
    }
}

/// The small trailing mark in the island: time left, or the result.
private struct CompactMark: View {
    let state: SendActivityAttributes.ContentState

    var body: some View {
        if state.isDone {
            Image(systemName: "checkmark.circle.fill").foregroundStyle(Palette.islandTint(state))
        } else if state.isFailed {
            Image(systemName: "xmark.circle.fill").foregroundStyle(Palette.islandTint(state))
        } else if state.isWaiting {
            Image(systemName: "moon.zzz.fill").foregroundStyle(Palette.islandTint(state))
        } else if let range = state.timerRange {
            Text(timerInterval: range, countsDown: true)
                .font(.caption2.weight(.semibold).monospacedDigit())
                .foregroundStyle(Palette.islandTint(state))
                .frame(width: 36)
        } else {
            Image(systemName: "arrow.up.circle").foregroundStyle(Palette.islandTint(state))
        }
    }
}

/// The app's colours (`Theme`), for the extension.
private enum Palette {
    static let paper = dynamic(light: 0xF5F1EA, dark: 0x1D1B19)
    static let ink = dynamic(light: 0x1D1B18, dark: 0xF1ECE4)
    static let inkSoft = dynamic(light: 0x6E675E, dark: 0xA79F94)
    static let vermilion = dynamic(light: 0xB8432F, dark: 0xE58A6F)
    static let good = dynamic(light: 0x3E7B56, dark: 0x7CC49A)
    static let warn = dynamic(light: 0xB7832A, dark: 0xE2B45E)

    static func tint(_ state: SendActivityAttributes.ContentState) -> Color {
        if state.isDone { return good }
        if state.isWaiting { return warn }
        return vermilion  // also failed: the app's "bad" is the same vermilion
    }

    /// The island is always black: the dark variants.
    static func islandTint(_ state: SendActivityAttributes.ContentState) -> Color {
        if state.isDone { return Color(hex: 0x7CC49A) }
        if state.isWaiting { return Color(hex: 0xE2B45E) }
        return Color(hex: 0xE58A6F)
    }

    /// The line under the title.
    static func line(_ state: SendActivityAttributes.ContentState, stale: Bool) -> String {
        if state.isWaiting {
            return state.wakes.map { "Czeka na ramkę, obudzi się \($0)" } ?? "Obraz poczeka, aż ramka się obudzi"
        }
        if stale, state.isActive { return "Otwórz aplikację, żeby sprawdzić, czy dotarł" }
        return state.label
    }

    private static func dynamic(light: UInt32, dark: UInt32) -> Color {
        Color(uiColor: UIColor { $0.userInterfaceStyle == .dark ? UIColor(hex: dark) : UIColor(hex: light) })
    }
}

private extension UIColor {
    convenience init(hex: UInt32) {
        self.init(
            red: CGFloat((hex >> 16) & 0xFF) / 255,
            green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255,
            alpha: 1
        )
    }
}

private extension Color {
    init(hex: UInt32) {
        self.init(uiColor: UIColor(hex: hex))
    }
}
