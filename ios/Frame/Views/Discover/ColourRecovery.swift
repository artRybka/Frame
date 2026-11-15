import CoreImage.CIFilterBuiltins
import SwiftUI

/// "Korekta barw": a work shown with the colours time took given back by
/// calculation, its aged varnish taken off or its sheet de-yellowed.
///
/// Mateusz 2026-11-15, of works „zgaszone, ściemniałe, zbrązowiałe czy
/// stonowane pod werniksem”: first a preview on the card with a slider
/// (1.145.155); then, 18:39: „To działa naprawdę fajnie. Z ściągania
/// werniksu usuwamy suwak. Zostawiamy tylko poziom propozycji. Wybranie w
/// menu podmienia na wersje z odżółconym papierem / ściągniętym werniksem
/// … Jeżeli wersja podmieniona na skorygowaną to wyliczamy kolory i pasek
/// z wersji po korekcie”; the names, 18:52: „Korekta barw”.
///
/// So the menu's entry asks the server for the work cleaned
/// (`Backend.clean`, `Item.cleaned`): the picture everywhere, the frame's
/// too, its colours and colour bar measured on it. The same entry gives
/// it up. The card says what was done in a line under the picture, and
/// that line opens the comparison with the picture as it came
/// (`RecoveryWipe`). No model is asked.
enum ColourRecovery {
    enum Kind: Equatable {
        case varnish, paper
    }

    /// How the server is told the work is made: in oil or tempera, on paper
    /// in a medium that lets the sheet through, or one that covers it; nil
    /// for what has nothing to recover here (photographs, posters, objects).
    static func made(_ style: PaintStyle?) -> String? {
        guard let style else { return nil }
        switch style {
        case .oil: return "oil"
        case .pastel, .gouache: return "opaque"
        case .water, .dry, .burin, .pen, .pencil, .woodblock, .litho, .wash, .handColoured, .woodcut, .grain, .aquatint, .waterPencil,
             .waterPen, .toned, .heightened: return "paper"
        case .screen, .offset, .photo: return nil
        }
    }

    /// "varnish" or "paper" as the server names them; nil for anything else.
    static func kind(named name: String?) -> Kind? {
        switch name ?? "" {
        case "varnish": return Kind.varnish
        case "paper": return Kind.paper
        default: return nil
        }
    }

    /// What the server offers for a work shown as it came.
    static func kind(_ view: RecoveryView?) -> Kind? { kind(named: view?.kind) }

    /// How a work shown cleaned is cleaned.
    static func kind(_ cleaned: Cleaned?) -> Kind? { kind(named: cleaned?.kind) }

    // MARK: Words

    /// The menu's entry: the correction, or the way back while it is on.
    static func menuTitle(_ kind: Kind, on: Bool) -> String {
        switch (kind, on) {
        case (.varnish, false): return "Zdejmij werniks"
        case (.paper, false): return "Odżółć papier"
        case (.varnish, true): return "Przywróć werniks"
        case (.paper, true): return "Przywróć ton papieru"
        }
    }

    static func menuNote(_ kind: Kind, on: Bool) -> String {
        if on { return "Obraz taki, jak przyszedł z muzeum" }
        return kind == .varnish ? "Barwy bez pożółkłego werniksu" : "Arkusz jak dobrze zachowany"
    }

    /// On the picture while the server makes it again.
    static func working(_ kind: Kind, on: Bool) -> String {
        if on { return kind == .varnish ? "Przywracam werniks…" : "Przywracam ton papieru…" }
        return kind == .varnish ? "Zdejmuję werniks…" : "Odżółcam arkusz…"
    }

    static func done(_ kind: Kind, on: Bool) -> String {
        if on { return kind == .varnish ? "Przywrócono werniks" : "Przywrócono ton papieru" }
        return kind == .varnish ? "Werniks zdjęty" : "Papier odżółcony"
    }

    /// The comparison's two sides.
    static let beforeLabel = "Przed korektą"
    static func afterLabel(_ kind: Kind) -> String {
        kind == .varnish ? "Bez werniksu" : "Papier odżółcony"
    }

    /// The line under the picture of a work shown cleaned.
    static func note(_ kind: Kind) -> String {
        kind == .varnish
            ? "Barwy bez pożółkłego werniksu. Rachunek, nie konserwacja."
            : "Papier odżółcony rachunkiem. Kreska i barwy z oryginału."
    }

    // MARK: The demo

