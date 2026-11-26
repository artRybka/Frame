import XCTest
@testable import Frame

/// "Resztka miesiąca" as a list in the owner's order (Mateusz 2026-11-15,
/// "Lista z kolejnością").
final class LeftoverUsesTests: XCTestCase {
    func testTheServersUsesAreReadInTheirOrder() throws {
        let json = """
        {"opens": "2026-11-13", "closes": "2026-11-16", "open": true, "free_usd": 30.5,
         "per_study_usd": 0.8, "measured": false, "ordered": 0, "in_flight": 0, "made": 0,
         "failed": 0, "candidates": 3,
         "uses": [
          {"key": "crops", "label": "Kadrowanie zdjęć dzieł", "about": "…", "on": true,
           "able": true, "waiting": 412, "each_usd": 0.01, "waiting_usd": 4.12, "a_night": 540,
           "done": 120, "done_usd": 1.2},
          {"key": "audit", "label": "Większy nocny przegląd", "about": "…", "on": false,
           "able": true, "waiting": null, "each_usd": 0.002, "waiting_usd": null,
           "a_night": 270, "done": 0, "done_usd": 0}
         ]}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let state = try decoder.decode(LeftoverState.self, from: Data(json.utf8))
        let uses = try XCTUnwrap(state.uses)
        XCTAssertEqual(uses.map(\.key), ["crops", "audit"])
        XCTAssertEqual(uses[0].aNight, 540)
        XCTAssertNil(uses[1].waiting)
        let note = AiSection.useNote(uses[0])
        XCTAssertTrue(note.contains("czeka 412"), note)
        XCTAssertTrue(note.contains("do 540 na noc"), note)
        XCTAssertTrue(note.contains("w tym okresie 120"), note)
    }

    func testAnOlderServerHasNoList() throws {
        let json = """
        {"opens": "2026-11-13", "closes": "2026-11-16", "open": false, "free_usd": 0,
         "per_study_usd": 0.8, "measured": false, "ordered": 0, "in_flight": 0, "made": 0,
         "failed": 0, "candidates": 0}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        XCTAssertNil(try decoder.decode(LeftoverState.self, from: Data(json.utf8)).uses)
    }

    func testAUseItsOwnSwitchKeepsOffSaysSo() {
        var use = DemoBackend.leftoverUses[0]
        use.able = false
        XCTAssertEqual(AiSection.useNote(use), "Wyłączone w ustawieniach wyżej.")
    }

    func testTheCataloguesTextsSayTheyAreBeingCounted() throws {
        var use = try XCTUnwrap(DemoBackend.leftoverUses.first { $0.key == "pl_text" })
        XCTAssertTrue(use.isCatalogueText)
        use.waiting = nil
        use.waitingUsd = nil
        XCTAssertEqual(AiSection.useNote(use), "liczę, ile czeka w katalogu…")
    }

