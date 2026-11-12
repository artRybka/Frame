import SwiftUI
import XCTest
@testable import Frame

/// The study sheet an image model draws for an analysis of composition
/// (Mateusz 2026-11-12 22:14: "Jest świetnie. Wdrażamy."): what the server
/// sends of it, which line gets which colour and number, what a tap puts
/// away, and Google's key in Konfiguracja.
final class DrawnSheetTests: XCTestCase {
    private typealias Spot = DailyWork.Spot
    private typealias Mark = DailyWork.Mark

    private let take = DailyWork.Take(
        title: "Analiza kompozycji", grid: "golden", text: "",
        marks: [
            Mark(shape: "triangle", points: [Spot(x: 0.4, y: 0.2), Spot(x: 0.4, y: 0.6), Spot(x: 0.55, y: 0.6)], title: "Żagiel", text: "dominanta"),
            Mark(shape: "line", points: [Spot(x: 0.1, y: 0.9), Spot(x: 0.9, y: 0.9)], title: "", text: ""),
            Mark(shape: "line", points: [Spot(x: 0.02, y: 0.55), Spot(x: 0.98, y: 0.55)], title: "Horyzont", text: "dzieli obraz"),
            Mark(shape: "loop", points: [Spot(x: 0.74, y: 0.21), Spot(x: 0.82, y: 0.32)], title: "Słońce", text: "akcent"),
        ]
    )

