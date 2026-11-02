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
    /// The composition's take shown first (CI screenshots of the later takes).
    static let take = UserDefaults.standard.integer(forKey: "take")
}

struct RootView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.scenePhase) private var scenePhase
    @State private var tab = Screen.initial

    enum Screen: Hashable {
        case now, discover, search, playlists, frame

        static var initial: Screen {
            switch LaunchRoute.screen {
            case "discover", "discover-group", "daily", "detail", "original": .discover
            case "museums", "search", "search-picker", "search-colors", "search-styles", "search-chosen": .search
            case "playlists", "playlist", "editor", "editor-new", "editor-manual": .playlists
            case "frame", "notices", "connection", "battery", "schedule", "schedule-economy", "presentation", "presentation-photo", "orientation": .frame
            default: .now
            }
        }
    }

    /// The tab bar's selection; Teraz tapped again while open goes back to
    /// the picture on the frame.
    private var tabSelection: Binding<Screen> {
        Binding(
            get: { tab },
            set: { selected in
                if selected == .now, tab == .now { model.nowTabTapped += 1 }
                tab = selected
            }
        )
    }

    var body: some View {
        // Szukaj is the system search tab: on its own at the bottom, the
        // other tabs fold into one as its glass field opens.
        TabView(selection: tabSelection) {
            Tab("Teraz", systemImage: "photo.fill", value: Screen.now) { NowView() }
            Tab("Odkrywaj", systemImage: "square.grid.2x2", value: Screen.discover) { DiscoverView() }
            Tab("Playlisty", systemImage: "rectangle.stack", value: Screen.playlists) { PlaylistsView() }
            Tab("Ramka", systemImage: "slider.horizontal.3", value: Screen.frame) { FrameTabView() }
            Tab("Szukaj", systemImage: "magnifyingglass", value: Screen.search, role: .search) { SearchView() }
        }
        // Cards and the send bar, in a window above the app (over sheets too).
        .background { NoticeWindowInstaller(model: model) }
        // "Teraz" shows the full send bar under the picture.
        .onChange(of: tab, initial: true) { _, tab in model.notices.nowTabOpen = tab == .now }
        .onChange(of: model.artistSearch) { _, artist in
            if artist != nil { tab = .search }
        }
        .onChange(of: model.suggestionsOpened) { tab = .discover }
        // A notification tapped: where it points.
        .onChange(of: PushCenter.shared.taps, initial: true) {
            guard let route = PushCenter.shared.takeRoute() else { return }
            let parts = route.split(separator: "/", maxSplits: 1).map(String.init)
            let argument = parts.count > 1 ? parts[1] : ""
            switch parts[0] {
            case "daily":
                tab = .discover
                model.dailyOpened += 1
            case "study" where !argument.isEmpty:
                model.openStudy(itemID: argument)
            case "theme" where !argument.isEmpty:
                tab = .discover
                model.themeOpened = argument
                model.themeOpenings += 1
            case "artist" where !argument.isEmpty:
                model.artistSearch = argument  // Szukaj opens on the artist
            case "now": tab = .now
            case "frame", "server": tab = .frame
            default: break
            }
        }
        // An invitation to the frame opened from its QR code or link.
        .sheet(item: Binding(
            get: { model.invitation },
            set: { model.invitation = $0 }
        )) { invitation in
            JoinView(invitation: invitation)
        }
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
            await model.settleStudyActivities()
            await model.offerServerUpdate()  // the app was updated, the server not yet
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
            // The queue and history as they are now, for the next launch.
            if phase == .background { model.rememberNow() }
            // Back from the background, maybe on another network.
            if old == .background, phase != .background {
                Task {
                    await model.recheckServer()
                    await model.settleLiveActivity()
                    await model.settleStudyActivities()
                }
            }
        }
    }
}

#Preview {
    RootView().environment(AppModel())
}
