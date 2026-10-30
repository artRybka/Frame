import SwiftUI
import UIKit
import Vision

/// Where a picture's subject is, so a box of another shape crops around it
/// instead of through its middle: the faces in it, else what draws the eye
/// (Vision's attention saliency), else the middle. Worked out once per
/// picture and remembered.
actor SubjectFocus {
    static let shared = SubjectFocus()

    private var cache: [String: UnitPoint] = [:]

    /// Unit point in the picture, origin top-left.
    func point(in image: UIImage, key: String) async -> UnitPoint {
        if let cached = cache[key] { return cached }
        // Detached: Vision runs beside this actor, not on it.
        let point = await Task.detached(priority: .utility) { Self.find(in: image) }.value
        cache[key] = point
        return point
    }

    private static func find(in image: UIImage) -> UnitPoint {
        guard let cgImage = image.cgImage else { return .center }
        let faces = VNDetectFaceRectanglesRequest()
        let attention = VNGenerateAttentionBasedSaliencyImageRequest()
        let handler = VNImageRequestHandler(cgImage: cgImage, orientation: .up)
        try? handler.perform([faces, attention])

        // The main faces: a crowd's small ones would pull to an empty middle.
        let faceBoxes = (faces.results ?? []).filter { $0.confidence > 0.5 }.map(\.boundingBox)
        let largest = faceBoxes.map(\.area).max() ?? 0
        if let box = union(faceBoxes.filter { $0.area >= largest * 0.4 }) {
            return center(of: box)
        }
        let salient = (attention.results?.first?.salientObjects ?? []).filter { $0.confidence > 0.3 }
        if let box = union(salient.map(\.boundingBox)) {
            return center(of: box)
        }
        return .center
    }

    private static func union(_ boxes: [CGRect]) -> CGRect? {
        guard let first = boxes.first else { return nil }
        return boxes.dropFirst().reduce(first) { $0.union($1) }
    }

    /// Vision's boxes are normalised with the origin bottom-left.
    private static func center(of box: CGRect) -> UnitPoint {
        UnitPoint(x: box.midX, y: 1 - box.midY)
    }
}

private extension CGRect {
    var area: CGFloat { width * height }
}

/// A picture filling its box, shifted so `focus` sits as near the middle as
/// the picture's edges allow.
struct FocusedFill: View {
    let image: UIImage
    let focus: UnitPoint

    var body: some View {
        GeometryReader { geo in
            let box = geo.size
            let scale = max(box.width / image.size.width, box.height / image.size.height)
            let width = image.size.width * scale
            let height = image.size.height * scale
            Image(uiImage: image)
                .resizable()
                .frame(width: width, height: height)
                .offset(
                    x: Self.shift(focus.x, length: width, box: box.width),
                    y: Self.shift(focus.y, length: height, box: box.height)
                )
        }
    }

    /// From the leading edge: centred on the focus, never past an edge.
    static func shift(_ focus: CGFloat, length: CGFloat, box: CGFloat) -> CGFloat {
        min(0, max(box - length, box / 2 - focus * length))
    }
}
