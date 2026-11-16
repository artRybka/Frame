import CoreImage
import CoreImage.CIFilterBuiltins
import SwiftUI

/// Sketches of the scan of three done anew, for Mateusz to choose from
/// before it is built (2026-11-16: "pierwsze zdjęcie na wprost, a kolejne
/// pod większym kątem z ramką pomocniczą na ekranie pokazująca gdzie ma
/// się znajdować dzieło"; "kropki działają z opóźnieniem i kąt … jest zbyt
/// mały"). No camera here: the demo's wall photograph, turned as the wall
/// shows from the side. `-screen own-scan2 -scanLook front | ready | side
/// | match | right | result`.
struct OwnScanSketch: View {
    let close: () -> Void
    let look = UserDefaults.standard.string(forKey: "scanLook") ?? "side"

    private static let good = Color(red: 0.36, green: 0.86, blue: 0.48)
    private static let wait = Color(red: 1.0, green: 0.80, blue: 0.30)

    private var front: [CGPoint] { DemoOwn.outer.map { CGPoint(x: $0[0], y: $0[1]) } }

    /// Where the phone stands in this sketch, and where it should (degrees).
    private var stands: Double {
        switch look {
        case "side": -13
        case "match": -29
        case "right": 12
        default: 0
        }
    }

    private var target: Double? {
        switch look {
        case "side", "match": -OwnScanView.side
        case "right": OwnScanView.side
        default: nil
        }
    }

    private var number: Int {
        switch look {
        case "side", "match": 2
        case "right": 3
        default: 1
        }
    }

    private var matched: Bool { look == "match" || look == "ready" }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            if look == "result" {
                result
            } else {
                VStack(spacing: 0) {
                    top
                    Spacer(minLength: 12)
                    viewfinder
                    caption
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
            Text("Zdjęcie \(number) z 3")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .glassEffect()
            Spacer()
            if number > 1 {
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
            if let photo = Self.wall(from: stands) {
                Image(uiImage: photo).resizable().scaledToFill()
            } else {
                Color(white: 0.1)
            }
            GeometryReader { geo in
                let live = OwnScanView.seen(front, from: stands)
                if let target {
                    // The helper frame: where the work should lie.
                    let frame = OwnScanView.seen(front, from: target)
                    Quad(corners: frame)
                        .fill(.white.opacity(matched ? 0 : 0.10))
                    Quad(corners: frame)
                        .stroke(matched ? Self.good : .white,
                                style: StrokeStyle(lineWidth: matched ? 4 : 3, lineCap: .round, lineJoin: .round, dash: matched ? [] : [10, 8]))
                        .shadow(color: .black.opacity(0.45), radius: 3)
                    if !matched {
                        // The work as the camera sees it now, and which way to go.
                        Quad(corners: live)
                            .stroke(Self.wait, style: StrokeStyle(lineWidth: 2, lineJoin: .round))
                        Image(systemName: target < stands ? "arrow.left" : "arrow.right")
                            .font(.system(size: 30, weight: .bold))
                            .foregroundStyle(.white)
                            .shadow(color: .black.opacity(0.55), radius: 4)
                            .position(x: geo.size.width * (target < stands ? 0.085 : 0.915), y: geo.size.height * 0.5)
                    }
                } else {
                    Quad(corners: live)
                        .stroke(matched ? Self.good : Self.wait,
                                style: StrokeStyle(lineWidth: matched ? 4 : 2.5, lineJoin: .round))
                        .shadow(color: .black.opacity(0.45), radius: 3)
                }
            }
            if matched {
                Label("Nie ruszaj", systemImage: "camera.aperture")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.black)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(Self.good, in: Capsule())
                    .frame(maxHeight: .infinity, alignment: .bottom)
                    .padding(.bottom, 18)
            }
        }
        .aspectRatio(3 / 4, contentMode: .fit)
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .padding(.horizontal, 8)
    }

    private var caption: some View {
        VStack(spacing: 4) {
            Text(advice)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.white.opacity(0.9))
                .multilineTextAlignment(.center)
            Text(note)
                .font(.caption)
                .foregroundStyle(.white.opacity(0.55))
                .multilineTextAlignment(.center)
        }
    }

    private var advice: String {
        switch look {
        case "front": "Stań na wprost dzieła, całe w kadrze"
        case "ready": "Dobrze. Robię zdjęcie na wprost"
        case "side": "Przejdź w lewo, aż dzieło wypełni ramkę"
        case "match": "Dobrze. Robię zdjęcie z lewej"
        case "right": "Teraz w prawo, aż dzieło wypełni ramkę"
        default: ""
        }
    }

    private var note: String {
        switch look {
        case "front", "ready": "Zdjęcie zrobi się samo, gdy obrys zrobi się zielony."
        default: "Celuj cały czas w dzieło. Zdjęcie zrobi się samo."
        }
    }

    private var bottom: some View {
        HStack {
            StandPlan(taken: number - 1, good: Self.good)
                .frame(width: 74, height: 52)
            Spacer()
            Button {} label: {
                ZStack {
                    Circle().strokeBorder(.white, lineWidth: 4).frame(width: 78, height: 78)
                    Circle().fill(.white).frame(width: 64, height: 64)
                }
            }
            .buttonStyle(.plain)
            Spacer()
            Color.clear.frame(width: 74, height: 52)
        }
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
                Button("Dalej") {}
                    .buttonStyle(.glassProminent)
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

/// An outline through four corners given as fractions of the view.
private struct Quad: Shape {
    let corners: [CGPoint]

    func path(in rect: CGRect) -> Path {
        var path = Path()
        guard let first = corners.first else { return path }
        func point(_ p: CGPoint) -> CGPoint { CGPoint(x: rect.minX + p.x * rect.width, y: rect.minY + p.y * rect.height) }
        path.move(to: point(first))
        for corner in corners.dropFirst() { path.addLine(to: point(corner)) }
        path.closeSubpath()
        return path
    }
}

/// Where to stand, seen from above: the work as a bar at the top, the
/// three places before it; those done are filled, the next one is ringed.
private struct StandPlan: View {
    /// How many photographs are taken (front, left, right in turn).
    let taken: Int
    let good: Color

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width, h = geo.size.height
            let work = CGPoint(x: w / 2, y: 7)
            // Front, left, right: the order they are taken in.
            let places = [CGPoint(x: w / 2, y: h - 9), CGPoint(x: w * 0.14, y: h - 20), CGPoint(x: w * 0.86, y: h - 20)]
            Capsule().fill(.white).frame(width: w * 0.42, height: 4).position(work)
            ForEach(0 ..< 3, id: \.self) { index in
                Path { path in
                    path.move(to: places[index])
                    path.addLine(to: work)
                }
                .stroke(.white.opacity(index == taken ? 0.7 : 0.2), style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
                Circle()
                    .fill(index < taken ? good : .clear)
                    .overlay(Circle().strokeBorder(index < taken ? good : .white.opacity(index == taken ? 1 : 0.4), lineWidth: 2))
                    .frame(width: index == taken ? 16 : 12, height: index == taken ? 16 : 12)
                    .position(places[index])
            }
        }
        .accessibilityHidden(true)
    }
}
