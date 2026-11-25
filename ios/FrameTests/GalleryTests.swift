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

    /// How many works swiped past bring the grid, by how quickly (Mateusz
    /// 2026-11-25 08:43: six within 1.5 s each, twelve within 3 s, three
    /// within 0.8 s, "płynne przejście" between them).
    @MainActor
    func testQuickRunBringsTheGrid() {
        let height: CGFloat = 874
        /// The page at which a run of swipes `apart` seconds apart brings
        /// the grid, nil when none of `pages` does.
        func comes(apart: TimeInterval, pages: Int = 20) -> Int? {
            let run = SwipeRun()
            var now = Date(timeIntervalSince1970: 1000)
            for page in 1 ... pages {
                now += apart
                // Half in: not reached yet.
                XCTAssertNil(run.scrolled(to: (CGFloat(page) - 0.5) * height, height: height, at: now))
                if let reached = run.scrolled(to: (CGFloat(page) - 0.3) * height, height: height, at: now) {
                    return reached
                }
            }
            return nil
        }
        // His three marks.
        XCTAssertEqual(comes(apart: 0.7), 3)
        XCTAssertEqual(comes(apart: 1.4), 6)
        XCTAssertEqual(comes(apart: 2.9), 12)
        // Between them, as many works as lie between.
        XCTAssertEqual(comes(apart: 1.0), 4)
        XCTAssertEqual(comes(apart: 1.2), 5)
        XCTAssertEqual(comes(apart: 1.9), 8)
        XCTAssertEqual(comes(apart: 2.4), 10)
        // Looked at for three seconds and more: never.
        XCTAssertNil(comes(apart: 3.0))
        XCTAssertNil(comes(apart: 5))
    }

    func testTheSecondsBetweenTheMarks() {
        XCTAssertNil(SwipeSpeed.within(2))
        XCTAssertEqual(SwipeSpeed.within(3) ?? 0, 0.8, accuracy: 0.0001)
        XCTAssertEqual(SwipeSpeed.within(6) ?? 0, 1.5, accuracy: 0.0001)
        XCTAssertEqual(SwipeSpeed.within(9) ?? 0, 2.25, accuracy: 0.0001)
        XCTAssertEqual(SwipeSpeed.within(12) ?? 0, 3, accuracy: 0.0001)
        XCTAssertEqual(SwipeSpeed.within(40) ?? 0, 3, accuracy: 0.0001)
        // Never less for more works: a longer run may be a slower one.
        for works in 3 ..< 12 {
            XCTAssertLessThan(SwipeSpeed.within(works) ?? 0, SwipeSpeed.within(works + 1) ?? 0)
        }
    }

    @MainActor
    func testAPauseAndTheWayBackStartTheRunAgain() {
        let height: CGFloat = 874
        var now = Date(timeIntervalSince1970: 1000)
        // Two quick works, a long look, two quick ones again: no three in
        // a row, and not enough slower ones either.
        let run = SwipeRun()
        for (page, apart) in [(1, 0.5), (2, 0.5), (3, 6), (4, 0.5)] {
            now += apart
            XCTAssertNil(run.scrolled(to: CGFloat(page) * height, height: height, at: now), "page \(page)")
        }
        now += 0.5
        XCTAssertEqual(run.scrolled(to: 5 * height, height: height, at: now), 5)
        // Quick ones, but every third a step back: the run starts again.
        let other = SwipeRun()
        for page in [1, 2, 1, 2, 3, 2, 3, 4, 3, 4] {
            now += 0.4
            XCTAssertNil(other.scrolled(to: CGFloat(page) * height, height: height, at: now), "page \(page)")
        }
    }

    /// The grid has no empty squares before its first work (Mateusz
    /// 2026-11-25: "widać puste kwadraty"): the works shown above the one
    /// it is entered from fill their rows, that one in the middle column.
    func testTheGridsFirstRowIsFull() {
        XCTAssertEqual(GalleryView.history(before: 0), 0)
        for index in 1 ... 200 {
            let above = GalleryView.history(before: index)
            let most = min(index, GalleryView.seen)
            XCTAssertEqual(above % GridMetrics.columns, 1, "the work at \(index) is not in the middle column")
            XCTAssertLessThanOrEqual(above, most)
            XCTAssertLessThanOrEqual(most - above, 2, "more than two works left out above \(index)")
        }
        // With two works above the one Galeria starts with, none looked
        // at since is left out: only those two, as the rows need.
        XCTAssertEqual(GalleryView.history(before: 2), 1)
        XCTAssertEqual(GalleryView.history(before: 3), 1)
        XCTAssertEqual(GalleryView.history(before: 4), 4)
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
