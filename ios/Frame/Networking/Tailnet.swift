import Foundation
import Network
import Tailscale
import UIKit

/// Tailscale built into the app (decision D16): away from home the app
/// reaches the server's Tailscale address through a Tailscale node of its
/// own, run by libtailscale inside the app, instead of the Tailscale app and
/// its VPN. So it needs no other app and works next to another VPN.
///
/// Only requests to the server's Tailscale address (`AppModel.remoteURL`,
/// Konfiguracja → Serwer → Dostęp spoza domu) go through it, and only when
/// that is a Tailscale address; everything else (the home address, museums)
/// goes as before. The node joins the tailnet with the household's auth key,
/// given once by the owner in Konfiguracja and read from the server by every
/// phone (`/api/tailnet`). It starts when first needed and keeps its identity
/// in Application Support, so later starts take a second or two.
///
/// iOS takes the sockets of a suspended app away, the node's local proxy
/// among them (TailscaleKit notes the same), so after a while in the
/// background, a network change or a request that could not get through,
/// the node is started again on its next use.
///
/// The C calls follow TailscaleKit's `TailscaleNode` (BSD-3-Clause,
/// Tailscale Inc & AUTHORS); libtailscale itself is built by
/// `scripts/build-tailscale.sh`.
final class Tailnet: @unchecked Sendable {
    static let shared = Tailnet()

    enum State: Equatable, Sendable {
        /// No key.
        case off
        /// Switched off on this phone: the Tailscale app's VPN (if any) is used.
        case paused
        /// Ready; starts with the first request that needs it.
        case idle
        case starting
        case running(address: String?)
        case failed(String)
    }

    /// What the node is started with.
    struct Setup: Equatable, Sendable {
        var key: String
        /// The server's Tailscale host; nil until the server is found
        /// (`findServer`), the node then carries nothing yet.
        var host: String?
        /// The node's name in the Tailscale admin panel.
        var name: String
    }

    /// A running node: its local SOCKS5 proxy, as URL sessions.
    private final class Node: @unchecked Sendable {
        let handle: tailscale
        let api: URLSession
        let images: URLSession
        /// For the requests that wait at the server (`LiveBackend.patient`).
        let waits: URLSession
        let address: String?
        /// The loopback address (SOCKS5 and LocalAPI) and LocalAPI's password.
        let loopback: String
        let apiKey: String

        init(
            handle: tailscale, api: URLSession, images: URLSession, waits: URLSession,
            address: String?, loopback: String, apiKey: String
        ) {
            self.handle = handle
            self.api = api
            self.images = images
            self.waits = waits
            self.address = address
            self.loopback = loopback
            self.apiKey = apiKey
        }
    }

    private struct StartFailure: Error {
        let message: String
    }

    /// How long a node may take to come up: joining for the first time
    /// asks Tailscale's servers more.
    static let joinTimeout: Duration = .seconds(25)
    static let upTimeout: Duration = .seconds(15)
    /// After a failed start, requests go the usual way for this long before
    /// the node is tried again (unless the key, the network or the app's
    /// return say otherwise).
    static let retryPause: TimeInterval = 30
    /// Longer than this in the background and the node starts again.
    static let staleAfter: TimeInterval = 20
    static let enabledKey = "tailnetInApp"

    private let lock = NSLock()
    private var setup: Setup?
    private var enabled: Bool
    private var node: Node?
    private var starting: Task<Node?, Never>?
    /// Counts starts: one begun before the setup changed is not kept.
    private var attempt = 0
    private var stale = false
    private var retryAt: Date?
    private var awaySince: Date?
    private var state = State.off
    private var observers: [NSObjectProtocol] = []
    /// Told whenever `state` changes (on any thread).
    var onChange: (@Sendable (State) -> Void)? {
        get { lock.withLock { changed } }
        set { lock.withLock { changed = newValue } }
    }

    private var changed: (@Sendable (State) -> Void)?

    private init() {
        enabled = UserDefaults.standard.object(forKey: Self.enabledKey) as? Bool ?? true
        let center = NotificationCenter.default
        observers = [
            center.addObserver(forName: UIApplication.didEnterBackgroundNotification, object: nil, queue: nil) { [weak self] _ in
                self?.wentAway()
            },
            center.addObserver(forName: UIApplication.willEnterForegroundNotification, object: nil, queue: nil) { [weak self] _ in
                self?.cameBack()
            },
        ]
    }

