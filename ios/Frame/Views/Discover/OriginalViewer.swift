import SwiftUI
import UIKit

/// The original on a dark screen of its own, opened filling the screen:
/// pinch out or double-tap to see it whole, pinch or double-tap to look
/// closer, drag to look around, tap to hide the caption. The sun button
/// brightens the screen to full while the viewer is open (remembered); it
/// dims back as soon as the viewer starts to close. A work kept also as a
/// set of sharper tiles (Commons; Mateusz 2026-11-09) gets them laid on it
/// while zooming in, only those in view.
struct OriginalViewer: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage(ScreenBoost.key) private var brighten = false
    let item: Item
    @State private var image: UIImage?
    @State private var failed = false
    @State private var chrome = true
    @State private var tiles: [ZoomTile] = []
    /// The picture is made of the tiles' own thumbnails: the work's picture
    /// may be another photograph (another copy, another crop, other
    /// colours), and the tiles would not lie on it (Mateusz 2026-11-09,
    /// Bosch's "Garden" bluish under yellowish tiles, a giraffe beside a boar).
    @State private var underlay = false

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            if let image {
                ZoomableImage(image: image, tiles: tiles) {
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
                HStack(spacing: 10) {
                    Button {
                        brighten.toggle()
                    } label: {
                        Image(systemName: brighten ? "sun.max.fill" : "sun.max")
                            .font(.headline)
                            .foregroundStyle(brighten ? .yellow : .white)
                            .frame(width: 40, height: 40)
                            .background(.black.opacity(0.5), in: Circle())
                            .contentTransition(.symbolEffect(.replace))
                    }
                    .accessibilityLabel("Rozjaśnij ekran")
                    .accessibilityAddTraits(brighten ? .isSelected : [])
                    Button {
                        // Dimming starts with the closing, not after it.
                        ScreenBoost.shared.restore()
                        dismiss()
                    } label: {
                        Image(systemName: "xmark")
                            .font(.headline)
                            .foregroundStyle(.white)
                            .frame(width: 40, height: 40)
                            .background(.black.opacity(0.5), in: Circle())
                    }
                    .accessibilityLabel("Zamknij")
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
        .sensoryFeedback(.selection, trigger: brighten)
        .task(id: item.id) { await load() }
        .task(id: item.id) { await loadTiles() }
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

    private var caption: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(item.displayTitle.isEmpty ? "Bez tytułu" : item.displayTitle)
                .font(.serif(19, weight: .semibold))
                .lineLimit(2)
            let line = item.kind == .photo
                ? item.photoLine
                : [Names.artist(item.artist), item.dateText].filter { !$0.isEmpty }.joined(separator: " · ")
            if !line.isEmpty {
                Text(line).font(.footnote).opacity(0.75)
            }
            if !tiles.isEmpty {
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

    /// The work's tiles with their places, when the server knows them
    /// (Commons tile sets; Cleveland's scroll sections have none yet).
    private func loadTiles() async {
        guard !item.isFragment, item.source == "wmc" || item.source == "cma",
              let view = await Fragments.load(item.id, backend: model.backend),
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

/// A sharper picture of one part of the whole, laid on it while zooming:
/// `unit` is its place as fractions of the whole, `pixels` how wide it
/// comes from the server.
struct ZoomTile: Equatable {
    let id: String
    let unit: CGRect
    let pixels: CGFloat
    let request: URLRequest

    /// The width the server keeps a picture of this size at (its long side
    /// at most 2560 px, `images.kept_size`).
    static func keptWidth(_ width: Int?, _ height: Int?) -> CGFloat {
        guard let width, let height, width > 0, height > 0 else { return 2560 }
        let long = CGFloat(max(width, height))
        return CGFloat(width) * min(1, 2560 / long)
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
    var onTap: () -> Void = {}

    func makeUIView(context: Context) -> ZoomScrollView { ZoomScrollView() }

    func updateUIView(_ view: ZoomScrollView, context: Context) {
        view.onTap = onTap
        view.show(image)
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
    /// Sharper pictures of parts of it, laid on it while zooming in.
    private var tiles: [ZoomTile] = []
    /// The tiles on the picture now, by id, and the size each was asked in.
    private var tileViews: [String: UIImageView] = [:]
    private var tileSizes: [String: CGFloat] = [:]
    private var tileLoads: [String: Task<Void, Never>] = [:]
    /// The look at which tiles are in view after a zoom or a drag settles.
    private var settling: Task<Void, Never>?
    private var lookedAt: CFTimeInterval = 0
    /// Below this many pixels across, a tile comes in its smaller size.
    private static let smallTile: CGFloat = 1280

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

    /// A sharper copy of the same picture keeps the zoom and place; another
    /// shape is fitted afresh.
    func show(_ image: UIImage) {
        guard imageView.image !== image else { return }
        let sameShape = imageView.image.map {
            abs($0.size.width / max($0.size.height, 1) - image.size.width / max(image.size.height, 1)) < 0.01
        } ?? false
        imageView.image = image
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
        zoomScale = fillScale
        centre()
        // The middle of the picture in the middle of the view.
        contentOffset = CGPoint(x: (contentSize.width - bounds.width) / 2,
                                y: (contentSize.height - bounds.height) / 2)
        for tile in tiles { tileViews[tile.id]?.frame = rect(of: tile) }
        lookAtTiles()
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
        let across = tiles.map { $0.pixels / max($0.unit.width, 0.001) }.max() ?? 0
        let shown = imageView.bounds.width * traitCollection.displayScale
        guard across > 0, shown > 0 else {
            maximumZoomScale = 8
            return
        }
        maximumZoomScale = min(24, max(8, across / shown))
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
            } else if onScreen <= Self.smallTile, tile.pixels > Self.smallTile * 1.2 {
                Self.smallTile
            } else {
                tile.pixels
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
