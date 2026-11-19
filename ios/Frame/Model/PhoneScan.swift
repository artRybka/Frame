import Accelerate
import CoreGraphics
import Foundation
import ImageIO
import os
import UIKit
import UniformTypeIdentifiers

/// The scan of three made by the phone itself, of its camera's own
/// photographs (Mateusz 2026-11-19 07:42 UTC, after the trial in
/// Diagnostyka: "Tak, składaj na iPhonie": some 4 s here against 34 s on
/// his NAS). The server's merge (`imaging/reflections.py`) in C++
/// (`ScanCore`), given the photographs as the server would read its own
/// copies of them, and the picture it makes sent to the server to be kept
/// in the first photograph's place (`FrameBackend.sendOwnScan`).
///
/// The server still makes the scan where the phone cannot: a colour chart
/// set the photographs' colours there, no corners of the work are known,
/// the phone has too little memory to spare, or anything of this fails.
enum PhoneScan {
    // What the server goes by: keep in step with it.
    /// `reflections.MATCH_SIDE`: a side photograph is read as small as its
    /// JPEG gives it with neither side under this.
    static let matchSide = 2400
    /// `own_works.SIDE_ANGLE`: of the photographs from one side, the one
    /// nearest this many degrees off is the one used.
    static let sideAngle = 30.0
    /// `reflections.AROUND`: so much of the work's size around its corners
    /// is cleaned too.
    static let around = 0.015
    /// `cut.LEAST_KEPT` and `cut.SQUARE`: the least of the photograph four
    /// corners may hold, and how far from square each may be (degrees).
    static let leastKept = 0.15
    static let square = 16.0
    /// The server keeps a scan as a JPEG of this quality.
    static let quality = 0.95
    /// The most the merge holds for each pixel of the first photograph
    /// (1.6 GB of 48 MP, measured on a Mac), and a third more: with less
    /// to spare the server makes the scan.
    static let bytesPerPixel = 44

    struct Failed: LocalizedError {
        let told: String
        var errorDescription: String? { "Składanie na iPhonie nie powiodło się: \(told)" }
    }

    /// The photographs as the merge reads them, kept while he sets the
    /// corners: beyond what was cleaned, the scan is made of them again.
    struct Read: Sendable {
        var folder: URL
        var first: URL
        var sides: [URL]
        var rows: Int
        var columns: Int
        /// Seconds the files took to become pictures.
        var seconds: Double
    }

    /// What the phone made of a scan.
    struct Made: Sendable {
        /// The work's corners the merge had.
        var corners: [[Double]]
        var note: ScanCore.Note
        /// The first photograph without its reflections, as the server
        /// keeps it (a plain JPEG); nil where nothing was taken off.
        var picture: Data?
        /// Seconds: the files `read`, the merge itself, the JPEG `written`.
        var read: Double
        var written: Double
    }

    // MARK: Which photographs

    /// Which of a scan's side photographs it is made of (their places, in
    /// order), by the angle the phone gave each: the one nearest
    /// `sideAngle` of those from the left and of those from the right; all
    /// of them when one has no angle. As `OwnWorks.chosen` on the server,
    /// which is told the angles to a tenth of a degree.
    static func chosen(angles: [Double?]) -> [Int] {
        var best: [Bool: (off: Double, index: Int)] = [:]
        for (index, angle) in angles.enumerated() {
            guard let angle = angle.flatMap(sent) else { return Array(angles.indices) }
            let left = angle < 0, off = abs(abs(angle) - sideAngle)
            if best[left].map({ off < $0.off }) ?? true { best[left] = (off, index) }
        }
        return best.values.map(\.index).sorted()
    }

    /// An angle as the server has it of `LiveBackend.sendOwnSide`.
    static func sent(_ angle: Double) -> Double? {
        guard angle.isFinite else { return nil }
        let within = max(-90, min(90, angle))
        return Double(String(format: "%.1f", locale: Locale(identifier: "en_US_POSIX"), within))
    }

