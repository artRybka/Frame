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
    /// Cards being started: their pictures are on the way.
    private var starting: Set<String> = []
    /// The work's small picture for the card (`ActivityPicture`), set by the model.
    var picture: ((String) async -> Data?)?

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
    func start(itemID: String, title: String, status: String) async {
        let state = State(status: status)
        guard state.isActive else { return }
        if activity(for: itemID) != nil {
            update(itemID: itemID, status: status)
            return
        }
        guard ActivityAuthorizationInfo().areActivitiesEnabled, !starting.contains(itemID) else { return }
        starting.insert(itemID)
        defer { starting.remove(itemID) }
        let image = await picture?(itemID)
        guard activity(for: itemID) == nil else { return }  // started meanwhile
        let content = ActivityContent(state: state, staleDate: .now.addingTimeInterval(Self.staleAfter))
        // Pushed by the server; without the push entitlement it still runs
        // while the app is open. Too big for ActivityKit: without the picture.
        var started: Activity<StudyActivityAttributes>?
        for picture in image == nil ? [nil] : [image, nil] {
            let attributes = StudyActivityAttributes(itemID: itemID, title: title, picture: picture)
            started = (try? Activity.request(attributes: attributes, content: content, pushType: .token))
                ?? (try? Activity.request(attributes: attributes, content: content))
            if started != nil { break }
        }
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

    /// Once over, how long the card stays on the Lock Screen before iOS
    /// takes it away: "Gotowe" (a tap opens it; the notification "Studium
    /// gotowe" stays in the Notification Centre), or why not. As the
    /// server's end push (notifications.py `STUDY_READY_FOR`, `STUDY_FAILED_FOR`).
    static let readyFor: TimeInterval = 2 * 60
    static let failedFor: TimeInterval = 5 * 60

    /// The study is over: its result stays on the Lock Screen briefly, then
    /// the card goes by itself.
    func finish(itemID: String, status: String, error: String? = nil) {
        guard let activity = activity(for: itemID) else { return }
        let state = State(status: status, error: error)
        let keep = state.isReady ? Self.readyFor : Self.failedFor
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

    /// The app is open again: finished cards still on the Lock Screen have
    /// done their job (the result is in the app).
    func tidy() {
        for activity in Activity<StudyActivityAttributes>.activities where !activity.content.state.isActive {
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
