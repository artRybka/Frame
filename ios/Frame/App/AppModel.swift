import Foundation
import Network
import Observation
import UIKit

/// App-wide state: connection, what the frame shows, its status and settings.
@MainActor
@Observable
final class AppModel {
    private enum Keys {
        static let serverURL = "serverURL"
        static let remoteURL = "remoteServerURL"
        static let apiToken = "apiToken"
        static let demoMode = "demoMode"
    }

    enum Connection: Equatable {
        case unknown, connected, failed(String)
    }

    var serverURL: String
    /// Optional second address used away from home, e.g. the NAS in Tailscale.
    var remoteURL: String
    var apiToken: String
    var demoMode: Bool
    private(set) var backend: any FrameBackend
    /// Which of the server's addresses the app talks to; nil in the demo or
    /// before the server answered.
    private(set) var serverPath: ServerRoute.Kind?

    /// Who this phone is on the server; nil before it answered (and from
    /// older servers): taken as the owner (`isOwner`).
    var me: Me?
    /// An invitation opened from its link or QR code, waiting for "Dołącz".
    var invitation: Invitation?
    /// This phone's own token stopped working ("Odbierz dostęp").
    var accessLost = false

    var player: PlayerView?
    /// "Teraz" as the last launch left it (`NowCache`): shown at once, until
    /// the server answers; nil on a first launch, a new server or the demo.
    private(set) var remembered: NowCache.Remembered?
    /// The preview whose picture is saved with it.
    @ObservationIgnored private var rememberedImageURL: String?
    var status: StatusView?
    var settings: FrameSettings?
    /// How the server reaches the panel; nil before it is loaded or on an older server.
    var panelConfig: PanelConfig?
    /// The Frame app on the panel; loaded when Konfiguracja opens, nil on
    /// an older server.
    var panelApp: PanelAppView?
    /// The library's size on the server; loaded when Konfiguracja opens
    /// (measuring is slow on a NAS), nil on an older server.
    var libraryStorage: LibraryStorage?
    var serverUpdate: ServerUpdate?
    /// "Aktualizuj serwer": waiting for the server to come back as the new version.
    var updatingServer = false
    /// The version `updateServer()` started from, for "old → new" once the
    /// new server already answers.
    var updatingServerFrom: String?
    /// Claude's settings, spending and progress; loaded when Konfiguracja
    /// opens, nil on an older server.
    var aiSettings: AiSettings?
    /// Notifications on this phone as the server has them; loaded when
    /// Konfiguracja opens, nil on an older server.
    var notificationSettings: NotificationSettings?
    /// Bumped to open Discover on the work of the day (a notification tapped).
    var dailyOpened = 0
    /// A theme to open in Discover (the artist of the week, from a notification).
    var themeOpened: String?
    var themeOpenings = 0
    var playlists: [PlaylistSummary] = []
    /// Each playlist's works as last opened: shown at once when it opens
    /// again while fresh ones load.
    var playlistDetails: [Int: PlaylistDetail] = [:]
    /// Goes up when a work is liked, unliked, left out or brought back:
    /// views listing a playlist's works load them again.
    private(set) var libraryRevision = 0
    /// The heart each work was last given here, for tiles loaded before
    /// (Szukaj's, after the work's card liked it).
    private(set) var hearts: [String: Bool] = [:]
    var facets = Facets.empty
    /// Works the server found no picture of anywhere (it answered 410):
    /// grids leave them out until the app starts again.
    private(set) var missingPictures: Set<String> = []
    /// Goes up when the owner taps a picture that did not load: every
    /// picture on screen that failed tries again.
    private(set) var pictureRetries = 0
    /// Styles, subjects, periods and techniques to search by, with Polish names.
    var vocabulary: [TermInfo] = []
    var connection = Connection.unknown
    /// The cards at the bottom of the screen (`NoticeStack`).
    let notices = Notices()
    /// The send bar on the Lock Screen and in the Dynamic Island.
    let liveActivity = SendLiveActivity()
    /// Studies being written, there too (`Studies.swift`).
    let studyActivity = StudyLiveActivity()
    var working = false
    /// A tap on the Sieć tile (the check) found the frame asleep and is
    /// waking it.
    var wakingForStatus = false
    /// The bar under the picture: set while a picture is on its way to the
    /// frame, and for a moment after it arrives.
    var displayProgress: DisplayProgress?
    /// An artist whose works Discover's search should show: set by tapping
    /// the name on a work, taken (and cleared) by the search.
    var artistSearch: String?
    /// Bumped to open Discover on Propozycje (from the menu of their tile
    /// in Playlisty).
    var suggestionsOpened = 0
    /// Discover's rows and themes as last loaded (also by the previous
    /// launch): shown at once while fresh ones load.
    var suggestionRows: [SuggestionRow]?
    var themes: [ArtTheme]?
    /// The work of the day at the top of Propozycje; nil while there is none.
    var daily: DailyWork?
    /// Studies of works asked for on their cards, as last heard (`Studies.swift`).
    var studies: [String: StudyView] = [:]
    /// Every work with a study or a work of the day's page, for Discover's row
    /// "Studia dzieł"; nil from older servers.
    var studyList: [StudyBrief]?
    /// The work whose card is on top: "Studium gotowe" opens its study there.
    var topCard: String?
    /// A study to open: pushed on its card when that is on top, else in a sheet.
    var studyOnCard: String?
    var studySheet: String?
    /// The cards following studies on their way, and those saying one is ready.
    @ObservationIgnored var studyCards: [String: Notice.ID] = [:]
    @ObservationIgnored var studyReadyCards: [String: Notice.ID] = [:]
    private var discoverLoad: Task<Void, Never>?
    private var discoverLoadedAt: Date?
    private var progressTask: Task<Void, Never>?
    private var route: ServerRoute?
    private let network = NWPathMonitor()
    private var networkSeen: String?
    private var networkSettle: Task<Void, Never>?

