import Accelerate
import CoreGraphics
import CoreML
import Foundation
import FrameScan
import ImageIO
import UIKit

/// A museum photograph cut down to the work by a small model on the phone,
/// with no Claude (Mateusz 2026-11-20: "Celem jest całkowite uniknięcie
/// Opus", "Gdy model brak pewności — po prostu zostawmy do ręcznego
/// kadrowania", "Musi szukać prostokątów prawie na wprost").
///
/// The model (`Models/Kadr.mlpackage`) gives two masks of the photograph
/// and how sure it is a cut is wanted; the scan's core (`core/scan`,
/// `frame_crop_find`) makes of them the work's corners set on the
/// photograph's own edges and what to do: as the server's
/// `imaging/crop_model.py` does, the truth it is held to. The server keeps
/// what was found and cuts the work when the model was sure
/// (`POST /api/crops/phone/{id}`, `phone_crops.py`).
enum MuseumCrop {
    /// The model's name, as the server knows it (`crop_model.MODEL`):
    /// drawings, prints and the rest (`Models/Kadr.mlpackage`; Mateusz
    /// 2026-11-24: „Tak, wymień”).
    static let model = "kadr-11s"
    /// Paintings' own (`crop_model.PAINTING_MODEL`, `Models/KadrPainting.mlpackage`;
    /// Mateusz 2026-11-21 21:31 UTC: „Tak, wymień dla malarstwa”).
    static let paintingModel = "kadr-10p"
    /// How sure of a cut each must be to cut (`crop_model.SURE`,
    /// `PAINTING_SURE`).
    static let sure = 0.795
    static let paintingSure = 0.81

    /// The model that looks at a work of `kind` (`crop_model.model_of`).
    static func modelOf(_ kind: Int) -> String { kind == 0 ? paintingModel : model }
    /// How sure of a cut it must be (`crop_model.sure_of`).
    static func sureOf(_ kind: Int) -> Double { kind == 0 ? paintingSure : sure }
    /// Its file in the app.
    private static func file(of kind: Int) -> String { kind == 0 ? "KadrPainting" : "Kadr" }
    /// The model's square (`crop_model.SIDE`).
    static let side = 384
    /// The photograph's long side looked at (`crop_model.PHOTO_SIDE`).
    static let photoSide = 1024
    /// A print's sheet is cut down round its impression when its paper is
    /// wide (`crop_model.plate`; Mateusz 2026-11-24: „kadrujmy do kartki,
    /// chyba że margines od odbitki jest wtedy bardzo duży”): as the
    /// server does it (`crop_model.PLATE`, told it with what was found),
    /// over this share of the impression's shorter side (`PLATE_OVER`).
    static let plates = 1
    static let plateOver = 0.15
    /// A print (`crop_model.KINDS`).
    static let printKind = 2

    struct Failed: LocalizedError {
        let told: String
        var errorDescription: String? { "Kadrowanie na iPhonie nie powiodło się: \(told)" }
    }

    /// A photograph as the core takes it: rows × columns × RGB, 8 bits.
    struct Pixels: Sendable {
        var rows: Int
        var columns: Int
        var rgb: [UInt8]
    }

    /// What the model and the core made of a photograph.
    struct Found: Equatable, Sendable {
        /// "cut", "whole" (it wants no cut) or "unsure" (left to him).
        var verdict: String
        var work: [[Double]]?
        var surround: [[Double]]?
        var sure: Double
        /// Of a print whose sheet was cut down round its impression
        /// (`plate(_:sheet:)`): the sheet the model found, the impression alone.
        var sheet: [[Double]]? = nil
        var plate: [[Double]]? = nil
    }

    /// A photograph's file read upright in sRGB, as the server's
    /// `load_image` reads the JPEG it sent.
    static func pixels(of file: Data) throws -> Pixels {
        guard let source = CGImageSourceCreateWithData(file as CFData, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, [kCGImageSourceShouldCache: false] as CFDictionary)
        else { throw Failed(told: "the photograph is no picture") }
        return try pixels(of: image)
    }

