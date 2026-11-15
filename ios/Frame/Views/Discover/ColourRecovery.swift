import CoreImage
import CoreImage.CIFilterBuiltins
import SwiftUI

/// The colours a work has lost, simulated as a preview on its card
/// (Mateusz 2026-11-15, of works „zgaszone, ściemniałe, zbrązowiałe czy
/// stonowane pod werniksem”: a simulation of their colours recovered;
/// „Koncepcja suwaka - super”; works on paper „mogłaby odżółcać papier”;
/// and, of the trials on thirty real conservations: „Zbudować bez modelu”).
///
/// Oil and tempera: an aged varnish is a yellow filter, one number says how
/// thick. The server reads the picture once (the strength to propose, how
/// light the result gets at every strength); the sum itself is done here,
/// in linear light, while the owner moves the strength: every pixel is
/// the work's own. Works on paper: the server sends the sheet de-yellowed.
///
/// A preview only: nothing of the work changes, neither its colours under
/// "Kolor i światło" and in Szukaj, nor its study, nor what the frame shows.
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
        case .water, .dry, .burin, .pen, .pencil, .woodblock, .litho, .wash, .handColoured, .woodcut: return "paper"
        case .screen, .offset, .photo: return nil
        }
    }

    static func kind(_ view: RecoveryView?) -> Kind? {
        switch view?.kind ?? "" {
        case "varnish": return Kind.varnish
        case "paper": return Kind.paper
        default: return nil
        }
    }

    /// The lightest of the result at `strength`, before it is brought into
    /// range: between the strengths the server read it at.
    static func top(_ view: RecoveryView, strength: Double) -> Double {
        guard view.steps.count == view.tops.count, let first = view.steps.first, let last = view.steps.last,
              view.steps.count > 1
        else { return 0 }
        if strength <= first { return view.tops[0] }
        if strength >= last { return view.tops[view.tops.count - 1] }
        let after = view.steps.firstIndex { $0 >= strength } ?? view.steps.count - 1
        let before = max(after - 1, 0)
        let span = view.steps[after] - view.steps[before]
        let t = span > 0 ? (strength - view.steps[before]) / span : 0
        return view.tops[before] + (view.tops[after] - view.tops[before]) * t
    }

    /// What red, green and blue (linear light) are multiplied by at
    /// `strength`: the varnish taken off, then the whole brought back so
    /// its lights stay in range (the server's `recovery.gains`).
    static func gains(_ view: RecoveryView, strength: Double) -> [Double] {
        let lightest = top(view, strength: strength)
        let scale = lightest > view.top ? view.top / lightest : 1
        return (0..<3).map { exp(strength * (view.alpha.count == 3 ? view.alpha[$0] : 0)) * scale }
    }

    /// The strengths the picture is drawn at: a slider's every point would
    /// be a picture of its own.
    static func snapped(_ strength: Double) -> Double {
        (strength * 50).rounded() / 50
    }

    private static let context = CIContext(options: [.cacheIntermediates: false])

    /// `source` with each channel multiplied in linear light (Core Image's
    /// own working space), as sRGB again.
    static func render(_ source: CGImage, gains: [Double]) -> CGImage? {
        guard gains.count == 3, let space = CGColorSpace(name: CGColorSpace.sRGB) else { return nil }
        let filter = CIFilter.colorMatrix()
        filter.inputImage = CIImage(cgImage: source)
        filter.rVector = CIVector(x: gains[0], y: 0, z: 0, w: 0)
        filter.gVector = CIVector(x: 0, y: gains[1], z: 0, w: 0)
        filter.bVector = CIVector(x: 0, y: 0, z: gains[2], w: 0)
        filter.aVector = CIVector(x: 0, y: 0, z: 0, w: 1)
        guard let output = filter.outputImage else { return nil }
        return context.createCGImage(output, from: output.extent, format: .RGBA8, colorSpace: space)
    }

    /// The picture without a varnish of `strength`.
    static func image(_ image: UIImage, view: RecoveryView, strength: Double) async -> UIImage? {
        guard let cg = image.cgImage else { return nil }
        let factors = gains(view, strength: strength)
        let scale = image.scale
        let orientation = image.imageOrientation
        guard let out = await Task.detached(priority: .userInitiated, operation: { render(cg, gains: factors) }).value
        else { return nil }
        return UIImage(cgImage: out, scale: scale, orientation: orientation)
    }

    // MARK: Words

    static func menuTitle(_ kind: Kind) -> String {
        kind == .varnish ? "Symulacja odzyskania barw" : "Odżółć papier"
    }

    static func menuNote(_ kind: Kind) -> String {
        kind == .varnish ? "Bez pożółkłego werniksu" : "Jak wyglądał świeży arkusz"
    }

    static func afterLabel(_ kind: Kind) -> String {
        kind == .varnish ? "Bez werniksu" : "Papier odżółcony"
    }

    static func note(_ kind: Kind) -> String {
        kind == .varnish
            ? "Symulacja barw bez pożółkłego werniksu. Rachunek, nie konserwacja. Siłę ustawiasz sam, kreska pokazuje propozycję."
            : "Arkusz odżółcony rachunkiem. Kreska i barwy z oryginału. Przesuń, żeby porównać."
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

/// The recovered picture over the work's own on its card, wiped by a
/// divider: left of it the work as it is today, right of it the simulation.
/// Only the handle is dragged, so the page still scrolls over the picture.
struct RecoveryWipe: View {
    /// The simulation, the size and shape of the picture under it; nil
    /// while it is made.
    let after: UIImage?
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
                if let after {
                    Image(uiImage: after)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(width: width, height: proxy.size.height)
                        .mask(alignment: .leading) {
                            Rectangle().padding(.leading, x)
                        }
                        .transition(.opacity)
                }
                HStack(alignment: .top) {
                    tag("Dziś").opacity(x > 64 ? 1 : 0)
                    Spacer(minLength: 0)
                    tag(ColourRecovery.afterLabel(kind)).opacity(width - x > 110 ? 1 : 0)
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
                    .accessibilityLabel("Porównanie: dziś i symulacja")
                    .accessibilityValue("\(Int((1 - split) * 100)) procent symulacji")
                    .accessibilityAdjustableAction { direction in
                        let step = direction == .increment ? -0.1 : 0.1
                        split = min(max(split + step, 0.04), 0.96)
                    }
                if after == nil {
                    LoadingBadge(text: kind == .varnish ? "Liczę barwy…" : "Odżółcam arkusz…")
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

/// The strength of the varnish taken off, under the picture: a narrow strip
/// from weaker to stronger with a tick where the calculation proposes.
struct RecoveryStrength: View {
    @Binding var strength: Double
    let proposed: Double
    let most: Double
    @State private var grabbed: Double?

    private static let knob: CGFloat = 22

    /// Where a strength is along the strip: the knob's middle.
    private func place(_ value: Double, _ run: CGFloat) -> CGFloat {
        Self.knob / 2 + run * CGFloat(min(max(value / max(most, 0.01), 0), 1))
    }

    var body: some View {
        VStack(spacing: 4) {
            GeometryReader { proxy in
                let run = max(proxy.size.width - Self.knob, 1)
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Theme.hairline)
                        .frame(height: 4)
                        .padding(.horizontal, Self.knob / 2)
                    Capsule()
                        .fill(Theme.inkSoft)
                        .frame(width: max(place(strength, run) - Self.knob / 2, 0), height: 4)
                        .padding(.leading, Self.knob / 2)
                    // The proposal's tick, through the track.
                    Rectangle()
                        .fill(Theme.ink)
                        .frame(width: 2, height: 14)
                        .offset(x: place(proposed, run) - 1)
                    Circle()
                        .fill(.white)
                        .frame(width: Self.knob, height: Self.knob)
                        .shadow(color: .black.opacity(0.3), radius: 3, y: 1)
                        .offset(x: place(strength, run) - Self.knob / 2)
                }
                .frame(height: proxy.size.height)
                .contentShape(Rectangle())
                .gesture(
                    DragGesture(minimumDistance: 0)
                        .onChanged { drag in
                            // The knob follows from where it was; a touch
                            // on the track elsewhere brings it there.
                            let start = grabbed ?? (abs(drag.startLocation.x - place(strength, run)) <= Self.knob
                                ? strength
                                : Double((drag.startLocation.x - Self.knob / 2) / run) * most)
                            grabbed = start
                            let moved = start + Double(drag.translation.width / run) * most
                            // The proposal holds the knob a little as it passes.
                            let near = abs(moved - proposed) < most * 0.02
                            strength = near ? proposed : min(max(moved, 0), most)
                        }
                        .onEnded { _ in grabbed = nil }
                )
            }
            .frame(height: 30)
            HStack {
                Text("słabiej")
                Spacer()
                Button("propozycja") {
                    withAnimation(.easeOut(duration: 0.2)) { strength = proposed }
                }
                .buttonStyle(.plain)
                .underline(strength != proposed)
                Spacer()
                Text("mocniej")
            }
            .font(.caption2)
            .foregroundStyle(Theme.inkSoft)
        }
        .sensoryFeedback(.selection, trigger: strength == proposed) { _, now in now }
        .accessibilityElement()
        .accessibilityLabel("Siła symulacji")
        .accessibilityValue("\(Int(strength / max(most, 0.01) * 100)) procent")
        .accessibilityAdjustableAction { direction in
            let step = most / 16 * (direction == .increment ? 1 : -1)
            strength = min(max(strength + step, 0), most)
        }
    }
}
