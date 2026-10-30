import ActivityKit
import UIKit

/// The bar following a picture to the frame, mirrored on the Lock Screen and
/// in the Dynamic Island for when the phone goes back in the pocket. The app
/// keeps it up to date while it runs; asleep, the bar moves on by itself
/// towards the end the server expects, and the result comes when the app is
/// back (`AppModel.settleLiveActivity`).
@MainActor
final class SendLiveActivity {
    typealias State = SendActivityAttributes.ContentState

    private var activity: Activity<SendActivityAttributes>?

    init() {
        // One left from before the app was closed.
        activity = Activity<SendActivityAttributes>.activities.first
    }

    var isRunning: Bool {
        guard let activity else { return false }
        return activity.activityState == .active || activity.activityState == .stale
    }

    /// A run under way: starts the card (only possible with the app open) or
    /// moves it on.
    func show(_ progress: DisplayProgress) {
        put(State(progress), title: progress.title, stale: progress.secondsLeft.map { .now.addingTimeInterval(Double($0) + 90) })
    }

    /// The picture waits for the frame to wake; `until`: its alarm (ISO).
    func wait(_ progress: DisplayProgress, until: String?) {
        var state = State(progress)
        state.wakes = When.at(until)
        put(state, title: progress.title, stale: When.date(until).map { $0.addingTimeInterval(15 * 60) })
    }

    /// The run ended: its result stays on the Lock Screen for a while; with
    /// nothing to say (idle) the card just goes.
    func finish(_ progress: DisplayProgress) {
        guard let activity else { return }
        self.activity = nil
        let result = progress.isDone || progress.isFailed
        let content = ActivityContent(state: State(progress), staleDate: nil)
        let policy: ActivityUIDismissalPolicy = result
            ? .after(.now.addingTimeInterval(progress.isDone ? 5 * 60 : 30 * 60)) : .immediate
        Task { await activity.end(result ? content : nil, dismissalPolicy: policy) }
    }

    private func put(_ state: State, title: String, stale: Date?) {
        let content = ActivityContent(state: state, staleDate: stale)
        if let activity, isRunning {
            if activity.attributes.title == title {
                Task { await activity.update(content) }
                return
            }
            // Another picture now: the old card goes.
            Task { await activity.end(nil, dismissalPolicy: .immediate) }
            self.activity = nil
        }
        guard ActivityAuthorizationInfo().areActivitiesEnabled else { return }
        activity = try? Activity.request(attributes: SendActivityAttributes(title: title), content: content)
    }
}

extension SendActivityAttributes.ContentState {
    init(_ progress: DisplayProgress) {
        self.init(
            stage: progress.stage,
            phase: progress.phase,
            label: progress.stageLabel,
            fraction: progress.isDone ? 1 : progress.fraction,
            heardAt: .now,
            expectedEnd: progress.active ? progress.secondsLeft.map { .now.addingTimeInterval(Double($0)) } : nil
        )
    }
}

/// A little more time when the app goes away in the middle of a run (about
/// half a minute), so the Lock Screen card keeps up with the server.
@MainActor
final class BackgroundTime {
    private var id = UIBackgroundTaskIdentifier.invalid

    init() {
        id = UIApplication.shared.beginBackgroundTask(withName: "progress") { [weak self] in
            MainActor.assumeIsolated { self?.end() }
        }
    }

    func end() {
        guard id != .invalid else { return }
        UIApplication.shared.endBackgroundTask(id)
        id = .invalid
    }
}
