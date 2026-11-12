import Foundation

/// A picture the UI wants to display.
enum ImageRef: Hashable, Sendable {
    case thumb(String)  // library item id
    /// The thumbnail cut to the work inside its paper or mount, for the
    /// small cover tiles (an older server sends the whole thumbnail).
    case tile(String)
    case image(String)  // display-size original
    /// The display-size original from a sharper copy (`Item.sharper`);
    /// `version` (the copy's id) keeps it apart from the one before.
    case original(String, version: String)
    /// Simulated look on the e-paper panel, framed with `settings` (saved or
    /// still being edited); nil means the server's saved settings. `framing`
    /// tries crops not saved yet. Without `ownLook` a photo sent once is
    /// framed as the settings frame photos.
    case framePreview(String, settings: FrameSettings? = nil, framing: FramingCrops? = nil, ownLook: Bool = true)
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
    /// `early`: the wait ends as soon as the Polish title is written, so
    /// the card shows it before the texts.
    func polish(itemID: String, wait: Int, early: Bool) async throws -> PolishView
    /// The card opened: the server asks the model about this item ahead of
    /// everything else (keywords, Polish texts); waits up to `wait` seconds
    /// for the keywords.
    func describe(itemID: String, wait: Int) async throws -> SeenView
    /// The card opened: when the work's picture is poor, the server looks
    /// for a sharper copy in other sources; waits up to `wait` seconds.
    func sharpen(itemID: String, wait: Int) async throws -> SharperView
    /// The card opened on a work whose source gathers pictures (Commons,
    /// Openverse, WikiArt): which museum it is in; waits up to `wait` seconds.
    func holder(itemID: String, wait: Int) async throws -> HolderView
    /// The card opened on a work that names no technique: what it is made
    /// with, from its record, Commons or Wikidata; waits up to `wait` seconds.
    func medium(itemID: String, wait: Int) async throws -> MediumView
    /// The work's fragments (a scroll's parts, a Commons tile set): none for most works.
    func fragments(itemID: String) async throws -> FragmentsView
    /// The work's details (pictures of a part of it): none for most works.
    func details(itemID: String) async throws -> DetailsView
    /// "Szukaj lepszej kopii": every copy of the work's picture in the
    /// sources, as they answer.
    func copies(itemID: String) async throws -> AsyncThrowingStream<CopyLine, Error>
    /// The owner's pick for the work's picture: a copy, or (the work's own
    /// id) its own picture again.
    func chooseCopy(itemID: String, copyID: String) async throws -> Item
    /// A copy of the work's picture the owner brought (bought in Alamy, a
    /// scan): kept for good and shown in its place, like a picked copy.
    func bringCopy(itemID: String, filename: String, data: Data, origin: String) async throws -> Item
    /// One spot of the picture shown now and of the copy, at the frame's
    /// scale; the most detailed one without `x` and `y`.
    func copySpot(itemID: String, copyID: String, x: Double?, y: Double?) async throws -> CopySpot
    func setFavorite(id: String, _ favorite: Bool) async throws -> Item
    /// "Ukryj dzieło" and back: a hidden work is never shown, listed or found.
    func setExcluded(id: String, _ excluded: Bool) async throws -> Item
    /// The hidden works ("Ukryte" at the end of Playlisty), the last hidden first.
    func hiddenItems() async throws -> ItemPage
    func show(itemID: String, hold: HoldSpec) async throws
    /// "Dodaj do kolejki": the work goes on the frame at the next change,
    /// before the rest of the queue (a museum work joins the library).
    func queueNext(itemID: String) async throws
    /// Takes back a work added with `queueNext`.
    func dequeue(itemID: String) async throws -> PlayerView
    /// "Pomiń": a picture waiting in the queue is not shown this round.
    func skip(itemID: String) async throws -> PlayerView
    func facets() async throws -> Facets

    /// How a picture is cropped for `orientation`, and what can be adjusted;
    /// with `automatic` the crops the server would choose, ignoring saved ones.
    func framing(itemID: String, orientation: String, automatic: Bool) async throws -> FramingView
    func saveFraming(itemID: String, orientation: String, crops: [Crop]) async throws -> FramingView
    func resetFraming(itemID: String, orientation: String) async throws -> FramingView
    /// The Multi board a preview of `itemID` with `settings` shows, for the
    /// app to draw from thumbnails (every grid, both orientations).
    func board(itemID: String, settings: FrameSettings, ownLook: Bool) async throws -> PhotoBoard