    var current: State { lock.withLock { state } }
    var isEnabled: Bool { lock.withLock { enabled } }
    var nodeName: String? { lock.withLock { setup?.name } }

    // MARK: Setup

    /// The key and the server's remote address; no key turns the node off.
    /// A remote address outside Tailscale (or none) leaves the node on for
    /// `findServer`, carrying nothing.
    func configure(key: String?, remote: URL?, name: String) {
        let host = remote?.host(percentEncoded: false).map { $0.lowercased() }.flatMap { Self.isTailscale($0) ? $0 : nil }
        let wanted: Setup? = if let key, !key.isEmpty {
            Setup(key: key, host: host, name: name)
        } else {
            nil
        }
        let (old, dropped): (Node?, Bool) = lock.withLock {
            guard wanted != setup else { return (nil, false) }
            // The same node keeps serving a new key or name; another host
            // needs no new node either. A key gone means leaving the tailnet.
            let leaving = wanted == nil
            setup = wanted
            retryAt = nil
            if leaving {
                let old = node
                node = nil
                attempt += 1
                starting = nil
                return (old, true)
            }
            if case .failed = state { state = .idle }
            return (nil, false)
        }
        if old != nil || dropped {
            // tailscale_close may take a moment: not on the caller's thread.
            Task.detached {
                if let old { self.close(old) }
                if dropped { Self.forget() }
            }
        }
        publish()
    }

    /// The phone's own switch: off, the app reaches "Spoza domu" directly
    /// (through the Tailscale app's VPN, if that is on).
    func setEnabled(_ on: Bool) {
        UserDefaults.standard.set(on, forKey: Self.enabledKey)
        let old: Node? = lock.withLock {
            enabled = on
            retryAt = nil
            guard !on else { return nil }
            let old = node
            node = nil
            attempt += 1
            starting = nil
            return old
        }
        if let old { Task.detached { self.close(old) } }
        publish()
    }

    /// Starts the node now (after a new key), and says how that went.
    @discardableResult
    func warm() async -> State {
        lock.withLock { retryAt = nil }
        _ = await ready()
        return current
    }

    /// The network changed: the node's sockets may be gone.
    func networkChanged() {
        lock.withLock {
            if node != nil { stale = true }
            retryAt = nil
        }
    }

    // MARK: Requests

    /// Whether `url` goes to the server's Tailscale address and the node is
    /// meant to carry it.
    func carries(_ url: URL?) -> Bool {
        guard let host = url?.host(percentEncoded: false)?.lowercased() else { return false }
        return lock.withLock { enabled && setup?.host != nil && setup?.host == host }
    }

    // MARK: Finding the server

    /// How long one machine of the tailnet may take to say whether it is a
    /// frame server.
    static let probeTimeout: TimeInterval = 6
    /// At most this many machines are asked.
    static let probeLimit = 32

    /// The frame server among the tailnet's machines, as
    /// `scheme://host:port` (MagicDNS name when there is one): the node lists
    /// the machines it sees (LocalAPI status) and asks each online one at
    /// `port` whether it is a frame server. Nil when the node is off or
    /// switched off on this phone, or no machine answers.
    func findServer(port: Int, scheme: String) async -> URL? {
        guard let node = await ready(), let status = await Self.status(node),
              let candidates = Self.candidates(status: status, port: port, scheme: scheme)
        else { return nil }
        return await withTaskGroup(of: URL?.self) { group in
            for base in candidates {
                group.addTask {
                    await ServerRoute.answers(base, timeout: Self.probeTimeout, through: node.api) ? base : nil
                }
            }
            for await found in group {
                if let found {
                    group.cancelAll()
                    return found
                }
            }
            return nil
        }
    }

    /// The node's view of the tailnet (`tailscale status --json`, the parts
    /// needed here).
    private struct Status: Decodable {
        struct Peer: Decodable {
            var dnsName: String?
            var ips: [String]?
            var online: Bool?

            enum CodingKeys: String, CodingKey {
                case dnsName = "DNSName", ips = "TailscaleIPs", online = "Online"
            }
        }

        var peer: [String: Peer]?

        enum CodingKeys: String, CodingKey {
            case peer = "Peer"
        }
    }

    /// LocalAPI on the loopback address, straight (no proxy).
    private static let local: URLSession = {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.connectionProxyDictionary = [:]
        return URLSession(configuration: configuration)
    }()

