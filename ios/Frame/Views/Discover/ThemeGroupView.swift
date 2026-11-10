import SwiftUI

/// Opens all the themes of one group ("Kierunki i style", …) as a grid.
struct ThemeGroupRoute: Hashable {
    let name: String
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

    /// The group's parts in the server's order ("Epoki": antiquity first);
    /// one part without a name for groups that have none.
    private var sections: [ThemeSection] {
        var found: [ThemeSection] = []
        for theme in themes {
            let name = theme.section ?? ""
            if let at = found.firstIndex(where: { $0.name == name }) {
                found[at].themes.append(theme)
            } else {
                found.append(ThemeSection(name: name, years: theme.sectionYears ?? "", themes: [theme]))
            }
        }
        return found
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 12) {
                ForEach(sections) { section in
                    if !section.name.isEmpty {
                        HStack(alignment: .firstTextBaseline) {
                            Text(section.name.uppercased())
                                .font(.caption.weight(.semibold))
                                .tracking(1.1)
                            Spacer()
                            Text(section.years)
                                .font(.footnote)
                        }
                        .foregroundStyle(Theme.inkSoft)
                        .padding(.top, section.id == sections.first?.id ? 0 : 12)
                        .accessibilityElement(children: .combine)
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

/// A part of a group's page: its name, years and cards.
private struct ThemeSection: Identifiable {
    let name: String
    let years: String
    var themes: [ArtTheme]
    var id: String { name }
}

/// A suggestion row's works as a grid, for rows that have no theme to browse.
struct SuggestionRowGridView: View {
    @Environment(AppModel.self) private var model
    let key: String

    private var row: SuggestionRow? { model.suggestionRows?.first { $0.key == key } }
    private var zoom: Bool { key == DiscoverLayout.zoom }
    private var subtitle: String? { zoom ? ZoomRow.subtitle : row?.subtitle }
    private let columns = [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)]

    var body: some View {
        let items = row?.items ?? []
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let subtitle, !subtitle.isEmpty {
                    Text(subtitle)
                        .font(.serif(17))
                        .foregroundStyle(Theme.inkSoft)
                }
                if zoom {
                    // "Pod lupą": cards like the studies', two to a row.
                    LazyVGrid(columns: columns, alignment: .leading, spacing: 12) {
                        ForEach(items) { ZoomWorkCard(remote: $0) }
                    }
                } else {
                    MasonryGrid(items: items.map(\.summary)) { summary in
                        NavigationLink(value: summary.id) {
                            ArtCard(item: summary, ref: items.first { $0.id == summary.id }?.thumb, showsFavorite: false)
                        }
                        .buttonStyle(.plain)
                        .contextMenu { QueueButton(itemID: summary.id) }
                        .overlay(alignment: .topTrailing) { LikeHeart(item: summary) }
                    }
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
