import UIKit

/// Raises the screen to full brightness while a picture is looked at and
/// gives the owner's own brightness back afterwards. iOS itself puts the
/// owner's brightness back when the app leaves the foreground, so a boost
/// that outlives that is raised again on return.
@MainActor
final class ScreenBoost {
    static let shared = ScreenBoost()
    /// Remembered by the full-screen viewer's sun button.
    static let key = "viewer.brighten"
    /// Konfiguracja → Pełny ekran: the sun also lifts the picture's light
    /// parts above the screen's white (`HDRBoost`).
    static let hdrKey = "viewer.hdrBoost"
    /// With the HDR lift on: the sun leaves the screen's brightness alone
    /// and only lifts the picture.
    static let keepKey = "viewer.keepBrightness"

    private var boosted = false
    /// The owner's brightness, kept until the glide back to it ends (a
    /// boost again halfway back must not take the halfway value for it).
    private var own: CGFloat?
    private var ramp: Task<Void, Never>?

    private var screen: UIScreen? {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        return (scenes.first { $0.activationState == .foregroundActive } ?? scenes.first)?.screen
    }

    /// How many times brighter than its white this screen can light HDR
    /// content at best (1 when it cannot: no EDR, Low Power Mode).
    var headroom: CGFloat { screen?.potentialEDRHeadroom ?? 1 }

    func raise() {
        guard !boosted, let screen else { return }
        boosted = true
        if own == nil { own = screen.brightness }
        glide(to: 1)
    }

    func restore() {
        guard boosted, let back = own else { return }
        boosted = false
        glide(to: back) { [weak self] in
            if self?.boosted == false { self?.own = nil }
        }
    }

    /// The app went to the background: iOS restores the brightness itself.
    func forget() {
        ramp?.cancel()
        ramp = nil
        boosted = false
        own = nil
    }

    /// A gentle change over about a third of a second instead of a jump.
    private func glide(to target: CGFloat, then done: @escaping @MainActor () -> Void = {}) {
        ramp?.cancel()
        guard let screen else { return }
        let start = screen.brightness
        ramp = Task { @MainActor [weak self] in
            let steps = 20
            for step in 1...steps {
                try? await Task.sleep(for: .milliseconds(16))
                if Task.isCancelled { return }
                let t = CGFloat(step) / CGFloat(steps)
                screen.brightness = start + (target - start) * (t * t * (3 - 2 * t))
            }
            self?.ramp = nil
            done()
        }
    }
}

/// The artificial HDR "boost", fitted to each picture and to its regions
/// rather than to single pixels. The picture's luminance is averaged into
/// a small grid (`grid` cells on the long side) and blurred, so the lift
/// follows lit areas (a sky, a face, a window) and a lone bright speck or
/// a hair of light gets no more than its surroundings. A histogram of that
/// blurred lightness (cube root of linear luminance, roughly how light it
/// looks) gives the picture's middle (median) and its own white (99.5th
/// percentile): the lift starts halfway between them (`Plan.knee`) and
/// grows slowly to its full strength at the white (`Plan.top`, at least
/// 0.25 of lightness away, so it never jumps). The strength (`Plan.gain`)
/// is lower when much of the picture would glow, when the picture is light
/// overall, and nothing when its lights are hardly lighter than the rest.
/// Each pixel takes the smoothly interpolated factor of its region, gated
/// softly by its own lightness so dark lines next to a light area are not
/// lifted (no halos); hue and saturation stay. Drawn on the CPU in half
/// floats, extended linear sRGB, shown by a `UIImageView` allowed the high
/// dynamic range. Not how the original or the frame look: a Konfiguracja
/// choice.
enum HDRBoost {
    /// Never more than this much brighter than white.
    static let maxGain: Float = 2.4
    /// The longest side of the boosted copy: half floats take 8 bytes a
    /// pixel, a 4096 px original would take over 100 MB.
    static let maxSide = 3072
    static let bins = 512
    /// Cells of the region grid on the picture's long side, and the blur
    /// radius in cells (three box passes, close to a Gaussian of ~4 cells,
    /// about 2 % of the picture).
    static let grid = 160
    static let blurRadius = 3
    /// How far below the knee (lightness) a pixel still takes some of its
    /// region's lift: wide, so only real darks (shadows, drawn lines) stay.
    static let gateWidth: Float = 0.45
    /// The ramp from the knee to the top never shorter than this (lightness).
    static let minRamp: Float = 0.25

