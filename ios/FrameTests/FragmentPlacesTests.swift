import XCTest
@testable import Frame

/// A Commons tile set's tiles laid on the whole in the full-screen viewer:
/// their places from the server, the width each comes in.
final class FragmentPlacesTests: XCTestCase {
    func testPlacesAreReadAndOlderServersHaveNone() throws {
        let decoder = LiveBackend.decoder()
        let older = try decoder.decode(FragmentsView.self, from: Data(#"{"whole": null, "fragments": []}"#.utf8))
        XCTAssertNil(older.places)
        let json = #"{"fragments": [], "places": [{"id": "wmc:1~p2", "x": 0.75, "y": 0, "w": 0.25, "h": 0.5}]}"#
        let view = try decoder.decode(FragmentsView.self, from: Data(json.utf8))
        XCTAssertEqual(view.places?.first?.unit, CGRect(x: 0.75, y: 0, width: 0.25, height: 0.5))
    }

    func testTilesComeInTheSizeTheServerKeeps() {
        XCTAssertEqual(ZoomTile.keptWidth(29952, 29952), 3840)
        XCTAssertEqual(ZoomTile.keptWidth(9984, 29952), 1280)
        XCTAssertEqual(ZoomTile.keptWidth(10000, 29952), 1282)  // whole pixels
        XCTAssertEqual(ZoomTile.keptWidth(1000, 800), 1000)
        XCTAssertEqual(ZoomTile.keptWidth(nil, 800), 3840)
    }

    func testTheCardTellsHowFarTheFullScreenZooms() {
        // Bosch's "Garden": 3840 px tiles, the widest a fifth of 157 841 px,
        // on a 393 pt wide phone at 3×.
        let across = ZoomTile.keptWidth(29952, 29952) / (29952 / 157_841)
        XCTAssertEqual(Int(ZoomTile.depth(across: across, shown: 393 * 3).rounded()), 17)
        XCTAssertEqual(ZoomTile.depth(across: 0, shown: 1179), 8)  // no tiles
        XCTAssertEqual(ZoomTile.depth(across: 1_000_000, shown: 1179), ZoomTile.deepestZoom)
    }
}
