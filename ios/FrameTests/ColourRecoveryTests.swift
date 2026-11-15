import XCTest
@testable import Frame

/// "Korekta barw" (`ColourRecovery`, `Cleaned`): what a work is offered,
/// when it is shown cleaned, and how the lists learn of it.
final class ColourRecoveryTests: XCTestCase {
    private func decoded<T: Decodable>(_ json: String) throws -> T {
        try LiveBackend.decoder().decode(T.self, from: Data(json.utf8))
    }

    /// A work of the demo's, as it came.
    private func work() async throws -> Item {
        let demo = DemoBackend()
        let themes = try await demo.themes()
        let page = try await demo.themePage(key: try XCTUnwrap(themes.first).key, page: 1)
        var item = try XCTUnwrap(page.items.first).item
        item.sharper = nil
        item.cleaned = nil
        return item
    }

    private var copy: SharperCopy {
        SharperCopy(url: "https://x/2.jpg", itemId: "wmc:9", source: "commons", museum: "Wikimedia Commons", width: 3000, height: 2000)
    }

    /// Oil and tempera have a varnish, drawings and prints a sheet; pastel
    /// and gouache cover theirs; a photograph or a poster has neither.
    func testWhatAWorkIsMadeInSaysWhatIsOffered() {
        XCTAssertEqual(ColourRecovery.made(.oil), "oil")
        XCTAssertEqual(ColourRecovery.made(.pen), "paper")
        XCTAssertEqual(ColourRecovery.made(.water), "paper")
        XCTAssertEqual(ColourRecovery.made(.woodblock), "paper")
        XCTAssertEqual(ColourRecovery.made(.grain), "paper")  // the stone's lithograph, 1.145.154
        XCTAssertEqual(ColourRecovery.made(.aquatint), "paper")  // the plate's aquatint, 1.145.156
        XCTAssertEqual(ColourRecovery.made(.toned), "paper")  // the server reads the sheet's tone itself
        XCTAssertEqual(ColourRecovery.made(.washLit), "paper")
        XCTAssertEqual(ColourRecovery.made(.chiaroscuro), "paper")
        XCTAssertEqual(ColourRecovery.made(.pastel), "opaque")
        XCTAssertEqual(ColourRecovery.made(.gouache), "opaque")
        XCTAssertNil(ColourRecovery.made(.photo))
        XCTAssertNil(ColourRecovery.made(.offset))
        XCTAssertNil(ColourRecovery.made(nil))
        XCTAssertEqual(ColourRecovery.kind(RecoveryView(kind: "varnish")), .varnish)
        XCTAssertEqual(ColourRecovery.kind(RecoveryView(kind: "paper")), .paper)
        XCTAssertNil(ColourRecovery.kind(RecoveryView(kind: "none")))
        XCTAssertNil(ColourRecovery.kind(nil as RecoveryView?))
    }

