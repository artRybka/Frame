import XCTest
@testable import Frame

/// Pictures fetched ahead (Galeria's stock) go after those wanted on a
/// screen and take at most four places of the line (Mateusz 2026-11-27:
/// covers of Odkrywaj and Playlisty came slower behind Galeria's stock).
///
/// Never by a fixed wait alone: on a busy runner the tasks came later than
/// 100 ms (PR #672). Each step waits till what must happen has happened,
/// and what must not is looked at after a short pause on top.
final class HostGateTests: XCTestCase {
    private static let host = HostGate.own + "frame.local"

    private final class Order: @unchecked Sendable {
        private let lock = NSLock()
        private var names: [String] = []
        func add(_ name: String) { lock.withLock { names.append(name) } }
        var all: [String] { lock.withLock { names } }
    }

    /// Waits (up to 10 s) till `order` holds `count` names, then a little
    /// longer, so that one let in too many would show.
    private func wait(for count: Int, in order: Order, file: StaticString = #filePath, line: UInt = #line) async {
        let deadline = ContinuousClock.now + .seconds(10)
        while order.all.count < count, ContinuousClock.now < deadline {
            try? await Task.sleep(for: .milliseconds(10))
        }
        try? await Task.sleep(for: .milliseconds(150))
        XCTAssertEqual(order.all.count, count, "let in", file: file, line: line)
    }

    /// Waits (up to 10 s) till `count` wait in the gate's line.
    private func wait(inLine count: Int, _ gate: HostGate, file: StaticString = #filePath, line: UInt = #line) async {
        let deadline = ContinuousClock.now + .seconds(10)
        while await gate.inLine(Self.host) < count, ContinuousClock.now < deadline {
            try? await Task.sleep(for: .milliseconds(10))
        }
        let waiting = await gate.inLine(Self.host)
        XCTAssertEqual(waiting, count, "in line", file: file, line: line)
    }

    func testAheadRunsFourAtATimeAndNormalPassesIt() async throws {
        let gate = HostGate()
        let host = Self.host
        let order = Order()
        var ahead: [UUID] = []
        for index in 0 ..< 6 {
            let id = UUID()
            ahead.append(id)
            Task {
                try await gate.enter(host, id: id, ahead: true)
                order.add("ahead\(index)")
            }
        }
        await wait(inLine: 2, gate)
        await wait(for: 4, in: order)
        XCTAssertTrue(order.all.allSatisfy { $0.hasPrefix("ahead") })
        try await gate.enter(host, id: UUID(), ahead: false)  // not behind the two waiting
        order.add("normal")
        XCTAssertEqual(order.all.last, "normal")
        let first = try XCTUnwrap(Int(order.all[0].dropFirst("ahead".count)))
        await gate.leave(host, id: ahead[first])
        await wait(for: 6, in: order)  // one of the two waiting
        XCTAssertTrue(order.all.last?.hasPrefix("ahead") == true)
    }

    func testFullLineLetsNormalInBeforeAhead() async throws {
        let gate = HostGate()
        let host = Self.host
        let order = Order()
        var normals: [UUID] = []
        for _ in 0 ..< 6 {
            let id = UUID()
            normals.append(id)
            try await gate.enter(host, id: id, ahead: false)
        }
        Task {
            try await gate.enter(host, id: UUID(), ahead: true)
            order.add("ahead")
        }
        await wait(inLine: 1, gate)  // in line before the normal one
        Task {
            try await gate.enter(host, id: UUID(), ahead: false)
            order.add("normal")
        }
        await wait(inLine: 2, gate)
        await gate.leave(host, id: normals[0])
        await wait(for: 1, in: order)
        XCTAssertEqual(order.all, ["normal"])
        await gate.leave(host, id: normals[1])
        await wait(for: 2, in: order)
        XCTAssertEqual(order.all, ["normal", "ahead"])
    }

    func testHeldAheadWaitsAndPromotedGoes() async throws {
        let gate = HostGate()
        let host = Self.host
        let order = Order()
        await gate.hold(true)
        let first = UUID(), second = UUID()
        Task {
            try await gate.enter(host, id: first, ahead: true)
            order.add("first")
        }
        Task {
            try await gate.enter(host, id: second, ahead: true)
            order.add("second")
        }
        await wait(inLine: 2, gate)
        await wait(for: 0, in: order)
        await gate.promote(second)  // wanted on a screen now, in line or not yet
        await wait(for: 1, in: order)
        XCTAssertEqual(order.all, ["second"])
        await gate.hold(false)
        await wait(for: 2, in: order)
        XCTAssertEqual(order.all, ["second", "first"])
    }
}
