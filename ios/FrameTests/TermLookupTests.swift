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

    /// Return (and the marked row): an artist's name as the artist
    /// (Mateusz 2026-11-13), else the words, "Słowa", also while the server
    /// can search by how works look: what they show is the words' too
    /// (Mateusz 2026-11-19).
    func testReturnPicksTheMarkedRow() {
        let lookup = TermLookup()
        XCTAssertNil(lookup.chosen)
        lookup.text = " mglisty poranek "
        XCTAssertEqual(lookup.chosen, SearchToken(kind: "word", key: "mglisty poranek", name: "mglisty poranek"))
        lookup.looks = true
        XCTAssertEqual(lookup.chosen, SearchToken(kind: "word", key: "mglisty poranek", name: "mglisty poranek"))
        XCTAssertEqual(lookup.chosen?.kindName, "Słowa")
        // An older playlist's look keeps its name.
        XCTAssertEqual(SearchToken.look("mglisty poranek").kindName, "Wygląd")
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
        // A title comes with its artist's chip: his work, not every title
        // with the word (Mateusz 2026-11-13, "Słoneczniki").
        let sunflowers = TermHit(kind: "title", key: "Słoneczniki", name: "Słoneczniki",
                                 detail: "Vincent van Gogh", item: "wmc:1", exact: true)
        XCTAssertEqual(TermLookup.artist(of: SearchToken.title("Słoneczniki"), in: [sunflowers]),
                       [SearchToken(kind: "artist", key: "Vincent van Gogh", name: "Vincent van Gogh")])
        XCTAssertEqual(TermLookup.artist(of: SearchToken.title("Noc"), in: [night]), [])
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

    /// "Szukaj podobnych" on a work's card: Szukaj's chip, the work's title
    /// by its mark of two pictures (Mateusz 2026-11-19),
    /// kept in the rules (Mateusz 2026-11-13).
    func testTheWorksLikeOneAreAChipOfTheRules() {
        var rules = PlaylistRules(terms: ["period:baroque"])
        let chip = SearchToken.like("met:1", title: "Słoneczniki")
        XCTAssertEqual(chip.name, "Słoneczniki")
        XCTAssertEqual(chip.icon, "photo.on.rectangle.angled")
        XCTAssertEqual(chip.markKind, SearchToken.likeWorkMark)
        XCTAssertEqual(GroupMark.Mark(kind: chip.markKind), .framed)
        rules.setTokens(rules.tokens(names: [:]) + [chip])
        XCTAssertEqual(rules.like, "met:1")
        XCTAssertEqual(rules.terms, ["period:baroque"])
        XCTAssertEqual(LibraryQuery(rules: rules).like, "met:1")
        let names = [SearchToken.likeName("met:1"): "Słoneczniki"]
        XCTAssertEqual(rules.tokens(names: names).last?.name, "Słoneczniki")
        XCTAssertEqual(rules.tokens(names: [:]).last?.name, "Podobne do dzieła")
        rules.setTokens([chip])
        XCTAssertFalse(rules.isEmpty)
        rules.setTokens([])
        XCTAssertTrue(rules.isEmpty)
    }

    /// "Szukaj zdjęciem" in Szukaj's own list (Mateusz 2026-11-15): the
    /// photograph's key is the chip "Zdjęcie" by its mark (Mateusz
    /// 2026-11-19), kept like a work's.
    func testAPhotographSearchedIsAChipOfTheRules() {
        var rules = PlaylistRules(terms: ["period:baroque"])
        let chip = SearchToken.like("photo:0a1b", title: "")
        XCTAssertTrue(SearchToken.isPhoto(chip.key))
        XCTAssertFalse(SearchToken.isPhoto("met:1"))
        XCTAssertEqual(chip.name, "Zdjęcie")
        XCTAssertEqual(chip.icon, "photo.on.rectangle.angled")
        XCTAssertEqual(chip.markKind, SearchToken.likeKind)
        XCTAssertNil(GroupMark.Mark(kind: chip.markKind))
        rules.setTokens(rules.tokens(names: [:]) + [chip])
        XCTAssertEqual(rules.like, "photo:0a1b")
        XCTAssertEqual(rules.tokens(names: [:]).last?.name, "Zdjęcie")
        XCTAssertEqual(LibraryQuery(rules: rules).like, "photo:0a1b")
    }

    /// "Słowa" (Mateusz 2026-11-19): words put in ask the server for what
    /// the works show too; a playlist saved with words alone keeps them so
    /// until words are added. The museums are asked two words or more as a
    /// look, one word as it is.
    func testWordsPutInAreSlowa() {
        var rules = PlaylistRules()
        rules.setTokens([SearchToken(kind: "word", key: "mglisty poranek", name: "mglisty poranek")])
        XCTAssertTrue(rules.seen)
        XCTAssertTrue(LibraryQuery(rules: rules).seen)
        XCTAssertEqual(LiveBackend.museumWords(rules).words, "")
        XCTAssertEqual(LiveBackend.museumWords(rules).look, "mglisty poranek")
        rules.setTokens([])
        XCTAssertFalse(rules.seen)

        var one = PlaylistRules()
        one.setTokens([SearchToken(kind: "word", key: "mgła", name: "mgła")])
        XCTAssertTrue(one.seen)
        XCTAssertEqual(LiveBackend.museumWords(one).words, "mgła")
        XCTAssertEqual(LiveBackend.museumWords(one).look, "")

        // Saved before: the words alone, also after another chip; not after
        // another word.
        var saved = PlaylistRules(query: "\"wielka fala\"")
        saved.setTokens(saved.tokens(names: [:]) + [SearchToken(kind: "artist", key: "Hokusai", name: "Hokusai")])
        XCTAssertFalse(saved.seen)
        XCTAssertEqual(LiveBackend.museumWords(saved).words, "\"wielka fala\"")
        saved.setTokens(saved.tokens(names: [:]) + [SearchToken(kind: "word", key: "morze", name: "morze")])
        XCTAssertTrue(saved.seen)
    }

    /// The suggestions' order A (Mateusz 2026-11-19): the words typed, then
    /// artists, works, keywords and groups, each kind as the server sent it.
    func testTheSuggestionsComeInOrderA() {
        let hits = [
            TermHit(kind: "style", key: "style:post", name: "Postimpresjonizm"),
            TermHit(kind: "word", key: "słoneczniki van gogha", name: "słoneczniki van gogha"),
            TermHit(kind: "title", key: "Sypialnia", name: "Sypialnia", item: "wmc:1", exact: false),
            TermHit(kind: "artist", key: "Vincent van Gogh", name: "Vincent van Gogh"),
            TermHit(kind: "artist", key: "Theo van Gogh", name: "Theo van Gogh"),
            TermHit(kind: "word", key: "van gogh", name: "van gogh"),
        ]
        XCTAssertEqual(
            TermSuggestions.ordered(hits, typed: "van gogh").map(\.key),
            ["van gogh", "Vincent van Gogh", "Theo van Gogh", "Sypialnia", "słoneczniki van gogha", "style:post"]
        )
    }

    /// The museums' artists are artists like any other, and one that is an
    /// artist already suggested, spelled otherwise, is left out (Mateusz
    /// 2026-11-19: "Van gogh · Artysta z muzeów" under Vincent van Gogh).
    func testTheMuseumsArtistsAreNoOtherSpellingOfOneSuggested() {
        let hits = [TermHit(kind: "artist", key: "Vincent van Gogh", name: "Vincent van Gogh", count: 3)]
        let museums = [
            TermHit(kind: "artist", key: "Van gogh", name: "Van gogh"),
            TermHit(kind: "artist", key: "Gogh, Vincent van", name: "Gogh, Vincent van"),
            TermHit(kind: "artist", key: "Theo van Gogh", name: "Theo van Gogh"),
        ]
        XCTAssertEqual(TermSuggestions.museumArtists(museums, besides: hits).map(\.key), ["Theo van Gogh"])
    }

    func testFoldingIgnoresCaseAndPolishLetters() {
        XCTAssertEqual(TermLookup.fold("Łódź"), "lodz")
        XCTAssertEqual(TermLookup.fold("Chełmoński"), "chelmonski")
    }
}
