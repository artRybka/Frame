import SwiftUI
import UIKit

/// What a framing looks like before its picture comes: the mat and its
/// windows, drawn on the phone.
struct PreviewLayout: Hashable {
    var portrait: Bool
    var fit: String
    var mat: String
    var margin: Double
    /// Multi: the grid drawn (the chosen one, else the count's first).
    var grid: MultiGrid?

    init(portrait: Bool, presentation: Presentation) {
        self.portrait = portrait
        fit = presentation.fit
        mat = presentation.mat
        margin = presentation.margin
        if fit == "multi" {
            let count = presentation.multiRandom ? 4 : presentation.multiCount
            let grids = MultiGrid.grids(count)
            grid = grids.first { $0.id == presentation.multiGrid } ?? grids.first
        }
    }

    /// The board's shape, without what only tints or nudges it: while a
    /// new picture renders, one of the same shape may stay.
    var shape: String { "\(portrait) \(fit) \(grid?.cells.count ?? 0)\(grid?.id ?? "")" }

    var darkMat: Bool { mat == "black" || mat == "picture_dark" }
}

/// The frame in Prezentacja, as tall as its orientation needs. Turned to
/// the other orientation, it rotates the way the frame on the wall would,
/// the picture going with it, and the new picture comes in over a sketch
/// of its framing.
struct PresentationPreview<Note: View>: View {
    @Environment(AppModel.self) private var model
    let ref: ImageRef?
    let layout: PreviewLayout
    /// Previews likely asked for next (the other orientation, the other
    /// grids), loaded once this one is in, so they come at once.
    var warm: [ImageRef] = []
    @ViewBuilder var note: Note

    /// A portrait frame's height.
    static var height: CGFloat { 290 }
    private static var moulding: CGFloat { 5 }

    private struct Shown: Equatable {
        let ref: ImageRef
        let image: UIImage
        let layout: PreviewLayout
    }

    /// The last picture in, kept while the next one renders; of the other
    /// orientation, it turns with the frame and fades.
    @State private var shown: Shown?
    @State private var failed: ImageRef?
    /// The room across, for the height: a landscape frame takes no more.
    @State private var width: CGFloat = 0

    /// The rotation's progress: the frame laid as it was, then upright.
    private struct Turn {
        var angle = 0.0
        var scale = 1.0
        var fade = 0.0  // the turning picture's opacity
    }

    var body: some View {
        GeometryReader { geo in
            let box = Self.box(portrait: layout.portrait, width: geo.size.width)
            let other = Self.box(portrait: !layout.portrait, width: geo.size.width)
            KeyframeAnimator(initialValue: Turn(), trigger: layout.portrait) { turn in
                framed(fade: turn.fade)
                    .frame(width: box.width, height: box.height)
                    .scaleEffect(turn.scale)
                    .rotationEffect(.degrees(turn.angle))
                    // Its size switches at once and the keyframes turn it:
                    // only its place goes with the spring of the switch.
                    .transaction { $0.animation = nil }
                    .frameShadow()
                    .position(x: geo.size.width / 2, y: geo.size.height / 2)
            } keyframes: { _ in
                // Starts as the old frame (the new one laid on its side and
                // scaled to it); portrait is the panel turned to the right.
                let spring = Spring(duration: 0.6, bounce: 0.15)
                KeyframeTrack(\.angle) {
                    MoveKeyframe(layout.portrait ? -90 : 90)
                    SpringKeyframe(0, duration: 0.6, spring: spring)
                }
                KeyframeTrack(\.scale) {
                    MoveKeyframe(other.width / box.height)
                    SpringKeyframe(1, duration: 0.6, spring: spring)
                }
                KeyframeTrack(\.fade) {
                    MoveKeyframe(1)
                    LinearKeyframe(1, duration: 0.25)
                    LinearKeyframe(0, duration: 0.3)
                }
            }
            .onAppear { width = geo.size.width }
            .onChange(of: geo.size.width) { _, new in width = new }
        }
        .frame(height: width > 0 ? Self.box(portrait: layout.portrait, width: width).height : Self.height)
        .task(id: ref) { await load() }
    }

    /// The frame at its size on the wall, the moulding included: a
    /// landscape one as wide as there is room, a portrait one `height` tall.
    static func box(portrait: Bool, width: CGFloat) -> CGSize {
        let m = 2 * moulding
        if portrait {
            let height = min(Self.height, (width - m) * 16 / 9 + m)
            return CGSize(width: (height - m) * 9 / 16 + m, height: height)
        }
        return CGSize(width: width, height: (width - m) * 9 / 16 + m)
    }

    /// The picture to show: the one asked for, else one of the same work
    /// and shape while it renders.
    private var picture: Shown? {
        // The settings come a moment after the switch: the old frame's
        // picture never fills the new one.
        guard let shown, let ref, shown.layout.portrait == layout.portrait else { return nil }
        if shown.ref == ref { return shown }
        let same = Self.item(shown.ref) == Self.item(ref) && shown.layout.shape == layout.shape
        return same ? shown : nil
    }

    private var waiting: Bool { ref != nil && shown?.ref != ref && failed != ref }

