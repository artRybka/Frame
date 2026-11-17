import XCTest
@testable import Frame

/// Polish line breaking: no one-letter word left at a line's end
/// ("sztuki i / kolekcjoner", Mateusz 2026-11-17). The same cases as the
/// server's (server/tests/test_breaks.py).
final class TypographyTests: XCTestCase {
    private func check(_ text: String, _ expected: String, line: UInt = #line) {
        XCTAssertEqual(
            Typography.bound(text), expected.replacingOccurrences(of: "_", with: "\u{00A0}"), line: line
        )
    }

    func testOneLetterWordsGoWithTheNext() {
        check("krytyk sztuki i kolekcjoner", "krytyk sztuki i_kolekcjoner")
        check("Duret siedzi w ciemnym ubraniu", "Duret siedzi w_ciemnym ubraniu")
        check("a w domu z kotem", "a_w_domu z_kotem")
        check("Pisał o nich (i o innych)", "Pisał o_nich (i_o_innych)")
        check("„A potem” u niego", "„A_potem” u_niego")
        check("W gabinecie. Z kotem", "W_gabinecie. Z_kotem")
    }

    func testInitialsNumbersAndDashes() {
        check("J. M. W. Turner malował", "J._M._W._Turner malował")
        check("w 1868 r. i w XIX wieku", "w_1868_r. i_w_XIX_wieku")
        check("ok. 2000 px, 50 cm", "ok. 2000_px, 50_cm")
        check("Duret – krytyk", "Duret_– krytyk")
    }

    func testLettersInsideWordsStay() {
        check("kawa mała", "kawa mała")
        check("x-a b", "x-a b")
        check("", "")
    }

    func testOneCharacterForOneSoRangesHold() {
        let text = "Znał Maneta, Whistlera i Moneta, a sam zbierał ich prace w 1870 r."
        let bound = Typography.bound(text)
        XCTAssertEqual((bound as NSString).length, (text as NSString).length)
        XCTAssertEqual(Typography.unbound(bound), text)
        XCTAssertEqual(text.bound, bound)
    }

    /// Styled text keeps its styles where a space becomes a no-break one.
    func testAttributedTextKeepsItsStyles() {
        var bold = AttributedString("sztuki")
        bold.inlinePresentationIntent = .stronglyEmphasized
        let text = AttributedString("krytyk ") + bold + AttributedString(" i kolekcjoner")
        let bound = text.bound
        XCTAssertEqual(String(bound.characters), "krytyk sztuki i\u{00A0}kolekcjoner")
        XCTAssertEqual(bound.runs.count, text.runs.count)
        let boldRun = bound.runs.first { $0.inlinePresentationIntent == .stronglyEmphasized }
        XCTAssertEqual(boldRun.map { String(bound[$0.range].characters) }, "sztuki")
    }

    /// A sentence written in the code goes through `Text(bound:)`: SwiftUI's
    /// own `Text("…")` would leave its "i" or "w" at a line's end, and no
    /// one place can bind it (iOS 26 never asks the bundle for it).
    func testNoSentenceInTheCodeIsShownUnbound() throws {
        let sources = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Frame")
        guard FileManager.default.fileExists(atPath: sources.path),
              let files = FileManager.default.enumerator(at: sources, includingPropertiesForKeys: nil)
        else { throw XCTSkip("sources not next to the tests") }
        // A plain literal: no interpolation, no Markdown (which needs Text's own init).
        let literal = try NSRegularExpression(pattern: #"(?<![\w.])Text\("([^"\\\n*`_\[]*)"\)"#)
        var unbound: [String] = []
        for case let file as URL in files where file.pathExtension == "swift" {
            let source = try String(contentsOf: file, encoding: .utf8)
            let whole = NSRange(source.startIndex..., in: source)
            for match in literal.matches(in: source, range: whole) {
                guard let range = Range(match.range(at: 1), in: source) else { continue }
                let text = String(source[range])
                if Typography.bound(text) != text { unbound.append("\(file.lastPathComponent): \(text)") }
            }
        }
        XCTAssertEqual(unbound, [], "use Text(bound: \"…\")")
    }
}
