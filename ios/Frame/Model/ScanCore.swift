import CoreGraphics
import Foundation
import FrameScan
import ImageIO
import UniformTypeIdentifiers

/// The scan of three merged on the phone: the server's merge
/// (`imaging/reflections.py`) written once more in C++ on the same OpenCV
/// (`core/scan`, linked as `libframescan`, `scripts/build-scan.sh`).
///
/// Mateusz 2026-11-18 23:34 UTC: "przyspieszyć składanie obrazów … Może
/// iPhone mógłby wykonywać część pracy znacznie szybciej niż serwer?". First
/// a trial (2026-11-19 00:12 UTC, "Najpierw próba na iPhonie": Konfiguracja →
/// Diagnostyka merges his kept scans with it, to be timed and compared with
/// the server's, `ScanTrial`), then the scans he takes (07:42 UTC, "Tak,
/// składaj na iPhonie": `PhoneScan`).
enum ScanCore {
    /// What a merge came to, and the seconds each part of it took, by the
    /// names the server's log gives them ("laid", "own", "layer"…).
    struct Note: Equatable, Sendable {
        var used: Int
        var removed: Double
        var doubt: Bool
        var took: [String: Double]

        /// All of it: the files read, the merge, the file written.
        var seconds: Double { took.values.reduce(0, +) }
    }

    struct Failed: LocalizedError {
        let told: String
        var errorDescription: String? { "Składanie na iPhonie nie powiodło się: \(told)" }
    }

    /// What the core was built of ("OpenCV 5.0.0, 6 thread(s) of 6 core(s)").
    static var built: String { String(cString: frame_scan_built()) }

    /// `first` without the reflections `sides` do not share, within the
    /// work's `corners` on it (x and y of its top left, top right, bottom
    /// right and bottom left, 0–1), written to `into`. All of them `.npy`
    /// files of rows × columns × RGB. `anyway`: also of photographs that
    /// show no one flat work, as the server makes the scan he chooses from.
    /// Seconds of all the phone's cores: never on the main thread.
    static func merge(first: URL, sides: [URL], corners: [Double], anyway: Bool, into: URL) throws -> Note {
        guard corners.count == 8 else { throw Failed(told: "the work's four corners are not given") }
        var note = frame_scan_note()
        var error = [CChar](repeating: 0, count: 512)
        let size = Int32(error.count)
        let paths: [UnsafeMutablePointer<CChar>?] = sides.map { strdup($0.path) }
        defer { paths.forEach { free($0) } }
        let given: [UnsafePointer<CChar>?] = paths.map { UnsafePointer($0) }
        let status = given.withUnsafeBufferPointer { sides in
            frame_scan_merge_files(
                first.path, sides.baseAddress, Int32(sides.count), corners, anyway ? 1 : 0, into.path,
                &note, &error, size
            )
        }
        guard status == 0 else { throw Failed(told: told(error)) }
        return Note(note)
    }

    /// A scene made up (a work under glass with a lamp in it, photographed
    /// three times), `side` pixels long, merged: nothing read or written.
    /// For a test of the core as it is linked into the app.
    static func madeUp(side: Int) throws -> Note {
        var note = frame_scan_note()
        var error = [CChar](repeating: 0, count: 512)
        let size = Int32(error.count)
        guard frame_scan_made_up(Int32(side), &note, &error, size) == 0 else {
            throw Failed(told: told(error))
        }
        return Note(note)
    }

    private static func told(_ error: [CChar]) -> String {
        String(decoding: error.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }, as: UTF8.self)
    }
}

private extension ScanCore.Note {
    init(_ note: frame_scan_note) {
        self.init(
            used: Int(note.used),
            removed: note.removed,
            doubt: note.doubt != 0,
            took: [
                "read": note.read, "laid": note.laid, "own": note.own, "layer": note.layer,
                "mended": note.mended, "whole": note.whole, "written": note.written,
            ]
        )
    }
}

