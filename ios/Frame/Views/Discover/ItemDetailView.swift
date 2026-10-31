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
    /// Polish title and texts, once the server has them ("Polskie tytuły i
    /// opisy" in the settings); the museum's own while they are written.
    @State private var polish: PolishText?
    @State private var polishWaiting = false
    @State private var showOriginal = false
    /// What the model saw in the picture (keywords), once it has looked.
    @State private var seen: [String] = []
    /// The item the server was asked about, out of turn, as the card opened.
    @State private var described: String?
    /// "Pokaż na ramce" until the picture reached the frame (as on "Teraz").
    @State private var sending = false
    /// How the last sending ended, for a moment on the button.
    @State private var sent: Sent?
    @State private var taps = 0
    @State private var queueTaps = 0
    @State private var loadFailed = false
    /// The work's study as the card found it ("Przygotuj studium dzieła");
    /// the model's, while one is followed, wins.
    @State private var study: StudyView?
    @State private var studyOpen = false
    @State private var studyTaps = 0

    enum Sent { case done, failed }

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
            // One over the other while the work fades in over its placeholder.
            ZStack(alignment: .top) {
                if let item {
                    loaded(item)
                        .transition(.opacity)
                } else {
                    loading
                        .transition(.opacity)
                }
            }
            // Full width from the first frame, also before the work is here:
            // a lone spinner made the page (and its paper) a narrow strip.
            .frame(maxWidth: .infinity, alignment: .leading)
            .animation(.easeOut(duration: 0.3), value: item == nil)
        }
        .background(Theme.paper)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if let item { itemToolbar(item) }
        }
        .task(id: itemID) { await load() }
        .task(id: described) { await loadSeen() }
        .task(id: view == .frame ? draftKey : "") { await loadFraming() }
        .onChange(of: item) { _, item in
            if let item { ItemPeeks.keep(item) }
        }
        .navigationDestination(isPresented: $studyOpen) {
            DailyView(route: DailyRoute(day: nil, study: itemID))
        }
        .onAppear { model.topCard = itemID }
        .onDisappear {
            if model.topCard == itemID { model.topCard = nil }
        }
        .onChange(of: model.studyOnCard) { _, id in
            // "Studium dzieła gotowe" tapped while this card is on top.
            guard id == itemID else { return }
            model.studyOnCard = nil
            studyOpen = true
        }
        .sheet(isPresented: $showingPlaylists) {
            if let item { AddToPlaylistSheet(item: item, beforeAdding: saveCrop) }
        }
    }

    private func loaded(_ item: Item) -> some View {
        VStack(alignment: .leading, spacing: 24) {
            picture(item)
            titleBlock(item)
            actions(item)
            if !item.colors.isEmpty { palette(item) }
            about(item)
            studySection(item)
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
    }

    /// The work, at once from the last visit if there was one, then fresh
    /// from the server; keywords and Polish texts after it.
    private func load() async {
        loadFailed = false
        if item == nil { item = ItemPeeks.cards[itemID] }
        do {
            item = try await model.backend.item(id: itemID)
            if LaunchRoute.screen == "original" { opened = .original }  // CI screenshots
        } catch {
            if item == nil {
                loadFailed = true
                model.show(error)
            }
            return
        }
        // Keywords and Polish texts ahead of the background queue.
        _ = try? await model.backend.describe(itemID: itemID, wait: 0)
        described = itemID
        await loadStudy()
        await loadPolish()
    }

    /// Whether the work has a study; one on its way (asked before the app
    /// was closed) is followed on a card at the bottom.
    private func loadStudy() async {
        guard let found = try? await model.backend.study(itemID: itemID, wait: 0) else { return }
        study = found
        if found.isPending, let item {
            let name = title(item)
            Task { await model.resumeStudy(itemID: itemID, title: name, view: found) }
        }
    }

    // MARK: Loading

    /// The card before the work is here: the picture, title and artist of
    /// the tile it was opened from (or quiet shapes where there was none),
    /// laid out as the card will be, so the work fades in over them.
    private var loading: some View {
        let peek = ItemPeeks.tiles[itemID]
        return VStack(alignment: .leading, spacing: 24) {
            VStack(spacing: 12) {
                ArtImage(
                    ref: peek?.thumb ?? .thumb(itemID), placeholder: peek?.summary.placeholderColor ?? Theme.mat,
                    maxPixel: 700, contentMode: .fit, priority: .high
                )
                    .aspectRatio(CGFloat(peek?.summary.aspectRatio ?? 4.0 / 3.0), contentMode: .fit)
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                    .shadow(color: .black.opacity(0.22), radius: 16, y: 12)
                    .frame(maxHeight: 460)
                    .frame(maxWidth: .infinity)
                Picker("Widok", selection: .constant(ViewMode.original)) {
                    ForEach(ViewMode.allCases, id: \.self) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
                .frame(maxWidth: 260)
                .disabled(true)
            }
            .padding(.top, 8)
            if let summary = peek?.summary {
                peekTitle(summary)
            } else {
                TitleSkeleton()
            }
            HStack(spacing: 12) {
                Button {} label: { Label("Pokaż na ramce", systemImage: "photo.artframe") }
                    .buttonStyle(ActionButtonStyle(prominent: true))
                Button {} label: { Label("Dodaj do kolejki", systemImage: QueueButton.symbol) }
                    .buttonStyle(ActionButtonStyle())
            }
            .labelStyle(ActionLabelStyle())
            .disabled(true)
            .opacity(0.45)
            if loadFailed {
                Button("Spróbuj ponownie", systemImage: "arrow.clockwise") {
                    Task { await load() }
                }
                .buttonStyle(.bordered)
                .frame(maxWidth: .infinity)
            } else {
                ProgressView().frame(maxWidth: .infinity)
            }
        }
        .padding(.horizontal, Theme.gutter)
        .padding(.bottom, 40)
    }

    /// The title block as the tile knew it.
    private func peekTitle(_ summary: ItemSummary) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Eyebrow(Names.source(summary.source), color: Theme.vermilion)
            Text(summary.title.isEmpty ? "Bez tytułu" : summary.title)
                .font(.serif(30, weight: .semibold))
                .foregroundStyle(Theme.ink)
                .fixedSize(horizontal: false, vertical: true)
            if !summary.artist.isEmpty {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(summary.artist).font(.serif(19)).foregroundStyle(Theme.ink)
                    Image(systemName: "magnifyingglass")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(Theme.inkSoft)
                }
            }
            if !summary.dateText.isEmpty {
                Text(summary.dateText).font(.subheadline).foregroundStyle(Theme.inkSoft)
            }
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
            Task { await model.followPlayer() }  // the send bar shows the redraw
        } else {
            model.notices.done("Zapisano kadr")
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
        taps += 1
        sent = nil
        sending = true
        defer { sending = false }
        let cropped = draft.key == draftKey && draft.change != nil
        guard await saveCrop() else {
            sent = .failed
            return
        }
        if cropped, hold == .untilNextChange, model.player?.current?.item?.id == itemID {
            // Already on the frame: the server redraws it with the new crop.
            await model.followPlayer()
            sent = model.player?.lastError?.isEmpty ?? true ? .done : .failed
            return
        }
        sent = await model.show(itemID: itemID, hold: hold) ? .done : .failed
    }

    // MARK: Polish

    /// The Polish texts shown, unless the museum's own are asked for.
    private var shownPolish: PolishText? { showOriginal ? nil : polish }

    /// Asks the server for the work's Polish texts; one being written now
    /// (a few seconds, half a minute for a note from the picture) is waited
    /// for a few times. Without a key or with the switch off: nothing.
    private func loadPolish() async {
        polish = nil
        showOriginal = false
        for attempt in 0..<4 {
            guard let view = try? await model.backend.polish(itemID: itemID, wait: attempt == 0 ? 20 : 30),
                  !Task.isCancelled
            else { break }
            polish = view.text
            polishWaiting = view.status == "waiting"
            if !polishWaiting { break }
        }
        polishWaiting = false
    }

    /// Waits for the keywords asked for as the card opened.
    private func loadSeen() async {
        seen = []
        guard let id = described, id == itemID else { return }
        for attempt in 0..<3 {
            guard let view = try? await model.backend.describe(itemID: id, wait: attempt == 0 ? 20 : 30),
                  !Task.isCancelled
            else { return }
            seen = view.words
            if view.status != "waiting" { return }
        }
    }

    /// "O dziele": the museum's description, its Polish translation or a
    /// note written by the model, with where the text comes from.
    @ViewBuilder
    private func about(_ item: Item) -> some View {
        let text = shownPolish?.full ?? item.description
        if !text.isEmpty || polish != nil || polishWaiting {
            VStack(alignment: .leading, spacing: 10) {
                Eyebrow("O dziele")
                if !text.isEmpty {
                    Text(text)
                        .font(.serif(17))
                        .lineSpacing(5)
                        .foregroundStyle(Theme.ink.opacity(0.9))
                        .textSelection(.enabled)
                } else if showOriginal {
                    Text("Muzeum nie podaje opisu.")
                        .font(.subheadline)
                        .foregroundStyle(Theme.inkSoft)
                }
                if polishWaiting {
                    HStack(spacing: 8) {
                        ProgressView().controlSize(.small)
                        Text("Piszę po polsku…")
                    }
                    .font(.footnote)
                    .foregroundStyle(Theme.inkSoft)
                }
                if let polish { polishOrigin(polish) }
            }
        }
    }

    /// "Przygotuj studium dzieła" under "O dziele": Claude writes the work
    /// of the day's page for this work; the card at the bottom follows it
    /// and opens it once ready. A study made is kept: "Otwórz studium".
    @ViewBuilder
    private func studySection(_ item: Item) -> some View {
        if let state = model.studies[itemID] ?? study, state.status != "off" {
            VStack(alignment: .leading, spacing: 8) {
                if state.status == "ready" {
                    Button {
                        studyOpen = true
                    } label: {
                        Label("Otwórz studium", systemImage: "text.book.closed.fill")
                    }
                    .contextMenu {
                        Button("Przygotuj od nowa", systemImage: "arrow.clockwise") { prepareStudy(item, again: true) }
                    }
                } else if state.isPending {
                    Button {} label: {
                        Label {
                            Text("Przygotowuję studium…")
                        } icon: {
                            ProgressView().controlSize(.small)
                        }
                    }
                    .disabled(true)
                    studyNote("Postęp widać w dymku na dole; możesz w tym czasie przeglądać dalej.")
                } else {
                    let failed = state.status == "failed"
                    Button {
                        prepareStudy(item, again: failed)
                    } label: {
                        Label(failed ? "Spróbuj ponownie" : "Przygotuj studium dzieła", systemImage: "sparkles")
                    }
                    if failed, !state.error.isEmpty {
                        studyNote(state.error, color: Theme.bad)
                    }
                }
            }
            .buttonStyle(ActionButtonStyle())
            .labelStyle(ActionLabelStyle())
            .sensoryFeedback(.impact(weight: .light), trigger: studyTaps)
            .animation(.easeInOut(duration: 0.2), value: state.status)
        }
    }

    private func prepareStudy(_ item: Item, again: Bool = false) {
        studyTaps += 1
        let name = title(item)
        Task { await model.prepareStudy(itemID: item.id, title: name, again: again) }
    }

    private func studyNote(_ text: String, color: Color = Theme.inkSoft) -> some View {
        Text(text)
            .font(.footnote)
            .foregroundStyle(color)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func polishOrigin(_ polish: PolishText) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Image(systemName: "sparkles").foregroundStyle(Theme.inkSoft)
            Text(polish.isNote ? noteOrigin(polish) : "Tłumaczenie maszynowe")
                .foregroundStyle(Theme.inkSoft)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            Button(showOriginal ? "Pokaż po polsku" : "Pokaż oryginał") {
                withAnimation(.easeInOut) { showOriginal.toggle() }
            }
            .font(.footnote.weight(.semibold))
        }
        .font(.footnote)
    }

    private func noteOrigin(_ polish: PolishText) -> String {
        polish.sources.isEmpty
            ? "Notka napisana przez model"
            : "Notka napisana przez model na podstawie: \(polish.sources.joined(separator: ", "))"
    }

    // MARK: Sections

    private func picture(_ item: Item) -> some View {
        VStack(spacing: 12) {
            Group {
                if view == .original {
                    // The tile's thumbnail, already loaded, under the
                    // original until it is here.
                    ArtImage(
                        ref: .image(item.id), fallback: .thumb(item.id), placeholder: .clear,
                        maxPixel: 1800, contentMode: .fit, priority: .high
                    )
                        .background {
                            ArtImage(
                                ref: ItemPeeks.tiles[item.id]?.thumb ?? .thumb(item.id),
                                placeholder: item.placeholderColor, maxPixel: 700, contentMode: .fit, priority: .high
                            )
                        }
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
            Text(title(item))
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
            let bio = nonEmpty(shownPolish?.artistNote) ?? item.artistBio
            if !bio.isEmpty {
                Text(bio).font(.subheadline).foregroundStyle(Theme.inkSoft)
            }
            let date = nonEmpty(shownPolish?.date) ?? item.dateText
            if !date.isEmpty {
                Text(date).font(.subheadline).foregroundStyle(Theme.inkSoft)
            }
        }
    }

    private func title(_ item: Item) -> String {
        nonEmpty(shownPolish?.title) ?? (item.title.isEmpty ? "Bez tytułu" : item.title)
    }

    private func nonEmpty(_ text: String?) -> String? {
        guard let text, !text.isEmpty else { return nil }
        return text
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

    /// "Pokaż na ramce": until the next change on a tap, longer when held.
    /// It gives way under the finger, a spinner while the picture is on its
    /// way and a tick once it went out.
    private var showButton: some View {
        Button {
            Task { await show(.untilNextChange) }
        } label: {
            Label {
                Text(sending ? "Wysyłam…" : sent == .done ? "Wysłano" : "Pokaż na ramce")
            } icon: {
                if sending {
                    ProgressView().tint(Theme.paper)
                } else {
                    Image(systemName: sent == .done ? "checkmark" : "photo.artframe")
                        .contentTransition(.symbolEffect(.replace))
                }
            }
        }
        .buttonStyle(ActionButtonStyle(prominent: true))
        .contentShape(.contextMenuPreview, RoundedRectangle(cornerRadius: 14, style: .continuous))
        .contextMenu {
            ForEach(HoldSpec.allCases) { spec in
                Button(spec.label) {
                    Task { await show(spec) }
                }
            }
        }
        .disabled(saving || sending)
        .animation(.easeInOut(duration: 0.2), value: sending)
        .animation(.easeInOut(duration: 0.2), value: sent)
        .sensoryFeedback(.impact(weight: .medium), trigger: taps)
        .sensoryFeedback(trigger: sent) { _, outcome in
            switch outcome {
            case .done: return .success
            case .failed: return .error
            case nil: return nil
            }
        }
        .task(id: sent) {
            // The tick for a moment, then the button as it was.
            guard sent == .done else { return }
            try? await Task.sleep(for: .seconds(2.5))
            sent = nil
        }
    }

    /// "Dodaj do kolejki": shown at the next change; once it is first in
    /// line, the button says so.
    private func queueButton(_ item: Item) -> some View {
        let next = model.player?.queued?.first == item.id
        return Button {
            queueTaps += 1
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
        }
        .buttonStyle(ActionButtonStyle())
        .disabled(next || saving || sending)
        .sensoryFeedback(.impact(weight: .light), trigger: queueTaps)
        .sensoryFeedback(.success, trigger: next) { _, now in now }
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
            fact(item.kind == .artwork ? "Na obrazie" : "Na zdjęciu", seen.joined(separator: ", "))
            fact("Technika", nonEmpty(shownPolish?.medium) ?? item.medium)
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
            model.notices.done("Utworzono „\(newName)”")
            dismiss()
        } catch { model.show(error) }
    }

    private func add(to id: Int) async {
        guard await beforeAdding() else { return }
        do {
            _ = try await model.backend.addToPlaylist(id: id, itemIDs: [item.id])
            await model.refreshPlaylists()
            model.notices.done("Dodano do playlisty")
            dismiss()
        } catch { model.show(error) }
    }
}

/// What the app already knows of a work before its card loads: the tile it
/// was opened from, and the card itself from the last visit. The card shows
/// them at once instead of an empty page.
@MainActor
enum ItemPeeks {
    struct Tile {
        var summary: ItemSummary
        /// The picture the tile showed, so the card asks for the same one.
        var thumb: ImageRef
    }

    private(set) static var tiles: [String: Tile] = [:]
    private(set) static var cards: [String: Item] = [:]

    static func remember(_ summary: ItemSummary, thumb: ImageRef) {
        if tiles.count > 3000 { tiles.removeAll() }
        tiles[summary.id] = Tile(summary: summary, thumb: thumb)
    }

    static func keep(_ item: Item) {
        if cards.count > 200 { cards.removeAll() }
        cards[item.id] = item
    }
}

/// Where the title and artist will be, before anything is known of them.
private struct TitleSkeleton: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Capsule().fill(Theme.mat).frame(width: 70, height: 9)
            Capsule().fill(Theme.mat).frame(height: 24).padding(.trailing, 60)
            Capsule().fill(Theme.mat).frame(width: 150, height: 14)
        }
        .breathing()
        .accessibilityElement()
        .accessibilityLabel("Wczytuję dzieło")
    }
}
