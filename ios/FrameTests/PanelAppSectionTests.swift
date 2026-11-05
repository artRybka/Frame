import XCTest
@testable import Frame

/// A new package of the frame's app installs only at a cold start by the
/// button (E19b): the section asks for it while the frame runs another one.
final class PanelAppSectionTests: XCTestCase {
    func testAsksForTheButtonOnlyForAnotherVersion() {
        XCTAssertTrue(PanelAppSection.waitsForButton(package: "2.0.9", onFrame: "2.0.8"))
        XCTAssertFalse(PanelAppSection.waitsForButton(package: "2.0.8", onFrame: "2.0.8"))
        XCTAssertFalse(PanelAppSection.waitsForButton(package: "2.0.8", onFrame: nil))
        XCTAssertFalse(PanelAppSection.waitsForButton(package: "2.0.8", onFrame: ""))
    }
}