    /// The demo and its screenshots have no server to keep the picture as
    /// it came: the comparison's "before" is the picture as if under an
    /// aged varnish (the server's `ALPHA` at 0.5).
    static func underVarnish(_ picture: UIImage) -> UIImage {
        guard let source = picture.cgImage else { return picture }
        let filter = CIFilter.colorMatrix()
        filter.inputImage = CIImage(cgImage: source)
        filter.rVector = CIVector(x: 0.93, y: 0, z: 0, w: 0)
        filter.gVector = CIVector(x: 0, y: 0.84, z: 0, w: 0)
        filter.bVector = CIVector(x: 0, y: 0, z: 0.61, w: 0)
        guard let output = filter.outputImage,
              let drawn = CIContext().createCGImage(output, from: output.extent)
        else { return picture }
        return UIImage(cgImage: drawn, scale: picture.scale, orientation: picture.imageOrientation)
    }

    // MARK: Answers kept

    /// What the server said of a work's picture, so a card opened again
    /// does not ask again.
    @MainActor private static var known: [String: RecoveryView] = [:]

    @MainActor static func cached(_ key: String) -> RecoveryView? { known[key] }

    @MainActor static func keep(_ view: RecoveryView, for key: String) {
        if known.count > 400 { known.removeAll() }
        known[key] = view
    }
}

/// The picture as it came over the cleaned one on the card, wiped by a
/// divider: left of it the work before the correction, right of it the
/// work as it is shown. Only the handle is dragged, so the page still
/// scrolls over the picture.
struct RecoveryWipe: View {
    /// The picture before the correction, the size and shape of the one
    /// under it; nil while it is had.
    let before: UIImage?
    let kind: ColourRecovery.Kind
    /// Where the divider is, as a share of the width.
    @Binding var split: Double
    /// Where the divider was when the finger came down.
    @State private var grabbed: Double?

    static let handle: CGFloat = 36

    var body: some View {
        GeometryReader { proxy in
            let width = proxy.size.width
            let x = width * split
            ZStack(alignment: .topLeading) {
                if let before {
                    Image(uiImage: before)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(width: width, height: proxy.size.height)
                        .mask(alignment: .leading) {
                            Rectangle().frame(width: max(x, 0))
                        }
                        .transition(.opacity)
                }
                HStack(alignment: .top) {
                    tag(ColourRecovery.beforeLabel).opacity(x > 120 ? 1 : 0)
                    Spacer(minLength: 0)
                    tag(ColourRecovery.afterLabel(kind)).opacity(width - x > 130 ? 1 : 0)
                }
                .padding(8)
                .allowsHitTesting(false)
                Rectangle()
                    .fill(.white)
                    .frame(width: 2, height: proxy.size.height)
                    .shadow(color: .black.opacity(0.35), radius: 2)
                    .offset(x: x - 1)
                    .allowsHitTesting(false)
                Image(systemName: "chevron.left.chevron.right")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(.black.opacity(0.75))
                    .frame(width: Self.handle, height: Self.handle)
                    .background(.white, in: Circle())
                    .shadow(color: .black.opacity(0.3), radius: 4, y: 1)
                    // A finger's size, whatever the circle's.
                    .frame(width: 52, height: 64)
                    .contentShape(Rectangle())
                    .offset(x: x - 26, y: proxy.size.height / 2 - 32)
                    .highPriorityGesture(
                        DragGesture(minimumDistance: 0, coordinateSpace: .global)
                            .onChanged { drag in
                                let from = grabbed ?? split
                                grabbed = from
                                split = min(max(from + drag.translation.width / max(width, 1), 0.04), 0.96)
                            }
                            .onEnded { _ in grabbed = nil }
                    )
                    .accessibilityElement()
                    .accessibilityLabel("Porównanie: przed korektą i po niej")
                    .accessibilityValue("\(Int(split * 100)) procent obrazu przed korektą")
                    .accessibilityAdjustableAction { direction in
                        let step = direction == .increment ? 0.1 : -0.1
                        split = min(max(split + step, 0.04), 0.96)
                    }
                if before == nil {
                    LoadingBadge(text: "Wczytuję obraz przed korektą…")
                        .frame(width: width, height: proxy.size.height)
                }
            }
        }
    }

    private func tag(_ text: String) -> some View {
        Text(text)
            .font(.caption2.weight(.semibold))
            .foregroundStyle(.white)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(.black.opacity(0.45), in: Capsule())
    }
}
