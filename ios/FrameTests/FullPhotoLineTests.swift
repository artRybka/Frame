import XCTest
@testable import Frame

/// The line under "Pełny kadr" (Mateusz 2026-11-14): what was around the
/// work, the backdrop only when alone, each sentence from its own line, no
/// "i" at a line's end and no last word alone.
final class FullPhotoLineTests: XCTestCase {
    private let hard = "\u{00A0}"

    func testTheBackdropIsSaidOnlyWhenAlone() {
        XCTAssertEqual(Cut(around: ["backdrop", "easel"]).aroundText, "na sztaludze")
        XCTAssertEqual(Cut(around: ["backdrop"]).aroundText, "na tle")
        XCTAssertEqual(Cut(around: ["easel", "frame"]).aroundText, "w ramie i na sztaludze")
    }

    func testEachSentenceHasItsLineAndNoWordIsLeftAlone() {
        let line = Cut.fullPhotoLine(around: "w ramie i na sztaludze", cropped: true)
        XCTAssertEqual(
            line,
            "Muzeum sfotografowało dzieło w\(hard)ramie i\(hard)na\(hard)sztaludze.\n"
                + "Prezentowane jest wykadrowane\(hard)dzieło."
        )
    }

    func testNothingCutSaysOnlyWhatWasAround() {
        XCTAssertEqual(Cut.fullPhotoLine(around: "", cropped: false), "Muzeum sfotografowało dzieło z\(hard)otoczeniem.")
    }
}

/// A work on paper (Mateusz 2026-11-14 22:36–22:42): named by its
/// technique, shown "z marginesem" or "bez marginesu".
final class PaperLineTests: XCTestCase {
    private let hard = "\u{00A0}"

    func testThePastelIsNoPrint() {
        XCTAssertEqual(PaperWork(medium: "pastel on paper").name, "pastel")
        XCTAssertEqual(PaperWork(medium: "Lithograph").name, "odbitka")
        XCTAssertEqual(PaperWork(medium: "akwarela, ołówek, papier").name, "akwarela")
        XCTAssertEqual(PaperWork(medium: "graphite on paper").name, "rysunek")
        XCTAssertEqual(PaperWork(medium: "").name, "dzieło")
        XCTAssertEqual(PaperWork(medium: "", around: ["page_text"]).name, "ilustracja")
    }

    func testTheLineSaysWhatIsShown() {
        let cut = Cut(plate: [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]], around: ["paper_margin"])
        XCTAssertEqual(
            cut.paperLine(medium: "pastel on paper"),
            "Muzeum sfotografowało pastel z\(hard)marginesem\(hard)kartki.\n"
                + "Prezentowany jest pastel bez\(hard)marginesu."
        )
        // Its plate not known yet: the sheet is shown.
        let print = Cut(around: ["backdrop", "mount", "paper_margin"])
        XCTAssertEqual(
            print.paperLine(medium: "etching"),
            "Muzeum sfotografowało odbitkę w\(hard)passe-partout i\(hard)z\(hard)marginesem\(hard)kartki.\n"
                + "Prezentowana jest odbitka z\(hard)marginesem."
        )
    }
}
