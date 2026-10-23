import XCTest
@testable import Frame

final class FrameAPITests: XCTestCase {
    func testDecodesNowPlaying() throws {
        let json = """
        {
          "file_id": "A1B2C3D4E5F60718",
          "file_name": "A1B2C3D4E5F60718.png",
          "mime": "image/png",
          "size": 597000,
          "created": "2026-10-23T20:00:00+00:00",
          "title": "Kwitnące migdałowce",
          "description": "Vincent van Gogh, 1890",
          "source": "upload",
          "render": {"strategy": "dither"},
          "extra": {},
          "preview_url": "/api/previews/A1B2C3D4E5F60718.png"
        }
        """
        let now = try FrameAPI.makeDecoder().decode(NowPlaying.self, from: Data(json.utf8))
        XCTAssertEqual(now.fileId, "A1B2C3D4E5F60718")
        XCTAssertEqual(now.previewUrl, "/api/previews/A1B2C3D4E5F60718.png")
        XCTAssertEqual(now.title, "Kwitnące migdałowce")
    }

    func testRequestAddsBearerToken() throws {
        let api = FrameAPI(baseURL: URL(string: "http://frame.local:8099")!, token: "secret")
        let request = api.request("/api/now")
        XCTAssertEqual(request.url?.absoluteString, "http://frame.local:8099/api/now")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer secret")
    }

    func testMultipartBodyContainsFieldsAndFile() throws {
        var form = MultipartForm()
        form.addField("preset", "photo")
        form.addFile("file", filename: "a.jpg", mimeType: "image/jpeg", data: Data([0xFF, 0xD8]))
        let body = String(decoding: form.body(), as: UTF8.self)
        XCTAssertTrue(body.contains("name=\"preset\"\r\n\r\nphoto\r\n"))
        XCTAssertTrue(body.contains("filename=\"a.jpg\""))
        XCTAssertTrue(body.hasSuffix("--\(form.boundary)--\r\n"))
    }
}