    func testTheServersDrawnSheetIsRead() throws {
        let json = #"""
        {"sheet": "/api/composition/drawn?item=met%3A1&v=ab12&part=page", "bleed": 0.08, "aspect": 1.5,
         "marks": [
          {"mark": 0, "layer": "/api/composition/drawn?item=met%3A1&v=ab12&part=m1", "colour": "#be4031",
           "numbers": [{"x": 0.41, "y": 0.3}]},
          {"mark": 2, "layer": "", "colour": "#394f98", "numbers": []},
          {"mark": 3, "layer": "/api/composition/drawn?item=met%3A1&v=ab12&part=m3", "colour": "#287b3f",
           "numbers": [{"x": 0.8, "y": 0.12}, {"x": 0.7, "y": 0.3}]}
         ]}
        """#
        let drawn = try LiveBackend.decoder().decode(DailyWork.Drawn.self, from: Data(json.utf8))
        XCTAssertEqual(drawn.bleed, 0.08)
        XCTAssertEqual(drawn.marks.map(\.mark), [0, 2, 3])
        XCTAssertEqual(drawn.marks[2].numbers.count, 2)

        let lines = DrawnSheet.lines(take, drawn)
        XCTAssertEqual(lines.count, 4)
        // Numbered as the notes are: the marks with a title, in their order.
        XCTAssertEqual(lines.map(\.number), [1, nil, 2, 3])
        // The model's own line where it drew one; a mark it left out, and
        // one it was not asked for, are drawn here.
        XCTAssertEqual(lines[0].layer, .path("/api/composition/drawn?item=met%3A1&v=ab12&part=m1"))
        XCTAssertNil(lines[1].layer)
        XCTAssertNil(lines[2].layer)
        XCTAssertNotNil(lines[3].layer)
        // Each in its own colour (the one it was not asked for in graphite).
        XCTAssertEqual(lines[0].colour, Color(hexString: "#be4031"))
        XCTAssertEqual(lines[2].colour, Color(hexString: "#394f98"))
        XCTAssertEqual(lines[1].colour, Pencil.lead)
        XCTAssertEqual(Set(lines.map(\.colour)).count, 4)

        // The numbers stand where the server found room on the line; on a
        // line drawn here, where the app puts them.
        let size = CGSize(width: 300, height: 200)
        XCTAssertEqual(DrawnSheet.spots(of: lines[0], in: size), [CGPoint(x: 0.41 * 300, y: 0.3 * 200)])
        XCTAssertEqual(DrawnSheet.spots(of: lines[3], in: size).count, 2)
        XCTAssertEqual(DrawnSheet.spots(of: lines[2], in: size), [Pencil.numberSpot(for: lines[2].mark, in: size)])
    }

    func testATapOnTheSheetPutsTheLinesAwayAndATappedNoteLeavesItsOwn() throws {
        let drawn = DailyWork.Drawn(sheet: "/s", bleed: 0.08, aspect: 1.5, marks: [
            .init(mark: 0, layer: "/m1", colour: "#be4031", numbers: []),
            .init(mark: 2, layer: "/m2", colour: "#394f98", numbers: []),
        ])
        let lines = DrawnSheet.lines(take, drawn)
        // As drawn: every line whole.
        XCTAssertEqual(lines.map { DrawnSheet.share(of: $0, chosen: nil, bare: false) }, [1, 1, 1, 1])
        // The sheet tapped: the sketch alone (20:54: "po dotknięciu
        // zostaje sam szkic").
        XCTAssertEqual(lines.map { DrawnSheet.share(of: $0, chosen: nil, bare: true) }, [0, 0, 0, 0])
        XCTAssertEqual(lines.map { DrawnSheet.share(of: $0, chosen: 2, bare: true) }, [0, 0, 0, 0])
        // A note tapped: its line stays, the others step back.
        XCTAssertEqual(
            lines.map { DrawnSheet.share(of: $0, chosen: 2, bare: false) },
            [Chalk.aside, Chalk.aside, 1, Chalk.aside]
        )
    }

    func testTheGridsNameIsWrittenOnTheSheet() {
        XCTAssertEqual(DrawnSheet.gridName("golden"), "złoty podział")
        XCTAssertEqual(DrawnSheet.gridName("halves"), "osie")
        XCTAssertEqual(DrawnSheet.gridName("thirds"), "trójpodział")
        XCTAssertNil(DrawnSheet.gridName("none"))
    }

    func testThePageSaysWhenItsSheetIsBeingDrawn() async throws {
        let demo = DemoBackend()
        let work = try await demo.daily(day: nil, wait: 0, lists: false)
        XCTAssertNil(work.compositionDrawn)  // only when asked for (`-demoDrawn YES`)
        XCTAssertNil(work.compositionDrawnPending)
        // As the server sends a page whose sheet is on its way.
        let data = try LiveBackend.encoder().encode(work)
        var raw = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        raw["composition_drawn_pending"] = true
        let sent = try JSONSerialization.data(withJSONObject: raw)
        let pending = try LiveBackend.decoder().decode(DailyWork.self, from: sent)
        XCTAssertEqual(pending.compositionDrawnPending, true)
        XCTAssertNil(pending.compositionDrawn)
        // What is written above the field: whose work and which.
        XCTAssertEqual(DailyView.sheetTitle(work), "\(work.item.item.artist), \(work.title)")
    }

    func testTheDemoHasAStandInForTheModelsSheet() async throws {
        let demo = DemoBackend()
        let work = try await demo.daily(day: nil, wait: 0, lists: false)
        let shown = try XCTUnwrap(work.composition?.views?.first)
        let drawn = try XCTUnwrap(DemoStudies.drawn(shown, id: work.item.id))
        XCTAssertEqual(drawn.bleed, DemoStudies.bleed)
        let titled = shown.marks.filter { !$0.title.isEmpty }
        XCTAssertEqual(drawn.marks.count, titled.count)
        XCTAssertEqual(Set(drawn.marks.map(\.colour)).count, titled.count)
        // The study: wider than the field by the margin on each side.
        let page = try XCTUnwrap(demo.request(for: .path(drawn.sheet))?.url)
        let picture = try XCTUnwrap(UIImage(contentsOfFile: page.path))
        XCTAssertEqual(Double(picture.size.width / picture.size.height), drawn.aspect * (1 + 2 * drawn.bleed), accuracy: 0.01)
        // A line: the field's shape, clear but for the pencil.
        let first = try XCTUnwrap(drawn.marks.first)
        XCTAssertFalse(first.layer.isEmpty)
        XCTAssertFalse(first.numbers.isEmpty)
        let layerURL = try XCTUnwrap(demo.request(for: .path(first.layer))?.url)
        let layer = try XCTUnwrap(UIImage(contentsOfFile: layerURL.path)?.cgImage)
        XCTAssertEqual(Double(layer.width) / Double(layer.height), drawn.aspect, accuracy: 0.01)
        let covered = try Self.covered(layer)
        XCTAssertGreaterThan(covered, 0.001)
        XCTAssertLessThan(covered, 0.2)
        // The last mark is one the model left out: the app draws it.
        if drawn.marks.count > 1 {
            XCTAssertEqual(drawn.marks.last?.layer, "")
            XCTAssertNil(DrawnSheet.lines(shown, drawn).last { $0.number != nil }?.layer)
        }
    }

    /// How much of a picture is not clear.
    private static func covered(_ image: CGImage) throws -> Double {
        let width = image.width, height = image.height
        var bytes = [UInt8](repeating: 0, count: width * height * 4)
        let space = CGColorSpaceCreateDeviceRGB()
        let context = try XCTUnwrap(CGContext(
            data: &bytes, width: width, height: height, bitsPerComponent: 8, bytesPerRow: width * 4,
            space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ))
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        let inked = stride(from: 3, to: bytes.count, by: 4).reduce(0) { $0 + (bytes[$1] > 128 ? 1 : 0) }
        return Double(inked) / Double(width * height)
    }

    func testGooglesKeyAndTheSwitchInKonfiguracja() async throws {
        let json = #"""
        {"key_set": true, "key_tail": "abcd", "key_from_app": true, "pl_text": true,
         "keywords_artworks": true, "keywords_photos": false, "monthly_limit_usd": 5, "spent_usd": 1.2,
         "spent_by_kind": {"sheet": 0.45},
         "keywords_progress": {"done": 0, "waiting": 0, "refused": 0, "batch_items": 0, "batch_done": 0, "preparing": false},
         "error": null,
         "gemini_key_set": true, "gemini_key_tail": "wxyz", "drawn": true, "drawn_usd": 0.15,
         "drawn_batch_usd": 0.075, "drawn_waiting": 8, "drawn_in_batch": 20, "gemini_error": null}
        """#
        var settings = try LiveBackend.decoder().decode(AiSettings.self, from: Data(json.utf8))
        XCTAssertEqual(settings.geminiKeyTail, "wxyz")
        XCTAssertEqual(settings.drawnInBatch, 20)
        // The saved studies' sheets go through the Batch: how many, about how much.
        var note = try XCTUnwrap(AiSection.drawnNote(settings, on: true))
        XCTAssertTrue(note.text.contains("28"))
        XCTAssertTrue(note.text.contains("w Batch: 20"))
        XCTAssertTrue(note.text.contains(Money.usd(2.1)))
        XCTAssertFalse(note.bad)
        XCTAssertTrue(AiSection.drawnHint(settings).contains(Money.usd(0.15)))
        // What stands in the way is said.
        settings.geminiError = "no_credit"
        note = try XCTUnwrap(AiSection.drawnNote(settings, on: true))
        XCTAssertTrue(note.bad)
        XCTAssertTrue(note.text.contains("środki"))
        settings.geminiError = nil
        settings.geminiKeySet = false
        XCTAssertEqual(AiSection.drawnNote(settings, on: true)?.icon, "key")
        XCTAssertNil(AiSection.drawnNote(settings, on: false))
        settings.geminiKeySet = true
        settings.drawnWaiting = 0
        settings.drawnInBatch = 0
        XCTAssertNil(AiSection.drawnNote(settings, on: true))
        // A server from before the drawn sheets: no switch, no key field.
        let older = try LiveBackend.decoder().decode(
            AiSettings.self, from: Data(json.replacingOccurrences(of: "\"gemini_key_set\": true,", with: "").replacingOccurrences(of: "\"drawn\": true,", with: "").utf8)
        )
        XCTAssertNil(older.geminiKeySet)
        XCTAssertNil(older.drawn)

        // The demo keeps the key as the server does: only its tail comes back.
        let demo = DemoBackend()
        let saved = try await demo.saveGeminiKey(" AIza-test-wxyz ")
        XCTAssertEqual(saved.geminiKeySet, true)
        XCTAssertEqual(saved.geminiKeyTail, "wxyz")
        let gone = try await demo.deleteGeminiKey()
        XCTAssertEqual(gone.geminiKeySet, false)
        XCTAssertNil(gone.geminiKeyTail)
        // The switch goes to the server by its own name.
        let sent = try LiveBackend.encoder().encode(AiSettingsUpdate(drawn: false))
        XCTAssertEqual(String(data: sent, encoding: .utf8), #"{"drawn":false}"#)
    }
}
