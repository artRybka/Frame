import UIKit
import XCTest
@testable import Frame

/// Elongated pictures keep their short side when downsampled: a handscroll
/// 24 times as long as it is tall came 500 × 21 px and its square tile was
/// a blur (Mateusz 2026-11-11).
final class WideThumbTests: XCTestCase {
    func testOrdinaryPicturesKeepTheLongSide() {
        XCTAssertEqual(ImageLoader.longSide(width: 4000, height: 3000, maxPixel: 500), 500)
        XCTAssertEqual(ImageLoader.longSide(width: 1000, height: 500, maxPixel: 500), 500)  // 2:1, the edge
    }

    func testElongatedPicturesKeepTheShortSide() {
        // Cleveland's print of "Flowers of Four Seasons", 24:1: whole.
        XCTAssertEqual(ImageLoader.longSide(width: 3400, height: 140, maxPixel: 500), 3400)
        // The server's thumbnail of a larger one: 250 px tall, not 21.
        XCTAssertEqual(ImageLoader.longSide(width: 7776, height: 320, maxPixel: 500), 6075)
        // Tall ones too.
        XCTAssertEqual(ImageLoader.longSide(width: 400, height: 1000, maxPixel: 500), 625)
        // Within the pixel budget.
        let long = ImageLoader.longSide(width: 60000, height: 1000, maxPixel: 500)
        XCTAssertLessThanOrEqual(long * long / 60, ImageLoader.wideArea * 1.001)
    }

    func testAScrollIsDownsampledThickEnoughForASquareTile() throws {
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let picture = UIGraphicsImageRenderer(size: CGSize(width: 7776, height: 320), format: format).image { context in
            UIColor.brown.setFill()
            context.fill(CGRect(x: 0, y: 0, width: 7776, height: 320))
        }
        let data = try XCTUnwrap(picture.jpegData(compressionQuality: 0.8))
        let image = try XCTUnwrap(ImageLoader.downsample(data, maxPixel: 500))
        XCTAssertEqual(image.size.height, 250, accuracy: 2)
        XCTAssertEqual(image.size.width, 6075, accuracy: 2)
    }
}
