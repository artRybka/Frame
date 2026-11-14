import SwiftUI

/// Small-caps label above titles, like a museum wall text.
/// Small stars after a title whose text Claude wrote (the study's
/// sections; Mateusz 2026-11-03: in place of a note at the end).
struct AiMark: View {
    var body: some View {
        Image(systemName: "sparkles")
            .font(.system(size: 10, weight: .semibold))
            .foregroundStyle(Theme.inkSoft.opacity(0.8))
            .accessibilityLabel(Text("napisał Claude"))
    }
}

struct Eyebrow: View {
    let text: String
    var color: Color = Theme.inkSoft

    init(_ text: String, color: Color = Theme.inkSoft) {
        self.text = text
        self.color = color
    }

    var body: some View {
        Text(text.uppercased())
            .font(.system(size: 11, weight: .semibold))
            .tracking(1.4)
            .foregroundStyle(color)
    }
}

struct SectionHeader: View {
    let title: String
    var subtitle: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.serif(22, weight: .semibold))
                .foregroundStyle(Theme.ink)
            if let subtitle {
                Text(subtitle)
                    .font(.subheadline)
                    .foregroundStyle(Theme.inkSoft)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// The white moulding around the screen, as a share of the screen's shorter
/// side, so a frame keeps its proportions at any size: the preview on Teraz,
/// the card or the study and the large one in Kadr flying out of it are the
/// same frame (Mateusz 2026-11-07: a fixed width jumped as Kadr opened and
/// closed). About the EM32DX's own (~14 mm around a 398 mm tall screen).
enum Moulding {
    static let share: CGFloat = 1.0 / 30

    /// The whole frame's shape, the moulding included, for a screen of `aspect`.
    static func frameAspect(_ aspect: CGFloat) -> CGFloat {
        let screen = aspect >= 1 ? CGSize(width: aspect, height: 1) : CGSize(width: 1, height: 1 / aspect)
        return (screen.width + 2 * share) / (screen.height + 2 * share)
    }

    /// The moulding's width on a frame of `size` (the moulding included).
    static func width(frame size: CGSize) -> CGFloat {
        max(min(size.width, size.height), 0) * share / (1 + 2 * share)
    }

    /// A frame's height at `width`, the moulding included.
    static func height(width: CGFloat, aspect: CGFloat) -> CGFloat {
        width / frameAspect(aspect)
    }

    /// The frame (moulding included) as large as fits in `space`.
    static func fitted(_ aspect: CGFloat, in space: CGSize) -> CGSize {
        let shape = frameAspect(aspect)
        guard space.width > 0, space.height > 0 else { return .zero }
        return space.width / space.height > shape
            ? CGSize(width: space.height * shape, height: space.height)
            : CGSize(width: space.width, height: space.width / shape)
    }
}

/// A picture in a real-looking frame: white moulding, as the real frame,
/// in proportion to its size (`Moulding`).
/// `inner` is laid over the picture (e.g. the crop windows on "Teraz").
struct FramedArtwork<Inner: View>: View {
    let ref: ImageRef?
    var aspectRatio: CGFloat = 16.0 / 9.0
    var placeholder: Color = Theme.mat
    /// Off when the frame is turned: the caller casts it, so it keeps falling down.
    var shadow = true
    /// A new picture fades in over the one before (`ArtImage.crossfade`).
    var crossfade = false
    @ViewBuilder var inner: Inner

    var body: some View {
        // The screen's shape is the frame's own, whatever the picture's: one
        // made for the other orientation (the panel still shows it after
        // Orientacja changed) sits in it with the mat around, instead of
        // giving the frame its own shape and shrinking it.
        Color.clear
            .aspectRatio(Moulding.frameAspect(aspectRatio), contentMode: .fit)
            .overlay {
                GeometryReader { geo in
                    screen
                        .padding(Moulding.width(frame: geo.size))
                        .frame(width: geo.size.width, height: geo.size.height)
                }
            }
            .background(
                LinearGradient(
                    colors: [Theme.moulding, Theme.moulding.opacity(0.94)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            )
            .clipShape(RoundedRectangle(cornerRadius: 2))
            .overlay(RoundedRectangle(cornerRadius: 2).strokeBorder(Theme.mouldingEdge, lineWidth: 0.5))
            .frameShadow(shadow)
    }

    private var screen: some View {
        Color.clear
            .aspectRatio(aspectRatio, contentMode: .fit)
            .overlay {
                if let ref {
                    ArtImage(
                        ref: ref, placeholder: placeholder, maxPixel: 1600, contentMode: .fit, priority: .high,
                        crossfade: crossfade
                    )
                } else {
                    Rectangle().fill(placeholder.gradient)
                }
            }
            .overlay { inner }
            .background(Theme.matWhite)
            .overlay { ScreenEdge().allowsHitTesting(false) }
    }
}

extension View {
    /// The shadow a frame casts on the wall.
    func frameShadow(_ on: Bool = true) -> some View {
        shadow(color: .black.opacity(on ? 0.22 : 0), radius: 18, x: 0, y: 14)
            .shadow(color: .black.opacity(on ? 0.12 : 0), radius: 2, x: 0, y: 1)
    }
}

/// Where the screen meets the moulding: a short shadow, darkest right at the
/// edge, and a fine line, so a light picture or a white passe-partout does
/// not run into the white frame.
private struct ScreenEdge: View {
    var body: some View {
        ZStack {
            // Centred on the edge, so it is darkest there and fades within ~3 pt.
            Rectangle()
                .stroke(Color.black.opacity(0.3), lineWidth: 3)
                .blur(radius: 1.5)
            Rectangle()
                .strokeBorder(Color.black.opacity(0.16), lineWidth: 0.75)
        }
        .clipped()
    }
}

extension FramedArtwork where Inner == EmptyView {
    init(ref: ImageRef?, aspectRatio: CGFloat = 16.0 / 9.0, placeholder: Color = Theme.mat, shadow: Bool = true) {
        self.init(ref: ref, aspectRatio: aspectRatio, placeholder: placeholder, shadow: shadow) {
            EmptyView()
        }
    }
}

private struct ArtCardAspectsKey: EnvironmentKey {
    static let defaultValue: ClosedRange<Double> = 0.45...2.2
}

extension EnvironmentValues {
    /// The proportions an `ArtCard` shows; a work outside them is cropped
    /// around its subject.
    var artCardAspects: ClosedRange<Double> {
        get { self[ArtCardAspectsKey.self] }
        set { self[ArtCardAspectsKey.self] = newValue }
    }
}

/// Grid tile: the picture, title and artist.
struct ArtCard: View {
    @Environment(AppModel.self) private var model
    @Environment(\.artCardAspects) private var aspects
    let item: ItemSummary
    var showsCaption = true
    /// Where the picture comes from; the server's thumbnail by default.
    var ref: ImageRef?
    /// The heart in the corner of a favourite; off where a `TileHeart`
    /// takes its place.
    var showsFavorite = true

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // The box keeps the card's proportions; the picture fills it and
            // is cropped, so a panorama can't spill over the next column.
            Color.clear
                .aspectRatio(aspects.clamp(item.aspectRatio), contentMode: .fit)
                .overlay {
                    ArtImage(
                        ref: ref ?? .thumb(item.id),
                        fallback: ref.flatMap { $0 == .thumb(item.id) ? nil : ImageRef.thumb(item.id) },
                        placeholder: item.placeholderColor,
                        maxPixel: 700,
                        // Only a work the box crops: the rest show whole.
                        subjectFocus: aspects.clamp(item.aspectRatio) != item.aspectRatio
                    )
                }
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                .contentShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                .overlay(alignment: .topTrailing) {
                    if showsFavorite, model.liked(item) {
                        HeartMark(on: true)
                            .padding(7)
                            .accessibilityLabel("W ulubionych")
                    }
                }
                .shadow(color: .black.opacity(0.14), radius: 8, x: 0, y: 5)
            if showsCaption {
                VStack(alignment: .leading, spacing: 2) {
                    // "Pod lupą": a small magnifier right after the title, in
                    // the caption's soft ink, not a mark on the picture.
                    title
                        .lineLimit(2)
                        // A long title gives way in the middle, not at its
                        // end: the marks after it stay in sight.
                        .truncationMode(marked ? .middle : .tail)
                    Text(Self.byline(item))
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .lineLimit(1)
                }
            }
        }
        // The card opened from here shows this much while it loads.
        .onAppear {
            ItemPeeks.remember(item, thumb: ref ?? .thumb(item.id))
            // Another copy since the thumbnail was kept: had anew.
            if let picture = item.picture { model.pictureSeen(item.id, copy: picture) }
        }
    }

    /// The title, and after it, wrapping with the last word: for a "Pod
    /// lupą" work a magnifier, for a picture small for the frame a grid of
    /// pixels (`LowRes`).
    /// A mark follows the title (`title`).
    private var marked: Bool {
        item.zoom == true || item.restored == true || (item.lowSide ?? 0) > 0
    }

    private var title: Text {
        var text = Text(item.title.isEmpty ? "Bez tytułu" : item.title)
            .font(.serif(15, weight: .medium))
            .foregroundStyle(Theme.ink)
        var label = item.title
        if item.zoom == true {
            text = text
                + Text("\u{00A0}").font(.serif(15, weight: .medium))
                + Text(Image(systemName: TitleYear.zoomSymbol))
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(Theme.inkSoft)
            label += ", można mocno przybliżyć"
        }
        if item.restored == true {
            text = text
                + Text("\u{00A0}").font(.serif(15, weight: .medium))
                + Text(Image(systemName: LowRes.restoredSymbol))
                    .font(.system(size: 11.5, weight: .medium))
                    .foregroundStyle(LowRes.tint)
            label += ", odnowione przez kreatywnego restauratora"
        } else if let side = item.lowSide, side > 0 {
            text = text
                + Text("\u{00A0}").font(.serif(15, weight: .medium))
                + Text(LowRes.image)
                    .foregroundStyle(LowRes.tint)
            label += ", \(LowRes.spoken(side))"
        }
        guard label != item.title else { return text }
        return text.accessibilityLabel(Text(label))
    }

    /// The line under the title: a photo's day and town, a work's artist,
    /// else where the picture is from.
    static func byline(_ item: ItemSummary) -> String {
        if item.kind == .photo, let line = item.subtitle, !line.isEmpty { return line }
        return item.artist.isEmpty ? Names.source(item.source) : Names.artist(item.artist)
    }
}

/// The glass drop with a symbol on the "Ukryte" cover: the one mark that
/// stays glass (Mateusz 2026-11-10: glass suits a misted cover, not a
/// picture's corner).
struct GlassBadge: View {
    let systemImage: String

    var body: some View {
        Image(systemName: systemImage)
            .font(.footnote.weight(.semibold))
            .foregroundStyle(Theme.inkSoft)
            .frame(width: 30, height: 30)
            .glassEffect(.regular, in: .circle)
    }
}

/// Marks on thumbnails and tiles, kept in order (Mateusz 2026-11-10, sheet
/// szklane-znaczki/szkic-2): on the picture only what the finger presses,
/// and only in the top right corner; what merely tells (the kind of a
/// collection, "Pod lupą", on the frame, in the queue) goes to the caption.
///
/// A heart without a circle: off, a heart of the system's own glass (Liquid
/// Glass in a heart's shape, its edge catching the light as iOS buttons
/// do; Mateusz 2026-11-10 12:13), the clear kind so the picture shows
/// through (12:40: "bardziej przezierne"); on, the same glass tinted red.
struct HeartMark: View {
    let on: Bool
    var size: CGFloat = 18
    /// Pressed (Szukaj): the glass answers the finger.
    var interactive = false

    var body: some View {
        Color.clear
            .frame(width: size + 4, height: size + 2)
            .glassEffect(glass, in: HeartShape())
            // The same glass in dark mode as in light (18:27).
            .environment(\.colorScheme, .light)
    }

    /// The same clear glass both ways; on, red laid under it (Mateusz
    /// 2026-11-10 17:18: "czerwony podłożony pod szkło clear"), a little
    /// see-through and the same red in both modes (18:27).
    private var glass: Glass {
        let glass: Glass = on ? .clear.tint(Self.red) : .clear
        return interactive ? glass.interactive() : glass
    }

    private static let red = Color(red: 0xD2 / 255, green: 0x46 / 255, blue: 0x3A / 255).opacity(0.81)
}

/// A heart drawn to fill its frame, for glass in its shape.
struct HeartShape: Shape {
    func path(in rect: CGRect) -> Path {
        let w = rect.width, h = rect.height / 0.95
        func pt(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: rect.minX + x * w, y: rect.minY + y * h) }
        var path = Path()
        path.move(to: pt(0.5, 0.92))
        path.addCurve(to: pt(0.02, 0.31), control1: pt(0.22, 0.74), control2: pt(0.02, 0.55))
        path.addCurve(to: pt(0.28, 0.03), control1: pt(0.02, 0.14), control2: pt(0.14, 0.03))
        path.addCurve(to: pt(0.5, 0.17), control1: pt(0.38, 0.03), control2: pt(0.46, 0.09))
        path.addCurve(to: pt(0.72, 0.03), control1: pt(0.54, 0.09), control2: pt(0.62, 0.03))
        path.addCurve(to: pt(0.98, 0.31), control1: pt(0.86, 0.03), control2: pt(0.98, 0.14))
        path.addCurve(to: pt(0.5, 0.92), control1: pt(0.98, 0.55), control2: pt(0.78, 0.74))
        path.closeSubpath()
        return path
    }
}

