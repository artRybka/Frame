import SwiftUI
import UIKit

/// A card at the bottom of the screen, in the look of the bar that follows
/// a picture to the frame: work under way, a confirmation, or a warning or
/// an error that stays until it is closed.
struct Notice: Identifiable, Equatable {
    enum Kind: Equatable {
        case working, done, info, warning, error

        /// Confirmations go by themselves; warnings and errors wait to be read.
        var transient: Bool { self == .done || self == .info }
    }

    let id = UUID()
    var kind: Kind
    var title: String
    var detail: String?
    /// 0…1 when the share done is known (a bar); otherwise only the spinner.
    var fraction: Double?
    /// "12 z 40" next to the title.
    var count: String?
    /// Work that goes on after its screen closed (an album, a museum fetch):
    /// kept above the rest.
    var background = false
}

/// The cards on screen. A new confirmation replaces the one before, a new
/// warning or error the one before; work under way keeps its own card until
/// it ends, and then turns into its result in the same place.
@MainActor
@Observable
final class Notices {
    private(set) var items: [Notice] = []
    /// "Teraz" shows the send bar under the picture; elsewhere it goes
    /// with the cards.
    var nowTabOpen = true
    @ObservationIgnored private var timers: [Notice.ID: Task<Void, Never>] = [:]

    func done(_ title: String, _ detail: String? = nil) { post(.done, title, detail) }
    func info(_ title: String, _ detail: String? = nil) { post(.info, title, detail) }
    func warn(_ title: String, _ detail: String? = nil) { post(.warning, title, detail) }
    func fail(_ title: String, _ detail: String? = nil) { post(.error, title, detail) }

    /// A card for work that takes a while; end it with `end`, or `drop` it.
    @discardableResult
    func begin(_ title: String, _ detail: String? = nil, background: Bool = false) -> Notice.ID {
        let notice = Notice(kind: .working, title: title, detail: detail, background: background)
        withAnimation(.snappy) {
            if background {
                items.insert(notice, at: items.lastIndex(where: \.background).map { $0 + 1 } ?? 0)
            } else {
                items.append(notice)
            }
        }
        announce(notice)
        return notice.id
    }

    /// Progress of work under way; `fraction` nil keeps the one it had.
    func update(_ id: Notice.ID, title: String? = nil, fraction: Double? = nil, count: String? = nil) {
        guard let index = items.firstIndex(where: { $0.id == id }), items[index].kind == .working else { return }
        if let title { items[index].title = title }
        if let fraction { items[index].fraction = min(max(fraction, 0), 1) }
        if let count { items[index].count = count }
    }

    /// The work ended: its card shows the result where it is.
    func end(_ id: Notice.ID, _ kind: Notice.Kind, _ title: String, _ detail: String? = nil) {
        guard let index = items.firstIndex(where: { $0.id == id }) else {
            post(kind, title, detail)
            return
        }
        withAnimation(.snappy) {
            items[index].kind = kind
            items[index].title = title
            items[index].detail = detail
            items[index].count = nil
            // A bar that was there fills up; none appears when there was none.
            items[index].fraction = kind == .done && items[index].fraction != nil ? 1 : nil
            clear(sameSlotAs: kind, except: id)
        }
        if let notice = items.first(where: { $0.id == id }) { settle(notice) }
    }

    /// The work ended with nothing to say (cancelled).
    func drop(_ id: Notice.ID) { close(id) }

    func close(_ id: Notice.ID) {
        timers[id]?.cancel()
        timers[id] = nil
        withAnimation(.snappy) { items.removeAll { $0.id == id } }
    }

    // MARK: Errors

    /// An error, said in Polish with the server's words under it; a request
    /// cut short (a pull to refresh let go, a view gone) is no news.
    func fail(_ error: Error, in card: Notice.ID? = nil) {
        guard !error.isCancellation else {
            if let card { drop(card) }
            return
        }
        let (title, detail) = Self.words(for: error)
        if let card { end(card, .error, title, detail) } else { fail(title, detail) }
    }

    static func words(for error: Error) -> (String, String?) {
        if let error = error as? BackendError {
            switch error {
            case let .http(status, body):
                let said = (try? JSONDecoder().decode([String: String].self, from: Data(body.utf8)))?["detail"]
                let detail = "Serwer odpowiedział \(status)" + (said.map { ": \($0)" } ?? "")
                if said?.hasPrefix("panel not configured") == true {
                    return ("Ramka nie jest jeszcze ustawiona", "Podaj jej adres w Połączeniu z ekranem.")
                }
                if said?.hasPrefix("panel") == true { return ("Ramka nie odpowiada", detail) }
                if let said, said.contains(where: { "ąćęłńóśźż".contains($0) }) {
                    // Already written for people, in Polish.
                    return (said.prefix(1).uppercased() + said.dropFirst(), nil)
                }
                switch status {
                case 401, 403: return ("Serwer nie przyjął tokenu", detail)
                case 404: return ("Serwer nie zna tej rzeczy", detail)
                case 409: return ("Teraz się nie da", detail)
                case 500...: return ("Błąd na serwerze", detail)
                default: return ("Serwer odmówił", detail)
                }
            case .invalidResponse: return ("Serwer odpowiedział coś niezrozumiałego", nil)
            case .notFound: return ("Nie znaleziono", nil)
            }
        }
        if let error = error as? URLError {
            let title = error.code == .timedOut ? "Serwer nie odpowiedział na czas" : "Brak połączenia z serwerem"
            return (title, error.localizedDescription)
        }
        return (error.localizedDescription, nil)
    }

    // MARK: Private

    private func post(_ kind: Notice.Kind, _ title: String, _ detail: String?) {
        let notice = Notice(kind: kind, title: title, detail: detail)
        withAnimation(.snappy) {
            clear(sameSlotAs: kind, except: notice.id)
            items.append(notice)
        }
        settle(notice)
    }

    /// One confirmation and one warning or error at a time.
    private func clear(sameSlotAs kind: Notice.Kind, except id: Notice.ID) {
        guard kind != .working else { return }
        let gone = items.filter { $0.id != id && $0.kind != .working && $0.kind.transient == kind.transient }
        for notice in gone {
            timers[notice.id]?.cancel()
            timers[notice.id] = nil
        }
        items.removeAll { notice in gone.contains { $0.id == notice.id } }
    }

    /// A result shown: felt, read out, and for a confirmation, gone after a
    /// while long enough to read it.
    private func settle(_ notice: Notice) {
        switch notice.kind {
        case .done: UINotificationFeedbackGenerator().notificationOccurred(.success)
        case .warning: UINotificationFeedbackGenerator().notificationOccurred(.warning)
        case .error: UINotificationFeedbackGenerator().notificationOccurred(.error)
        case .working, .info: break
        }
        announce(notice)
        guard notice.kind.transient else { return }
        let id = notice.id
        timers[id]?.cancel()
        timers[id] = Task { [weak self] in
            try? await Task.sleep(for: .seconds(Self.readingTime(notice)))
            guard !Task.isCancelled else { return }
            self?.close(id)
        }
    }

    /// 2.5 s and about a second for every 15 characters, at most 5 s.
    static func readingTime(_ notice: Notice) -> Double {
        let characters = notice.title.count + (notice.detail?.count ?? 0)
        return min(5, 2.5 + Double(characters) / 15)
    }

    private func announce(_ notice: Notice) {
        let text = [notice.title, notice.detail].compactMap { $0 }.joined(separator: ". ")
        AccessibilityNotification.Announcement(text).post()
    }
}
