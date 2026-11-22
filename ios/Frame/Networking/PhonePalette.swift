import CoreGraphics
import Foundation
import ImageIO

/// "Barwy" in "Podobne do" (Mateusz 2026-11-21 23:08: "Liczenie koloru
/// zdjęcia - róbmy na iPhone"): a photograph's colours made on the phone,
/// as the server's `palettes.colours_of` makes them, and sent beside its
/// numbers (`POST /api/looks/photo/numbers`, `palette`). Its masses (the
/// server's `tonal.masses`) from the darkest, then its small colours no
/// mass is, each with its share: rows (L, a, b, share) in OKLab.
/// `PhonePaletteTests` holds it to the server's (`tests/test_palettes.py`
/// holds these numbers to the server's).
enum PhonePalette {
    /// The photograph's longer side, as `colors._grid` reads it.
    static let grid = 128
    /// k-means on (L, 2a, 2b), from pixels taken evenly from the darkest to
    /// the lightest, `rounds` rounds (`palettes.CLUSTERS`, `ROUNDS`).
    static let clusters = 10
    static let rounds = 25
    /// A mass is at least `band` of the picture, `maxMasses` at most
    /// (`tonal.BAND`, `MAX_MASSES`); a small colour this near a mass is it
    /// (`tonal.APART`).
    static let maxMasses = 5
    static let band: Double = 0.13
    static let apart: Double = 0.08
    /// The palette's colours at most, how a coloured one counts more, and
    /// Sinkhorn's softness and steps (`palettes.K`, `EMPHASIS`…): only for
    /// telling two palettes apart in the tests.
    static let most = 8
    static let emphasis: Double = 2.0
    static let chromaFull: Double = 0.10
    static let soft: Double = 0.03
    static let steps = 60

    typealias Lab = SIMD3<Double>

