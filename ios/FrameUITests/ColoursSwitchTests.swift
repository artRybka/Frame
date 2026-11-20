import XCTest

/// The colours' button on the full-screen viewer, with a finger, on the
/// simulator (Mateusz 2026-11-20: "Nadal działa do niczego. Jest olbrzymie
/// opóźnienie. Zmiana na bez werniksu następuje skokiem… ikona jest już
/// niebieska a obraz zostaje z werniksem… Zastanów się jak to zrobić
/// porządnie i sprawdź przed wydaniem"). The demo's server answers a
/// switch 4 s late (`-demoSlowServer`, as a NAS making the files again):
/// the picture must change within a moment of the tap all the same, stay
/// so when the answer comes, and go back at the next tap. Screenshots of
/// each step go to /tmp/frame-colours/ for the `colours-probe` run of
/// ios-screenshots.yml.
final class ColoursSwitchTests: XCTestCase {
    private static let folder = "/tmp/frame-colours"

    @MainActor
    func testTheColoursSwitchAtOnce() throws {
        try check(["-paintStyle", "oil"], named: "")
    }

    /// The sheet de-yellowed on the phone too (Mateusz 2026-11-20: "A może
    /// warto jednak się pokłonić nad papierem?").
    @MainActor
    func testTheSheetSwitchesAtOnce() throws {
        try check(["-paintStyle", "pen", "-demoPaper", "YES"], named: "paper-")
    }

