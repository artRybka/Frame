import ImageIO
import UIKit
import simd
import XCTest
@testable import Frame

/// "Dodaj własne dzieło": the technique's line and chips, the size's words,
/// and what the server sends of his work.
final class OwnWorksTests: XCTestCase {
    func testTheTechniqueLineIsWrittenFromTheChipsAndReadBack() {
        XCTAssertEqual(OwnTechnique.medium(technique: "oil", support: "canvas"), "olej na płótnie")
        XCTAssertEqual(OwnTechnique.medium(technique: "watercolour", support: nil), "akwarela")
        XCTAssertEqual(OwnTechnique.medium(technique: nil, support: "paper"), "na papierze")
        XCTAssertEqual(OwnTechnique.read("olej na płótnie")?.technique, "oil")
        XCTAssertEqual(OwnTechnique.read("olej na płótnie")?.support, "canvas")
        XCTAssertEqual(OwnTechnique.read("Akwarela")?.technique, "watercolour")
        // His own words stay his: no chip claims them.
        XCTAssertNil(OwnTechnique.read("olej i złoto na desce lipowej"))
    }

    func testTheSizeIsHeightByWidthInCentimetres() {
        XCTAssertEqual(OwnWork(heightCm: 46, widthCm: 55.5).sizeText, "46 × 55,5 cm")
        XCTAssertNil(OwnWork(heightCm: 46).sizeText)
        XCTAssertEqual(Names.ownCollection("Salon"), "Moja kolekcja · Salon")
        XCTAssertEqual(Names.ownCollection(""), "Moja kolekcja")
    }

