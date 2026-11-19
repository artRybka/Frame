import ImageIO
import UniformTypeIdentifiers
import XCTest
@testable import Frame

/// The scan of three made by the phone itself of its camera's own
/// photographs (`PhoneScan`; Mateusz 2026-11-19 07:42 UTC: "Tak, składaj na
/// iPhonie"), and sent to the server, which is left as the spare.
final class PhoneScanTests: XCTestCase {
    // MARK: A photograph read as the server reads it

    /// A made-up photograph as the phone's camera writes one: a JPEG in
    /// Display P3, lying on its side with a turn in its EXIF (96 × 64 as
    /// stored, 64 × 96 as held), of squares of 16 pixels, each one colour.
    /// Written by Pillow. `server/tests/test_scan_core.py` takes this very
    /// file and the numbers under it out of here, and holds the server's
    /// reading to them: the two read a photograph alike.
    static let photograph = """
    /9j/4AAQSkZJRgABAQAAAQABAAD/4QAiRXhpZgAATU0AKgAAAAgAAQESAAMAAAABAAYAAAAAAAD/4gIQSUNDX1BST0ZJTEUAAQEA
    AAIAAAAAAAQwAABtbnRyUkdCIFhZWiAH6gABAAEAAAAAAABhY3NwQVBQTAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA9tYAAQAA
    AADTLQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAApkZXNjAAAA/AAAAERjcHJ0AAAB
    QAAAACR3dHB0AAABZAAAABRyWFlaAAABeAAAABRnWFlaAAABjAAAABRiWFlaAAABoAAAABRyVFJDAAABtAAAACBnVFJDAAABtAAA
    ACBiVFJDAAABtAAAACBjaGFkAAAB1AAAACxtbHVjAAAAAAAAAAEAAAAMZW5VUwAAACgAAAAcAEQAaQBzAHAAbABhAHkAIABQADMA
    IAAoAG0AYQBkAGUAIAB1AHAAKW1sdWMAAAAAAAAAAQAAAAxlblVTAAAACAAAABwAbgBvAG4AZVhZWiAAAAAAAAD21gABAAAAANMt
    WFlaIAAAAAAAAIPfAAA9v////7tYWVogAAAAAAAASr8AALE3AAAKuVhZWiAAAAAAAAAoOAAAEQsAAMi5cGFyYQAAAAAAAwAAAAJm
    ZgAA8qcAAA1ZAAAT0AAACltzZjMyAAAAAAABDEIAAAXe///zJgAAB5MAAP2Q///7of///aIAAAPcAADAbv/bAEMAAgEBAQEBAgEB
    AQICAgICBAMCAgICBQQEAwQGBQYGBgUGBgYHCQgGBwkHBgYICwgJCgoKCgoGCAsMCwoMCQoKCv/bAEMBAgICAgICBQMDBQoHBgcK
    CgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCv/AABEIAEAAYAMBIgACEQEDEQH/xAAfAAAB
    BQEBAQEBAQAAAAAAAAAAAQIDBAUGBwgJCgv/xAC1EAACAQMDAgQDBQUEBAAAAX0BAgMABBEFEiExQQYTUWEHInEUMoGRoQgjQrHB
    FVLR8CQzYnKCCQoWFxgZGiUmJygpKjQ1Njc4OTpDREVGR0hJSlNUVVZXWFlaY2RlZmdoaWpzdHV2d3h5eoOEhYaHiImKkpOUlZaX
    mJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4eLj5OXm5+jp6vHy8/T19vf4+fr/xAAfAQADAQEBAQEBAQEB
    AAAAAAAAAQIDBAUGBwgJCgv/xAC1EQACAQIEBAMEBwUEBAABAncAAQIDEQQFITEGEkFRB2FxEyIygQgUQpGhscEJIzNS8BVictEK
    FiQ04SXxFxgZGiYnKCkqNTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqCg4SFhoeIiYqSk5SVlpeYmZqio6Sl
    pqeoqaqys7S1tre4ubrCw8TFxsfIycrS09TV1tfY2dri4+Tl5ufo6ery8/T19vf4+fr/2gAMAwEAAhEDEQA/ACiiigD9/KKKKAP4
    U6KKKAP2gooor+Vz+2Dg6KKK/wBSD/Js9Qooor/Ns9w/SyiiivoD+uD8K6KKK+oMzqKKKKD+qDzOiiiv7IP8+z9MKKKK/wAnz6g/
    Puiiiv8AQQ/mM+5KKKK/zLP9mD8d6KKK/tw/y/P1Eooor+hD9wP08ooor+ez4s/nvooor+ez/fQ+wKKKK9w/4nzx+iiiv6QP9ZD9
    QKKKKAP5u6KKK+fPrD+uyiiiv8rz6Q/kPooor/fA/Bz+iSiiiv5PP60P/9k=
    """

