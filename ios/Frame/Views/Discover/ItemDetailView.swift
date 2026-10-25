import SwiftUI

/// One picture: original vs. how it will look on the e-paper, its story,
/// palette, and actions (show now, favourite, add to playlist). On "Na
/// ramce" the picture is cropped right on the preview, and showing it or
/// adding it to a playlist saves that crop first.
struct ItemDetailView: View {
    @Environment(AppModel.self) private var model
    let itemID: String
    @State private var item: Item?
    @State private var view = ViewMode.original
    @State private var showingPlaylists = false
    @State private var draft = FramingDraft()
    /// Crops saved here: the preview asks for them by name, as the one
    /// cached from before shows the old crop.
    @State private var applied: FramingCrops?
    /// The preview last loaded: the crop windows wait for the first one, so
    /// a half-loaded preview never shows.
    @State private var loadedPreview: ImageRef?
    @State private var saving = false

    enum ViewMode: String, CaseIterable {
        case original = "Oryginał"
        case frame = "Na ramce"
    }

    var body: some View {
        ScrollView {
            if let item {
                VStack(alignment: .leading, spacing: 24) {
                    picture(item)
                    titleBlock(item)
                    actions(item)
                    if !item.colors.isEmpty { palette(item) }
                    if !item.description.isEmpty {
                        VStack(alignment: .leading, spacing: 10) {
                            Eyebrow("O dziele")
                            Text(item.description)
                                .font(.serif(17))
                                .lineSpacing(5)
                                .foregroundStyle(Theme.ink.opacity(0.9))
                                .textSelection(.enabled)
                        }
                    }
                    facts(item)
                    if !(item.styles + item.subjects).isEmpty {
                        VStack(alignment: .leading, spacing: 10) {
                            Eyebrow("Styl i tematy")
                            FlowLayout(spacing: 6) {
                                ForEach(item.styles + item.subjects, id: \.self) { TagLabel(text: $0) }
                            }
                        }
                    }
                }
                .padding(.horizontal, Theme.gutter)
                .padding(.bottom, 40)
            } else {
                ProgressView().padding(.top, 120)
            }
        }
        .background(Theme.paper)
        .navigationBarTitleDisplayMode(.inline)
        .task(id: itemID) {
            do {
                item = try await model.backend.item(id: itemID)
            } catch {
                model.show(error)
            }
        }
        .task(id: view == .frame ? draftKey : "") { await loadFraming() }
        .sheet(isPresented: $showingPlaylists) {
            if let item { AddToPlaylistSheet(item: item, beforeAdding: saveCrop) }
        }
    }

    // MARK: Crop

    /// Item, orientation and presentation: a crop belongs to all three.
    private var draftKey: String {
        [itemID, model.settings?.presentationKey ?? ""].joined(separator: "|")
    }

    private var cropping: Bool {
        draft.key == draftKey && draft.view?.windows.isEmpty == false
    }

    private var previewRef: ImageRef {
        let current = draft.key == draftKey
        return .framePreview(
            itemID, settings: model.settings,
            framing: current ? draft.trial ?? applied : nil
        )
    }

    /// The crop as the server has it, once "Na ramce" is opened; an edited
    /// one is kept while the settings stay the same.
    private func loadFraming() async {
        let key = draftKey
        guard view == .frame, draft.key != key else { return }
        draft = FramingDraft()
        applied = nil
        let orientation = model.settings?.orientation ?? "landscape"
        guard let loaded = await FramingDraft.load(model.backend, itemID: itemID, orientation: orientation, key: key),
              key == draftKey
        else { return }
        draft = loaded
    }

    /// Saves the crop edited on "Na ramce", if it was; false if that failed,
    /// so nothing goes out with the old crop.
    private func saveCrop() async -> Bool {
        guard draft.key == draftKey, let change = draft.change else { return true }
        saving = true
        defer { saving = false }
        let key = draft.key
        do {
            let saved = try await model.applyFraming(itemID: itemID, change)
            guard key == draft.key else { return true }
            draft = FramingDraft(saved: saved, key: key)
            applied = draft.savedCrops
            return true
        } catch {
            model.show(error)
            return false
        }
    }

    private func show(_ hold: HoldSpec) async {
        let cropped = draft.key == draftKey && draft.change != nil
        guard await saveCrop() else { return }
        if cropped, hold == .untilNextChange, model.player?.current?.item?.id == itemID {
            // Already on the frame: the server redraws it with the new crop.
            model.toast = "Nowy kadr — ramka odświeża obraz"
            await model.followPlayer()
            return
        }
        await model.show(itemID: itemID, hold: hold)
    }

    // MARK: Sections