    init() {
        let defaults = UserDefaults.standard
        let url = defaults.string(forKey: Keys.serverURL) ?? ""
        let remote = defaults.string(forKey: Keys.remoteURL) ?? ""
        let token = KeychainStore.read(Keys.apiToken) ?? ""
        let forcedDemo = defaults.bool(forKey: "demo")  // launch argument -demo YES
        let demo = forcedDemo || (defaults.object(forKey: Keys.demoMode) as? Bool ?? url.isEmpty)
        serverURL = url
        remoteURL = remote
        apiToken = token
        demoMode = demo
        backend = DemoBackend()
        connect(demo: demo, url: url, remote: remote, token: token)
        restoreNow()
        restoreDiscover()
        watchNetwork()
        PushCenter.shared.onToken = { [weak self] token in
            Task { await self?.registerPush(token) }
        }
        studyActivity.onToken = { [weak self] itemID, token in
            await self?.followStudyOnLockScreen(itemID: itemID, token: token)
        }
    }

    private func connect(demo: Bool, url: String, remote: String, token: String) {
        serverPath = nil
        guard !demo, let home = Self.serverAddress(url) else {
            route = nil
            backend = DemoBackend()
            return
        }
        let route = ServerRoute(home: home, remote: Self.serverAddress(remote))
        route.onSwitch = { [weak self] kind in
            Task { @MainActor in self?.serverPath = kind }
        }
        self.route = route
        backend = LiveBackend(route: route, token: token.isEmpty ? nil : token)
    }

    private static func serverAddress(_ text: String) -> URL? {
        let text = text.trimmingCharacters(in: .whitespaces)
        guard let url = URL(string: text), url.scheme != nil else { return nil }
        return url
    }

    /// Persist connection settings and switch backend.
    func applyConnection() async {
        UserDefaults.standard.set(serverURL, forKey: Keys.serverURL)
        UserDefaults.standard.set(remoteURL, forKey: Keys.remoteURL)
        UserDefaults.standard.set(demoMode, forKey: Keys.demoMode)
        KeychainStore.write(Keys.apiToken, value: apiToken)
        connect(demo: demoMode, url: serverURL, remote: remoteURL, token: apiToken)
        player = nil
        status = nil
        displayProgress = nil
        settings = nil
        panelConfig = nil
        panelApp = nil
        libraryStorage = nil
        serverUpdate = nil
        aiSettings = nil
        notificationSettings = nil
        me = nil
        playlists = []
        playlistDetails = [:]
        facets = .empty
        vocabulary = []
        restoreNow()
        restoreDiscover()
        await refreshAll()
    }

    var currentItem: Item? { player?.current?.item }

    /// As last seen, until the settings are in: the frame on "Teraz" keeps its shape.
    var isPortrait: Bool { (settings?.orientation ?? remembered?.orientation) == "portrait" }

    // MARK: Loading

    func refreshAll() async {
        if let route, route.hasRemote, await route.resolve() == nil {
            connection = .failed("Serwer nie odpowiada pod żadnym adresem. Poza domem włącz Tailscale.")
            return
        }
        do {
            _ = try await backend.health()
            connection = .connected
            serverPath = route?.active
        } catch {
            if !error.isCancellation { connection = .failed(error.localizedDescription) }
            return
        }
        let backend = self.backend
        let player = Task { try? await backend.player() }
        let status = Task { try? await backend.status(refresh: false) }
        let settings = Task { try? await backend.settings() }
        let playlists = Task { try? await backend.playlists() }
        let facets = Task { try? await backend.facets() }
        let panelConfig = Task { try? await backend.panelConfig() }
        let me = Task { () -> Result<Me, Error> in
            do { return .success(try await backend.me()) } catch { return .failure(error) }
        }
        switch await me.value {
        case let .success(found):
            self.me = found
            accessLost = false
        case let .failure(error):
            if case let BackendError.http(status, _) = error, status == 401 {
                connection = .failed("Serwer nie przyjmuje tego telefonu. Poproś o nowe zaproszenie albo wpisz token serwera w Konfiguracji.")
                self.me = nil
                accessLost = true
                return
            }
            self.me = nil  // an older server: no people, the owner
        }
        self.player = await player.value
        if self.player?.progress?.active == true { trackProgress() }
        self.status = await status.value
        self.settings = await settings.value
        self.playlists = await playlists.value ?? []
        self.facets = await facets.value ?? .empty
        self.panelConfig = await panelConfig.value
        rememberNow()
        // The APNs token goes to the server on every start (registerPush).
        if !demoMode { Task { await PushCenter.shared.registerIfAllowed() } }
        // Ready before Discover is opened.
        Task { await refreshDiscover() }
    }

    // MARK: "Teraz" from the last launch

