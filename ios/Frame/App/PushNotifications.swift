import Observation
import SwiftUI
import UIKit
import UserNotifications

/// Notifications from the frame's server over APNs: the server sends them
/// (notifications.py) to the device token this phone registered there, so
/// they arrive away from home too. Taps open where they point (`route`).
@MainActor
@Observable
final class PushCenter {
    static let shared = PushCenter()
    private static let tokenKey = "pushToken"

    /// The APNs device token (hex), as iOS last gave it.
    private(set) var token: String? = UserDefaults.standard.string(forKey: PushCenter.tokenKey)
    private(set) var authorization: UNAuthorizationStatus = .notDetermined
    /// Why iOS gave no token (e.g. a build without the push entitlement).
    private(set) var registrationError: String?
    /// A tapped notification's `route` waiting for the app to take it.
    private(set) var pendingRoute: String?
    private(set) var taps = 0

    @ObservationIgnored var onToken: ((String) -> Void)?

    /// A build from Xcode talks to APNs' sandbox; TestFlight and the App Store do not.
    static var sandbox: Bool {
        #if DEBUG
        true
        #else
        false
        #endif
    }

    func refreshAuthorization() async {
        authorization = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
    }

    /// Asks once; then registers with APNs (the token comes to `received`).
    @discardableResult
    func request() async -> Bool {
        let granted = (try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge])) ?? false
        await refreshAuthorization()
        if granted { register() }
        return granted
    }

    /// On every launch when allowed: the token may change.
    func registerIfAllowed() async {
        await refreshAuthorization()
        if authorization == .authorized || authorization == .provisional { register() }
    }

    private func register() {
        UIApplication.shared.registerForRemoteNotifications()
    }

    func received(token: String) {
        registrationError = nil
        self.token = token
        UserDefaults.standard.set(token, forKey: Self.tokenKey)
        onToken?(token)
    }

    func failed(_ error: Error) {
        registrationError = error.localizedDescription
    }

    func open(_ route: String?) {
        pendingRoute = route
        taps += 1
    }

    func takeRoute() -> String? {
        defer { pendingRoute = nil }
        return pendingRoute
    }
}

/// The app delegate for what only UIKit hears: the APNs token and taps.
final class PushAppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        Task { @MainActor in PushCenter.shared.received(token: token) }
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        let message = error.localizedDescription
        Task { @MainActor in PushCenter.shared.failed(PushRegistrationError(message: message)) }
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        // With the app open its send bar already says these.
        let kind = notification.request.content.userInfo["kind"] as? String
        if kind == "changed" || kind == "send_failed" {
            completionHandler([])
        } else {
            completionHandler([.banner, .list, .sound])
        }
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let route = response.notification.request.content.userInfo["route"] as? String
        Task { @MainActor in PushCenter.shared.open(route) }
        completionHandler()
    }
}

private struct PushRegistrationError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

// MARK: The model's side

extension AppModel {
    /// Server's view of notifications for this phone; registers it first
    /// when iOS allows notifications and the token is not there yet.
    func loadNotifications() async {
        let push = PushCenter.shared
        await push.refreshAuthorization()
        notificationSettings = try? await backend.notifications(device: push.token)
        if let token = push.token, notificationSettings?.device == nil,
           push.authorization == .authorized || push.authorization == .provisional {
            await registerPush(token)
        }
    }

    /// The token on the server (on every launch: it may change); the kinds stay.
    func registerPush(_ token: String) async {
        let update = PushDeviceUpdate(sandbox: PushCenter.sandbox, kinds: nil, name: UIDevice.current.name)
        do {
            notificationSettings = try await backend.registerPush(token: token, update)
        } catch {
            if !error.isCancellation { notices.fail(error) }
        }
    }

    func enableNotifications() async {
        let push = PushCenter.shared
        if await push.request() {
            if let token = push.token { await registerPush(token) }  // a new one follows if it changed
        } else {
            notices.warn("Powiadomienia są wyłączone", "Włącz je w Ustawieniach iOS → Frame → Powiadomienia.")
        }
    }

    func setNotification(_ kind: String, on: Bool) async {
        guard let token = PushCenter.shared.token, var settings = notificationSettings else { return }
        var kinds = settings.device?.kinds ?? settings.kinds.map(\.key)
        kinds.removeAll { $0 == kind }
        if on { kinds.append(kind) }
        // In the server's order; at once on screen, the server answers after.
        kinds = settings.kinds.map(\.key).filter(kinds.contains)
        settings.device?.kinds = kinds
        notificationSettings = settings
        let update = PushDeviceUpdate(sandbox: PushCenter.sandbox, kinds: kinds, name: UIDevice.current.name)
        do {
            notificationSettings = try await backend.registerPush(token: token, update)
        } catch {
            if !error.isCancellation { notices.fail(error) }
            await loadNotifications()
        }
    }

    func uploadPushKey(from url: URL) async {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        do {
            let data = try Data(contentsOf: url)
            notificationSettings = try await backend.uploadPushKey(
                filename: url.lastPathComponent, data: data, device: PushCenter.shared.token
            )
            notices.done("Klucz APNs zapisany na serwerze")
        } catch {
            if !error.isCancellation { notices.fail(error) }
        }
    }

    func deletePushKey() async {
        do {
            notificationSettings = try await backend.deletePushKey(device: PushCenter.shared.token)
        } catch {
            if !error.isCancellation { notices.fail(error) }
        }
    }

    /// A test notification; nil when Apple took it, else why not.
    func testNotification() async -> String? {
        guard let token = PushCenter.shared.token else { return "Telefon nie ma jeszcze tokenu APNs." }
        do {
            let result = try await backend.testPush(device: token)
            return result.ok ? nil : (result.error ?? "Apple nie przyjął powiadomienia.")
        } catch {
            let (title, detail) = Notices.words(for: error)
            return [title, detail].compactMap { $0 }.joined(separator: ". ")
        }
    }
}
