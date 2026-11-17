import XCTest
@testable import Frame

/// "W ramie" on a work's card (Mateusz 2026-11-17, variant C): the button
/// is there only when the server says what is around the work, for the
/// picture its cut was set on.
final class FramedLookTests: XCTestCase {
    private func item(cut: [String: Any]?, picture: String? = nil) throws -> Item {
        let url = try XCTUnwrap(Bundle.main.url(forResource: "DemoFramed", withExtension: "json"))
        let file = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        var fields = try XCTUnwrap((file["items"] as? [[String: Any]])?.first)
        // The server always sends a cut's every field; the test names only those that matter.
        let base: [String: Any] = ["paper": true, "by": "auto", "aspect": 1.2, "picture": "", "around": [], "at": ""]
        fields["cut"] = cut.map { base.merging($0) { _, given in given } } ?? NSNull()
        if let picture {
            fields["sharper"] = ["url": "https://example.org/a.jpg", "item_id": picture, "source": "wmc", "museum": "Wikimedia Commons", "width": 2000, "height": 1500]
        }
        return try LiveBackend.decoder().decode(Item.self, from: JSONSerialization.data(withJSONObject: fields))
    }

    private let work: [[Double]] = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]

    func testTheFrameIsOfferedWithItsShapeAndTheWorksPlace() throws {
        let cut: [String: Any] = [
            "work": work, "aspect": 1.2, "framed_kind": "frame", "framed_aspect": 1.2,
            "framed_inner": [0.1, 0.12, 0.9, 0.88],
        ]
        let look = try XCTUnwrap(try item(cut: cut).framed)
        XCTAssertEqual(look.name, "W ramie")
        XCTAssertEqual(look.aspect, 1.2, accuracy: 1e-9)
        XCTAssertEqual(look.inner.minY, 0.12, accuracy: 1e-9)
        XCTAssertEqual(look.inner.height, 0.76, accuracy: 1e-9)
        XCTAssertEqual(FramedLook(kind: "mount", aspect: 1, inner: .zero).name, "W passe-partout")
        XCTAssertEqual(FramedLook(kind: "paper", aspect: 1, inner: .zero).name, "Z marginesem")
    }

    func testNothingAroundAnOlderServerOrAnotherPictureOffersNothing() throws {
        XCTAssertNil(try item(cut: nil).framed)
        XCTAssertNil(try item(cut: ["work": work, "aspect": 1.2]).framed)  // an older server
        XCTAssertNil(try item(cut: ["work": work, "aspect": 1.2, "framed_kind": ""]).framed)
        let other: [String: Any] = [
            "work": work, "aspect": 1.2, "framed_kind": "frame", "framed_aspect": 1.2,
            "framed_inner": [0.1, 0.1, 0.9, 0.9],
        ]
        XCTAssertNil(try item(cut: other, picture: "wmc:9").framed)  // cut set on the museum's own
    }
}
