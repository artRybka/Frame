import XCTest
@testable import Frame

/// "Kolor i światło" painted in the work's technique (Mateusz 2026-11-11
/// 11:09: „Musielibyśmy stworzyć osobne style malowania dla
/// olejnych/akrylu/tempery razem i dla kolorowych szkiców - tak żeby
/// paleta odpowiadała rzeczywistej technice dzieła”).
final class PaintTests: XCTestCase {
    private func shares(_ list: [(String, Double)]) -> [PaintShare] {
        list.map { PaintShare(rgb: Paint.rgb($0.0) ?? [0, 0, 0], weight: $0.1) }
    }

    private var jatte: [PaintShare] {
        shares([("#7C8F45", 0.28), ("#49603A", 0.19), ("#C9B36B", 0.15), ("#3F4A78", 0.13), ("#D8824A", 0.11), ("#A8463A", 0.08),
                ("#E4D8B4", 0.06)])
    }

    /// The pixel at a point of the bar (from its upper left corner).
    private func pixel(_ x: Double, _ y: Double) -> (Int, Int) {
        (Int((x + Paint.pad) * Double(Paint.scale)), Int((y + Paint.pad) * Double(Paint.scale)))
    }

    private func covered(_ frame: PaintFrame) -> Double {
        var sum = 0.0
        for k in 0..<(frame.wide * frame.high) { sum += Double(frame.bytes[4 * k + 3]) / 255 }
        return sum
    }

    func testTheMediumNamesTheWayItIsPainted() {
        let oil = ["Oil on canvas", "olej na płótnie", "Huile sur toile", "Öl auf Leinwand", "olieverf op doek", "Olio su tela",
                   "Tempera and gold on wood", "Acrylic on canvas", "akryl, płótno", "Oil and tempera on panel"]
        let water = ["Watercolor over graphite", "akwarela, papier", "Gouache et aquarelle", "Aquarell auf Papier", "gwasz, tektura",
                     "Watercolour with pen and ink", "tusz, akwarela, papier"]
        let dry = ["pastel on paper", "kredka, papier", "black chalk", "Pastel over watercolour", "pastel, papier naklejony na tekturę",
                   "Red chalk on laid paper", "kreda, papier"]
        // Prints, photographs, ink, and whatever names no paint: flat.
        let flat = ["Color woodblock print; ink and color on paper", "Pen and brown ink, brown wash, over black chalk",
                    "litografia barwna", "Gelatin silver print", "Oil print", "", "Ink and color on silk", "Etching and aquatint",
                    "Bronze", "Colour lithograph after a pastel", "drzeworyt barwny"]
        for text in oil { XCTAssertEqual(PaintStyle.of(medium: text), .oil, text) }
        for text in water { XCTAssertEqual(PaintStyle.of(medium: text), .water, text) }
        for text in dry { XCTAssertEqual(PaintStyle.of(medium: text), .dry, text) }
        for text in flat { XCTAssertNil(PaintStyle.of(medium: text), text) }
        // What kind of thing it is counts too: a print is no painting.
        XCTAssertNil(PaintStyle.of(medium: "oil colours on paper", classification: "Prints"))
        XCTAssertEqual(PaintStyle.of(medium: "Oil on canvas", classification: "Paintings"), .oil)
    }

    func testTheNoiseIsTheSameEachTimeAndStaysInItsBounds() {
        for k in 0..<400 {
            let x = Double(k) * 0.37 - 30, y = Double(k) * 0.91 - 70
            let value = Paint.noise(x, y, 41)
            XCTAssertGreaterThanOrEqual(value, 0)
            XCTAssertLessThanOrEqual(value, 1)
            XCTAssertEqual(value, Paint.noise(x, y, 41))
        }
        var one = PaintRandom(22), two = PaintRandom(22)
        for _ in 0..<50 {
            let value = one.next()
            XCTAssertEqual(value, two.next())
            XCTAssertGreaterThanOrEqual(value, 0)
            XCTAssertLessThan(value, 1)
        }
        XCTAssertEqual(Paint.rgb("#7C8F45") ?? [], [124, 143, 69])
        XCTAssertNil(Paint.rgb("zielony"))
        XCTAssertEqual(Paint.seed("met-436535"), Paint.seed("met-436535"))
        XCTAssertTrue((1...60).contains(Paint.seed("met-436535")))
    }

