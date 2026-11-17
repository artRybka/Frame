import SwiftUI
import UIKit

/// The original on a dark screen of its own, opened filling the screen:
/// pinch out or double-tap to see it whole, pinch or double-tap to look
/// closer, drag to look around, tap to hide the caption, close with the
/// cross or a swipe down (no sun button; Mateusz 2026-11-09, the cross back
/// 2026-11-10). With "Jaśniejsze dzieła"
/// on in Konfiguracja the screen comes up to full brightness on the way in
/// and dims back as soon as the viewer starts to close. A work kept also as a
/// set of sharper tiles (Commons; Mateusz 2026-11-09) gets them laid on it
/// while zooming in, only those in view.
struct OriginalViewer: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage(ArtGlow.key) private var brighten = true
    let item: Item
    /// Opened showing the picture whole, not filling the screen: "Do
    /// sprawdzenia", where what is wrong is often at an edge (a ruler, a
    /// colour chart, a cut corner; Mateusz 2026-11-15).
    var whole = false
    /// Opened on "W ramie" (`FrameToggle`): the work in its frame, as the
    /// card showed it; its button under the cross shows the work alone.
    var inFrame = false
    @State private var framedOn = false
    @State private var framedImage: UIImage?
    @State private var framedLoading = false
    @State private var image: UIImage?
    @State private var failed = false
    @State private var chrome = true
    @State private var tiles: [ZoomTile] = []
    /// The picture is made of the tiles' own thumbnails: the work's picture
    /// may be another photograph (another copy, another crop, other
    /// colours), and the tiles would not lie on it (Mateusz 2026-11-09,
    /// Bosch's "Garden" bluish under yellowish tiles, a giraffe beside a boar).
    @State private var underlay = false
    /// What was done to the picture and is left off at the owner's tap on
    /// its button under the cross (`Treatment`; Mateusz 2026-11-16): the
    /// buttons say this at once…
    @State private var off: Set<Treatment> = []
    /// …and the picture this, once it has come: until then the one before
    /// stays (no blink to the original between two left-off pictures).
    @State private var shownOff: Set<Treatment> = []
    /// The pictures with some left off, as they came, by what is left off.
    @State private var treated: [Set<Treatment>: UIImage] = [:]
    @State private var treatFailed = false

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            if let picture = framedOn ? framedImage : shownImage {
                // One view for the work and the work in its frame: the work
                // stays where it is on the screen as its frame comes and
                // goes (Mateusz 2026-11-17: „przełączenie pomiędzy widokiem
                // w ramie i bez jest płynne i zachowuje zoom”).
                ZoomableImage(
                    image: picture, tiles: framedOn || !shownOff.isEmpty ? [] : tiles, whole: whole || inFrame,
                    look: Treatment.look(framedOn ? [] : shownOff), inner: framedOn ? item.framed?.inner : nil
                ) {
                    withAnimation(.easeInOut(duration: 0.2)) { chrome.toggle() }
                }
                .ignoresSafeArea()
            } else if failed {
                Label("Nie udało się wczytać obrazu", systemImage: "photo")
                    .font(.subheadline)
                    .foregroundStyle(.white.opacity(0.7))
            } else {
                ProgressView().tint(.white)
            }
        }
        .overlay(alignment: .topTrailing) {
            if chrome {
                VStack(alignment: .trailing, spacing: 12) {
                    Button(action: close) {
                        Image(systemName: "xmark")
                            .font(.headline)
                            .foregroundStyle(.white)
                            .frame(width: 40, height: 40)
                            .background(.black.opacity(0.5), in: Circle())
                    }
                    .accessibilityLabel("Zamknij")
                    // Under the cross, only for what was done (Mateusz
                    // 2026-11-16, the places marked on his screenshot).
                    if let look = item.framed {
                        FrameViewerButton(look: look, on: framedOn, loading: framedLoading) {
                            Task { await toggleFramed() }
                        }
                    }
                    ForEach(framedOn ? [] : treatments, id: \.self) { treatment in
                        TreatmentButton(
                            treatment: treatment, on: !off.contains(treatment),
                            loading: off != shownOff && off.contains(treatment) != shownOff.contains(treatment)
                        ) { toggle(treatment) }
                    }
                    if treatFailed {
                        Text("Nie udało się wczytać")
                            .font(.caption)
                            .foregroundStyle(.white)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(.black.opacity(0.5), in: Capsule())
                            .transition(.opacity)
                    }
                }
                .padding(.trailing, 16)
                .padding(.top, 8)
                .transition(.opacity)
            }
        }
        .overlay(alignment: .bottom) {
            if chrome { caption.transition(.opacity) }
        }
        .statusBarHidden(!chrome)
        // VoiceOver's two-finger scrub closes it, as the cross does.
        .accessibilityAction(.escape, close)
        .task(id: item.id) { await load() }
        .task(id: item.id) {
            if inFrame { await toggleFramed() }
            // Simulator recordings: `-frameCycle 4` turns the frame on and
            // off that many times (demo only).
            let cycles = model.demoMode ? UserDefaults.standard.integer(forKey: "frameCycle") : 0
            for _ in 0 ..< cycles * 2 {
                try? await Task.sleep(for: .seconds(2.5))
                if Task.isCancelled { return }
                await toggleFramed()
            }
        }
        .task(id: item.fragmentsID) { await loadTiles() }
        .task(id: off) { await loadTreated() }
        .onAppear {
            // CI screenshots: the work shown without all that was done.
            if model.demoMode, LaunchRoute.sheet == "untreated" { off = Set(treatments) }
        }
        .onAppear { if brighten { ScreenBoost.shared.raise() } }
        // A swipe down starts closing long before the screen is gone: the
        // brightness goes back from its first frame (and comes up again
        // if the swipe is let go).
        .background {
            Appearance(willDisappear: { ScreenBoost.shared.restore() },
                       willAppear: { if brighten { ScreenBoost.shared.raise() } })
        }
        .onDisappear { ScreenBoost.shared.restore() }
        .onChange(of: brighten) { _, on in
            if on { ScreenBoost.shared.raise() } else { ScreenBoost.shared.restore() }
        }
        .onChange(of: scenePhase) { _, phase in
            // iOS gives the owner's brightness back in the background.
            if phase == .background { ScreenBoost.shared.forget() }
            if phase == .active, brighten { ScreenBoost.shared.raise() }
        }
    }

    /// "W ramie" on and off: the framed photograph, fetched once.
    private func toggleFramed() async {
        UISelectionFeedbackGenerator().selectionChanged()
        if framedOn {
            framedOn = false  // the picture itself moves (`ZoomScrollView.swap`)
            return
        }
        if framedImage == nil {
            guard let look = item.framed else { return }
            framedLoading = true
            let version = "\(item.pictureVersion)|\(look.kind)\(look.aspect)\(look.inner.minX)\(look.inner.minY)\(look.inner.width)"
            if let request = model.backend.request(for: .framed(item.id, side: 4000, version: version)) {
                framedImage = try? await ImageLoader.shared.image(for: request, maxPixel: 4096, priority: .high)
            }
            framedLoading = false
        }
        if framedImage != nil { framedOn = true }
    }

    /// What was done to the work's picture, in the buttons' order.
    private var treatments: [Treatment] { Treatment.done(on: item) }

    /// The picture with what is left off, once it came; else the work's.
    private var shownImage: UIImage? {
        shownOff.isEmpty ? image : treated[shownOff] ?? image
    }

    private func toggle(_ treatment: Treatment) {
        UISelectionFeedbackGenerator().selectionChanged()
        withAnimation(.easeInOut(duration: 0.2)) {
            treatFailed = false
            if off.contains(treatment) { off.remove(treatment) } else { off.insert(treatment) }
        }
    }

    /// The picture with `off` left off, from the server (made there once
    /// and kept in the app's cache by its address); the work's own at once
    /// when nothing is. A picture that does not come puts the buttons back
    /// as the picture shown is.
    private func loadTreated() async {
        let wanted = off
        if wanted.isEmpty || treated[wanted] != nil {
            shownOff = wanted
            return
        }
        guard let ref = Treatment.ref(item, off: wanted), let request = model.backend.request(for: ref) else { return }
        let loaded = try? await ImageLoader.shared.image(for: request, maxPixel: 4096, priority: .high)
        if Task.isCancelled || wanted != off { return }
        if let loaded {
            treated[wanted] = model.demoMode ? Treatment.demo(loaded, off: wanted) : loaded
            shownOff = wanted
        } else {
            withAnimation(.easeInOut(duration: 0.2)) {
                off = shownOff
                treatFailed = true
            }
        }
    }

    /// Dimming starts with the closing, not after it.
    private func close() {
        ScreenBoost.shared.restore()
        dismiss()
    }

    private var caption: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(bound: item.displayTitle.isEmpty ? "Bez tytułu" : item.displayTitle)
                .font(.serif(19, weight: .semibold))
                .lineLimit(2)
            let line = item.kind == .photo
                ? item.photoLine
                : [Names.artist(item.artist), item.dateText].filter { !$0.isEmpty }.joined(separator: " · ")
            if !line.isEmpty {
                Text(bound: line).font(.footnote).opacity(0.75)
            }
            if !tiles.isEmpty, shownOff.isEmpty {
                Label("Przybliż, a ostrzejsze fragmenty (\(tiles.count)) doczytają się same",
                      systemImage: "square.grid.3x3")
                    .font(.caption)
                    .opacity(0.6)
                    .padding(.top, 2)
            }
        }
        .foregroundStyle(.white)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, Theme.gutter)
        .padding(.top, 36)
        .padding(.bottom, 12)
        .background(
            LinearGradient(colors: [.clear, .black.opacity(0.65)], startPoint: .top, endPoint: .bottom)
                .ignoresSafeArea()
        )
        .allowsHitTesting(false)
    }

    /// The tile's thumbnail at once (in memory already, so the screen is
    /// never a lone spinner while the original comes), then the copy the
    /// detail screen shows, then a sharper one to zoom into.
    private func load() async {
        if let request = model.backend.request(for: ItemPeeks.tiles[item.id]?.thumb ?? .thumb(item.id)),
           let thumb = try? await ImageLoader.shared.image(for: request, maxPixel: 700, priority: .high) {
            if !underlay { image = thumb }
        }
        for maxPixel: CGFloat in [1800, 4096] {
            guard let request = model.backend.request(for: item.originalRef) else { break }
            if let loaded = try? await ImageLoader.shared.image(for: request, maxPixel: maxPixel, priority: .high) {
                if !underlay { image = loaded }
            }
            if Task.isCancelled { return }
        }
        failed = image == nil
    }

    fileprivate func setTiles(_ found: [ZoomTile]) { tiles = found }

    /// The work's tiles with their places, when the server knows them
    /// (Commons tile sets; Cleveland's scroll sections have none yet).
    private func loadTiles() async {
        if item.isOwnWork {
            await loadFine()
            return
        }
        let ids = [item.fragmentsID, item.id]
        guard !item.isFragment, ids.contains(where: { $0.hasPrefix("wmc:") || $0.hasPrefix("cma:") }),
              let view = await Fragments.load(shownWith: item, backend: model.backend),
              let places = view.places, !places.isEmpty
        else { return }
        let fragments = Dictionary(view.fragments.map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a })
        var found: [(tile: ZoomTile, thumb: URLRequest, item: Item)] = []
        for place in places {
            guard let fragment = fragments[place.id], place.w > 0, place.h > 0,
                  let request = model.backend.request(for: fragment.item.originalRef),
                  let thumb = model.backend.request(for: fragment.thumb)
            else { return }  // a hole in the grid: no tiles at all
            let tile = ZoomTile(id: place.id, unit: place.unit,
                                pixels: ZoomTile.keptWidth(fragment.item.width, fragment.item.height),
                                request: request)
            found.append((tile, thumb, fragment.item))
        }
        // The thumbnails first, all of them, laid into one picture.
        let thumbs = await withTaskGroup(of: (Int, UIImage?).self) { group in
            for (index, entry) in found.enumerated() {
                let request = entry.thumb
                group.addTask {
                    (index, try? await ImageLoader.shared.image(for: request, maxPixel: 600, priority: .high))
                }
            }
            var thumbs = [UIImage?](repeating: nil, count: found.count)
            for await (index, image) in group { thumbs[index] = image }
            return thumbs
        }
        let laid = zip(found, thumbs).compactMap { entry, thumb in thumb.map { (unit: entry.tile.unit, image: $0) } }
        guard !Task.isCancelled, laid.count == found.count,
              let first = found.first,
              let mosaic = ZoomTile.mosaic(laid, shape: ZoomTile.gridShape(first.tile.unit, first.item))
        else { return }
        underlay = true
        image = mosaic
        tiles = found.map { $0.tile }
    }
}

