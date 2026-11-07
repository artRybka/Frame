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

    func testDecodesTheServersAddress() throws {
        let json = """
        {"key_set": false, "key_tail": null, "key": null, "saved_at": null, "address": "http://nas.tail1234.ts.net:8099"}
        """
        let key = try LiveBackend.decoder().decode(TailnetKey.self, from: Data(json.utf8))
        XCTAssertEqual(key.address, "http://nas.tail1234.ts.net:8099")
        let older = try LiveBackend.decoder().decode(TailnetKey.self, from: Data(#"{"key_set": false}"#.utf8))
        XCTAssertNil(older.address)
    }

    /// The machines asked whether they are the frame server: online ones,
    /// by MagicDNS name, else by IPv4 address.
    func testAsksTheTailnetsOnlineMachines() throws {
        let status = """
        {"Self": {"DNSName": "frame-mateusz.tail1234.ts.net."},
         "Peer": {
           "nodekey:a": {"DNSName": "synology.tail1234.ts.net.", "TailscaleIPs": ["100.95.9.80", "fd7a:115c:a1e0::1"], "Online": true},
           "nodekey:b": {"DNSName": "", "TailscaleIPs": ["fd7a:115c:a1e0::2", "100.70.1.2"], "Online": true},
           "nodekey:c": {"DNSName": "macbook.tail1234.ts.net.", "TailscaleIPs": ["100.80.0.3"], "Online": false},
           "nodekey:d": {"DNSName": "", "TailscaleIPs": ["fd7a:115c:a1e0::4"]}
         }}
        """
        let found = try XCTUnwrap(Tailnet.candidates(status: Data(status.utf8), port: 8099, scheme: "http"))
        XCTAssertEqual(found.map(\.absoluteString), ["http://100.70.1.2:8099", "http://synology.tail1234.ts.net:8099"])
        XCTAssertEqual(Tailnet.candidates(status: Data(#"{"Self": {}}"#.utf8), port: 8099, scheme: "http"), [])
        XCTAssertNil(Tailnet.candidates(status: Data("nope".utf8), port: 8099, scheme: "http"))
    }

    func testShowsTheAddressWithoutTheScheme() {
        XCTAssertEqual(TailnetSection.shown("http://synology.tail1234.ts.net:8099"), "synology.tail1234.ts.net:8099")
        XCTAssertEqual(TailnetSection.shown("https://nas.tail1234.ts.net"), "nas.tail1234.ts.net")
        XCTAssertNil(TailnetSection.shown(""))
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
