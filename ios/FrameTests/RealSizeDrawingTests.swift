import XCTest
@testable import Frame

/// "Rozmiar obrazu": how big the drawing makes the work and the man
/// (Mateusz 2026-11-03 15:29).
final class RealSizeDrawingTests: XCTestCase {
    private let column: CGFloat = 350

    func testASmallWorkIsBroughtCloseAndHisLegsFade() {
        // "Wielka fala", 25.7 × 37.9 cm: as wide as the column allows.
        let plan = RealSizeDrawing.plan(height: 25.7, width: 37.9, column: column)
        XCTAssertGreaterThan(plan.picture.width, 90)
        XCTAssertTrue(plan.cropped)
        XCTAssertEqual(plan.cut, 10 + RealSizeDrawing.room)
        XCTAssertEqual(plan.height, ceil(plan.cut + 1))
        // His head and the work's top are in the drawing.
        XCTAssertGreaterThanOrEqual(plan.man.minY, 0)
        XCTAssertGreaterThanOrEqual(plan.picture.minY, 0)
        // Never so close that less than 80 cm of him shows.
        XCTAssertLessThanOrEqual(plan.scale, RealSizeDrawing.room / RealSizeDrawing.leastOfHim + 0.001)
    }

    func testAWorkAboutAMetreShowsTheWholeMan() {
        // "Alegoria wiary", 114 × 89 cm, hangs; he is whole.
        let plan = RealSizeDrawing.plan(height: 114.3, width: 88.9, column: column)
        XCTAssertFalse(plan.cropped)
        XCTAssertGreaterThanOrEqual(plan.picture.maxY, 0)
        XCTAssertLessThanOrEqual(plan.man.maxY, plan.height)
    }

    func testABigWorkStandsOnTheFloorBesideHim() {
        let plan = RealSizeDrawing.plan(height: 378.5, width: 647.7, column: column)
        XCTAssertFalse(plan.cropped)
        XCTAssertEqual(plan.picture.maxY, plan.man.maxY, accuracy: 0.5)
        // Everything fits across.
        XCTAssertLessThanOrEqual(plan.man.maxX + 56, column + 0.5)
    }

    func testNoRoomIsLeftUnderTheDrawing() {
        // The width's number under the work is the lowest thing on it.
        let plan = RealSizeDrawing.plan(height: 378.5, width: 647.7, column: column)
        XCTAssertLessThanOrEqual(plan.height - plan.picture.maxY, 40)
    }
}
