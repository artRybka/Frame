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
        case denied, unavailable

        var errorDescription: String? {
            switch self {
            case .denied: "Zezwól na dodawanie zdjęć: Ustawienia → Frame → Zdjęcia"
            case .unavailable: "Nie udało się pobrać obrazu"
            }
        }
    }

    /// What Photos takes as it is.
    private static let accepted: [UTType] = [.jpeg, .png, .heic, .heif, .tiff]

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
        for source in sources(for: item, backend: backend) {
            if Task.isCancelled { throw CancellationError() }
            guard let file = try? await download(source) else { continue }
            defer { try? FileManager.default.removeItem(at: file.url) }
            let name = "\(fileName(for: item)).\(file.type.preferredFilenameExtension ?? "jpg")"
            do {
                try await PHPhotoLibrary.shared().performChanges {
                    let options = PHAssetResourceCreationOptions()
                    options.originalFilename = name
                    options.uniformTypeIdentifier = file.type.identifier
                    PHAssetCreationRequest.forAsset().addResource(with: .photo, fileURL: file.url, options: options)
                }
                return
            } catch {
                continue  // e.g. too large for Photos: the server's copy next
            }
        }
        throw Failure.unavailable
    }

    /// The picture in a file of its own, if it is one Photos takes.
    private static func download(_ request: URLRequest) async throws -> (url: URL, type: UTType) {
        let (temporary, response) = try await URLSession.shared.download(for: request)
        let file = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        try FileManager.default.moveItem(at: temporary, to: file)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 200
        guard (200 ..< 300).contains(status),
              let image = CGImageSourceCreateWithURL(file as CFURL, nil),
              CGImageSourceGetCount(image) > 0,
              let identifier = CGImageSourceGetType(image) as String?,
              let type = UTType(identifier),
              accepted.contains(where: { type.conforms(to: $0) })
        else {
            try? FileManager.default.removeItem(at: file)
            throw Failure.unavailable
        }
        return (file, type)
    }
}
