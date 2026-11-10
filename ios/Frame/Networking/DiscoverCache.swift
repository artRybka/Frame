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

    static func load(server: String) -> Snapshot? { CacheFile.load(Snapshot.self, "discover", server: server) }

    static func save(_ snapshot: Snapshot, server: String) { CacheFile.save(snapshot, "discover", server: server) }
}

/// The playlists as last loaded from a server, so Playlisty (and the
/// playlist's name on "Teraz") show at once on the next launch while the
/// server counts their works afresh.
enum PlaylistsCache {
    static func load(server: String) -> [PlaylistSummary]? {
        CacheFile.load([PlaylistSummary].self, "playlists", server: server)
    }

    static func save(_ playlists: [PlaylistSummary], server: String) {
        CacheFile.save(playlists, "playlists", server: server)
    }
}

/// The hidden works ("Ukryte" in Playlisty) of each server, from the last launch.
enum HiddenCache {
    static func load(server: String) -> [ItemSummary]? {
        CacheFile.load([ItemSummary].self, "hidden", server: server)
    }

    static func save(_ items: [ItemSummary], server: String) {
        CacheFile.save(items, "hidden", server: server)
    }
}

/// Propozycje dnia as last loaded from a server: their tile in Playlisty
/// shows the same works at the next launch, not others swapped a moment
/// later (Mateusz 2026-11-10).
enum DayPicksCache {
    static func load(server: String) -> DayPicks? {
        CacheFile.load(DayPicks.self, "day-picks", server: server)
    }

    static func save(_ picks: DayPicks, server: String) {
        CacheFile.save(picks, "day-picks", server: server)
    }
}

/// A screen kept per server in Caches, as the server sent it.
enum CacheFile {
    private static func url(_ name: String, server: String) -> URL? {
        guard !server.isEmpty,
              let dir = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
        else { return nil }
        let host = String(server.map { $0.isLetter || $0.isNumber ? $0 : "_" })
        return dir.appendingPathComponent("\(name)-\(host).json")
    }

    static func load<T: Decodable>(_ type: T.Type, _ name: String, server: String) -> T? {
        guard let url = url(name, server: server), let data = try? Data(contentsOf: url) else { return nil }
        return try? LiveBackend.decoder().decode(T.self, from: data)
    }

    static func save<T: Encodable>(_ value: T, _ name: String, server: String) {
        guard let url = url(name, server: server), let data = try? LiveBackend.encoder().encode(value) else {
            return
        }
        try? data.write(to: url, options: .atomic)
    }
}