/// A round mark pressed on a tile's top right corner: ink with a ring of
/// the page, as the tick on a chosen miniature in Prezentacja
/// (`miniatureChoice`), light in the dark. Remove (minus, cross) and the
/// editor's added tick; `light` is the editor's plus before it is added.
struct CornerMark: View {
    let systemImage: String
    var size: CGFloat = 22
    var light = false

    var body: some View {
        ZStack {
            Circle().fill(Theme.card)
            if light {
                Circle().strokeBorder(Theme.hairline, lineWidth: 0.75)
            } else {
                Circle().fill(Theme.ink).padding(2)
            }
            Image(systemName: systemImage)
                .font(.system(size: (size * 0.45).rounded(), weight: .bold))
                .foregroundStyle(light ? Theme.ink : Theme.card)
        }
        .frame(width: size, height: size)
        .shadow(color: .black.opacity(0.22), radius: 3, y: 1.5)
    }

    /// How far a remove mark sits out over the corner, as the tick does.
    static let overhang: CGFloat = 6
}

/// The heart over a tile's top right corner, as `ArtCard` shows a
/// favourite's, but tapped: into Ulubione and out again. Put over the tile's
/// link, so the tap doesn't open the work.
/// A tile's heart to press, over the card's top right corner: in Odkrywaj,
/// its sets and playlists as in Szukaj (Mateusz 2026-11-10).
struct LikeHeart: View {
    @Environment(AppModel.self) private var model
    let item: ItemSummary

