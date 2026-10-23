import PhotosUI
import SwiftUI
import UIKit

/// Pick a photo, choose a preset, send it to the frame.
struct SendView: View {
    @Environment(AppModel.self) private var model
    @State private var selection: PhotosPickerItem?
    @State private var imageData: Data?
    @State private var preset: RenderPreset = .photo
    @State private var title = ""
    @State private var status: String?
    @State private var sending = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    PhotosPicker(selection: $selection, matching: .images) {
                        Label(imageData == nil ? "Wybierz zdjęcie" : "Zmień zdjęcie",
                              systemImage: "photo.on.rectangle")
                    }
                    if let imageData, let image = UIImage(data: imageData) {
                        Image(uiImage: image)
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(maxHeight: 240)
                    }
                }
                Section("Ustawienia") {
                    TextField("Tytuł", text: $title)
                    Picker("Styl", selection: $preset) {
                        ForEach(RenderPreset.allCases) { Text($0.label).tag($0) }
                    }
                }
                Section {
                    Button {
                        Task { await send() }
                    } label: {
                        if sending {
                            ProgressView()
                        } else {
                            Text("Wyślij na ramkę")
                        }
                    }
                    .disabled(imageData == nil || sending || model.api == nil)
                    if let status {
                        Text(status).font(.footnote).foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("Wyślij")
            .onChange(of: selection) { _, item in
                Task { imageData = try? await item?.loadTransferable(type: Data.self) }
            }
        }
    }

    private func send() async {
        guard let api = model.api, let data = imageData else { return }
        sending = true
        defer { sending = false }
        status = String(localized: "Przygotowuję obraz i budzę ramkę…")
        do {
            let result = try await api.display(
                image: data, filename: "photo.jpg", preset: preset, title: title
            )
            if result.fetched == true {
                status = String(localized: "Ramka pobrała obraz.")
            } else {
                status = result.message ?? String(localized: "Wysłano.")
            }
            await model.refresh()
        } catch {
            status = error.localizedDescription
        }
    }
}
