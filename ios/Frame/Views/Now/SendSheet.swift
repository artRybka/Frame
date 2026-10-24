import PhotosUI
import SwiftUI
import UIKit

/// Send one photo from the camera roll, choosing how long it stays.
struct SendSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var selection: PhotosPickerItem?
    @State private var imageData: Data?
    @State private var preset = "photo"
    @State private var hold = HoldSpec.untilNextChange
    @State private var title = ""
    @State private var sending = false
    @State private var status: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    picker
                    VStack(alignment: .leading, spacing: 10) {
                        Eyebrow("Podpis")
                        TextField("Np. Wakacje na Helu", text: $title)
                            .padding(14)
                            .background(Theme.card, in: RoundedRectangle(cornerRadius: 12))
                            .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Theme.hairline))
                    }
                    VStack(alignment: .leading, spacing: 10) {
                        Eyebrow("Styl obrazu")
                        Picker("Styl", selection: $preset) {
                            ForEach(["photo", "painting", "graphic", "bw"], id: \.self) { key in
                                Text(Names.preset(key)).tag(key)
                            }
                        }
                        .pickerStyle(.segmented)
                    }
                    VStack(alignment: .leading, spacing: 10) {
                        Eyebrow("Jak długo")
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                ForEach(HoldSpec.allCases) { spec in
                                    Chip(title: spec.label, selected: hold == spec) { hold = spec }
                                }
                            }
                        }
                    }
                    Button {
                        Task { await send() }
                    } label: {
                        HStack(spacing: 10) {
                            if sending { ProgressView().tint(.white) }
                            Text(sending ? "Wysyłam…" : "Pokaż na ramce")
                        }
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(imageData == nil || sending)
                    .opacity(imageData == nil ? 0.5 : 1)
                    if let status {
                        Text(status)
                            .font(.footnote)
                            .foregroundStyle(Theme.inkSoft)
                    }
                }
                .padding(Theme.gutter)
            }
            .background(Theme.paper)
            .navigationTitle("Zdjęcie na ramkę")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Anuluj") { dismiss() }
                }
            }
            .onChange(of: selection) { _, item in
                Task { imageData = try? await item?.loadTransferable(type: Data.self) }
            }
        }
        .presentationDetents([.large])
    }

    private var picker: some View {
        PhotosPicker(selection: $selection, matching: .images) {
            ZStack {
                if let imageData, let image = UIImage(data: imageData) {
                    Image(uiImage: image)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .padding(14)
                        .background(Theme.matWhite)
                        .padding(6)
                        .background(Theme.frameWood)
                        .shadow(color: .black.opacity(0.2), radius: 14, y: 10)
                } else {
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
            }
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.plain)
    }

    private func send() async {
        guard let imageData else { return }
        sending = true
        defer { sending = false }
        status = "Przygotowuję obraz dla e-papieru i budzę ramkę…"
        do {
            let result = try await model.backend.sendPhoto(
                Self.jpeg(imageData), title: title, preset: preset, hold: hold
            )
            if result.fetched == true || model.backend.isDemo {
                model.toast = "Zdjęcie jest na ramce"
                await model.refreshPlayer()
                dismiss()
            } else {
                status = result.message ?? "Wysłano — ramka pobierze obraz po wybudzeniu."
            }
        } catch {
            status = error.localizedDescription
        }
    }

    /// HEIC and huge originals → a reasonable JPEG for upload.
    private static func jpeg(_ data: Data) -> Data {
        guard let image = UIImage(data: data) else { return data }
        let maxSide: CGFloat = 3000
        let scale = min(1, maxSide / max(image.size.width, image.size.height))
        let size = CGSize(width: image.size.width * scale, height: image.size.height * scale)
        let rendered = UIGraphicsImageRenderer(size: size).image { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
        return rendered.jpegData(compressionQuality: 0.9) ?? data
    }
}
