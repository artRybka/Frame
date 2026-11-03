import XCTest
@testable import Frame

/// "Tytuł w oryginale": holding a Polish title shows the source's own,
/// and only when there is a different one.
final class TitlePeekTests: XCTestCase {
    func testDifferentTitleIsShown() {
        XCTAssertEqual(
            OriginalTitle.of("Young Woman with a Water Pitcher", shown: "Młoda kobieta z dzbanem"),
            "Young Woman with a Water Pitcher"
        )
    }

    func testSameOrEmptyTitleShowsNothing() {
        // Polish museums: the Polish title is the museum's.
        XCTAssertNil(OriginalTitle.of("Bitwa pod Grunwaldem", shown: "Bitwa pod Grunwaldem"))
        XCTAssertNil(OriginalTitle.of("nighthawks ", shown: "Nighthawks"))
        XCTAssertNil(OriginalTitle.of("  ", shown: "Bez tytułu"))
    }

    func testGlintStartsAndEndsOffTheTitle() {
        let first = Glint.band(at: 0)
        let last = Glint.band(at: 1)
        XCTAssertLessThanOrEqual(first.end, 0)
        XCTAssertGreaterThanOrEqual(last.start, 1)
        let middle = Glint.band(at: 0.5)
        XCTAssertEqual((middle.start + middle.end) / 2, 0.5, accuracy: 0.0001)
    }
}
