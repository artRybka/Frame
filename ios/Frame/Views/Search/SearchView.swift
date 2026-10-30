import SwiftUI

/// The Szukaj tab: one search over the catalogue and the museums.
struct SearchView: View {
    @Environment(AppModel.self) private var model
    @State private var path = NavigationPath()

    /// The scrolled content's coordinate space, and the room under it.
    static let content = "search.content"
    static let bottomPadding: CGFloat = 32

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                MuseumSearchView()
                    .padding(.horizontal, Theme.gutter)
                    .padding(.bottom, Self.bottomPadding)
                    .coordinateSpace(.named(Self.content))
            }
            .scrollDismissesKeyboard(.interactively)
            .background(Theme.paper)
            .navigationTitle("Szukaj")
            .navigationDestination(for: String.self) { id in
                ItemDetailView(itemID: id)
            }
        }
        // A tapped artist's name: back to the top, on the search.
        .onChange(of: model.artistSearch, initial: true) { _, artist in
            if artist != nil { path = NavigationPath() }
        }
    }
}
