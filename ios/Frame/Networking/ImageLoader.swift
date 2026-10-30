import ImageIO
import SwiftUI
import UIKit

/// Loads, downsamples and caches pictures. Downsampling with ImageIO keeps
/// grids of large museum images light on memory.
///
/// What the owner looks at (`.high`: the picture on "Teraz", a card's
/// original or preview) goes first: it skips the line of a grid's
/// thumbnails and has connections of its own, apart from those of the
/// thumbnails and of the app's other requests. A picture nobody waits for
/// any more (scrolled away) leaves the line.
actor ImageLoader {
    static let shared = ImageLoader()

    enum Priority: Sendable {
        case normal, high
    }

    private struct Download {
        let task: Task<UIImage, Error>
        var waiting: Set<UUID>
    }

    private let cache = NSCache<NSString, UIImage>()
    private var inflight: [String: Download] = [:]

    init() {
        cache.totalCostLimit = 160 * 1024 * 1024
    }

    func image(for request: URLRequest, maxPixel: CGFloat, priority: Priority = .normal) async throws -> UIImage {
        let key = "\(request.url?.absoluteString ?? "")#\(Int(maxPixel))"
        if let cached = cache.object(forKey: key as NSString) { return cached }
        let waiter = UUID()
        let task: Task<UIImage, Error>
        if var running = inflight[key] {
            running.waiting.insert(waiter)
            inflight[key] = running
            task = running.task
        } else {
            // Detached: downsampling runs beside this actor, not on it.
            task = Task.detached(priority: priority == .high ? .userInitiated : .utility) {
                let data = try await Self.download(request, priority: priority)
                guard let image = Self.downsample(data, maxPixel: maxPixel) else {
                    throw BackendError.invalidResponse
                }
                return image
            }
            inflight[key] = Download(task: task, waiting: [waiter])
        }
        let image: UIImage
        do {
            image = try await withTaskCancellationHandler {
                try await task.value
            } onCancel: {
                Task { await self.abandon(key, waiter: waiter) }
            }
        } catch {
            finish(key, task: task)
            throw error
        }
        finish(key, task: task)
        let cost = Int(image.size.width * image.size.height * image.scale * image.scale * 4)
        cache.setObject(image, forKey: key as NSString, cost: cost)
        return image
    }

    private func finish(_ key: String, task: Task<UIImage, Error>) {
        guard inflight[key]?.task == task else { return }
        inflight[key] = nil  // done: the next ask downloads again or finds it cached
    }

    /// A view stopped waiting; with nobody else waiting, the download goes.
    private func abandon(_ key: String, waiter: UUID) {
        guard var running = inflight[key], running.waiting.remove(waiter) != nil else { return }
        if running.waiting.isEmpty {
            inflight[key] = nil
            running.task.cancel()
        } else {
            inflight[key] = running
        }
    }

    // MARK: Downloads

    private static let gate = HostGate()
    /// Connections of their own: a burst of thumbnails, each waiting for
    /// the server to fetch it from a museum, fills neither the line of the
    /// app's other requests nor that of the picture looked at.
    private static let sessions: [Priority: URLSession] = [
        .normal: session(), .high: session(),
    ]
    /// Answers worth another try: throttled (museums and Commons answer a
    /// grid's burst with 429) or briefly down.
    private static let retryStatus: Set<Int> = [408, 429, 500, 502, 503, 504]
    private static let attempts = 3

    private static func session() -> URLSession {
        let configuration = URLSessionConfiguration.default
        configuration.urlCache = .shared
        configuration.httpMaximumConnectionsPerHost = 6
        return URLSession(configuration: configuration)
    }

    /// The picture's bytes: thumbnails a few per host at a time, the one
    /// looked at right away; tried again after a short wait when the host
    /// is busy.
    private static func download(_ request: URLRequest, priority: Priority) async throws -> Data {
        let session = sessions[priority] ?? .shared
        guard priority == .normal else { return try await fetch(request, session: session) }
        let host = request.url?.host ?? ""
        try await gate.enter(host)
        do {
            let data = try await fetch(request, session: session)
            await gate.leave(host)
            return data
        } catch {
            await gate.leave(host)
            throw error
        }
    }

    private static func fetch(_ request: URLRequest, session: URLSession) async throws -> Data {
        var attempt = 1
        while true {
            do {
                let (data, response) = try await session.data(for: request)
                let status = (response as? HTTPURLResponse)?.statusCode ?? 200
                if (200 ..< 300).contains(status) { return data }
                guard retryStatus.contains(status), attempt < attempts else {
                    throw BackendError.http(status: status, body: "")
                }
                try await Task.sleep(for: .seconds(retryDelay(response, attempt: attempt)))
            } catch let error as URLError where error.code != .cancelled && attempt < attempts {
                try await Task.sleep(for: .seconds(attempt))
            }
            attempt += 1
        }
    }

    /// What the host asked for in Retry-After, else a growing pause; a few
    /// seconds at most, so a grid still fills in.
    private static func retryDelay(_ response: URLResponse, attempt: Int) -> Double {
        let asked = (response as? HTTPURLResponse)?
            .value(forHTTPHeaderField: "Retry-After")
            .flatMap { Double($0) }
        return min(max(asked ?? 1.5 * Double(attempt), 0.5), 8)
    }

    private static func downsample(_ data: Data, maxPixel: CGFloat) -> UIImage? {
        let options = [kCGImageSourceShouldCache: false] as CFDictionary
        guard let source = CGImageSourceCreateWithData(data as CFData, options) else { return nil }
        let thumbOptions = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceShouldCacheImmediately: true,
            kCGImageSourceThumbnailMaxPixelSize: maxPixel,
        ] as CFDictionary
        guard let cgImage = CGImageSourceCreateThumbnailAtIndex(source, 0, thumbOptions) else {
            return nil
        }
        return UIImage(cgImage: cgImage)
    }
}

