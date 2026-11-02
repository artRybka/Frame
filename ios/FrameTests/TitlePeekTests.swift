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
}
