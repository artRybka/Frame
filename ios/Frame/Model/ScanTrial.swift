import Foundation
import Observation
import UIKit

/// A scan of three kept on the server (two weeks) with what its merge noted
/// of it (`/api/debug/own-scans`): what the trial of merging on the phone
/// is run on.
struct KeptScan: Decodable, Identifiable, Hashable, Sendable {
    var token: String
    /// When the server made it (ISO 8601).
    var at: String? = nil
    /// The work's corners on the first photograph (0–1), as the merge had them.
    var corners: [[Double]]? = nil
    var used: Int? = nil
    var replaced: Double? = nil
    var doubt: Bool? = nil
    /// The scan's files by name ("first.jpg", "side1.jpg"…) with their sizes.
    var files: [String: Int] = [:]

    var id: String { token }

    /// The side photographs the scan was made of, in their order.
    var sides: [String] {
        files.keys.filter { $0.hasPrefix("side") && $0.hasSuffix(".jpg") }.sorted()
    }

    /// The corners as the core takes them (x0, y0 … x3, y3); nil unless four.
    var quad: [Double]? {
        guard let corners, corners.count == 4, corners.allSatisfy({ $0.count == 2 }) else { return nil }
        return corners.flatMap { $0 }
    }

    /// A scan of a work found on its first photograph, with a side one:
    /// what the server merged within the work's corners.
    var mergeable: Bool { quad != nil && files["first.jpg"] != nil && !sides.isEmpty }

    var date: Date? { at.flatMap { ISO8601DateFormatter().date(from: $0) } }

    enum CodingKeys: String, CodingKey {
        case token, at, corners, used, replaced, doubt, files
    }

    init(token: String, at: String? = nil, corners: [[Double]]? = nil, files: [String: Int] = [:]) {
        self.token = token
        self.at = at
        self.corners = corners
        self.files = files
    }

    /// Lenient: what an older merge noted otherwise is simply not known.
    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        token = try values.decode(String.self, forKey: .token)
        at = try? values.decodeIfPresent(String.self, forKey: .at)
        corners = try? values.decodeIfPresent([[Double]].self, forKey: .corners)
        used = try? values.decodeIfPresent(Int.self, forKey: .used)
        replaced = try? values.decodeIfPresent(Double.self, forKey: .replaced)
        doubt = try? values.decodeIfPresent(Bool.self, forKey: .doubt)
        files = (try? values.decodeIfPresent([String: Int].self, forKey: .files)) ?? [:]
    }
}

/// Konfiguracja → Diagnostyka, "Składanie skanu na iPhonie": the phone
/// merges his last kept scans itself (`ScanCore`) from the very numbers the
/// server merged them from, times it, and leaves what it made beside the
/// scan on the server to be compared with the server's. Nothing of his
/// collection changes (Mateusz 2026-11-19 00:12 UTC: "Najpierw próba na
/// iPhonie").
@MainActor
@Observable
final class ScanTrial {
    struct Row: Identifiable, Equatable {
        enum Stage: Equatable {
            case waiting, fetching, merging, sending, done
            case failed(String)
        }

        let id: String
        var date: Date?
        var stage: Stage = .waiting
        /// The merge on the phone, files read and written too.
        var seconds: Double?
    }

    /// So many of his latest scans: a few minutes with their photographs
    /// fetched whole (some 220 MB each) and the picture sent back.
    static let most = 3

    private(set) var rows: [Row] = []
    private(set) var running = false
    /// Why there is nothing to show, in his words.
    private(set) var told: String?

    /// The mean of the merges that went well.
    var mean: Double? {
        let times = rows.compactMap(\.seconds)
        return times.isEmpty ? nil : times.reduce(0, +) / Double(times.count)
    }

    /// The latest scans the phone can merge as the server did.
    nonisolated static func chosen(_ scans: [KeptScan], most: Int = ScanTrial.most) -> [KeptScan] {
        Array(scans.filter(\.mergeable).prefix(most))
    }