    /// `corners` as four corners of a work the merge can go by, as the
    /// server's `cut.valid` has them (within the photograph, convex,
    /// roughly square at each, of a sensible size); nil when they are not.
    static func valid(_ corners: [[Double]]?) -> [[Double]]? {
        guard let corners, corners.count == 4,
              corners.allSatisfy({ $0.count == 2 && $0[0].isFinite && $0[1].isFinite })
        else { return nil }
        let points = corners.map { CGPoint(x: max(0, min(1, $0[0])), y: max(0, min(1, $0[1]))) }
        var area = 0.0
        var turns: [Double] = []
        for i in 0 ..< 4 {
            let before = points[(i + 3) % 4], at = points[i], after = points[(i + 1) % 4]
            area += Double(at.x * after.y - after.x * at.y)
            let one = CGVector(dx: before.x - at.x, dy: before.y - at.y)
            let other = CGVector(dx: after.x - at.x, dy: after.y - at.y)
            let long = Double(hypot(one.dx, one.dy) * hypot(other.dx, other.dy))
            guard long >= 1e-9 else { return nil }
            let cosine = max(-1, min(1, Double(one.dx * other.dx + one.dy * other.dy) / long))
            guard abs(acos(cosine) * 180 / .pi - 90) <= square else { return nil }
            let next = points[(i + 2) % 4]
            turns.append(Double((after.x - at.x) * (next.y - after.y) - (after.y - at.y) * (next.x - after.x)))
        }
        guard (leastKept ... 1).contains(abs(area) / 2) else { return nil }
        guard turns.allSatisfy({ $0 > 0 }) || turns.allSatisfy({ $0 < 0 }) else { return nil }
        return points.map { [rounded5(Double($0.x)), rounded5(Double($0.y))] }
    }

    private static func rounded5(_ value: Double) -> Double { (value * 100_000).rounded() / 100_000 }

