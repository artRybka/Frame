import PhotosUI
import SwiftUI

/// Create or edit a playlist. Smart playlists are built from rules with a
/// live preview of the matching pictures; manual ones can take photos from
/// the camera roll, uploaded to the library when the playlist is saved.
struct PlaylistEditorView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var playlist: Playlist
    @State private var preview: RulesPreview?
    @State private var facetSheet: FacetKind?
    @State private var saving = false
    @State private var bestOnly: Bool
    @State private var picked: [PhotosPickerItem] = []
    @State private var photos: [PickedPhoto] = []
    @State private var loadingPhotos = false
    @State private var uploaded = 0

    init(playlist: Playlist) {
        _playlist = State(initialValue: playlist)
        _bestOnly = State(initialValue: playlist.rules.minSuitability != nil)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 26) {
                    nameFields
                    Picker("Rodzaj", selection: $playlist.kind) {
                        Text("Inteligentna").tag(PlaylistKind.smart)
                        Text("Ręczna").tag(PlaylistKind.manual)
                    }
                    .pickerStyle(.segmented)

                    if playlist.kind == .smart {
                        rules
                        previewSection
                    } else {
                        cameraRoll
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
                        .disabled(playlist.name.trimmingCharacters(in: .whitespaces).isEmpty || saving)
                }
            }
            .sheet(item: $facetSheet) { kind in
                RuleFacetPicker(kind: kind, rules: $playlist.rules)
                    .presentationDetents([.medium, .large])
            }
            .task(id: playlist.rules) { await refreshPreview() }
            .task(id: picked) { await loadPhotos() }
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
            ruleRow(.artists, values: playlist.rules.artists)
            ruleRow(.styles, values: playlist.rules.styles)
            ruleRow(.subjects, values: playlist.rules.subjects)

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

            VStack(alignment: .leading, spacing: 10) {
                Eyebrow("Słowa kluczowe")
                TextField("np. woodblock, sea, flowers", text: $playlist.rules.query)
                    .textInputAutocapitalization(.never)
                    .padding(12)
                    .background(Theme.card, in: RoundedRectangle(cornerRadius: 12))
                    .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Theme.hairline))
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

    private func ruleRow(_ kind: FacetKind, values: [String]) -> some View {
        Button {
            facetSheet = kind
        } label: {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Label(kind.title, systemImage: kind.icon)
                        .font(.headline)
                        .foregroundStyle(Theme.ink)
                    Spacer()
                    Text(values.isEmpty ? "dowolne" : "\(values.count)")
                        .foregroundStyle(Theme.inkSoft)
                    Image(systemName: "chevron.right")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(Theme.inkSoft)
                }
                if !values.isEmpty {
                    FlowLayout(spacing: 6) {
                        ForEach(values, id: \.self) { TagLabel(text: $0) }
                    }
                }
            }
            .padding(14)
            .background(Theme.card, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(Theme.hairline))
        }
        .buttonStyle(.plain)
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
                Text("Żadne dzieło w bibliotece nie spełnia tych reguł.")
                    .font(.subheadline)
                    .foregroundStyle(Theme.inkSoft)
            }
        }
    }

    // MARK: Actions

    private func refreshPreview() async {
        try? await Task.sleep(for: .milliseconds(250))
        guard !Task.isCancelled else { return }
        let result = try? await model.backend.previewRules(playlist.rules)
        withAnimation(.snappy) { preview = result }
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
            _ = try await model.backend.savePlaylist(playlist)
            await model.refreshPlaylists()
            model.toast = "Zapisano „\(playlist.name)”"
            dismiss()
        } catch {
            model.show(error)
        }
    }
}

/// Facet picker editing playlist rules instead of a library query.
struct RuleFacetPicker: View {
    @Environment(AppModel.self) private var model
    let kind: FacetKind
    @Binding var rules: PlaylistRules
    @State private var query = LibraryQuery()

    var body: some View {
        FacetPicker(kind: kind, query: $query)
            .onAppear {
                query.artists = rules.artists
                query.styles = rules.styles
                query.subjects = rules.subjects
            }
            .onChange(of: query) { _, new in
                rules.artists = new.artists
                rules.styles = new.styles
                rules.subjects = new.subjects
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
