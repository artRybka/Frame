import Foundation
import Observation

/// App-wide state: connection settings and what the frame currently shows.
@MainActor
@Observable
final class AppModel {
    private enum Keys {
        static let serverURL = "serverURL"
        static let apiToken = "apiToken"
    }

    var serverURL: String
    var apiToken: String
    var nowPlaying: NowPlaying?
    var preview: Data?
    var deviceStatus: DeviceStatus?
    var lastError: String?
    var isLoading = false

    init() {
        serverURL = UserDefaults.standard.string(forKey: Keys.serverURL)
            ?? "http://homeassistant.local:8099"
        apiToken = KeychainStore.read(Keys.apiToken) ?? ""
    }

    var api: FrameAPI? {
        guard let url = URL(string: serverURL), url.scheme != nil else { return nil }
        return FrameAPI(baseURL: url, token: apiToken.isEmpty ? nil : apiToken)
    }

    func saveSettings() {
        UserDefaults.standard.set(serverURL, forKey: Keys.serverURL)
        KeychainStore.write(Keys.apiToken, value: apiToken)
    }

    func refresh() async {
        guard let api else {
            lastError = String(localized: "Nieprawidłowy adres serwera")
            return
        }
        isLoading = true
        defer { isLoading = false }
        do {
            let now = try await api.nowPlaying()
            if now != nowPlaying {
                nowPlaying = now
                preview = try await api.data(path: now.previewUrl)
            }
            lastError = nil
        } catch {
            lastError = error.localizedDescription
        }
    }

    func loadDeviceStatus() async {
        guard let api else { return }
        do {
            deviceStatus = try await api.deviceStatus()
            lastError = nil
        } catch {
            lastError = error.localizedDescription
        }
    }
}
