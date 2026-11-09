import PhotosUI
import SwiftUI

/// Konfiguracja → Wyświetlanie → Przykładowe zdjęcia: up to eight photos
/// from the phone that Prezentacja previews photos on (Passe-partout and
/// Wypełnij the first, Multi grids all of them in the order added) (Mateusz 2026-11-09: "Przenieśmy to ustawienie do konfiguracji.
/// I tam wgram te 8 zdjęć."). They are sent once (with a look), so they
/// stay out of the library's lists and the frame's rotation.
struct SamplePhotosSection: View {
    @Environment(AppModel.self) private var model
    let settings: FrameSettings
    @State private var picked: [PhotosPickerItem] = []
    @State private var uploading = 0

    static let most = 8

    private var photos: [String] { settings.multiPhotos ?? [] }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Przykładowe zdjęcia", subtitle: "Do podglądu Prezentacji zdjęć")
            Card {
                Text("Na nich Prezentacja pokazuje zdjęcia: Passe-partout i Wypełnij na pierwszym, Multi każdy układ w kolejności dodania (przy czterech zdjęciach na planszy cztery pierwsze). Nie trafiają do biblioteki ani na ramkę.")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .fixedSize(horizontal: false, vertical: true)
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 6), count: 4), spacing: 6) {
                    ForEach(photos, id: \.self) { id in
                        tile(id)
                    }
                    ForEach(0 ..< max(Self.most - photos.count, 0), id: \.self) { index in
                        if index < uploading {
                            slot.overlay { ProgressView() }
                        } else {
                            slot
                        }
                    }
                }
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

    private func tile(_ id: String) -> some View {
        ArtImage(ref: .thumb(id), placeholder: Theme.mat, maxPixel: 240)
            .aspectRatio(1, contentMode: .fit)
            .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
            .overlay(alignment: .topTrailing) {
                Button {
                    remove(id)
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.body)
                        .symbolRenderingMode(.palette)
                        .foregroundStyle(.white, .black.opacity(0.45))
                        .padding(3)
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
