import XCTest
@testable import Frame

/// "Tytuł w oryginale": holding a Polish title shows the source's own,
/// and only when there is a different one.
final class TitlePeekTests: XCTestCase {
    func testDifferentTitleIsShown() {
        XCTAssertEqual(
            TitlePeekNote.original("Young Woman with a Water Pitcher", shown: "Młoda kobieta z dzbanem"),
            "Young Woman with a Water Pitcher"
        )
    }

    func testSameOrEmptyTitleShowsNothing() {
        // Polish museums: the Polish title is the museum's.
        XCTAssertNil(TitlePeekNote.original("Bitwa pod Grunwaldem", shown: "Bitwa pod Grunwaldem"))
        XCTAssertNil(TitlePeekNote.original("nighthawks ", shown: "Nighthawks"))
        XCTAssertNil(TitlePeekNote.original("  ", shown: "Bez tytułu"))
    }

    func testNoteNamesNonMuseumSources() {
        XCTAssertEqual(TitlePeekNote.text("met"), "Tytuł z muzeum")
        XCTAssertEqual(TitlePeekNote.text("wmc"), "Tytuł ze źródła, Wikimedia Commons")
    }
}
