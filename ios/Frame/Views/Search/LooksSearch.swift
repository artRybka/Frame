import PhotosUI
import SwiftUI
import UIKit

/// Szukaj by how works look (Google's embedding model, Mateusz 2026-11-13,
/// "G1"): words for how a work looks are the chip "Wygląd"; the works that
/// look like a work, or like a photograph (of a work in a museum, a
/// postcard, a page of a book), are the chip "Podobne do", in Szukaj's own
/// list, the groups narrowing them (Mateusz 2026-11-15: "tak jak przy
/// „szukaj podobnych” z karty dzieła"). Only the museums' works are found
/// so; his own photos are never sent to Google.
enum LookPhoto {
    /// The photograph picked, as a JPEG of at most 1024 px a side: the
    /// model sees no more, and an iPhone's HEIC is no picture to the server.
    static func small(from original: Data) -> Data? {
        guard let image = UIImage(data: original) else { return nil }
        let side = max(image.size.width, image.size.height)
        let scale = min(1, 1024 / max(side, 1))
        let size = CGSize(width: image.size.width * scale, height: image.size.height * scale)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let small = UIGraphicsImageRenderer(size: size, format: format).image { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
        return small.jpegData(compressionQuality: 0.85)
    }

    /// The server's 409 (the works' numbers not ready yet) in Polish.
    static func why(_ error: Error) -> String {
        switch error {
        case BackendError.http(409, _):
            return "Szukanie wyglądem jeszcze się przygotowuje. Postęp jest w Konfiguracja → Diagnostyka."
        default:
            return error.localizedDescription
        }
    }
}

/// On a work's card, above its facts: the three works that look most like
/// it, side by side in their own proportions, standing on one line as on a
/// wall, title and artist under each; a tap opens the work. Under them
/// "Szukaj podobnych" with how many there are opens Szukaj with the chip
/// "Podobne do: …" (Mateusz 2026-11-13, sketch B: "Super, wdrażamy").
/// Nothing while it has none (no numbers yet, or the search switched off).
struct LooksLikeSection: View {
    @Environment(AppModel.self) private var model
    let item: Item
    @State private var found: [ItemSummary] = []
    /// Of `found`, how many Szukaj's "Podobne do" shows (the server's
    /// closeness floor, Mateusz 2026-11-19); an older server says nothing.
    @State private var alike: Int?
    /// The card's width, for the height of the row's pictures.
    @State private var width: CGFloat?

    /// The works shown on the card.
    static let shown = 3
    /// The works counted ("60+" at this many): the server's most at once.
    static let counted = 60

    var body: some View {
        // Something there also while nothing is found: a task on a Group of
        // nothing never ran, and the row never came (Mateusz 2026-11-13: "Na
        // karcie dzieła nie widzę sekcji „podobne wyglądem”").
        VStack(alignment: .leading, spacing: 0) {
            if found.isEmpty {
                Color.clear.frame(height: 0)
            } else {
                VStack(alignment: .leading, spacing: 14) {
                    Eyebrow("Podobne wyglądem")
                    row
                    if found.count > Self.shown { searchButton }
                }
                .transition(.opacity)
            }
        }
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { width = $0 }
        .task(id: item.id) {
            guard item.kind == .artwork || item.isOwnWork,  // his own works too (Mateusz 2026-11-16)
                  let answer = try? await model.backend.looksLike(itemID: item.id, limit: Self.counted)
            else { return }
            withAnimation(.easeOut(duration: 0.25)) {
                found = answer.items
                alike = answer.alike
            }
        }
    }

    private var picked: [ItemSummary] { Array(found.prefix(Self.shown)) }

    /// One line of pictures, all as tall as `LooksRow.pictureHeight` and in
    /// their own proportions, the same gap between them (Mateusz
    /// 2026-11-14: tall scrolls stuck out over the heading and the button
    /// above, a long folding screen ran into its neighbour). A picture too
    /// long for its share of the row is fitted to its column, shorter, on
    /// the same bottom line; a tall one keeps a column wide enough for its
    /// title. The pictures' box is only as tall as the tallest of them, so
    /// three long screens sit right under the heading (Mateusz 2026-11-15:
    /// a large empty space above three Japanese screens).
    private var row: some View {
        LooksRow(ratios: picked.map { shape($0) }, slots: Self.shown) {
            ForEach(picked) { summary in
                tile(summary)
            }
        }
    }