    func playlists() async throws -> [PlaylistSummary]
    func playlist(id: Int) async throws -> PlaylistDetail
    func savePlaylist(_ playlist: Playlist) async throws -> PlaylistDetail
    /// The cards in Playlisty in this order from now on (each person's own);
    /// the playlists back in it.
    func arrangePlaylists(ids: [Int]) async throws -> [PlaylistSummary]
    func deletePlaylist(id: Int) async throws
    /// The order of the playlist's works, in the app and on the frame.
    func sortPlaylist(id: Int, sort: PlaylistSort) async throws -> PlaylistDetail
    func addToPlaylist(id: Int, itemIDs: [String]) async throws -> PlaylistDetail
    /// Takes one work out; a smart playlist keeps it in `rules.excludeIds`.
    func removeFromPlaylist(id: Int, itemID: String) async throws -> PlaylistDetail
    func previewRules(_ rules: PlaylistRules) async throws -> RulesPreview
    func play(playlistID: Int) async throws
    /// Propozycje on the frame: the rotation without a playlist.
    func playSuggestions() async throws
    /// Propozycje dnia of the asking person (made once a day).
    func daySuggestions() async throws -> DayPicks

    func settings() async throws -> FrameSettings
    func saveSettings(_ settings: FrameSettings) async throws -> FrameSettings

