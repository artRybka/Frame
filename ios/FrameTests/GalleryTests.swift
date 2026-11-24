import SwiftUI
import XCTest
@testable import Frame

/// Galeria's two views and the way between them (Mateusz 2026-11-24): the
/// grid's measures, the camera, the run of quick swipes, and where a swipe
/// down asks for the grid.
final class GalleryTests: XCTestCase {
    private let screen = CGSize(width: 402, height: 874)

    func testGridFillsTheScreenFromEdgeToEdge() {
        let metrics = GridMetrics(area: screen, scale: 3)
        // Three tiles and two gaps are the screen's width, to the pixel.
        XCTAssertEqual(metrics.tile.width * 3 + GridMetrics.gap * 2, screen.width, accuracy: 0.001)
        XCTAssertEqual(metrics.cell(2).maxX, screen.width, accuracy: 0.001)
        // Each tile is the screen's own shape, on whole pixels.
        XCTAssertEqual(metrics.tile.height / metrics.tile.width, screen.height / screen.width, accuracy: 0.002)
        XCTAssertEqual((metrics.tile.height * 3).rounded(), metrics.tile.height * 3, accuracy: 0.0001)
        // Three rows to a screen, a sliver of the fourth at most.
        XCTAssertEqual(metrics.pitch * 3, screen.height, accuracy: 8)
    }

    func testCellsAndPointsAgree() {
        let metrics = GridMetrics(area: screen, scale: 3)
        for n in [0, 1, 2, 3, 7, 100] {
            let cell = metrics.cell(n)
            XCTAssertEqual(metrics.index(at: CGPoint(x: cell.midX, y: cell.midY)), n)
        }
        // The middle column's middle is the screen's.
        XCTAssertEqual(metrics.cell(4).midX, screen.width / 2, accuracy: 0.001)
        // In a gap, no cell.
        XCTAssertNil(metrics.index(at: CGPoint(x: metrics.tile.width + 1, y: 10)))
        XCTAssertNil(metrics.index(at: CGPoint(x: -5, y: 10)))
    }

    func testCameraGoesFromThePageToItsTile() {
        let page = CGRect(origin: .zero, size: screen)
        let metrics = GridMetrics(area: screen, scale: 3)
        let tile = metrics.cell(4)
        XCTAssertEqual(GalleryCamera.between(page, tile, 0), page)
        let end = GalleryCamera.between(page, tile, 1)
        XCTAssertEqual(end.minX, tile.minX, accuracy: 0.001)
        XCTAssertEqual(end.minY, tile.minY, accuracy: 0.001)
        XCTAssertEqual(end.width, tile.width, accuracy: 0.001)
        // Halfway it is between the two in size and in place, and the
        // point the two share stays where it is: one zoom, no slide.
        let half = GalleryCamera.between(page, tile, 0.5)
        XCTAssertGreaterThan(half.width, tile.width)
        XCTAssertLessThan(half.width, page.width)
        let scale = tile.width / page.width
        let fixed = (tile.midY - page.midY * scale) / (1 - scale)
        let halfScale = half.width / page.width
        XCTAssertEqual(half.midY, fixed + (page.midY - fixed) * halfScale, accuracy: 0.01)
    }

    @MainActor
    func testQuickRunBringsTheGrid() {
        let run = SwipeRun()
        let height: CGFloat = 874
        var now = Date(timeIntervalSince1970: 1000)
        var reached: Int?
        // Eight works, each most of the way in within a second.
        for page in 1 ... 8 {
            now += 0.5
            // Half in: not reached yet.
            XCTAssertNil(run.scrolled(to: (CGFloat(page) - 0.5) * height, height: height, at: now))
            reached = run.scrolled(to: (CGFloat(page) - 0.3) * height, height: height, at: now)
            if page < 8 { XCTAssertNil(reached) }
        }
        XCTAssertEqual(reached, 8)
    }

    @MainActor
    func testSlowSwipesAndTheWayBackBringNoGrid() {
        let run = SwipeRun()
        let height: CGFloat = 874
        var now = Date(timeIntervalSince1970: 1000)
        for page in 1 ... 12 {
            now += 2
            XCTAssertNil(run.scrolled(to: CGFloat(page) * height, height: height, at: now))
        }
        // Quick ones, but one back among them: the run starts again.
        let other = SwipeRun()
        for page in [1, 2, 3, 4, 5, 4, 5, 6, 7, 8, 9, 10] {
            now += 0.4
            XCTAssertNil(other.scrolled(to: CGFloat(page) * height, height: height, at: now), "page \(page)")
        }
    }

    func testSwipeZoneIsLearntFromTheSwipesUp() {
        // Nothing learnt yet: near the middle of the screen.
        XCTAssertEqual(SwipeZone.line([]), SwipeZone.first)
        XCTAssertEqual(SwipeZone.line([0.7, 0.72, 0.8]), SwipeZone.first)
        // A thumb that starts low: the line a little above its highest
        // starts, no lower than the middle.
        let low = Array(repeating: 0.75, count: 10) + [0.7, 0.8, 0.72]
        XCTAssertEqual(SwipeZone.line(low), 0.5)
        // One that starts about the middle: the line above it.
        let middle = [0.5, 0.52, 0.48, 0.55, 0.5, 0.47, 0.51, 0.53, 0.49, 0.5]
        XCTAssertEqual(SwipeZone.line(middle), 0.48 - SwipeZone.margin, accuracy: 0.0001)
        // Never above a quarter of the screen, and one stray swipe from
        // the very top does not move it.
        XCTAssertEqual(SwipeZone.line(Array(repeating: 0.2, count: 12)), 0.25)
        XCTAssertEqual(SwipeZone.line(Array(repeating: 0.75, count: 19) + [0.05]), 0.5)
    }
}
