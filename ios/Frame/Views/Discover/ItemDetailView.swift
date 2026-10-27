import SwiftUI

/// One picture: original vs. how it will look on the e-paper, its story,
/// palette, and actions (show now, queue next, favourite, add to playlist,
/// save to Photos).
/// Tapping the original opens it on the whole screen; tapping the preview on
/// "Na ramce" opens it there to be cropped.
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
    /// The preview last loaded: cropping waits for it, so a half-loaded
    /// preview never opens.
    @State private var loadedPreview: ImageRef?
    @State private var saving = false
    @State private var opened: Opened?
    @State private var savingPhoto = false

    /// What a tap on the picture opened on the whole screen.
    enum Opened: String, Identifiable {
        case original, crop
        var id: String { rawValue }
    }

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
        .toolbar {
            if let item { itemToolbar(item) }
        }
        .task(id: itemID) {
            do {
                item = try await model.backend.item(id: itemID)
                if LaunchRoute.screen == "original" { opened = .original }  // CI screenshots
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

    /// "Zapisz kadr" on the crop screen; the picture on the frame now is
    /// redrawn with it there.
    private func saveFromCropScreen() async -> Bool {
        guard draft.key == draftKey, draft.change != nil else { return true }
        let onFrame = model.player?.current?.item?.id == itemID
        guard await saveCrop() else { return false }
        if onFrame {
            model.toast = "Nowy kadr — ramka odświeża obraz"
            Task { await model.followPlayer() }
        } else {
            model.toast = "Zapisano kadr"
        }
        return true
    }

    /// Saves the crop edited, if it was; false if that failed, so nothing
    /// goes out with the old crop.
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
                        .contentShape(Rectangle())
                        .onTapGesture { opened = .original }
                        .accessibilityAddTraits(.isButton)
                        .accessibilityHint(Text("Otwiera obraz na całym ekranie"))
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
                Text(frameHint)
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .multilineTextAlignment(.center)
                    .contentTransition(.opacity)
            }
        }
        .padding(.top, 8)
        .fullScreenCover(item: $opened) { screen in
            switch screen {
            case .original:
                OriginalViewer(item: item)
            case .crop:
                CropScreen(
                    itemID: item.id, preview: previewRef,
                    aspectRatio: model.isPortrait ? 9.0 / 16.0 : 16.0 / 9.0,
                    placeholder: item.placeholderColor,
                    onFrame: model.player?.current?.item?.id == item.id,
                    draft: $draft, save: saveFromCropScreen
                )
            }
        }
    }

    /// The picture as the frame will show it; a tap opens it on the crop
    /// screen once its crop is loaded.
    private func framePreview(_ item: Item) -> some View {
        let ref = previewRef
        return FramedArtwork(
            ref: ref, aspectRatio: model.isPortrait ? 9.0 / 16.0 : 16.0 / 9.0,
            placeholder: item.placeholderColor, moulding: 7
        )
        .environment(\.artImageLoaded) { loaded in
            guard loaded == previewRef else { return }
            withAnimation(.easeOut(duration: 0.3)) { loadedPreview = loaded }
        }
        .overlay {
            if loadedPreview != ref {
                LoadingBadge(text: "Wczytuję podgląd…")
            }
        }
        .contentShape(Rectangle())
        .onTapGesture {
            if cropping { opened = .crop }
        }
        .accessibilityAddTraits(cropping ? .isButton : [])
        .accessibilityHint(Text(cropping ? "Otwiera kadrowanie na całym ekranie" : ""))
    }

    /// One short line under the preview.
    private var frameHint: String {
        cropping
            ? "Dotknij podglądu, żeby wykadrować obraz."
            : "Podgląd w oryginalnych kolorach. Kolory dopasowuje dopiero ekran."
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
                // Their other works, on Discover's search.
                Button {
                    model.artistSearch = item.artist
                } label: {
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text(item.artist).font(.serif(19)).foregroundStyle(Theme.ink)
                        Image(systemName: "magnifyingglass")
                            .font(.footnote.weight(.semibold))
                            .foregroundStyle(Theme.inkSoft)
                    }
                    .multilineTextAlignment(.leading)
                }
                .buttonStyle(.plain)
                .accessibilityHint(Text("Szuka innych dzieł tego autora"))
            }
            if !item.artistBio.isEmpty {
                Text(item.artistBio).font(.subheadline).foregroundStyle(Theme.inkSoft)
            }
            if !item.dateText.isEmpty {
                Text(item.dateText).font(.subheadline).foregroundStyle(Theme.inkSoft)
            }
        }
    }

    /// The two ways onto the frame, side by side: now, or next. Keeping it
    /// (favourite, playlist, hiding it) is in the navigation bar.
    private func actions(_ item: Item) -> some View {
        HStack(spacing: 12) {
            showButton
            queueButton(item)
        }
        .labelStyle(ActionLabelStyle())
    }

    /// "Pokaż na ramce": until the next change on a tap, longer from its menu.
    private var showButton: some View {
        Menu {
            ForEach(HoldSpec.allCases) { spec in
                Button(spec.label) {
                    Task { await show(spec) }
                }
            }
        } label: {
            Label("Pokaż na ramce", systemImage: "photo.artframe")
                .foregroundStyle(Theme.paper)  // dark text on the lighter dark-mode accent
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(Theme.accent, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        } primaryAction: {
            Task { await show(.untilNextChange) }
        }
        .disabled(saving)
    }

    /// "Dodaj do kolejki": shown at the next change; once it is first in
    /// line, the button says so.
    private func queueButton(_ item: Item) -> some View {
        let next = model.player?.queued?.first == item.id
        return Button {
            Task {
                guard await saveCrop() else { return }
                await model.queueNext(itemID: item.id)
            }
        } label: {
            Label(
                next ? "Następne na ramce" : "Dodaj do kolejki",
                systemImage: next ? "checkmark" : QueueButton.symbol
            )
            .contentTransition(.symbolEffect(.replace))
            .foregroundStyle(Theme.ink)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(Theme.card, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(Theme.hairline))
        }
        .buttonStyle(PressableStyle())
        .disabled(next || saving)
    }

    /// Favourite and the rest of the picture's options, top right.
    @ToolbarContentBuilder
    private func itemToolbar(_ item: Item) -> some ToolbarContent {
        ToolbarItemGroup(placement: .topBarTrailing) {
            Button {
                Task {
                    if let updated = await model.setFavorite(item.id, !item.favorite) { self.item = updated }
                }
            } label: {
                Image(systemName: item.favorite ? "heart.fill" : "heart")
                    .foregroundStyle(item.favorite ? Theme.vermilion : Theme.ink)
                    .contentTransition(.symbolEffect(.replace))
            }
            .accessibilityLabel(item.favorite ? "Usuń z ulubionych" : "Dodaj do ulubionych")
            Menu {
                Button("Dodaj do playlisty", systemImage: "text.badge.plus") { showingPlaylists = true }
                Button(item.excluded ? "Pokazuj ponownie" : "Nie pokazuj na ramce", systemImage: "eye.slash") {
                    Task {
                        if let updated = await model.setExcluded(item.id, !item.excluded) {
                            self.item = updated
                        }
                    }
                }
                if let url = URL(string: item.url), !item.url.isEmpty {
                    Divider()
                    Link(destination: url) { Label("Otwórz w muzeum", systemImage: "safari") }
                }
                // Last, under the museum link.
                Button("Zapisz w Zdjęciach", systemImage: "square.and.arrow.down") {
                    savingPhoto = true
                    Task {
                        await model.saveToPhotos(item)
                        savingPhoto = false
                    }
                }
                .disabled(savingPhoto)
            } label: {
                Image(systemName: "ellipsis.circle").foregroundStyle(Theme.ink)
            }
            .accessibilityLabel("Więcej")
        }
    }

    private func palette(_ item: Item) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Eyebrow("Kolorystyka")
            // Like the strip in "Teraz", taller, with the shares that fit.
            VStack(spacing: 6) {
                PaletteStrip(swatches: item.colors, height: 18, cornerRadius: 6)
                GeometryReader { geo in
                    let widths = PaletteStrip.widths(item.colors, in: geo.size.width)
                    HStack(spacing: PaletteStrip.spacing) {
                        ForEach(Array(item.colors.enumerated()), id: \.offset) { index, swatch in
                            Text(widths[index] >= 30 ? "\(Int(swatch.weight * 100))%" : "")
                                .font(.caption2.monospacedDigit())
                                .foregroundStyle(Theme.inkSoft)
                                .fixedSize()
                                .frame(width: widths[index])
                        }
                    }
                }
                .frame(height: 14)
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
                        .tint(score >= 0.72 ? Theme.good : score >= 0.45 ? Theme.warn : Theme.bad)
                        .frame(width: 120)
                    Text(score >= 0.72 ? "świetnie" : score >= 0.45 ? "dobrze" : "słabiej")
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