    /// Discover's rows: picked for the frame, because you like…, theme of
    /// the day.
    func suggestions() async throws -> [SuggestionRow]
    func themes() async throws -> [ArtTheme]
    func themePage(key: String, page: Int) async throws -> ArtThemePage
    /// The same from `page`, several of the theme's searches at once, each
    /// one's works as it answers, then a last line with the page that follows.
    func themeLines(key: String, page: Int) async throws -> AsyncThrowingStream<ThemeLine, Error>
    /// The work of the day (`day`: a past one, "2026-10-30"); waits up to
    /// `wait` seconds for Claude's page being written. Without `lists`: the
    /// page without the lists under its text (`DailyWork.partial`), at once:
    /// all Discover's tile needs (older servers send the whole page).
    func daily(day: String?, wait: Int, lists: Bool) async throws -> DailyWork
    /// Another work of the day for today, drawn now (Konfiguracja, the
    /// owner only); its page is asked for at once. 409: nothing else fits.
    func dailyAgain() async throws -> DailyWork.Brief
    /// Another artist of the week, drawn now (Konfiguracja, the owner
    /// only), as its card in Discover. 409: nobody else fits.
    func weekArtistAgain() async throws -> ArtTheme
    /// The work's study as far as it is; waits up to `wait` seconds for one
    /// on its way to get a step further. Without `lists`: its page without
    /// the lists under the text (`DailyWork.partial`), which the server
    /// needs a while for: the text at once, the lists asked for next.
    func study(itemID: String, wait: Int, lists: Bool) async throws -> StudyView
    /// Every work with a study, the last asked for first.
    func studies() async throws -> [StudyBrief]
    /// Asks Claude for the work's study (`again`: a new one, though there is one).
    /// `later`: for less, through Anthropic's batches ("Przygotuj na
    /// później"); a study ordered so and asked for without it is made now.
    func prepareStudy(itemID: String, again: Bool, later: Bool) async throws -> StudyView
    /// The owner's "Wykonaj ponowną analizę": the work's analysis of the
    /// composition asked for anew (minutes); the one its page shows is kept
    /// among its versions. 409: no key, or no page yet.
    func compositionAgain(itemID: String) async throws -> CompositionAgain
    /// Whether the analysis asked for anew is still being made.
    func compositionState(itemID: String) async throws -> CompositionAgain
    /// The owner's pick among the page's analyses (`DailyWork.compositionVersions`).
    func pickComposition(itemID: String, shown: Int) async throws -> CompositionAgain
    /// The owner's "Popraw detale": each of the page's details checked over
    /// its cut, a box that misses drawn anew (a minute or two). 409: no
    /// key, or no page with details yet.
    func detailsAgain(itemID: String) async throws -> DetailsAgain
    /// Whether the details' check is still on its way, and what it moved.
    func detailsState(itemID: String) async throws -> DetailsAgain
    /// The push token of the Lock Screen card following the work's study:
    /// the server pushes each step to it.
    func followStudy(itemID: String, activityToken: String, sandbox: Bool) async throws
    /// The send bar's push token: the server moves it on and ends it.
    func followSend(title: String, activityToken: String, sandbox: Bool) async throws
    /// The smart playlist made from a theme (made now if there is none);
    /// `play` also puts it on the frame.
    func themePlaylist(key: String, play: Bool) async throws -> ThemePlaylist
    /// Every style, subject, period and technique, with Polish names.
    func vocabulary() async throws -> [TermInfo]
    /// What typed words could mean: artists, terms and the words themselves.
    func terms(_ text: String) async throws -> [TermHit]
    /// Szukaj by a sentence: its choices as chips (`POST /api/terms/sentence`).
    func sentence(_ text: String) async throws -> SentenceReading
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
    /// Szukaj's "Muzeum": the museums of the catalogue's works, ours, and
    /// with `query` (3 letters or more) those Wikidata knows by it.
    func places(query: String) async throws -> [PlaceHit]
    /// A picture of a work in a museum with none in the catalogue.
    func placePicture(key: String) async throws -> PlacePicture
    func searchMuseum(source: String, query: String, page: Int) async throws -> RemotePage
    func importArtwork(source: String, sourceID: String) async throws -> Item
    /// Imports up to `limit` search results in the background; returns the job id.
    func importSearch(source: String, query: String, limit: Int) async throws -> String
    func packs() async throws -> [LibraryPack]
    /// Starts (or joins) a pack's import; returns the job id.
    func importPack(key: String) async throws -> String
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
    /// Renewed Samsung certificates (author.p12, distributor.p12, their
    /// password); the server signs the app with them. Another author key
    /// than the stored one is 409 unless `newAuthor`.
    func uploadPanelCertificates(_ upload: PanelCertificatesUpload) async throws -> PanelAppView
    /// The last screenshot of the frame's screen, and one asked for.
    func panelScreenshot() async throws -> PanelScreenshot
    /// A new screenshot: the frame's app takes it at its next question on
    /// the charger (`/api/device/screenshot.jpg` once `takenAt` changes).
    func askPanelScreenshot() async throws -> PanelScreenshot
    /// How much disk the library takes on the server, and its limits.
    func libraryStorage() async throws -> LibraryStorage
    /// Requests to each art source lately, and the refusals (the owner's).
    func sourceRequests() async throws -> SourceRequests
    /// How many works the server has gathered, and in large pictures.
    func catalogueCounts() async throws -> CatalogueCounts
    /// The night's tasks and how each last went (the owner's).
    func nightTasks() async throws -> NightTasks
    /// The night's tasks started now (all of them for nil); 409 while a run goes on.
    func startNightTasks(_ start: NightStart) async throws -> NightTasks
    /// Stops the tasks started from the app after the current step.
    func stopNightTasks() async throws -> NightTasks
    /// A limit equal to its default goes back to frame.env or the add-on options.
    func saveLibraryLimits(_ update: LibraryStorageUpdate) async throws -> LibraryStorage
    /// The newest server image next to the running one (Synology).
    func serverUpdate() async throws -> ServerUpdate
    /// The helper looks for a new image now.
    func checkServerUpdate() async throws -> ServerUpdate
    /// The helper replaces the server's container: about a minute without a server.
    func updateServer() async throws -> ServerUpdate
    /// Claude's settings, spending and progress.
    /// Notifications on the phone: the APNs key, this phone (`device`: its token) and its kinds.
    func notifications(device: String?) async throws -> NotificationSettings
    func registerPush(token: String, _ update: PushDeviceUpdate) async throws -> NotificationSettings
    func uploadPushKey(filename: String, data: Data, device: String?) async throws -> NotificationSettings
    func deletePushKey(device: String?) async throws -> NotificationSettings
    /// A notification to this phone now; Apple's answer if it fails.
    func testPush(device: String) async throws -> PushTestResult
    func aiSettings() async throws -> AiSettings
    func saveAiSettings(_ update: AiSettingsUpdate) async throws -> AiSettings
    /// What the tidying of copies changed, the judge's (doubtful) first.
    func tidyChanges() async throws -> TidyChanges
    /// "To nie to samo": the two pictures apart again, for good.
    func keepApart(_ apart: TidyApart) async throws -> TidyChanges
    /// "Do sprawdzenia": the gatekeeper's and the night audit's lists.
    func aiReview() async throws -> AiReview
    /// A work the gatekeeper set aside back in the catalogue, for good.
    func bringBack(itemID: String) async throws -> AiReview
    /// Off the list.
    func dismissReview(itemID: String) async throws -> AiReview
    /// The server checks the key with Anthropic before keeping it.
    func saveAiKey(_ key: String) async throws -> AiSettings
    func deleteAiKey() async throws -> AiSettings
    /// Keys of art sources; the server checks a key with its source before keeping it.
    func sourceKeys() async throws -> [SourceKey]
    func saveSourceKey(_ source: String, key: String) async throws -> [SourceKey]
    func deleteSourceKey(_ source: String) async throws -> [SourceKey]
    /// The household's Tailscale key for the app's own Tailscale node: every
    /// phone reads it, the owner sets it.
    func tailnet() async throws -> TailnetKey
    func saveTailnetKey(_ key: String) async throws -> TailnetKey
    func deleteTailnetKey() async throws -> TailnetKey
    func saveTailnetAddress(_ address: String) async throws -> TailnetKey
    func keywordsEstimate() async throws -> AiEstimate
    /// Keywords for the whole library through Anthropic's batches (within a day).
    func describeLibrary() async throws -> AiStarted
    /// `sleepAfter`: woken only to check its state, so on battery it goes back to light sleep.
    func wake(sleepAfter: Bool) async throws -> WakeResult
    /// The current picture to the panel again; waits until it is downloaded.
    func pushAgain() async throws -> DisplayResponse
    func sleep() async throws
    /// "Uruchom ponownie": the frame's app reboots the panel (woken for it
    /// when asleep in the network, started again when it hung).
    func restart() async throws -> WakeResult
    /// "Głęboki sen" for `hours` (1–72) with the Wi-Fi off, or with `hours`
    /// nil "Wyłącz ramkę": no alarm, only the button wakes it.
    func rest(hours: Int?) async throws -> RestResult

