import SwiftUI

// A work cut out of its museum photograph (Mateusz 2026-11-14): the server
// cuts away a frame, an easel or a board around the work (`ai/crops.py`),
// the card shows the photograph as the museum made it ("Pełny kadr"), a
// print chooses between its sheet and the print alone, and the owner sets
// the corners again on a screen of their own, like "Kadr" for the frame.

/// The part of a picture inside four corners, as a plain box around them
/// (the server sets the perspective straight; a thumbnail here need not).
struct QuadCrop: View {
    let ref: ImageRef
    /// The photograph's width / height.
    let photoAspect: Double
    /// Corners as fractions of the photograph; nil, the whole of it.
    let quad: [[Double]]?
    let height: CGFloat
    var maxWidth: CGFloat = .infinity

    var body: some View {
        let box = Self.box(quad)
        let boxAspect = photoAspect * Double(box.width / max(box.height, 0.001))
        let width = min(height * boxAspect, maxWidth)
        let tall = width / boxAspect
        let fullWidth = width / box.width
        let fullHeight = tall / box.height
        ArtImage(ref: ref, placeholder: Theme.mat, maxPixel: 700, contentMode: .fill)
            .frame(width: fullWidth, height: fullHeight)
            .offset(x: -box.minX * fullWidth, y: -box.minY * fullHeight)
            .frame(width: width, height: tall, alignment: .topLeading)
            .clipped()
    }

    static func box(_ quad: [[Double]]?) -> CGRect {
        guard let quad, quad.count == 4 else { return CGRect(x: 0, y: 0, width: 1, height: 1) }
        let xs = quad.map { $0[0] }, ys = quad.map { $0[1] }
        let minX = max(0, xs.min() ?? 0), minY = max(0, ys.min() ?? 0)
        let maxX = min(1, xs.max() ?? 1), maxY = min(1, ys.max() ?? 1)
        return CGRect(x: minX, y: minY, width: max(maxX - minX, 0.01), height: max(maxY - minY, 0.01))
    }
}

/// Four corners as a closed path in a box of `size`.
private func quadPath(_ quad: [[Double]], in size: CGSize) -> Path {
    var path = Path()
    let points = quad.map { CGPoint(x: $0[0] * size.width, y: $0[1] * size.height) }
    guard let first = points.first else { return path }
    path.move(to: first)
    for point in points.dropFirst() { path.addLine(to: point) }
    path.closeSubpath()
    return path
}

/// "Pełny kadr" on the work's card: the museum's photograph with what is
/// shown outlined, a line on what was around the work, and for a print on
/// its sheet the choice "Z papierem" / "Sama odbitka" as two small
/// pictures, the chosen one outlined (Mateusz 2026-11-14, variant A).
struct FullPhotoSection: View {
    let item: Item
    /// Waiting for the server (the print's edge asked of the model).
    var busy = false
    let choosePaper: (Bool) -> Void
    let correct: () -> Void
    let open: () -> Void