extension OriginalViewer {
    /// A work of his own: the tiles of his photograph's every pixel, laid
    /// on its original (the same picture, so no underlay of thumbnails).
    fileprivate func loadFine() async {
        guard let fine = try? await model.backend.fine(itemID: item.id), !fine.tiles.isEmpty else { return }
        let found = fine.tiles.compactMap { tile -> ZoomTile? in
            guard tile.w > 0, tile.h > 0,
                  let request = model.backend.request(for: .fine(item.id, tile: tile.id, version: fine.stamp))
            else { return nil }
            return ZoomTile(id: tile.id, unit: tile.unit, pixels: CGFloat(tile.pixels), request: request)
        }
        guard !Task.isCancelled, found.count == fine.tiles.count else { return }
        setTiles(found)
    }
}

/// A sharper picture of one part of the whole, laid on it while zooming:
/// `unit` is its place as fractions of the whole, `pixels` how wide it
/// comes from the server.
struct ZoomTile: Equatable {
    let id: String
    let unit: CGRect
    let pixels: CGFloat
    let request: URLRequest

    /// Zooming in goes no deeper than this, however large the tiles.
    static let deepestZoom: CGFloat = 48

    /// How far the full screen zooms in: as deep as the tiles' pixels reach
    /// (`across`, the whole's width in them) one to one of the screen's
    /// (`shown`, the picture's width fitted on it), at least 8 (no tiles).
    static func depth(across: CGFloat, shown: CGFloat) -> CGFloat {
        guard across > 0, shown > 0 else { return 8 }
        return min(deepestZoom, max(8, across / shown))
    }