    func request(for image: ImageRef) -> URLRequest?

    // People (Model/People.swift; the demo's are there too).
    /// Who this phone is on the server: a member sees no Konfiguracja.
    func me() async throws -> Me
    /// "Odłącz ten telefon": this phone's own token stops working.
    func leave() async throws
    /// Konfiguracja → Domownicy (the owner's).
    func people() async throws -> People
    func invite(_ request: InviteRequest) async throws -> NewInvite
    func cancelInvite(id: String) async throws -> People
    /// "Odbierz dostęp": that phone's token stops working at once.
    func removeDevice(id: String) async throws -> People
    func removePerson(id: String) async throws -> People
    func renamePerson(id: String, name: String) async throws -> People
    func savePeopleSettings(_ settings: PeopleSettings) async throws -> People
}

extension FrameBackend {
    /// The work of the day with its whole page.
    func daily(day: String?, wait: Int) async throws -> DailyWork {
        try await daily(day: day, wait: wait, lists: true)
    }

    /// The work's study with its whole page.
    func study(itemID: String, wait: Int) async throws -> StudyView {
        try await study(itemID: itemID, wait: wait, lists: true)
    }
}

extension FrameBackend {
    /// Only the server has the photos' crops: elsewhere the sketch stays.
    func board(itemID: String, settings: FrameSettings, ownLook: Bool) async throws -> PhotoBoard {
        throw BackendError.notFound
    }

    func framing(itemID: String, orientation: String) async throws -> FramingView {
        try await framing(itemID: itemID, orientation: orientation, automatic: false)
    }
}

enum BackendError: LocalizedError {
    case http(status: Int, body: String)
    case invalidResponse
    case notFound
    /// A change sent as the app went to the background, cut short there:
    /// it may or may not have reached the server.
    case interrupted

    var errorDescription: String? {
        switch self {
        case let .http(status, body):
            let detail = (try? JSONDecoder().decode([String: String].self, from: Data(body.utf8)))?[
                "detail"]
            return "Serwer odpowiedział \(status)" + (detail.map { ": \($0)" } ?? "")
        case .invalidResponse: return "Nieprawidłowa odpowiedź serwera"
        case .notFound: return "Nie znaleziono"
        case .interrupted: return "Przerwane, gdy aplikacja była w tle"
        }
    }
}

extension FrameBackend {
    /// The work's Polish texts, waited for whole.
    func polish(itemID: String, wait: Int) async throws -> PolishView {
        try await polish(itemID: itemID, wait: wait, early: false)
    }
}
