import SwiftUI
import XCTest
@testable import Frame

/// A page with nothing in it yet (a spinner, an empty list) must still be
/// the whole screen: a narrow beige strip on white came back three times.
@MainActor
final class PageLayoutTests: XCTestCase {
    private let screen = CGSize(width: 393, height: 852)

    func testAPageWithOnlyASpinnerIsTheWholeScreen() {
        let page = ScrollView { ProgressView().pageWidth() }.paperPage()
        let size = UIHostingController(rootView: page).sizeThatFits(in: screen)
        XCTAssertEqual(size.width, screen.width, accuracy: 0.5)
        XCTAssertEqual(size.height, screen.height, accuracy: 0.5)
    }

    func testThePaperIsTheWholeScreenEvenAroundNarrowContent() {
        let page = ScrollView { ProgressView() }.paperPage()
        let size = UIHostingController(rootView: page).sizeThatFits(in: screen)
        XCTAssertEqual(size.width, screen.width, accuracy: 0.5)
    }

    /// Pages put their paper with `paperPage()`, never a bare background
    /// that is only as wide as the ScrollView (see Design/Page.swift).
    func testNoPageHasABarePaperBackground() throws {
        let views = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Frame/Views")
        guard FileManager.default.fileExists(atPath: views.path),
              let files = FileManager.default.enumerator(at: views, includingPropertiesForKeys: nil)
        else {
            throw XCTSkip("The app's sources are not at \(views.path)")
        }
        let bare = [".background(Theme.paper)", ".background(Theme.paper.ignoresSafeArea())"]
        // The group sheets of Szukaj become glass panels on their own branch.
        let leaving: Set = ["TermFacets.swift"]
        var found: [String] = []
        for case let url as URL in files where url.pathExtension == "swift" && !leaving.contains(url.lastPathComponent) {
            let lines = try String(contentsOf: url, encoding: .utf8).components(separatedBy: "\n")
            for (index, line) in lines.enumerated() where bare.contains(where: { line.contains($0) }) {
                found.append("\(url.lastPathComponent):\(index + 1)")
            }
        }
        XCTAssertEqual(found, [], "Use .paperPage() on the page and .pageWidth() on its content")
    }
}
