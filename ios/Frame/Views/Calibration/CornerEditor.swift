import SwiftUI
import UIKit
import Vision

/// The palette chart's patches (server/src/frame_server/imaging/testchart.py
/// `palette_patches`) as fractions of the panel, and the middle part of each
/// that the server samples (`calibrate.INSET`).
enum ChartGeometry {
    static let patches: [CGRect] = (0 ..< 6).map { index in
        let width: CGFloat = 2560, height: CGFloat = 1440, margin: CGFloat = 200, gap: CGFloat = 60
        let patchWidth = ((width - 2 * margin - 2 * gap) / 3).rounded(.down)
        let patchHeight = ((height - 2 * margin - gap) / 2).rounded(.down)
        let x = margin + CGFloat(index % 3) * (patchWidth + gap)
        let y = margin + CGFloat(index / 3) * (patchHeight + gap)
        return CGRect(x: x / width, y: y / height, width: patchWidth / width, height: patchHeight / height)
    }

    static let sampled: [CGRect] = patches.map { $0.insetBy(dx: $0.width * 0.25, dy: $0.height * 0.25) }
}

/// Maps the unit square (the panel) onto the quadrilateral of `corners`
/// (TL, TR, BR, BL): the same perspective transform the server undoes.
struct QuadMapping {
    private let a, b, c, d, e, f, g, h: CGFloat

    init?(corners q: [CGPoint]) {
        guard q.count == 4 else { return nil }
        let dx1 = q[1].x - q[2].x, dx2 = q[3].x - q[2].x, dx3 = q[0].x - q[1].x + q[2].x - q[3].x
        let dy1 = q[1].y - q[2].y, dy2 = q[3].y - q[2].y, dy3 = q[0].y - q[1].y + q[2].y - q[3].y
        let det = dx1 * dy2 - dx2 * dy1
        guard abs(det) > 1e-9 else { return nil }
        g = (dx3 * dy2 - dx2 * dy3) / det
        h = (dx1 * dy3 - dx3 * dy1) / det
        a = q[1].x - q[0].x + g * q[1].x
        b = q[3].x - q[0].x + h * q[3].x
        c = q[0].x
        d = q[1].y - q[0].y + g * q[1].y
        e = q[3].y - q[0].y + h * q[3].y
        f = q[0].y
    }

    func callAsFunction(_ p: CGPoint) -> CGPoint {
        let w = g * p.x + h * p.y + 1
        return CGPoint(x: (a * p.x + b * p.y + c) / w, y: (d * p.x + e * p.y + f) / w)
    }
}

/// Getting the photo ready: upright, not too big, the panel's corners guessed.
enum CalibrationPhoto {
    static var sample: UIImage? {
        Bundle.main.url(forResource: "DemoChartPhoto", withExtension: "jpg")
            .flatMap { UIImage(contentsOfFile: $0.path) }
    }

    /// Upright and at most `maxPixel` on the long side, as JPEG. The colour
    /// profile stays embedded; the server converts it to sRGB.
    static func prepare(_ image: UIImage, maxPixel: CGFloat = 2400) -> (image: UIImage, data: Data)? {
        let scale = min(1, maxPixel / max(image.size.width, image.size.height))
        let size = CGSize(width: (image.size.width * scale).rounded(), height: (image.size.height * scale).rounded())
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let upright = UIGraphicsImageRenderer(size: size, format: format).image { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
        guard let data = upright.jpegData(compressionQuality: 0.9) else { return nil }
        return (upright, data)
    }

    /// The largest rectangle Vision finds: usually the panel (or its bezel,
    /// close enough to start from).
    static func detectCorners(in image: UIImage) async -> [CGPoint]? {
        guard let cgImage = image.cgImage else { return nil }
        return await Task.detached(priority: .userInitiated) { () -> [CGPoint]? in
            let request = VNDetectRectanglesRequest()
            request.minimumAspectRatio = 0.3
            request.maximumAspectRatio = 1
            request.minimumSize = 0.3
            request.quadratureTolerance = 25
            request.maximumObservations = 4
            try? VNImageRequestHandler(cgImage: cgImage, orientation: .up).perform([request])
            let area = { (o: VNRectangleObservation) in o.boundingBox.width * o.boundingBox.height }
            guard let best = request.results?.max(by: { area($0) < area($1) }) else { return nil }
            // Vision's origin is bottom-left.
            return [best.topLeft, best.topRight, best.bottomRight, best.bottomLeft]
                .map { CGPoint(x: $0.x, y: 1 - $0.y) }
        }.value
    }
}

/// The photo with four handles for the panel's corners. The magenta boxes
/// show where each ink will be measured, so a good fit is easy to see.
struct CornerEditor: View {
    let image: UIImage
    @Binding var corners: [CGPoint]
    @State private var active: Int?
    @State private var start = CGPoint.zero

