import XCTest
@testable import Frame

/// The year at a title's end ("W oranżerii 1890") moves to the next line
/// whole: no break inside "ok. 1893–1894".
final class TitleYearTests: XCTestCase {
    func testAPlainYearStaysAsItIs() {
        XCTAssertEqual(TitleYear.unbroken("1890"), "1890")
    }

    func testSpacesAndDashesDoNotBreak() {
        let date = TitleYear.unbroken(" ok. 1893–1894 ")
        XCTAssertFalse(date.contains(" "))
        XCTAssertEqual(date, "ok.\u{00A0}1893\u{2060}–\u{2060}1894")
        XCTAssertEqual(TitleYear.unbroken("1665-1667"), "1665\u{2011}1667")
    }

    func testNoDateIsNothing() {
        XCTAssertEqual(TitleYear.unbroken("  "), "")
    }
}
