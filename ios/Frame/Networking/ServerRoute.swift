import Foundation

/// The server's addresses: the one at home and, optionally, a remote one
/// (e.g. the NAS's Tailscale address), and which of them the app uses now.
/// Read from any thread: image requests are built synchronously.
final class ServerRoute: @unchecked Sendable {
    enum Kind: String, Sendable {
        case home, remote
    }

    let home: URL
    let remote: URL?
    /// Told when `resolve()` switches to the other address.
    var onSwitch: (@Sendable (Kind) -> Void)?

    /// How long the home address may take before the remote one is used.
    static let homeHeadStart: Duration = .seconds(2)
    /// How long either address may take to answer at all.
    static let timeout: TimeInterval = 8

    private let lock = NSLock()
    private var kind = Kind.home
    private var resolving: Task<Kind?, Never>?

    init(home: URL, remote: URL? = nil, active: Kind = .home) {
        self.home = home
        self.remote = remote == home ? nil : remote
        kind = self.remote == nil ? .home : active
    }

    var hasRemote: Bool { remote != nil }
    var active: Kind { lock.withLock { kind } }
    var baseURL: URL { url(for: active) }

    func url(for kind: Kind) -> URL {
        kind == .remote ? remote ?? home : home
    }

    /// Asks both addresses at once and switches to the one that answers,
    /// home first. Calls made meanwhile share the same check. Nil when
    /// neither answers; the route then stays as it was.
    @discardableResult
    func resolve() async -> Kind? {
        guard hasRemote else { return .home }
        let task = lock.withLock {
            if let running = resolving { return running }
            let task = Task { await self.probe() }
            resolving = task
            return task
        }
        let found = await task.value
        let switched: Kind? = lock.withLock {
            if resolving == task { resolving = nil }
            guard let found, found != kind else { return nil }
            kind = found
            return found
        }
        if let switched { onSwitch?(switched) }
        return found
    }

    private enum Probe {
        case home(Bool), remote(Bool), headStartOver
    }

    private func probe() async -> Kind? {
        let home = home, remote = remote ?? home
        return await withTaskGroup(of: Probe.self, returning: Kind?.self) { group in
            group.addTask { .home(await Self.answers(home, timeout: Self.timeout)) }
            group.addTask { .remote(await Self.answers(remote, timeout: Self.timeout)) }
            group.addTask {
                try? await Task.sleep(for: Self.homeHeadStart)
                return .headStartOver
            }
            var atHome: Bool?, away: Bool?, waited = false
            for await answer in group {
                switch answer {
                case let .home(ok): atHome = ok
                case let .remote(ok): away = ok
                case .headStartOver: waited = true
                }
                if atHome == true {
                    group.cancelAll()
                    return .home
                }
                if away == true, waited || atHome == false {
                    group.cancelAll()
                    return .remote
                }
                if atHome == false, away == false {
                    group.cancelAll()
                    return nil
                }
            }
            return nil
        }
    }

    /// Whether a frame server answers there. No token is sent: the home
    /// address is not private, so away from home it may belong to someone
    /// else.
    static func answers(_ base: URL, timeout: TimeInterval) async -> Bool {
        var request = URLRequest(url: base.appending(path: "api/health"))
        request.timeoutInterval = timeout
        request.cachePolicy = .reloadIgnoringLocalCacheData
        guard let (data, response) = try? await URLSession.shared.data(for: request),
              (response as? HTTPURLResponse)?.statusCode == 200,
              let health = try? LiveBackend.decoder().decode(Health.self, from: data)
        else { return false }
        return health.ok
    }

    /// The request pointed at the address in use, when it was built for the
    /// other one.
    func rebased(_ request: URLRequest) -> URLRequest? {
        guard let url = request.url?.absoluteString else { return nil }
        let current = Self.prefix(baseURL)
        for base in [home, remote].compactMap({ $0 }) {
            let old = Self.prefix(base)
            guard old != current, url.hasPrefix(old) else { continue }
            var moved = request
            moved.url = URL(string: current + url.dropFirst(old.count))
            return moved
        }
        return nil
    }

    private static func prefix(_ url: URL) -> String {
        let text = url.absoluteString
        return text.hasSuffix("/") ? String(text.dropLast()) : text
    }

    /// Errors that mean the address did not answer at all, as opposed to the
    /// server answering with an error.
    static func unreachable(_ error: URLError) -> Bool {
        switch error.code {
        case .cannotConnectToHost, .cannotFindHost, .dnsLookupFailed, .notConnectedToInternet,
             .timedOut, .networkConnectionLost, .secureConnectionFailed:
            true
        default:
            false
        }
    }

    /// Whether the request surely never reached the server, so sending it
    /// again elsewhere cannot do anything twice.
    static func neverArrived(_ error: URLError) -> Bool {
        switch error.code {
        case .cannotConnectToHost, .cannotFindHost, .dnsLookupFailed, .notConnectedToInternet:
            true
        default:
            false
        }
    }
}