    /// A photograph's colours, or nil when it cannot be read.
    static func colours(_ picture: Data) -> [[Float]]? {
        guard let source = CGImageSourceCreateWithData(picture as CFData, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
        else { return nil }
        return colours(image)
    }

    /// As `colors._grid`: no longer than `grid`, in proportion, in sRGB.
    static func colours(_ image: CGImage) -> [[Float]]? {
        let longer = max(image.width, image.height)
        guard longer > 0 else { return nil }
        let scale = min(1, Double(grid) / Double(longer))
        let width = max(1, Int((Double(image.width) * scale).rounded()))
        let height = max(1, Int((Double(image.height) * scale).rounded()))
        var bytes = [UInt8](repeating: 0, count: width * height * 4)
        let drawn = bytes.withUnsafeMutableBytes { raw -> Bool in
            guard let space = CGColorSpace(name: CGColorSpace.sRGB),
                  let context = CGContext(
                      data: raw.baseAddress, width: width, height: height, bitsPerComponent: 8,
                      bytesPerRow: width * 4, space: space,
                      bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
                  )
            else { return false }
            context.interpolationQuality = .medium
            context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
        guard drawn else { return nil }
        var rgb = [UInt8]()
        rgb.reserveCapacity(width * height * 3)
        for at in 0 ..< width * height {
            rgb += [bytes[at * 4], bytes[at * 4 + 1], bytes[at * 4 + 2]]
        }
        return colours(rgb: rgb)
    }

    /// The colours of 8-bit sRGB pixels (three bytes each).
    static func colours(rgb: [UInt8]) -> [[Float]] {
        let count = rgb.count / 3
        guard count > 0 else { return [] }
        let fine = (0 ..< count).map { oklab(rgb[$0 * 3], rgb[$0 * 3 + 1], rgb[$0 * 3 + 2]) }
        let found = clustered(fine)
        let mains = masses(found)
        let small = found.filter { c, w in
            w < band && mains.map { distance($0.0, c) }.min() ?? 0 >= apart
        }
        return (mains + small).map { c, w in [Float(c.x), Float(c.y), Float(c.z), Float(w)] }
    }

    // MARK: OKLab, as the server's `imaging/color.py`

    private static let linear: [Double] = (0 ..< 256).map { v in
        let x = Double(Float(v) / 255)
        return Double(Float(x <= 0.04045 ? x / 12.92 : pow((x + 0.055) / 1.055, 2.4)))
    }

    static func oklab(_ r: UInt8, _ g: UInt8, _ b: UInt8) -> Lab {
        let (lr, lg, lb) = (linear[Int(r)], linear[Int(g)], linear[Int(b)])
        let l = cbrt(0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb)
        let m = cbrt(0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb)
        let s = cbrt(0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb)
        return Lab(
            0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
        )
    }

    static func chroma(_ c: Lab) -> Double { (c.y * c.y + c.z * c.z).squareRoot() }

    /// `colors._distance`: colour (a, b) counted twice.
    static func distance(_ p: Lab, _ q: Lab) -> Double {
        let d = p - q
        return (d.x * d.x + 4 * (d.y * d.y + d.z * d.z)).squareRoot()
    }

    // MARK: The picture's colours and masses

    /// `palettes._clusters`.
    static func clustered(_ fine: [Lab]) -> [(Lab, Double)] {
        let stretch = Lab(1, 2, 2)
        let weighted = fine.map { $0 * stretch }
        let k = min(clusters, weighted.count)
        let order = weighted.indices.sorted { a, b in
            weighted[a].x != weighted[b].x ? weighted[a].x < weighted[b].x : a < b
        }
        var centres = (0 ..< k).map { j -> Lab in
            let at = k > 1 ? Int(Double(j) * Double(weighted.count - 1) / Double(k - 1)) : 0
            return weighted[order[at]]
        }
        var owner = [Int](repeating: 0, count: weighted.count)
        for _ in 0 ..< rounds {
            for (n, p) in weighted.enumerated() {
                var best = 0
                var least = Double.infinity
                for (j, c) in centres.enumerated() {
                    let d = c - p
                    let far = (d * d).sum()
                    if far < least {
                        least = far
                        best = j
                    }
                }
                owner[n] = best
            }
            var sums = [Lab](repeating: .zero, count: k)
            var counts = [Int](repeating: 0, count: k)
            for (n, p) in weighted.enumerated() {
                sums[owner[n]] += p
                counts[owner[n]] += 1
            }
            for j in 0 ..< k where counts[j] > 0 {
                centres[j] = sums[j] / Double(counts[j])
            }
        }
        var out: [(Lab, Double)] = []
        for j in 0 ..< k {
            let pixels = fine.indices.filter { owner[$0] == j }.map { fine[$0] }
            guard !pixels.isEmpty else { continue }
            let chromas = pixels.map(chroma).sorted()
            let half = chromas.count / 2
            let median = chromas.count % 2 == 1 ? chromas[half] : (chromas[half - 1] + chromas[half]) / 2
            let clean = pixels.filter { chroma($0) >= median }
            var core = clean.reduce(Lab.zero, +) / Double(clean.count)
            core.x = pixels.reduce(0) { $0 + $1.x } / Double(pixels.count)
            out.append((core, Double(pixels.count) / Double(fine.count)))
        }
        return out
    }

    /// `tonal.masses`: merged into at most `maxMasses`, each at least
    /// `band`, from the darkest; a merged mass keeps the cleaner chroma.
    static func masses(_ found: [(Lab, Double)]) -> [(Lab, Double)] {
        var m = found
        func merge(_ i: Int, _ j: Int) {
            let (a, wa) = m[i]
            let (b, wb) = m[j]
            let w = wa + wb
            var c = (a * wa + b * wb) / w
            let keep = max(chroma(a), chroma(b))
            let now = chroma(c)
            if now > 1e-6 {
                let k = min(keep / now, 1.3)
                c.y *= k
                c.z *= k
            }
            m[i] = (c, w)
            m.remove(at: j)
        }
        while m.count > 1 {
            let small = m.indices.filter { m[$0].1 < band }
            if small.isEmpty, m.count <= maxMasses { break }
            var i = 0
            var j = 1
            if !small.isEmpty {
                i = m.indices.min { m[$0].1 < m[$1].1 }!
                j = m.indices.filter { $0 != i }.min { distance(m[i].0, m[$0].0) < distance(m[i].0, m[$1].0) }!
            } else {
                var least = Double.infinity
                for a in m.indices {
                    for b in (a + 1) ..< m.count where distance(m[a].0, m[b].0) < least {
                        least = distance(m[a].0, m[b].0)
                        (i, j) = (a, b)
                    }
                }
            }
            merge(min(i, j), max(i, j))
        }
        return m.sorted { $0.0.x < $1.0.x }
    }

    // MARK: Two palettes apart (`palettes.palette`, `distances`)

    /// At most `most` colours, the largest, each weighted by how coloured it is.
    static func palette(_ rows: [[Float]]) -> [(Lab, Double)] {
        let largest = rows.enumerated().sorted { a, b in
            a.element[3] != b.element[3] ? a.element[3] > b.element[3] : a.offset < b.offset
        }.prefix(most).map(\.element)
        let weighted = largest.map { r -> (Lab, Double) in
            let c = Lab(Double(r[0]), Double(r[1]), Double(r[2]))
            let w = max(Double(r[3]), 1e-4) * (1 + emphasis * min(chroma(c) / chromaFull, 1))
            return (c, w)
        }
        let total = weighted.reduce(0) { $0 + $1.1 }
        return weighted.map { ($0.0, $0.1 / total) }
    }

    /// Sinkhorn's earth mover's distance between two palettes.
    static func far(_ p: [(Lab, Double)], _ q: [(Lab, Double)]) -> Double {
        let cost = p.map { a in q.map { b in distance(a.0, b.0) } }
        let kern = cost.map { $0.map { exp(-$0 / soft) } }
        var u = [Double](repeating: 1, count: p.count)
        var v = [Double](repeating: 1, count: q.count)
        for _ in 0 ..< steps {
            for i in p.indices {
                let s = q.indices.reduce(0) { $0 + kern[i][$1] * v[$1] }
                u[i] = p[i].1 / max(s, 1e-300)
            }
            for j in q.indices {
                let s = p.indices.reduce(0) { $0 + kern[$1][j] * u[$1] }
                v[j] = q[j].1 / max(s, 1e-300)
            }
        }
        var total = 0.0
        for i in p.indices {
            for j in q.indices {
                total += u[i] * kern[i][j] * v[j] * cost[i][j]
            }
        }
        return total
    }
}
