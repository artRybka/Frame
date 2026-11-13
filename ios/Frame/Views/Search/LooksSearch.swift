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

/// Szukaj's camera (Mateusz 2026-11-13: "obok paska wyszukiwania z prawej -
/// sama ikonka aparatu widoczna tylko gdy nic nie jest wpisane ani wybrane z
/// grup", "wywoływać (domyślnie) funkcję aparatu"): an icon at the right end
/// of the system search field, there while nothing is asked. A tap opens
/// the camera (the photo library where there is none); held, it offers the
/// library too. The photograph is searched by how it looks.
extension View {
    func looksCamera(shown: Bool, found: @escaping (LooksAsk) -> Void) -> some View {
        modifier(LooksCamera(shown: shown, found: found))
    }
}

private struct LooksCamera: ViewModifier {
    @Environment(AppModel.self) private var model
    let shown: Bool
    let found: (LooksAsk) -> Void
    @State private var camera = false
    @State private var library = false
    @State private var picked: PhotosPickerItem?

    func body(content: Content) -> some View {
        content
            .background {
                SearchFieldCamera(
                    shown: shown,
                    onCamera: {
                        if UIImagePickerController.isSourceTypeAvailable(.camera) {
                            camera = true
                        } else {
                            library = true
                        }
                    },
                    onLibrary: { library = true }
                )
                .frame(width: 0, height: 0)
                .accessibilityHidden(true)
            }
            .fullScreenCover(isPresented: $camera) {
                CameraPicker { image in
                    guard let data = image.jpegData(compressionQuality: 0.9) else { return }
                    take(data)
                }
                .ignoresSafeArea()
            }
            .photosPicker(isPresented: $library, selection: $picked, matching: .images)
            .onChange(of: picked) { _, item in
                guard let item else { return }
                picked = nil
                Task {
                    guard let data = try? await item.loadTransferable(type: Data.self) else {
                        model.notices.warn("Nie udało się wczytać zdjęcia")
                        return
                    }
                    take(data)
                }
            }
    }

    private func take(_ data: Data) {
        Task {
            guard let ask = await Task.detached(priority: .userInitiated, operation: { LooksAsk.picture(from: data) }).value
            else {
                model.notices.warn("Nie udało się wczytać zdjęcia")
                return
            }
            found(ask)
        }
    }
}

/// The camera, as UIKit has it (SwiftUI has none).
private struct CameraPicker: UIViewControllerRepresentable {
    let took: (UIImage) -> Void
    @Environment(\.dismiss) private var dismiss

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ picker: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let parent: CameraPicker

        init(_ parent: CameraPicker) { self.parent = parent }

        func imagePickerController(
            _ picker: UIImagePickerController,
            didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]
        ) {
            if let image = info[.originalImage] as? UIImage { parent.took(image) }
            parent.dismiss()
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { parent.dismiss() }
    }
}

/// Puts the camera button at the right end of the system search field
/// (`.searchable` gives no place for one): the field's right view, the
/// place of the microphone in Apple's own fields, while ``shown``.
private struct SearchFieldCamera: UIViewRepresentable {
    let shown: Bool
    let onCamera: () -> Void
    let onLibrary: () -> Void

    func makeUIView(context: Context) -> Probe {
        let probe = Probe()
        probe.isUserInteractionEnabled = false
        return probe
    }

    func updateUIView(_ probe: Probe, context: Context) {
        probe.shown = shown
        probe.onCamera = onCamera
        probe.onLibrary = onLibrary
        probe.apply()
    }

    static func dismantleUIView(_ probe: Probe, coordinator: ()) {
        probe.shown = false
        probe.apply()
    }

    final class Probe: UIView {
        var shown = false
        var onCamera: () -> Void = {}
        var onLibrary: () -> Void = {}
        private weak var field: UISearchTextField?
        private lazy var button: UIButton = {
            var look = UIButton.Configuration.plain()
            // Filled and a little smaller than the magnifier, close to the
            // field's end (Mateusz 2026-11-13: "pełna i trochę drobniejsza").
            look.image = UIImage(
                systemName: "camera.fill",
                withConfiguration: UIImage.SymbolConfiguration(pointSize: 14, weight: .regular)
            )
            look.baseForegroundColor = .secondaryLabel
            look.contentInsets = NSDirectionalEdgeInsets(top: 0, leading: 4, bottom: 0, trailing: 0)
            let button = UIButton(configuration: look)
            button.accessibilityLabel = "Szukaj zdjęciem"
            button.accessibilityHint = "Zrób zdjęcie dzieła, a Szukaj znajdzie podobne. Przytrzymaj, by wybrać z Biblioteki."
            button.addAction(UIAction { [weak self] _ in self?.onCamera() }, for: .primaryActionTriggered)
            button.menu = UIMenu(children: [
                UIAction(title: "Zrób zdjęcie", image: UIImage(systemName: "camera")) { [weak self] _ in
                    self?.onCamera()
                },
                UIAction(title: "Wybierz z Biblioteki", image: UIImage(systemName: "photo.on.rectangle")) { [weak self] _ in
                    self?.onLibrary()
                },
            ])
            button.showsMenuAsPrimaryAction = false
            button.sizeToFit()
            return button
        }()

        override func didMoveToWindow() {
            super.didMoveToWindow()
            apply()
            // The system puts the field in place a moment after the page.
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [weak self] in self?.apply() }
        }

        func apply() {
            guard let window else {
                take()
                return
            }
            if field == nil || field?.window == nil { field = Self.searchField(in: window) }
            guard let field else { return }
            if shown {
                if field.rightView !== button {
                    field.rightView = button
                    field.rightViewMode = .always
                }
            } else {
                take()
            }
        }

        /// The button out of the field.
        private func take() {
            guard let field, field.rightView === button else { return }
            field.rightView = nil
        }

        /// Szukaj's own field: the one showing, not in a sheet over it.
        private static func searchField(in view: UIView) -> UISearchTextField? {
            if let field = view as? UISearchTextField, !field.isHidden, field.alpha > 0.01 {
                return field
            }
            for subview in view.subviews.reversed() {
                if let field = searchField(in: subview) { return field }
            }
            return nil
        }
    }
}