    static let defaultCorners = [
        CGPoint(x: 0.15, y: 0.2), CGPoint(x: 0.85, y: 0.2),
        CGPoint(x: 0.85, y: 0.8), CGPoint(x: 0.15, y: 0.8),
    ]
    private static let names = ["Lewy górny", "Prawy górny", "Prawy dolny", "Lewy dolny"]

    var body: some View {
        GeometryReader { geo in
            let size = geo.size
            ZStack(alignment: .topLeading) {
                Image(uiImage: image)
                    .resizable()
                    .frame(width: size.width, height: size.height)
                guides(size)
                ForEach(0 ..< 4, id: \.self) { handle($0, size) }
                if let active {
                    loupe(at: point(corners[active], size), size: size)
                }
            }
        }
        .aspectRatio(image.size.width / max(image.size.height, 1), contentMode: .fit)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private func point(_ p: CGPoint, _ size: CGSize) -> CGPoint {
        CGPoint(x: p.x * size.width, y: p.y * size.height)
    }

    private func guides(_ size: CGSize) -> some View {
        let map = QuadMapping(corners: corners)
        return ZStack {
            Path { path in
                path.addLines(corners.map { point($0, size) })
                path.closeSubpath()
            }
            .stroke(.white.opacity(0.9), style: StrokeStyle(lineWidth: 1.5, dash: [6, 4]))
            if let map {
                Path { path in
                    for rect in ChartGeometry.sampled {
                        let quad = [
                            CGPoint(x: rect.minX, y: rect.minY), CGPoint(x: rect.maxX, y: rect.minY),
                            CGPoint(x: rect.maxX, y: rect.maxY), CGPoint(x: rect.minX, y: rect.maxY),
                        ]
                        path.addLines(quad.map { point(map($0), size) })
                        path.closeSubpath()
                    }
                }
                .stroke(Color(red: 1, green: 0.1, blue: 0.9), lineWidth: 2)
            }
        }
        .allowsHitTesting(false)
    }

    private func handle(_ index: Int, _ size: CGSize) -> some View {
        Circle()
            .strokeBorder(.white, lineWidth: 3)
            .background(Circle().fill(Theme.accent.opacity(active == index ? 0.45 : 0.25)))
            .frame(width: 30, height: 30)
            .shadow(color: .black.opacity(0.45), radius: 3)
            .frame(width: 50, height: 50)
            .contentShape(Circle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { value in
                        if active != index {
                            active = index
                            start = corners[index]
                        }
                        corners[index] = CGPoint(
                            x: min(max(start.x + value.translation.width / size.width, 0), 1),
                            y: min(max(start.y + value.translation.height / size.height, 0), 1)
                        )
                    }
                    .onEnded { _ in active = nil }
            )
            .position(point(corners[index], size))
            .accessibilityLabel("\(Self.names[index]) narożnik")
            .sensoryFeedback(.selection, trigger: active == index)
    }

    /// Magnified view above the finger, so the corner can be placed exactly.
    private func loupe(at p: CGPoint, size: CGSize) -> some View {
        let zoom: CGFloat = 3, diameter: CGFloat = 112
        return Image(uiImage: image)
            .resizable()
            .frame(width: size.width * zoom, height: size.height * zoom)
            .offset(x: diameter / 2 - p.x * zoom, y: diameter / 2 - p.y * zoom)
            .frame(width: diameter, height: diameter, alignment: .topLeading)
            .clipShape(Circle())
            .overlay(Circle().strokeBorder(.white, lineWidth: 3))
            .overlay(Image(systemName: "plus").font(.system(size: 20, weight: .light)).foregroundStyle(.white))
            .shadow(color: .black.opacity(0.35), radius: 8, y: 4)
            .position(
                x: min(max(p.x, diameter / 2), size.width - diameter / 2),
                y: p.y > diameter * 1.2 ? p.y - diameter * 0.8 : p.y + diameter * 0.8
            )
            .allowsHitTesting(false)
    }
}