    /// The same for a work's tile set fitted on this screen, as the card
    /// tells it ("17×"); nil without places.
    @MainActor
    static func depth(of view: FragmentsView, screen: CGSize, scale: CGFloat) -> Int? {
        guard let places = view.places, !places.isEmpty, screen.width > 0, screen.height > 0 else { return nil }
        let items = Dictionary(view.fragments.map { ($0.id, $0.item) }, uniquingKeysWith: { a, _ in a })
        var across: CGFloat = 0
        var shape: CGFloat?
        for place in places where place.w > 0 {
            guard let tile = items[place.id] else { continue }
            across = max(across, keptWidth(tile.width, tile.height) / place.w)
            shape = shape ?? gridShape(place.unit, tile)
        }
        guard let shape, across > 0 else { return nil }
        let fitted = min(screen.width, screen.height * shape)
        return Int(depth(across: across, shown: fitted * scale).rounded())
    }

    /// The long side the server keeps a tile at (`images.TILE_MAX`, Commons'
    /// widest rendition; 2560 before 2026-11-10).
    static let keptSide: CGFloat = 3840

    /// The width the server keeps a tile of this size at.
    static func keptWidth(_ width: Int?, _ height: Int?) -> CGFloat {
        guard let width, let height, width > 0, height > 0 else { return keptSide }
        let long = CGFloat(max(width, height))
        return (CGFloat(width) * min(1, keptSide / long)).rounded()
    }

