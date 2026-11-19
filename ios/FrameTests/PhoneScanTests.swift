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

    // MARK: A colour chart beside the work

    /// A colour chart as the server read one (`Chart.to_json` there: its
    /// white and the grey after it at the photograph's top, so the curves
    /// begin at the third grey), what the server gives the phone of it
    /// (`colorchecker.tables`, deflated here), a made-up picture (32 × 24,
    /// RGB) and that picture in the chart's colours as the core puts it.
    /// `server/tests/test_scan_core.py` takes all four out of here and
    /// holds them to the server's own `colorchecker.apply`.
    static let chart = #"{"corners": [[0.70486, 0.37658], [0.90135, 0.36673], [0.9048, 0.55234], [0.70901, 0.55747]], "darkest": 5, "greys": [[1.0, 0.921582, 0.55834, 0.309469, 0.144128, 0.05448], [0.991102, 0.964686, 0.590619, 0.323143, 0.14996, 0.056128], [0.991102, 1.0, 0.838799, 0.456411, 0.215861, 0.082283]], "left": 0.0008, "lightest": 2, "look": 1, "matrix": [[1.129914, -0.061719, -0.068195], [-0.044678, 1.085177, -0.040499], [-0.057307, -0.064547, 1.121854]], "off": 0.1179}"#
    static let chartTables = """
    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
    tfWFYRiGYZqwaua7/g8=
    """
    static let chartPicture = """
    ////////////////////////////////////////////////////////////////////////////////////////////////////
    ////////////////////////////MS3/Mrz/iaT/jfD/DSv/k5v/KAf/8dz/z4P/ZLX/jkT/mjn/uoH/8mH/ik//xSH/FKj/prr/
    NVj/1b3/L7b/XtX/0YX/a3f/roL/eqz/Os3/Mtr/urj/vPX/WXH/H6r/8PDw8fHx8vLy8/Pz9PT09fX19vb29/f3+Pj4+fn5+vr6
    +/v7/Pz8/f39/v7+////gRzdQE7FlH/eHs5kJl2th9W6fduK5KhPoEHjuuXolJ31te9U2bd3reRlT4xViAwTAAAAAAAAAAAAAAAA
    AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
    AAAAAAAAAAAAUTS/LFSPJnplUrMKQcpLTjzZsKD/ZmUrjhJnyEhk7gG43Kv+f6z+wY8jcjtPc9vhYKKgyAC1R5i9LvqUg6ocudWP
    HvZ9i1lrPqKaj4Z9vIN+7Z8oBuA0bSqAkdeeGmxgpkZ96qQdQVLC3yOQSc3G7fMkL3zt4az+kFMgr5bjqpYtzorH52DcMieGW5FN
    3B2eOuTEz/qyjl7+a5lVOxCq2jfxXaYbVxVYQMmZnob1eqpFY9QFf27vpbHVTwqPpiVxVS5cPxpZH+tpknNDA0EcqBcLADILsZbN
    sAeyn60g9JSO5xtRKNEGdJn8fsqJTJ11tU90/S09qLNSPQAn3/VarSa0mv/xUxcf34IU+uitX5SXgFxxdoaC5okcjRYzmKMw19hM
    SmxfyVKzy02Uniu/uJxoZY49tugLfRwKk/Q4uvitY3EEFADEl+/f8CIrWM/9pJreSeZqmYM22YKAxP9yTYr75R0CP4AObPAv0QmG
    qV23fgBun9ePFSsY3FZxTnvEw/nRptUyJB2iL5RHLFYJxxsXYKMJkgVh3Hw/wjSd97bk78mizkq162trU0G8cNxwzyFsXKoQ4omK
    9AGPk39IkvpxvuHWTVqasDpAoloD+c8Ps6DbXKBC2c9Q+oya050UuSmg6XKQ4nat1wJ+tsP9m5J5JV2DtrCtcps/ir7R7mmZfdVA
    2UKuP3vywl6fhXX8xgeYiSnh9EdInUBIAtuLiQc05ep8h64pMTmtb+oWsBlPLbHq/kM2KK/kUoee3OQJxfaL18eksfnSbQ8ZRRke
    LZ1/7JcrL+g262CKjWmDj3jvdkpWGZzxDmWrl3IrkfspM+zzkwIVKPb9pmS/QQEutTVSe5jy2iii8sWKKgWrbEZrGWtV2q5AJDP2
    gCU3CXNkeegffWaL+DefIXj3eDkuc5DUqYIidgF37xbeETxeZcHTuqKlPtAhOe7dLUEcbLpd3prvABiRwrdGDu8iJwWgnzgNVOd9
    5ZSw+CzfYxmkHBPrvVmChrvRVDDr1IFzp17Wc0wQVPOr+SqQsA91bZ7S1Yjy/sntuWpFuoVlDeasczWxu5ShjXleORlyID1wucaI
    i5g649jSbAuW88STDJgeHAHWf8+w6Gw0iyNBim5aqAbHBN0QV7q3op5elANeqPePkwaUrm5eZmKBXRtPm0PoHgWz4+Lw/AVPzbm8
    k894fkMVsCrCqEDWh4hXo6t3heYIFZTY0zTVdgdN23FBsdzlRfWeCSf2eOryi/1XL8zhVulehBMpt0+NITaoYkC8vetaxyeDDSS6
    EsiwVbt7zKoChIamK7eHe1PUUVBJxKEg/VryOC4bmD+pRcyMcksanqxFiFlrFTmHbTZqEeCil9bSj/Yvc0y4GIlfUFAgNBdpGI8D
    ssSIUb/k7GwPRg5BB3wteWDcZWmgQNyv5+fGrOV8ASua9ekxKm6Vylgkl75nadYhdypBmRB1QaZ/i3E1Kq6PBBYBEwPKKBHpWgRn
    0G8lvMniJTER7q8bgP5ALy613vLMihwaWbSnzYsV0wrN6QRUU+WCgD03+pJvTFYAj4c2ojbRZPVlIPLc0LWWMFYyTcNncnL18vAX
    d3YTt82oAPTZShX5jFq8xsP/4D2ODDUZpud6DCCFHNBNsx52nrLsBI/7/Izh0yK5ofWChP7Sb9XwIjVsDE5RQKQ5HQc8N1FdNClN
    IHwkoi3gaR/Q8S3imy8TD01iN0p39RCSEg4us6cYgDHDkF0HGysxa7E2+B9b09oRJT6jRWSN/+HmFFlt4wjbuzVZLZDdX77lyu80
    4Fz423BglZCgmP+4OuPXWfjuh/y0mkccs3Y8TKr+VKLV+5EAELdM8ZdI1ZuE+tV/I7VxV52GvjVPXa+FFsREylX6twM/DXFqnIqL
    t8OW/AlJ3uvKML5V9pAah06/8t95J/tMa/w8bzlm0+NeX7Frgnnnm6HZfVBtg/0YcaqYe+WupP8Bl/H6p+4qo9NJzV5/GGEXKtmo
    as4Lbq97wXEzmMAj7WpySrCuiY/pPOZPsFfDYjCjdphMuNLBWMMYQgHvMvoFsyN+jQrNsreiZ75yL5Xev/buBo2A26vrCDq6zpMp
    dDswAyLoExI0W5RBavuSMYG/pmKti5MKC0uljGxK02vkKxiZiinqxYT29pUFzG9GCAr937fMNVSB9aI+ZxwLDl3q6Fm93s32osxV
    lXz5RYIkadXGseZHMpaNBfZsPUwi6DDCFsX43dMPnOqeJCuLpt93aLIY8zfAwgh/spXWJprHzbdQ56NQhwVYzhH8wRKH0ZXkbAqt
    0TJa0dUvRoJCc7gexgUQu2jEfW9lf7XDsGNpm07K+Ij/4AoyG7OU2yO8Dd84TmKk3StQ7VSs9M9yQDToeCU1o+hBEiTP5r3wsJOQ
    X3B0L89Xg5UAYLZM8ATLPsiFSI9pJcTGH9weohA+57yQPaZ2+uKrOSiXoGNiIn7NdJkgq/jV/iU7xRi3MZOvDAk2yqrJCaMKRqbc
    LqB0LNbhQ23UrVlcLpVyxX4xU7HGwewIuU/nid/zFyyB5pPCk9dnJ+4JgC5/Rk5rAFNcy4ca
    """
    static let chartPut = """
    6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo
    6Ojo6Ojo6Ojo6Ojo6Ojo6Ojo6OjoAADPAKzLdpLKcNzcAADPgYjKAADP4MzgxGzJRaTKgCTMjAXMrGzK5DnkezbMugDLAJjMlKfJ
    AEbOxqjGAKbMNMTJxW7JVWbMoG7KY5rKALzKAMjKqqTIpt/gPmDOAJrM4N6+4d7A4uDE4uDH4+HK5OLN5OPQ5OTU5eTW5uXZ5ubc
    5ubg5ubj5ubk5+fm6OjodQCyKkCfhm6wAMA9AFKKdMSMbMpe3JYAlSK1qNGxg4vCqN0A0KVEoNIoRII4hAAAAAAAAAAAAAAAAAAA
    AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
    AAAAAAAAAAAAQiGaF0pxDHFKRKcAJLwbOiivoIzJYFwGiABMwjI+5QCMzpXOaZrKuoAAbTA2WMmvT5V7wACMK4qVAOZnep0ArMRf
    AORQhE1NIZV2hnlatHRW5I0AANEAZhlkgcZyAGRIoDRc4pIALEWc2ABoHL2a4t8AAG6+05XSikgAooSyoogAxHaY3kKqJhxrUIYt
    1AB2ANOWxuR8fkjMYY0zLACK0ADCUpoAUgNCFrpyj3TCcJ0UUsYAb1y/lqClRwByoABSUCRGOhBFANw8i2gcADwOpAAAAC4CpYWf
    qACMlp8A54Be4QAcAMQAXojJbrpgPJJUrj1R7AAAnqQaOgAa2uEApQCNgObGUA0M2HEA6OBzUIh0eVBUbHpg3ngAiAAUkJYAzMcA
    QGNFwDqKxDVulQCYr408XIMXqtYAeQgAg+MAquR6XGgAAACfgtyq5gAAK77IloiuJtY9knYA0XBUtuguKHrJ4AAANXgAWOAAygBg
    oEqPeABUkMZiECgN1kBIOG6csuSamsQABwaDGYopJlAAwgAAVpgAjQBF1msAugh356Cs5LRuxi2L5FY7RTKXXsxDyQBHUJ4A2nZd
    6ABkjHMhgOY4rs6iQE96qiYXnE4A6cAApo6qUJQaz74A6nZqzI0AsgB74Vxk2WGA0QBYpa/GkoRUC1Rmqp+BaZASeK2i5VJsbsYA
    0R2EDGzCukp4dGLKvwBzfQC06CYAmDEoAMxkhQAY2dY9faAAGiyMXNoAqgAuAKK67BwAAKC1Qnt70tEAt+NUzLRznuScagAAQhIP
    AJJe5IUAANkA5EhehVxigGa+cEA8AI3BAFqIkGYAgOYAANnJjwAAAOLgnFKWPgAgsBwuaIjA0gB65rFUEgCKZjxQAGM+0p0AABbH
    fBQdAGpKaNgAdFpq6gBzAGnHdC4SYoGoonUAcABc5ACsADZJTLGlsJJ6IMIAANyrKDwKXqw10oS9AAZ0uacAAOAAEQCCmigANtdS
    3ICC6ACsWgCDAAC+tkdddKqiQA2+zHBInEqpbkMAK+J+6gBkqgBUWo+myXLB6rK3slwSsnY8ANaBaSCNsoR4hm09MgpaEDZYrrVa
    gowA1secZAB25rBeAI4AAACubL6E4VkAhg0mg2I6nwCeAM4APqyOmpA0jwBCmORcjABzp2A5XldiWQw6jya5AACS1M+87AAGwaaM
    hr9MejkApwCYniGqfnw0mJxOdtYAAIasygCncgA21GAAoMiwAORxAADIWdfEeecAALyxO9kqgAAIsDxpACqIVjCXsNkAwABeAA2X
    ALmIQq1WxJoAeHiAAKpkbkKqTEgzvJIA6i/ONSkMkCqEI71mbkIAlZ4Agk1NADBsZypQANB4hcSgf+QAaDySAIBETEkDLgpSAIYA
    prRbKa+05FgAQgIwAHQSa0+wWl1+AMyE2dSPntRIAB985t8ACWR2xEcAjK86WccAcx0pkwBXKppehWYEAKJsAhQAAACkAAC9VQBQ
    yl8ArbauIiwD5J0AbOgAFR2S1dyUhgIARKaAxnwAygCg4wAiNNRXezIa6n44R08AiHsAmA6mS+QuAOCqxqNoKVAeNrVBX2HE5eIA
    cGwAqrt6AOKoLgDKgkqVtq7H2RRmBDENmNZGABRqAMIerQBVjaC5AIDK6nSsywCPkONOaueeUsO+FS5VAEg9L5gMGQIuLkpGLiI6
    CnQAlwCyXACo5gCwlh4AAEZMLEJd6ABnDgoiqpgAdhOcilIAFiYkX6QA6gAmycgAAzODOFpu6tmqAFJU2gCqtho2AIKwQK60wNwA
    1DrO1F4wioJ6g+iGANKnIOS+cOaDlToArGgAGprKOJSo634AAKon5oUAzIpX6Mk/AKhPSJBkuBopTKJhALcUvzXGsgAWAGhQknxm
    rLJp7AAA0taTALEw6H4AfDyY5dQ1AOcAVOcAaS5MytAAUKRHcmi4jJCqdkRQcegAYpxyZtSAlegAfNzWmtwAl8IAxkpYCFoAAMl+
    XMAAYKJWumIAjrEA5FRELqKHeX64BNYSpkKYWR6CbIwmqr+QSLYAJgDCAOYArQBcgwCkpqZ2V7BMAIexrOG6AIJizpa2ACyWxoQA
    cDEVAAC8Dg4oUIoeT+ZjAHSYnVGGg4cAAECFhmEpyFKyGgB7fgC8uG7C6IIAxl8DAADO06KaKExm6JAAZBAAAE694DyQz7jGlrwX
    hmnGO3gAT8SYpNQAD4psAOQ9OEYM4ACVALTF08QAi9huESBvmM5FXKUA5wCSvABcpoOnAI2exKYA3pIAggA+xADIugBkxYCxYwCK
    ywYyx8QAPHgmaKoAwQAAslSYdmRHbqWXqlRGkDmg5mvm2gAAAKZw0wCQANAAQFeC1wAf5DaA5r8vIhq8dBccltcAAASo2Ke/p4Ro
    VmZXAMEse4oAUqkh5gCcFrpfOoRLALSaAM4AnQAd3KleJJpV6NpyLBp5mlZAAHGka44AmOSg7AAAvQCOAIaKBgUpvpiYAJgAHJeu
    BpRUAMawJ2Cqp0o5DopUvm8AN6KbtdoArjK3cMzCACNn3H6Shcc1AN4AehxhPkZSAExGxHgA
    """

    /// What a fixture above holds (base64; `deflated`: packed by zlib
    /// with no head, as `NSData` unpacks it).
    private static func held(_ text: String, deflated: Bool = false) throws -> Data {
        let data = try XCTUnwrap(Data(base64Encoded: text, options: .ignoreUnknownCharacters))
        guard deflated else { return data }
        return try (data as NSData).decompressed(using: .zlib) as Data
    }

    /// The phone puts its own photographs in the colours of the chart the
    /// server read (Mateusz 2026-11-19 08:09 UTC: "Czy iPhone będzie także
    /// obsługiwać kartę koloru"), value for value as the core does it on
    /// any processor, which is the server's `colorchecker.apply` (but for
    /// a level in one value of a million, where the server's OpenCV adds
    /// up in one step).
    func testAChartsColoursArePutAsTheServerPutsThem() throws {
        let tables = try Self.held(Self.chartTables, deflated: true)
        XCTAssertEqual(tables.count, 69704)
        XCTAssertEqual(String(decoding: tables.prefix(8), as: UTF8.self), "FRAMECH1")
        let pixels = try Self.held(Self.chartPicture), put = try Self.held(Self.chartPut)
        XCTAssertEqual(pixels.count, 24 * 32 * 3)
        XCTAssertEqual(put.count, pixels.count)
        XCTAssertNotEqual(put, pixels)

        let folder = try folder()
        let picture = folder.appendingPathComponent("picture.npy"), by = folder.appendingPathComponent("chart.tables")
        let head = ScanPicture.head(rows: 24, columns: 32)
        try (head + pixels).write(to: picture)
        try tables.write(to: by)
        try ScanCore.chart(picture, by: by)
        let made = try Data(contentsOf: picture)
        let shape = try XCTUnwrap(ScanPicture.shape(of: made))
        XCTAssertEqual(shape.rows, 24)
        XCTAssertEqual(shape.columns, 32)
        let got = [UInt8](made.suffix(from: made.startIndex + shape.from)), want = [UInt8](put)
        XCTAssertEqual(got.count, want.count)
        let off = zip(got, want).enumerated().filter { $0.element.0 != $0.element.1 }
        let first = off.first.map { "\($0.offset): \($0.element.0) for \($0.element.1)" } ?? "none"
        XCTAssertTrue(off.isEmpty, "\(off.count) values differ, the first at \(first)")

        // Tables this core does not know (another server's, a file cut
        // short) put nothing: the picture stays, and the server makes the scan.
        try (head + pixels).write(to: picture)
        try tables.prefix(4000).write(to: by)
        XCTAssertThrowsError(try ScanCore.chart(picture, by: by))
        var other = tables
        other[other.startIndex + 7] = UInt8(ascii: "9")
        try other.write(to: by)
        XCTAssertThrowsError(try ScanCore.chart(picture, by: by))
        XCTAssertEqual(try Data(contentsOf: picture), head + pixels)
        // And what is no picture is not taken for one.
        try tables.write(to: by)
        XCTAssertThrowsError(try ScanCore.chart(folder.appendingPathComponent("none.npy"), by: by))
    }

    /// A scan with a chart beside the work: each of its photographs is put
    /// in the chart's colours as it is read, and the server is told so (it
    /// takes no scan of such a photograph that was not).
    func testAScanWithAChartIsReadInTheChartsColours() throws {
        let tables = try Self.held(Self.chartTables, deflated: true)
        let wall = try XCTUnwrap(PhoneScan.jpeg(of: Self.picture(rows: 320, columns: 240) { _, _, colour in
            UInt8(120 + colour * 30)
        }))
        let plain = try PhoneScan.read(first: wall, sides: [wall], into: folder().appendingPathComponent("plain"))
        let trued = try PhoneScan.read(
            first: wall, sides: [wall], into: folder().appendingPathComponent("trued"), chart: tables
        )
        XCTAssertFalse(plain.trued)
        XCTAssertTrue(trued.trued)
        for (taken, put) in zip([plain.first] + plain.sides, [trued.first] + trued.sides) {
            let before = try Data(contentsOf: taken), after = try Data(contentsOf: put)
            XCTAssertEqual(before.count, after.count)
            XCTAssertNotEqual(before, after)
            let shape = try XCTUnwrap(ScanPicture.shape(of: after))
            XCTAssertEqual(shape.rows, 320)
            XCTAssertEqual(shape.columns, 240)
        }
        // Tables that are none: the phone makes no scan of it.
        XCTAssertThrowsError(try PhoneScan.read(
            first: wall, sides: [wall], into: folder().appendingPathComponent("none"), chart: Data("nothing".utf8)
        ))

        let corners = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
        let made = try PhoneScan.make(trued, corners: corners)
        XCTAssertTrue(made.trued)
        let told = try XCTUnwrap(JSONSerialization.jsonObject(
            with: PhoneScan.told(made, trace: [:], heat: (.nominal, .nominal))
        ) as? [String: Any])
        XCTAssertEqual(told["trued"] as? Bool, true)
        let bare = try XCTUnwrap(JSONSerialization.jsonObject(
            with: PhoneScan.told(PhoneScan.make(plain, corners: corners), trace: [:], heat: (.nominal, .nominal))
        ) as? [String: Any])
        XCTAssertNil(bare["trued"])
    }

    /// The demo's photographs have no chart: no tables of one.
    @MainActor
    func testTheDemoGivesNoTablesOfAChart() async throws {
        let demo = DemoBackend()
        do {
            _ = try await demo.ownChartTables(token: "0123456789abcdef01234567")
            XCTFail("tables of no chart")
        } catch {
            XCTAssertTrue(OwnPhoneScan.refused(error))
        }
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
