import CoreGraphics
import CoreML
import Foundation
import os

/// Our restorer's model (ArtSR G3, the server's `imaging/artsr.py`) on the
/// phone's Neural Engine, for now only measured (Mateusz 2026-11-26: "Czy
/// prace modelu możemy wrzucić na iPhone w sytuacji gdy wchodzimy na kartę
/// dzieła?" … "Przetestujmy"): the picture four times larger, drawn in
/// windows of `window` px as the server draws its tiles, then brought to
/// 2K. The base model is LocalSR Photo M (Hermes Reisner, CC BY 4.0).
enum PhoneRestorer {
    /// The model's fixed window, its overlap and its scale (`TILE` +
    /// 2 × `OVERLAP`, `SCALE` on the server).
    static let window = 320
    static let overlap = 32
    static let scale = 4
    /// The drawing's long side (`restorer.LONGEST`).
    static let longest = 2048

    struct Failed: Error, LocalizedError {
        var told: String
        var errorDescription: String? { told }
    }

    /// What one drawing took.
    struct Measured: Sendable {
        var columns: Int
        var rows: Int
        var windows: Int
        var load: Duration
        var draw: Duration
        var thermalBefore: ProcessInfo.ThermalState
        var thermalAfter: ProcessInfo.ThermalState
        var drawing: CGImage
    }

    private static let log = Logger(subsystem: "Frame", category: "PhoneRestorer")

    private final class Loaded: @unchecked Sendable {
        static let shared = Loaded()
        private let lock = NSLock()
        private var model: MLModel?

        func get() throws -> MLModel {
            lock.lock()
            defer { lock.unlock() }
            if let model { return model }
            guard let url = Bundle.main.url(forResource: "ArtSR", withExtension: "mlmodelc") else {
                throw Failed(told: "the model is not in the app")
            }
            let configuration = MLModelConfiguration()
            // All of it runs on the Neural Engine; with `.all` Core ML sent
            // its FiLM sums to the GPU and was twice as slow (Mac, M2 Pro).
            configuration.computeUnits = .cpuAndNeuralEngine
            let made = try MLModel(contentsOf: url, configuration: configuration)
            model = made
            return made
        }
    }

    /// `photo` drawn four times larger and brought to 2K, measured. `look`:
    /// the work's 768 SigLIP numbers (zeros when not known: the time is the
    /// same); `kind`: 0 painting, 1 print, 2 drawing.
    static func measure(_ photo: MuseumCrop.Pixels, look: [Float]? = nil, kind: Int = 0) throws -> Measured {
        let before = ProcessInfo.processInfo.thermalState
        let clock = ContinuousClock()
        var model: MLModel?
        let load = try clock.measure { model = try Loaded.shared.get() }
        guard let model else { throw Failed(told: "the model did not load") }
        var windows = 0
        var drawn: [UInt8] = []
        let draw = try clock.measure {
            (drawn, windows) = try larger(photo, model: model, look: look ?? [Float](repeating: 0, count: 768), kind: kind)
        }
        let image = try twoK(drawn, columns: photo.columns * scale, rows: photo.rows * scale)
        let measured = Measured(
            columns: photo.columns, rows: photo.rows, windows: windows, load: load, draw: draw,
            thermalBefore: before, thermalAfter: ProcessInfo.processInfo.thermalState, drawing: image
        )
        log.info("drew \(photo.columns)×\(photo.rows) in \(windows) windows: \(draw)")
        return measured
    }

    /// Where the windows start along a side of `n` px (at least `window`):
    /// every `window - 2 overlap`, the last one moved in to end at the edge.
    static func starts(_ n: Int) -> [Int] {
        guard n > window else { return [0] }
        var found: [Int] = []
        var s = 0
        while s + window < n {
            found.append(s)
            s += window - 2 * overlap
        }
        found.append(n - window)
        return found
    }

    /// The part of a window starting at `s` (of `n`) that is kept: its
    /// middle, all the way to the picture's edges.
    static func kept(_ s: Int, of n: Int) -> Range<Int> {
        let a = s == 0 ? 0 : s + overlap
        let b = s + window >= n ? n : s + window - overlap
        return a ..< b
    }

