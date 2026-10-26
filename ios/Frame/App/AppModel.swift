import Foundation
import Observation

/// App-wide state: connection, what the frame shows, its status and settings.
@MainActor
@Observable
final class AppModel {
    private enum Keys {
        static let serverURL = "serverURL"
        static let apiToken = "apiToken"
        static let demoMode = "demoMode"
    }

    enum Connection: Equatable {
        case unknown, connected, failed(String)
    }

    var serverURL: String
    var apiToken: String
    var demoMode: Bool
    private(set) var backend: any FrameBackend

    var player: PlayerView?
    var status: StatusView?
    var settings: FrameSettings?
    /// How the server reaches the panel; nil before it is loaded or on an older server.
    var panelConfig: PanelConfig?
    var playlists: [PlaylistSummary] = []
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
    private var progressTask: Task<Void, Never>?

    init() {
        let defaults = UserDefaults.standard
        let url = defaults.string(forKey: Keys.serverURL) ?? ""
        let token = KeychainStore.read(Keys.apiToken) ?? ""
        let forcedDemo = defaults.bool(forKey: "demo")  // launch argument -demo YES
        let demo = forcedDemo || (defaults.object(forKey: Keys.demoMode) as? Bool ?? url.isEmpty)
        serverURL = url
        apiToken = token
        demoMode = demo
        backend = Self.makeBackend(demo: demo, url: url, token: token)
    }

    private static func makeBackend(demo: Bool, url: String, token: String) -> any FrameBackend {
        if !demo, let base = URL(string: url), base.scheme != nil {
            return LiveBackend(baseURL: base, token: token.isEmpty ? nil : token)
        }
        return DemoBackend()
    }

    /// Persist connection settings and switch backend.
    func applyConnection() async {
        UserDefaults.standard.set(serverURL, forKey: Keys.serverURL)
        UserDefaults.standard.set(demoMode, forKey: Keys.demoMode)
        KeychainStore.write(Keys.apiToken, value: apiToken)
        backend = Self.makeBackend(demo: demoMode, url: serverURL, token: apiToken)
        player = nil
        status = nil
        displayProgress = nil
        settings = nil
        panelConfig = nil
        playlists = []
        facets = .empty
        vocabulary = []
        await refreshAll()
    }

    var currentItem: Item? { player?.current?.item }

    var isPortrait: Bool { settings?.orientation == "portrait" }

    // MARK: Loading

    func refreshAll() async {
        do {
            _ = try await backend.health()
            connection = .connected
        } catch {
            connection = .failed(error.localizedDescription)
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
    }

    func refreshPlayer() async {
        if let value = try? await backend.player() { player = value }
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
            try? await Task.sleep(for: .seconds(1))
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
            return item
        } catch {
            show(error)
            return nil
        }
    }

    func saveSettings(_ new: FrameSettings) async {
        let reframed = settings?.presentationKey != new.presentationKey
        do {
            settings = try await backend.saveSettings(new)
            toast = "Zapisano ustawienia"
            if reframed {
                // The server redraws the current picture with the new framing.
                await followPlayer()
            } else {
                await refreshPlayer()
            }
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
            } else if let until = result.asleepUntil {
                toast = Self.deepSleepNote(until: until)
            } else if !result.sent {
                toast = "Brak adresu MAC ramki, ustaw go w Połączeniu z ekranem"
            } else {
                toast = "Ramka nie odpowiada na sygnał budzenia"
            }
            await refreshStatus(live: false)
        } catch {
            show(error)
        }
    }

    func sleepFrame() async {
        await perform { try await self.backend.sleep() }
        toast = "Ramka uśpiona"
    }

    private func perform(_ action: @escaping () async throws -> Void) async {
        do {
            try await action()
        } catch {
            show(error)
        }
    }

    func show(_ error: Error) {
        toast = error.localizedDescription
    }
}
