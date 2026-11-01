import SwiftUI

/// Small-caps label above titles, like a museum wall text.
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

/// A picture in a real-looking frame: white moulding, as the real frame.
/// `inner` is laid over the picture (e.g. the crop windows on "Teraz").
struct FramedArtwork<Inner: View>: View {
    let ref: ImageRef?
    var aspectRatio: CGFloat = 16.0 / 9.0
    var placeholder: Color = Theme.mat
    var mat: CGFloat = 0
    var moulding: CGFloat = 8
    /// Off when the frame is turned: the caller casts it, so it keeps falling down.
    var shadow = true
    /// A new picture fades in over the one before (`ArtImage.crossfade`).
    var crossfade = false
    @ViewBuilder var inner: Inner

    var body: some View {
        Group {
            if let ref {
                ArtImage(
                    ref: ref, placeholder: placeholder, maxPixel: 1600, contentMode: .fit, priority: .high,
                    crossfade: crossfade
                )
            } else {
                Rectangle().fill(placeholder.gradient)
            }
        }
            .aspectRatio(aspectRatio, contentMode: .fit)
            .overlay { inner }
            .padding(mat)
            .background(Theme.matWhite)
            .overlay { ScreenEdge().allowsHitTesting(false) }
            .padding(moulding)
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
    init(
        ref: ImageRef?, aspectRatio: CGFloat = 16.0 / 9.0, placeholder: Color = Theme.mat,
        mat: CGFloat = 0, moulding: CGFloat = 8
    ) {
        self.init(ref: ref, aspectRatio: aspectRatio, placeholder: placeholder, mat: mat, moulding: moulding) {
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
                    if showsFavorite, item.favorite {
                        Image(systemName: "heart.fill")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.white)
                            .padding(6)
                            .background(.black.opacity(0.35), in: Circle())
                            .padding(6)
                    }
                }
                .shadow(color: .black.opacity(0.14), radius: 8, x: 0, y: 5)
            if showsCaption {
                VStack(alignment: .leading, spacing: 2) {
                    Text(item.title.isEmpty ? "Bez tytułu" : item.title)
                        .font(.serif(15, weight: .medium))
                        .foregroundStyle(Theme.ink)
                        .lineLimit(2)
                    Text(item.artist.isEmpty ? Names.source(item.source) : item.artist)
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .lineLimit(1)
                }
            }
        }
        // The card opened from here shows this much while it loads.
        .onAppear { ItemPeeks.remember(item, thumb: ref ?? .thumb(item.id)) }
    }
}

/// The heart over a tile's top right corner, as `ArtCard` shows a
/// favourite's, but tapped: into Ulubione and out again. Put over the tile's
/// link, so the tap doesn't open the work.
struct TileHeart: View {
    let favorite: Bool
    let toggle: () -> Void
    @State private var taps = 0

    var body: some View {
        Button {
            taps += 1
            toggle()
        } label: {
            Image(systemName: favorite ? "heart.fill" : "heart")
                .font(.caption.weight(.bold))
                .foregroundStyle(.white)
                .contentTransition(.symbolEffect(.replace))
                .padding(6)
                .background(.black.opacity(0.35), in: Circle())
                .padding(6)
                // A finger's room, the circle where the favourite's is.
                .padding([.leading, .bottom], 8)
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
struct MasonryGrid<Content: View>: View {
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

    private var columnWidth: Double {
        guard width > 0 else { return Self.phoneColumn }
        return Double((width - spacing * CGFloat(columns - 1)) / CGFloat(columns))
    }

    var body: some View {
        LazyVStack(alignment: .leading, spacing: spacing + 6) {
            ForEach(Self.blocks(items, columns: columns, columnWidth: columnWidth)) { block in
                switch block {
                case .columns(let buckets):
                    HStack(alignment: .top, spacing: spacing) {
                        ForEach(Array(buckets.enumerated()), id: \.offset) { _, column in
                            VStack(spacing: spacing + 6) {
                                ForEach(column) { item in
                                    content(item)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .top)
                        }
                    }
                    .environment(\.artCardAspects, 0.45...Self.wide)
                case .row(let item):
                    content(item)
                        .environment(\.artCardAspects, Self.wide...Self.panorama)
                }
            }
        }
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { width = $0 }
    }
}

private extension ClosedRange where Bound == Double {
    func clamp(_ value: Double) -> Double { Swift.min(Swift.max(value, lowerBound), upperBound) }
}

struct Chip: View {
    let title: String
    var systemImage: String?
    var swatch: Color?
    var selected = false
    var action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                if let swatch {
                    Circle()
                        .fill(swatch)
                        .frame(width: 12, height: 12)
                        .overlay(Circle().strokeBorder(Theme.inkSoft.opacity(0.4), lineWidth: 0.75))
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
    var swatch: Color?

    var body: some View {
        HStack(spacing: 5) {
            if let swatch {
                Circle()
                    .fill(swatch)
                    .frame(width: 9, height: 9)
                    .overlay(Circle().strokeBorder(Theme.inkSoft.opacity(0.4), lineWidth: 0.75))
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

/// Wide filled call-to-action.
struct PrimaryButtonStyle: ButtonStyle {
    var color: Color = Theme.accent

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .foregroundStyle(Theme.paper)  // dark text on the lighter dark-mode accent
            .frame(maxWidth: .infinity)
            .padding(.vertical, 15)
            .background(color, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .opacity(configuration.isPressed ? 0.85 : 1)
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
    }
}

struct SecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .foregroundStyle(Theme.ink)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 15)
            .background(Theme.card, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(Theme.hairline))
            .opacity(configuration.isPressed ? 0.85 : 1)
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
                configuration.title
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }
            .font(.subheadline.weight(.semibold))
        }
    }
}

/// One of two actions sharing a row, like "Pokaż na ramce" and "Dodaj do
/// kolejki": filled when prominent, else on a card; a narrow one is as wide
/// as its label. With only its icon, it is a narrow one of three ("Teraz",
/// "Pomiń").
struct ActionButtonStyle: ButtonStyle {
    var prominent = false
    var wide = true
    var iconOnly = false

    func makeBody(configuration: Configuration) -> some View {
        let shape = RoundedRectangle(cornerRadius: 14, style: .continuous)
        return configuration.label
            .labelStyle(ActionLabelStyle(iconOnly: iconOnly))
            .foregroundStyle(prominent ? Theme.paper : Theme.ink)  // dark text on the lighter dark-mode accent
            .frame(maxWidth: wide ? .infinity : nil)
            .frame(width: iconOnly ? 54 : nil)
            .padding(.horizontal, wide || iconOnly ? 0 : 18)
            .padding(.vertical, 14)
            .background(prominent ? Theme.accent : Theme.card, in: shape)
            .overlay(shape.strokeBorder(prominent ? Color.clear : Theme.hairline))
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
    var systemImage = "photo.artframe"

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
        let picture = ArtImage(ref: .thumb(itemIDs[index]), maxPixel: 400, subjectFocus: true)
            .frame(width: width, height: height)
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