    var body: some View {
        let on = model.liked(item)
        TileHeart(favorite: on) {
            Task { await model.like(item, !on) }
        }
    }
}

struct TileHeart: View {
    let favorite: Bool
    let toggle: () -> Void
    @State private var taps = 0

    var body: some View {
        Button {
            taps += 1
            toggle()
        } label: {
            HeartMark(on: favorite, interactive: true)
                .animation(.snappy, value: favorite)
                .padding(7)
                // A finger's room (44 pt), the heart where the favourite's is.
                .padding([.leading, .bottom], 12)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .sensoryFeedback(.impact(weight: .light), trigger: taps)
        .accessibilityLabel(favorite ? "Usuń z ulubionych" : "Dodaj do ulubionych")
    }
}

/// "Dodaj do kolejki" in a picture's context menu: the next one on the frame.
struct QueueButton: View {
    @Environment(AppModel.self) private var model
    let itemID: String

    var body: some View {
        Button("Dodaj do kolejki", systemImage: QueueButton.symbol) {
            Task { await model.queueNext(itemID: itemID) }
        }
    }

    static let symbol = "text.line.first.and.arrowtriangle.forward"
}

/// Two-column waterfall layout using the pictures' aspect ratios. A work
/// wider than `wide` takes the whole row, once the columns above it end
/// about level.
///
/// The columns are cut into short blocks that end where both columns are
/// about level, and only the list of blocks is lazy: the columns inside a
/// block are plain stacks. Lazy columns nested in an `HStack` guessed the
/// heights of the cards they hadn't made yet, so the grid grew and shrank
/// while scrolling (the results jumped back) and could lose its cards
/// altogether (an empty screen) until scrolled again.
///
/// Up to `measuredUpTo` works the blocks are a plain stack instead.
///
/// A wide work rides in the lazy list with the block above it, so a short
/// row never comes in alone under a guessed height (the page jumped as a
/// wide work came on screen). And the works whose pictures are missing
/// are left out when the list changes, never under the finger: a picture
/// that fails on screen keeps its tile (with the arrow to try again)
/// until the list is loaded again, instead of every card after it moving
/// over, which at the end of a playlist took the page back up each time.
struct MasonryGrid<Content: View>: View {
    @Environment(AppModel.self) private var model
    let items: [ItemSummary]
    var columns = 2
    var spacing: CGFloat = 16
    @ViewBuilder let content: (ItemSummary) -> Content

