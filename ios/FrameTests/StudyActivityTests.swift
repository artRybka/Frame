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
        XCTAssertEqual(State(status: "details").stepIndex, 3)
        XCTAssertEqual(State(status: "failed", error: "Brak klucza.").line, "Brak klucza.")
        XCTAssertEqual(State(status: "failed", error: "").line, "Nie udało się przygotować studium")
        XCTAssertTrue(State(status: "stopped").isFailed)
        XCTAssertFalse(State(status: "stopped").isActive)
    }

    /// From 1.117.0 the server pushes the part too, and since when and
    /// until when (seconds since 2001, as ActivityKit decodes dates).
    func testThePartAndTheBarDecode() throws {
        let pushed = #"{"status": "writing", "error": "", "part": "composition_check", "startedAt": 800000000, "expectedEnd": 800000210}"#
        let state = try JSONDecoder().decode(State.self, from: Data(pushed.utf8))
        XCTAssertEqual(state.stepIndex, 2)
        XCTAssertEqual(state.line, "Sprawdzam ślady")
        XCTAssertEqual(state.timerRange, Date(timeIntervalSinceReferenceDate: 800_000_000)...Date(timeIntervalSinceReferenceDate: 800_000_210))
        XCTAssertEqual(state.aboutWhole, "z ok. 3½ min")
        // Each part has its line and its step.
        for part in State.stepOfPart.keys { XCTAssertNotNil(State.partLines[part], part) }
        XCTAssertEqual(State(status: "writing", part: "text").stepIndex, 1)
        XCTAssertEqual(State(status: "details", part: "later").stepIndex, 3)
        // Waiting for Claude: no bar.
        XCTAssertNil(State(status: "waiting", part: "waiting").timerRange)
        XCTAssertEqual(State(status: "waiting", part: "waiting").line, "Zaraz zabieram się do pracy")
    }

    func testTimeLeftInWords() {
        XCTAssertEqual(State.about(20), "1 min")
        XCTAssertEqual(State.about(80), "1½ min")
        XCTAssertEqual(State.about(125), "2 min")
        let start = Date(timeIntervalSinceReferenceDate: 0)
        let state = State(status: "writing", part: "text", startedAt: start, expectedEnd: start.addingTimeInterval(200))
        XCTAssertEqual(
            AppModel.studyDetail("Ul", state: state, now: start.addingTimeInterval(110)), "„Ul” · jeszcze ok. 1½ min"
        )
        XCTAssertEqual(AppModel.studyDetail("Ul", state: state, now: start.addingTimeInterval(230)), "„Ul” · trwa dłużej niż zwykle")
        XCTAssertEqual(AppModel.studyDetail("Ul", state: State(status: "writing")), "„Ul” · zwykle 1–3 minuty")
    }

    /// A tap on the finished card opens the study, as the notification does.
    func testTheCardOpensTheStudy() throws {
        let url = StudyActivityAttributes(itemID: "met:7", title: "Ul").url
        XCTAssertEqual(url.scheme, "com.artrybka.frame")
        let route = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first { $0.name == "route" }
        XCTAssertEqual(route?.value, "study/met:7")
    }
}
