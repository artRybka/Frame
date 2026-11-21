import CoreML
import Foundation
import XCTest

@testable import Frame

/// "Szukaj zdjęciem" numbered on the phone (`PhoneLook`): the model's tar
/// unpacked, a photograph read as the server's `SeenModel.pixels` reads
/// it, and the model's numbers as the server's own (ONNX) for the same file.
final class PhoneLookTests: XCTestCase {
    /// A ustar tar of `A.mlpackage/Manifest.json` ("hello") and
    /// `A.mlpackage/Data/w.bin` ("xyz"), as GNU tar writes it (raw deflate).
    private static let tar =
        "7dVNDoIwGEXRLoUVYEtbGJM4dRHVoKIIBjD+rF7CiDDAmABGvWfyNWkHTV76Gvun7Ow2R7dLFmIishFZ285Gf7ZrZbWUOlAqMEIqFclQeFbM4FLVrmyuUhZFPXTu1f6Xijv5r1yebpOq9g9VkY+cf2jMQP62l7/RJhCeJP/J7ZMsKwT+Vff9L13tpvgE3u//wNqI/v9I/ld/nebj5z/c/7qXv7ZK0v9zuN0flCAAAAAAAAAAAAAA/IAn"

    /// The server's numbers (`seen.SeenModel.pictures`, ONNX, float32
    /// little-endian, base64) of `DemoImages/aic_14598.jpg`.
    private static let serverAic = "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"

    /// The phone's model, as released (`seen.PHONE`).
    private static let release =
        "https://github.com/artRybka/Frame/releases/download/look-model-siglip2-b16-phone-1/Look.mlpackage.tar"

    private func scratch() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString, directoryHint: .isDirectory)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }
        return url
    }

    func testTheModelsTarIsUnpacked() throws {
        let packed = try XCTUnwrap(Data(base64Encoded: Self.tar))
        let tar = try (packed as NSData).decompressed(using: .zlib) as Data
        let folder = try scratch()
        let file = folder.appending(path: "a.tar")
        try tar.write(to: file)
        let out = folder.appending(path: "out", directoryHint: .isDirectory)
        try PhoneLook.untar(file, into: out)
        let package = out.appending(path: "A.mlpackage")
        XCTAssertEqual(try String(contentsOf: package.appending(path: "Manifest.json"), encoding: .utf8), "hello")
        XCTAssertEqual(try Data(contentsOf: package.appending(path: "Data/w.bin")), Data("xyz".utf8))
        XCTAssertEqual(try PhoneLook.sum(file).count, 64)
    }

    func testAPictureIsReadAsTheServerReadsIt() throws {
        let white = try XCTUnwrap(
            CGContext(
                data: nil, width: 30, height: 10, bitsPerComponent: 8, bytesPerRow: 0,
                space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
            )
        )
        white.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
        white.fill(CGRect(x: 0, y: 0, width: 30, height: 10))
        let pixels = try XCTUnwrap(PhoneLook.pixels(try XCTUnwrap(white.makeImage())))
        XCTAssertEqual(pixels.shape, [1, 3, 256, 256])
        let values = pixels.dataPointer.bindMemory(to: Float.self, capacity: pixels.count)
        XCTAssertEqual((0 ..< pixels.count).map { values[$0] }.min() ?? 0, 1, accuracy: 1e-6)
    }

    func testNumbersGoAsTheServerTakesThem() throws {
        let sent = try XCTUnwrap(Data(base64Encoded: PhoneLook.encoded([1, -0.5])))
        XCTAssertEqual(Array(sent), [0, 0, 0x80, 0x3F, 0, 0, 0, 0xBF])
    }

    /// The released model, fetched as the server hands it on, numbers a
    /// work's picture as the server does: the same works lie nearest.
    func testThePhonesModelNumbersAsTheServerDoes() async throws {
        let (file, response) = try await URLSession.shared.download(from: try XCTUnwrap(URL(string: Self.release)))
        guard (response as? HTTPURLResponse)?.statusCode == 200 else {
            throw XCTSkip("the phone's model is not released yet")
        }
        let status = PhoneLook.Status(
            model: "look-model-siglip2-b16-phone-1", here: true, size: 0,
            sha256: try PhoneLook.sum(file), answers: true
        )
        try await PhoneLook.install(file, status: status)
        let ml = try MLModel(contentsOf: PhoneLook.compiled(status.model))
        let jpeg = try Data(contentsOf: try XCTUnwrap(Bundle.main.url(forResource: "aic_14598", withExtension: "jpg")))
        let phone = try PhoneLook.look(ml, try XCTUnwrap(PhoneLook.pixels(jpeg)))
        let raw = try XCTUnwrap(Data(base64Encoded: Self.serverAic))
        let server = raw.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) }
        XCTAssertEqual(server.count, PhoneLook.size)
        let near = zip(phone, server).reduce(Float(0)) { $0 + $1.0 * $1.1 }
        XCTAssertGreaterThan(near, 0.98, "the phone's numbers are not the server's")
    }
}
