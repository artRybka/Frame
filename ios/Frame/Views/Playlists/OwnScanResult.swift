import SwiftUI

/// The page after the scan of three, when the side photographs took
/// reflections off the work (stage 4 of the scan's design, Mateusz
/// 2026-11-16: "Może dzięki wykonaniu trzech zdjęć jesteśmy w stanie
/// uzyskać też lepszą jakość reprodukcji?"): the scan made of the three
/// and the photograph from the front as it was taken, one in the other's
/// place under a switch, so that he sees what the scan gave and chooses
/// which goes on. It comes after "Kadr", both cut as he set the corners:
/// the server makes the scan while he sets them (2026-11-16 16:44 UTC).
///
/// There was a handle to draw across the two until 2026-11-16 21:48 UTC
/// (Mateusz: "zrezygnujmy z pionowego suwaka. Wystarczy switch „jedno
/// zdjęcie / skan” - po wyborze płynnie pokazuje się wybrana opcja.
/// Domyślnie skan. Zmieńmy nazwę na „na wprost / inteligentne”").
struct OwnScanResult: View {
    /// The first photograph as the camera took it.
    let before: UIImage
    /// The same with the reflections taken off.
    let after: UIImage
    /// Back to the camera, for the three anew.
    let again: () -> Void
    /// On, with the scan or (`true`) with the one photograph from the
    /// front as it was taken.
    let next: (_ single: Bool) -> Void
    /// "Dalej" was pressed and the server is at it (a new photograph of a
    /// work he has: cut and kept).
    var busy = false
    /// Which of the two goes on (Mateusz 2026-11-16 19:00 UTC: "daj
    /// możliwość wyboru zdjęcia bez korekty usunięcia odbić, tj. „Jedno
    /// zdjęcie” - bywa że to lepsze rozwiązanie").
    @State private var single = false

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            VStack(spacing: 0) {
                HStack {
                    Button(action: again) {
                        Image(systemName: "chevron.backward")
                            .font(.body.weight(.semibold))
                            .frame(width: 44, height: 44)
                    }
                    .buttonStyle(.glass)
                    .buttonBorderShape(.circle)
                    .accessibilityLabel("Wróć do aparatu")
                    Spacer()
                    Text("Skan gotowy")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                        .glassEffect()
                    Spacer()
                    Color.clear.frame(width: 44, height: 44)
                }
                .padding(.horizontal, Theme.gutter)
                .padding(.top, 4)
                Spacer(minLength: 12)
                OwnScanPicture(before: before, after: after, single: single)
                    .padding(.horizontal, 12)
                Text(single ? "Zdjęcie na wprost, bez zmian" : "Odbicia usunięte z trzech zdjęć")
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.white.opacity(0.9))
                    .contentTransition(.opacity)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, Theme.gutter)
                    .padding(.top, 14)
                Picker("Co zachować", selection: $single.animation(.easeInOut(duration: OwnScanPicture.turn))) {
                    Text("Na wprost").tag(true)
                    Text("Inteligentne").tag(false)
                }
                .pickerStyle(.segmented)
                .frame(maxWidth: 300)
                .padding(.horizontal, Theme.gutter)
                .padding(.top, 14)
                .disabled(busy)
                Spacer(minLength: 12)
                HStack(spacing: 12) {
                    Button("Powtórz", action: again)
                        .buttonStyle(.glass)
                        .controlSize(.large)
                    Button {
                        next(single)
                    } label: {
                        // The glass is light on this dark page.
                        HStack(spacing: 8) {
                            if busy { ProgressView().controlSize(.small).tint(.black) }
                            Text("Dalej").foregroundStyle(.black)
                        }
                    }
                    .buttonStyle(.glassProminent)
                    .tint(.white)
                    .controlSize(.large)
                }
                .disabled(busy)
                .padding(.bottom, 20)
            }
        }
        .environment(\.colorScheme, .dark)  // as the camera before it
    }
}

/// The scan, or the photograph from the front in its place: the same
/// view of the work, so the one comes up through the other where they
/// differ and nothing else moves.
struct OwnScanPicture: View {
    let before: UIImage
    let after: UIImage
    /// The photograph from the front is the one shown.
    let single: Bool

    /// How long the one takes to come up through the other (seconds).
    static let turn = 0.35

    var body: some View {
        let shape = after.size.height > 0 ? after.size.width / after.size.height : 1
        // The scan lies under, whole; the photograph comes up over it.
        Color.clear
            .overlay { Image(uiImage: after).resizable().scaledToFill() }
            .overlay { Image(uiImage: before).resizable().scaledToFill().opacity(single ? 1 : 0) }
            .aspectRatio(shape, contentMode: .fit)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(single ? "Zdjęcie na wprost" : "Skan z trzech zdjęć")
    }
}