    /// A picture already read (a thumbnail shown), in sRGB.
    static func pixels(of image: CGImage) throws -> Pixels {
        guard let colours = CGColorSpace(name: CGColorSpace.sRGB) else { throw Failed(told: "no sRGB") }
        let columns = image.width, rows = image.height
        guard let context = CGContext(
            data: nil, width: columns, height: rows, bitsPerComponent: 8, bytesPerRow: columns * 4,
            space: colours, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
        ) else { throw Failed(told: "no memory for the photograph") }
        context.interpolationQuality = .none
        context.draw(image, in: CGRect(x: 0, y: 0, width: columns, height: rows))
        guard let drawn = context.data else { throw Failed(told: "no memory for the photograph") }
        var rgb = [UInt8](repeating: 0, count: rows * columns * 3)
        let converted = rgb.withUnsafeMutableBytes { raw -> vImage_Error in
            var from = vImage_Buffer(
                data: drawn, height: vImagePixelCount(rows), width: vImagePixelCount(columns),
                rowBytes: context.bytesPerRow
            )
            var to = vImage_Buffer(
                data: raw.baseAddress, height: vImagePixelCount(rows), width: vImagePixelCount(columns),
                rowBytes: columns * 3
            )
            return vImageConvert_RGBA8888toRGB888(&from, &to, vImage_Flags(kvImageNoFlags))
        }
        guard converted == kvImageNoError else { throw Failed(told: "the photograph could not be read") }
        return Pixels(rows: rows, columns: columns, rgb: rgb)
    }

    /// The photograph as the model takes it (`crop_model.letterbox`):
    /// 3 × `side` × `side` floats 0–255.
    static func letterbox(_ photo: Pixels) throws -> [Float] {
        var into = [Float](repeating: 0, count: 3 * side * side)
        var box = [Int32](repeating: 0, count: 4)
        var error = [CChar](repeating: 0, count: 512)
        let size = Int32(error.count)
        let status = photo.rgb.withUnsafeBufferPointer { rgb in
            into.withUnsafeMutableBufferPointer { into in
                frame_crop_letterbox(
                    rgb.baseAddress, Int32(photo.rows), Int32(photo.columns), Int32(side), into.baseAddress, &box,
                    &error, size
                )
            }
        }
        guard status == 0 else { throw Failed(told: told(error)) }
        return into
    }

    /// What the model's answer about `photo` comes to
    /// (`crop_model.find`): `logits` its `masks` (2 × `side` × `side`),
    /// `sure` its `cut`.
    static func find(_ photo: Pixels, logits: [Float], sure: Double, cutAt: Double = MuseumCrop.sure) throws -> Found {
        guard logits.count == 2 * side * side else { throw Failed(told: "the model's masks are not its size") }
        var work = [Double](repeating: 0, count: 8), surround = [Double](repeating: 0, count: 8)
        var found: Int32 = 0
        var error = [CChar](repeating: 0, count: 512)
        let size = Int32(error.count)
        let verdict = photo.rgb.withUnsafeBufferPointer { rgb in
            logits.withUnsafeBufferPointer { logits in
                frame_crop_find(
                    rgb.baseAddress, Int32(photo.rows), Int32(photo.columns), logits.baseAddress, Int32(side), sure,
                    cutAt, &work, &surround, &found, &error, size
                )
            }
        }
        guard verdict >= 0 else { throw Failed(told: told(error)) }
        func corners(_ q: [Double]) -> [[Double]] { stride(from: 0, to: 8, by: 2).map { [q[$0], q[$0 + 1]] } }
        return Found(
            verdict: verdict == 1 ? "cut" : verdict == 0 ? "whole" : "unsure",
            work: found & 1 != 0 ? corners(work) : nil,
            surround: found & 2 != 0 ? corners(surround) : nil,
            sure: sure
        )
    }

    /// A print's `sheet` on `photo` cut down round its impression when its
    /// paper is wide (`crop_model.plate`): the cut and the impression
    /// alone; nil when the sheet stays.
    static func plate(_ photo: Pixels, sheet: [[Double]]) throws -> (cut: [[Double]], plate: [[Double]])? {
        guard sheet.count == 4, sheet.allSatisfy({ $0.count == 2 }) else { throw Failed(told: "no sheet") }
        let given = sheet.flatMap { $0 }
        var cut = [Double](repeating: 0, count: 8), alone = [Double](repeating: 0, count: 8)
        var found: Int32 = 0
        var error = [CChar](repeating: 0, count: 512)
        let size = Int32(error.count)
        let made = photo.rgb.withUnsafeBufferPointer { rgb in
            frame_crop_plate(
                rgb.baseAddress, Int32(photo.rows), Int32(photo.columns), given, plateOver, &cut, &alone, &found,
                &error, size
            )
        }
        guard made >= 0 else { throw Failed(told: told(error)) }
        guard made == 1, found & 3 == 3 else { return nil }
        return (corners(cut), corners(alone))
    }

    private static func corners(_ q: [Double]) -> [[Double]] {
        stride(from: 0, to: 8, by: 2).map { [q[$0], q[$0 + 1]] }
    }

