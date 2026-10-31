import SwiftUI

/// Ideas for playlists and works the server picked (Propozycje); the
/// search has its own tab.
struct DiscoverView: View {
    @Environment(AppModel.self) private var model
    @State private var path = NavigationPath()
    @State private var dailyShown = 0
    @State private var themeShown = 0
    /// How far the page is scrolled, for the glow of the study of the day.
    @State private var scrolled: CGFloat = 0

    var body: some View {
        NavigationStack(path: $path) {
            ScrollViewReader { proxy in
                ScrollView {
                    SuggestionsView(path: $path)
                        .pageWidth()
                        .padding(.horizontal, Theme.gutter)
                        .padding(.top, 8)
                        .padding(.bottom, 32)
                }
                // Clamped, so scrolling further down the page redraws nothing.
                .onScrollGeometryChange(for: CGFloat.self) { geometry in
                    min(max(geometry.contentOffset.y + geometry.contentInsets.top, 0), PageGlow.height)
                } action: { _, offset in
                    scrolled = offset
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
            // The colours of the study of the day glow behind its card, as in "Teraz".
            .paperPage(glow: model.daily?.item.item.colors ?? [], lift: scrolled)
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
        .opensStudies(on: $path)
        .onChange(of: model.suggestionsOpened) { path = NavigationPath() }
        // The artist of the week from a notification: its theme, loaded if need be.
        .onChange(of: model.themeOpenings, initial: true) { _, count in
            guard count > themeShown, let key = model.themeOpened else { return }
            themeShown = count
            Task {
                if model.themes?.contains(where: { $0.key == key }) != true {
                    await model.refreshDiscover(force: true)
                }
                guard let theme = model.themes?.first(where: { $0.key == key }) else { return }
                path = NavigationPath()
                path.append(theme)
            }
        }
        // A notification of the work of the day tapped (also before this tab was first opened).
        .onChange(of: model.dailyOpened, initial: true) { _, count in
            guard count > dailyShown else { return }
            dailyShown = count
            path = NavigationPath()
            path.append(DailyRoute(day: nil))
        }
    }
}
