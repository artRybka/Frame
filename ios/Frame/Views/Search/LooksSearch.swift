import PhotosUI
import SwiftUI
import UIKit

/// Szukaj by how works look (Google's embedding model, Mateusz 2026-11-13,
/// "G1"): words for how a work looks ("mglisty poranek nad wodą"), a
/// photograph of one (in a museum, a postcard, a page of a book), and the
/// works that look like a work ("Podobne wyglądem"). Only the museums' works
/// are found so; his own photos are never sent to Google.
enum LooksAsk: Hashable, Identifiable {
    case words(String)
    /// A JPEG made small on the phone (`LooksAsk.picture(from:)`).
    case picture(Data)
    /// Works that look like this one: its id and title.
    case like(String, String)

    var id: Self { self }

    var title: String {
        switch self {
        case .words(let words): "„\(words)”"
        case .picture: "Podobne do zdjęcia"
        case .like: "Podobne wyglądem"
        }
    }

    /// The photograph picked, as a JPEG of at most 1024 px a side: the
    /// model sees no more, and an iPhone's HEIC is no picture to the server.
    static func picture(from original: Data) -> LooksAsk? {
        guard let image = UIImage(data: original) else { return nil }
        let side = max(image.size.width, image.size.height)
        let scale = min(1, 1024 / max(side, 1))
        let size = CGSize(width: image.size.width * scale, height: image.size.height * scale)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let small = UIGraphicsImageRenderer(size: size, format: format).image { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
        return small.jpegData(compressionQuality: 0.85).map { LooksAsk.picture($0) }
    }
}

/// The works found by how they look, nearest first.
struct LooksResultsView: View {
    @Environment(AppModel.self) private var model
    let ask: LooksAsk
    @State private var found: [ItemSummary]?
    @State private var failed: String?
    @State private var liking: Set<String> = []

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                header
                if let found {
                    if found.isEmpty {
                        Text("Nie znalazłem dzieł, które tak wyglądają.")
                            .font(.subheadline)
                            .foregroundStyle(Theme.inkSoft)
                    } else {
                        MasonryGrid(items: found) { summary in
                            NavigationLink(value: summary.id) {
                                ArtCard(item: summary, showsFavorite: false)
                            }
                            .buttonStyle(.plain)
                            .contextMenu { QueueButton(itemID: summary.id) }
                            .overlay(alignment: .topTrailing) { heart(summary) }
                        }
                    }
                } else if let failed {
                    Label(failed, systemImage: "exclamationmark.circle")
                        .font(.subheadline)
                        .foregroundStyle(Theme.inkSoft)
                } else {
                    SearchWaiting()
                }
            }
            .pageWidth()
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 32)
        }
        .paperPage()
        .navigationTitle(ask.title)
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .onChange(of: model.hearts) { _, hearts in
            for (id, favorite) in hearts where !liking.contains(id) { mark(id, favorite: favorite) }
        }
    }

    @ViewBuilder
    private var header: some View {
        switch ask {
        case .words(let words):
            Text("Dzieła, które wyglądają jak „\(words)”")
                .font(.serif(17, weight: .medium))
                .foregroundStyle(Theme.ink)
        case .picture(let data):
            HStack(spacing: 12) {
                if let image = UIImage(data: data) {
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFill()
                        .frame(width: 64, height: 64)
                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                }
                Text("Dzieła podobne do tego zdjęcia")
                    .font(.serif(17, weight: .medium))
                    .foregroundStyle(Theme.ink)
            }
        case .like(_, let title):
            Text("Dzieła, które wyglądają jak „\(title)”")
                .font(.serif(17, weight: .medium))
                .foregroundStyle(Theme.ink)
        }
    }

    private func heart(_ item: ItemSummary) -> some View {
        TileHeart(favorite: item.favorite) {
            guard !liking.contains(item.id) else { return }
            Task { await setFavorite(item.id, !item.favorite) }
        }
    }

    private func mark(_ id: String, favorite: Bool) {
        guard let at = found?.firstIndex(where: { $0.id == id }) else { return }
        found?[at].favorite = favorite
    }

    @MainActor
    private func setFavorite(_ id: String, _ favorite: Bool) async {
        liking.insert(id)
        defer { liking.remove(id) }
        mark(id, favorite: favorite)
        let item = await model.setFavorite(id, favorite)
        mark(id, favorite: item?.favorite ?? !favorite)
    }

    private func load() async {
        guard found == nil else { return }
        failed = nil
        do {
            let answer: LooksAnswer = switch ask {
            case .words(let words): try await model.backend.looks(words: words)
            case .picture(let data): try await model.backend.looks(picture: data)
            case .like(let id, _): try await model.backend.looksLike(itemID: id)
            }
            withAnimation(.easeOut(duration: 0.25)) { found = answer.items }
        } catch {
            if error.isCancellation { return }
            failed = Self.why(error)
        }
    }

    /// The server's 409 (no key, switched off, nothing ready yet, the
    /// month's limit) and 502 (Google did not answer) in Polish.
    static func why(_ error: Error) -> String {
        switch error {
        case BackendError.http(409, _):
            return "Szukanie wyglądem jest teraz niedostępne. Sprawdź Konfiguracja → Gemini."
        case BackendError.http(502, _):
            return "Google teraz nie odpowiada. Spróbuj za chwilę."
        default:
            return error.localizedDescription
        }
    }
}

