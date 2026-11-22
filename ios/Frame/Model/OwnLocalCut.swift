import CoreGraphics
import Foundation
import ImageIO
import UIKit
import Vision

/// His own work found in his photograph on the phone, with no Claude
/// (Mateusz 2026-11-21 20:44 UTC: „kadrowanie moich własnych dzieł na
/// pewno chce robić na iPhone, bez Opus”): the museum photographs'
/// painting model (`MuseumCrop`), its work's corners whatever its doubt,
/// and its frame where it found one. Where it takes nearly the whole
/// photograph for the work (a canvas with no frame on a light wall, in
/// three of his 27) it says nothing, and what the camera followed
/// (Vision, `OwnScanView.work`) is the start, as before Opus answered.
/// Of his 27 works the two together came within 5% of what he kept in 17.
enum OwnLocalCut {
    /// The work's corners and its frame's (0–1 across and down the
    /// photograph upright, as on the server).
    struct Found: Sendable {
        var work: [[Double]]
        var surround: [[Double]]?
    }

    /// So much of the photograph and more taken for the work is no answer.
    static let nearlyAll = 0.85

    /// The photograph's file (the camera's, any size) or, without one, its
    /// picture drawn upright (`OwnWorkFlow.upright`).
    static func find(file: Data?, picture: UIImage) async -> Found? {
        await Task.detached(priority: .userInitiated) { () -> Found? in
            guard let image = file.flatMap(small) ?? picture.cgImage,
                  let photo = try? MuseumCrop.pixels(of: image),
                  let asked = try? MuseumCrop.ask(photo, kind: 0),
                  let found = try? MuseumCrop.find(photo, logits: asked.logits, sure: asked.sure),
                  let work = found.work, area(work) < nearlyAll
            else { return nil }
            return Found(work: work, surround: found.surround ?? frame(in: image, around: work))
        }.value
    }

    /// A frame's area to its work's: less is the work's own edge or a
    /// slip of the model, more is a wall, a door, the photograph.
    static let frameArea = 1.04 ... 3.0
    /// How far (0–1 of the photograph) a work's corner may stand outside
    /// a frame found around it.
    static let slack = 0.01

    /// Where the model saw no frame around the work (Mateusz 2026-11-22:
    /// „Dlaczego gdy dodaję własne dzieło to kadrowane jest tylko dzieło a
    /// rama obrazu nie?”; it was trained on museum photographs, where
    /// there is rarely one, and found 4–5 of his 15): the rectangles
    /// the phone sees in the photograph (Vision), the least of those
    /// around the work.
    static func frame(in image: CGImage, around work: [[Double]]) -> [[Double]]? {
        let request = VNDetectRectanglesRequest()
        request.maximumObservations = 16
        request.minimumSize = 0.2
        request.minimumAspectRatio = 0.1
        request.maximumAspectRatio = 1
        request.quadratureTolerance = 25
        request.minimumConfidence = 0.4
        guard (try? VNImageRequestHandler(cgImage: image).perform([request])) != nil else { return nil }
        // Vision's corners go up from the bottom; ours down from the top.
        let seen = (request.results ?? []).map { r in
            [r.topLeft, r.topRight, r.bottomRight, r.bottomLeft].map { [Double($0.x), 1 - Double($0.y)] }
        }
        return frame(of: seen, around: work)
    }

    /// Of the rectangles seen, the least that holds the work and is a
    /// frame's size around it (`frameArea`).
    static func frame(of seen: [[[Double]]], around work: [[Double]]) -> [[Double]]? {
        let inner = area(work)
        guard inner > 0 else { return nil }
        return seen
            .filter { q in
                q.count == 4 && frameArea.contains(area(q) / inner)
                    && work.allSatisfy { holds(q, $0) }
            }
            .min { area($0) < area($1) }
    }

    /// Whether the point is within the quadrilateral (corners in order
    /// around it), or no further out than `slack`.
    static func holds(_ q: [[Double]], _ p: [Double]) -> Bool {
        guard q.count == 4 else { return false }
        // Which way round the corners go: inside is on that side of each.
        var twice = 0.0
        for i in 0 ..< 4 {
            let a = q[i], b = q[(i + 1) % 4]
            twice += a[0] * b[1] - b[0] * a[1]
        }
        guard twice != 0 else { return false }
        let way: Double = twice > 0 ? 1 : -1
        for i in 0 ..< 4 {
            let a = q[i], b = q[(i + 1) % 4]
            let dx = b[0] - a[0], dy = b[1] - a[1]
            let length = (dx * dx + dy * dy).squareRoot()
            guard length > 0 else { return false }
            // How far in from this side (0–1 of the photograph).
            let inward = way * (dx * (p[1] - a[1]) - dy * (p[0] - a[0])) / length
            if inward < -slack { return false }
        }
        return true
    }

    /// The file upright and no longer than the model looks (`photoSide`),
    /// never drawn whole (48 MP).
    private static func small(_ file: Data) -> CGImage? {
        guard let source = CGImageSourceCreateWithData(file as CFData, nil) else { return nil }
        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: MuseumCrop.photoSide,
        ]
        return CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary)
    }

    /// Of the photograph (0–1).
    static func area(_ q: [[Double]]) -> Double {
        guard q.count == 4 else { return 0 }
        var twice = 0.0
        for i in 0 ..< 4 {
            let a = q[i], b = q[(i + 1) % 4]
            twice += a[0] * b[1] - b[0] * a[1]
        }
        return abs(twice) / 2
    }
}
