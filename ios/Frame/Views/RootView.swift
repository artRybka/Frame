import SwiftUI

/// Launch arguments used by CI screenshots, e.g. `-demo YES -screen discover`,
/// plus `-fit description -mat black` to start the demo with that presentation.
enum LaunchRoute {
    static let screen = UserDefaults.standard.string(forKey: "screen") ?? ""
    static let fit = UserDefaults.standard.string(forKey: "fit")
    static let mat = UserDefaults.standard.string(forKey: "mat")
}

struct RootView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.scenePhase) private var scenePhase
    @State private var tab = Tab.initial

    enum Tab: Hashable {
        case now, discover, playlists, frame

        static var initial: Tab {
            switch LaunchRoute.screen {
            case "discover", "detail", "original", "museums": .discover
            case "playlists", "playlist", "editor": .playlists
            case "frame", "connection": .frame
            default: .now
            }
        }
    }

    var body: some View {
        TabView(selection: $tab) {
            NowView()
                .tabItem { Label("Teraz", systemImage: "photo.artframe") }
                .tag(Tab.now)
            DiscoverView()
                .tabItem { Label("Odkrywaj", systemImage: "square.grid.2x2") }
                .tag(Tab.discover)
            PlaylistsView()
                .tabItem { Label("Playlisty", systemImage: "rectangle.stack") }
                .tag(Tab.playlists)
            FrameTabView()
                .tabItem { Label("Ramka", systemImage: "slider.horizontal.3") }
                .tag(Tab.frame)
        }
        .overlay(alignment: .top) { ToastView() }
        .overlay(alignment: .bottom) {
            // "Teraz" shows the full bar under the picture.
            if tab != .now, let progress = model.displayProgress {
                DisplayProgressBar(progress: progress, compact: true)
                    .padding(.horizontal, 16)
                    .padding(.bottom, 58)  // above the tab bar
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.easeInOut, value: model.displayProgress == nil)
        .onChange(of: model.artistSearch) { _, artist in
            if artist != nil { tab = .discover }
        }
        .task { await model.refreshAll() }
        .onChange(of: scenePhase) { old, phase in
            // Back from the background, maybe on another network.
            if old == .background, phase != .background { Task { await model.recheckServer() } }
        }
    }
}

/// Short confirmation / error banner.
struct ToastView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        if let message = model.toast {
            Text(message)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(Theme.paper)
                .padding(.horizontal, 18)
                .padding(.vertical, 11)
                .background(Theme.ink.opacity(0.92), in: Capsule())
                .shadow(color: .black.opacity(0.2), radius: 12, y: 6)
                .padding(.top, 8)
                .transition(.move(edge: .top).combined(with: .opacity))
                .task(id: message) {
                    try? await Task.sleep(for: .seconds(2.6))
                    withAnimation(.easeOut) { model.toast = nil }
                }
                .onTapGesture { model.toast = nil }
        }
    }
}

#Preview {
    RootView().environment(AppModel())
}
