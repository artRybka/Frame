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
    static let chart = #"{"corners": [[0.70486, 0.37658], [0.90135, 0.36673], [0.9048, 0.55234], [0.70901, 0.55747]], "darkest": 5, "greys": [[1.0, 0.921582, 0.55834, 0.309469, 0.144128, 0.05448], [0.991102, 0.964686, 0.590619, 0.323143, 0.14996, 0.056128], [0.991102, 1.0, 0.838799, 0.456411, 0.215861, 0.082283]], "left": 0.0008, "lightest": 2, "look": 2, "matrix": [[1.129914, -0.061719, -0.068195], [-0.044678, 1.085177, -0.040499], [-0.057307, -0.064547, 1.121854]], "off": 0.1179}"#
    static let chartTables = """
    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
    zLfUMAzTAP4F
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
    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
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

    // MARK: The lens's bend

    /// A made-up picture (36 × 48, RGB) and that picture as a lens without
    /// its bend would have drawn it: by the one measured term
    /// (`lensNumber`) and by a camera's own table (`lensTable` about
    /// `lensCentre`), as the server's `lens.straight` makes them
    /// (`tests/test_scan_core.py` holds these to it).
    static let lensNumber = -0.023
    static let lensTable: [Double] = [0.0, -0.000248, -0.000987, -0.002209, -0.003897, -0.006028, -0.008572, -0.011493, -0.014749, -0.01829, -0.022061, -0.026]
    static let lensCentre: [Double] = [0.512, 0.488]
    static let lensPicture = """
    ob5FocRFm8BQs65ir6F6uImKzoOjzXLN12DZvVLZrGjFm320goudZqCRUqaGMaV8K5N+IYhvLoBzJmiIJWiBIFaQEUZ9HUp1IzFk
    GjxWJTFkKzlTUDNQXTFsdDtrfjx1lz9+jk+ColCPnUmKmsw8pcw9nsBAqa5OqZ50u4iCyHyt0mS30ljGzlvTql7NpGm5dYuvcZuO
    TpxvP5p9NJ18KpOAH3t8KnaGH2SUK1GPKkF6GkF5FEVnGTJlMTdWLDhYOzVWWDhdazpygkBxf096m0KIm0eJk015r79Uor9Gn7JG
    nrVopp18x4qWy3uj12HIwGHUtmTUqGbBo3mziI+naqOQSqV6O69wKpRtMIyDIIWLIH6HKlyMIk95IFSAI0V0GzNyID9nL0BeQzla
    UUFdYT1iajRrdURqijt5kj5yolN1nE17o7BZq8Jiq71SoJ5osaRxvIWXxHKoz2nBwFjMuGLCuHTIlHa0i4+rgZiFY5+CXJ2FUqGA
    PpuCMnp+O2V6O2J/N113K0R6KjVzPjRrOTNZRCtTTjdGUTBMYDpTbDFieDdfiUlllUtvjD5vlD5zqqZvpbJpqpZ+opJx6+vr6+vr
    6+vr6+vr6+vr6+vr6+vr6+vr6+vr6+vr6+vr6+vr6+vr6+vr6+vr6+vr6+vr6+vr6+vr6+vr6+vr6+vr6+vr6+vr6+vr6+vr6+vr
    6+vrkD1UiT5blExjlEpptY+UrpV9oIuLrYiJroucs3KhpV6VtFubslyltmKnpGequX+dpJuktaGgo6+hnK6LgKeGbqaKVo6GVHiC
    PlN/TkxpUzVsYDdiZDpcdTc8eDBCgzg1jjAykC8tgjlJjDpIijI9e0VAhTtKf0NFtnypp4WlqHykqnqdqnmjFBQUn2CQoFmUml6J
    p16MsW+VsouduqSZzq+Zt8GSuLKRpaaVk5OLgYiLYWiMWEtxVE5vUy9hdjBLfj4/hTc1pzQurz02ry4kkyotjz8iljgqhS42fT0+
    bz4/ezpAt2rAqHu4pXqtqHixoHKkFBQUp0+DkFSCoWB/omdyqnaOs5eE16uh2L6m4Laey8Swy72XpaGil4ePfl+FaVSBYEtcZjdZ
    fydKiyk1rTg9wDAftC0lxDsarDsYqDYahkMrfzUqezciekMWfEIjrFrEs2y9vmG4qmmsn2SjFBQUkk2Ql02Ej1Fpm213pHB+rZd7
    y6OS2q2U58mk57GyyqqXvYyYkXWWj1uMfkJwejhffSxPoCU+si0t0Dkq0UEbxz4QxjcauS4Tr0AOkDkVeTYfZD4RXjUcbTMdvWC2
    wl+/v2bJtFG7pGmcFBQUlWd9jWd6fWNii3Ven4R0ppKCwJ+I4LCU5rap26Cm2pyktYyYp3+Sj2dugUByjUdikixEoS1DujI73S4t
    6UIk5jITyjMJsUIbo0QRg0AfbUAaXkYMaD8aYFAQsl6stUqrtlqnsFatrVefFBQUjGh4fn9ng4JVeItrgINfkZpupo96rpqWv6CV
    vYSQv4mNtHJ8uWeBrV5kl0xnoTtXsS9AuyswyDsnzz8h1Eop3k4RyEkftVERnFIXjFgibVQYWVgjVGceYWgbxFOmw1OXwVSNvmqd
    n2GTFBQUfX19h5RldI5edZ1ggJdbhZNwfI9ukHh/nXGLomqKrmF8sl1ssFBnoVBgqkZZvEhRtDc3wDI/1Doy10Yh0kIuvj4gv10Y
    o1EmiVYocmUnZnYmY3osRnwvSXUttV+AwGB2tWaItWBurm91FBQUiIhpg5NebJlgbZ9kYZ9jXZlicYd3ZmZ+b2RyeFx7llNvl0tv
    rThftk5Ur0VKyUI9xks11Uo0zUY0xUEizFMmrVAwrFgiiWo2gmk1d4MsWYQ1XJAzRoBESYg9wlhtwFtmv1tovHVknIZvFBQUi6dh
    ebNoYrVhZqJsSZxqSI50TGpnQ2BlVD1vUTJvcC9RejxcpTxZtTI/wE44xDw33EZDyj04wEoywlI3s1c8o2QtiV45jXg7aHZIYIY/
    XJo+VpVUQaVPVphQy2pHw2xOt2M9sX9DtYhaFBQUjaZndblfbMJuWLxeVJlfNYdxKHdvL1BgOz1hSihbXCZUgyJKni5Qqzc/xT5F
    31ky3Eo22VE/zVM8tFc4nFs4kHc9fIA4gYtRb4dHXpZgXo9eUpdTXKNjVqJq0HEz03U003gtwnlGqYFJFBQUl6dWdMRWdr5kXrBj
    SJljM49XNGtmI1pfNDFPNypGZDBMfy5QlT9GtVE631o+51U86Woz4Vs1w14otHIlm2s5loE8h48+epBFa4ladJ5UYaJzaZtzVaJp
    X5552nQ24Xoz0HAuwXs0r4wxFBQUkJ1DhbZPbrhTVrBRQp9PSJFRL3lSOlViMk1TSjJIZThNfEVEqj9RvFE74lxG2Wg23Ho41YU1
    unghqpEtn5EwnJo3kZM5eYxOjZFee5Fdb5Bva4+IgZB4dnuK03Qi3YYzzXs30IguxZA0FBQUnpQ0ip9Jd55SW6NNYpNUSoBMQnBW
    S2RgUmhhW2debmVmkWZMslZZzG1Gx25A3W8/0X0y3Iw60Jcrv6UfspkfnqE3jpI8lpVKnY5ij4RxlntzimOTg2yFjF6F4oIx6YMr
    534p1nwzvYY2FBQUp4QwiItAeoU+c5M5X5NBXYZHYotYdIBXcYhpdINnioRylHhrtIdgvXxhwX9Y3JFK2Y0206QzzKAbwbMfq6wm
    prQipKw5o4xEoYBQn197qGZ6rFaTnFOJq1KP8YYv7Jkx7ZIv1Ikqy40lFBQUoIUkh3EghnYlbYAtd3o3foxHfIRjio1ni5l0qaNv
    qKdvuZh6uZ5oxpNnzY1Z1I1Vzqw+yrYuwb8isMQctcESubQUtK00vZo5r3VYwl5ztkaCsCiLxSijtS6c6Iw16Z834o815JI7x4U+
    FBQUo3chkWIliGole2k6im06f4RTmodpnKZuq7t6sbJ8vrF+t7SIxKZwsKN1uJdisJhVwLA+xMUrutQfv9YjudAcwcMmvbAsuYY+
    y2VWz0Jm1id+xxGZ2Q6c2wyP9qdA9ZxF56xM3I81w4cvFBQUqGUei1giglEpb1Iqh1c6mHdIoZBfsZ14vbWPzruO0MmC0smFuqd9
    sp58o65ssp1LpalDs8M9uMUetc8dvN0iu9EczaAqw30632td1T9s4B5z3RGA2wWX5QiZ/6xK7ahM96NY5KtO1I1FFBQUm1Akf0Ue
    fTgbdjQviEU/lGZTtohyvKV33LOE2s2UzL6Yw8aCvriBs6d0oalimZ9Fk7A5kbY7o9c2n84sq9EqubcqxaIy1X0542NX3S1s4Bhw
    +QCC6giD8QB+/8Ra+7tc+bFj16FZxZdeFBQUnFE8fzQvdDU2bTM0fEc6mVZkrXZ+yJWU7Kaf6cGT0bqS1rh/raZ5qJ5zkYpihZdB
    kKFHh7g4n7U4ocMtp786rrowups50X034FZF3jlg7hBk8ABZ9gBu8wBs/9B6/8N8975q3aZjzIlhFBQUmEU/fS83ahIqZyA4fyZL
    mFFpwl544I2N7aKh7LGu4aeiyrWSpJZzkYpjkJJFgohRcZczfJxIjq4+lK46rq1LsaxNyJVEy3871lFG6DY86BVU6AJT+gBD/wBX
    6N6Q7tWJ6cZ70a6EwZVpFBQUfERFazg7ah5HXBdIgSxYj0NxrGZ60HyY7JSk3Z6i1JygxaaKoZ15goRbg3xLeIE3a304c5NOgJVO
    mrBLoqlasKBUvY1VyXNO2lBI3kA/8h5E9gsy+As37QA+7+Ka5OOI48qRy8CSr6JwFBQUe0tZbDxBUR09TxtQahtljENwq2SExWub
    6Zqr6qWq052rtaCbloZ+gX1pbndOWodTZpBKcJBYb5NNfZVXo5ZdoJdfwHxiyGVJ1ExP4C5C7Sg84Rgy9AIt5hgt7OKg4+Se0cig
    1MKFqqyDFBQUalFXYUdOTRxQSiZaVSJWfD14olOCy4KW146l4KCiyaSfp6afipaJfIZsY4BiZYdaZJRmZYhZeqNskaJynI1/pJZz
    s4BywlpowVRa3i5N5CI65xYs6wU46A022c+l1+Wh2d6Yt76YraaEFBQUcnRjV1dSPztNQD5YWzlTbFhnjm99q4ySvJ+ivqyrxa2t
    n6SdgZ+Ka5uEX5SAZ5Rua5RucZ9/eaWJiamPlqKMroOBr3N8vm9xy0xs0C1XySVMzxpM2gpP2g5U1tmRxs+ZwNOWuMd+kLaDFBQU
    Y39aPGZLL2hUPVlGUmZmZHJcfnV4noyRvJ2Zwbaat6uWobCphMGVdbKVYLCZXrSPb7Wcc6idlbuhpKybpp6UsomWvYKGyWeGvVl3
    uTpqux1qyB9nyR5nxg1iusGTxsh+r86Po7V/mLR/FBQUWYxnPntOMHtVLHZQSYtLT4tZeIt1fax6orB9n7SbnsSUmrqwdsCgddGq
    a9a2c9a8fMa4jryvnsKvo7acu6OSuZOVuYSVtWOHwUuOwDGFtyyGtxJ+uBOIwxSHrcx+u8iGrsx+mcRugbpwFBQUT55mL6tXNZBJ
    MZlIQKhRUqJVX6BUdrBgirmBhMKPh8iViNGpdt3CatTCetzFb9vQedPFls/QosSvsci7s6ipyKWoy3qctHGnu1iZpjaboCuwpSal
    nyCyoRKip8aAqb+DmrB7kbZxgbVxFBQUR7ZYOKdIMbY/H60+H7pINq1URatOZ7hmZbRxgs17ecaRgdeeeN7CY/DLb+zfdPPkftrg
    kOPOnNa7qs6tyKerz56szHqnxHantU27tUe2pyK4qSXHmRi/nBu5oLx+q8F9lbt5mqxkh8BiFBQUVLZLL7BTMrpFL7pQHK9OOLZE
    N7ROQb9RZbxyZriCX8+XY9Ksa9Gza9nEZ+LZaeXbedbfitHLr83Rvb+2sa24yaKvuoGztG+4t0rDqULOoyjFlhTXigvZkBXXo8Fv
    o7JwpblnkbprcrtsFBQUSLJAPrI9N8A2McJDKrhBMrxHKqpLPrRcQrtuSax6U7t+TL6bQ9a4SNm0Y9m7adbMacrXiNHBnMK1qLC3
    v5vAxZW/sYWvuWu6t0W8qkXBqS7YlxvXpB7WlBrYprpvmrN4lbV/m755jLZhFBQUUrdFT6grLKwyH6MvIKwxKZw6OZtKP55UQaFu
    OqGARa9/QrOLQLabTKumR7+zXr++a7Gqea2qhLOtk5ywnZ2rq320uHm1tly+tUXUpTrNmSraohLXmgnQoBfhob50sbN6n69/o8Bm
    e6pdFBQUX6lGU6U4OJAaPZAhNIg1KZQtNYxWKJxnKJ9tKJZ+KYqAO5d9KZuCOJ+PPZ6TPJeIWJOXY5qSgpmjj5CelI6zm3GqonTE
    pl/BpDjAoifDqxXFsxDXrw3IsBTepcaEscCGta15o6xokKhfFBQUZYkwZZQeRHwoPn4QOX0yKnIuMndZOYpsNZFqJIeIHnuGGnt8
    KoR7LYBgKX5sMnpqQn+EWm94dYiKhn+lkXOgnXuuslq7slS4qj67uja2shG5rQ/EtRW9rAjIxMFxwcN4urN5obZyo55bFBQUdIUx
    WnUiToAaRHYeOHQuMngzKW9MOYB0KH6DNYSIH3J/HXJxEmBhI2dSGlFYJ19jP2drQWd+Um2Ra3CSem6rmnWmrWSwn163u0C8rD6w
    sC7AtROxvg/ExRGxurVxxrJoyL1hvLZmm5tSFBQUbI0nZXknTWYnSG8ZQGQtL3A8RXdlRox1PH2KMH2OIYOKIGuAIGheG1hfDVBQ
    H09JKVBkQFt5V1+CdGiOjHy1n26+pl6/tVOuuV23s0utpT6qtimiwTeptTWu16hUxKljvbRcu51SrJ5AFBQUcok2aHMhVnkmPmwl
    P3U1PnRfPYVpVo5/S5SLP5KeQHeVNIF3EmN3E19lDUhSCU5kMFhpPV2CVm6QcH6piIOrkYO7oX6prnenpW+oqV6cnkuXq0mSpk+X
    tDyV2LFB5KtR1ZxEx61Rt45IFBQUgJE1WnY9VH84SoBCM3dQT5NnUZV6Z6CKWpyjV6SkVpiYM3yXHm1+C258BGV0FEtlMWd+OmCQ
    VnuefHqmnH23o4jDtIOsp4KxrnKel2+Nn2iApXN+lV97mWt84a5C6p4w464ywacxs5Ezmoc3eJVIUIxIQIdQN4djQ4dlTqVuWqGO
    dK2ghbOtb6qdbq6gQo+nKXmaG4GKC154D257G26FTnihWYOpdoarm4y8tpC9qJ2mo56VppKZmoFykn9vkIthiIhjkpJU7qcg5pop
    65Ii0Zc0rKQ/lYo6b5BOSotPPJdhQYl4SZ6IX6uWbq+hisarh8Kwhbuod7elVrSoPJKbF3uaGXSmDG+fLXWiUnSncIPCgofHoJa9
    saSxrp6urZqMpap9j6h4jp1ad6pTgaNPg6FF9KAL85wT5J4P06AXsZM4l5hFd50+UIxZMZttLp57SqiIUMCZgM2fl8yxn8+0nc+6
    h8TFb8CzPKq0Lom6EZCuIIOvKISvU4a8eY/BnZXPpJvSwKvBtLOorrCVlLJ3kbpXesI/f8I/erc3aMY7/4sN/YgE9KAE2JgTuJgs
    lJo2d49aXJ1eRpt/MqeMRbyOVcuvjdG4nd29rNe6tenHouDPbb/FSLq5M5m+G4fII5DANXzDQZLXcpHQkKLVqZzVxrm0sruuu7WZ
    m8hricledsxHa9YpctcoaMsb/ZgL+p0A+5kF7YwMypIonJ0zdppWUJRkN6V1LLWLTrqiWcyjhM68sN26t+25q9rBqNPHbtDGTLvC
    IJm8HJS5HJbNJIa+UZfLfJHYoKbluqXHvqrAycatssSBmcZkgN5WaeFCZd4tbdcXaeAQ+YkH9pQA7pAU1okXvJUrnI44eptQRqFl
    Q6CANKqSOq+UZtGik+G7qOXDsOa7uem7quPAedK8Rq7OIp/BFovHFo25NZPNQoXagaLioJTSwa/YwLTMyLavusKLkMBpetxFfNcy
    a9cZW9gbV94Q
    """
    static let lensByNumber = """
    n8c/ocpDobtKsahfrJp5vISKzHyuz2jF1ljSwVTVqmbHmna0eYyhaZ2NT6F9Np5+L5d+I4xzKHxzKGqGIWeGJFaRGkF8GUV2Hjll
    GDZZKDBdJzZVPjJOVTBgajhsfDlwiEZ4kUuDnEiPmUqGpMpDocE9n7VFpLBgr5uDxoySzX2z1mO+zmLNx2XWqWPKp3O5epKwcaGQ
    TqFyQqJ8NZ17MpSHI4KGLIGKJmeZL1WOMU6BJEp+GEpxHj1vNURgOUFhQkJiXUVja0B1gEp3gEt5kDx+oUiBmlF7q7pZpb5LorVR
    napuqI9ywniUx2ag0FLItlDPrVfKpV+7lXGrgYieY5uERJ91NadpJI5mJYd5FXqAFW56H1F+FkVrEER1EzFnFR5lFipVISlNNiRC
    QydFUSlKWxxVYSVRgzlskkNyl0lumkd2o7JgrcJoqKdep59yzMGhx6Ky1JrD2JPSzYXVyIrNyJjUp5bFpam9mquZg7CagKygebWc
    Z6+bX5OWaIKUZ4WYZIKVWmyVXWaWcGmPa2aDcl5+f3F7fWp+h3OElnSRpHuYj1NokUVlj0VvkUBwraN1p6V0ood/r5+J6+Tz7N3o
    4drf5Nrf5d3h5uDk4t7j7OPi5+Xl6+fq7Ojq6url5ufk5ujm4+jm4+fl3+Hm49/h5eDj5N3f4dzg5t3b5N3c4tfW5tjW6dnU3s7Q
    5uTjoVZmfzJGkkxbkUpbtYqXqo6Io4WRsISPnnGLh0h3nUyMqkaRpkiYrFCdn1ifr3WVnJKZsZqVmquVlKZ/dp58Y5t+SYJ7Q2h3
    LkFxPDtdQCBdTx5OViVHZSAmbRgqeSEegxYXghETcx4nfB0oiSk2fEQ+ejtGeztEs3uvpYOtpHejtICtkGuQDRIMsmyel12OnmeJ
    qWWJtHiWtJSdxaqc1LaewcOVvraYsKuam5aRjIyPamqPYVF2XFZyWzhlfDVQh0NCjj8+sToxuUI9vDoqnzUymUQnm0cuhzE0gDY5
    dEE2eT84sWnCqHm2pnOrr3u4h2CMHhUZr1GOjFB9o157oWhzqHaMtJmB16qh17yk4rafzcOxy7yVp5+hlYSPgF2Fa1KAYUdaZzVX
    gSVJjCUyrzY7wTAdsywexDkZsTkTrDMVi0AkfjgoeDYfdUATeT8csF7Bu2q/vF24sGmziFeKFBMVnlebk0x+jFRom252pXN8rph9
    yqOR3K2T6Mmm566xy6iYvouXknWWj1yLf0FwfTlgfixOoCY/tC0v0jcp1kIdzD4QxzcXui0WsEAOlDoRejUfZUAQXDYaZjQdvV+0
    wV7AuGHEuVS9k1+KFxUVn2+DhWhzfmhginhenYZ0pZOBwJ6H3rCW47Oo2J6k2ZujtIuXqX+RkmdrgkFyjkdilS1Eoi1CuTM72i4t
    6EIl6TUUzjMJs0UapUYSiEQfcEIcXkgOZkUYY1MStFestkmmtFifuFyymU2NFBYUknGAe4Fgg4VWd41sf4RdkZpuo455q5iVvZ2U
    u4KPvYaLtHB6uWV/rV1kmUxmojtXsi9AvCowyTsnz0Eg0kkr208Sykwft1ATnFIXjVkjclkZXVslUGsiXGsexFWfw1WQvleLwW6d
    jVd/FBcVh4iDhZNhco9gdZ5fgJhcg5Nwe49uj3V/mm+KoGmJrV98sVxsr05moVBgqkVYvklQtTk3wDQ/1Do010Uh00MtvDwkvlwX
    o1QnilYqdGUoZHcoZn4rS30xRXgxt195v2F2smSCu2Zun2lsFBcUj5BsfpNca5thbJ9lXp9kW5licIR3ZGV9bmNxdlt6lVJulktv
    rThft01Tr0VJyUE9x0s21UozzEc0xEEjy1QmrlIwq1Yki2s1gGo4eYMtW4Y1XJE2SIVESYlBxFppv1tkvVtivoFmjnxmFhgUkbBm
    dLNmYrdiZaNrSJxqSIx1SmlmQl9kUzxvUDFvby5RejtbpTxZtTE/wE44xD033EZDyz05wEoywlI3slc9pGUuiF85jng8a3dIXoRE
    XZk+WJRTQ6VSU51Tym1FwmxKtWU4uIdIqHxTFBgWk65qcbhdbMNuWLtdVJhgM4dxKHZvLlBgOj1gSShaXCZUgyJKni5Qqzg/xT5F
    4Fky3Es22lE/zlM8tVc3nFs4kHc+fYE3gIxRcYdIYJZeX5BiVJVUW6FhWKNs0XI01XYx0XYuxH1JmXdCFRYVnK9YccJVdr5kXa9j
    RpliM45WNGtlI1pfNDFPNypGZDBMfy9QlT9GtVE64Fs+51U86Wsz4Vw1w14otHMknGw5l4E8iY8+e5BDbIlbdZtTYqNwapt3WaFp
    X51423U14Hozym4uxII0oYItFBUVlqVFhLRPbrhTVa9QQ55PSJBRL3lSOlViMk1TSjJIZThNfEVEqj9RvFE74lxG2Wg23Ho41YY1
    u3kiq5EtoJIvnJo3kpM5eoxNjpFefpFeco9saoyIgY96enuH1Xck3IY0y3k11o4vuogzFBUUpZs2iJ1Jd51SXKJNYpJUSoBMQnBW
    S2RgUmhhW2debmVmkWZMslZZzG1Gx25A3W8/0X0y3Iw60JcrwKYfs5kfn6I2jpM8lpVIno9gkINyl3xxj2ORg2qIjV+E5IMx6oMq
    5X0p2IA0soAzFRQUrYoyhYk/e4U9cpM5X5NBXYZHYotYdIBXcYhpdINnioRylHhrtIdgvXxhwX9Y3JFK2Y0206QzzKAbwrMfrKwm
    p7Qhpa04pI5EoYFNoGB6p2V6rVeRnlKLqlGP8Ikv7Jsx6Y8v2I4qwYYkFBUUo4gkhXAghnclbYAtd3o3foxHfIRjio1ni5l0qaNv
    qKdvuZh6uZ5oxpNnzY1Z1I1Vzqw+yrYuwb8isMQctcESubQTtK0zvps5sHdWwl9xuUiBryiJxSaiuSyd6ZA26J834I416JU9u308
    FBUTp3kij2EliGsme2k6im06f4RTmodpnKZuq7t6sbJ8vrF+t7SIxKZwsKN1uJdisJhVwLA+xMUrutQfv9YjudAcwcMmvbEsuYc9
    ymdVz0Rl1yl7yBKX1w6d3QyQ96ZA9J5H5apL35A0uIEuFRMTq2ceiVciglEpb1Iqh1c6mHdIoZBfsZ14vbWPzruO0MmC0smFuqd9
    sp58o65ssp1LpalDs8M9uMUetc8dvN0iu9IczaIpw3453m1b1UJr3yBy3xJ+2waV5AeZ/axK7adO9aNY561OyYVCExMTnlIlfUQd
    fTgbdjQwiEU/lGZTtohyvKV33LOE2s2UzL6Yw8aCvriBs6d0oalimZ9Fk7A5kbY7o9c2n84sqtEqubgqxaMy1H4442ZV3jBr3hpv
    +AGA7AeE8AF+/sNa+7pd9a5i2KJaupBaFBITn1I9fTMudDU2bTM0fEc6mVZkrXZ+yJWU7Kaf6cGT0bqS1rh/raZ5qJ5zkYpihZdB
    kKFHh7g4n7U4ocMtp786rrswuZw50H434FhD3jtf7RJl8ABY9QBs8wBt/897/8J787xo36ZkwYJdExITm0ZAey02ahIqZyA5fyZL
    mFFpwl544I2N7aKh7LGu4aeiyrWSpJZzkYpjkJJFgohRcZczfJxIjq4+lK46ra1LsaxNx5ZEy4A71VRG5zg86BdS5wNV+ABD/wBV
    6N2Q79OH5cN71K6Ft45jEhEUf0ZGajc7ah1HXBdIgSxYj0NxrGZ60HyY7JSk3Z6i1JygxaaKoZ15goRbg3xLeIE3a304c5NOgJVO
    mrBLoqlar6BUvY5VyHRO2VJJ3UE/8CJF9gwz+Aw17gE+7eOY5OGH4ceRzMKSpplpExEUfk1aajpAUR0+UBtRahtljENwq2SExWub
    6Zqr6qWq052rtaCbloZ+gX1pbndOWodTZpBKcJBYb5NNfZVXo5ZdoJdfv31jyGZJ005P3y9D7Sg94Rsz8wIt6BUt7OSf4OGe0MWd
    1sWGoKN9ExETbVNZX0VNTRxRSiZaVSJWfD14olOCy4KW146l4KCiyaSfp6afipaJfIZsY4BiZYdaZJRmZYhZeqNskaJynI1/pJZz
    soFywltpwFVb3TBO5SI85xgs6wY26Qw22NKl2eeg1dqXub+apZ19EhMUdHVlVVVRPztOQT5YWzlTbFhnjm99q4ySvJ+ivqyrxa2t
    n6SdgZ+Ka5uEX5SAZ5Rua5RucZ9/eaWJiamPlaOMroSBr3N8vW9xyk9s0S5YyiZLzhxL2gpO2w1T1diSxNCbwNKTuMqBiKx9FBMT
    Z4RdOmRKMGdUPllGU2dmZHJcfnV4noyRvJ2Zwbaat6uWobCphMGVdbKVYLCZXrSPb7Wcc6idlbuhpK2bpp+UsYmWvIKGyWmGvlp4
    uTxpuh5pxx9nyiBmxw9hvsKQxcqAq8mOpriBkKt5EhMUXJFqPXhMMHtWLXVPSotMT4tZeIt1fax6orB9n7SbnsSUmrqwdsCgddGq
    a9a2c9a8fMa4jryvnsKvoracu6OSuZOVuYWVtWWHwE2NwTKFuC2FuRR8uRKEwxSFr8qAvcmGqst7msdxd6toExQUUaZqLqhWNY9K
    MZlJQqdRU6FVYKBVdrBgirmBhMKPh8iViNGpdt3CatTCetzFb9vQedPFls7PosOvsci7sqmpx6aoy3uctHGmu1qZqTiYoCyupSaj
    oCGvohOjqMeAqL2DmK54kr10dqVpEhUUSb1cNqVGMbY/H60+IbpJN6xURqtOaLhmZrRxgs17esaRgteeeN/DY/DLcOzedPPkftrg
    kOPOm9a7qc+ux6irz5+szXunxXimtlC4tUi1pyW2qibEnBzAmxq2o71/qMJ/kbV3nrRmfbFcExYTVr9QLKxRMrtFLblQHK9OObZE
    N7ROQr9RZrxyZ7mCYM+XZNKsbNGzbNnEZ+LaaebcetbfidHLrs7RvcC2sa63yaOvvYKytXG3t03Cq0POpCvEmhfUigrYjxPVor5x
    pbNvo7hlkcBtaKxkExYSS7pDO7A+OMI3MsJFKrhCMrxHKqpLPrVcQ7xuSqx6U7x/Tb+cRNa4Sdq1ZNm8adbMacvYh9LCncO2qLG3
    vpzBx5fAsYevt265uEe7qkXAqzLVlxvYoh3XlhvYpLpwl7J4lrR7ncR6gKdaEhcUVb5GTKUpK640H6UwIK4yKp08OZxKQJ5VQaJu
    O6GARrB/QrSMQLecTKymSMCzX8C/a7Kseq+rhLWtk56xn52rrIC1uHq0t1+8t0fSqD3Mmi7ZnxfZmwvPnRbdprtyrLB8mrB9pMdo
    bZVUFBcUZLdLTqE1NpMaPJEkMoo1KZUuNY1WKJ1mKZ9tKZd+K4yAPZl9KpyDOqCSPqCWPpmMWZWYY5yUgZulj5Gek5Gzm3Kpo3bC
    pmPCpjvCoSnFphrGshHYrQrLrhPbpMWFs7uEsKl0prVofJZWExQSa5YzYJIgQnwnP4AROX0zKXMuM3lbOIxsNJJqI4iHHnyGG3x9
    K4Z8LoJjKoFuMnxqQoGFWnF5domJiIGlknWinHutr129s1W5pz+6tze4tBS3rQ3HtRe+rQzJwMR1vsF9sa55pLlxko1SExYTeosz
    VnQeTYIbQnYeN3YvMXczKG9NOYB0KICBNIWIH3F/HXNxEmFjJGlRHFNZJ2FlQGptQ2d9U2+Ra3KUeW2ol3elr2Wun2C2t0K9sD2w
    sC7AsxS0uQ3Cwgy4vbhxybZnw7plur1rhIJKEhYRdpcqXnInTGkkSXAaPWQuL3I7RHZkRIt1OXuLMH2NH4OIH2qAH2dcHFleDVBS
    IFBJKlFjP1x5VF+DcWaKiXq0nm+8p17AsFKxu1i4tEuwpz+wsyemwyusuzCxzKdfv65ku7RbwKVTkIo4FxoWeZI1ZXEeUnUnPWsh
    QXM1OnJdPoRpVI1+SpKKPI6cPHeUMn93E2R1FV5kDkdPCk9gLVZnPl2AVWuMbnumh4OrkYC7nXuusHKlp2+srV6hoEmcqj+WrUya
    sz6d269J2qdYx5tKzbBXmng/CA8RiJg5VW42WII0R3s+NHhOT49pTpN3ZZ2IVJqgVKOkU5OXM32SHGt8Cmt5BWRyEUhlM2V7OF2M
    VHiceHunmHyynIjCsYKtqYCxrXGim22UnWGHqGmFm1yDnliE4K1B7aI12K43wKg4q4M1enIxeJhETYVHQoVMOYZeQINfTaVqWZ+L
    cqqdgK+sa6mda6yfP4mmJ3aXGoCJCGB1EWl1G22CSHSdVoKldYSmmIi6tIzCrZeqopubqIugnXx7lHdymoRrjnxpkIVj6KMu55gp
    5poqwps3qqA5mo49Z49SSI5NPpJiQId3Sp2DXqiRaqughsOqhr+vgbekdraiUa6nOo2aF3yVGW2fCm+ZKXKdT3SkaYG9eYbCm5O8
    sZ+xq56vqpmQqaWElKF9kpJnf5xYfqBYiplM8KUU6pwd45cVzZ4op5VBjZNBbplBRolaL51qNZl7TKeMVbuYfseelsqvmc2zlsi2
    gb6+a8CvPKWuKIS0Eo6sG36sJoKrUoCzd4vAmJDOopnNuKbAtq2tr6qWm6x8krVnhLdJfLxIf69CdLVA+44L+JMI5aUIypoarJYz
    kJpAcpNTVpthPpqAMqaHRbmLVsusj9Sxmtm8qtO5sufGm9zPb73BRLe5N5i/GIjEI466M36+QY7TbpHMkZ7PopraxrS9srqsuLOi
    nb95j8JcfsVJdM4yd80uacor/pAJ/ZcA+JoE4I4WupkqkJw6b5NgUphkOKV8MbOPT7+gWsyqicy+rd+6tei6rd3Ep9bKbMvITb2+
    JZq7HZC8HpbNJ4C/SpfNdI7VlqbksaLNv6q6wsOxub+RosVqidVfctlPY9wzbdwib9cV+ZYE95wE8I8P24sXupQulZY7b51WQ5tp
    O6V+Ma+RRrWbZtKikdu9reO/s+q6s+K8qNzBdtO/SLLLIJ3AGJDAF5DALJHGRYrSfJzfnprcvqrSvq7Myrm1vMWMmr9tgNhRdOE+
    a9sqZdYbYd0S
    """
    static let lensByTable = """
    oMg+ocpDortKsahfrJl5vYOLzHuw0GfE1lfSwVXVqmXHmXa0eIyiaZ2MT6F8Np5+L5d+I4xzKHxzKGqGIWeGJFaRGkF7GUR2HTll
    GDZZKDBcJzZUPjJOVDBeajhsfDlwiEZ4kkuEnEiPmUqGpclDoMA9n7VGo69ksJqEx4yUznyz1mO/zWPOxWbWqWTJp3S5epOwcaGQ
    TaFyQqN8NZ16MpSHI4OHLIGMJ2eZL1WOMU6BJEp+GUpyHj9xNURgOkJiQ0NjXUVjbEF2gEp3gEt5jzx+oUiAmlF7qrpZpb5LorVT
    nKhtqY1xwXaUxmSfz1DItE7OrFXJpF+6lHCqgImdY5mCQp50NaZpJI5lI4d4E3l+FGt4Hk98FENqDkFzEzFnFR5lFShSICZLNiRC
    QSVCTydIWxxVYCJPgzlskkRyl0lumkd2o7NhrsFppqNfqqF2z8WnyKa21qDH2ZjTzYXVy5DPyp3WppbFpam9nq6diLOeha+kgLih
    brKfZ5eab4aYb4qcbIiaYXOaXWaWcGiPcm2JeWaEf3F7fWp+jXqLlnSRqYOfkFVqkERkj0VvkUFvraN1p6R2ooZ/saGM6uLy69zn
    3tXc49bd5d3h5d3i4Nvh7OPi5+Xl6ubp6+fp6enj5Obi5Ofk4Obk4OXj3N7k39ve4tzg5N3f4dzg5t3b4tjY4tfW5tjW59TP3s7P
    5uXkoFRlfzJGkkxakUpbtIqWqY2KpISSsISQm26Ih0h3nkuMqUSQpkiYq06bn1idr3WVnJKZsJmTmauTlKR+dJ17Ypl8R4B5QWZ2
    LD9uOjlbPh1bTx5OViVHZCEmbRYneSAegxYXgg4Rcx4nfB0oiSk1fUQ+eTtGezpEsnuwpYOuo3aitoGwiWeKDxMPtm6hl16OnmeJ
    qWaItXqWtZWdxaqc1LaewcOVv7eZsaybnZeSjoyQa2uQY1J4XFZyWzhlfDVQh0NCkEA/szsyuUI9vDoqoDYymUQnm0cuhjI0gDY5
    dEI0eT84sGrCqXi1pnKqsXy5gVyHIBUasFGQi098o157oWh0p3WLtJmA2Kui17yk4rafzcOxy7yVp5+hlYSPgF2Fa1KAYUdaZzVX
    gSVJjSUxsDY6wTEesywexDkZsjkTrTMVi0AkfjgoeTYgdD8TeUAcsV7AvWm/vFy4sWq0g1SEFhQWnlebkkx8i1Rnm293pXN8rph9
    y6KR3K2S6Mmm566xy6iYvouXknWWj1yLf0BvfTlgfytOoSY/tC0v0jcp1kIdzD4QxzYWui0WsEAOlDoRezUfZUAQXDYaZjQdvV60
    wV/At2DDulW9jlyFGRcWoXGEhWhzfmlginhenIZzpZOBwJ6H3rCW47Oo2J6k2ZujtIuXqn6RkmdrgkFyjkdilS1Eoi1CuTM72i4t
    6EIl6TUUzjMJs0UapUYSiUQecEIcXUgPZkUYY1MTtFast0mltFiful6zk0uIFRcVlHSDe4Jgg4ZXd41sgIRdkJpuoo55q5iVvZ2U
    u4GPvYaLtHB6uWV/rV1kmUxmojtXsi9AvCowyTsnz0Eg0kkr208Sykwft1ATnVIWjVkjcVoZXVskUGsiW2wexFWew1aPvliLwW+e
    iFR6FBkWh4iDhJJgco9gdZ9egJhcg5Nwe49uj3V/mm+KoGmJrV98sVxsr05moVBgqkVYvklQtTk3wDQ/1Do010Uh00MtvDwkvlwX
    o1QnilYqdGYoZHcoZn4rS30yRXgxt154v2J3sWOBvWhummZpFRgVkpRtfJNba5thbJ9lXp9kW5licIR3Y2V9bmNydlt6lVJulktv
    rThft01Tr0VJyUE9x0s21UozzEc0xEEjy1QmrlIwq1Yki2s0gGo4eoItW4Y1XJE2SIZESIhBxFpov1tkvVthv4NoiXhkFhgUk7No
    dLNmYrdiZKJsSJxqSIx1SmlmQl9lUzxvUDFvby5RejtbpTxZtTE/wE44xD033EZDyz05wEoywlI3slc9pGUuiF85jng8a3dIXoRE
    XZk+WJRTRKVSU51Tym1GwmxJtGU3uIdIonhRFBgWlrFscbhdbcNvWLtdVJhgM4dxKHZvL09gOj1gSShaXCZUgyJKni5Qqzg/xT5F
    4Fky3Es22lE/zlM8tVc3nFs4kHc+fYE3gIxRcYdIYJZeX5BiVJVUW6FhWKNs0nI01nYx0HYuxX9KlHNAFhgWnK9YccJVdr5kXa9j
    RpliM45WNGpmI1pfNDFPNypGZDBMfy9QlT9GtVE64Fs+51U86Wsz4Vw1w14otHMknGw5l4E8iY8+e5BDbIlbdZtTYqNvapt3WaFp
    Xp143HY14HoyyW4uxoQ0ooItFBYWlqVFgrRPbrhTVa9QQ55PSJBRL3hSO1ViMk1TSjJIZThNfEVEqj9RvFE74lxG2Wg23Ho41YY1
    u3kiq5EtoJIvnJo3k5Q4eoxNjpFefpFeco9saoyIgY97enyG1Xgk3IY1y3k12I8wtIQyFRYUpZs2hpxKd51SXKJNYpJUSX9MQnBW
    S2RgUmhhW2debmVmkWZMslZZzG1Gx25A3W8/0X0y3Iw60JcrwKYfs5kfn6I2jpM8lpVIno9gkINxl3xxj2ORg2mIjV+E5IMx6oMq
    5Hwp2YI1rHwyFRQUrYoyg4g/e4U9c5M4X5NBXYZHYotYdIBXcYhpdINnioRylHhrtIdgvXxhwX9Y3JFK2Y0206QzzKAbwrMfrKwm
    p7Qhpa04pI5EoYFNoGB5p2V6rliQnlKLqlGP8Ikv7Zsx6I4u2Y8qu4IkFBUUpookhW8fhnclbYAteHo3foxHfIRjio1ni5l0qaNv
    qKdvuZh6uZ5oxpNnzY1Z1I1Vzqw+yrYuwb8isMQctcESubQTtK0zvpw4sHdWwl9xuUiBrimJxSaiuSyd6ZA26J434I016JU9tXk7
    FBUTqnsij2EliGsme2k6im46f4RTmodpnKZuq7t6sbJ8vrF+t7SIxKZwsKN1uJdisJhVwLA+xMUrutQfv9YjudAcwcMmvbEsuYc9
    ymdVz0Rl1yl7yBOW1w6d3QyQ96RA855I46lK35A0sn0tFRMTr2kfiVciglEpb1IqiFg7mHdIoZBfsZ14vbWPzruO0MmC0smFuqd9
    sp58o65ssp1LpalDs8M9uMUetc8dvN0iu9IczaIpw3453m1b1UJr3yBy3hJ+2gaV5AeZ+6xK7qZO9KNX561Ow4FBExMToVMlfUQd
    fTgbdjQwiEY/lGZTtohyvKV33LOE2s2UzL6Yw8aCvriBs6d0oalimZ9Fk7A5kbY7o9c2n84sqtEqubgqxaMy1H4442ZV3jBr3hpv
    +AGA7AeE7wJ+/sNa/Lpe9K1h2aNbtYxYFBITolQ+fTMudDU2bTM0fUg7mVZkrXZ+yJWU7Kaf6cGT0bqS1rh/raZ5qJ5zkYpihZdB
    kKFHh7g4n7U4ocMtp786rrswuZw50H434FhD3jtf7RRl8ABY9QBs9ABt/857/8J68rtn4KZlu35aExITnkhCey02ahIqZyA5gCdM
    mFFpwl544I2N7aKh7LGu4aeiyrWSpJZzkYpjkJJFgohRcZczfJxIjq4+lK46ra1LsaxNx5ZEy4A71VRG5zg86RhS5wNV+ABD/wBU
    6dyP79KG5MJ61K6FsopgEhEUgUdHajc7ah1HXBdIgi1Zj0NxrGZ60HyY7JSk3Z6i1JygxaaKoZ15goRbg3xLeIE3a304c5NOgJVO
    mrBLoqlar6BUvY5VyHRO2VJJ3UE/8CJF9gwz+Qw27wE+7eOX5OCH4MaRzMGSoZRlExEUgU9cajpAUR0+UBtRaxxljENwq2SExWub
    6Zqr6qWq052rtaCbloZ+gX1pbndOWodTZpBKcJBYb5NNfZVXo5ZdoJdfv31jyGZJ005P3zBD7ig94Rwz8wIt6RQt7OSf3+Cf0MSc
    18aHmp56ExETb1VaYERNTRxRSiZaViJXfD14olOCy4KW146l4KCiyaSfp6afipaJfIZsY4BiZYdaZJRmZYhZeqNskaJynI1/pJZz
    soFywltowFVa3TBO5SI85hks6wY26Qw22dKl2uig1NiXur+boJh5EhMUd3hnVFJPQDpOQT1ZXDlTbVlojm99q4ySvJ+ivqyrxa2t
    n6SdgZ+Ka5uEX5SAZ5Rua5RucZ9/eaWJiamPlaOMrYSBrnN8vHBxyk9s0S9ZyiZLzhxL2gpO3A1S1NiTxdGcwNGQucuDg6d6FBMT
    Z4RdOGNKMGdUPlhHU2VnZXFcfnV4noyRvJ2Zwbaat6uWobCphMGVdbKVYLCZXrSPb7Wcc6idlbuho6ybpZ+UsYmWvIKGyWmGvlp4
    uT5quh5pxx9myyBmxw9hv8OPxMuBqsiOqLqCjKZ3EhQUXJFqO3dLMHtWLXVPSotMUIpaeYt2fqt7orB9n7SbnsSUmrqwdsCgddGq
    a9a2c9a8fMa4jbuunsKvoracu6OSuZOVuYaVtWWHwE2NwTOEuS2EuRR8uRKEwxSFscqBvcqGqcp7m8hydKVlExQVUqVrLadVNo5K
    MZlJQqdRU6FVYaBVdrBgi7mBhMGQiMiViNCqdtzBa9PBetzEb9rPedPEls7PosOvsci7sqmpx6aozH2cs3GlvFuZqTeYoCyupSaj
    oSCuoxSjqceAqLyDmK53k8B1c6BmEhcUSsBdNqVGMbU/H60+IbpJN6xUR6tOabhnZrRxgs17esaRgteeeN/DY/DLcOzedPPkftrg
    kOPPm9a7qc+ux6irz5+szXunxXimtlG4tUi1qCW2qibDnR2/mxq2pL1/p8J/kbN2n7dneatZExYTV8JRLKxRM7tFLLhQG69NOLVF
    N7ROQ79SZrxyZ7mCYM+XZNKsbNGzbNnEZ+LaaebcetbfidHLrs7RvcG2sa63yKSuvYKytXG3t03CrETOpCvDmhfTiwrYkBTUo71x
    prRvobdkkcJtZadiFBgSTL5FOa8+OMI3MsJFKrdCM71HKqtMPrZcRLxvSqx6U7x/Tb+cRNa4Sdq1ZNm8adbMacvZh9LDnsO3qrK3
    vp3Ax5fAsYevt3C5uEe7qkW/qzLVlxzYoR3XlxvYo7lwl7J4lrR6ncZ6eJtVERkVVsJGSqQoK680HqYwIK4yKp08OZxKQJ9VQqJv
    O6KAR7F/QrSMQbmeTK2nSMG0YMHAa7Oteq+rhLWtk56xoJ6srYG1uXq0uGC7t0fSqT7Mmi/ZnxfZnAzPnBbcp7tyqrB9mbB9pMpp
    apBRFRkUZbtNTKA0NpMaO5ElMYs0KpYvNo5WKJ1lKZ9uKZd+K4yAPZl9KpyDOqCSPqCWPZqLWZWYZJ2VgZylj5Gek5Kzm3KponXB
    pmPCpj3CoCnGpRvHshLYrArLrhLapMSEtLmErqhyprhnd5FUFBYSbJs0X5MgQXwmP4EROH00KXQuM3lcN41rNJNqIoeIHnyGHH19
    K4h8LoNkK4JvMnxqQoGGW3J5d4mKiIKkk3WinHutrl69s1W5pz+6tje5tBS3rQzItRe+rQ3JvsV3vcB+r6x4pblxiYNNFBcTe40z
    VXQcTYMbQXYeN3cvMXYzKG9OOYB0KYCANISIH3F/HHNxE2JkJGlRHFNZJ2JmQGttQ2d9U3CQa3OUeW2nlnilr2WuoGC2t0G9sT2w
    sC6/shS2uQ3CwQu5vrlwyrdowLlnu79sgHxIExgReJkrW3AnTGojSXAbPWQuL3M6Q3ZjQ4t1OHuLMH2MH4OIH2p/H2dcHFleDlFS
    IVBJK1FjP1x5VF+EcWWJh3mznm+7p1+/r1KyvFe4tEmwp0CxsyenwyeuvC+xyqdiv7Bku7NbwadTioU3GR4XeZQ0ZHAeUXUnPWsh
    QXI1OXFbP4RqVI1+SZGJO42cO3eTMn93FGR0FV1jDkdOCk9fLFVmPlx+VWqLbnqkhoOrkoC7nXqvsXClqG+sr16joEmcqj6Xr0ua
    sz6d265M16dZw5tL0LFYjG46CRERiZk6VWwzWIIzR3o8NXhNT41qTZJ3ZZ2JU5qfU6KkUY+XM32QG2p7Cmp3BmJwEEhlNGR6OF2M
    VHecdnuolnyxm4jBsIKsqYCxrHGinW2WnWCJqGiFnFyFnlaF4a1B7aM31a44wak6p341cWwveJlETYNHQ4VMOoZcP4NeTaVqWZ+K
    cqqdfq2saqidaaufPoemJnaVGX+IB2F1EmdzHG2BSHSdVoKldIOlmYe6s4vDrpaqopmdqYuhnnt+lHZznINtkHpqj4Jl56Iv6Jkp
    5J0rvpw3q584mo8/Zo9SSI9MPpFiQIZ3S52BXaiPaqqghcKqhr6vf7ajdLWiUKynOYuaF3yTGGucCm+XJnGbT3SkaIG8eIbAmZK8
    sZ+xq5+vqpqQqqSFlp99kpBpgZpZfp5Zi5lN76UX6poe45UYy54sppVCi5JAa5dDRYlaMJ1pN5h7TKeNV7qZfsWflsqvl8yylMe1
    f728asCuPKStJoOyE42sGnysJ4GrU3+ydorAl4/PoZjMt6bAtquur6iWnat8krVqhbVMfLpJfq5EdrJB+48L9pUI4qUJyJkcqpU2
    jppCcZVQVJphPJp/MqaFRriLVsuqj9Svmde7qtO5sebFmtrPb73AQ7a5Npa/F4nCJI25Mn+9Qo7SbpLLkp3OoZraxbK/s7qst7Oi
    nr17j8FcfsVIdc0zeMsvaskt/o0J/ZYA9poF3I8Yt5oqjps7bpJhUppkOKR+MrOPT8CfW8yti82+rd+6tOa6rt/FptfLa8nITb29
    J5q7Ho6/H5bMKH/AR5fOc47Vk6XisKHOwKu5wMKxur6UpMVritRgc9hRZNszbdwib9YX+ZkE95wE8Y4N24sYuJQuk5g8a5xYQ5pp
    OKd9MLGRSLacZdKjj9m9r+K+s+u6suC9qNrCc9LASLPKIJ2/GJG/F5HBKpDFR4zQfJrdnpvdvarRvazKyru1vMaMm79tgtdTdOI/
    at0tZtYcY90S
    """
    /// Corners on a photograph 6048 × 8064 as taken; where they are on it
    /// straightened (`lens.moved`: by the number, by the table), and, set
    /// on it straightened, where they are on it as taken (`lens.bent`).
    static let lensCorners: [[Double]] = [[0.08, 0.1], [0.93, 0.07], [0.95, 0.92], [0.06, 0.9]]
    static let lensMoved: [[[Double]]] = [[[0.07328, 0.0936], [0.93772, 0.06228], [0.95812, 0.92757], [0.05268, 0.90665]], [[0.0722, 0.09299], [0.93804, 0.06196], [0.95905, 0.92893], [0.05095, 0.90825]]]
    static let lensBent: [[[Double]]] = [[[0.08641, 0.10611], [0.92269, 0.07731], [0.94231, 0.91282], [0.06697, 0.89367]], [[0.08742, 0.10667], [0.92238, 0.07762], [0.94145, 0.91156], [0.06856, 0.8922]]]

    /// The lens's bend is taken out on the phone as the server takes it
    /// out (Mateusz 2026-11-19 09:52 UTC: "prostowanie obiektywu. Czy tego
    /// także nie lepiej robić na iPhone? … telefon i tak pewnie zrobi to
    /// szybciej"): the picture pixel for pixel (a level apart at the most,
    /// should a processor's sine end otherwise), and the corners where
    /// the server would put them, both ways.
    func testALensBendIsTakenOutAsTheServerTakesItOut() throws {
        let pixels = try Self.held(Self.lensPicture)
        XCTAssertEqual(pixels.count, 48 * 36 * 3)
        let bends = [OwnBend(k1: Self.lensNumber), OwnBend(table: Self.lensTable, centre: Self.lensCentre)]
        let wanted = try [Self.held(Self.lensByNumber), Self.held(Self.lensByTable)]
        let folder = try folder()
        for (n, bend) in bends.enumerated() {
            let want = [UInt8](wanted[n])
            let picture = folder.appendingPathComponent("lens\(n).npy")
            try (ScanPicture.head(rows: 48, columns: 36) + pixels).write(to: picture)
            try ScanCore.straight(picture, by: bend)
            let made = try Data(contentsOf: picture)
            let shape = try XCTUnwrap(ScanPicture.shape(of: made))
            XCTAssertEqual(shape.rows, 48)
            XCTAssertEqual(shape.columns, 36)
            let got = [UInt8](made.suffix(from: made.startIndex + shape.from))
            XCTAssertEqual(got.count, want.count)
            let apart = zip(got, want).map { abs(Int($0.0) - Int($0.1)) }
            XCTAssertLessThanOrEqual(apart.max() ?? 0, 1, "bend \(n)")
            XCTAssertLessThanOrEqual(apart.filter { $0 > 0 }.count, got.count / 100, "bend \(n)")
            XCTAssertNotEqual(got, [UInt8](pixels))

            // What he is shown (the picture's bytes, no file): the same.
            var shown = [UInt8](pixels)
            try ScanCore.straight(&shown, rows: 48, columns: 36, by: bend)
            XCTAssertEqual(shown, got)

            // Corners on the photograph as taken to where they are on it
            // straightened, and the other way.
            let moved = try ScanCore.moved(Self.lensCorners, columns: 6048, rows: 8064, by: bend)
            let back = try ScanCore.moved(Self.lensCorners, columns: 6048, rows: 8064, by: bend, back: true)
            for (mine, theirs) in zip(moved + back, Self.lensMoved[n] + Self.lensBent[n]) {
                XCTAssertEqual(mine[0], theirs[0], accuracy: 1e-9, "bend \(n)")
                XCTAssertEqual(mine[1], theirs[1], accuracy: 1e-9, "bend \(n)")
            }
            // A barrel: straightened, a corner lies further out.
            XCTAssertLessThan(moved[0][0], Self.lensCorners[0][0])
            XCTAssertGreaterThan(back[0][0], Self.lensCorners[0][0])
            // There and back is where it was.
            let again = try ScanCore.moved(moved, columns: 6048, rows: 8064, by: bend, back: true)
            for (mine, was) in zip(again, Self.lensCorners) {
                XCTAssertEqual(mine[0], was[0], accuracy: 3e-5)
                XCTAssertEqual(mine[1], was[1], accuracy: 3e-5)
            }
        }
        // No picture, bytes that are not the picture said, a table of one
        // value: nothing is made of them.
        XCTAssertThrowsError(try ScanCore.straight(folder.appendingPathComponent("none.npy"), by: bends[0]))
        var short = [UInt8](repeating: 0, count: 10)
        XCTAssertThrowsError(try ScanCore.straight(&short, rows: 48, columns: 36, by: bends[0]))
        var whole = [UInt8](pixels)
        XCTAssertThrowsError(try ScanCore.straight(&whole, rows: 48, columns: 36, by: OwnBend(table: [0.01])))
        XCTAssertThrowsError(try ScanCore.moved([[0.1]], columns: 6048, rows: 8064, by: bends[0]))
    }

    /// The scan the phone made is sent without its lens's bend, with what
    /// it was taken out by: the server then keeps the work as it came.
    /// Where nothing was taken off no picture goes, and no word of it.
    func testTheServerIsToldWhatAScanWasStraightenedBy() throws {
        let wall = try XCTUnwrap(PhoneScan.jpeg(of: Self.picture(rows: 320, columns: 240) { _, _, _ in 128 }))
        let read = try PhoneScan.read(first: wall, sides: [wall, wall], into: folder().appendingPathComponent("scan"))
        let corners = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
        let bend = OwnBend(k1: Self.lensNumber)
        func told(_ made: PhoneScan.Made) throws -> [String: Any] {
            try XCTUnwrap(JSONSerialization.jsonObject(
                with: PhoneScan.told(made, trace: [:], heat: (.nominal, .nominal))
            ) as? [String: Any])
        }
        let made = try PhoneScan.make(read, corners: corners, straight: bend)
        XCTAssertNil(made.picture)
        XCTAssertNil(made.straight)
        let bare = try told(made)
        XCTAssertNil(bare["straight"])

        var cleaned = made
        cleaned.note.used = 2
        cleaned.note.removed = 0.0412
        cleaned.picture = wall
        cleaned.straight = bend
        cleaned.straightened = 0.614
        var note = try told(cleaned)
        var said = try XCTUnwrap(note["straight"] as? [String: Any])
        // (Foundation writes and reads some numbers a last digit off:
        // -0.026 came back -0.026000000000000002. The server takes a
        // bend for its own within far more, `LensBend.same`.)
        XCTAssertEqual(try XCTUnwrap(said["k1"] as? Double), Self.lensNumber, accuracy: 1e-12)
        XCTAssertEqual((said["table"] as? [Double])?.count, 0)
        XCTAssertEqual(said["centre"] as? [Double], [0.5, 0.5])
        let phone = try XCTUnwrap(note["phone"] as? [String: Any])
        XCTAssertEqual(try XCTUnwrap(phone["straight"] as? Double), 0.61, accuracy: 1e-9)
        XCTAssertLessThanOrEqual(phone.count, 32)  // the most the server takes

        cleaned.straight = OwnBend(table: Self.lensTable, centre: Self.lensCentre)
        note = try told(cleaned)
        said = try XCTUnwrap(note["straight"] as? [String: Any])
        let table = try XCTUnwrap(said["table"] as? [Double])
        let centre = try XCTUnwrap(said["centre"] as? [Double])
        XCTAssertEqual(table.count, Self.lensTable.count)
        for (told, was) in zip(table, Self.lensTable) { XCTAssertEqual(told, was, accuracy: 1e-12) }
        XCTAssertEqual(centre.count, 2)
        for (told, was) in zip(centre, Self.lensCentre) { XCTAssertEqual(told, was, accuracy: 1e-12) }
        XCTAssertEqual(said["k1"] as? Double, 0)
        // A scan as the photographs were taken says nothing of it.
        cleaned.straight = nil
        note = try told(cleaned)
        XCTAssertNil(note["straight"])
        XCTAssertNil((note["phone"] as? [String: Any])?["straight"])
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
        // How this app's core merges: the server makes a scan merged as
        // it no longer merges again.
        XCTAssertEqual(note["merging"] as? Int, PhoneScan.merging)
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
