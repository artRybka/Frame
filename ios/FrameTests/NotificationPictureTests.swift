import UIKit
import XCTest
@testable import Frame

final class NotificationPictureTests: XCTestCase {
    private let server = URL(string: "http://192.168.1.5:8099/push/picture?id=met%3A7&s=ab")!
    private let museum = URL(string: "https://images.metmuseum.org/ul-small.jpg")!
    private let jpeg = Data([0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10])

    /// The server sends `"pictures": [own, museum]` (notifications.py `picture_urls`).
    func testTheAddressesComeInTheServersOrder() {
        let info: [AnyHashable: Any] = [
            "kind": "changed",
            "pictures": [server.absoluteString, "file:///etc/passwd", 7, museum.absoluteString],
        ]
        XCTAssertEqual(NotificationPicture.urls(in: info), [server, museum])
        XCTAssertEqual(NotificationPicture.urls(in: ["kind": "battery"]), [])
    }

    func testOnlyAPictureIsAttached() throws {
        XCTAssertEqual(NotificationPicture.attachable(jpeg)?.ext, "jpg")
        XCTAssertEqual(NotificationPicture.attachable(Data([0x89, 0x50, 0x4E, 0x47, 0x0D]))?.ext, "png")
        XCTAssertNil(NotificationPicture.attachable(Data("<html>Not found</html>".utf8)))
        XCTAssertNil(NotificationPicture.attachable(Data()))
        // Another kind UIKit reads (here a TIFF) becomes a JPEG.
        let tiff = try XCTUnwrap(Self.tiff())
        let converted = try XCTUnwrap(NotificationPicture.attachable(tiff))
        XCTAssertEqual(converted.ext, "jpg")
        XCTAssertEqual(Array(converted.data.prefix(2)), [0xFF, 0xD8])
    }

    /// Away from home the server only times out: the museum's picture comes.
    func testTheMuseumsPictureWhenTheServerIsOutOfReach() async {
        let jpeg = jpeg
        let museum = museum
        let picture = await NotificationPicture.load([server, museum]) { url in
            url == museum ? jpeg : nil
        }
        XCTAssertEqual(picture?.data, jpeg)
    }

    /// At home the server's thumbnail wins, even when the museum is quicker.
    func testTheServersPictureWinsWhenItAnswers() async {
        let own = Data([0xFF, 0xD8, 0xFF, 0x01])
        let server = server
        let jpeg = jpeg
        let picture = await NotificationPicture.load([server, museum]) { url in
            if url == server {
                try? await Task.sleep(for: .milliseconds(200))
                return own
            }
            return jpeg
        }
        XCTAssertEqual(picture?.data, own)
    }

    func testNothingLoadsNothingIsAttached() async {
        let picture = await NotificationPicture.load([server, museum]) { _ in Data("nope".utf8) }
        XCTAssertNil(picture)
    }

    private static func tiff() -> Data? {
        let image = UIGraphicsImageRenderer(size: CGSize(width: 4, height: 4)).image { context in
            UIColor.red.setFill()
            context.fill(CGRect(x: 0, y: 0, width: 4, height: 4))
        }
        guard let cg = image.cgImage else { return nil }
        let data = NSMutableData()
        guard let dest = CGImageDestinationCreateWithData(data, "public.tiff" as CFString, 1, nil) else { return nil }
        CGImageDestinationAddImage(dest, cg, nil)
        return CGImageDestinationFinalize(dest) ? data as Data : nil
    }
}
