import XCTest
@testable import Frame

/// Odkrywaj sets: the museums answer one search at a time (one painter's
/// works, or one museum's on a subject), and the works are woven so that
/// one painter's, or one museum's, do not stand in a row.
final class WorkWeaveTests: XCTestCase {
    private var template: Item!

    override func setUp() async throws {
        let demo = DemoBackend()
        let themes = try await demo.themes()
        let theme = try XCTUnwrap(themes.first)
        let page = try await demo.themePage(key: theme.key, page: 1)
        template = try XCTUnwrap(page.items.first).item
    }

    /// `count` works of `artist` in `museum`, ids "<artist><museum><n>",
    /// years from `from` on.
    private func works(
        _ artist: String, _ count: Int, from year: Int? = 1920, museum: String? = nil, kind: String = "Painting"
    ) -> [RemoteItem] {
        (0..<count).map { index in
            let item = Item(
                copying: template, id: "\(artist)\(museum ?? "")\(index)", artist: artist,
                year: year.map { $0 + index }, museum: museum ?? "Museum of \(artist)", kind: kind
            )
            return RemoteItem(item: item, inLibrary: false)
        }
    }

    private func sideBySide(_ weave: WorkWeave, _ key: (RemoteItem) -> String) -> Int {
        let keys = weave.shown.map(key)
        return zip(keys, keys.dropFirst()).filter { $0 == $1 }.count
    }

    func testOnePaintersAnswerWaitsForAnother() {
        var weave = WorkWeave()
        weave.add(works("Strzemiński", 10))
        XCTAssertEqual(weave.shown.count, 1)
        XCTAssertEqual(weave.held.count, 9)
        weave.add(works("Witkacy", 10))
        XCTAssertEqual(weave.shown.count, 20)
        XCTAssertEqual(sideBySide(weave, WorkWeave.painter), 0)
    }

    func testPaintersAreNotRepeatedWithinAFewWorks() {
        var weave = WorkWeave()
        weave.add(["A", "B", "C", "D"].flatMap { works($0, 6) })
        weave.endRound(more: false)
        let names = weave.shown.map(WorkWeave.painter)
        XCTAssertEqual(names.count, 24)
        for start in 0...(names.count - 4) {
            XCTAssertEqual(Set(names[start..<start + 4]).count, 4, "\(names)")
        }
    }

    func testOneMuseumsAnswerOnASubjectWaitsForAnother() {
        // A set of a subject: each answer is one museum's, many painters.
        var weave = WorkWeave()
        let chicago = (0..<8).flatMap { works("Painter \($0)", 1, museum: "Art Institute of Chicago") }
        let met = (0..<8).flatMap { works("Artist \($0)", 1, museum: "The Met") }
        weave.add(chicago)
        XCTAssertEqual(weave.shown.count, 1)
        weave.add(met)
        XCTAssertEqual(weave.shown.count, 16)
        XCTAssertEqual(sideBySide(weave, WorkWeave.museum), 0)
    }

    func testOneMuseumAloneComesTogetherAtTheEndOfTheRound() {
        var weave = WorkWeave()
        weave.add((0..<10).flatMap { works("Painter \($0)", 1, museum: "Muzeum Narodowe w Warszawie") })
        weave.endRound(more: true)  // no other museum answered
        XCTAssertEqual(weave.shown.count, 10)
    }

    func testTheFirstWorksOfOneMuseumComeWhenTheOthersAreLate() {
        // Antiquity: the Met answers first, and the others take long.
        var weave = WorkWeave()
        weave.add((0..<10).flatMap { works("Painter \($0)", 1, museum: "The Met") })
        XCTAssertEqual(weave.shown.count, 1)
        weave.showFirst()
        XCTAssertEqual(weave.shown.count, WorkWeave.fewestPerRound)
        weave.showFirst()  // only the first few
        XCTAssertEqual(weave.shown.count, WorkWeave.fewestPerRound)
    }

