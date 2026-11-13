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

    /// Return (and the marked row): two words or more searched by how the
    /// works look while the server can, an artist's name as the artist
    /// (Mateusz 2026-11-13).
    func testReturnPicksTheMarkedRow() {
        let lookup = TermLookup()
        XCTAssertNil(lookup.chosen)
        lookup.text = " mglisty poranek "
        XCTAssertEqual(lookup.chosen, SearchToken(kind: "word", key: "mglisty poranek", name: "mglisty poranek"))
        lookup.looks = true
        XCTAssertEqual(lookup.chosen, SearchToken.look("mglisty poranek"))
        XCTAssertEqual(lookup.chosen?.kindName, "Wygląd")
        lookup.text = "mgła"
        XCTAssertEqual(lookup.chosen?.kind, "word")
        XCTAssertTrue(TermLookup.isName("Claude Monet", typed: "claude monet"))
        XCTAssertTrue(TermLookup.isName("Claude Monet", typed: "monet"))
        XCTAssertTrue(TermLookup.isName("Vincent van Gogh", typed: "van gogh"))
        XCTAssertTrue(TermLookup.isName("Gogh, Vincent van", typed: "gogh"))
        XCTAssertFalse(TermLookup.isName("Claude Monet", typed: "claude"))
        XCTAssertFalse(TermLookup.isName("Claude Monet", typed: "mon"))

        // A work's title typed: its works ("Tytuł"), before a look; one the
        // words are only part of is a row, not Return's.
        let starry = TermHit(kind: "title", key: "Gwiaździsta noc", name: "Gwiaździsta noc", item: "met:1", exact: true)
        let night = TermHit(kind: "title", key: "Noc", name: "Noc", item: "met:2", exact: false)
        XCTAssertNil(TermLookup.typedTitle(in: [night]))
        XCTAssertEqual(TermLookup.typedTitle(in: [night, starry]), SearchToken.title("Gwiaździsta noc"))
        XCTAssertEqual(SearchToken.title("Noc").kindName, "Tytuł")
        var titled = PlaylistRules()
        titled.setTokens([SearchToken.title("Gwiaździsta noc")])
        XCTAssertEqual(titled.title, "Gwiaździsta noc")
        XCTAssertFalse(titled.isEmpty)
        XCTAssertEqual(LibraryQuery(rules: titled).title, "Gwiaździsta noc")
        XCTAssertEqual(titled.tokens(names: [:]), [SearchToken.title("Gwiaździsta noc")])

        // The look is a chip of the rules: the groups narrow it, a playlist keeps it.
        var rules = PlaylistRules(terms: ["technique:painting"])
        rules.setTokens(rules.tokens(names: [:]) + [SearchToken.look("mglisty poranek")])
        XCTAssertEqual(rules.look, "mglisty poranek")
        XCTAssertEqual(rules.terms, ["technique:painting"])
        XCTAssertEqual(LibraryQuery(rules: rules).look, "mglisty poranek")
        XCTAssertEqual(rules.tokens(names: [:]).last, SearchToken.look("mglisty poranek"))
        rules.setTokens([])
        XCTAssertTrue(rules.isEmpty)
    }

    func testFoldingIgnoresCaseAndPolishLetters() {
        XCTAssertEqual(TermLookup.fold("Łódź"), "lodz")
        XCTAssertEqual(TermLookup.fold("Chełmoński"), "chelmonski")
    }
}
