import XCTest
@testable import Frame

final class StudyActivityTests: XCTestCase {
    typealias State = StudyActivityAttributes.ContentState

    /// The server pushes `{"status": …, "error": …}` (notifications.py `push_study`).
    func testTheServersPushDecodes() throws {
        let pushed = #"{"status": "writing", "error": ""}"#
        let state = try JSONDecoder().decode(State.self, from: Data(pushed.utf8))
        XCTAssertEqual(state.status, "writing")
        XCTAssertTrue(state.isActive)
        XCTAssertEqual(state.stepIndex, 1)
        // Without "error" too.
        let ready = try JSONDecoder().decode(State.self, from: Data(#"{"status": "ready"}"#.utf8))
        XCTAssertTrue(ready.isReady)
        XCTAssertEqual(ready.stepIndex, State.steps.count)
    }

    func testEachStepHasItsLine() {
        XCTAssertEqual(State(status: "waiting").line, "Czekam na Claude’a")
        XCTAssertNil(State(status: "waiting").stepIndex)
        XCTAssertEqual(State(status: "details").stepIndex, 2)
        XCTAssertEqual(State(status: "failed", error: "Brak klucza.").line, "Brak klucza.")
        XCTAssertEqual(State(status: "failed", error: "").line, "Nie udało się przygotować studium")
        XCTAssertTrue(State(status: "stopped").isFailed)
        XCTAssertFalse(State(status: "stopped").isActive)
    }

    /// A tap on the finished card opens the study, as the notification does.
    func testTheCardOpensTheStudy() throws {
        let url = StudyActivityAttributes(itemID: "met:7", title: "Ul").url
        XCTAssertEqual(url.scheme, "com.artrybka.frame")
        let route = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first { $0.name == "route" }
        XCTAssertEqual(route?.value, "study/met:7")
    }
}
