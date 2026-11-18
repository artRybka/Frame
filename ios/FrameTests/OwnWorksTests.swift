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

    /// The scan of a work that is no flat one comes in doubt, and the
    /// photograph from the front is then the one chosen at first (Mateusz
    /// 2026-11-17 22:43 UTC: "w sytuacji gdzie podejrzewasz płaskorzeźbę
    /// albo dzieło które wymaga pojedynczego zdjęcia ustawiaj je jako
    /// domyślne").
    func testAScanInDoubtComesWithTheMerge() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let relief = #"{"token": "a1", "width": 3024, "height": 4032, "used": 2, "replaced": 0.18, "doubt": true}"#
        let made = try decoder.decode(OwnMerged.self, from: Data(relief.utf8))
        XCTAssertEqual(made.doubt, true)
        XCTAssertEqual(made.used, 2)
        // A server before the choice says nothing of it: no doubt.
        let before = #"{"token": "a1", "width": 3024, "height": 4032, "used": 2, "replaced": 0.03}"#
        XCTAssertNil(try decoder.decode(OwnMerged.self, from: Data(before.utf8)).doubt)
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

        // The words: no shutter but when the work's edges are not found.
        var look = OwnScanLook(number: 2)
        // The first photograph is taken: round the work, either way
        // (Mateusz 2026-11-18 14:03 UTC: "po zdjęciu na wprost można
        // pójść w lewo albo w prawo").
        look.advice = .either
        look.angle = 0
        XCTAssertNil(look.pill)
        XCTAssertTrue(look.either)
        XCTAssertNil(look.walk)
        XCTAssertEqual(look.line, "Przejdź łukiem w lewo albo w prawo")
        look.advice = .go(left: true)
        look.angle = -10
        XCTAssertNil(look.pill)
        XCTAssertFalse(look.either)
        XCTAssertEqual(look.line, "Przejdź łukiem w lewo, celując w dzieło")
        XCTAssertEqual(look.walk, true)
        // Beyond where the photograph is taken: back a little.
        look.advice = .go(left: false)
        look.angle = -45
        XCTAssertEqual(look.line, "Za daleko w bok, wróć trochę")
        XCTAssertEqual(look.walk, false)
        // The left has its photograph: the right now.
        look.left = true
        look.angle = -30
        XCTAssertEqual(look.line, "Lewa strona gotowa, teraz w prawo")
        look.left = false
        look.right = true
        look.advice = .go(left: true)
        look.angle = 30
        XCTAssertEqual(look.line, "Prawa strona gotowa, teraz w lewo")
        look.right = false
        look.angle = -10
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
        look.angle = 29
        XCTAssertEqual(look.line, "Dobrze. Robię zdjęcie z prawej")
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

    /// Mateusz 2026-11-18 08:08 UTC, a canvas with no frame ("ani z jednego
    /// ani drugiego kąta dzieło nie zostało wykryte automatycznie i
    /// musiałem robić zdjęcie ręcznie"): the rectangles found nothing in
    /// most looks, and what Vision takes for a sheet was the canvas in
    /// every one. The numbers are that scan's.
    func testACanvasWithNoFrameIsFoundAsASheet() {
        func q(_ c: [(Double, Double)]) -> [CGPoint] { c.map { CGPoint(x: $0.0, y: $0.1) } }
        let canvas = q([(0.0903, 0.0586), (0.9375, 0.0664), (0.9097, 0.8203), (0.1111, 0.8164)])
        let fromLeft = q([(0.201, 0.070), (0.875, 0.203), (0.819, 0.781), (0.188, 0.894)])
        // No rectangle: the sheet, from the front and from the side.
        XCTAssertEqual(OwnCameraSession.work(among: [], paper: canvas, last: nil), canvas)
        XCTAssertEqual(OwnCameraSession.work(among: [], paper: fromLeft, last: canvas), fromLeft)
        // From 27° to the left, as he stood: the side photograph's angle.
        let shape = OwnScanView.shape(of: canvas)!
        let turn = OwnScanView.turn(of: fromLeft, shape: shape)! - OwnScanView.turn(of: canvas, shape: shape)!
        XCTAssertEqual(turn, -27, accuracy: 2)
        XCTAssertTrue(OwnScanView.near.contains(abs(turn)))
        // The rectangles come first: a frame's outer edge stays the work
        // with the picture in it found as the sheet, and with the sheet
        // taking in the work hanging beside it (his relief, from the right).
        let frame = q([(0.10, 0.10), (0.90, 0.10), (0.90, 0.80), (0.10, 0.80)])
        let picture = q([(0.16, 0.16), (0.84, 0.16), (0.84, 0.74), (0.16, 0.74)])
        XCTAssertEqual(OwnCameraSession.work(among: [frame], paper: picture, last: nil), frame)
        let both = q([(0.03, 0.12), (0.92, 0.08), (0.92, 0.82), (0.03, 0.78)])
        XCTAssertEqual(OwnCameraSession.work(among: [frame], paper: both, last: frame), frame)
        // A rectangle that is a part of the sheet gives way to it (the
        // relief's upper half, down to the glasses on it).
        let upper = q([(0.17, 0.15), (0.78, 0.15), (0.78, 0.38), (0.17, 0.38)])
        let relief = q([(0.16, 0.14), (0.79, 0.14), (0.79, 0.77), (0.16, 0.77)])
        XCTAssertEqual(OwnCameraSession.work(among: [upper], paper: relief, last: nil), relief)
        XCTAssertEqual(OwnCameraSession.work(among: [upper], paper: relief, last: upper), relief)
        // A sheet running out of the picture, or a scrap, is none.
        let cut = q([(0.0, 0.0), (0.95, 0.0), (0.2, 0.98), (0.0, 0.98)])
        XCTAssertNil(OwnCameraSession.work(among: [], paper: cut, last: nil))
        let scrap = q([(0.05, 0.22), (0.37, 0.22), (0.37, 0.35), (0.05, 0.35)])
        XCTAssertFalse(OwnCameraSession.large(scrap))
        XCTAssertNil(OwnCameraSession.work(among: [], paper: scrap, last: nil))
        XCTAssertEqual(OwnCameraSession.work(among: [frame], paper: scrap, last: nil), frame)
        // No sheet: as it was.
        XCTAssertEqual(OwnCameraSession.work(among: [frame], paper: nil, last: nil), frame)
        XCTAssertNil(OwnCameraSession.work(among: [], paper: nil, last: frame))
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
        // (Each with the angle the phone counted, when it did.)
        XCTAssertNil(shots.angle(0))
        shots.angles.append(-28.4)
        XCTAssertEqual(shots.angle(0), -28.4)
        sending.send(shots, with: demo)
        shots.sides.append(picture())
        shots.angles.append(31)
        sending.send(shots, with: demo)
        // All of them again (the third taken, the steps go on): none twice.
        sending.send(shots, with: demo)
        let sent = await sending.sidesSent()
        XCTAssertTrue(sent)
        let same = try await sending.photo()
        XCTAssertEqual(same.token, first.token)
        let looked = await sending.looked()
        XCTAssertEqual(looked?.token, first.token)
        let merged = try await demo.mergeOwnPhotos(token: first.token, outline: nil, trace: ["pinned": 2.4])
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

    /// The scan in one arc (Mateusz 2026-11-18 13:35 UTC: "może da się to
    /// zbudować jeszcze lepiej, intuicyjniej i szybciej"; 14:03 UTC: "po
    /// zdjęciu na wprost można pójść w lewo albo w prawo"): either side
    /// first, a side done with a photograph from where they were always
    /// taken, one more in passing on the way out.
    func testTheScanIsOneArcEitherWay() {
        var arc = OwnScanArc()
        // In front of the work: either way will do.
        XCTAssertNil(arc.target(at: 0))
        XCTAssertNil(arc.target(at: -4))
        // The side he walks to is the one meant.
        XCTAssertEqual(arc.target(at: -8), -30)
        XCTAssertEqual(arc.target(at: 9), 30)
        // On the way out one more is taken in passing, once a side.
        XCTAssertFalse(arc.early(at: 9))
        XCTAssertTrue(arc.early(at: 15))
        XCTAssertFalse(arc.early(at: 21))
        arc.took(15.2)
        XCTAssertFalse(arc.early(at: 16))
        XCTAssertTrue(arc.early(at: -16))
        // It does not make the side done: only one from 22–38° does.
        XCTAssertFalse(arc.done(left: false))
        XCTAssertEqual(arc.target(at: 18), 30)
        arc.took(27.5)
        XCTAssertTrue(arc.done(left: false))
        XCTAssertFalse(arc.done(left: true))
        XCTAssertFalse(arc.finished)
        // The right came first: the left is meant now, wherever he stands.
        XCTAssertEqual(arc.target(at: 27), -30)
        XCTAssertEqual(arc.target(at: 0), -30)
        XCTAssertEqual(OwnScanView.side(target: -30, angle: 27), .go(left: true))
        arc.took(-35)
        XCTAssertTrue(arc.finished)
        XCTAssertNil(arc.target(at: -35))
        XCTAssertEqual(arc.taken, [15.2, 27.5, -35])
        // The shutter pressed with no count of where he stands: the left, then the right.
        var byHand = OwnScanArc()
        XCTAssertEqual(byHand.next, -30)
        byHand.took(byHand.next)
        XCTAssertEqual(byHand.next, 30)
        byHand.took(byHand.next)
        XCTAssertTrue(byHand.finished)
        // A server from before it takes the first two that come: no
        // extra ones for it, nor for one that has not said which it is.
        XCTAssertTrue(OwnScanArc.extras(server: OwnScanArc.server))
        XCTAssertTrue(OwnScanArc.extras(server: "1.146.0"))
        XCTAssertFalse(OwnScanArc.extras(server: "1.145.240"))
        XCTAssertFalse(OwnScanArc.extras(server: nil))
        // A side one is taken as soon as the phone has been still a moment.
        XCTAssertFalse(OwnScanGuide.still(since: nil, now: 10))
        XCTAssertFalse(OwnScanGuide.still(since: 9.9, now: 10))
        XCTAssertTrue(OwnScanGuide.still(since: 9.8, now: 10))

        // The plan: a stretch on either side where its photograph is
        // taken, within what the dot can reach.
        let plan = CGSize(width: 300, height: 64)
        let from = OwnScanPlan.place(-OwnScanView.near.lowerBound, in: plan)
        let to = OwnScanPlan.place(-OwnScanView.near.upperBound, in: plan)
        XCTAssertLessThan(to.x, from.x - 30)
        XCTAssertLessThan(to.y, from.y)
        XCTAssertGreaterThan(to.x, 9)
    }

    /// What the hand feels on the way (Mateusz 2026-11-18 14:03 UTC:
    /// "coraz szybsze tykanie i potwierdzenie wykonania danej strony.
    /// Zaczyna tykać gdy zaczyna się ruch w porządanym kierunku. (jak
    /// przy szukaniu airtaga)").
    func testTheWayToASideTicksFasterAndFaster() {
        XCTAssertEqual(OwnScanTicks.behind(0), 0)
        XCTAssertEqual(OwnScanTicks.behind(0.19), 0)
        XCTAssertEqual(OwnScanTicks.behind(0.21), 1)
        XCTAssertEqual(OwnScanTicks.behind(0.5), 3)
        XCTAssertEqual(OwnScanTicks.behind(1), OwnScanTicks.most)
        XCTAssertEqual(OwnScanTicks.behind(1.3), OwnScanTicks.most)

        var ticks = OwnScanTicks()
        let start = Date(timeIntervalSinceReferenceDate: 3000)
        // In front of the work with no side chosen: nothing.
        XCTAssertNil(ticks.walked(to: 0, target: nil, at: start))
        XCTAssertNil(ticks.walked(to: 3, target: nil, at: start + 0.1))
        // To the left, a degree every tenth of a second.
        var felt: [(angle: Double, strength: Double)] = []
        var time = start + 1
        for step in 6 ... 22 {
            time += 0.1
            if let strength = ticks.walked(to: -Double(step), target: -30, at: time) { felt.append((Double(step), strength)) }
        }
        // It starts as he sets off, and comes faster and stronger to
        // where the photograph is taken.
        XCTAssertEqual(felt.first?.angle, 6)
        XCTAssertEqual(felt.last?.angle, 22)
        XCTAssertGreaterThanOrEqual(felt.count, 9)
        let early = felt.prefix(4), late = felt.suffix(4)
        XCTAssertGreaterThan(early.last!.angle - early.first!.angle, late.last!.angle - late.first!.angle)
        XCTAssertEqual(felt.map(\.strength), felt.map(\.strength).sorted())
        XCTAssertLessThan(felt.first!.strength, 0.6)
        XCTAssertEqual(felt.last!.strength, 1, accuracy: 1e-9)
        // Standing there, and walking back: nothing. On again: again.
        XCTAssertNil(ticks.walked(to: -22, target: -30, at: time + 1))
        XCTAssertNil(ticks.walked(to: -24, target: -30, at: time + 1.5))
        XCTAssertNil(ticks.walked(to: -15, target: -30, at: time + 2))
        XCTAssertNotNil(ticks.walked(to: -20, target: -30, at: time + 3))
        // The left has its photograph: the way to the right is counted
        // from where he stands.
        XCTAssertNil(ticks.walked(to: -30, target: 30, at: time + 4))
        XCTAssertNil(ticks.walked(to: -28, target: 30, at: time + 4.1))
        XCTAssertNotNil(ticks.walked(to: -19, target: 30, at: time + 4.2))
        // Never two at once.
        XCTAssertNil(ticks.walked(to: -9, target: 30, at: time + 4.22))
        XCTAssertNotNil(ticks.walked(to: -9, target: 30, at: time + 4.3))
        // Both done: nothing more.
        XCTAssertNil(ticks.walked(to: 30, target: nil, at: time + 6))
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
