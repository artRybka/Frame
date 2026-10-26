import SwiftUI

@main
struct FrameApp: App {
    @State private var model = AppModel()

    init() {
        // Thumbnails the server marks as good for a day stay on disk across
        // launches, so Discover's covers and rows show at once.
        URLCache.shared = URLCache(memoryCapacity: 32 << 20, diskCapacity: 300 << 20)
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .tint(Theme.accent)
        }
    }
}