    /// Width / height of the whole grid, from one tile's size and place.
    static func gridShape(_ unit: CGRect, _ tile: Item) -> CGFloat? {
        guard let width = tile.width, let height = tile.height, width > 0, height > 0,
              unit.width > 0, unit.height > 0 else { return nil }
        return (CGFloat(width) / unit.width) / (CGFloat(height) / unit.height)
    }

    /// The tiles' pictures laid side by side into one, each in its place:
    /// as sharp as they are (at most 4096 px wide), of `shape`.
    static func mosaic(_ laid: [(unit: CGRect, image: UIImage)], shape: CGFloat?) -> UIImage? {
        guard let shape, shape > 0, !laid.isEmpty else { return nil }
        let across = laid.map { $0.image.size.width * $0.image.scale / max($0.unit.width, 0.001) }.max() ?? 0
        let width = min(4096, max(1, across.rounded()))
        let size = CGSize(width: width, height: max(1, (width / shape).rounded()))
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = true
        return UIGraphicsImageRenderer(size: size, format: format).image { context in
            UIColor.black.setFill()
            context.fill(CGRect(origin: .zero, size: size))
            for (unit, image) in laid {
                // Whole pixels, a hair over: no seams between tiles.
                let rect = CGRect(x: unit.minX * size.width, y: unit.minY * size.height,
                                  width: unit.width * size.width, height: unit.height * size.height)
                    .integral
                image.draw(in: rect.insetBy(dx: -0.5, dy: -0.5))
            }
        }
    }
}

