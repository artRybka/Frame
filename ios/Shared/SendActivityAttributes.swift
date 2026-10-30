import ActivityKit
import Foundation

/// A picture on its way to the frame, on the Lock Screen and in the Dynamic
/// Island while the app is away (the app's `SendLiveActivity`, drawn by
/// `SendActivityWidget`). iOS shows it in the island only outside the app.
struct SendActivityAttributes: ActivityAttributes {
    struct ContentState: Codable, Hashable {
        /// The server's stage: rendering … refreshing, done, waiting, failed.
        var stage: String
        /// processing, loading or displaying.
        var phase: String?
        var label: String
        /// 0…1 as last heard from the server, at `heardAt`.
        var fraction: Double
        var heardAt: Date
        /// When the server expects the bar to reach the end: it moves on by
        /// itself while the app sleeps.
        var expectedEnd: Date?
        /// Waiting for the frame: "jutro o 07:00", when its alarm rings.
        var wakes: String?

        var isDone: Bool { stage == "done" }
        var isFailed: Bool { stage == "failed" }
        var isWaiting: Bool { stage == "waiting" }
        var isActive: Bool { !isDone && !isFailed && !isWaiting }

        /// The span the bar runs over, so that it stood at `fraction` at
        /// `heardAt` and is full at `expectedEnd`.
        var timerRange: ClosedRange<Date>? {
            guard isActive, let expectedEnd, expectedEnd > heardAt, fraction < 0.99 else { return nil }
            let left = expectedEnd.timeIntervalSince(heardAt)
            let start = heardAt.addingTimeInterval(-left * fraction / (1 - fraction))
            return start...expectedEnd
        }

        /// The three parts of the bar, as in the app.
        static let phases: [(key: String, label: String)] = [
            ("processing", "Przetwarzanie"), ("loading", "Ładowanie"), ("displaying", "Wyświetlanie"),
        ]

        var phaseIndex: Int? {
            if isDone { return Self.phases.count }
            return phase.flatMap { key in Self.phases.firstIndex { $0.key == key } }
        }
    }

    /// The work's title.
    var title: String
}
