import XCTest
@testable import Frame

/// The scan of three merged on the phone (`ScanCore`: `core/scan` in C++
/// with OpenCV, linked into the app) and its trial in Konfiguracja →
/// Diagnostyka (`ScanTrial`; Mateusz 2026-11-19: "Najpierw próba na iPhonie").
final class ScanCoreTests: XCTestCase {
    /// The core as it is linked into the app merges: a work under glass
    /// with a lamp in it, made up and photographed three times, comes out
    /// as it does on the server's processor (two laid over, some 7% of the
    /// light within the work taken off, no doubt of its being flat).
    func testTheCoreMergesAScanOfThreeMadeUp() throws {
        let note = try ScanCore.madeUp(side: 700)
        XCTAssertEqual(note.used, 2)
        XCTAssertEqual(note.removed, 0.07, accuracy: 0.02)
        XCTAssertFalse(note.doubt)
        XCTAssertGreaterThan(note.took["laid"] ?? 0, 0)
        XCTAssertTrue(ScanCore.built.hasPrefix("OpenCV 5."), ScanCore.built)
    }

    /// Photographs as `.npy` files go in and one comes out, the size of
    /// the first; what is no photograph is said, not crashed on.
    func testTheCoreReadsAndWritesPicturesAsFiles() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("scan-core-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }

        // A wall with nothing on it, three times: nothing can be laid over
        // nothing, and the first comes back as it went.
        let rows = 300, columns = 240
        var plain = Self.npyHead(rows: rows, columns: columns)
        plain.append(Data(repeating: 128, count: rows * columns * 3))
        let first = folder.appendingPathComponent("first.npy")
        let side = folder.appendingPathComponent("side1.npy")
        let into = folder.appendingPathComponent("phone.npy")
        try plain.write(to: first)
        try plain.write(to: side)
        let corners = [0.2, 0.2, 0.8, 0.2, 0.8, 0.8, 0.2, 0.8]
        let note = try ScanCore.merge(first: first, sides: [side, side], corners: corners, anyway: true, into: into)
        XCTAssertEqual(note.used, 0)
        XCTAssertEqual(note.removed, 0)
        let made = try Data(contentsOf: into)
        let shape = try XCTUnwrap(ScanPicture.shape(of: made))
        XCTAssertEqual(shape.rows, rows)
        XCTAssertEqual(shape.columns, columns)
        XCTAssertEqual(made.count, plain.count)

        let nowhere = folder.appendingPathComponent("none.npy")
        XCTAssertThrowsError(
            try ScanCore.merge(first: nowhere, sides: [side], corners: corners, anyway: true, into: into)
        ) { error in
            XCTAssertTrue(error.localizedDescription.contains("none.npy"), error.localizedDescription)
        }
        XCTAssertThrowsError(try ScanCore.merge(first: first, sides: [side], corners: [0.2, 0.2], anyway: true, into: into))
    }

    func testAPictureSaysItsSizeAndHowLongItsJpegTakes() throws {
        let rows = 120, columns = 160
        var picture = Self.npyHead(rows: rows, columns: columns)
        picture.append(Data((0 ..< rows * columns * 3).map { UInt8(truncatingIfNeeded: $0 / 7) }))
        let shape = try XCTUnwrap(ScanPicture.shape(of: picture))
        XCTAssertEqual(shape.rows, rows)
        XCTAssertEqual(shape.columns, columns)
        XCTAssertEqual(shape.from, picture.count - rows * columns * 3)
        let jpeg = try XCTUnwrap(ScanPicture.jpegSeconds(of: picture))
        XCTAssertGreaterThan(jpeg.bytes, 500)
        XCTAssertGreaterThanOrEqual(jpeg.written, 0)
        XCTAssertGreaterThanOrEqual(jpeg.read, 0)
        // Cut short, or no picture at all.
        XCTAssertNil(ScanPicture.shape(of: picture.dropLast(3)))
        XCTAssertNil(ScanPicture.shape(of: Data("nothing at all".utf8)))
        XCTAssertNil(ScanPicture.jpegSeconds(of: Data()))
    }

