import Foundation

/// Studies of works ("Przygotuj studium dzieła" on a work's card): Claude
/// writes the work of the day's page for the work, in a minute or three.
/// A card at the bottom follows it wherever the app goes, says each step and
/// at the end opens the study when tapped; the same on the Lock Screen and
/// in the Dynamic Island (`StudyLiveActivity`), pushed on by the server
/// while the app is closed.
extension AppModel {
    /// Asks for the work's study (`again`: a new one) and follows it.
    func prepareStudy(itemID: String, title: String, again: Bool = false) async {
        guard studyCards[itemID] == nil else { return }
        let card = beginStudyCard(itemID: itemID, title: title)
        do {
            let view = try await backend.prepareStudy(itemID: itemID, again: again, later: false)
            await studyActivity.start(itemID: itemID, title: title, state: view.activityState)
            await followStudy(itemID: itemID, title: title, from: view, card: card)
        } catch {
            studyCards[itemID] = nil
            notices.fail(error, in: card)
        }
    }

    /// Orders the work's study for later, for less ("Przygotuj na później"):
    /// Claude's long questions go through Anthropic's batches at half the
    /// price, mostly within minutes to hours. No card follows it; the server
    /// says "Studium gotowe" in a notification when it is.
    func orderStudyLater(itemID: String, title: String) async {
        guard studyCards[itemID] == nil else { return }
        do {
            let view = try await backend.prepareStudy(itemID: itemID, again: false, later: true)
            studies[itemID] = view
            switch view.status {
            case "later":
                notices.done("Studium zamówione na później", "„\(title)” · dam znać powiadomieniem, gdy będzie gotowe")
            case "ready":
                notices.done("Studium dzieła gotowe", "„\(title)”")
            case "off":
                notices.warn("Claude jest wyłączony", "Dodaj klucz API w Konfiguracji.")
            default:
                // A server from before "na później" makes it now: followed as usual.
                if view.isPending {
                    await resumeStudy(itemID: itemID, title: title, view: view)
                }
            }
        } catch {
            notices.fail(error)
        }
    }

    /// A study found on its way as the card opened (asked before the app
    /// was closed): followed on a card too.
    func resumeStudy(itemID: String, title: String, view: StudyView) async {
        studies[itemID] = view
        guard view.isPending, studyCards[itemID] == nil else { return }
        await studyActivity.start(itemID: itemID, title: title, state: view.activityState)
        let card = beginStudyCard(itemID: itemID, title: title)
        await followStudy(itemID: itemID, title: title, from: view, card: card)
    }

    /// The study, from a tap on "Studium gotowe": on the work's card when it
    /// is on top, else over whatever is open.
    func openStudy(itemID: String) {
        if topCard == itemID {
            studyOnCard = itemID
        } else {
            studySheet = itemID
        }
    }

    /// The study is on screen: the card saying it is ready has done its job.
    func studyOpened(itemID: String) {
        if let card = studyReadyCards.removeValue(forKey: itemID) { notices.close(card) }
        studyActivity.dismiss(itemID: itemID)
    }

    /// The Lock Screen card's push token, on the server (`StudyLiveActivity.onToken`).
    func followStudyOnLockScreen(itemID: String, token: String) async {
        try? await backend.followStudy(itemID: itemID, activityToken: token, sandbox: PushCenter.sandbox)
    }

    /// Lock Screen cards of studies asked for before the app was closed:
    /// followed again while still on their way (with the card at the bottom
    /// too), ended with the result otherwise, in case no push said it.
    func settleStudyActivities() async {
        studyActivity.watchTokens()
        for activity in studyActivity.running {
            let itemID = activity.attributes.itemID
            guard studyCards[itemID] == nil else { continue }
            guard let view = try? await backend.study(itemID: itemID, wait: 0) else { continue }
            if view.isPending {
                Task { await resumeStudy(itemID: itemID, title: activity.attributes.title, view: view) }
            } else {
                studies[itemID] = view
                studyActivity.finish(itemID: itemID, status: Self.studyResult(view.status), error: view.error)
            }
        }
    }

    /// The server's word for a study that is no longer on its way, as the
    /// Lock Screen card says it: "none" means the server lost it.
    private static func studyResult(_ status: String) -> String {
        status == "none" ? "stopped" : status
    }

