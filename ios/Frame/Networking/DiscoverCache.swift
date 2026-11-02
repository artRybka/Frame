import Foundation

/// Discover's opening screen as last loaded from a server, kept in Caches so
/// the next launch shows it at once while fresh rows and themes load: the
/// study of the day (its tile; only on its day) and "Studia dzieł" too.
enum DiscoverCache {
    struct Snapshot: Codable {
        var rows: [SuggestionRow]
        var themes: [ArtTheme]
        /// Missing in snapshots from before 1.75.6.
        var daily: DailyWork? = nil
        var studies: [StudyBrief]? = nil
    }

    private static func file(for server: String) -> URL? {
        guard !server.isEmpty,
              let dir = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
        else { return nil }
        let name = String(server.map { $0.isLetter || $0.isNumber ? $0 : "_" })
        return dir.appendingPathComponent("discover-\(name).json")
    }

    static func load(server: String) -> Snapshot? {
        guard let url = file(for: server), let data = try? Data(contentsOf: url) else { return nil }
        return try? LiveBackend.decoder().decode(Snapshot.self, from: data)
    }

    static func save(_ snapshot: Snapshot, server: String) {
        guard let url = file(for: server), let data = try? LiveBackend.encoder().encode(snapshot) else {
            return
        }
        try? data.write(to: url, options: .atomic)
    }
}