    private func picture(_ item: Item) -> some View {
        VStack(spacing: 12) {
            Group {
                if view == .original {
                    ArtImage(ref: .image(item.id), placeholder: item.placeholderColor, maxPixel: 1800, contentMode: .fit)
                        .aspectRatio(CGFloat(aspect(item)), contentMode: .fit)
                        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                        .shadow(color: .black.opacity(0.22), radius: 16, y: 12)
                } else {
                    framePreview(item)
                }
            }
            .frame(maxHeight: 460)
            .frame(maxWidth: .infinity)
            Picker("Widok", selection: $view.animation(.easeInOut)) {
                ForEach(ViewMode.allCases, id: \.self) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .frame(maxWidth: 260)
            if view == .frame {
                if cropping {
                    CropTools(itemID: item.id, draft: $draft)
                        .disabled(saving)
                }
                Text(frameHint)
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .multilineTextAlignment(.center)
                    .contentTransition(.opacity)
                if cropping, draft.changed {
                    Button {
                        Task {
                            if await saveCrop() { model.toast = "Zapisano kadr" }
                        }
                    } label: {
                        Label("Zapisz kadr", systemImage: "crop").toolChip()
                    }
                    .buttonStyle(.plain)
                    .disabled(saving)
                }
            }
        }
        .padding(.top, 8)
    }

    /// The picture as the frame will show it, with its crop windows over it.
    private func framePreview(_ item: Item) -> some View {
        let ref = previewRef
        return FramedArtwork(
            ref: ref, aspectRatio: model.isPortrait ? 9.0 / 16.0 : 16.0 / 9.0,
            placeholder: item.placeholderColor, moulding: 7
        ) {
            if draft.key == draftKey, loadedPreview != nil {
                CropWindows(itemID: item.id, draft: $draft)
                    .transition(.opacity)
            }
        }
        .environment(\.artImageLoaded) { loaded in
            guard loaded == previewRef else { return }
            withAnimation(.easeOut(duration: 0.3)) { loadedPreview = loaded }
        }
        .overlay {
            if loadedPreview != ref {
                LoadingBadge(text: "Wczytuję podgląd…")
            }
        }
    }

    private var frameHint: String {
        guard cropping else {
            return "Kadr i passe-partout z bieżącymi ustawieniami, w oryginalnych kolorach. Kolory dopasowuje dopiero ekran."
        }
        return draft.changed
            ? "Nowy kadr zapisze się po „Pokaż na ramce” albo dodaniu do playlisty."
            : "Przesuń obraz palcem albo rozsuń dwa palce, żeby go wykadrować. Kolory dopasowuje dopiero ekran."
    }

    private func aspect(_ item: Item) -> Double {
        guard let w = item.width, let h = item.height, w > 0, h > 0 else { return 4 / 3 }
        return Double(w) / Double(h)
    }

    private func titleBlock(_ item: Item) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Eyebrow(Names.source(item.source), color: Theme.vermilion)
            Text(item.title.isEmpty ? "Bez tytułu" : item.title)
                .font(.serif(30, weight: .semibold))
                .foregroundStyle(Theme.ink)
                .fixedSize(horizontal: false, vertical: true)
            if !item.artist.isEmpty {
                Text(item.artist).font(.serif(19)).foregroundStyle(Theme.ink)
            }
            if !item.artistBio.isEmpty {
                Text(item.artistBio).font(.subheadline).foregroundStyle(Theme.inkSoft)
            }
            if !item.dateText.isEmpty {
                Text(item.dateText).font(.subheadline).foregroundStyle(Theme.inkSoft)
            }
        }
    }

    private func actions(_ item: Item) -> some View {
        HStack(spacing: 12) {
            Menu {
                ForEach(HoldSpec.allCases) { spec in
                    Button(spec.label) {
                        Task { await show(spec) }
                    }
                }
            } label: {
                Label("Pokaż na ramce", systemImage: "photo.artframe")
                    .font(.headline)
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 15)
                    .background(Theme.accent, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            } primaryAction: {
                Task { await show(.untilNextChange) }
            }
            .disabled(saving)
            iconButton(item.favorite ? "heart.fill" : "heart", tint: item.favorite ? Theme.vermilion : Theme.ink) {
                Task {
                    if let updated = await model.setFavorite(item.id, !item.favorite) { self.item = updated }
                }
            }
            iconButton("text.badge.plus", tint: Theme.ink) { showingPlaylists = true }
            Menu {
                Button(item.excluded ? "Pokazuj ponownie" : "Nie pokazuj na ramce", systemImage: "eye.slash") {
                    Task {
                        if let updated = try? await model.backend.setExcluded(id: item.id, !item.excluded) {
                            self.item = updated
                        }
                    }
                }
                if let url = URL(string: item.url), !item.url.isEmpty {
                    Link(destination: url) { Label("Otwórz w muzeum", systemImage: "safari") }
                }
            } label: {
                Image(systemName: "ellipsis")
                    .font(.headline)
                    .foregroundStyle(Theme.ink)
                    .frame(width: 50, height: 50)
                    .background(Theme.card, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(Theme.hairline))
            }
        }
    }

    private func iconButton(_ symbol: String, tint: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.headline)
                .foregroundStyle(tint)
                .frame(width: 50, height: 50)
                .background(Theme.card, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(Theme.hairline))
                .contentTransition(.symbolEffect(.replace))
        }
        .buttonStyle(PressableStyle())
    }

    private func palette(_ item: Item) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Eyebrow("Kolorystyka")
            HStack(spacing: 10) {
                ForEach(Array(item.colors.prefix(6).enumerated()), id: \.offset) { _, swatch in
                    VStack(spacing: 6) {
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .fill(Color(hexString: swatch.hex) ?? Theme.mat)
                            .frame(height: 52)
                            .overlay(
                                RoundedRectangle(cornerRadius: 8, style: .continuous)
                                    .strokeBorder(.black.opacity(0.08))
                            )
                        Text("\(Int(swatch.weight * 100))%")
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(Theme.inkSoft)
                    }
                }
            }
            if !item.colorTags.isEmpty {
                FlowLayout(spacing: 6) {
                    ForEach(item.colorTags, id: \.self) { tag in
                        TagLabel(text: ColorTag.name(tag), swatch: ColorTag.color(tag))
                    }
                }
            }
        }
    }

    private func facts(_ item: Item) -> some View {
        Card {
            fact("Technika", item.medium)
            fact("Rodzaj", item.classification)
            fact("Pochodzenie", item.culture)
            fact("Kolekcja", item.museum)
            fact("Licencja", item.license)
            if let score = item.suitability {
                HStack {
                    Text("Na e-papierze").foregroundStyle(Theme.inkSoft)
                    Spacer()
                    Gauge(value: score) { EmptyView() }
                        .gaugeStyle(.accessoryLinearCapacity)
                        .tint(score > 0.75 ? Theme.good : score > 0.6 ? Theme.warn : Theme.bad)
                        .frame(width: 120)
                    Text(score > 0.75 ? "świetnie" : score > 0.6 ? "dobrze" : "słabiej")
                        .font(.subheadline.weight(.medium))
                }
                .font(.subheadline)
            }
            if item.showCount > 0 {
                fact("Na ramce", "\(item.showCount)×, ostatnio \(When.ago(item.lastShownAt) ?? "")")
            }
        }
    }

    @ViewBuilder
    private func fact(_ label: String, _ value: String) -> some View {
        if !value.isEmpty {
            HStack(alignment: .firstTextBaseline) {
                Text(label).foregroundStyle(Theme.inkSoft)
                Spacer(minLength: 16)
                Text(value).multilineTextAlignment(.trailing).foregroundStyle(Theme.ink)
            }
            .font(.subheadline)
        }
    }
}

