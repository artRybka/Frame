import CoreImage
import CoreImage.CIFilterBuiltins
import SwiftUI

/// The scan's camera as the screenshots show it (the simulator has no
/// camera): the demo's wall photograph, turned as the wall shows from the
/// side, under the camera's own overlay and words. `-screen own-scan
/// -scanLook front | ready | far | near | lost | arc | side | match | aim |
/// turned | right | result` ("arc": the first photograph just taken,
/// round the work either way now; "side": on the way to the left, one
/// photograph taken in passing; "match": where the left's is taken;
/// "aim": there with the phone looking past the work; "turned": the
/// phone turned to the left where he was to walk there; "right": the
/// left done, on the way to the right; "result": the page after the
/// scan, `OwnScanResult`), with `-scanHeld left` the phone on its side.
struct OwnScanSketch: View {
    let close: () -> Void
    let name = UserDefaults.standard.string(forKey: "scanLook") ?? "side"
    /// The phone held with its top to the left: what is said over the
    /// picture turns (the scene's wall stays as it is).
    let quarter = UserDefaults.standard.string(forKey: "scanHeld") == "left" ? 1 : 0
    /// The white balance on the page after the scan (`-scanBalance cool|warm`).
    @State private var balance = OwnBalance.launched
    /// `-scanDoubt YES`: the page after the scan of a work that is no flat
    /// one, the photograph from the front chosen at first.
    let doubt = UserDefaults.standard.bool(forKey: "scanDoubt")

    private var front: [CGPoint] { DemoOwn.outer.map { CGPoint(x: $0[0], y: $0[1]) } }

    /// Where the phone stands in this look (degrees to the side).
    private var stands: Double {
        switch name {
        case "side": -13
        case "match", "aim": -29
        case "turned": -7
        case "right": 12
        default: 0
        }
    }

    /// The first photograph is taken in this look: the ones from the sides now.
    private var walking: Bool { ["arc", "side", "match", "aim", "turned", "right"].contains(name) }

    /// From where the side photographs so far were taken in it.
    private var arc: OwnScanArc {
        var taken = OwnScanArc()
        if ["side", "match", "aim", "right"].contains(name) { taken.took(-12.6) }
        if name == "right" { taken.took(-29.4) }
        return taken
    }

    /// How large the wall shows: the phone too far from it, or too near.
    private var zoom: Double {
        switch name {
        case "far": 0.5
        case "near": 1.8
        default: 1
        }
    }

    /// How far the phone looks past the work: the wall shows so much to
    /// the side (of the picture's width).
    private var past: Double { name == "aim" ? 0.17 : name == "side" ? 0.06 : name == "turned" ? 0.52 : 0 }

    private var look: OwnScanLook {
        let live = OwnScanView.seen(front, from: stands)
            .map { CGPoint(x: 0.5 + ($0.x - 0.5) * zoom + past, y: 0.5 + ($0.y - 0.5) * zoom) }
        var look = OwnScanLook(number: walking ? 2 : 1)
        look.manual = name == "lost"
        look.quarter = quarter
        let taken = arc
        look.left = taken.done(left: true)
        look.right = taken.done(left: false)
        look.shots = taken.taken
        if walking, name == "turned" {
            // The work has left the picture: the gyroscope alone counts.
            look.angle = stands
            look.advice = OwnScanView.side(target: taken.target(at: stands) ?? -OwnScanView.side, angle: stands, stray: 22)
        } else if walking {
            // As the camera has it (`OwnCamera.reading`).
            look.angle = stands
            look.live = live
            let fits = OwnScanView.fits(live)
            if let target = taken.target(at: stands) {
                look.advice = OwnScanView.side(
                    target: target, angle: stands, fits: fits, aim: fits ? 0 : OwnScanView.offAim(live)
                )
            } else {
                look.advice = fits ? .either : .farther
            }
        } else {
            look.live = name == "lost" ? nil : live
            // The demo's work hangs a little askew: its outline is what "from the front" is here.
            look.advice = name == "ready" ? .hold : name == "lost" ? .lost : OwnScanView.first(live)
            if look.advice == .hold, name == "front" { look.advice = .straight }
        }
        return look
    }

