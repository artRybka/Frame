@testable import Frame
import XCTest

/// Konfiguracja's "Koszty" (Mateusz 2026-11-16: "czytelnie podaj koszt dla
/// każdej pozycji za ostatnie dni").
final class AiCostsTests: XCTestCase {
    func testTheServersRowsAreRead() throws {
        let json = #"""
        {"key_set": true, "key_tail": "abcd", "key_from_app": true, "pl_text": true,
         "keywords_artworks": true, "keywords_photos": false, "monthly_limit_usd": 20, "spent_usd": 1.2,
         "keywords_progress": {"done": 0, "waiting": 0, "refused": 0, "batch_items": 0, "batch_done": 0, "preparing": false},
         "error": null, "cost_days": 7,
         "claude_costs": [{"key": "crops", "label": "Kadrowanie zdjęć dzieł", "days_usd": 0.12, "period_usd": 0.4}],
         "gemini_costs": [{"key": "drawn", "label": "Arkusze kompozycji", "days_usd": 0.9, "period_usd": 1.2}]}
        """#
        let settings = try LiveBackend.decoder().decode(AiSettings.self, from: Data(json.utf8))
        XCTAssertEqual(settings.costDays, 7)
        XCTAssertEqual(settings.claudeCosts?.first?.daysUsd, 0.12)
        XCTAssertEqual(settings.geminiCosts?.first?.key, "drawn")
        // An older server: no table, nothing breaks.
        let older = try LiveBackend.decoder().decode(
            AiSettings.self,
            from: Data(json.replacingOccurrences(of: #""cost_days": 7,"#, with: "").utf8)
        )
        XCTAssertNil(older.costDays)
    }

    func testTheDearestComeFirstAndOtherLast() {
        let rows = [
            AiCost(key: "other", label: "Inne", daysUsd: 5, periodUsd: 5),
            AiCost(key: "pl_text", label: "Polskie", daysUsd: 0.2, periodUsd: 1),
            AiCost(key: "study_refresh", label: "Uzupełnianie", daysUsd: 0, periodUsd: 5.15),
            AiCost(key: "studies", label: "Studia", daysUsd: 1.18, periodUsd: 2),
            AiCost(key: "audit", label: "Przegląd", daysUsd: 0, periodUsd: 0.1),
        ]
        XCTAssertEqual(
            AiSection.sorted(rows).map(\.key), ["studies", "pl_text", "study_refresh", "audit", "other"]
        )
    }

    func testMoneyIsToldPlainly() {
        XCTAssertEqual(CostTable.short(0), "–")
        XCTAssertEqual(CostTable.short(0.004), "<0,01")
        XCTAssertEqual(CostTable.short(1.234), "1,23")
        XCTAssertEqual(AiSection.usd(0), "0 USD")
        XCTAssertEqual(AiSection.usd(0.003), "poniżej 1 centa")
        XCTAssertEqual(
            AiSection.progressNote(.init(done: 3691, waiting: 9, refused: 0, batchItems: 0, batchDone: 0, preparing: false)),
            "gotowe \(AiSection.count(3691)) · czeka 9"
        )
    }

    func testGeminisMonthIsTheCalendars() {
        let date = ISO8601DateFormatter().date(from: "2026-11-16T07:00:00Z")!
        XCTAssertEqual(AiSection.monthStart(date), "2026-11-01")
    }
}
