import PhotosUI
import SwiftUI

/// Create or edit a playlist. Smart playlists are built like Szukaj: the
/// system search field at the bottom of the sheet with the same glass groups
/// over it (hidden while the works scroll, back when the field is tapped),
/// the icon's squares at play until something is asked, then
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
    /// Works opened from the search, and their studies.
    @State private var path = NavigationPath()
    /// What a manual playlist's works are looked for with.
    @State private var manualSearch = PlaylistRules()
    /// Museum works being saved to the library to join a manual playlist.
    @State private var adding: Set<String> = []
    @FocusState private var nameFocused: Bool
    /// "Zapisz" was tapped with no name.
    @State private var nameMissing = false
    /// What the museums have for the rules, as each answers (as in Szukaj).
    @State private var remote: [RemoteItem] = []
    @State private var askingMuseums = false
    @State private var lookup = TermLookup()
    @FocusState private var fieldFocused: Bool
    @FocusState private var descriptionFocused: Bool
    /// The groups over the field: hidden while scrolling the works.
    @State private var groupsShown = true
    /// "Wybrane · N" was tapped: up to the playlist's works.
    @State private var showChosen = 0
    /// Where the squares start, from the top of the scrolled content.
    @State private var squaresTop: CGFloat = 0
    /// "Zapisz" was tapped on a smart playlist with nothing searched.
    @State private var rulesMissing = false
    @State private var museums: [Museum] = []
    @State private var picked: [PhotosPickerItem] = []
    @State private var photos: [PickedPhoto] = []
    @State private var loadingPhotos = false
    @State private var album: AlbumSource
    @State private var albumCheck: Result<AlbumCheck, Error>?
    @State private var checkingAlbum = false
    /// An album playlist being edited stays one (its photos are the album's).
    private let wasAlbum: Bool
    /// So does "Ulubione", the hearts' playlist.
    private let wasFavorites: Bool

    /// A new playlist starts with `Playlist.defaultLimit` works; one saved
    /// before there was a limit keeps all that match ("Wszystkie").
    init(playlist: Playlist) {
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
        if playlist.id == nil, !playlist.isFavorites, playlist.limit == nil {
            playlist.limit = Playlist.defaultLimit
        }
        _playlist = State(initialValue: playlist)
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
    private var asksMuseums: Bool {
        // Favourites and playlists are the owner's: no museum has them.
        guard !searched.wrappedValue.asksMine else { return false }
        return playlist.kind == .manual || fetchBlocker == nil
    }

    /// How many works the playlist misses that the museums are asked for
    /// after saving: up to its limit ("Wszystkie": up to the default), when
    /// museums can supply them; nil until the matching works are counted.
    private var missing: Int? {
        guard playlist.kind == .smart, let preview else { return nil }
        guard fetchBlocker == nil else { return 0 }
        return max(0, (playlist.limit ?? Playlist.defaultLimit) - preview.count)
    }

    var body: some View {
        NavigationStack(path: $path) {
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
                        if model.me?.people == true {
                            // Mateusz, 2026-10-31: new playlists are private.
                            Toggle(isOn: Binding(
                                get: { playlist.shared ?? false },
                                set: { playlist.shared = $0 }
                            )) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Wspólna")
                                    Text("Domownicy też ją widzą i mogą pokazać na ramce; zmieniasz ją tylko Ty.")
                                        .font(.caption)
                                        .foregroundStyle(Theme.inkSoft)
                                }
                            }
                            .tint(Theme.accent)
                        }

                        switch playlist.kind {
                        case .smart:
                            search
                        case .manual:
                            cameraRoll
                            chosen
                                .id(Self.chosenID)
                            search
                        case .album:
                            albumSection
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(Theme.gutter)
                    .coordinateSpace(.named(Self.content))
                }
                .scrollDismissesKeyboard(.immediately)
                .hidesOnScroll($groupsShown)
                .paperPage()
                .modifier(EditorSearch(
                    enabled: playlist.kind != .album,
                    lookup: lookup,
                    tokens: tokens,
                    focused: $fieldFocused,
                    groupsShown: groupsShown && !nameFocused && !descriptionFocused,
                    museums: museums
                ))
                // Typing: up to the suggestions.
                .onChange(of: lookup.typing) { _, typing in
                    if typing { withAnimation(.snappy) { scroller.scrollTo(Self.searchID, anchor: .top) } }
                }
                .onChange(of: showChosen) {
                    withAnimation(.snappy) { scroller.scrollTo(Self.chosenID, anchor: .top) }
                }
                // Tapping the field brings the groups back, as does asking nothing.
                .onChange(of: fieldFocused) { _, focused in
                    if focused, !groupsShown { withAnimation(.snappy) { groupsShown = true } }
                }
                .onChange(of: asked) { _, asked in
                    if !asked, !groupsShown { withAnimation(.snappy) { groupsShown = true } }
                }
                .navigationTitle(playlist.id == nil ? "Nowa playlista" : "Edycja playlisty")
                .navigationBarTitleDisplayMode(.inline)
                .navigationDestination(for: String.self) { id in
                    ItemDetailView(itemID: id)
                }
                .navigationDestination(for: DailyRoute.self) { route in
                    DailyView(route: route)
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
        .opensStudies(on: $path)
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
                .focused($descriptionFocused)
                .font(.serif(17))
                .foregroundStyle(Theme.inkSoft)
                .lineLimit(1 ... 3)
        }
    }

    /// The scrolled content's coordinate space.
    private static let content = "playlist.editor.content"
    /// The name fields, to scroll up to.
    private static let nameID = "playlist.editor.name"
    /// The search's part, with the suggestions while typing.
    private static let searchID = "playlist.editor.search"
    /// A manual playlist's works.
    private static let chosenID = "playlist.editor.chosen"

    /// Nothing asked yet: no chips (exceptions and the hidden "favourites
    /// only" of the seeded playlist count as asked).
    private var asked: Bool { !searched.wrappedValue.isEmpty }

    /// While typing, what the words could mean; (smart) whether to fetch
    /// from the museums, a word on how groups combine, and the squares until
    /// something is asked, then the works. The field and its groups are at
    /// the bottom of the sheet.
    private var search: some View {
        VStack(alignment: .leading, spacing: 14) {
            if playlist.kind == .manual {
                Eyebrow("Dodaj dzieła")
            }
            if lookup.typing {
                TermSuggestions(lookup: lookup, tokens: tokens)
            }
            if playlist.kind == .smart {
                if rulesMissing, playlist.rules.isEmpty {
                    Label(
                        "Wyszukaj coś na dole albo wybierz grupę nad polem: bez tego playlista objęłaby wszystkie dzieła.",
                        systemImage: "exclamationmark.circle"
                    )
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(Theme.bad)
                    .fixedSize(horizontal: false, vertical: true)
                }
                limitRow
            }
            if !lookup.typing {
                if asked {
                    previewSection
                } else {
                    idle
                }
            }
        }
        .id(Self.searchID)
    }

    private var idle: some View {
        VStack(spacing: 4) {
            Group {
                if playlist.kind == .manual {
                    Text("Znajdź dzieła jak w Szukaj i dodaj każde przyciskiem \(Image(systemName: "plus")) przy nim.")
                } else {
                    Text("W jednej grupie wystarczy jedno z wybranych, różne grupy muszą pasować razem: np. Impresjonizm lub Secesja, a do tego Morze.")
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

    /// "Ile dzieł", right under the field: the playlist's limit, and what
    /// saving does with it (works asked from the museums, or which are taken).
    private var limitRow: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(playlist.rules.favoritesOnly ? "Ile ulubionych" : "Ile dzieł")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(Theme.ink)
            HStack(spacing: 6) {
                ForEach(Playlist.limits, id: \.self) { limit in
                    let chosen = playlist.limit == limit
                    Button {
                        withAnimation(.snappy) { playlist.limit = limit }
                    } label: {
                        Text(limit.map(String.init) ?? "Wszystkie")
                            .font(.footnote.weight(.medium))
                            .lineLimit(1)
                            .minimumScaleFactor(0.8)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 7)
                            .foregroundStyle(chosen ? Theme.paper : Theme.ink)
                            .background(chosen ? Theme.ink : Theme.ink.opacity(0.06), in: Capsule())
                            .contentShape(Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityAddTraits(chosen ? .isSelected : [])
                }
            }
            .sensoryFeedback(.selection, trigger: playlist.limit)
            Text(limitNote)
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
                .fixedSize(horizontal: false, vertical: true)
                .contentTransition(.numericText())
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(Theme.hairline))
    }

    /// Under "Ile dzieł": how many match and what saving does about it.
    private var limitNote: AttributedString {
        guard let preview, let missing else {
            return AttributedString(playlist.rules.isEmpty ? "Wyszukaj albo wybierz grupę, a policzę pasujące." : "Liczę pasujące…")
        }
        let matching = preview.count
        if let limit = playlist.limit, matching > limit {
            var note = AttributedString("Pasuje \(matching), playlista weźmie ")
            var taken = AttributedString("\(limit)")
            taken.foregroundColor = Theme.accent
            note += taken + AttributedString(": najpierw ulubione, reszta losowo.")
            return note
        }
        if missing > 0 {
            var note = AttributedString(matching == 0 ? "Jeszcze nic nie pasuje. " : "Pasuje \(matching). ")
            var asked = AttributedString(matching == 0 ? "\(missing) dobiorę z muzeów" : "Brakujące \(missing) dobiorę z muzeów")
            asked.foregroundColor = Theme.accent
            note += asked + AttributedString(" w tle po zapisaniu.")
            return note
        }
        let mine = fetchBlocker.map { " \($0)" } ?? ""
        return AttributedString((playlist.limit == nil ? "Pasuje \(matching), playlista weźmie wszystkie." : "Pasuje \(matching).") + mine)
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
            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .firstTextBaseline) {
                    Text(summary)
                        .font(.serif(17, weight: .medium))
                        .foregroundStyle(preview?.count == 0 && fromMuseums.isEmpty && !askingMuseums ? Theme.bad : Theme.ink)
                        .contentTransition(.numericText())
                    if preview == nil || askingMuseums { ProgressView().controlSize(.small) }
                    Spacer()
                    if playlist.kind == .manual, !playlist.itemIds.isEmpty {
                        Button {
                            showChosen += 1
                        } label: {
                            Label("Wybrane · \(playlist.itemIds.count)", systemImage: "checkmark.circle")
                                .font(.footnote.weight(.semibold))
                                .foregroundStyle(Theme.accent)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 5)
                                .glassEffect(.regular.interactive(), in: .capsule)
                        }
                        .buttonStyle(.plain)
                        .accessibilityHint("Pokazuje dzieła tej playlisty")
                    }
                }
                // What makes the playlist, also while the groups are hidden.
                TokenSummary(tokens: tokens.wrappedValue)
            }
            if playlist.kind == .manual {
                manualPreview
            } else {
                smartPreview
            }
        }
    }

    /// A smart playlist's works: those that match first, then (paler) what
    /// the museums would add up to the limit after saving.
    @ViewBuilder
    private var smartPreview: some View {
        let remotes = asksMuseums ? Array(fromMuseums.prefix(missing ?? 0)) : []
        let byID = Dictionary(remotes.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        let known = preview?.items ?? []
        if !known.isEmpty || !remotes.isEmpty {
            MasonryGrid(items: known + remotes.map(\.item.summary)) { item in
                let remote = byID[item.id]
                card(item, remote: remote)
                    .opacity(remote == nil ? 1 : 0.55)
            }
        } else if preview != nil, missing == 0 {
            Text("Nic nie pasuje.")
                .font(.subheadline)
                .foregroundStyle(Theme.inkSoft)
        }
    }

    /// A manual playlist's search: one grid, the works we have first and
    /// the museums' coming in under them, without saying which is which.
    @ViewBuilder
    private var manualPreview: some View {
        let remotes = asksMuseums && preview != nil ? fromMuseums : []
        let byID = Dictionary(remotes.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        let known = preview?.items ?? []
        if !known.isEmpty || !remotes.isEmpty {
            MasonryGrid(items: known + remotes.map(\.item.summary)) { item in
                card(item, remote: byID[item.id])
            }
        } else if preview != nil, !askingMuseums {
            Text("Nic nie pasuje.")
                .font(.subheadline)
                .foregroundStyle(Theme.inkSoft)
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
        if playlist.kind == .manual { return "Znalezione · " + Names.works(preview.count + fromMuseums.count) }
        if let limit = playlist.limit, preview.count > limit { return "\(limit) z " + Names.works(preview.count) }
        return Names.works(preview.count + (missing ?? 0))
    }

    /// Why museums can't supply works for these rules, if they can't.
    private var fetchBlocker: String? {
        let rules = playlist.rules
        if rules.favoritesOnly { return "Bierze dzieła z Ulubionych, z muzeów nie pobiera." }
        if rules.asksMine { return "Ulubione i playlisty to Twoje dzieła, z muzeów nie pobiera." }
        if !rules.kinds.isEmpty, !rules.kinds.contains(.artwork) { return "Z muzeów przychodzą tylko dzieła sztuki." }
        let museums: Set<String> = [
            "aic", "cma", "met", "rijks", "wmc", "europeana", "openverse", "smk", "wikiart",
            "nga", "mnw", "mnk", "yale", "si", "vam",
        ]
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

    /// Follows the first sync of an album on its card; runs on after the editor closes.
    @MainActor
    private static func followSync(_ id: String, name: String, card: Notice.ID, model: AppModel) async throws {
        let job = try await watchJob(id, backend: model.backend) { job in
            if job.total > 0 {
                model.notices.update(card, fraction: Double(job.done) / Double(job.total), count: "\(job.done) z \(job.total)")
            }
        }
        if job.error.isEmpty {
            model.notices.end(card, .done, "„\(name)”: \(Names.photos(job.done)) z albumu")
        } else {
            model.notices.end(card, .error, "„\(name)”: nie udało się pobrać albumu", job.error)
        }
        await model.refreshPlaylists()
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
            askingMuseums = false
            return
        }
        try? await Task.sleep(for: .milliseconds(400))
        guard !Task.isCancelled else { return }
        let rules = searched.wrappedValue
        remote = []
        askingMuseums = true
        do {
            let answers = try await model.backend.museumAnswers(rules, sources: museumKeys, page: 1)
            for try await answer in answers {
                guard !Task.isCancelled else { return }
                withAnimation(.snappy) { remote = remote.adding(answer.items) }
            }
        } catch {}
        // A newer search may have started meanwhile; it owns the spinner.
        guard !Task.isCancelled else { return }
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

    /// Follows the museum fetch on its card; runs on after the editor closes.
    @MainActor
    private static func followFill(_ id: String, name: String, card: Notice.ID, model: AppModel) async throws {
        let job = try await watchJob(id, backend: model.backend) { job in
            if job.total > 0 {
                let seen = job.done + job.failed
                model.notices.update(card, fraction: Double(seen) / Double(job.total), count: "\(seen) z \(job.total)")
            }
        }
        model.notices.end(card, .done, "„\(name)”: dodano \(Names.works(job.done)) z muzeów")
        await model.refreshPlaylists()
        await model.refreshFacets()
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
    /// sent in the background, followed on a card.
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
        let fetch = missing ?? 0
        if playlist.kind != .smart { playlist.limit = nil }
        Task { [model] in await Self.store(playlist, uploads: uploads, fetch: fetch, model: model) }
        dismiss()
    }

    @MainActor
    private static func store(_ playlist: Playlist, uploads: [PhotoUpload], fetch: Int, model: AppModel) async {
        var playlist = playlist
        let name = playlist.name
        let notices = model.notices
        let card = notices.begin("Zapisuję „\(name)”", background: true)
        do {
            for (index, upload) in uploads.enumerated() {
                notices.update(
                    card, title: "„\(name)”: wysyłam zdjęcia",
                    fraction: Double(index) / Double(uploads.count), count: "\(index) z \(uploads.count)"
                )
                let item = try await model.backend.uploadPhoto(upload)
                playlist.itemIds.append(item.id)
            }
            let saved = try await model.backend.savePlaylist(playlist)
            model.libraryChanged()
            if saved.playlist.kind == .album, saved.playlist.albumSync == nil {
                // A new album (or a new link): its first sync is running.
                let jobID = try await model.backend.syncAlbum(playlistID: saved.playlist.id)
                notices.update(card, title: "„\(name)”: pobieram miniatury zdjęć")
                try await followSync(jobID, name: name, card: card, model: model)
            } else if saved.playlist.kind == .smart, fetch > 0 {
                let jobID = try await model.backend.fillLibrary(rules: playlist.rules, count: fetch)
                notices.update(card, title: "„\(name)”: pobieram dzieła z muzeów")
                try await followFill(jobID, name: name, card: card, model: model)
            } else {
                notices.end(card, .done, "Zapisano „\(name)”")
            }
        } catch {
            notices.fail(error, in: card)
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

/// The editor's search, except for an album playlist: the system field at the
/// bottom of the sheet and the glass groups over it.
private struct EditorSearch: ViewModifier {
    let enabled: Bool
    let lookup: TermLookup
    let tokens: Binding<[SearchToken]>
    let focused: FocusState<Bool>.Binding
    /// Not while the name or description is being typed.
    let groupsShown: Bool
    let museums: [Museum]
    /// The sheet's height, for how tall an open group may be.
    @State private var height: CGFloat = 700

    @ViewBuilder
    func body(content: Content) -> some View {
        if enabled {
            content
                .safeAreaInset(edge: .bottom, spacing: 0) {
                    if groupsShown {
                        TermFacetBar(
                            tokens: tokens, museums: museums, colors: ColorTag.families + ColorTag.moods,
                            focus: focused, panelHeight: height * TermFacetBar.panelShare
                        )
                        .padding(.horizontal, Theme.gutter)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                    }
                }
                // Measured outside the groups' inset: an open group grows it.
                .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { height = $0 }
                .termSearch(lookup, tokens: tokens, focused: focused)
                .toolbar {
                    DefaultToolbarItem(kind: .search, placement: .bottomBar)
                }
        } else {
            content
        }
    }
}
