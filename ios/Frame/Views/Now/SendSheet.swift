import PhotosUI
import SwiftUI
import UIKit

/// "Zdjęcie na ramkę": one photo from the camera roll, shown once. Picked,
/// it goes to the server as a photo sent once; here it gets its look (over
/// the whole frame or in a passe-partout) and its crop on the frame's
/// preview, then goes on the frame now or next in the queue, and into the
/// playlist "Historia przesłanych". Its style is always automatic.
struct SendSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var selection: PhotosPickerItem?
    /// The photo as the server has it, once uploaded.
    @State private var item: Item?
    @State private var uploading = false
    /// As chosen here; the server's (`item.look`) follows it.
    @State private var look: Look?
    @State private var hold = HoldSpec.untilNextChange
    @State private var draft = FramingDraft()
    /// Crops saved here: the preview asks for them by name, as the one
    /// cached from before shows the old crop.
    @State private var applied: FramingCrops?
    @State private var loadedPreview: ImageRef?
    @State private var cropping = false
    @State private var sending = false
    /// Shown or queued: the photo stays on the server.
    @State private var sent = false

    /// Ways to hold it; "Na stałe" is for the library's works.
    private static let holds = HoldSpec.allCases.filter { $0 != .forever }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    photoArea
                    if item != nil, let look = Binding($look) {
                        lookSection(look)
                        holdSection
                        actions
                    }
                }
                .padding(Theme.gutter)
                .animation(.easeInOut(duration: 0.2), value: look?.fit)
            }
            .background(Theme.paper)
            .navigationTitle("Zdjęcie na ramkę")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Anuluj") { dismiss() }
                }
            }
            .onChange(of: selection) { _, picked in
                guard let picked else { return }
                Task { await upload(picked) }
            }
            .task(id: look) { await applyLook() }
            .task(id: draftKey) { await loadFraming() }
            .fullScreenCover(isPresented: $cropping) {
                if let item {
                    CropScreen(
                        itemID: item.id, preview: previewRef, aspectRatio: frameAspect,
                        onFrame: model.player?.current?.item?.id == item.id,
                        draft: $draft, save: saveCrop
                    )
                }
            }
        }
        .presentationDetents([.large])
        .onAppear {
            if look == nil { look = Look(model.settings?.photo ?? FrameSettings.defaults.photo) }
        }
        .onDisappear {
            // Closed without sending (the crop screen covering it is not closing).
            if !sent, !cropping, let item { discard(item) }
        }
    }

    // MARK: Photo

    private var frameAspect: CGFloat { model.isPortrait ? 9.0 / 16.0 : 16.0 / 9.0 }

    @ViewBuilder
    private var photoArea: some View {
        if let item {
            VStack(spacing: 12) {
                framePreview(item)
                    .frame(maxHeight: 400)
                    .frame(maxWidth: .infinity)
                Text("Dotknij podglądu, żeby wykadrować zdjęcie.")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .multilineTextAlignment(.center)
                PhotosPicker(selection: $selection, matching: .images) {
                    Label("Inne zdjęcie", systemImage: "photo.on.rectangle")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(Theme.accent)
                }
                .disabled(uploading || sending)
            }
            .padding(.top, 4)
        } else if uploading {
            FramedArtwork(ref: nil, aspectRatio: frameAspect, moulding: 7)
                .overlay { LoadingBadge(text: "Przygotowuję zdjęcie…") }
                .frame(maxHeight: 400)
                .frame(maxWidth: .infinity)
                .padding(.top, 4)
        } else {
            PhotosPicker(selection: $selection, matching: .images) {
                VStack(spacing: 12) {
                    Image(systemName: "photo.on.rectangle.angled")
                        .font(.system(size: 40, weight: .light))
                    Text("Wybierz zdjęcie z rolki")
                        .font(.serif(18, weight: .medium))
                }
                .foregroundStyle(Theme.inkSoft)
                .frame(maxWidth: .infinity, minHeight: 220)
                .background(
                    RoundedRectangle(cornerRadius: Theme.corner)
                        .strokeBorder(Theme.hairline, style: StrokeStyle(lineWidth: 1.5, dash: [6, 5]))
                )
            }
            .buttonStyle(.plain)
        }
    }

    /// The photo as the frame will show it, in the frame's proportions; a
    /// tap opens it on the crop screen once its crop is loaded.
    private func framePreview(_ item: Item) -> some View {
        let ref = previewRef
        let ready = draft.key == draftKey && draft.view?.windows.isEmpty == false
        return FramedArtwork(ref: ref, aspectRatio: frameAspect, moulding: 7)
            .environment(\.artImageLoaded) { loaded in
                guard loaded == previewRef else { return }
                withAnimation(.easeOut(duration: 0.3)) { loadedPreview = loaded }
            }
            .overlay {
                if uploading {
                    LoadingBadge(text: "Przygotowuję zdjęcie…")
                } else if loadedPreview != ref {
                    LoadingBadge(text: "Wczytuję podgląd…")
                }
            }
            .contentShape(Rectangle())
            .onTapGesture {
                if ready, !uploading { cropping = true }
            }
            .accessibilityAddTraits(ready ? .isButton : [])
            .accessibilityHint(Text(ready ? "Otwiera kadrowanie na całym ekranie" : ""))
    }

    private func upload(_ picked: PhotosPickerItem) async {
        uploading = true
        defer { uploading = false }
        do {
            guard let original = try await picked.loadTransferable(type: Data.self) else { return }
            var photo = await Task.detached(priority: .userInitiated) { PhotoUpload(original: original) }.value
            photo.title = PickedPhoto.title(photo.takenAt)
            photo.look = look
            let uploaded = try await model.backend.uploadPhoto(photo)
            guard selection == picked else {  // another one was picked meanwhile
                discard(uploaded)
                return
            }
            if let previous = item { discard(previous) }
            draft = FramingDraft()
            applied = nil
            item = uploaded
            look = uploaded.look ?? look
        } catch {
            model.show(error)
        }
    }

    /// A photo uploaded here but never sent leaves the server.
    private func discard(_ photo: Item) {
        let backend = model.backend
        Task { try? await backend.deleteItem(id: photo.id) }
    }

    // MARK: Look and crop

    /// The settings with this photo's look, as the server shows it; the
    /// preview's address changes with it.
    private var previewSettings: FrameSettings {
        var settings = model.settings ?? .defaults
        if let look = item?.look { settings.photo = settings.photo.with(look) }
        return settings
    }

    /// Photo, orientation and look: a crop belongs to all three.
    private var draftKey: String {
        guard let item else { return "" }
        return [item.id, previewSettings.orientation, item.look?.key ?? ""].joined(separator: "|")
    }

    private var previewRef: ImageRef? {
        guard let item else { return nil }
        let current = draft.key == draftKey
        return .framePreview(item.id, settings: previewSettings, framing: current ? draft.trial ?? applied : nil)
    }

    /// The look chosen goes to the server, which frames the photo with it.
    private func applyLook() async {
        guard let item, let look, item.look != look else { return }
        do {
            let updated = try await model.backend.setLook(itemID: item.id, look)
            if self.item?.id == updated.id { self.item = updated }
        } catch {
            if !error.isCancellation { model.show(error) }
        }
    }

    /// The crop as the server has it for the photo's look.
    private func loadFraming() async {
        let key = draftKey
        guard let item, !key.isEmpty, draft.key != key else { return }
        draft = FramingDraft()
        applied = nil
        guard let loaded = await FramingDraft.load(
            model.backend, itemID: item.id, orientation: previewSettings.orientation, key: key
        ), key == draftKey
        else { return }
        draft = loaded
    }

    /// "Zapisz kadr" on the crop screen.
    private func saveCrop() async -> Bool {
        guard let item, draft.key == draftKey, let change = draft.change else { return true }
        let key = draft.key
        do {
            let saved = try await model.applyFraming(itemID: item.id, change)
            guard key == draft.key else { return true }
            draft = FramingDraft(saved: saved, key: key)
            applied = draft.savedCrops
            return true
        } catch {
            model.show(error)
            return false
        }
    }

    // MARK: Sections

    private func lookSection(_ look: Binding<Look>) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Eyebrow("Jak pokazać")
            Picker("Jak pokazać", selection: look.fit) {
                Text("Na całą ramkę").tag("fill")
                Text("Z passe-partout").tag("fit")
            }
            .pickerStyle(.segmented)
            if look.wrappedValue.fit == "fit" {
                // Six swatches: one row where they fit, else two rows of three.
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 10) { matSwatches(look) }
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3), spacing: 10) {
                        matSwatches(look)
                    }
                }
                .transition(.opacity)
            }
            Text(look.wrappedValue.fit == "fit"
                ? "Całe zdjęcie w okienku passe-partout. Dotknij podglądu, żeby zmienić kadr albo kształt okienka."
                : "Zdjęcie na całym ekranie; to, co się nie mieści, zostaje przycięte.")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
                .fixedSize(horizontal: false, vertical: true)
        }
        .disabled(uploading || sending)
    }

    private func matSwatches(_ look: Binding<Look>) -> some View {
        ForEach(MatSwatch.names, id: \.self) { name in
            MatSwatch(name: name, selected: look.wrappedValue.mat == name) {
                look.wrappedValue.mat = name
            }
        }
    }

    private var holdSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Eyebrow("Jak długo")
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(Self.holds) { spec in
                        Chip(title: spec.label, selected: hold == spec) { hold = spec }
                    }
                }
            }
        }
    }

    /// Now, or next in the queue.
    private var actions: some View {
        HStack(spacing: 12) {
            Button {
                Task { await show() }
            } label: {
                Label("Pokaż na ramce", systemImage: "photo.artframe")
            }
            .buttonStyle(ActionButtonStyle(prominent: true))
            Button {
                Task { await queue() }
            } label: {
                Label("Dodaj do kolejki", systemImage: QueueButton.symbol)
            }
            .buttonStyle(ActionButtonStyle())
        }
        .disabled(uploading || sending || item?.look != look)
    }

    private func show() async {
        guard let item, await saveCrop() else { return }
        sent = true
        dismiss()  // the bar under the picture follows it onto the frame
        await model.show(itemID: item.id, hold: hold)
        await model.refreshPlaylists()  // it joined "Historia przesłanych"
    }

    private func queue() async {
        guard let item, await saveCrop() else { return }
        sending = true
        defer { sending = false }
        await model.queueNext(itemID: item.id)
        guard model.isQueued(item.id) else { return }
        sent = true
        dismiss()
        await model.refreshPlaylists()  // it joined "Historia przesłanych"
    }
}
