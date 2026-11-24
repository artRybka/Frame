import XCTest
@testable import Frame

/// The museum photographs cut on the phone (`MuseumCrop`; Mateusz
/// 2026-11-20): the core finds the work in a made-up photograph from
/// made-up masks as the server's `imaging/crop_model.find` does (the
/// numbers below are its, held by `server/tests/test_scan_core.py`), and the
/// model in the app answers about a photograph.
final class MuseumCropTests: XCTestCase {
    /// What `crop_model.find` finds in the made-up photograph.
    static let sure = 0.95
    static let verdict = "cut"
    static let work: [[Double]] = [[0.20133, 0.21007], [0.79534, 0.20912], [0.79534, 0.78583], [0.20133, 0.78583]]
    static let surround: [[Double]] = [[0.13333, 0.125], [0.86333, 0.125], [0.86333, 0.87083], [0.13333, 0.87083]]

    /// What `crop_model.plate` makes of the made-up print's sheet.
    static let printSheet: [[Double]] = [[0.1, 0.08333333333333333], [0.9, 0.08333333333333333], [0.9, 0.9166666666666666], [0.1, 0.9166666666666666]]
    static let printCut: [[Double]] = [[0.30217, 0.25271], [0.69605, 0.25271], [0.69605, 0.74507], [0.30217, 0.74507]]
    static let printPlate: [[Double]] = [[0.32933, 0.28667], [0.66889, 0.28667], [0.66889, 0.71111], [0.32933, 0.71111]]

    /// A sheet of paper on a dark board, an etching's lines on it: 300 × 240.
    static func print() -> MuseumCrop.Pixels {
        let rows = 240, columns = 300
        var photo = [UInt8](repeating: 50, count: rows * columns * 3)
        for y in 20 ..< 220 {
            for x in 30 ..< 270 {
                photo[(y * columns + x) * 3] = 236
                photo[(y * columns + x) * 3 + 1] = 230
                photo[(y * columns + x) * 3 + 2] = 216
            }
        }
        for y in 70 ..< 170 {
            for x in 100 ..< 200 where (x * 3 + y * 7) % 19 < 8 {
                photo[(y * columns + x) * 3] = 70
                photo[(y * columns + x) * 3 + 1] = 60
                photo[(y * columns + x) * 3 + 2] = 50
            }
        }
        return MuseumCrop.Pixels(rows: rows, columns: columns, rgb: photo)
    }

    /// A grey wall, a frame on it, a painting of stripes in the frame:
    /// 300 × 240.
    static func photo() -> MuseumCrop.Pixels {
        let rows = 240, columns = 300
        var photo = [UInt8](repeating: 120, count: rows * columns * 3)
        for y in 30 ..< 210 {
            for x in 40 ..< 260 {
                photo[(y * columns + x) * 3] = 200
                photo[(y * columns + x) * 3 + 1] = 160
                photo[(y * columns + x) * 3 + 2] = 60
            }
        }
        for y in 50 ..< 190 {
            for x in 60 ..< 240 {
                photo[(y * columns + x) * 3] = UInt8((x * 7 + y * 13) % 60 + 30)
                photo[(y * columns + x) * 3 + 1] = UInt8((x * 3 + y * 5) % 40 + 20)
                photo[(y * columns + x) * 3 + 2] = UInt8((x + y * 11) % 80 + 90)
            }
        }
        return MuseumCrop.Pixels(rows: rows, columns: columns, rgb: photo)
    }

    /// The masks a model sure of the painting and its frame would give.
    static func logits() -> [Float] {
        let side = MuseumCrop.side
        var logits = [Float](repeating: -8, count: 2 * side * side)
        for y in 102 ..< 281 {
            for x in 77 ..< 307 { logits[(y * side + x)] = 8 }
        }
        for y in 76 ..< 307 {
            for x in 51 ..< 333 { logits[side * side + y * side + x] = 8 }
        }
        return logits
    }

    private func near(_ mine: [[Double]]?, _ theirs: [[Double]], file: StaticString = #filePath, line: UInt = #line) {
        guard let mine else { return XCTFail("no corners", file: file, line: line) }
        for (a, b) in zip(mine.joined(), theirs.joined()) {
            XCTAssertEqual(a, b, accuracy: 2e-5, file: file, line: line)
        }
    }

    func testTheWorkIsFoundAsTheServerFindsIt() throws {
        let found = try MuseumCrop.find(Self.photo(), logits: Self.logits(), sure: Self.sure)
        XCTAssertEqual(found.verdict, Self.verdict)
        near(found.work, Self.work)
        near(found.surround, Self.surround)
        // Not sure enough: left whole for him; sure it wants none: whole.
        XCTAssertEqual(try MuseumCrop.find(Self.photo(), logits: Self.logits(), sure: 0.5).verdict, "unsure")
        XCTAssertEqual(try MuseumCrop.find(Self.photo(), logits: Self.logits(), sure: 0.05).verdict, "whole")
    }

    /// A print's wide sheet cut down round its impression as the server
    /// cuts it (Mateusz 2026-11-24); the sheet of a painting's photograph
    /// (no paper round anything) stays.
    func testAPrintsWideSheetIsCutRoundItsImpression() throws {
        let made = try XCTUnwrap(MuseumCrop.plate(Self.print(), sheet: Self.printSheet))
        near(made.cut, Self.printCut)
        near(made.plate, Self.printPlate)
        XCTAssertNil(try MuseumCrop.plate(Self.photo(), sheet: Self.work))
    }

    func testThePhotographIsLetterboxedForTheModel() throws {
        let boxed = try MuseumCrop.letterbox(Self.photo())
        let side = MuseumCrop.side
        XCTAssertEqual(boxed.count, 3 * side * side)
        // 300 × 240 into 384: 384 × 307, 38 rows of black above.
        XCTAssertEqual(boxed[10 * side + 100], 0)
        XCTAssertEqual(boxed[200 * side + 5], 120, accuracy: 0.5)
    }

    /// The model in the app answers: two masks of its square and how
    /// sure it is, and the work it finds lies within the frame.
    func testTheModelInTheAppAnswers() throws {
        let photo = Self.photo()
        let (logits, sure) = try MuseumCrop.ask(photo, kind: 0)
        XCTAssertEqual(logits.count, 2 * MuseumCrop.side * MuseumCrop.side)
        XCTAssertTrue((0 ... 1).contains(sure))
        XCTAssertTrue(logits.allSatisfy(\.isFinite))
        _ = try MuseumCrop.find(photo, logits: logits, sure: sure)
    }
}