/// A picture in a scroll view, shown filling the view (centred, the sides
/// that do not fit off screen): pinch to zoom, drag around, double-tap to
/// see it whole and to zoom back in on a spot, single tap for `onTap`.
struct ZoomableImage: UIViewRepresentable {
    let image: UIImage
    var tiles: [ZoomTile] = []
    /// Opened whole (fitted), not filling the view.
    var whole = false
    /// Which version of the work the picture is (`Treatment.look`): a new
    /// one fades in over the one before, a sharper copy of the same does not.
    var look = 0
    /// The picture is the work in its frame ("W ramie"): where the work
    /// lies in it (fractions). Going from the work to it and back keeps
    /// the work where it is on the screen (`ZoomScrollView.swap`).
    var inner: CGRect?
    var onTap: () -> Void = {}

    func makeUIView(context: Context) -> ZoomScrollView { ZoomScrollView() }

    func updateUIView(_ view: ZoomScrollView, context: Context) {
        view.onTap = onTap
        view.startsWhole = whole
        view.show(image, look: look, inner: inner)
        view.lay(tiles)
    }
}

final class ZoomScrollView: UIScrollView, UIScrollViewDelegate {
    private let imageView = UIImageView()
    var onTap: () -> Void = {}
    /// The bounds the picture was last fitted to.
    private var fitted: CGSize = .zero
    /// The zoom at which the picture covers the whole view; it opens there.
    private var fillScale: CGFloat = 1
    /// Laid out whole (the smallest scale) rather than filling the view.
    var startsWhole = false
    /// The version of the work shown (`ZoomableImage.look`).
    private var shownLook = 0
    static let lookFade: TimeInterval = 0.18
    /// Sharper pictures of parts of it, laid on it while zooming in.
    private var tiles: [ZoomTile] = []
    /// The tiles on the picture now, by id, and the size each was asked in.
    private var tileViews: [String: UIImageView] = [:]
    private var tileSizes: [String: CGFloat] = [:]
    private var tileLoads: [String: Task<Void, Never>] = [:]
    /// The look at which tiles are in view after a zoom or a drag settles.
    private var settling: Task<Void, Never>?
    private var lookedAt: CFTimeInterval = 0
    /// The sizes a tile comes in, smallest first: the least that covers
    /// what it takes on the screen (a full 3840 px tile decoded is 59 MB).
    private static let tileSteps: [CGFloat] = [1280, 2560]

