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

    private let cache = Memory.shared.cache
    private var inflight: [String: Download] = [:]

    /// The pictures in memory, readable without waiting for the loader.
    private final class Memory: @unchecked Sendable {
        static let shared = Memory()
        /// NSCache is safe to use from any thread.
        let cache = NSCache<NSString, UIImage>()
        private let lock = NSLock()
        private var server: ServerRoute?
        /// Works whose crop was saved since launch, and how many times: their
        /// framed previews are kept under a new name each time.
        private var reframeCounts: [String: Int] = [:]
        /// Works whose picture changed since launch (another copy of it),
        /// and how many times: their thumbnails and framed previews too.
        private var repictureCounts: [String: Int] = [:]
        /// Framed previews fetched past the disk cache since their work's
        /// last crop, by address.
        private var refetchedAt: [String: Int] = [:]

        private init() {
            cache.totalCostLimit = 160 * 1024 * 1024
        }

        /// The frame server's addresses (at home, away) and the one in use.
        var route: ServerRoute? {
            get { lock.withLock { server } }
            set { lock.withLock { server = newValue } }
        }

        func reframe(_ itemID: String) {
            lock.withLock { reframeCounts[itemID, default: 0] += 1 }
        }

        func reframes(_ itemID: String) -> Int {
            lock.withLock { reframeCounts[itemID] ?? 0 }
        }

        func repicture(_ itemID: String) {
            lock.withLock { repictureCounts[itemID, default: 0] += 1 }
        }

        func repictures(_ itemID: String) -> Int {
            lock.withLock { repictureCounts[itemID] ?? 0 }
        }

        /// The address must skip the disk cache: fetched there before the
        /// work's last crop, or not at all since.
        func stale(_ url: String, reframes: Int) -> Bool {
            lock.withLock { refetchedAt[url] != reframes }
        }

        func refetched(_ url: String, reframes: Int) {
            lock.withLock { refetchedAt[url] = reframes }
        }
    }

    /// The frame server's addresses: a picture of the server's is the same
    /// one whichever of them it came from, so the last launch's "Teraz",
    /// remembered under the address at home, is found away from home too;
    /// and one still loading from an address the app has left is asked at
    /// the other one.
    nonisolated static func sameServer(_ route: ServerRoute?) {
        Memory.shared.route = route
    }

    private static var route: ServerRoute? { Memory.shared.route }

    /// The work's crop was saved: its framed previews are drawn anew. The
    /// one without a crop in the address (a study or card opened later,
    /// the pictures coming up on "Teraz") stood an hour in the disk cache
    /// and for the whole launch in memory, so the old crop came back.
    /// `requests`: such addresses, dropped from the disk cache now so the
    /// next launch does not find them either.
    nonisolated static func reframed(_ itemID: String, requests: [URLRequest]) {
        Memory.shared.reframe(itemID)
        for request in requests {
            URLCache.shared.removeCachedResponse(for: request)
            if let other = route?.rebased(request) { URLCache.shared.removeCachedResponse(for: other) }
        }
    }

    /// The work's picture changed (the owner picked another copy of it,
    /// or the server found a sharper one): its thumbnail and framed
    /// previews are had anew. The thumbnail stood a day in the disk cache
    /// and for the whole launch in memory, so every list kept the old
    /// picture, in other tones or with the frame round it (Mateusz
    /// 2026-11-04). `requests`: such addresses, dropped from the disk cache
    /// now so the next launch does not find them either.
    nonisolated static func repictured(_ itemID: String, requests: [URLRequest]) {
        Memory.shared.repicture(itemID)
        for request in requests {
            URLCache.shared.removeCachedResponse(for: request)
            if let other = route?.rebased(request) { URLCache.shared.removeCachedResponse(for: other) }
        }
    }

    /// The work whose framed preview or thumbnail `request` asks for, with
    /// the times it changed since launch (a preview: its crop saved or its
    /// picture changed; a thumbnail: its picture); nil for any other
    /// picture, or one unchanged.
    private static func reframes(_ request: URLRequest) -> (id: String, count: Int)? {
        guard let url = request.url,
              let path = URLComponents(url: url, resolvingAgainstBaseURL: false)?.percentEncodedPath
        else { return nil }
        let preview = path.hasSuffix("/preview")
        guard preview || path.hasSuffix("/thumb") else { return nil }
        let parts = path.split(separator: "/")  // …/library/items/<id>/preview
        guard parts.count >= 4, parts[parts.count - 3] == "items", parts[parts.count - 4] == "library",
              let id = String(parts[parts.count - 2]).removingPercentEncoding
        else { return nil }
        let count = Memory.shared.repictures(id) + (preview ? Memory.shared.reframes(id) : 0)
        return count > 0 ? (id, count) : nil
    }

    /// What a picture's subject is remembered under: not where it was in
    /// the work's picture before another copy took its place.
    nonisolated static func pictureKey(_ request: URLRequest) -> String {
        let changed = reframes(request).map { "~\($0.count)" } ?? ""
        return (request.url?.absoluteString ?? "") + changed
    }

    /// What the picture is kept under in memory: the server's own pictures
    /// by their path, not by the address they were asked at.
    private static func key(_ request: URLRequest, _ maxPixel: CGFloat) -> String {
        var url = request.url?.absoluteString ?? ""
        if let route {
            let servers = [route.home, route.remote].compactMap { $0?.absoluteString }
                .map { $0.hasSuffix("/") ? String($0.dropLast()) : $0 }
            if let server = servers.first(where: { url.hasPrefix($0 + "/") }) {
                url = "server:" + url.dropFirst(server.count)
            }
        }
        if let reframed = reframes(request) { url += "~\(reframed.count)" }  // not the one from before the crop
        return "\(url)#\(Int(maxPixel))"
    }

    /// What a download is shared under: the address too, so a picture asked
    /// again at the other address does not wait for one that went nowhere;
    /// not one started before the work's crop was saved.
    private static func downloadKey(_ request: URLRequest, _ maxPixel: CGFloat) -> String {
        let reframed = reframes(request).map { "~\($0.count)" } ?? ""
        return "\(request.url?.absoluteString ?? "")\(reframed)#\(Int(maxPixel))"
    }

    /// The picture loaded for `request` at `maxPixel`, if it is in memory,
    /// right now: a screen opened over another that showed it (a study over
    /// the work's card) starts with it instead of fading it in again.
    nonisolated static func inMemory(for request: URLRequest, maxPixel: CGFloat) -> UIImage? {
        Memory.shared.cache.object(forKey: key(request, maxPixel) as NSString)
    }

    func image(for request: URLRequest, maxPixel: CGFloat, priority: Priority = .normal) async throws -> UIImage {
        let memoryKey = Self.key(request, maxPixel)
        if let cached = cache.object(forKey: memoryKey as NSString) { return cached }
        let key = Self.downloadKey(request, maxPixel)
        let waiter = UUID()
        let task: Task<UIImage, Error>
        if var running = inflight[key] {
            running.waiting.insert(waiter)
            inflight[key] = running
            task = running.task
        } else {
            // Detached: downsampling runs beside this actor, not on it.
            // A framed preview first asked since its work's crop was saved
            // (or a thumbnail since its picture changed) skips the disk
            // cache, which may hold it with the old crop or picture.
            var request = request
            let address = request.url?.absoluteString ?? ""
            let reframed = Self.reframes(request)?.count
            if let reframed, Memory.shared.stale(address, reframes: reframed) {
                request.cachePolicy = .reloadIgnoringLocalCacheData
            }
            task = Task.detached(priority: priority == .high ? .userInitiated : .utility) { [request] in
                let data = try await Self.download(request, priority: priority)
                if let reframed { Memory.shared.refetched(address, reframes: reframed) }
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
        cache.setObject(image, forKey: memoryKey as NSString, cost: cost)
        return image
    }

    /// A picture kept from before (the last launch's "Teraz"), as if it had
    /// just been loaded for `request` at `maxPixel`.
    func remember(_ image: UIImage, for request: URLRequest, maxPixel: CGFloat) {
        let key = Self.key(request, maxPixel)
        guard cache.object(forKey: key as NSString) == nil else { return }
        let cost = Int(image.size.width * image.size.height * image.scale * image.scale * 4)
        cache.setObject(image, forKey: key as NSString, cost: cost)
    }

    /// The picture loaded for `request` at `maxPixel`, if it is in memory.
    func cached(for request: URLRequest, maxPixel: CGFloat) -> UIImage? {
        cache.object(forKey: Self.key(request, maxPixel) as NSString)
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
        var request = request
        var attempt = 1
        var looked = false
        while true {
            do {
                let (data, response) = try await send(request, session: session)
                let status = (response as? HTTPURLResponse)?.statusCode ?? 200
                if (200 ..< 300).contains(status) { return data }
                guard retryStatus.contains(status), attempt < attempts else {
                    throw BackendError.http(status: status, body: "")
                }
                try await Task.sleep(for: .seconds(retryDelay(response, attempt: attempt)))
            } catch let error as URLError where error.code != .cancelled && attempt < attempts {
                // The server's address did not answer: the other one, once.
                if !looked, let route, route.hasRemote, route.serves(request), ServerRoute.unreachable(error),
                   await route.resolve() != nil, let moved = route.rebased(request) {
                    looked = true
                    request = moved
                    continue
                }
                try await Task.sleep(for: .seconds(attempt))
            }
            attempt += 1
        }
    }

    /// The server's pictures follow it to its other address mid-download.
    /// Pictures from the server's Tailscale address come through the app's
    /// own Tailscale node (`Tailnet`), with the same disk cache.
    private static func send(_ request: URLRequest, session: URLSession) async throws -> (Data, URLResponse) {
        let load: @Sendable (URLRequest) async throws -> (Data, URLResponse) = { request in
            try await Tailnet.shared.send(request, else: session, images: true) { try await $0.data(for: request) }
        }
        guard let route else { return try await load(request) }
        return try await route.follow(request, load)
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
    /// The artwork itself (the work's card, the study): shown a little
    /// brighter than the page (`ArtGlow`) when Konfiguracja allows it.
    var brighten = false

    /// Pauses before the picture is asked for again on its own.
    static let retryDelays: [Duration] = [.seconds(4), .seconds(15), .seconds(45)]

    @State private var image: UIImage?
    /// The ref `image` was loaded for.
    @State private var shownRef: ImageRef?
    /// `picture` when the image shown was loaded.
    @State private var shownPicture = 0
    @State private var focus: UnitPoint = .center
    @State private var failed = false
    @AppStorage(ArtGlow.key) private var glowAllowed = true
    @AppStorage(ArtGlow.gainKey) private var glowGain = ArtGlow.defaultGain
    /// The brighter copy of the picture shown (`brighten`).
    @State private var glowing: UIImage?

    private var glows: Bool { brighten && glowAllowed }

    private struct GlowJob: Equatable {
        let image: ObjectIdentifier?
        let on: Bool
        let gain: Double
    }

    /// Failed, and shows it: a clear placeholder lies over another picture
    /// (the card's original over the tile's thumbnail), which speaks for it.
    private var retries: Bool { failed && placeholder != .clear }

    /// How many times the work's picture changed since launch (another
    /// copy): a thumbnail or preview from before is had anew.
    private var picture: Int {
        switch ref {
        case let .thumb(id), let .framePreview(id, _, _, _): model.pictureChanges[id] ?? 0
        default: 0
        }
    }

    private struct Round: Hashable {
        let ref: ImageRef
        /// The work's picture changed (another copy): asked for again.
        let picture: Int
        let retries: Int
        /// A new address of the server: asked there again.
        let switches: Int
    }

    /// The picture loaded, else one already in memory for `ref`: shown from
    /// the first frame, not faded in from the placeholder (which blinked
    /// a picture the screen before had shown, and every cover of a lazy
    /// row scrolled back into view). Not where the subject is still to be
    /// found: it would slide once found.
    private var shown: UIImage? {
        if let image { return image }
        guard let request = model.backend.request(for: ref) else { return nil }
        if subjectFocus, focusPoint == nil, SubjectFocus.known(ImageLoader.pictureKey(request)) == nil { return nil }
        return ImageLoader.inMemory(for: request, maxPixel: maxPixel)
    }

    /// Where the picture shown is cropped around: the point given, else
    /// the one found for it; a picture from memory, not loaded yet, by the
    /// point found for it before.
    private var shownFocus: UnitPoint {
        if let focusPoint { return focusPoint }
        if image == nil, subjectFocus, let request = model.backend.request(for: ref),
           let known = SubjectFocus.known(ImageLoader.pictureKey(request)) {
            return known
        }
        return focus
    }

    /// What is drawn: the brighter copy once made (from the cache at once
    /// when it was made before), else the picture itself.
    private var drawn: UIImage? {
        guard let shown else { return nil }
        guard glows else { return shown }
        return ArtGlow.cached(shown, gain: glowGain) ?? glowing ?? shown
    }

    var body: some View {
        ZStack {
            if let image = drawn, subjectFocus || focusPoint != nil, contentMode == .fill {
                FocusedFill(image: image, focus: shownFocus)
                    .transition(.opacity)
            } else if let image = drawn {
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
        .allowedDynamicRange(glows ? .high : nil)
        .task(id: GlowJob(image: shown.map(ObjectIdentifier.init), on: glows, gain: glowGain)) {
            guard glows, let source = shown else {
                glowing = nil
                return
            }
            if ArtGlow.cached(source, gain: glowGain) != nil { return }
            // The last brighter copy stays up until this one is ready.
            if let lit = await ArtGlow.image(source, gain: glowGain), !Task.isCancelled {
                withAnimation(.easeInOut(duration: 0.25)) { glowing = lit }
            }
        }
        .task(id: Round(ref: ref, picture: picture, retries: model.pictureRetries, switches: model.serverSwitches)) {
            await load()
        }
    }

    private enum Outcome {
        case loaded, failed, missing, cancelled
    }

    private func load() async {
        let ref = ref
        let picture = picture
        // Another round of retries: a picture already here stays. One
        // from before its work's picture changed is asked for again, and
        // stays until the new one is here.
        if image != nil, shownRef == ref, shownPicture == picture { return }
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
                    let point = await SubjectFocus.shared.point(in: loaded, key: ImageLoader.pictureKey(request))
                    if Task.isCancelled { return .cancelled }
                    focus = point
                }
                if crossfade, image != nil, image !== loaded {
                    withAnimation(.easeInOut(duration: 0.5)) { image = loaded }
                } else {
                    image = loaded
                }
                shownRef = ref
                shownPicture = picture
                return .loaded
            } catch {
                if Task.isCancelled { return .cancelled }
                if case let .http(status, _) = error as? BackendError, let id = candidate.itemID {
                    if status == 410 {
                        model.pictureMissing(id)
                        missing = true
                    } else if status == 503 {
                        // The museum turned the server away for now: asked
                        // again only after the pause, not every few seconds.
                        model.picturePaused(id)
                        missing = true
                    }
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
