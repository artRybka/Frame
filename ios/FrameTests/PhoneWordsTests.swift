import XCTest

@testable import Frame

/// Which Szukaj words the phone translates itself (`PhoneWords`).
final class PhoneWordsTests: XCTestCase {
    func testPolishLettersAreAlwaysPolish() {
        XCTAssertTrue(PhoneWords.mayBePolish("żaglowiec"))
        XCTAssertTrue(PhoneWords.mayBePolish("zimowy pejzaż"))
        XCTAssertTrue(PhoneWords.mayBePolish("Łódź"))
    }

    func testNoWordsAreNotTranslated() {
        XCTAssertFalse(PhoneWords.mayBePolish("1889"))
        XCTAssertFalse(PhoneWords.mayBePolish("  "))
        XCTAssertFalse(PhoneWords.mayBePolish(String(repeating: "a", count: 81)))
    }

    func testFoldedAsTheServerFoldsThem() {
        XCTAssertEqual(PhoneWords.fold("  Stara   KOBIETA "), "stara kobieta")
        XCTAssertEqual(PhoneWords.fold("Pejzaż"), "pejzaz")
    }
}