    private var cut: Cut { item.cut ?? Cut() }
    private var photoAspect: Double {
        if cut.aspect > 0 { return cut.aspect }
        if let w = item.width, let h = item.height, w > 0, h > 0 { return Double(w) / Double(h) }
        return 0.75
    }
    private var photo: ImageRef { .museumPhoto(item.id, side: 900, version: item.pictureVersion) }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                Eyebrow("Pełny kadr")
                Spacer()
                Text("zdjęcie muzeum")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
            }
            HStack(alignment: .bottom, spacing: 14) {
                whole
                if cut.hasPaper {
                    Rectangle().fill(Theme.hairline).frame(width: 1).frame(maxHeight: 112)
                    choice(paper: true)
                    choice(paper: false)
                    Spacer(minLength: 0)
                } else {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(line)
                            .font(.subheadline)
                            .foregroundStyle(Theme.inkSoft)
                            .fixedSize(horizontal: false, vertical: true)
                        Button("Popraw kadr", action: correct)
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(Theme.ink)
                    }
                    Spacer(minLength: 0)
                }
            }
        }
    }

    private var line: String {
        let around = cut.aroundText
        let said = around.isEmpty ? "Muzeum sfotografowało dzieło z otoczeniem." : "Muzeum sfotografowało dzieło \(around)."
        return item.isCropped ? "\(said) Na ramce i w aplikacji pokazujemy samo dzieło." : said
    }

    /// The photograph whole, what is shown outlined; a tap opens it large.
    private var whole: some View {
        Button(action: open) {
            QuadCrop(ref: photo, photoAspect: photoAspect, quad: nil, height: 112, maxWidth: 150)
                .overlay {
                    if let shown = item.cutShown {
                        GeometryReader { geo in
                            let path = quadPath(shown, in: geo.size)
                            path.stroke(.black.opacity(0.45), style: StrokeStyle(lineWidth: 2.5, dash: [4, 3]))
                            path.stroke(.white, style: StrokeStyle(lineWidth: 1.2, dash: [4, 3]))
                        }
                    }
                }
                .clipShape(RoundedRectangle(cornerRadius: 3, style: .continuous))
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Zdjęcie muzeum w całości")
    }

    /// One of the two ways a print is shown, as a small picture.
    private func choice(paper: Bool) -> some View {
        let chosen = cut.paper == paper
        let quad: [[Double]]? = paper ? cut.work : (cut.plate ?? cut.work)
        return Button {
            if !chosen { choosePaper(paper) }
        } label: {
            VStack(spacing: 8) {
                QuadCrop(ref: photo, photoAspect: photoAspect, quad: quad, height: paper ? 84 : 72, maxWidth: 76)
                    // Before the print's edge is known: the sheet's picture,
                    // drawn in a little, stands for it.
                    .scaleEffect(!paper && cut.plate == nil ? 0.82 : 1)
                    .overlay {
                        if busy, !paper, !chosen { ProgressView().controlSize(.small) }
                    }
                    .padding(3)
                    .overlay {
                        RoundedRectangle(cornerRadius: 3, style: .continuous)
                            .strokeBorder(Theme.ink, lineWidth: chosen ? 2 : 0)
                    }
                Text(paper ? "Z papierem" : "Sama odbitka")
                    .font(.caption.weight(chosen ? .semibold : .regular))
                    .foregroundStyle(chosen ? Theme.ink : Theme.inkSoft)
            }
        }
        .buttonStyle(.plain)
        .disabled(busy)
        .accessibilityAddTraits(chosen ? .isSelected : [])
    }
}

/// The museum's photograph large, as it came ("Pełny kadr" tapped).
struct MuseumPhotoView: View {
    let item: Item
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack(alignment: .topLeading) {
            Color.black.ignoresSafeArea()
            ArtImage(
                ref: .museumPhoto(item.id, side: 2400, version: item.pictureVersion),
                placeholder: .clear, maxPixel: 2400, contentMode: .fit
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            Button("Zamknij") { dismiss() }
                .buttonStyle(.glass)
                .padding(.horizontal, Theme.gutter)
                .padding(.top, 6)
        }
    }
}

/// "Popraw kadr" / "Przytnij zdjęcie": the museum's photograph on the whole
/// screen and the four corners of the work on it, each dragged on its own
/// (a photograph taken at an angle has no right angles), with a loupe at
/// the corner held. Like "Kadr" for the frame (Mateusz 2026-11-14).
struct CutEditor: View {
    let item: Item
    /// Saves the corners (of the work as shown); whether it went.
    let save: ([[Double]]) async -> Bool
    @Environment(\.dismiss) private var dismiss
    @State private var corners: [[Double]] = []
    @State private var start: [[Double]] = []
    @State private var held: Int?
    @State private var saving = false

    private var photoAspect: Double {
        if let cut = item.cut, cut.aspect > 0 { return cut.aspect }
        if let w = item.width, let h = item.height, w > 0, h > 0 { return Double(w) / Double(h) }
        return 0.75
    }
    private var photo: ImageRef { .museumPhoto(item.id, side: 2400, version: item.pictureVersion) }
    /// The corners when nothing is cut yet: a little in from the edges.
    private static let inset: [[Double]] = [[0.06, 0.06], [0.94, 0.06], [0.94, 0.94], [0.06, 0.94]]
    private var changed: Bool { corners != start }

