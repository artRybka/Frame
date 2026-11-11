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
        // A museum that names no paint (the Getty: only "Painting";
        // Mateusz 13:50: „może w takiej sytuacji da jednak jakoś radę
        // ustalić ze to obraz olejny”): a painting is in oil, unless its
        // medium says what else it is; canvas is painted in oil.
        XCTAssertEqual(PaintStyle.of(medium: "", classification: "Painting"), .oil)
        XCTAssertEqual(PaintStyle.of(medium: "", classification: "Malarstwo"), .oil)
        XCTAssertEqual(PaintStyle.of(medium: "wood", classification: "Paintings"), .oil)
        XCTAssertEqual(PaintStyle.of(medium: "canvas"), .oil)
        XCTAssertEqual(PaintStyle.of(medium: "płótno"), .oil)
        XCTAssertEqual(PaintStyle.of(medium: "Watercolor", classification: "Paintings"), .water)
        XCTAssertNil(PaintStyle.of(medium: "Ink and color on silk", classification: "Paintings"))
        XCTAssertNil(PaintStyle.of(medium: "paper", classification: "Paintings"))
        XCTAssertNil(PaintStyle.of(medium: "fresco", classification: "Paintings"))
        XCTAssertNil(PaintStyle.of(medium: "", classification: "Drawing"))
        XCTAssertNil(PaintStyle.of(medium: "", classification: "Photograph"))
        XCTAssertNil(PaintStyle.of(medium: "", classification: "Illuminated Manuscript"))
        XCTAssertNil(PaintStyle.of(medium: "", classification: ""))
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

    /// The colour about a point of the bar, 0…255 each: the mean of a few pixels, so that no one bristle's streak decides.
    private func colour(_ frame: PaintFrame, _ x: Double, _ y: Double) -> (red: Double, green: Double, blue: Double) {
        var sum = (0.0, 0.0, 0.0), count = 0.0
        for dy in stride(from: -3.0, through: 3.0, by: 1) {
            for dx in stride(from: -1.0, through: 1.0, by: 1) {
                let at = pixel(x + dx, y + dy), colour = frame.colour(at.0, at.1)
                sum = (sum.0 + colour.red, sum.1 + colour.green, sum.2 + colour.blue)
                count += 1
            }
        }
        return (sum.0 / count, sum.1 / count, sum.2 / count)
    }

    /// Mateusz 2026-11-11 18:59: „Same farby na pasku jednak bliżej
    /// siebie, mogą się trochę mieszać ze sobą i dawać płynniejsze
    /// przejście. Tak jakby malarz poszczególnymi pociągnięciami malował
    /// gradient. Akcenty z końca jako pacnięcia na wierzchu.”
    func testOilIsOneBandOfPullsWithTheSmallColoursAsTouchesOnTop() {
        let pulls = OilStrip.pulls(jatte, width: 350, seed: 5)
        let mains = pulls.filter { !$0.on }, accents = pulls.filter(\.on)
        // The four big colours are pulls (the widest in two), the three small ones touches on top.
        XCTAssertEqual(mains.count, 5)
        XCTAssertEqual(accents.map(\.rgb), [jatte[4].rgb, jatte[5].rgb, jatte[6].rgb])
        XCTAssertEqual(mains.map(\.rgb), [jatte[0].rgb, jatte[0].rgb, jatte[1].rgb, jatte[2].rgb, jatte[3].rgb])
        XCTAssertEqual(mains[0].a, 0)
        XCTAssertNil(mains[0].under)
        for (before, after) in zip(mains, mains.dropFirst()) {
            // Each begun in the wet paint of the one before, with that paint on the brush.
            XCTAssertEqual(after.a, before.e - OilStrip.back, accuracy: 0.001)
            XCTAssertEqual(after.under, before.rgb)
            XCTAssertGreaterThan(after.blend, 0.3)
            XCTAssertGreaterThan(after.at, before.at)
        }
        XCTAssertLessThanOrEqual(mains[mains.count - 1].e, 350)
        // The accents come last, on the body of a pull: not across the place where one begins, not on each other.
        let seams = mains.dropFirst().map(\.a)
        for (n, accent) in accents.enumerated() {
            XCTAssertTrue(accent.touch)
            XCTAssertNil(accent.under)
            XCTAssertGreaterThanOrEqual(accent.at, mains[mains.count - 1].at + mains[mains.count - 1].takes)
            XCTAssertGreaterThan(accent.a, 0)
            XCTAssertLessThan(accent.e, 350 - 16)
            for seam in seams { XCTAssertFalse(seam + 3 > accent.a - 5 && seam + 3 < accent.e + 10, "accent \(n)") }
            for other in accents.prefix(n) { XCTAssertTrue(accent.a > other.e + 8 || accent.e < other.a - 8, "accent \(n)") }
        }
        // Enough of the picture stays in the pulls: of eight equal colours only three are accents, and one colour alone is a pull.
        let equal = shares((0..<8).map { _ in ("#6A7F9A", 0.125) })
        XCTAssertEqual(OilStrip.pulls(equal, width: 350, seed: 5).filter(\.on).count, 3)
        XCTAssertEqual(OilStrip.pulls(shares([("#6A7F9A", 1)]), width: 350, seed: 5).filter(\.on).count, 0)
        XCTAssertTrue(OilStrip.pulls([], width: 350, seed: 5).isEmpty)

        let strip = OilStrip(shares: jatte, width: 350, seed: 5, dark: false)
        XCTAssertEqual(strip.last, pulls.map { $0.at + $0.takes }.max() ?? 0, accuracy: 0.001)
        XCTAssertEqual(strip.length, strip.last + OilStrip.lag + OilStrip.soak, accuracy: 0.001)
        XCTAssertEqual(covered(strip.frame(age: 0)), 0)
        let early = strip.frame(age: 0.3)
        let first = pixel(mains[0].a + 8, 13), fourth = pixel(mains[3].a + 24, 13)
        XCTAssertGreaterThan(early.cover(first.0, first.1), 0.9)
        XCTAssertEqual(early.cover(fourth.0, fourth.1), 0)
        // All the paint down: one band, no paper between the pulls; only the last one runs dry.
        let wet = strip.frame(age: strip.last), last = mains[mains.count - 1]
        for x in stride(from: 6.0, to: last.a + 0.4 * (last.e - last.a), by: 4) {
            let at = pixel(x, 13)
            XCTAssertGreaterThan(wet.cover(at.0, at.1), 0.9, "at \(x)")
        }
        let green = wet.colour(first.0, first.1)
        XCTAssertEqual(green.green, jatte[0].rgb[1], accuracy: 60)
        XCTAssertGreaterThan(green.green, green.blue + 30)
        // An accent is on top of the paint that was there: green before it, orange after.
        let orange = accents[0], spot = (x: orange.a + 0.45 * (orange.e - orange.a), y: 13 + orange.dy)
        let under = colour(strip.frame(age: orange.at), spot.x, spot.y), over = colour(wet, spot.x, spot.y)
        XCTAssertGreaterThan(under.green, under.red + 10)
        XCTAssertGreaterThan(over.red, over.green + 40)
        // On a dark page the same paint.
        let dark = OilStrip(shares: jatte, width: 350, seed: 5, dark: true).frame(age: 99)
        XCTAssertEqual(dark.cover(first.0, first.1), wet.cover(first.0, first.1), accuracy: 0.01)
    }

    func testOilColoursGoOverIntoEachOther() {
        // Two colours, each wide enough for three pulls.
        let two = shares([("#B03020", 0.5), ("#2040B0", 0.5)])
        let pulls = OilStrip.pulls(two, width: 350, seed: 5)
        XCTAssertEqual(pulls.count, 6)
        XCTAssertFalse(pulls.contains(where: \.on))
        // The pull next to the other colour has some of it on the brush; the ones away from it are pure.
        XCTAssertEqual(pulls[0].rgb, two[0].rgb)
        XCTAssertEqual(pulls[5].rgb, two[1].rgb)
        XCTAssertGreaterThan(pulls[2].rgb[2], two[0].rgb[2] + 5)
        XCTAssertLessThan(pulls[2].rgb[0], two[0].rgb[0] - 5)
        XCTAssertGreaterThan(pulls[3].rgb[0], two[1].rgb[0] + 10)
        XCTAssertLessThan(pulls[3].rgb[2], two[1].rgb[2] - 10)
        for (mixed, pure) in zip(OilStrip.mixed(two[0].rgb, two[1].rgb, 0), two[0].rgb) { XCTAssertEqual(mixed, pure, accuracy: 0.001) }
        // Along the bar red gives way to blue by degrees: no place where one stops and the other begins.
        let done = OilStrip(shares: two, width: 350, seed: 5, dark: false).frame(age: 99)
        func warm(_ x: Double) -> Double {
            let here = colour(done, x, 13)
            return here.red / max(1, here.red + here.blue)
        }
        let left = warm(40), right = warm(pulls[5].a + 0.6 * (pulls[5].e - pulls[5].a))
        XCTAssertGreaterThan(left, 0.75)
        XCTAssertLessThan(right, 0.3)
        let between = stride(from: pulls[2].a + 10, through: pulls[4].a + 30, by: 6).map(warm)
        XCTAssertGreaterThanOrEqual(between.filter { $0 > right + 0.12 && $0 < left - 0.12 }.count, 5)
        for (here, next) in zip(between, between.dropFirst()) { XCTAssertLessThan(abs(here - next), 0.36) }
    }

    /// Mateusz 2026-11-11 18:59: „Przy lini kolorów robionych farba
    /// olejna także dodaj „tłustą plamę” na papierze pod spodem.”
    func testThePaperUnderTheOilBarSoaksTheOilUp() {
        let strip = OilStrip(shares: jatte, width: 350, seed: 5, dark: false)
        func count(_ frame: PaintFrame, _ range: ClosedRange<UInt8>) -> Int {
            var count = 0
            for k in 0..<(frame.wide * frame.high) where range.contains(frame.bytes[4 * k + 3]) { count += 1 }
            return count
        }
        // A faint stain round the paint that was not there when the first pulls were just down, and comes slowly.
        let begun = strip.frame(age: 0.5), wet = strip.frame(age: strip.last), soaked = strip.frame(age: strip.length)
        XCTAssertLessThan(count(begun, 12...80), 1200)
        XCTAssertGreaterThan(count(soaked, 12...80), count(wet, 12...80) + 3000)
        let half = strip.frame(age: strip.last + OilStrip.soak / 2)
        XCTAssertGreaterThan(count(half, 12...80), count(wet, 12...80))
        XCTAssertLessThan(count(half, 5...80), count(soaked, 5...80))
        // The paint itself is as it was, and the stain stays near it.
        XCTAssertEqual(Double(count(soaked, 201...255)), Double(count(wet, 201...255)), accuracy: 60)
        XCTAssertEqual(soaked.cover(2, 2), 0)
        XCTAssertEqual(soaked.cover(soaked.wide / 2, 4), 0)
        XCTAssertEqual(strip.frame(age: 999).bytes, soaked.bytes)
        // On a dark page too.
        let dark = OilStrip(shares: jatte, width: 350, seed: 5, dark: true).frame(age: 99)
        XCTAssertGreaterThan(count(dark, 12...80), 3000)
    }

    func testAPaintsSwatchIsATouchADabOrAScribbleOfItsColour() {
        let rgb = Paint.rgb("#3B4FA0") ?? [0, 0, 0]
        // In oil a touch of the brush, as the bar's small colours are
        // (13:50: „kropki kolorów farb olejnych / akryli etc. rób
        // pacnieciami jak na pasku przy niewielkiej ilości koloru”).
        let sure = OilStrip(touch: rgb, index: 0, seed: 5, dark: false)
        XCTAssertEqual(sure.pulls.count, 1)
        XCTAssertTrue(sure.pulls[0].touch)
        XCTAssertEqual(sure.wide, 58 * Paint.scale)
        XCTAssertEqual(sure.high, 58 * Paint.scale)
        XCTAssertEqual(covered(sure.frame(age: 0)), 0)
        XCTAssertGreaterThan(covered(sure.frame(age: 99)), covered(sure.frame(age: 0.1)))
        let middle = sure.frame(age: 99).colour(sure.wide / 2, sure.high / 2)
        XCTAssertGreaterThan(middle.blue, middle.red + 40)
        // A little bigger than the dot it was (13:51: „mogą być trochę
        // większe niż obecne kropki”): that was 20 points across.
        func solid(_ frame: PaintFrame) -> Double {
            var count = 0.0
            for k in 0..<(frame.wide * frame.high) where frame.bytes[4 * k + 3] > 200 { count += 1 }
            return count / Double(Paint.scale * Paint.scale)
        }
        XCTAssertGreaterThan(solid(sure.frame(age: 99)), 360)
        XCTAssertLessThan(solid(sure.frame(age: 99)), 600)
        // Round it the paper soaks a little oil up, slowly (13:51: „Wokół
        // nich tło może trochę nasiąkać jak przy farbach olejnych”): a
        // faint stain that was not there when the touch was just down.
        func faint(_ frame: PaintFrame) -> Int {
            var count = 0
            for k in 0..<(frame.wide * frame.high) where frame.bytes[4 * k + 3] > 12 && frame.bytes[4 * k + 3] < 80 { count += 1 }
            return count
        }
        let down = sure.frame(age: sure.last), soaked = sure.frame(age: sure.length)
        XCTAssertGreaterThan(faint(soaked), faint(down) + 400)
        XCTAssertEqual(solid(soaked), solid(down), accuracy: 15)
        XCTAssertEqual(sure.frame(age: 999).bytes, soaked.bytes)
        XCTAssertEqual(sure.length, sure.last + OilStrip.soak, accuracy: 0.001)
        let wet = WaterDab(rgb: rgb, index: 0, seed: 5)
        XCTAssertEqual(covered(wet.frame(age: 0)), 0)
        // As wide as the swatch's place, 26 points across, or a little over.
        XCTAssertGreaterThan(solid(wet.frame(age: 99)), 300)
        XCTAssertEqual(wet.frame(age: 99).bytes, wet.frame(age: wet.length).bytes)
    }

    /// Mateusz 2026-11-11 22:54: „akcenty na linii kolorów większe (teraz
    /// są zbyt drobne)”.
    func testAnAccentIsBigEnoughToBeSeen() {
        // The Little Street: bricks, greys, and a hundredth of the picture in the shutter's red.
        let street = shares([("#7d543e", 0.284), ("#b3a590", 0.194), ("#cfc3ad", 0.18), ("#544133", 0.144), ("#c4a87f", 0.074),
                             ("#9c3e26", 0.013)])
        // In oil a touch of the brush on top, well over a point of the finger long and nearly as high as the bar.
        let touches = OilStrip.pulls(street, width: 350, seed: 5).filter(\.on)
        XCTAssertEqual(touches.map(\.rgb), [street[4].rgb, street[5].rgb])
        for touch in touches {
            XCTAssertGreaterThanOrEqual(touch.e - touch.a, 30)
            XCTAssertLessThanOrEqual(touch.e - touch.a, 42)
            XCTAssertGreaterThan(touch.wide, 0.6 * Paint.bar / 2)
        }
        // In watercolour and pastel a patch of its own, as wide as a finger's tip; the others make room by their shares.
        let spans = Paint.spans(street, width: 350)
        XCTAssertEqual(spans[5].1 - spans[5].0, Paint.least, accuracy: 0.001)
        XCTAssertEqual(spans[0].0, 0)
        XCTAssertEqual(spans[5].1, 350, accuracy: 0.001)
        for (before, after) in zip(spans, spans.dropFirst()) { XCTAssertEqual(before.1, after.0, accuracy: 0.001) }
        XCTAssertEqual((spans[0].1 - spans[0].0) / (spans[1].1 - spans[1].0), 0.284 / 0.194, accuracy: 0.001)
        XCTAssertEqual(WaterStrip.spans(street, width: 350).map(\.1), spans.map(\.1))
        // Colours that all have room keep their shares; more colours than there is room for share the bar.
        let even = Paint.spans(jatte, width: 350)
        XCTAssertEqual(even[6].1 - even[6].0, 350 * 0.06, accuracy: 0.001)
        let many = Paint.spans(shares((0..<8).map { _ in ("#6A7F9A", 0.125) }), width: 80)
        XCTAssertEqual(many.map { $0.1 - $0.0 }, Array(repeating: 10, count: 8))
        XCTAssertTrue(Paint.spans([], width: 350).isEmpty)
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
        // A paint's scribble is a close hatching across its swatch, never
        // a line or two; a likely paint's is the same (Mateusz 2026-11-11
        // 18:39: „zawsze duże (nawet gdy niepewne)”), so there is one kind.
        for index in 0..<6 {
            let scribble = DryPlan.scribble(index: index, seed: 5)
            XCTAssertEqual(scribble.count, 8)
            let across = (scribble.map(\.x).max() ?? 0) - (scribble.map(\.x).min() ?? 0)
            XCTAssertGreaterThan(across, 17)
            XCTAssertLessThan(across, 27)
        }
        let tooth = DryPlan.tooth(wide: 40, high: 40, seed: 5)
        XCTAssertEqual(tooth.count, 1600)
        XCTAssertGreaterThanOrEqual(tooth.min() ?? 0, 96)
        XCTAssertGreaterThan(tooth.max() ?? 0, 240)
    }

    func testThePaintsBeginWhileTheBarIsPaintedOneAfterAnother() {
        let three = Array(jatte.prefix(3))
        for style in PaintStyle.allCases {
            // With no bar the first is there at once.
            XCTAssertEqual(style.barTime([], width: 350), 0)
            XCTAssertEqual(style.swatchDelay(bar: 0, index: 0), 0)
            XCTAssertGreaterThan(style.swatchDelay(bar: 0, index: 1), 0.2)
            let bar = style.barTime(jatte, width: 350), first = style.swatchDelay(bar: bar, index: 0)
            XCTAssertGreaterThan(style.swatchDelay(bar: bar, index: 1), first + 0.2)
            XCTAssertLessThan(style.swatchDelay(bar: bar, index: 1), first + 0.3)
            XCTAssertGreaterThan(bar, style.barTime(three, width: 350))
            // They do not wait for the bar's last stroke (Mateusz 2026-11-11
            // 18:39: „muszą się pojawiać trochę wcześniej”): the first begins
            // about half way through the bar, when its first colours are down.
            XCTAssertLessThan(first, 0.7 * bar, "\(style)")
            XCTAssertGreaterThan(first, 0.3 * bar, "\(style)")
        }
        // The bar's time is the time its painter takes over its paint.
        XCTAssertEqual(PaintStyle.oil.barTime(jatte, width: 350), OilStrip(shares: jatte, width: 350, seed: 5, dark: false).last, accuracy: 0.001)
        XCTAssertEqual(PaintStyle.oil.barTime(jatte, width: 350), OilStrip(shares: jatte, width: 350, seed: 41, dark: true).last, accuracy: 0.001)
        XCTAssertEqual(PaintStyle.water.barTime(jatte, width: 350), WaterStrip(shares: jatte, width: 350, seed: 5).last, accuracy: 0.001)
        XCTAssertEqual(PaintStyle.dry.barTime(jatte, width: 350), DryPlan(shares: jatte, width: 350, seed: 5).last, accuracy: 0.001)
    }
}
