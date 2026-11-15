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

    func testTheCataloguesTextsSayTheyAreBeingCounted() {
        var use = DemoBackend.leftoverUses[4]
        XCTAssertEqual(use.key, "descriptions")
        use.waiting = nil
        use.waitingUsd = nil
        XCTAssertEqual(AiSection.useNote(use), "liczę, ile czeka w katalogu…")
    }

    /// Mateusz 2026-11-15, "czeka 125323 · ok. 824,84 USD": "Jak to
    /// zlimitować?" The row tells what a night takes, and the limit is his.
    func testTheCataloguesTextsTellTheNightsPart() throws {
        let use = DemoBackend.leftoverUses[4]
        XCTAssertEqual(use.key, "descriptions")
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
        let texts = try XCTUnwrap(got.leftoverState?.uses?.first { $0.key == "descriptions" })
        XCTAssertEqual(texts.aNight, 500)
        XCTAssertEqual(texts.tonight, 500)
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let body = String(decoding: try encoder.encode(update), as: UTF8.self)
        XCTAssertTrue(body.contains("\"leftover_texts_a_night\":500"), body)
    }

    func testTheDemoMovesAndSwitchesTheUses() async throws {
        let demo = DemoBackend()
        var update = AiSettingsUpdate()
        update.leftoverOrder = ["studies", "refresh", "crops", "text_review", "descriptions", "audit"]
        update.leftoverOff = ["crops"]
        let got = try await demo.saveAiSettings(update)
        let uses = try XCTUnwrap(got.leftoverState?.uses)
        XCTAssertEqual(uses.first?.key, "studies")
        XCTAssertEqual(uses.first { $0.key == "crops" }?.on, false)
        XCTAssertEqual(uses.first { $0.key == "audit" }?.on, true)
    }
}