    /// The node's status from LocalAPI, as JSON.
    private static func status(_ node: Node) async -> Data? {
        guard let url = URL(string: "http://\(node.loopback)/localapi/v0/status") else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 5
        request.setValue("localapi", forHTTPHeaderField: "Sec-Tailscale")
        let credential = Data(":\(node.apiKey)".utf8).base64EncodedString()
        request.setValue("Basic \(credential)", forHTTPHeaderField: "Authorization")
        guard let (data, response) = try? await local.data(for: request),
              (response as? HTTPURLResponse)?.statusCode == 200
        else { return nil }
        return data
    }

    /// The addresses to ask, from the node's `status`: each online machine
    /// at `port`, by its MagicDNS name (else its IPv4 address), sorted so
    /// the same tailnet is always asked the same way. Nil when `status` is
    /// not the node's status.
    static func candidates(status: Data, port: Int, scheme: String) -> [URL]? {
        guard let decoded = try? JSONDecoder().decode(Status.self, from: status) else { return nil }
        let hosts = (decoded.peer ?? [:]).values
            .filter { $0.online != false }
            .compactMap { peer -> String? in
                let name = peer.dnsName.map { $0.hasSuffix(".") ? String($0.dropLast()) : $0 } ?? ""
                return name.isEmpty ? peer.ips?.first(where: { $0.contains(".") }) : name.lowercased()
            }
        return Set(hosts).sorted().prefix(probeLimit).compactMap { URL(string: "\(scheme)://\($0):\(port)") }
    }

    // MARK: Requests through the node

    /// Sends `request` with `body` through the node when it goes to the
    /// server's Tailscale address, else through `fallback`. When the node
    /// cannot be started the request goes through `fallback` too: the
    /// Tailscale app's VPN may still carry it. `waits`: a request that
    /// waits at the server, on the node's connections for those.
    func send<T>(
        _ request: URLRequest, else fallback: URLSession = .shared, images: Bool = false, waits: Bool = false,
        _ body: (URLSession) async throws -> T
    ) async throws -> T {
        guard carries(request.url), let node = await ready() else { return try await body(fallback) }
        do {
            return try await body(images ? node.images : waits ? node.waits : node.api)
        } catch let error as URLError where Self.lost(error) {
            lose(node)
            throw error
        }
    }

    func data(
        for request: URLRequest, else fallback: URLSession = .shared, waits: Bool = false
    ) async throws -> (Data, URLResponse) {
        try await send(request, else: fallback, waits: waits) { try await $0.data(for: request) }
    }

    /// Errors after which the node's proxy or sockets may be gone.
    private static func lost(_ error: URLError) -> Bool {
        switch error.code {
        case .cannotConnectToHost, .networkConnectionLost, .timedOut, .cannotFindHost:
            true
        default:
            false
        }
    }

    private func lose(_ failed: Node) {
        lock.withLock {
            if node === failed { stale = true }
        }
    }

    // MARK: The node

    /// The running node, started (or started again) when needed; nil when
    /// it is off or could not start.
    private func ready() async -> Node? {
        enum Next {
            case use(Node?)
            case wait(Task<Node?, Never>)
        }
        let next: Next = lock.withLock {
            guard enabled, let setup else { return .use(nil) }
            if let node, !stale { return .use(node) }
            if let starting { return .wait(starting) }
            if let retryAt, retryAt > Date() { return .use(nil) }
            let old = node
            node = nil
            stale = false
            attempt += 1
            let mine = attempt
            let task = Task.detached { [weak self] () -> Node? in
                guard let self else { return nil }
                if let old { self.close(old) }
                return await self.start(setup, attempt: mine)
            }
            starting = task
            return .wait(task)
        }
        switch next {
        case let .use(node):
            return node
        case let .wait(task):
            publish()
            return await task.value
        }
    }

    private func start(_ setup: Setup, attempt mine: Int) async -> Node? {
        let outcome: Result<Node, StartFailure>
        do {
            outcome = try .success(await Self.bringUp(setup))
        } catch let failure as StartFailure {
            outcome = .failure(failure)
        } catch {
            outcome = .failure(StartFailure(message: error.localizedDescription))
        }
        let (kept, spare): (Node?, Node?) = lock.withLock {
            // Switched off, or the key went, meanwhile: not wanted any more.
            guard mine == attempt else {
                if case let .success(started) = outcome { return (nil, started) }
                return (nil, nil)
            }
            starting = nil
            switch outcome {
            case let .success(started):
                guard enabled, self.setup?.key == setup.key else { return (nil, started) }
                node = started
                retryAt = nil
                state = .running(address: started.address)
                return (started, nil)
            case let .failure(failure):
                retryAt = Date().addingTimeInterval(Self.retryPause)
                state = .failed(failure.message)
                return (nil, nil)
            }
        }
        if let spare { close(spare) }
        publish(notify: true)
        return kept
    }