    /// The card under the full screen takes the switched picture at once
    /// too, not when the slow server has made its own (Mateusz 2026-11-20:
    /// "I miniatury też już tak działają?… Tak. Działajmy.").
    @MainActor
    func testTheCardTakesTheSwitchAtOnce() throws {
        try? FileManager.default.createDirectory(atPath: Self.folder, withIntermediateDirectories: true)
        let app = XCUIApplication()
        app.launchArguments = ["-demo", "YES", "-screen", "original", "-demoSlowServer", "4", "-paintStyle", "oil"]
        app.launch()
        guard let button = Self.find("Korekta barw", in: app, within: 40) else {
            XCTFail("no colours button on the viewer")
            return
        }
        sleep(6)
        let close = app.buttons["Zamknij"].firstMatch
        close.tap()
        sleep(2)
        let before = shot("card-1-before")
        // The card's picture opens the full screen; it has only a hint
        // ("Otwiera obraz na całym ekranie"), no label to find it by, so it
        // is tapped where it sits (upper third, under the toolbar).
        // ("Pokaż oryginał" on the card is the translation toggle.)
        XCTAssertFalse(button.exists, "the full screen did not close")
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.33)).tap()
        XCTAssertTrue(button.waitForExistence(timeout: 10))
        sleep(3)  // the other picture made
        button.tap()
        usleep(900_000)
        close.tap()
        usleep(1_200_000)  // still before the slow server answers
        let after = shot("card-2-after-switch")
        let moved = Self.apart(before, after, top: 0.12)
        XCTAssertGreaterThan(moved, 4, "the card did not take the switched picture at once")
        sleep(6)  // the server has answered
        let answered = shot("card-3-server-answered")
        XCTAssertLessThan(Self.apart(after, answered, top: 0.12), 1.5, "the card changed again when the server answered")
        Self.log("card-moved \(moved)")
    }

    @MainActor
    private func check(_ style: [String], named prefix: String) throws {
        try? FileManager.default.createDirectory(atPath: Self.folder, withIntermediateDirectories: true)
        let app = XCUIApplication()
        app.launchArguments = ["-demo", "YES", "-screen", "original", "-demoSlowServer", "4"] + style
        app.launch()
        func shot(_ name: String) -> UIImage { self.shot(prefix + name) }
        // A toggle (`.isToggle`): XCUITest may have it as a switch or a
        // toggle, not a button. (Asking for any element at all timed out on
        // the whole tree.)
        guard let button = Self.find("Korekta barw", in: app, within: 40) else {
            _ = shot("0-no-button")
            print("--- the tree:\n\(app.debugDescription)")
            XCTFail("no colours button on the viewer")
            return
        }
        sleep(6)  // the picture shown in full, the other made from it
        let before = shot("1-before")
        XCTAssertFalse(Self.on(button))

        button.tap()
        usleep(900_000)
        let switched = shot("2-just-after-tap")
        XCTAssertTrue(Self.on(button))
        let moved = Self.apart(before, switched)
        XCTAssertGreaterThan(moved, 4, "the picture did not change within a second of the tap")

        sleep(6)  // the slow server has answered
        let answered = shot("3-server-answered")
        XCTAssertLessThan(Self.apart(switched, answered), 1.5, "the picture changed again when the server answered")
        XCTAssertTrue(Self.on(button))

        button.tap()
        usleep(900_000)
        let back = shot("4-back")
        XCTAssertFalse(Self.on(button))
        XCTAssertLessThan(Self.apart(before, back), 1.5, "the picture did not come back as it was")

        // Quick taps: the last one wins, the server too.
        button.tap()
        button.tap()
        button.tap()
        sleep(14)
        let settled = shot("5-three-taps-settled")
        XCTAssertTrue(Self.on(button))
        XCTAssertLessThan(Self.apart(switched, settled), 1.5)
        Self.log("\(prefix)moved \(moved)")
    }

    private static func find(_ name: String, in app: XCUIApplication, within seconds: TimeInterval) -> XCUIElement? {
        let until = Date.now.addingTimeInterval(seconds)
        repeat {
            for query in [app.switches, app.toggles, app.buttons] where query[name].exists {
                return query[name].firstMatch
            }
            usleep(500_000)
        } while Date.now < until
        return nil
    }

    /// The button's state, as the value it speaks ("widoczna") or as a
    /// switch's 1.
    private static func on(_ button: XCUIElement) -> Bool {
        let value = button.value.map { "\($0)" } ?? ""
        return value == "widoczna" || value == "1"
    }

    private func shot(_ name: String) -> UIImage {
        let screenshot = XCUIScreen.main.screenshot()
        FileManager.default.createFile(
            atPath: "\(Self.folder)/colours-\(name).png", contents: screenshot.pngRepresentation
        )
        let attachment = XCTAttachment(screenshot: screenshot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
        return screenshot.image
    }

    /// How far apart two screenshots are in the middle of the picture (mean
    /// level difference, 0–255), away from the buttons and the caption.
    private static func apart(_ a: UIImage, _ b: UIImage, top: Double = 0.35) -> Double {
        guard let x = levels(a, top: top), let y = levels(b, top: top), x.count == y.count, !x.isEmpty else { return -1 }
        let sum = zip(x, y).reduce(0) { $0 + abs(Int($1.0) - Int($1.1)) }
        return Double(sum) / Double(x.count)
    }

    private static func levels(_ image: UIImage, top: Double) -> [UInt8]? {
        guard let source = image.cgImage else { return nil }
        let width = 60, height = 40
        let crop = CGRect(
            x: Double(source.width) * 0.2, y: Double(source.height) * top,
            width: Double(source.width) * 0.6, height: Double(source.height) * 0.3
        )
        guard let part = source.cropping(to: crop),
              let context = CGContext(
                  data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: width * 4,
                  space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue
              )
        else { return nil }
        context.draw(part, in: CGRect(x: 0, y: 0, width: width, height: height))
        guard let data = context.data else { return nil }
        let bytes = data.assumingMemoryBound(to: UInt8.self)
        return (0 ..< width * height * 4).filter { $0 % 4 != 3 }.map { bytes[$0] }
    }

    private static func log(_ line: String) {
        let path = "\(folder)/colours.log"
        let data = Data((line + "\n").utf8)
        if let file = FileHandle(forWritingAtPath: path) {
            file.seekToEndOfFile()
            file.write(data)
            try? file.close()
        } else {
            FileManager.default.createFile(atPath: path, contents: data)
        }
    }
}
