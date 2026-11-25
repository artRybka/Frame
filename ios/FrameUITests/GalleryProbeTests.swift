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
        app.launchArguments = [
            "-demo", "YES", "-screen", "gallery", "-galleryLog", "\(Self.folder)/gallery.log", "-galleryTrace", "YES",
        ]
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

        // A finger drawn down slowly from the upper part, all the way, and
        // left lying: the work follows it evenly into its tile, and the
        // grid is there under it (Mateusz 2026-11-25: the work stopped
        // half way and waited for the finger to lift; then, going the
        // rest by itself from there: "w połowie „wskakuje”").
        mark(app, "slow drag down begins")
        at(0.5, 0.14).press(forDuration: 0.05, thenDragTo: at(0.5, 0.58), withVelocity: .slow, thenHoldForDuration: 1.2)
        sleep(2)
        mark(app, "drawn down and held: the grid")
        shot("07b-grid-under-the-finger")
        at(0.5, 0.5).tap()
        sleep(3)
        mark(app, "tile tapped again")

        // Half the way, held there, then let go: it waits under the finger
        // and goes on to the grid when the finger lifts.
        mark(app, "half drag down begins")
        at(0.5, 0.14).press(forDuration: 0.05, thenDragTo: at(0.5, 0.32), withVelocity: .slow, thenHoldForDuration: 1.2)
        sleep(2)
        mark(app, "drawn half way, held, let go: the grid")
        shot("07c-grid-after-half-a-drag")
        at(0.5, 0.5).tap()
        sleep(3)
        mark(app, "tile tapped a third time")

        // The grid's own button on the page's corner.
        let gridButton = app.buttons["Pokaż siatkę"].firstMatch
        if gridButton.waitForExistence(timeout: 3) {
            shot("07d-the-grid-button")
            gridButton.tap()
        } else {
            mark(app, "no grid button on the page")
        }
        sleep(3)
        mark(app, "grid button tapped: the grid")
        shot("07e-grid-by-its-button")
        at(0.5, 0.5).tap()
        sleep(3)
        mark(app, "tile tapped a fourth time")

        // Held: the whole work while the finger lies.
        mark(app, "hold begins")
        at(0.5, 0.55).press(forDuration: 2.2)
        sleep(2)
        mark(app, "held and let go")
        shot("08-after-the-hold")

        // Held as soon as a work is come to, while it still draws back
        // and drifts: the press leaves that as it is (Mateusz 2026-11-25
        // 18:08: "przy przytrzymaniu palca najpierw szuka środka a potem
        // zmniejsza"; the log's "under the finger" lines, frame by frame).
        swipe(from: at(0.5, 0.78), to: at(0.5, 0.35))
        mark(app, "hold at once begins")
        at(0.5, 0.55).press(forDuration: 1.6)
        sleep(2)
        mark(app, "held at once and let go")
        shot("08b-after-the-hold-at-once")

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

        // The card again, and drawn down by its work: back to the whole
        // work under the finger, and to the page once it lifts (Mateusz
        // 2026-11-25 18:12).
        mark(app, "hold and pull begin again")
        at(0.5, 0.6).press(forDuration: 1.2, thenDragTo: at(0.5, 0.42), withVelocity: .slow, thenHoldForDuration: 0.4)
        sleep(4)
        mark(app, "pulled up again: the card")
        mark(app, "card drawn down begins")
        at(0.5, 0.3).press(forDuration: 0.05, thenDragTo: at(0.5, 0.6), withVelocity: .slow, thenHoldForDuration: 1.0)
        sleep(3)
        if back.exists {
            // Not by its work: by the blank beside its artist, then.
            mark(app, "the card stayed; drawn down beside its head")
            at(0.85, 0.64).press(forDuration: 0.05, thenDragTo: at(0.85, 0.89), withVelocity: .slow, thenHoldForDuration: 1.0)
            sleep(3)
        }
        mark(app, back.exists ? "the card stayed again" : "card drawn down and let go: the page")
        shot("10b-back-by-drawing-the-card-down")

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

    /// Thumbnails of another shape than their full pictures (`-galleryStale`,
    /// as one kept from before its work was cut down): the full picture
    /// fades in as itself over the one looked at, and the works coming are
    /// whole before they are seen (Mateusz 2026-11-25: "przeskok, jakby
    /// dzieło zmieniało proporcje i zoom").
    @MainActor
    func testAThumbnailOfAnotherShape() throws {
        try? FileManager.default.createDirectory(atPath: Self.folder, withIntermediateDirectories: true)
        let app = XCUIApplication()
        app.launchArguments = [
            "-demo", "YES", "-screen", "gallery", "-galleryStale", "YES",
            "-galleryLog", "\(Self.folder)/gallery-stale.log", "-galleryTrace", "YES",
        ]
        app.launch()
        mark(app, "stale: launched")
        sleep(7)
        shot("14-stale-first")
        let window = app.windows.firstMatch
        for _ in 0 ..< 3 {
            window.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.78))
                .press(
                    forDuration: 0.05, thenDragTo: window.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.35)),
                    withVelocity: .fast, thenHoldForDuration: 0
                )
            sleep(3)
        }
        mark(app, "stale: three swipes up")
        shot("15-stale-fourth")
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
