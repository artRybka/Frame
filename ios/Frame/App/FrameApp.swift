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
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .tint(Theme.accent)
        }
    }
}
