import XCTest

/// Galeria's ways between the whole screen and the grid, with a finger, on
/// the simulator (Mateusz 2026-11-24 17:23: "Powrót z siatki … bardzo
/// skacze. To nie wygląda dobrze"): every one of them is gone through
/// while the `gallery-probe` run of ios-screenshots.yml films the screen,
/// so each can be looked at frame by frame before a release. What the app
/// did and when (`GalleryLog`), the times of the steps here and a
/// screenshot after each go to /tmp/frame-gallery/.
final class GalleryProbeTests: XCTestCase {
    private static let folder = "/tmp/frame-gallery"

    @MainActor
    func testTheWaysBetweenTheTwoViews() throws {
        try? FileManager.default.createDirectory(atPath: Self.folder, withIntermediateDirectories: true)
        let app = XCUIApplication()
        app.launchArguments = ["-demo", "YES", "-screen", "gallery", "-galleryLog", "\(Self.folder)/gallery.log"]
        app.launch()
        sleep(9)
        let window = app.windows.firstMatch
        func at(_ x: CGFloat, _ y: CGFloat) -> XCUICoordinate {
            window.coordinate(withNormalizedOffset: CGVector(dx: x, dy: y))
        }
        func swipe(from: XCUICoordinate, to: XCUICoordinate) {
            from.press(forDuration: 0.05, thenDragTo: to, withVelocity: .fast, thenHoldForDuration: 0)
        }
        mark(app, "started")
        shot("01-start")

        // The next work, twice, from where a thumb lies.
        for _ in 0 ..< 3 {
            swipe(from: at(0.5, 0.78), to: at(0.5, 0.35))
            sleep(2)
        }
        mark(app, "three swipes up")
        shot("02-fourth-work")

        // A swipe down from the lower part: the work before.
        swipe(from: at(0.5, 0.62), to: at(0.5, 0.92))
        sleep(2)
        mark(app, "swipe down, low: the work before")
        shot("03-work-before")

        // A swipe down from the upper part: the grid.
        swipe(from: at(0.5, 0.14), to: at(0.5, 0.44))
        sleep(3)
        mark(app, "swipe down, high: the grid")
        shot("04-grid")

        // A tile tapped: that work.
        at(0.83, 0.5).tap()
        sleep(3)
        mark(app, "tile tapped")
        shot("05-from-a-tile")

        // Two fingers drawn together: the grid.
        window.pinch(withScale: 0.45, velocity: -1.2)
        sleep(3)
        mark(app, "pinched in")
        shot("06-grid-by-pinch")

        // Two fingers spread on a tile: that work.
        window.pinch(withScale: 2.6, velocity: 2)
        sleep(3)
        mark(app, "spread")
        shot("07-from-a-spread")

        // Held: the whole work while the finger lies.
        mark(app, "hold begins")
        at(0.5, 0.55).press(forDuration: 2.2)
        sleep(2)
        mark(app, "held and let go")
        shot("08-after-the-hold")

        // Held and drawn up: the card.
        mark(app, "hold and pull begin")
        at(0.5, 0.6).press(forDuration: 1.2, thenDragTo: at(0.5, 0.42), withVelocity: .slow, thenHoldForDuration: 0.4)
        sleep(4)
        mark(app, "pulled up: the card")
        shot("09-card")
        let back = app.buttons["Wróć"].firstMatch
        if back.waitForExistence(timeout: 5) {
            back.tap()
        } else {
            mark(app, "no back button on the card")
        }
        sleep(3)
        mark(app, "back from the card")
        shot("10-back-from-the-card")

        // A quick run of swipes: the grid, the wall flowing on.
        mark(app, "quick swipes begin")
        for _ in 0 ..< 10 {
            swipe(from: at(0.5, 0.8), to: at(0.5, 0.3))
        }
        sleep(4)
        mark(app, "quick swipes done")
        shot("11-after-quick-swipes")
    }

    /// The same run of swipes made by the app itself (`-gallerySweep`),
    /// each a quarter of a second: the test's finger waits for the app to
    /// rest between swipes and may be too slow for a quick run.
    @MainActor
    func testTheSweepByItself() throws {
        try? FileManager.default.createDirectory(atPath: Self.folder, withIntermediateDirectories: true)
        let app = XCUIApplication()
        app.launchArguments = [
            "-demo", "YES", "-screen", "gallery", "-gallerySweep", "YES",
            "-galleryLog", "\(Self.folder)/gallery-sweep.log", "-galleryTrace", "YES",
        ]
        app.launch()
        mark(app, "sweep: launched")
        sleep(14)
        mark(app, "sweep: done")
        shot("12-sweep-by-itself")
        // A tile tapped while nothing moves any more.
        app.windows.firstMatch.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        sleep(3)
        mark(app, "sweep: tile tapped")
        shot("13-from-the-sweep")
    }

    private func shot(_ name: String) {
        let png = XCUIScreen.main.screenshot().pngRepresentation
        FileManager.default.createFile(atPath: "\(Self.folder)/gallery-probe-\(name).png", contents: png)
    }

    /// A step done: when (seconds since 1970, as the film's start is
    /// noted), and whether the tab bar is there (the grid has it).
    private func mark(_ app: XCUIApplication, _ what: String) {
        let line = String(
            format: "%.3f %@ (tab bar %@)\n", Date().timeIntervalSince1970, what,
            app.tabBars.firstMatch.exists ? "shown" : "hidden"
        )
        let path = "\(Self.folder)/gallery-steps.log"
        if let file = FileHandle(forWritingAtPath: path), let data = line.data(using: .utf8) {
            file.seekToEndOfFile()
            file.write(data)
            try? file.close()
        } else {
            FileManager.default.createFile(atPath: path, contents: line.data(using: .utf8))
        }
    }
}
