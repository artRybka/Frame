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

    /// The glow of a picture (Odkrywaj) is only a background: the page is
    /// still the whole screen, also scrolled past the glow.
    func testAGlowingPageIsTheWholeScreen() {
        let glow = [ColorSwatch(hex: "#2B4C8C", weight: 0.6), ColorSwatch(hex: "#D9A441", weight: 0.4)]
        for lift: CGFloat in [-80, 0, 300, 2000] {
            let page = ScrollView { ProgressView() }.paperPage(glow: glow, lift: lift)
            let size = UIHostingController(rootView: page).sizeThatFits(in: screen)
            XCTAssertEqual(size.width, screen.width, accuracy: 0.5)
            XCTAssertEqual(size.height, screen.height, accuracy: 0.5)
        }
    }

    /// The picture on a work's card is as wide as the page (at most 460 pt
    /// tall), also where the page's stack offers it less height: The
    /// Mussel Harvest shrank to 250 × 207 pt (Mateusz 2026-11-13).
    func testTheCardsPictureFillsThePageWhateverHeightItIsOffered() {
        // A landscape picture as wide as the page; a portrait one 460 pt tall.
        let pictures: [(aspect: CGFloat, height: CGFloat)] = [(15503.0 / 12844.0, 400 * 12844.0 / 15503.0), (0.75, 460)]
        for picture in pictures {
            for offered: CGFloat in [120, 207, 2000] {
                let box = Color.clear.aspectRatio(picture.aspect, contentMode: .fit).pictureBox()
                let size = UIHostingController(rootView: box).sizeThatFits(in: CGSize(width: 400, height: offered))
                XCTAssertEqual(size.width, 400, accuracy: 0.5, "aspect \(picture.aspect), offered \(offered)")
                XCTAssertEqual(size.height, picture.height, accuracy: 0.5, "aspect \(picture.aspect), offered \(offered)")
            }
        }
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
