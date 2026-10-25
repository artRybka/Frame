import ImageIO
import SwiftUI
import UIKit

/// Loads, downsamples and caches pictures. Downsampling with ImageIO keeps
/// grids of large museum images light on memory.
actor ImageLoader {
    static let shared = ImageLoader()

    private let cache = NSCache<NSString, UIImage>()
    private var inflight: [String: Task<UIImage, Error>] = [:]

    init() {
        cache.totalCostLimit = 160 * 1024 * 1024
    }

    func image(for request: URLRequest, maxPixel: CGFloat) async throws -> UIImage {
        let key = "\(request.url?.absoluteString ?? "")#\(Int(maxPixel))" as NSString
        if let cached = cache.object(forKey: key) { return cached }
        if let running = inflight[key as String] { return try await running.value }
        let task = Task<UIImage, Error> {
            let data = try await Self.download(request)
            guard let image = Self.downsample(data, maxPixel: maxPixel) else {
                throw BackendError.invalidResponse
            }
            return image
        }
        inflight[key as String] = task
        defer { inflight[key as String] = nil }
        let image = try await task.value
        let cost = Int(image.size.width * image.size.height * image.scale * image.scale * 4)
        cache.setObject(image, forKey: key, cost: cost)
        return image
    }

    // MARK: Downloads

    private static let gate = HostGate()
    /// Answers worth another try: throttled (museums and Commons answer a
    /// grid's burst with 429) or briefly down.
    private static let retryStatus: Set<Int> = [408, 429, 500, 502, 503, 504]
    private static let attempts = 3

    /// The picture's bytes, a few downloads per host at a time, trying again
    /// after a short wait when the host is busy.
    private static func download(_ request: URLRequest) async throws -> Data {
        let host = request.url?.host ?? ""
        await gate.enter(host)
        do {
            let data = try await fetch(request)
            await gate.leave(host)
            return data
        } catch {
            await gate.leave(host)
            throw error
        }
    }

    private static func fetch(_ request: URLRequest) async throws -> Data {
        var attempt = 1
        while true {
            do {
                let (data, response) = try await URLSession.shared.data(for: request)
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

/// Lets a few downloads per host run at once; the rest wait in line. Commons
/// allows two parallel media requests, museum CDNs throttle bursts too.
private actor HostGate {
    private var running: [String: Int] = [:]
    private var waiting: [String: [CheckedContinuation<Void, Never>]] = [:]

    private static func limit(_ host: String) -> Int {
        host.hasSuffix("wikimedia.org") ? 2 : 4
    }

    func enter(_ host: String) async {
        if running[host, default: 0] < Self.limit(host) {
            running[host, default: 0] += 1
            return
        }
        await withCheckedContinuation { continuation in
            Task { await self.wait(continuation, for: host) }
        }
    }

    private func wait(_ continuation: CheckedContinuation<Void, Never>, for host: String) {
        if running[host, default: 0] < Self.limit(host) {
            running[host, default: 0] += 1
            continuation.resume()
        } else {
            waiting[host, default: []].append(continuation)
        }
    }

    func leave(_ host: String) {
        if var queue = waiting[host], !queue.isEmpty {
            // The slot passes straight to the next in line.
            let next = queue.removeFirst()
            waiting[host] = queue
            next.resume()
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

    @State private var image: UIImage?
    @State private var failed = false

    var body: some View {
        ZStack {
            if let image {
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
        for candidate in [ref, fallback].compactMap({ $0 }) {
            guard let request = model.backend.request(for: candidate) else { continue }
            do {
                image = try await ImageLoader.shared.image(for: request, maxPixel: maxPixel)
                break
            } catch {
                if Task.isCancelled { return }
            }
        }
        failed = image == nil
        if !Task.isCancelled { loaded(ref) }
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
