import Foundation

/// Changes the app asks of the server (POST, PUT, PATCH, DELETE) go with an
/// `Idempotency-Key`. The server keeps their answers (server
/// `web/replays.py`) and says so with `Frame-Replays: 1` on every answer;
/// a change cut short by the app going away is then simply sent again,
/// with the same key, once the app is back: it runs on the server once and
/// the app hears how it ended, instead of „Przerwane, gdy aplikacja była w
/// tle” (Mateusz 2026-11-13). An older server never said so, and a change
/// that may have arrived is not sent to it twice.
/// Read from any thread.
final class Replays: @unchecked Sendable {
    static let shared = Replays()

    static let keyHeader = "Idempotency-Key"
    static let markHeader = "Frame-Replays"

    private let lock = NSLock()
    private var keeps = false

    /// Whether the server answering last keeps changes' answers.
    var serverKeeps: Bool { lock.withLock { keeps } }

    /// Learns from an answer of the server whether it keeps changes' answers.
    func saw(_ response: URLResponse) {
        guard let http = response as? HTTPURLResponse, http.url?.path.contains("/api/") ?? false else { return }
        let marked = http.value(forHTTPHeaderField: Self.markHeader) == "1"
        lock.withLock { keeps = marked }
    }

    /// The request with a key of its own, if it changes something and has none.
    static func keyed(_ req: URLRequest) -> URLRequest {
        guard isChange(req), req.value(forHTTPHeaderField: keyHeader) == nil else { return req }
        var keyed = req
        keyed.setValue(UUID().uuidString, forHTTPHeaderField: keyHeader)
        return keyed
    }

    static func isChange(_ req: URLRequest) -> Bool {
        !["GET", "HEAD"].contains(req.httpMethod ?? "GET")
    }

    /// Whether `req`, cut short by `error`, can go again without anything
    /// happening twice: a read, one that never reached the server, or a
    /// change with a key the server keeps the answer to.
    func mayResend(_ req: URLRequest, after error: URLError) -> Bool {
        !Self.isChange(req) || ServerRoute.neverArrived(error)
            || (serverKeeps && req.value(forHTTPHeaderField: Self.keyHeader) != nil)
    }
}