    /// Whether any of `corners` lies beyond what a merge within `had`
    /// cleaned (those with `around` more about their middle): the scan is
    /// then made again within `corners`, as the server's `_again` would.
    static func beyond(_ corners: [[Double]], cleaned had: [[Double]]) -> Bool {
        guard corners.count == 4, had.count == 4, (corners + had).allSatisfy({ $0.count == 2 }) else { return false }
        let middle = [had.map { $0[0] }.reduce(0, +) / 4, had.map { $0[1] }.reduce(0, +) / 4]
        let grown = had.map { [middle[0] + ($0[0] - middle[0]) * (1 + 2 * around), middle[1] + ($0[1] - middle[1]) * (1 + 2 * around)] }
        return corners.contains { point in
            var sides: [Double] = []
            for i in 0 ..< 4 {
                let a = grown[i], b = grown[(i + 1) % 4]
                sides.append((b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0]))
            }
            // On an edge is within.
            return !(sides.allSatisfy { $0 >= -1e-9 } || sides.allSatisfy { $0 <= 1e-9 })
        }
    }

    /// Whether the phone has the memory to spare for the merge of a first
    /// photograph of so many pixels (`available`: what this app may still
    /// take, 0 where the system does not say).
    static func roomy(pixels: Int, available: Int = Int(clamping: os_proc_available_memory())) -> Bool {
        available <= 0 || available >= pixels * bytesPerPixel
    }

    // MARK: The photographs read

    /// A photograph's size standing upright, as its file says it.
    static func size(of file: Data) -> (columns: Int, rows: Int)? {
        guard let source = CGImageSourceCreateWithData(file as CFData, nil),
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let width = properties[kCGImagePropertyPixelWidth] as? Int,
              let height = properties[kCGImagePropertyPixelHeight] as? Int, width > 0, height > 0
        else { return nil }
        let turned = (properties[kCGImagePropertyOrientation] as? UInt32).map { $0 >= 5 } ?? false
        return turned ? (height, width) : (width, height)
    }

    /// How many times smaller a side photograph of that size is read: as
    /// Pillow's `draft` makes a JPEG on the server (1, 2, 4 or 8, neither
    /// side under `least`).
    static func smaller(columns: Int, rows: Int, least: Int) -> Int {
        let times = min(columns / max(least, 1), rows / max(least, 1))
        return times >= 8 ? 8 : times >= 4 ? 4 : times >= 2 ? 2 : 1
    }

    /// A photograph's file as the merge reads it, written to `into` (a
    /// `.npy` of rows × columns × RGB): upright, in sRGB as the server
    /// turns the camera's Display P3, whole or (`least`, a side one) as
    /// small as `smaller` says. Its rows and columns.
    @discardableResult
    static func write(_ file: Data, into: URL, least: Int? = nil) throws -> (rows: Int, columns: Int) {
        guard let source = CGImageSourceCreateWithData(file as CFData, nil), let whole = size(of: file) else {
            throw Failed(told: "a photograph's file is no picture")
        }
        let times = least.map { smaller(columns: whole.columns, rows: whole.rows, least: $0) } ?? 1
        let long = (max(whole.columns, whole.rows) + times - 1) / times
        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: long,
            kCGImageSourceShouldCacheImmediately: true,
        ]
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary),
              let colours = CGColorSpace(name: CGColorSpace.sRGB)
        else { throw Failed(told: "a photograph could not be read") }
        let columns = image.width, rows = image.height
        guard let context = CGContext(
            data: nil, width: columns, height: rows, bitsPerComponent: 8, bytesPerRow: columns * 4,
            space: colours, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
        ) else { throw Failed(told: "no memory for a photograph") }
        context.interpolationQuality = .none  // pixel for pixel
        context.draw(image, in: CGRect(x: 0, y: 0, width: columns, height: rows))
        guard let drawn = context.data else { throw Failed(told: "no memory for a photograph") }

        let head = ScanPicture.head(rows: rows, columns: columns)
        var picture = Data(count: head.count + rows * columns * 3)
        picture.replaceSubrange(0 ..< head.count, with: head)
        let converted = picture.withUnsafeMutableBytes { raw -> vImage_Error in
            guard let base = raw.baseAddress else { return kvImageNullPointerArgument }
            var from = vImage_Buffer(
                data: drawn, height: vImagePixelCount(rows), width: vImagePixelCount(columns),
                rowBytes: context.bytesPerRow
            )
            var to = vImage_Buffer(
                data: base.advanced(by: head.count), height: vImagePixelCount(rows),
                width: vImagePixelCount(columns), rowBytes: columns * 3
            )
            return vImageConvert_RGBA8888toRGB888(&from, &to, vImage_Flags(kvImageNoFlags))
        }
        guard converted == kvImageNoError else { throw Failed(told: "a photograph could not be read") }
        try picture.write(to: into)
        return (rows, columns)
    }

    /// A scan's photographs read into `folder` for the merge: the first
    /// whole, each side one as the server's merge reads its own.
    static func read(first: Data, sides: [Data], into folder: URL) throws -> Read {
        let began = ProcessInfo.processInfo.systemUptime
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let firstAt = folder.appendingPathComponent("first.npy")
        // One at a time: the first whole is 200 MB while it is drawn.
        let shape = try autoreleasepool { try write(first, into: firstAt) }
        var sidesAt: [URL] = []
        for (n, side) in sides.enumerated() {
            let at = folder.appendingPathComponent("side\(n + 1).npy")
            try autoreleasepool { _ = try write(side, into: at, least: matchSide) }
            sidesAt.append(at)
        }
        return Read(
            folder: folder, first: firstAt, sides: sidesAt, rows: shape.rows, columns: shape.columns,
            seconds: ProcessInfo.processInfo.systemUptime - began
        )
    }

    // MARK: The scan made

    /// The scan of `read`'s photographs within the work's `corners`: made
    /// also of photographs that show no one flat work, in doubt, as the
    /// server makes the one he chooses from. Seconds of all the phone's
    /// cores: never on the main thread.
    static func make(_ read: Read, corners: [[Double]]) throws -> Made {
        let into = read.folder.appendingPathComponent("made.npy")
        defer { try? FileManager.default.removeItem(at: into) }
        let note = try ScanCore.merge(
            first: read.first, sides: read.sides, corners: corners.flatMap { $0 }, anyway: true, into: into
        )
        var picture: Data?
        let began = ProcessInfo.processInfo.systemUptime
        if note.used > 0, note.removed > 0 {
            let made = try Data(contentsOf: into, options: .mappedIfSafe)
            guard let jpeg = autoreleasepool(invoking: { jpeg(of: made) }) else {
                throw Failed(told: "the scan could not be written")
            }
            picture = jpeg
        }
        return Made(
            corners: corners, note: note, picture: picture, read: read.seconds,
            written: ProcessInfo.processInfo.systemUptime - began
        )
    }

    /// A picture (`.npy`, rows × columns × RGB in sRGB) as the JPEG the
    /// server keeps of a scan: its own size, upright, and plain (no colour
    /// profile of its own: the server then keeps the very file).
    static func jpeg(of npy: Data) -> Data? {
        guard let (rows, columns, from) = ScanPicture.shape(of: npy) else { return nil }
        let pixels = npy.subdata(in: (npy.startIndex + from) ..< npy.endIndex)
        guard let provider = CGDataProvider(data: pixels as CFData),
              let image = CGImage(
                  width: columns, height: rows, bitsPerComponent: 8, bitsPerPixel: 24, bytesPerRow: columns * 3,
                  space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.none.rawValue),
                  provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent
              )
        else { return nil }
        let jpeg = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(
            jpeg as CFMutableData, UTType.jpeg.identifier as CFString, 1, nil
        ) else { return nil }
        CGImageDestinationAddImage(
            destination, image, [kCGImageDestinationLossyCompressionQuality: quality] as CFDictionary
        )
        guard CGImageDestinationFinalize(destination) else { return nil }
        return plain(jpeg as Data)
    }

    /// A JPEG without a colour profile of its own (its `ICC_PROFILE`
    /// parts left out): its numbers are sRGB's, which is what a JPEG that
    /// names none is read as.
    static func plain(_ jpeg: Data) -> Data {
        let bytes = [UInt8](jpeg)
        guard bytes.count > 4, bytes[0] == 0xFF, bytes[1] == 0xD8 else { return jpeg }
        var out: [UInt8] = [0xFF, 0xD8]
        out.reserveCapacity(bytes.count)
        var at = 2
        let named = Array("ICC_PROFILE".utf8) + [0]
        while at + 4 <= bytes.count, bytes[at] == 0xFF {
            let kind = bytes[at + 1]
            // The picture itself begins: the rest is its own.
            if kind == 0xDA { break }
            let length = Int(bytes[at + 2]) << 8 | Int(bytes[at + 3])
            guard length >= 2, at + 2 + length <= bytes.count else { return jpeg }
            let profile = kind == 0xE2 && length >= 2 + named.count
                && Array(bytes[(at + 4) ..< (at + 4 + named.count)]) == named
            if !profile { out.append(contentsOf: bytes[at ..< (at + 2 + length)]) }
            at += 2 + length
        }
        out.append(contentsOf: bytes[at...])
        return Data(out)
    }

    // MARK: What the server is told

    /// What goes to the server with the scan (`PhoneScan` in
    /// `web/own_api.py`), as JSON: what it came to, what the camera noted
    /// of the scan (`trace`), and what the phone noted of making it.
    static func told(
        _ made: Made, trace: [String: Double],
        heat: (before: ProcessInfo.ThermalState, after: ProcessInfo.ThermalState)
    ) -> Data {
        let process = ProcessInfo.processInfo, system = process.operatingSystemVersion
        let app = Bundle.main.infoDictionary ?? [:]
        var phone: [String: Any] = [
            "seconds": tenths(made.note.seconds + made.read + made.written, 100),
            "took": made.note.took.mapValues { tenths($0, 100) },
            "files": tenths(made.read, 100),
            "jpeg": tenths(made.written, 100),
            "built": ScanCore.built,
            "model": ScanTrial.model,
            "system": "\(system.majorVersion).\(system.minorVersion).\(system.patchVersion)",
            "app": "\(app["CFBundleShortVersionString"] ?? "?") (\(app["CFBundleVersion"] ?? "?"))",
            "cores": process.activeProcessorCount,
            "memory_gb": tenths(Double(process.physicalMemory) / 1_073_741_824, 10),
            "low_power": process.isLowPowerModeEnabled,
            "heat": [heat.before.rawValue, heat.after.rawValue],
        ]
        if let picture = made.picture { phone["bytes"] = picture.count }
        var note: [String: Any] = [
            "corners": made.corners,
            "used": made.note.used,
            "replaced": made.picture == nil ? 0 : min(1, max(0, made.note.removed)),
            "doubt": made.note.doubt,
            "phone": phone,
        ]
        let noted = trace.filter { $0.value.isFinite }
        if !noted.isEmpty { note["trace"] = noted }
        return (try? JSONSerialization.data(withJSONObject: note, options: [.sortedKeys])) ?? Data("{}".utf8)
    }

    private static func tenths(_ value: Double, _ of: Double) -> Double {
        value.isFinite ? (value * of).rounded() / of : 0
    }
}

