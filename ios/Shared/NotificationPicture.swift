import Foundation
import UIKit
import UserNotifications

/// The picture of the work a notification is about: the server lists where
/// to fetch it (notifications.py, `pictures`: its own thumbnail first, then
/// the museum's, which also loads away from home) and the notification
/// extension (FrameNotifications) attaches the first that loads.
enum NotificationPicture {
    static let key = "pictures"
    /// Each address may take this long; together they stay well inside the
    /// extension's half a minute.
    static let timeout: TimeInterval = 8
    static let limit: TimeInterval = 20
    /// iOS takes images up to 10 MB as an attachment.
    static let maxBytes = 10_000_000

    /// The addresses in a notification's payload, in the server's order.
    static func urls(in userInfo: [AnyHashable: Any]) -> [URL] {
        let raw = userInfo[key] as? [Any] ?? []
        let urls = raw.compactMap { ($0 as? String).flatMap(URL.init(string:)) }
            .filter { ["http", "https"].contains($0.scheme?.lowercased() ?? "") }
        return Array(urls.prefix(4))
    }

    /// Data iOS can attach as it is (JPEG, PNG, GIF) with its file
    /// extension, anything else UIKit can read turned into a JPEG; nil
    /// when it is no picture.
    static func attachable(_ data: Data) -> (data: Data, ext: String)? {
        guard !data.isEmpty, data.count <= maxBytes else { return nil }
        let head = [UInt8](data.prefix(4))
        if head.starts(with: [0xFF, 0xD8, 0xFF]) { return (data, "jpg") }
        if head.starts(with: [0x89, 0x50, 0x4E, 0x47]) { return (data, "png") }
        if head.starts(with: [0x47, 0x49, 0x46, 0x38]) { return (data, "gif") }
        guard let image = UIImage(data: data), let jpeg = image.jpegData(compressionQuality: 0.85) else { return nil }
        return (jpeg, "jpg")
    }

    static func session() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = timeout
        config.timeoutIntervalForResource = limit
        config.waitsForConnectivity = false
        config.httpAdditionalHeaders = ["User-Agent": "Frame (iOS notification picture)"]
        return URLSession(configuration: config)
    }

    /// The first address in order that gives a picture. All start at once,
    /// so the museum's is there when the server is out of reach (away from
    /// home its address only times out), yet the server's wins when it answers.
    static func load(_ urls: [URL], using fetch: @escaping @Sendable (URL) async -> Data?) async -> (data: Data, ext: String)? {
        await withTaskGroup(of: (Int, (data: Data, ext: String)?).self) { group in
            for (index, url) in urls.enumerated() {
                group.addTask {
                    let data = await fetch(url)
                    return (index, data.flatMap { attachable($0) })
                }
            }
            var done: [Int: (data: Data, ext: String)?] = [:]
            var next = 0
            for await (index, picture) in group {
                done[index] = picture
                while let result = done[next] {
                    if let picture = result {
                        group.cancelAll()
                        return picture
                    }
                    next += 1
                }
            }
            return nil
        }
    }

    static func download(_ url: URL, with session: URLSession) async -> Data? {
        guard let (data, response) = try? await session.data(from: url),
              (response as? HTTPURLResponse)?.statusCode == 200 else { return nil }
        return data
    }

    /// The picture as a notification attachment (iOS moves the file).
    static func attachment(_ picture: (data: Data, ext: String)) throws -> UNNotificationAttachment {
        let file = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension(picture.ext)
        try picture.data.write(to: file)
        return try UNNotificationAttachment(identifier: "picture", url: file)
    }
}
