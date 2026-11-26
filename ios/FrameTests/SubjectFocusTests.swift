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

    /// The study of the day: Claude's point on the lady's chest in Homer's
    /// "Autumn" cut her face off; the face Vision finds by it wins.
    func testStudyCropsOnTheFaceByClaudesPoint() {
        let face = CGRect(x: 0.4, y: 0.3, width: 0.08, height: 0.05)
        let point = SubjectFocus.near(UnitPoint(x: 0.45, y: 0.42), faces: [face], people: [])
        XCTAssertEqual(point.x, face.midX, accuracy: 0.001)
        XCTAssertEqual(point.y, face.midY, accuracy: 0.001)
    }

    func testOfSeveralFacesTheOneByThePoint() {
        let left = CGRect(x: 0.1, y: 0.3, width: 0.1, height: 0.1)
        let right = CGRect(x: 0.7, y: 0.3, width: 0.1, height: 0.1)
        let point = SubjectFocus.near(UnitPoint(x: 0.7, y: 0.45), faces: [left, right], people: [])
        XCTAssertEqual(point.x, right.midX, accuracy: 0.001)
    }

    func testAFaceFarFromThePointIsNotTheOneMeant() {
        let face = CGRect(x: 0.0, y: 0.0, width: 0.05, height: 0.05)
        let point = SubjectFocus.near(UnitPoint(x: 0.7, y: 0.8), faces: [face], people: [])
        XCTAssertEqual(point, UnitPoint(x: 0.7, y: 0.8))
    }

    /// No face found (turned away, too small): the head of the figure the
    /// point is on.
    func testWithoutAFaceTheFiguresHead() {
        let figure = CGRect(x: 0.3, y: 0.2, width: 0.2, height: 0.7)
        let point = SubjectFocus.near(UnitPoint(x: 0.4, y: 0.55), faces: [], people: [figure])
        XCTAssertEqual(point.x, 0.4, accuracy: 0.001)
        XCTAssertEqual(point.y, 0.2 + 0.7 * SubjectFocus.headInFigure, accuracy: 0.001)
    }

    func testNothingFoundKeepsThePoint() {
        XCTAssertEqual(SubjectFocus.near(UnitPoint(x: 0.3, y: 0.6), faces: [], people: []), UnitPoint(x: 0.3, y: 0.6))
    }

    /// Galeria: two places draw the eye far apart; the cut goes to the
    /// stronger one, not to the empty middle between them.
    func testGalleryCutsOnOnePlaceNotBetweenTwo() {
        let point = SubjectFocus.subject(faces: [], figures: [], salient: [
            (box: CGRect(x: 0.05, y: 0.3, width: 0.2, height: 0.3), weight: 0.9),
            (box: CGRect(x: 0.75, y: 0.3, width: 0.1, height: 0.1), weight: 0.5),
        ])
        XCTAssertEqual(point.x, 0.15, accuracy: 0.001)
    }

    /// A large figure is the subject (its head); a small one in a landscape
    /// is not.
    func testGalleryLargeFigureSmallStaffage() {
        let large = CGRect(x: 0.5, y: 0.1, width: 0.2, height: 0.8)
        let point = SubjectFocus.subject(faces: [], figures: [large], salient: [])
        XCTAssertEqual(point.y, 0.1 + 0.8 * SubjectFocus.headInFigure, accuracy: 0.001)
        let small = CGRect(x: 0.8, y: 0.6, width: 0.03, height: 0.1)
        XCTAssertEqual(SubjectFocus.subject(faces: [], figures: [small], salient: []), .center)
    }

    /// A map of what draws the eye, `wide` by `tall`: `faint` everywhere
    /// in `body`, 1 in `hot` (cells, rows from the top).
    private func heat(wide: Int, tall: Int, body: CGRect, hot: CGRect, faint: Float = 0.1) -> SubjectFocus.Heat {
        var values = [Float](repeating: 0, count: wide * tall)
        for y in 0 ..< tall {
            for x in 0 ..< wide {
                let cell = CGPoint(x: CGFloat(x) + 0.5, y: CGFloat(y) + 0.5)
                if hot.contains(cell) { values[y * wide + x] = 1 } else if body.contains(cell) { values[y * wide + x] = faint }
            }
        }
        return SubjectFocus.Heat(wide: wide, tall: tall, values: values)
    }

    /// Galeria: a subject much wider than the screen (Stubbs's tiger, its
    /// head at the left; Mateusz 2026-11-26) is cut at the part that draws
    /// the eye, not at its middle, the ribs.
    func testWideSubjectIsCutWhereItTells() {
        let tiger = heat(
            wide: 40, tall: 20, body: CGRect(x: 1, y: 3, width: 38, height: 14), hot: CGRect(x: 2, y: 3, width: 6, height: 5)
        )
        let point = SubjectFocus.telling(tiger, shape: 1.8, from: UnitPoint(x: 0.5, y: 0.5))
        let share = SubjectFocus.seen(of: 1.8).share
        // The whole head is on the screen.
        XCTAssertLessThanOrEqual(point.x - share / 2, 2.0 / 40 + 0.001)
        XCTAssertGreaterThanOrEqual(point.x + share / 2, 8.0 / 40 - 0.001)
        XCTAssertLessThan(point.y, 0.5)
    }

    /// A subject one screen holds stays cut about its middle, as it was.
    func testSubjectOneScreenHoldsIsCutAsItWas() {
        let rider = heat(
            wide: 40, tall: 20, body: CGRect(x: 17, y: 4, width: 7, height: 12), hot: CGRect(x: 19, y: 4, width: 2, height: 3)
        )
        let middle = UnitPoint(x: 0.51, y: 0.5)
        XCTAssertEqual(SubjectFocus.telling(rider, shape: 1.8, from: middle), middle)
    }

    /// Nothing in it draws the eye more than the rest (a field, a sea):
    /// the middle found before stays.
    func testEvenPictureIsCutAsItWas() {
        let sea = heat(wide: 40, tall: 20, body: CGRect(x: 0, y: 0, width: 40, height: 20), hot: .zero)
        let middle = UnitPoint(x: 0.45, y: 0.6)
        XCTAssertEqual(SubjectFocus.telling(sea, shape: 2.2, from: middle), middle)
    }

    /// A picture of the screen's own shape is seen whole: nothing to choose.
    func testPictureOfTheScreensShapeIsNotMoved() {
        let any = heat(wide: 20, tall: 40, body: CGRect(x: 0, y: 0, width: 20, height: 40), hot: CGRect(x: 0, y: 0, width: 4, height: 4))
        let middle = UnitPoint(x: 0.5, y: 0.5)
        XCTAssertEqual(SubjectFocus.telling(any, shape: SubjectFocus.screen, from: middle), middle)
    }

    /// A scroll far taller than the screen: the same along its height.
    func testTallSubjectIsCutWhereItTells() {
        let scroll = heat(
            wide: 10, tall: 60, body: CGRect(x: 1, y: 2, width: 8, height: 56), hot: CGRect(x: 3, y: 44, width: 4, height: 8)
        )
        let point = SubjectFocus.telling(scroll, shape: 0.15, from: UnitPoint(x: 0.5, y: 0.5))
        XCTAssertEqual(point.y, 48.0 / 60, accuracy: 0.06)
        XCTAssertEqual(point.x, 0.5, accuracy: 0.1)
    }

    /// The whole rule: no face and no figure found (a drawn animal), the
    /// eye's place a box as wide as the subject.
    func testGalleryCutsAWideSubjectAtItsHead() {
        let tiger = heat(
            wide: 40, tall: 20, body: CGRect(x: 1, y: 3, width: 38, height: 14), hot: CGRect(x: 2, y: 3, width: 6, height: 5)
        )
        let whole = (box: CGRect(x: 0.02, y: 0.15, width: 0.95, height: 0.7), weight: CGFloat(0.5))
        let before = SubjectFocus.subject(faces: [], figures: [], salient: [whole], shape: 1.8)
        XCTAssertEqual(before.x, 0.495, accuracy: 0.001)
        let point = SubjectFocus.subject(faces: [], figures: [], salient: [whole], heat: tiger, shape: 1.8)
        XCTAssertLessThan(point.x, 0.2)
    }

    /// Two faces too far apart for one screen: the larger one, not the
    /// wall between them. Near each other, both.
    func testFacesTooFarApartForOneScreen() {
        let large = CGRect(x: 0.15, y: 0.2, width: 0.1, height: 0.2)
        let far = CGRect(x: 0.75, y: 0.25, width: 0.08, height: 0.16)
        let apart = SubjectFocus.subject(faces: [large, far], figures: [], salient: [], shape: 1.8)
        XCTAssertEqual(apart.x, large.midX, accuracy: 0.001)
        let near = CGRect(x: 0.27, y: 0.25, width: 0.08, height: 0.16)
        let both = SubjectFocus.subject(faces: [large, near], figures: [], salient: [], shape: 1.8)
        XCTAssertEqual(both.x, large.union(near).midX, accuracy: 0.001)
        // A picture seen whole: all of them, as before.
        let whole = SubjectFocus.subject(faces: [large, far], figures: [], salient: [], shape: 0.5)
        XCTAssertEqual(whole.x, large.union(far).midX, accuracy: 0.001)
    }

    /// A figure lying down, wider than the screen, with no face found: its
    /// head is where the eye goes, not over the middle of its box.
    func testLyingFiguresHeadIsWhereTheEyeGoes() {
        let figure = CGRect(x: 0.1, y: 0.35, width: 0.8, height: 0.35)
        let lying = heat(
            wide: 40, tall: 20, body: CGRect(x: 4, y: 7, width: 32, height: 7), hot: CGRect(x: 29, y: 6, width: 5, height: 4)
        )
        let point = SubjectFocus.subject(faces: [], figures: [figure], salient: [], heat: lying, shape: 1.8)
        XCTAssertGreaterThan(point.x, 0.7)
        // Standing, one screen holds it: its head, as before.
        let standing = CGRect(x: 0.45, y: 0.1, width: 0.2, height: 0.8)
        let upright = SubjectFocus.subject(faces: [], figures: [standing], salient: [], heat: lying, shape: 1.8)
        XCTAssertEqual(upright.x, standing.midX, accuracy: 0.001)
    }
}
