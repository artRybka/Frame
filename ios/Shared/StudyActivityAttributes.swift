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
        var status: String
        /// Why it failed, in Polish.
        var error: String?

        static let onWay: Set<String> = ["waiting", "sources", "writing", "details"]

        var isActive: Bool { Self.onWay.contains(status) }
        var isReady: Bool { status == "ready" }
        var isFailed: Bool { !isActive && !isReady }

        /// The three parts the study goes through, as the app's card says them.
        static let steps: [(key: String, label: String)] = [
            ("sources", "Źródła"), ("writing", "Pisanie"), ("details", "Detale"),
        ]

        /// The step under way (0…2), past the last when ready; nil while
        /// waiting for Claude or when it did not get there.
        var stepIndex: Int? {
            if isReady { return Self.steps.count }
            return Self.steps.firstIndex { $0.key == status }
        }

        /// The line under the title.
        var line: String {
            switch status {
            case "sources": "Zbieram źródła: muzeum, Wikidata, Wikipedia"
            case "writing": "Claude pisze studium, zwykle 1–3 minuty"
            case "details": "Wycinam detale z oryginału"
            case "ready": "Gotowe. Stuknij, żeby przeczytać"
            case "failed": error.flatMap { $0.isEmpty ? nil : $0 } ?? "Nie udało się przygotować studium"
            case "off": "Claude jest wyłączony: dodaj klucz API w Konfiguracji"
            case "stopped": "Serwer przestał je pisać. Spróbuj jeszcze raz"
            default: "Czekam na Claude’a"
            }
        }
    }

    var itemID: String
    /// The work's title, as on its card.
    var title: String

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
