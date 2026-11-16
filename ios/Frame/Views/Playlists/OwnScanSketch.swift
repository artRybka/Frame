import CoreImage
import CoreImage.CIFilterBuiltins
import SwiftUI

/// The scan's camera as the screenshots show it (the simulator has no
/// camera): the demo's wall photograph, turned as the wall shows from the
/// side, under the camera's own overlay and words. `-screen own-scan2
/// -scanLook front | ready | far | near | lost | side | match | right |
/// result` ("result": a sketch of the page after the scan, not built yet).
struct OwnScanSketch: View {
    let close: () -> Void
    let name = UserDefaults.standard.string(forKey: "scanLook") ?? "side"

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
        look.live = name == "lost" ? nil : live
        look.helper = target.map { OwnScanView.seen(front, from: $0) }
        look.manual = name == "lost"
        if let target {
            look.advice = OwnScanView.side(target: target, angle: stands)
        } else {
            // The demo's work hangs a little askew: its outline is what "from the front" is here.
            look.advice = name == "ready" ? .hold : name == "lost" ? .lost : OwnScanView.first(live)
            if look.advice == .hold, name == "front" { look.advice = .straight }
        }
        return look
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
            OwnScanOverlay(look: look)
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
            } else {
                StandPlan(taken: look.number - 1)
                    .frame(width: 116, height: 78)
            }
        }
        .frame(height: 82)
        .padding(.horizontal, 32)
        .padding(.bottom, 12)
    }

    // MARK: The result

    private var result: some View {
        VStack(spacing: 0) {
            HStack {
                Button(action: close) {
                    Image(systemName: "chevron.backward")
                        .font(.body.weight(.semibold))
                        .frame(width: 44, height: 44)
                }
                .buttonStyle(.glass)
                .buttonBorderShape(.circle)
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
            compare
            VStack(spacing: 4) {
                Text("Odblask usunięty z trzech zdjęć")
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.white.opacity(0.9))
                Text("Przesuń, żeby porównać ze zdjęciem na wprost.")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.55))
            }
            .padding(.top, 14)
            Spacer(minLength: 12)
            HStack(spacing: 12) {
                Button("Powtórz") {}
                    .buttonStyle(.glass)
                    .controlSize(.large)
                Button {} label: {
                    Text("Dalej").foregroundStyle(.black)
                }
                .buttonStyle(.glassProminent)
                .tint(.white)
                .controlSize(.large)
            }
            .padding(.bottom, 20)
        }
    }

    /// The first photograph on the left of the handle, the scan on the right.
    private var compare: some View {
        let before = DemoOwn.photo().map { OwnPicture.cut($0, corners: DemoOwn.work) }
        let after = DemoOwn.photo(glare: 0).map { OwnPicture.cut($0, corners: DemoOwn.work) }
        let shape = after.map { $0.size.width / max($0.size.height, 1) } ?? 1.3
        return GeometryReader { geo in
            let split = geo.size.width * 0.46
            ZStack(alignment: .leading) {
                if let after { Image(uiImage: after).resizable().scaledToFill().frame(width: geo.size.width, height: geo.size.height) }
                if let before {
                    Image(uiImage: before).resizable().scaledToFill()
                        .frame(width: geo.size.width, height: geo.size.height)
                        .mask(alignment: .leading) { Rectangle().frame(width: split) }
                }
                Rectangle().fill(.white).frame(width: 2).offset(x: split - 1)
                Image(systemName: "arrow.left.and.right")
                    .font(.footnote.weight(.bold))
                    .foregroundStyle(.black)
                    .frame(width: 34, height: 34)
                    .background(.white, in: Circle())
                    .shadow(color: .black.opacity(0.4), radius: 4)
                    .offset(x: split - 17)
                tag("Jedno zdjęcie").frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                tag("Skan").frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
            }
        }
        .aspectRatio(shape, contentMode: .fit)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .padding(.horizontal, 12)
    }

    private func tag(_ text: String) -> some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .foregroundStyle(.white)
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background(.black.opacity(0.55), in: Capsule())
            .padding(10)
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
