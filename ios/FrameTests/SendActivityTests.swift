import UIKit
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

    /// A busy painting (noise) still fits the card: ActivityKit keeps a
    /// card's data under 4 KB, picture, title and state together.
    func testTheWorksPictureFitsTheCard() throws {
        let photo = UIGraphicsImageRenderer(size: CGSize(width: 900, height: 600)).image { context in
            var rng = SystemRandomNumberGenerator()
            for x in stride(from: 0, to: 900, by: 6) {
                for y in stride(from: 0, to: 600, by: 6) {
                    UIColor(
                        red: .random(in: 0...1, using: &rng), green: .random(in: 0...1, using: &rng),
                        blue: .random(in: 0...1, using: &rng), alpha: 1
                    ).setFill()
                    context.fill(CGRect(x: x, y: y, width: 6, height: 6))
                }
            }
        }
        let data = try XCTUnwrap(ActivityPicture.data(from: photo))
        XCTAssertLessThanOrEqual(data.count, ActivityPicture.maxBytes)
        let small = try XCTUnwrap(UIImage(data: data))
        XCTAssertEqual(small.size.width / small.size.height, 1.5, accuracy: 0.05)  // its own proportions

        let title = String(repeating: "Peasant Woman Cooking by a Fireplace ", count: 3)
        let attributes = SendActivityAttributes(title: title, picture: data)
        let state = State(stage: "waiting", phase: "loading", label: "Ładowanie obrazu na ramkę",
                          fraction: 0.4, heardAt: .now, expectedEnd: .now, wakes: "jutro o 07:00")
        let size = try JSONEncoder().encode(attributes).count + JSONEncoder().encode(state).count
        XCTAssertLessThan(size, 4096)
        let study = StudyActivityAttributes(itemID: "met:437984", title: title, picture: data)
        XCTAssertLessThan(try JSONEncoder().encode(study).count, 3800)
    }

    /// The server names the work on its way (progress.py `item_id`).
    func testTheProgressNamesItsWork() throws {
        let json = #"{"stage": "rendering", "active": true, "title": "Ul", "fraction": 0.1, "item_id": "met:7"}"#
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        XCTAssertEqual(try decoder.decode(DisplayProgress.self, from: Data(json.utf8)).itemId, "met:7")
    }
}
