import SwiftUI

/// Search public-domain collections and add works to the library.
struct MuseumSearchView: View {
    @Environment(AppModel.self) private var model
    @State private var museums: [Museum] = []
    @State private var source = "aic"
    @State private var text = ""
    @State private var results: [RemoteItem] = []
    @State private var total = 0
    @State private var searching = false
    @State private var adding: Set<String> = []
    @State private var page = 1
    @State private var loadingMore = false
    /// Set while "Dodaj wszystkie" runs; nil inside until the server counts.
    @State private var bulk: JobStatus?? = nil

    private let suggestions = [
        "Hokusai", "Hiroshige", "Monet", "Van Gogh", "Mucha", "Kwiaty", "Morze", "Plakat",
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(museums) { museum in
                        Chip(title: museum.name, systemImage: "building.columns", selected: source == museum.key) {
                            source = museum.key
                        }
                    }
                }
                .padding(.vertical, 2)
            }
            .scrollClipDisabled()

            HStack(spacing: 10) {
                Image(systemName: "magnifyingglass").foregroundStyle(Theme.inkSoft)
                TextField("Szukaj w \(Names.source(source))", text: $text)
                    .submitLabel(.search)
                    .onSubmit { Task { await search() } }
                if searching { ProgressView() }
            }
            .padding(14)
            .background(Theme.card, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Theme.hairline))

            if results.isEmpty && !searching {
                VStack(alignment: .leading, spacing: 10) {
                    Eyebrow("Podpowiedzi")
                    FlowLayout(spacing: 8) {
                        ForEach(suggestions, id: \.self) { word in
                            Chip(title: word) {
                                text = word
                                Task { await search() }
                            }
                        }
                    }
                }
                Toggle(isOn: privateUse) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Użytek prywatny")
                        Text(
                            privateUse.wrappedValue
                                ? "Z Wikimedia Commons także dzieła na wolnych licencjach (np. CC BY-SA), z podanym autorem. Muzea nadal dają tylko domenę publiczną."
                                : "Tylko dzieła w domenie publicznej (CC0). Opisy w oryginale, po angielsku."
                        )
                        .font(.footnote)
                        .foregroundStyle(Theme.inkSoft)
                    }
                }
                .disabled(model.settings == nil)
                LibraryPacksSection()
            } else {
                HStack {
                    Text("\(total) wyników")
                        .font(.serif(17, weight: .medium))
                    Spacer()
                    addAllMenu
                }
                MasonryGrid(items: results.map(\.item.summary)) { summary in
                    let remote = results.first { $0.id == summary.id }
                    VStack(alignment: .leading, spacing: 8) {
                        ArtImage(
                            ref: URL(string: remote?.item.thumbUrl ?? "").map(ImageRef.url) ?? .thumb(summary.id),
                            placeholder: Theme.mat,
                            maxPixel: 700
                        )
                        .aspectRatio(max(0.45, min(summary.aspectRatio, 2.2)), contentMode: .fit)
                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                        Text(summary.title)
                            .font(.serif(15, weight: .medium))
                            .lineLimit(2)
                        Text(summary.artist).font(.caption).foregroundStyle(Theme.inkSoft).lineLimit(1)
                        addButton(remote)
                    }
                }
                if results.count < total {
                    Button {
                        Task { await loadMore() }
                    } label: {
                        HStack(spacing: 8) {
                            if loadingMore { ProgressView().controlSize(.small) }
                            Text("Więcej wyników")
                        }
                        .font(.subheadline.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(Theme.card, in: RoundedRectangle(cornerRadius: 12))
                        .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Theme.hairline))
                    }
                    .disabled(loadingMore)
                }
            }
        }
        .task {
            if museums.isEmpty { museums = (try? await model.backend.museums()) ?? [] }
            if LaunchRoute.screen == "museums", results.isEmpty {
                text = "Hiroshige"
                await search()
            }
        }
        .onChange(of: source) { _, _ in
            if !text.isEmpty { Task { await search() } }
        }
    }

    /// Saved with the frame settings, so imports on the server follow it.
    private var privateUse: Binding<Bool> {
        Binding(
            get: { model.settings?.privateUse ?? false },
            set: { value in
                guard var settings = model.settings else { return }
                settings.privateUse = value
                Task { await model.saveSettings(settings) }
            }
        )
    }

    /// Adds many results at once, in the background on the server.
    @ViewBuilder
    private var addAllMenu: some View {
        if let job = bulk {
            HStack(spacing: 6) {
                ProgressView().controlSize(.mini)
                Text(jobProgress(job))
            }
            .font(.caption.weight(.semibold))
            .foregroundStyle(Theme.accent)
        } else {
            Menu {
                ForEach(Set([24, 100, 250].filter { $0 < total } + [min(total, 500)]).sorted(), id: \.self) { limit in
                    Button(limit == total ? "Wszystkie (\(limit))" : "Pierwsze \(limit)") {
                        Task { await addAll(limit: limit) }
                    }
                }
            } label: {
                Label("Dodaj wiele", systemImage: "plus.square.on.square")
                    .font(.caption.weight(.semibold))
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(Theme.accent.opacity(0.12), in: Capsule())
            }
        }
    }

    @ViewBuilder
    private func addButton(_ remote: RemoteItem?) -> some View {
        if let remote {
            if remote.inLibrary {
                Label("W bibliotece", systemImage: "checkmark")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Theme.good)
            } else {
                Button {
                    Task { await add(remote) }
                } label: {
                    HStack(spacing: 6) {
                        if adding.contains(remote.id) {
                            ProgressView().controlSize(.mini)
                        } else {
                            Image(systemName: "plus")
                        }
                        Text("Dodaj")
                    }
                    .font(.caption.weight(.semibold))
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(Theme.accent.opacity(0.12), in: Capsule())
                }
                .disabled(adding.contains(remote.id))
            }
        }
    }

    private func search() async {
        guard !text.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        searching = true
        defer { searching = false }
        do {
            let found = try await model.backend.searchMuseum(source: source, query: text, page: 1)
            results = found.items
            total = found.total
            page = 1
        } catch {
            model.show(error)
        }
    }

    private func loadMore() async {
        loadingMore = true
        defer { loadingMore = false }
        do {
            let found = try await model.backend.searchMuseum(source: source, query: text, page: page + 1)
            let known = Set(results.map(\.id))
            results += found.items.filter { !known.contains($0.id) }
            page += 1
            // Some sources only learn the total as they go; stop when a page is empty.
            total = found.items.isEmpty ? results.count : max(found.total, results.count)
        } catch {
            model.show(error)
        }
    }

    private func addAll(limit: Int) async {
        bulk = .some(nil)
        defer { bulk = nil }
        do {
            let id = try await model.backend.importSearch(source: source, query: text, limit: limit)
            let job = try await watchJob(id, backend: model.backend) { bulk = $0 }
            let added = Set(job.itemIds)
            for index in results.indices where added.contains(results[index].id) {
                results[index].inLibrary = true
            }
            model.toast = "W bibliotece: \(job.done) dzieł" + (job.failed > 0 ? ", nie udało się \(job.failed)" : "")
            await model.refreshFacets()
        } catch {
            model.show(error)
        }
    }

    private func add(_ remote: RemoteItem) async {
        adding.insert(remote.id)
        defer { adding.remove(remote.id) }
        do {
            _ = try await model.backend.importArtwork(source: remote.item.source, sourceID: remote.item.sourceId)
            if let index = results.firstIndex(where: { $0.id == remote.id }) {
                results[index].inLibrary = true
            }
            model.toast = "Dodano do biblioteki"
            await model.refreshFacets()
        } catch {
            model.show(error)
        }
    }
}

/// Wrapping row of chips.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if x > 0 && x + size.width > width {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return CGSize(width: width.isFinite ? width : x, height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX
        var y = bounds.minY
        var rowHeight: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if x > bounds.minX && x + size.width > bounds.maxX {
                x = bounds.minX
                y += rowHeight + spacing
                rowHeight = 0
            }
            view.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}
