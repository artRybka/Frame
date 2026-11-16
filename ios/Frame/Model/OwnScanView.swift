import CoreGraphics
import Foundation

/// Where a flat work on the wall shows in the camera's picture when the
/// phone stands off to the side of it, as far away and aiming at its
/// middle (the scan of three, Mateusz 2026-11-16: "pierwsze zdjęcie na
/// wprost, a kolejne pod większym kątem z ramką pomocniczą na ekranie
/// pokazująca gdzie ma się znajdować dzieło"). From the work's outline in
/// the first photograph comes the helper frame for the side ones: the
/// shape that outline takes from 30° to the left and to the right.
enum OwnScanView {
    /// How far to the side the side photographs are taken, in degrees: a
    /// lamp's reflection moves about a third of a metre across the work
    /// from a metre away, while the work's far side is 13 % narrower.
    static let side = 30.0
    /// The side photograph is taken between these (the frame is a guide,
    /// not a gauge).
    static let near = 22.0 ... 38.0
    /// The main camera's focal length in half-widths of the upright picture
    /// (26 mm equivalent: 69° across the sensor's long side).
    static let focal = 1.94

    /// A point of the front view (0–1 across and down a picture `aspect`
    /// wide to high) as seen from `degrees` to the side: negative from
    /// the left, where the work's left side comes nearer and taller.
    /// `centre`: the work's middle in the front view, which the camera
    /// keeps aiming at.
    static func seen(
        _ point: CGPoint, from degrees: Double, centre: CGPoint, aspect: Double = 0.75, focal: Double = OwnScanView.focal
    ) -> CGPoint {
        let turn = degrees * .pi / 180
        // Across and down from the middle, in focal lengths.
        let a = Double(point.x - centre.x) * 2 / focal
        let b = Double(point.y - centre.y) * 2 / aspect / focal
        let depth = max(1 - a * sin(turn), 0.05)
        return CGPoint(
            x: Double(centre.x) + a * cos(turn) / depth * focal / 2,
            y: Double(centre.y) + b / depth * focal * aspect / 2
        )
    }

    /// The outline `corners` (top left, top right, bottom right, bottom
    /// left, 0–1) as seen from `degrees` to the side.
    static func seen(_ corners: [CGPoint], from degrees: Double, aspect: Double = 0.75) -> [CGPoint] {
        guard !corners.isEmpty else { return [] }
        let centre = middle(corners)
        return corners.map { seen($0, from: degrees, centre: centre, aspect: aspect) }
    }

    static func middle(_ corners: [CGPoint]) -> CGPoint {
        let n = CGFloat(max(corners.count, 1))
        return CGPoint(x: corners.map(\.x).reduce(0, +) / n, y: corners.map(\.y).reduce(0, +) / n)
    }

    /// From how far to the side an outline is seen, in degrees (negative:
    /// from the left), by how much taller its left side is than its right:
    /// the opposite of `seen`. `front`: the same outline from the front.
    static func angle(of outline: [CGPoint], front: [CGPoint], aspect: Double = 0.75) -> Double? {
        guard outline.count == 4, front.count == 4 else { return nil }
        func lean(_ q: [CGPoint]) -> Double {
            let left = Double(hypot(q[3].x - q[0].x, q[3].y - q[0].y))
            let right = Double(hypot(q[2].x - q[1].x, q[2].y - q[1].y))
            return right > 0 ? log(left / right) : 0
        }
        let seenLean = lean(outline) - lean(front)
        // The lean grows evenly enough with the angle to look it up.
        var best: (angle: Double, off: Double)?
        for step in -120 ... 120 {
            let degrees = Double(step) / 2
            let off = abs(lean(seen(front, from: degrees, aspect: aspect)) - lean(front) - seenLean)
            if best == nil || off < best!.off { best = (degrees, off) }
        }
        return best?.angle
    }

    /// How well a live outline lies in the helper frame: the largest
    /// distance between their corners, in picture widths.
    static func off(_ outline: [CGPoint], frame: [CGPoint]) -> Double {
        guard outline.count == frame.count, !outline.isEmpty else { return 1 }
        return zip(outline, frame).map { Double(hypot($0.x - $1.x, $0.y - $1.y)) }.max() ?? 1
    }
}
