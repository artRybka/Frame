import SwiftUI
import XCTest
@testable import Frame

/// The waterfall grid of Szukaj and the playlists: short blocks, each work
/// once, and works added at the end (the museums' answers, "więcej") never
/// move the blocks above them.
final class MasonryGridTests: XCTestCase {
    private typealias Grid = MasonryGrid<EmptyView>

    /// Works of varied shapes (portraits, landscapes, a panorama now and then).
    private func works(_ count: Int, from start: Int = 0) -> [ItemSummary] {
        let shapes: [(Int, Int)] = [(3, 4), (4, 3), (2, 3), (1, 1), (5, 4), (3, 5), (16, 9), (5, 2), (4, 5)]
        return (start..<start + count).map { index in
            let shape = shapes[(index * 7) % shapes.count]
            return ItemSummary(
                id: "w\(index)", kind: .artwork, source: "test",
                title: index % 3 == 0 ? "A rather long title for the work" : "Short",
                artist: "", dateText: "", year: nil, colors: [],
                width: shape.0, height: shape.1, favorite: false
            )
        }
    }

    private func ids(_ blocks: [Grid.Block]) -> [String] {
        blocks.flatMap { block -> [String] in
            switch block {
            case .columns(let buckets): return buckets.flatMap { $0.map(\.id) }
            case .row(let item): return [item.id]
            }
        }
    }

    func testEveryWorkIsShownOnce() {
        let items = works(120)
        XCTAssertEqual(Set(ids(Grid.blocks(items))), Set(items.map(\.id)))
        XCTAssertEqual(ids(Grid.blocks(items)).count, items.count)
    }

    func testTheSameWorkTwiceIsShownOnce() {
        let items = works(10)
        XCTAssertEqual(ids(Grid.blocks(items + items.prefix(3))).count, items.count)
    }

    /// Lazy columns guessed the heights of cards not made yet; short blocks
    /// in a lazy list are measured whole.
    func testBlocksAreShort() {
        for block in Grid.blocks(works(300)) {
            if case .columns(let buckets) = block {
                XCTAssertLessThanOrEqual(buckets.joined().count, Grid.maxBlock)
            }
        }
        XCTAssertGreaterThan(Grid.blocks(works(300)).count, 20)
    }

    func testWorksAddedAtTheEndKeepTheBlocksAbove() throws {
        let first = works(60)
        let before = Grid.blocks(first)
        let after = Grid.blocks(first + works(48, from: 60))
        // All blocks before the last columns (which the new works may
        // continue, with the wide works waiting after them) stay.
        let open = try XCTUnwrap(before.lastIndex { if case .columns = $0 { true } else { false } })
        XCTAssertGreaterThan(open, 3)
        for (old, new) in zip(before[..<open], after) {
            XCTAssertEqual(old.id, new.id)
            XCTAssertEqual(ids([old]), ids([new]))
        }
    }

    func testOneColumnIsOneBlock() {
        XCTAssertEqual(Grid.blocks(works(30), columns: 1).count, 1)
    }

    /// The grid's columns are plain stacks: a lazy stack nested in them lost
    /// its cards while scrolling (an empty screen in Szukaj).
    func testTheColumnsAreNotLazy() throws {
        let source = try String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .appendingPathComponent("Frame/Design/Components.swift"),
            encoding: .utf8
        )
        let grid = try XCTUnwrap(source.range(of: "struct MasonryGrid"))
        let end = try XCTUnwrap(source.range(of: "\nstruct Chip", range: grid.upperBound..<source.endIndex))
        let body = source[grid.upperBound..<end.lowerBound]
        XCTAssertEqual(body.components(separatedBy: "LazyVStack").count - 1, 1, "only the list of blocks is lazy")
    }
}