    /// The last "Teraz" of this server, with its picture ready for the hero.
    /// What was on its way then is not known now: the picture, its queue and
    /// history only.
    private func restoreNow() {
        guard !demoMode, var saved = NowCache.load(server: serverURL) else {
            remembered = nil
            rememberedImageURL = nil
            return
        }
        saved.snapshot.player.delivery = nil
        saved.snapshot.player.progress = nil
        saved.snapshot.player.busy = false
        saved.snapshot.player.lastError = nil
        remembered = saved
        rememberedImageURL = saved.image == nil ? nil : saved.snapshot.imageURL
        if let image = saved.image, let url = saved.snapshot.imageURL,
           let request = backend.request(for: .path(url)) {
            Task { await ImageLoader.shared.remember(image, for: request, maxPixel: NowCache.maxPixel) }
        }
    }

    /// Keeps "Teraz" for the next launch; `image` is the picture on the
    /// frame, once "Teraz" has loaded it.
    func rememberNow(image: UIImage? = nil) {
        guard !demoMode, let player else { return }
        var image = image
        if image != nil {
            // Saved already: only the queue and history are new.
            if rememberedImageURL == player.current?.previewUrl { image = nil }
            rememberedImageURL = player.current?.previewUrl
        }
        let snapshot = NowCache.Snapshot(
            player: player,
            orientation: settings?.orientation ?? remembered?.orientation ?? "landscape",
            imageURL: rememberedImageURL
        )
        NowCache.save(snapshot, image: image, server: serverURL)
    }

    // MARK: Server address

    /// Back in the app or on another network: checks which of the server's
    /// addresses answers now, and reloads when that changed or the server
    /// was out of reach.
    func recheckServer() async {
        guard let route, route.hasRemote, connection != .unknown else { return }
        let before = route.active
        guard let found = await route.resolve() else { return }
        if found != before || connection != .connected { await refreshAll() }
    }

    private func watchNetwork() {
        network.pathUpdateHandler = { [weak self] path in
            let seen = "\(path.status) \(path.availableInterfaces.map(\.name).sorted())"
            Task { @MainActor in self?.networkChanged(seen) }
        }
        network.start(queue: .main)
    }

    private func networkChanged(_ seen: String) {
        defer { networkSeen = seen }
        guard let before = networkSeen, before != seen else { return }
        // A new network (or the VPN coming up) takes a moment to settle.
        networkSettle?.cancel()
        networkSettle = Task {
            try? await Task.sleep(for: .seconds(1.5))
            guard !Task.isCancelled else { return }
            await recheckServer()
        }
    }

    // MARK: Discover

    /// Loads Discover's rows and themes, each shown as soon as it comes, and
    /// keeps them for the next launch. A load a minute ago is enough, unless
    /// `force` (pull to refresh).
    func refreshDiscover(force: Bool = false) async {
        if let running = discoverLoad { return await running.value }
        if !force, let at = discoverLoadedAt, Date().timeIntervalSince(at) < 60 { return }
        let load = Task { await loadDiscover() }
        discoverLoad = load
        await load.value
        discoverLoad = nil
    }

    private func loadDiscover() async {
        let backend = self.backend
        async let rows = loadSuggestionRows(backend)
        async let themes = loadThemes(backend)
        async let daily: Void = loadDaily(backend)
        async let studyRow: Void = loadStudyList(backend)
        let (gotRows, gotThemes, _, _) = await (rows, themes, daily, studyRow)
        guard gotRows, gotThemes else { return }
        discoverLoadedAt = Date()
        if !demoMode, let suggestionRows, let themes = self.themes {
            DiscoverCache.save(.init(rows: suggestionRows, themes: themes), server: serverURL)
        }
    }

    private func loadSuggestionRows(_ backend: any FrameBackend) async -> Bool {
        do {
            suggestionRows = try await backend.suggestions()
            return true
        } catch {
            if suggestionRows == nil { show(error) }  // else the last ones stay
            return false
        }
    }

    /// The works with a study or a day's page; an older server without the
    /// list shows no row.
    func loadStudyList(_ backend: any FrameBackend) async {
        do {
            studyList = try await backend.studies()
        } catch {
            if case BackendError.notFound = error {
                studyList = nil
            } else if case let BackendError.http(status, _) = error, status == 404 {
                studyList = nil
            }
        }
    }

    /// The work of the day; an older server without one, or a catalogue
    /// without a work fit for it, shows no tile.
    private func loadDaily(_ backend: any FrameBackend) async {
        do {
            daily = try await backend.daily(day: nil, wait: 0)
        } catch {
            // Offline for a moment: the last one stays.
            if case BackendError.notFound = error {
                daily = nil
            } else if case let BackendError.http(status, _) = error, status == 404 {
                daily = nil
            }
        }
    }

    private func loadThemes(_ backend: any FrameBackend) async -> Bool {
        do {
            themes = try await backend.themes()
            return true
        } catch {
            if themes == nil { show(error) }
            return false
        }
    }

    /// The last Discover of this server, from the previous launch.
    private func restoreDiscover() {
        let saved = demoMode ? nil : DiscoverCache.load(server: serverURL)
        suggestionRows = saved?.rows
        themes = saved?.themes
        discoverLoadedAt = nil
    }

    func refreshPlayer() async {
        guard let value = try? await backend.player() else { return }
        player = value
        // The playlist may have changed without the app's settings (a theme
        // presented from Discover): a draft saved later must not undo it.
        if let settings, settings.playlistId != value.playlist?.id {
            self.settings?.playlistId = value.playlist?.id
        }
    }

    func refreshStatus(live: Bool) async {
        do {
            status = try await backend.status(refresh: live)
        } catch {
            show(error)
        }
    }

