import XCTest
@testable import Frame

final class TermFacetTests: XCTestCase {
    private let periods = [
        TermInfo(key: "period:ancient", kind: "period", name: "Starożytność", yearTo: 499),
        TermInfo(key: "period:medieval", kind: "period", name: "Średniowiecze", yearFrom: 500, yearTo: 1399),
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
        XCTAssertEqual(split.axis.count, 11)
        XCTAssertEqual(split.named.map(\.name), ["Belle Époque", "Międzywojnie"])
        XCTAssertEqual(split.axis.map(PeriodAxis.mark).prefix(3), ["staroż.", "500", "1400"])
        // An older server's axis starts with the Middle Ages.
        let older = TermInfo(key: "period:medieval", kind: "period", name: "Średniowiecze", yearTo: 1399)
        XCTAssertEqual(PeriodAxis.mark(older), "śr.")
    }

    func testAntiquitysYearsReadWithTheEra() {
        let egypt = TermInfo(key: "period:egypt", kind: "period", name: "Starożytny Egipt", yearFrom: -3100, yearTo: -30, region: "antiquity")
        let rome = TermInfo(key: "period:rome", kind: "period", name: "Starożytny Rzym", yearFrom: -509, yearTo: 476, region: "antiquity")
        XCTAssertEqual(PeriodAxis.years(egypt), "3100–30 p.n.e.")
        XCTAssertEqual(PeriodAxis.years(rome), "509 p.n.e.–476 n.e.")
        XCTAssertEqual(PeriodAxis.regions.first?.id, "antiquity")
        // In the oldest piece (1300 years up to 500): Egypt from its start,
        // Rome's end near the piece's.
        let axis = PeriodAxis.split(periods).axis
        XCTAssertEqual(PeriodAxis.position(-3100, on: axis), 0)
        XCTAssertEqual(PeriodAxis.position(477, on: axis), 1277.0 / 1300 / 11, accuracy: 0.001)
        XCTAssertEqual(PeriodAxis.span(["period:ancient", "period:medieval"], periods: periods), "do 1400")
    }

    func testNamedPeriodsComeInTheServersGroups() {
        let named = [
            TermInfo(key: "period:belle-epoque", kind: "period", name: "Belle Époque", yearFrom: 1880, yearTo: 1914, region: "europe"),
            TermInfo(key: "period:edo", kind: "period", name: "Edo", yearFrom: 1603, yearTo: 1868, region: "east-asia"),
            TermInfo(key: "period:ming", kind: "period", name: "Ming", yearFrom: 1368, yearTo: 1644, region: "east-asia"),
        ]
        let withRegions = periods.filter { !["period:belle-epoque", "period:interwar"].contains($0.key) } + named
        let split = PeriodAxis.split(withRegions)
        XCTAssertEqual(split.axis.count, 11)
        XCTAssertEqual(split.named.map(\.name), ["Belle Époque", "Edo", "Ming"])
        XCTAssertEqual(PeriodAxis.years(named[1]), "1603–1868")
        // Where a year falls on the axis of eleven equal pieces.
        XCTAssertEqual(PeriodAxis.position(1400, on: split.axis), 2.0 / 11, accuracy: 0.001)
        XCTAssertEqual(PeriodAxis.position(1650, on: split.axis), 4.5 / 11, accuracy: 0.001)
        XCTAssertEqual(PeriodAxis.position(1368, on: split.axis), (1 + 868.0 / 900) / 11, accuracy: 0.001)
        XCTAssertEqual(PeriodAxis.position(2100, on: split.axis), 1)
    }

    func testOlderPlaylistsMineTermsStayInTheField() {
        let token = SearchToken(kind: "mine", key: "mine:favorites", name: "Ulubione")
        XCTAssertTrue(TermFacet.inField(token))
        XCTAssertEqual(TermFacet.allCases.map(\.title), ["Technika", "Epoka", "Styl", "Kolor", "Temat", "Muzeum"])
    }

    func testPiecesSideBySideReadAsOneSpan() {
        XCTAssertEqual(PeriodAxis.span(["period:18c", "period:1850-1900", "period:1800-1850"], periods: periods), "1700–1900")
        XCTAssertEqual(PeriodAxis.span(["period:medieval", "period:15c"], periods: periods), "500–1500")
        XCTAssertEqual(PeriodAxis.span(["period:ancient", "period:medieval", "period:15c"], periods: periods), "do 1500")
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
        // Under the group's name on its button.
        XCTAssertEqual(TermFacet.style.value(tokens, periods: periods), "Ukiyo-e +1")
        XCTAssertEqual(TermFacet.period.value(tokens, periods: periods), "1700–1850")
        XCTAssertNil(TermFacet.subject.value(tokens, periods: periods))
        XCTAssertEqual(tokens.filter(TermFacet.inField).map(\.name), ["Hiroshige"])
    }

