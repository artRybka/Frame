import XCTest
@testable import Frame

/// "Rozmiar obrazu": how big the drawing makes the work and the man
/// (Mateusz 2026-11-03 15:29).
final class RealSizeDrawingTests: XCTestCase {
    private let column: CGFloat = 350

    func testASmallWorkIsBroughtCloseWithHisBust() {
        // "Wielka fala", 25.7 × 37.9 cm: as wide as the column allows.
        let plan = RealSizeDrawing.plan(height: 25.7, width: 37.9, column: column)
        XCTAssertGreaterThan(plan.picture.width, 90)
        XCTAssertTrue(plan.cropped)
        // Cut just under his jacket, never anywhere else.
        let shown = (plan.cut - plan.man.minY) / plan.scale
        XCTAssertEqual(shown, CGFloat(180 - RealSizeDrawing.waist), accuracy: 0.5)
        XCTAssertEqual(plan.height, ceil(plan.cut + 1))
        // His head and the work's top are in the drawing, the work above the cut.
        XCTAssertGreaterThanOrEqual(plan.man.minY, 0)
        XCTAssertGreaterThanOrEqual(plan.picture.minY, 0)
        XCTAssertLessThan(plan.picture.maxY, plan.cut)
    }

    func testAWorkJustTooSmallForTheWholeManGetsTheBustToo() {
        // Vermeer's "The Glass of Wine", 67.7 × 79.6 cm (Mateusz 2026-11-03
        // 19:36: no man cut at the shins).
        let plan = RealSizeDrawing.plan(height: 67.7, width: 79.6, column: column)
        XCTAssertTrue(plan.cropped)
        XCTAssertEqual((plan.cut - plan.man.minY) / plan.scale, CGFloat(180 - RealSizeDrawing.waist), accuracy: 0.5)
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
