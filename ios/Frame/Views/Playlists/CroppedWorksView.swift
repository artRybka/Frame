import SwiftUI

/// Opens "Kadrowane" within Playlisty.
struct CroppedRoute: Hashable {}

/// "Kadrowane" (the owner's; Mateusz 2026-11-20: „album »kadrowane« gdzie
/// trafiałyby dzieła kadrowane przez model (i te które model nie wiedział
/// jak zrobić), ja mógłbym je korygować ręcznie”): the museum works the
/// phone's model cut, and those it was unsure of and left whole. A work
/// leaves the list once he corrects it in its card ("Popraw kadr", or
/// "Przywróć zdjęcie muzeum") or, held, says its cut is right ("Dobrze").
/// Both are what the model is taught again from (`/api/crops/lessons`).
struct CroppedWorksView: View {
    @Environment(AppModel.self) private var model
    @State private var loading = false

    private var review: CropReview { model.cropReview ?? CropReview(cut: [], unsure: []) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                header
                if !review.cut.isEmpty {
                    part(
                        "Wykadrowane przez model",
                        about: "Przytrzymaj dzieło i wybierz „Dobrze”, jeśli kadr jest dobry. Jeśli nie, popraw go w karcie dzieła.",
                        review.cut, fine: true
                    )
                }
                if !review.unsure.isEmpty {
                    part(
                        "Do wykadrowania",
                        about: "Model nie był pewny albo dzieło jest sfotografowane pod kątem. Wykadruj je w karcie dzieła: „Popraw kadr”.",
                        review.unsure, fine: false
                    )
                }
                if review.isEmpty {
                    if loading {
                        GridSkeleton(count: 4)
                    } else {
                        EmptyStateView(
                            title: "Nic nie czeka",
                            message: "Tu trafiają dzieła wykadrowane przez model na iPhonie i te, których nie był pewny.",
                            systemImage: "crop"
                        )
                    }
                }
            }
            .pageWidth()
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 40)
        }
        .paperPage()
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await model.refreshCropReview() }
        .task(id: model.libraryRevision) {
            loading = model.cropReview == nil
            await model.refreshCropReview()
            loading = false
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 14) {
            Eyebrow("Model na iPhonie", color: Theme.vermilion)
            Text("Kadrowane")
                .font(.serif(32, weight: .semibold))
                .foregroundStyle(Theme.ink)
            Text(bound: "Zdjęcia z muzeów, które model przyciął do samego dzieła, i te, które zostawił Tobie. Twoje poprawki posłużą do jego dalszej nauki.")
                .font(.serif(17))
                .foregroundStyle(Theme.inkSoft)
        }
    }

    private func part(_ title: String, about: String, _ items: [ItemSummary], fine: Bool) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                Text(bound: title)
                    .font(.serif(22, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                Spacer(minLength: 8)
                Text(bound: Names.works(items.count))
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(Theme.inkSoft)
            }
            Text(bound: about)
                .font(.subheadline)
                .foregroundStyle(Theme.inkSoft)
            MasonryGrid(items: items) { item in card(item, fine: fine) }
        }
    }

    private func card(_ item: ItemSummary, fine: Bool) -> some View {
        NavigationLink(value: item.id) { ArtCard(item: item, showsFavorite: false) }
            .buttonStyle(.plain)
            .contextMenu {
                if fine {
                    Button("Dobrze", systemImage: "checkmark") {
                        Task { await keep(item) }
                    }
                }
            }
    }

    private func keep(_ item: ItemSummary) async {
        do {
            model.cropReview = try await model.backend.cropFine(itemID: item.id)
        } catch {
            model.show(error)
        }
    }
}

/// "Kadrowane" among the playlists: the works waiting there.
struct CroppedCard: View {
    let review: CropReview

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            FrostedCover(itemIDs: (review.cut + review.unsure).prefix(4).map(\.id))
                .aspectRatio(1, contentMode: .fit)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(alignment: .bottomTrailing) {
                    GlassBadge(systemImage: "crop")
                        .padding(9)
                }
                .shadow(color: .black.opacity(0.12), radius: 10, y: 6)
            CardCaption {
                Text("Kadrowane")
                    .font(.serif(16, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                Text(bound: "\(review.cut.count) wykadrowane · \(review.unsure.count) do wykadrowania")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityHint("Otwiera dzieła wykadrowane przez model i te do ręcznego kadrowania")
    }
}
