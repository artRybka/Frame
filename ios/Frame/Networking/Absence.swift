import UIKit

/// When the app was away (in the background) and when it came back. A
/// request running while iOS froze the app ends with a timeout or a lost
/// connection once it is back, and one sent the moment it came back may
/// fail before the Wi-Fi wakes up. Neither says anything about the server,
/// so such a request is sent again instead of showing an error.
/// Read from any thread.
final class Absence: @unchecked Sendable {
    static let shared = Absence(observing: true)

    /// Taken when a request starts.
    struct Mark: Sendable {
        let leaves: Int
    }

    /// How long after coming back a failure may still be the network waking up.
    static let settling: TimeInterval = 15

    private let lock = NSLock()
    private var leaves = 0
    private var away = false
    private var backAt = Date.distantPast
    private var waiting: [CheckedContinuation<Void, Never>] = []

    init(observing: Bool = false) {
        guard observing else { return }
        let center = NotificationCenter.default
        center.addObserver(forName: UIApplication.didEnterBackgroundNotification, object: nil, queue: nil) { [weak self] _ in
            self?.left()
        }
        center.addObserver(forName: UIApplication.willEnterForegroundNotification, object: nil, queue: nil) { [weak self] _ in
            self?.cameBack()
        }
    }

    func mark() -> Mark { lock.withLock { Mark(leaves: leaves) } }

    func left() {
        lock.withLock {
            leaves += 1
            away = true
        }
    }

    func cameBack(at now: Date = .now) {
        let resumed = lock.withLock {
            away = false
            backAt = now
            defer { waiting = [] }
            return waiting
        }
        for continuation in resumed { continuation.resume() }
    }

    /// Whether a request started at `mark` failed because the app was away,
    /// not because the server did not answer.
    func interrupted(_ error: Error, since mark: Mark, now: Date = .now) -> Bool {
        guard let error = error as? URLError, ServerRoute.unreachable(error) else { return false }
        return lock.withLock {
            away || leaves != mark.leaves || now.timeIntervalSince(backAt) < Self.settling
        }
    }

    /// Returns once the app is in the foreground, and the network has had
    /// `pause` since it came back.
    func whenBack(pause: TimeInterval) async {
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            let now = lock.withLock {
                if away { waiting.append(continuation) }
                return !away
            }
            if now { continuation.resume() }
        }
        let since = lock.withLock { Date.now.timeIntervalSince(backAt) }
        if since < pause { try? await Task.sleep(for: .seconds(pause - since)) }
    }
}
