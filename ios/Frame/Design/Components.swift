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
    @ViewBuilder var inner: Inner

    var body: some View {
        Group {
            if let ref {
                ArtImage(ref: ref, placeholder: placeholder, maxPixel: 1600, contentMode: .fit)
            } else {
                Rectangle().fill(placeholder.gradient)
            }
        }
            .aspectRatio(aspectRatio, contentMode: .fit)
            .overlay { inner }
            .padding(mat)
            .background(Theme.matWhite)
            .overlay(
                Rectangle()
                    .strokeBorder(Color.black.opacity(0.18), lineWidth: 1)
                    .blur(radius: 1.5)
                    .allowsHitTesting(false)
            )
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
            .shadow(color: .black.opacity(0.22), radius: 18, x: 0, y: 14)
            .shadow(color: .black.opacity(0.12), radius: 2, x: 0, y: 1)
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

/// Grid tile: the picture, title and artist.
struct ArtCard: View {
    let item: ItemSummary
    var showsCaption = true

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ArtImage(ref: .thumb(item.id), placeholder: item.placeholderColor, maxPixel: 700)
                .aspectRatio(max(0.45, min(item.aspectRatio, 2.2)), contentMode: .fit)
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                .overlay(alignment: .topTrailing) {
                    if item.favorite {
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
    }
}

/// Two-column waterfall layout using the pictures' aspect ratios.
struct MasonryGrid<Content: View>: View {
    let items: [ItemSummary]
    var columns = 2
    var spacing: CGFloat = 16
    @ViewBuilder let content: (ItemSummary) -> Content

    private var distributed: [[ItemSummary]] {
        var buckets = Array(repeating: [ItemSummary](), count: columns)
        var heights = Array(repeating: 0.0, count: columns)
        for item in items {
            let target = heights.indices.min { heights[$0] < heights[$1] } ?? 0
            buckets[target].append(item)
            heights[target] += 1 / max(0.45, min(item.aspectRatio, 2.2)) + 0.28
        }
        return buckets
    }

    var body: some View {
        HStack(alignment: .top, spacing: spacing) {
            ForEach(Array(distributed.enumerated()), id: \.offset) { _, column in
                LazyVStack(spacing: spacing + 6) {
                    ForEach(column) { item in
                        content(item)
                    }
                }
            }
        }
    }
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

/// Proportional strip of the picture's dominant colours.
struct PaletteStrip: View {
    let swatches: [ColorSwatch]
    var height: CGFloat = 10

    var body: some View {
        GeometryReader { geo in
            let total = max(swatches.reduce(0) { $0 + $1.weight }, 0.001)
            HStack(spacing: 2) {
                ForEach(Array(swatches.enumerated()), id: \.offset) { _, swatch in
                    Rectangle()
                        .fill(Color(hexString: swatch.hex) ?? Theme.mat)
                        .frame(width: max(4, geo.size.width * swatch.weight / total - 2))
                }
            }
        }
        .frame(height: height)
        .clipShape(Capsule())
    }
}

/// Soft background tinted by the current picture's palette.
struct AmbientBackground: View {
    let swatches: [ColorSwatch]

    var body: some View {
        let colors = swatches.prefix(3).compactMap { Color(hexString: $0.hex) }
        ZStack {
            Theme.paper
            if !colors.isEmpty {
                LinearGradient(
                    colors: colors.map { $0.opacity(0.45) } + [Theme.paper.opacity(0)],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .blur(radius: 60)
                .saturation(0.8)
            }
            LinearGradient(
                colors: [.clear, Theme.paper.opacity(0.85), Theme.paper],
                startPoint: .top,
                endPoint: .bottom
            )
        }
        .ignoresSafeArea()
        .animation(.easeInOut(duration: 0.8), value: swatches)
    }
}

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

/// 2×2 collage of playlist covers.
/// Playlist cover: up to four works, laid out by how many there are. An
/// empty playlist gets a monogram on a mat instead of blank tiles.
struct Collage: View {
    let itemIDs: [String]
    var title: String = ""
    var spacing: CGFloat = 2

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

    private func tile(_ index: Int, _ width: CGFloat, _ height: CGFloat) -> some View {
        ArtImage(ref: .thumb(itemIDs[index]), maxPixel: 400)
            .frame(width: width, height: height)
            .clipped()
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