    func testWatercolourFillsEachColoursShareAndIsStillWhenDry() {
        let strip = WaterStrip(shares: jatte, width: 350, seed: 5)
        XCTAssertEqual(strip.wide, 382 * Paint.scale)
        XCTAssertEqual(strip.high, 58 * Paint.scale)
        XCTAssertEqual(covered(strip.frame(age: 0)), 0)
        // Half a second in only the first stroke is down.
        let early = strip.frame(age: 0.3)
        let spans = WaterStrip.spans(jatte, width: 350)
        XCTAssertGreaterThan(early.cover(pixel(20, 13).0, pixel(20, 13).1), 0.8)
        XCTAssertEqual(early.cover(pixel(spans[3].0 + 10, 13).0, pixel(spans[3].0 + 10, 13).1), 0)
        let dry = strip.frame(age: strip.length)
        for (i, span) in spans.enumerated() {
            let at = pixel((span.0 + span.1) / 2, 13)
            XCTAssertGreaterThan(dry.cover(at.0, at.1), 0.85, "colour \(i)")
            let colour = dry.colour(at.0, at.1)
            XCTAssertEqual(colour.red, jatte[i].rgb[0], accuracy: 45, "colour \(i)")
            XCTAssertEqual(colour.green, jatte[i].rgb[1], accuracy: 45, "colour \(i)")
            XCTAssertEqual(colour.blue, jatte[i].rgb[2], accuracy: 45, "colour \(i)")
        }
        // Nothing far off the bar, and nothing changes once it is dry.
        XCTAssertEqual(dry.cover(2, 2), 0)
        XCTAssertEqual(strip.frame(age: 999).bytes, dry.bytes)
    }

    func testOilIsAPullOfTheBrushForEachColourOneAfterAnother() {
        let pulls = OilStrip.pulls(jatte, width: 350, seed: 5)
        XCTAssertEqual(pulls.count, jatte.count)
        for (before, after) in zip(pulls, pulls.dropFirst()) {
            // Each a little over the one before (12:02: „Mogą na siebie trochę nachodzić”).
            XCTAssertEqual(after.a, before.e + OilStrip.gap, accuracy: 0.001)
        }
        XCTAssertLessThanOrEqual(pulls[pulls.count - 1].e, 350)
        // The small shares are touches of the brush (12:12: „Przy
        // mniejszych - muśnięcia / pacnięcia”), never too narrow to see.
        XCTAssertFalse(pulls[0].touch)
        XCTAssertTrue(pulls[6].touch)
        for pull in pulls { XCTAssertGreaterThanOrEqual(pull.e - pull.a, OilStrip.least - 0.001) }

        let strip = OilStrip(shares: jatte, width: 350, seed: 5, dark: false)
        XCTAssertEqual(covered(strip.frame(age: 0)), 0)
        let early = strip.frame(age: 0.45)
        let first = pixel(pulls[0].a + 8, 13), third = pixel(pulls[2].a + 8, 13)
        XCTAssertGreaterThan(early.cover(first.0, first.1), 0.9)
        XCTAssertEqual(early.cover(third.0, third.1), 0)
        let done = strip.frame(age: strip.length)
        for (i, pull) in pulls.enumerated() {
            // Where the brush came down the paint is full and of its colour, a little lighter or darker in the light.
            let at = pixel(pull.a + 8, 13 + pull.dy)
            XCTAssertGreaterThan(done.cover(at.0, at.1), 0.9, "pull \(i)")
        }
        let colour = done.colour(first.0, first.1)
        XCTAssertEqual(colour.green, jatte[0].rgb[1], accuracy: 60)
        XCTAssertGreaterThan(colour.green, colour.blue + 30)
        XCTAssertGreaterThan(covered(done), covered(early) * 2)
        XCTAssertEqual(strip.frame(age: 999).bytes, done.bytes)
        // On a dark page the same paint, with a deeper shadow under it.
        let dark = OilStrip(shares: jatte, width: 350, seed: 5, dark: true).frame(age: 99)
        XCTAssertEqual(dark.cover(first.0, first.1), done.cover(first.0, first.1), accuracy: 0.01)
        XCTAssertGreaterThan(covered(dark), covered(done))
    }