    /// The picture four times larger, as bytes (rows × columns × 3); a side
    /// shorter than `window` is drawn with its edge repeated.
    static func larger(
        _ photo: MuseumCrop.Pixels, model: MLModel, look: [Float], kind: Int
    ) throws -> ([UInt8], Int) {
        let w = photo.columns, h = photo.rows
        let pw = max(w, window), ph = max(h, window)
        let lookArray = try MLMultiArray(shape: [1, 768], dataType: .float32)
        let norm = max(sqrt(look.reduce(0) { $0 + $1 * $1 }), 1e-12)
        for i in 0 ..< 768 { lookArray[i] = NSNumber(value: Float(Float16(i < look.count ? look[i] / norm : 0))) }
        let kindArray = try MLMultiArray(shape: [1, 3], dataType: .float32)
        for i in 0 ..< 3 { kindArray[i] = NSNumber(value: i == kind ? Float(1) : 0) }
        let input = try MLMultiArray(
            shape: [1, 3, NSNumber(value: window), NSNumber(value: window)], dataType: .float32
        )
        let ow = w * scale
        var out = [UInt8](repeating: 0, count: ow * h * scale * 3)
        var windows = 0
        let outputName = model.modelDescription.outputDescriptionsByName.keys.first ?? "output"
        for y0 in starts(ph) {
            for x0 in starts(pw) {
                input.withUnsafeMutableBufferPointer(ofType: Float.self) { into, strides in
                    for c in 0 ..< 3 {
                        for y in 0 ..< window {
                            let sy = min(y0 + y, h - 1)
                            for x in 0 ..< window {
                                let sx = min(x0 + x, w - 1)
                                into[c * strides[1] + y * strides[2] + x * strides[3]] =
                                    Float(photo.rgb[(sy * w + sx) * 3 + c]) / 255
                            }
                        }
                    }
                }
                let features = try MLDictionaryFeatureProvider(dictionary: [
                    "image": MLFeatureValue(multiArray: input),
                    "look": MLFeatureValue(multiArray: lookArray),
                    "kind": MLFeatureValue(multiArray: kindArray),
                ])
                let answer = try model.prediction(from: features)
                guard let drawn = answer.featureValue(for: outputName)?.multiArrayValue else {
                    throw Failed(told: "the model gave no picture")
                }
                windows += 1
                let ys = kept(y0, of: ph).clamped(to: 0 ..< h)
                let xs = kept(x0, of: pw).clamped(to: 0 ..< w)
                copy(drawn, origin: (x0, y0), rows: ys, columns: xs, into: &out, width: ow)
            }
        }
        return (out, windows)
    }

    private static func copy(
        _ drawn: MLMultiArray, origin: (Int, Int), rows: Range<Int>, columns: Range<Int>,
        into out: inout [UInt8], width: Int
    ) {
        func put(_ value: (Int) -> Float, _ strides: [Int]) {
            for y in rows.lowerBound * scale ..< rows.upperBound * scale {
                let wy = y - origin.1 * scale
                for x in columns.lowerBound * scale ..< columns.upperBound * scale {
                    let wx = x - origin.0 * scale
                    for c in 0 ..< 3 {
                        let v = value(c * strides[1] + wy * strides[2] + wx * strides[3])
                        out[(y * width + x) * 3 + c] = UInt8(max(0, min(255, v * 255 + 0.5)))
                    }
                }
            }
        }
        if drawn.dataType == .float16 {
            drawn.withUnsafeBufferPointer(ofType: Float16.self) { from in
                put({ Float(from[$0]) }, drawn.strides.map(\.intValue))
            }
        } else {
            drawn.withUnsafeBufferPointer(ofType: Float.self) { from in
                put({ from[$0] }, drawn.strides.map(\.intValue))
            }
        }
    }

    /// The drawing brought down to `longest` on its long side.
    static func twoK(_ rgb: [UInt8], columns: Int, rows: Int) throws -> CGImage {
        var rgba = [UInt8](repeating: 255, count: columns * rows * 4)
        for i in 0 ..< columns * rows {
            rgba[i * 4] = rgb[i * 3]
            rgba[i * 4 + 1] = rgb[i * 3 + 1]
            rgba[i * 4 + 2] = rgb[i * 3 + 2]
        }
        let space = CGColorSpace(name: CGColorSpace.sRGB)!
        let info = CGImageAlphaInfo.noneSkipLast.rawValue
        guard let provider = CGDataProvider(data: Data(rgba) as CFData),
              let full = CGImage(
                  width: columns, height: rows, bitsPerComponent: 8, bitsPerPixel: 32,
                  bytesPerRow: columns * 4, space: space, bitmapInfo: CGBitmapInfo(rawValue: info),
                  provider: provider, decode: nil, shouldInterpolate: true, intent: .defaultIntent
              )
        else { throw Failed(told: "the drawing could not be made") }
        let k = Double(longest) / Double(max(columns, rows))
        let tw = Int((Double(columns) * k).rounded()), th = Int((Double(rows) * k).rounded())
        guard let context = CGContext(
            data: nil, width: tw, height: th, bitsPerComponent: 8, bytesPerRow: 0, space: space, bitmapInfo: info
        ) else { throw Failed(told: "the drawing could not be made") }
        context.interpolationQuality = .high
        context.draw(full, in: CGRect(x: 0, y: 0, width: tw, height: th))
        guard let made = context.makeImage() else { throw Failed(told: "the drawing could not be made") }
        return made
    }
}
