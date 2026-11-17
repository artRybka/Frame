import CoreImage
import CoreImage.CIFilterBuiltins
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
///
/// The switch is there after every scan of three, also where the side
/// photographs took nothing off or the work is no flat one; there the
/// scan is made all the same and the photograph from the front is the one
/// chosen at first (Mateusz 2026-11-17 22:43 UTC: "wybór pomiędzy obrazem
/// składanym (inteligentnym) a z pojedynczego zdjęcia - zawsze go dawaj,
/// a w sytuacji gdzie podejrzewasz płaskorzeźbę albo dzieło które wymaga
/// pojedynczego zdjęcia ustawiaj je jako domyślne").
///
/// With no colour chart beside the work it comes after every "Kadr",
/// scan or no scan, with the white balance his to set under the picture
/// (Mateusz 2026-11-17 16:27 UTC: "Gdy przy robieniu zdjęcia dzieła nie
/// zostanie wykryta karta koloru dodaj suwak regulacji balansu bieli":
/// his works hang under warm lamps, and nothing else says what is white
/// there). The picture is shown in the balance set; the server keeps the
/// work's photograph in it (`OwnBalance`). The slider says nothing in
/// words (`OwnBalanceSlider`).
struct OwnScanResult: View {
    /// The first photograph as the camera took it.
    let before: UIImage
    /// The same with the reflections taken off.
    let after: UIImage
    /// The side photographs were laid over the first: he chooses which of
    /// the two goes on. Not so, there is the one photograph.
    var scanned = true
    /// The three do not show one flat work (a relief, a mirror in it):
    /// the photograph from the front is the one chosen at first.
    var doubt = false
    /// The side photographs took nothing off: the two are the same.
    var nothing = false
    /// The white balance he sets (-1 cooler … 1 warmer; 0, as taken);
    /// nil where a colour chart set the colours, and there is no slider.
    var balance: Binding<Double>?
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
    @State private var picked: Bool?
    /// The two small, for the slider to draw them anew as it moves, and
    /// as they are at the balance set.
    @State private var small: (before: UIImage, after: UIImage)?
    @State private var tinted: (before: UIImage, after: UIImage)?

    private var chosen: Double { balance?.wrappedValue ?? 0 }

    /// The photograph from the front goes on: his choice, and before it
    /// what the scan is thought of.
    private var single: Bool { picked ?? doubt }

    /// What the picture shown is, under it.
    private var said: String {
        if single { return doubt ? "Na wprost, bo dzieło nie wygląda na płaskie" : "Zdjęcie na wprost, bez zmian" }
        if doubt { return "Z trzech zdjęć, choć dzieło nie wygląda na płaskie" }
        return nothing ? "Trzy zdjęcia nie pokazały odbić" : "Odbicia usunięte z trzech zdjęć"
    }

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
                    Text(scanned ? "Skan gotowy" : "Zdjęcie gotowe")
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
                OwnScanPicture(
                    before: tinted?.before ?? before, after: tinted?.after ?? after,
                    single: scanned && single
                )
                .padding(.horizontal, 12)
                if scanned {
                    Text(bound: said)
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(.white.opacity(0.9))
                        .contentTransition(.opacity)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, Theme.gutter)
                        .padding(.top, 14)
                    Picker("Co zachować", selection: Binding(get: { single }, set: { picked = $0 }).animation(.easeInOut(duration: OwnScanPicture.turn))) {
                        Text("Na wprost").tag(true)
                        Text("Inteligentne").tag(false)
                    }
                    .pickerStyle(.segmented)
                    .frame(maxWidth: 300)
                    .padding(.horizontal, Theme.gutter)
                    .padding(.top, 14)
                    .disabled(busy)
                }
                if let balance {
                    OwnBalanceSlider(balance: balance)
                        .frame(maxWidth: 340)
                        .padding(.horizontal, Theme.gutter)
                        .padding(.top, scanned ? 10 : 8)
                        .disabled(busy)
                }
                Spacer(minLength: 12)
                HStack(spacing: 12) {
                    Button("Powtórz", action: again)
                        .buttonStyle(.glass)
                        .controlSize(.large)
                    Button {
                        next(scanned && single)
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
        .task {
            guard balance != nil, small == nil else { return }
            small = (OwnBalance.small(before), scanned ? OwnBalance.small(after) : OwnBalance.small(before))
            tint()
        }
        .onChange(of: chosen) { tint() }
    }

    /// The two as they are at the balance set (untouched at none).
    private func tint() {
        guard let small else { return }
        guard chosen != 0 else {
            tinted = nil
            return
        }
        let first = OwnBalance.tinted(small.before, balance: chosen)
        tinted = (first, scanned ? OwnBalance.tinted(small.after, balance: chosen) : first)
    }
}

/// The white balance's slider: a cloud to the left (cooler), the sun to
/// the right (warmer), a round knob between them, and nothing written
/// (Mateusz 2026-11-17 21:32 UTC, of the first one with the system's
/// slider under "Balans bieli · cieplej" and "Wyzeruj": "Gdy suwak jest
/// w punkcie „0” (domyślnym) to stuknij haptyką i delikatnie przyciągnij.
/// Suwak kółko a nie elipsa/zaokrąglony prostokąt. Bez podpowiedzi
/// „ciepłej, etc”. Bez guzika „wyzeruj”. Bez tekstu „balans bieli”.
/// Zamiast sniezynki - chmurka."). The middle, as taken, draws the knob
/// to itself and taps under the finger: that is the way back to none.
struct OwnBalanceSlider: View {
    @Binding var balance: Double

