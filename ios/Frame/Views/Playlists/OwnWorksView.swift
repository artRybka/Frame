import SwiftUI

struct OwnWorksRoute: Hashable {}

/// "Moje dzieła" in Playlisty, before "Ukryte": the works he added from
/// his own photographs (Mateusz 2026-11-15), shown once there is one.
struct OwnWorksCard: View {
    let items: [ItemSummary]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Collage(itemIDs: items.prefix(4).map(\.id), title: "Moje dzieła")
                .aspectRatio(1, contentMode: .fit)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(alignment: .bottomTrailing) {
                    GlassBadge(systemImage: "house")
                        .padding(9)
                }
                .shadow(color: .black.opacity(0.12), radius: 10, y: 6)
            CardCaption {
                Text("Moje dzieła")
                    .font(.serif(16, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                Text(bound: Names.works(items.count))
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityHint("Otwiera dzieła dodane z Twoich zdjęć")
    }
}

/// His own works, the last added first, and "Dodaj własne dzieło".
struct OwnWorksView: View {
    @Environment(AppModel.self) private var model
    let add: () -> Void
    @State private var loading = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                header
                if !model.ownWorks.isEmpty {
                    MasonryGrid(items: model.ownWorks) { item in
                        NavigationLink(value: item.id) { ArtCard(item: item) }
                            .buttonStyle(.plain)
                    }
                } else if loading {
                    GridSkeleton(count: 4)
                } else {
                    EmptyStateView(
                        title: "Jeszcze nic",
                        message: "Sfotografuj obraz, który masz w domu: „+” w Playlistach → „Dodaj własne dzieło”.",
                        systemImage: "house"
                    )
                }
            }
            .pageWidth()
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 40)
        }
        .paperPage()
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if model.isOwner {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(action: add) { Image(systemName: "camera") }
                        .accessibilityLabel("Dodaj własne dzieło")
                }
            }
        }
        .refreshable { await model.refreshOwnWorks() }
        .task(id: model.libraryRevision) {
            loading = model.ownWorks.isEmpty
            await model.refreshOwnWorks()
            loading = false
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 14) {
            Eyebrow("Moja kolekcja", color: Theme.vermilion)
            Text("Moje dzieła")
                .font(.serif(32, weight: .semibold))
                .foregroundStyle(Theme.ink)
            Text(bound: "Dzieła z Twoich zdjęć: na ramce, w playlistach, w Szukaj i w studiach jak każde inne.")
                .font(.serif(17))
                .foregroundStyle(Theme.inkSoft)
            if !model.ownWorks.isEmpty {
                Text(bound: Names.works(model.ownWorks.count))
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(Theme.inkSoft)
            }
        }
    }
}
