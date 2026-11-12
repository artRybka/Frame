import SwiftUI
import XCTest
@testable import Frame

/// The analysis of the composition drawn on a study sheet: what the server
/// sends for it, the picture's field, the coloured pencil and the mark of a
/// colour that returns.
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

    func testBlueDrawsTheMarksAndRedOverAPicturesBlues() {
        let red = SIMD3<Double>(0.75, 0.15, 0.1)
        let blue = SIMD3<Double>(0.1, 0.2, 0.6)
        let grey = SIMD3<Double>(0.5, 0.5, 0.5)
        XCTAssertEqual(Crayon.pick(over: Array(repeating: red, count: 80) + Array(repeating: grey, count: 20)), .blue)
        XCTAssertEqual(Crayon.pick(over: Array(repeating: blue, count: 80) + Array(repeating: grey, count: 20)), .red)
        // A few bluish places do not turn the pencil; nor do as many blues as reds.
        XCTAssertEqual(Crayon.pick(over: Array(repeating: blue, count: 5) + Array(repeating: grey, count: 95)), .blue)
        XCTAssertEqual(Crayon.pick(over: Array(repeating: blue, count: 50) + Array(repeating: red, count: 50)), .blue)
        XCTAssertEqual(Crayon.pick(over: []), .blue)
        XCTAssertEqual(Crayon.red.other, .blue)
        // What only answers across the picture is drawn in the other end.
        let echo = Mark(shape: "echo", points: [], title: "", text: "")
        let loop = Mark(shape: "loop", points: [], title: "", text: "")
        XCTAssertEqual(Crayon.red.color(for: echo, dark: false), Crayon.blue.color(dark: false))
        XCTAssertEqual(Crayon.red.color(for: loop, dark: false), Crayon.red.color(dark: false))
        // Lab as everyone has it: white is L 100, and black 0.
        XCTAssertEqual(Crayon.lab(SIMD3<Double>(1, 1, 1)).x, 100, accuracy: 0.01)
        XCTAssertEqual(Crayon.lab(SIMD3<Double>(0, 0, 0)).x, 0, accuracy: 0.01)
    }

    func testThePencilIsPickedWhereTheMarksLie() {
        // A sheet blue on its left half and red on its right.
        let renderer = UIGraphicsImageRenderer(size: CGSize(width: 80, height: 40))
        let image = renderer.image { context in
            UIColor(red: 0.1, green: 0.2, blue: 0.6, alpha: 1).setFill()
            context.fill(CGRect(x: 0, y: 0, width: 40, height: 40))
            UIColor(red: 0.75, green: 0.15, blue: 0.1, alpha: 1).setFill()
            context.fill(CGRect(x: 40, y: 0, width: 40, height: 40))
        }
        let colours = Crayon.colours(of: image, side: 32)
        XCTAssertEqual(colours.count, 32 * 32)
        XCTAssertEqual(colours[16 * 32 + 4].z, 0.6, accuracy: 0.04)   // left: blue
        XCTAssertEqual(colours[16 * 32 + 28].x, 0.75, accuracy: 0.04)  // right: red
        let left = Mark(shape: "line", points: [Spot(x: 0.1, y: 0.2), Spot(x: 0.4, y: 0.8)], title: "", text: "")
        let right = Mark(shape: "loop", points: [Spot(x: 0.75, y: 0.5), Spot(x: 0.9, y: 0.7)], title: "", text: "")
        XCTAssertEqual(Crayon.pick(for: image, under: [left]), .red)
        XCTAssertEqual(Crayon.pick(for: image, under: [right]), .blue)
        // An echo is drawn in the other end: it does not choose the pencil.
        let echo = Mark(shape: "echo", points: [Spot(x: 0.1, y: 0.5), Spot(x: 0.4, y: 0.5)], title: "", text: "")
        XCTAssertEqual(Crayon.pick(for: image, under: [right, echo]), .blue)
        // No mark on the sheet: all of it, as many blues as reds.
        XCTAssertEqual(Crayon.pick(for: image, under: []), .blue)
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
