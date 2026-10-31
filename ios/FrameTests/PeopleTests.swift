import XCTest
@testable import Frame

final class PeopleTests: XCTestCase {
    func testInvitationLinkRoundTrip() throws {
        let invitation = Invitation(
            code: "abc_DEF-123456789012",
            home: "http://192.0.2.10:8099",
            remote: "http://100.64.0.5:8099",
            from: "Mateusz",
            frame: "Salon"
        )
        let url = invitation.url
        XCTAssertEqual(url.scheme, "com.artrybka.frame")
        XCTAssertEqual(url.host, "join")
        XCTAssertEqual(Invitation(url: url), invitation)
    }

    func testOtherLinksAreNoInvitations() throws {
        XCTAssertNil(Invitation(url: URL(string: "com.artrybka.frame://open?route=study/met:1")!))
        XCTAssertNil(Invitation(url: URL(string: "com.artrybka.frame://join?home=http://x")!))
        XCTAssertNil(Invitation(url: URL(string: "https://example.com/join?code=x&home=y")!))
    }

    func testDecodesMeAndPlaylistOwners() throws {
        let me = try LiveBackend.decoder().decode(Me.self, from: Data("""
        {"id": "u-1a2b3c4d", "name": "Paulina", "role": "member", "device_id": "9f8e7d6c",
         "studies_left": 5, "people": true}
        """.utf8))
        XCTAssertFalse(me.isOwner)
        XCTAssertEqual(me.studiesLeft, 5)

        let shared = try LiveBackend.decoder().decode(PlaylistSummary.self, from: Data("""
        {"id": 3, "name": "Ala", "description": "", "kind": "smart",
         "rules": {"query": "", "artists": ["Ala"], "styles": [], "subjects": [], "colors": [], "kinds": [], "sources": [], "favorites_only": false}, "item_count": 2, "cover_item_ids": [],
         "owner": "owner", "owner_name": "Mateusz", "shared": true, "mine": false}
        """.utf8))
        XCTAssertFalse(shared.isMine)
        XCTAssertEqual(shared.ownerName, "Mateusz")

        // An older server: no owner, the phone's own.
        let old = try LiveBackend.decoder().decode(PlaylistSummary.self, from: Data("""
        {"id": 4, "name": "Stare", "description": "", "kind": "manual",
         "rules": {"query": "", "artists": [], "styles": [], "subjects": [], "colors": [], "kinds": [], "sources": [], "favorites_only": false}, "item_count": 0, "cover_item_ids": []}
        """.utf8))
        XCTAssertTrue(old.isMine)
    }
}
