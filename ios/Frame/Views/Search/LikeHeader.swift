import SwiftUI

/// What Szukaj's "Podobne do" looks for, over its works (Mateusz
/// 2026-11-18: "A, ale nagłówek „PODOBNE DO [Tytuł dzieła]” jak w B, ale
/// z miniaturą obok tytułu"): the work (or the photograph) small, its
/// title and artist, a cross that ends the search for works like it, and
/// under them the two switches, `LikeBySwitches`.
struct LikeHeader: View {
    @Environment(AppModel.self) private var model
    /// The work's id, or a photograph's key (`SearchToken.isPhoto`).
    let like: String
    /// The photograph searched, when it is one.
    let photo: Data?
    let close: () -> Void
    @State private var item: Item?
    @State private var photoShown = false

    private var isPhoto: Bool { SearchToken.isPhoto(like) }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            thumb
            VStack(alignment: .leading, spacing: 3) {
                Eyebrow("Podobne do")
                Text(bound: title)
                    .font(.serif(20, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
                if !byline.isEmpty {
                    Text(bound: byline)
                        .font(.footnote)
                        .foregroundStyle(Theme.inkSoft)
                        .lineLimit(1)
                }
            }
            .padding(.top, 1)
            Spacer(minLength: 0)
            Button(action: close) {
                Image(systemName: "xmark")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(Theme.inkSoft)
                    .frame(width: 26, height: 26)
                    .background(Theme.ink.opacity(0.07), in: Circle())
                    .frame(width: 44, height: 44)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .padding(.top, -9)
            .padding(.trailing, -9)
            .accessibilityLabel("Zakończ szukanie podobnych")
        }
        .task(id: like) {
            item = nil
            guard !isPhoto, !like.isEmpty else { return }
            item = try? await model.backend.item(id: like)
        }
        .fullScreenCover(isPresented: $photoShown) {
            PhotoShown(photo: photo) { photoShown = false }
        }
    }

    private var title: String {
        if isPhoto { return "Twojego zdjęcia" }
        return item?.displayTitle ?? model.likeTitles[SearchToken.likeName(like)] ?? ""
    }

    private var byline: String {
        if isPhoto { return photo == nil ? "" : "Dotknij, by zobaczyć całe" }
        guard let item else { return "" }
        return [Names.artist(item.artist), item.dateText].filter { !$0.isEmpty }.joined(separator: ", ")
    }

    /// As tall as the title's lines; a work in its own proportions (within
    /// reason), a photograph square, as it was shown before.
    private static let side: CGFloat = 70

    @ViewBuilder
    private var thumb: some View {
        if isPhoto {
            if let photo, let image = UIImage(data: photo) {
                Button { photoShown = true } label: {
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFill()
                        .frame(width: Self.side, height: Self.side)
                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Szukane zdjęcie")
                .accessibilityHint("Pokazuje całe zdjęcie")
            }
        } else {
            NavigationLink(value: like) {
                ArtImage(ref: .thumb(like), placeholder: item?.placeholderColor ?? Theme.mat,
                         maxPixel: 300, contentMode: .fill)
                    .frame(width: Self.side * ratio, height: Self.side)
                    .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Otwórz kartę dzieła")
        }
    }

    /// Width / height of the work's thumbnail, between a tall scroll's and
    /// a long screen's, so the title keeps its room.
    private var ratio: CGFloat {
        guard let width = item?.width, let height = item?.height, width > 0, height > 0 else { return 1 }
        return min(1.6, max(0.6, CGFloat(width) / CGFloat(height)))
    }
}

/// The photograph searched, whole, on black; a tap closes it.
private struct PhotoShown: View {
    let photo: Data?
    let close: () -> Void

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            if let photo, let image = UIImage(data: photo) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()
                    .accessibilityLabel("Szukane zdjęcie")
            }
        }
        .contentShape(Rectangle())
        .onTapGesture(perform: close)
        .accessibilityAction(named: "Zamknij", close)
    }
}

/// "Temat" and "Forma", each on or off, both on at first: what "Podobne
/// do" finds alike (`PlaylistRules.likeBy`). One of them is always on; the
/// line under them says what the choice means (Mateusz 2026-11-18: no
/// "Wyłącz jedno, by szukać po drugim").
struct LikeBySwitches: View {
    @Binding var selection: String

    private var by: LikeBy { LikeBy(rawValue: selection) ?? .both }
    private var subject: Bool { by != .style }
    private var style: Bool { by != .subject }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                toggle(LikeBy.subject.title, on: subject) {
                    // Off only while the other is on.
                    selection = subject ? (style ? LikeBy.style.rawValue : selection) : LikeBy.both.rawValue
                }
                toggle(LikeBy.style.title, on: style) {
                    selection = style ? (subject ? LikeBy.subject.rawValue : selection) : LikeBy.both.rawValue
                }
            }
            Text(bound: by.meaning)
                .font(.footnote)
                .foregroundStyle(Theme.inkSoft)
                .contentTransition(.opacity)
        }
        .animation(.snappy(duration: 0.2), value: selection)
        .sensoryFeedback(.selection, trigger: selection)
        .accessibilityIdentifier("likeBy")
    }

    private func toggle(_ title: String, on: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                if on {
                    Image(systemName: "checkmark")
                        .font(.system(size: 13, weight: .bold))
                        .transition(.scale.combined(with: .opacity))
                }
                Text(bound: title)
            }
            .font(.system(size: 16, weight: .semibold))
            .foregroundStyle(on ? Theme.paper : Theme.ink)
            .frame(maxWidth: .infinity, minHeight: 40)
            .background {
                Capsule().fill(on ? Theme.ink : Color.clear)
                Capsule().strokeBorder(Theme.inkSoft.opacity(on ? 0 : 0.6), lineWidth: 1)
            }
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}
