import XCTest
@testable import Frame

/// Pictures fetched ahead (Galeria's stock) go after those wanted on a
/// screen and take few places of the line (Mateusz 2026-11-27: covers of
/// Odkrywaj and Playlisty came slower behind Galeria's stock).
final class HostGateTests: XCTestCase {
    private static let host = HostGate.own + "frame.local"

    /// A short while for the gate to let in whoever may run.
    private func settle() async {
        try? await Task.sleep(for: .milliseconds(100))
    }

    private final class Order: @unchecked Sendable {
        private let lock = NSLock()
        private var names: [String] = []
        func add(_ name: String) { lock.withLock { names.append(name) } }
        var all: [String] { lock.withLock { names } }
    }

    func testAheadRunsTwoAtATimeAndNormalPassesIt() async throws {
        let gate = HostGate()
        let host = Self.host
        let order = Order()
        var ahead: [UUID] = []
        for index in 0 ..< 4 {
            let id = UUID()
            ahead.append(id)
            Task {
                try await gate.enter(host, id: id, ahead: true)
                order.add("ahead\(index)")
            }
        }
        await settle()
        XCTAssertEqual(order.all, ["ahead0", "ahead1"])
        let normal = UUID()
        try await gate.enter(host, id: normal, ahead: false)  // not behind the two waiting
        order.add("normal")
        XCTAssertEqual(order.all, ["ahead0", "ahead1", "normal"])
        await gate.leave(host, id: ahead[0])
        await settle()
        XCTAssertEqual(order.all.last, "ahead2")
        XCTAssertEqual(order.all.count, 4)
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
        let early = UUID()
        Task {
            try await gate.enter(host, id: early, ahead: true)
            order.add("ahead")
        }
        await settle()
        Task {
            try await gate.enter(host, id: UUID(), ahead: false)
            order.add("normal")
        }
        await settle()
        await gate.leave(host, id: normals[0])
        await settle()
        XCTAssertEqual(order.all, ["normal"])
        await gate.leave(host, id: normals[1])
        await settle()
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
        await settle()
        XCTAssertEqual(order.all, [])
        await gate.promote(second)  // wanted on a screen now
        await settle()
        XCTAssertEqual(order.all, ["second"])
        await gate.hold(false)
        await settle()
        XCTAssertEqual(order.all, ["second", "first"])
    }
}
