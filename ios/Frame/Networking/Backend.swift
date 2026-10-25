import Foundation

/// A picture the UI wants to display.
enum ImageRef: Hashable, Sendable {
    case thumb(String)  // library item id
    case image(String)  // display-size original
    /// Simulated look on the e-paper panel, framed with `settings` (saved or
    /// still being edited); nil means the server's saved settings.
    case framePreview(String, settings: FrameSettings? = nil)
    case path(String)  // server-relative path, e.g. /api/previews/<id>.png
    case url(URL)  // public URL (museum CDN)
}

/// Everything the app needs from the frame server. Implemented by the live
/// HTTP client and by an in-memory demo used before a server exists.
protocol FrameBackend: Sendable {
    var isDemo: Bool { get }

    func health() async throws -> Health
    func status(refresh: Bool) async throws -> StatusView
    func player() async throws -> PlayerView
    func next() async throws
    func previous() async throws
    func hold(_ spec: HoldSpec) async throws -> PlayerView
    func releaseHold() async throws -> PlayerView

    func items(_ query: LibraryQuery) async throws -> ItemPage
    func item(id: String) async throws -> Item
    func setFavorite(id: String, _ favorite: Bool) async throws -> Item
    func setExcluded(id: String, _ excluded: Bool) async throws -> Item
    func show(itemID: String, hold: HoldSpec) async throws
    func facets() async throws -> Facets

    /// How a picture is cropped for `orientation`, and what can be adjusted.
    func framing(itemID: String, orientation: String) async throws -> FramingView
    func saveFraming(itemID: String, orientation: String, crops: [Crop]) async throws -> FramingView
    func resetFraming(itemID: String, orientation: String) async throws -> FramingView

    func playlists() async throws -> [PlaylistSummary]
    func playlist(id: Int) async throws -> PlaylistDetail
    func savePlaylist(_ playlist: Playlist) async throws -> PlaylistDetail
    func deletePlaylist(id: Int) async throws
    func addToPlaylist(id: Int, itemIDs: [String]) async throws -> PlaylistDetail
    /// Takes one work out; a smart playlist keeps it in `rules.excludeIds`.
    func removeFromPlaylist(id: Int, itemID: String) async throws -> PlaylistDetail
    func previewRules(_ rules: PlaylistRules) async throws -> RulesPreview
    func play(playlistID: Int) async throws

    func settings() async throws -> FrameSettings
    func saveSettings(_ settings: FrameSettings) async throws -> FrameSettings

    func museums() async throws -> [Museum]
    func searchMuseum(source: String, query: String, page: Int) async throws -> RemotePage
    func importArtwork(source: String, sourceID: String) async throws -> Item
    /// Imports up to `limit` search results in the background; returns the job id.
    func importSearch(source: String, query: String, limit: Int) async throws -> String
    func packs() async throws -> [LibraryPack]
    /// Starts (or joins) a pack's import; returns the job id.
    func importPack(key: String) async throws -> String
    /// Adds random works by period, style and kind; returns the job id.
    func drawRandom(_ request: DrawRequest) async throws -> String
    /// Adds museum works a smart playlist with `rules` would pick; returns the job id.
    func fillLibrary(rules: PlaylistRules, count: Int) async throws -> String
    func job(id: String) async throws -> JobStatus

    func album() async throws -> AlbumInfo
    func syncAlbum() async throws

    func sendPhoto(_ data: Data, title: String, preset: String, hold: HoldSpec) async throws
        -> DisplayResponse
    /// Adds a photo to the library without showing it (e.g. for a playlist).
    func uploadPhoto(_ upload: PhotoUpload) async throws -> Item
    func wake() async throws
    func sleep() async throws

    func request(for image: ImageRef) -> URLRequest?
}

enum BackendError: LocalizedError {
    case http(status: Int, body: String)
    case invalidResponse
    case notFound

    var errorDescription: String? {
        switch self {
        case let .http(status, body):
            let detail = (try? JSONDecoder().decode([String: String].self, from: Data(body.utf8)))?[
                "detail"]
            return "Serwer odpowiedział \(status)" + (detail.map { ": \($0)" } ?? "")
        case .invalidResponse: return "Nieprawidłowa odpowiedź serwera"
        case .notFound: return "Nie znaleziono"
        }
    }
}