    /// A server of 1.145.155–161 says more (the preview's slider): only
    /// the kind is read.
    func testTheServersAnswerIsRead() throws {
        let view: RecoveryView = try decoded("""
        {"kind": "varnish", "strength": 0.72, "most": 1.6, "alpha": [0.15, 0.36, 1.0], "top": 0.97,
         "steps": [0.0, 0.1], "tops": [0.81, 0.84], "version": 1}
        """)
        XCTAssertEqual(ColourRecovery.kind(view), .varnish)
        let none: RecoveryView = try decoded(#"{"kind": "none"}"#)
        XCTAssertNil(ColourRecovery.kind(none))
    }

    /// "Korekta barw" (Mateusz 2026-11-15 18:52): the menu takes the
    /// varnish off or de-yellows the sheet, and gives either back.
    func testTheWordsAreTheOwners() {
        XCTAssertEqual(ColourRecovery.menuTitle(.varnish, on: false), "Zdejmij werniks")
        XCTAssertEqual(ColourRecovery.menuTitle(.paper, on: false), "Odżółć papier")
        XCTAssertEqual(ColourRecovery.menuTitle(.varnish, on: true), "Przywróć werniks")
        XCTAssertEqual(ColourRecovery.menuTitle(.paper, on: true), "Przywróć ton papieru")
        XCTAssertEqual(CleanedMark.spoken, "barwy skorygowane")
        XCTAssertTrue(ColourRecovery.note(.varnish).contains("Rachunek, nie konserwacja"))
    }

    /// A work the server sends cleaned: shown so, its pictures had anew, a
    /// mark in the lists.
    func testACleanedWorkIsShownSoEverywhere() async throws {
        let plain = try await work()
        XCTAssertNil(plain.cleanedShown)
        XCTAssertFalse(plain.summary.isCleaned)

        var cleaned = plain
        cleaned.cleaned = try decoded("""
        {"kind": "varnish", "made": "oil", "strength": 0.52, "picture": "", "drawn": null,
         "at": "2026-11-15T19:00:00+00:00"}
        """)
        XCTAssertEqual(cleaned.cleaned?.strength, 0.52)
        XCTAssertEqual(ColourRecovery.kind(cleaned.cleanedShown), .varnish)
        XCTAssertNotEqual(cleaned.pictureVersion, plain.pictureVersion)
        XCTAssertTrue(cleaned.summary.isCleaned)
        XCTAssertEqual(cleaned.summary.cleaned, "varnish")
        XCTAssertNotEqual(cleaned.summary.pictureVersion, plain.summary.pictureVersion)

        // Cleaned again later: the pictures kept by the app are had anew.
        var again = cleaned
        again.cleaned?.at = "2026-11-16T08:00:00+00:00"
        XCTAssertNotEqual(again.pictureVersion, cleaned.pictureVersion)
        XCTAssertNotEqual(again.summary.pictureVersion, cleaned.summary.pictureVersion)
    }

    /// Another copy is another photograph, shown as it comes (Mateusz
    /// 2026-11-15 18:54: "nie wiemy jaką ona ma kolorystykę"); the
    /// restorer's drawing of the same picture is cleaned the same.
    func testAnotherCopyIsNotCleanedAndTheRestorersDrawingIs() async throws {
        var other = try await work()
        other.sharper = copy
        other.cleaned = Cleaned(kind: "varnish", made: "oil", strength: 0.52, picture: "", at: "t1")
        XCTAssertNil(other.cleanedShown)
        XCTAssertFalse(other.summary.isCleaned)
        XCTAssertEqual(other.cleanedVersion, "")

        var drawn = other
        drawn.cleaned = try decoded("""
        {"kind": "varnish", "made": "oil", "strength": 0.52, "picture": "", "drawn": "wmc:9", "at": "t2"}
        """)
        XCTAssertNotNil(drawn.cleanedShown)
        XCTAssertTrue(drawn.summary.isCleaned)

        // Read on the copy itself: shown on it, not on the work's own picture.
        var onCopy = other
        onCopy.cleaned = Cleaned(kind: "paper", made: "paper", strength: 0, picture: "wmc:9", at: "t3")
        XCTAssertEqual(ColourRecovery.kind(onCopy.cleanedShown), .paper)
        onCopy.sharper = nil
        XCTAssertNil(onCopy.cleanedShown)
    }

    /// The mark stands with the others after the title, in the lists and
    /// on the card.
    func testTheMarkStandsWithTheOthers() async throws {
        var cleaned = try await work()
        var plain = cleaned.summary
        plain.zoom = nil
        plain.restored = nil
        plain.lowSide = nil
        plain.cropped = nil
        XCTAssertFalse(ArtCard.hasMarks(plain))
        cleaned.cleaned = Cleaned(kind: "varnish", picture: "", at: "t1")
        var marked = plain
        marked.cleaned = cleaned.summary.cleaned
        XCTAssertTrue(ArtCard.hasMarks(marked))
        XCTAssertNotNil(UIImage(named: CleanedMark.symbol))
    }

    /// A list loaded before the card took the varnish off shows the drop
    /// when he is back in it, and asks for the cleaned picture (Mateusz
    /// 2026-11-15 21:44: "Brakuje ikonki widocznej na liście dzieł w
    /// odkrywaj").
    @MainActor
    func testAListLoadedBeforeFollowsTheCard() async throws {
        let plain = try await work()
        var tile = plain.summary  // as the list has it
        tile.lowSide = 600
        tile.zoom = true
        XCTAssertFalse(tile.isCleaned)

        var cleaned = plain
        cleaned.cleaned = Cleaned(kind: "varnish", made: "oil", strength: 0.69, picture: "", at: "t1")
        let model = AppModel()
        XCTAssertEqual(model.asOnCard(tile), tile)  // nothing is known of it yet
        model.cardShows(cleaned, changed: true)
        let shown = model.asOnCard(tile)
        XCTAssertTrue(shown.isCleaned)
        XCTAssertEqual(shown.pictureVersion, cleaned.pictureVersion)
        XCTAssertNotEqual(shown.pictureVersion, tile.pictureVersion)
        // What the list alone knows stays: the title, its pixels, the magnifier.
        XCTAssertEqual(shown.title, tile.title)
        XCTAssertEqual(shown.lowSide, 600)
        XCTAssertEqual(shown.zoom, true)
        // Another work's tile is as it was.
        var other = tile
        other.title = "Inne"
        XCTAssertEqual(PictureMarks(cleaned).on(other).title, "Inne")

        // "Przywróć werniks": the drop goes from the list too.
        model.cardShows(plain, changed: true)
        XCTAssertFalse(model.asOnCard(tile).isCleaned)
        XCTAssertEqual(model.asOnCard(tile).pictureVersion, plain.pictureVersion)

        // Another copy in the picture's place: the list's count of pixels
        // was the other picture's.
        var copied = plain
        copied.sharper = copy
        model.cardShows(copied, changed: true)
        XCTAssertNil(model.asOnCard(tile).lowSide)
        XCTAssertEqual(model.asOnCard(tile).picture, "wmc:9")
    }

    /// The demo takes a varnish off and gives it back, like the server.
    func testTheDemoCleansAndGivesUp() async throws {
        let demo = DemoBackend()
        let kept = try await demo.items(LibraryQuery())
        let item = try XCTUnwrap(kept.items.first)
        let cleaned = try await demo.clean(itemID: item.id, made: "oil")
        XCTAssertEqual(ColourRecovery.kind(cleaned.cleanedShown), .varnish)
        let back = try await demo.unclean(itemID: item.id)
        XCTAssertNil(back.cleaned)
    }
}
