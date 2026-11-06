import XCTest
@testable import Frame

final class ArtGlowTests: XCTestCase {
    /// The whole picture is lifted evenly: white goes to the gain, a mid
    /// grey by the same factor in linear light, black stays black.
    func testTheWholePictureIsLiftedEvenly() throws {
        let width = 3, height = 1
        let bytes: [UInt8] = [255, 255, 255, 255, 128, 128, 128, 255, 0, 0, 0, 255]
        let space = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
        let provider = try XCTUnwrap(CGDataProvider(data: Data(bytes) as CFData))
        let source = try XCTUnwrap(CGImage(width: width, height: height, bitsPerComponent: 8, bitsPerPixel: 32,
                                           bytesPerRow: width * 4, space: space,
                                           bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.noneSkipLast.rawValue),
                                           provider: provider, decode: nil, shouldInterpolate: false,
                                           intent: .defaultIntent))
        let lit = try XCTUnwrap(ArtGlow.render(source, gain: 1.6))
        XCTAssertTrue(lit.colorSpace?.name == CGColorSpace.extendedLinearSRGB)
        let data = try XCTUnwrap(lit.dataProvider?.data) as Data
        let row = lit.bytesPerRow
        func red(_ x: Int) -> Float {
            data.withUnsafeBytes { Float($0.load(fromByteOffset: x * lit.bitsPerPixel / 8 + 0 * row, as: Float16.self)) }
        }
        XCTAssertEqual(red(0), 1.6, accuracy: 0.02)
        let grey: Float = pow((128 / 255 + 0.055) / 1.055, 2.4)
        XCTAssertEqual(red(1) / grey, 1.6, accuracy: 0.03)
        XCTAssertEqual(red(2), 0, accuracy: 0.001)
    }

    func testTheGainReadsAsPolishWrites() {
        XCTAssertEqual(ArtGlow.label(1.6), "1,6×")
        XCTAssertTrue(ArtGlow.gains.contains(ArtGlow.defaultGain))
    }
}