    func testAPaintTheSourcesDoNotNameIsASmallerSwatch() {
        let rgb = Paint.rgb("#3B4FA0") ?? [0, 0, 0]
        let sure = OilDab(rgb: rgb, sure: true, index: 0, seed: 5, dark: false), likely = OilDab(rgb: rgb, sure: false, index: 0, seed: 5, dark: false)
        XCTAssertEqual(covered(sure.frame(age: 0)), 0)
        XCTAssertGreaterThan(covered(sure.frame(age: 99)), covered(likely.frame(age: 99)) * 1.4)
        XCTAssertGreaterThan(covered(sure.frame(age: 99)), covered(sure.frame(age: 0.2)))
        let middle = sure.frame(age: 99).colour(sure.wide / 2, sure.high / 2)
        XCTAssertGreaterThan(middle.blue, middle.red + 40)
        let wet = WaterDab(rgb: rgb, sure: true, index: 0, seed: 5), thin = WaterDab(rgb: rgb, sure: false, index: 0, seed: 5)
        XCTAssertEqual(covered(wet.frame(age: 0)), 0)
        XCTAssertGreaterThan(covered(wet.frame(age: 99)), covered(thin.frame(age: 99)) * 1.15)
        XCTAssertEqual(wet.frame(age: 99).bytes, wet.frame(age: wet.length).bytes)
    }

    func testPastelIsHatchedColourByColour() {
        let plan = DryPlan(shares: jatte, width: 350, seed: 5)
        for i in jatte.indices { XCTAssertGreaterThanOrEqual(plan.strokes.filter { $0.colour == i }.count, 4, "colour \(i)") }
        for stroke in plan.strokes {
            XCTAssertLessThanOrEqual(plan.made(stroke, age: 0), 0)
            XCTAssertGreaterThanOrEqual(plan.made(stroke, age: plan.length), 1)
            XCTAssertTrue((0.25...1).contains(stroke.alpha))
        }
        // The first colour's strokes are all begun before the last colour's first.
        let firstDone = plan.strokes.filter { $0.colour == 0 }.map { Double($0.colour) * DryPlan.apart + $0.part * DryPlan.stroke }.max() ?? 0
        XCTAssertLessThan(firstDone, Double(jatte.count - 1) * DryPlan.apart)
        XCTAssertEqual(DryPlan.scribble(sure: true, index: 0, seed: 5).count, 8)
        XCTAssertEqual(DryPlan.scribble(sure: false, index: 0, seed: 5).count, 5)
        let tooth = DryPlan.tooth(wide: 40, high: 40, seed: 5)
        XCTAssertEqual(tooth.count, 1600)
        XCTAssertGreaterThanOrEqual(tooth.min() ?? 0, 96)
        XCTAssertGreaterThan(tooth.max() ?? 0, 240)
    }

    func testThePaintsComeAfterTheBarOneAfterAnother() {
        for style in PaintStyle.allCases {
            // With no bar the first is there at once.
            XCTAssertEqual(style.swatchDelay(colours: 0, index: 0), 0)
            XCTAssertGreaterThan(style.swatchDelay(colours: 0, index: 1), 0.2)
            let first = style.swatchDelay(colours: 7, index: 0)
            XCTAssertGreaterThan(style.swatchDelay(colours: 7, index: 1), first + 0.2)
            XCTAssertGreaterThan(first, style.swatchDelay(colours: 3, index: 0))
        }
        // After the bar's last stroke is down.
        XCTAssertGreaterThan(PaintStyle.oil.swatchDelay(colours: 7, index: 0), OilStrip(shares: jatte, width: 350, seed: 5, dark: false).last)
        XCTAssertGreaterThan(PaintStyle.water.swatchDelay(colours: 7, index: 0), WaterStrip(shares: jatte, width: 350, seed: 5).last)
        XCTAssertGreaterThan(PaintStyle.dry.swatchDelay(colours: 7, index: 0), DryPlan(shares: jatte, width: 350, seed: 5).last)
    }
}
