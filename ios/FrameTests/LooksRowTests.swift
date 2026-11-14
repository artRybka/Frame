import XCTest
@testable import Frame

/// "Podobne wyglądem" on a work's card: one height of pictures, the same gap
/// between them, nothing wider than the row (Mateusz 2026-11-14: tall scrolls
/// stuck out over the button above, a folding screen ran into the next work).
final class LooksRowTests: XCTestCase {
    private let width: CGFloat = 358
    private var room: CGFloat { width - 2 * LooksRow.spacing }

    func testThreeScrollsKeepTheRowHeightAndAColumnForTheirTitles() {
        let columns = LooksRow.widths(ratios: [0.33, 0.44, 0.42], width: width, slots: 3)
        let least = LooksRow.leastShare * room / 3
        for column in columns {
            XCTAssertEqual(column, least, accuracy: 0.01)
        }
        // Each scroll fits its column at the row's height.
        for ratio: CGFloat in [0.33, 0.44, 0.42] {
            XCTAssertLessThanOrEqual(LooksRow.pictureHeight * ratio, least)
        }
    }

    func testALongScreenGivesWayBeforeTheOthers() {
        // Hiroshige's six-panel screen, a hanging scroll, a landscape.
        let columns = LooksRow.widths(ratios: [2.66, 0.85, 1.5], width: width, slots: 3)
        XCTAssertEqual(columns.reduce(0, +), room, accuracy: 0.01)
        XCTAssertEqual(columns[0], columns[2], accuracy: 0.01)
        XCTAssertLessThanOrEqual(columns[1], LooksRow.pictureHeight * 0.85 + 0.01)
    }

    func testATallWorkKeepsItsHeightBesideTwoLongOnes() {
        let columns = LooksRow.widths(ratios: [0.4, 1.5, 1.33], width: width, slots: 3)
        XCTAssertEqual(columns.reduce(0, +), room, accuracy: 0.01)
        XCTAssertEqual(columns[0], LooksRow.leastShare * room / 3, accuracy: 0.01)
        XCTAssertEqual(columns[1], columns[2], accuracy: 0.01)
    }

    func testTheRowNeverRunsPastItsWidth() {
        for ratios: [CGFloat] in [[40, 40, 40], [0.05, 40, 1], [1, 1, 1], [3], [0.2, 6]] {
            let columns = LooksRow.widths(ratios: ratios, width: width, slots: 3)
            let used = columns.reduce(0, +) + LooksRow.spacing * CGFloat(columns.count - 1)
            XCTAssertLessThanOrEqual(used, width + 0.01, "\(ratios)")
            XCTAssertTrue(columns.allSatisfy { $0 > 0 }, "\(ratios)")
        }
    }
}