    private func framed(fade: Double) -> some View {
        FramedArtwork(
            ref: nil,
            aspectRatio: layout.portrait ? 9.0 / 16.0 : 16.0 / 9.0,
            placeholder: MatSwatch.color(layout.mat),
            moulding: Self.moulding,
            shadow: false
        ) {
            ZStack {
                LayoutSketch(layout: layout, pulsing: waiting)
                if let picture {
                    Image(uiImage: picture.image)
                        .resizable()
                        .transition(.opacity)
                        .id(picture.ref)
                }
                if let turning = shown, turning.layout.portrait != layout.portrait {
                    GeometryReader { geo in
                        // Laid in the old frame's shape, turned with the frame.
                        Image(uiImage: turning.image)
                            .resizable()
                            .frame(width: geo.size.height, height: geo.size.width)
                            .rotationEffect(.degrees(layout.portrait ? 90 : -90))
                            .position(x: geo.size.width / 2, y: geo.size.height / 2)
                    }
                    .opacity(fade)
                }
                if waiting, picture != nil {
                    ProgressView()
                        .controlSize(.small)
                        .padding(6)
                        .background(.ultraThinMaterial, in: Circle())
                        .padding(8)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
                        .transition(.opacity)
                }
                note
            }
            .animation(.easeOut(duration: 0.3), value: picture?.ref)
            .animation(.easeOut(duration: 0.2), value: waiting)
        }
    }

    private func load() async {
        guard let ref, let request = model.backend.request(for: ref) else { return }
        var layout = layout
        if case let .framePreview(_, settings?, _, _) = ref {
            layout.portrait = settings.orientation == "portrait"  // the frame it was drawn for
        }
        do {
            let image = try await ImageLoader.shared.image(for: request, maxPixel: 1600, priority: .high)
            shown = Shown(ref: ref, image: image, layout: layout)
            failed = nil
        } catch {
            if !Task.isCancelled { failed = ref }
            return
        }
        // One at a time, behind what the owner looks at; gone when the
        // settings change again.
        for next in warm {
            guard !Task.isCancelled else { return }
            guard let request = model.backend.request(for: next) else { continue }
            _ = try? await ImageLoader.shared.image(for: request, maxPixel: 1600)
        }
    }

    private static func item(_ ref: ImageRef) -> String? {
        if case let .framePreview(id, _, _, _) = ref { return id }
        return nil
    }
}

/// The mat with the framing's windows, as the server lays them out
/// (roughly: the picture's own shape is not known yet). The windows pulse
/// while the picture renders.
struct LayoutSketch: View {
    let layout: PreviewLayout
    var pulsing = true
    @State private var dim = false

    var body: some View {
        ZStack {
            Rectangle().fill(MatSwatch.color(layout.mat))
            Canvas { context, size in
                let field = layout.darkMat ? Color.white.opacity(0.14) : Theme.ink.opacity(0.09)
                let (windows, lines) = Self.parts(of: layout, in: size)
                for window in windows {
                    context.fill(Path(window), with: .color(field))
                }
                for line in lines {
                    context.fill(Path(roundedRect: line, cornerRadius: line.height / 2), with: .color(field))
                }
            }
            .opacity(pulsing && dim ? 0.45 : 1)
        }
        .onAppear {
            withAnimation(.easeInOut(duration: 0.85).repeatForever(autoreverses: true)) { dim = true }
        }
        .accessibilityHidden(true)
    }

    /// The windows and the lines of text on a canvas of `size`.
    static func parts(of layout: PreviewLayout, in size: CGSize) -> (windows: [CGRect], lines: [CGRect]) {
        let canvas = CGRect(origin: .zero, size: size)
        let short = min(size.width, size.height)
        let outer = short * max(layout.margin, 0.05)
        switch layout.fit {
        case "fill":
            return ([canvas], [])
        case "multi":
            let grid = layout.grid ?? MultiGrid.grids(4)[0]
            return (grid.rects(in: size, margin: layout.margin), [])
        case "description":
            let inner = canvas.insetBy(dx: outer, dy: outer)
            let gap = outer * 0.6
            let split = layout.portrait
                ? inner.divided(atDistance: inner.height * 0.62, from: .minYEdge)
                : inner.divided(atDistance: inner.width * 0.6, from: .minXEdge)
            let (picture, beside) = (split.slice, split.remainder)
            let rest = layout.portrait
                ? beside.inset(by: UIEdgeInsets(top: gap, left: 0, bottom: 0, right: 0))
                : beside.inset(by: UIEdgeInsets(top: 0, left: gap, bottom: 0, right: 0))
            let side = min(rest.width, rest.height) * (layout.portrait ? 1 : 0.62)
            let detail = CGRect(x: rest.minX, y: rest.minY, width: side, height: side)
            let text = layout.portrait
                ? CGRect(x: detail.maxX + gap, y: rest.minY, width: rest.maxX - detail.maxX - gap, height: rest.height)
                : CGRect(x: rest.minX, y: detail.maxY + gap, width: rest.width, height: rest.maxY - detail.maxY - gap)
            let height = max(short * 0.012, 1.5)
            let lines = [0.7, 1.0, 0.92, 0.96, 0.55].enumerated().compactMap { index, share -> CGRect? in
                let y = text.minY + CGFloat(index) * height * 3
                guard y + height <= text.maxY else { return nil }
                return CGRect(x: text.minX, y: y, width: text.width * share, height: height)
            }
            return ([picture, detail], lines)
        default:
            return ([canvas.insetBy(dx: outer, dy: outer)], [])
        }
    }
}

extension Animation {
    /// The frame turning to the other orientation, and what moves with it.
    static let frameTurn = Animation.spring(duration: 0.6, bounce: 0.15)
}
