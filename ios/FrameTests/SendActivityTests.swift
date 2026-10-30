import XCTest
@testable import Frame

final class SendActivityTests: XCTestCase {
    typealias State = SendActivityAttributes.ContentState

    func testTheBarRunsOnFromWhereItWasHeardToTheExpectedEnd() throws {
        let heard = Date(timeIntervalSinceReferenceDate: 1000)
        let state = State(
            stage: "refreshing", phase: "displaying", label: "", fraction: 0.75,
            heardAt: heard, expectedEnd: heard.addingTimeInterval(30)
        )
        let range = try XCTUnwrap(state.timerRange)
        // A quarter left takes 30 s, so the whole bar spans 120 s.
        XCTAssertEqual(range.upperBound.timeIntervalSince(range.lowerBound), 120, accuracy: 0.001)
        XCTAssertEqual(heard.timeIntervalSince(range.lowerBound) / 120, 0.75, accuracy: 0.001)
    }

    func testNoMovingBarWhenDoneWaitingOrWithoutAnEstimate() {
        let heard = Date.now
        let end = heard.addingTimeInterval(30)
        XCTAssertNil(State(stage: "done", label: "", fraction: 1, heardAt: heard, expectedEnd: end).timerRange)
        XCTAssertNil(State(stage: "waiting", label: "", fraction: 0.4, heardAt: heard, expectedEnd: end).timerRange)
        XCTAssertNil(State(stage: "rendering", label: "", fraction: 0.1, heardAt: heard).timerRange)
        XCTAssertNil(State(stage: "rendering", label: "", fraction: 0.1, heardAt: heard, expectedEnd: heard).timerRange)
    }

    func testStateFromTheServersProgress() {
        let progress = DisplayProgress(
            stage: "downloading", phase: "loading", active: true, title: "Fala", fraction: 0.4, secondsLeft: 50
        )
        let state = State(progress)
        XCTAssertEqual(state.label, "Ramka pobiera obraz")
        XCTAssertEqual(state.phaseIndex, 1)
        XCTAssertEqual(state.expectedEnd?.timeIntervalSince(state.heardAt) ?? 0, 50, accuracy: 0.5)
        let done = State(DisplayProgress(stage: "done", active: false, title: "Fala", fraction: 0.97))
        XCTAssertEqual(done.fraction, 1)
        XCTAssertNil(done.expectedEnd)
    }
}