    /// A tap on the Ramka tab's Sieć tile. A frame the server knows to be
    /// asleep in the network is woken at once, only to be looked at (it goes
    /// back to sleep); when the server is not sure (it last saw the frame
    /// awake, or never), it asks the frame first and wakes it if it does not
    /// answer. Deep sleep has the Wi-Fi off: only the frame's alarm or its
    /// button ends it, so no signal is sent then, the app says when it wakes
    /// instead.
    func checkStatus() async {
        await refreshStatus(live: false)  // what the server knows, the frame not asked
        let known = status?.device.powerState
        if known != "standby", known != "deep_sleep" {
            await refreshStatus(live: true)
        }
        guard let device = status?.device, device.configured, device.powerState != "online" else { return }
        if device.powerState == "deep_sleep" {
            warnDeepSleep(device.wakeAt, off: device.switchedOff == true, lost: device.wifiLost == true)
            return
        }
        if device.powerState == nil, device.reachable != false { return }  // a server before 0.12
        if device.onNetwork == false {
            notices.warn("Ramki nie ma w sieci Wi-Fi", "Sygnał budzenia do niej nie dotrze.")
            return
        }
        wakingForStatus = true
        defer { wakingForStatus = false }
        await wake(sleepAfter: true)
    }

    /// `until`: the alarm (ISO); `lost`: asleep deeply by itself (unplugged).
    private func warnDeepSleep(_ until: String?, off: Bool = false, lost: Bool = false, in card: Notice.ID? = nil) {
        let (title, detail) = Self.deepSleepNote(until, off: off, lost: lost)
        if let card { notices.end(card, .warning, title, detail) } else { notices.warn(title, detail) }
    }

    private static func deepSleepNote(_ until: String?, off: Bool, lost: Bool) -> (String, String) {
        if off { return ("Ramka jest wyłączona", "Włączysz ją przyciskiem na ramce.") }
        let alarm = When.at(until)
        if lost {
            return (
                alarm.map { "Ramka śpi głęboko, sama obudzi się \($0)" } ?? "Ramka śpi głęboko",
                "Po odpięciu zasilacza sygnał budzenia jej nie budzi. "
                    + (alarm == nil ? "Obudzi" : "Wcześniej obudzi") + " ją krótkie naciśnięcie przycisku z tyłu."
            )
        }
        return (
            "Ramka w głębokim śnie",
            "Wi-Fi jest wyłączone. Obudzi ją " + (alarm.map { "budzik \($0) lub przycisk." } ?? "tylko przycisk.")
        )
    }

    /// The server cannot build the frame's app.
    private static let noCertificates = (
        "Brak certyfikatów Samsunga na serwerze",
        "Skopiuj raz author.p12, distributor.p12 i password.txt do folderu data/panel-app/certs serwera (np. File Station)."
    )

    func refreshPlaylists() async {
        if let value = try? await backend.playlists() { playlists = value }
    }

    func refreshFacets() async {
        if let value = try? await backend.facets() { facets = value }
    }

    /// The server's words to search by, asked once; `fresh` asks again (a
    /// group opening: the server may have been updated while the app ran).
    func loadVocabulary(fresh: Bool = false) async {
        guard fresh || vocabulary.isEmpty else { return }
        if let value = try? await backend.vocabulary(), value != vocabulary { vocabulary = value }
    }

    /// Polish names of the vocabulary's terms by key.
    var termNames: [String: String] {
        Dictionary(vocabulary.map { ($0.key, $0.name) }, uniquingKeysWith: { first, _ in first })
    }

    /// While a picture waits for the frame ("Czeka na ramkę"), look now and
    /// then whether it woke (the button, its alarm): the server sends the
    /// picture as soon as the frame's app asks, and the bar follows it.
    func followWaiting() async {
        while !Task.isCancelled, player?.delivery?.isWaiting == true {
            try? await Task.sleep(for: .seconds(8))
            if Task.isCancelled { return }
            await refreshPlayer()
            if let value = try? await backend.status(refresh: false) { status = value }
            if player?.progress?.active == true { trackProgress() }
        }
    }

    /// A change of the schedule while the app is open: its bar and swap
    /// come up as for a picture sent from the app. Waits for the change
    /// (or the end of a timed hold), then for the server's scheduler, which
    /// looks every 30 s.
    func followSchedule() async {
        guard let player, player.hold?.forever != true,
              let due = When.date(player.hold?.until ?? player.nextChangeAt)
        else { return }
        let wait = due.timeIntervalSinceNow
        guard wait > -60 else { return }
        if wait > 0 { try? await Task.sleep(for: .seconds(wait)) }
        for _ in 0 ..< 30 {
            if Task.isCancelled || progressTask != nil { return }
            if let value = try? await backend.progress(), value.active {
                trackProgress()
                return
            }
            try? await Task.sleep(for: .seconds(3))
        }
        if !Task.isCancelled { await refreshPlayer() }
    }

    /// After an action the server renders and pushes in the background;
    /// follow it until the panel has the picture. The bar goes on through
    /// the panel's redraw on its own.
    func followPlayer() async {
        working = true
        defer { working = false }
        trackProgress(expectingStart: true)
        for attempt in 0 ..< 90 {
            try? await Task.sleep(for: .seconds(attempt == 0 ? 0.4 : 1.5))
            await refreshPlayer()
            if player?.busy != true { break }
        }
        if let error = player?.lastError, !error.isEmpty { notices.fail("Nie udało się wysłać obrazu", error) }
    }

