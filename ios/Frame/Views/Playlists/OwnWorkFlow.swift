import CoreImage
import CoreImage.CIFilterBuiltins
import PhotosUI
import SwiftUI

/// "Dodaj własne dzieło" (Mateusz 2026-11-15, variant A with hints): from
/// the "+" in Playlisty, three steps on the whole screen. A photograph from
/// the camera (or Photos); the work found in it by the server and cut out
/// of its frame and mount, its corners his to move; then what he knows of
/// it, with what was read off the picture (signature, date, technique) as
/// chips to take. One work at a time. "Zrób zdjęcie ponownie" on its card
/// takes the first two steps again and keeps what he wrote.
struct OwnWorkFlow: View {
    enum Mode {
        case add
        /// A new photograph of a work of his ("Zrób zdjęcie ponownie").
        case retake(Item)
    }

    enum Step: Int, CaseIterable {
        case photo, cut, describe

        var name: String {
            switch self {
            case .photo: "Zdjęcie"
            case .cut: "Kadr"
            case .describe: "Opis"
            }
        }
    }

    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let mode: Mode
    /// The work as added (or photographed again): its card opens.
    let done: (Item) -> Void

    @State private var step = Step.photo
    @State private var photo: UIImage?
    @State private var incoming: OwnIncoming?
    /// The server is sending or looking at the photograph.
    @State private var finding = false
    /// The corners the server found; nil when none.
    @State private var found: [[Double]]?
    /// The corners he went on with; nil, the photograph whole.
    @State private var corners: [[Double]]?
    @State private var cutBy = "auto"
    /// The work cut out on the phone, for the description's header.
    @State private var picture: UIImage?
    @State private var hints: OwnHints?
    @State private var readingHints = false
    @State private var text = OwnDescription()
    @State private var adding = false
    @State private var camera = false
    @State private var library = false
    @State private var picked: PhotosPickerItem?

    private var retaking: Item? {
        if case let .retake(item) = mode { return item }
        return nil
    }

    private var steps: [Step] { retaking == nil ? Step.allCases : [.photo, .cut] }

    var body: some View {
        VStack(spacing: 0) {
            StepDots(steps: steps.map(\.name), current: steps.firstIndex(of: step) ?? 0)
                .padding(.top, 10)
                .padding(.bottom, 16)
            switch step {
            case .photo: photoStep
            case .cut: cutStep
            case .describe: describeStep
            }
        }
        .background { Color.clear.paperPage() }
        .fullScreenCover(isPresented: $camera) {
            CameraPicker { image in take(image) }
                .ignoresSafeArea()
        }
        .photosPicker(isPresented: $library, selection: $picked, matching: .images)
        .onChange(of: picked) { _, item in
            guard let item else { return }
            picked = nil
            Task {
                guard let data = try? await item.loadTransferable(type: Data.self), let image = UIImage(data: data) else {
                    model.notices.warn("Nie udało się wczytać zdjęcia")
                    return
                }
                take(image)
            }
        }
        .task { await openForScreenshot() }
    }

    // MARK: 1. The photograph

