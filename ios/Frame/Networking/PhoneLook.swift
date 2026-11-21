import CoreGraphics
import CoreML
import CryptoKit
import Foundation
import ImageIO
import os

/// "Szukaj zdjęciem" numbered on the phone (Mateusz 2026-11-21: "szykujmy
/// takie rozwiązanie"): SigLIP 2's picture side in Core ML, fetched once
/// from the server (`GET /api/looks/phone/model`, the server's
/// `seen.PHONE`), numbers a photograph as the server's
/// `SeenModel.pixels` and `pictures` do, and only its 768 numbers go
/// (`POST /api/looks/photo/numbers`), never the photograph. Until the model
/// is here, or while the server answers with Google's numbers, the
/// photograph goes as before; the model is fetched meanwhile, in the
/// background, for the next time.
actor PhoneLook {
    static let shared = PhoneLook()

    /// The side the model sees a picture at, and its numbers.
    static let side = 256
    static let size = 768

    /// `GET /api/looks/phone`.
    struct Status: Codable, Sendable {
        var model: String
        var here: Bool
        var size: Int
        var sha256: String
        var answers: Bool
    }

    enum Failure: Error {
        case changed, broken(String)
    }

    private static let log = Logger(subsystem: "Frame", category: "PhoneLook")

    private var loaded: (model: String, ml: MLModel)?
    private var fetching: Task<Void, Never>?

    /// Where the compiled model is kept (one, the server's release's name).
    static var folder: URL {
        URL.applicationSupportDirectory.appending(path: "PhoneLook", directoryHint: .isDirectory)
    }

    static func compiled(_ model: String) -> URL {
        folder.appending(path: "\(model).mlmodelc", directoryHint: .isDirectory)
    }

    /// The photograph's numbers (length 1), or nil when the model is not
    /// here yet (fetched meanwhile by `fetch`, which gives the tar's file)
    /// or the photograph cannot be read.
    func numbers(
        _ picture: Data,
        status: Status,
        fetch: @escaping @Sendable () async throws -> URL
    ) async -> [Float]? {
        guard status.answers, status.here else { return nil }
        guard let ml = model(status.model) else {
            start(status, fetch)
            return nil
        }
        guard let pixels = Self.pixels(picture) else { return nil }
        do {
            return try Self.look(ml, pixels)
        } catch {
            Self.log.error("numbering a photograph failed: \(error.localizedDescription)")
            return nil
        }
    }

    private func model(_ name: String) -> MLModel? {
        if let loaded, loaded.model == name { return loaded.ml }
        let url = Self.compiled(name)
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        let configuration = MLModelConfiguration()
        configuration.computeUnits = .all
        guard let ml = try? MLModel(contentsOf: url, configuration: configuration) else {
            try? FileManager.default.removeItem(at: url)  // broken: fetched again
            return nil
        }
        loaded = (name, ml)
        return ml
    }

    private func start(_ status: Status, _ fetch: @escaping @Sendable () async throws -> URL) {
        guard fetching == nil else { return }
        fetching = Task.detached(priority: .utility) {
            do {
                let tar = try await fetch()
                defer { try? FileManager.default.removeItem(at: tar) }
                try await Self.install(tar, status: status)
                Self.log.info("the phone's look model is here (\(status.model))")
            } catch {
                Self.log.error("fetching the phone's look model failed: \(error.localizedDescription)")
            }
            await self.fetched()
        }
    }

    private func fetched() { fetching = nil }

    /// The tar checked against the server's sum, unpacked, compiled and
    /// kept in `folder` (the only model there).
    static func install(_ tar: URL, status: Status) async throws {
        guard try sum(tar) == status.sha256.lowercased() else { throw Failure.changed }
        let manager = FileManager.default
        let unpacked = manager.temporaryDirectory.appending(path: UUID().uuidString, directoryHint: .isDirectory)
        defer { try? manager.removeItem(at: unpacked) }
        try untar(tar, into: unpacked)
        guard let package = try manager.contentsOfDirectory(at: unpacked, includingPropertiesForKeys: nil)
            .first(where: { $0.pathExtension == "mlpackage" })
        else { throw Failure.broken("no .mlpackage in the tar") }
        let made = try await MLModel.compileModel(at: package)
        try manager.createDirectory(at: folder, withIntermediateDirectories: true)
        for old in (try? manager.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)) ?? [] {
            try? manager.removeItem(at: old)
        }
        let target = compiled(status.model)
        try manager.moveItem(at: made, to: target)
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        var kept = target
        try? kept.setResourceValues(values)
    }

    /// The file's SHA-256, read a piece at a time.
    static func sum(_ file: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: file)
        defer { try? handle.close() }
        var digest = SHA256()
        while let piece = try handle.read(upToCount: 4 << 20), !piece.isEmpty {
            digest.update(data: piece)
        }
        return digest.finalize().map { String(format: "%02x", $0) }.joined()
    }

    /// An uncompressed (ustar) tar's directories and files into `folder`.
    static func untar(_ file: URL, into folder: URL) throws {
        let data = try Data(contentsOf: file, options: .alwaysMapped)
        let manager = FileManager.default
        try manager.createDirectory(at: folder, withIntermediateDirectories: true)
        var at = data.startIndex
        while at + 512 <= data.endIndex {
            let head = data[at ..< at + 512]
            if head.allSatisfy({ $0 == 0 }) { break }
            func text(_ from: Int, _ count: Int) -> String {
                let field = head[(at + from) ..< (at + from + count)]
                return String(decoding: field.prefix { $0 != 0 }, as: UTF8.self)
            }
            let name = text(0, 100)
            let prefix = text(345, 155)
            let octal = text(124, 12).trimmingCharacters(in: .whitespaces)
            guard let size = Int(octal.isEmpty ? "0" : octal, radix: 8) else {
                throw Failure.broken("a size not read: \(octal)")
            }
            let type = head[at + 156]
            let path = prefix.isEmpty ? name : "\(prefix)/\(name)"
            at += 512
            guard at + size <= data.endIndex else { throw Failure.broken("cut short") }
            let parts = path.split(separator: "/").filter { $0 != "." }
            guard !parts.isEmpty, !parts.contains("..") else {
                at += (size + 511) / 512 * 512
                continue
            }
            let target = parts.reduce(folder) { $0.appending(path: String($1)) }
            switch type {
            case UInt8(ascii: "5"):
                try manager.createDirectory(at: target, withIntermediateDirectories: true)
            case 0, UInt8(ascii: "0"):
                try manager.createDirectory(at: target.deletingLastPathComponent(), withIntermediateDirectories: true)
                try data[at ..< at + size].write(to: target)
            default:
                break  // links, extended headers: none in the model's tar
            }
            at += (size + 511) / 512 * 512
        }
    }

    /// A photograph as the model sees it, as the server's
    /// `SeenModel.pixels`: RGB squeezed to `side` square (not kept in
    /// proportion), -1 to 1, the three colours one after another. Its
    /// pixels as stored, as the server reads them (no turning by EXIF).
    static func pixels(_ picture: Data) -> MLMultiArray? {
        guard let source = CGImageSourceCreateWithData(picture as CFData, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
        else { return nil }
        return pixels(image)
    }

    static func pixels(_ image: CGImage) -> MLMultiArray? {
        let side = Self.side
        var bytes = [UInt8](repeating: 0, count: side * side * 4)
        let drawn = bytes.withUnsafeMutableBytes { raw -> Bool in
            guard let space = CGColorSpace(name: CGColorSpace.sRGB),
                  let context = CGContext(
                      data: raw.baseAddress, width: side, height: side, bitsPerComponent: 8,
                      bytesPerRow: side * 4, space: space,
                      bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
                  )
            else { return false }
            context.interpolationQuality = .high
            context.draw(image, in: CGRect(x: 0, y: 0, width: side, height: side))
            return true
        }
        guard drawn,
              let array = try? MLMultiArray(shape: [1, 3, NSNumber(value: side), NSNumber(value: side)], dataType: .float32)
        else { return nil }
        let plane = side * side
        let out = array.dataPointer.bindMemory(to: Float.self, capacity: 3 * plane)
        for at in 0 ..< plane {
            for colour in 0 ..< 3 {
                out[colour * plane + at] = Float(bytes[at * 4 + colour]) / 127.5 - 1
            }
        }
        return array
    }

    /// The model's numbers for `pixels`, at length 1.
    static func look(_ ml: MLModel, _ pixels: MLMultiArray) throws -> [Float] {
        let input = try MLDictionaryFeatureProvider(dictionary: ["pixels": MLFeatureValue(multiArray: pixels)])
        let output = try ml.prediction(from: input)
        guard let look = output.featureValue(for: "look")?.multiArrayValue, look.count == size else {
            throw Failure.broken("no numbers")
        }
        var numbers = (0 ..< look.count).map { Float(truncating: look[$0]) }
        let norm = numbers.reduce(0) { $0 + $1 * $1 }.squareRoot()
        guard norm > 1e-6, norm.isFinite else { throw Failure.broken("numbers of nothing") }
        numbers = numbers.map { $0 / norm }
        return numbers
    }

    /// The numbers as the server takes them: float32, little-endian, base64.
    static func encoded(_ numbers: [Float]) -> String {
        var data = Data(capacity: numbers.count * 4)
        for number in numbers {
            withUnsafeBytes(of: number.bitPattern.littleEndian) { data.append(contentsOf: $0) }
        }
        return data.base64EncodedString()
    }
}