    /// So near the middle (of the way to an end) the knob is drawn to it.
    static let pull = 0.07
    /// The knob across, and the height it is caught in (pt).
    static let knob: CGFloat = 28
    static let reach: CGFloat = 44

    @Environment(\.isEnabled) private var enabled
    /// The balance where the finger came down.
    @State private var from: Double?

    /// The balance with the finger at `raw`: none within the pull of the
    /// middle, else as far as the finger is, no further than the ends.
    static func settled(_ raw: Double) -> Double {
        let at = min(1, max(-1, raw))
        return abs(at) < pull ? 0 : at
    }

    private var said: String {
        if balance == 0 { return "jak na zdjęciu" }
        return balance < 0 ? "chłodniej" : "cieplej"
    }

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "cloud.fill")
                .foregroundStyle(Color(red: 0.72, green: 0.84, blue: 1))
            GeometryReader { geo in
                let room = max(1, geo.size.width - Self.knob)
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(.white.opacity(0.24))
                        .frame(height: 4)
                        .padding(.horizontal, Self.knob / 2 - 2)
                    // The middle, where the photograph is as taken.
                    Capsule()
                        .fill(.white.opacity(0.55))
                        .frame(width: 2, height: 10)
                        .offset(x: geo.size.width / 2 - 1)
                    Circle()
                        .fill(.white)
                        .frame(width: Self.knob, height: Self.knob)
                        .shadow(color: .black.opacity(0.35), radius: 3, y: 1)
                        .offset(x: CGFloat((balance + 1) / 2) * room)
                }
                .frame(width: geo.size.width, height: geo.size.height, alignment: .leading)
                .contentShape(Rectangle())
                .gesture(
                    DragGesture(minimumDistance: 0)
                        .onChanged { drag in
                            let began = from ?? balance
                            from = began
                            let now = Self.settled(began + 2 * Double(drag.translation.width / room))
                            guard now != balance else { return }
                            // Into the middle and out of it the knob goes of itself.
                            if (now == 0) != (balance == 0) {
                                withAnimation(.snappy(duration: 0.14)) { balance = now }
                            } else {
                                balance = now
                            }
                        }
                        .onEnded { _ in from = nil }
                )
            }
            .frame(height: Self.reach)
            Image(systemName: "sun.max.fill")
                .foregroundStyle(Color(red: 1, green: 0.78, blue: 0.42))
        }
        .font(.body)
        .opacity(enabled ? 1 : 0.5)
        .sensoryFeedback(.impact(flexibility: .rigid, intensity: 0.7), trigger: balance == 0) { _, now in now }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Balans bieli")
        .accessibilityValue(said)
        .accessibilityAdjustableAction { way in
            let step = way == .increment ? 0.1 : -0.1
            balance = Self.settled(((balance + step) * 10).rounded() / 10)
        }
    }
}

/// The white balance set by hand, drawn on the phone as the server makes
/// it (`imaging/balance.py`: the two must agree): red and blue light the
/// way a lamp's warmth moves them, green staying, a grey as light as it
/// was.
enum OwnBalance {
    /// Full warmth: red and blue so many times two (in linear light).
    static let warm = (red: 0.72, blue: -1.2)

    private static let context = CIContext(options: [
        .workingColorSpace: CGColorSpace(name: CGColorSpace.linearSRGB) as Any,
    ])

    /// `-scanBalance cool|warm`: the slider as the screenshots have it.
    static var launched: Double {
        switch UserDefaults.standard.string(forKey: "scanBalance") {
        case "cool": -0.45
        case "warm": 0.45
        default: 0
        }
    }

    /// What red, green and blue light are multiplied by.
    static func gains(_ balance: Double) -> (red: Double, green: Double, blue: Double) {
        let at = min(1, max(-1, balance))
        let red = pow(2, warm.red * at), blue = pow(2, warm.blue * at)
        let seen = 0.2126 * red + 0.7152 + 0.0722 * blue
        return (red / seen, 1 / seen, blue / seen)
    }

    /// `image` at `balance`: itself at none.
    static func tinted(_ image: UIImage, balance: Double) -> UIImage {
        guard abs(balance) >= 0.001, let source = CIImage(image: image) else { return image }
        let gain = gains(balance)
        let matrix = CIFilter.colorMatrix()
        matrix.inputImage = source
        matrix.rVector = CIVector(x: gain.red, y: 0, z: 0, w: 0)
        matrix.gVector = CIVector(x: 0, y: gain.green, z: 0, w: 0)
        matrix.bVector = CIVector(x: 0, y: 0, z: gain.blue, w: 0)
        matrix.aVector = CIVector(x: 0, y: 0, z: 0, w: 1)
        guard let out = matrix.outputImage, let cg = context.createCGImage(out, from: source.extent)
        else { return image }
        return UIImage(cgImage: cg, scale: image.scale, orientation: image.imageOrientation)
    }

    /// `image` no longer than `side`, for the slider to draw as it moves.
    static func small(_ image: UIImage, side: CGFloat = 1400) -> UIImage {
        let scale = min(1, side / max(image.size.width, image.size.height, 1))
        guard scale < 1 else { return image }
        let size = CGSize(width: (image.size.width * scale).rounded(), height: (image.size.height * scale).rounded())
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        return UIGraphicsImageRenderer(size: size, format: format).image { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
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