    private static func bringUp(_ setup: Setup) async throws -> Node {
        let directory = try stateDirectory()
        let joined = FileManager.default.fileExists(atPath: directory.appending(path: "tailscaled.state").path(percentEncoded: false))
        let handle = tailscale_new()
        // The descriptor is libtailscale's from here on: Go closes it.
        tailscale_set_logfd(handle, openLog())
        tailscale_set_dir(handle, directory.path(percentEncoded: false))
        tailscale_set_hostname(handle, setup.name)
        tailscale_set_authkey(handle, setup.key)
        tailscale_set_ephemeral(handle, 0)
        func fail(_ message: String) -> StartFailure {
            tailscale_close(handle)
            return StartFailure(message: message)
        }
        guard tailscale_start(handle) == 0 else { throw fail(Self.words(errorMessage(handle))) }

        // tailscale_up waits until the node is on the tailnet; never forever.
        let timeout = joined ? upTimeout : joinTimeout
        let up = await withTaskGroup(of: Int32?.self) { group in
            group.addTask { await Task.detached { tailscale_up(handle) }.value }
            group.addTask {
                try? await Task.sleep(for: timeout)
                return nil
            }
            let first = await group.next() ?? nil
            group.cancelAll()
            return first
        }
        guard let up else {
            throw fail("Tailscale nie połączył się w \(timeout.components.seconds) s. Sprawdź internet albo klucz.")
        }
        guard up == 0 else { throw fail(Self.words(errorMessage(handle))) }

        let addressBuffer = UnsafeMutablePointer<CChar>.allocate(capacity: 64)
        let credentialBuffer = UnsafeMutablePointer<CChar>.allocate(capacity: 33)
        let apiKeyBuffer = UnsafeMutablePointer<CChar>.allocate(capacity: 33)
        defer {
            addressBuffer.deallocate()
            credentialBuffer.deallocate()
            apiKeyBuffer.deallocate()
        }
        guard tailscale_loopback(handle, addressBuffer, 64, credentialBuffer, apiKeyBuffer) == 0 else {
            throw fail(Self.words(errorMessage(handle)))
        }
        let proxy = String(cString: addressBuffer)
        let credential = String(cString: credentialBuffer)
        let apiKey = String(cString: apiKeyBuffer)
        let parts = proxy.split(separator: ":")
        guard parts.count == 2, let port = UInt16(parts[1]), let nwPort = NWEndpoint.Port(rawValue: port) else {
            throw fail("Tailscale podał zły adres pośrednika: \(proxy)")
        }
        let endpoint = NWEndpoint.hostPort(host: NWEndpoint.Host(String(parts[0])), port: nwPort)
        func session(images: Bool) -> URLSession {
            let configuration = URLSessionConfiguration.default
            let socks = ProxyConfiguration(socksv5Proxy: endpoint)
            socks.applyCredential(username: "tsnet", password: credential)
            configuration.proxyConfigurations = [socks]
            if images {
                // As ImageLoader's own sessions.
                configuration.urlCache = .shared
                configuration.httpMaximumConnectionsPerHost = 6
            }
            return URLSession(configuration: configuration)
        }
        return Node(
            handle: handle, api: session(images: false), images: session(images: true),
            waits: session(images: false), address: addresses(handle).first, loopback: proxy, apiKey: apiKey
        )
    }

    private func close(_ old: Node) {
        old.api.invalidateAndCancel()
        old.images.invalidateAndCancel()
        old.waits.invalidateAndCancel()
        tailscale_close(old.handle)
    }

    private func wentAway() {
        lock.withLock { awaySince = Date() }
    }

    private func cameBack() {
        lock.withLock {
            defer { awaySince = nil }
            retryAt = nil
            guard let awaySince, Date().timeIntervalSince(awaySince) > Self.staleAfter, node != nil else { return }
            stale = true
        }
    }

