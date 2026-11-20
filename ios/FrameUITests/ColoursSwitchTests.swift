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
        try? FileManager.default.createDirectory(atPath: Self.folder, withIntermediateDirectories: true)
        let app = XCUIApplication()
        app.launchArguments = ["-demo", "YES", "-screen", "original", "-paintStyle", "oil", "-demoSlowServer", "4"]
        app.launch()
        let button = app.buttons["Korekta barw"]
        XCTAssertTrue(button.waitForExistence(timeout: 40), "no colours button on the viewer")
        sleep(6)  // the picture shown in full, the other made from it
        let before = shot("1-before")
        XCTAssertEqual(button.value as? String, "ukryta")

        button.tap()
        usleep(900_000)
        let switched = shot("2-just-after-tap")
        XCTAssertEqual(button.value as? String, "widoczna")
        let moved = Self.apart(before, switched)
        XCTAssertGreaterThan(moved, 4, "the picture did not change within a second of the tap")

        sleep(6)  // the slow server has answered
        let answered = shot("3-server-answered")
        XCTAssertLessThan(Self.apart(switched, answered), 1.5, "the picture changed again when the server answered")
        XCTAssertEqual(button.value as? String, "widoczna")

        button.tap()
        usleep(900_000)
        let back = shot("4-back")
        XCTAssertEqual(button.value as? String, "ukryta")
        XCTAssertLessThan(Self.apart(before, back), 1.5, "the picture did not come back as it was")

        // Quick taps: the last one wins, the server too.
        button.tap()
        button.tap()
        button.tap()
        sleep(14)
        let settled = shot("5-three-taps-settled")
        XCTAssertEqual(button.value as? String, "widoczna")
        XCTAssertLessThan(Self.apart(switched, settled), 1.5)
        Self.log("moved \(moved)")
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
    private static func apart(_ a: UIImage, _ b: UIImage) -> Double {
        guard let x = levels(a), let y = levels(b), x.count == y.count, !x.isEmpty else { return -1 }
        let sum = zip(x, y).reduce(0) { $0 + abs(Int($1.0) - Int($1.1)) }
        return Double(sum) / Double(x.count)
    }

    private static func levels(_ image: UIImage) -> [UInt8]? {
        guard let source = image.cgImage else { return nil }
        let width = 60, height = 40
        let crop = CGRect(
            x: Double(source.width) * 0.2, y: Double(source.height) * 0.35,
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
        FileManager.default.createFile(atPath: "\(folder)/colours.log", contents: Data((line + "\n").utf8))
    }
}
