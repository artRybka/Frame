import CoreGraphics
import Foundation
import ImageIO
import UIKit

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
            return Found(work: work, surround: found.surround)
        }.value
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