    private static func told(_ error: [CChar]) -> String {
        String(decoding: error.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }, as: UTF8.self)
    }

    // MARK: The model

    /// The compiled model in the app for a work of `kind` (`Kadr.mlmodelc`,
    /// `KadrPainting.mlmodelc`), each loaded once.
    static func loaded(of kind: Int = 1) throws -> MLModel {
        try Loaded.shared.model(file(of: kind))
    }

    /// Both models loaded while the app starts: the first card opened after
    /// an update waited a minute on the new one (nga:2993, 2026-11-25).
    static func warm() async {
        await Task.detached(priority: .utility) {
            for kind in [0, 1] { _ = try? loaded(of: kind) }
        }.value
    }

    private final class Loaded: @unchecked Sendable {
        static let shared = Loaded()
        private let lock = NSLock()
        private var kept: [String: MLModel] = [:]

        func model(_ name: String) throws -> MLModel {
            lock.lock()
            defer { lock.unlock() }
            if let made = kept[name] { return made }
            guard let url = Bundle.main.url(forResource: name, withExtension: "mlmodelc") else {
                throw Failed(told: "the model is not in the app")
            }
            let made = try MLModel(contentsOf: url, configuration: MLModelConfiguration())
            kept[name] = made
            return made
        }
    }

    /// The model's answer about `photo` of `kind` (`crop_model.KINDS`):
    /// its masks before the sigmoid, and how sure it is a cut is wanted.
    static func ask(_ photo: Pixels, kind: Int) throws -> (logits: [Float], sure: Double) {
        let model = try loaded(of: kind)
        let x = try MLMultiArray(shape: [1, 3, NSNumber(value: side), NSNumber(value: side)], dataType: .float32)
        let boxed = try letterbox(photo)
        boxed.withUnsafeBufferPointer { from in
            x.withUnsafeMutableBufferPointer(ofType: Float.self) { into, strides in
                // [1, 3, side, side]: rows may be padded.
                for c in 0 ..< 3 {
                    for y in 0 ..< side {
                        for column in 0 ..< side {
                            into[c * strides[1] + y * strides[2] + column * strides[3]] =
                                from[(c * side + y) * side + column]
                        }
                    }
                }
            }
        }
        let kinds = try MLMultiArray(shape: [1, 5], dataType: .float32)
        for n in 0 ..< 5 { kinds[n] = NSNumber(value: n == min(max(kind, 0), 4) ? 1.0 : 0.0) }
        let given = try MLDictionaryFeatureProvider(dictionary: ["x": x, "kind": kinds])
        let said = try model.prediction(from: given)
        guard let masks = said.featureValue(for: "masks")?.multiArrayValue,
              let cut = said.featureValue(for: "cut")?.multiArrayValue, cut.count > 0
        else { throw Failed(told: "the model gave no answer") }
        return (floats(masks), cut[0].doubleValue)  // `cut` comes out of a sigmoid
    }

    /// The masks (1 × 2 × side × side, of whatever strides and numbers) as
    /// 2 × side × side floats.
    private static func floats(_ masks: MLMultiArray) -> [Float] {
        let strides = masks.strides.map(\.intValue)
        let kind = masks.dataType
        var out = [Float](repeating: 0, count: 2 * side * side)
        masks.withUnsafeBytes { raw in
            for c in 0 ..< 2 {
                for y in 0 ..< side {
                    for x in 0 ..< side {
                        let at = c * strides[1] + y * strides[2] + x * strides[3]
                        out[(c * side + y) * side + x] = switch kind {
                        case .float16: Float(raw.load(fromByteOffset: at * 2, as: Float16.self))
                        case .double: Float(raw.load(fromByteOffset: at * 8, as: Double.self))
                        default: raw.load(fromByteOffset: at * 4, as: Float.self)
                        }
                    }
                }
            }
        }
        return out
    }

    /// The photograph's file looked at, start to end: what the server is told.
    static func look(at file: Data, kind: Int) throws -> (found: Found, columns: Int, rows: Int) {
        try look(at: try pixels(of: file), kind: kind)
    }

    /// A picture already read (the card's own, no longer than `photoSide`).
    static func look(at image: CGImage, kind: Int) throws -> (found: Found, columns: Int, rows: Int) {
        try look(at: try pixels(of: image), kind: kind)
    }

    private static func look(at photo: Pixels, kind: Int) throws -> (found: Found, columns: Int, rows: Int) {
        let (logits, sure) = try ask(photo, kind: kind)
        var found = try find(photo, logits: logits, sure: sure, cutAt: sureOf(kind))
        if kind == printKind, let sheet = found.work, let made = try plate(photo, sheet: sheet) {
            found.sheet = sheet
            found.work = made.cut
            found.plate = made.plate
        }
        return (found, photo.columns, photo.rows)
    }
}

