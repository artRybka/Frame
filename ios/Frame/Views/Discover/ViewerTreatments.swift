import SwiftUI
import UIKit

/// What was done to a work's picture that the full-screen viewer can show
/// it without: its colours corrected ("Korekta barw", `ColourRecovery`)
/// and its picture drawn again ("Restauracja dzieła", the restorer).
///
/// Mateusz 2026-11-16: "Dodajmy natomiast w podglądzie pełnego ekranu …
/// kółka z ikonką poprawy kolorystyki i restauracji. Kliknięcie/odkliknięcie
/// pokazuje podgląd z i bez korekt/poprawy. Widoczne są tylko gdy wykonano
/// powyższe zabiegi." So the card says it by the marks at the title alone,
/// and the comparison lives here, under the cross.
enum Treatment: String, CaseIterable, Hashable, Sendable {
    /// In the order of the buttons, top down (the menu's order).
    case colours, restored

    /// What was done to `item`'s picture shown now, in the buttons' order.
    static func done(on item: Item) -> [Treatment] {
        allCases.filter { $0.isDone(on: item) }
    }

    func isDone(on item: Item) -> Bool {
        switch self {
        case .colours: item.cleanedShown != nil
        case .restored: item.sharper?.isRestored == true
        }
    }

    /// The picture with `off` left off, as the server makes it; nil with
    /// nothing left off (the work's own original is that).
    static func ref(_ item: Item, off: Set<Treatment>) -> ImageRef? {
        guard !off.isEmpty else { return nil }
        return .treated(
            item.id, restored: !off.contains(.restored), cleaned: !off.contains(.colours),
            version: item.pictureVersion
        )
    }

    /// Spoken, and the viewer's caption: what the picture is now.
    var name: String {
        switch self {
        case .colours: "Korekta barw"
        case .restored: LowRes.restoredName
        }
    }

    /// The caption's line while some are left off: "Przed korektą barw",
    /// "Przed restauracją dzieła", or both.
    static func before(_ off: Set<Treatment>, kind: ColourRecovery.Kind?) -> String? {
        switch (off.contains(.colours), off.contains(.restored)) {
        case (true, true): "Przed korektą barw i restauracją dzieła"
        case (true, false): kind == .paper ? "Przed odżółceniem papieru" : "Przed zdjęciem werniksu"
        case (false, true): "Przed restauracją dzieła"
        case (false, false): nil
        }
    }

    /// The demo has no server to keep the pictures before: the colours
    /// as if under an aged varnish, the drawing as a small photograph.
    static func demo(_ picture: UIImage, off: Set<Treatment>) -> UIImage {
        var shown = picture
        if off.contains(.colours) { shown = ColourRecovery.underVarnish(shown) }
        if off.contains(.restored) {
            let size = CGSize(width: max(1, shown.size.width / 5), height: max(1, shown.size.height / 5))
            let format = UIGraphicsImageRendererFormat()
            format.scale = 1
            let small = UIGraphicsImageRenderer(size: size, format: format).image { _ in
                shown.draw(in: CGRect(origin: .zero, size: size))
            }
            shown = small
        }
        return shown
    }
}

/// One of the viewer's round buttons under the cross, as the cross is:
/// the treatment's mark, struck through while the picture is shown without
/// it; a spinner while that picture comes.
struct TreatmentButton: View {
    let treatment: Treatment
    /// The picture is shown with it.
    let on: Bool
    let loading: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            ZStack {
                if loading {
                    ProgressView().tint(.white).controlSize(.small)
                } else {
                    mark
                        .opacity(on ? 1 : 0.55)
                        .overlay {
                            if !on {
                                Capsule()
                                    .fill(.white)
                                    .frame(width: 2, height: 26)
                                    .rotationEffect(.degrees(-45))
                                    .shadow(color: .black.opacity(0.5), radius: 0.5)
                                    .transition(.scale.combined(with: .opacity))
                            }
                        }
                }
            }
            .foregroundStyle(.white)
            .frame(width: 40, height: 40)
            .background(.black.opacity(0.5), in: Circle())
            .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(treatment.name)
        .accessibilityValue(on ? "widoczna" : "ukryta")
        .accessibilityAddTraits(.isToggle)
        .accessibilityHint(Text("Pokazuje dzieło z nią albo bez niej"))
    }

    @ViewBuilder
    private var mark: some View {
        switch treatment {
        case .colours:
            CleanedMark.image
                .resizable()
                .scaledToFit()
                .frame(width: 15, height: 18)
        case .restored:
            Image(systemName: LowRes.restoredSymbol)
                .font(.system(size: 17, weight: .semibold))
        }
    }
}