    /// Poll the server's progress while a picture is on its way. With
    /// `expectingStart` the run may not have begun yet (the request was just
    /// sent), so an idle or finished state is not the end at first.
    func trackProgress(expectingStart: Bool = false) {
        if expectingStart { progressTask?.cancel() } else if progressTask != nil { return }
        progressTask = Task { [weak self] in
            await self?.pollProgress(expectingStart: expectingStart)
        }
    }

    private func pollProgress(expectingStart: Bool) async {
        let awake = BackgroundTime()
        defer { awake.end() }
        let started = Date.now
        var seenActive = false
        var first: DisplayProgress?  // with `expectingStart`, maybe the run before
        let clock = ContinuousClock()
        var beat = clock.now  // a steady second, whatever a request takes: the bar glides
        while !Task.isCancelled, Date.now.timeIntervalSince(started) < 300 {
            guard let value = try? await backend.progress() else { break }  // older server
            if Task.isCancelled { return }
            if let first, value.startedAt != first.startedAt {
                seenActive = true  // a new run, even if it ended between two polls
            }
            first = first ?? value
            if value.active {
                seenActive = true
                displayProgress = value
                liveActivity.show(value)
            } else if seenActive || !expectingStart || Date.now.timeIntervalSince(started) > 20 {
                if seenActive { await finishProgress(value) }
                break
            }
            beat = max(beat + .seconds(1), clock.now)
            try? await Task.sleep(until: beat, clock: clock)
        }
        if !Task.isCancelled {
            displayProgress = nil
            progressTask = nil
            await settleLiveActivity()
        }
    }

    private func finishProgress(_ value: DisplayProgress) async {
        displayProgress = value
        if value.isWaiting {
            await refreshPlayer()
            liveActivity.wait(value, until: player?.delivery?.asleepUntilAt)
        } else {
            liveActivity.finish(value)
        }
        if value.isDone {
            await refreshPlayer()
            try? await Task.sleep(for: .seconds(2.5))
        } else {
            try? await Task.sleep(for: .seconds(5))  // long enough to read why
        }
    }

    /// The Lock Screen card after a run, or when the app is back: on while
    /// a picture is under way or waits for the frame, its result otherwise.
    func settleLiveActivity() async {
        guard liveActivity.isRunning, progressTask == nil else { return }
        guard let value = try? await backend.progress() else {
            liveActivity.finish(.idle)
            return
        }
        if value.active {
            trackProgress()
            return
        }
        await refreshPlayer()
        if player?.delivery?.isWaiting == true {
            var waiting = value
            waiting.stage = "waiting"
            if waiting.title.isEmpty { waiting.title = player?.current?.title ?? "" }
            liveActivity.wait(waiting, until: player?.delivery?.asleepUntilAt)
        } else {
            liveActivity.finish(value)
        }
    }

    // MARK: Actions

    /// "Pokaż na ramce" on "Teraz": the picture browsed to, `offset` places
    /// from the one on the frame (back in the history, ahead in the queue),
    /// with its crop changed first. The neighbours go as "previous" and
    /// "next" would, so the playlist keeps its order. False if it failed.
    func present(itemID: String, offset: Int, framing change: FramingChange?) async -> Bool {
        do {
            if let change { _ = try await applyFraming(itemID: itemID, change) }
            switch offset {
            case 0: break  // a new crop: the server redraws the picture on its own
            case 1: try await backend.next()
            case -1: try await backend.previous()
            default: try await backend.show(itemID: itemID, hold: .untilNextChange)
            }
        } catch {
            show(error)
            return false
        }
        return true  // the bar follows it
    }

    /// Saves a crop edited in the app (or forgets it); the framing as the
    /// server has it now.
    func applyFraming(itemID: String, _ change: FramingChange) async throws -> FramingView {
        switch change {
        case let .save(orientation, crops):
            try await backend.saveFraming(itemID: itemID, orientation: orientation, crops: crops)
        case let .reset(orientation):
            try await backend.resetFraming(itemID: itemID, orientation: orientation)
        }
    }

    func releaseHold() async {
        do {
            player = try await backend.releaseHold()
            notices.done("Odpięto")
        } catch { show(error) }
    }

    /// Sends the work to the frame and follows it there; false if that
    /// failed (the error is on a card).
    @discardableResult
    func show(itemID: String, hold: HoldSpec) async -> Bool {
        do {
            try await backend.show(itemID: itemID, hold: hold)
        } catch {
            show(error)
            return false
        }
        await followPlayer()
        return player?.lastError?.isEmpty ?? true
    }

    /// Whether the work was added with "Dodaj do kolejki" and waits its turn.
    func isQueued(_ itemID: String) -> Bool {
        player?.queued?.contains(itemID) ?? false
    }

    /// "Dodaj do kolejki": the work is the next one on the frame.
    func queueNext(itemID: String) async {
        do {
            try await backend.queueNext(itemID: itemID)
        } catch {
            show(error)
            return
        }
        await refreshPlayer()
        notices.done("W kolejce jako następne", player?.hold?.forever == true ? "Pojawi się po odpięciu obrazu." : nil)
    }

    func dequeue(itemID: String) async {
        do {
            player = try await backend.dequeue(itemID: itemID)
            notices.done("Usunięto z kolejki")
        } catch { show(error) }
    }

    /// "Pomiń" on a picture waiting in the queue; false if it failed.
    func skip(_ summary: ItemSummary) async -> Bool {
        do {
            player = try await backend.skip(itemID: summary.id)
            notices.done("Pominięto „\(summary.shownTitle)”")
            return true
        } catch {
            show(error)
            return false
        }
    }