    var body: some View {
        VStack(spacing: 14) {
            HStack {
                Button("Anuluj") { dismiss() }
                    .buttonStyle(.glass)
                    .disabled(saving)
                Spacer()
            }
            .padding(.horizontal, Theme.gutter)
            .padding(.top, 6)
            GeometryReader { geo in
                let size = fitted(in: geo.size)
                ZStack(alignment: .topLeading) {
                    ArtImage(ref: photo, placeholder: Theme.mat, maxPixel: 2400, contentMode: .fit)
                        .frame(width: size.width, height: size.height)
                    if corners.count == 4 {
                        // Outside the work dimmed, the work's edges drawn.
                        Path { path in
                            path.addRect(CGRect(origin: .zero, size: size))
                            path.addPath(quadPath(corners, in: size))
                        }
                        .fill(.black.opacity(0.42), style: FillStyle(eoFill: true))
                        quadPath(corners, in: size)
                            .stroke(Color.white, lineWidth: 1.5)
                        ForEach(0 ..< 4, id: \.self) { n in
                            handle(n, in: size)
                        }
                        if let held { loupe(held, in: size) }
                    }
                }
                .frame(width: size.width, height: size.height)
                .frame(width: geo.size.width, height: geo.size.height)
            }
            .padding(.horizontal, Theme.gutter)
            Text("Przeciągnij narożniki na krawędzie dzieła.")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
            HStack(spacing: 10) {
                Button {
                    withAnimation(.easeInOut(duration: 0.25)) { corners = [[0, 0], [1, 0], [1, 1], [0, 1]] }
                } label: {
                    Text("Całe zdjęcie").lineLimit(1).minimumScaleFactor(0.8)
                }
                .buttonStyle(SecondaryButtonStyle())
                .disabled(saving)
                Button {
                    Task {
                        saving = true
                        if await save(corners) { dismiss() }
                        saving = false
                    }
                } label: {
                    HStack(spacing: 10) {
                        if saving { ProgressView().tint(Theme.paper) }
                        Text("Zapisz kadr")
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(!changed || saving)
                .opacity(changed || saving ? 1 : 0.45)
            }
            .frame(maxWidth: 420)
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 8)
        }
        .background { Color.clear.paperPage() }
        .onAppear {
            guard corners.isEmpty else { return }
            let shown = item.cutShown ?? Self.inset
            corners = shown
            start = item.cutShown ?? []
        }
    }

    private func fitted(in space: CGSize) -> CGSize {
        guard space.width > 0, space.height > 0 else { return .zero }
        let aspect = CGFloat(photoAspect)
        return space.width / space.height > aspect
            ? CGSize(width: space.height * aspect, height: space.height)
            : CGSize(width: space.width, height: space.width / aspect)
    }

    private func handle(_ n: Int, in size: CGSize) -> some View {
        let point = CGPoint(x: corners[n][0] * size.width, y: corners[n][1] * size.height)
        return Circle()
            .fill(.white)
            .overlay(Circle().strokeBorder(Theme.ink, lineWidth: 2))
            .frame(width: 24, height: 24)
            .shadow(color: .black.opacity(0.3), radius: 3, y: 1)
            // A finger's worth to hold.
            .frame(width: 48, height: 48)
            .contentShape(Rectangle())
            .position(point)
            .gesture(
                DragGesture(minimumDistance: 0, coordinateSpace: .local)
                    .onChanged { drag in
                        held = n
                        let x = min(max(drag.location.x / size.width, 0), 1)
                        let y = min(max(drag.location.y / size.height, 0), 1)
                        corners[n] = [(x * 10000).rounded() / 10000, (y * 10000).rounded() / 10000]
                    }
                    .onEnded { _ in held = nil }
            )
            .accessibilityLabel(["Lewy górny narożnik", "Prawy górny narożnik", "Prawy dolny narożnik", "Lewy dolny narożnik"][n])
    }

    /// The photograph around the corner held, three times larger, where the
    /// finger does not cover it (the top corner away from it).
    private func loupe(_ n: Int, in size: CGSize) -> some View {
        let zoom: CGFloat = 3
        let side: CGFloat = 96
        let point = CGPoint(x: corners[n][0] * size.width, y: corners[n][1] * size.height)
        let left = point.x > size.width / 2
        return ZStack {
            ArtImage(ref: photo, placeholder: Theme.mat, maxPixel: 2400, contentMode: .fit)
                .frame(width: size.width * zoom, height: size.height * zoom)
                .offset(x: side / 2 - point.x * zoom, y: side / 2 - point.y * zoom)
                .frame(width: side, height: side, alignment: .topLeading)
            Rectangle().fill(Theme.ink).frame(width: 1.5, height: side)
            Rectangle().fill(Theme.ink).frame(width: side, height: 1.5)
        }
        .frame(width: side, height: side)
        .clipShape(Circle())
        .overlay(Circle().strokeBorder(.white, lineWidth: 3))
        .shadow(color: .black.opacity(0.35), radius: 6, y: 2)
        .position(x: left ? side / 2 + 8 : size.width - side / 2 - 8, y: side / 2 + 8)
        .allowsHitTesting(false)
    }
}