    func testKindsTakeTurnsWhenTheyCan() {
        var weave = WorkWeave()
        weave.add(
            works("A", 2, kind: "Print") + works("B", 2, kind: "Print")
                + works("C", 2, kind: "Painting") + works("D", 2, kind: "Painting")
        )
        weave.endRound(more: false)
        XCTAssertEqual(sideBySide(weave, WorkWeave.kind), 0)
    }

    func testWhatIsLeftWaitsForTheNextRound() {
        var weave = WorkWeave()
        weave.add(works("Strzemiński", 12))
        weave.add(works("Witkacy", 4))
        weave.endRound(more: true)
        XCTAssertFalse(weave.held.isEmpty)  // Strzemiński's rest
        weave.add(works("Chwistek", 8))
        weave.endRound(more: false)
        XCTAssertTrue(weave.held.isEmpty)
        XCTAssertEqual(weave.shown.count, 24)
        XCTAssertEqual(sideBySide(weave, WorkWeave.painter), 0)
    }

    func testTheLastRoundShowsEverything() {
        var weave = WorkWeave()
        weave.add(works("Solo", 5))
        weave.endRound(more: false)
        XCTAssertEqual(weave.shown.count, 5)
        XCTAssertTrue(weave.held.isEmpty)
    }

    func testARoundThatShowedTooLittleLetsItsWorksGo() {
        var weave = WorkWeave()
        weave.add(works("Solo", 20))
        weave.endRound(more: true)  // no other painter came
        XCTAssertEqual(weave.shown.count, 20)
    }

    func testEarlierWorksComeFirst() {
        var weave = WorkWeave()
        var late = works("A", 3, from: 1935)
        late.append(
            RemoteItem(
                item: Item(copying: template, id: "A-undated", artist: "A", year: nil, museum: "Museum of A", kind: "Painting"),
                inLibrary: false
            )
        )
        weave.add(Array(late.reversed()) + works("B", 4, from: 1920))
        weave.endRound(more: false)
        XCTAssertEqual(weave.shown.first?.item.year, 1920)
        let a = weave.shown.filter { $0.item.artist == "A" }.map(\.item.year)
        XCTAssertEqual(a, [1935, 1936, 1937, nil])
    }

    func testACopyOfAWorkComesOnce() {
        var weave = WorkWeave()
        let a = works("A", 2)
        weave.add(a)
        weave.add(a)
        weave.endRound(more: false)
        XCTAssertEqual(weave.shown.count, 2)
    }

    func testNamesAreFoldedAndUnknownOnesAreTheirOwn() {
        let one = works("Mojżesz Kisling", 1)[0]
        let two = RemoteItem(
            item: Item(copying: template, id: "other", artist: " mojzesz kisling ", year: nil, museum: "", kind: ""),
            inLibrary: false
        )
        XCTAssertEqual(WorkWeave.painter(one), WorkWeave.painter(two))
        let x = RemoteItem(item: Item(copying: template, id: "x", artist: "", year: nil, museum: "", kind: ""), inLibrary: false)
        let y = RemoteItem(item: Item(copying: template, id: "y", artist: "", year: nil, museum: "", kind: ""), inLibrary: false)
        XCTAssertNotEqual(WorkWeave.painter(x), WorkWeave.painter(y))
        XCTAssertNotEqual(WorkWeave.kind(x), WorkWeave.kind(y))
    }
}

private extension Item {
    /// `item` with another id, painter, year, museum and kind (`id` can't
    /// be changed in place).
    init(copying item: Item, id: String, artist: String, year: Int?, museum: String, kind: String) {
        var fields = try! JSONSerialization.jsonObject(with: JSONEncoder().encode(item)) as! [String: Any]
        fields["id"] = id
        fields["artist"] = artist
        fields["year"] = year ?? NSNull()
        fields["museum"] = museum
        fields["heldBy"] = museum
        fields["classification"] = kind
        self = try! JSONDecoder().decode(Item.self, from: JSONSerialization.data(withJSONObject: fields))
    }
}
