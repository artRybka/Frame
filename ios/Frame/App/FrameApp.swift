import SwiftUI

@main
struct FrameApp: App {
    @UIApplicationDelegateAdaptor(PushAppDelegate.self) private var pushDelegate
    @State private var model = AppModel()

    init() {
        // Thumbnails the server marks as good for a day stay on disk across
        // launches, so Discover's covers and rows show at once.
        URLCache.shared = URLCache(memoryCapacity: 32 << 20, diskCapacity: 300 << 20)
        // Watches the app going away from the first request on.
        _ = Absence.shared
        Theme.serifNavigationTitles()
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .tint(Theme.ink)
                // A tap on a Lock Screen card ("Studium gotowe"): where it points,
                // as for a notification.
                .onOpenURL { url in
                    // An invitation to the frame (QR code, AirDrop, Wiadomości).
                    if model.open(invitation: url) { return }
                    let route = URLComponents(url: url, resolvingAgainstBaseURL: false)?
                        .queryItems?.first { $0.name == "route" }?.value
                    if let route { PushCenter.shared.open(route) }
                }
        }
    }
}
