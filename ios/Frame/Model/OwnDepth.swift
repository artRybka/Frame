import Foundation
import ImageIO
import simd

/// The distance to everything in the first photograph of a work, from the
/// LiDAR (iPhone Pro), and the size of the work it gives (Mateusz
/// 2026-11-16: "pobierać jego szacowany wymiar"). The wall is fitted with a
/// plane from the depth inside the work's corners; each corner's ray meets
/// it, and the sides between them are the work's width and height.
struct OwnDepth: Sendable {
    /// The depth map, in the sensor's own turn (landscape), metres along the lens.
    let width: Int
    let height: Int
    let values: [Float]
    /// The lens, in the map's pixels.
    let fx: Double
    let fy: Double
    let cx: Double
    let cy: Double
    /// How the photograph was turned to stand upright.
    let orientation: CGImagePropertyOrientation

    struct Size: Equatable, Sendable {
        var heightCm: Double
        var widthCm: Double
    }

    /// An upright photograph's point (0–1 across and down) on the map.
    func sensor(_ point: [Double]) -> (x: Double, y: Double) {
        let u = point[0], v = point[1]
        let (x, y): (Double, Double)
        switch orientation {
        case .right: (x, y) = (v, 1 - u)  // the phone upright
        case .left: (x, y) = (1 - v, u)
        case .down: (x, y) = (1 - u, 1 - v)
        default: (x, y) = (u, v)
        }
        return (x * Double(width), y * Double(height))
    }

    private func ray(_ pixel: (x: Double, y: Double)) -> SIMD3<Double> {
        SIMD3((pixel.x - cx) / fx, (pixel.y - cy) / fy, 1)
    }

    private func depth(at pixel: (x: Double, y: Double)) -> Double? {
        let x = Int(pixel.x), y = Int(pixel.y)
        guard x >= 0, y >= 0, x < width, y < height else { return nil }
        let z = Double(values[y * width + x])
        return z.isFinite && z > 0.05 && z < 20 ? z : nil
    }

    /// The work's height and width in centimetres between `corners` (top
    /// left, top right, bottom right, bottom left, 0–1 on the upright
    /// photograph); nil when the depth there makes no flat rectangle.
    func size(_ corners: [[Double]]) -> Size? {
        guard corners.count == 4, values.count == width * height, fx > 0, fy > 0 else { return nil }
        // The depth inside the work, away from its edges (a frame, the wall).
        var points: [SIMD3<Double>] = []
        let steps = 14
        for i in 0 ... steps {
            for j in 0 ... steps {
                let s = 0.15 + 0.7 * Double(i) / Double(steps), t = 0.15 + 0.7 * Double(j) / Double(steps)
                let top = Self.mix(corners[0], corners[1], s), bottom = Self.mix(corners[3], corners[2], s)
                let pixel = sensor(Self.mix(top, bottom, t))
                if let z = depth(at: pixel) { points.append(ray(pixel) * z) }
            }
        }
        guard var plane = Self.plane(points) else { return nil }
        // Once more without what lies off it (a reflection, the frame's edge).
        let near = points.filter { abs($0.z - plane.z(at: $0)) < 0.03 }
        guard near.count >= points.count / 2, let refit = Self.plane(near) else { return nil }
        plane = refit

        var ends: [SIMD3<Double>] = []
        for corner in corners {
            let r = ray(sensor(corner))
            let along = 1 - plane.a * r.x - plane.b * r.y
            guard along > 1e-3 else { return nil }
            let t = plane.c / along
            guard t > 0.1, t < 20 else { return nil }
            ends.append(r * t)
        }
        func side(_ a: Int, _ b: Int) -> Double { simd_length(ends[a] - ends[b]) * 100 }
        let top = side(0, 1), right = side(1, 2), bottom = side(2, 3), left = side(3, 0)
        // Opposite sides as long as each other, or it is no rectangle on the wall.
        guard abs(top - bottom) / max(top, bottom) < 0.15, abs(left - right) / max(left, right) < 0.15 else { return nil }
        let width = (top + bottom) / 2, height = (left + right) / 2
        guard (3 ... 600).contains(width), (3 ... 600).contains(height) else { return nil }
        return Size(heightCm: Self.round(height), widthCm: Self.round(width))
    }

    /// Whole centimetres, halves below 20 cm.
    static func round(_ cm: Double) -> Double {
        cm < 20 ? (cm * 2).rounded() / 2 : cm.rounded()
    }

    private static func mix(_ a: [Double], _ b: [Double], _ t: Double) -> [Double] {
        [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
    }

    /// z = a·x + b·y + c, by least squares.
    struct Plane {
        var a: Double
        var b: Double
        var c: Double
        func z(at p: SIMD3<Double>) -> Double { a * p.x + b * p.y + c }
    }

    static func plane(_ points: [SIMD3<Double>]) -> Plane? {
        guard points.count >= 20 else { return nil }
        var sxx = 0.0, sxy = 0.0, sx = 0.0, syy = 0.0, sy = 0.0, n = 0.0, sxz = 0.0, syz = 0.0, sz = 0.0
        for p in points {
            sxx += p.x * p.x; sxy += p.x * p.y; sx += p.x
            syy += p.y * p.y; sy += p.y; n += 1
            sxz += p.x * p.z; syz += p.y * p.z; sz += p.z
        }
        // [sxx sxy sx; sxy syy sy; sx sy n] · [a b c] = [sxz syz sz], by Cramer's rule.
        func det(_ m: [[Double]]) -> Double {
            m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
        }
        let m = [[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, n]]
        let d = det(m)
        guard abs(d) > 1e-12 else { return nil }
        let r = [sxz, syz, sz]
        func with(_ column: Int) -> [[Double]] {
            m.enumerated().map { row, values in values.enumerated().map { $0.offset == column ? r[row] : $0.element } }
        }
        return Plane(a: det(with(0)) / d, b: det(with(1)) / d, c: det(with(2)) / d)
    }
}
