import SwiftUI
import XCTest
@testable import Frame

/// The picture on a work's card fills the column (Mateusz 2026-11-13: a
/// landscape work's picture shrank right after the card opened).
@MainActor
final class CardPictureLayoutTests: XCTestCase {
    func testALandscapePictureFillsTheCardsColumn() async throws {
        let model = AppModel()
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 440, height: 956))
        LayoutProbe.log = []
        let root = NavigationStack { ItemDetailView(itemID: "aic:14598") }
            .environment(model)
        window.rootViewController = UIHostingController(rootView: root)
        window.makeKeyAndVisible()
        for _ in 0 ..< 20 {
            try await Task.sleep(for: .milliseconds(500))
        }
        print("LAYOUT PROBE:\n" + LayoutProbe.log.joined(separator: "\n"))
        let boxes = LayoutProbe.log.filter { $0.hasPrefix("box ") }
        let last = try XCTUnwrap(boxes.last, "the picture was never laid out")
        XCTAssertEqual(last, "box 400x295", "\(LayoutProbe.log)")
        window.isHidden = true
    }
}
