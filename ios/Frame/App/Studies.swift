import Foundation

/// Studies of works ("Przygotuj studium dzieła" on a work's card): Claude
/// writes the work of the day's page for the work, in a minute or three.
/// A card at the bottom follows it wherever the app goes, says each step and
/// at the end opens the study when tapped.
extension AppModel {
    /// Asks for the work's study (`again`: a new one) and follows it.
    func prepareStudy(itemID: String, title: String, again: Bool = false) async {
        guard studyCards[itemID] == nil else { return }
        let card = beginStudyCard(itemID: itemID, title: title)
        do {
            let view = try await backend.prepareStudy(itemID: itemID, again: again)
            await followStudy(itemID: itemID, title: title, from: view, card: card)
        } catch {
            studyCards[itemID] = nil
            notices.fail(error, in: card)
        }
    }

    /// A study found on its way as the card opened (asked before the app
    /// was closed): followed on a card too.
    func resumeStudy(itemID: String, title: String, view: StudyView) async {
        studies[itemID] = view
        guard view.isPending, studyCards[itemID] == nil else { return }
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
    }

    // MARK: Private

    private func beginStudyCard(itemID: String, title: String) -> Notice.ID {
        if let ready = studyReadyCards.removeValue(forKey: itemID) { notices.close(ready) }
        let card = notices.begin(Self.studyStep("waiting"), Self.studyDetail(title, step: "waiting"))
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
            notices.update(card, title: Self.studyStep(view.status), detail: Self.studyDetail(title, step: view.status))
            do {
                view = try await backend.study(itemID: itemID, wait: 25)
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
        switch view.status {
        case "ready":
            notices.end(
                card, .done, "Studium dzieła gotowe", "„\(title)”",
                action: Notice.Action(label: "Otwórz") { [weak self] in self?.openStudy(itemID: itemID) }
            )
            studyReadyCards[itemID] = card
        case "failed":
            notices.end(card, .error, "Nie udało się przygotować studium", view.error.isEmpty ? nil : view.error)
        case "off":
            notices.end(card, .warning, "Claude jest wyłączony", "Dodaj klucz API w Konfiguracji.")
        default:
            notices.end(card, .warning, "Studium przerwane", "Serwer przestał je pisać, np. po ponownym uruchomieniu. Spróbuj jeszcze raz.")
        }
    }

    private static func studyStep(_ status: String) -> String {
        switch status {
        case "sources": "Studium dzieła: zbieram źródła"
        case "writing": "Claude pisze studium dzieła"
        case "details": "Wycinam detale z oryginału"
        default: "Studium dzieła: czekam na Claude’a"
        }
    }

    private static func studyDetail(_ title: String, step: String) -> String {
        switch step {
        case "sources": "„\(title)” · muzeum, Wikidata, Wikipedia"
        case "writing": "„\(title)” · zwykle 1–3 minuty"
        default: "„\(title)”"
        }
    }
}
