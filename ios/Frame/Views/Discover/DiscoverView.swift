import SwiftUI

/// Ideas for playlists and works the server picked (Propozycje), and one
/// search over the catalogue and the museums (Szukaj).
struct DiscoverView: View {
    @Environment(AppModel.self) private var model
    @State private var scope = Scope.initial
    @State private var path = NavigationPath()

    /// The scrolled content's coordinate space, and the room under it.
    static let content = "discover.content"
    static let bottomPadding: CGFloat = 32

    enum Scope: String, CaseIterable {
        case suggestions = "Propozycje"
        case museums = "Szukaj"

        /// Suggestions, unless CI screenshots ask for another screen.
        static var initial: Scope {
            ["museums", "search", "search-picker"].contains(LaunchRoute.screen) ? .museums : .suggestions
        }
    }

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Picker("Zakres", selection: $scope) {
                        ForEach(Scope.allCases, id: \.self) { Text($0.rawValue).tag($0) }
                    }
                    .pickerStyle(.segmented)

                    switch scope {
                    case .suggestions: SuggestionsView(path: $path)
                    case .museums: MuseumSearchView()
                    }
                }
                .padding(.horizontal, Theme.gutter)
                .padding(.bottom, Self.bottomPadding)
                .coordinateSpace(.named(Self.content))
            }
            .scrollDismissesKeyboard(.interactively)
            .refreshable {
                if scope == .suggestions { await model.refreshDiscover(force: true) }
            }
            .background(Theme.paper)
            .navigationTitle("Odkrywaj")
            .navigationDestination(for: String.self) { id in
                ItemDetailView(itemID: id)
            }
            .navigationDestination(for: ArtTheme.self) { theme in
                ThemeView(theme: theme)
            }
        }
        // A tapped artist's name: back to the top, on the search.
        .onChange(of: model.artistSearch, initial: true) { _, artist in
            guard artist != nil else { return }
            scope = .museums
            path = NavigationPath()
        }
    }
}