    /// What the server reads in the middle of each of its squares, upright
    /// (four across, six down), in sRGB.
    static let read: [[Int]] = [
        [100, 100, 100], [255, 112, 0], [235, 199, 154], [128, 128, 128],
        [180, 180, 180], [17, 62, 26], [117, 78, 56], [255, 255, 255],
        [53, 29, 19], [157, 108, 174], [196, 47, 66], [20, 20, 20],
        [252, 239, 0], [211, 210, 188], [70, 70, 145], [215, 93, 31],
        [17, 30, 95], [255, 0, 0], [158, 169, 28], [30, 122, 185],
        [232, 146, 148], [0, 204, 14], [0, 112, 111], [61, 162, 56],
    ]

    private static func file() throws -> Data {
        try XCTUnwrap(Data(base64Encoded: photograph, options: .ignoreUnknownCharacters))
    }

    private func folder() throws -> URL {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("phone-scan-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: folder) }
        return folder
    }

    /// The squares' middles in a picture read of `photograph` (squares of
    /// `square` pixels there), held against the server's: every one that
    /// is further off than `within` levels, said at once.
    private func assertSquares(_ picture: Data, square: Int, within: Int = 3, line: UInt = #line) throws {
        let shape = try XCTUnwrap(ScanPicture.shape(of: picture), line: line)
        XCTAssertEqual(shape.rows, 6 * square, line: line)
        XCTAssertEqual(shape.columns, 4 * square, line: line)
        XCTAssertEqual(picture.count, shape.from + shape.rows * shape.columns * 3, line: line)
        guard shape.rows == 6 * square, shape.columns == 4 * square else { return }
        var off: [String] = []
        for row in 0 ..< 6 {
            for column in 0 ..< 4 {
                let at = shape.from + ((row * square + square / 2) * shape.columns + column * square + square / 2) * 3
                let seen = (0 ..< 3).map { Int(picture[picture.startIndex + at + $0]) }
                let server = Self.read[row * 4 + column]
                if zip(seen, server).contains(where: { abs($0 - $1) > within }) {
                    off.append("square \(row),\(column): \(seen) here, \(server) on the server")
                }
            }
        }
        XCTAssertTrue(off.isEmpty, off.joined(separator: "; "), line: line)
    }

    /// The first photograph goes into the merge whole, upright as it was
    /// held, and in sRGB as the server turns the camera's Display P3
    /// (read as they stand, P3's numbers are other colours: its 200, 100,
    /// 50 is sRGB's 215, 93, 31).
    func testAPhotographIsReadUprightAndInTheServersColours() throws {
        let file = try Self.file()
        let size = try XCTUnwrap(PhoneScan.size(of: file))
        XCTAssertEqual(size.columns, 64)
        XCTAssertEqual(size.rows, 96)
        // The made-up file is one this phone takes for what it is: a
        // picture in colours of its own, not sRGB's.
        let source = try XCTUnwrap(CGImageSourceCreateWithData(file as CFData, nil))
        let stored = try XCTUnwrap(CGImageSourceCreateImageAtIndex(source, 0, nil))
        XCTAssertEqual(stored.width, 96)
        XCTAssertNotEqual(stored.colorSpace?.name, CGColorSpace.sRGB)
        XCTAssertNotNil(stored.colorSpace?.copyICCData())

        let into = try folder().appendingPathComponent("first.npy")
        let shape = try PhoneScan.write(file, into: into)
        XCTAssertEqual(shape.rows, 96)
        XCTAssertEqual(shape.columns, 64)
        try assertSquares(try Data(contentsOf: into), square: 16)

        XCTAssertNil(PhoneScan.size(of: Data("no picture".utf8)))
        XCTAssertThrowsError(try PhoneScan.write(Data("no picture".utf8), into: into))
    }

    /// A side photograph is read as small as the server's merge reads its
    /// own: halved, quartered… as its JPEG gives it, neither side under
    /// what the merge matches at.
    func testASidePhotographIsReadAsSmallAsTheServerReadsIt() throws {
        // Pillow's `draft`: 48 MP halves for 2400, a 12 MP one stays whole.
        XCTAssertEqual(PhoneScan.smaller(columns: 8064, rows: 6048, least: PhoneScan.matchSide), 2)
        XCTAssertEqual(PhoneScan.smaller(columns: 6048, rows: 8064, least: PhoneScan.matchSide), 2)
        XCTAssertEqual(PhoneScan.smaller(columns: 4032, rows: 3024, least: PhoneScan.matchSide), 1)
        XCTAssertEqual(PhoneScan.smaller(columns: 9600, rows: 9600, least: 2400), 4)
        XCTAssertEqual(PhoneScan.smaller(columns: 14400, rows: 12000, least: 2400), 4)
        XCTAssertEqual(PhoneScan.smaller(columns: 20000, rows: 19200, least: 2400), 8)
        XCTAssertEqual(PhoneScan.smaller(columns: 100, rows: 100, least: 0), 8)

        let into = try folder().appendingPathComponent("side1.npy")
        let shape = try PhoneScan.write(try Self.file(), into: into, least: 24)
        XCTAssertEqual(shape.rows, 48)
        XCTAssertEqual(shape.columns, 32)
        try assertSquares(try Data(contentsOf: into), square: 8)
        // Not small enough to halve: whole.
        let whole = try PhoneScan.write(try Self.file(), into: into, least: 40)
        XCTAssertEqual(whole.rows, 96)
        XCTAssertEqual(whole.columns, 64)
    }

    // MARK: The server's rules, kept here

    /// Of the photographs from each side, the one nearest 30° off is used,
    /// as the server chooses (`OwnWorks.chosen`); all, where the phone did
    /// not say from where one was taken.
    func testTheSidePhotographsNearestThirtyDegreesAreTheOnesUsed() {
        XCTAssertEqual(PhoneScan.chosen(angles: [-31, 29, -12, 44]), [0, 1])
        XCTAssertEqual(PhoneScan.chosen(angles: [-50, -28, 20, 33]), [1, 3])
        XCTAssertEqual(PhoneScan.chosen(angles: [18, 27]), [1])
        XCTAssertEqual(PhoneScan.chosen(angles: [-30.2, nil]), [0, 1])
        XCTAssertEqual(PhoneScan.chosen(angles: [Double.nan, 30]), [0, 1])
        XCTAssertEqual(PhoneScan.chosen(angles: []), [])
        // The first of two as near (the server keeps the earlier one too).
        XCTAssertEqual(PhoneScan.chosen(angles: [28, 32]), [0])
        // As the server has them: to a tenth of a degree, no further than 90.
        XCTAssertEqual(PhoneScan.sent(29.96), 30)
        XCTAssertEqual(PhoneScan.sent(-123), -90)
        XCTAssertNil(PhoneScan.sent(.infinity))
    }

    /// Corners the merge can go by, as the server's `cut.valid` has them.
    func testFourCornersOfAWorkAreThoseTheServerWouldTake() {
        let work = [[0.2, 0.25], [0.8, 0.24], [0.81, 0.7], [0.19, 0.71]]
        XCTAssertEqual(PhoneScan.valid(work), work)
        // Kept within the photograph, to five places.
        XCTAssertEqual(
            PhoneScan.valid([[-0.01, 0.1], [0.9, 0.1], [0.9, 1.2], [0, 0.999_996]]),
            [[0, 0.1], [0.9, 0.1], [0.9, 1], [0, 1]]
        )
        XCTAssertEqual(PhoneScan.valid([[0.123_456_7, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]])?[0][0], 0.12346)
        XCTAssertNil(PhoneScan.valid(nil))
        XCTAssertNil(PhoneScan.valid([[0.2, 0.2], [0.8, 0.2], [0.8, 0.8]]))
        XCTAssertNil(PhoneScan.valid([[0.2, 0.2], [0.8, 0.2], [0.8], [0.2, 0.8]]))
        XCTAssertNil(PhoneScan.valid([[0.2, .nan], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]))
        // Too little of the photograph (a tenth of it).
        XCTAssertNil(PhoneScan.valid([[0.3, 0.3], [0.6, 0.3], [0.6, 0.63], [0.3, 0.63]]))
        // A corner far from square, and corners that cross.
        XCTAssertNil(PhoneScan.valid([[0.1, 0.1], [0.9, 0.1], [0.6, 0.9], [0.1, 0.9]]))
        XCTAssertNil(PhoneScan.valid([[0.1, 0.1], [0.9, 0.9], [0.9, 0.1], [0.1, 0.9]]))
    }

    /// The scan is made again within his corners only when one of them
    /// lies beyond what the first merge cleaned: 1.5% of the work's size
    /// around the corners it had (the server's `_again`).
    func testCornersBeyondWhatWasCleanedMakeTheScanAgain() {
        let had = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
        XCTAssertFalse(PhoneScan.beyond(had, cleaned: had))
        XCTAssertFalse(PhoneScan.beyond([[0.3, 0.3], [0.7, 0.3], [0.7, 0.7], [0.3, 0.7]], cleaned: had))
        // Cleaned to 0.191…0.809 each way.
        XCTAssertFalse(PhoneScan.beyond([[0.195, 0.195], [0.805, 0.195], [0.805, 0.805], [0.195, 0.805]], cleaned: had))
        XCTAssertTrue(PhoneScan.beyond([[0.18, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]], cleaned: had))
        XCTAssertTrue(PhoneScan.beyond([[0.2, 0.2], [0.8, 0.2], [0.8, 0.83], [0.2, 0.8]], cleaned: had))
        // Corners the other way round are the same work.
        XCTAssertFalse(PhoneScan.beyond(had, cleaned: had.reversed()))
        XCTAssertFalse(PhoneScan.beyond([], cleaned: had))
    }

    /// The merge of 48 MP holds some 1.6 GB at its most: with less to
    /// spare the server makes the scan.
    func testThePhoneMakesTheScanOnlyWithTheMemoryToSpare() {
        let pixels = 8064 * 6048
        XCTAssertFalse(PhoneScan.roomy(pixels: pixels, available: 1 << 30))
        XCTAssertTrue(PhoneScan.roomy(pixels: pixels, available: 3 << 30))
        // The system does not say: tried.
        XCTAssertTrue(PhoneScan.roomy(pixels: pixels, available: 0))
    }

    // MARK: The scan as the server keeps it

    private static func picture(rows: Int, columns: Int, _ value: (Int, Int, Int) -> UInt8) -> Data {
        var picture = ScanPicture.head(rows: rows, columns: columns)
        for row in 0 ..< rows {
            for column in 0 ..< columns {
                for colour in 0 ..< 3 { picture.append(value(row, column, colour)) }
            }
        }
        return picture
    }

    /// The scan goes to the server as a JPEG of its own size, upright,
    /// with no colour profile of its own: the server keeps such a file as
    /// it came (any other it would draw anew, a JPEG of a JPEG).
    func testTheScanIsWrittenAsAPlainJpegOfItsSize() throws {
        let rows = 120, columns = 90
        let picture = Self.picture(rows: rows, columns: columns) { row, column, colour in
            UInt8(min(255, 40 + row + column / 2 + colour * 20))
        }
        let jpeg = try XCTUnwrap(PhoneScan.jpeg(of: picture))
        let size = try XCTUnwrap(PhoneScan.size(of: jpeg))
        XCTAssertEqual(size.columns, columns)
        XCTAssertEqual(size.rows, rows)
        XCTAssertNil(jpeg.range(of: Data("ICC_PROFILE".utf8)))
        let source = try XCTUnwrap(CGImageSourceCreateWithData(jpeg as CFData, nil))
        XCTAssertEqual(CGImageSourceGetType(source) as String?, UTType.jpeg.identifier)
        let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
        XCTAssertTrue([nil, 1].contains(properties?[kCGImagePropertyOrientation] as? Int))
        // The same picture, to what a JPEG of that quality loses.
        let into = try folder().appendingPathComponent("again.npy")
        try PhoneScan.write(jpeg, into: into)
        let again = try Data(contentsOf: into)
        XCTAssertEqual(again.count, picture.count)
        let worst = zip(again.dropFirst(again.count - rows * columns * 3), picture.dropFirst(picture.count - rows * columns * 3))
            .map { abs(Int($0) - Int($1)) }.max() ?? 255
        XCTAssertLessThanOrEqual(worst, 6)

        XCTAssertNil(PhoneScan.jpeg(of: Data("no picture".utf8)))
    }

    /// A JPEG's colour profile is left out and nothing else of it touched.
    func testAJpegIsMadePlainByLeavingItsColourProfileOut() throws {
        let file = try Self.file()
        let plain = PhoneScan.plain(file)
        // The made-up profile is 512 bytes, in one part of the file.
        XCTAssertEqual(plain.count, file.count - (2 + 2 + 14 + 512))
        XCTAssertNil(plain.range(of: Data("ICC_PROFILE".utf8)))
        XCTAssertEqual(PhoneScan.plain(plain), plain)
        let size = try XCTUnwrap(PhoneScan.size(of: plain))
        XCTAssertEqual(size.columns, 64)
        XCTAssertEqual(size.rows, 96)
        // Its numbers are then read as they stand, as sRGB's: P3's 200,
        // 100, 50 (the server's 215, 93, 31) in the fourth square down.
        let into = try folder().appendingPathComponent("plain.npy")
        try PhoneScan.write(plain, into: into)
        let read = try Data(contentsOf: into)
        let shape = try XCTUnwrap(ScanPicture.shape(of: read))
        let at = read.startIndex + shape.from + ((3 * 16 + 8) * shape.columns + 3 * 16 + 8) * 3
        XCTAssertEqual(Int(read[at]), 200, accuracy: 3)
        XCTAssertEqual(Int(read[at + 1]), 100, accuracy: 3)
        XCTAssertEqual(Int(read[at + 2]), 50, accuracy: 3)
        // What is no JPEG stays as it is.
        XCTAssertEqual(PhoneScan.plain(Data("no picture".utf8)), Data("no picture".utf8))
        XCTAssertEqual(PhoneScan.plain(Data()), Data())
    }

    // MARK: The scan made and sent

    /// A scan's photographs are read into files of their own and merged:
    /// the first whole, the sides the merge is made of. Where nothing
    /// could be laid over (a bare wall three times), no picture is made
    /// and the server is told so.
    func testAScanIsReadMergedAndToldToTheServer() throws {
        let wall = try XCTUnwrap(PhoneScan.jpeg(of: Self.picture(rows: 320, columns: 240) { _, _, _ in 128 }))
        let into = try folder().appendingPathComponent("scan")
        let read = try PhoneScan.read(first: wall, sides: [wall, wall], into: into)
        XCTAssertEqual(read.rows, 320)
        XCTAssertEqual(read.columns, 240)
        XCTAssertEqual(read.sides.count, 2)
        XCTAssertTrue(FileManager.default.fileExists(atPath: read.first.path))
        let corners = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
        let made = try PhoneScan.make(read, corners: corners)
        XCTAssertEqual(made.note.used, 0)
        XCTAssertNil(made.picture)
        XCTAssertEqual(made.corners, corners)
        // The merge's own file is not left behind.
        XCTAssertFalse(FileManager.default.fileExists(atPath: into.appendingPathComponent("made.npy").path))

        let told = PhoneScan.told(made, trace: ["first": 0.4, "turn": .nan], heat: (.nominal, .fair))
        let note = try XCTUnwrap(JSONSerialization.jsonObject(with: told) as? [String: Any])
        XCTAssertEqual(note["corners"] as? [[Double]], corners)
        XCTAssertEqual(note["used"] as? Int, 0)
        XCTAssertEqual(note["replaced"] as? Double, 0)
        XCTAssertEqual(note["doubt"] as? Bool, false)
        // What is no number is not sent (the server takes none such).
        XCTAssertEqual(note["trace"] as? [String: Double], ["first": 0.4])
        let phone = try XCTUnwrap(note["phone"] as? [String: Any])
        for key in ["seconds", "took", "files", "jpeg", "built", "model", "system", "app", "cores", "memory_gb", "low_power", "heat"] {
            XCTAssertNotNil(phone[key], key)
        }
        XCTAssertNil(phone["bytes"])
        XCTAssertEqual(phone["heat"] as? [Int], [0, 1])
        XCTAssertLessThanOrEqual(phone.count, 32)  // the most the server takes

        // With a picture: how much went, and how large the file is.
        var cleaned = made
        cleaned.note.used = 2
        cleaned.note.removed = 0.0412
        cleaned.picture = wall
        let more = try XCTUnwrap(JSONSerialization.jsonObject(with: PhoneScan.told(cleaned, trace: [:], heat: (.nominal, .nominal))) as? [String: Any])
        XCTAssertEqual(more["replaced"] as? Double, 0.0412)
        XCTAssertEqual(more["used"] as? Int, 2)
        XCTAssertNil(more["trace"])
        XCTAssertEqual((more["phone"] as? [String: Any])?["bytes"] as? Int, wall.count)
    }

    /// The phone makes the scan only of the camera's own files of all its
    /// photographs, the first as large as the server keeps it.
    @MainActor
    func testThePhoneMakesTheScanOnlyOfTheCamerasOwnFiles() throws {
        let file = try XCTUnwrap(PhoneScan.jpeg(of: Self.picture(rows: 40, columns: 30) { _, _, _ in 90 }))
        let small = UIImage()
        var shots = OwnShots(first: small, sides: [small, small], files: [file, file, file])
        XCTAssertTrue(OwnPhoneScan.can(shots, size: (30, 40)))
        // The server keeps it smaller, or turned: its own merge then.
        XCTAssertFalse(OwnPhoneScan.can(shots, size: (40, 30)))
        XCTAssertFalse(OwnPhoneScan.can(shots, size: (15, 20)))
        // A photograph without its file (the demo's), or no scan at all.
        shots.files = [file, file]
        XCTAssertFalse(OwnPhoneScan.can(shots, size: (30, 40)))
        XCTAssertFalse(OwnPhoneScan.can(OwnShots(first: small, files: [file]), size: (30, 40)))
    }

    /// The scan the phone made goes to the server; a server that will not
    /// take it has answered (it then makes the scan itself), one that
    /// could not be reached may be asked again.
    @MainActor
    func testThePhonesScanIsSentAndAnAnswerToldFromALostWay() async throws {
        XCTAssertTrue(OwnPhoneScan.refused(BackendError.http(status: 422, body: "")))
        XCTAssertTrue(OwnPhoneScan.refused(BackendError.http(status: 404, body: "")))
        XCTAssertTrue(OwnPhoneScan.refused(BackendError.notFound))
        XCTAssertFalse(OwnPhoneScan.refused(BackendError.http(status: 502, body: "")))
        XCTAssertFalse(OwnPhoneScan.refused(BackendError.interrupted))
        XCTAssertFalse(OwnPhoneScan.refused(URLError(.networkConnectionLost)))

        let demo = DemoBackend()
        let wall = try XCTUnwrap(PhoneScan.jpeg(of: Self.picture(rows: 40, columns: 30) { _, _, _ in 128 }))
        let sent = try await demo.sendOwnPhoto(wall)
        let corners = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
        func owed(_ token: String, replaced: Double, picture: Data?) throws -> OwnPhoneScan.Owed {
            let note = try JSONSerialization.data(withJSONObject: ["corners": corners, "used": 2, "replaced": replaced, "doubt": false])
            return OwnPhoneScan.Owed(token: token, note: note, picture: picture, outline: nil, trace: [:])
        }
        let whole = try owed(sent.token, replaced: 0.03, picture: wall)
        let kept = await OwnPhoneScan.deliver(whole, with: demo)
        XCTAssertEqual(kept, .kept)
        // Something taken off and no picture of it, or no such photograph.
        let bare = try owed(sent.token, replaced: 0.03, picture: nil)
        let none = await OwnPhoneScan.deliver(bare, with: demo)
        XCTAssertEqual(none, .refused)
        let other = try owed("0123456789abcdef01234567", replaced: 0, picture: nil)
        let unknown = await OwnPhoneScan.deliver(other, with: demo)
        XCTAssertEqual(unknown, .refused)
        // The phone's own photographs are let go of with the scan.
        let scan = OwnPhoneScan()
        let again = await scan.again(corners: corners)
        XCTAssertNil(again)
        scan.clear()
    }
}
