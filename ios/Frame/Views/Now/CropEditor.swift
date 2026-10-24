import SwiftUI

extension Crop {
    /// The part of a picture of `size` this crop shows in a window of `aspect`
    /// (server: layout.crop_box).
    func box(in size: CGSize, aspect: CGFloat) -> CGRect {
        DemoFraming.cropBox(size, aspect: aspect, crop: self)
    }
}

/// Adjusting what the frame shows of the current picture: the crop in
/// "Wypełnij", the two close-ups in "Detale", the one in "Opis". Saved with
/// the artwork, for this orientation of the frame.
struct CropEditorSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let item: Item

    @State private var view: FramingView?
    @State private var crops: [Crop] = []
    @State private var selected = 0
    @State private var busy = false
    @State private var error: String?

    private var orientation: String { model.settings?.orientation ?? "landscape" }

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 18) {
                if let view, crops.count == view.windows.count {
                    if view.windows.isEmpty {
                        wholePicture
                    } else {
                        editor(view)
                    }
                } else if error == nil {
                    ProgressView().frame(maxWidth: .infinity, minHeight: 260)
                }
                if let error {
                    Label(error, systemImage: "exclamationmark.triangle")
                        .font(.subheadline)
                        .foregroundStyle(Theme.bad)
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, Theme.gutter)
            .padding(.top, 8)
            .background(Theme.paper)
            .navigationTitle("Kadr na ramce")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Anuluj") { dismiss() }
                }
            }
        }
        .interactiveDismissDisabled(busy)
        .task { await load() }
    }

    private func editor(_ view: FramingView) -> some View {
        let window = view.windows[min(selected, view.windows.count - 1)]
        let portraitFrame = orientation == "portrait"
        let hint = switch view.fit {
        case "details": "Przesuń palcem i rozsuń dwa palce, żeby wybrać, co pokażą okienka z detalami."
        case "description": "Przesuń palcem i rozsuń dwa palce, żeby wybrać detal pokazany obok opisu."
        default: "Przesuń palcem i rozsuń dwa palce, żeby wybrać, co pokaże ramka."
        }
        return VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Eyebrow(item.artist.isEmpty ? "Kadr" : item.artist, color: Theme.vermilion)
                Text(item.title).font(.serif(22, weight: .semibold)).lineLimit(2)
            }
            Text(hint)
                .font(.callout)
                .foregroundStyle(Theme.inkSoft)
                .fixedSize(horizontal: false, vertical: true)
            if view.windows.count > 1 {
                Picker("Detal", selection: $selected) {
                    ForEach(view.windows.indices, id: \.self) { Text("Detal \($0 + 1)").tag($0) }
                }
                .pickerStyle(.segmented)
            }
            CropViewport(
                ref: .image(item.id),
                imageSize: CGSize(width: view.width, height: view.height),
                aspect: window.aspect,
                maxZoom: window.role == "detail" ? 6 : 4,
                crop: $crops[min(selected, crops.count - 1)]
            )
            .id(selected)  // a fresh gesture state per window
            .padding(5)
            .background(Theme.frameWood)
            .clipShape(RoundedRectangle(cornerRadius: 2))
            .shadow(color: .black.opacity(0.25), radius: 12, y: 8)
            .frame(maxWidth: portraitFrame && window.role == "fill" ? 240 : .infinity)
            .frame(maxWidth: .infinity)
            Label(
                view.windows.contains(where: \.custom) ? "Twój kadr" : "Kadr dobrany automatycznie",
                systemImage: view.windows.contains(where: \.custom) ? "hand.draw" : "sparkles"
            )
            .font(.caption.weight(.medium))
            .foregroundStyle(Theme.inkSoft)
            Button {
                Task { await save() }
            } label: {
                HStack(spacing: 10) {
                    if busy { ProgressView().tint(Theme.paper) }
                    Text("Pokaż na ramce")
                }
            }
            .buttonStyle(PrimaryButtonStyle())
            .disabled(busy)
            Button("Kadr automatyczny") { Task { await reset() } }
                .buttonStyle(SecondaryButtonStyle())
                .disabled(busy || !view.windows.contains(where: \.custom))
        }
    }

    private var wholePicture: some View {
        Card {
            Label("Widać cały obraz", systemImage: "rectangle.inset.filled")
                .font(.headline)
            Text("Teraz obraz jest pokazany w całości, w passe-partout, więc nie ma czego kadrować. Kadr ustawisz w trybach „Wypełnij”, „Detale” i „Opis” (Ramka → Prezentacja).")
                .font(.callout)
                .foregroundStyle(Theme.inkSoft)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func load() async {
        do {
            let loaded = try await model.backend.framing(itemID: item.id, orientation: orientation)
            crops = loaded.windows.map(\.crop)
            view = loaded
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            view = try await model.backend.saveFraming(itemID: item.id, orientation: orientation, crops: crops)
            model.toast = "Nowy kadr — ramka odświeża obraz"
            dismiss()
            await model.followPlayer()
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func reset() async {
        busy = true
        defer { busy = false }
        do {
            let restored = try await model.backend.resetFraming(itemID: item.id, orientation: orientation)
            crops = restored.windows.map(\.crop)
            view = restored
            model.toast = "Przywrócono kadr automatyczny"
            await model.followPlayer()
        } catch {
            self.error = error.localizedDescription
        }
    }
}

/// A window onto the picture: drag to move, pinch to zoom.
struct CropViewport: View {
    let ref: ImageRef
    let imageSize: CGSize
    let aspect: CGFloat
    var maxZoom: Double = 4
    @Binding var crop: Crop

    @State private var dragStart: Crop?
    @State private var zoomStart: Crop?

    private var interacting: Bool { dragStart != nil || zoomStart != nil }

    var body: some View {
        GeometryReader { geo in
            let box = crop.box(in: imageSize, aspect: aspect)
            let scale = geo.size.width / max(box.width, 1)
            ArtImage(ref: ref, maxPixel: 2200, contentMode: .fill)
                .frame(width: imageSize.width * scale, height: imageSize.height * scale)
                .offset(x: -box.minX * scale, y: -box.minY * scale)
                .frame(width: geo.size.width, height: geo.size.height, alignment: .topLeading)
                .clipped()
                .overlay { if interacting { ThirdsGrid() } }
                .contentShape(Rectangle())
                .gesture(drag(scale).simultaneously(with: magnify))
        }
        .aspectRatio(aspect, contentMode: .fit)
        .accessibilityLabel("Kadr: przeciągnij, żeby przesunąć, rozsuń palce, żeby przybliżyć")
    }

    private func drag(_ scale: CGFloat) -> some Gesture {
        DragGesture(minimumDistance: 1)
            .onChanged { value in
                if dragStart == nil { dragStart = crop }
                guard let start = dragStart else { return }
                var next = crop
                next.x = start.x - value.translation.width / (imageSize.width * scale)
                next.y = start.y - value.translation.height / (imageSize.height * scale)
                crop = clamped(next)
            }
            .onEnded { _ in dragStart = nil }
    }

    private var magnify: some Gesture {
        MagnifyGesture()
            .onChanged { value in
                if zoomStart == nil { zoomStart = crop }
                guard let start = zoomStart else { return }
                var next = crop
                next.zoom = min(max(start.zoom * value.magnification, 1), maxZoom)
                crop = clamped(next)
            }
            .onEnded { _ in zoomStart = nil }
    }

    /// Keep the centre where the window stays inside the picture, so the
    /// next drag starts from what is visible.
    private func clamped(_ value: Crop) -> Crop {
        let box = value.box(in: imageSize, aspect: aspect)
        var next = value
        next.x = box.midX / imageSize.width
        next.y = box.midY / imageSize.height
        return next
    }
}

private struct ThirdsGrid: View {
    var body: some View {
        GeometryReader { geo in
            Path { path in
                for i in 1 ... 2 {
                    let x = geo.size.width * CGFloat(i) / 3, y = geo.size.height * CGFloat(i) / 3
                    path.move(to: CGPoint(x: x, y: 0))
                    path.addLine(to: CGPoint(x: x, y: geo.size.height))
                    path.move(to: CGPoint(x: 0, y: y))
                    path.addLine(to: CGPoint(x: geo.size.width, y: y))
                }
            }
            .stroke(.white.opacity(0.55), lineWidth: 0.75)
        }
        .allowsHitTesting(false)
    }
}