    /// From this width / height on a work spans the columns.
    static var wide: Double { 2.0 }
    /// A spanning work is shown whole up to this; wider ones are cropped.
    static var panorama: Double { 4.5 }
    /// Columns this much apart (in column widths) count as level.
    static var level: Double { 0.3 }
    /// A wide work waits for level columns behind at most this many cards.
    static var maxDeferred: Int { 3 }
    /// A block ends at level columns once it holds this many cards...
    static var minBlock: Int { 4 }
    /// ...and at the latest with this many, level or not.
    static var maxBlock: Int { 16 }

    enum Block: Identifiable {
        case columns([[ItemSummary]])
        case row(ItemSummary)

        var id: String {
            switch self {
            case .columns(let buckets): return "columns-" + (buckets.first?.first?.id ?? "")
            case .row(let item): return item.id
            }
        }
    }

    /// One place in the lazy list: a block of columns with the wide works
    /// after it.
    struct Chunk: Identifiable {
        var columns: [[ItemSummary]] = []
        var rows: [ItemSummary] = []

        var id: String {
            if let first = columns.first?.first { return "columns-" + first.id }
            return rows.first?.id ?? ""
        }
    }

    /// The blocks as the lazy list holds them: each wide row joins the
    /// block above it; only wide works at the very top start one alone.
    static func chunks(_ blocks: [Block]) -> [Chunk] {
        var chunks: [Chunk] = []
        for block in blocks {
            switch block {
            case .columns(let buckets):
                chunks.append(Chunk(columns: buckets))
            case .row(let item):
                if chunks.isEmpty { chunks.append(Chunk()) }
                chunks[chunks.count - 1].rows.append(item)
            }
        }
        return chunks
    }

    /// Up to this many works the grid is a plain stack, measured whole:
    /// a lazy list guesses the height of what it has not made yet, so the
    /// page grew and shrank by thousands of points while scrolling (10 386
    /// → 7 984 pt for 51 works, `PlaylistScrollTests`), opened with small
    /// jumps and stopped short of its end (Mateusz 2026-11-14). Longer
    /// lists stay lazy, so their pictures do not all load at once.
    static var measuredUpTo: Int { 160 }

    /// A column's width on a phone, until the grid is measured.
    static var phoneColumn: Double { 170 }

    /// A card's height in column widths: the picture and its caption, the
    /// title on one or two lines as it fits the column (`ArtCard`: serif
    /// 15 pt title, caption-size artist, 8 pt apart).
    static func height(_ item: ItemSummary, columnWidth: Double = phoneColumn) -> Double {
        let title = item.title.isEmpty ? "Bez tytułu" : item.title
        let lines = Double(title.count) * 8 > columnWidth ? 2.0 : 1.0
        let caption = 8 + lines * 19 + 2 + 16
        return 1 / (0.45...wide).clamp(item.aspectRatio) + caption / max(columnWidth, 60)
    }

    /// The blocks for these works. Only the last block changes as works
    /// are added at the end, so the ones above keep their place.
    static func blocks(_ items: [ItemSummary], columns: Int = 2, columnWidth: Double = phoneColumn) -> [Block] {
        var blocks: [Block] = []
        var buckets = Array(repeating: [ItemSummary](), count: columns)
        var heights = Array(repeating: 0.0, count: columns)
        var waiting: [ItemSummary] = []
        var deferred = 0
        var count = 0
        // The same work twice would confuse the lazy list.
        var seen = Set<String>()

        func isLevel() -> Bool { (heights.max() ?? 0) - (heights.min() ?? 0) <= level }
        func flush() {
            if buckets.contains(where: { !$0.isEmpty }) { blocks.append(.columns(buckets)) }
            blocks += waiting.map(Block.row)
            buckets = Array(repeating: [], count: columns)
            heights = Array(repeating: 0, count: columns)
            waiting = []
            deferred = 0
            count = 0
        }

        for item in items {
            guard seen.insert(item.id).inserted else { continue }
            if columns > 1, item.aspectRatio >= wide {
                waiting.append(item)
                if isLevel() { flush() }
                continue
            }
            let target = heights.indices.min { heights[$0] < heights[$1] } ?? 0
            buckets[target].append(item)
            heights[target] += height(item, columnWidth: columnWidth)
            count += 1
            if !waiting.isEmpty {
                deferred += 1
                if isLevel() || deferred >= maxDeferred { flush() }
            } else if columns > 1, (count >= minBlock && isLevel()) || count >= maxBlock {
                flush()
            }
        }
        flush()
        return blocks
    }

    /// The grid's width, for how long the titles are in a column.
    @State private var width: CGFloat = 0
    /// The works left out for their pictures, as they were when the list
    /// last changed; nil before the first look.
    @State private var leftOut: Set<String>?

    private var columnWidth: Double {
        guard width > 0 else { return Self.phoneColumn }
        return Double((width - spacing * CGFloat(columns - 1)) / CGFloat(columns))
    }

    /// Works with no picture anywhere, or none for now (the museum turned
    /// the server away): an empty tile helps nobody. Read from the model
    /// only until the list is first seen, so a failure later does not move
    /// the cards.
    private var shown: [ItemSummary] {
        if let leftOut {
            return leftOut.isEmpty ? items : items.filter { !leftOut.contains($0.id) }
        }
        return model.missingPictures.isEmpty && model.pausedPictures.isEmpty
            ? items : items.filter { !model.hidesPicture($0.id) }
    }

    var body: some View {
        Group {
            if MasonryProbe.lazy ?? (items.count > Self.measuredUpTo) {
                LazyVStack(alignment: .leading, spacing: spacing + 6) { chunkViews }
            } else {
                VStack(alignment: .leading, spacing: spacing + 6) { chunkViews }
            }
        }
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { width = $0 }
        .onChange(of: items.map(\.id), initial: true) {
            leftOut = Set(items.lazy.map(\.id).filter { model.hidesPicture($0) })
        }
    }

