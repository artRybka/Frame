import XCTest
@testable import Frame

/// A work's picture became another photograph with no copy in its place
/// (its original kept from Commons while Paris Musées was down, the
/// thumbnail made again from it): the lists drop the thumbnail they kept
/// (Mateusz 2026-11-17: "Po wejściu zdjęcie się podmieniło. A miniatura
/// została stara").
final class PictureStampTests: XCTestCase {
    private func decoded<T: Decodable>(_ json: String) throws -> T {
        try LiveBackend.decoder().decode(T.self, from: Data(json.utf8))
    }

    private func work() async throws -> Item {
        let demo = DemoBackend()
        let themes = try await demo.themes()
        let page = try await demo.themePage(key: try XCTUnwrap(themes.first).key, page: 1)
        var item = try XCTUnwrap(page.items.first).item
        item.sharper = nil
        item.cut = nil
        item.cleaned = nil
        item.pictureStamp = nil
        return item
    }

    func testTheServerSaysIt() throws {
        let view: SharperView = try decoded(#"{"status": "fine", "picture_stamp": "1a2b3c4d5e6f"}"#)
        XCTAssertEqual(view.pictureStamp, "1a2b3c4d5e6f")
        let old: SharperView = try decoded(#"{"status": "fine"}"#)
        XCTAssertNil(old.pictureStamp)
    }

    func testTheStampIsAnotherPicture() async throws {
        let first = try await work()
        var other = first
        other.pictureStamp = "1a2b3c4d5e6f"
        XCTAssertEqual(first.pictureVersion, "")
        XCTAssertNotEqual(other.pictureVersion, first.pictureVersion)
        XCTAssertEqual(other.summary.pictureVersion, other.pictureVersion)
        // The card's original follows the stamp too: a printed page's scan
        // made again without its screen shows at once (Mateusz 2026-11-26).
        XCTAssertNotEqual(other.originalRef, first.originalRef)
        // With a copy in its place the stamp stays beside the copy's id.
        other.sharper = SharperCopy(url: "https://x/2.jpg", itemId: "wmc:9", source: "commons", museum: "Wikimedia Commons", width: 3000, height: 2000)
        XCTAssertEqual(other.pictureVersion, "wmc:9@1a2b3c4d5e6f")
    }

    /// The list loaded before the card learnt of it follows the card: the
    /// stamp, and no pixel count of the other photograph.
    @MainActor
    func testAListLoadedBeforeFollowsTheStamp() async throws {
        let plain = try await work()
        var tile = plain.summary
        tile.lowSide = 300
        var stamped = plain
        stamped.pictureStamp = "1a2b3c4d5e6f"
        let model = AppModel()
        model.cardShows(stamped)
        let shown = model.asOnCard(tile)
        XCTAssertEqual(shown.pictureStamp, "1a2b3c4d5e6f")
        XCTAssertEqual(shown.pictureVersion, stamped.pictureVersion)
        XCTAssertNil(shown.lowSide)
        XCTAssertNotEqual(shown.pictureVersion, tile.pictureVersion)  // its tile asks again
    }
}
