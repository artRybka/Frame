import SwiftUI

extension Crop {
    /// The part of a picture of `size` this crop shows in a window of `aspect`
    /// (server: layout.crop_box).
    func box(in size: CGSize, aspect: CGFloat) -> CGRect {
        DemoFraming.cropBox(size, aspect: aspect, crop: self)
    }
}

/// The crop of the picture browsed to on "Teraz", as loaded and as edited.
/// Nothing reaches the frame until "Pokaż na ramce".
struct FramingDraft: Equatable {
    var key = ""  // item, orientation and presentation it was loaded for
    var view: FramingView?
    var saved: [Crop] = []  // what the server has now
    var crops: [Crop] = []  // as edited
    /// The user went back to the automatic crop: these are the ones the
    /// server would choose, and sending forgets the saved ones.
    var automatic: [Crop]?

    var custom: Bool { view?.windows.contains(where: \.custom) == true }

    var changed: Bool {
        if let automatic { return custom || crops != automatic }
        return crops != saved
    }

    /// What sending has to do to the saved framing, if anything.
    var change: FramingChange? {
        guard let view, changed else { return nil }
        if let automatic, crops == automatic { return .reset(orientation: view.orientation) }
        return .save(orientation: view.orientation, crops: crops)
    }

    /// Passe-partout with a window of another shape than the saved one.
    var reshaped: Bool {
        view?.fit == "fit" && crops.first?.aspect != saved.first?.aspect
    }

    /// The preview to show while the shape is being tried.
    var trial: FramingCrops? {
        guard reshaped, let view, let crop = crops.first else { return nil }
        return FramingCrops(mode: view.fit, crops: [Crop(aspect: crop.aspect)])
    }

    /// The viewport's shape: the window's, or in passe-partout the one chosen.
    func aspect(_ index: Int) -> CGFloat {
        guard let view, index < view.windows.count else { return 1 }
        guard view.fit == "fit" else { return view.windows[index].aspect }
        return crops[index].aspect ?? Double(view.width) / Double(max(view.height, 1))
    }
}

enum FramingChange: Equatable {
    case save(orientation: String, crops: [Crop])
    case reset(orientation: String)
}

/// Shapes for the passe-partout window; nil keeps the picture's own.
let windowShapes: [(title: String, aspect: Double?)] = [
    ("Oryginał", nil), ("1:1", 1), ("4:5", 4.0 / 5), ("3:4", 3.0 / 4), ("2:3", 2.0 / 3),
    ("4:3", 4.0 / 3), ("3:2", 3.0 / 2), ("16:9", 16.0 / 9),
]

/// The picture's crop windows laid over the preview at their places on the
/// canvas, so it is cropped right on the frame: drag to move, pinch to zoom.
struct CropWindows: View {
    let itemID: String
    @Binding var draft: FramingDraft

    var body: some View {
        GeometryReader { geo in
            if let view = draft.view, draft.crops.count == view.windows.count {
                ForEach(view.windows.indices, id: \.self) { index in
                    if let rect = place(index, view, in: geo.size) {
                        let aspect = draft.aspect(index)
                        CropViewport(
                            ref: .image(itemID),
                            imageSize: CGSize(width: view.width, height: view.height),
                            aspect: aspect,
                            maxZoom: view.windows[index].role == "detail" ? 6 : 4,
                            placeholder: .clear,
                            crop: $draft.crops[index]
                        )
                        .frame(width: rect.width, height: rect.height)
                        .position(x: rect.midX, y: rect.midY)
                        .id("\(index)-\(aspect)")  // a fresh gesture state per shape
                    }
                }
            }
        }
    }

    /// Where window `index` is on the picture of the frame, in points.
    private func place(_ index: Int, _ view: FramingView, in size: CGSize) -> CGRect? {
        let window = view.windows[index]
        func scaled(_ unit: CGRect) -> CGRect {
            CGRect(x: unit.minX * size.width, y: unit.minY * size.height,
                   width: unit.width * size.width, height: unit.height * size.height)
        }
        if draft.reshaped, let area = window.areaFrame.map(scaled) {
            // A new shape, centred where the mat window may go (layout.fit_area).
            let aspect = draft.aspect(index)
            let fitted = area.width / area.height > aspect
                ? CGSize(width: area.height * aspect, height: area.height)
                : CGSize(width: area.width, height: area.width / aspect)
            return CGRect(x: area.midX - fitted.width / 2, y: area.midY - fitted.height / 2,
                          width: fitted.width, height: fitted.height)
        }
        return window.frame.map(scaled)
    }
}

/// A window onto the picture: drag to move, pinch to zoom.
struct CropViewport: View {
    let ref: ImageRef
    let imageSize: CGSize
    let aspect: CGFloat
    var maxZoom: Double = 4
    var placeholder: Color = Theme.mat
    @Binding var crop: Crop

    @State private var dragStart: Crop?
    @State private var zoomStart: Crop?

    private var interacting: Bool { dragStart != nil || zoomStart != nil }

    var body: some View {
        GeometryReader { geo in
            let box = crop.box(in: imageSize, aspect: aspect)
            let scale = geo.size.width / max(box.width, 1)
            ArtImage(ref: ref, placeholder: placeholder, maxPixel: 2200, contentMode: .fill)
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
