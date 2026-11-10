import PhotosUI
import SwiftUI

/// Konfiguracja → Wyświetlanie → Przykładowe zdjęcia: up to eight photos
/// from the phone that Prezentacja previews photos on: Passe-partout and
/// Wypełnij the first, the Multi grids all of them in this order, which a
/// photo held and dragged changes (Mateusz 2026-11-09: "Przenieśmy to
/// ustawienie do konfiguracji. I tam wgram te 8 zdjęć."). They are sent
/// once (with a look), so they stay out of the library's lists and the
/// frame's rotation.
struct SamplePhotosSection: View {
    @Environment(AppModel.self) private var model
    let settings: FrameSettings
    @State private var picked: [PhotosPickerItem] = []
    @State private var uploading = 0
    /// The order while a photo is dragged (nil: as saved).
    @State private var arranged: [String]?
    @State private var dragged: String?

    static let most = 8

    private var photos: [String] { arranged ?? settings.multiPhotos ?? [] }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Przykładowe zdjęcia", subtitle: "Do podglądu Prezentacji zdjęć")
            Card {
                Text("Na nich Prezentacja pokazuje zdjęcia: Passe-partout i Wypełnij na pierwszym, Multi każdy układ w tej kolejności (przy czterech zdjęciach na planszy cztery pierwsze). Przytrzymaj zdjęcie i przesuń, aby zmienić kolejność. Nie trafiają do biblioteki ani na ramkę.")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .fixedSize(horizontal: false, vertical: true)
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 6), count: 4), spacing: 6) {
                    ForEach(photos, id: \.self) { id in
                        tile(id)
                            .onDrag {
                                arranged = photos
                                dragged = id
                                return NSItemProvider(object: id as NSString)
                            } preview: {
                                // Drawn apart from the page: `ArtImage` needs the model.
                                square(id).frame(width: 80, height: 80).environment(model)
                            }
                            .onDrop(of: [.text], delegate: SampleDrop(target: id, order: $arranged, dragged: $dragged, save: save))
                    }
                    ForEach(0 ..< max(Self.most - photos.count, 0), id: \.self) { index in
                        if index < uploading {
                            slot.overlay { ProgressView() }
                        } else {
                            slot
                        }
                    }
                }
                .onDrop(of: [.text], delegate: SampleDrop(target: nil, order: $arranged, dragged: $dragged, save: save))
                if photos.count < Self.most {
                    Divider()
                    PhotosPicker(
                        selection: $picked,
                        maxSelectionCount: Self.most - photos.count,
                        selectionBehavior: .ordered,
                        matching: .images
                    ) {
                        Label(photos.isEmpty ? "Dodaj zdjęcia" : "Dodaj kolejne", systemImage: "photo.badge.plus")
                    }
                    .disabled(uploading > 0)
                }
            }
        }
        .onChange(of: settings.multiPhotos) { arranged = nil }  // saved, or changed elsewhere
        .onDisappear { arranged = nil; dragged = nil }  // a drag let go outside the grid
        .onChange(of: picked) { _, items in
            guard !items.isEmpty else { return }
            picked = []
            Task { await upload(items) }
        }
    }

    private var slot: some View {
        RoundedRectangle(cornerRadius: 4, style: .continuous)
            .strokeBorder(Theme.ink.opacity(0.15), style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
            .aspectRatio(1, contentMode: .fit)
    }

    /// A square whatever the photo's shape: the picture fills it and is
    /// cut to it (on its own it kept its size and spilled over the next
    /// tiles, Mateusz 2026-11-09).
    private func square(_ id: String) -> some View {
        Color.clear
            .aspectRatio(1, contentMode: .fit)
            .overlay { ArtImage(ref: .thumb(id), placeholder: Theme.mat, maxPixel: 240) }
            .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
            .contentShape(.dragPreview, RoundedRectangle(cornerRadius: 4, style: .continuous))
    }

    private func tile(_ id: String) -> some View {
        square(id)
            .overlay(alignment: .topTrailing) {
                Button {
                    remove(id)
                } label: {
                    GlassBadge(systemImage: "xmark", role: .small)
                        .padding(4)
                        // A finger's room towards the picture.
                        .padding([.leading, .bottom], 10)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Usuń przykładowe zdjęcie")
            }
    }

    private func upload(_ items: [PhotosPickerItem]) async {
        uploading = items.count
        defer { uploading = 0 }
        var added: [String] = []
        let look = Look(model.settings?.photo ?? FrameSettings.defaults.photo)
        for item in items {
            do {
                guard let original = try await item.loadTransferable(type: Data.self) else { continue }
                var photo = await Task.detached(priority: .userInitiated) { PhotoUpload(original: original) }.value
                photo.title = "Przykładowe zdjęcie"
                photo.look = look  // sent once: never listed nor shown on its own
                added.append(try await model.backend.uploadPhoto(photo).id)
                uploading = max(uploading - 1, 0)
            } catch {
                model.show(error)
            }
        }
        guard !added.isEmpty, var new = model.settings else { return }
        new.multiPhotos = Array(((new.multiPhotos ?? []) + added).prefix(Self.most))
        await model.saveSettings(new)
    }

    /// The order after a drag, as the photos stand now.
    private func save(_ order: [String]) {
        guard var new = model.settings, order != (new.multiPhotos ?? []) else {
            arranged = nil
            return
        }
        new.multiPhotos = order
        Task {
            await model.saveSettings(new)
            arranged = nil
        }
    }

    private func remove(_ id: String) {
        guard var new = model.settings else { return }
        new.multiPhotos = (new.multiPhotos ?? []).filter { $0 != id }
        let backend = model.backend
        Task {
            await model.saveSettings(new)
            try? await backend.deleteItem(id: id)
        }
    }
}

/// Moves the sample photo held over the one it is dragged onto; the order
/// is saved when it is let go.
private struct SampleDrop: DropDelegate {
    let target: String?
    @Binding var order: [String]?
    @Binding var dragged: String?
    let save: ([String]) -> Void

    func dropEntered(info: DropInfo) {
        guard let target, let dragged, dragged != target, var list = order,
              let from = list.firstIndex(of: dragged), let to = list.firstIndex(of: target)
        else { return }
        withAnimation(.snappy) {
            list.move(fromOffsets: IndexSet(integer: from), toOffset: to > from ? to + 1 : to)
            order = list
        }
    }

    func dropUpdated(info: DropInfo) -> DropProposal? {
        DropProposal(operation: dragged == nil ? .forbidden : .move)
    }

    func performDrop(info: DropInfo) -> Bool {
        guard dragged != nil, let list = order else { return false }
        dragged = nil
        save(list)
        return true
    }
}
