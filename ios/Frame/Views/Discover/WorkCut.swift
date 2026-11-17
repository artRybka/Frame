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

/// "Popraw kadr" / "Przytnij zdjęcie": the photograph as large as it fits
/// and the four corners of the work on it, each set on its own (a
/// photograph taken at an angle has no right angles). Mateusz 2026-11-17,
/// "C: lupa przy palcu + magnes": a corner is taken anywhere near it and
/// follows the finger's movement, not the finger, so the finger stays
/// beside it; a slow finger moves it a quarter as far (`gain`); while it is
/// dragged a loupe beside the finger shows it four times larger; on a
/// strong edge of the photograph (a frame, a sheet) the phone taps and the
/// corner is pulled the last 2 pt onto it ("Magnes możliwie delikatny.
/// Raczej stuknięcie haptyki, a przyciągnięcie minimalne."). The same
/// screen cuts his own works' scans (`OwnWorkFlow`).
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
    /// The own work's steps go on: nothing to dismiss, and the bar (the
    /// arrow back, "Dalej") is theirs.
    let cancel: (() -> Void)?
    /// Saves the corners (of the work as shown); whether it went.
    let save: ([[Double]]) async -> Bool
    @Environment(\.dismiss) private var dismiss
    @State private var corners: [[Double]] = []
    @State private var start: [[Double]] = []
    @Environment(AppModel.self) private var model
    /// The corner last moved: drawn in amber.
    @State private var active: Int?
    /// The corner a drag on the photograph took.
    @State private var grab: Int?
    /// Where the corner would be by the finger alone, before the magnet.
    @State private var raw: [Double] = []
    /// The finger: where it was last, when, and how fast it moves (pt/s).
    @State private var finger: CGPoint?
    @State private var fingerAt: Date?
    @State private var speed: CGFloat = 0
    /// The corner lies on an edge of the photograph found by `EdgeMap`.
    @State private var onEdge = false
    /// Counts each time the corner meets an edge: a tap of the phone.
    @State private var edgeTaps = 0
    @State private var edges: EdgeMap?
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
    /// How much larger the photograph is in the loupe than on the screen.
    private static let zoom: CGFloat = 4
    /// The loupe's side.
    private static let loupeSide: CGFloat = 124
    /// How far from a corner on the photograph a finger still takes it: an
    /// 80 pt circle, well over Apple's 44 pt, as a corner is small and the
    /// work is often near the photograph's edge.
    private static let reach: CGFloat = 40
    /// The magnet: an edge this near (pt) takes the corner, and lets it go
    /// once the finger is past it; a finger faster than `fast` (pt/s) is
    /// never held.
    private static let pull: CGFloat = 2
    private static let fast: CGFloat = 400
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

    /// "Anuluj" and "Zapisz" over the photograph ("Popraw kadr").
    private var bar: some View {
        HStack {
            Button(cancelTitle) { dismiss() }
                .buttonStyle(.glass)
                .disabled(saving)
            Spacer()
            Button {
                Task {
                    saving = true
                    if await save(corners) { dismiss() }
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
    }

    /// "Dalej" in the bar of the own work's steps (the arrow back is theirs).
    private func saveInSteps() {
        Task {
            saving = true
            _ = await save(corners)
            saving = false
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            if cancel == nil { bar }
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
            Text("Przeciągnij narożnik. Wolny ruch palca ustawia go dokładniej.")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
                .multilineTextAlignment(.center)
                .padding(.horizontal, Theme.gutter)
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
        .sensoryFeedback(.impact(flexibility: .rigid, intensity: 0.55), trigger: edgeTaps)
        .toolbar {
            if cancel != nil {
                ToolbarItem(placement: .confirmationAction) {
                    Button(action: saveInSteps) {
                        if saving { ProgressView() } else { Text(saveTitle) }
                    }
                    .disabled(saving)
                }
            }
        }
        .onAppear {
            guard corners.isEmpty else { return }
            corners = initial ?? Self.inset
            start = initial ?? []
        }
        .task { await findEdges() }
    }

    /// The photograph's edges for the magnet, from the picture shown.
    private func findEdges() async {
        let image: UIImage?
        switch photoSource {
        case let .local(local):
            image = local
        case let .ref(ref):
            if let request = model.backend.request(for: ref) {
                image = try? await ImageLoader.shared.image(for: request, maxPixel: 2400, priority: .high)
            } else {
                image = nil
            }
        }
        guard let image else { return }
        let found = await Task.detached(priority: .userInitiated) { EdgeMap(image) }.value
        if !Task.isCancelled { edges = found }
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

    private func fitted(_ box: CGSize) -> CGSize {
        guard box.width > 0, box.height > 0 else { return .zero }
        let aspect = CGFloat(photoAspect)
        return box.width / box.height > aspect
            ? CGSize(width: box.height * aspect, height: box.height)
            : CGSize(width: box.width, height: box.width / aspect)
    }

    private func board(in space: CGSize) -> some View {
        let size = fitted(space)
        let origin = CGPoint(x: (space.width - size.width) / 2, y: (space.height - size.height) / 2)
        return ZStack(alignment: .topLeading) {
            photoWithCorners(size)
                .frame(width: size.width, height: size.height)
                .offset(x: origin.x, y: origin.y)
            grips(size: size, origin: origin, in: space)
            if let n = grab, let finger {
                let centre = loupeCentre(finger: finger, in: space)
                VStack(spacing: 6) {
                    loupe(n, photoSize: size)
                    if onEdge || gain(speed) < 0.4 {
                        Text(onEdge ? "na krawędzi" : "wolno: ¼")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(Theme.paper)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(Theme.ink.opacity(0.85), in: Capsule())
                    }
                }
                .frame(width: Self.loupeSide)
                .position(x: centre.x, y: centre.y + 14)
                .allowsHitTesting(false)
                .transition(.opacity)
            }
        }
        .frame(width: space.width, height: space.height, alignment: .topLeading)
        .animation(.easeOut(duration: 0.15), value: grab)
    }

    /// The loupe's centre: above the finger, as for text in iOS; when that
    /// is off the board (a top corner), beside the finger towards the middle.
    private func loupeCentre(finger: CGPoint, in space: CGSize) -> CGPoint {
        let side = Self.loupeSide
        let gap: CGFloat = 44
        var centre = CGPoint(x: finger.x, y: finger.y - side / 2 - gap)
        if centre.y - side / 2 < 0 {
            let toward: CGFloat = finger.x > space.width / 2 ? -1 : 1
            centre = CGPoint(x: finger.x + toward * (side / 2 + gap), y: finger.y)
        }
        centre.x = min(max(centre.x, side / 2), space.width - side / 2)
        centre.y = min(max(centre.y, side / 2), space.height - side / 2 - 22)
        return centre
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

    /// A corner on the photograph: a bracket along its two edges. It is
    /// dragged by `grips`.
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
                    .position(point)
                    .accessibilityElement()
                    .accessibilityLabel(Self.names[n])
                    .allowsHitTesting(false)
            }
    }

    /// How far the corner moves for each point the finger moves, by the
    /// finger's speed: a quarter at a slow finger (up to 60 pt/s), all of
    /// it from 400 pt/s, smoothly between (Mateusz 2026-11-17: „gdy palec
    /// jedzie wolniej, to celowanie jest dokładniejsze”).
    private func gain(_ speed: CGFloat) -> CGFloat {
        let slow: CGFloat = 60
        guard speed > slow else { return 0.25 }
        guard speed < Self.fast else { return 1 }
        let t = (speed - slow) / (Self.fast - slow)
        return 0.25 + 0.75 * t * t * (3 - 2 * t)
    }

    /// The corners on the photograph to drag: a circle of `reach` around
    /// each, also past the photograph's edge; where two meet, the corner
    /// nearer the finger. The corner moves with the finger's movement (by
    /// `gain`), not to it, so a finger beside it leaves it in sight.
    private func grips(size: CGSize, origin: CGPoint, in space: CGSize) -> some View {
        let points = corners.map { CGPoint(x: origin.x + $0[0] * size.width, y: origin.y + $0[1] * size.height) }
        return Color.clear
            .frame(width: space.width, height: space.height)
            .contentShape(Reach(points: points, radius: Self.reach))
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { drag in
                        guard size.width > 0, size.height > 0 else { return }
                        if grab == nil {
                            let at = drag.startLocation
                            grab = points.indices.min {
                                hypot(points[$0].x - at.x, points[$0].y - at.y) < hypot(points[$1].x - at.x, points[$1].y - at.y)
                            }
                            raw = grab.map { corners[$0] } ?? []
                            finger = at
                            fingerAt = drag.time
                            speed = 0
                            onEdge = false
                        }
                        guard let n = grab, raw.count == 2, let last = finger, let lastAt = fingerAt else { return }
                        active = n
                        let dx = drag.location.x - last.x, dy = drag.location.y - last.y
                        guard dx != 0 || dy != 0 else { return }
                        let dt = max(drag.time.timeIntervalSince(lastAt), 1.0 / 240)
                        // Smoothed, so one jerky event does not jump the gain.
                        speed = speed * 0.6 + hypot(dx, dy) / CGFloat(dt) * 0.4
                        finger = drag.location
                        fingerAt = drag.time
                        let g = gain(speed)
                        raw = Self.rounded(raw[0] + Double(dx * g / size.width), raw[1] + Double(dy * g / size.height))
                        corners[n] = magnet(n, size: size)
                    }
                    .onEnded { _ in
                        grab = nil
                        finger = nil
                        fingerAt = nil
                        onEdge = false
                    }
            )
            .accessibilityHidden(true)
    }

    /// Corner n where the finger puts it (`raw`), or on an edge of the
    /// photograph within `pull` of it, along each of its two sides: a tap
    /// of the phone when it comes onto one. Never for a fast finger.
    private func magnet(_ n: Int, size: CGSize) -> [Double] {
        var placed = raw
        var held = false
        if let edges, speed < Self.fast {
            let along = corners[[3, 2, 1, 0][n]]  // the other end of its upright side
            let across = corners[[1, 0, 3, 2][n]]  // the other end of its level side
            if let x = edges.upright(near: raw[0], from: raw[1], toward: along[1], within: Double(Self.pull / size.width)) {
                placed[0] = x
                held = true
            }
            if let y = edges.level(near: raw[1], from: raw[0], toward: across[0], within: Double(Self.pull / size.height)) {
                placed[1] = y
                held = true
            }
        }
        if held && !onEdge { edgeTaps += 1 }
        onEdge = held
        return Self.rounded(placed[0], placed[1])
    }

    private func corner(_ n: Int, in size: CGSize) -> CGPoint {
        let c = corners[n % 4]
        return CGPoint(x: c[0] * size.width, y: c[1] * size.height)
    }

    private static func rounded(_ x: Double, _ y: Double) -> [Double] {
        [(min(max(x, 0), 1) * 10000).rounded() / 10000, (min(max(y, 0), 1) * 10000).rounded() / 10000]
    }

    /// The photograph around corner n, `zoom` times larger, the cross on
    /// the corner, the work's edges drawn.
    private func loupe(_ n: Int, photoSize: CGSize) -> some View {
        let side = Self.loupeSide
        let large = CGSize(width: photoSize.width * Self.zoom, height: photoSize.height * Self.zoom)
        let point = CGPoint(x: corners[n][0] * large.width, y: corners[n][1] * large.height)
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
        .overlay(Circle().strokeBorder(Self.mark, lineWidth: 3))
        .shadow(color: .black.opacity(0.3), radius: 8, y: 3)
    }
}

/// Strong straight edges of a photograph (a frame, a sheet's border) for
/// the corners' magnet: the change of brightness across each pixel of a
/// small grey copy, sideways (upright edges) and up and down (level ones).
struct EdgeMap: Sendable {
    let width: Int
    let height: Int
    private let sideways: [Float]
    private let upDown: [Float]

    /// The copy's long side: 1/640 of the photograph is under a point of a
    /// phone's screen, and the map stays small.
    init?(_ image: UIImage, long: CGFloat = 640) {
        let scale = long / max(image.size.width, image.size.height, 1)
        let w = max(Int((image.size.width * scale).rounded()), 3)
        let h = max(Int((image.size.height * scale).rounded()), 3)
        // Drawn upright (a photo from the camera keeps its orientation).
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let small = UIGraphicsImageRenderer(size: CGSize(width: w, height: h), format: format).image { _ in
            image.draw(in: CGRect(x: 0, y: 0, width: w, height: h))
        }
        guard let cg = small.cgImage else { return nil }
        var grey = [UInt8](repeating: 0, count: w * h)
        let drawn = grey.withUnsafeMutableBytes { bytes -> Bool in
            guard let context = CGContext(
                data: bytes.baseAddress, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w,
                space: CGColorSpaceCreateDeviceGray(), bitmapInfo: CGImageAlphaInfo.none.rawValue
            ) else { return false }
            context.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
            return true
        }
        guard drawn else { return nil }
        var sideways = [Float](repeating: 0, count: w * h)
        var upDown = [Float](repeating: 0, count: w * h)
        for y in 1 ..< h - 1 {
            for x in 1 ..< w - 1 {
                func g(_ dx: Int, _ dy: Int) -> Float { Float(grey[(y + dy) * w + x + dx]) }
                let gx = (g(1, -1) + 2 * g(1, 0) + g(1, 1)) - (g(-1, -1) + 2 * g(-1, 0) + g(-1, 1))
                let gy = (g(-1, 1) + 2 * g(0, 1) + g(1, 1)) - (g(-1, -1) + 2 * g(0, -1) + g(1, -1))
                sideways[y * w + x] = abs(gx)
                upDown[y * w + x] = abs(gy)
            }
        }
        width = w
        height = h
        self.sideways = sideways
        self.upDown = upDown
    }

    /// An upright edge within `within` of `x` (fractions of the width),
    /// looked for along the corner's side, from `from` toward `toward`
    /// (fractions of the height); nil when nothing there stands out.
    func upright(near x: Double, from: Double, toward: Double, within: Double) -> Double? {
        strongest(
            near: x * Double(width), within: max(within * Double(width), 1), length: width,
            from: from * Double(height), toward: toward * Double(height), depth: height
        ) { across, along in sideways[along * width + across] }
            .map { $0 / Double(width) }
    }

    /// A level edge within `within` of `y`, along the corner's other side.
    func level(near y: Double, from: Double, toward: Double, within: Double) -> Double? {
        strongest(
            near: y * Double(height), within: max(within * Double(height), 1), length: height,
            from: from * Double(width), toward: toward * Double(width), depth: width
        ) { across, along in upDown[across * width + along] }
            .map { $0 / Double(height) }
    }

    /// The line across (column or row) near `near` whose change, summed
    /// over a stretch of the side from the corner inwards, is clearly the
    /// strongest around: at least twice the mean of the lines nearby and
    /// not faint. Sub-pixel, by a parabola through the best and its two
    /// neighbours.
    private func strongest(
        near: Double, within: Double, length: Int, from: Double, toward: Double, depth: Int,
        value: (Int, Int) -> Float
    ) -> Double? {
        let direction: Double = toward >= from ? 1 : -1
        let stretch = min(abs(toward - from) * 0.4, Double(depth) * 0.2)
        guard stretch >= 4 else { return nil }
        let start = Int(from.rounded()), end = Int((from + direction * stretch).rounded())
        let lo = max(min(start, end), 1), hi = min(max(start, end), depth - 2)
        guard hi > lo else { return nil }
        let reach = Int(within.rounded(.up)) + 3
        let first = max(Int(near.rounded()) - reach, 1), last = min(Int(near.rounded()) + reach, length - 2)
        guard last - first >= 2 else { return nil }
        var sums = [Float]()
        for across in first ... last {
            var sum: Float = 0
            for along in lo ... hi { sum += value(across, along) }
            sums.append(sum / Float(hi - lo + 1))
        }
        guard let best = sums.indices.max(by: { sums[$0] < sums[$1] }) else { return nil }
        let mean = sums.reduce(0, +) / Float(sums.count)
        // Sobel of 0–255 greys: 4 × a step of brightness; 60 ≈ a step of 15.
        guard sums[best] >= 60, sums[best] >= 2 * mean else { return nil }
        var at = Double(first + best)
        if best > 0, best < sums.count - 1 {
            let a = Double(sums[best - 1]), b = Double(sums[best]), c = Double(sums[best + 1])
            let bend = a - 2 * b + c
            if bend < 0 { at += 0.5 * (a - c) / bend }
        }
        // The edge lies between pixels: the map's pixel x covers x…x+1.
        let edge = at + 0.5
        return abs(edge - near) <= within ? edge : nil
    }
}

/// Circles of `radius` around `points`: where a finger takes a corner.
private struct Reach: Shape {
    let points: [CGPoint]
    let radius: CGFloat

    func path(in _: CGRect) -> Path {
        var path = Path()
        for point in points {
            path.addEllipse(in: CGRect(x: point.x - radius, y: point.y - radius, width: 2 * radius, height: 2 * radius))
        }
        return path
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
