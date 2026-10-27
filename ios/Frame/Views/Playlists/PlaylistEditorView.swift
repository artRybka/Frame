import PhotosUI
import SwiftUI

/// Create or edit a playlist. Smart playlists are built like Discover's
/// search: the field at once (museums, colours, styles, subjects and periods
/// under "+"), the icon's squares at play until something is asked, then
/// what the catalogue and the museums have for it as Szukaj shows it (with
/// fetching on, the museums' works first: they are what it brings).
/// Manual ones can take photos from the camera roll, uploaded to the library
/// when the playlist is saved, and works found with the same search, each
/// added with its "+"; album playlists mirror a shared iCloud album.
struct PlaylistEditorView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var playlist: Playlist
    @State private var preview: RulesPreview?
    /// What a manual playlist's works are looked for with.
    @State private var manualSearch = PlaylistRules()
    /// Museum works being saved to the library to join a manual playlist.
    @State private var adding: Set<String> = []
    @FocusState private var nameFocused: Bool
    /// "Zapisz" was tapped with no name.
    @State private var nameMissing = false
    /// What the museums have for the rules, as each answers (as in Szukaj).
    @State private var remote: [RemoteItem] = []
    /// How many works the museums that answered have for the rules.
    @State private var remoteTotal = 0
    @State private var askingMuseums = false
    /// The rules the museums finished answering for.
    @State private var remoteAsked = PlaylistRules()
    @State private var typing = false
    /// Where the squares start, from the top of the scrolled content.
    @State private var squaresTop: CGFloat = 0
    /// "Zapisz" was tapped on a smart playlist with nothing searched.
    @State private var rulesMissing = false
    @State private var museums: [Museum] = []
    @State private var picked: [PhotosPickerItem] = []
    @State private var photos: [PickedPhoto] = []
    @State private var loadingPhotos = false
    /// Also fetch this many matching museum works into the library (0: no).
    @State private var fetchCount: Int
    @State private var album: AlbumSource
    @State private var albumCheck: Result<AlbumCheck, Error>?
    @State private var checkingAlbum = false
    /// An album playlist being edited stays one (its photos are the album's).
    private let wasAlbum: Bool
    /// So does "Ulubione", the hearts' playlist.
    private let wasFavorites: Bool

    /// `fetchFromMuseums` starts with fetching on, e.g. for a playlist made
    /// from a search that showed museum works.
    init(playlist: Playlist, fetchFromMuseums: Bool = false) {
        var playlist = playlist
        // "Only the best on e-paper" is gone from the editor: saving drops it.
        playlist.rules.minSuitability = nil
        // A range of years from older editors becomes a period chip.
        if playlist.rules.yearFrom != nil || playlist.rules.yearTo != nil {
            let years = "years:\(playlist.rules.yearFrom.map(String.init) ?? "")-\(playlist.rules.yearTo.map(String.init) ?? "")"
            if !playlist.rules.terms.contains(years) { playlist.rules.terms.append(years) }
            playlist.rules.yearFrom = nil
            playlist.rules.yearTo = nil
        }
        _playlist = State(initialValue: playlist)
        _fetchCount = State(initialValue: fetchFromMuseums ? 100 : 0)
        _album = State(initialValue: playlist.album ?? AlbumSource(url: ""))
        wasAlbum = playlist.id != nil && playlist.kind == .album
        wasFavorites = playlist.id != nil && playlist.isFavorites
    }

    /// With no name "Zapisz" still works: it takes you to the name.
    private var canSave: Bool {
        playlist.kind != .album || !album.url.trimmingCharacters(in: .whitespaces).isEmpty
    }

    private var hasName: Bool { !playlist.name.trimmingCharacters(in: .whitespaces).isEmpty }

    /// What the works below are looked for with: a smart playlist's rules,
    /// or a manual one's search.
    private var searched: Binding<PlaylistRules> {
        playlist.kind == .manual ? $manualSearch : $playlist.rules
    }

    /// Whether the museums are asked too: always for a manual playlist's
    /// search, for a smart one when its rules let them supply works.
    private var asksMuseums: Bool { playlist.kind == .manual || fetchBlocker == nil }

    /// Museum works go first: a smart playlist fetching them.
    private var museumsFirst: Bool { playlist.kind == .smart && fetchCount > 0 && fetchBlocker == nil }

    var body: some View {
        NavigationStack {
            ScrollViewReader { scroller in
                ScrollView {
                    VStack(alignment: .leading, spacing: 26) {
                        nameFields
                            .id(Self.nameID)
                        if !wasAlbum, !wasFavorites {
                            Picker("Rodzaj", selection: $playlist.kind) {
                                Text("Inteligentna").tag(PlaylistKind.smart)
                                Text("Ręczna").tag(PlaylistKind.manual)
                                Text("Album iCloud").tag(PlaylistKind.album)
                            }
                            .pickerStyle(.segmented)
                        }

                        switch playlist.kind {
                        case .smart:
                            search
                        case .manual:
                            cameraRoll
                            chosen
                            search
                        case .album:
                            albumSection
                        }
                    }
                    .padding(Theme.gutter)
                    .coordinateSpace(.named(Self.content))
                }
                .scrollDismissesKeyboard(.interactively)
                .background(Theme.paper)
                .navigationTitle(playlist.id == nil ? "Nowa playlista" : "Edycja playlisty")
                .navigationBarTitleDisplayMode(.inline)
                .navigationDestination(for: String.self) { id in
                    ItemDetailView(itemID: id)
                }
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Anuluj") { dismiss() }
                    }
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Zapisz") {
                            if !hasName {
                                // Up to the name, with the keyboard out.
                                nameMissing = true
                                withAnimation(.snappy) { scroller.scrollTo(Self.nameID, anchor: .top) }
                                nameFocused = true
                            } else if playlist.kind == .smart, playlist.rules.isEmpty {
                                // With no rules it would be the whole catalogue.
                                withAnimation(.snappy) {
                                    rulesMissing = true
                                    scroller.scrollTo(Self.nameID, anchor: .top)
                                }
                            } else {
                                save()
                            }
                        }
                        .disabled(!canSave)
                    }
                }
            }
            .task {
                await model.loadVocabulary()
                if LaunchRoute.screen == "editor-manual", manualSearch.isEmpty {  // CI screenshots
                    manualSearch.artists = ["Utagawa Hiroshige"]
                }
            }
            .task { if museums.isEmpty { museums = (try? await model.backend.museums()) ?? [] } }
            .task(id: searched.wrappedValue) { await refreshPreview() }
            .task(id: playlist.kind == .album ? nil : searched.wrappedValue) { await askMuseums() }
            .task(id: picked) { await loadPhotos() }
            .task(id: playlist.kind == .album ? album.url : "") { await checkAlbum() }
        }
    }

    // MARK: Sections

    private var nameFields: some View {
        VStack(alignment: .leading, spacing: 12) {
            TextField(
                "Nazwa", text: $playlist.name,
                prompt: nameMissing ? Text("Podaj nazwę playlisty").foregroundStyle(Theme.bad) : nil
            )
            .font(.serif(26, weight: .semibold))
            .focused($nameFocused)
            .submitLabel(.done)
            .onChange(of: playlist.name) { _, name in
                if !name.trimmingCharacters(in: .whitespaces).isEmpty { nameMissing = false }
            }
            TextField("Opis (opcjonalnie)", text: $playlist.description, axis: .vertical)
                .font(.serif(17))
                .foregroundStyle(Theme.inkSoft)
                .lineLimit(1 ... 3)
        }
    }

    /// The scrolled content's coordinate space.
    private static let content = "playlist.editor.content"
    /// The name fields, to scroll up to.
    private static let nameID = "playlist.editor.name"

    /// Nothing asked yet: no chips (exceptions and the hidden "favourites
    /// only" of the seeded playlist count as asked).
    private var asked: Bool { !searched.wrappedValue.isEmpty }

    /// Szukaj's field, then (smart) whether to fetch from the museums, a
    /// word on "+", and the squares until something is asked, then the works.
    private var search: some View {
        VStack(alignment: .leading, spacing: 14) {
            if playlist.kind == .manual {
                Eyebrow("Dzieła z katalogu i muzeów")
            }
            TermSearchField(
                tokens: tokens, museums: museums, colors: ColorTag.families + ColorTag.moods, typing: $typing
            ) {
                // The catalogue has nothing for it yet: museums will.
                if playlist.kind == .smart, fetchCount == 0, fetchBlocker == nil { fetchCount = 100 }
            }
            if playlist.kind == .smart {
                if rulesMissing, playlist.rules.isEmpty {
                    Label(
                        "Wyszukaj coś albo wybierz z \(Image(systemName: "plus.circle.fill")): bez tego playlista objęłaby cały katalog.",
                        systemImage: "exclamationmark.circle"
                    )
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(Theme.bad)
                    .fixedSize(horizontal: false, vertical: true)
                }
                fetchRow
            }
            if !typing {
                if asked {
                    previewSection
                } else {
                    idle
                }
            }
        }
    }

    private var idle: some View {
        VStack(spacing: 4) {
            Group {
                if playlist.kind == .manual {
                    Text("Znajdź dzieła jak w Szukaj i dodaj każde przyciskiem \(Image(systemName: "plus")) przy nim. Muzea, style, tematy, epoki i kolory dodasz przyciskiem \(Image(systemName: "plus.circle.fill")) w polu wyszukiwania.")
                } else {
                    Text("Muzea, style, tematy, epoki, techniki i kolory dodasz przyciskiem \(Image(systemName: "plus.circle.fill")) w polu wyszukiwania. Te same rodzaje to alternatywy, różne muszą pasować razem.")
                }
            }
                .font(.footnote)
                .foregroundStyle(Theme.inkSoft)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 12)
            // Down to the bottom of the sheet, so the squares have room
            // below their row (in the middle of the screen) to fall to.
            SquaresAnimation()
                .frame(maxWidth: .infinity)
                .containerRelativeFrame(.vertical) { height, _ in
                    max(200, height - squaresTop - Theme.gutter)
                }
                .onGeometryChange(for: CGFloat.self) { proxy in
                    proxy.frame(in: .named(Self.content)).minY
                } action: { squaresTop = $0 }
        }
        .frame(maxWidth: .infinity)
    }

    /// Fetching from the museums, right under the field: on, it says how
    /// many works it brings after saving.
    private var fetchRow: some View {
        HStack(spacing: 12) {
            Image(systemName: playlist.rules.favoritesOnly ? "heart" : "arrow.down.circle")
                .font(.title3)
                .foregroundStyle(fetchCount > 0 ? Theme.accent : Theme.inkSoft)
            VStack(alignment: .leading, spacing: 2) {
                Text(playlist.rules.favoritesOnly ? "Tylko ulubione" : "Pobieraj pasujące z muzeów")
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(Theme.ink)
                if let fetchBlocker {
                    Text(fetchBlocker).font(.caption).foregroundStyle(Theme.inkSoft)
                } else if fetchCount > 0 {
                    Menu {
                        Picker("Ile dzieł", selection: $fetchCount) {
                            ForEach([50, 100, 200, 300], id: \.self) { Text("do \($0) dzieł").tag($0) }
                        }
                    } label: {
                        HStack(spacing: 3) {
                            Text("do \(fetchCount) dzieł, w tle po zapisaniu")
                            Image(systemName: "chevron.up.chevron.down").font(.caption2)
                        }
                        .font(.caption)
                        .foregroundStyle(Theme.accent)
                    }
                } else {
                    Text("Teraz tylko to, co jest już w katalogu")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
            }
            Spacer(minLength: 8)
            if fetchBlocker == nil {
                Toggle("Pobieraj pasujące z muzeów", isOn: Binding(get: { fetchCount > 0 }, set: { fetchCount = $0 ? 100 : 0 }))
                    .labelsHidden()
                    .tint(Theme.accent)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(Theme.hairline))
        .animation(.snappy, value: fetchCount > 0)
    }

    /// The rules' chips, then the colours' and the museums' (the playlist's
    /// `sources`; other sources, such as the owner's photos, stay as they are).
    private var tokens: Binding<[SearchToken]> {
        let rules = searched
        return Binding(
            get: {
                let keys = Set(museums.map(\.key))
                return rules.wrappedValue.tokens(names: model.termNames)
                    + rules.wrappedValue.colors.map { SearchToken(kind: "color", key: $0, name: ColorTag.name($0)) }
                    + rules.wrappedValue.sources.filter { keys.contains($0) }.map {
                        SearchToken(kind: "museum", key: $0, name: museumName($0))
                    }
            },
            set: { tokens in
                let keys = Set(museums.map(\.key))
                rules.wrappedValue.setTokens(tokens)
                rules.wrappedValue.colors = tokens.filter { $0.kind == "color" }.map(\.key)
                rules.wrappedValue.sources = rules.wrappedValue.sources.filter { !keys.contains($0) }
                    + tokens.filter { $0.kind == "museum" }.map(\.key)
            }
        )
    }

    /// The searched museums, to ask (none: all of them).
    private var museumKeys: [String] {
        let keys = Set(museums.map(\.key))
        return searched.wrappedValue.sources.filter { keys.contains($0) }
    }

    private func museumName(_ key: String) -> String {
        museums.first { $0.key == key }?.name ?? Names.source(key)
    }

    private var cameraRoll: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Dodaj zdjęcia z rolki aparatu albo znajdź dzieła poniżej i dodaj je plusem.")
                .font(.subheadline)
                .foregroundStyle(Theme.inkSoft)
                .fixedSize(horizontal: false, vertical: true)
            PhotosPicker(selection: $picked, maxSelectionCount: 100, selectionBehavior: .ordered, matching: .images) {
                Label(photos.isEmpty ? "Dodaj zdjęcia z rolki" : "Zmień wybór zdjęć", systemImage: "photo.on.rectangle.angled")
            }
            .buttonStyle(SecondaryButtonStyle())
            if loadingPhotos {
                ProgressView("Wczytywanie zdjęć…")
                    .frame(maxWidth: .infinity)
            }
            if !photos.isEmpty {
                Text("\(Names.photos(photos.count)) trafi do biblioteki i do tej playlisty po zapisaniu.")
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(Theme.accent)
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 6), count: 4), spacing: 6) {
                    ForEach(photos) { photo in
                        Color.clear
                            .aspectRatio(1, contentMode: .fit)
                            .overlay(Image(uiImage: photo.thumbnail).resizable().scaledToFill())
                            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                    }
                }
            }
        }
    }

    /// The works a manual playlist holds; a tap on one takes it out.
    @ViewBuilder
    private var chosen: some View {
        if !playlist.itemIds.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                Eyebrow("W playliście · \(playlist.itemIds.count)")
                ScrollView(.horizontal, showsIndicators: false) {
                    LazyHStack(spacing: 8) {
                        ForEach(playlist.itemIds, id: \.self) { id in
                            Button {
                                withAnimation(.snappy) { playlist.itemIds.removeAll { $0 == id } }
                            } label: {
                                ArtImage(ref: .thumb(id), maxPixel: 240)
                                    .frame(width: 72, height: 72)
                                    .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                                    .overlay(alignment: .topTrailing) {
                                        Image(systemName: "xmark.circle.fill")
                                            .font(.body)
                                            .symbolRenderingMode(.palette)
                                            .foregroundStyle(.white, .black.opacity(0.45))
                                            .padding(3)
                                    }
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel("Usuń z playlisty")
                        }
                    }
                }
                .frame(height: 72)
            }
        }
    }

    private var albumSection: some View {
        VStack(alignment: .leading, spacing: 20) {
            VStack(alignment: .leading, spacing: 10) {
                SectionHeader(title: "Album udostępniony", subtitle: "Z aplikacji Zdjęcia na iPhonie")
                HStack(spacing: 10) {
                    TextField("https://photos.icloud.com/shared/album/…", text: $album.url)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                        .font(.subheadline)
                    PasteButton(payloadType: String.self) { strings in
                        if let link = strings.first?.trimmingCharacters(in: .whitespacesAndNewlines) {
                            album.url = link
                        }
                    }
                    .labelStyle(.iconOnly)
                    .buttonBorderShape(.capsule)
                }
                .padding(12)
                .background(Theme.card, in: RoundedRectangle(cornerRadius: 12))
                .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Theme.hairline))
                albumCheckStatus
                Text("W Zdjęciach: album udostępniony → Osoby → Witryna publiczna → Udostępnij link.")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
            }

            VStack(alignment: .leading, spacing: 10) {
                Eyebrow("Kolejność zdjęć")
                VStack(spacing: 0) {
                    ForEach(AlbumOrder.allCases) { order in
                        Button {
                            album.order = order
                        } label: {
                            HStack {
                                Text(order.title).foregroundStyle(Theme.ink)
                                Spacer()
                                if album.order == order {
                                    Image(systemName: "checkmark").foregroundStyle(Theme.accent)
                                }
                            }
                            .padding(.vertical, 12)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        if order != AlbumOrder.allCases.last { Divider() }
                    }
                }
                .padding(.horizontal, 14)
                .background(Theme.card, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(Theme.hairline))
                Text(album.order.explanation)
                    .font(.footnote)
                    .foregroundStyle(Theme.inkSoft)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Label(
                "Po zapisaniu serwer pobierze miniatury zdjęć z albumu, a oryginał każdego zdjęcia tuż przed "
                    + "pokazaniem go na ramce. Nowe zdjęcia z albumu dochodzą same co 30 minut. "
                    + "Wygląd zdjęć ustawisz w zakładce Ramka → Prezentacja → Zdjęcia.",
                systemImage: "icloud.and.arrow.down"
            )
            .font(.footnote)
            .foregroundStyle(Theme.inkSoft)
            .fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder
    private var albumCheckStatus: some View {
        if checkingAlbum {
            HStack(spacing: 8) {
                ProgressView()
                Text("Sprawdzanie albumu…")
            }
            .font(.footnote)
            .foregroundStyle(Theme.inkSoft)
        } else {
            switch albumCheck {
            case let .success(check):
                Label(
                    "\(check.name.isEmpty ? "Album" : "„\(check.name)”") · \(Names.photos(check.count))",
                    systemImage: "checkmark.circle.fill"
                )
                .font(.footnote.weight(.medium))
                .foregroundStyle(Theme.accent)
            case .failure:
                Label("Nie udało się otworzyć albumu. Sprawdź, czy link jest pełny, a witryna publiczna włączona.",
                      systemImage: "exclamationmark.triangle")
                    .font(.footnote)
                    .foregroundStyle(Theme.bad)
            case nil:
                EmptyView()
            }
        }
    }

    /// Museum works the catalogue doesn't hold, in any copy: what fetching
    /// would bring.
    private var fromMuseums: [RemoteItem] {
        let shown = Set(preview?.items.map(\.id) ?? [])
        return remote.filter {
            (!$0.inLibrary || playlist.itemIds.contains($0.id))
                && !shown.contains($0.id) && !shown.contains($0.twin ?? "")
        }
    }

    /// The works as Szukaj shows them: the catalogue's, then the museums';
    /// the museums' first when the playlist fetches them.
    private var previewSection: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                Text(summary)
                    .font(.serif(17, weight: .medium))
                    .foregroundStyle(preview?.count == 0 && fromMuseums.isEmpty && !askingMuseums ? Theme.bad : Theme.ink)
                    .contentTransition(.numericText())
                Spacer()
                if preview == nil || askingMuseums { ProgressView().controlSize(.small) }
            }
            if museumsFirst {
                museumPreview
                cataloguePreview
            } else {
                cataloguePreview
                museumPreview
            }
        }
    }

    @ViewBuilder
    private var cataloguePreview: some View {
        if let preview, !preview.items.isEmpty {
            Eyebrow("W katalogu · \(Names.works(preview.count))")
            MasonryGrid(items: preview.items) { item in
                card(item)
            }
        } else if preview != nil, !museumsFirst {
            Text(playlist.kind == .manual
                 ? "W katalogu nic nie pasuje."
                 : "W bazie nic jeszcze nie pasuje. Włącz pobieranie z muzeów, a playlista zapełni się w tle.")
                .font(.subheadline)
                .foregroundStyle(Theme.inkSoft)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// A found work; in a manual playlist with its "+" (a tick once added).
    @ViewBuilder
    private func card(_ item: ItemSummary, remote: RemoteItem? = nil) -> some View {
        let link = NavigationLink(value: item.id) {
            ArtCard(item: item, ref: remote?.thumb)
        }
        .buttonStyle(.plain)
        if playlist.kind == .manual {
            link.overlay(alignment: .topLeading) { addButton(item.id, remote: remote) }
        } else {
            link
        }
    }

    private func addButton(_ id: String, remote: RemoteItem?) -> some View {
        let added = playlist.itemIds.contains(id)
        return Button {
            Task { await toggle(id, remote: remote) }
        } label: {
            ZStack {
                if adding.contains(id) {
                    ProgressView().controlSize(.small).tint(.white)
                } else {
                    Image(systemName: added ? "checkmark" : "plus")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(.white)
                }
            }
            .frame(width: 32, height: 32)
            .background(added ? Theme.accent : .black.opacity(0.45), in: Circle())
            .overlay(Circle().strokeBorder(.white.opacity(0.8), lineWidth: 1.5))
            .padding(6)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(adding.contains(id))
        .accessibilityLabel(added ? "Usuń z playlisty" : "Dodaj do playlisty")
        .sensoryFeedback(.selection, trigger: added)
    }

    private var summary: String {
        guard let preview else { return "Szukam…" }
        return Names.works(preview.count + fromMuseums.count)
    }

    @ViewBuilder
    private var museumPreview: some View {
        if asksMuseums, !fromMuseums.isEmpty || askingMuseums {
            HStack {
                Eyebrow("Z muzeów" + (remoteTotal > 0 ? " · \(Names.works(remoteTotal))" : ""), color: Theme.accent)
                Spacer()
                if askingMuseums {
                    Text("doczytuję…").font(.caption).foregroundStyle(Theme.inkSoft)
                }
            }
            if playlist.kind == .smart, !fromMuseums.isEmpty {
                Text(fetchCount == 0
                     ? "Takie dzieła trafią do playlisty, gdy włączysz pobieranie z muzeów."
                     : "Takie dzieła trafią do playlisty w tle po zapisaniu.")
                    .font(.footnote)
                    .foregroundStyle(Theme.inkSoft)
                    .fixedSize(horizontal: false, vertical: true)
            }
            MasonryGrid(items: fromMuseums.map(\.item.summary)) { summary in
                card(summary, remote: fromMuseums.first { $0.id == summary.id })
            }
        } else if asksMuseums, preview != nil, remoteAsked == searched.wrappedValue, remoteTotal == 0 {
            Text("W muzeach nic więcej nie znaleziono.")
                .font(.footnote)
                .foregroundStyle(Theme.inkSoft)
        }
    }

    /// Why museums can't supply works for these rules, if they can't.
    private var fetchBlocker: String? {
        let rules = playlist.rules
        if rules.favoritesOnly { return "Bierze dzieła z Ulubionych, z muzeów nie pobiera." }
        if !rules.kinds.isEmpty, !rules.kinds.contains(.artwork) { return "Z muzeów przychodzą tylko dzieła sztuki." }
        let museums: Set<String> = ["aic", "cma", "met", "rijks", "wmc", "europeana", "openverse", "wikiart"]
        if !rules.sources.isEmpty, museums.isDisjoint(with: rules.sources) {
            return "Reguły nie dopuszczają żadnego muzeum."
        }
        return nil
    }

    // MARK: Actions

    /// Opens the album the link points to: its name (proposed as the
    /// playlist's) and number of photos.
    private func checkAlbum() async {
        let url = album.url.trimmingCharacters(in: .whitespacesAndNewlines)
        guard playlist.kind == .album, !url.isEmpty else {
            albumCheck = nil
            return
        }
        try? await Task.sleep(for: .milliseconds(500))
        guard !Task.isCancelled else { return }
        checkingAlbum = true
        defer { checkingAlbum = false }
        do {
            let check = try await model.backend.checkAlbum(url: url)
            guard !Task.isCancelled else { return }
            albumCheck = .success(check)
            if playlist.name.trimmingCharacters(in: .whitespaces).isEmpty, !check.name.isEmpty {
                playlist.name = check.name
            }
        } catch {
            if !Task.isCancelled { albumCheck = .failure(error) }
        }
    }

    /// Reports the first sync of an album once it ends; runs on after the editor closes.
    @MainActor
    private static func followSync(_ id: String, name: String, model: AppModel) async {
        do {
            let job = try await watchJob(id, backend: model.backend) { _ in }
            model.toast = job.error.isEmpty
                ? "„\(name)”: \(Names.photos(job.done)) z albumu"
                : "„\(name)”: nie udało się pobrać albumu"
            await model.refreshPlaylists()
        } catch {
            model.show(error)
        }
    }

    private func refreshPreview() async {
        try? await Task.sleep(for: .milliseconds(250))
        guard !Task.isCancelled else { return }
        let result = try? await model.backend.previewRules(searched.wrappedValue)
        withAnimation(.snappy) { preview = result }
    }

    /// Asks the museums what Discover's search would show for the rules,
    /// taking in each one's answer as it comes.
    private func askMuseums() async {
        guard playlist.kind != .album, asksMuseums, !searched.wrappedValue.isEmpty else {
            remote = []
            remoteTotal = 0
            remoteAsked = PlaylistRules()
            askingMuseums = false
            return
        }
        try? await Task.sleep(for: .milliseconds(400))
        guard !Task.isCancelled else { return }
        let rules = searched.wrappedValue
        remote = []
        remoteTotal = 0
        remoteAsked = PlaylistRules()
        askingMuseums = true
        var totals: [String: Int] = [:]
        do {
            let answers = try await model.backend.museumAnswers(rules, sources: museumKeys, page: 1)
            for try await answer in answers {
                guard !Task.isCancelled else { return }
                totals[answer.source] = max(totals[answer.source] ?? 0, answer.total)
                withAnimation(.snappy) {
                    remote = remote.adding(answer.items)
                    remoteTotal = totals.values.reduce(0, +)
                }
            }
        } catch {}
        // A newer search may have started meanwhile; it owns the spinner.
        guard !Task.isCancelled else { return }
        remoteAsked = rules
        askingMuseums = false
    }

    /// Adds a found work to the manual playlist, or takes it out again; a
    /// museum's work is saved to the library first.
    private func toggle(_ id: String, remote: RemoteItem?) async {
        if playlist.itemIds.contains(id) {
            withAnimation(.snappy) { playlist.itemIds.removeAll { $0 == id } }
            return
        }
        guard let remote, !remote.inLibrary else {
            withAnimation(.snappy) { playlist.itemIds.append(id) }
            return
        }
        adding.insert(id)
        defer { adding.remove(id) }
        do {
            let item = try await model.backend.importArtwork(source: remote.item.source, sourceID: remote.item.sourceId)
            if !playlist.itemIds.contains(item.id) {
                withAnimation(.snappy) { playlist.itemIds.append(item.id) }
            }
        } catch {
            model.show(error)
        }
    }

    /// Reports the fetch once it ends; runs on after the editor closes.
    @MainActor
    private static func followFill(_ id: String, name: String, model: AppModel) async {
        do {
            let job = try await watchJob(id, backend: model.backend) { _ in }
            model.toast = "„\(name)”: dodano \(job.done) dzieł z muzeów"
            await model.refreshPlaylists()
            await model.refreshFacets()
        } catch {
            model.show(error)
        }
    }

    /// Reads the chosen photos: an upright JPEG with its date and place, and a thumbnail.
    private func loadPhotos() async {
        guard !picked.isEmpty else {
            photos = []
            return
        }
        loadingPhotos = true
        defer { loadingPhotos = false }
        var loaded: [PickedPhoto] = []
        for item in picked {
            guard let data = try? await item.loadTransferable(type: Data.self) else { continue }
            if Task.isCancelled { return }
            let photo = await Task.detached(priority: .userInitiated) { PickedPhoto(original: data) }.value
            if let photo { loaded.append(photo) }
        }
        photos = loaded
    }

    /// Closes the editor at once; photos, the playlist and what follows are
    /// sent in the background, reported in toasts.
    private func save() {
        var playlist = playlist
        if !photos.isEmpty { playlist.kind = .manual }
        if playlist.kind == .album {
            var album = album
            album.url = album.url.trimmingCharacters(in: .whitespacesAndNewlines)
            playlist.album = album
        } else {
            playlist.album = nil
        }
        let uploads = photos.map(\.upload)
        let fetch = playlist.kind == .smart && fetchBlocker == nil ? fetchCount : 0
        Task { [model] in await Self.store(playlist, uploads: uploads, fetch: fetch, model: model) }
        dismiss()
    }

    @MainActor
    private static func store(_ playlist: Playlist, uploads: [PhotoUpload], fetch: Int, model: AppModel) async {
        var playlist = playlist
        let name = playlist.name
        do {
            if !uploads.isEmpty { model.toast = "„\(name)”: wysyłam \(Names.photos(uploads.count))…" }
            for upload in uploads {
                let item = try await model.backend.uploadPhoto(upload)
                playlist.itemIds.append(item.id)
            }
            let saved = try await model.backend.savePlaylist(playlist)
            model.toast = "Zapisano „\(name)”"
            model.libraryChanged()
            if saved.playlist.kind == .album, saved.playlist.albumSync == nil {
                // A new album (or a new link): its first sync is running.
                let jobID = try await model.backend.syncAlbum(playlistID: saved.playlist.id)
                model.toast = "Zapisano „\(name)”, pobieram miniatury zdjęć"
                await followSync(jobID, name: name, model: model)
            }
            if saved.playlist.kind == .smart, fetch > 0 {
                let jobID = try await model.backend.fillLibrary(rules: playlist.rules, count: fetch)
                model.toast = "Zapisano „\(name)”, pobieram do \(fetch) dzieł w tle"
                await followFill(jobID, name: name, model: model)
            }
        } catch {
            model.show(error)
        }
    }
}

/// A photo chosen from the camera roll, ready to upload.
struct PickedPhoto: Identifiable, Sendable {
    let id = UUID()
    let upload: PhotoUpload
    let thumbnail: UIImage

    init?(original: Data) {
        var upload = PhotoUpload(original: original)
        upload.title = Self.title(upload.takenAt)
        guard let image = UIImage(data: upload.data),
              let thumbnail = image.preparingThumbnail(of: CGSize(width: 240, height: 240 * image.size.height / max(image.size.width, 1)))
        else { return nil }
        self.upload = upload
        self.thumbnail = thumbnail
    }

    /// "Zdjęcie z 1 lipca 2026", or "Zdjęcie z rolki" without a date.
    static func title(_ takenAt: String?) -> String {
        let parts = (takenAt ?? "").prefix(10).split(separator: "-").compactMap { Int($0) }
        guard parts.count == 3,
              let date = Calendar.current.date(from: DateComponents(year: parts[0], month: parts[1], day: parts[2]))
        else { return "Zdjęcie z rolki" }
        return "Zdjęcie z " + date.formatted(.dateTime.day().month(.wide).year().locale(Locale(identifier: "pl_PL")))
    }
}
