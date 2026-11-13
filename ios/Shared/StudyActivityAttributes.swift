import ActivityKit
import Foundation

/// A study of a work being written on the server ("Przygotuj studium
/// dzieła"), on the Lock Screen and in the Dynamic Island (the app's
/// `StudyLiveActivity`, drawn by `StudyActivityWidget`). The server pushes
/// each step to it (notifications.py `push_study`), so it moves on with the
/// app closed; a tap opens the study.
struct StudyActivityAttributes: ActivityAttributes {
    /// What the server pushes as "content-state": keep the keys as they are.
    struct ContentState: Codable, Hashable {
        /// waiting, sources, writing, details (on its way), then ready,
        /// failed, off (no Claude key) or stopped (the server lost it).
        /// The older word, kept for apps before `part`.
        var status: String
        /// Why it failed, in Polish.
        var error: String?
        /// The part it is at (study.py `PARTS`: sources, text, text_again,
        /// details_check, composition, composition_check, composition_motion,
        /// composition_text, cutting, later; or waiting); nil from a server
        /// before 1.118.0.
        var part: String? = nil
        /// Since when Claude writes it (after any wait), and when it should
        /// be done, judged by the server from the last studies: the bar
        /// moves on by itself between pushes.
        var startedAt: Date? = nil
        var expectedEnd: Date? = nil

        static let onWay: Set<String> = ["waiting", "sources", "writing", "details"]

        var isActive: Bool { Self.onWay.contains(status) }
        var isReady: Bool { status == "ready" }
        var isFailed: Bool { !isActive && !isReady }

        /// The four steps the study goes through, as the app's card says them.
        static let steps: [(key: String, label: String)] = [
            ("sources", "Źródła"), ("text", "Tekst"), ("composition", "Kompozycja"), ("details", "Detale"),
        ]

        /// Each part's step (index in `steps`).
        static let stepOfPart: [String: Int] = [
            "restoring": 0, "sources": 0,
            "text": 1, "text_again": 1, "details_check": 1,
            "composition": 2, "composition_check": 2, "composition_motion": 2, "composition_text": 2,
            "cutting": 3, "later": 3,
        ]

        /// What each part says, on the Lock Screen and on the app's card.
        static let partLines: [String: String] = [
            // In the voice of the one preparing the study (Mateusz 2026-11-07).
            "waiting": "Zaraz zabieram się do pracy",
            // A small picture drawn larger first (Kreatywny restaurator, 2026-11-13).
            "restoring": "Odnawiam zdjęcie dzieła",
            "sources": "Zbieram źródła i informacje",
            "text": "Piszę studium",
            "text_again": "Nanoszę korekty",
            "details_check": "Sprawdzam kadry detali",
            "composition": "Analizuję kompozycję dzieła",
            "composition_check": "Sprawdzam ślady",
            "composition_motion": "Patrzę na układ i ruch",
            "composition_text": "Opisuję kompozycję",
            "cutting": "Wycinam detale z oryginału",
            "later": "Szukam dzieł, które z niego wyrosły",
        ]

        /// The step under way (0…3), past the last when ready; nil while
        /// waiting for Claude or when it did not get there. From a server
        /// before `part`, its "writing" is the text.
        var stepIndex: Int? {
            if isReady { return Self.steps.count }
            guard isActive else { return nil }
            if let part, let step = Self.stepOfPart[part] { return step }
            switch status {
            case "sources": return 0
            case "writing": return 1
            case "details": return 3
            default: return nil
            }
        }

        /// The line under the title.
        var line: String {
            if isActive, let part, let line = Self.partLines[part] { return line }
            switch status {
            case "sources": return "Zbieram źródła: muzeum, Wikidata, Wikipedia"
            case "writing": return "Claude pisze studium, zwykle 1–3 minuty"
            case "details": return "Wycinam detale z oryginału"
            case "ready": return "Gotowe. Stuknij, żeby przeczytać"
            case "failed": return error.flatMap { $0.isEmpty ? nil : $0 } ?? "Nie udało się przygotować studium"
            case "off": return "Claude jest wyłączony: dodaj klucz API w Konfiguracji"
            case "stopped": return "Serwer przestał je pisać. Spróbuj jeszcze raz"
            default: return "Czekam na Claude’a"
            }
        }

        /// The span the bar runs over while Claude writes it; nil while it
        /// waits, from older servers, and once over.
        var timerRange: ClosedRange<Date>? {
            guard isActive, part != "waiting", let startedAt, let expectedEnd, expectedEnd > startedAt else {
                return nil
            }
            return startedAt...expectedEnd
        }

        /// "z ok. 3½ min": how long the whole study takes, about, as the
        /// server judged it at its last push (the Lock Screen cannot count
        /// down in words between pushes).
        var aboutWhole: String? {
            timerRange.map { "z ok. \(Self.about($0.upperBound.timeIntervalSince($0.lowerBound)))" }
        }

        /// "1 min", "1½ min", "3 min": to the half minute, at least one.
        static func about(_ seconds: TimeInterval) -> String {
            let halves = max(2, Int((seconds / 30).rounded()))
            let whole = halves / 2
            return halves % 2 == 0 ? "\(whole) min" : "\(whole)½ min"
        }
    }

    var itemID: String
    /// The work's title, as on its card.
    var title: String
    /// Its small picture (`ActivityPicture`), when the app had it in time.
    var picture: Data? = nil

    /// Where a tap on the card goes: the app opens the study
    /// (`PushCenter.open`, as for the notification "Studium gotowe").
    var url: URL {
        var parts = URLComponents()
        parts.scheme = "com.artrybka.frame"
        parts.host = "open"
        parts.queryItems = [URLQueryItem(name: "route", value: "study/\(itemID)")]
        return parts.url ?? URL(string: "com.artrybka.frame://open")!
    }
}
