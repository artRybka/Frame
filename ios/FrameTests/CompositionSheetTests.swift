import SwiftUI
import XCTest
@testable import Frame

/// The analysis of the composition drawn on a study sheet: what the server
/// sends for it, the picture's field, the chalk and the mark of a colour
/// that returns.
final class CompositionSheetTests: XCTestCase {
    private typealias Spot = DailyWork.Spot
    private typealias Mark = DailyWork.Mark

    func testATakeReadsItsFieldAndAnOlderOneHasNone() throws {
        let json = #"""
        {"title": "Analiza kompozycji", "grid": "thirds", "text": "",
         "marks": [{"shape": "echo", "points": [{"x": 0.3, "y": 0.4}, {"x": 0.7, "y": 0.6}], "title": "Błękit wraca", "text": ""}],
         "field": {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.6},
         "sketch": [{"points": [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.9}], "sharp": false, "closed": false}]}
        """#
        let take = try LiveBackend.decoder().decode(DailyWork.Take.self, from: Data(json.utf8))
        XCTAssertEqual(take.shownField, .init(x: 0.1, y: 0.2, w: 0.8, h: 0.6))
        // The marks are fractions of the whole reproduction; the sheet shows the field.
        let inside = take.marksInField[0].points
        XCTAssertEqual(inside[0].x, 0.25, accuracy: 1e-9)
        XCTAssertEqual(inside[0].y, 1.0 / 3, accuracy: 1e-9)
        XCTAssertEqual(inside[1].x, 0.75, accuracy: 1e-9)
        let older = try LiveBackend.decoder().decode(
            DailyWork.Take.self, from: Data(#"{"title": "Geometria", "grid": "none", "text": "", "marks": []}"#.utf8)
        )
        XCTAssertNil(older.field)
        XCTAssertEqual(older.shownField, .whole)
        // A field that is no part of the picture is not shown.
        var odd = take
        odd.field = .init(x: 0.5, y: 0, w: 0.9, h: 1)
        XCTAssertEqual(odd.shownField, .whole)
        XCTAssertEqual(odd.marksInField, odd.marks)
    }

    func testAnEchoIsARingAtEachPlaceAndABrokenLineBetween() {
        let size = CGSize(width: 400, height: 300)
        let echo = Mark(
            shape: "echo", points: [Spot(x: 0.2, y: 0.3), Spot(x: 0.6, y: 0.5), Spot(x: 0.85, y: 0.25)],
            title: "Błękit wraca", text: ""
        )
        let radius = Pencil.echoRing(in: size)
        XCTAssertEqual(radius, 12, accuracy: 1e-9)
        let points = echo.points.map { CGPoint(x: $0.x * size.width, y: $0.y * size.height) }
        let dashes = Pencil.echoDashes(points, in: size)
        XCTAssertGreaterThanOrEqual(dashes.count, 4)
        // No dash reaches into a ring, and the line is broken: the dashes
        // cover about half of the way.
        for dash in dashes {
            for point in dash {
                for centre in points {
                    XCTAssertGreaterThan(hypot(point.x - centre.x, point.y - centre.y), radius)
                }
            }
        }
        let paths = Pencil.paths(for: echo, in: size, seed: 1, weight: Pencil.crayonWeight)
        XCTAssertEqual(paths.count, 3 + dashes.count)
        // Two places too close for a line between them: the rings alone.
        let close = Mark(shape: "echo", points: [Spot(x: 0.5, y: 0.5), Spot(x: 0.55, y: 0.5)], title: "", text: "")
        XCTAssertEqual(Pencil.paths(for: close, in: size, seed: 1).count, 2)
        let spot = Pencil.numberSpot(for: echo, in: size)
        XCTAssertGreaterThan(hypot(spot.x - points[0].x, spot.y - points[0].y), radius)
    }

    func testTheHeavierPencilIsWiderAndNumbersDoNotLieOnEachOther() {
        let size = CGSize(width: 360, height: 480)
        let line = Mark(shape: "line", points: [Spot(x: 0.1, y: 0.5), Spot(x: 0.9, y: 0.5)], title: "Poziom", text: "")
        let thin = Pencil.paths(for: line, in: size, seed: 1)[0].boundingRect
        let heavy = Pencil.paths(for: line, in: size, seed: 1, weight: Pencil.crayonWeight)[0].boundingRect
        XCTAssertGreaterThan(heavy.height, thin.height)
        // Three marks whose numbers would sit on one spot.
        let same = (0..<3).map { _ in line }
        let spots = Pencil.numberSpots(for: same, in: size)
        XCTAssertEqual(spots.count, 3)
        for first in spots.indices {
            for second in spots.indices where second > first {
                XCTAssertGreaterThan(hypot(spots[first].x - spots[second].x, spots[first].y - spots[second].y), 20)
            }
        }
        // The frame's sides run past the corners.
        let side = Pencil.ruled(.zero, CGPoint(x: 360, y: 0), over: Pencil.reach, width: 0.9, seed: 70).boundingRect
        XCTAssertLessThan(side.minX, -Pencil.reach + 1)
        XCTAssertGreaterThan(side.maxX, 360 + Pencil.reach - 1)
    }

    func testTheMarksAreWhiteChalkAndAReturningColourRed() {
        let echo = Mark(shape: "echo", points: [], title: "", text: "")
        let loop = Mark(shape: "loop", points: [], title: "", text: "")
        XCTAssertEqual(Chalk.color(for: loop), Chalk.white)
        // What only answers across the picture is not read as a line that runs there.
        XCTAssertEqual(Chalk.color(for: echo), Chalk.red)
        // Brighter than the page's white only where the screen can show it.
        XCTAssertNil(Chalk.lift(headroom: 1))
        XCTAssertEqual(Chalk.lift(headroom: 8), Chalk.gain)
        XCTAssertEqual(try XCTUnwrap(Chalk.lift(headroom: 1.5)), 1.35, accuracy: 1e-9)
        // A point and a half at a full turn of the phone, the shadow the other way; still with Reduce Motion.
        XCTAssertEqual(Chalk.shift, 1.5)
        XCTAssertEqual(Chalk.offset(x: 1, y: -1, shift: Chalk.shift, still: false), CGSize(width: 1.5, height: -1.5))
        XCTAssertEqual(Chalk.offset(x: 0.5, y: 0, shift: -Chalk.castShift, still: false), CGSize(width: -0.5, height: 0))
        XCTAssertEqual(Chalk.offset(x: 1, y: 1, shift: Chalk.shift, still: true), .zero)
    }

    /// The marks as a picture, clear around them: what the brighter copy
    /// (above the page's white, where the screen can) is made of.
    @MainActor
    func testTheChalkIsDrawnOnNothingAndItsBrighterCopyIsTheSameSize() throws {
        // Untitled, so no number lies among them.
        let line = Mark(shape: "line", points: [Spot(x: 0.1, y: 0.5), Spot(x: 0.9, y: 0.5)], title: "", text: "")
        let echo = Mark(shape: "echo", points: [Spot(x: 0.25, y: 0.2), Spot(x: 0.75, y: 0.2)], title: "", text: "")
        let marks = [line, echo]
        let size = CGSize(width: 200, height: 100)
        let plain = try XCTUnwrap(ChalkMarks.plain(
            marks: marks, labelled: CompositionSketch.labelled(marks), room: EdgeInsets(), size: size, scale: 1
        ))
        XCTAssertEqual(plain.width, 200)
        XCTAssertEqual(plain.height, 100)
        var bytes = [UInt8](repeating: 0, count: 200 * 100 * 4)
        let space = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
        try bytes.withUnsafeMutableBytes { buffer in
            let context = try XCTUnwrap(CGContext(
                data: buffer.baseAddress, width: 200, height: 100, bitsPerComponent: 8, bytesPerRow: 800,
                space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
            ))
            context.draw(plain, in: CGRect(x: 0, y: 0, width: 200, height: 100))
        }
        func pixel(_ x: Int, _ y: Int) -> [Int] { (0..<4).map { Int(bytes[(y * 200 + x) * 4 + $0]) } }
        // Nothing under the strokes or beside them: no wash wiped, no edge.
        XCTAssertEqual(pixel(100, 80), [0, 0, 0, 0])
        XCTAssertEqual(pixel(5, 5), [0, 0, 0, 0])
        // The line in white, across the middle.
        let onLine = (44...56).map { pixel(100, $0) }.max { $0[3] < $1[3] }!
        XCTAssertGreaterThan(onLine[3], 200)
        XCTAssertGreaterThan(onLine[2], 200)
        // The echo's broken line in red, between its rings.
        let reds = (0..<200).flatMap { x in (10...30).map { y in pixel(x, y) } }.filter { $0[3] > 200 }
        XCTAssertFalse(reds.isEmpty)
        XCTAssertTrue(reds.allSatisfy { $0[0] > $0[2] + 60 })
        // The copy for a screen with headroom: the same picture, lit.
        let lit = try XCTUnwrap(ArtGlow.render(plain, gain: Chalk.gain))
        XCTAssertEqual(lit.width, plain.width)
        XCTAssertEqual(lit.height, plain.height)
    }

    func testTheDemoHasASheetForItsStudyInBothAppearances() async throws {
        let demo = DemoBackend()
        let work = try await demo.daily(day: nil, wait: 0, lists: false)
        let sheet = try XCTUnwrap(work.compositionSheet)
        XCTAssertFalse(sheet.isEmpty)
        for path in [sheet, sheet + "&dark=1"] {
            let url = try XCTUnwrap(demo.request(for: .path(path))?.url)
            XCTAssertNotNil(UIImage(contentsOfFile: url.path))
        }
        XCTAssertTrue(try XCTUnwrap(demo.request(for: .path(sheet + "&dark=1"))?.url).lastPathComponent.hasSuffix("-sheet-dark.jpg"))
        // Every other demo study has its sheets, and its marks lie in the field.
        for study in DemoStudies.named.values {
            for path in [DemoStudies.sheet(study.id), DemoStudies.sheet(study.id) + "&dark=1"] {
                XCTAssertNotNil(demo.request(for: .path(path))?.url, path)
            }
            for mark in study.take.marksInField {
                for point in mark.points {
                    XCTAssertTrue((-0.5...1.5).contains(point.x) && (-0.5...1.5).contains(point.y))
                }
            }
        }
        XCTAssertNotNil(DemoStudies.named["shower"]?.take.field)
    }
}