    func run(with backend: any FrameBackend) async {
        guard !running else { return }
        running = true
        told = nil
        rows = []
        // Minutes of work: the screen stays on, the app in front.
        UIApplication.shared.isIdleTimerDisabled = true
        defer {
            UIApplication.shared.isIdleTimerDisabled = false
            running = false
        }
        do {
            let scans = Self.chosen(try await backend.keptScans())
            guard !scans.isEmpty else {
                told = "Na serwerze nie ma skanu z trzech zdjęć z ostatnich dwóch tygodni. Zeskanuj dowolne dzieło i wróć tutaj."
                return
            }
            rows = scans.map { Row(id: $0.token, date: $0.date) }
            for (n, scan) in scans.enumerated() {
                do {
                    let seconds = try await merge(scan, row: n, with: backend)
                    rows[n].seconds = seconds
                    rows[n].stage = .done
                } catch {
                    rows[n].stage = .failed(error.localizedDescription)
                }
            }
        } catch {
            told = "Serwer nie podał zachowanych skanów: \(error.localizedDescription)"
        }
    }

    /// One scan fetched, merged and sent back; the seconds the merge took.
    private func merge(_ scan: KeptScan, row n: Int, with backend: any FrameBackend) async throws -> Double {
        let files = FileManager.default
        let folder = files.temporaryDirectory.appendingPathComponent("scan-trial-\(scan.token)", isDirectory: true)
        try? files.removeItem(at: folder)
        try files.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? files.removeItem(at: folder) }

        rows[n].stage = .fetching
        var photographs: [URL] = []
        for name in ["first.jpg"] + scan.sides {
            let file = folder.appendingPathComponent(name + ".npy")
            try await backend.keptScanPixels(token: scan.token, name: name).write(to: file)
            photographs.append(file)
        }

        rows[n].stage = .merging
        let first = photographs[0], sides = Array(photographs.dropFirst()), quad = scan.quad ?? []
        let into = folder.appendingPathComponent("phone.npy")
        let before = ProcessInfo.processInfo.thermalState
        // The server makes the scan he chooses from also of photographs
        // that show no one flat work (`choice`): so does the phone.
        let (note, jpeg) = try await Task.detached(priority: .userInitiated) {
            let note = try ScanCore.merge(first: first, sides: sides, corners: quad, anyway: true, into: into)
            let made = try Data(contentsOf: into, options: .mappedIfSafe)
            return (note, ScanPicture.jpegSeconds(of: made))
        }.value
        let after = ProcessInfo.processInfo.thermalState

        rows[n].stage = .sending
        var report = Self.report(note, of: scan, heat: (before, after))
        if let jpeg {
            report["jpeg"] = ["written": jpeg.written, "read": jpeg.read, "bytes": jpeg.bytes] as [String: Any]
        }
        let made = try Data(contentsOf: into, options: .mappedIfSafe)
        try await backend.sendPhoneScan(token: scan.token, name: "phone.npy", made)
        let noted = try JSONSerialization.data(withJSONObject: report, options: [.sortedKeys])
        try await backend.sendPhoneScan(token: scan.token, name: "phone.json", noted)
        return note.seconds
    }

    /// What the phone notes of a merge beside its picture: how long each
    /// part took, what it came to (and what the server's came to), and on
    /// what phone in what state.
    static func report(
        _ note: ScanCore.Note, of scan: KeptScan,
        heat: (before: ProcessInfo.ThermalState, after: ProcessInfo.ThermalState)
    ) -> [String: Any] {
        let process = ProcessInfo.processInfo
        var server: [String: Any] = [:]
        if let used = scan.used { server["used"] = used }
        if let replaced = scan.replaced { server["replaced"] = replaced }
        if let doubt = scan.doubt { server["doubt"] = doubt }
        let app = Bundle.main.infoDictionary ?? [:]
        return [
            "at": ISO8601DateFormatter().string(from: .now),
            "seconds": note.seconds,
            "took": note.took,
            "used": note.used,
            "removed": note.removed,
            "doubt": note.doubt,
            "server": server,
            "built": ScanCore.built,
            "model": model,
            "system": UIDevice.current.systemVersion,
            "app": "\(app["CFBundleShortVersionString"] ?? "?") (\(app["CFBundleVersion"] ?? "?"))",
            "cores": process.activeProcessorCount,
            "memory_gb": (Double(process.physicalMemory) / 1_073_741_824 * 10).rounded() / 10,
            "low_power": process.isLowPowerModeEnabled,
            "heat": [heat.before.rawValue, heat.after.rawValue],
        ]
    }

    /// The phone's model as it names itself ("iPhone18,2").
    nonisolated static var model: String {
        var system = utsname()
        uname(&system)
        return withUnsafeBytes(of: &system.machine) { bytes in
            String(decoding: bytes.prefix { $0 != 0 }, as: UTF8.self)
        }
    }
}
