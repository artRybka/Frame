import SwiftUI
import XCTest
@testable import Frame

/// The picture on a work's card fills the column, also once the card's
/// sections are in (Mateusz 2026-11-13: a picture shrank right after the
/// card opened; here the box went 362 → 237 → 318 pt wide in a 362 pt
/// column as the sections came).
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
        defer { window.isHidden = true }
        print("LAYOUT PROBE:\n" + LayoutProbe.log.joined(separator: "\n"))
        func size(_ line: String) -> CGSize? {
            let parts = line.split(separator: " ").last?.split(separator: "x").compactMap { Double($0) } ?? []
            return parts.count == 2 ? CGSize(width: parts[0], height: parts[1]) : nil
        }
        let column = try XCTUnwrap(LayoutProbe.log.last { $0.hasPrefix("column ") }.flatMap(size))
        let boxes = LayoutProbe.log.filter { $0.hasPrefix("box ") }.compactMap(size)
        XCTAssertFalse(boxes.isEmpty, "the picture was never laid out")
        // The Beach at Sainte-Adresse, 6793 × 5021: as wide as the column.
        for box in boxes {
            XCTAssertEqual(box.width, column.width, accuracy: 1, "\(LayoutProbe.log)")
            XCTAssertEqual(box.height, (column.width * 5021 / 6793).rounded(.down), accuracy: 1, "\(LayoutProbe.log)")
        }
    }
}
