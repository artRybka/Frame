import Foundation

/// A picture the UI wants to display.
enum ImageRef: Hashable, Sendable {
    case thumb(String)  // library item id
    case image(String)  // display-size original
    /// Simulated look on the e-paper panel, framed with `settings` (saved or
    /// still being edited); nil means the server's saved settings. `framing`
    /// tries crops not saved yet.
    case framePreview(String, settings: FrameSettings? = nil, framing: FramingCrops? = nil)
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
    /// The picture on its way to the frame; polled while one is.
    func progress() async throws -> DisplayProgress
    func next() async throws
    func previous() async throws
    func hold(_ spec: HoldSpec) async throws -> PlayerView
    func releaseHold() async throws -> PlayerView

    func items(_ query: LibraryQuery) async throws -> ItemPage
    func item(id: String) async throws -> Item
    /// The work's Polish title and texts, asked for now if it has none;
    /// waits up to `wait` seconds for them.
    func polish(itemID: String, wait: Int) async throws -> PolishView
    /// The card opened: the server asks the model about this item ahead of
    /// everything else (keywords, Polish texts); waits up to `wait` seconds
    /// for the keywords.
    func describe(itemID: String, wait: Int) async throws -> SeenView
    func setFavorite(id: String, _ favorite: Bool) async throws -> Item
    func setExcluded(id: String, _ excluded: Bool) async throws -> Item
    func show(itemID: String, hold: HoldSpec) async throws
    /// "Dodaj do kolejki": the work goes on the frame at the next change,
    /// before the rest of the queue (a museum work joins the library).
    func queueNext(itemID: String) async throws
    /// Takes back a work added with `queueNext`.
    func dequeue(itemID: String) async throws -> PlayerView
    func facets() async throws -> Facets

    /// How a picture is cropped for `orientation`, and what can be adjusted;
    /// with `automatic` the crops the server would choose, ignoring saved ones.
    func framing(itemID: String, orientation: String, automatic: Bool) async throws -> FramingView
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

    /// Discover's rows: picked for the frame, because you like…, theme of
    /// the day.
    func suggestions() async throws -> [SuggestionRow]
    func themes() async throws -> [ArtTheme]
    func themePage(key: String, page: Int) async throws -> ArtThemePage
    /// The smart playlist made from a theme (made now if there is none);
    /// `play` also puts it on the frame.
    func themePlaylist(key: String, play: Bool) async throws -> ThemePlaylist
    /// Every style, subject, period and technique, with Polish names.
    func vocabulary() async throws -> [TermInfo]
    /// What typed words could mean: artists, terms and the words themselves.
    func terms(_ text: String) async throws -> [TermHit]
    /// What the museums have for words the catalogue does not know.
    func museumHint(_ text: String) async throws -> MuseumHint
    /// The museums' works for a search's words, artists, terms, colours and
    /// years, from the museums of `sources` (every museum when empty).
    func searchMuseums(_ rules: PlaylistRules, sources: [String], page: Int) async throws -> RemotePage
    /// The same, a page of one museum at a time as each answers (with
    /// colours, several pages of each); each museum's `next` is the page to
    /// ask it for more.
    func museumAnswers(_ rules: PlaylistRules, sources: [String], page: Int) async throws
        -> AsyncThrowingStream<MuseumAnswer, Error>

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

    /// A shared iCloud album's name and number of photos; fails on a bad link.
    func checkAlbum(url: String) async throws -> AlbumCheck
    /// Syncs an album playlist with its album now; returns the job id.
    func syncAlbum(playlistID: Int) async throws -> String

    /// Adds a photo to the library without showing it (e.g. for a playlist),
    /// or with `upload.look`, a photo sent once to be shown or queued.
    func uploadPhoto(_ upload: PhotoUpload) async throws -> Item
    /// A photo sent once, shown another way.
    func setLook(itemID: String, _ look: Look) async throws -> Item
    func deleteItem(id: String) async throws
    /// The panel's address, PIN and MAC as the server uses them.
    func panelConfig() async throws -> PanelConfig
    func savePanelConfig(_ update: PanelConfigUpdate) async throws -> PanelConfig
    /// Back to the values in frame.env or the add-on options.
    func resetPanelConfig() async throws -> PanelConfig
    /// The Frame app on the panel, and switching the panel to it or back.
    func panelApp() async throws -> PanelAppView
    func installPanelApp() async throws -> PanelAppView
    /// How much disk the library takes on the server, and its limits.
    func libraryStorage() async throws -> LibraryStorage
    /// A limit equal to its default goes back to frame.env or the add-on options.
    func saveLibraryLimits(_ update: LibraryStorageUpdate) async throws -> LibraryStorage
    /// Claude's settings, spending and progress.
    func aiSettings() async throws -> AiSettings
    func saveAiSettings(_ update: AiSettingsUpdate) async throws -> AiSettings
    /// The server checks the key with Anthropic before keeping it.
    func saveAiKey(_ key: String) async throws -> AiSettings
    func deleteAiKey() async throws -> AiSettings
    func keywordsEstimate() async throws -> AiEstimate
    /// Keywords for the whole library through Anthropic's batches (within a day).
    func describeLibrary() async throws -> AiStarted
    /// `sleepAfter`: woken only to check its state, so on battery it goes back to light sleep.
    func wake(sleepAfter: Bool) async throws -> WakeResult
    /// The current picture to the panel again; waits until it is downloaded.
    func pushAgain() async throws -> DisplayResponse
    func sleep() async throws

    func request(for image: ImageRef) -> URLRequest?
}

extension FrameBackend {
    func framing(itemID: String, orientation: String) async throws -> FramingView {
        try await framing(itemID: itemID, orientation: orientation, automatic: false)
    }
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