    func play(_ playlist: PlaylistSummary) async {
        do {
            try await backend.play(playlistID: playlist.id)
        } catch {
            show(error)
            return
        }
        settings?.playlistId = playlist.id
        notices.done("Teraz prezentowane: \(playlist.name)")
        await followPlayer()
    }

    /// "Propozycje" in Playlisty: back to the rotation from Discover.
    func playSuggestions() async {
        do {
            try await backend.playSuggestions()
        } catch {
            show(error)
            return
        }
        settings?.playlistId = nil
        notices.done("Teraz prezentowane: Propozycje")
        await followPlayer()
    }

    /// The works next in Propozycje, for its cover in Playlisty.
    var suggestionCover: [RemoteItem] {
        let rows = suggestionRows ?? []
        return Array((rows.first { $0.key == "for-you" } ?? rows.first)?.items.prefix(4) ?? [])
    }

    func setFavorite(_ id: String, _ favorite: Bool) async -> Item? {
        do {
            let item = try await backend.setFavorite(id: id, favorite)
            hearts[id] = item.favorite
            if player?.current?.item?.id == id { player?.current?.item = item }
            libraryChanged()
            return item
        } catch {
            show(error)
            return nil
        }
    }

    /// "Nie pokazuj na ramce" and back.
    func setExcluded(_ id: String, _ excluded: Bool) async -> Item? {
        do {
            let item = try await backend.setExcluded(id: id, excluded)
            libraryChanged()
            return item
        } catch {
            show(error)
            return nil
        }
    }

    /// A work joined or left playlists (Ulubione and smart ones): their
    /// tiles and counts, and the queue in "Teraz", which the server updates.
    func libraryChanged() {
        libraryRevision += 1
        Task {
            await refreshPlaylists()
            await refreshPlayer()
        }
    }

    func saveSettings(_ new: FrameSettings) async {
        let turned = settings?.screenKey != new.screenKey
        let restyled = settings?.presentationKey != new.presentationKey
        let remoded = settings?.powerMode != new.powerMode
        do {
            settings = try await backend.saveSettings(new)
            // A sleeping frame takes a new power mode on only when it wakes:
            // the status says so (DeviceStatus.modePending).
            if remoded { await refreshStatus(live: false) }
            if !turned, restyled {
                notices.done("Zapisano", "Nowy wygląd dostanie następny obraz.")
            } else {
                notices.done("Zapisano ustawienia")
            }
            if turned {
                // The server redraws the current picture for the turned screen.
                await followPlayer()
            } else {
                await refreshPlayer()
            }
        } catch { show(error) }
    }

    /// The frame's name in the app; empty goes back to the panel's own.
    func renameFrame(_ name: String) async {
        guard var new = settings else { return }
        let trimmed = String(name.split(whereSeparator: \.isWhitespace).joined(separator: " ").prefix(40))
        new.name = trimmed.isEmpty ? nil : trimmed
        do {
            settings = try await backend.saveSettings(new)
            notices.done(new.name.map { "Ramka nazywa się teraz „\($0)”" } ?? "Przywrócono nazwę z ekranu")
        } catch { show(error) }
    }

    /// Saves the panel's address, PIN and MAC on the server, then checks
    /// whether the panel answers there.
    func savePanelConfig(_ update: PanelConfigUpdate) async {
        do {
            panelConfig = try await backend.savePanelConfig(update)
        } catch {
            show(error)
            return
        }
        await checkPanel(saved: "Zapisano ustawienia ekranu")
    }

    func resetPanelConfig() async {
        do {
            panelConfig = try await backend.resetPanelConfig()
        } catch {
            show(error)
            return
        }
        await checkPanel(saved: "Przywrócono ustawienia z serwera")
    }

    func loadLibraryStorage() async {
        libraryStorage = try? await backend.libraryStorage()
    }

    /// A new limit for the catalogue's thumbnails or the originals; the
    /// frame.env value resets to it. A lower one is trimmed on the server in
    /// the background, measured anew a little later.
    func setLibraryLimit(catalogueMb: Int? = nil, originalsMb: Int? = nil) async {
        guard let old = libraryStorage else { return }
        let catalogue = catalogueMb.flatMap { $0 == old.catalogueMb ? nil : $0 }
        let originals = originalsMb.flatMap { $0 == old.originalsMb ? nil : $0 }
        guard catalogue != nil || originals != nil else { return }
        do {
            libraryStorage = try await backend.saveLibraryLimits(
                LibraryStorageUpdate(catalogueMb: catalogue, originalsMb: originals)
            )
        } catch {
            show(error)
            return
        }
        if let originals {
            notices.done("Oryginały mogą zająć do \(ByteSize.mb(originals))")
        } else if let catalogue {
            notices.done("Katalog może zająć do \(ByteSize.mb(catalogue))")
        }
        let lower = (catalogue ?? .max) < old.catalogueMb || (originals ?? .max) < old.originalsMb
        guard lower else { return }
        try? await Task.sleep(for: .seconds(8))
        await loadLibraryStorage()
    }

    func loadServerUpdate() async {
        serverUpdate = try? await backend.serverUpdate()
    }

