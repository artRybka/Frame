import SwiftUI

/// The works the owner kept: saved from the museums or Suggestions, liked,
/// shown or framed (not those the server only put in its catalogue).
struct SavedWorksView: View {
    /// Navigation value that opens this list.
    struct Route: Hashable {}

    @Environment(AppModel.self) private var model
    @State private var page: ItemPage?
    @State private var sort = "recent"

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    Text(page.map { Names.works($0.total) } ?? " ")
                        .font(.serif(17, weight: .medium))
                        .foregroundStyle(Theme.ink)
                    Spacer()
                    Picker("Sortuj", selection: $sort) {
                        Text("Ostatnio dodane").tag("recent")
                        Text("Artysta").tag("artist")
                        Text("Rok").tag("year")
                    }
                    .pickerStyle(.menu)
                }
                if let page, page.items.isEmpty {
                    EmptyStateView(
                        title: "Nic jeszcze nie zapisałeś",
                        message: "Zapisz dzieło w Odkrywaj albo dodaj serduszko, a pojawi się tutaj.",
                        systemImage: "bookmark"
                    )
                } else {
                    MasonryGrid(items: page?.items ?? []) { item in
                        NavigationLink(value: item.id) {
                            ArtCard(item: item)
                        }
                        .buttonStyle(.plain)
                        .contextMenu { QueueButton(itemID: item.id) }
                    }
                }
            }
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 32)
        }
        .background(Theme.paper)
        .navigationTitle("Zapisane dzieła")
        .navigationBarTitleDisplayMode(.inline)
        .overlay { if page == nil { ProgressView() } }
        .task(id: sort) { await load() }
        .refreshable { await load() }
    }

    private func load() async {
        var query = LibraryQuery()
        query.keptOnly = true
        query.kinds = [.artwork]
        query.sort = sort
        do {
            page = try await model.backend.items(query)
        } catch is CancellationError {
        } catch {
            model.show(error)
        }
    }
}
