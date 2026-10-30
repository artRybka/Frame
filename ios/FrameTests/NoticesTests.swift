import XCTest
@testable import Frame

@MainActor
final class NoticesTests: XCTestCase {
    func testAConfirmationReplacesTheOneBeforeButNotAWarning() {
        let notices = Notices()
        notices.warn("Ramka nie odpowiada")
        notices.done("Zapisano")
        notices.done("Odpięto")
        XCTAssertEqual(notices.items.map(\.title), ["Ramka nie odpowiada", "Odpięto"])
        notices.fail("Błąd na serwerze")
        XCTAssertEqual(notices.items.map(\.title), ["Odpięto", "Błąd na serwerze"])
    }

    func testWorkTurnsIntoItsResultInPlace() {
        let notices = Notices()
        let card = notices.begin("Budzę ramkę")
        notices.done("Zapisano")
        notices.update(card, fraction: 0.4, count: "2 z 5")
        XCTAssertEqual(notices.items.first?.count, "2 z 5")
        notices.end(card, .done, "Ramka się obudziła")
        // The older confirmation goes, the card keeps its place and identity.
        XCTAssertEqual(notices.items.map(\.id), [card])
        XCTAssertEqual(notices.items.first?.kind, .done)
        XCTAssertNil(notices.items.first?.count)
    }

    func testBackgroundWorkStaysAboveTheRest() {
        let notices = Notices()
        notices.begin("Budzę ramkę")
        notices.begin("„Japonia”: pobieram dzieła z muzeów", background: true)
        XCTAssertEqual(notices.items.first?.title, "„Japonia”: pobieram dzieła z muzeów")
    }

    func testCancellationDropsTheCardSilently() {
        let notices = Notices()
        let card = notices.begin("Pobieram obraz do Zdjęć")
        notices.fail(CancellationError(), in: card)
        XCTAssertTrue(notices.items.isEmpty)
    }

    func testReadingTimeGrowsWithTheTextUpToFiveSeconds() {
        XCTAssertEqual(Notices.readingTime(Notice(kind: .done, title: "")), 2.5)
        XCTAssertEqual(Notices.readingTime(Notice(kind: .done, title: String(repeating: "a", count: 15))), 3.5)
        XCTAssertEqual(Notices.readingTime(Notice(kind: .done, title: String(repeating: "a", count: 200))), 5)
    }

    func testServerErrorsAreSaidInPolish() {
        let panel = BackendError.http(status: 502, body: #"{"detail": "panel: timed out"}"#)
        XCTAssertEqual(Notices.words(for: panel).0, "Ramka nie odpowiada")
        XCTAssertEqual(Notices.words(for: panel).1, "Serwer odpowiedział 502: panel: timed out")
        let polish = BackendError.http(status: 409, body: #"{"detail": "aktualizacja już trwa"}"#)
        XCTAssertEqual(Notices.words(for: polish).0, "Aktualizacja już trwa")
        XCTAssertNil(Notices.words(for: polish).1)
        XCTAssertEqual(Notices.words(for: URLError(.cannotConnectToHost)).0, "Brak połączenia z serwerem")
    }
}