    private var chunkViews: some View {
        ForEach(Self.chunks(Self.blocks(shown, columns: columns, columnWidth: columnWidth))) { chunk in
            VStack(alignment: .leading, spacing: spacing + 6) {
                if !chunk.columns.isEmpty {
                    HStack(alignment: .top, spacing: spacing) {
                        ForEach(Array(chunk.columns.enumerated()), id: \.offset) { _, column in
                            VStack(spacing: spacing + 6) {
                                ForEach(column) { item in
                                    content(item)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .top)
                        }
                    }
                    .environment(\.artCardAspects, 0.45...Self.wide)
                }
                ForEach(chunk.rows) { item in
                    content(item)
                        .environment(\.artCardAspects, Self.wide...Self.panorama)
                }
            }
        }
    }
}

/// Tests only: the grid lazy (true) or a plain stack (false) whatever
/// its length, to compare the two.
enum MasonryProbe {
    nonisolated(unsafe) static var lazy: Bool?
}

private extension ClosedRange where Bound == Double {
    func clamp(_ value: Double) -> Double { Swift.min(Swift.max(value, lowerBound), upperBound) }
}

struct Chip: View {
    let title: String
    var systemImage: String?
    /// A colour or mood tag whose dot leads the title.
    var colorTag: String?
    var selected = false
    var action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                if let colorTag {
                    ColorTagDot(tag: colorTag)
                }
                if let systemImage {
                    Image(systemName: systemImage).font(.caption.weight(.semibold))
                }
                Text(title).font(.subheadline.weight(.medium))
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .foregroundStyle(selected ? Theme.paper : Theme.ink)
            .background(selected ? Theme.ink : Theme.card, in: Capsule())
            .overlay(Capsule().strokeBorder(selected ? .clear : Theme.hairline))
        }
        .buttonStyle(.plain)
        .sensoryFeedback(.selection, trigger: selected)
    }
}

/// Static tag (no action).
struct TagLabel: View {
    let text: String
    /// A colour or mood tag whose dot leads the text.
    var colorTag: String?

    var body: some View {
        HStack(spacing: 5) {
            if let colorTag {
                ColorTagDot(tag: colorTag, size: 9)
            }
            Text(text)
        }
        .font(.caption.weight(.medium))
        .foregroundStyle(Theme.ink)
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(Theme.mat.opacity(0.7), in: Capsule())
    }
}

/// Round translucent control button.
struct GlassButton: View {
    let systemImage: String
    var size: CGFloat = 54
    var prominent = false
    var label: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: size * 0.36, weight: .semibold))
                .foregroundStyle(prominent ? Theme.paper : Theme.ink)
                .frame(width: size, height: size)
                .background {
                    if prominent {
                        Circle().fill(Theme.ink)
                    } else {
                        Circle().fill(.ultraThinMaterial)
                    }
                }
                .overlay(Circle().strokeBorder(Color.white.opacity(prominent ? 0 : 0.35)))
                .shadow(color: .black.opacity(0.12), radius: 10, y: 6)
        }
        .buttonStyle(PressableStyle())
        .accessibilityLabel(label)
    }
}

struct PressableStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.93 : 1)
            .animation(.spring(response: 0.25, dampingFraction: 0.7), value: configuration.isPressed)
    }
}

/// The look of every button that does something, like a museum wall label:
/// nearly square corners, capitals with a little letter-spacing, and ink.
/// A prominent one is filled with ink, the other only outlined; nothing in
/// the app is blue any more.
enum LabelButton {
    static let corner: CGFloat = 4
    static let shape = RoundedRectangle(cornerRadius: corner, style: .continuous)
    static let font = Font.caption.weight(.semibold)
    static let tracking: CGFloat = 1.2

    /// Ink on paper, or paper on ink when filled (cream on black in the dark).
    static func foreground(_ filled: Bool) -> Color { filled ? Theme.paper : Theme.ink }

    /// `fill`: under an outlined one, to make it stand out (`Theme.raised`).
    @ViewBuilder
    static func background(_ filled: Bool, fill: Color? = nil) -> some View {
        if filled {
            shape.fill(Theme.ink)
        } else if let fill {
            shape.fill(fill).overlay(shape.strokeBorder(Theme.ink, lineWidth: 1))
        } else {
            shape.strokeBorder(Theme.ink, lineWidth: 1)
        }
    }
}

/// The arrow in the corner of a card that opens a page (the study of the
/// day, "Teraz prezentowane"): only a hint, the whole card is the link.
struct CardArrow: View {
    var body: some View {
        Image(systemName: "arrow.right")
            .font(.system(size: 13, weight: .semibold))
            .foregroundStyle(Theme.paper)
            .frame(width: 30, height: 30)
            .background(LabelButton.shape.fill(Theme.ink))
            .accessibilityHidden(true)
    }
}

extension View {
    /// Capitals with the label buttons' letter-spacing.
    func labelButtonType() -> some View {
        font(LabelButton.font)
            .tracking(LabelButton.tracking)
            .textCase(.uppercase)
    }

    /// Options under a long press on a label button ("Pokaż na ramce" held
    /// for longer). The lifted button keeps its nearly square corners: left
    /// alone, the system cuts it out with its own rounder ones, and the
    /// corners pop back when the menu closes. The paper under it: an
    /// outlined button is otherwise lifted with nothing inside its frame,
    /// the page dimmed behind showing through (Mateusz 2026-11-04, held
    /// "Przygotuj studium dzieła"); on the page it looks the same.
    func labelButtonMenu<MenuItems: View>(@ViewBuilder _ items: () -> MenuItems) -> some View {
        background(Theme.paper, in: LabelButton.shape)
            .contentShape(.contextMenuPreview, LabelButton.shape)
            .contextMenu(menuItems: items)
    }
}

