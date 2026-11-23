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
        XCTAssertEqual(TasksSection.whenChip(.rest), "Koniec okresu")
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

    /// Mateusz 2026-11-17: the tasks named by what they do, small ones
    /// together, every when and mode on each; the study of the day and the
    /// curator's picks only switches; a row tells when, how and what it
    /// cost.
    func testTheTasksAreNamedByWhatTheyDo() async throws {
        let settings = try await DemoBackend().aiSettings()
        let uses = try XCTUnwrap(settings.leftoverState?.uses)
        XCTAssertEqual(TasksSection.discover(settings).map(\.title), ["Studium dnia", "Propozycje kuratora"])
        XCTAssertEqual(TasksSection.groups.map(\.title), ["Katalog", "Obraz", "Opisy i fakty", "Odkrywaj"])
        // The looks are SigLIP's on the server since 2026-11-23: no switch.
        XCTAssertEqual(TasksSection.switches("Obraz", settings).map(\.title), [])
        // Nor are the museum photographs cut by Claude: the phone does it.
        XCTAssertNil(uses.first { $0.key == "crops" })
        let grouped = Set(TasksSection.groups.flatMap(\.keys))
        XCTAssertTrue(uses.allSatisfy { grouped.contains($0.key) })
        // every when a task can have: "when asked" only for what can run now
        let tidy = try XCTUnwrap(uses.first { $0.key == "tidy" })
        XCTAssertTrue(tidy.isCheck)
        XCTAssertEqual(tidy.whens, [.night, .demand, .off])
        XCTAssertEqual(tidy.nightTasks, ["gatekeeper", "twins judge"])
        let audit = try XCTUnwrap(uses.first { $0.key == "audit" })
        XCTAssertFalse(audit.isCheck)
        XCTAssertEqual(audit.nightTasks, ["audit"])
        XCTAssertEqual(uses.first { $0.key == "studies" }?.whens, [.rest, .night, .off])
        let texts = try XCTUnwrap(uses.first { $0.key == "pl_text" })
        XCTAssertEqual(TasksSection.chips(texts), ["Koniec okresu", "Batch ½"])
        XCTAssertEqual(TasksSection.costLine(texts, settings: settings), "7 dni: " + AiSection.usd(0.21))
        XCTAssertEqual(TasksSection.costLine(tidy, settings: settings), "7 dni: " + AiSection.usd(0.11))
        let studies = try XCTUnwrap(uses.first { $0.key == "studies" })
        XCTAssertTrue(TasksSection.costLine(studies, settings: settings).hasPrefix("w okresie"))
        XCTAssertEqual(TasksSection.extras("tidy", settings).map(\.title), ["Strażnik katalogu", "Sędzia powtórek"])
        XCTAssertEqual(
            TasksSection.extras("keywords", settings).map(\.title),
            ["Nowe dzieła od razu", "Twoje zdjęcia", "Błękit pod werniksem", "Tłumaczenie słów w Szukaj"]
        )
    }

    /// Mateusz 2026-11-17: "A możemy je dać do listy powyżej i tylko
    /// iskierkami oznaczyć co robi AI a co nie?": the server's own work in
    /// the groups by what it does, small tasks together, none left over and
    /// none of the AI's twice.
    func testTheServersWorkStandsAmongTheTasks() async throws {
        let night = try await DemoBackend().nightTasks()
        let rows = Dictionary(uniqueKeysWithValues: TasksSection.groups.map {
            ($0.title, TasksSection.serverRows($0, night).map(\.label))
        })
        XCTAssertEqual(rows["Katalog"], [
            "Nowe dzieła do katalogu", "Powtórki i detale", "Kopie razem i podpowiedzi Szukaj",
            "Porządki w plikach", "Spisy muzeów",
        ])
        XCTAssertEqual(rows["Obraz"], ["Ostrzejsze kopie", "Kafle „Pod lupą”", "Oryginały Twoich dzieł"])
        XCTAssertEqual(rows["Odkrywaj"]?.last, "Kolejka ramki i playlisty")
        let shown = TasksSection.groups.flatMap { TasksSection.serverRows($0, night) }.flatMap(\.entries)
        XCTAssertFalse(shown.contains(where: \.paid))
        XCTAssertEqual(Set(shown.map(\.name)), Set(night.tasks.filter { !$0.paid }.map(\.name)))
        XCTAssertTrue(TasksSection.otherServerRows(night).isEmpty)
    }
}
