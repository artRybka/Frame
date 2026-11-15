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

    func testThreeLongScreensSitRightUnderTheHeading() {
        // Mateusz 2026-11-15: three Japanese screens (about 2.4 : 1) in a box
        // as tall as a scroll's, a large empty space above them.
        let ratios: [CGFloat] = [2.43, 2.6, 2.3]
        let columns = LooksRow.widths(ratios: ratios, width: width, slots: 3)
        let box = LooksRow.pictureBox(ratios: ratios, width: width, slots: 3)
        let tallest = zip(columns, ratios).map { $0 / $1 }.max() ?? 0
        XCTAssertEqual(box, tallest, accuracy: 1)
        XCTAssertLessThan(box, LooksRow.pictureHeight / 2)
    }

    func testOneTallWorkKeepsTheFullHeight() {
        for ratios: [CGFloat] in [[0.4, 2.5, 2.5], [0.33, 0.44, 0.42], [0.6, 2.66, 1.5]] {
            let box = LooksRow.pictureBox(ratios: ratios, width: width, slots: 3)
            XCTAssertEqual(box, LooksRow.pictureHeight, accuracy: 0.01, "\(ratios)")
        }
    }

    func testEveryPictureFitsTheBox() {
        for ratios: [CGFloat] in [[40, 40, 40], [0.05, 40, 1], [1, 1, 1], [3], [0.2, 6], [1.9, 2.1, 2.4]] {
            let columns = LooksRow.widths(ratios: ratios, width: width, slots: 3)
            let box = LooksRow.pictureBox(ratios: ratios, width: width, slots: 3)
            XCTAssertLessThanOrEqual(box, LooksRow.pictureHeight, "\(ratios)")
            XCTAssertGreaterThan(box, 0, "\(ratios)")
            for (column, ratio) in zip(columns, ratios) {
                XCTAssertLessThanOrEqual(min(LooksRow.pictureHeight, column / ratio), box + 0.01, "\(ratios)")
            }
        }
    }
}
