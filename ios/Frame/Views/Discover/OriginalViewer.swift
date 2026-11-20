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
    /// The card says the work may be shown with its colours corrected, as
    /// this person does not see it yet: the colours' button is there too.
    var cleaningOffered = false
    /// The work changed here (its colours' correction switched on or off,
    /// for this person): the card follows.
    var onChange: ((Item) -> Void)? = nil
    /// The work as it is now, once its colours were switched here.
    @State private var current: Item?
    /// What the colours button switches for this person (`GET …/colours`),
    /// asked once the viewer is open, only where the button is.
    @State private var colours: ColoursView?
    /// The picture without the colours' correction and with it: the one
    /// shown when the viewer opened, the other made here (a varnish taken
    /// off what is shown, `VarnishSum`) or had from the server (a sheet, or
    /// the picture as it came). Mateusz 2026-11-20: "korekta może dotyczyć
    /// tylko tego co widać a nie pliku i będzie szybciej i prościej".
    @State private var plain: UIImage?
    @State private var corrected: UIImage?
    /// The colours as the button and the picture show them: switched at
    /// the tap, the server told after (`tellColours`).
    @State private var openedAs: Bool?
    @State private var coloursOn: Bool?
    /// What the server was last told here; nil, as the viewer opened.
    @State private var toldColours: Bool?
    @State private var telling = false
    @State private var framedOn = false
    /// Opened on "W ramie": the frame asked for once (in, or not to be
    /// had). Until then nothing is shown, so the work in its frame is the
    /// first picture laid out, filling the screen as the work alone would
    /// (Mateusz 2026-11-18: „na początku na pełnym ekranie (czyli na pełną
    /// wysokość)”), not the work alone with the frame then put on it.
    @State private var framedAsked = false
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
            if inFrame, !framedAsked {
                ProgressView().tint(.white)
            } else if let picture = shownImage {
                // The work never moves as its frame comes and goes; only
                // the frame fades (Mateusz 2026-11-18).
                ZoomableImage(
                    image: picture, tiles: shownOff.isEmpty && !showsCorrected ? tiles : [], whole: whole,
                    // The colours fade from one to the other, as the
                    // restorer's drawing does ("skokiem a nie płynnym
                    // przejściem", Mateusz 2026-11-20).
                    look: Treatment.look(shownOff) + (showsCorrected == openedCorrected ? 0 : 4),
                    framed: framedImage, inner: work.framed?.inner,
                    framedOn: framedOn
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
                    if let look = work.framed {
                        FrameViewerButton(look: look, on: framedOn, loading: framedLoading) {
                            Task { await toggleFramed() }
                        }
                    }
                    ForEach(treatments, id: \.self) { treatment in
                        if treatment == .colours {
                            // Each person's own, kept (Mateusz 2026-11-19:
                            // "można je włączyć/wyłączyć z pełnego ekranu
                            // (zapamiętuje się stan)").
                            TreatmentButton(
                                treatment: treatment, on: coloursShown,
                                loading: showsCorrected != coloursShown
                            ) { switchColours() }
                        } else {
                            TreatmentButton(
                                treatment: treatment, on: !off.contains(treatment),
                                loading: off != shownOff && off.contains(treatment) != shownOff.contains(treatment)
                            ) { toggle(treatment) }
                        }
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
        .task(id: work.id) { await load() }
        .task(id: work.id) {
            if inFrame {
                await toggleFramed()
                framedAsked = true
            }
            // Simulator recordings: `-frameCycle 4` turns the frame on and
            // off that many times (demo only).
            let cycles = model.demoMode ? UserDefaults.standard.integer(forKey: "frameCycle") : 0
            for _ in 0 ..< cycles * 2 {
                try? await Task.sleep(for: .seconds(2.5))
                if Task.isCancelled { return }
                await toggleFramed()
            }
        }
        .task(id: work.fragmentsID) { await loadTiles() }
        .task(id: work.id) {
            if openedAs == nil { openedAs = item.cleanedShown != nil }
            await prepareColours()
        }
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
            framedOn = false  // the frame fades (`ZoomScrollView.frame`)
            return
        }
        if framedImage == nil {
            guard let look = work.framed else { return }
            framedLoading = true
            let version = "\(work.pictureVersion)|\(look.kind)\(look.aspect)\(look.inner.minX)\(look.inner.minY)\(look.inner.width)"
            if let request = model.backend.request(for: .framed(work.id, side: 4000, version: version)) {
                let loaded = try? await ImageLoader.shared.image(for: request, maxPixel: 4096, priority: .high)
                // Decoded before it is shown: a 4000 px picture decoded on
                // the first frame of the fade held the whole screen up.
                framedImage = await loaded?.byPreparingForDisplay() ?? loaded
            }
            framedLoading = false
        }
        if framedImage != nil { framedOn = true }
    }

    /// The work as opened, or as it is since its colours were switched here.
    private var work: Item { current ?? item }

    /// What was done to the work's picture, in the buttons' order; the
    /// colours' button where the server says there is something to switch
    /// (or, until it has said, where the card offered it).
    private var treatments: [Treatment] {
        var found = Treatment.done(on: work).filter { $0 != .colours }
        let offered = colours.map { $0.kind != "none" }
            ?? (cleaningOffered || item.cleanedShown != nil)
        if offered, work.kind == .artwork { found.insert(.colours, at: 0) }
        return found
    }

    /// Whether the viewer opened on the picture with its colours corrected
    /// (the picture `load` has is that one).
    /// Kept as it was when the viewer opened: the card follows a switch
    /// made here (`onChange`) and hands the viewer the work as the server
    /// now has it, while the picture `load` has is still the one opened on
    /// (read from `item` anew, the answer put the varnish back on the
    /// picture under a blue button; the colours probe on the Mac).
    private var openedCorrected: Bool { openedAs ?? (item.cleanedShown != nil) }

    /// The colours as the button says them.
    private var coloursShown: Bool { coloursOn ?? openedCorrected }

    /// Whether the picture shown has them corrected: what the button says
    /// once that picture is here, the one before until then.
    private var showsCorrected: Bool {
        if coloursShown == openedCorrected { return openedCorrected }
        return (coloursShown ? corrected : plain) != nil ? coloursShown : openedCorrected
    }

    /// The other picture, ready before the button is touched: what it
    /// switches asked of the server, and the picture made or had.
    private func prepareColours() async {
        // Asked here too, not only when the card has heard: the viewer
        // opened before the card's own question was answered had no button
        // (and the card does not ask while the viewer covers it).
        guard item.kind == .artwork, let made = ColourRecovery.made(PaintStyle.of(item)) else { return }
        guard let view = try? await model.backend.colours(itemID: item.id, made: made) else { return }
        colours = view
        guard view.kind != "none",
              let request = model.backend.request(for: item.originalRef),
              let shown = try? await ImageLoader.shared.image(for: request, maxPixel: 4096, priority: .high)
        else { return }
        if Task.isCancelled { return }
        if openedCorrected {
            corrected = shown
            plain = await had(.treated(item.id, restored: true, cleaned: false, version: item.pictureVersion))
        } else {
            plain = shown
            if view.kind == "varnish" {
                let sum = VarnishSum(view)
                let made = await Task.detached(priority: .userInitiated) { sum.apply(to: shown) }.value
                corrected = await made?.byPreparingForDisplay() ?? made
            } else {
                corrected = await had(.treated(
                    item.id, restored: true, cleaned: true, version: item.pictureVersion, made: made
                ))
            }
        }
    }

    private func had(_ ref: ImageRef) async -> UIImage? {
        guard let request = model.backend.request(for: ref),
              let loaded = try? await ImageLoader.shared.image(for: request, maxPixel: 4096, priority: .normal)
        else { return nil }
        return await loaded.byPreparingForDisplay() ?? loaded
    }

    /// The colours' button: the picture switched at once (as soon as the
    /// other one is here), the server told after (`tellColours`).
    private func switchColours() {
        UISelectionFeedbackGenerator().selectionChanged()
        treatFailed = false
        if !shownOff.isEmpty {
            off.remove(.restored)  // the colours of the work as it is shown
        }
        coloursOn = !coloursShown
        Task { await tellColours() }
    }

    /// The server told what the button says now, one ask at a time, the
    /// last switch of quick ones winning; refused, the picture goes back
    /// as the server has it. The card follows each answer.
    private func tellColours() async {
        guard !telling else { return }
        telling = true
        defer { telling = false }
        while true {
            let wanted = coloursShown
            let kept = toldColours ?? openedCorrected
            if wanted == kept { return }
            do {
                let updated = wanted
                    ? try await model.backend.clean(
                        itemID: item.id, made: ColourRecovery.made(PaintStyle.of(item)) ?? "paper"
                    )
                    : try await model.backend.unclean(itemID: item.id)
                toldColours = wanted
                current = updated
                onChange?(updated)
            } catch {
                withAnimation(.easeInOut(duration: 0.2)) {
                    coloursOn = kept
                    if !error.isCancellation { treatFailed = true }
                }
                return
            }
        }
    }

    /// The picture with what is left off, once it came; else the work's.
    private var shownImage: UIImage? {
        if !shownOff.isEmpty { return treated[shownOff] ?? image }
        if showsCorrected != openedCorrected { return showsCorrected ? corrected : plain }
        return image
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
        guard let ref = Treatment.ref(work, off: wanted), let request = model.backend.request(for: ref) else { return }
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
            Text(bound: work.displayTitle.isEmpty ? "Bez tytułu" : work.displayTitle)
                .font(.serif(19, weight: .semibold))
                .lineLimit(2)
            let line = work.kind == .photo
                ? work.photoLine
                : [Names.artist(work.artist), work.dateText].filter { !$0.isEmpty }.joined(separator: " · ")
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
        if let request = model.backend.request(for: ItemPeeks.tiles[work.id]?.thumb ?? .thumb(work.id)),
           let thumb = try? await ImageLoader.shared.image(for: request, maxPixel: 700, priority: .high) {
            if !underlay { image = thumb }
        }
        for maxPixel: CGFloat in [1800, 4096] {
            guard let request = model.backend.request(for: work.originalRef) else { break }
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
        if work.isOwnWork {
            await loadFine()
            return
        }
        let ids = [work.fragmentsID, work.id]
        guard !work.isFragment, ids.contains(where: { $0.hasPrefix("wmc:") || $0.hasPrefix("cma:") }),
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
        guard let fine = try? await model.backend.fine(itemID: work.id), !fine.tiles.isEmpty else { return }
        let found = fine.tiles.compactMap { tile -> ZoomTile? in
            guard tile.w > 0, tile.h > 0,
                  let request = model.backend.request(for: .fine(work.id, tile: tile.id, version: fine.stamp))
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
    /// "W ramie": the work in its frame as photographed, where the work
    /// lies in it (fractions), and whether it is shown around the work
    /// (`ZoomScrollView.frame`).
    var framed: UIImage?
    var inner: CGRect?
    var framedOn = false
    var onTap: () -> Void = {}

    func makeUIView(context: Context) -> ZoomScrollView { ZoomScrollView() }

    func updateUIView(_ view: ZoomScrollView, context: Context) {
        view.onTap = onTap
        view.startsWhole = whole
        view.frame(framed, inner: inner, on: framedOn)
        view.show(image, look: look)
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
        frameView.contentMode = .scaleToFill  // its opening on the work exactly
        frameView.alpha = 0
        addSubview(frameView)
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

    /// "W ramie" (Mateusz 2026-11-18: „samo dzieło jest statyczne, a
    /// animuje się tylko pojawienie lub zniknięcie ramy”): the photograph in
    /// its frame lies under the work, its opening fitted to the work, and
    /// only fades in and out. The work stays the same picture at the same
    /// place and zoom, so its proportions never change either (the framed
    /// photograph is set straight by the frame's corners, the work by its own).
    private let frameView = UIImageView()
    /// Where the work lies in the framed photograph (fractions); nil without.
    private var frameInner: CGRect?
    private var frameOn = false
    static let frameFade: TimeInterval = 0.3

    /// The framed photograph, where the work lies in it, and whether it is
    /// shown (faded in or out once the picture is laid out).
    func frame(_ image: UIImage?, inner: CGRect?, on: Bool) {
        if frameView.image !== image { frameView.image = image }
        frameInner = inner
        placeFrame()
        let shown = on && image != nil && inner != nil
        guard shown != frameOn else { return }
        frameOn = shown
        if fitted == bounds.size, imageView.image != nil {
            UIView.animate(
                withDuration: Self.frameFade, delay: 0,
                options: [.curveEaseInOut, .allowUserInteraction, .beginFromCurrentState],
                animations: { self.frameView.alpha = shown ? 1 : 0 }
            )
        } else {
            frameView.alpha = shown ? 1 : 0
        }
        reach()
        // Where one may drag to changes, the place on the screen does not:
        // UIKit would pull a place now out of reach into it at once (the
        // work jumped by 2 pt as the frame went, its frame being a little
        // thicker at the bottom). Kept within reach until he next drags or
        // zooms (`scrollViewWillBeginDragging`).
        centre(holding: true)
    }

    /// The framed photograph around the work as it is now, its opening on
    /// the work.
    private func placeFrame() {
        guard let inner = frameInner, inner.width > 0, inner.height > 0 else { return }
        let work = imageView.frame
        let width = work.width / inner.width, height = work.height / inner.height
        frameView.frame = CGRect(x: work.minX - inner.minX * width, y: work.minY - inner.minY * height,
                                 width: width, height: height)
    }

    /// What may be looked at (content coordinates): the work, and with its
    /// frame on the frame too.
    private var extent: CGRect {
        let work = CGRect(origin: .zero, size: imageView.frame.size)
        return frameOn ? frameView.frame.union(work) : work
    }

    /// How far out one may zoom: the work whole, or with its frame on the
    /// frame whole. Never above the zoom now, so nothing moves when the
    /// frame goes; the next zoom ends within it (`scrollViewDidEndZooming`).
    private func reach() {
        let e = extent
        let whole = frameOn && e.width > 0 && e.height > 0
            ? min(bounds.width / (e.width / zoomScale), bounds.height / (e.height / zoomScale))
            : 1
        minimumZoomScale = min(1, whole, zoomScale)
        // Double-tap's "filling the screen" with what is looked at now.
        if e.width > 0, e.height > 0 {
            let fill = max(bounds.width / (e.width / zoomScale), bounds.height / (e.height / zoomScale))
            fillScale = min(maximumZoomScale, max(minimumZoomScale, fill))
        }
    }

    /// A sharper copy of the same picture keeps the zoom and place; another
    /// shape is fitted afresh.
    func show(_ image: UIImage, look: Int = 0) {
        guard imageView.image !== image else { return }
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
        minimumZoomScale = 1
        zoomScale = 1
        let scale = min(bounds.width / size.width, bounds.height / size.height)
        imageView.frame = CGRect(x: 0, y: 0, width: size.width * scale, height: size.height * scale)
        contentSize = imageView.frame.size
        placeFrame()
        deepest()
        reach()
        // Filling the screen with what is looked at: the work, or the work
        // in its frame (opened on "W ramie": „na pełną wysokość”).
        let e = extent
        let fill = max(bounds.width / e.width, bounds.height / e.height)
        fillScale = min(maximumZoomScale, max(minimumZoomScale, fill))
        zoomScale = startsWhole ? minimumZoomScale : fillScale
        centre()
        // The middle of it in the middle of the view.
        let shown = extent
        contentOffset = startsWhole
            ? CGPoint(x: -contentInset.left, y: -contentInset.top)
            : CGPoint(x: shown.midX - bounds.width / 2, y: shown.midY - bounds.height / 2)
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
        maximumZoomScale = depth
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

    /// Keeps what is looked at (`extent`: the work, or the work in its
    /// frame) in the middle when smaller than the screen, and lets a drag
    /// reach its edges when larger: the frame reaches past the work.
    /// `holding`: the place shown now kept within reach, too.
    private func centre(holding: Bool = false) {
        placeFrame()
        let e = extent, content = imageView.frame.size
        let x = (bounds.width - e.width) / 2, y = (bounds.height - e.height) / 2
        var inset = UIEdgeInsets(
            top: y > 0 ? y - e.minY : -e.minY,
            left: x > 0 ? x - e.minX : -e.minX,
            bottom: y > 0 ? y - (content.height - e.maxY) : e.maxY - content.height,
            right: x > 0 ? x - (content.width - e.maxX) : e.maxX - content.width
        )
        if holding {
            let at = contentOffset
            inset.top = max(inset.top, -at.y)
            inset.left = max(inset.left, -at.x)
            inset.bottom = max(inset.bottom, at.y + bounds.height - content.height)
            inset.right = max(inset.right, at.x + bounds.width - content.width)
        }
        contentInset = inset
    }

    func scrollViewWillBeginDragging(_ scrollView: UIScrollView) {
        if !isZooming { centre() }
    }

    func scrollViewWillBeginZooming(_ scrollView: UIScrollView, with view: UIView?) { centre() }

    func viewForZooming(in scrollView: UIScrollView) -> UIView? { imageView }

    func scrollViewDidZoom(_ scrollView: UIScrollView) {
        centre()
        tilesMoved()
    }

    func scrollViewDidScroll(_ scrollView: UIScrollView) { tilesMoved() }

    func scrollViewDidEndZooming(_ scrollView: UIScrollView, with view: UIView?, atScale scale: CGFloat) {
        // The frame gone while zoomed out to it: the work whole at the most.
        let low = minimumZoomScale
        reach()
        if !frameOn { minimumZoomScale = 1 }
        if zoomScale < minimumZoomScale * 0.999, low < minimumZoomScale {
            setZoomScale(minimumZoomScale, animated: true)
        }
    }

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
