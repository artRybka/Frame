import SwiftUI

/// Ideas for playlists and works the server picked (Propozycje); the
/// search has its own tab.
struct DiscoverView: View {
    @Environment(AppModel.self) private var model
    @State private var path = NavigationPath()

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                SuggestionsView(path: $path)
                    .padding(.horizontal, Theme.gutter)
                    .padding(.top, 8)
                    .padding(.bottom, 32)
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
        }
        .onChange(of: model.suggestionsOpened) { path = NavigationPath() }
    }
}