    func testHisWorkComesWithWhatHeWrote() throws {
        let json = """
        {"id": "upload:1", "kind": "own", "source": "upload", "title": "Klif", "artist": "Stefan Nowak",
         "date_text": "ok. 1965", "medium": "olej na płótnie", "colors": [], "favorite": false,
         "own": {"hangs": "Salon", "origin": "Po dziadku", "height_cm": 46, "width_cm": 55}}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let summary = try decoder.decode(ItemSummary.self, from: Data(json.utf8))
        XCTAssertTrue(summary.isOwnWork)
        XCTAssertEqual(summary.own?.hangs, "Salon")
        XCTAssertEqual(summary.own?.sizeText, "46 × 55 cm")
    }

    func testAColourChartBesideTheWorkComesWithThePhotograph() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let with = """
        {"token": "a1", "width": 3024, "height": 4032, "corners": null, "shape": "",
         "chart": [[0.7, 0.1], [0.9, 0.1], [0.9, 0.4], [0.7, 0.4]]}
        """
        XCTAssertEqual(try decoder.decode(OwnIncoming.self, from: Data(with.utf8)).chart?.count, 4)
        // A server before the chart, or a photograph without one.
        let without = #"{"token": "a1", "width": 3024, "height": 4032, "corners": null, "shape": ""}"#
        XCTAssertNil(try decoder.decode(OwnIncoming.self, from: Data(without.utf8)).chart)
    }

    func testTheDescriptionGoesInTheServersWords() throws {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let text = OwnDescription(title: " Klif ", dateText: "1965", heightCm: 46, widthCm: 55)
        let sent = try JSONSerialization.jsonObject(with: encoder.encode(text.trimmed)) as? [String: Any]
        XCTAssertEqual(sent?["title"] as? String, "Klif")
        XCTAssertEqual(sent?["date_text"] as? String, "1965")
        XCTAssertEqual(sent?["height_cm"] as? Double, 46)
    }

    func testHisSizeGivesTheWorkItsShape() throws {
        // The corners give 1.25; he measured 46 × 55 cm: the work is 55 / 46.
        XCTAssertEqual(try XCTUnwrap(OwnWork(heightCm: 46, widthCm: 55).ratio(1.25)), 55.0 / 46.0, accuracy: 1e-9)
        // No size, or one far off the photograph (a slip), leaves the corners' shape.
        XCTAssertNil(OwnWork(heightCm: 46).ratio(1.25))
        XCTAssertNil(OwnWork(heightCm: 46, widthCm: 550).ratio(1.25))
    }

    /// The LiDAR's depth of a wall turned a little away, the phone upright:
    /// the work's corners on the photograph give its size on the wall.
    func testTheWorksSizeIsMeasuredOnTheWallFromItsCorners() throws {
        let width = 256, height = 192
        let fx = 200.0, cx = 128.0, cy = 96.0
        // The wall: z = 1.2 + 0.2·x (metres along the lens).
        var values = [Float](repeating: 0, count: width * height)
        for row in 0 ..< height {
            for col in 0 ..< width {
                let rx = (Double(col) + 0.5 - cx) / fx
                values[row * width + col] = Float(1.2 / (1 - 0.2 * rx))
            }
        }
        let depth = OwnDepth(width: width, height: height, values: values, fx: fx, fy: fx, cx: cx, cy: cy, orientation: .right)
        // 50 cm along the sensor's x (up and down on the upright photograph), 40 across.
        let along = SIMD3(1, 0, 0.2) / simd_length(SIMD3(1, 0, 0.2))
        let across = SIMD3(0.0, 1, 0)
        func corner(_ a: Double, _ b: Double) -> [Double] {
            let p = SIMD3(0, 0, 1.2) + along * a + across * b
            let xs = (fx * p.x / p.z + cx) / Double(width), ys = (fx * p.y / p.z + cy) / Double(height)
            return [1 - ys, xs]  // upright: u = 1 − y, v = x
        }
        let corners = [corner(-0.25, 0.2), corner(-0.25, -0.2), corner(0.25, -0.2), corner(0.25, 0.2)]
        XCTAssertLessThan(corners[0][0], corners[1][0])  // top left, then top right
        XCTAssertLessThan(corners[1][1], corners[2][1])  // top, then bottom
        let size = try XCTUnwrap(depth.size(corners))
        XCTAssertEqual(size, OwnDepth.Size(heightCm: 50, widthCm: 40))

        // No depth there: no size, nothing guessed.
        let blind = OwnDepth(width: width, height: height, values: [Float](repeating: .nan, count: width * height),
                             fx: fx, fy: fx, cx: cx, cy: cy, orientation: .right)
        XCTAssertNil(blind.size(corners))
        XCTAssertEqual(OwnDepth.round(12.3), 12.5)
        XCTAssertEqual(OwnDepth.round(64.6), 65)
    }

    /// The upright photograph's point on the map, however the phone was held.
    func testAnUprightPointLiesOnTheSensorAsThePhoneWasTurned() {
        func at(_ orientation: CGImagePropertyOrientation) -> [Double] {
            let depth = OwnDepth(width: 100, height: 50, values: [], fx: 1, fy: 1, cx: 0, cy: 0, orientation: orientation)
            let point = depth.sensor([0.1, 0.2])
            return [point.x, point.y]
        }
        XCTAssertEqual(at(.up), [10, 10])
        XCTAssertEqual(at(.right), [20, 45])  // upright: the sensor turned a quarter clockwise
        XCTAssertEqual(at(.left), [80, 5])
        XCTAssertEqual(at(.down), [90, 40])
    }

    /// Mateusz 2026-11-16: "Dla własnych dzieł ustaw zdecydowanie wyższą
    /// jakość niż 4000px": the server is sent the camera's own files, and
    /// the work comes back in tiles of every pixel for the full screen.
    func testThePhotographsAreSentAsTheCameraWroteThem() {
        let picture = UIImage()
        var shots = OwnShots(first: picture, files: [Data([1])])
        XCTAssertEqual(shots.file(0), Data([1]))
        shots.sides.append(picture)
        // A side photograph without its file: none is trusted to be in step.
        XCTAssertNil(shots.file(0))
        shots.files.append(Data([2]))
        XCTAssertEqual(shots.file(1), Data([2]))
        XCTAssertNil(shots.file(2))
        XCTAssertNil(OwnShots(first: picture).file(0))  // the demo's
        XCTAssertFalse(OwnPicture.sendable(Data([0, 1, 2])))
    }

    func testAWorkOfHisOwnComesInTilesOfEveryPixel() throws {
        let json = """
        {"width": 4838, "height": 4014, "stamp": "ab12cd34",
         "tiles": [{"id": "0-0", "x": 0, "y": 0, "w": 0.5, "h": 0.5, "pixels": 2419},
                   {"id": "0-1", "x": 0.5, "y": 0, "w": 0.5, "h": 0.5, "pixels": 2419}]}
        """
        let fine = try LiveBackend.decoder().decode(FineView.self, from: Data(json.utf8))
        XCTAssertEqual(fine.tiles.count, 2)
        XCTAssertEqual(fine.tiles[1].unit, CGRect(x: 0.5, y: 0, width: 0.5, height: 0.5))
        // The whole is as wide as its tiles' pixels reach: twice the 2419.
        let across = fine.tiles.map { CGFloat($0.pixels) / $0.unit.width }.max()
        XCTAssertEqual(across, 4838)
        let none = try LiveBackend.decoder().decode(
            FineView.self, from: Data(#"{"width": 0, "height": 0, "stamp": "", "tiles": []}"#.utf8)
        )
        XCTAssertTrue(none.tiles.isEmpty)
    }

    /// The helper frame of the side photographs (Mateusz 2026-11-16: "z
    /// ramką pomocniczą na ekranie pokazująca gdzie ma się znajdować
    /// dzieło"): the work's outline as it shows from 30° to the side.
    func testTheHelperFrameIsTheWorkSeenFromTheSide() throws {
        let front = [CGPoint(x: 0.2, y: 0.3), CGPoint(x: 0.8, y: 0.3), CGPoint(x: 0.8, y: 0.7), CGPoint(x: 0.2, y: 0.7)]
        // From the front it is itself.
        for (seen, was) in zip(OwnScanView.seen(front, from: 0), front) {
            XCTAssertEqual(seen.x, was.x, accuracy: 1e-9)
            XCTAssertEqual(seen.y, was.y, accuracy: 1e-9)
        }
        // From the left its left side is nearer: taller, and the whole narrower.
        let left = OwnScanView.seen(front, from: -OwnScanView.side)
        XCTAssertGreaterThan(left[3].y - left[0].y, 0.4 * 1.1)
        XCTAssertLessThan(left[2].y - left[1].y, 0.4 * 0.95)
        XCTAssertLessThan(left[1].x - left[0].x, 0.6 * 0.95)
        // From the right, the mirror of it.
        let right = OwnScanView.seen(front, from: OwnScanView.side)
        XCTAssertEqual(right[2].y - right[1].y, left[3].y - left[0].y, accuracy: 1e-9)
        XCTAssertEqual(1 - right[1].x, left[0].x, accuracy: 1e-9)
        // The angle is read back off the outline, and the outline lies in its frame.
        XCTAssertEqual(try XCTUnwrap(OwnScanView.angle(of: left, front: front)), -30, accuracy: 0.5)
        let nearly = OwnScanView.seen(front, from: -27)
        XCTAssertEqual(try XCTUnwrap(OwnScanView.angle(of: nearly, front: front)), -27, accuracy: 0.5)
        XCTAssertTrue(OwnScanView.near.contains(27))
        XCTAssertLessThan(OwnScanView.off(nearly, frame: left), 0.03)
        XCTAssertGreaterThan(OwnScanView.off(front, frame: left), 0.05)
    }

    /// From where the phone sees the work is read off its outline alone,
    /// however far away it stands (Mateusz 2026-11-16: "kąt wykonywania
    /// kolejnych ujęć jest zbyt mały"; the helper counts the angle itself).
    func testTheAngleIsReadOffTheOutlineWhateverTheDistance() throws {
        let front = [CGPoint(x: 0.2, y: 0.3), CGPoint(x: 0.8, y: 0.3), CGPoint(x: 0.8, y: 0.7), CGPoint(x: 0.2, y: 0.7)]
        let shape = try XCTUnwrap(OwnScanView.shape(of: front))
        XCTAssertEqual(shape, 0.4 / 0.75 / 0.6, accuracy: 1e-9)
        for degrees in [-38.0, -30, -22, 0, 12, 30] {
            let outline = OwnScanView.seen(front, from: degrees)
            XCTAssertEqual(try XCTUnwrap(OwnScanView.turn(of: outline, shape: shape)), degrees, accuracy: 0.01)
            XCTAssertEqual(try XCTUnwrap(OwnScanView.away(outline, front: front)), 1, accuracy: 0.001)
        }
        // Twice as far away the work is half as large: the same angle.
        let small = front.map { CGPoint(x: 0.5 + ($0.x - 0.5) / 2, y: 0.5 + ($0.y - 0.5) / 2) }
        XCTAssertEqual(try XCTUnwrap(OwnScanView.turn(of: OwnScanView.seen(small, from: -30), shape: shape)), -30, accuracy: 0.01)
        XCTAssertEqual(try XCTUnwrap(OwnScanView.away(small, front: front)), 2, accuracy: 0.001)
        // The phone on its side: a wide picture, the lens as many half-widths shorter.
        let wide = [CGPoint(x: 0.25, y: 0.2), CGPoint(x: 0.75, y: 0.2), CGPoint(x: 0.75, y: 0.8), CGPoint(x: 0.25, y: 0.8)]
        let lens = OwnScanView.focal * 0.75
        let seen = OwnScanView.seen(wide, from: 30, aspect: 4.0 / 3, focal: lens)
        let wideShape = try XCTUnwrap(OwnScanView.shape(of: wide, aspect: 4.0 / 3))
        XCTAssertEqual(try XCTUnwrap(OwnScanView.turn(of: seen, shape: wideShape, aspect: 4.0 / 3, focal: lens)), 30, accuracy: 0.01)
    }

    /// What the helper says (Mateusz 2026-11-16 09:52 UTC: "Czy pomocnik
    /// przy aparacie mówi żeby zbliżyć się do dzieła, oddalić? Mógłby to
    /// robić?").
    func testTheHelperSaysWhereToStand() {
        let front = [CGPoint(x: 0.2, y: 0.3), CGPoint(x: 0.8, y: 0.3), CGPoint(x: 0.8, y: 0.7), CGPoint(x: 0.2, y: 0.7)]
        // The first photograph: whole, large enough, from the front.
        XCTAssertEqual(OwnScanView.first(nil), .lost)
        XCTAssertEqual(OwnScanView.first(front), .hold)
        XCTAssertEqual(OwnScanView.first(OwnScanView.seen(front, from: -3)), .hold)
        XCTAssertEqual(OwnScanView.first(front.map { CGPoint(x: 0.5 + ($0.x - 0.5) / 2, y: 0.5 + ($0.y - 0.5) / 2) }), .nearer)
        XCTAssertEqual(OwnScanView.first(front.map { CGPoint(x: $0.x - 0.2, y: $0.y) }), .farther)
        XCTAssertEqual(OwnScanView.first(OwnScanView.seen(front, from: -12)), .straight)
        let leaning = [CGPoint(x: 0.2, y: 0.3), CGPoint(x: 0.8, y: 0.3), CGPoint(x: 0.74, y: 0.7), CGPoint(x: 0.26, y: 0.7)]
        XCTAssertEqual(OwnScanView.first(leaning), .level)

        // The one from the left: on to the left, there, too far, back.
        let left = -OwnScanView.side
        XCTAssertEqual(OwnScanView.side(target: left, angle: 0), .go(left: true))
        XCTAssertEqual(OwnScanView.side(target: left, angle: -15), .go(left: true))
        XCTAssertEqual(OwnScanView.side(target: left, angle: -24), .hold)
        XCTAssertEqual(OwnScanView.side(target: left, angle: -36), .hold)
        XCTAssertEqual(OwnScanView.side(target: left, angle: -45), .go(left: false))
        // The one from the right starts where the left one was taken.
        XCTAssertEqual(OwnScanView.side(target: OwnScanView.side, angle: -30), .go(left: false))
        XCTAssertEqual(OwnScanView.side(target: OwnScanView.side, angle: 29), .hold)
        XCTAssertEqual(OwnScanView.side(target: OwnScanView.side, angle: 44), .go(left: true))
        // Standing right, but too far away or with the work cut off.
        XCTAssertEqual(OwnScanView.side(target: left, angle: -30, away: 1.5), .nearer)
        XCTAssertEqual(OwnScanView.side(target: left, angle: -30, away: 1.2), .hold)
        XCTAssertEqual(OwnScanView.side(target: left, angle: -30, fits: false), .farther)
        // Standing right with the phone looking past the work: the work's
        // middle is to be in the sight (Mateusz 2026-11-16 13:35 UTC).
        XCTAssertEqual(OwnScanView.offAim(front), 0, accuracy: 1e-9)
        XCTAssertEqual(OwnScanView.offAim(front.map { CGPoint(x: $0.x + 0.2, y: $0.y) }), 0.2, accuracy: 1e-9)
        XCTAssertEqual(OwnScanView.offAim(front.map { CGPoint(x: $0.x, y: $0.y + 0.15) }), 0.2, accuracy: 1e-9)
        XCTAssertEqual(OwnScanView.offAim(front.map { CGPoint(x: $0.x + 0.15, y: $0.y) }, aspect: 4.0 / 3), 0.2, accuracy: 1e-9)
        XCTAssertEqual(OwnScanView.side(target: left, angle: -30, aim: 0.05), .hold)
        XCTAssertEqual(OwnScanView.side(target: left, angle: -30, aim: 0.2), .aim)
        XCTAssertEqual(OwnScanView.side(target: left, angle: -30, aim: 0.13), .aim)
        XCTAssertEqual(OwnScanView.side(target: left, angle: -30, aim: 0.13, held: true), .hold)
        XCTAssertEqual(OwnScanView.side(target: left, angle: -10, aim: 0.2), .go(left: true))
        XCTAssertEqual(OwnScanView.side(target: left, angle: -30, fits: false, aim: 0.3), .aim)
        // And its four corners seen ("łapanie narożników"): on the way
        // there they are not waited for.
        XCTAssertEqual(OwnScanView.side(target: left, angle: -30, seen: false), .corners)
        XCTAssertEqual(OwnScanView.side(target: left, angle: -30, seen: false, held: true), .corners)
        XCTAssertEqual(OwnScanView.side(target: left, angle: -10, seen: false), .go(left: true))
        // Walking to the left turns the phone to the right. Turned to the
        // left instead (the way the arrows point), it was turned, not
        // walked with ("Odruchem przy pokazanych strzałkach jest samo
        // przekręcenie telefonu w lewo").
        XCTAssertEqual(OwnScanView.side(target: left, angle: 0, stray: 14), .turned(left: true))
        XCTAssertEqual(OwnScanView.side(target: left, angle: 0, stray: 6), .go(left: true))
        XCTAssertEqual(OwnScanView.side(target: left, angle: -12, stray: -14), .go(left: true))
        XCTAssertEqual(OwnScanView.side(target: OwnScanView.side, angle: -30, stray: -14), .turned(left: false))
        XCTAssertEqual(OwnScanView.side(target: OwnScanView.side, angle: -10, stray: 20), .go(left: false))
        // Too far to the left and coming back: the phone turns to the left.
        XCTAssertEqual(OwnScanView.side(target: left, angle: -45, stray: 12), .go(left: false))
        XCTAssertEqual(OwnScanView.side(target: left, angle: -30, stray: 14), .hold)
        let sight = CGSize(width: 300, height: 400)
        XCTAssertEqual(OwnScanSight.radius(in: sight), 33, accuracy: 1e-9)
        XCTAssertTrue(OwnScanSight.inside(CGPoint(x: 0.55, y: 0.45), size: sight))
        XCTAssertFalse(OwnScanSight.inside(CGPoint(x: 0.65, y: 0.5), size: sight))

        // The words: no shutter but when the work's edges are not found.
        var look = OwnScanLook(number: 2)
        look.advice = .go(left: true)
        XCTAssertNil(look.pill)
        XCTAssertEqual(look.line, "Zrób krok w lewo, celując w dzieło")
        XCTAssertEqual(look.walk, true)
        look.advice = .go(left: false)
        XCTAssertEqual(look.line, "Za daleko w bok, wróć trochę")
        XCTAssertEqual(look.walk, false)
        // The phone turned where he was to walk, or held another way than
        // at the first photograph (Mateusz 2026-11-16 15:02 UTC).
        look.advice = .turned(left: true)
        XCTAssertEqual(look.pill?.text, "Nie obracaj telefonu")
        XCTAssertEqual(look.line, "Zrób krok w lewo, a telefon skieruj na dzieło")
        XCTAssertEqual(look.walk, true)
        look.advice = .rolled
        XCTAssertEqual(look.pill?.text, "Nie obracaj telefonu")
        XCTAssertEqual(look.line, "Trzymaj telefon tak jak przy pierwszym zdjęciu")
        XCTAssertNil(look.walk)
        look.advice = .nearer
        XCTAssertEqual(look.pill?.text, "Podejdź bliżej")
        look.advice = .aim
        XCTAssertEqual(look.pill?.text, "Wyceluj w dzieło")
        look.advice = .corners
        XCTAssertEqual(look.line, "Nie widzę wszystkich narożników dzieła")
        look.manual = true
        XCTAssertEqual(look.line, "Zrób zdjęcie sam, gdy całe dzieło jest w kadrze")
        look.manual = false
        look.advice = .farther
        XCTAssertEqual(look.pill?.text, "Odsuń się")
        look.advice = .hold
        XCTAssertTrue(look.matched)
        XCTAssertEqual(look.line, "Dobrze. Robię zdjęcie z lewej")
        look.advice = .lost
        XCTAssertNil(look.pill)
        look.manual = true
        XCTAssertEqual(look.line, "Zrób zdjęcie sam")
    }

    /// The outline's corners in their order, on the screen and as the world
    /// stands when the phone is held on its side; the work among other
    /// rectangles in the picture.
    func testTheOutlineIsOrderedTurnedAndFollowed() {
        let front = [CGPoint(x: 0.2, y: 0.3), CGPoint(x: 0.8, y: 0.3), CGPoint(x: 0.8, y: 0.7), CGPoint(x: 0.2, y: 0.7)]
        XCTAssertEqual(OwnScanView.ordered([front[2], front[0], front[3], front[1]]), front)
        for quarter in [1, -1, 0] {
            for corner in front {
                let back = OwnScanView.shown(OwnScanView.upright(corner, quarter: quarter), quarter: quarter)
                XCTAssertEqual(back.x, corner.x, accuracy: 1e-9)
                XCTAssertEqual(back.y, corner.y, accuracy: 1e-9)
            }
        }
        // The phone's top to the left: the screen's top edge is the world's
        // left, its right edge the world's top (Mateusz 2026-11-16: "Nie
        // obsługuje robienia zdjęcia w poziomie": they were the other way
        // round, the world upside down).
        let turned = OwnScanView.upright(CGPoint(x: 0.2, y: 0.3), quarter: 1)
        XCTAssertEqual(turned.x, 0.3, accuracy: 1e-9)
        XCTAssertEqual(turned.y, 0.8, accuracy: 1e-9)
        let top = OwnScanView.upright(CGPoint(x: 0.5, y: 0.05), quarter: 1)
        XCTAssertLessThan(top.x, 0.1)
        let right = OwnScanView.upright(CGPoint(x: 0.95, y: 0.5), quarter: 1)
        XCTAssertLessThan(right.y, 0.1)
        // Its top to the right: the other way.
        XCTAssertGreaterThan(OwnScanView.upright(CGPoint(x: 0.5, y: 0.05), quarter: -1).x, 0.9)
        // A tall work on the screen is a tall work in the world with the
        // phone upright only: on its side the outline is ordered anew.
        let world = OwnScanView.ordered(front.map { OwnScanView.upright($0, quarter: 1) })
        XCTAssertEqual(world[0].x, 0.3, accuracy: 1e-9)
        XCTAssertEqual(world[0].y, 0.2, accuracy: 1e-9)
        XCTAssertEqual(world[2].x, 0.7, accuracy: 1e-9)
        XCTAssertEqual(world[2].y, 0.8, accuracy: 1e-9)
        // A work seen from the left on the screen of a phone on its side
        // is seen from the left in the world: its left side the taller.
        let seen = OwnScanView.seen(front, from: -30, aspect: 4.0 / 3, focal: OwnScanView.focal * 0.75)
        let screen = seen.map { OwnScanView.shown($0, quarter: 1) }
        let back = OwnScanView.ordered(screen.map { OwnScanView.upright($0, quarter: 1) })
        let sides = OwnScanView.sides(back, aspect: 4.0 / 3)
        XCTAssertGreaterThan(sides.left, sides.right)
        // On the screen that taller side lies along the top edge.
        XCTAssertLessThan(screen[0].y, 0.5)
        XCTAssertLessThan(screen[3].y, 0.5)

        // The largest rectangle is the work, until one is followed.
        let door = [CGPoint(x: 0.05, y: 0.1), CGPoint(x: 0.95, y: 0.1), CGPoint(x: 0.95, y: 0.95), CGPoint(x: 0.05, y: 0.95)]
        XCTAssertEqual(OwnCameraSession.area(front), 0.24, accuracy: 1e-9)
        XCTAssertEqual(OwnCameraSession.work(among: [front, door], last: nil), door)
        let moved = front.map { CGPoint(x: $0.x + 0.03, y: $0.y - 0.02) }
        XCTAssertNil(OwnCameraSession.work(among: [], last: front))
        // One a little larger about it (its frame) does not take over.
        let framed = [CGPoint(x: 0.27, y: 0.17), CGPoint(x: 0.73, y: 0.17), CGPoint(x: 0.73, y: 0.83), CGPoint(x: 0.27, y: 0.83)]
        XCTAssertEqual(OwnCameraSession.work(among: [framed, moved], last: front), moved)
        // His painting of bottles, 2026-11-16: the rectangle painted in
        // its middle was followed; the work about it takes over.
        XCTAssertTrue(OwnCameraSession.part(front, of: door))
        XCTAssertFalse(OwnCameraSession.part(front, of: framed))
        XCTAssertFalse(OwnCameraSession.part(moved.map { CGPoint(x: $0.x + 0.3, y: $0.y) }, of: door))
        XCTAssertEqual(OwnCameraSession.work(among: [door, moved], last: front), door)
        // The wall about the work, running out of the picture, is not it,
        // whether first seen or followed.
        let wall = [CGPoint(x: 0, y: 0.08), CGPoint(x: 0.97, y: 0.12), CGPoint(x: 0.97, y: 0.9), CGPoint(x: 0.1, y: 0.95)]
        XCTAssertFalse(OwnCameraSession.whole(wall))
        XCTAssertEqual(OwnCameraSession.work(among: [wall, front], last: nil), front)
        XCTAssertEqual(OwnCameraSession.work(among: [wall, front], last: wall), front)
        XCTAssertEqual(OwnCameraSession.work(among: [wall], last: nil), wall)
        // The work slips a look and a part of it is found: it stays for a
        // few looks, then the part is what there is.
        var shown: [CGPoint]? = door
        var missed = 0
        for _ in 0 ..< OwnCameraSession.patience {
            (shown, missed) = OwnCameraSession.kept(OwnCameraSession.work(among: [front], last: shown), was: shown, missed: missed)
            XCTAssertEqual(shown, door)
        }
        (shown, missed) = OwnCameraSession.kept(OwnCameraSession.work(among: [front], last: shown), was: shown, missed: missed)
        XCTAssertEqual(shown, front)
        XCTAssertEqual(missed, 0)
        // Nothing found is nothing shown, at once.
        XCTAssertNil(OwnCameraSession.kept(nil, was: door, missed: 0).outline)
    }

    /// Mateusz 2026-11-16 16:44 UTC ("etap „łączę trzy zdjęcia, usuwam
    /// odblaski” trwa bardzo długo"): each photograph of a scan goes to
    /// the server when it is taken, the sides one after another under the
    /// first's token, and the work is looked for in the first meanwhile.
    @MainActor
    func testAScansPhotographsAreSentAsTheyAreTaken() async throws {
        let demo = DemoBackend()
        func picture() -> UIImage {
            UIGraphicsImageRenderer(size: CGSize(width: 40, height: 30)).image { context in
                UIColor.gray.setFill()
                context.fill(CGRect(x: 0, y: 0, width: 40, height: 30))
            }
        }
        let sending = OwnSending()
        // Nothing taken: no side photographs with the server, none looked at.
        let none = await sending.sidesSent()
        XCTAssertFalse(none)
        let unseen = await sending.looked()
        XCTAssertNil(unseen)

        var shots = OwnShots(first: picture())
        sending.send(shots, with: demo)
        let first = try await sending.photo()
        // One photograph is no scan.
        let alone = await sending.sidesSent()
        XCTAssertFalse(alone)
        shots.sides.append(picture())
        sending.send(shots, with: demo)
        shots.sides.append(picture())
        sending.send(shots, with: demo)
        // All of them again (the third taken, the steps go on): none twice.
        sending.send(shots, with: demo)
        let sent = await sending.sidesSent()
        XCTAssertTrue(sent)
        let same = try await sending.photo()
        XCTAssertEqual(same.token, first.token)
        let looked = await sending.looked()
        XCTAssertEqual(looked?.token, first.token)
        let merged = try await demo.mergeOwnPhotos(token: first.token, outline: nil)
        XCTAssertEqual(merged.used, 2)
        // "Na wprost": the first photograph waits again as it was taken.
        try await demo.keepOwnFirstPhoto(token: first.token)
        do {
            try await demo.keepOwnFirstPhoto(token: "none")
            XCTFail("no such photograph waits")
        } catch {}
    }

    /// "Zrób zdjęcie ponownie": the way there closes at once, and the
    /// new photograph is kept behind the work's card, which takes the
    /// work as kept (Mateusz 2026-11-16 21:48 UTC, the long "Dalej").
    @MainActor
    func testANewPhotographIsKeptBehindTheCard() async throws {
        let model = AppModel()
        let image = UIGraphicsImageRenderer(size: CGSize(width: 40, height: 30)).image { context in
            UIColor.gray.setFill()
            context.fill(CGRect(x: 0, y: 0, width: 40, height: 30))
        }
        let data = try XCTUnwrap(image.jpegData(compressionQuality: 0.9))
        let first = try await model.backend.sendOwnPhoto(data)
        let work = try await model.backend.addOwnWork(NewOwnWork(token: first.token, text: OwnDescription()))
        let next = try await model.backend.sendOwnPhoto(data)
        model.retakeOwnWork(itemID: work.id, OwnPhotoCut(token: next.token))
        XCTAssertTrue(model.ownRetaking.contains(work.id))
        XCTAssertNil(model.ownRetaken[work.id])
        for _ in 0 ..< 100 where model.ownRetaking.contains(work.id) {
            try await Task.sleep(for: .milliseconds(50))
        }
        XCTAssertFalse(model.ownRetaking.contains(work.id))
        XCTAssertEqual(model.ownRetaken[work.id]?.id, work.id)
    }

    /// The white balance he sets where no colour chart is beside the work
    /// (Mateusz 2026-11-17 16:27 UTC: "Gdy przy robieniu zdjęcia dzieła nie
    /// zostanie wykryta karta koloru dodaj suwak regulacji balansu
    /// bieli"): the phone draws the picture as the server will make it
    /// (`imaging/balance.py`), and the number goes with the cut.
    /// The slider's middle draws the knob to itself (Mateusz 2026-11-17
    /// 21:32 UTC: "Gdy suwak jest w punkcie „0” (domyślnym) to stuknij
    /// haptyką i delikatnie przyciągnij"): near it the balance is none,
    /// past the pull it is where the finger is, and no further than the ends.
    func testTheWhiteBalanceSliderIsDrawnToTheMiddle() {
        let pull = OwnBalanceSlider.pull
        XCTAssertEqual(OwnBalanceSlider.settled(0), 0)
        XCTAssertEqual(OwnBalanceSlider.settled(pull * 0.9), 0)
        XCTAssertEqual(OwnBalanceSlider.settled(-pull * 0.9), 0)
        XCTAssertEqual(OwnBalanceSlider.settled(pull * 1.1), pull * 1.1, accuracy: 1e-12)
        XCTAssertEqual(OwnBalanceSlider.settled(-0.45), -0.45, accuracy: 1e-12)
        XCTAssertEqual(OwnBalanceSlider.settled(3), 1)
        XCTAssertEqual(OwnBalanceSlider.settled(-3), -1)
        // Gently: the pull is a small part of the way, a few points of the track.
        XCTAssertLessThanOrEqual(pull, 0.1)
        XCTAssertGreaterThanOrEqual(pull, 0.04)
    }

    func testTheWhiteBalanceIsDrawnAsTheServerMakesItAndGoesWithTheCut() throws {
        // The server's numbers.
        let cool = OwnBalance.gains(-1), warm = OwnBalance.gains(0.5)
        XCTAssertEqual(cool.red, 0.6010027, accuracy: 1e-6)
        XCTAssertEqual(cool.green, 0.9899608, accuracy: 1e-6)
        XCTAssertEqual(cool.blue, 2.2743328, accuracy: 1e-6)
        XCTAssertEqual(warm.red, 1.2391982, accuracy: 1e-6)
        XCTAssertEqual(warm.blue, 0.6370184, accuracy: 1e-6)
        let none = OwnBalance.gains(0), far = OwnBalance.gains(7)
        XCTAssertEqual(none.red, 1, accuracy: 1e-12)
        XCTAssertEqual(none.blue, 1, accuracy: 1e-12)
        XCTAssertEqual(far.red, OwnBalance.gains(1).red, accuracy: 1e-12)

        // A grey picture, warmer and cooler: the server makes 128 of each
        // colour (141, 126, 104) at 0.5 and (101, 127, 186) at -1.
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let grey = UIGraphicsImageRenderer(size: CGSize(width: 8, height: 8), format: format).image { context in
            UIColor(red: 128 / 255, green: 128 / 255, blue: 128 / 255, alpha: 1).setFill()
            context.fill(CGRect(x: 0, y: 0, width: 8, height: 8))
        }
        func colour(_ image: UIImage) throws -> [Int] {
            var bytes = [UInt8](repeating: 0, count: 4)
            let space = try XCTUnwrap(CGColorSpace(name: CGColorSpace.sRGB))
            let picture = try XCTUnwrap(image.cgImage)
            try bytes.withUnsafeMutableBytes { buffer in
                let context = try XCTUnwrap(CGContext(
                    data: buffer.baseAddress, width: 1, height: 1, bitsPerComponent: 8, bytesPerRow: 4,
                    space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
                ))
                context.draw(picture, in: CGRect(x: 0, y: 0, width: 1, height: 1))
            }
            return bytes.prefix(3).map { Int($0) }
        }
        XCTAssertTrue(OwnBalance.tinted(grey, balance: 0) === grey)
        for (balance, made) in [(0.5, [141, 126, 104]), (-1.0, [101, 127, 186])] {
            let drawn = try colour(OwnBalance.tinted(grey, balance: balance))
            for (one, other) in zip(drawn, made) {
                XCTAssertEqual(Double(one), Double(other), accuracy: 3, "\(balance): \(drawn)")
            }
        }

        // It goes to the server with the corners; none says "as taken".
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let cut = OwnPhotoCut(token: "a1", balance: -0.4)
        let sent = try JSONSerialization.jsonObject(with: encoder.encode(cut)) as? [String: Any]
        XCTAssertEqual(sent?["balance"] as? Double, -0.4)
        let work = NewOwnWork(token: "a1", text: OwnDescription())
        let plain = try JSONSerialization.jsonObject(with: encoder.encode(work)) as? [String: Any]
        XCTAssertEqual(plain?["balance"] as? Double, 0)
    }

    /// What the helper draws and counts after the first test on the phone
    /// (Mateusz 2026-11-16 12:53 UTC): the word held a moment, the
    /// gyroscope and the outline as one angle, the plan's dot, the ring.
    func testTheHelperIsSteadyAndInTheMiddle() {
        // The word changes only once something else has been true a moment.
        var steady = OwnScanSteady()
        let start = Date(timeIntervalSinceReferenceDate: 1000)
        XCTAssertEqual(steady.take(.go(left: true), at: start), .lost)
        XCTAssertEqual(steady.take(.go(left: true), at: start + 0.3), .go(left: true))
        XCTAssertEqual(steady.take(.hold, at: start + 0.4), .go(left: true))
        XCTAssertEqual(steady.take(.go(left: true), at: start + 0.5), .go(left: true))
        XCTAssertEqual(steady.take(.hold, at: start + 0.6), .go(left: true))
        XCTAssertEqual(steady.take(.hold, at: start + 0.9), .hold)
        // A photograph being taken goes on a little beyond the edge.
        XCTAssertEqual(OwnScanView.side(target: -30, angle: -20), .go(left: true))
        XCTAssertEqual(OwnScanView.side(target: -30, angle: -20, held: true), .hold)
        XCTAssertEqual(OwnScanView.side(target: -30, angle: -17, held: true), .go(left: true))

        // The gyroscope's count, drawn towards the outline's when they agree.
        var stands = OwnScanAngle()
        XCTAssertEqual(stands.fuse(gyro: -10, seen: nil).angle, -10)
        let first = stands.fuse(gyro: -10, seen: -14)
        XCTAssertTrue(first.seen)
        XCTAssertEqual(first.angle!, -11, accuracy: 1e-9)
        // Another rectangle on the wall is not believed.
        let other = stands.fuse(gyro: -10, seen: 40)
        XCTAssertFalse(other.seen)
        XCTAssertEqual(other.angle!, -11, accuracy: 1e-9)
        // Without a gyroscope the outline alone; with neither, nothing.
        var bare = OwnScanAngle()
        XCTAssertEqual(bare.fuse(gyro: nil, seen: -25).angle, -25)
        XCTAssertNil(bare.fuse(gyro: nil, seen: nil).angle)
        // Between the camera's looks the outline is the last one: the
        // count is not drawn to it, and the phone turned away from the
        // work in that while is seen to have turned.
        var turning = OwnScanAngle()
        XCTAssertEqual(turning.fuse(gyro: 0, seen: 0).stray, 0)
        let between = turning.fuse(gyro: 9, seen: 0, fresh: false)
        XCTAssertTrue(between.seen)
        XCTAssertEqual(between.angle!, 9, accuracy: 1e-9)
        XCTAssertEqual(between.stray, 9, accuracy: 1e-9)
        let away = turning.fuse(gyro: 25, seen: nil, fresh: false)
        XCTAssertFalse(away.seen)
        XCTAssertEqual(away.stray, 25, accuracy: 1e-9)
        // Back at the work, the camera finds it: nothing has strayed.
        XCTAssertEqual(turning.fuse(gyro: 2, seen: 0).stray, 0)
        // A photograph taken where the camera does not find the work: from there.
        turning.rest(gyro: -30)
        XCTAssertEqual(turning.fuse(gyro: -20, seen: nil).stray, 10, accuracy: 1e-9)

        // The plan: the work above, the place in front under it in the
        // middle, the side places up the arc to either side.
        let plan = CGSize(width: 300, height: 64)
        let before = OwnScanPlan.place(0, in: plan)
        XCTAssertEqual(before.x, 150, accuracy: 1e-9)
        XCTAssertEqual(before.y, 47, accuracy: 1e-9)
        let leftward = OwnScanPlan.place(-30, in: plan), rightward = OwnScanPlan.place(30, in: plan)
        XCTAssertLessThan(leftward.x, 60)
        XCTAssertGreaterThan(leftward.x, 17)
        XCTAssertLessThan(leftward.y, before.y - 10)
        XCTAssertEqual(leftward.x + rightward.x, 300, accuracy: 1e-9)
        XCTAssertEqual(leftward.y, rightward.y, accuracy: 1e-9)
        // The dot stays on the plan however far he goes.
        XCTAssertEqual(OwnScanPlan.place(-80, in: plan), OwnScanPlan.place(-37.5, in: plan))
        XCTAssertGreaterThan(OwnScanPlan.place(-80, in: plan).x, 9)
        // The ring fills while the phone is held, and is full while the camera writes.
        let since = Date(timeIntervalSinceReferenceDate: 2000)
        XCTAssertEqual(OwnShotRing.filled(since: nil, taking: false, now: since), 0)
        XCTAssertEqual(OwnShotRing.filled(since: since, taking: false, now: since + OwnShotRing.time / 2), 0.5, accuracy: 1e-9)
        XCTAssertEqual(OwnShotRing.filled(since: since, taking: false, now: since + 5), 1)
        XCTAssertEqual(OwnShotRing.filled(since: nil, taking: true, now: since), 1)

        // The gyroscope: before a wall about the gravity's line, over a
        // table about the phone's own upright.
        let wall = OwnScanGuide.turning(rate: (0, 1, 0), gravity: (0, -1, 0), quarter: 0)
        XCTAssertEqual(wall!, 1, accuracy: 1e-9)
        let onItsSide = OwnScanGuide.turning(rate: (1, 0, 0), gravity: (-1, 0, 0), quarter: 1)
        XCTAssertEqual(onItsSide!, 1, accuracy: 1e-9)
        let table = OwnScanGuide.turning(rate: (0, 1, 0), gravity: (0, 0, -1), quarter: 0)
        XCTAssertEqual(table!, 1, accuracy: 1e-9)
        let tableOnItsSide = OwnScanGuide.turning(rate: (1, 0, 0), gravity: (0, 0, -1), quarter: 1)
        XCTAssertEqual(tableOnItsSide!, 1, accuracy: 1e-9)
        XCTAssertNil(OwnScanGuide.turning(rate: (0, 1, 0), gravity: (0, 0, 0), quarter: 0))
    }
}
