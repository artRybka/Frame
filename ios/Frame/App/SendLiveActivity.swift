import ActivityKit
import UIKit

/// The bar following a picture to the frame, mirrored on the Lock Screen and
/// in the Dynamic Island for when the phone goes back in the pocket. The app
/// keeps it up to date while it runs; its push token goes to the server
/// (`onToken`), which moves it on and ends it with the app asleep too
/// (notifications.py `push_send`). Without push the bar moves on by itself
/// towards the end the server expects, and the result comes when the app is
/// back (`AppModel.settleLiveActivity`).
@MainActor
final class SendLiveActivity {
    typealias State = SendActivityAttributes.ContentState

    private var activity: Activity<SendActivityAttributes>?
    /// The card being started: its picture is on its way.
    private var starting: String?
    /// The work's small picture for the card (`ActivityPicture`), set by the model.
    var picture: ((String) async -> Data?)?
    /// Leaves the card's push token on the server, with its picture's title.
    var onToken: ((_ title: String, _ token: String) async -> Void)?
    private var watching: Task<Void, Never>?
    private var watchedID: String?

    init() {
        // One left from before the app was closed, still under way.
        activity = Activity<SendActivityAttributes>.activities.first {
            $0.activityState == .active || $0.activityState == .stale
        }
    }

    /// The card left from before the app was closed: its token goes to the
    /// server again (set once `onToken` is).
    func watchToken() {
        if let activity, watchedID != activity.id { watchToken(activity) }
    }

    var isRunning: Bool {
        guard let activity else { return false }
        return activity.activityState == .active || activity.activityState == .stale
    }

    /// A run under way: starts the card (only possible with the app open) or
    /// moves it on.
    func show(_ progress: DisplayProgress) async {
        let stale = progress.secondsLeft.map { Date.now.addingTimeInterval(Double($0) + 90) }
        await put(State(progress), title: progress.title, itemID: progress.itemId, stale: stale)
    }

    /// The picture waits for the frame to wake; `until`: its alarm (ISO).
    func wait(_ progress: DisplayProgress, until: String?) async {
        var state = State(progress)
        state.wakes = When.at(until)
        let stale = When.date(until).map { $0.addingTimeInterval(15 * 60) }
        await put(state, title: progress.title, itemID: progress.itemId, stale: stale)
    }

    /// How long a result stays on the Lock Screen once the run is over:
    /// "Obraz jest na ramce" just long enough to be seen, a failure long
    /// enough to read why. Then iOS takes the card away by itself.
    static let doneFor: TimeInterval = 15
    static let failedFor: TimeInterval = 5 * 60

    /// The run ended: its result stays on the Lock Screen briefly, then goes
    /// by itself; with nothing to say (idle) the card goes at once.
    func finish(_ progress: DisplayProgress) {
        guard let activity else { return }
        self.activity = nil
        let result = progress.isDone || progress.isFailed
        let content = ActivityContent(state: State(progress), staleDate: nil)
        let policy: ActivityUIDismissalPolicy = result
            ? .after(.now.addingTimeInterval(progress.isDone ? Self.doneFor : Self.failedFor)) : .immediate
        Task { await activity.end(result ? content : nil, dismissalPolicy: policy) }
    }

    /// Cards that should no longer be on the Lock Screen, cleared when the
    /// app is back: results whose time is up but still shown, and cards
    /// left behind by an earlier run of the app (only one is followed).
    func tidy() {
        for card in Activity<SendActivityAttributes>.activities where card.id != activity?.id {
            Task { await card.end(nil, dismissalPolicy: .immediate) }
        }
    }

    private func put(_ state: State, title: String, itemID: String?, stale: Date?) async {
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
        guard ActivityAuthorizationInfo().areActivitiesEnabled, starting != title else { return }
        starting = title
        defer { starting = nil }
        var image: Data?
        if let itemID, let picture { image = await picture(itemID) }
        if let activity, isRunning, activity.attributes.title == title { return }  // started meanwhile
        // Pushed by the server too; without the push entitlement it still
        // runs while the app is open. Too big for ActivityKit: without the picture.
        var started: Activity<SendActivityAttributes>?
        for picture in image == nil ? [nil] : [image, nil] {
            let attributes = SendActivityAttributes(title: title, picture: picture)
            started = (try? Activity.request(attributes: attributes, content: content, pushType: .token))
                ?? (try? Activity.request(attributes: attributes, content: content))
            if started != nil { break }
        }
        activity = started
        if let started { watchToken(started) }
    }

    private func watchToken(_ activity: Activity<SendActivityAttributes>) {
        watching?.cancel()
        watchedID = activity.id
        let title = activity.attributes.title
        watching = Task { [weak self] in
            for await data in activity.pushTokenUpdates {
                if Task.isCancelled { return }
                let token = data.map { String(format: "%02x", $0) }.joined()
                await self?.onToken?(title, token)
            }
        }
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
/// half a minute), so the Lock Screen card keeps up with the server, or a
/// change sent to the server is answered.
@MainActor
final class BackgroundTime {
    private var id = UIBackgroundTaskIdentifier.invalid

    init(name: String = "progress") {
        id = UIApplication.shared.beginBackgroundTask(withName: name) { [weak self] in
            MainActor.assumeIsolated { self?.end() }
        }
    }

    func end() {
        guard id != .invalid else { return }
        UIApplication.shared.endBackgroundTask(id)
        id = .invalid
    }
}