    // MARK: Private

    private func beginStudyCard(itemID: String, title: String) -> Notice.ID {
        if let ready = studyReadyCards.removeValue(forKey: itemID) { notices.close(ready) }
        let waiting = StudyActivityAttributes.ContentState(status: "waiting", part: "waiting")
        let card = notices.begin(Self.studyStep(waiting), Self.studyDetail(title, state: waiting))
        studyCards[itemID] = card
        studies[itemID]?.status = "waiting"
        return card
    }

    /// Asks where the study is until it is ready (a few misses, e.g. the
    /// network after the app was away, are waited out); the card says each step.
    private func followStudy(itemID: String, title: String, from first: StudyView, card: Notice.ID) async {
        defer { studyCards[itemID] = nil }
        var view = first
        var misses = 0
        studies[itemID] = view
        while view.isPending {
            let state = view.activityState
            notices.update(
                card, title: Self.studyStep(state), detail: Self.studyDetail(title, state: state),
                count: Self.studyCount(state), span: .some(state.timerRange)
            )
            studyActivity.update(itemID: itemID, state: state)
            do {
                // Back sooner while Claude writes it: "jeszcze ok. …" moves on.
                view = try await backend.study(itemID: itemID, wait: state.timerRange == nil ? 25 : 10)
                misses = 0
                studies[itemID] = view
            } catch let error where !error.isCancellation && misses < 6 {
                misses += 1
                try? await Task.sleep(for: .seconds(5))
            } catch {
                notices.fail(error, in: card)
                return
            }
        }
        studyActivity.finish(itemID: itemID, status: Self.studyResult(view.status), error: view.error)
        switch view.status {
        case "ready":
            notices.end(
                card, .done, "Studium dzieła gotowe", "„\(title)”",
                action: Notice.Action(label: "Otwórz") { [weak self] in self?.openStudy(itemID: itemID) }
            )
            studyReadyCards[itemID] = card
            await loadStudyList(backend)  // first in "Studia dzieł"
        case "failed":
            notices.end(card, .error, "Nie udało się przygotować studium", view.error.isEmpty ? nil : view.error)
        case "off":
            notices.end(card, .warning, "Claude jest wyłączony", "Dodaj klucz API w Konfiguracji.")
        default:
            notices.end(card, .warning, "Studium przerwane", "Serwer przestał je pisać, np. po ponownym uruchomieniu. Spróbuj jeszcze raz.")
        }
    }

    /// What goes on now, as the Lock Screen says it.
    private static func studyStep(_ state: StudyActivityAttributes.ContentState) -> String {
        if let part = state.part, let line = StudyActivityAttributes.ContentState.partLines[part] { return line }
        switch state.status {
        case "sources": return "Zbieram źródła"
        case "writing": return "Claude pisze studium"
        case "details": return "Wycinam detale z oryginału"
        default: return "Czekam na Claude’a"
        }
    }

    /// "3 z 4" at the card's end, as the Lock Screen counts the steps.
    private static func studyCount(_ state: StudyActivityAttributes.ContentState) -> String {
        guard let index = state.stepIndex, index < StudyActivityAttributes.ContentState.steps.count else { return "" }
        return "\(index + 1) z \(StudyActivityAttributes.ContentState.steps.count)"
    }

    /// The work and how long it has left: "„Uliczka” · jeszcze ok. 1½ min",
    /// "trwa dłużej niż zwykle" once past the end the server expected.
    nonisolated static func studyDetail(_ title: String, state: StudyActivityAttributes.ContentState, now: Date = .now) -> String {
        if let range = state.timerRange {
            let left = range.upperBound.timeIntervalSince(now)
            if left <= 0 { return "„\(title)” · trwa dłużej niż zwykle" }
            return "„\(title)” · jeszcze ok. \(StudyActivityAttributes.ContentState.about(left))"
        }
        switch state.status {
        case "sources" where state.part == nil: return "„\(title)” · muzeum, Wikidata, Wikipedia"
        case "writing" where state.part == nil: return "„\(title)” · zwykle 1–3 minuty"
        default: return "„\(title)”"
        }
    }
}
