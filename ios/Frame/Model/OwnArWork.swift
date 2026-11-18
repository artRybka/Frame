import CoreGraphics
import Foundation
import simd

/// The work pinned in the room after the first photograph of a scan
/// (Mateusz 2026-11-18 08:22 UTC: "A może aparat w AR mógłby dodawać po
/// pierwszym kroku jakieś znaczniki wkoło obrazu? Naniesione na ścianę lub
/// przyklejone do jego ramy? Bo nadal to skanowanie nie jest w 100%
/// intuicyjne"). The phone's AR session knows where the phone is in the
/// room; once the work's four corners are known there, the side
/// photographs need not find the work in the picture any more (an
/// unframed canvas was not found from either side that morning): where
/// its corners are on the screen and from how far to the side the phone
/// looks at it both follow from where the phone stands.
struct OwnArWork: Equatable {
    /// Top left, top right, bottom right, bottom left, in the room (metres).
    let corners: [SIMD3<Float>]
    let centre: SIMD3<Float>
    /// Out of the wall, towards where the phone stood when it was pinned.
    let normal: SIMD3<Float>
    /// Along the work to its right as seen from the front.
    let right: SIMD3<Float>
    /// How far the phone was from the work's middle when it was pinned.
    let distance: Float

    /// The work no smaller and no larger than this across (metres), the
    /// phone no nearer and no farther: anything else was not the work.
    static let sizes: ClosedRange<Float> = 0.04 ... 6
    static let distances: ClosedRange<Float> = 0.15 ... 8

    /// `corners` in the order top left, top right, bottom right, bottom
    /// left as the phone at `eye` saw them.
    init?(corners: [SIMD3<Float>], from eye: SIMD3<Float>) {
        guard corners.count == 4 else { return nil }
        let centre = (corners[0] + corners[1] + corners[2] + corners[3]) / 4
        var normal = simd_cross(corners[2] - corners[0], corners[3] - corners[1])
        guard simd_length(normal) > 1e-6 else { return nil }
        normal = simd_normalize(normal)
        let from = eye - centre
        let distance = simd_length(from)
        guard Self.distances.contains(distance) else { return nil }
        if simd_dot(normal, from) < 0 { normal = -normal }
        // Not seen edge-on: the phone stood before it.
        guard simd_dot(normal, from) / distance > 0.2 else { return nil }
        var right = (corners[1] - corners[0]) + (corners[2] - corners[3])
        right -= simd_dot(right, normal) * normal
        let across = simd_length(right) / 2
        let down = simd_length((corners[3] - corners[0]) + (corners[2] - corners[1])) / 2
        guard Self.sizes.contains(across), Self.sizes.contains(down) else { return nil }
        self.corners = corners
        self.centre = centre
        self.normal = normal
        self.right = simd_normalize(right)
        self.distance = distance
    }

    /// From how far to the side the phone at `eye` looks at the work, in
    /// degrees (negative: from its left), as the scan counts it.
    func angle(from eye: SIMD3<Float>) -> Double {
        let from = eye - centre
        return Double(atan2(simd_dot(from, right), simd_dot(from, normal))) * 180 / .pi
    }

    /// How far the phone at `eye` is from the work, in its distances when
    /// the work was pinned (1: as far).
    func away(from eye: SIMD3<Float>) -> Double {
        Double(simd_length(eye - centre) / distance)
    }

    // MARK: Pinning

    /// How far into the work (from its middle, 1: its corners) the wall
    /// is felt for: a frame's corners stand off the wall, and beside them
    /// is the wall itself.
    static let inset: CGFloat = 0.6
    /// The four places felt lie in one plane to within this (metres).
    static let flat: Float = 0.05

    /// The points of the picture where the wall is felt for under an
    /// outline (its corners drawn towards its middle).
    static func felt(_ outline: [CGPoint]) -> [CGPoint] {
        let m = OwnScanView.middle(outline)
        return outline.map { CGPoint(x: m.x + ($0.x - m.x) * inset, y: m.y + ($0.y - m.y) * inset) }
    }

    /// A point of the upright screen's picture (0–1 across and down) in
    /// the camera's own picture, which lies on its side: across the
    /// sensor's long side and down its short one, as ARKit counts them.
    static func sensor(_ point: CGPoint) -> CGPoint {
        CGPoint(x: point.y, y: 1 - point.x)
    }

    /// The plane through four places felt on the work (in the outline's
    /// order): a point of it and its normal; nil when they are not flat.
    static func plane(through hits: [SIMD3<Float>]) -> (point: SIMD3<Float>, normal: SIMD3<Float>)? {
        guard hits.count == 4 else { return nil }
        let cross = simd_cross(hits[2] - hits[0], hits[3] - hits[1])
        guard simd_length(cross) > 1e-6 else { return nil }
        let normal = simd_normalize(cross)
        let point = (hits[0] + hits[1] + hits[2] + hits[3]) / 4
        guard hits.allSatisfy({ abs(simd_dot($0 - point, normal)) < flat }) else { return nil }
        return (point, normal)
    }

    /// Where the ray from `origin` along `direction` meets the plane; nil
    /// when it runs along it or away from it.
    static func hit(
        origin: SIMD3<Float>, direction: SIMD3<Float>, plane: (point: SIMD3<Float>, normal: SIMD3<Float>)
    ) -> SIMD3<Float>? {
        let along = simd_dot(direction, plane.normal)
        guard abs(along) > 1e-4 else { return nil }
        let far = simd_dot(plane.point - origin, plane.normal) / along
        guard far > 0 else { return nil }
        return origin + direction * far
    }
}

/// What the AR session says of the pinned work in its latest picture.
struct OwnArSight: Equatable {
    /// Where the phone stands, in degrees to the side of the work.
    var angle: Double
    /// How far, in its distances when the work was pinned.
    var away: Double
    /// The work's corners on the upright screen's picture (0–1; they may
    /// lie beyond its edges), nil when the phone looks away from it.
    var outline: [CGPoint]?
}