    func testMuseumsLeftOutSayBez() {
        let tokens = [
            SearchToken.museum("yale", name: "Yale", out: true),
            SearchToken.museum("met", name: "The Metropolitan Museum of Art", out: true),
        ]
        XCTAssertEqual(tokens.map(\.kind), [SearchToken.museumOut, SearchToken.museumOut])
        XCTAssertTrue(tokens.allSatisfy(TermFacet.museum.holds))
        XCTAssertTrue(tokens.filter(TermFacet.inField).isEmpty)
        XCTAssertEqual(TermFacet.museum.label(tokens, periods: periods), "Muzeum: bez Yale +1")
        XCTAssertEqual(SearchToken.museum("yale", name: "Yale").name, "Yale")
    }

    func testColourTagsRowsGoColoursAccentsMoods() {
        // "only:" tags (the colours a work is painted in) never show.
        let tags = ["light", "accent:red", "warm", "brown", "colorful", "orange", "muted", "accent:blue", "only:orange"]
        XCTAssertEqual(ColorTag.rows(tags), [
            ["orange", "brown"],
            ["accent:red", "accent:blue"],
            ["warm", "muted", "colorful", "light"],
        ])
        // Moods in pairs: Kolorowe beside Mono.
        let colorful = ColorTag.moods.firstIndex(of: "colorful")!
        XCTAssertEqual(ColorTag.moods[colorful + 1], "monochrome")
        XCTAssertEqual(colorful % 2, 0)
    }

    func testOnlyColoursNameThemselves() {
        XCTAssertEqual(ColorTag.name("only:blue"), "Dominuje: błękit")
        XCTAssertEqual(ColorTag.family("only:teal"), "teal")
        XCTAssertEqual(ColorTag.family("accent:red"), "red")
        XCTAssertEqual(ColorTag.family("blue"), "blue")
        let tokens = [SearchToken(kind: "color", key: "only:blue", name: "Dominuje: błękit")]
        XCTAssertEqual(TermFacet.color.label(tokens, periods: periods), "Dominuje: błękit")
    }

    func testColoursAtLevels() {
        XCTAssertEqual(ColorTag.name("blue@much"), "Błękit · wyraźny")
        XCTAssertEqual(ColorTag.name("red@accent"), "Czerwień · akcent")
        XCTAssertEqual(ColorTag.name("tone:warm"), "Ciepłe")
        XCTAssertEqual(ColorTag.name("monochrome"), "Mono")
        XCTAssertEqual(ColorTag.name("gray@clear"), "Szarości · obecne")
        XCTAssertEqual(ColorTag.name("red@most"), "Czerwień · główna")
        XCTAssertEqual(ColorTag.name("brown@clear"), "Brąz · obecny")
        XCTAssertEqual(ColorTag.name("white@much"), "Biel · wyraźna")
        XCTAssertEqual(ColorTag.name("red@accent"), "Czerwień · akcent")
        XCTAssertEqual(ColorTag.toneGroups.map { ColorTag.toneTitle($0[0]) }, ["Temperatura", "Nasycenie", "Barwność", "Jasność"])
        XCTAssertEqual(ColorTag.toneGroups.map(\.count), [3, 3, 2, 3])
        XCTAssertEqual(ColorTag.name("tone:neutral"), "Neutralne")
        XCTAssertEqual(ColorTag.rows(["warm", "tone:warm", "tone:medium"])[2], ["warm"])
        XCTAssertEqual(ColorTag.family("blue@most"), "blue")
        XCTAssertEqual(ColorTag.family("tone:dark"), "dark")
        XCTAssertEqual(ColorTag.level(of: "blue@much"), .much)
        // Older rules show at the level nearest to what they ask.
        XCTAssertEqual(ColorTag.level(of: "accent:red"), .accent)
        XCTAssertEqual(ColorTag.level(of: "blue"), .clear)
        XCTAssertEqual(ColorTag.level(of: "only:blue"), .most)
        XCTAssertNil(ColorTag.level(of: "warm"))
        XCTAssertNil(ColorTag.level(of: "tone:warm"))
        // White, grey and black are never an accent.
        XCTAssertEqual(ColorTag.Level.of("white"), [.clear, .much, .most])
        XCTAssertEqual(ColorTag.Level.of("blue").first, .accent)
        let tokens = [
            SearchToken(kind: "color", key: "blue@much", name: "Błękit · wyraźny"),
            SearchToken(kind: "color", key: "tone:warm", name: "Ciepłe"),
        ]
        XCTAssertEqual(TermFacet.color.label(tokens, periods: periods), "Błękit · wyraźny +1")
    }

    func testTechniquesHaveTheirWorkAndTheOtherThingsApart() {
        XCTAssertEqual(TechniqueArt.asset("technique:painting"), "technique-painting")
        XCTAssertEqual(TechniqueArt.asset("technique:decorative"), "technique-decorative")
        XCTAssertNil(TechniqueArt.asset("technique:mosaic"))
        XCTAssertNil(TechniqueArt.asset("style:impressionism"))
        XCTAssertTrue(TechniqueArt.objects.contains("technique:photography"))
        XCTAssertFalse(TechniqueArt.objects.contains("technique:poster"))
    }

    func testOneLetterWordsKeepToTheNextWord() {
        XCTAssertEqual(TechniqueSwatch.bound("Rysunki i akwarele"), "Rysunki i\u{00A0}akwarele")
        XCTAssertEqual(TechniqueSwatch.bound("Malarstwo"), "Malarstwo")
    }
}
