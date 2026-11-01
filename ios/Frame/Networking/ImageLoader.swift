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

    /// A picture kept from before (the last launch's "Teraz"), as if it had
    /// just been loaded for `request` at `maxPixel`.
    func remember(_ image: UIImage, for request: URLRequest, maxPixel: CGFloat) {
        let key = "\(request.url?.absoluteString ?? "")#\(Int(maxPixel))"
        guard cache.object(forKey: key as NSString) == nil else { return }
        let cost = Int(image.size.width * image.size.height * image.scale * image.scale * 4)
        cache.setObject(image, forKey: key as NSString, cost: cost)
    }

    /// The picture loaded for `request` at `maxPixel`, if it is in memory.
    func cached(for request: URLRequest, maxPixel: CGFloat) -> UIImage? {
        cache.object(forKey: "\(request.url?.absoluteString ?? "")#\(Int(maxPixel))" as NSString)
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
///
/// One that did not load tries again on its own a few times while it is on
/// screen (a museum's image server turns the frame's server away for a
/// while); a tap on it tries again at once, with every other picture on
/// screen that failed. A work the server has no picture of anywhere (410)
/// is told to the model, and grids leave it out.
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
    /// A known place to crop around instead (fractions of the picture).
    var focusPoint: UnitPoint?
    /// A new picture fades in over the one before instead of taking its
    /// place at once ("Teraz" from the last launch, then the fresh one).
    var crossfade = false

    /// Pauses before the picture is asked for again on its own.
    static let retryDelays: [Duration] = [.seconds(4), .seconds(15), .seconds(45)]

    @State private var image: UIImage?
    /// The ref `image` was loaded for.
    @State private var shownRef: ImageRef?
    @State private var focus: UnitPoint = .center
    @State private var failed = false

    /// Failed, and shows it: a clear placeholder lies over another picture
    /// (the card's original over the tile's thumbnail), which speaks for it.
    private var retries: Bool { failed && placeholder != .clear }

    private struct Round: Hashable {
        let ref: ImageRef
        let retries: Int
    }

    var body: some View {
        ZStack {
            if let image, subjectFocus || focusPoint != nil, contentMode == .fill {
                FocusedFill(image: image, focus: focus)
                    .transition(.opacity)
            } else if let image {
                Image(uiImage: image)
                    .resizable()
                    .aspectRatio(contentMode: contentMode)
                    .transition(.opacity)
                    .id(crossfade ? ObjectIdentifier(image) : nil)
            } else {
                Rectangle()
                    .fill(placeholder.gradient)
                    .overlay {
                        if retries {
                            Image(systemName: "arrow.clockwise")
                                .font(.title2)
                                .foregroundStyle(.secondary)
                                .accessibilityLabel("Obraz się nie wczytał")
                                .accessibilityHint("Dotknij, aby spróbować ponownie")
                        }
                    }
                    .contentShape(Rectangle())
                    .onTapGesture { model.retryPictures() }
                    .allowsHitTesting(retries)
            }
        }
        .animation(.easeOut(duration: 0.35), value: image != nil)
        .task(id: Round(ref: ref, retries: model.pictureRetries)) {
            await load()
        }
    }

    private enum Outcome {
        case loaded, failed, missing, cancelled
    }

    private func load() async {
        let ref = ref
        // Another round of retries: a picture already here stays.
        if image != nil, shownRef == ref { return }
        failed = false
        var told = false
        for delay in [Duration.zero] + Self.retryDelays {
            if delay > .zero {
                try? await Task.sleep(for: delay)
            }
            if Task.isCancelled { return }
            let outcome = await attempt(ref)
            switch outcome {
            case .loaded:
                failed = false
                loaded(ref)
                return
            case .cancelled:
                return
            case .failed, .missing:
                failed = image == nil
                if !told {
                    told = true
                    loaded(ref)  // gave up for now: the screen stops waiting
                }
                if outcome == .missing { return }
            }
        }
    }

    private func attempt(_ ref: ImageRef) async -> Outcome {
        var missing = false
        for candidate in [ref, fallback].compactMap({ $0 }) {
            guard let request = model.backend.request(for: candidate) else { continue }
            do {
                let loaded = try await ImageLoader.shared.image(for: request, maxPixel: maxPixel, priority: priority)
                if let focusPoint {
                    focus = focusPoint
                } else if subjectFocus {
                    // The placeholder stays until the crop is known, so the
                    // picture fades in already framed instead of sliding.
                    let point = await SubjectFocus.shared.point(in: loaded, key: request.url?.absoluteString ?? "")
                    if Task.isCancelled { return .cancelled }
                    focus = point
                }
                if crossfade, image != nil, image !== loaded {
                    withAnimation(.easeInOut(duration: 0.5)) { image = loaded }
                } else {
                    image = loaded
                }
                shownRef = ref
                return .loaded
            } catch {
                if Task.isCancelled { return .cancelled }
                if case let .http(status, _) = error as? BackendError, status == 410,
                   let id = candidate.itemID {
                    model.pictureMissing(id)
                    missing = true
                }
            }
        }
        return missing ? .missing : .failed
    }
}

extension ImageRef {
    /// The library work whose picture this is, for the server's own copies.
    var itemID: String? {
        switch self {
        case let .thumb(id), let .image(id), let .original(id, _): id
        default: nil
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