    init() {
        super.init(frame: .zero)
        delegate = self
        showsVerticalScrollIndicator = false
        showsHorizontalScrollIndicator = false
        contentInsetAdjustmentBehavior = .never
        decelerationRate = .fast
        backgroundColor = .clear
        minimumZoomScale = 1
        maximumZoomScale = 8
        imageView.contentMode = .scaleAspectFit
        addSubview(imageView)

        let double = UITapGestureRecognizer(target: self, action: #selector(doubleTapped(_:)))
        double.numberOfTapsRequired = 2
        addGestureRecognizer(double)
        let single = UITapGestureRecognizer(target: self, action: #selector(tapped))
        single.require(toFail: double)
        addGestureRecognizer(single)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    /// Where the work lies in the picture shown when that is the work in
    /// its frame (`ZoomableImage.inner`); nil for the work alone.
    private var shownInner: CGRect?
    /// A move between the work and its frame is under way: the zoom may
    /// be out of its usual bounds until it settles.
    private var swapping = false
    static let swapFade: TimeInterval = 0.25
    static let settleTime: TimeInterval = 0.45

    /// A sharper copy of the same picture keeps the zoom and place; another
    /// shape is fitted afresh; the work and the work in its frame keep the
    /// work where it is (`swap`).
    func show(_ image: UIImage, look: Int = 0, inner: CGRect? = nil) {
        guard imageView.image !== image else { return }
        if inner != shownInner, imageView.image != nil, fitted == bounds.size, bounds.width > 0,
           let within = Self.within(from: shownInner, to: inner) {
            shownInner = inner
            shownLook = look
            swap(to: image, oldWithin: within, framing: inner)
            return
        }
        shownInner = inner
        let sameShape = imageView.image.map {
            abs($0.size.width / max($0.size.height, 1) - image.size.width / max(image.size.height, 1)) < 0.01
        } ?? false
        if look != shownLook, imageView.image != nil {
            // The work with or without what was done to it: a quick fade,
            // not a jump (Mateusz 2026-11-16: "Bardzo szybkie, ale przejście").
            UIView.transition(
                with: imageView, duration: Self.lookFade,
                options: [.transitionCrossDissolve, .allowUserInteraction, .beginFromCurrentState],
                animations: { self.imageView.image = image }
            )
        } else {
            imageView.image = image
        }
        shownLook = look
        if !sameShape {
            fitted = .zero
            setNeedsLayout()
        }
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        guard bounds.size != fitted, bounds.width > 0, bounds.height > 0,
              let size = imageView.image?.size, size.width > 0, size.height > 0
        else { return }
        fitted = bounds.size
        zoomScale = 1
        let scale = min(bounds.width / size.width, bounds.height / size.height)
        imageView.frame = CGRect(x: 0, y: 0, width: size.width * scale, height: size.height * scale)
        contentSize = imageView.frame.size
        deepest()
        let fill = max(bounds.width / imageView.frame.width, bounds.height / imageView.frame.height)
        fillScale = min(maximumZoomScale, max(minimumZoomScale, fill))
        zoomScale = startsWhole ? minimumZoomScale : fillScale
        centre()
        // The middle of the picture in the middle of the view.
        contentOffset = startsWhole
            ? CGPoint(x: -contentInset.left, y: -contentInset.top)
            : CGPoint(x: (contentSize.width - bounds.width) / 2,
                      y: (contentSize.height - bounds.height) / 2)
        for tile in tiles { tileViews[tile.id]?.frame = rect(of: tile) }
        lookAtTiles()
    }

    // MARK: The work and its frame

    /// Where the picture shown so far lies in the next (fractions of it):
    /// the work in its frame, or the frame around the work.
    private static func within(from old: CGRect?, to new: CGRect?) -> CGRect? {
        if let new, old == nil { return new }
        if let old, new == nil, old.width > 0, old.height > 0 {
            return CGRect(x: -old.minX / old.width, y: -old.minY / old.height,
                          width: 1 / old.width, height: 1 / old.height)
        }
        return nil
    }

    /// The other picture in place of this one with the work where it is on
    /// the screen, the two crossing in a quick fade; then, only where it
    /// must, a gentle move: the work alone smaller than the screen holds it
    /// whole grows to fit, a frame not in sight at all comes into view whole.
    private func swap(to image: UIImage, oldWithin r: CGRect, framing inner: CGRect?) {
        let old = imageView.frame.offsetBy(dx: -contentOffset.x, dy: -contentOffset.y)
        let width = old.width / r.width, height = old.height / r.height
        let shown = CGRect(x: old.minX - r.minX * width, y: old.minY - r.minY * height, width: width, height: height)
        swapping = true
        UIView.transition(
            with: self, duration: Self.swapFade,
            options: [.transitionCrossDissolve, .allowUserInteraction],
            animations: {
                self.imageView.image = image
                self.refit(showing: shown)
            },
            completion: { _ in self.settle(framing: inner) }
        )
    }

    /// The place within what a drag may reach (the picture's edges, or its
    /// middle when it is smaller than the view).
    private var heldOffset: CGPoint {
        let lowest = CGPoint(x: -contentInset.left, y: -contentInset.top)
        let highest = CGPoint(x: contentSize.width - bounds.width + contentInset.right,
                              y: contentSize.height - bounds.height + contentInset.bottom)
        return CGPoint(x: min(max(contentOffset.x, lowest.x), max(highest.x, lowest.x)),
                       y: min(max(contentOffset.y, lowest.y), max(highest.y, lowest.y)))
    }

    /// Fitted to the view anew, at the zoom and place that show the picture
    /// at `shown` (on the screen).
    private func refit(showing shown: CGRect) {
        guard let size = imageView.image?.size, size.width > 0, size.height > 0 else { return }
        minimumZoomScale = min(minimumZoomScale, 1)
        zoomScale = 1
        let base = min(bounds.width / size.width, bounds.height / size.height)
        imageView.frame = CGRect(x: 0, y: 0, width: size.width * base, height: size.height * base)
        contentSize = imageView.frame.size
        fitted = bounds.size
        let fill = max(bounds.width / imageView.frame.width, bounds.height / imageView.frame.height)
        fillScale = min(depth, max(1, fill))
        let zoom = shown.width / max(imageView.frame.width, 1)
        minimumZoomScale = min(1, zoom)
        maximumZoomScale = max(depth, zoom)
        zoomScale = zoom
        centre()
        contentOffset = CGPoint(x: -shown.minX, y: -shown.minY)
    }

    /// After `swap`: the zoom back within its bounds, gently.
    private func settle(framing inner: CGRect?) {
        let seen = convert(bounds, to: imageView)
        let unit = CGRect(x: seen.minX / max(imageView.bounds.width, 1), y: seen.minY / max(imageView.bounds.height, 1),
                          width: seen.width / max(imageView.bounds.width, 1),
                          height: seen.height / max(imageView.bounds.height, 1))
        let frameUnseen = inner.map { $0.insetBy(dx: -0.002, dy: -0.002).contains(unit) } ?? false
        let target: CGFloat? = if zoomScale < 0.999 || frameUnseen {
            1  // whole
        } else if zoomScale > depth * 1.001 {
            depth
        } else {
            nil
        }
        guard let target else {
            swapping = false
            minimumZoomScale = 1
            deepest()
            // Looking at the frame's edge, the frame gone: the work's
            // nearest part slides in, as a drag past the edge would.
            let held = heldOffset
            if held != contentOffset {
                UIView.animate(
                    withDuration: Self.settleTime, delay: 0,
                    options: [.curveEaseInOut, .allowUserInteraction, .beginFromCurrentState],
                    animations: { self.contentOffset = held }
                )
            }
            return
        }
        // Around the middle of what is in view, or the whole picture.
        let middle = CGPoint(x: seen.midX, y: seen.midY)
        UIView.animate(
            withDuration: Self.settleTime, delay: 0,
            options: [.curveEaseInOut, .allowUserInteraction, .beginFromCurrentState],
            animations: {
                self.zoomScale = target
                self.centre()
                let content = self.imageView.frame.size
                if target <= 1 {
                    self.contentOffset = CGPoint(x: (content.width - self.bounds.width) / 2,
                                                 y: (content.height - self.bounds.height) / 2)
                } else {
                    self.contentOffset = CGPoint(x: middle.x * target - self.bounds.width / 2,
                                                 y: middle.y * target - self.bounds.height / 2)
                }
            },
            completion: { _ in
                self.swapping = false
                self.minimumZoomScale = 1
                self.deepest()
                self.lookAtTiles()
            }
        )
    }

    // MARK: Tiles

    /// Lays `new` tiles on the picture (none until zoomed in past what the
    /// picture itself shows).
    func lay(_ new: [ZoomTile]) {
        guard new != tiles else { return }
        for view in tileViews.values { view.removeFromSuperview() }
        for load in tileLoads.values { load.cancel() }
        tileViews = [:]
        tileSizes = [:]
        tileLoads = [:]
        tiles = new
        deepest()
        lookAtTiles()
    }

    /// With tiles, zooming goes as deep as their pixels reach (one of
    /// theirs to one of the screen's), within reason.
    private func deepest() {
        maximumZoomScale = swapping ? max(depth, zoomScale) : depth
    }

    /// How deep zooming goes for the picture and its tiles.
    private var depth: CGFloat {
        let across = tiles.map { $0.pixels / max($0.unit.width, 0.001) }.max() ?? 0
        return ZoomTile.depth(across: across, shown: imageView.bounds.width * traitCollection.displayScale)
    }

    private func rect(of tile: ZoomTile) -> CGRect {
        let size = imageView.bounds.size
        return CGRect(x: tile.unit.minX * size.width, y: tile.unit.minY * size.height,
                      width: tile.unit.width * size.width, height: tile.unit.height * size.height)
    }

    /// Looks again at once now and then while a zoom or a drag goes on,
    /// and once more when it stops.
    private func tilesMoved() {
        guard !tiles.isEmpty else { return }
        if CACurrentMediaTime() - lookedAt > 0.3 { lookAtTiles() }
        settling?.cancel()
        settling = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(150))
            guard !Task.isCancelled else { return }
            self?.lookAtTiles()
        }
    }

    /// Asks for the tiles in view that show more than the picture there
    /// (in a size to what they cover on the screen), and lets go of the
    /// rest: a tile set is far too large to hold whole.
    private func lookAtTiles() {
        lookedAt = CACurrentMediaTime()
        guard !tiles.isEmpty, let picture = imageView.image, imageView.bounds.width > 0 else { return }
        let seen = convert(bounds, to: imageView)
        let near = seen.insetBy(dx: -seen.width * 0.15, dy: -seen.height * 0.15)
        let screen = traitCollection.displayScale
        let pictureWidth = picture.size.width * picture.scale
        for tile in tiles {
            let place = rect(of: tile)
            let onScreen = place.width * zoomScale * screen
            let inPicture = tile.unit.width * pictureWidth
            let wanted: CGFloat? = if !near.intersects(place) || onScreen <= inPicture * 1.2 {
                nil
            } else {
                Self.tileSteps.first { onScreen <= $0 && tile.pixels > $0 * 1.2 } ?? tile.pixels
            }
            guard let wanted else {
                drop(tile.id)
                continue
            }
            if tileSizes[tile.id] != wanted { load(tile, size: wanted) }
        }
    }

    private func load(_ tile: ZoomTile, size: CGFloat) {
        tileSizes[tile.id] = size
        tileLoads[tile.id]?.cancel()
        tileLoads[tile.id] = Task { [weak self] in
            let image = try? await ImageLoader.shared.image(for: tile.request, maxPixel: size)
            guard let image, !Task.isCancelled, let self else { return }
            self.put(image, on: tile)
        }
    }

    private func put(_ image: UIImage, on tile: ZoomTile) {
        guard tileSizes[tile.id] != nil else { return }
        if let view = tileViews[tile.id] {
            view.image = image  // a sharper (or lighter) one in its place
            return
        }
        let view = UIImageView(image: image)
        view.contentMode = .scaleToFill
        view.frame = rect(of: tile)
        view.alpha = 0
        imageView.addSubview(view)
        tileViews[tile.id] = view
        UIView.animate(withDuration: 0.25) { view.alpha = 1 }
    }

    private func drop(_ id: String) {
        tileLoads.removeValue(forKey: id)?.cancel()
        tileSizes[id] = nil
        tileViews.removeValue(forKey: id)?.removeFromSuperview()
    }

    /// Keeps a picture smaller than the screen in its middle.
    private func centre() {
        let size = imageView.frame.size
        let x = max(0, (bounds.width - size.width) / 2)
        let y = max(0, (bounds.height - size.height) / 2)
        contentInset = UIEdgeInsets(top: y, left: x, bottom: y, right: x)
    }

    func viewForZooming(in scrollView: UIScrollView) -> UIView? { imageView }

    func scrollViewDidZoom(_ scrollView: UIScrollView) {
        centre()
        tilesMoved()
    }

    func scrollViewDidScroll(_ scrollView: UIScrollView) { tilesMoved() }

    @objc private func tapped() { onTap() }

    @objc private func doubleTapped(_ gesture: UITapGestureRecognizer) {
        if zoomScale > minimumZoomScale * 1.01 {
            setZoomScale(minimumZoomScale, animated: true)
            return
        }
        let point = gesture.location(in: imageView)
        // Back to filling the screen, or closer when the picture already
        // fills it whole.
        let scale = fillScale > minimumZoomScale * 1.15 ? fillScale : min(maximumZoomScale, 3)
        let size = CGSize(width: bounds.width / scale, height: bounds.height / scale)
        zoom(to: CGRect(x: point.x - size.width / 2, y: point.y - size.height / 2,
                        width: size.width, height: size.height), animated: true)
    }
}

/// Tells when the screen holding it starts to go away or to come back
/// (UIKit's will-disappear and will-appear, which a swipe-down dismissal
/// calls at its start and again when it is let go).
private struct Appearance: UIViewControllerRepresentable {
    var willDisappear: () -> Void
    var willAppear: () -> Void

    func makeUIViewController(context: Context) -> Watcher { Watcher() }

    func updateUIViewController(_ watcher: Watcher, context: Context) {
        watcher.willDisappear = willDisappear
        watcher.willAppear = willAppear
    }

    final class Watcher: UIViewController {
        var willDisappear: () -> Void = {}
        var willAppear: () -> Void = {}
        /// The first appearance is the opening, handled by `onAppear`.
        private var appeared = false

        override func viewDidLoad() {
            super.viewDidLoad()
            view.isUserInteractionEnabled = false
            view.backgroundColor = .clear
        }

        override func viewWillAppear(_ animated: Bool) {
            super.viewWillAppear(animated)
            if appeared { willAppear() }
            appeared = true
        }

        override func viewWillDisappear(_ animated: Bool) {
            super.viewWillDisappear(animated)
            willDisappear()
        }
    }
}
