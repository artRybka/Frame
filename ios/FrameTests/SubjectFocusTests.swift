import SwiftUI
import XCTest
@testable import Frame

final class SubjectFocusTests: XCTestCase {
    func testCropCentresOnTheSubject() {
        // A tall picture 300 high in a box 100 high, subject at mid height.
        XCTAssertEqual(FocusedFill.shift(0.5, length: 300, box: 100), -100)
    }

    func testCropStopsAtTheEdges() {
        // A face near the top: the picture's top edge stays at the box's.
        XCTAssertEqual(FocusedFill.shift(0.05, length: 300, box: 100), 0)
        // Near the bottom: its bottom edge stays at the box's.
        XCTAssertEqual(FocusedFill.shift(0.98, length: 300, box: 100), -200)
    }

    /// "Teraz": the strips' tiles crop portraits around the face; a work
    /// already about the tile's shape shows at once, centred.
    func testNowStripCropsOnlyWorksOfAnotherShape() {
        func item(_ width: Int?, _ height: Int?, aspect: Double? = nil) -> ItemSummary {
            ItemSummary(
                id: "w", kind: .artwork, source: "test", title: "", artist: "",
                dateText: "", year: nil, colors: [], width: width, height: height,
                favorite: false, aspect: aspect
            )
        }
        XCTAssertTrue(Strip.cropsSubject(item(800, 1000)))  // a portrait
        XCTAssertTrue(Strip.cropsSubject(item(2000, 900)))  // a panorama
        XCTAssertFalse(Strip.cropsSubject(item(1300, 1000)))  // the tile's shape
        XCTAssertFalse(Strip.cropsSubject(item(nil, nil, aspect: 1.25)))
        XCTAssertTrue(Strip.cropsSubject(item(nil, nil)))  // not known yet
    }

    func testPlainPictureFindsTheMiddle() async {
        let image = UIGraphicsImageRenderer(size: CGSize(width: 40, height: 80)).image { context in
            UIColor.gray.setFill()
            context.fill(CGRect(x: 0, y: 0, width: 40, height: 80))
        }
        let point = await SubjectFocus.shared.point(in: image, key: "test:plain")
        XCTAssertEqual(point.x, 0.5, accuracy: 0.25)
        XCTAssertEqual(point.y, 0.5, accuracy: 0.25)
    }

    /// A screen of collages asks for many pictures at once: Vision must not
    /// take Swift's shared threads, or every other task (downloads) stalls.
    func testManyPicturesLeaveTheSharedThreadsFree() async throws {
        let image = UIGraphicsImageRenderer(size: CGSize(width: 300, height: 400)).image { context in
            UIColor.brown.setFill()
            context.fill(CGRect(x: 0, y: 0, width: 300, height: 400))
            UIColor.white.setFill()
            context.fill(CGRect(x: 120, y: 60, width: 60, height: 80))
        }
        let busy = Task {
            await withTaskGroup(of: UnitPoint.self) { group in
                for index in 0 ..< 48 {
                    group.addTask { await SubjectFocus.shared.point(in: image, key: "test:busy:\(index)") }
                }
                for await _ in group {}
            }
        }
        // Meanwhile other work still runs at once.
        let started = Date()
        for _ in 0 ..< ProcessInfo.processInfo.activeProcessorCount * 2 {
            _ = await Task.detached { 1 }.value
        }
        XCTAssertLessThan(Date().timeIntervalSince(started), 2)
        _ = await busy.result
    }
}
