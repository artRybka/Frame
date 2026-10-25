import SwiftUI

/// Ideas for playlists and works the server picked (Propozycje), and one
/// search over the catalogue and the museums (Muzea).
struct DiscoverView: View {
    @State private var scope = Scope.initial
    @State private var path = NavigationPath()

    enum Scope: String, CaseIterable {
        case suggestions = "Propozycje"
        case museums = "Muzea"

        /// Suggestions, unless CI screenshots ask for another screen.
        static var initial: Scope {
            LaunchRoute.screen == "museums" ? .museums : .suggestions
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
                .padding(.bottom, 32)
            }
            .scrollDismissesKeyboard(.interactively)
            .background(Theme.paper)
            .navigationTitle("Odkrywaj")
            .navigationDestination(for: String.self) { id in
                ItemDetailView(itemID: id)
            }
            .navigationDestination(for: ArtTheme.self) { theme in
                ThemeView(theme: theme)
            }
        }
    }
}

/// Colour and mood dots.
struct ColorFilterRow: View {
    @Binding var selected: [String]
    let available: [String]

    private var tags: [String] {
        let order = ColorTag.families + ColorTag.moods
        let present = Set(available)
        let shown = order.filter { present.contains($0) }
        return shown.isEmpty ? ColorTag.families : shown
    }

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(tags, id: \.self) { tag in
                    Chip(
                        title: ColorTag.name(tag),
                        swatch: ColorTag.color(tag),
                        selected: selected.contains(tag)
                    ) {
                        if selected.contains(tag) {
                            selected.removeAll { $0 == tag }
                        } else {
                            selected.append(tag)
                        }
                    }
                }
            }
            .padding(.vertical, 2)
        }
        .scrollClipDisabled()
    }
}
