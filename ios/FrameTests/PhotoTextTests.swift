import XCTest
@testable import Frame

/// A photo's title and line, as the server names it (`photo_text.py`):
/// its caption, else the model's words, else the day; under it the day and
/// the town, without what the title says already.
final class PhotoTextTests: XCTestCase {
    private func photo(title: String = "", info: PhotoInfo) -> Item {
        Item(
            id: "icloud:G1", kind: .photo, source: "icloud", sourceId: "G1", title: title, artist: "",
            artistBio: "", dateText: "2026-10-29", year: nil, medium: "", classification: "",
            styles: [], subjects: [], culture: "", museum: "Rodzina", credit: "", license: "", url: "",
            description: "", imageUrl: "", thumbUrl: "", width: nil, height: nil,
            colors: [], colorTags: [], suitability: nil, favorite: false, excluded: false,
            addedAt: "2026-10-29T12:00:00Z", lastShownAt: nil, showCount: 0, photo: info
        )
    }

    func testModelsWordsOverDayAndPlace() {
        let item = photo(info: PhotoInfo(title: "Montaż drewnianej ścianki", place: "Kraków"))
        XCTAssertEqual(item.displayTitle, "Montaż drewnianej ścianki")
        XCTAssertEqual(item.photoLine, "29 października 2026 · Kraków")
        XCTAssertEqual(item.summary.title, "Montaż drewnianej ścianki")
        XCTAssertEqual(ArtCard.byline(item.summary), "29 października 2026 · Kraków")
    }

    func testCaptionWins() {
        let item = photo(title: "Hel", info: PhotoInfo(caption: "Hel", title: "Plaża nad morzem"))
        XCTAssertEqual(item.displayTitle, "Hel")
    }

    func testDayIsTheTitleOnceWithoutWords() {
        let item = photo(info: PhotoInfo(takenAt: "2026-10-28T21:15:00Z", place: "Kraków"))
        XCTAssertEqual(item.displayTitle, "28 października 2026")
        XCTAssertEqual(item.photoLine, "Kraków")
    }
}
