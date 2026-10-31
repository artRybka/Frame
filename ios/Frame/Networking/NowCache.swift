import Foundation
import UIKit

/// "Teraz" as last seen from a server: what the frame showed, the queue and
/// the history, the frame's orientation, and the picture itself. Kept in
/// Caches so the next launch shows it at once while the server is asked.
enum NowCache {
    /// As "Teraz" loads the picture on the frame.
    static let maxPixel: CGFloat = 1600

    struct Snapshot: Codable, Sendable {
        var player: PlayerView
        var orientation: String
        /// The preview the saved picture is of; nil when none was saved.
        var imageURL: String?
    }

    /// The snapshot and its picture, when it is still the one on the frame.
    struct Remembered {
        var snapshot: Snapshot
        var image: UIImage?

        var player: PlayerView { snapshot.player }
        var orientation: String { snapshot.orientation }
    }

    private static func file(_ kind: String, server: String) -> URL? {
        guard !server.isEmpty,
              let dir = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
        else { return nil }
        let name = String(server.map { $0.isLetter || $0.isNumber ? $0 : "_" })
        return dir.appendingPathComponent("now-\(name).\(kind)")
    }

    /// Plain keys, unlike the server's: what is written is read back as it was.
    static func encode(_ snapshot: Snapshot) -> Data? { try? JSONEncoder().encode(snapshot) }
    static func decode(_ data: Data) -> Snapshot? { try? JSONDecoder().decode(Snapshot.self, from: data) }

    static func load(server: String) -> Remembered? {
        guard let url = file("json", server: server), let data = try? Data(contentsOf: url),
              let snapshot = decode(data)
        else { return nil }
        var image: UIImage?
        if let saved = snapshot.imageURL, saved == snapshot.player.current?.previewUrl,
           let imageFile = file("jpg", server: server), let bytes = try? Data(contentsOf: imageFile) {
            image = UIImage(data: bytes)
        }
        return Remembered(snapshot: snapshot, image: image)
    }

    /// Writes the snapshot, and the picture when one is given; off the main thread.
    static func save(_ snapshot: Snapshot, image: UIImage?, server: String) {
        guard let url = file("json", server: server), let imageFile = file("jpg", server: server) else { return }
        Task.detached(priority: .utility) {
            if let image, let bytes = image.jpegData(compressionQuality: 0.85) {
                try? bytes.write(to: imageFile, options: .atomic)
            }
            if let data = encode(snapshot) {
                try? data.write(to: url, options: .atomic)
            }
        }
    }
}
