import PhotosUI
import SwiftUI

/// Create or edit a playlist. Smart playlists are built from rules with a
/// live preview of the matching pictures; manual ones can take photos from
/// the camera roll, uploaded to the library when the playlist is saved;
/// album playlists mirror a shared iCloud album.
struct PlaylistEditorView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var playlist: Playlist
    @State private var preview: RulesPreview?
    @State private var saving = false
    @State private var bestOnly: Bool
    @State private var picked: [PhotosPickerItem] = []
    @State private var photos: [PickedPhoto] = []
    @State private var loadingPhotos = false
    @State private var uploaded = 0
    /// Also fetch this many matching museum works into the library (0: no).
    @State private var fetchCount = 0
    @State private var album: AlbumSource
    @State private var albumCheck: Result<AlbumCheck, Error>?
    @State private var checkingAlbum = false
    /// An album playlist being edited stays one (its photos are the album's).
    private let wasAlbum: Bool

    init(playlist: Playlist) {
        _playlist = State(initialValue: playlist)
        _bestOnly = State(initialValue: playlist.rules.minSuitability != nil)
        _album = State(initialValue: playlist.album ?? AlbumSource(url: ""))
        wasAlbum = playlist.id != nil && playlist.kind == .album
    }

    private var canSave: Bool {
        !playlist.name.trimmingCharacters(in: .whitespaces).isEmpty && !saving
            && (playlist.kind != .album || !album.url.trimmingCharacters(in: .whitespaces).isEmpty)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 26) {
                    nameFields
                    if !wasAlbum {
                        Picker("Rodzaj", selection: $playlist.kind) {
                            Text("Inteligentna").tag(PlaylistKind.smart)
                            Text("Ręczna").tag(PlaylistKind.manual)
                            Text("Album iCloud").tag(PlaylistKind.album)
                        }
                        .pickerStyle(.segmented)
                    }

                    switch playlist.kind {
                    case .smart:
                        rules
                        previewSection
                        fetchSection
                    case .manual:
                        cameraRoll
                    case .album:
                        albumSection
                    }
                }
                .padding(Theme.gutter)
            }
            .background(Theme.paper)
            .navigationTitle(playlist.id == nil ? "Nowa playlista" : "Edycja playlisty")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Anuluj") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Zapisz") { Task { await save() } }
                        .disabled(!canSave)
                }
            }
            .task { await model.loadVocabulary() }
            .task(id: playlist.rules) { await refreshPreview() }
            .task(id: picked) { await loadPhotos() }
            .task(id: playlist.kind == .album ? album.url : "") { await checkAlbum() }
            .interactiveDismissDisabled(saving)
            .onChange(of: bestOnly) { _, on in playlist.rules.minSuitability = on ? 0.72 : nil }
        }
    }

    // MARK: Sections

    private var nameFields: some View {
        VStack(alignment: .leading, spacing: 12) {
            TextField("Nazwa", text: $playlist.name)
                .font(.serif(26, weight: .semibold))
            TextField("Opis (opcjonalnie)", text: $playlist.description, axis: .vertical)
                .font(.serif(17))
                .foregroundStyle(Theme.inkSoft)
                .lineLimit(1 ... 3)
        }
    }

    private var rules: some View {
        VStack(alignment: .leading, spacing: 20) {
            SectionHeader(title: "Reguły", subtitle: "Wszystkie warunki muszą być spełnione")
            VStack(alignment: .leading, spacing: 8) {
                Eyebrow("Czego szukasz")
                TermSearchField(tokens: tokens) {
                    // The catalogue has nothing for it yet: museums will.
                    if fetchCount == 0, fetchBlocker == nil { fetchCount = 100 }
                }
                Text("Artyści, style i tematy tego samego rodzaju to alternatywy; różne rodzaje muszą pasować razem.")
                    .font(.footnote)
                    .foregroundStyle(Theme.inkSoft)
                    .fixedSize(horizontal: false, vertical: true)
            }

            VStack(alignment: .leading, spacing: 10) {
                Eyebrow("Kolorystyka")
                FlowLayout(spacing: 8) {
                    ForEach(ColorTag.families + ColorTag.moods, id: \.self) { tag in
                        Chip(
                            title: ColorTag.name(tag),
                            swatch: ColorTag.color(tag),
                            selected: playlist.rules.colors.contains(tag)
                        ) {
                            if playlist.rules.colors.contains(tag) {
                                playlist.rules.colors.removeAll { $0 == tag }
                            } else {
                                playlist.rules.colors.append(tag)
                            }
                        }
                    }
                }
            }

            VStack(alignment: .leading, spacing: 10) {
                Eyebrow("Epoka")
                HStack(spacing: 12) {
                    yearField("od roku", value: $playlist.rules.yearFrom)
                    Text("–").foregroundStyle(Theme.inkSoft)
                    yearField("do roku", value: $playlist.rules.yearTo)
                }
            }

            Toggle(isOn: $playlist.rules.favoritesOnly) {
                Label("Tylko ulubione", systemImage: "heart")
            }
            Toggle(isOn: $bestOnly) {
                Label("Tylko najlepsze na e-papier", systemImage: "sparkles")
            }
        }
        .tint(Theme.accent)
    }

    private var tokens: Binding<[SearchToken]> {
        Binding(
            get: { playlist.rules.tokens(names: model.termNames) },
            set: { playlist.rules.setTokens($0) }
        )
    }

    private func yearField(_ title: String, value: Binding<Int?>) -> some View {
        TextField(
            title,
            text: Binding(
                get: { value.wrappedValue.map(String.init) ?? "" },
                set: { value.wrappedValue = Int($0.filter(\.isNumber)) }
            )
        )
        .keyboardType(.numberPad)
        .padding(12)
        .frame(maxWidth: 140)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Theme.hairline))
    }

    private var cameraRoll: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Dodaj zdjęcia z rolki aparatu albo dzieła z ich szczegółów („Dodaj do playlisty”).")
                .font(.subheadline)
                .foregroundStyle(Theme.inkSoft)
                .fixedSize(horizontal: false, vertical: true)
            PhotosPicker(selection: $picked, maxSelectionCount: 100, selectionBehavior: .ordered, matching: .images) {
                Label(photos.isEmpty ? "Dodaj zdjęcia z rolki" : "Zmień wybór zdjęć", systemImage: "photo.on.rectangle.angled")
            }
            .buttonStyle(SecondaryButtonStyle())
            .disabled(saving)
            if loadingPhotos {
                ProgressView("Wczytywanie zdjęć…")
                    .frame(maxWidth: .infinity)
            }
            if !photos.isEmpty {
                Text(saving
                     ? "Wysyłanie: \(uploaded) z \(uploaded + photos.count)…"
                     : "\(Names.photos(photos.count)) trafi do biblioteki i do tej playlisty po zapisaniu.")
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

    private var previewSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                SectionHeader(title: "Podgląd")
                Spacer()
                if let preview {
                    Text(Names.works(preview.count))
                        .font(.headline)
                        .foregroundStyle(preview.count == 0 ? Theme.bad : Theme.accent)
                        .contentTransition(.numericText())
                }
            }
            if let items = preview?.items, !items.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 10) {
                        ForEach(items) { item in
                            ArtImage(ref: .thumb(item.id), placeholder: item.placeholderColor, maxPixel: 300)
                                .frame(width: 84, height: 84)
                                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                        }
                    }
                }
                .scrollClipDisabled()
            } else if preview != nil {
                Text("W bazie nic jeszcze nie pasuje. Włącz pobieranie z muzeów poniżej, a playlista zapełni się w tle.")
                    .font(.subheadline)
                    .foregroundStyle(Theme.inkSoft)
            }
        }
    }

    /// Why museums can't supply works for these rules, if they can't.
    private var fetchBlocker: String? {
        let rules = playlist.rules
        if rules.favoritesOnly { return "Ulubionych nie da się pobrać z muzeów." }
        if !rules.kinds.isEmpty, !rules.kinds.contains(.artwork) { return "Z muzeów przychodzą tylko dzieła sztuki." }
        let museums: Set<String> = ["aic", "cma", "met", "rijks", "wmc", "europeana", "openverse", "wikiart"]
        if !rules.sources.isEmpty, museums.isDisjoint(with: rules.sources) {
            return "Reguły nie dopuszczają żadnego muzeum."
        }
        return nil
    }

    private var fetchSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Toggle(
                isOn: Binding(get: { fetchCount > 0 }, set: { fetchCount = $0 ? 100 : 0 })
            ) {
                Label("Pobierz pasujące dzieła z muzeów", systemImage: "arrow.down.circle")
            }
            .tint(Theme.accent)
            .disabled(fetchBlocker != nil)
            if let fetchBlocker {
                Text(fetchBlocker).font(.footnote).foregroundStyle(Theme.inkSoft)
            } else if fetchCount > 0 {
                Picker("Ile dzieł", selection: $fetchCount) {
                    ForEach([50, 100, 200, 300], id: \.self) { Text("\($0)").tag($0) }
                }
                .pickerStyle(.segmented)
                Text(fetchHint)
                    .font(.footnote)
                    .foregroundStyle(Theme.inkSoft)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var fetchHint: String {
        var text = "Po zapisaniu serwer poszuka we wszystkich muzeach dzieł spełniających reguły i doda je do biblioteki w tle. Te, które już masz, są pomijane."
        if !playlist.rules.colors.isEmpty || playlist.rules.minSuitability != nil {
            text += " Kolorystykę i jakość na e-papierze widać dopiero po pobraniu miniatury, więc to potrwa dłużej."
        }
        return text
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
        let result = try? await model.backend.previewRules(playlist.rules)
        withAnimation(.snappy) { preview = result }
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

    private func save() async {
        saving = true
        uploaded = 0
        defer { saving = false }
        do {
            // Photos first, one by one; each uploaded one leaves the list, so
            // a retry after an error does not add it twice.
            if !photos.isEmpty { playlist.kind = .manual }
            while let photo = photos.first {
                let item = try await model.backend.uploadPhoto(photo.upload)
                playlist.itemIds.append(item.id)
                photos.removeFirst()
                uploaded += 1
            }
            picked = []
            if playlist.kind == .album {
                album.url = album.url.trimmingCharacters(in: .whitespacesAndNewlines)
                playlist.album = album
            } else {
                playlist.album = nil
            }
            let saved = try await model.backend.savePlaylist(playlist)
            await model.refreshPlaylists()
            model.toast = "Zapisano „\(playlist.name)”"
            if saved.playlist.kind == .album, saved.playlist.albumSync == nil {
                // A new album (or a new link): its first sync is running.
                let jobID = try await model.backend.syncAlbum(playlistID: saved.playlist.id)
                model.toast = "Zapisano „\(playlist.name)”, pobieram miniatury zdjęć"
                Task { [model, name = playlist.name] in await Self.followSync(jobID, name: name, model: model) }
            }
            if playlist.kind == .smart, fetchCount > 0, fetchBlocker == nil {
                let jobID = try await model.backend.fillLibrary(rules: playlist.rules, count: fetchCount)
                model.toast = "Zapisano „\(playlist.name)”, pobieram do \(fetchCount) dzieł w tle"
                Task { [model, name = playlist.name] in await Self.followFill(jobID, name: name, model: model) }
            }
            dismiss()
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