    /// The server asks the image registry and answers at once (newer servers);
    /// older servers, or one that cannot reach the registry, leave it to the
    /// helper, which pulls the newest image (a minute or more).
    func checkServerUpdate() async {
        let card = notices.begin("Sprawdzam, czy jest nowsza wersja serwera")
        do {
            serverUpdate = try await backend.checkServerUpdate()
        } catch {
            notices.fail(error, in: card)
            return
        }
        for _ in 0..<60 where serverUpdate?.busy ?? false {
            try? await Task.sleep(for: .seconds(3))
            guard let view = try? await backend.serverUpdate() else { continue }
            serverUpdate = view
            if !view.busy { break }
        }
        guard let view = serverUpdate, !view.busy else {
            notices.drop(card)
            return
        }
        if view.state == "failed" {
            notices.end(card, .error, "Nie udało się sprawdzić wersji serwera", view.error)
        } else if view.offersUpdate {
            notices.end(card, .info, "Jest nowsza wersja serwera", view.latestVersion.map { "Wersja \($0)." })
        } else {
            notices.end(card, .done, "Serwer jest aktualny")
        }
    }

    /// The helper replaces the server's container with the newest image; the
    /// server is away for about a minute and comes back as the new version
    /// (or as the old one, when the new one did not start).
    func updateServer() async {
        guard let before = serverUpdate else { return }
        let card = notices.begin("Aktualizuję serwer", "Na około minutę zniknie z sieci.")
        do {
            serverUpdate = try await backend.updateServer()
        } catch {
            notices.fail(error, in: card)
            return
        }
        updatingServer = true
        updatingServerFrom = before.version
        defer {
            updatingServer = false
            updatingServerFrom = nil
        }
        var wentAway = false
        let deadline = Date.now.addingTimeInterval(300)
        while Date.now < deadline {
            try? await Task.sleep(for: .seconds(3))
            guard let view = try? await backend.serverUpdate() else {
                wentAway = true
                continue
            }
            serverUpdate = view
            if view.busy { continue }
            if view.state == "failed" {
                notices.end(card, .error, "Aktualizacja serwera się nie udała", view.error)
                return
            }
            if wentAway || view.version != before.version {
                notices.end(card, .done, "Serwer zaktualizowany do wersji \(view.version)")
                await refreshAll()
                return
            }
            if !view.offersUpdate {
                notices.end(card, .done, "Serwer jest aktualny")
                return
            }
        }
        notices.end(card, .error, "Serwer nie wrócił po aktualizacji", "Sprawdź Container Manager na NAS-ie.")
    }

    func loadPanelApp() async {
        panelApp = try? await backend.panelApp()
    }

    /// Points the panel's launcher at the Frame app and starts it (installs
    /// it when the frame has another version); a sleeping frame is woken first.
    func installPanelApp() async {
        let card = notices.begin("Uruchamiam aplikację Frame na ramce", "Śpiącą ramkę najpierw budzę.")
        do {
            panelApp = try await backend.installPanelApp()
            notices.end(card, .done, "Aplikacja Frame uruchomiona", "Za chwilę ramka sama poprosi o obraz.")
        } catch {
            notices.fail(error, in: card)
        }
        await refreshStatus(live: false)
    }

    func loadAiSettings() async {
        aiSettings = try? await backend.aiSettings()
    }

    func saveAiSettings(_ update: AiSettingsUpdate) async {
        do {
            aiSettings = try await backend.saveAiSettings(update)
        } catch {
            show(error)
        }
    }

    /// True when the server checked the key with Anthropic and kept it.
    func saveAiKey(_ key: String) async -> Bool {
        do {
            aiSettings = try await backend.saveAiKey(key)
        } catch BackendError.http(400, _) {
            notices.fail("Anthropic nie przyjął klucza", "Sprawdź, czy skopiowano go w całości.")
            return false
        } catch BackendError.http(502, _) {
            notices.fail("Anthropic teraz nie odpowiada", "Spróbuj za chwilę.")
            return false
        } catch {
            show(error)
            return false
        }
        notices.done("Klucz zapisany")
        return true
    }

    func deleteAiKey() async {
        do {
            aiSettings = try await backend.deleteAiKey()
        } catch {
            show(error)
            return
        }
        notices.done("Usunięto klucz")
    }

    func keywordsEstimate() async -> AiEstimate? {
        do {
            return try await backend.keywordsEstimate()
        } catch {
            show(error)
            return nil
        }
    }

    func describeLibrary() async {
        do {
            let started = try await backend.describeLibrary()
            if started.items == 0 {
                notices.info("Cała biblioteka ma już słowa kluczowe")
            } else {
                notices.done("Opisuję \(Names.pictures(started.items))", "Potrwa do doby.")
            }
        } catch {
            show(error)
        }
        await loadAiSettings()
    }

    private func checkPanel(saved: String) async {
        guard panelConfig?.host != nil, panelConfig?.pinSet == true else {
            await refreshStatus(live: false)
            notices.done(saved)
            return
        }
        let card = notices.begin(saved, "Sprawdzam, czy ekran odpowiada")
        await refreshStatus(live: true)
        switch status?.device.reachable {
        case .some(true): notices.end(card, .done, saved, "Ekran odpowiada.")
        case .some(false) where status?.device.error?.contains("authentication") == true:
            notices.end(card, .error, "Ekran odrzucił PIN", "\(saved). Sprawdź PIN w menu ekranu.")
        case .some(false): notices.end(card, .warning, "Ekran nie odpowiada, może śpi", "\(saved).")
        case .none: notices.end(card, .done, saved)
        }
    }