/// The scan the phone makes of one scan's photographs, and the photographs
/// as it read them, kept (in the app's temporary files) while he sets the
/// corners.
@MainActor
final class OwnPhoneScan {
    /// A scan the phone made, as it goes to the server: with what the
    /// server's own merge of the same photographs would be asked by,
    /// should the server not take the phone's.
    struct Owed: Sendable {
        var token: String
        var note: Data
        var picture: Data?
        var outline: [[Double]]?
        var trace: [String: Double]
    }

    /// What came of sending one: the server keeps it, would not take it
    /// (an answer of its own: it then makes the scan itself), or it was
    /// lost on the way there (and may be sent again).
    enum Delivery: Sendable, Equatable {
        case kept, refused
        case lost(String)
    }

    struct Lost: LocalizedError {
        let told: String
        var errorDescription: String? { "Nie udało się wysłać skanu na serwer: \(told)" }
    }

    private var read: PhoneScan.Read?
    /// What the camera noted of the scan this is made of.
    private(set) var outline: [[Double]]?
    private(set) var trace: [String: Double] = [:]
    private let folder = FileManager.default.temporaryDirectory
        .appendingPathComponent("own-scan-\(UUID().uuidString)", isDirectory: true)

    /// What an earlier scan left, should the app have been closed on it.
    static func sweep() {
        let files = FileManager.default
        let all = (try? files.contentsOfDirectory(at: files.temporaryDirectory, includingPropertiesForKeys: nil)) ?? []
        for old in all where old.lastPathComponent.hasPrefix("own-scan-") { try? files.removeItem(at: old) }
    }

