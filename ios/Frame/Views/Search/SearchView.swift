import SwiftUI

/// The Szukaj tab, the system search tab: one search over the catalogue and
/// the museums, its glass field at the bottom.
struct SearchView: View {
    @Environment(AppModel.self) private var model
    @State private var path = NavigationPath()

    /// The scrolled content's coordinate space, and the room under it.
    static let content = "search.content"
    static let bottomPadding: CGFloat = 32

    var body: some View {
        NavigationStack(path: $path) {
            MuseumSearchView(path: $path)
                .navigationTitle("Szukaj")
                .serverLinkBadge()
                .navigationDestination(for: String.self) { id in
                    ItemDetailView(itemID: id)
                }
                // "Podobne wyglądem" → "Więcej" on a work's card, in the same path.
                .navigationDestination(for: LooksAsk.self) { ask in
                    LooksResultsView(ask: ask)
                }
                .navigationDestination(for: DailyRoute.self) { route in
                    DailyView(route: route)
                }
        }
        .opensStudies(on: $path)
        // A held artist's name: back to the top, on the search.
        .onChange(of: model.artistSearch, initial: true) { _, artist in
            if artist != nil { path = NavigationPath() }
        }
        .onChange(of: model.placeSearch, initial: true) { _, place in
            if place != nil { path = NavigationPath() }
        }
        .onChange(of: model.likeSearch, initial: true) { _, like in
            if like != nil { path = NavigationPath() }
        }
    }
}
