import Foundation
import Network
import Observation

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

    var player: PlayerView?
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
    /// Claude's settings, spending and progress; loaded when Konfiguracja
    /// opens, nil on an older server.
    var aiSettings: AiSettings?
    var playlists: [PlaylistSummary] = []
    /// Goes up when a work is liked, unliked, left out or brought back:
    /// views listing a playlist's works load them again.
    private(set) var libraryRevision = 0
    var facets = Facets.empty
    /// Styles, subjects, periods and techniques to search by, with Polish names.
    var vocabulary: [TermInfo] = []
    var connection = Connection.unknown
    var toast: String?
    var working = false
    /// "Sprawdź stan" found the frame asleep and is waking it.
    var wakingForStatus = false
    /// The bar under the picture: set while a picture is on its way to the
    /// frame, and for a moment after it arrives.
    var displayProgress: DisplayProgress?
    /// An artist whose works Discover's search should show: set by tapping
    /// the name on a work, taken (and cleared) by the search.
    var artistSearch: String?
    /// Discover's rows and themes as last loaded (also by the previous
    /// launch): shown at once while fresh ones load.
    var suggestionRows: [SuggestionRow]?
    var themes: [ArtTheme]?
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
        restoreDiscover()
        watchNetwork()
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
        aiSettings = nil
        playlists = []
        facets = .empty
        vocabulary = []
        restoreDiscover()
        await refreshAll()
    }

    var currentItem: Item? { player?.current?.item }

    var isPortrait: Bool { settings?.orientation == "portrait" }

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
        self.player = await player.value
        if self.player?.progress?.active == true { trackProgress() }
        self.status = await status.value
        self.settings = await settings.value
        self.playlists = await playlists.value ?? []
        self.facets = await facets.value ?? .empty
        self.panelConfig = await panelConfig.value
        // Ready before Discover is opened.
        Task { await refreshDiscover() }
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
        let (gotRows, gotThemes) = await (rows, themes)
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

    /// "Sprawdź stan": a live check, and if the frame does not answer, an
    /// attempt to wake it. Deep sleep has the Wi-Fi off: only the frame's
    /// alarm or its button ends it, so no signal is sent then.
    func checkStatus() async {
        await refreshStatus(live: true)
        guard let device = status?.device, device.configured, device.reachable == false else { return }
        if device.powerState == "deep_sleep" {
            toast = Self.deepSleepNote(until: device.wakesAt)
            return
        }
        wakingForStatus = true
        defer { wakingForStatus = false }
        await wake(sleepAfter: true)
    }

    private static func deepSleepNote(until: String?) -> String {
        let alarm = until.map { "budzik o \($0) lub przycisk" } ?? "tylko przycisk"
        return "Ramka w głębokim śnie (Wi-Fi wyłączone), obudzi ją \(alarm)"
    }

    func refreshPlaylists() async {
        if let value = try? await backend.playlists() { playlists = value }
    }

    func refreshFacets() async {
        if let value = try? await backend.facets() { facets = value }
    }

    func loadVocabulary() async {
        guard vocabulary.isEmpty else { return }
        if let value = try? await backend.vocabulary() { vocabulary = value }
    }

    /// Polish names of the vocabulary's terms by key.
    var termNames: [String: String] {
        Dictionary(vocabulary.map { ($0.key, $0.name) }, uniquingKeysWith: { first, _ in first })
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
        if let error = player?.lastError, !error.isEmpty { toast = error }
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
        }
    }

    private func finishProgress(_ value: DisplayProgress) async {
        displayProgress = value
        if value.isDone {
            await refreshPlayer()
            try? await Task.sleep(for: .seconds(2.5))
        } else {
            try? await Task.sleep(for: .seconds(5))  // long enough to read why
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
        toast = offset == 0 ? "Nowy kadr — ramka odświeża obraz" : "Wysyłam na ramkę…"
        return true
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
            toast = "Odpięto"
        } catch { show(error) }
    }

    func show(itemID: String, hold: HoldSpec) async {
        await perform { try await self.backend.show(itemID: itemID, hold: hold) }
        toast = "Wysyłam na ramkę…"
        await followPlayer()
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
        toast = player?.hold?.forever == true
            ? "W kolejce jako następne — po odpięciu obrazu"
            : "W kolejce jako następne"
    }

    func dequeue(itemID: String) async {
        do {
            player = try await backend.dequeue(itemID: itemID)
            toast = "Usunięto z kolejki"
        } catch { show(error) }
    }

    /// "Pomiń" on a picture waiting in the queue; false if it failed.
    func skip(_ summary: ItemSummary) async -> Bool {
        do {
            player = try await backend.skip(itemID: summary.id)
            toast = "Pominięto „\(summary.shownTitle)”"
            return true
        } catch {
            show(error)
            return false
        }
    }

    func play(_ playlist: PlaylistSummary) async {
        await perform { try await self.backend.play(playlistID: playlist.id) }
        settings?.playlistId = playlist.id
        toast = "Teraz prezentowane: \(playlist.name)"
        await followPlayer()
    }

    func setFavorite(_ id: String, _ favorite: Bool) async -> Item? {
        do {
            let item = try await backend.setFavorite(id: id, favorite)
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
            toast = !turned && restyled ? "Zapisano. Nowy wygląd dostanie następny obraz" : "Zapisano ustawienia"
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
            toast = new.name.map { "Ramka nazywa się teraz „\($0)”" } ?? "Przywrócono nazwę z ekranu"
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
            toast = "Oryginały mogą zająć do \(ByteSize.mb(originals))"
        } else if let catalogue {
            toast = "Katalog może zająć do \(ByteSize.mb(catalogue))"
        }
        let lower = (catalogue ?? .max) < old.catalogueMb || (originals ?? .max) < old.originalsMb
        guard lower else { return }
        try? await Task.sleep(for: .seconds(8))
        await loadLibraryStorage()
    }

    func loadPanelApp() async {
        panelApp = try? await backend.panelApp()
    }

    /// Points the panel's launcher at the Frame app and starts it (installs
    /// it when the frame has another version); a sleeping frame is woken first.
    func installPanelApp() async {
        toast = "Uruchamiam aplikację Frame na ramce…"
        do {
            panelApp = try await backend.installPanelApp()
            toast = "Ramka uruchamia aplikację Frame, za chwilę sama poprosi o obraz"
        } catch {
            show(error)
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
            toast = "Anthropic nie przyjął klucza. Sprawdź, czy skopiowano go w całości."
            return false
        } catch BackendError.http(502, _) {
            toast = "Anthropic teraz nie odpowiada. Spróbuj za chwilę."
            return false
        } catch {
            show(error)
            return false
        }
        toast = "Klucz zapisany"
        return true
    }

    func deleteAiKey() async {
        do {
            aiSettings = try await backend.deleteAiKey()
        } catch {
            show(error)
            return
        }
        toast = "Usunięto klucz"
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
            toast = started.items == 0
                ? "Cała biblioteka ma już słowa kluczowe"
                : "Opisuję \(Names.pictures(started.items)), potrwa do doby"
        } catch {
            show(error)
        }
        await loadAiSettings()
    }

    private func checkPanel(saved: String) async {
        guard panelConfig?.host != nil, panelConfig?.pinSet == true else {
            await refreshStatus(live: false)
            toast = saved
            return
        }
        toast = "\(saved) · sprawdzam ekran…"
        await refreshStatus(live: true)
        switch status?.device.reachable {
        case .some(true): toast = "\(saved) · ekran odpowiada"
        case .some(false) where status?.device.error?.contains("authentication") == true:
            toast = "\(saved) · ekran odrzucił PIN"
        case .some(false): toast = "\(saved) · ekran nie odpowiada (może śpi)"
        case .none: toast = saved
        }
    }

    /// `sleepAfter`: woken only to check on it (see `checkStatus`).
    func wake(sleepAfter: Bool = false) async {
        toast = "Budzę ramkę…"
        do {
            let result = try await backend.wake(sleepAfter: sleepAfter)
            if result.woke == true {
                toast = "Ramka się obudziła"
            } else if result.problem == "no_certificates" {
                toast = Delivery.noCertificates
            } else if let until = result.asleepUntil {
                toast = Self.deepSleepNote(until: until)
            } else if !result.sent {
                toast = "Brak adresu MAC ramki, ustaw go w Połączeniu z ekranem"
            } else {
                toast = "Ramka nie odpowiada na sygnał budzenia. Na baterii bywa zawodny: naciśnij krótko przycisk z tyłu ramki"
            }
            await refreshStatus(live: false)
        } catch {
            show(error)
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
                toast = "Ramka pobrała obraz"
            } else if !result.pushed {
                toast = "Ramka nie odpowiada, obraz trafi na nią, gdy się obudzi"
            } else {
                toast = "Ramka znowu nie pobrała obrazu"
            }
        } catch {
            show(error)
        }
        await refreshPlayer()
    }

    /// "Zapisz w Zdjęciach" on a work's screen.
    func saveToPhotos(_ item: Item) async {
        toast = "Pobieram obraz…"
        do {
            try await PhotoSaver.save(item, backend: backend)
            toast = "Zapisano w Zdjęciach"
        } catch is CancellationError {
            toast = nil
        } catch {
            show(error)
        }
    }

    /// "Uśpij ramkę": the server notes the sleep, so the status from it
    /// (not asking the panel, which may still answer for a while) shows it.
    func sleepFrame() async {
        do {
            try await backend.sleep()
        } catch {
            show(error)
            return
        }
        toast = "Ramka uśpiona"
        await refreshStatus(live: false)
    }

    private func perform(_ action: @escaping () async throws -> Void) async {
        do {
            try await action()
        } catch {
            show(error)
        }
    }

    func show(_ error: Error) {
        // A request cut short (a pull to refresh let go, a view gone) is no news.
        guard !error.isCancellation else { return }
        toast = error.localizedDescription
    }
}

extension Error {
    /// URLSession says "anulowane" for a cancelled task: nothing went wrong.
    var isCancellation: Bool {
        if self is CancellationError { return true }
        return (self as? URLError)?.code == .cancelled
    }
}
