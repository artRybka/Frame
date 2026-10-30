import XCTest
@testable import Frame

final class PresentationPreviewTests: XCTestCase {
    private func presentation(_ fit: String, margin: Double = 0.07) -> Presentation {
        Presentation(preset: "photo", fit: fit, margin: margin, label: false)
    }

    func testTheSketchKeepsEveryWindowOnTheMat() {
        for portrait in [false, true] {
            let size = portrait ? CGSize(width: 90, height: 160) : CGSize(width: 160, height: 90)
            let canvas = CGRect(origin: .zero, size: size)
            for fit in ["fit", "fill", "description", "multi"] {
                let layout = PreviewLayout(portrait: portrait, presentation: presentation(fit))
                let (windows, lines) = LayoutSketch.parts(of: layout, in: size)
                XCTAssertFalse(windows.isEmpty, fit)
                for rect in windows + lines {
                    XCTAssertTrue(canvas.contains(rect), "\(fit) \(portrait): \(rect)")
                    XCTAssertGreaterThan(rect.width, 0, fit)
                    XCTAssertGreaterThan(rect.height, 0, fit)
                }
            }
        }
    }

    func testAMultiBoardSketchesTheChosenGrid() {
        var multi = presentation("multi")
        multi.multiCount = 5
        multi.multiGrid = "B"
        let layout = PreviewLayout(portrait: false, presentation: multi)
        XCTAssertEqual(layout.grid?.name, "Pion i cztery")
        XCTAssertEqual(LayoutSketch.parts(of: layout, in: CGSize(width: 160, height: 90)).windows.count, 5)
        multi.multiGrid = "auto"
        XCTAssertEqual(PreviewLayout(portrait: false, presentation: multi).grid?.id, "A")
    }

    func testOnlyTheBoardsShapeDecidesWhetherAPictureMayStay() {
        var photo = presentation("fit")
        let before = PreviewLayout(portrait: true, presentation: photo)
        photo.mat = "black"
        photo.margin = 0.12
        XCTAssertEqual(PreviewLayout(portrait: true, presentation: photo).shape, before.shape)
        XCTAssertNotEqual(PreviewLayout(portrait: false, presentation: photo).shape, before.shape)
        photo.fit = "fill"
        XCTAssertNotEqual(PreviewLayout(portrait: true, presentation: photo).shape, before.shape)
    }
}