// MARK: What the server is asked and told (`web/crops_api.py`)

/// Whether to look at a work's photograph now, the work's kind as the
/// model is told it, the server's model and the photograph's key.
struct PhoneCropAsk: Codable, Hashable, Sendable {
    var look: Bool
    var kind: Int
    var model: String
    var picture: String
    var side: Int
}

/// "Kadruj partię": works to look at, how many wait in all.
struct PhoneCropsWaiting: Codable, Hashable, Sendable {
    struct Work: Codable, Hashable, Sendable {
        var id: String
        var look: Bool
        var kind: Int
        var model: String
        var picture: String
    }

    var model: String
    var side: Int
    var works: [Work]
    var left: Int
}

/// What the model found (`MuseumCrop.Found`), of a photograph of
/// `width` × `height`.
struct PhoneCropFound: Codable, Hashable, Sendable {
    var model: String
    var picture: String
    var verdict: String
    var sure: Double
    var work: [[Double]]?
    var surround: [[Double]]?
    var width: Int
    var height: Int
    /// Of a print whose sheet was cut down round its impression: the sheet
    /// the model found, the impression alone, and how (`MuseumCrop.plates`).
    var sheet: [[Double]]? = nil
    var plate: [[Double]]? = nil
    var plates: Int? = MuseumCrop.plates
}

/// What came of it: the verdict as the server kept it ("" when it did
/// nothing: the photograph shown changed meanwhile, or he cut it himself).
struct PhoneCropResult: Codable, Hashable, Sendable {
    var cut: Bool
    var verdict: String
    var item: Item
}

/// "Sprawdź kadry": the works the model cut, and those it left to him.
struct CropReview: Codable, Hashable, Sendable {
    var cut: [ItemSummary]
    var unsure: [ItemSummary]
    /// How sure the model was of each work (nil from an older server).
    var sure: [Sure]? = nil

    struct Sure: Codable, Hashable, Sendable {
        var id: String
        var sure: Double
    }

    var isEmpty: Bool { cut.isEmpty && unsure.isEmpty }
}

/// "Ucz kadrowania": catalogue photographs of one kind for his word at a
/// glance, and how many he has given.
struct CropTeach: Codable, Hashable, Sendable {
    var works: [ItemSummary]
    var told: Int

    /// What he says of a photograph.
    enum Answer: String, Codable, Sendable {
        case whole, cut, framed
    }
}

extension MuseumCrop {
    /// A work's photograph looked at on the phone and what was found told
    /// to the server: the work as it is now when it was cut, else nil.
    /// Nothing when the server has nothing for the phone to look at (an
    /// older server, a work looked at already, not the owner's phone).
    ///
    /// `picture`: the work's picture as the card shows it (the museum's
    /// photograph while it is not cut), read through the app's own cache
    /// instead of asking the server for the photograph again (Mateusz
    /// 2026-11-25: seconds behind other downloads there). `seen`: what the
    /// model found, and the picture it looked at, before the server is told.
    static func look(
        itemID: String, backend: any FrameBackend, asked: PhoneCropAsk? = nil, picture: ImageRef? = nil,
        seen: (@MainActor (Found, UIImage) async -> Void)? = nil
    ) async throws -> PhoneCropResult? {
        let ask: PhoneCropAsk
        if let asked { ask = asked } else { ask = try await backend.phoneCropAsk(itemID: itemID) }
        guard ask.look, ask.model == modelOf(ask.kind) else { return nil }
        var shown: UIImage?
        if let picture, let request = backend.request(for: picture) {
            shown = try? await ImageLoader.shared.image(for: request, maxPixel: CGFloat(ask.side), priority: .high)
        }
        let looked: (found: Found, columns: Int, rows: Int)
        if let image = shown?.cgImage {
            looked = try await Task.detached(priority: .userInitiated) { try MuseumCrop.look(at: image, kind: ask.kind) }.value
        } else {
            let file = try await backend.museumPhoto(itemID: itemID, side: ask.side)
            looked = try await Task.detached(priority: .userInitiated) { try MuseumCrop.look(at: file, kind: ask.kind) }.value
            shown = UIImage(data: file)
        }
        if let seen, let shown { await seen(looked.found, shown) }
        let found = PhoneCropFound(
            model: ask.model, picture: ask.picture, verdict: looked.found.verdict, sure: looked.found.sure,
            work: looked.found.work, surround: looked.found.surround, width: looked.columns, height: looked.rows,
            sheet: looked.found.sheet, plate: looked.found.plate
        )
        return try await backend.phoneCropFound(itemID: itemID, found)
    }
}
