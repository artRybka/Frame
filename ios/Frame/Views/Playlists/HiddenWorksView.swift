import SwiftUI

/// "Ukryte", the last card in Playlisty: the works hidden with "Ukryj
/// dzieło", the last hidden first. They are never shown on the frame, in a
/// playlist or found in a search (at the museums neither); each comes back
/// with "Przywróć dzieło", held here or in its card's ⋯ menu.
struct HiddenWorksView: View {
    @Environment(AppModel.self) private var model
    /// The first load is under way, with nothing loaded before.
    @State private var loading = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                header
                if !model.hidden.isEmpty {
                    MasonryGrid(items: model.hidden) { item in card(item) }
                } else if loading {
                    GridSkeleton(count: 4)
                } else {
                    EmptyStateView(
                        title: "Nic nie jest ukryte",
                        message: "Dzieło ukryjesz w jego karcie: menu ⋯, „Ukryj dzieło”.",
                        systemImage: "eye.slash"
                    )
                }
            }
            .pageWidth()
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 40)
        }
        .paperPage()
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await model.refreshPlaylists() }
        .task(id: model.libraryRevision) {
            loading = model.hidden.isEmpty
            await model.refreshPlaylists()
            loading = false
        }
    }

    private static let explanation =
        "Te dzieła nie pojawiają się na ramce, w playlistach, w Odkrywaj ani w wyszukiwaniu, "
        + "także w muzeach. Przytrzymaj dzieło, aby je przywrócić."

    private var header: some View {
        VStack(alignment: .leading, spacing: 14) {
            Eyebrow("Poza ramką", color: Theme.vermilion)
            Text("Ukryte")
                .font(.serif(32, weight: .semibold))
                .foregroundStyle(Theme.ink)
            Text(Self.explanation)
                .font(.serif(17))
                .foregroundStyle(Theme.inkSoft)
            if !model.hidden.isEmpty {
                Text(Names.works(model.hidden.count))
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(Theme.inkSoft)
            }
        }
    }

    private func card(_ item: ItemSummary) -> some View {
        NavigationLink(value: item.id) { ArtCard(item: item) }
            .buttonStyle(.plain)
            .contextMenu {
                Button("Przywróć dzieło", systemImage: "eye") {
                    Task { _ = await model.setExcluded(item.id, false) }
                }
            }
    }
}
