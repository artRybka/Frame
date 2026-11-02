import UIKit
import XCTest
@testable import Frame

/// The folded description on "Teraz" ends on a full sentence, never on a
/// word cut in half with "…".
final class SentenceClipTests: XCTestCase {
    private let boat = """
    Praca przedstawia łódź rybacką na morzu. Na pierwszym planie, po lewej stronie, płynie \
    drewniana łódź z dużym białym żaglem, a w niej widać siedzącą postać z wiosłem. Dalej, bliżej \
    horyzontu, unoszą się kolejne żaglowce o jasnych żaglach. Niebo zajmuje górną część obrazu, \
    a fale oddane są krótkimi, gęstymi pociągnięciami pędzla.
    """

    private func styled(_ text: String) -> NSAttributedString {
        let base = UIFont.systemFont(ofSize: 16)
        let font = base.fontDescriptor.withDesign(.serif).map { UIFont(descriptor: $0, size: 16) } ?? base
        let paragraph = NSMutableParagraphStyle()
        paragraph.lineSpacing = 4
        return NSAttributedString(string: text, attributes: [.font: font, .paragraphStyle: paragraph])
    }

    func testSentenceEndsAreFullStops() {
        let text = "Pierwsze zdanie. Czy drugie? Tak! Namalowany ok. 1888 r. w Arles. Bez kropki"
        let ns = text as NSString
        let ends = SentenceClip.sentenceEnds(text).map { ns.substring(to: $0) }
        XCTAssertEqual(ends.first, "Pierwsze zdanie.")
        XCTAssertTrue(ends.contains("Pierwsze zdanie. Czy drugie? Tak!"))
        XCTAssertTrue(ends.contains("Pierwsze zdanie. Czy drugie? Tak! Namalowany ok. 1888 r. w Arles."))
        // The unfinished last sentence is no place to stop.
        XCTAssertFalse(ends.contains(text))
    }

    func testAFoldedDescriptionEndsOnTheLastSentenceThatFits() {
        let full = styled(boat)
        for width: CGFloat in [300, 345, 400] {
            let clip = SentenceClip.clip(full, width: width, lines: 5)
            let shown = clip.text.string
            XCTAssertEqual(clip.lines, 0, "\(width)")
            XCTAssertTrue(boat.hasPrefix(shown), "\(width)")
            XCTAssertTrue(shown.hasSuffix("."), "\(width): \(shown)")
            XCTAssertLessThan(shown.count, boat.count, "\(width)")
            XCTAssertLessThanOrEqual(SentenceClip.lineCount(clip.text, width: width), 5, "\(width)")
            // One sentence more would not fit.
            let next = SentenceClip.sentenceEnds(boat).first { $0 > (shown as NSString).length }
            if let next {
                let longer = full.attributedSubstring(from: NSRange(location: 0, length: next))
                XCTAssertGreaterThan(SentenceClip.lineCount(longer, width: width), 5, "\(width)")
            }
        }
    }

    func testAShortDescriptionIsShownWhole() {
        let full = styled("Praca przedstawia łódź rybacką na morzu.")
        let clip = SentenceClip.clip(full, width: 345, lines: 5)
        XCTAssertEqual(clip.text.string, full.string)
        XCTAssertEqual(clip.lines, 0)
    }

    func testALongFirstSentenceIsStillReadWhole() {
        // At this width the first sentence alone takes more than two lines.
        let full = styled(boat)
        let clip = SentenceClip.clip(full, width: 120, lines: 2, grace: 6)
        XCTAssertEqual(clip.text.string, "Praca przedstawia łódź rybacką na morzu.")
        XCTAssertEqual(clip.lines, 0)
    }

    func testTextWithoutFullStopsIsCutAsBefore() {
        let words = Array(repeating: "fale i żagle", count: 60).joined(separator: " ")
        let full = styled(words)
        let clip = SentenceClip.clip(full, width: 345, lines: 5)
        XCTAssertEqual(clip.text.string, words)
        XCTAssertEqual(clip.lines, 5)
    }
}