/// Wide filled call-to-action.
struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .labelButtonType()
            .lineLimit(1)
            .minimumScaleFactor(0.8)
            .foregroundStyle(LabelButton.foreground(true))
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 10)
            .padding(.vertical, 15)
            .background(LabelButton.background(true))
            .contentShape(LabelButton.shape)
            .opacity(configuration.isPressed ? 0.85 : 1)
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
    }
}

/// Wide outlined button, for the second of two.
struct SecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .labelButtonType()
            .lineLimit(1)
            .minimumScaleFactor(0.8)
            .foregroundStyle(LabelButton.foreground(false))
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 10)
            .padding(.vertical, 15)
            .background(LabelButton.background(false))
            .contentShape(LabelButton.shape)
            .opacity(configuration.isPressed ? 0.6 : 1)
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
    }
}

/// Icon and title on one line, shrinking a little before it would wrap,
/// for two actions sharing a row; only the icon for a narrow one of three.
struct ActionLabelStyle: LabelStyle {
    var iconOnly = false

    @ViewBuilder
    func makeBody(configuration: Configuration) -> some View {
        if iconOnly {
            configuration.icon
                .font(.subheadline.weight(.semibold))  // as tall as a title beside it
        } else {
            HStack(spacing: 7) {
                configuration.icon
                    .font(.footnote.weight(.semibold))
                configuration.title
                    .labelButtonType()
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
            }
        }
    }
}

/// One of two actions sharing a row, like "Pokaż na ramce" and "Dodaj do
/// kolejki": filled with ink when prominent, else outlined; a narrow one is
/// as wide as its label. With only its icon, it is a narrow one of three
/// ("Teraz", "Pomiń"). A compact one is a small button inside a card, like
/// "Szczegóły".
struct ActionButtonStyle: ButtonStyle {
    var prominent = false
    var wide = true
    var iconOnly = false
    var compact = false
    /// Under an outlined one (`LabelButton.background`).
    var fill: Color? = nil

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .labelStyle(ActionLabelStyle(iconOnly: iconOnly))
            .foregroundStyle(LabelButton.foreground(prominent))
            .frame(maxWidth: wide ? .infinity : nil)
            .frame(width: iconOnly ? (compact ? 32 : 54) : nil)
            .padding(.horizontal, wide || iconOnly ? 0 : (compact ? 12 : 18))
            .padding(.vertical, compact ? 8 : 14)
            .background(LabelButton.background(prominent, fill: fill))
            .contentShape(LabelButton.shape)
            .opacity(configuration.isPressed && !prominent ? 0.6 : 1)
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .animation(.spring(response: 0.25, dampingFraction: 0.7), value: configuration.isPressed)
    }
}

/// Rounded card container.
struct Card<Content: View>: View {
    var padding: CGFloat = 18
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            content
        }
        .padding(padding)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: Theme.corner, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: Theme.corner, style: .continuous)
                .strokeBorder(Theme.hairline.opacity(0.7))
        )
    }
}

/// Proportional strip of the picture's colours: the dominant ones, then its
/// accents (small, vivid areas), each by its share of the picture.
struct PaletteStrip: View {
    let swatches: [ColorSwatch]
    var height: CGFloat = 10
    /// Rounded ends by default.
    var cornerRadius: CGFloat? = nil

    static let spacing: CGFloat = 2

    /// Each part's width in a strip `width` wide: its share, at least 4 points.
    static func widths(_ swatches: [ColorSwatch], in width: CGFloat) -> [CGFloat] {
        let room = max(width - spacing * CGFloat(max(swatches.count - 1, 0)), 0)
        let total = max(swatches.reduce(0) { $0 + $1.weight }, 0.001)
        let widths = swatches.map { max(4, room * $0.weight / total) }
        let scale = min(1, room / max(widths.reduce(0, +), 0.001))
        return widths.map { $0 * scale }
    }

    var body: some View {
        GeometryReader { geo in
            let widths = Self.widths(swatches, in: geo.size.width)
            HStack(spacing: Self.spacing) {
                ForEach(Array(swatches.enumerated()), id: \.offset) { index, swatch in
                    Rectangle()
                        .fill(Color(hexString: swatch.hex) ?? Theme.mat)
                        .frame(width: widths[index])
                }
            }
        }
        .frame(height: height)
        .clipShape(RoundedRectangle(cornerRadius: cornerRadius ?? height / 2, style: .continuous))
    }
}

/// Soft background tinted by the current picture's palette.
struct EmptyStateView: View {
    let title: String
    let message: String
    var systemImage = "photo.fill"

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: systemImage)
                .font(.system(size: 42, weight: .light))
                .foregroundStyle(Theme.inkSoft)
            Text(title).font(.serif(20, weight: .semibold)).foregroundStyle(Theme.ink)
            Text(message)
                .font(.subheadline)
                .foregroundStyle(Theme.inkSoft)
                .multilineTextAlignment(.center)
        }
        .padding(32)
        .frame(maxWidth: .infinity)
    }
}

/// A search that found nothing (Mateusz's words): one quiet line, and under it the choices
/// that, given up, would find something, as chips with how many works
/// the library has without them ("Pomarańcz · obecny · 3 dzieła"; no
/// strike-through, Mateusz). A tap gives the choice up.
struct NothingFound: View {
    let without: [(token: SearchToken, count: Int)]
    /// A phrase typed ("nocna straż"): offered as its words, each a chip of
    /// its own (all of them still wanted, anywhere in the work's texts).
    var phrase: SearchToken? = nil
    var splitUp: (SearchToken) -> Void = { _ in }
    let giveUp: (SearchToken) -> Void