    /// Mateusz 2026-11-15, "czeka 125323 · ok. 824,84 USD": "Jak to
    /// zlimitować?" The row tells what a night takes, and the limit is his.
    func testTheCataloguesTextsTellTheNightsPart() throws {
        let use = try XCTUnwrap(DemoBackend.leftoverUses.first { $0.key == "pl_text" })
        let note = AiSection.useNote(use)
        XCTAssertTrue(note.contains("tej nocy"), note)
        XCTAssertFalse(note.contains("824"), note)
        XCTAssertFalse(note.contains("na noc"), note)  // the menu says it
        XCTAssertEqual(use.aNightOptions?.contains(1000), true)
        let json = """
        {"key": "descriptions", "label": "Słowa", "about": "…", "on": true, "able": true,
         "waiting": 125323, "each_usd": 0.0066, "waiting_usd": 824.84, "a_night": 1000,
         "a_night_options": [250, 500, 1000], "tonight": 1000, "tonight_usd": 6.58,
         "done": 0, "done_usd": 0}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let decoded = try decoder.decode(LeftoverUse.self, from: Data(json.utf8))
        XCTAssertEqual(decoded.tonight, 1000)
        XCTAssertEqual(decoded.aNightOptions, [250, 500, 1000])
    }

    func testTheDemoSetsTheTextsANight() async throws {
        let demo = DemoBackend()
        var update = AiSettingsUpdate()
        update.leftoverTextsANight = 500
        let got = try await demo.saveAiSettings(update)
        // both of the catalogue's texts (two tasks since 2026-11-17)
        for key in ["keywords", "pl_text"] {
            let texts = try XCTUnwrap(got.leftoverState?.uses?.first { $0.key == key })
            XCTAssertEqual(texts.aNight, 500)
            XCTAssertEqual(texts.tonight, 500)
        }
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let body = String(decoding: try encoder.encode(update), as: UTF8.self)
        XCTAssertTrue(body.contains("\"leftover_texts_a_night\":500"), body)
    }

    func testTheDemoMovesAndSwitchesTheUses() async throws {
        let demo = DemoBackend()
        var update = AiSettingsUpdate()
        update.leftoverOrder = ["studies", "refresh", "text_review", "keywords", "pl_text", "audit"]
        update.leftoverOff = ["keywords"]
        let got = try await demo.saveAiSettings(update)
        let uses = try XCTUnwrap(got.leftoverState?.uses)
        XCTAssertEqual(uses.first?.key, "studies")
        XCTAssertEqual(uses.first { $0.key == "keywords" }?.on, false)
        XCTAssertEqual(uses.first { $0.key == "audit" }?.on, true)
    }

    /// Mateusz 2026-11-17: "podaję 50 $ na polskie słowa kluczowe i opisy i
    /// mogę je puścić od razu". The run comes with the use, and its row tells
    /// the works and the money.
    func testARunOnDemandDecodesAndTellsItsMoney() async throws {
        let json = """
        {"key": "descriptions", "label": "Słowa", "about": "…", "on": true, "able": true,
         "waiting": 125323, "each_usd": 0.0066, "waiting_usd": 824.84, "a_night": 1000,
         "done": 0, "done_usd": 0, "now_each_usd": 0.0132,
         "run": {"label": "Słowa", "usd": 50, "spent_usd": 12.37, "done": 936, "changed": 936,
                 "failed": 0, "waiting": 125323, "left": 124387, "running": true,
                 "stopping": false, "started": "2026-11-17T08:15:00+00:00", "ended": null,
                 "why": null}}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let use = try decoder.decode(LeftoverUse.self, from: Data(json.utf8))
        let run = try XCTUnwrap(use.run)
        XCTAssertEqual(use.nowEachUsd, 0.0132)
        XCTAssertTrue(run.running)
        let note = OnDemandRow.runningNote(run)
        XCTAssertTrue(note.hasPrefix("Teraz: 936 dzieł"), note)
        XCTAssertTrue(note.contains("w kolejce 124"), note)
        XCTAssertEqual(OnDemandRow.works(1), "1 dzieło")
        XCTAssertEqual(OnDemandRow.works(3), "3 dzieła")
        XCTAssertEqual(OnDemandRow.works(12), "12 dzieł")

        let demo = DemoBackend()
        let started = try await demo.startOnDemand(key: "pl_text", usd: 50)
        let texts = try XCTUnwrap(started.leftoverState?.uses?.first { $0.key == "pl_text" })
        XCTAssertEqual(texts.run?.running, true)
        XCTAssertEqual(texts.run?.usd, 50)
        let stopped = try await demo.stopOnDemand(key: "pl_text")
        let after = try XCTUnwrap(stopped.leftoverState?.uses?.first { $0.key == "pl_text" })
        XCTAssertEqual(after.run?.running, false)
        XCTAssertEqual(after.run.map(OnDemandRow.lastNote)?.contains("zatrzymane"), true)
    }

    /// Mateusz 2026-11-26: "przywróć przycisk. Ale jako losowe partie po 500".
    func testTheOldNotesDecodeAndTheDemoTakesFiveHundred() async throws {
        let json = """
        {"old_form": 6793, "rewrite_batch": 500, "rewrite_usd": 3.6, "running": false,
         "writing": 0, "written": 12, "translations": 1495, "unchecked": 2}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let review = try decoder.decode(TextReview.self, from: Data(json.utf8))
        XCTAssertEqual(review.oldForm, 6793)
        XCTAssertEqual(review.rewriteBatch, 500)
        let got = try await DemoBackend().rewriteOldNotes()
        let after = try XCTUnwrap(got.textReview)
        XCTAssertTrue(after.running)
        XCTAssertEqual(after.writing, 500)
        XCTAssertEqual(after.oldForm, 6293)
    }
}
