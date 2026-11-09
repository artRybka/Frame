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
        XCTAssertEqual(ZoomTile.keptWidth(29952, 29952), 2560)
        XCTAssertEqual(ZoomTile.keptWidth(9984, 29952), 9984 * 2560 / 29952, accuracy: 0.01)
        XCTAssertEqual(ZoomTile.keptWidth(1000, 800), 1000)
        XCTAssertEqual(ZoomTile.keptWidth(nil, 800), 2560)
    }
}