    private func publish(notify: Bool = false) {
        let (now, tell): (State, (@Sendable (State) -> Void)?) = lock.withLock {
            let now: State = if setup == nil {
                .off
            } else if !enabled {
                .paused
            } else if starting != nil {
                .starting
            } else if let node {
                .running(address: node.address)
            } else if case .failed = state {
                state
            } else {
                .idle
            }
            let changed = now != state || notify
            state = now
            return (now, changed ? self.changed : nil)
        }
        tell?(now)
    }

    // MARK: Helpers

    /// A Tailscale address: 100.64.0.0/10, Tailscale's IPv6 range, a
    /// MagicDNS name (`*.ts.net`) or a bare machine name.
    static func isTailscale(_ host: String) -> Bool {
        let host = host.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
        if host.hasSuffix(".ts.net") { return true }
        if host.hasPrefix("fd7a:115c:a1e0:") { return true }
        let octets = host.split(separator: ".", omittingEmptySubsequences: false)
        if octets.count == 4, octets.allSatisfy({ UInt8($0) != nil }) {
            guard let first = UInt8(octets[0]), let second = UInt8(octets[1]) else { return false }
            return first == 100 && (64 ... 127).contains(second)
        }
        return !host.contains(".") && !host.contains(":") && !host.isEmpty && host != "localhost"
    }

    /// The node's name in the Tailscale admin panel: "frame-" and whose
    /// phone it is, in letters Tailscale takes.
    static func nodeName(for person: String?) -> String {
        let folded = (person ?? "")
            .lowercased()
            .replacingOccurrences(of: "ł", with: "l")
            .folding(options: .diacriticInsensitive, locale: Locale(identifier: "pl"))
        let slug = folded.unicodeScalars
            .map { CharacterSet.alphanumerics.contains($0) && $0.isASCII ? String($0) : "-" }
            .joined()
            .split(separator: "-")
            .joined(separator: "-")
        return slug.isEmpty ? "frame-iphone" : "frame-\(slug.prefix(40))"
    }

    /// The node's identity, kept from start to start; not in the phone's
    /// backup, so a new phone joins as a node of its own.
    private static func stateDirectory() throws -> URL {
        var directory = URL.applicationSupportDirectory.appending(path: "Tailscale", directoryHint: .isDirectory)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try? directory.setResourceValues(values)
        return directory
    }

    /// Leaves the tailnet on this phone: the next key joins anew.
    private static func forget() {
        try? FileManager.default.removeItem(at: URL.applicationSupportDirectory.appending(path: "Tailscale"))
    }

    private static var logURL: URL { URL.cachesDirectory.appending(path: "tailscale.log") }

    /// The node's own log, anew at every start (its end is shown in
    /// Konfiguracja); -1, no log, when the file cannot be opened.
    private static func openLog() -> Int32 {
        open(logURL.path(percentEncoded: false), O_WRONLY | O_CREAT | O_TRUNC | O_APPEND, 0o644)
    }

    /// The last lines of the node's log.
    static func recentLog(lines: Int = 40) -> String {
        guard let data = try? Data(contentsOf: logURL) else { return "" }
        let text = String(decoding: data.suffix(64 * 1024), as: UTF8.self)
        return text.split(separator: "\n", omittingEmptySubsequences: true).suffix(lines).joined(separator: "\n")
    }

    private static func errorMessage(_ handle: tailscale) -> String {
        let buffer = UnsafeMutablePointer<CChar>.allocate(capacity: 256)
        defer { buffer.deallocate() }
        guard tailscale_errmsg(handle, buffer, 256) == 0 else { return "" }
        return String(cString: buffer)
    }

    private static func addresses(_ handle: tailscale) -> [String] {
        let buffer = UnsafeMutablePointer<CChar>.allocate(capacity: 128)
        defer { buffer.deallocate() }
        guard tailscale_getips(handle, buffer, 128) == 0 else { return [] }
        // IPv4 first.
        return String(cString: buffer).split(separator: ",").map(String.init).sorted { $0.contains(".") && !$1.contains(".") }
    }

    /// libtailscale's error, in words for Konfiguracja.
    static func words(_ message: String) -> String {
        let lower = message.lowercased()
        if lower.contains("invalid key") || lower.contains("authkey") || lower.contains("auth key")
            || lower.contains("expired") || lower.contains("needslogin") || lower.contains("not authorized") {
            return "Tailscale odrzucił klucz (wygasł albo został cofnięty). Utwórz nowy w panelu Tailscale i zapisz go tutaj."
        }
        return message.isEmpty ? "Tailscale nie wystartował." : "Tailscale: \(message)"
    }
}
