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
                // No "Szukaj" over it, neither big at the top nor in the
                // bar when scrolled (Mateusz 2026-11-19: "konsekwentnie nie
                // dajemy go zatem nigdzie", "Także go usuwamy"): the tab
                // says where one is.
                .navigationBarTitleDisplayMode(.inline)
                .serverLinkBadge()
                .navigationDestination(for: String.self) { id in
                    ItemDetailView(itemID: id)
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
