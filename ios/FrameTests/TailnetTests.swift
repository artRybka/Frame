import XCTest
@testable import Frame

/// Tailscale built into the app: which addresses it carries, how its node
/// is named and what Konfiguracja says when it fails.
final class TailnetTests: XCTestCase {
    func testOnlyTailscaleAddressesGoThroughTheNode() {
        for host in ["100.95.9.80", "100.64.0.1", "100.127.255.254", "nas.tail1234.ts.net", "NAS.TAIL1234.TS.NET",
                     "fd7a:115c:a1e0::1", "[fd7a:115c:a1e0::1]", "nas"] {
            XCTAssertTrue(Tailnet.isTailscale(host), host)
        }
        for host in ["192.100.3.185", "100.63.0.1", "100.128.0.1", "10.0.0.5", "frame.example.com", "localhost", "", "::1"] {
            XCTAssertFalse(Tailnet.isTailscale(host), host)
        }
    }

    func testNodeNameSaysWhosePhone() {
        XCTAssertEqual(Tailnet.nodeName(for: "Mateusz"), "frame-mateusz")
        XCTAssertEqual(Tailnet.nodeName(for: "Paulina Łęcka"), "frame-paulina-lecka")
        XCTAssertEqual(Tailnet.nodeName(for: nil), "frame-iphone")
        XCTAssertEqual(Tailnet.nodeName(for: "  "), "frame-iphone")
    }

    func testARefusedKeyIsSaidSo() {
        XCTAssertTrue(Tailnet.words("tsnet.Up: backend: invalid key: unable to validate API key").contains("odrzucił klucz"))
        XCTAssertEqual(Tailnet.words(""), "Tailscale nie wystartował.")
        XCTAssertEqual(Tailnet.words("dial tcp: no route"), "Tailscale: dial tcp: no route")
    }

    func testDecodesTheServersKey() throws {
        let json = """
        {"key_set": true, "key_tail": "CDEF", "key": "tskey-auth-k123-ABCDEF", "saved_at": "2026-11-03T15:00:00+00:00"}
        """
        let key = try LiveBackend.decoder().decode(TailnetKey.self, from: Data(json.utf8))
        XCTAssertTrue(key.keySet)
        XCTAssertEqual(key.keyTail, "CDEF")
        XCTAssertEqual(key.key, "tskey-auth-k123-ABCDEF")
    }

    func testDemoKeepsAKeyButNotAnything() async throws {
        let demo = DemoBackend()
        do {
            _ = try await demo.saveTailnetKey("sk-ant-nope")
            XCTFail("not a Tailscale key")
        } catch BackendError.http(400, _) {}
        let saved = try await demo.saveTailnetKey("tskey-auth-kAbCdEf1CNTRL-0123456789")
        XCTAssertTrue(saved.keySet)
        XCTAssertEqual(saved.keyTail, "6789")
        let gone = try await demo.deleteTailnetKey()
        XCTAssertFalse(gone.keySet)
    }
}
