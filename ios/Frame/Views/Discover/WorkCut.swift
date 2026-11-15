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

/// "Pełny kadr" on the work's card, a card of rows above the facts
/// (Mateusz 2026-11-15, layout B: „moduł pokażmy nad blokiem «słowa
/// kluczowe, technika, rodzaj…»”): the museum's photograph small with the
/// line on what was around the work and what is shown (a tap opens "Popraw
/// kadr"), for a work on paper a switch "Z marginesem", then "Popraw kadr ›".
struct FullPhotoSection: View {
    let item: Item
    /// Waiting for the server (the print's edge asked of the model).
    var busy = false
    let choosePaper: (Bool) -> Void
    let correct: () -> Void

    private var cut: Cut { item.cut ?? Cut() }
    private var photoAspect: Double {
        if cut.aspect > 0 { return cut.aspect }
        if let w = item.width, let h = item.height, w > 0, h > 0 { return Double(w) / Double(h) }
        return 0.75
    }
    private var photo: ImageRef { .museumPhoto(item.id, side: 900, version: item.pictureVersion) }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Eyebrow("Pełny kadr")
            Card(padding: 0) {
                VStack(alignment: .leading, spacing: 0) {
                    Button(action: correct) {
                        HStack(alignment: .center, spacing: 12) {
                            // No outline of the cut on it (Mateusz 2026-11-14): just the photograph.
                            QuadCrop(ref: photo, photoAspect: photoAspect, quad: nil, height: 60, maxWidth: 96)
                                .clipShape(RoundedRectangle(cornerRadius: 3, style: .continuous))
                                .frame(width: 96, height: 60)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(item.isOwnWork ? "Twoje zdjęcie" : "Zdjęcie muzeum")
                                    .font(.body)
                                    .foregroundStyle(Theme.ink)
                                Text(line)
                                    .font(.footnote)
                                    .foregroundStyle(Theme.inkSoft)
                                    .fixedSize(horizontal: false, vertical: true)
                                    .contentTransition(.opacity)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .padding(.horizontal, 14)
                        .padding(.vertical, 12)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityHint("Otwiera poprawianie kadru")
                    if cut.hasPaper {
                        Divider().overlay(Theme.hairline)
                        Toggle(isOn: Binding(get: { cut.paper }, set: { choosePaper($0) })) {
                            HStack(spacing: 8) {
                                Text("Z marginesem").foregroundStyle(Theme.ink)
                                if busy { ProgressView().controlSize(.small) }
                            }
                        }
                        .disabled(busy)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 10)
                    }
                    Divider().overlay(Theme.hairline)
                    Button(action: correct) {
                        HStack(spacing: 12) {
                            Image(systemName: "crop")
                                .font(.body.weight(.medium))
                                .frame(width: 22)
                            Text("Popraw kadr")
                                .frame(maxWidth: .infinity, alignment: .leading)
                            Image(systemName: "chevron.right")
                                .font(.footnote.weight(.semibold))
                                .foregroundStyle(Theme.inkSoft)
                        }
                        .foregroundStyle(Theme.ink)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 14)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private var line: String {
        if item.isOwnWork {
            // His own photograph, not a museum's.
            return item.isCropped ? "Rama i ściana wycięte, prezentowane jest samo dzieło." : "Prezentowane jest całe zdjęcie."
        }
        return cut.hasPaper
            ? cut.paperLine(medium: item.medium)
            : Cut.fullPhotoLine(around: cut.aroundText, cropped: item.isCropped)
    }
}

/// "Popraw kadr" / "Przytnij zdjęcie": the museum's photograph and the
/// four corners of the work on it, each set on its own (a photograph taken
/// at an angle has no right angles). Four loupes, one for each corner,
/// above and below the photograph (Mateusz 2026-11-15, "cztery lupy"): the
/// cross in a loupe is its corner, and moving the photograph in the loupe
/// moves the corner, so no finger covers it; a corner on the photograph can
/// be dragged too. "Zapisz" at the top beside "Anuluj".
struct CutEditor: View {
    /// The photograph the corners are set on: the museum's, or one just
    /// taken of a work of his own ("Dodaj własne dzieło").
    enum Photo {
        case ref(ImageRef)
        case local(UIImage)
    }

    let photoSource: Photo
    /// The photograph's width / height.
    let photoAspect: Double
    /// The corners it opens with; nil, a little in from the edges.
    let initial: [[Double]]?
    let saveTitle: String
    let cancelTitle: String
    /// "Dalej" in the own work's steps: on with the corners as found too.
    let savesUnchanged: Bool
    /// Over the hint under the photograph: what was found ("Rama wycięta").
    let note: String?
    /// The own work's steps go on: nothing to dismiss.
    let cancel: (() -> Void)?
    /// Saves the corners (of the work as shown); whether it went.
    let save: ([[Double]]) async -> Bool
    @Environment(\.dismiss) private var dismiss
    @State private var corners: [[Double]] = []
    @State private var start: [[Double]] = []
    /// The corner last moved: its loupe ringed.
    @State private var active: Int?
    /// The corner where a drag in its loupe began.
    @State private var loupeFrom: [Double]?
    @State private var saving = false

    init(item: Item, save: @escaping ([[Double]]) async -> Bool) {
        let aspect: Double
        if let cut = item.cut, cut.aspect > 0 {
            aspect = cut.aspect
        } else if let w = item.width, let h = item.height, w > 0, h > 0 {
            aspect = Double(w) / Double(h)
        } else {
            aspect = 0.75
        }
        self.init(
            photo: .ref(.museumPhoto(item.id, side: 2400, version: item.pictureVersion)),
            aspect: aspect, corners: item.cutShown, save: save
        )
    }

    init(
        photo: Photo, aspect: Double, corners: [[Double]]?, saveTitle: String = "Zapisz",
        cancelTitle: String = "Anuluj", savesUnchanged: Bool = false, note: String? = nil, cancel: (() -> Void)? = nil,
        save: @escaping ([[Double]]) async -> Bool
    ) {
        photoSource = photo
        photoAspect = aspect
        initial = corners
        self.saveTitle = saveTitle
        self.cancelTitle = cancelTitle
        self.savesUnchanged = savesUnchanged
        self.note = note
        self.cancel = cancel
        self.save = save
    }

    /// The corners when nothing is cut yet: a little in from the edges.
    private static let inset: [[Double]] = [[0.06, 0.06], [0.94, 0.06], [0.94, 0.94], [0.06, 0.94]]
    private static let whole: [[Double]] = [[0, 0], [1, 0], [1, 1], [0, 1]]
    private var changed: Bool { corners != start }
    /// The cross and the ring of the corner in hand: bright on any picture.
    private static let mark = Color(light: 0xF2B93B, dark: 0xF2C14E)
    /// How much larger the photograph is in a loupe than on the screen.
    private static let zoom: CGFloat = 4
    private static let names = ["Lewy górny narożnik", "Prawy górny narożnik", "Prawy dolny narożnik", "Lewy dolny narożnik"]

    @ViewBuilder
    private func photoView(_ size: CGSize) -> some View {
        switch photoSource {
        case let .ref(ref):
            ArtImage(ref: ref, placeholder: Theme.mat, maxPixel: 2400, contentMode: .fit)
                .frame(width: size.width, height: size.height)
        case let .local(image):
            Image(uiImage: image)
                .resizable()
                .frame(width: size.width, height: size.height)
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Button(cancelTitle) { if let cancel { cancel() } else { dismiss() } }
                    .buttonStyle(.glass)
                    .disabled(saving)
                Spacer()
                Button {
                    Task {
                        saving = true
                        if await save(corners), cancel == nil { dismiss() }
                        saving = false
                    }
                } label: {
                    HStack(spacing: 8) {
                        if saving { ProgressView().controlSize(.small).tint(Theme.paper) }
                        Text(saveTitle)
                    }
                    .foregroundStyle(Theme.paper)
                }
                .buttonStyle(.glassProminent)
                .tint(Theme.ink)
                .disabled((!changed && !savesUnchanged) || saving)
            }
            .padding(.horizontal, Theme.gutter)
            .padding(.top, 6)
            .padding(.bottom, 12)
            GeometryReader { geo in
                if corners.count == 4 { board(in: geo.size) }
            }
            .padding(.horizontal, Theme.gutter)
            if let note {
                Text(note)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(Theme.ink)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, Theme.gutter)
                    .padding(.top, 12)
            }
            Text("Przesuń zdjęcie w lupie albo przeciągnij narożnik.")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
                .padding(.top, 12)
            HStack(spacing: 8) {
                chip("Cofnij zmiany", symbol: "arrow.uturn.backward", enabled: changed && !saving) {
                    corners = start.count == 4 ? start : Self.inset
                }
                chip("Całe zdjęcie", symbol: "arrow.up.left.and.arrow.down.right", enabled: corners != Self.whole && !saving) {
                    corners = Self.whole
                }
            }
            .padding(.top, 12)
            .padding(.bottom, 8)
        }
        .background { Color.clear.paperPage() }
        .onAppear {
            guard corners.isEmpty else { return }
            corners = initial ?? Self.inset
            start = initial ?? []
        }
    }

    private func chip(_ title: String, symbol: String, enabled: Bool, action: @escaping () -> Void) -> some View {
        Button {
            withAnimation(.easeInOut(duration: 0.25)) { action() }
        } label: {
            Label(title, systemImage: symbol)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(Theme.ink)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(Theme.card, in: Capsule())
                .overlay(Capsule().strokeBorder(Theme.hairline))
                .opacity(enabled ? 1 : 0.4)
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
    }

    /// Where everything goes in `space`: the loupes' side, the photograph's
    /// size and its top left corner. The loupes take what the photograph
    /// leaves above and below it, at least `least` each: a tall photograph
    /// is made smaller for them.
    private func layout(in space: CGSize) -> (side: CGFloat, size: CGSize, origin: CGPoint) {
        let gap: CGFloat = 18
        let least: CGFloat = 104
        let most = min(160, (space.width - 16) / 2)
        let natural = space.width / CGFloat(photoAspect)
        let side = min(most, max(least, (space.height - natural - 2 * gap) / 2))
        let box = CGSize(width: space.width, height: max(space.height - 2 * (side + gap), 40))
        let size = fitted(box)
        let origin = CGPoint(x: (space.width - size.width) / 2, y: side + gap + (box.height - size.height) / 2)
        return (side, size, origin)
    }

    private func fitted(_ box: CGSize) -> CGSize {
        guard box.width > 0, box.height > 0 else { return .zero }
        let aspect = CGFloat(photoAspect)
        return box.width / box.height > aspect
            ? CGSize(width: box.height * aspect, height: box.height)
            : CGSize(width: box.width, height: box.width / aspect)
    }

    /// Loupe n's centre: the top two above the photograph, the bottom two
    /// below, each on its corner's side.
    private func loupeCentre(_ n: Int, side: CGFloat, in space: CGSize) -> CGPoint {
        let left = n == 0 || n == 3
        let top = n < 2
        return CGPoint(x: left ? side / 2 : space.width - side / 2, y: top ? side / 2 : space.height - side / 2)
    }

    private func board(in space: CGSize) -> some View {
        let (side, size, origin) = layout(in: space)
        return ZStack(alignment: .topLeading) {
            // A dotted lead from each loupe to its corner.
            Path { path in
                for n in 0 ..< 4 {
                    let centre = loupeCentre(n, side: side, in: space)
                    let corner = CGPoint(x: origin.x + corners[n][0] * size.width, y: origin.y + corners[n][1] * size.height)
                    let dx = corner.x - centre.x, dy = corner.y - centre.y
                    let length = max(hypot(dx, dy), 0.001)
                    guard length > side / 2 + 6 else { continue }
                    path.move(to: CGPoint(x: centre.x + dx / length * (side / 2 + 3), y: centre.y + dy / length * (side / 2 + 3)))
                    path.addLine(to: CGPoint(x: corner.x - dx / length * 6, y: corner.y - dy / length * 6))
                }
            }
            .stroke(Theme.inkSoft.opacity(0.6), style: StrokeStyle(lineWidth: 1, dash: [2, 3]))
            photoWithCorners(size)
                .frame(width: size.width, height: size.height)
                .offset(x: origin.x, y: origin.y)
            ForEach(0 ..< 4, id: \.self) { n in
                loupe(n, photoSize: size, side: side)
                    .position(loupeCentre(n, side: side, in: space))
            }
        }
        .frame(width: space.width, height: space.height, alignment: .topLeading)
    }

    private func photoWithCorners(_ size: CGSize) -> some View {
        ZStack(alignment: .topLeading) {
            photoView(size)
            // Outside the work dimmed, the work's edges drawn.
            Path { path in
                path.addRect(CGRect(origin: .zero, size: size))
                path.addPath(quadPath(corners, in: size))
            }
            .fill(.black.opacity(0.42), style: FillStyle(eoFill: true))
            quadPath(corners, in: size)
                .stroke(Color.white, lineWidth: 1.2)
            ForEach(0 ..< 4, id: \.self) { n in
                handle(n, in: size)
            }
        }
    }

    /// A corner on the photograph: a bracket along its two edges, and a
    /// finger's worth around it to drag.
    private func handle(_ n: Int, in size: CGSize) -> some View {
        let point = CGPoint(x: corners[n][0] * size.width, y: corners[n][1] * size.height)
        return Bracket(corner: point, next: corner(n + 1, in: size), previous: corner(n + 3, in: size))
            .stroke(n == active ? Self.mark : Color.white, style: StrokeStyle(lineWidth: 3.5, lineCap: .square, lineJoin: .miter))
            .shadow(color: .black.opacity(0.35), radius: 2, y: 1)
            .frame(width: size.width, height: size.height)
            .allowsHitTesting(false)
            .overlay(alignment: .topLeading) {
                Color.clear
                    .frame(width: 48, height: 48)
                    .contentShape(Rectangle())
                    .position(point)
                    .gesture(
                        DragGesture(minimumDistance: 0, coordinateSpace: .named("cutPhoto"))
                            .onChanged { drag in
                                active = n
                                let x = min(max(drag.location.x / size.width, 0), 1)
                                let y = min(max(drag.location.y / size.height, 0), 1)
                                corners[n] = Self.rounded(x, y)
                            }
                    )
                    .accessibilityLabel(Self.names[n])
            }
            .coordinateSpace(name: "cutPhoto")
    }

    private func corner(_ n: Int, in size: CGSize) -> CGPoint {
        let c = corners[n % 4]
        return CGPoint(x: c[0] * size.width, y: c[1] * size.height)
    }

    private static func rounded(_ x: Double, _ y: Double) -> [Double] {
        [(min(max(x, 0), 1) * 10000).rounded() / 10000, (min(max(y, 0), 1) * 10000).rounded() / 10000]
    }

    /// The photograph around corner n, `zoom` times larger, the cross on
    /// the corner. Moving the photograph here moves the corner under the
    /// cross the other way, as if the cross stood still over it.
    private func loupe(_ n: Int, photoSize: CGSize, side: CGFloat) -> some View {
        let large = CGSize(width: photoSize.width * Self.zoom, height: photoSize.height * Self.zoom)
        let point = CGPoint(x: corners[n][0] * large.width, y: corners[n][1] * large.height)
        let held = n == active
        return ZStack(alignment: .topLeading) {
            Theme.mat
            ZStack(alignment: .topLeading) {
                photoView(large)
                quadPath(corners, in: large)
                    .stroke(Color.white.opacity(0.85), lineWidth: 1)
            }
            .frame(width: large.width, height: large.height, alignment: .topLeading)
            .offset(x: side / 2 - point.x, y: side / 2 - point.y)
            Rectangle().fill(Self.mark).frame(width: 1.5, height: side).offset(x: side / 2 - 0.75)
            Rectangle().fill(Self.mark).frame(width: side, height: 1.5).offset(y: side / 2 - 0.75)
        }
        .frame(width: side, height: side, alignment: .topLeading)
        .clipShape(Circle())
        .overlay(Circle().strokeBorder(held ? Self.mark : Color.white, lineWidth: 3))
        .shadow(color: .black.opacity(0.25), radius: 6, y: 2)
        .contentShape(Circle())
        .gesture(
            DragGesture(minimumDistance: 0)
                .onChanged { drag in
                    if loupeFrom == nil { loupeFrom = corners[n] }
                    active = n
                    guard let from = loupeFrom else { return }
                    let x = from[0] - Double(drag.translation.width / large.width)
                    let y = from[1] - Double(drag.translation.height / large.height)
                    corners[n] = Self.rounded(x, y)
                }
                .onEnded { _ in loupeFrom = nil }
        )
        .accessibilityLabel("Lupa: \(Self.names[n].lowercased())")
    }
}

/// Two short arms from a corner along its edges, towards the next and the
/// previous corner.
private struct Bracket: Shape {
    let corner: CGPoint
    let next: CGPoint
    let previous: CGPoint
    var arm: CGFloat = 16

    func path(in rect: CGRect) -> Path {
        func toward(_ p: CGPoint) -> CGPoint {
            let dx = p.x - corner.x, dy = p.y - corner.y
            let length = max(hypot(dx, dy), 0.001)
            let reach = min(arm, length / 3)
            return CGPoint(x: corner.x + dx / length * reach, y: corner.y + dy / length * reach)
        }
        var path = Path()
        path.move(to: toward(previous))
        path.addLine(to: corner)
        path.addLine(to: toward(next))
        return path
    }
}
