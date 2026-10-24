import Foundation

/// A picture the UI wants to display.
enum ImageRef: Hashable, Sendable {
    case thumb(String)  // library item id
    case image(String)  // display-size original
    case framePreview(String)  // simulated look on the e-paper panel
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

    func playlists() async throws -> [PlaylistSummary]
    func playlist(id: Int) async throws -> PlaylistDetail
    func savePlaylist(_ playlist: Playlist) async throws -> PlaylistDetail
    func deletePlaylist(id: Int) async throws
    func addToPlaylist(id: Int, itemIDs: [String]) async throws -> PlaylistDetail
    func previewRules(_ rules: PlaylistRules) async throws -> RulesPreview
    func play(playlistID: Int) async throws

    func settings() async throws -> FrameSettings
    func saveSettings(_ settings: FrameSettings) async throws -> FrameSettings

    func museums() async throws -> [Museum]
    func searchMuseum(source: String, query: String, page: Int) async throws -> RemotePage
    func importArtwork(source: String, sourceID: String) async throws -> Item

    func album() async throws -> AlbumInfo
    func syncAlbum() async throws

    func sendPhoto(_ data: Data, title: String, preset: String, hold: HoldSpec) async throws
        -> DisplayResponse
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
