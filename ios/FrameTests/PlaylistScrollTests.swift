import SwiftUI
import UIKit
import XCTest
@testable import Frame

/// The playlist page as it is on the phone (pushed in the Playlisty tab,
/// the tab bar below): it opens with the cover under the bar, not behind
/// it, holds still while it settles, and scrolls to its last work
/// (Mateusz 2026-11-14, „Paul Cezanne · Bathers”, 51 works: the cover hid
/// behind the buttons, the page made small jumps on opening and its last
/// row stayed under the tab bar).
@MainActor
final class PlaylistScrollTests: XCTestCase {
    private static let playlistID = 9_999

    private struct Host: View {
        @State private var tab = 1
        @State private var path: [Int] = []

        var body: some View {
            TabView(selection: $tab) {
                Tab("Teraz", systemImage: "photo.fill", value: 0) { Color.clear }
                Tab("Playlisty", systemImage: "rectangle.stack", value: 1) {
                    NavigationStack(path: $path) {
                        ScrollView { Color.clear.frame(height: 200) }
                            // As Playlisty: a large title over the list.
                            .navigationTitle("Playlisty")
                            .navigationDestination(for: Int.self) { id in PlaylistDetailView(playlistID: id) }
                    }
                    .task {
                        try? await Task.sleep(for: .milliseconds(500))
                        path = [PlaylistScrollTests.playlistID]
                    }
                }
            }
        }
    }

    /// Works like the Cézanne playlist's: portraits, landscapes, drawings,
    /// and a few wide ones that take a whole row.
    private static func works(_ count: Int) -> [ItemSummary] {
        let shapes: [(Int, Int)] = [(4, 3), (3, 4), (5, 2), (4, 3), (1, 1), (3, 2), (2, 3), (16, 9), (4, 5), (7, 3)]
        let titles = [
            "Bathers", "The Large Bathers (Les Grandes baigneuses)", "Seven Bathers",
            "Bathers by a Bridge (recto); Study after Houdon's Ecorché (verso)", "Group of Bathers", "Two Bathers",
        ]
        return (0 ..< count).map { index in
            let shape = shapes[(index * 3) % shapes.count]
            return ItemSummary(
                id: "test:\(index)", kind: .artwork, source: "test",
                title: titles[(index * 5) % titles.count],
                artist: "Paul Cézanne", dateText: "", year: nil, colors: [],
                width: shape.0, height: shape.1, favorite: false
            )
        }
    }