    struct Plan: Equatable {
        /// Lightness (0…1) where the lift starts.
        var knee: Float
        /// Lightness at which the lift is full: the picture's own white.
        var top: Float
        /// How many times brighter than before the picture's white gets.
        var gain: Float
    }

    /// The lift for a lightness histogram (`bins` bins over 0…1), or nil
    /// when it would hardly show. `headroom`: what the screen can give.
    static func plan(histogram: [Int], headroom: Float) -> Plan? {
        let total = histogram.reduce(0, +)
        guard total > 0, histogram.count > 1 else { return nil }
        func percentile(_ p: Float) -> Float {
            let goal = Int((Float(total) * p).rounded(.up))
            var sum = 0
            for (bin, count) in histogram.enumerated() {
                sum += count
                if sum >= goal { return (Float(bin) + 0.5) / Float(histogram.count) }
            }
            return 1
        }
        func share(above lightness: Float) -> Float {
            let first = min(histogram.count, max(0, Int(lightness * Float(histogram.count))))
            return Float(histogram[first...].reduce(0, +)) / Float(total)
        }
        let middle = percentile(0.5)
        let top = max(percentile(0.995), 0.35)
        let knee = max(0.2, min(middle + 0.5 * (top - middle), 0.85, top - minRamp))
        guard top > knee else { return nil }
        // Glowing specks look like light; a glowing half of the picture
        // glares and wipes out its gradation.
        let lit = share(above: (knee + top) / 2)
        let area = max(0.3, min(1, 1 - (lit - 0.04) / 0.36))
        // A light picture as a whole needs less to look lit.
        let key = max(0.5, min(1, 1.25 - middle))
        // Lights hardly lighter than the rest are no lights: an even
        // picture would only get brighter all over.
        let spread = max(0, min(1, (top - middle - 0.05) / 0.2))
        let most = min(maxGain, headroom * 0.9)
        let gain = 1 + (most - 1) * area * key * spread
        guard gain > 1.08 else { return nil }
        return Plan(knee: knee, top: top, gain: gain)
    }

    /// The factor for a region of this lightness: a smootherstep from the
    /// knee to the top, so it leaves 1 and reaches the gain with no kink.
    static func factor(_ plan: Plan, lightness: Float) -> Float {
        let t = max(0, min(1, (lightness - plan.knee) / (plan.top - plan.knee)))
        return 1 + (plan.gain - 1) * t * t * t * (t * (t * 6 - 15) + 10)
    }

    /// How much of its region's lift a pixel of this lightness takes: none
    /// well below the knee (dark lines and shadows inside a lit area), all
    /// from the knee up, softly between.
    static func gate(_ plan: Plan, lightness: Float) -> Float {
        let low = plan.knee - gateWidth
        let t = max(0, min(1, (lightness - low) / gateWidth))
        return t * t * (3 - 2 * t)
    }

    /// Linear light of the 256 sRGB codes.
    static let linear: [Float] = (0..<256).map { code in
        let c = Float(code) / 255
        return c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
    }

    static func render(_ image: UIImage, headroom: CGFloat) async -> UIImage? {
        guard headroom > 1.05, let cg = image.cgImage else { return nil }
        let scale = image.scale
        let orientation = image.imageOrientation
        let room = Float(headroom)
        let out = await Task.detached(priority: .userInitiated) { boost(cg, headroom: room) }.value
        return out.map { UIImage(cgImage: $0, scale: scale, orientation: orientation) }
    }

    /// Three box blurs of `radius` along rows, then along columns.
    static func blur(_ values: inout [Float], width: Int, height: Int, radius: Int) {
        guard radius > 0 else { return }
        var line = [Float]()
        func pass(count: Int, lines: Int, at: (Int, Int) -> Int) {
            line = [Float](repeating: 0, count: count)
            for l in 0..<lines {
                for _ in 0..<3 {
                    for i in 0..<count { line[i] = values[at(l, i)] }
                    var sum: Float = 0
                    for k in -radius...radius { sum += line[max(0, min(count - 1, k))] }
                    for i in 0..<count {
                        values[at(l, i)] = sum / Float(2 * radius + 1)
                        sum += line[min(count - 1, i + radius + 1)] - line[max(0, i - radius)]
                    }
                }
            }
        }
        pass(count: width, lines: height) { row, x in row * width + x }
        pass(count: height, lines: width) { column, y in y * width + column }
    }