    /// The trial takes his latest scans the server merged within a work's
    /// corners, and merges each of the side photographs the server did.
    func testTheTrialTakesHisLatestScansOfAWorkFound() throws {
        let json = """
        [{"token": "aaaaaaaaaaaaaaaaaaaaaaaa", "at": "2026-11-18T19:13:05+00:00", "used": 2, "replaced": 0.0812,
          "doubt": false, "corners": [[0.1, 0.2], [0.9, 0.2], [0.9, 0.8], [0.1, 0.8]], "angles": {"side1.jpg": -31.0},
          "files": {"first.jpg": 100, "side2.jpg": 30, "side1.jpg": 20, "more1.jpg": 10, "phone.npy": 5}},
         {"token": "bbbbbbbbbbbbbbbbbbbbbbbb", "corners": null, "files": {"first.jpg": 100, "side1.jpg": 20}},
         {"token": "cccccccccccccccccccccccc", "corners": [[0, 0], [1, 0], [1, 1], [0, 1]], "files": {"first.jpg": 1}},
         {"token": "dddddddddddddddddddddddd", "files": {}},
         {"token": "eeeeeeeeeeeeeeeeeeeeeeee", "corners": [[0, 0], [1, 0], [1, 1], [0, 1]],
          "files": {"first.jpg": 1, "side1.jpg": 1}}]
        """
        let scans = try LiveBackend.decoder().decode([KeptScan].self, from: Data(json.utf8))
        XCTAssertEqual(scans.count, 5)
        XCTAssertEqual(scans[0].sides, ["side1.jpg", "side2.jpg"])
        XCTAssertEqual(scans[0].quad, [0.1, 0.2, 0.9, 0.2, 0.9, 0.8, 0.1, 0.8])
        XCTAssertEqual(scans[0].replaced, 0.0812)
        XCTAssertNotNil(scans[0].date)
        XCTAssertNil(scans[1].quad)
        // No corners, no side photograph, nothing noted: not what the server merged within a work.
        XCTAssertEqual(ScanTrial.chosen(scans).map(\.token), ["aaaaaaaaaaaaaaaaaaaaaaaa", "eeeeeeeeeeeeeeeeeeeeeeee"])
        XCTAssertEqual(ScanTrial.chosen(scans, most: 1).count, 1)
    }

    @MainActor
    func testTheTrialNotesWhatThePhoneDidAndOnWhat() throws {
        let note = ScanCore.Note(used: 2, removed: 0.08, doubt: false, took: ["read": 0.5, "laid": 2.5, "own": 1.5])
        XCTAssertEqual(note.seconds, 4.5, accuracy: 1e-9)
        var scan = KeptScan(token: "aaaaaaaaaaaaaaaaaaaaaaaa")
        scan.used = 2
        scan.replaced = 0.0812
        let report = ScanTrial.report(note, of: scan, heat: (.nominal, .fair))
        // What goes to the server is JSON.
        let sent = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
        let back = try XCTUnwrap(JSONSerialization.jsonObject(with: sent) as? [String: Any])
        // A number written as JSON and read back is the nearest one, not the same to the last bit.
        XCTAssertEqual(try XCTUnwrap(back["seconds"] as? Double), 4.5, accuracy: 1e-9)
        XCTAssertEqual(back["used"] as? Int, 2)
        XCTAssertEqual(try XCTUnwrap((back["took"] as? [String: Double])?["laid"]), 2.5, accuracy: 1e-9)
        let server = try XCTUnwrap(back["server"] as? [String: Any])
        XCTAssertEqual(try XCTUnwrap(server["replaced"] as? Double), 0.0812, accuracy: 1e-9)
        XCTAssertEqual(back["heat"] as? [Int], [0, 1])
        XCTAssertFalse(try XCTUnwrap(back["model"] as? String).isEmpty)
        XCTAssertTrue(try XCTUnwrap(back["built"] as? String).hasPrefix("OpenCV"))
    }

    func testTheTrialsWordsInPolish() {
        XCTAssertEqual(ScanTrialText.seconds(5.234), "5,2 s")
        XCTAssertEqual(ScanTrialText.seconds(12), "12,0 s")
        XCTAssertEqual(ScanTrialText.name(nil), "Skan")
        XCTAssertTrue(ScanTrialText.name(Date(timeIntervalSince1970: 1_795_000_000)).hasPrefix("Skan z "))
        XCTAssertEqual(ScanTrialText.stage(.merging), "Składam")
        XCTAssertEqual(ScanTrialText.stage(.failed("x")), "Nie udało się")
    }

    /// The head of a `.npy` file of rows × columns × 3 bytes, as NumPy writes it.
    private static func npyHead(rows: Int, columns: Int) -> Data {
        var head = "{'descr': '|u1', 'fortran_order': False, 'shape': (\(rows), \(columns), 3), }"
        head += String(repeating: " ", count: (64 - (10 + head.utf8.count + 1) % 64) % 64) + "\n"
        var data = Data([0x93, 0x4E, 0x55, 0x4D, 0x50, 0x59, 1, 0])
        data.append(contentsOf: [UInt8(head.utf8.count & 0xFF), UInt8(head.utf8.count >> 8)])
        data.append(Data(head.utf8))
        return data
    }
}
