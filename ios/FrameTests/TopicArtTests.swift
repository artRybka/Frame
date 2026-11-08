import SwiftUI
import XCTest
@testable import Frame

final class TopicArtTests: XCTestCase {
    /// The server's 29 subjects (`vocabulary.py`), all in the demo's terms.
    func testEverySubjectHasADrawing() {
        let subjects = DemoDiscover.terms.filter { $0.kind == "subject" }
        XCTAssertEqual(subjects.count, 29)
        for term in subjects {
            XCTAssertNotNil(TopicArt.drawing(term.key), term.key)
        }
        XCTAssertEqual(TopicArt.drawings.count, 29)
        XCTAssertNotNil(TopicArt.drawing("sea"))
        XCTAssertNil(TopicArt.drawing("subject:unknown"))
    }

    func testDrawingsStayOnTheirGrid() {
        for (key, drawing) in TopicArt.drawings {
            XCTAssertFalse(drawing.layers.isEmpty, key)
            for layer in drawing.layers {
                let box = layer.path.boundingRect
                XCTAssertFalse(layer.path.isEmpty, key)
                XCTAssertGreaterThanOrEqual(box.minX, -0.5, key)
                XCTAssertGreaterThanOrEqual(box.minY, -0.5, key)
                XCTAssertLessThanOrEqual(box.maxX, 24.5, key)
                XCTAssertLessThanOrEqual(box.maxY, 24.5, key)
            }
            // A colour to fill only where the drawing has one.
            let tinted = drawing.layers.contains { $0.paint == .tint }
            XCTAssertEqual(tinted, drawing.tint != nil, key)
        }
    }

    func testThePathReaderFollowsTheCommands() {
        let path = TopicArt.path("M2 20 C5 11.5 9.5 11.5 12.5 15.5 L22 20 Z M4 4 L6 6")
        let box = path.boundingRect
        XCTAssertEqual(box.minX, 2, accuracy: 0.01)
        XCTAssertEqual(box.maxX, 22, accuracy: 0.01)
        XCTAssertEqual(box.minY, 4, accuracy: 0.01)
        XCTAssertEqual(box.maxY, 20, accuracy: 0.01)
    }

    /// The line is always black: a dark chip puts the drawing on a disc.
    func testTheDiscIsUnderTheDrawingOnADarkChip() {
        XCTAssertFalse(TopicChip.onDisc(selected: false, dark: false))
        XCTAssertTrue(TopicChip.onDisc(selected: true, dark: false))
        XCTAssertTrue(TopicChip.onDisc(selected: false, dark: true))
        XCTAssertFalse(TopicChip.onDisc(selected: true, dark: true))
    }
}
