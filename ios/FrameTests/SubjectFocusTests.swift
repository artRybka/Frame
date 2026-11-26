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
}

import Vision

/// What Vision says of two works whose subject is much wider than the
/// screen (Mateusz 2026-11-26: Czapski's "Bitiuk", Stubbs's tiger): read
/// from the run's log before the rule is changed.
final class WideSubjectDiagnosis: XCTestCase {
    func testWhatVisionFinds() throws {
        for name in ["wide-cart", "wide-tiger"] {
            guard let url = Bundle(for: Self.self).url(forResource: name, withExtension: "jpg"),
                  let cg = UIImage(contentsOfFile: url.path)?.cgImage
            else {
                print("FOCUSDIAG \(name): no picture")
                continue
            }
            print("FOCUSDIAG \(name): \(cg.width)x\(cg.height)")
            let handler = VNImageRequestHandler(cgImage: cg, orientation: .up)
            func box(_ rect: CGRect) -> String {
                String(format: "x %.3f-%.3f y %.3f-%.3f", rect.minX, rect.maxX, 1 - rect.maxY, 1 - rect.minY)
            }
            let faces = VNDetectFaceRectanglesRequest()
            do {
                try handler.perform([faces])
                for face in faces.results ?? [] { print("FOCUSDIAG \(name) face \(box(face.boundingBox)) sure \(face.confidence)") }
                print("FOCUSDIAG \(name) faces: \(faces.results?.count ?? -1)")
            } catch { print("FOCUSDIAG \(name) faces failed: \(error)") }
            let people = VNDetectHumanRectanglesRequest()
            people.upperBodyOnly = false
            do {
                try handler.perform([people])
                for one in people.results ?? [] { print("FOCUSDIAG \(name) figure \(box(one.boundingBox)) sure \(one.confidence)") }
                print("FOCUSDIAG \(name) figures: \(people.results?.count ?? -1)")
            } catch { print("FOCUSDIAG \(name) figures failed: \(error)") }
            let animals = VNRecognizeAnimalsRequest()
            do {
                try handler.perform([animals])
                for one in animals.results ?? [] {
                    print("FOCUSDIAG \(name) animal \(one.labels.map(\.identifier)) \(box(one.boundingBox)) sure \(one.confidence)")
                }
                print("FOCUSDIAG \(name) animals: \(animals.results?.count ?? -1)")
            } catch { print("FOCUSDIAG \(name) animals failed: \(error)") }
            for (kind, request) in [
                ("attention", VNGenerateAttentionBasedSaliencyImageRequest() as VNImageBasedRequest),
                ("objects", VNGenerateObjectnessBasedSaliencyImageRequest() as VNImageBasedRequest),
            ] {
                do {
                    try handler.perform([request])
                    guard let found = request.results?.first as? VNSaliencyImageObservation else {
                        print("FOCUSDIAG \(name) \(kind): nothing")
                        continue
                    }
                    for one in found.salientObjects ?? [] {
                        print("FOCUSDIAG \(name) \(kind) place \(box(one.boundingBox)) sure \(one.confidence)")
                    }
                    let buffer = found.pixelBuffer
                    CVPixelBufferLockBaseAddress(buffer, .readOnly)
                    defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
                    let wide = CVPixelBufferGetWidth(buffer), tall = CVPixelBufferGetHeight(buffer)
                    let stride = CVPixelBufferGetBytesPerRow(buffer)
                    guard let base = CVPixelBufferGetBaseAddress(buffer) else { continue }
                    var columns = [Float](repeating: 0, count: wide), rows = [Float](repeating: 0, count: tall)
                    var top: Float = 0, at = (0, 0)
                    for y in 0 ..< tall {
                        let row = base.advanced(by: y * stride).assumingMemoryBound(to: Float32.self)
                        for x in 0 ..< wide {
                            let heat = row[x]
                            columns[x] += heat
                            rows[y] += heat
                            if heat > top { top = heat; at = (x, y) }
                        }
                    }
                    print("FOCUSDIAG \(name) \(kind) heat \(wide)x\(tall), format \(CVPixelBufferGetPixelFormatType(buffer)), hottest \(top) at \(at)")
                    print("FOCUSDIAG \(name) \(kind) columns " + columns.map { String(format: "%.1f", $0) }.joined(separator: " "))
                    print("FOCUSDIAG \(name) \(kind) rows " + rows.map { String(format: "%.1f", $0) }.joined(separator: " "))
                } catch { print("FOCUSDIAG \(name) \(kind) failed: \(error)") }
            }
        }
    }
}
