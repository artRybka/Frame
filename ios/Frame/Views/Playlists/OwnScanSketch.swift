import CoreImage
import CoreImage.CIFilterBuiltins
import SwiftUI

/// The scan's camera as the screenshots show it (the simulator has no
/// camera): the demo's wall photograph, turned as the wall shows from the
/// side, under the camera's own overlay and words. `-screen own-scan
/// -scanLook front | ready | far | near | lost | side | match | right |
/// result` ("result": the page after the scan, `OwnScanResult`), with
/// `-scanGuide frame` the helper frame in place of the track, with
/// `-scanHeld left` the phone on its side.
struct OwnScanSketch: View {
    let close: () -> Void
    let name = UserDefaults.standard.string(forKey: "scanLook") ?? "side"
    /// The way to the side photographs as the helper frame, not the track.
    let framed = UserDefaults.standard.string(forKey: "scanGuide") == "frame"
    /// The phone held with its top to the left: what is said over the
    /// picture turns (the scene's wall stays as it is).
    let quarter = UserDefaults.standard.string(forKey: "scanHeld") == "left" ? 1 : 0

    private var front: [CGPoint] { DemoOwn.outer.map { CGPoint(x: $0[0], y: $0[1]) } }

    /// Where the phone stands in this look, and where it should (degrees).
    private var stands: Double {
        switch name {
        case "side": -13
        case "match": -29
        case "right": 12
        default: 0
        }
    }

    private var target: Double? {
        switch name {
        case "side", "match": -OwnScanView.side
        case "right": OwnScanView.side
        default: nil
        }
    }

    /// How large the wall shows: the phone too far from it, or too near.
    private var zoom: Double {
        switch name {
        case "far": 0.5
        case "near": 1.8
        default: 1
        }
    }

    private var look: OwnScanLook {
        let live = OwnScanView.seen(front, from: stands)
            .map { CGPoint(x: 0.5 + ($0.x - 0.5) * zoom, y: 0.5 + ($0.y - 0.5) * zoom) }
        var look = OwnScanLook(number: target == nil ? 1 : (name == "right" ? 3 : 2))
        look.manual = name == "lost"
        look.quarter = quarter
        if let target {
            look.helper = framed ? helper : nil
            look.angle = stands
            look.advice = OwnScanView.side(target: target, angle: stands)
        } else {
            look.live = name == "lost" ? nil : live
            // The demo's work hangs a little askew: its outline is what "from the front" is here.
            look.advice = name == "ready" ? .hold : name == "lost" ? .lost : OwnScanView.first(live)
            if look.advice == .hold, name == "front" { look.advice = .straight }
        }
        return look
    }

    /// The helper frame: the work from where the next photograph is taken.
    private var helper: [CGPoint]? {
        target.map { OwnScanView.fitted(OwnScanView.seen(front, from: $0)) }
    }

    /// The work of the first photograph in the helper frame.
    private var ghost: UIImage? {
        guard framed, let helper, let photo = DemoOwn.photo() else { return nil }
        return OwnScanGhost.picture(of: photo, corners: front, onto: helper)
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
            Text("Zdjęcie \(look.number) z 3")
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
            }
            OwnScanOverlay(look: look, ghost: ghost, holding: holding)
        }
        .aspectRatio(3 / 4, contentMode: .fit)
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .padding(.horizontal, 8)
    }

    /// Where to stand; the shutter only when the work cannot be found.
    private var bottom: some View {
        ZStack {
            if look.manual {
                OwnShutter {}
                StandPlan(taken: look.number - 1)
                    .frame(width: 74, height: 52)
                    .frame(maxWidth: .infinity, alignment: .trailing)
            } else if look.number == 1 || framed {
                StandPlan(taken: look.number - 1)
                    .frame(width: 116, height: 78)
            }
        }
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
            OwnScanResult(before: before, after: after, again: close, next: {})
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
