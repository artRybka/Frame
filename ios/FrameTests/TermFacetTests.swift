import XCTest
@testable import Frame

final class TermFacetTests: XCTestCase {
    private let periods = [
        TermInfo(key: "period:medieval", kind: "period", name: "Średniowiecze", yearTo: 1399),
        TermInfo(key: "period:15c", kind: "period", name: "XV wiek", yearFrom: 1400, yearTo: 1499),
        TermInfo(key: "period:16c", kind: "period", name: "XVI wiek", yearFrom: 1500, yearTo: 1599),
        TermInfo(key: "period:17c", kind: "period", name: "XVII wiek", yearFrom: 1600, yearTo: 1699),
        TermInfo(key: "period:18c", kind: "period", name: "XVIII wiek", yearFrom: 1700, yearTo: 1799),
        TermInfo(key: "period:1800-1850", kind: "period", name: "1800–1850", yearFrom: 1800, yearTo: 1849),
        TermInfo(key: "period:1850-1900", kind: "period", name: "1850–1900", yearFrom: 1850, yearTo: 1899),
        TermInfo(key: "period:belle-epoque", kind: "period", name: "Belle Époque", yearFrom: 1880, yearTo: 1914),
        TermInfo(key: "period:1900-1930", kind: "period", name: "1900–1930", yearFrom: 1900, yearTo: 1930),
        TermInfo(key: "period:interwar", kind: "period", name: "Międzywojnie", yearFrom: 1918, yearTo: 1939),
        TermInfo(key: "period:1930-1945", kind: "period", name: "1930–1945", yearFrom: 1930, yearTo: 1944),
        TermInfo(key: "period:post-1945", kind: "period", name: "1945–1955", yearFrom: 1945, yearTo: 1955),
    ]

    func testPeriodsThatFollowOneAnotherMakeTheAxis() {
        let split = PeriodAxis.split(periods)
        XCTAssertEqual(split.axis.count, 10)
        XCTAssertEqual(split.named.map(\.name), ["Belle Époque", "Międzywojnie"])
        XCTAssertEqual(split.axis.map(PeriodAxis.mark).first, "śr.")
    }

    func testPiecesSideBySideReadAsOneSpan() {
        XCTAssertEqual(PeriodAxis.span(["period:18c", "period:1850-1900", "period:1800-1850"], periods: periods), "1700–1900")
        XCTAssertEqual(PeriodAxis.span(["period:medieval", "period:15c"], periods: periods), "do 1500")
        XCTAssertEqual(PeriodAxis.span(["period:1930-1945", "period:post-1945"], periods: periods), "1930–1955")
        // A gap, or a named period: no span.
        XCTAssertNil(PeriodAxis.span(["period:16c", "period:18c"], periods: periods))
        XCTAssertNil(PeriodAxis.span(["period:1850-1900", "period:belle-epoque"], periods: periods))
    }

    func testButtonsSayWhatIsPicked() {
        let tokens = [
            SearchToken(kind: "artist", key: "Hiroshige", name: "Hiroshige"),
            SearchToken(kind: "style", key: "style:ukiyo-e", name: "Ukiyo-e"),
            SearchToken(kind: "style", key: "style:shin-hanga", name: "Shin-hanga"),
            SearchToken(kind: "period", key: "period:18c", name: "XVIII wiek"),
            SearchToken(kind: "period", key: "period:1800-1850", name: "1800–1850"),
            SearchToken(kind: "color", key: "accent:red", name: "Akcent: czerwień"),
        ]
        XCTAssertEqual(TermFacet.style.label(tokens, periods: periods), "Styl: Ukiyo-e +1")
        XCTAssertEqual(TermFacet.period.label(tokens, periods: periods), "Epoka: 1700–1850")
        XCTAssertEqual(TermFacet.color.label(tokens, periods: periods), "Akcent: czerwień")
        XCTAssertEqual(TermFacet.subject.label(tokens, periods: periods), "Temat")
        XCTAssertEqual(tokens.filter(TermFacet.inField).map(\.name), ["Hiroshige"])
    }
}