    private func tile(_ summary: ItemSummary) -> some View {
        NavigationLink(value: summary.id) {
            VStack(alignment: .leading, spacing: 8) {
                Color.clear
                    .frame(maxWidth: .infinity)
                    .frame(height: pictureBox)
                    .overlay(alignment: .bottomLeading) {
                        ArtImage(
                            ref: .thumb(summary.id), placeholder: summary.placeholderColor,
                            maxPixel: 400, contentMode: .fit
                        )
                        .aspectRatio(shape(summary), contentMode: .fit)
                    }
                    .clipped()
                VStack(alignment: .leading, spacing: 2) {
                    Text(bound: summary.shownTitle)
                        .font(.serif(14, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                    if !summary.artist.isEmpty {
                        Text(bound: summary.artist)
                            .font(.caption)
                            .foregroundStyle(Theme.inkSoft)
                            .lineLimit(1)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
    }

    private var searchButton: some View {
        LooksSearchButton(itemID: item.id, title: item.displayTitle, count: alike ?? found.count)
    }

    /// The height every picture of the row is fitted into.
    private var pictureBox: CGFloat {
        guard let width, width > 0 else { return LooksRow.pictureHeight }
        return LooksRow.pictureBox(ratios: picked.map { shape($0) }, width: width, slots: Self.shown)
    }

    /// Width / height, as the picture is (only nonsense kept out).
    private func shape(_ summary: ItemSummary) -> CGFloat {
        LooksRow.ratio(summary.aspectRatio)
    }
}

/// "Szukaj podobnych N": into Szukaj with the works that look like one
/// (`AppModel.searchLike`), under the card's "Podobne wyglądem" and the
/// study's "Podobne dzieła" (Mateusz 2026-11-18: „Na studium dzieła dodaj
/// guzik szukania podobnych jak w karcie dzieła”). Given no `count`, it
/// asks the server for one and stays away until some are found.
///
/// Filled with ink, like the app's other buttons that lead on (Mateusz
/// 2026-11-14: "Ten guzik zróbmy w kolorze czarnym"): black with light
/// letters on paper, cream with dark ones in the dark, where a black one
/// would sink into the page. The count is its letters, fainter.
struct LooksSearchButton: View {
    @Environment(AppModel.self) private var model
    let itemID: String
    let title: String
    var count: Int?
    @State private var asked: Int?

    private var shown: Int { count ?? asked ?? 0 }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if shown > 0 {
                Button {
                    model.searchLike(itemID, title: title)
                } label: {
                    HStack(spacing: 8) {
                        // "Podobne do dzieła"'s own mark, as on its chip.
                        GroupMark(kind: SearchToken.likeWorkMark, side: 20)
                        Text(bound: "Szukaj podobnych")
                        Text(shown >= LooksLikeSection.counted ? "\(LooksLikeSection.counted)+" : "\(shown)")
                            .opacity(0.65)
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .accessibilityHint("Otwiera Szukaj z dziełami podobnymi do tego")
                .transition(.opacity)
            } else {
                Color.clear.frame(height: 0)
            }
        }
        .task(id: itemID) {
            guard count == nil, !itemID.isEmpty,
                  let answer = try? await model.backend.looksLike(itemID: itemID, limit: LooksLikeSection.counted)
            else { return }
            withAnimation(.easeOut(duration: 0.25)) { asked = answer.alike ?? answer.items.count }
        }
    }
}

/// The row of "Podobne wyglądem": columns as wide as their pictures are at
/// `pictureHeight`, never narrower than a title needs, `spacing` between
/// them. When they don't fit, the widest give way first (each down to what
/// the others leave), so a long screen shrinks before a tall scroll does.
/// The columns start at the left; what is left over stays at the right.
struct LooksRow: Layout {
    let ratios: [CGFloat]
    /// The columns the narrowest title width is reckoned from.
    let slots: Int

    /// Every picture's box: one height for the whole row.
    static let pictureHeight: CGFloat = 150
    static let spacing: CGFloat = 12
    /// A column's least width, as a share of an equal column.
    static let leastShare: CGFloat = 0.8

    /// Width / height of a picture, as it is (only nonsense kept out).
    static func ratio(_ aspect: Double) -> CGFloat {
        guard aspect.isFinite, aspect > 0 else { return 4.0 / 3.0 }
        return CGFloat(max(0.05, min(40, aspect)))
    }

    /// The columns' widths in `width`.
    static func widths(ratios: [CGFloat], width: CGFloat, slots: Int) -> [CGFloat] {
        guard !ratios.isEmpty else { return [] }
        let count = ratios.count
        let room = max(0, width - spacing * CGFloat(count - 1))
        let least = min(room / CGFloat(count), leastShare * room / CGFloat(max(slots, count)))
        let wanted = ratios.map { max(least, pictureHeight * $0) }
        guard wanted.reduce(0, +) > room else { return wanted }
        // The widest are cut to one width: what the narrower ones leave.
        let order = wanted.indices.sorted { wanted[$0] < wanted[$1] }
        var left = room
        var cap = room / CGFloat(count)
        for (done, index) in order.enumerated() {
            cap = left / CGFloat(count - done)
            if wanted[index] >= cap { break }
            left -= wanted[index]
        }
        return wanted.map { min($0, cap) }
    }

    /// The height of the row's pictures in `width`: the tallest of them as
    /// fitted to its column, never more than `pictureHeight`. Three long
    /// screens, each cut to a third of the row, get a low box instead of
    /// one as tall as a scroll's with nothing in its upper part.
    static func pictureBox(ratios: [CGFloat], width: CGFloat, slots: Int) -> CGFloat {
        let columns = widths(ratios: ratios, width: width, slots: slots)
        let tallest = zip(columns, ratios).map { min(pictureHeight, $0 / $1) }.max()
        return (tallest ?? pictureHeight).rounded(.up)
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 360
        let columns = Self.widths(ratios: fitted(subviews), width: width, slots: slots)
        let height = zip(subviews, columns)
            .map { $0.sizeThatFits(ProposedViewSize(width: $1, height: nil)).height }
            .max() ?? 0
        return CGSize(width: width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let columns = Self.widths(ratios: fitted(subviews), width: bounds.width, slots: slots)
        var x = bounds.minX
        for (subview, column) in zip(subviews, columns) {
            subview.place(
                at: CGPoint(x: x, y: bounds.minY), anchor: .topLeading,
                proposal: ProposedViewSize(width: column, height: nil)
            )
            x += column + Self.spacing
        }
    }

    /// One ratio per subview (a missing one, landscape).
    private func fitted(_ subviews: Subviews) -> [CGFloat] {
        subviews.indices.map { $0 < ratios.count ? ratios[$0] : 4.0 / 3.0 }
    }
}

/// Szukaj's camera (Mateusz 2026-11-13: "obok paska wyszukiwania z prawej -
/// sama ikonka aparatu widoczna tylko gdy nic nie jest wpisane ani wybrane z
/// grup", "wywoływać (domyślnie) funkcję aparatu"): an icon at the right end
/// of the system search field, there while nothing is asked. A tap opens
/// the camera (the photo library where there is none); held, it offers the
/// library too. The photograph is searched by how it looks.
extension View {
    func looksCamera(shown: Bool, found: @escaping (Data) -> Void) -> some View {
        modifier(LooksCamera(shown: shown, found: found))
    }
}

private struct LooksCamera: ViewModifier {
    @Environment(AppModel.self) private var model
    let shown: Bool
    let found: (Data) -> Void
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
            guard let small = await Task.detached(priority: .userInitiated, operation: { LookPhoto.small(from: data) }).value
            else {
                model.notices.warn("Nie udało się wczytać zdjęcia")
                return
            }
            found(small)
        }
    }
}

/// The camera, as UIKit has it (SwiftUI has none).
struct CameraPicker: UIViewControllerRepresentable {
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
