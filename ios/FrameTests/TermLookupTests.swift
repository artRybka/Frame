import XCTest
@testable import Frame

/// Suggestions while typing: something at once, the server's counts after.
@MainActor
final class TermLookupTests: XCTestCase {
    func testEveryLetterShowsAGuessAtOnceAndTheAnswerAfter() async throws {
        let lookup = TermLookup()
        lookup.text = "impre"
        let asking = Task { await lookup.lookUp(DemoBackend(), vocabulary: DemoDiscover.terms) }
        await until { !lookup.hits.isEmpty }
        // Before the server answers: the vocabulary's term and the words, not counted.
        XCTAssertEqual(lookup.hits.map(\.key), ["style:impressionism", "impre"])
        XCTAssertEqual(lookup.uncounted, Set(lookup.hits.map(\.id)))
        XCTAssertFalse(lookup.typed()?.fromMuseums ?? true)
        await asking.value
        XCTAssertTrue(lookup.uncounted.isEmpty)
        XCTAssertEqual(lookup.hits.last?.key, "impre")

        // The next letter keeps what still fits, with its count.
        let impressionism = try XCTUnwrap(lookup.hits.first { $0.key == "style:impressionism" })
        lookup.text = "impres"
        let next = Task { await lookup.lookUp(DemoBackend(), vocabulary: DemoDiscover.terms) }
        await until { lookup.hits.last?.key == "impres" }
        let kept = try XCTUnwrap(lookup.hits.first { $0.key == "style:impressionism" })
        XCTAssertEqual(kept.count, impressionism.count)
        XCTAssertFalse(lookup.uncounted.contains(kept.id))
        XCTAssertTrue(lookup.uncounted.contains("word:impres"))
        next.cancel()
        await next.value
        // Cut short by the next letter: the guess stays, no empty list.
        XCTAssertFalse(lookup.hits.isEmpty)
    }

    /// Lets the lookup's task run up to its first wait.
    private func until(_ done: () -> Bool) async {
        for _ in 0 ..< 200 where !done() {
            await Task.yield()
        }
    }

    /// An open group with a list takes the field's words; closed, the
    /// search's words come back.
    func testAGroupNarrowedByTheFieldGivesTheSearchsWordsBack() async {
        let lookup = TermLookup()
        lookup.text = "rembrandt"
        lookup.narrow(.museum)
        XCTAssertEqual(lookup.text, "")
        XCTAssertEqual(lookup.prompt("Artysta albo słowo"), "Muzeum albo miasto")
        lookup.text = "krak"
        // No suggestions for a group's words, nor asking the server.
        XCTAssertFalse(lookup.suggesting(true))
        await lookup.lookUp(DemoBackend(), vocabulary: DemoDiscover.terms)
        XCTAssertTrue(lookup.hits.isEmpty)
        // Another group with a list: empty again, the search's words still held.
        lookup.narrow(.style)
        XCTAssertEqual(lookup.text, "")
        XCTAssertEqual(lookup.prompt("Artysta albo słowo"), "Szukaj stylu")
        lookup.narrow(nil)
        XCTAssertEqual(lookup.text, "rembrandt")
        XCTAssertEqual(lookup.prompt("Artysta albo słowo"), "Artysta albo słowo")
        XCTAssertTrue(lookup.suggesting(true))

        // The X empties the field with the held words too.
        lookup.narrow(.subject)
        lookup.text = "koń"
        lookup.clear()
        lookup.narrow(nil)
        XCTAssertEqual(lookup.text, "")
        // Groups without a list never take the field (Epoka's named periods
        // are a list).
        XCTAssertEqual(TermFacet.period.fieldPrompt, "Okres albo rok")
        XCTAssertNil(TermFacet.color.fieldPrompt)
        XCTAssertNil(TermFacet.technique.fieldPrompt)
    }

    func testFoldingIgnoresCaseAndPolishLetters() {
        XCTAssertEqual(TermLookup.fold("Łódź"), "lodz")
        XCTAssertEqual(TermLookup.fold("Chełmoński"), "chelmonski")
    }
}