    private var photoStep: some View {
        VStack(spacing: 0) {
            HStack {
                Button("Anuluj") { dismiss() }
                    .buttonStyle(.glass)
                Spacer()
            }
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 12)
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Eyebrow(retaking == nil ? "Moja kolekcja" : "Nowe zdjęcie", color: Theme.vermilion)
                    Text(retaking.map { $0.title.isEmpty ? "Zrób zdjęcie ponownie" : $0.title } ?? "Własne dzieło")
                        .font(.serif(32, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                    Text(retaking == nil
                         ? "Sfotografuj obraz, rysunek albo grafikę, którą masz w domu. Ramę, passe-partout i ścianę wytnę sam, a narożniki poprawisz w następnym kroku."
                         : "Nowe zdjęcie zastąpi obecne, opis zostanie bez zmian.")
                        .font(.serif(17))
                        .foregroundStyle(Theme.inkSoft)
                    PhotoTips()
                        .padding(.top, 4)
                    if finding, let photo {
                        HStack(spacing: 12) {
                            Image(uiImage: photo)
                                .resizable()
                                .scaledToFill()
                                .frame(width: 56, height: 56)
                                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Szukam dzieła na zdjęciu…")
                                    .font(.subheadline.weight(.medium))
                                    .foregroundStyle(Theme.ink)
                                Text("Kilka sekund")
                                    .font(.caption)
                                    .foregroundStyle(Theme.inkSoft)
                            }
                            Spacer()
                            ProgressView()
                        }
                        .padding(12)
                        .background(Theme.card, in: RoundedRectangle(cornerRadius: Theme.corner, style: .continuous))
                        .transition(.opacity)
                    }
                }
                .pageWidth()
                .padding(.horizontal, Theme.gutter)
                .padding(.bottom, 24)
            }
            VStack(spacing: 10) {
                Button {
                    if UIImagePickerController.isSourceTypeAvailable(.camera) {
                        camera = true
                    } else if model.demoMode, let demo = DemoOwn.photo() {
                        take(demo)  // the simulator has no camera
                    } else {
                        library = true
                    }
                } label: {
                    Label("Zrób zdjęcie", systemImage: "camera.fill")
                }
                .buttonStyle(ActionButtonStyle(prominent: true))
                Button { library = true } label: {
                    Label("Wybierz ze Zdjęć", systemImage: "photo.on.rectangle")
                }
                .buttonStyle(ActionButtonStyle())
            }
            .disabled(finding)
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 16)
            .pageWidth()
        }
        .animation(.easeOut(duration: 0.25), value: finding)
    }

    /// The photograph upright (the camera's turn drawn in), sent, and the
    /// work looked for in it.
    private func take(_ taken: UIImage) {
        let image = Self.upright(taken)
        photo = image
        finding = true
        Task {
            defer { finding = false }
            guard let data = image.jpegData(compressionQuality: 0.9) else { return }
            do {
                var sent = try await model.backend.sendOwnPhoto(data)
                do {
                    sent = try await model.backend.findOwnWork(token: sent.token)
                } catch {
                    // No key, or Opus could not: he sets the corners himself.
                }
                incoming = sent
                found = sent.corners
                withAnimation(.easeInOut(duration: 0.3)) { step = .cut }
            } catch {
                model.show(error)
            }
        }
    }

    // MARK: 2. The cut

    private var cutNote: String {
        if let shape = incoming?.shape, !shape.isEmpty, shape != "rectangle" {
            return "To dzieło nie jest prostokątem, więc zostaje całe zdjęcie. Możesz je przyciąć sam."
        }
        if found != nil { return "Rama wycięta. Popraw narożniki w lupach, jeśli trzeba." }
        return "Nie znalazłem dzieła na zdjęciu. Ustaw narożniki sam."
    }

    @ViewBuilder
    private var cutStep: some View {
        if let photo, let incoming {
            CutEditor(
                photo: .local(photo), aspect: incoming.aspect, corners: found,
                saveTitle: retaking == nil ? "Dalej" : "Zapisz", cancelTitle: "Wstecz", savesUnchanged: true,
                note: cutNote,
                cancel: { withAnimation(.easeInOut(duration: 0.3)) { step = .photo } }
            ) { chosen in
                await cutChosen(chosen)
            }
        }
    }

    private func cutChosen(_ chosen: [[Double]]) async -> Bool {
        let whole = chosen == [[0, 0], [1, 0], [1, 1], [0, 1]]
        corners = whole ? nil : chosen
        cutBy = chosen == found ? "auto" : "owner"
        guard let incoming else { return false }
        if let item = retaking {
            do {
                let updated = try await model.backend.retakeOwnWork(
                    itemID: item.id,
                    OwnPhotoCut(token: incoming.token, corners: corners, by: cutBy, shape: incoming.shape)
                )
                model.ownWorkChanged(updated)
                done(updated)
                dismiss()
                return true
            } catch {
                model.show(error)
                return false
            }
        }
        if let photo { picture = OwnPicture.cut(photo, corners: corners) }
        withAnimation(.easeInOut(duration: 0.3)) { step = .describe }
        readHints()
        return true
    }

    /// What can be read off the work (Sonnet, about a grosz): the chips
    /// come in while he writes. None without a key, and no word of it.
    private func readHints() {
        guard let incoming, hints == nil, !readingHints else { return }
        readingHints = true
        Task {
            defer { readingHints = false }
            if let read = try? await model.backend.ownHints(token: incoming.token, corners: corners), !read.isEmpty {
                withAnimation(.easeOut(duration: 0.3)) { hints = read }
            }
        }
    }

    // MARK: 3. The description

    private var describeStep: some View {
        VStack(spacing: 0) {
            HStack {
                Button("Wstecz") { withAnimation(.easeInOut(duration: 0.3)) { step = .cut } }
                    .buttonStyle(.glass)
                    .disabled(adding)
                Spacer()
                Button {
                    Task { await add() }
                } label: {
                    HStack(spacing: 8) {
                        if adding { ProgressView().controlSize(.small).tint(Theme.paper) }
                        Text("Dodaj")
                    }
                    .foregroundStyle(Theme.paper)
                }
                .buttonStyle(.glassProminent)
                .tint(Theme.ink)
                .disabled(adding)
            }
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 12)
            ScrollViewReader { proxy in
                ScrollView {
                    OwnDescriptionForm(
                        text: $text, picture: picture, aspect: picture.map { Double($0.size.width / max($0.size.height, 1)) },
                        hints: hints, readingHints: readingHints, places: places
                    )
                    .pageWidth()
                    .padding(.horizontal, Theme.gutter)
                    .padding(.bottom, 40)
                }
                .scrollDismissesKeyboard(.interactively)
                .onChange(of: text.hangs) { _, hangs in
                    // CI screenshots: the lower fields, filled.
                    guard LaunchRoute.scroll == "filled", !hangs.isEmpty else { return }
                    Task {
                        try? await Task.sleep(for: .milliseconds(400))
                        withAnimation(nil) { proxy.scrollTo("size", anchor: .center) }
                    }
                }
            }
        }
    }

    /// Where his other works hang: chips under "Gdzie wisi".
    private var places: [String] {
        var seen = Set<String>()
        return model.ownWorks.compactMap { $0.own?.hangs }.filter { !$0.isEmpty && seen.insert($0).inserted }
    }

    private func add() async {
        guard let incoming else { return }
        adding = true
        defer { adding = false }
        do {
            let item = try await model.backend.addOwnWork(
                NewOwnWork(token: incoming.token, corners: corners, by: cutBy, shape: incoming.shape, text: text.trimmed)
            )
            model.ownWorkChanged(item)
            model.notices.info("Dodane do kolekcji", item.title.isEmpty ? "Bez tytułu" : item.title)
            done(item)
            dismiss()
        } catch {
            model.show(error)
        }
    }

    // MARK: Screenshots

    /// `-screen own-cut|own-describe` (demo): the demo's photograph taken,
    /// the flow at that step.
    private func openForScreenshot() async {
        guard model.demoMode, ["own-cut", "own-describe", "own-card"].contains(LaunchRoute.screen), photo == nil,
              let demo = DemoOwn.photo()
        else { return }
        take(demo)
        guard LaunchRoute.screen != "own-cut" else { return }
        for _ in 0 ..< 50 where step != .cut { try? await Task.sleep(for: .milliseconds(200)) }
        guard step == .cut else { return }
        _ = await cutChosen(DemoOwn.work)
        if LaunchRoute.scroll == "filled" || LaunchRoute.screen == "own-card" {
            try? await Task.sleep(for: .seconds(2))
            text.title = "Spacer po klifie"
            text.artist = "Claude Monet"
            text.dateText = "1882"
            text.medium = "olej na płótnie"
            text.heightCm = 65
            text.widthCm = 81
            text.hangs = "Salon"
            text.origin = "Prezent od dziadka"
        }
        if LaunchRoute.screen == "own-card" {
            try? await Task.sleep(for: .seconds(1))
            await add()  // the card opens
        }
    }

    /// The camera's photograph as it was held: pixels upright, so the
    /// corners mean the same on the phone and on the server.
    static func upright(_ image: UIImage) -> UIImage {
        let side: CGFloat = 4000
        let scale = min(1, side / max(image.size.width, image.size.height))
        guard image.imageOrientation != .up || scale < 1 else { return image }
        let size = CGSize(width: (image.size.width * scale).rounded(), height: (image.size.height * scale).rounded())
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        return UIGraphicsImageRenderer(size: size, format: format).image { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
    }
}

