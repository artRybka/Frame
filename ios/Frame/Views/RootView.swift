import SwiftUI

/// Launch arguments used by CI screenshots, e.g. `-demo YES -screen discover`,
/// plus `-fit description -mat black` to start the demo with that presentation.
enum LaunchRoute {
    static let screen = UserDefaults.standard.string(forKey: "screen") ?? ""
    static let fit = UserDefaults.standard.string(forKey: "fit")
    static let mat = UserDefaults.standard.string(forKey: "mat")
    /// "end", "composition", "details", "legacy": a long page opens scrolled
    /// there; "studies": Discover at "Studia dzieł".
    static let scroll = UserDefaults.standard.string(forKey: "scroll")
    /// The composition's take shown first (CI screenshots of "Rytm").
    static let take = UserDefaults.standard.integer(forKey: "take")
}

struct RootView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.scenePhase) private var scenePhase
    @State private var tab = Tab.initial

    enum Tab: Hashable {
        case now, discover, search, playlists, frame

        static var initial: Tab {
            switch LaunchRoute.screen {
            case "discover", "discover-group", "daily", "detail", "original": .discover
            case "museums", "search", "search-picker": .search
            case "playlists", "playlist", "editor", "editor-new", "editor-manual": .playlists
            case "frame", "notices", "connection", "battery", "schedule", "schedule-economy", "presentation", "presentation-photo", "orientation": .frame
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
            SearchView()
                .tabItem { Label("Szukaj", systemImage: "magnifyingglass") }
                .tag(Tab.search)
            PlaylistsView()
                .tabItem { Label("Playlisty", systemImage: "rectangle.stack") }
                .tag(Tab.playlists)
            FrameTabView()
                .tabItem { Label("Ramka", systemImage: "slider.horizontal.3") }
                .tag(Tab.frame)
        }
        // Cards and the send bar, in a window above the app (over sheets too).
        .background { NoticeWindowInstaller(model: model) }
        // "Teraz" shows the full send bar under the picture.
        .onChange(of: tab, initial: true) { _, tab in model.notices.nowTabOpen = tab == .now }
        .onChange(of: model.artistSearch) { _, artist in
            if artist != nil { tab = .search }
        }
        .onChange(of: model.suggestionsOpened) { tab = .discover }
        // A study ready, opened from its card at the bottom.
        .sheet(isPresented: Binding(
            get: { model.studySheet != nil },
            set: { if !$0 { model.studySheet = nil } }
        )) {
            if let id = model.studySheet { StudySheet(itemID: id) }
        }
        .task {
            await model.refreshAll()
            await model.settleLiveActivity()  // one left from before the app was closed
        }
        .task {
            // CI screenshots: the cards at the bottom, one of each kind.
            guard LaunchRoute.screen == "notices" else { return }
            try? await Task.sleep(for: .seconds(2))
            model.notices.begin("„Japonia”: pobieram dzieła z muzeów", background: true)
            let wake = model.notices.begin("Budzę ramkę", "Na baterii trwa to do 3 minut")
            model.notices.warn(
                "Ramka śpi głęboko, sama obudzi się jutro o 7:00",
                "Po odpięciu zasilacza sygnał budzenia jej nie budzi. Wcześniej obudzi ją krótkie naciśnięcie przycisku z tyłu."
            )
            try? await Task.sleep(for: .seconds(4))
            model.notices.end(wake, .done, "Ramka się obudziła")
        }
        .task(id: model.player?.delivery?.isWaiting == true) { await model.followWaiting() }
        .task(id: "\(model.player?.nextChangeAt ?? "") \(model.player?.hold?.until ?? "")") {
            await model.followSchedule()
        }
        .onChange(of: scenePhase) { old, phase in
            // Back from the background, maybe on another network.
            if old == .background, phase != .background {
                Task {
                    await model.recheckServer()
                    await model.settleLiveActivity()
                }
            }
        }
    }
}

#Preview {
    RootView().environment(AppModel())
}
