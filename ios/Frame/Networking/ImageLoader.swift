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
            let (data, response) = try await URLSession.shared.data(for: request)
            if let http = response as? HTTPURLResponse, !(200 ..< 300).contains(http.statusCode) {
                throw BackendError.http(status: http.statusCode, body: "")
            }
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

/// A picture from the library or the server, with a soft placeholder in the
/// artwork's own dominant colour while it loads.
struct ArtImage: View {
    @Environment(AppModel.self) private var model
    @Environment(\.artImageLoaded) private var loaded
    let ref: ImageRef
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
        guard let request = model.backend.request(for: ref) else {
            failed = true
            loaded(ref)
            return
        }
        do {
            image = try await ImageLoader.shared.image(for: request, maxPixel: maxPixel)
        } catch {
            failed = true
        }
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
