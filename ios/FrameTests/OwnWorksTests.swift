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
}
