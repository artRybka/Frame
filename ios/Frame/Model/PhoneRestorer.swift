import CoreGraphics
import CoreML
import Foundation
import FrameScan
import ImageIO
import os
import UniformTypeIdentifiers

/// Our restorer on the phone, all of it (Mateusz 2026-11-27: „Wszystko.”,
/// „telefon wykonuje poprawę. Od razu ja pokazuje a w tle wysyła na
/// serwer”): the picture the server would draw from (`/restore/source`)
/// loses its printed screen (the core's `frame_restore_descreen`, the
/// server's `imaging/descreen.py`), is drawn four times larger by our model
/// (ArtSR G3, the server's `imaging/artsr.py`) on the Neural Engine in
/// windows of `window` px as the server draws its tiles, and is brought to
/// 2K and put in the picture's colours (`frame_restore_colours`, the
/// server's `restorer.recoloured`). Some seconds when a card opens; the
/// iPhone drew 1800 × 1415 px in 1.0 s, cool (Mateusz's trial,
/// 2026-11-27). The base model is LocalSR Photo M (Hermes Reisner, CC BY 4.0).
enum PhoneRestorer {
    /// The model's fixed window, its overlap and its scale (`TILE` +
    /// 2 × `OVERLAP`, `SCALE` on the server).
    static let window = 320
    static let overlap = 32
    static let scale = 4
    /// The drawing's long side (`restorer.LONGEST`).
    static let longest = 2048
    /// What is kept of what the model drew finer than the picture
    /// (`restorer.DRAWN`); the rest is the picture enlarged plainly.
    static let drawn = 0.7

    struct Failed: Error, LocalizedError {
        var told: String
        var errorDescription: String? { told }
    }

    /// A work drawn on the phone: the drawing (in the picture's colours, 2K
    /// long) and its JPEG for the server, of a picture `columns` × `rows`.
    struct Made: @unchecked Sendable {
        var image: CGImage
        var jpeg: Data
        var columns: Int
        var rows: Int
        /// The printed screen's points taken out (0: none).
        var screen: Int
        /// The drawing lay on its picture (else kept as drawn).
        var laid: Bool
        var took: Duration
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

    /// The picture in `file` (the server's `/restore/source`) drawn again
    /// as the server's restorer draws it: `look` the work's 768 SigLIP
    /// numbers, `kind` 0 painting, 1 print, 2 drawing (`/restore/plan`).
    static func restore(_ file: Data, look: [Float], kind: Int) throws -> Made {
        let clock = ContinuousClock()
        let start = clock.now
        var photo = try MuseumCrop.pixels(of: file)
        var error = [CChar](repeating: 0, count: 512)
        let size = Int32(error.count)
        var screen: Int32 = 0
        let rows = Int32(photo.rows), columns = Int32(photo.columns)
        let cleared = photo.rgb.withUnsafeMutableBufferPointer { rgb in
            frame_restore_descreen(rgb.baseAddress, rows, columns, &screen, &error, size)
        }
        guard cleared == 0 else { throw Failed(told: told(error)) }
        let model = try Loaded.shared.get()
        let (big, windows) = try larger(photo, model: model, look: look, kind: kind)
        var into = [UInt8](repeating: 0, count: longest * longest * 3)
        var height: Int32 = 0, width: Int32 = 0, laid: Int32 = 0
        let coloured = photo.rgb.withUnsafeBufferPointer { rgb in
            big.withUnsafeBufferPointer { big in
                into.withUnsafeMutableBufferPointer { into in
                    frame_restore_colours(
                        rgb.baseAddress, rows, columns, big.baseAddress, rows * Int32(scale), columns * Int32(scale),
                        drawn, into.baseAddress, &height, &width, &laid, &error, size
                    )
                }
            }
        }
        guard coloured == 0 else { throw Failed(told: told(error)) }
        let image = try picture(into, columns: Int(width), rows: Int(height))
        let jpeg = try encoded(image)
        let took = clock.now - start
        log.info(
            "drew \(photo.columns)×\(photo.rows) in \(windows) windows (screen \(screen), laid \(laid)): \(took)"
        )
        return Made(
            image: image, jpeg: jpeg, columns: photo.columns, rows: photo.rows, screen: Int(screen), laid: laid != 0,
            took: took
        )
    }

    private static func told(_ error: [CChar]) -> String {
        String(decoding: error.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }, as: UTF8.self)
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

    /// RGB bytes as a picture.
    static func picture(_ rgb: [UInt8], columns: Int, rows: Int) throws -> CGImage {
        var rgba = [UInt8](repeating: 255, count: columns * rows * 4)
        for i in 0 ..< columns * rows {
            rgba[i * 4] = rgb[i * 3]
            rgba[i * 4 + 1] = rgb[i * 3 + 1]
            rgba[i * 4 + 2] = rgb[i * 3 + 2]
        }
        guard let space = CGColorSpace(name: CGColorSpace.sRGB),
              let provider = CGDataProvider(data: Data(rgba) as CFData),
              let made = CGImage(
                  width: columns, height: rows, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: columns * 4,
                  space: space, bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.noneSkipLast.rawValue),
                  provider: provider, decode: nil, shouldInterpolate: true, intent: .defaultIntent
              )
        else { throw Failed(told: "the drawing could not be made") }
        return made
    }

    /// The drawing as the server keeps one (a JPEG of 95).
    static func encoded(_ image: CGImage) throws -> Data {
        let out = NSMutableData()
        guard let into = CGImageDestinationCreateWithData(out, UTType.jpeg.identifier as CFString, 1, nil) else {
            throw Failed(told: "the drawing could not be written")
        }
        CGImageDestinationAddImage(into, image, [kCGImageDestinationLossyCompressionQuality: 0.95] as CFDictionary)
        guard CGImageDestinationFinalize(into) else { throw Failed(told: "the drawing could not be written") }
        return out as Data
    }
}

/// How the server says a work is to be drawn on the phone (`/restore/plan`).
struct RestorePlan: Codable, Sendable {
    var kind: Int
    var look: [Float]
}
