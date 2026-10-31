import SwiftUI

/// Ideas for playlists and works the server picked (Propozycje); the
/// search has its own tab.
struct DiscoverView: View {
    @Environment(AppModel.self) private var model
    @State private var path = NavigationPath()
    @State private var dailyShown = 0

    var body: some View {
        NavigationStack(path: $path) {
            ScrollViewReader { proxy in
                ScrollView {
                    SuggestionsView(path: $path)
                        .padding(.horizontal, Theme.gutter)
                        .padding(.top, 8)
                        .padding(.bottom, 32)
                }
                .onChange(of: model.studyList?.count) {
                    guard LaunchRoute.screen == "discover", LaunchRoute.scroll == "studies" else { return }  // CI screenshots
                    Task {
                        try? await Task.sleep(for: .seconds(1))
                        proxy.scrollTo("studies", anchor: .top)
                    }
                }
            }
            .refreshable { await model.refreshDiscover(force: true) }
            .background(Theme.paper)
            .navigationTitle("Odkrywaj")
            .navigationDestination(for: String.self) { id in
                ItemDetailView(itemID: id)
            }
            .navigationDestination(for: ArtTheme.self) { theme in
                ThemeView(theme: theme)
            }
            .navigationDestination(for: ThemeGroupRoute.self) { route in
                ThemeGroupView(name: route.name)
            }
            .navigationDestination(for: SuggestionRowRoute.self) { route in
                SuggestionRowGridView(key: route.key)
            }
            .navigationDestination(for: DailyRoute.self) { route in
                DailyView(route: route)
            }
            .navigationDestination(for: StudiesRoute.self) { _ in
                StudiesGridView()
            }
        }
        .onChange(of: model.suggestionsOpened) { path = NavigationPath() }
        // A notification of the work of the day tapped (also before this tab was first opened).
        .onChange(of: model.dailyOpened, initial: true) { _, count in
            guard count > dailyShown else { return }
            dailyShown = count
            path = NavigationPath()
            path.append(DailyRoute(day: nil))
        }
    }
}
