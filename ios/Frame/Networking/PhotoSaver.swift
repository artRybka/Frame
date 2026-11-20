import Foundation
import ImageIO
import Photos
import UniformTypeIdentifiers

/// "Zapisz w Zdjęciach": a work into the phone's photos, as large as it can
/// be had. A museum work comes straight from the museum; the server's copy
/// (up to some 4000 px) is the fallback and the only source for photos.
/// A work shown cut out of its photograph, or with its colours corrected
/// for this person ("Zdejmij werniks", "Odżółć papier"), is saved as it is
/// shown: the server's copy, which is this person's (Mateusz 2026-11-20:
/// „Zapisz w zdjęciach… zapisuje z korektą werniksu / papieru”). In its
/// frame: the card's "W ramie" picture, as large as the server makes it.
/// Asks only to add to Photos, never to read them.
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

    /// The largest "W ramie" picture the server makes.
    static let framedSide = 4000

    /// Where the picture can come from, largest first; `framed`, the work
    /// in its frame or passe-partout.
    static func sources(for item: Item, framed: Bool = false, backend: any FrameBackend) -> [URLRequest] {
        if framed {
            guard let look = item.framed else { return [] }
            let version = "\(item.pictureVersion)|\(look.kind)\(look.aspect)\(look.inner.minX)\(look.inner.minY)\(look.inner.width)"
            guard var request = backend.request(for: .framed(item.id, side: framedSide, version: version)) else { return [] }
            request.timeoutInterval = 120  // made on the server from the museum's photograph
            return [request]
        }
        // As shown: only the server has it so.
        if item.cleanedShown != nil || item.cutShown != nil {
            return backend.request(for: item.originalRef).map { [$0] } ?? []
        }
        var sources: [URLRequest] = []
        // A sharper copy from another source first: larger than the museum's own.
        if let sharper = item.sharper, let url = URL(string: sharper.url), url.scheme == "https" {
            sources.append(URLRequest(url: url, timeoutInterval: 120))
        }
        // A photo's address (an iCloud album's) expires; its server copy is the original.
        if item.kind == .artwork, let url = URL(string: item.imageUrl),
           url.scheme == "https" || url.scheme == "http"
        {
            sources.append(URLRequest(url: url, timeoutInterval: 120))
        }
        if let server = backend.request(for: item.originalRef) { sources.append(server) }
        return sources
    }

    /// The name the picture gets in Photos: artist and title.
    static func fileName(for item: Item) -> String {
        let parts = [item.artist, item.displayTitle.isEmpty ? "Bez tytułu" : item.displayTitle]
            .filter { !$0.isEmpty }
            .joined(separator: " – ")
        let separators = CharacterSet(charactersIn: "/\\:?*\"<>|").union(.whitespacesAndNewlines)
        let cleaned = parts.components(separatedBy: separators)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
        return String(cleaned.prefix(100))
    }

    /// Under "Zapisz w Zdjęciach" / "Samo dzieło": the colours' correction
    /// the picture is saved with, when this person sees the work so.
    static func colourNote(_ item: Item) -> String? {
        switch item.cleanedShown?.kind {
        case "varnish": "Bez werniksu"
        case "paper": "Z odżółconym papierem"
        case .some: "Z korektą barw"
        case nil: nil
        }
    }

    /// Under "W ramie": what is around the work.
    static func framedNote(_ item: Item) -> String {
        let around = switch item.framed?.kind {
        case "mount": "Z passe-partout"
        case "paper": "Z marginesem kartki"
        default: "Z ramą"
        }
        guard let note = colourNote(item) else { return "\(around) ze zdjęcia muzeum" }
        return "\(around), \(note.lowercased())"
    }

    static func save(_ item: Item, framed: Bool = false, backend: any FrameBackend) async throws {
        let access = await PHPhotoLibrary.requestAuthorization(for: .addOnly)
        guard access == .authorized || access == .limited else { throw Failure.denied }
        var lastError: Error = Failure.unavailable(nil)
        for source in sources(for: item, framed: framed, backend: backend) {
            if Task.isCancelled { throw CancellationError() }
            do {
                let (data, type) = try await download(source, route: (backend as? LiveBackend)?.route)
                let name = "\(fileName(for: item))\(framed ? " (w ramie)" : "").\(type.preferredFilenameExtension ?? "jpg")"
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
    private static func download(_ request: URLRequest, route: ServerRoute?) async throws -> (Data, UTType) {
        // The server's copy follows it to its other address mid-download.
        let fetch: @Sendable (URLRequest) async throws -> (URL, URLResponse) = { request in
            try await Tailnet.shared.send(request) { try await $0.download(for: request) }
        }
        let fetched = if let route { try await route.follow(request, fetch) } else { try await fetch(request) }
        let (file, response) = fetched
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
