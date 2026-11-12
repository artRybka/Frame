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
        // The strokes of the sheet's pen, which the app follows as it lays the pen's layer down.
        XCTAssertEqual(take.sketch?.count, 1)
        XCTAssertEqual(take.sketch?.first?.sharp, false)
        XCTAssertEqual(take.sketch?.first?.points.last, Spot(x: 0.9, y: 0.9))
        let older = try LiveBackend.decoder().decode(
            DailyWork.Take.self, from: Data(#"{"title": "Geometria", "grid": "none", "text": "", "marks": []}"#.utf8)
        )
        XCTAssertNil(older.field)
        XCTAssertNil(older.sketch)
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

    func testTheMarksAreChalkOfThePensColourAndAReturningColourRed() {
        let echo = Mark(shape: "echo", points: [], title: "", text: "")
        let loop = Mark(shape: "loop", points: [], title: "", text: "")
        // The pen's colour on each page, heavier than the sketch under it
        // and that sketch weaker (Mateusz 2026-11-12 11:31: "szkic pod spodem
        // słabszy, a linie kredą - ciut mocniejsze i grubsze niż rysunek
        // teraz. W kolorze rysunku, a powtórki kolorów zostawiamy czerwone").
        XCTAssertEqual(Chalk.color(for: loop, dark: false), Chalk.ink(dark: false))
        XCTAssertEqual(Chalk.color(for: loop, dark: true), Chalk.ink(dark: true))
        XCTAssertNotEqual(Chalk.ink(dark: false), Chalk.ink(dark: true))
        // 12:44, having seen that: "Rysunki kredy są za słabe. muszą się
        // wyraźniej odcinać. Może trzeba jeszcze rozjaśnić akwarelę w trybie
        // jasnym, a przyciemnić w ciemnym?": the sheet under the marks is
        // laid thin (its stains towards the page, its pen under half, less
        // still where it is light on dark) and the chalk is broad.
        XCTAssertLessThan(SheetPlan.washShare, 0.8)
        XCTAssertGreaterThan(SheetPlan.washShare, 0.5)
        XCTAssertLessThan(SheetPlan.penShare(dark: false), 0.5)
        XCTAssertLessThan(SheetPlan.penShare(dark: true), SheetPlan.penShare(dark: false))
        XCTAssertGreaterThan(SheetPlan.penShare(dark: true), 0.2)
        XCTAssertLessThan(Chalk.weight, Pencil.crayonWeight)  // not the broad white stick
        XCTAssertGreaterThan(Chalk.weight, 1.1)
        // What only answers across the picture is not read as a line that runs there.
        XCTAssertEqual(Chalk.color(for: echo, dark: false), Chalk.red)
        XCTAssertEqual(Chalk.color(for: echo, dark: true), Chalk.red)
        // Brighter than the page's white only where the screen can show
        // it, and only light chalk (the dark page).
        XCTAssertNil(Chalk.lift(headroom: 1))
        XCTAssertEqual(Chalk.lift(headroom: 8), Chalk.gain)
        XCTAssertEqual(try XCTUnwrap(Chalk.lift(headroom: 1.5)), 1.35, accuracy: 1e-9)
        XCTAssertNil(Chalk.lift(headroom: 8, dark: false))
        // A point and a half at a full turn of the phone, the shadow the other way; still with Reduce Motion.
        XCTAssertEqual(Chalk.shift, 1.5)
        XCTAssertEqual(Chalk.offset(x: 1, y: -1, shift: Chalk.shift, still: false), CGSize(width: 1.5, height: -1.5))
        XCTAssertEqual(Chalk.offset(x: 0.5, y: 0, shift: -Chalk.castShift, still: false), CGSize(width: -0.5, height: 0))
        XCTAssertEqual(Chalk.offset(x: 1, y: 1, shift: Chalk.shift, still: true), .zero)
        // Each mark on a plane of its own, the first (the main one) highest
        // (Mateusz 2026-11-12 09:47); a sheet from a server before that, all on one.
        XCTAssertEqual(Chalk.planes(3, apart: true), [[0], [1], [2]])
        XCTAssertEqual(Chalk.planes(3, apart: false), [[0, 1, 2]])
        XCTAssertEqual(Chalk.planes(0, apart: true), [])
        XCTAssertEqual(Chalk.planeShift(0, of: 1), Chalk.shift)
        XCTAssertEqual(Chalk.planeShift(0, of: 5), Chalk.highShift)
        XCTAssertEqual(Chalk.planeShift(4, of: 5), Chalk.lowShift)
        XCTAssertEqual(Chalk.planeShift(2, of: 5), (Chalk.highShift + Chalk.lowShift) / 2, accuracy: 1e-9)
        XCTAssertGreaterThan(Chalk.highShift, Chalk.shift)
        XCTAssertLessThan(Chalk.lowShift, Chalk.shift)
        // A higher plane's shadow goes further the other way.
        XCTAssertEqual(Chalk.castReach(under: Chalk.shift), Chalk.castShift)
        XCTAssertGreaterThan(Chalk.castReach(under: Chalk.highShift), Chalk.castShift)
        // The shadow shows only as the phone turns (Mateusz 2026-11-12 07:01);
        // where the chalk cannot be lit above the page's white a faint one stays.
        XCTAssertEqual(Chalk.castShown(x: 0, y: 0, lit: true, still: false), 0)
        XCTAssertEqual(Chalk.castShown(x: 0.6, y: 0.8, lit: true, still: false), 1, accuracy: 1e-9)
        XCTAssertEqual(Chalk.castShown(x: 0.3, y: 0.4, lit: true, still: false), 0.5, accuracy: 1e-9)
        XCTAssertEqual(Chalk.castShown(x: 1, y: 1, lit: true, still: true), 0)
        XCTAssertEqual(Chalk.castShown(x: 0, y: 0, lit: false, still: false), Chalk.castUnlit)
        XCTAssertEqual(Chalk.castShown(x: 1, y: 0, lit: false, still: false), 1)
    }

    func testANumberDoesNotLieOnAnArrowhead() {
        // Mateusz 2026-11-12 11:31: "Kółeczko (4) zakrywa grot strzałki".
        let size = CGSize(width: 345, height: 430)
        // An arrow of two points that runs out through the lower edge: its
        // "middle" point was its tip.
        let down = Mark(shape: "arrow", points: [Spot(x: 0.62, y: 0.78), Spot(x: 0.55, y: 1.0)], title: "Ucięty tułów", text: "")
        let tip = CGPoint(x: 0.55 * 345, y: 430)
        let spot = Pencil.numberSpot(for: down, in: size)
        XCTAssertGreaterThanOrEqual(hypot(spot.x - tip.x, spot.y - tip.y), Pencil.headClear)
        // Beside the middle of its way, not on the line.
        let middle = CGPoint(x: 0.585 * 345, y: 0.89 * 430)
        XCTAssertLessThan(hypot(spot.x - middle.x, spot.y - middle.y), 40)
        XCTAssertEqual(Pencil.heads(of: [down], in: size), [tip])
        // Another mark's number that would sit on the head moves aside,
        // even when the arrow itself has no label.
        let line = Mark(shape: "line", points: [Spot(x: 0.2, y: 0.9), Spot(x: 0.56, y: 1.0)], title: "Brzeg", text: "")
        let bare = Mark(shape: "arrow", points: down.points, title: "", text: "")
        let alone = Pencil.numberSpots(for: [line], in: size)[0]
        XCTAssertLessThan(hypot(alone.x - tip.x, alone.y - tip.y), Pencil.headClear)
        let moved = Pencil.numberSpots(for: [line], in: size, among: [line, bare])[0]
        XCTAssertGreaterThanOrEqual(hypot(moved.x - tip.x, moved.y - tip.y), Pencil.headClear)
        // A movement's head too.
        let motion = Mark(shape: "motion", points: [Spot(x: 0.9, y: 0.6), Spot(x: 0.3, y: 0.5)], title: "Lot", text: "")
        XCTAssertEqual(Pencil.heads(of: [motion, line], in: size).count, 1)
        // Beside an upright line: to its right; beside a level one: above it.
        let right = Pencil.beside([CGPoint(x: 100, y: 0), CGPoint(x: 100, y: 200)], at: 0.5, by: 15)
        XCTAssertEqual(right.x, 115, accuracy: 1e-6)
        XCTAssertEqual(right.y, 100, accuracy: 1e-6)
        let above = Pencil.beside([CGPoint(x: 0, y: 50), CGPoint(x: 200, y: 50)], at: 0.25, by: 15)
        XCTAssertEqual(above.x, 50, accuracy: 1e-6)
        XCTAssertEqual(above.y, 35, accuracy: 1e-6)
    }

    /// Mateusz 2026-11-12 12:44, of a label whose title took two lines
    /// ("Żółć wraca / trzy razy"): "coś się posypały odstępy w nagłówkach
    /// tekstu?". As one text the title's lines stood the face's whole tall
    /// line apart; written word by word they are as close as the note's.
    @MainActor
    func testATitleOfTwoLinesKeepsThemClose() throws {
        func drawn(_ text: String, width: CGFloat?) throws -> CGSize {
            let lines = HandLines(text: text, size: 20)
            let renderer = width.map { ImageRenderer(content: AnyView(lines.frame(width: $0, alignment: .leading))) }
                ?? ImageRenderer(content: AnyView(lines.fixedSize()))
            renderer.scale = 1
            let image = try XCTUnwrap(renderer.cgImage)
            return CGSize(width: image.width, height: image.height)
        }
        let word = try drawn("wraca", width: nil)
        // Room for one word and a half: the second goes under the first.
        let two = try drawn("wraca wraca", width: word.width * 1.5)
        XCTAssertEqual(two.height - word.height, 19, accuracy: 1.5)
        XCTAssertLessThan(two.height - word.height, word.height * 0.9)
        // With room for both they share the line.
        let wide = try drawn("wraca wraca", width: word.width * 2.6)
        XCTAssertEqual(wide.height, word.height, accuracy: 1)
    }

    func testATappedLabelLeavesItsMarkAndTheOthersStepBack() {
        // Mateusz 2026-11-12 11:31: "Dotknięcie podpisu z numerkiem pod spodem
        // niech jakoś zapala - wyróżnia wskazane zakreślenie na szkicu powyżej".
        let named = Mark(shape: "loop", points: [], title: "Twarz", text: "")
        let plain = Mark(shape: "line", points: [], title: "", text: "")
        // Labels are numbered among the titled marks only.
        let marks = [plain, named, plain, named]
        XCTAssertEqual(CompositionSketch.chosenMark(1, among: marks), 1)
        XCTAssertEqual(CompositionSketch.chosenMark(2, among: marks), 3)
        XCTAssertNil(CompositionSketch.chosenMark(3, among: marks))
        XCTAssertNil(CompositionSketch.chosenMark(nil, among: marks))
        // The plane of the tapped mark stays whole, the others step back;
        // nothing tapped, all whole; before the sheet is drawn, none.
        XCTAssertEqual(ChalkMarks.share(of: [3], chosen: 3, shown: true), 1)
        XCTAssertEqual(ChalkMarks.share(of: [1], chosen: 3, shown: true), Chalk.aside)
        XCTAssertEqual(ChalkMarks.share(of: [1], chosen: nil, shown: true), 1)
        XCTAssertEqual(ChalkMarks.share(of: [3], chosen: 3, shown: false), 0)
        // The others stepping back is all that picks it out (12:44: "na
        // pewno nie żółte podświetlenie. raczej przygaszenie pozostałych").
        XCTAssertLessThan(Chalk.aside, 0.3)
        XCTAssertGreaterThan(Chalk.aside, 0.1)
    }

    func testAStrokeOfChalkIsAStickNotAPoint() throws {
        let size = CGSize(width: 360, height: 480)
        let line = Mark(shape: "line", points: [Spot(x: 0.1, y: 0.5), Spot(x: 0.9, y: 0.5)], title: "", text: "")
        // Blunt where it lands: wider there than the pencil's point.
        func landing(_ path: Path) -> CGFloat {
            var heights: [CGFloat] = []
            path.forEach { element in
                switch element {
                case let .move(to: point), let .line(to: point):
                    if point.x < 40 { heights.append(point.y) }
                default: break
                }
            }
            return (heights.max() ?? 0) - (heights.min() ?? 0)
        }
        let pencil = Pencil.paths(for: line, in: size, seed: 1, weight: Pencil.crayonWeight)[0]
        let chalk = Pencil.paths(for: line, in: size, seed: 1, weight: Pencil.crayonWeight, chalk: true)[0]
        XCTAssertGreaterThan(landing(chalk), landing(pencil) * 1.5)
        XCTAssertEqual(chalk.boundingRect.width, pencil.boundingRect.width, accuracy: 1)
        // Pressed unevenly, never lightly; and it stays on the paper's hills.
        let presses = (0..<40).map(Chalk.press)
        XCTAssertGreaterThanOrEqual(try XCTUnwrap(presses.min()), 0.9)
        XCTAssertLessThanOrEqual(try XCTUnwrap(presses.max()), 1)
        XCTAssertGreaterThan(Set(presses.map { Int($0 * 1000) }).count, 5)
        XCTAssertEqual(Chalk.kept(1), 1, accuracy: 1e-9)
        XCTAssertEqual(Chalk.kept(0), 0.78, accuracy: 1e-9)
        let tooth = try XCTUnwrap(Chalk.tooth)
        XCTAssertEqual(tooth.width, Chalk.toothSide * Chalk.toothScale)
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
        // The line in the pen's colour (dark on the light page), across the
        // middle: where the chalk lies thickest in each column.
        let along = (40...160).map { x in (44...56).map { pixel(x, $0) }.max { $0[3] < $1[3] }! }
        let most = along.max { $0[3] < $1[3] }!
        XCTAssertGreaterThan(most[3], 180)
        XCTAssertLessThan(most[2], 70)
        // Chalk, not ink: it is not as thick everywhere (the paper's tooth).
        XCTAssertLessThan(along.map { $0[3] }.min()!, most[3] - 15)
        // The echo's rings and broken line in red.
        let reds = (0..<200).flatMap { x in (10...30).map { y in pixel(x, y) } }.filter { $0[3] > 150 }
        XCTAssertFalse(reds.isEmpty)
        XCTAssertTrue(reds.allSatisfy { $0[0] > $0[2] + 40 })
        // On the dark page the same line is light.
        let night = try XCTUnwrap(ChalkMarks.plain(
            marks: marks, labelled: CompositionSketch.labelled(marks), room: EdgeInsets(), size: size, scale: 1, dark: true
        ))
        try bytes.withUnsafeMutableBytes { buffer in
            let context = try XCTUnwrap(CGContext(
                data: buffer.baseAddress, width: 200, height: 100, bitsPerComponent: 8, bytesPerRow: 800,
                space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
            ))
            context.clear(CGRect(x: 0, y: 0, width: 200, height: 100))
            context.draw(night, in: CGRect(x: 0, y: 0, width: 200, height: 100))
        }
        let light = (40...160).flatMap { x in (44...56).map { pixel(x, $0) } }.max { $0[3] < $1[3] }!
        XCTAssertGreaterThan(light[3], 180)
        XCTAssertGreaterThan(light[2], 160)
        // The copy for a screen with headroom (light chalk): the same picture, lit.
        let lit = try XCTUnwrap(ArtGlow.render(night, gain: Chalk.gain))
        XCTAssertEqual(lit.width, plain.width)
        XCTAssertEqual(lit.height, plain.height)
        // One plane holds one mark: the line alone has no red in it, and
        // its brighter copy is cut to where the line lies.
        let alone = try XCTUnwrap(ChalkMarks.plain(
            marks: marks, labelled: CompositionSketch.labelled(marks), room: EdgeInsets(), size: size, scale: 1, only: [0]
        ))
        try bytes.withUnsafeMutableBytes { buffer in
            let context = try XCTUnwrap(CGContext(
                data: buffer.baseAddress, width: 200, height: 100, bitsPerComponent: 8, bytesPerRow: 800,
                space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
            ))
            context.clear(CGRect(x: 0, y: 0, width: 200, height: 100))
            context.draw(alone, in: CGRect(x: 0, y: 0, width: 200, height: 100))
        }
        XCTAssertTrue((0..<200).allSatisfy { x in (10...30).allSatisfy { y in pixel(x, y)[3] == 0 } })
        XCTAssertGreaterThan((40...160).map { x in (44...56).map { pixel(x, $0)[3] }.max()! }.max()!, 180)
        let drawing = ChalkDrawing(marks: marks, labelled: CompositionSketch.labelled(marks), room: EdgeInsets(), only: [0])
        let box = drawing.bounds(in: size)
        XCTAssertLessThan(box.height, 40)
        XCTAssertGreaterThan(box.width, 150)
        XCTAssertTrue(box.contains(CGPoint(x: 100, y: 50)))
        let cut = try XCTUnwrap(ChalkMarks.cut(box, of: alone, scale: 1))
        XCTAssertEqual(cut.frame, cut.pixels)
        XCTAssertTrue(CGRect(x: 0, y: 0, width: 200, height: 100).contains(cut.pixels))
        XCTAssertNil(ChalkMarks.cut(CGRect(x: 300, y: 300, width: 10, height: 10), of: alone, scale: 1))
        // At three pixels a point the cut lies on whole pixels.
        let fine = try XCTUnwrap(ChalkMarks.cut(CGRect(x: 10.2, y: 20.4, width: 30.3, height: 10.1), of: alone, scale: 3))
        XCTAssertEqual(fine.pixels, CGRect(x: 30, y: 61, width: 92, height: 31))
        XCTAssertEqual(fine.frame.minX, 10, accuracy: 1e-9)
    }

    /// The sheet laid down before the reader: the pen stroke after stroke,
    /// the stains under it, then the chalk (Mateusz 2026-11-12 09:47:
    /// "malować / rysować się na żywo").
    func testTheSheetIsDrawnPenThenStainsThenChalk() {
        // Two strokes, the second three times as long: the pen moves at one speed.
        let spans = SheetPlan.spans([100, 300])
        XCTAssertEqual(spans[0].from, 0)
        XCTAssertEqual(spans[0].takes, SheetPlan.pen / 4, accuracy: 1e-9)
        XCTAssertEqual(spans[1].from, SheetPlan.pen / 4, accuracy: 1e-9)
        XCTAssertEqual(spans[1].from + spans[1].takes, SheetPlan.pen, accuracy: 1e-9)
        XCTAssertEqual(SheetPlan.drawn(spans[1], at: 0), 0)
        XCTAssertEqual(SheetPlan.drawn(spans[1], at: SheetPlan.pen), 1)
        XCTAssertEqual(SheetPlan.drawn(spans[0], at: SheetPlan.pen / 8), 0.5, accuracy: 1e-9)
        // A dot of a stroke still takes a moment; no strokes, no trouble.
        XCTAssertEqual(SheetPlan.spans([1, 10_000])[0].takes, SheetPlan.dash)
        XCTAssertTrue(SheetPlan.spans([]).isEmpty)
        XCTAssertEqual(SheetPlan.spans([0, 0]).count, 2)
        // The stains start under the pen still drawing, the chalk comes on
        // the drawn sheet, and all of it is there within three seconds.
        XCTAssertLessThan(SheetPlan.washFrom, SheetPlan.pen)
        XCTAssertLessThanOrEqual(SheetPlan.washFrom + SheetPlan.wash, SheetPlan.whole)
        XCTAssertLessThanOrEqual(SheetPlan.hatchFrom + SheetPlan.hatch, SheetPlan.whole)
        XCTAssertLessThanOrEqual(SheetPlan.marksAt, SheetPlan.whole)
        XCTAssertLessThanOrEqual(SheetPlan.whole, 3)
        // A stroke's line: through its points on the sheet, closed back to its start.
        let size = CGSize(width: 200, height: 100)
        let open = DailyWork.Stroke(points: [Spot(x: 0, y: 0), Spot(x: 0.5, y: 0), Spot(x: 1, y: 1)], sharp: true)
        XCTAssertEqual(SheetPlan.line(open, in: size), [.zero, CGPoint(x: 100, y: 0), CGPoint(x: 200, y: 100)])
        XCTAssertEqual(SheetPlan.length(SheetPlan.line(open, in: size)), 100 + hypot(100, 100), accuracy: 1e-6)
        let ring = DailyWork.Stroke(points: open.points, sharp: true, closed: true)
        XCTAssertEqual(SheetPlan.line(ring, in: size).last, CGPoint.zero)
        XCTAssertGreaterThan(SheetPlan.line(DailyWork.Stroke(points: open.points), in: size).count, 10)
        XCTAssertTrue(SheetPlan.line(DailyWork.Stroke(points: [Spot(x: 0, y: 0)]), in: size).isEmpty)
        // The stains come up all over the sheet at once, evenly, not from
        // places (Mateusz 2026-11-12 10:54): nothing before their time,
        // half of them half-way, all of them at the end, never going back.
        XCTAssertEqual(SheetPlan.washShown(at: SheetPlan.washFrom), 0)
        XCTAssertEqual(SheetPlan.washShown(at: SheetPlan.washFrom + SheetPlan.wash / 2), 0.5, accuracy: 1e-9)
        XCTAssertEqual(SheetPlan.washShown(at: SheetPlan.washFrom + SheetPlan.wash), 1)
        XCTAssertEqual(SheetPlan.washShown(at: SheetPlan.whole), 1)
        let rising = stride(from: 0.0, through: SheetPlan.whole, by: 0.05).map { SheetPlan.washShown(at: $0) }
        XCTAssertTrue(zip(rising, rising.dropFirst()).allSatisfy { $0.0 <= $0.1 })
        // The sheet's pictures: whole from a server before the layers, else
        // its stains and its pen, for the page's colour.
        XCTAssertEqual(CompositionSketch.sheetRefs("", layers: true, dark: false), [])
        XCTAssertEqual(CompositionSketch.sheetRefs("/s?v=1", layers: false, dark: true), [.path("/s?v=1&dark=1")])
        XCTAssertEqual(
            CompositionSketch.sheetRefs("/s?v=1", layers: true, dark: false),
            [.path("/s?v=1&layer=wash"), .path("/s?v=1&layer=pen")]
        )
        // From a server that has them with the page's margin beside the
        // field, those: a stain runs out and a stroke goes on past the
        // frame (Mateusz 2026-11-12 11:04).
        XCTAssertEqual(
            CompositionSketch.sheetRefs("/s?v=1", layers: true, bleed: 0.08, dark: true),
            [.path("/s?v=1&dark=1&layer=wash-bleed"), .path("/s?v=1&dark=1&layer=pen-bleed")]
        )
        XCTAssertEqual(CompositionSketch.sheetRefs("/s?v=1", layers: false, bleed: 0.08, dark: false), [.path("/s?v=1")])
    }

    func testTheSheetRunsOutOfItsFrameAtTheSides() {
        // A picture wider than the field by a tenth of it on each side:
        // the field is the middle of it.
        let wide = CGSize(width: 240, height: 100)
        let field = SheetPlan.field(in: wide, bleed: 0.1)
        XCTAssertEqual(field.minX, 20, accuracy: 1e-9)
        XCTAssertEqual(field.width, 200, accuracy: 1e-9)
        XCTAssertEqual(field.height, 100)
        XCTAssertEqual(SheetPlan.field(in: wide, bleed: 0), CGRect(origin: .zero, size: wide))
        // A stroke that ends at the right side heading out of it is
        // followed over the margin; its other end, inside, is not.
        let out = DailyWork.Stroke(points: [Spot(x: 0.5, y: 0.5), Spot(x: 0.99, y: 0.5)], sharp: true)
        let line = SheetPlan.line(out, in: field, margin: field.minX)
        XCTAssertEqual(line.count, 3)
        XCTAssertEqual(line[0].x, 120, accuracy: 1e-6)
        XCTAssertEqual(line[0].y, 50, accuracy: 1e-6)
        XCTAssertEqual(line[2].x, 240, accuracy: 1e-6)
        XCTAssertEqual(line[2].y, 50, accuracy: 1e-6)
        // To the left the same, at the stroke's start.
        let back = DailyWork.Stroke(points: [Spot(x: 0.02, y: 0.4), Spot(x: 0.3, y: 0.6)], sharp: true)
        let left = SheetPlan.line(back, in: field, margin: field.minX)
        XCTAssertEqual(left.count, 3)
        XCTAssertLessThan(left[0].x, field.minX)
        XCTAssertLessThan(left[0].y, left[1].y)
        // One that runs along the side, one that ends inside, a closed
        // one, and any on a sheet with no margin: as they are.
        let along = DailyWork.Stroke(points: [Spot(x: 0.99, y: 0.2), Spot(x: 0.99, y: 0.8)], sharp: true)
        XCTAssertEqual(SheetPlan.line(along, in: field, margin: field.minX).count, 2)
        let inside = DailyWork.Stroke(points: [Spot(x: 0.2, y: 0.2), Spot(x: 0.8, y: 0.8)], sharp: true)
        XCTAssertEqual(SheetPlan.line(inside, in: field, margin: field.minX).count, 2)
        let ring = DailyWork.Stroke(points: out.points + [Spot(x: 0.7, y: 0.9)], sharp: true, closed: true)
        XCTAssertEqual(SheetPlan.line(ring, in: field, margin: field.minX).count, 4)
        XCTAssertEqual(SheetPlan.line(out, in: field, margin: 0).count, 2)
        // A steep one is not carried further than a little over twice the margin.
        let steep = SheetPlan.past(CGPoint(x: 218, y: 50), from: CGPoint(x: 210, y: 30), field: field, margin: 20)
        XCTAssertEqual(hypot((steep?.x ?? 0) - 218, (steep?.y ?? 0) - 50), 44, accuracy: 1e-6)
    }

    func testTheDemoHasASheetForItsStudyInBothAppearances() async throws {
        let demo = DemoBackend()
        let work = try await demo.daily(day: nil, wait: 0, lists: false)
        let sheet = try XCTUnwrap(work.compositionSheet)
        XCTAssertFalse(sheet.isEmpty)
        // In its two layers, as a server that has them: the stains and the pen.
        XCTAssertEqual(work.compositionLayers, true)
        // With the page's margin beside the field, as the server's renderer makes them.
        XCTAssertEqual(work.compositionBleed, DemoStudies.bleed)
        let wideRef = try XCTUnwrap(CompositionSketch.sheetRefs(sheet, layers: true, bleed: 0.08, dark: false).first)
        let wideURL = try XCTUnwrap(demo.request(for: wideRef)?.url)
        XCTAssertTrue(wideURL.lastPathComponent.hasSuffix("-wash.jpg"))
        XCTAssertNotNil(UIImage(contentsOfFile: wideURL.path))
        let refs = CompositionSketch.sheetRefs(sheet, layers: true, dark: false) + CompositionSketch.sheetRefs(sheet, layers: true, dark: true)
        XCTAssertEqual(refs.count, 4)
        for ref in refs {
            let url = try XCTUnwrap(demo.request(for: ref)?.url)
            XCTAssertNotNil(UIImage(contentsOfFile: url.path))
        }
        XCTAssertEqual(try XCTUnwrap(demo.request(for: refs[2])?.url).lastPathComponent.hasSuffix("-wash-dark.jpg"), true)
        XCTAssertEqual(try XCTUnwrap(demo.request(for: refs[1])?.url).lastPathComponent.hasSuffix("-pen.png"), true)
        // With the strokes its pen was drawn along, on the sheet.
        let strokes = try XCTUnwrap(work.composition?.takes.first?.sketch)
        XCTAssertGreaterThan(strokes.count, 8)
        XCTAssertTrue(strokes.allSatisfy { $0.points.count >= 2 && $0.points.allSatisfy { (0...1).contains($0.x) && (0...1).contains($0.y) } })
        // Every other demo study has its sheets, and its marks lie in the field.
        for study in DemoStudies.named.values {
            let layers = CompositionSketch.sheetRefs(DemoStudies.sheet(study.id), layers: true, dark: false)
                + CompositionSketch.sheetRefs(DemoStudies.sheet(study.id), layers: true, dark: true)
            for ref in layers {
                XCTAssertNotNil(demo.request(for: ref)?.url, study.id)
            }
            XCTAssertGreaterThan(DemoStudies.sketches[study.id]?.count ?? 0, 8, study.id)
            for mark in study.take.marksInField {
                for point in mark.points {
                    XCTAssertTrue((-0.5...1.5).contains(point.x) && (-0.5...1.5).contains(point.y))
                }
            }
        }
        XCTAssertNotNil(DemoStudies.named["shower"]?.take.field)
    }
}
