import SwiftUI

/// A study opened while it is still being prepared: in place of its text,
/// composition and details, only that it is on its way, with the same
/// progress as the Lock Screen card (what goes on now, the bar towards the
/// end the server expects, the four steps). Mateusz 2026-11-15: "W sytuacji
/// gdy ktoś wcześniej wejdzie w studium w trakcie opracowania nie pokazuj
/// ani treści, ani kompozycji tylko informacje o tym że studium dzieła jest
/// w trakcie opracowania" (variant A of the sketch: the picture and the
/// title stay above it).
struct StudyComingCard: View {
    typealias State = StudyActivityAttributes.ContentState

    let state: State

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 14) {
                Text("Studium dzieła\nw trakcie opracowania")
                    .font(.serif(21, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                    .fixedSize(horizontal: false, vertical: true)
                HStack(spacing: 9) {
                    ProgressView().controlSize(.small)
                    Text(state.line)
                        .font(.subheadline)
                        .foregroundStyle(Theme.inkSoft)
                        .contentTransition(.opacity)
                }
                .animation(.easeInOut(duration: 0.3), value: state.line)
                if let range = state.timerRange { bar(range) }
                steps
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.card, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(Theme.hairline))
            Text("Otworzy się tutaj samo, gdy będzie gotowe. Możesz wyjść: dam znać powiadomieniem.")
                .font(.footnote)
                .foregroundStyle(Theme.inkSoft)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 4)
        }
        .padding(.top, 20)
        .accessibilityElement(children: .combine)
    }

    /// Fills by itself towards the expected end; the time since it began
    /// on the left, what is left, about, on the right.
    private func bar(_ range: ClosedRange<Date>) -> some View {
        VStack(spacing: 6) {
            ProgressView(timerInterval: range, countsDown: false) {
                EmptyView()
            } currentValueLabel: {
                EmptyView()
            }
            .progressViewStyle(.linear)
            .tint(Theme.ink)
            HStack {
                Text(range.lowerBound, style: .timer)
                    .monospacedDigit()
                Spacer(minLength: 8)
                TimelineView(.periodic(from: .now, by: 15)) { context in
                    Text(Self.left(range, now: context.date))
                }
            }
            .font(.caption)
            .foregroundStyle(Theme.inkSoft)
        }
    }

    /// "jeszcze ok. 1½ min", "trwa dłużej niż zwykle" past the expected end.
    nonisolated static func left(_ range: ClosedRange<Date>, now: Date) -> String {
        let left = range.upperBound.timeIntervalSince(now)
        return left <= 0 ? "trwa dłużej niż zwykle" : "jeszcze ok. \(State.about(left))"
    }

    /// Źródła · Tekst · Kompozycja · Detale, as on the Lock Screen.
    private var steps: some View {
        HStack(spacing: 0) {
            ForEach(Array(State.steps.enumerated()), id: \.offset) { index, step in
                if index > 0 { Spacer(minLength: 6) }
                let current = state.stepIndex
                let done = current.map { index < $0 } ?? false
                let now = current == index && state.isActive
                HStack(spacing: 4) {
                    Image(systemName: done ? "checkmark" : now ? "circle.fill" : "circle")
                        .font(.system(size: done ? 9 : 6, weight: .bold))
                    Text(step.label)
                }
                .font(.caption.weight(now ? .semibold : .regular))
                .foregroundStyle(now ? Theme.ink : done ? Theme.inkSoft : Theme.inkSoft.opacity(0.55))
            }
        }
    }
}