/// Pick a manual playlist to add the picture to.
struct AddToPlaylistSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let item: Item
    /// Run first, e.g. to save the crop edited for it; false stops the adding.
    var beforeAdding: () async -> Bool = { true }
    @State private var newName = ""

    private var manual: [PlaylistSummary] { model.playlists.filter { $0.kind == .manual } }

    var body: some View {
        NavigationStack {
            List {
                Section("Nowa playlista") {
                    HStack {
                        TextField("Nazwa, np. Do sypialni", text: $newName)
                        Button("Utwórz") { Task { await create() } }
                            .disabled(newName.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                }
                if !manual.isEmpty {
                    Section("Twoje playlisty") {
                        ForEach(manual) { playlist in
                            Button {
                                Task { await add(to: playlist.id) }
                            } label: {
                                HStack {
                                    Text(playlist.name).foregroundStyle(Theme.ink)
                                    Spacer()
                                    Text(Names.works(playlist.itemCount)).foregroundStyle(Theme.inkSoft)
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Dodaj do playlisty")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Zamknij") { dismiss() } }
            }
        }
        .presentationDetents([.medium])
    }

    private func create() async {
        guard await beforeAdding() else { return }
        let playlist = Playlist(name: newName, kind: .manual, itemIds: [item.id])
        do {
            _ = try await model.backend.savePlaylist(playlist)
            await model.refreshPlaylists()
            model.toast = "Utworzono „\(newName)”"
            dismiss()
        } catch { model.show(error) }
    }

    private func add(to id: Int) async {
        guard await beforeAdding() else { return }
        do {
            _ = try await model.backend.addToPlaylist(id: id, itemIDs: [item.id])
            await model.refreshPlaylists()
            model.toast = "Dodano do playlisty"
            dismiss()
        } catch { model.show(error) }
    }
}
