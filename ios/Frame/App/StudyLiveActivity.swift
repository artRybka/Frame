import ActivityKit
import Foundation

/// A study being written ("Przygotuj studium dzieła"), followed on the Lock
/// Screen and in the Dynamic Island. Started by the app as it asks for the
/// study; each activity's push token goes to the server (`onToken`), which
/// pushes every step to it, so it moves on and ends with the app closed.
/// While the app runs it moves it on too, from what it hears itself.
@MainActor
final class StudyLiveActivity {
    typealias State = StudyActivityAttributes.ContentState

    /// With no word for this long the card says to open the app (as the
    /// server's pushes do, notifications.py `STUDY_STALE`).
    static let staleAfter: TimeInterval = 15 * 60

    /// Leaves an activity's push token on the server (it may change).
    var onToken: ((_ itemID: String, _ token: String) async -> Void)?

    private var watching: [String: Task<Void, Never>] = [:]

    /// The cards still under way (not ended), by work.
    var running: [Activity<StudyActivityAttributes>] {
        Activity<StudyActivityAttributes>.activities.filter {
            $0.activityState == .active || $0.activityState == .stale
        }
    }

    private func activity(for itemID: String) -> Activity<StudyActivityAttributes>? {
        running.first { $0.attributes.itemID == itemID }
    }

    /// The card for a study on its way (only possible with the app open),
    /// or the one already there moved on.
    func start(itemID: String, title: String, status: String) {
        let state = State(status: status)
        guard state.isActive else { return }
        if activity(for: itemID) != nil {
            update(itemID: itemID, status: status)
            return
        }
        guard ActivityAuthorizationInfo().areActivitiesEnabled else { return }
        let attributes = StudyActivityAttributes(itemID: itemID, title: title)
        let content = ActivityContent(state: state, staleDate: .now.addingTimeInterval(Self.staleAfter))
        // Pushed by the server; without the push entitlement it still runs
        // while the app is open.
        let started = (try? Activity.request(attributes: attributes, content: content, pushType: .token))
            ?? (try? Activity.request(attributes: attributes, content: content))
        if let started { watchToken(started) }
    }

    /// A step heard by the app; a result ends the card (`finish`).
    func update(itemID: String, status: String, error: String? = nil) {
        let state = State(status: status, error: error)
        guard state.isActive else {
            finish(itemID: itemID, status: status, error: error)
            return
        }
        guard let activity = activity(for: itemID), activity.content.state != state else { return }
        let content = ActivityContent(state: state, staleDate: .now.addingTimeInterval(Self.staleAfter))
        Task { await activity.update(content) }
    }

    /// The study is over: "Gotowe" stays on the Lock Screen for an hour
    /// (a tap opens it), a failure a quarter.
    func finish(itemID: String, status: String, error: String? = nil) {
        guard let activity = activity(for: itemID) else { return }
        let state = State(status: status, error: error)
        let keep: TimeInterval = state.isReady ? 60 * 60 : 15 * 60
        Task {
            await activity.end(
                ActivityContent(state: state, staleDate: nil),
                dismissalPolicy: .after(.now.addingTimeInterval(keep))
            )
        }
    }

    /// The study is open in the app: its finished card has done its job.
    func dismiss(itemID: String) {
        for activity in Activity<StudyActivityAttributes>.activities
        where activity.attributes.itemID == itemID && !activity.content.state.isActive {
            Task { await activity.end(nil, dismissalPolicy: .immediate) }
        }
    }

    /// Cards left from before the app was closed: their tokens go to the
    /// server again (it may have restarted, or the token changed).
    func watchTokens() {
        for activity in running { watchToken(activity) }
    }

    private func watchToken(_ activity: Activity<StudyActivityAttributes>) {
        let id = activity.id
        guard watching[id] == nil else { return }
        let itemID = activity.attributes.itemID
        watching[id] = Task { [weak self] in
            for await data in activity.pushTokenUpdates {
                let token = data.map { String(format: "%02x", $0) }.joined()
                await self?.onToken?(itemID, token)
            }
            self?.watching[id] = nil
        }
    }
}
