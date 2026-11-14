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