    /// Whether the phone can make the scan of these photographs: it has
    /// the camera's own files of them all, the first as large as the
    /// server keeps it (`size`), and the memory to spare.
    static func can(_ shots: OwnShots, size: (width: Int, height: Int)) -> Bool {
        guard !shots.sides.isEmpty, shots.files.count == shots.sides.count + 1,
              let first = PhoneScan.size(of: shots.files[0]),
              first.columns == size.width, first.rows == size.height
        else { return false }
        return PhoneScan.roomy(pixels: first.columns * first.rows)
    }

    /// The scan of `shots` within `corners`; nil when the phone could not
    /// make it (the server then does).
    func make(_ shots: OwnShots, corners: [[Double]]) async -> PhoneScan.Made? {
        let files = shots.files, folder = self.folder
        guard files.count == shots.sides.count + 1 else { return nil }
        outline = shots.outline
        trace = shots.trace
        let used = PhoneScan.chosen(angles: shots.sides.indices.map { shots.angle($0) })
        let made = await Task.detached(priority: .userInitiated) { () -> (PhoneScan.Read, PhoneScan.Made)? in
            do {
                let read = try PhoneScan.read(first: files[0], sides: used.map { files[$0 + 1] }, into: folder)
                let scan = try PhoneScan.make(read, corners: corners)
                return (read, scan)
            } catch {
                try? FileManager.default.removeItem(at: folder)
                return nil
            }
        }.value
        read = made?.0
        return made?.1
    }

    /// The scan once more, within other corners.
    func again(corners: [[Double]]) async -> PhoneScan.Made? {
        guard let read else { return nil }
        return await Task.detached(priority: .userInitiated) {
            try? PhoneScan.make(read, corners: corners)
        }.value
    }

    /// The photographs let go of.
    func clear() {
        read = nil
        try? FileManager.default.removeItem(at: folder)
    }

    /// `owed` sent to the server to be kept in the first photograph's
    /// place; once more, a moment later, where it was lost on the way.
    static func deliver(_ owed: Owed, with backend: any FrameBackend) async -> Delivery {
        var lost = ""
        for attempt in 0 ..< 2 {
            do {
                _ = try await backend.sendOwnScan(token: owed.token, note: owed.note, picture: owed.picture)
                return .kept
            } catch let error {
                if refused(error) { return .refused }
                lost = error.localizedDescription
                if attempt == 0 { try? await Task.sleep(for: .seconds(1)) }
            }
        }
        return .lost(lost)
    }

    /// Whether the server answered that it will not take the scan (no
    /// such photograph, no scan of it, a server that has no such way):
    /// sending it again would be answered the same.
    static func refused(_ error: Error) -> Bool {
        guard let error = error as? BackendError else { return false }
        switch error {
        case .notFound: return true
        case let .http(status, _): return (400 ..< 500).contains(status)
        default: return false
        }
    }

    deinit { try? FileManager.default.removeItem(at: folder) }
}