    var body: some View {
        VStack(spacing: 10) {
            Text("Brak dzieł spełniających kryteria")
                .font(.serif(17).italic())
                .foregroundStyle(Theme.inkSoft)
                .multilineTextAlignment(.center)
            if let phrase {
                Button { splitUp(phrase) } label: {
                    Label("Szukaj słów osobno", systemImage: "text.word.spacing")
                        .font(.footnote.weight(.medium))
                        .foregroundStyle(Theme.ink)
                        .padding(.horizontal, 13)
                        .padding(.vertical, 7)
                        .background(Theme.ink.opacity(0.06), in: Capsule())
                        .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .padding(.top, 4)
                .accessibilityHint("„\(phrase.name)” jako osobne słowa")
            }
            if !without.isEmpty {
                Text("Usuń jedno z poniższych:")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .padding(.top, 8)
                ForEach(without, id: \.token) { row in
                    Button { giveUp(row.token) } label: {
                        HStack(spacing: 6) {
                            if row.token.kind == "color" {
                                ColorTagDot(tag: row.token.key, size: 9, stroke: nil)
                            }
                            Text(row.token.shownName).foregroundStyle(Theme.ink)
                            Text("· " + Names.works(row.count)).foregroundStyle(Theme.inkSoft)
                        }
                        .font(.footnote)
                        .lineLimit(1)
                        .padding(.horizontal, 11)
                        .padding(.vertical, 6)
                        .background(Theme.ink.opacity(0.06), in: Capsule())
                        .contentShape(Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Bez: \(row.token.shownName), \(Names.works(row.count))")
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 56)
        .frame(maxWidth: .infinity)
    }
}

/// How far each picture of a cover is enlarged inside its tile, around the
/// middle: museum scans often carry a strip of the frame, the mount or the
/// photographer's backdrop at the edge, and a few percent more keeps it out
/// of the small squares (Mateusz 2026-11-05). Playlist collages, Propozycje
/// and the theme cards in Odkrywaj.
enum CoverZoom {
    static let scale: CGFloat = 1.12
}

/// 2×2 collage of playlist covers, each cropped around its subject.
/// Playlist cover: up to four works, laid out by how many there are. An
/// empty playlist gets a monogram on a mat instead of blank tiles.
struct Collage: View {
    let itemIDs: [String]
    var title: String = ""
    var spacing: CGFloat = 2
    /// Each picture opens its work (a playlist's header); else the collage
    /// is one picture inside a tile that opens the playlist.
    var opensWorks = false

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let h = geo.size.height
            switch itemIDs.count {
            case 0:
                EmptyCover(title: title)
            case 1:
                tile(0, w, h)
            case 2:
                HStack(spacing: spacing) {
                    tile(0, (w - spacing) / 2, h)
                    tile(1, (w - spacing) / 2, h)
                }
            case 3:
                HStack(spacing: spacing) {
                    tile(0, (w - spacing) * 0.6, h)
                    VStack(spacing: spacing) {
                        tile(1, (w - spacing) * 0.4, (h - spacing) / 2)
                        tile(2, (w - spacing) * 0.4, (h - spacing) / 2)
                    }
                }
            default:
                VStack(spacing: spacing) {
                    ForEach(0 ..< 2, id: \.self) { row in
                        HStack(spacing: spacing) {
                            ForEach(0 ..< 2, id: \.self) { col in
                                tile(row * 2 + col, (w - spacing) / 2, (h - spacing) / 2)
                            }
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func tile(_ index: Int, _ width: CGFloat, _ height: CGFloat) -> some View {
        // The work without its paper or mount (Mateusz 2026-11-12).
        let picture = ArtImage(
            ref: .tile(itemIDs[index]), fallback: .thumb(itemIDs[index]), maxPixel: 400, subjectFocus: true
        )
            .frame(width: width, height: height)
            .scaleEffect(CoverZoom.scale)
            .clipped()
            .contentShape(Rectangle())  // taps only where the tile shows
        if opensWorks {
            NavigationLink(value: itemIDs[index]) { picture }
                .buttonStyle(PressableStyle())
                .accessibilityLabel("Otwórz dzieło \(index + 1) z okładki")
        } else {
            picture
        }
    }
}

/// Cover for a playlist with nothing in it yet: a passe-partout with the
/// playlist's initial, like an empty frame waiting for a picture.
private struct EmptyCover: View {
    let title: String

    private var monogram: String {
        title.first.map { String($0).uppercased() } ?? "∗"
    }

    var body: some View {
        GeometryReader { geo in
            let side = min(geo.size.width, geo.size.height)
            ZStack {
                Theme.mat
                RoundedRectangle(cornerRadius: 2)
                    .strokeBorder(Theme.hairline, lineWidth: max(1, side / 90))
                    .padding(side * 0.14)
                Text(monogram)
                    .font(.serif(side * 0.34, weight: .light))
                    .italic()
                    .foregroundStyle(Theme.inkSoft.opacity(0.7))
            }
        }
    }
}

/// A work's title with its date at the end on a small badge, "W oranżerii
/// [1890]" (Mateusz 2026-11-04, variant 9: a light tint of ink, thin
/// figures): Teraz and the work's card. The badge moves
/// to the next line whole with the title's last word.
struct TitleWithYear: View {
    let title: String
    let date: String
    let font: Font
    /// "Pod lupą": a magnifier and how far the full screen zooms in ("17×")
    /// on a badge after the year; 0, the magnifier alone (not known yet);
    /// nil, no badge.
    var zoom: Int? = nil
    /// A picture small for the frame: its long side on a badge after the
    /// year ("950 px", `LowRes`); 0 or nil, no badge.
    var lowSide: Int? = nil
    /// Drawn again by the image model: amber sparkles on a badge in place
    /// of the low resolution's (`LowRes.restoredSymbol`).
    var restored = false
    @Environment(\.colorScheme) private var scheme
    @Environment(\.displayScale) private var scale

    var body: some View {
        TitleYear.text(
            title, date: date, font: font, scheme: scheme, scale: scale, zoom: zoom, lowSide: lowSide,
            restored: restored
        )
    }
}

/// A work whose picture is small for the frame (Mateusz 2026-11-12): its
/// long side, when known, under the server's `low_res.LOW_SIDE` (1600 px;
/// the frame's 2560 enlarge it 1.6 times or more). Not a button, so not on
/// the picture: after the title, as "Pod lupą"'s magnifier. The pixels of
/// an enlarged picture's jagged edge, a staircase in two strengths
/// (Mateusz 2026-11-13, variant D: gentler than the coarse screen's full
/// dots, `circle.grid.3x3.fill`); drawn in the assets, no SF Symbol has it.
enum LowRes {
    /// The asset's name (`LowResStairs.imageset`, 11 pt): a template, in
    /// the text's colour, its pale pixels at 38 %.
    static let symbol = "LowResStairs"
    static var image: Image { Image(symbol).renderingMode(.template) }
    /// A picture drawn again by the image model ("Kreatywny restaurator",
    /// Mateusz 2026-11-12): AI's sparkles in the same amber, in place of
    /// the dots.
    static let restoredSymbol = "sparkles"
    static let restoredName = "Kreatywny restaurator"
    /// The tint of a warning, as "Szukaj lepszej kopii"'s notes.
    static let tint = Theme.warn

    /// The server's `LOW_SIDE`, for a copy picked on the card before the
    /// server is asked again.
    static let limit = 1600

    /// `side` when it is small for the frame, else 0.
    static func side(_ side: Int) -> Int { side > 0 && side < limit ? side : 0 }

    static func spoken(_ side: Int) -> String { "niska rozdzielczość, \(side) pikseli" }
}

@MainActor
enum TitleYear {
    static func text(
        _ title: String, date: String, font: Font, scheme: ColorScheme, scale: CGFloat, zoom: Int? = nil,
        lowSide: Int? = nil, restored: Bool = false
    ) -> Text {
        var text = Text(title).font(font).foregroundStyle(Theme.ink)
        var label = title
        let date = unbroken(date)
        // An image inside the text wraps with it; it sits on the baseline,
        // lowered so the badge's middle meets the small letters'.
        if !date.isEmpty, let badge = badge(date, scheme: scheme, scale: scale) {
            text = text + Text(" ").font(font) + Text(badge).baselineOffset(-3)
            label += ", \(date)"
        }
        if let zoom, let badge = badge(zoom > 0 ? "\(zoom)×" : "", scheme: scheme, scale: scale, symbol: zoomSymbol) {
            text = text + Text(" ").font(font) + Text(badge).baselineOffset(-3)
            label += zoom > 0 ? ", można przybliżyć \(zoom) razy" : ", można mocno przybliżyć"
        }
        if restored,
           let badge = badge("", scheme: scheme, scale: scale, symbol: LowRes.restoredSymbol, warn: true) {
            text = text + Text(" ").font(font) + Text(badge).baselineOffset(-3)
            label += ", odnowione przez kreatywnego restauratora"
        } else if let lowSide, lowSide > 0,
           let badge = badge("\(lowSide) px", scheme: scheme, scale: scale, symbol: LowRes.symbol, warn: true) {
            text = text + Text(" ").font(font) + Text(badge).baselineOffset(-3)
            label += ", \(LowRes.spoken(lowSide))"
        }
        return text.accessibilityLabel(Text(label))
    }

    static let zoomSymbol = "plus.magnifyingglass"

    /// No line break inside the date: spaces held, dashes joined.
    nonisolated static func unbroken(_ date: String) -> String {
        date.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: " ", with: "\u{00A0}")
            .replacingOccurrences(of: "–", with: "\u{2060}–\u{2060}")
            .replacingOccurrences(of: "-", with: "\u{2011}")
    }

    private static var drawn: [String: Image] = [:]

    /// The badge drawn once per date, look and screen.
    private static func badge(
        _ date: String, scheme: ColorScheme, scale: CGFloat, symbol: String? = nil, warn: Bool = false
    ) -> Image? {
        let key = "\(date)|\(symbol ?? "")|\(warn)|\(scheme == .dark)|\(scale)"
        if let image = drawn[key] { return image }
        let renderer = ImageRenderer(content: YearBadge(date: date, dark: scheme == .dark, symbol: symbol, warn: warn))
        renderer.scale = scale
        guard let cgImage = renderer.cgImage else { return nil }
        // Decorative: VoiceOver reads the date from the text's label.
        let image = Image(decorative: cgImage, scale: scale)
        if drawn.count > 200 { drawn.removeAll() }
        drawn[key] = image
        return image
    }
}

/// The year's badge: a light tint of the title's ink, no outline, figures
/// thin in the title's colour; a label, not a button (Mateusz 2026-11-04,
/// variant 9: a filled black one looked like "Szczegóły").
private struct YearBadge: View {
    let date: String
    let dark: Bool
    /// A symbol before the figures ("Pod lupą": a magnifier before "17×").
    var symbol: String? = nil
    /// In the tint of a warning (`LowRes`), not the title's ink.
    var warn = false

    var body: some View {
        let ink = warn
            ? Color(hex: dark ? 0xE2B45E : 0xB7832A)
            : Color(hex: dark ? 0xF1ECE4 : 0x1D1B18)
        HStack(spacing: 3) {
            if symbol == LowRes.symbol {
                LowRes.image
            } else if let symbol {
                Image(systemName: symbol).font(.system(size: 11.5, weight: .regular))
            }
            if !date.isEmpty {
                Text(date)
                    .font(.system(size: 12.5, weight: .light))
                    .monospacedDigit()
                    .tracking(0.3)
            }
        }
        .foregroundStyle(ink)
        .padding(.horizontal, 6)
        .padding(.vertical, 2.5)
        .background(ink.opacity(0.08), in: RoundedRectangle(cornerRadius: 5, style: .continuous))
    }
}