/// A picture as the core reads and writes it: a NumPy `.npy` file of rows ×
/// columns × RGB, a byte each.
enum ScanPicture {
    /// The head of such a file, as NumPy writes it (version 1.0).
    static func head(rows: Int, columns: Int) -> Data {
        var head = "{'descr': '|u1', 'fortran_order': False, 'shape': (\(rows), \(columns), 3), }"
        head += String(repeating: " ", count: (64 - (10 + head.utf8.count + 1) % 64) % 64) + "\n"
        var data = Data([0x93, 0x4E, 0x55, 0x4D, 0x50, 0x59, 1, 0])  // "\x93NUMPY", version 1.0
        data.append(contentsOf: [UInt8(head.utf8.count & 0xFF), UInt8(head.utf8.count >> 8)])
        data.append(Data(head.utf8))
        return data
    }

    /// The picture's rows and columns, and where its bytes begin.
    static func shape(of npy: Data) -> (rows: Int, columns: Int, from: Int)? {
        let magic: [UInt8] = [0x93, 0x4E, 0x55, 0x4D, 0x50, 0x59, 1, 0]  // "\x93NUMPY", version 1.0
        guard npy.count > 10, npy.prefix(8).elementsEqual(magic) else { return nil }
        let base = npy.startIndex
        let from = 10 + Int(npy[base + 8]) + Int(npy[base + 9]) << 8
        guard npy.count >= from else { return nil }
        let head = String(decoding: npy[(base + 10) ..< (base + from)], as: UTF8.self)
        guard let found = head.firstMatch(of: #/\((\d+), *(\d+), *3\)/#),
              let rows = Int(found.1), let columns = Int(found.2),
              rows > 0, columns > 0, npy.count == from + rows * columns * 3
        else { return nil }
        return (rows, columns, from)
    }

    /// Seconds the phone takes to write the picture as the JPEG the server
    /// keeps of a scan (quality 95) and to read that JPEG back whole: what
    /// the phone would spend besides the merge, were it to make the scan of
    /// its own photographs. nil when the picture is none.
    static func jpegSeconds(of npy: Data) -> (written: Double, read: Double, bytes: Int)? {
        guard let (rows, columns, from) = shape(of: npy) else { return nil }
        let pixels = npy.subdata(in: (npy.startIndex + from) ..< npy.endIndex)
        let colours = CGColorSpaceCreateDeviceRGB()
        guard let provider = CGDataProvider(data: pixels as CFData),
              let image = CGImage(
                  width: columns, height: rows, bitsPerComponent: 8, bitsPerPixel: 24, bytesPerRow: columns * 3,
                  space: colours, bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.none.rawValue),
                  provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent
              )
        else { return nil }
        let jpeg = NSMutableData()
        var began = ProcessInfo.processInfo.systemUptime
        guard let destination = CGImageDestinationCreateWithData(
            jpeg as CFMutableData, UTType.jpeg.identifier as CFString, 1, nil
        ) else { return nil }
        CGImageDestinationAddImage(
            destination, image, [kCGImageDestinationLossyCompressionQuality: 0.95] as CFDictionary
        )
        guard CGImageDestinationFinalize(destination) else { return nil }
        let written = ProcessInfo.processInfo.systemUptime - began

        began = ProcessInfo.processInfo.systemUptime
        guard let source = CGImageSourceCreateWithData(jpeg as CFData, nil),
              let back = CGImageSourceCreateImageAtIndex(source, 0, [kCGImageSourceShouldCache: false] as CFDictionary),
              let context = CGContext(
                  data: nil, width: back.width, height: back.height, bitsPerComponent: 8, bytesPerRow: 0,
                  space: colours, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
              )
        else { return nil }
        context.draw(back, in: CGRect(x: 0, y: 0, width: back.width, height: back.height))
        let read = ProcessInfo.processInfo.systemUptime - began
        return (written, read, jpeg.length)
    }
}
