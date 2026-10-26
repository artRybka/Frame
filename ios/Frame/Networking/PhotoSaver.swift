import Foundation
import ImageIO
import Photos
import UniformTypeIdentifiers

/// "Zapisz w Zdjęciach": a work into the phone's photos, as large as it can
/// be had. A museum work comes straight from the museum (the server keeps
/// a copy of at most 2560 px); the server's copy is the fallback and the
/// only source for photos. Asks only to add to Photos, never to read them.
enum PhotoSaver {
    enum Failure: LocalizedError {
        case denied
        /// Why the last source failed, when known.
        case unavailable(String?)

        var errorDescription: String? {
            switch self {
            case .denied: "Zezwól na dodawanie zdjęć: Ustawienia → Frame → Zdjęcia"
            case let .unavailable(reason): "Nie udało się zapisać obrazu" + (reason.map { ": \($0)" } ?? "")
            }
        }
    }

    /// What Photos takes as it is.
    private static let accepted: [UTType] = [.jpeg, .png, .heic, .heif, .tiff]
    /// Larger museum files (a few huge TIFFs) give way to the server's copy.
    private static let maxBytes = 150 * 1024 * 1024

    /// Where the picture can come from, largest first.
    static func sources(for item: Item, backend: any FrameBackend) -> [URLRequest] {
        var sources: [URLRequest] = []
        // A photo's address (an iCloud album's) expires; its server copy is the original.
        if item.kind == .artwork, let url = URL(string: item.imageUrl),
           url.scheme == "https" || url.scheme == "http"
        {
            sources.append(URLRequest(url: url, timeoutInterval: 120))
        }
        if let server = backend.request(for: .image(item.id)) { sources.append(server) }
        return sources
    }

    /// The name the picture gets in Photos: artist and title.
    static func fileName(for item: Item) -> String {
        let parts = [item.artist, item.title.isEmpty ? "Bez tytułu" : item.title]
            .filter { !$0.isEmpty }
            .joined(separator: " – ")
        let separators = CharacterSet(charactersIn: "/\\:?*\"<>|").union(.whitespacesAndNewlines)
        let cleaned = parts.components(separatedBy: separators)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
        return String(cleaned.prefix(100))
    }

    static func save(_ item: Item, backend: any FrameBackend) async throws {
        let access = await PHPhotoLibrary.requestAuthorization(for: .addOnly)
        guard access == .authorized || access == .limited else { throw Failure.denied }
        var lastError: Error = Failure.unavailable(nil)
        for source in sources(for: item, backend: backend) {
            if Task.isCancelled { throw CancellationError() }
            do {
                let (data, type) = try await download(source)
                let name = "\(fileName(for: item)).\(type.preferredFilenameExtension ?? "jpg")"
                // From memory, not a file: Photos refuses a file whose name has
                // no extension, and the download's file has none.
                try await PHPhotoLibrary.shared().performChanges {
                    let options = PHAssetResourceCreationOptions()
                    options.originalFilename = name
                    options.uniformTypeIdentifier = type.identifier
                    PHAssetCreationRequest.forAsset().addResource(with: .photo, data: data, options: options)
                }
                return
            } catch {
                lastError = error  // e.g. a format Photos does not take: the server's copy next
            }
        }
        throw (lastError as? Failure) ?? Failure.unavailable(lastError.localizedDescription)
    }

    /// The picture's bytes and type, if it is one Photos takes.
    private static func download(_ request: URLRequest) async throws -> (Data, UTType) {
        let (file, response) = try await URLSession.shared.download(for: request)
        defer { try? FileManager.default.removeItem(at: file) }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 200
        guard (200 ..< 300).contains(status) else {
            throw Failure.unavailable("serwer odpowiedział \(status)")
        }
        let data = try Data(contentsOf: file)
        guard data.count <= maxBytes else { throw Failure.unavailable("plik za duży") }
        guard let image = CGImageSourceCreateWithData(data as CFData, nil),
              CGImageSourceGetCount(image) > 0,
              let identifier = CGImageSourceGetType(image) as String?,
              let type = UTType(identifier),
              accepted.contains(where: { type.conforms(to: $0) })
        else {
            throw Failure.unavailable("nieobsługiwany format")
        }
        return (data, type)
    }
}
