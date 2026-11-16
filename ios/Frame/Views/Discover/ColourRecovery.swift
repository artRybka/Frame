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
/// it up. The card says what was done by a mark at the title, and the
/// full-screen viewer shows the work with and without it (`Treatment`;
/// Mateusz 2026-11-16, in place of a line and a comparison under the
/// picture). No model is asked.
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
             .waterPen, .toned, .heightened, .washLit, .washLitChalk, .washToned, .washTonedChalk, .chiaroscuro: return "paper"
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

    // MARK: The demo

    /// The demo and its screenshots have no server to keep the picture as
    /// it came: the viewer's "before" is the picture as if under an aged
    /// varnish (the server's `ALPHA` at 0.5).
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