    static func boost(_ source: CGImage, headroom: Float) -> CGImage? {
        let longest = max(source.width, source.height)
        let shrink = longest > maxSide ? Double(maxSide) / Double(longest) : 1
        let width = max(1, Int((Double(source.width) * shrink).rounded()))
        let height = max(1, Int((Double(source.height) * shrink).rounded()))
        guard let srgb = CGColorSpace(name: CGColorSpace.sRGB),
              let wide = CGColorSpace(name: CGColorSpace.extendedLinearSRGB),
              let context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8,
                                      bytesPerRow: width * 4, space: srgb,
                                      bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue),
              let data = context.data
        else { return nil }
        context.interpolationQuality = .high
        context.draw(source, in: CGRect(x: 0, y: 0, width: width, height: height))
        let rowBytes = context.bytesPerRow
        let pixels = data.bindMemory(to: UInt8.self, capacity: rowBytes * height)
        let linear = Self.linear

        // The region grid: mean linear luminance of each cell, blurred.
        let cell = max(1, Double(max(width, height)) / Double(grid))
        let gw = max(1, Int((Double(width) / cell).rounded(.up)))
        let gh = max(1, Int((Double(height) / cell).rounded(.up)))
        var sums = [Float](repeating: 0, count: gw * gh)
        var counts = [Float](repeating: 0, count: gw * gh)
        for y in 0..<height {
            let row = y * rowBytes
            let gy = min(gh - 1, Int(Double(y) / cell)) * gw
            for x in 0..<width {
                let p = row + x * 4
                let lum = 0.2126 * linear[Int(pixels[p])] + 0.7152 * linear[Int(pixels[p + 1])]
                    + 0.0722 * linear[Int(pixels[p + 2])]
                let g = gy + min(gw - 1, Int(Double(x) / cell))
                sums[g] += lum
                counts[g] += 1
            }
        }
        var regions = zip(sums, counts).map { $1 > 0 ? $0 / $1 : 0 }
        blur(&regions, width: gw, height: gh, radius: blurRadius)
        let lightness = regions.map { cbrt(max(0, $0)) }

        var histogram = [Int](repeating: 0, count: bins)
        for l in lightness { histogram[min(bins - 1, Int(l * Float(bins)))] += 1 }
        guard let plan = Self.plan(histogram: histogram, headroom: headroom) else { return nil }
        let lift = lightness.map { Self.factor(plan, lightness: $0) - 1 }
        // The gate by a pixel's own luminance, from a table.
        let steps = 4096
        let last = Float(steps - 1)
        let gates = (0..<steps).map { Self.gate(plan, lightness: cbrt(Float($0) / last)) }

        // Handed to the image without a copy and freed with it.
        let count = width * height
        let output = UnsafeMutablePointer<Float16>.allocate(capacity: count * 4)
        for y in 0..<height {
            // Bilinear position in the grid (cell centres).
            let fy = max(0, min(Float(gh - 1), Float((Double(y) + 0.5) / cell - 0.5)))
            let y0 = Int(fy), y1 = min(gh - 1, y0 + 1)
            let wy = fy - Float(y0)
            let row = y * rowBytes
            for x in 0..<width {
                let fx = max(0, min(Float(gw - 1), Float((Double(x) + 0.5) / cell - 0.5)))
                let x0 = Int(fx), x1 = min(gw - 1, x0 + 1)
                let wx = fx - Float(x0)
                let top = lift[y0 * gw + x0] * (1 - wx) + lift[y0 * gw + x1] * wx
                let bottom = lift[y1 * gw + x0] * (1 - wx) + lift[y1 * gw + x1] * wx
                let regional = top * (1 - wy) + bottom * wy

                let p = row + x * 4
                let r = linear[Int(pixels[p])]
                let g = linear[Int(pixels[p + 1])]
                let b = linear[Int(pixels[p + 2])]
                let lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
                let m = 1 + regional * gates[Int(lum * last)]
                let o = (y * width + x) * 4
                output[o] = Float16(r * m)
                output[o + 1] = Float16(g * m)
                output[o + 2] = Float16(b * m)
                output[o + 3] = 1
            }
        }
        guard let provider = CGDataProvider(dataInfo: nil, data: output, size: count * 8,
                                            releaseData: { _, data, _ in data.deallocate() })
        else {
            output.deallocate()
            return nil
        }
        return CGImage(width: width, height: height, bitsPerComponent: 16, bitsPerPixel: 64,
                       bytesPerRow: width * 8, space: wide,
                       bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue
                           | CGBitmapInfo.floatComponents.rawValue | CGBitmapInfo.byteOrder16Little.rawValue),
                       provider: provider, decode: nil, shouldInterpolate: true, intent: .defaultIntent)
    }
}
