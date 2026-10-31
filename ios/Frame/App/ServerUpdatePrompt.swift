import Foundation

/// After the app was updated: when the server is older than the app and a
/// newer server image is out, a card says so with "Aktualizuj" on it. A
/// release that only changed the app brings no new image, so no card then.
enum ServerUpdatePrompt {
    private enum Keys {
        /// The app version whose launch already asked the helper to look.
        static let checkedFor = "serverUpdatePrompt.checkedFor"
        /// "<app> <server>" already shown once.
        static let shown = "serverUpdatePrompt.shown"
    }

    /// The app's own version (TestFlight builds carry the release's, local
    /// builds 1.0).
    static var appVersion: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0"
    }

    /// Worth saying: the app can update this server, a newer one is out and
    /// the running one is older than the app (whose features it may lack).
    static func needed(app: String, update: ServerUpdate) -> Bool {
        update.updater && !update.addon && !update.busy && update.offersUpdate
            && isOlder(update.version, than: app)
    }

    /// "1.47.0" before "1.48.0", "0.46.1" before "1.47.0"; anything after
    /// the numbers ("-dev") is left out.
    static func isOlder(_ version: String, than other: String) -> Bool {
        let a = numbers(version), b = numbers(other)
        guard !a.isEmpty, !b.isEmpty else { return false }
        for i in 0..<max(a.count, b.count) {
            let x = i < a.count ? a[i] : 0, y = i < b.count ? b[i] : 0
            if x != y { return x < y }
        }
        return false
    }

    private static func numbers(_ version: String) -> [Int] {
        var out: [Int] = []
        for part in version.split(separator: ".") {
            guard let n = Int(part.prefix(while: \.isNumber)) else { break }
            out.append(n)
            if part.contains(where: { !$0.isNumber }) { break }
        }
        return out
    }

    static var checkedFor: String? {
        get { UserDefaults.standard.string(forKey: Keys.checkedFor) }
        set { UserDefaults.standard.set(newValue, forKey: Keys.checkedFor) }
    }

    static var shown: String? {
        get { UserDefaults.standard.string(forKey: Keys.shown) }
        set { UserDefaults.standard.set(newValue, forKey: Keys.shown) }
    }
}

extension AppModel {
    /// At launch. On the first launch of a new app version the helper looks
    /// for a newer image right away (it otherwise looks every 6 hours); the
    /// card shows once per app and server version, the Serwer tile keeps the
    /// arrow after that.
    func offerServerUpdate() async {
        guard !demoMode, connection == .connected else { return }
        let app = ServerUpdatePrompt.appVersion
        guard var update = try? await backend.serverUpdate() else { return }
        serverUpdate = update
        guard update.updater, !update.addon,
              ServerUpdatePrompt.isOlder(update.version, than: app) else { return }
        if ServerUpdatePrompt.checkedFor != app, !update.offersUpdate, !update.busy {
            guard let asked = try? await backend.checkServerUpdate() else { return }
            update = asked
            // Pulling a new image takes a minute or so.
            var polls = 0
            while update.busy, polls < 60 {
                try? await Task.sleep(for: .seconds(3))
                polls += 1
                if let view = try? await backend.serverUpdate() { update = view }
            }
            if !updatingServer { serverUpdate = update }
            if update.busy { return }  // next launch looks again
        }
        ServerUpdatePrompt.checkedFor = app
        guard ServerUpdatePrompt.needed(app: app, update: update), !updatingServer,
              let latest = update.latestVersion else { return }
        let key = "\(app) \(latest)"
        guard ServerUpdatePrompt.shown != key else { return }
        ServerUpdatePrompt.shown = key
        notices.info(
            "Zaktualizuj serwer do wersji \(latest)",
            "Aplikacja ma wersję \(app), serwer \(update.version), więc część nowości nie zadziała. Serwer zniknie na około minutę.",
            action: Notice.Action(label: "Aktualizuj") { [weak self] in
                Task { await self?.updateServer() }
            }
        )
    }
}