/// Lets a few downloads per host run at once; the rest wait in line, and
/// one cancelled while waiting leaves it. Commons allows two parallel media
/// requests, museum CDNs throttle bursts too.
private actor HostGate {
    private typealias Waiter = (id: UUID, continuation: CheckedContinuation<Void, Error>)

    private var running: [String: Int] = [:]
    private var waiting: [String: [Waiter]] = [:]
    /// On their way into the line, and those of them cancelled already.
    private var coming: Set<UUID> = []
    private var cancelled: Set<UUID> = []

    private static func limit(_ host: String) -> Int {
        host.hasSuffix("wikimedia.org") ? 2 : 4
    }

    func enter(_ host: String) async throws {
        try Task.checkCancellation()
        if running[host, default: 0] < Self.limit(host) {
            running[host, default: 0] += 1
            return
        }
        let id = UUID()
        coming.insert(id)
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                Task { await self.wait(id, continuation, for: host) }
            }
        } onCancel: {
            Task { await self.cancel(id, for: host) }
        }
    }

    private func wait(_ id: UUID, _ continuation: CheckedContinuation<Void, Error>, for host: String) {
        coming.remove(id)
        if cancelled.remove(id) != nil {
            continuation.resume(throwing: CancellationError())
        } else if running[host, default: 0] < Self.limit(host) {
            running[host, default: 0] += 1
            continuation.resume()
        } else {
            waiting[host, default: []].append((id, continuation))
        }
    }

    private func cancel(_ id: UUID, for host: String) {
        if let index = waiting[host]?.firstIndex(where: { $0.id == id }) {
            let waiter = waiting[host]!.remove(at: index)
            waiter.continuation.resume(throwing: CancellationError())
        } else if coming.contains(id) {
            cancelled.insert(id)  // not in line yet: it leaves as it comes
        }
    }

    func leave(_ host: String) {
        if var queue = waiting[host], !queue.isEmpty {
            // The slot passes straight to the next in line.
            let next = queue.removeFirst()
            waiting[host] = queue
            next.continuation.resume()
        } else {
            running[host, default: 1] -= 1
        }
    }
}

/// A picture from the library or the server, with a soft placeholder in the
/// artwork's own dominant colour while it loads.
struct ArtImage: View {
    @Environment(AppModel.self) private var model
    @Environment(\.artImageLoaded) private var loaded
    let ref: ImageRef
    /// Tried when `ref` fails: the server's copy of a museum's thumbnail.
    var fallback: ImageRef?
    var placeholder: Color = Theme.mat
    var maxPixel: CGFloat = 900
    var contentMode: ContentMode = .fill
    /// `.high` for the picture the screen is about, ahead of thumbnails.
    var priority: ImageLoader.Priority = .normal
    /// Filling a box of another shape, crop around the faces or what draws
    /// the eye instead of through the middle.
    var subjectFocus = false

    @State private var image: UIImage?
    @State private var focus: UnitPoint = .center
    @State private var failed = false

    var body: some View {
        ZStack {
            if let image, subjectFocus, contentMode == .fill {
                FocusedFill(image: image, focus: focus)
                    .transition(.opacity)
            } else if let image {
                Image(uiImage: image)
                    .resizable()
                    .aspectRatio(contentMode: contentMode)
                    .transition(.opacity)
            } else {
                Rectangle()
                    .fill(placeholder.gradient)
                    .overlay {
                        if failed {
                            Image(systemName: "photo")
                                .font(.title2)
                                .foregroundStyle(.secondary)
                        }
                    }
            }
        }
        .animation(.easeOut(duration: 0.35), value: image != nil)
        .task(id: ref) {
            await load()
        }
    }

    private func load() async {
        let ref = ref
        failed = false
        var key = ""
        for candidate in [ref, fallback].compactMap({ $0 }) {
            guard let request = model.backend.request(for: candidate) else { continue }
            do {
                let loaded = try await ImageLoader.shared.image(for: request, maxPixel: maxPixel, priority: priority)
                key = request.url?.absoluteString ?? ""
                if subjectFocus {
                    focus = await SubjectFocus.shared.cached(key) ?? .center
                }
                image = loaded
                break
            } catch {
                if Task.isCancelled { return }
            }
        }
        failed = image == nil
        if !Task.isCancelled { loaded(ref) }
        // The picture shows at once, centred; the crop glides to its
        // subject once found. Never wait for it: the picture comes first.
        if subjectFocus, let image, !Task.isCancelled, await SubjectFocus.shared.cached(key) == nil {
            let point = await SubjectFocus.shared.point(in: image, key: key)
            if !Task.isCancelled {
                withAnimation(.easeInOut(duration: 0.5)) { focus = point }
            }
        }
    }
}

private struct ArtImageLoadedKey: EnvironmentKey {
    static let defaultValue: (ImageRef) -> Void = { _ in }
}

extension EnvironmentValues {
    /// Told when an `ArtImage` inside has its picture, or gave up on it.
    var artImageLoaded: (ImageRef) -> Void {
        get { self[ArtImageLoadedKey.self] }
        set { self[ArtImageLoadedKey.self] = newValue }
    }
}