    /// `sleepAfter`: woken only to check on it (see `checkStatus`).
    func wake(sleepAfter: Bool = false) async {
        let card = notices.begin("Budzę ramkę", "Na baterii trwa to do 3 minut")
        do {
            let result = try await backend.wake(sleepAfter: sleepAfter)
            if result.woke == true {
                notices.end(
                    card, .done, "Ramka się obudziła",
                    result.started == true ? "Aplikacja na niej wystartowała od nowa." : nil
                )
            } else if result.problem == "no_certificates" {
                notices.end(card, .error, Self.noCertificates.0, Self.noCertificates.1)
            } else if result.asleepUntil != nil || result.deepSleep == true {
                warnDeepSleep(
                    result.asleepUntilAt ?? status?.device.wakeAt,
                    off: status?.device.switchedOff == true,
                    lost: result.wifiLost == true,
                    in: card
                )
            } else if !result.sent, result.problem == nil, status?.device.switchedOff == true {
                warnDeepSleep(nil, off: true, in: card)
            } else if !result.sent {
                notices.end(card, .warning, "Brak adresu MAC ramki", "Ustaw go w Połączeniu z ekranem.")
            } else {
                notices.end(
                    card, .warning, "Ramka nie odpowiada na sygnał budzenia",
                    "Na baterii bywa zawodny. Naciśnij krótko przycisk z tyłu ramki."
                )
            }
            await refreshStatus(live: false)
        } catch {
            notices.fail(error, in: card)
        }
    }

    /// "Wyślij ponownie" on "Teraz": the picture that did not reach the frame.
    func pushAgain() async {
        working = true
        defer { working = false }
        trackProgress(expectingStart: true)
        do {
            let result = try await backend.pushAgain()
            if result.fetched == true {
                notices.done("Ramka pobrała obraz")
            } else if !result.pushed {
                notices.warn("Ramka nie odpowiada", "Obraz trafi na nią, gdy się obudzi.")
            } else {
                notices.fail("Ramka znowu nie pobrała obrazu")
            }
        } catch {
            show(error)
        }
        await refreshPlayer()
    }

    /// "Zapisz w Zdjęciach" on a work's screen.
    func saveToPhotos(_ item: Item) async {
        let card = notices.begin("Pobieram obraz do Zdjęć")
        do {
            try await PhotoSaver.save(item, backend: backend)
            notices.end(card, .done, "Zapisano w Zdjęciach")
        } catch {
            notices.fail(error, in: card)
        }
    }

    /// "Uśpij ramkę": the app on the frame sleeps at its next question
    /// (within seconds when awake); on the charger only until its next wake.
    func sleepFrame() async {
        do {
            try await backend.sleep()
        } catch {
            show(error)
            return
        }
        notices.done(
            "Ramka zaśnie za kilka sekund",
            status?.device.powerSource == "ac"
                ? "Na zasilaczu obudzi się na najbliższą zmianę i znów nie będzie spać." : nil
        )
        await refreshStatus(live: false)
    }

    /// "Uruchom ponownie": the frame reboots and shows its picture again.
    func restartFrame() async {
        let card = notices.begin("Uruchamiam ramkę ponownie", "Śpiącą ramkę najpierw budzę.")
        do {
            let result = try await backend.restart()
            if result.woke == true {
                notices.end(card, .done, "Ramka uruchamia się ponownie", "Za 2–3 minuty znów pokaże obraz.")
            } else if result.problem == "no_certificates" {
                notices.end(card, .error, Self.noCertificates.0, Self.noCertificates.1)
            } else if result.asleepUntil != nil || result.deepSleep == true {
                warnDeepSleep(
                    result.asleepUntilAt ?? status?.device.wakeAt,
                    off: status?.device.switchedOff == true,
                    lost: result.wifiLost == true,
                    in: card
                )
            } else if !result.sent, status?.device.switchedOff == true {
                warnDeepSleep(nil, off: true, in: card)
            } else {
                notices.end(
                    card, .warning, "Ramka nie odpowiada",
                    "Naciśnij krótko przycisk z tyłu ramki i spróbuj jeszcze raz."
                )
            }
            await refreshStatus(live: false)
        } catch {
            notices.fail(error, in: card)
        }
    }

    /// "Głęboki sen" for `hours`, or "Wyłącz ramkę" (`hours` nil).
    func restFrame(hours: Int?) async {
        let result: RestResult
        do {
            result = try await backend.rest(hours: hours)
        } catch {
            show(error)
            return
        }
        let later = result.applies == "at_wake"
        switch (When.at(result.until), later) {
        case let (at?, true):
            notices.done("Ramka śpi teraz bez Wi-Fi", "Przy najbliższej pobudce zaśnie głęboko do \(at).")
        case let (at?, false):
            notices.done("Ramka zaśnie bez Wi-Fi do \(at)", "Wcześniej obudzi ją tylko przycisk.")
        case (nil, true):
            notices.done("Ramka śpi teraz bez Wi-Fi", "Wyłączy się przy najbliższej pobudce.")
        case (nil, false):
            notices.done("Ramka wyłączy się za chwilę", "Włączysz ją przyciskiem na ramce.")
        }
        await refreshStatus(live: false)
    }

    /// An error on a card; a request cut short is no news.
    func show(_ error: Error) {
        notices.fail(error)
    }

    // MARK: Pictures that did not load

    /// The server has no picture of the work anywhere: grids leave it out.
    func pictureMissing(_ itemID: String) {
        guard !missingPictures.contains(itemID) else { return }
        missingPictures.insert(itemID)
    }

    /// Every picture on screen that failed tries again (a tap on one of them).
    func retryPictures() {
        pictureRetries += 1
    }
}

extension Error {
    /// URLSession says "anulowane" for a cancelled task: nothing went wrong.
    var isCancellation: Bool {
        if self is CancellationError { return true }
        return (self as? URLError)?.code == .cancelled
    }
}
