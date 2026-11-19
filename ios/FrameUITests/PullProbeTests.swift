import XCTest

/// The pull at the end of "Podobne do", with a finger, on the simulator:
/// what the app measures goes to /tmp/frame-pull.log (`PullProbe`), and a
/// screenshot of each step to /tmp/frame-pull-*.png, for the
/// `pull-probe` run of ios-screenshots.yml.
final class PullProbeTests: XCTestCase {
    private static let folder = "/tmp/frame-pull"

    @MainActor
    func testPullAtTheEnd() throws {
        try? FileManager.default.createDirectory(atPath: Self.folder, withIntermediateDirectories: true)
        let app = XCUIApplication()
        app.launchArguments = ["-demo", "YES", "-screen", "search-like", "-pullLog", "\(Self.folder)/frame-pull.log"]
        app.launch()
        sleep(10)
        shot("1-start")
        let window = app.windows.firstMatch
        for _ in 0 ..< 10 {
            window.swipeUp(velocity: .fast)
            sleep(1)
        }
        sleep(3)
        shot("2-end")
        mark(app, "rested at the end")
        for (step, distance) in [80.0, 160.0, 320.0].enumerated() {
            mark(app, "pull \(Int(distance))")
            let start = window.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.65))
            let end = start.withOffset(CGVector(dx: 0, dy: -distance))
            start.press(forDuration: 0.15, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.8)
            sleep(4)
            shot("\(3 + step)-after-\(Int(distance))")
            for _ in 0 ..< 6 {
                window.swipeUp(velocity: .fast)
                sleep(1)
            }
            sleep(3)
        }
    }

    private func shot(_ name: String) {
        let png = XCUIScreen.main.screenshot().pngRepresentation
        FileManager.default.createFile(atPath: "\(Self.folder)/frame-pull-\(name).png", contents: png)
    }

    private func mark(_ app: XCUIApplication, _ what: String) {
        let line = "--- \(what): footer \(app.buttons["Więcej podobnych"].exists ? "\(app.buttons["Więcej podobnych"].frame)" : "absent")\n"
        let path = "\(Self.folder)/frame-pull.log"
        if let file = FileHandle(forWritingAtPath: path), let data = line.data(using: .utf8) {
            file.seekToEndOfFile()
            file.write(data)
            try? file.close()
        } else {
            FileManager.default.createFile(atPath: path, contents: line.data(using: .utf8))
        }
    }
}
