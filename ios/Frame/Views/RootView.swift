import SwiftUI

struct RootView: View {
    var body: some View {
        TabView {
            NowPlayingView()
                .tabItem { Label("Teraz", systemImage: "photo.artframe") }
            SendView()
                .tabItem { Label("Wyślij", systemImage: "square.and.arrow.up") }
            SettingsView()
                .tabItem { Label("Ustawienia", systemImage: "gearshape") }
        }
    }
}

#Preview {
    RootView()
        .environment(AppModel())
}
