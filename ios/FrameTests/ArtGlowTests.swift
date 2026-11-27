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

    /// Nothing at first, then evenly brighter, all of it by a second.
    func testTheWayInTakesAboutASecond() {
        XCTAssertEqual(ArtGlow.WayIn.shown(at: 0), 0)
        XCTAssertEqual(ArtGlow.WayIn.shown(at: 0.15), 0)
        XCTAssertEqual(ArtGlow.WayIn.shown(at: 0.575), 0.5, accuracy: 0.001)
        XCTAssertEqual(ArtGlow.WayIn.shown(at: 1), 1)
    }

    func testTheGainReadsAsPolishWrites() {
        XCTAssertEqual(ArtGlow.label(1.6), "1,6×")
        XCTAssertTrue(ArtGlow.gains.contains(ArtGlow.defaultGain))
    }

    private func picture(_ greys: [UInt8]) throws -> CGImage {
        var bytes: [UInt8] = []
        for grey in greys { bytes += [grey, grey, grey, 255] }
        let space = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
        let provider = try XCTUnwrap(CGDataProvider(data: Data(bytes) as CFData))
        return try XCTUnwrap(CGImage(width: greys.count, height: 1, bitsPerComponent: 8, bitsPerPixel: 32,
                                     bytesPerRow: greys.count * 4, space: space,
                                     bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.noneSkipLast.rawValue),
                                     provider: provider, decode: nil, shouldInterpolate: false,
                                     intent: .defaultIntent))
    }

    private func reds(_ lit: CGImage) throws -> [Float] {
        let data = try XCTUnwrap(lit.dataProvider?.data) as Data
        var reds: [Float] = []
        for x in 0..<lit.width {
            let half: Float16 = data.withUnsafeBytes { $0.load(fromByteOffset: x * lit.bitsPerPixel / 8, as: Float16.self) }
            reds.append(Float(half))
        }
        return reds
    }

    /// The page's white stays close to the page (at most 1.25×), a dark
    /// grey has the whole gain; one white among ten is no reason to lower it.
    func testTheLightsStayNearThePage() throws {
        let lit = try XCTUnwrap(ArtGlow.lit(try picture([255] + [UInt8](repeating: 60, count: 9)), gain: 1.6))
        XCTAssertTrue(lit.colorSpace?.name == CGColorSpace.extendedLinearSRGB)
        let red = try reds(lit)
        XCTAssertLessThanOrEqual(red[0], 1.251)
        XCTAssertGreaterThan(red[0], 1.1)
        let grey: Float = pow((60 / 255 + 0.055) / 1.055, 2.4)
        XCTAssertEqual(red[1] / grey, 1.6, accuracy: 0.03)
    }

    /// A picture all of white paper is lit no brighter than the ceiling.
    func testWhitePaperIsNoLightbox() throws {
        let lit = try XCTUnwrap(ArtGlow.lit(try picture([UInt8](repeating: 255, count: 10)), gain: 2))
        for red in try reds(lit) { XCTAssertEqual(red, 1, accuracy: 0.01) }
    }

    /// A picture all of white paper is hardly lifted, a dark one fully.
    func testTheGainFitsThePicture() {
        XCTAssertEqual(ArtGlow.fitted(1.6, lightness: [Float](repeating: 1, count: 100), share: 0.05), 1, accuracy: 0.01)
        XCTAssertEqual(ArtGlow.fitted(1.6, lightness: [Float](repeating: 0.3, count: 100), share: 0.05), 1.6)
        let half = [Float](repeating: 0.8, count: 50) + [Float](repeating: 0.2, count: 50)
        XCTAssertEqual(ArtGlow.fitted(1.6, lightness: half, share: 0.05), 1.25, accuracy: 0.01)
    }

    func testTheShoulderNeverPassesItsCeiling() {
        XCTAssertEqual(ArtGlow.eased(0.5, knee: 0.9, ceiling: 1.25), 0.5)
        XCTAssertLessThan(ArtGlow.eased(3, knee: 0.9, ceiling: 1.25), 1.25)
        XCTAssertGreaterThan(ArtGlow.eased(1.6, knee: 0.9, ceiling: 1.25), 1.1)
    }
}