    private func detail(_ model: AppModel) async throws -> PlaylistDetail {
        let playlists = try await model.backend.playlists()
        let demo = try XCTUnwrap(playlists.first { $0.kind == .smart && !$0.isFavorites })
        var json = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(demo)) as? [String: Any])
        let items = Self.works(51)
        json["id"] = Self.playlistID
        for key in json.keys where key.lowercased().contains("count") { json[key] = items.count }
        let summary = try JSONDecoder().decode(PlaylistSummary.self, from: JSONSerialization.data(withJSONObject: json))
        return PlaylistDetail(playlist: summary, itemIds: items.map(\.id), items: items)
    }

    private func scrollView(in view: UIView) -> UIScrollView? {
        var found: [UIScrollView] = []
        func walk(_ view: UIView) {
            if let scroll = view as? UIScrollView, scroll.bounds.width > 300, scroll.contentSize.height > 1_000 {
                found.append(scroll)
            }
            view.subviews.forEach(walk)
        }
        walk(view)
        return found.max { $0.contentSize.height < $1.contentSize.height }
    }

    private func pause(_ milliseconds: Int) async throws {
        try await Task.sleep(for: .milliseconds(milliseconds))
    }

    private func run(lazy: Bool?) async throws -> [String] {
        MasonryProbe.lazy = lazy
        defer { MasonryProbe.lazy = nil }
        FramePositionProbe.frames = [:]
        let model = AppModel()
        model.playlistDetails[Self.playlistID] = try await detail(model)
        // In the test app's own scene, as on the phone: a window outside
        // any scene lays SwiftUI out but makes no scroll views.
        let scene = try XCTUnwrap(UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let window = UIWindow(windowScene: scene)
        window.frame = CGRect(x: 0, y: 0, width: 402, height: 874)
        window.rootViewController = UIHostingController(rootView: Host().environment(model))
        window.makeKeyAndVisible()
        defer { window.isHidden = true }
        var log: [String] = []
        var problems: [String] = []
        let mode = lazy.map { $0 ? "lazy" : "plain" } ?? "as shipped"

        // Opening: pushed at 0.5 s, settled well before 2.5 s.
        try await pause(1_600)
        var tops: [Double] = []
        for _ in 0 ..< 30 {
            if let top = FramePositionProbe.frames["collage"]?.minY { tops.append(Double(top)) }
            try await pause(50)
        }
        let scroll = try XCTUnwrap(scrollView(in: window), "no scroll view; frames \(FramePositionProbe.frames)")
        let inset = scroll.adjustedContentInset
        let collage = try XCTUnwrap(FramePositionProbe.frames["collage"], "no cover")
        log.append("\(mode) open: inset top \(inset.top) bottom \(inset.bottom), offset \(scroll.contentOffset.y), content \(scroll.contentSize.height), cover top \(collage.minY), cover tops while settling \(Set(tops).sorted())")
        if collage.minY < inset.top - 1 {
            problems.append("\(mode): the cover starts at \(collage.minY), under the bar ending at \(inset.top)")
        }
        if Set(tops.map { $0.rounded() }).count > 1 {
            problems.append("\(mode): the cover moved after opening: \(tops)")
        }

        // Down the page in steps, as a finger would; the grid's top must
        // stay where it is in the page.
        var sizes: [Double] = []
        var gridTops: [Double] = []
        var offset = scroll.contentOffset.y
        for _ in 0 ..< 200 {
            let end = scroll.contentSize.height + scroll.adjustedContentInset.bottom - scroll.bounds.height
            if offset >= end { break }
            offset = min(offset + 120, end)
            scroll.setContentOffset(CGPoint(x: 0, y: offset), animated: false)
            try await pause(40)
            sizes.append(Double(scroll.contentSize.height))
            if let grid = FramePositionProbe.frames["grid"] {
                gridTops.append(Double(grid.minY + scroll.contentOffset.y).rounded())
            }
        }
        // The very end, again until the page stops growing.
        for _ in 0 ..< 10 {
            let end = scroll.contentSize.height + scroll.adjustedContentInset.bottom - scroll.bounds.height
            scroll.setContentOffset(CGPoint(x: 0, y: end), animated: false)
            try await pause(250)
        }
        let grid = try XCTUnwrap(FramePositionProbe.frames["grid"], "no grid")
        let visibleBottom = scroll.frame.maxY - scroll.adjustedContentInset.bottom
        log.append("\(mode) end: content \(scroll.contentSize.height), offset \(scroll.contentOffset.y), grid bottom \(grid.maxY), visible bottom \(visibleBottom), content sizes \(Set(sizes.map { $0.rounded() }).count) different, grid tops in page \(Set(gridTops).sorted())")
        if grid.maxY > visibleBottom + 1 {
            problems.append("\(mode): the last row ends at \(grid.maxY), under the tab bar from \(visibleBottom)")
        }
        if lazy != true, Set(sizes.map { $0.rounded() }).count > 1 {
            problems.append("\(mode): the page changed its height while scrolling: \(Set(sizes.map { $0.rounded() }).sorted())")
        }
        if Set(gridTops).count > 1 {
            problems.append("\(mode): the grid moved in the page while scrolling: \(Set(gridTops).sorted())")
        }
        print("PLAYLIST SCROLL:\n" + log.joined(separator: "\n"))
        return problems
    }

    /// 51 works, as the Cézanne playlist: a plain stack, measured whole.
    func testThePlaylistPageOpensStillAndScrollsToTheEnd() async throws {
        let problems = try await run(lazy: nil)
        XCTAssertTrue(problems.isEmpty, problems.joined(separator: "\n"))
    }

    /// The lazy list, for comparison (its height is a guess until the end
    /// is reached): it must at least reach its end and keep its cover still.
    func testTheLazyGridStillReachesItsEnd() async throws {
        let problems = try await run(lazy: true)
        XCTAssertTrue(problems.isEmpty, problems.joined(separator: "\n"))
    }
}
