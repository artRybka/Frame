import SwiftUI

/// The page after the scan of three, when the side photographs took
/// reflections off the work (stage 4 of the scan's design, Mateusz
/// 2026-11-16: "Może dzięki wykonaniu trzech zdjęć jesteśmy w stanie
/// uzyskać też lepszą jakość reprodukcji?"): the photograph from the front
/// as it was taken and the scan made of the three, under one handle to
/// draw across, so that he sees what the scan gave before going on. It
/// comes after "Kadr", both cut as he set the corners: the server makes
/// the scan while he sets them (2026-11-16 16:44 UTC).
struct OwnScanResult: View {
    /// The first photograph as the camera took it.
    let before: UIImage
    /// The same with the reflections taken off.
    let after: UIImage
    /// Back to the camera, for the three anew.
    let again: () -> Void
    let next: () -> Void
    /// "Dalej" was pressed and the server is at it (a new photograph of a
    /// work he has: cut and kept).
    var busy = false

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
                OwnScanCompare(before: before, after: after)
                    .padding(.horizontal, 12)
                VStack(spacing: 4) {
                    Text("Odbicia usunięte z trzech zdjęć")
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(.white.opacity(0.9))
                    Text("Przesuń, żeby porównać ze zdjęciem na wprost.")
                        .font(.caption)
                        .foregroundStyle(.white.opacity(0.55))
                }
                .multilineTextAlignment(.center)
                .padding(.horizontal, Theme.gutter)
                .padding(.top, 14)
                Spacer(minLength: 12)
                HStack(spacing: 12) {
                    Button("Powtórz", action: again)
                        .buttonStyle(.glass)
                        .controlSize(.large)
                    Button(action: next) {
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

/// Two pictures of the same view under one handle: the first to its left,
/// the second to its right; a finger anywhere on them draws it across.
struct OwnScanCompare: View {
    let before: UIImage
    let after: UIImage
    /// Where the handle stands, across the picture (0–1).
    @State private var split = 0.5

    /// How far the handle may go, so that it stays in reach.
    static let reach = 0.04 ... 0.96

    /// Where a finger at `x` of a picture `width` wide puts the handle.
    static func split(at x: Double, width: Double) -> Double {
        guard width > 0 else { return 0.5 }
        return min(max(x / width, reach.lowerBound), reach.upperBound)
    }

    var body: some View {
        let shape = after.size.height > 0 ? after.size.width / after.size.height : 1
        GeometryReader { geo in
            let at = geo.size.width * split
            ZStack(alignment: .leading) {
                Image(uiImage: after).resizable().scaledToFill()
                    .frame(width: geo.size.width, height: geo.size.height)
                Image(uiImage: before).resizable().scaledToFill()
                    .frame(width: geo.size.width, height: geo.size.height)
                    .mask(alignment: .leading) { Rectangle().frame(width: at) }
                Rectangle().fill(.white).frame(width: 2).offset(x: at - 1)
                    .shadow(color: .black.opacity(0.4), radius: 2)
                Image(systemName: "arrow.left.and.right")
                    .font(.footnote.weight(.bold))
                    .foregroundStyle(.black)
                    .frame(width: 34, height: 34)
                    .background(.white, in: Circle())
                    .shadow(color: .black.opacity(0.4), radius: 4)
                    .offset(x: at - 17)
                tag("Jedno zdjęcie")
                    .opacity(split > 0.3 ? 1 : 0)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                tag("Skan")
                    .opacity(split < 0.7 ? 1 : 0)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
            }
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { split = Self.split(at: $0.location.x, width: geo.size.width) }
            )
        }
        .aspectRatio(shape, contentMode: .fit)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Porównanie: jedno zdjęcie i skan z trzech")
        .accessibilityValue("\(Int((split * 100).rounded())) procent")
        .accessibilityAdjustableAction { direction in
            let step = direction == .increment ? 0.1 : -0.1
            split = min(max(split + step, Self.reach.lowerBound), Self.reach.upperBound)
        }
    }

    private func tag(_ text: String) -> some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .foregroundStyle(.white)
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background(.black.opacity(0.55), in: Capsule())
            .padding(10)
            .animation(.easeOut(duration: 0.15), value: split > 0.3 && split < 0.7)
    }
}
