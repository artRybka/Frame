import SwiftUI

/// Suggestions and themes, the catalogue the server grows from museum
/// collections (filters by artist, style, subject, colour), or a search of
/// the museums themselves.
struct DiscoverView: View {
    @Environment(AppModel.self) private var model
    @State private var scope = Scope.initial
    @State private var query = LibraryQuery()
    @State private var page: ItemPage?
    @State private var loading = false
    @State private var facetSheet: FacetKind?
    @State private var path = NavigationPath()

    enum Scope: String, CaseIterable {
        case suggestions = "Propozycje"
        case library = "Katalog"
        case museums = "Muzea"

        /// Suggestions, unless CI screenshots ask for another screen.
        static var initial: Scope {
            switch LaunchRoute.screen {
            case "museums": .museums
            case "detail": .library
            default: .suggestions
            }
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
                    case .suggestions: SuggestionsView()
                    case .library:
                        filters
                        results
                    case .museums: MuseumSearchView()
                    }
                }
                .padding(.horizontal, Theme.gutter)
                .padding(.bottom, 32)
            }
            .background(Theme.paper)
            .navigationTitle("Odkrywaj")
            .searchable(text: $query.text, prompt: "Szukaj w katalogu: tytuł, artysta, temat")
            .navigationDestination(for: String.self) { id in
                ItemDetailView(itemID: id)
            }
            .navigationDestination(for: ArtTheme.self) { theme in
                ThemeView(theme: theme)
            }
            .sheet(item: $facetSheet) { kind in
                FacetPicker(kind: kind, query: $query)
                    .presentationDetents([.medium, .large])
            }
            .task(id: query) { if scope == .library { await load() } }
            .onChange(of: scope) { _, scope in
                if scope == .library, page == nil { Task { await load() } }
            }
            .onChange(of: query.text) { _, text in
                if !text.isEmpty, scope == .suggestions { scope = .library }  // search the catalogue
            }
            .refreshable {
                await model.refreshFacets()
                await load()
            }
            .onAppear {
                if LaunchRoute.screen == "detail", path.isEmpty, let first = page?.items.first {
                    path.append(first.id)
                }
            }
            .onChange(of: page?.items.first?.id) { _, first in
                if LaunchRoute.screen == "detail", path.isEmpty, let first { path.append(first) }
            }
        }
    }

    // MARK: Filters

    private var filters: some View {
        VStack(alignment: .leading, spacing: 12) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    Chip(title: "Ulubione", systemImage: "heart", selected: query.favoritesOnly) {
                        query.favoritesOnly.toggle()
                    }
                    Chip(title: "Moje", systemImage: "bookmark", selected: query.keptOnly) {
                        query.keptOnly.toggle()
                    }
                    ForEach(FacetKind.allCases) { kind in
                        let count = kind.selected(in: query).count
                        Chip(
                            title: count > 0 ? "\(kind.title) · \(count)" : kind.title,
                            systemImage: kind.icon,
                            selected: count > 0
                        ) { facetSheet = kind }
                    }
                    Menu {
                        Picker("Sortuj", selection: $query.sort) {
                            Text("Artysta").tag("artist")
                            Text("Tytuł").tag("title")
                            Text("Rok").tag("year")
                            Text("Ostatnio dodane").tag("recent")
                            Text("Najlepsze na e-papier").tag("suitability")
                        }
                    } label: {
                        Image(systemName: "arrow.up.arrow.down")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(Theme.ink)
                            .padding(9)
                            .background(Theme.card, in: Circle())
                            .overlay(Circle().strokeBorder(Theme.hairline))
                    }
                }
                .padding(.vertical, 2)
            }
            .scrollClipDisabled()

            ColorFilterRow(selected: $query.colors, available: model.facets.colors.map(\.value))
        }
    }

    private var results: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text(page.map { Names.works($0.total) } ?? " ")
                    .font(.serif(17, weight: .medium))
                    .foregroundStyle(Theme.ink)
                Spacer()
                if query.activeFilterCount > 0 {
                    Button("Wyczyść filtry") {
                        let text = query.text
                        query = LibraryQuery()
                        query.text = text
                    }
                    .font(.subheadline.weight(.semibold))
                }
            }
            if let page, page.items.isEmpty, !loading {
                EmptyStateView(
                    title: "Nic tu nie ma",
                    message: "Katalog rośnie sam w tle. Zmień filtry albo poszukaj w muzeach.",
                    systemImage: "magnifyingglass"
                )
            } else {
                MasonryGrid(items: page?.items ?? []) { item in
                    NavigationLink(value: item.id) {
                        ArtCard(item: item)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .overlay(alignment: .top) {
            if loading && page == nil { ProgressView().padding(.top, 60) }
        }
    }

    private func load() async {
        loading = true
        defer { loading = false }
        if model.facets.artists.isEmpty { await model.refreshFacets() }
        do {
            try await Task.sleep(for: .milliseconds(180))  // debounce typing
            page = try await model.backend.items(query)
        } catch is CancellationError {
        } catch {
            model.show(error)
        }
    }
}

/// Which facet a picker edits.
enum FacetKind: String, CaseIterable, Identifiable {
    case artists, styles, subjects

    var id: String { rawValue }

    var title: String {
        switch self {
        case .artists: "Artyści"
        case .styles: "Style"
        case .subjects: "Tematy"
        }
    }

    var icon: String {
        switch self {
        case .artists: "person"
        case .styles: "paintpalette"
        case .subjects: "tag"
        }
    }

    func values(in facets: Facets) -> [FacetValue] {
        switch self {
        case .artists: facets.artists
        case .styles: facets.styles
        case .subjects: facets.subjects
        }
    }

    func selected(in query: LibraryQuery) -> [String] {
        switch self {
        case .artists: query.artists
        case .styles: query.styles
        case .subjects: query.subjects
        }
    }

    func binding(_ query: Binding<LibraryQuery>) -> Binding<[String]> {
        switch self {
        case .artists: query.artists
        case .styles: query.styles
        case .subjects: query.subjects
        }
    }
}

/// Searchable multi-select list of facet values with counts.
struct FacetPicker: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let kind: FacetKind
    @Binding var query: LibraryQuery
    @State private var search = ""

    var body: some View {
        let selection = kind.binding($query)
        NavigationStack {
            List {
                ForEach(filtered) { facet in
                    let isOn = selection.wrappedValue.contains(facet.value)
                    Button {
                        if isOn {
                            selection.wrappedValue.removeAll { $0 == facet.value }
                        } else {
                            selection.wrappedValue.append(facet.value)
                        }
                    } label: {
                        HStack {
                            Text(facet.value)
                                .font(kind == .artists ? .serif(17) : .body)
                                .foregroundStyle(Theme.ink)
                            Spacer()
                            Text("\(facet.count)")
                                .font(.footnote.monospacedDigit())
                                .foregroundStyle(Theme.inkSoft)
                            Image(systemName: isOn ? "checkmark.circle.fill" : "circle")
                                .foregroundStyle(isOn ? Theme.accent : Theme.hairline)
                                .font(.title3)
                        }
                    }
                }
            }
            .listStyle(.plain)
            .searchable(text: $search, placement: .navigationBarDrawer(displayMode: .always))
            .navigationTitle(kind.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Gotowe") { dismiss() }
                }
                ToolbarItem(placement: .cancellationAction) {
                    Button("Wyczyść") { selection.wrappedValue = [] }
                        .disabled(selection.wrappedValue.isEmpty)
                }
            }
        }
    }

    private var filtered: [FacetValue] {
        let values = kind.values(in: model.facets)
        guard !search.isEmpty else { return values }
        return values.filter { $0.value.localizedCaseInsensitiveContains(search) }
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