    /// The ring as it is a moment before the photograph.
    private var holding: Date? {
        look.advice == .hold ? Date.now.addingTimeInterval(-OwnShotRing.time * 0.6) : nil
    }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            if name == "result" {
                result
            } else {
                VStack(spacing: 0) {
                    top
                    Spacer(minLength: 12)
                    viewfinder
                    OwnScanCaption(look: look)
                        .padding(.horizontal, Theme.gutter)
                        .padding(.top, 14)
                    Spacer(minLength: 12)
                    bottom
                }
            }
        }
        .environment(\.colorScheme, .dark)
    }

    private var top: some View {
        HStack {
            Button(action: close) {
                Image(systemName: "chevron.backward")
                    .font(.body.weight(.semibold))
                    .frame(width: 44, height: 44)
            }
            .buttonStyle(.glass)
            .buttonBorderShape(.circle)
            Spacer()
            Text(bound: "Krok \(look.number) z 2")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .glassEffect()
            Spacer()
            if look.number > 1 {
                Button("Pomiń") {}
                    .buttonStyle(.glass)
            } else {
                Color.clear.frame(width: 44, height: 44)
            }
        }
        .padding(.horizontal, Theme.gutter)
        .padding(.top, 4)
    }

    private var viewfinder: some View {
        ZStack {
            Color(red: 0.84, green: 0.80, blue: 0.73)
            if let photo = Self.wall(from: stands) {
                Image(uiImage: photo).resizable().scaledToFill().scaleEffect(zoom)
                    .visualEffect { [past] content, proxy in content.offset(x: proxy.size.width * past) }
            }
            OwnScanOverlay(look: look, holding: holding)
        }
        .aspectRatio(3 / 4, contentMode: .fit)
        // Across the whole screen, square (Mateusz 2026-11-16 16:44 UTC:
        // "Na pełną szerokość ekranu? Może bez wyoblonych narożników?").
        .clipped()
    }

    /// The shutter, only when the work cannot be found.
    private var bottom: some View {
        ZStack {
            if look.manual { OwnShutter {} }
        }
        .frame(maxWidth: .infinity)
        .frame(height: 82)
        .padding(.horizontal, 32)
        .padding(.bottom, 12)
    }

    // MARK: The result

    /// The page after the scan, with the demo's work with and without its glare.
    @ViewBuilder
    private var result: some View {
        if let before = DemoOwn.photo().map({ OwnPicture.cut($0, corners: DemoOwn.work) }),
           let after = DemoOwn.photo(glare: 0).map({ OwnPicture.cut($0, corners: DemoOwn.work) }) {
            OwnScanResult(before: before, after: after, doubt: doubt, balance: $balance, again: close, next: { _ in })
        }
    }

    // MARK: The wall from the side

    private static let context = CIContext()

    /// The demo's wall photograph as the wall shows from `degrees` to the
    /// side (the phone as far from the work and aiming at it).
    private static func wall(from degrees: Double) -> UIImage? {
        guard let photo = DemoOwn.photo(), let source = CIImage(image: photo) else { return nil }
        guard degrees != 0 else { return photo }
        let w = source.extent.width, h = source.extent.height
        let centre = OwnScanView.middle(DemoOwn.outer.map { CGPoint(x: $0[0], y: $0[1]) })
        func point(_ x: Double, _ y: Double) -> CGPoint {
            let p = OwnScanView.seen(CGPoint(x: x, y: y), from: degrees, centre: centre)
            return CGPoint(x: p.x * w, y: (1 - p.y) * h)  // CI's origin is bottom left
        }
        let turn = CIFilter.perspectiveTransform()
        turn.inputImage = source
        turn.topLeft = point(0, 0)
        turn.topRight = point(1, 0)
        turn.bottomRight = point(1, 1)
        turn.bottomLeft = point(0, 1)
        // More of the same wall where the photograph ends.
        let wall = CIImage(color: CIColor(red: 0.84, green: 0.80, blue: 0.73)).cropped(to: source.extent)
        guard let out = turn.outputImage?.composited(over: wall),
              let cg = context.createCGImage(out, from: source.extent)
        else { return photo }
        return UIImage(cgImage: cg)
    }
}