/// On a work's card: the works that look like it, a row to scroll sideways
/// ("Podobne wyglądem"). Nothing while it has none (no numbers yet, or the
/// search switched off).
struct LooksLikeSection: View {
    @Environment(AppModel.self) private var model
    let item: Item
    @State private var found: [ItemSummary] = []

    var body: some View {
        Group {
            if !found.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(alignment: .firstTextBaseline) {
                        Eyebrow("Podobne wyglądem")
                        Spacer()
                        NavigationLink {
                            LooksResultsView(ask: .like(item.id, item.displayTitle))
                        } label: {
                            Text("Więcej").font(.caption)
                        }
                    }
                    ScrollView(.horizontal, showsIndicators: false) {
                        LazyHStack(alignment: .top, spacing: 8) {
                            ForEach(found) { summary in
                                NavigationLink(value: summary.id) {
                                    ArtImage(ref: .thumb(summary.id), placeholder: summary.placeholderColor, maxPixel: 400)
                                        .frame(width: 110 * shape(summary), height: 110)
                                        .clipShape(RoundedRectangle(cornerRadius: 3, style: .continuous))
                                }
                                .buttonStyle(.plain)
                                .accessibilityLabel(summary.title)
                            }
                        }
                        .scrollTargetLayout()
                    }
                    .scrollTargetBehavior(.viewAligned)
                    .edgeToEdgeRow()
                }
                .transition(.opacity)
            }
        }
        .task(id: item.id) {
            guard item.kind == .artwork,
                  let answer = try? await model.backend.looksLike(itemID: item.id)
            else { return }
            withAnimation(.easeOut(duration: 0.25)) { found = Array(answer.items.prefix(12)) }
        }
    }

    /// Width / height, kept between a tall work and a long one.
    private func shape(_ summary: ItemSummary) -> CGFloat {
        CGFloat(max(0.6, min(2.0, summary.aspectRatio)))
    }
}

/// Szukaj's "Szukaj zdjęciem": a photograph from the library, searched by
/// how it looks.
struct LooksPhotoButton: View {
    @Environment(AppModel.self) private var model
    let found: (LooksAsk) -> Void
    @State private var picked: PhotosPickerItem?

    var body: some View {
        PhotosPicker(selection: $picked, matching: .images) {
            Label("Szukaj zdjęciem", systemImage: "camera.viewfinder")
                .font(.subheadline.weight(.medium))
                .foregroundStyle(Theme.ink)
                .padding(.horizontal, 14)
                .padding(.vertical, 9)
                .glassEffect(.regular.interactive(), in: Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityHint(Text("Wybierz zdjęcie dzieła, a Szukaj znajdzie podobne"))
        .onChange(of: picked) { _, item in
            guard let item else { return }
            picked = nil
            Task {
                guard let data = try? await item.loadTransferable(type: Data.self),
                      let ask = await Task.detached(priority: .userInitiated, operation: { LooksAsk.picture(from: data) }).value
                else {
                    model.notices.warn("Nie udało się wczytać zdjęcia")
                    return
                }
                found(ask)
            }
        }
    }
}