/// How to photograph a work so it cuts well.
private struct PhotoTips: View {
    private static let tips: [(String, String)] = [
        ("viewfinder", "Całe dzieło w kadrze, z kawałkiem ściany wokół"),
        ("arrow.up.and.down.and.arrow.left.and.right", "Najlepiej na wprost; ukos wyprostuję"),
        ("sun.max", "Dzienne światło, bez lampy błyskowej i odbić w szybie"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(Self.tips, id: \.1) { symbol, tip in
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    Image(systemName: symbol)
                        .font(.subheadline)
                        .foregroundStyle(Theme.vermilion)
                        .frame(width: 22)
                    Text(tip)
                        .font(.subheadline)
                        .foregroundStyle(Theme.ink)
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: Theme.corner, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: Theme.corner, style: .continuous).strokeBorder(Theme.hairline))
    }
}

/// "Zdjęcie · Kadr · Opis": where in the steps he is.
private struct StepDots: View {
    let steps: [String]
    let current: Int

    var body: some View {
        HStack(spacing: 8) {
            ForEach(Array(steps.enumerated()), id: \.offset) { index, name in
                if index > 0 {
                    Rectangle().fill(Theme.hairline).frame(width: 18, height: 1)
                }
                HStack(spacing: 5) {
                    Text("\(index + 1)")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(index <= current ? Theme.paper : Theme.inkSoft)
                        .frame(width: 18, height: 18)
                        .background(index <= current ? Theme.ink : Theme.mat, in: Circle())
                    Text(name)
                        .font(.caption.weight(index == current ? .semibold : .regular))
                        .foregroundStyle(index == current ? Theme.ink : Theme.inkSoft)
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Krok \(current + 1) z \(steps.count): \(steps[min(current, steps.count - 1)])")
    }
}

/// The work cut out of a photograph on the phone, as the server cuts it.
enum OwnPicture {
    private static let context = CIContext()

    /// The work inside `corners` of `image`, upright; in the shape of his
    /// size (`own`) when he gave one near enough, as the server keeps it.
    static func cut(_ image: UIImage, corners: [[Double]]?, own: OwnWork?) -> UIImage {
        let upright = cut(image, corners: corners)
        guard corners != nil, let own, let source = CIImage(image: upright) else { return upright }
        let w = source.extent.width, h = source.extent.height
        guard h > 0, let ratio = own.ratio(Double(w / h)) else { return upright }
        let area = Double(w * h)
        let width = CGFloat((area * ratio).squareRoot()), height = CGFloat((area / ratio).squareRoot())
        let scaled = source.transformed(by: CGAffineTransform(scaleX: width / w, y: height / h))
        guard let cg = context.createCGImage(scaled, from: scaled.extent) else { return upright }
        return UIImage(cgImage: cg)
    }

    static func cut(_ image: UIImage, corners: [[Double]]?) -> UIImage {
        guard let corners, corners.count == 4, let source = CIImage(image: image) else { return image }
        let w = source.extent.width, h = source.extent.height
        func point(_ p: [Double]) -> CGPoint { CGPoint(x: p[0] * w, y: (1 - p[1]) * h) }
        let straighten = CIFilter.perspectiveCorrection()
        straighten.inputImage = source
        straighten.topLeft = point(corners[0])
        straighten.topRight = point(corners[1])
        straighten.bottomRight = point(corners[2])
        straighten.bottomLeft = point(corners[3])
        guard let out = straighten.outputImage, let cg = context.createCGImage(out, from: out.extent) else { return image }
        return UIImage(cgImage: cg)
    }
}

extension OwnDescription {
    /// Without spaces at the ends.
    var trimmed: OwnDescription {
        var out = self
        let paths: [WritableKeyPath<OwnDescription, String>] = [\.title, \.artist, \.dateText, \.medium, \.description, \.hangs, \.origin]
        for path in paths {
            out[keyPath: path] = out[keyPath: path].trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return out
    }
}
