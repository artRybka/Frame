import XCTest
@testable import Frame

final class ServerUpdatePromptTests: XCTestCase {
    private func update(
        version: String, latest: String?, available: Bool = true,
        addon: Bool = false, updater: Bool = true, state: String = "idle"
    ) -> ServerUpdate {
        ServerUpdate(
            version: version, addon: addon, updater: updater, state: state,
            updateAvailable: available, latestVersion: latest, latestRevision: nil,
            checkedAt: nil, error: nil, lastUpdate: nil, pending: nil
        )
    }

    func testVersionsCompareByNumbers() {
        XCTAssertTrue(ServerUpdatePrompt.isOlder("1.47.0", than: "1.48.0"))
        XCTAssertTrue(ServerUpdatePrompt.isOlder("0.46.1", than: "1.47.0"))
        XCTAssertTrue(ServerUpdatePrompt.isOlder("1.9.0", than: "1.10.0"))
        XCTAssertTrue(ServerUpdatePrompt.isOlder("1.48", than: "1.48.1"))
        XCTAssertFalse(ServerUpdatePrompt.isOlder("1.48.0", than: "1.48"))
        XCTAssertFalse(ServerUpdatePrompt.isOlder("1.49.0", than: "1.48.0"))
        XCTAssertFalse(ServerUpdatePrompt.isOlder("1.48.0-dev", than: "1.48.0"))
        XCTAssertFalse(ServerUpdatePrompt.isOlder("", than: "1.48.0"))
    }

    func testAnOlderServerWithANewerImageIsWorthSaying() {
        XCTAssertTrue(ServerUpdatePrompt.needed(app: "1.49.0", update: update(version: "1.47.0", latest: "1.49.0")))
    }

    func testAnAppOnlyReleaseBringsNoCard() {
        // 1.48.0 changed only the app: no image, the server stays 1.47.0.
        XCTAssertFalse(ServerUpdatePrompt.needed(
            app: "1.48.0", update: update(version: "1.47.0", latest: "1.47.0", available: false)
        ))
    }

    func testAServerAsNewAsTheAppNeedsNoCard() {
        // A newer server alone is the Serwer tile's (and a notification's) news.
        XCTAssertFalse(ServerUpdatePrompt.needed(app: "1.48.0", update: update(version: "1.48.0", latest: "1.49.0")))
        // Local builds are 1.0.
        XCTAssertFalse(ServerUpdatePrompt.needed(app: "1.0", update: update(version: "1.47.0", latest: "1.48.0")))
    }

    func testOnlyWhereTheAppCanUpdateIt() {
        XCTAssertFalse(ServerUpdatePrompt.needed(app: "1.49.0", update: update(version: "1.47.0", latest: "1.49.0", addon: true)))
        XCTAssertFalse(ServerUpdatePrompt.needed(app: "1.49.0", update: update(version: "1.47.0", latest: "1.49.0", updater: false)))
        XCTAssertFalse(ServerUpdatePrompt.needed(app: "1.49.0", update: update(version: "1.47.0", latest: "1.49.0", state: "updating")))
    }
}
