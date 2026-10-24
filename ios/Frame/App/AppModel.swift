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
    var playlists: [PlaylistSummary] = []
    var facets = Facets.empty
    var calibration: CalibrationInfo?
    var connection = Connection.unknown
    var toast: String?
    var working = false

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
        settings = nil
        playlists = []
        facets = .empty
        calibration = nil
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
        let calibration = Task { try? await backend.calibration() }
        self.player = await player.value
        self.status = await status.value
        self.settings = await settings.value
        self.playlists = await playlists.value ?? []
        self.facets = await facets.value ?? .empty
        self.calibration = await calibration.value
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

    func refreshPlaylists() async {
        if let value = try? await backend.playlists() { playlists = value }
    }

    func refreshFacets() async {
        if let value = try? await backend.facets() { facets = value }
    }

    /// After an action the server renders and pushes in the background;
    /// follow it until it is done.
    func followPlayer() async {
        working = true
        defer { working = false }
        for attempt in 0 ..< 90 {
            try? await Task.sleep(for: .seconds(attempt == 0 ? 0.4 : 1.5))
            await refreshPlayer()
            if player?.busy != true { break }
        }
        if let error = player?.lastError, !error.isEmpty { toast = error }
    }

    // MARK: Actions

    func next() async {
        await perform { try await self.backend.next() }
        await followPlayer()
    }

    func previous() async {
        await perform { try await self.backend.previous() }
        await followPlayer()
    }

    func hold(_ spec: HoldSpec) async {
        do {
            player = try await backend.hold(spec)
            toast = spec == .untilNextChange ? "Wróci zwykły harmonogram" : "Przypięto: \(spec.label.lowercased())"
        } catch { show(error) }
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
        toast = "Gotowe — obraz jest na ramce"
    }

    func play(_ playlist: PlaylistSummary) async {
        await perform { try await self.backend.play(playlistID: playlist.id) }
        settings?.playlistId = playlist.id
        settings?.mode = "art"
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

    func resetCalibration() async {
        do {
            calibration = try await backend.resetCalibration()
            toast = "Przywrócono domyślne kolory"
            await followPlayer()
        } catch { show(error) }
    }

    func wake() async {
        await perform { try await self.backend.wake() }
        toast = "Wysłano sygnał budzenia"
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
