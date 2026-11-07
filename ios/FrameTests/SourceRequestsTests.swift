import XCTest
@testable import Frame

/// Konfiguracja → Diagnostyka: requests to the art sources, as the server
/// sends them (`/api/diagnostics/sources`).
final class SourceRequestsTests: XCTestCase {
    func testDecodesTheServersReport() throws {
        let json = """
        {"days": 7, "sources": [
          {"name": "Paris Musées",
           "today": {"sent": 3, "walled": 0, "throttled": 1, "failed": 0, "refused": 2, "bytes": 1000},
           "week": {"sent": 40, "walled": 1, "throttled": 2, "failed": 3, "refused": 5, "bytes": 90000},
           "quota": {"spent": 40, "of": 1000, "background": 600, "hours": 24.0},
           "resting": 600,
           "why_today": {"Szukaj": 2, "noc": 0, "spisy muzeów": 1},
           "why_week": {"Odkrywaj": 30, "Szukaj": 10}},
          {"name": null,
           "today": {"sent": 0, "walled": 0, "throttled": 0, "failed": 0, "refused": 0, "bytes": 0},
           "week": {"sent": 0, "walled": 0, "throttled": 0, "failed": 0, "refused": 0, "bytes": 0},
           "quota": null, "resting": 0}
        ]}
        """
        let report = try LiveBackend.decoder().decode(SourceRequests.self, from: Data(json.utf8))
        XCTAssertEqual(report.days, 7)
        XCTAssertEqual(report.sources[0].week.turnedAway, 6)
        XCTAssertEqual(report.sources[0].quota?.background, 600)
        XCTAssertFalse(report.sources[0].quiet)
        XCTAssertTrue(report.sources[1].quiet)
        // Who asked: today's, most first, the keys as the server wrote them.
        XCTAssertEqual(report.sources[0].askers.map { $0.0 }, ["Szukaj", "spisy muzeów"])
        XCTAssertEqual(report.sources[0].askers.map { $0.1 }, [2, 1])
        XCTAssertNil(report.sources[1].whyToday)  // an older server
        XCTAssertTrue(report.sources[1].askers.isEmpty)
        XCTAssertEqual(SourceRequestText.name(report.sources[1].name), "Inne serwery (obrazy z Openverse i Europeany)")
    }

    func testWordsInPolish() {
        XCTAssertEqual(SourceRequestText.requests(1), "1 zapytanie")
        XCTAssertEqual(SourceRequestText.requests(3), "3 zapytania")
        XCTAssertEqual(SourceRequestText.requests(12), "12 zapytań")
        XCTAssertEqual(SourceRequestText.requests(22), "22 zapytania")
        XCTAssertEqual(SourceRequestText.window(24), "na dobę")
        XCTAssertEqual(SourceRequestText.window(1), "na godzinę")
        XCTAssertEqual(SourceRequestText.duration(40), "40 s")
        XCTAssertEqual(SourceRequestText.duration(61), "2 min")
        XCTAssertEqual(SourceRequestText.duration(3900), "1 godz. 5 min")
    }
}
