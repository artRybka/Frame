import SwiftUI

/// Opens all the themes of one group ("Kierunki i style", …) as a grid.
struct ThemeGroupRoute: Hashable {
    let name: String
}

/// "Sztuki inne": manuscripts, photographs, sculpture and decorative arts,
/// kept to their own group in Odkrywaj (the server's ``OTHER_ART_THEMES``).
enum OtherArts {
    static let group = "Sztuki inne"
    static let techniques: [(key: String, name: String)] = [
        ("technique:manuscripts", "Rękopisy i miniatury"),
        ("technique:photography", "Fotografia"),
        ("technique:sculpture", "Rzeźba"),
        ("technique:decorative", "Ceramika i rzemiosło"),
    ]

    /// The technique of "Sztuki inne" a theme is of, if any.
    static func technique(of theme: ArtTheme) -> String? {
        guard theme.group == group, let terms = theme.rules?.terms else { return nil }
        return techniques.first { terms.contains($0.key) }?.key
    }
}

/// Opens the works of a suggestion row with no theme behind it ("Dawno ich nie było").
struct SuggestionRowRoute: Hashable {
    let key: String
}

/// A section's title with a chevron, tapped to see all of it.
struct SeeAllHeader: View {
    let title: String
    var size: CGFloat = 22
    var weight: Font.Weight = .semibold

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text(title)
                .font(.serif(size, weight: weight))
                .foregroundStyle(Theme.ink)
                .multilineTextAlignment(.leading)
            Image(systemName: "chevron.right")
                .font(.system(size: size * 0.72, weight: .semibold))
                .foregroundStyle(Theme.inkSoft)
        }
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityHint("Pokaż wszystkie")
    }
}

/// Every theme of a group, two cards to a row.
struct ThemeGroupView: View {
    @Environment(AppModel.self) private var model
    let name: String

    private var themes: [ArtTheme] {
        DiscoverLayout.themes(model.themes ?? [], rows: model.suggestionRows ?? [])
            .filter { ($0.group ?? "Motywy") == name }
    }

    private let columns = [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)]

    /// "Sztuki inne" in a section for each technique; other groups in one.
    private var sections: [(title: String?, themes: [ArtTheme])] {
        let found = OtherArts.techniques.compactMap { technique -> (title: String?, themes: [ArtTheme])? in
            let own = themes.filter { OtherArts.technique(of: $0) == technique.key }
            return own.isEmpty ? nil : (title: technique.name, themes: own)
        }
        let rest = themes.filter { OtherArts.technique(of: $0) == nil }
        if found.isEmpty { return [(title: nil, themes: themes)] }
        return rest.isEmpty ? found : found + [(title: nil, themes: rest)]
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                ForEach(Array(sections.enumerated()), id: \.offset) { _, section in
                    if let title = section.title {
                        Text(title)
                            .font(.caption.weight(.semibold))
                            .textCase(.uppercase)
                            .tracking(1)
                            .foregroundStyle(Theme.inkSoft)
                            .padding(.top, 8)
                            .accessibilityAddTraits(.isHeader)
                    }
                    LazyVGrid(columns: columns, alignment: .leading, spacing: 12) {
                        ForEach(section.themes) { theme in
                            NavigationLink(value: theme) {
                                ThemeCard(theme: theme) {
                                    _ = await ThemeActions.makePlaylist(theme, play: false, model: model)
                                }
                            }
                            .buttonStyle(.plain)
                            .drawWeekArtistAgainMenu(theme)
                        }
                    }
                }
            }
            .pageWidth()
            .padding(.horizontal, Theme.gutter)
            .padding(.top, 4)
            .padding(.bottom, 32)
            if themes.isEmpty {
                EmptyStateView(
                    title: "Nic tu teraz nie ma",
                    message: "Pociągnij w dół, żeby wczytać propozycje jeszcze raz.",
                    systemImage: "square.grid.2x2"
                )
                .padding(.horizontal, Theme.gutter)
            }
        }
        .paperPage()
        .navigationTitle(name)
        .refreshable { await model.refreshDiscover(force: true) }
    }
}

/// A suggestion row's works as a grid, for rows that have no theme to browse.
struct SuggestionRowGridView: View {
    @Environment(AppModel.self) private var model
    let key: String

    private var row: SuggestionRow? { model.suggestionRows?.first { $0.key == key } }

    var body: some View {
        let items = row?.items ?? []
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let subtitle = row?.subtitle, !subtitle.isEmpty {
                    Text(subtitle)
                        .font(.serif(17))
                        .foregroundStyle(Theme.inkSoft)
                }
                MasonryGrid(items: items.map(\.summary)) { summary in
                    NavigationLink(value: summary.id) {
                        ArtCard(item: summary, ref: items.first { $0.id == summary.id }?.thumb)
                    }
                    .buttonStyle(.plain)
                    .contextMenu { QueueButton(itemID: summary.id) }
                }
                if items.isEmpty {
                    EmptyStateView(
                        title: "Nic tu teraz nie ma",
                        message: "Pociągnij w dół, żeby wczytać propozycje jeszcze raz.",
                        systemImage: "sparkles"
                    )
                }
            }
            .pageWidth()
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 32)
        }
        .paperPage()
        .navigationTitle(row?.title ?? "Propozycje")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await model.refreshDiscover(force: true) }
    }
}
