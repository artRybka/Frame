import XCTest
@testable import Frame

/// Konfiguracja → Zadania (Mateusz 2026-11-17): each task of the month's
/// rest with when it runs, how many a night, its amounts and its mode.
final class TasksTests: XCTestCase {
    func testATasksSettingsDecodeAndTellTheList() throws {
        let json = """
        {"key": "pl_text", "label": "Polskie opisy katalogu", "about": "…",
         "on": true, "able": true, "waiting": 125323, "each_usd": 0.0066, "waiting_usd": 824.84,
         "a_night": 1000, "done": 2000, "done_usd": 13.16, "now_each_usd": 0.0132,
         "when": "night", "a_night_choices": [250, 500, 1000], "night_usd": 10,
         "period_usd": null, "mode": "normal", "modes": ["batch", "normal"],
         "period_spent_usd": 13.16}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let use = try decoder.decode(LeftoverUse.self, from: Data(json.utf8))
        XCTAssertEqual(use.when, .night)
        XCTAssertEqual(use.mode, .normal)
        XCTAssertEqual(use.modes, [.batch, .normal])
        XCTAssertEqual(use.nightUsd, 10)
        XCTAssertNil(use.periodUsd)
        let line = TasksSection.line(use)
        XCTAssertTrue(line.hasPrefix("noc do 10 USD · czeka 125"), line)
        XCTAssertTrue(line.contains("w okresie 13,16"), line)
        XCTAssertFalse(line.contains("okres do"), line)
        // the mode tells what a work costs so, and what the night's amount buys
        let note = TaskPage.modeNote(use)
        XCTAssertTrue(note.contains("0,013 USD za dzieło"), note)
        XCTAssertTrue(note.contains("10 USD to ok. 757 dzieł"), note)
    }

    func testAnOlderServersUseIsAsBefore() throws {
        let json = """
        {"key": "audit", "label": "Większy nocny przegląd", "about": "…", "on": false,
         "able": true, "waiting": null, "each_usd": 0.002, "waiting_usd": null,
         "a_night": 270, "done": 0, "done_usd": 0}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let use = try decoder.decode(LeftoverUse.self, from: Data(json.utf8))
        XCTAssertNil(use.when)
        XCTAssertNil(use.modes)
        XCTAssertEqual(TasksSection.whenChip(.rest), "Resztka okresu")
        XCTAssertEqual(TasksSection.amount(2.5), Money.usd(2.5))
        XCTAssertEqual(TasksSection.amount(50), "50 USD")
        XCTAssertTrue(TaskPage.modeNote(use).hasPrefix("Przez Batch"))
    }

    func testTheUpdateSendsOnlyWhatChanged() throws {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(TaskUpdate(when: .demand, nightUsd: 0))
        let sent = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(sent["when"] as? String, "demand")
        XCTAssertEqual(sent["night_usd"] as? Double, 0)
        XCTAssertNil(sent["a_night"])
        XCTAssertNil(sent["mode"])
    }

    func testTheDemoSetsATask() async throws {
        let demo = DemoBackend()
        let got = try await demo.saveTask(key: "studies", update: TaskUpdate(when: .night, aNight: 10, periodUsd: 0))
        let studies = try XCTUnwrap(got.leftoverState?.uses?.first { $0.key == "studies" })
        XCTAssertEqual(studies.when, .night)
        XCTAssertEqual(studies.aNight, 10)
        XCTAssertNil(studies.periodUsd)
        XCTAssertTrue(studies.on)
    }

    /// Mateusz 2026-11-17: Odkrywaj with two switches, the study's parts
    /// without any; Gemini's looks among what runs at once; names and costs
    /// only.
    func testOdkrywajHasTwoSwitchesAndTheLooksRunAtOnce() async throws {
        let settings = try await DemoBackend().aiSettings()
        XCTAssertEqual(TasksSection.discover(settings).map(\.title), ["Studium dnia", "Propozycje kuratora"])
        let instant = TasksSection.instant(settings).map(\.title)
        XCTAssertEqual(instant.last, "Odciski wyglądu (Gemini)")
        let all = instant + TasksSection.night(settings).map(\.title)
        XCTAssertFalse(all.contains("Fakty z sieci"))
        XCTAssertFalse(all.contains("Droga dzieła"))
    }

    /// The audit of Zadania (Mateusz 2026-11-17): below Odkrywaj only
    /// tasks; the night's small checks every night or off; crops and the
    /// night audit one task each, more at the period's end their option; a
    /// row tells how it runs and what it cost.
    func testTheTasksTellOnlyHowTheyRunAndWhatTheyCost() async throws {
        let settings = try await DemoBackend().aiSettings()
        let uses = try XCTUnwrap(settings.leftoverState?.uses)
        let gate = try XCTUnwrap(uses.first { $0.key == "gatekeeper" })
        XCTAssertTrue(gate.isCheck)
        XCTAssertEqual(TasksSection.chips(gate), [])
        XCTAssertEqual(TasksSection.costLine(gate, settings: settings), "7 dni: " + AiSection.usd(0.09))
        let crops = try XCTUnwrap(uses.first { $0.key == "crops" })
        XCTAssertFalse(crops.isCheck)
        XCTAssertEqual(TasksSection.chips(crops), ["Batch ½", "+ koniec okresu"])
        let texts = try XCTUnwrap(uses.first { $0.key == "pl_text" })
        XCTAssertEqual(TasksSection.chips(texts), ["Batch ½", "do 1000"])
        XCTAssertTrue(TasksSection.costLine(texts, settings: settings).hasPrefix("w okresie"))
        XCTAssertFalse(uses.contains { $0.key == "text_review" || $0.key == "refresh" })
        XCTAssertEqual(uses.first { $0.key == "audit" }?.label, "Nocny przegląd")
    }
}
