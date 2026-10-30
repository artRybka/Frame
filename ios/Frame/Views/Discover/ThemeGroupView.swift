import SwiftUI

/// Opens all the themes of one group ("Kierunki i style", …) as a grid.
struct ThemeGroupRoute: Hashable {
    let name: String
}

/// Opens the works of a suggestion row with no theme behind it ("Dla Ciebie").
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
        (model.themes ?? []).filter { ($0.group ?? "Motywy") == name }
    }

    private let columns = [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)]

    var body: some View {
        ScrollView {
            LazyVGrid(columns: columns, alignment: .leading, spacing: 12) {
                ForEach(themes) { theme in
                    NavigationLink(value: theme) {
                        ThemeCard(theme: theme) {
                            _ = await ThemeActions.makePlaylist(theme, play: false, model: model)
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
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
        .background(Theme.paper)
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
                MasonryGrid(items: items.map(\.item.summary)) { summary in
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
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 32)
        }
        .background(Theme.paper)
        .navigationTitle(row?.title ?? "Propozycje")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await model.refreshDiscover(force: true) }
    }
}
