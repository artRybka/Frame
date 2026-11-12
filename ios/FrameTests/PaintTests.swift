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
        // Ink with colours, and whatever names something that is no paint: flat.
        let flat = ["Ink and color on silk", "Bronze", "papier", "Porcelain", "mixed media"]
        // A photograph: its tones under grain (Mateusz 2026-11-12 10:47:
        // „fotografia - gradientowy pasek z lekkim ziarnem”).
        let photo = ["Gelatin silver print", "Oil print", "Albumen silver print", "Platinum print",
                     "Salted paper print from a paper negative", "Chromogenic print", "fotografia"]
        for text in photo { XCTAssertEqual(PaintStyle.of(medium: text), .photo, text) }
        for text in oil { XCTAssertEqual(PaintStyle.of(medium: text), .oil, text) }
        for text in water { XCTAssertEqual(PaintStyle.of(medium: text), .water, text) }
        for text in dry { XCTAssertEqual(PaintStyle.of(medium: text), .dry, text) }
        for text in flat { XCTAssertNil(PaintStyle.of(medium: text), text) }
        // What kind of thing it is counts too: a print is no painting.
        XCTAssertEqual(PaintStyle.of(medium: "oil colours on paper", classification: "Prints"), .woodblock)
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
        XCTAssertEqual(PaintStyle.of(medium: "", classification: "Photograph"), .photo)
        XCTAssertNil(PaintStyle.of(medium: "", classification: "Illuminated Manuscript"))
        // Nothing at all about how it is made: paint (Mateusz 2026-11-12
        // 12:25, of the "View of Delft" that came without a medium: „Chyba
        // musimy założyć że w takiej sytuacji dajemy farbę”).
        XCTAssertEqual(PaintStyle.of(medium: "", classification: ""), .oil)
        XCTAssertEqual(PaintStyle.of(medium: ""), .oil)
        XCTAssertEqual(PaintStyle.of(medium: "", classification: "Stadsgezicht"), .oil)
        // Only what it is painted on: paint too.
        XCTAssertEqual(PaintStyle.of(medium: "panel (wood by form)"), .oil)
        XCTAssertEqual(PaintStyle.of(medium: "paneel"), .oil)
        XCTAssertEqual(PaintStyle.of(medium: "cardboard"), .oil)
        // Not what is of one colour (rather a print or a drawing), nor what is filed as a drawing or an object.
        XCTAssertNil(PaintStyle.of(medium: "", classification: "", mono: true))
        XCTAssertNil(PaintStyle.of(medium: "", classification: "Ceramics"))
        XCTAssertNil(PaintStyle.of(medium: "", classification: "Textiles"))
        XCTAssertNil(PaintStyle.of(medium: "", classification: "clocks"))
        XCTAssertNil(PaintStyle.of(medium: "Six-panel folding screen; ink, color and gold on paper"))
        XCTAssertFalse(PaintStyle.sculpted(medium: "", classification: ""))
        XCTAssertTrue(PaintStyle.sculpted(medium: "", classification: "Sculpture"))
    }

    /// Mateusz 2026-11-12 07:26: „dla rycin, rysunków, grafik, plakatów
    /// chciałbym opracować inny wygląd paska kolorów. Ten teraz w żaden
    /// sposób nie ma sensu”; 07:55, of the two looks of sketch 35:
    /// „Wdrażamy oba. Jest super.”
    func testAPrintOrADrawingIsShownInItsLinesOrItsInks() {
        // A print of one colour: a scale of tones in the engraver's lines; in colours: its inks.
        for text in ["Etching and aquatint", "Engraving", "miedzioryt", "akwaforta, papier", "Woodcut", "drzeworyt", "Kupferstich",
                     "Radierung", "ets", "Mezzotint", "rycina"] {
            XCTAssertEqual(PaintStyle.of(medium: text, mono: true), .burin, text)
            XCTAssertEqual(PaintStyle.of(medium: text), .woodblock, text)
        }
        for text in ["Color woodblock print; ink and color on paper", "drzeworyt barwny", "Farbholzschnitt", "kleurenhoutsnede"] {
            XCTAssertEqual(PaintStyle.of(medium: text), .woodblock, text)
        }
        XCTAssertEqual(PaintStyle.of(medium: "", classification: "Prints", mono: true), .burin)
        // From the stone or the screen, and posters: the inks with the crayon's grain; of one colour, the crayon's lines.
        for text in ["litografia barwna", "Colour lithograph after a pastel", "Chromolithograph", "Screenprint", "serigrafia", "plakat",
                     "Lithograph in black and red"] {
            XCTAssertEqual(PaintStyle.of(medium: text), .litho, text)
            XCTAssertEqual(PaintStyle.of(medium: text, mono: true), .pencil, text)
        }
        XCTAssertEqual(PaintStyle.of(medium: "", classification: "Posters"), .litho)
        XCTAssertEqual(PaintStyle.of(medium: "papier", classification: "Plakat"), .litho)
        // A drawing in pen and ink, whatever chalk is under it.
        for text in ["Pen and brown ink, brown wash, over black chalk", "tusz, papier", "piórko, atrament", "Plume et encre brune", "Feder in Braun",
                     "Ink on paper"] {
            XCTAssertEqual(PaintStyle.of(medium: text), .pen, text)
            XCTAssertEqual(PaintStyle.of(medium: text, classification: "Drawings", mono: true), .pen, text)
        }
        // Ink with colours is a painting: flat; in ink alone, a brush's tones are a pen's.
        XCTAssertNil(PaintStyle.of(medium: "Ink and color on silk", classification: "Paintings"))
        XCTAssertNil(PaintStyle.of(medium: "Hanging scroll; ink on paper", classification: "Paintings"))
        XCTAssertEqual(PaintStyle.of(medium: "Hanging scroll; ink on paper", classification: "Paintings", mono: true), .pen)
        // A soft point; a paint over it is what the work is in.
        for text in ["Graphite on paper", "ołówek, papier", "rysunek ołówkiem", "Charcoal", "węgiel, papier", "Bleistift", "Pencil on wove paper",
                     "Silverpoint on prepared paper"] {
            XCTAssertEqual(PaintStyle.of(medium: text), .pencil, text)
        }
        XCTAssertEqual(PaintStyle.of(medium: "Watercolor over graphite"), .water)
        XCTAssertEqual(PaintStyle.of(medium: "Pencil, pen and ink"), .pen)
        XCTAssertEqual(PaintStyle.of(medium: "black chalk and graphite"), .dry)
        // A drawing that names no tool goes by its colours: of one colour, the pen for a brown, the pencil for a grey.
        XCTAssertNil(PaintStyle.of(medium: "", classification: "Drawing"))
        XCTAssertEqual(PaintStyle.of(medium: "", classification: "Drawing", mono: true), .pencil)
        XCTAssertEqual(PaintStyle.of(medium: "papier", classification: "Rysunek", mono: true, warm: true), .pen)
        // A painting of one colour is still painted.
        XCTAssertEqual(PaintStyle.of(medium: "Oil on panel", classification: "Paintings", mono: true), .oil)
        XCTAssertEqual(PaintStyle.of(medium: "Gelatin silver print", classification: "Photographs", mono: true), .photo)
        // Which tool or press each is.
        XCTAssertEqual(PaintStyle.allCases.compactMap(\.tool).count, 3)
        XCTAssertEqual(PaintStyle.allCases.compactMap(\.press).count, 2)
        XCTAssertTrue(PaintStyle.allCases.allSatisfy { $0.tool == nil || $0.press == nil })
    }

    private var engraving: [PaintShare] { shares([("#918d78", 0.28), ("#4c4a3c", 0.26), ("#5f5c4b", 0.24), ("#78745f", 0.22)]) }
    private var wave: [PaintShare] {
        shares([("#d9cdb0", 0.34), ("#c8bc9d", 0.22), ("#1f3a5f", 0.16), ("#3d5f86", 0.12), ("#8fa7b8", 0.09), ("#e9e2cf", 0.07)])
    }

    /// The pixel at a point of a printed or drawn bar.
    private func dot(_ x: Double, _ y: Double) -> (Int, Int) {
        (Int((x + Paint.pad) * Double(PrintPaint.scale)), Int((y + Paint.pad) * Double(PrintPaint.scale)))
    }

    /// How dark a picture is between two places along the bar, 0 (paper) … 1.
    private func darkness(_ frame: PaintFrame, from: Double, to: Double, paper: [Double]) -> Double {
        var sum = 0.0, count = 0.0
        for x in stride(from: from + 1, to: to - 1, by: 0.4) {
            for y in stride(from: 3.0, to: 23.0, by: 0.4) {
                let (i, j) = dot(x, y)
                sum += 1 - PrintPaint.lightness([frame.colour(i, j).red, frame.colour(i, j).green, frame.colour(i, j).blue]) / PrintPaint.lightness(paper)
                count += 1
            }
        }
        return sum / count
    }

    func testTheColoursOfOneColourAreToldFromThoseOfSeveral() {
        // His engraving, a pen's browns, a pencil's greys, red chalk.
        XCTAssertTrue(PrintPaint.oneColour(engraving.map(\.rgb)))
        XCTAssertTrue(PrintPaint.oneColour(shares([("#c9b79a", 0.4), ("#a9856a", 0.27), ("#8a5a44", 0.2), ("#6b3f30", 0.13)]).map(\.rgb)))
        XCTAssertTrue(PrintPaint.oneColour(shares([("#d2cec4", 0.46), ("#a9a59c", 0.26), ("#7d7a74", 0.18), ("#55534f", 0.1)]).map(\.rgb)))
        XCTAssertTrue(PrintPaint.oneColour(shares([("#e0cdb0", 0.5), ("#c08a6a", 0.3), ("#a0523a", 0.2)]).map(\.rgb)))
        XCTAssertTrue(PrintPaint.oneColour([]))
        // The Great Wave's indigo beside its paper, a poster, the Grande Jatte.
        XCTAssertFalse(PrintPaint.oneColour(wave.map(\.rgb)))
        XCTAssertFalse(PrintPaint.oneColour(shares([("#1d1a17", 0.3), ("#e8dcc0", 0.28), ("#c8a23a", 0.18), ("#b5432b", 0.14)]).map(\.rgb)))
        XCTAssertFalse(PrintPaint.oneColour(jatte.map(\.rgb)))
        XCTAssertEqual(PrintPaint.lightness([255, 255, 255]), 1, accuracy: 0.001)
        XCTAssertEqual(PrintPaint.lightness([0, 0, 0]), 0, accuracy: 0.001)
    }

    func testAWorkOfOneColourIsAScaleOfItsTonesInLines() {
        for tool in [LineTool.burin, .pen, .pencil] {
            let plan = LineStrip.plan(engraving, width: 350, seed: 5, tool: tool)
            // Lightest to darkest, each as wide as its share, end to end.
            XCTAssertEqual(plan.tones.map(\.colour), [0, 3, 2, 1])
            XCTAssertEqual(plan.tones.first?.from ?? -1, 0, accuracy: 0.001)
            XCTAssertEqual(plan.tones.last?.to ?? 0, 350, accuracy: 0.001)
            for (tone, next) in zip(plan.tones, plan.tones.dropFirst()) {
                XCTAssertEqual(tone.to, next.from, accuracy: 0.001)
                XCTAssertLessThan(tone.cover, next.cover)
            }
            XCTAssertEqual((plan.tones[0].to - plan.tones[0].from) / 350, 0.28, accuracy: 0.001)
            // The paper is lighter than the lightest of the work's colours, the ink darker than the darkest.
            XCTAssertGreaterThan(PrintPaint.lightness(plan.paper), PrintPaint.lightness(engraving[0].rgb))
            XCTAssertLessThan(PrintPaint.lightness(plan.ink), PrintPaint.lightness(engraving[1].rgb))
            // A light tone is lines one way; the darkest is crossed, with more of them.
            func lines(_ tone: Int, _ layer: Int) -> Int {
                plan.strokes.filter { $0.layer == layer && ($0.ax + $0.bx) / 2 >= plan.tones[tone].from && ($0.ax + $0.bx) / 2 < plan.tones[tone].to }.count
            }
            XCTAssertGreaterThan(lines(0, 0), 12, "\(tool)")
            XCTAssertEqual(lines(0, 1), 0, "\(tool)")
            XCTAssertGreaterThan(lines(3, 1), 12, "\(tool)")
            XCTAssertGreaterThan(Double(lines(3, 0)) / (plan.tones[3].to - plan.tones[3].from),
                                 Double(lines(0, 0)) / (plan.tones[0].to - plan.tones[0].from), "\(tool)")
            // One line after another, all down by the bar's time, which is the same for any work of as many tones.
            XCTAssertEqual(plan.last, LineStrip.time(4), accuracy: 0.001)
            XCTAssertEqual(plan.last, LineStrip.plan(engraving, width: 350, seed: 41, tool: tool).last, accuracy: 0.001)
            for (stroke, next) in zip(plan.strokes, plan.strokes.dropFirst()) { XCTAssertLessThanOrEqual(stroke.at, next.at) }
            XCTAssertGreaterThanOrEqual(plan.strokes.first?.at ?? 0, PrintPaint.appear - 0.001)
            XCTAssertLessThanOrEqual((plan.strokes.last?.at ?? 9) + LineStrip.takes, plan.last + 0.001)

            let strip = LineStrip(shares: engraving, width: 350, seed: 5, tool: tool)
            XCTAssertEqual(strip.length, plan.last, accuracy: 0.001)
            XCTAssertEqual(covered(strip.frame(age: 0)), 0)
            // First the paper alone, then the lines over it; the paper goes on past the bar's ends.
            let bare = strip.frame(age: PrintPaint.appear), half = strip.frame(age: strip.length / 2), whole = strip.frame(age: strip.length)
            XCTAssertEqual(whole.wide, (350 + 2 * Int(Paint.pad)) * PrintPaint.scale)
            XCTAssertEqual(whole.cover(dot(175, 13).0, dot(175, 13).1), 1, accuracy: 0.01)
            XCTAssertEqual(whole.cover(dot(-4, 13).0, dot(-4, 13).1), 1, accuracy: 0.01)
            XCTAssertEqual(whole.cover(dot(-14, 13).0, dot(-14, 13).1), 0, accuracy: 0.01)
            XCTAssertLessThan(darkness(bare, from: 0, to: 350, paper: plan.paper), 0.03, "\(tool)")
            XCTAssertGreaterThan(darkness(half, from: 0, to: 350, paper: plan.paper), 0.03, "\(tool)")
            XCTAssertLessThan(darkness(half, from: 0, to: 350, paper: plan.paper), darkness(whole, from: 0, to: 350, paper: plan.paper), "\(tool)")
            // Each tone darker than the one before it, and no line outside the bar.
            let dark = plan.tones.map { darkness(whole, from: $0.from + 6, to: $0.to - 6, paper: plan.paper) }
            for (tone, next) in zip(dark, dark.dropFirst()) { XCTAssertLessThan(tone + 0.02, next, "\(tool) \(dark)") }
            XCTAssertLessThan(darkness(whole, from: -6, to: -1.5, paper: plan.paper), 0.03, "\(tool)")
            // Done is done: the same picture ever after, and again when asked from the start.
            XCTAssertEqual(strip.frame(age: strip.length + 3).bytes, whole.bytes)
            XCTAssertEqual(strip.frame(age: strip.length / 2).bytes, half.bytes)
            XCTAssertEqual(LineStrip(shares: engraving, width: 350, seed: 5, tool: tool).frame(age: 9).bytes, whole.bytes)
        }
        // No colours: no bar. One colour: one tone.
        XCTAssertEqual(covered(LineStrip(shares: [], width: 350, seed: 5, tool: .burin).frame(age: 1)), 0)
        XCTAssertEqual(LineStrip.plan(Array(engraving.prefix(1)), width: 350, seed: 5, tool: .pen).tones.count, 1)
    }

    /// Kiyonaga's "Uma no Naishi": aged paper and the key block's browns,
    /// with a salmon and a yellow on a twentieth of it each (Mateusz
    /// 2026-11-12 11:35: „jeżeli pojawią się plama barwna, to nasza skala
    /// koloru musi ją uwzględniać”).
    private var kiyonaga: [PaintShare] {
        shares([("#c7bc9a", 0.431), ("#7e6e52", 0.179), ("#9d7f5a", 0.171), ("#ac9c77", 0.138), ("#c06e4f", 0.044), ("#aa8e38", 0.043)])
    }

    func testAPatchOfColourIsToldFromTheTonesOfTheOneColour() {
        // The salmon and the yellow are patches, the browns the tones; and the work is still one of tones.
        XCTAssertEqual(PrintPaint.patches(kiyonaga) ?? [], [false, false, false, false, true, true])
        XCTAssertTrue(PrintPaint.mostlyOne(kiyonaga))
        XCTAssertFalse(PrintPaint.oneColour(kiyonaga.map(\.rgb)))
        // A work of one colour has none.
        for tones in [engraving,
                      shares([("#c9b79a", 0.4), ("#a9856a", 0.27), ("#8a5a44", 0.2), ("#6b3f30", 0.13)]),
                      shares([("#d2cec4", 0.46), ("#a9a59c", 0.26), ("#7d7a74", 0.18), ("#55534f", 0.1)]),
                      shares([("#e0cdb0", 0.5), ("#c08a6a", 0.3), ("#a0523a", 0.2)])] {
            XCTAssertEqual(PrintPaint.patches(tones)?.contains(true), false)
            XCTAssertTrue(PrintPaint.mostlyOne(tones))
        }
        // A pale colour is a patch as well: the green of a lithograph in colours among its greys.
        let bathers = shares([("#f3ebe3", 0.484), ("#d0cec4", 0.325), ("#aeb1a5", 0.122), ("#909489", 0.069), ("#b0bd99", 0.044)])
        XCTAssertEqual(PrintPaint.patches(bathers) ?? [], [false, false, false, false, true])
        XCTAssertTrue(PrintPaint.mostlyOne(bathers))
        // A work in colours is not a scale of tones with patches: there is too much colour in it.
        XCTAssertFalse(PrintPaint.mostlyOne(wave))
        XCTAssertFalse(PrintPaint.mostlyOne(shares([("#1d1a17", 0.3), ("#e8dcc0", 0.28), ("#c8a23a", 0.18), ("#b5432b", 0.14)])))
        XCTAssertFalse(PrintPaint.mostlyOne(jatte))
        XCTAssertEqual(PrintPaint.patches([]) ?? [true], [])
    }

    func testAPatchOfColourIsPrintedOnTheScaleOfTones() {
        for tool in [LineTool.burin, .pen, .pencil] {
            let plan = LineStrip.plan(kiyonaga, width: 350, seed: 5, tool: tool)
            // Every colour keeps its place by lightness and its share; the patches are marked.
            XCTAssertEqual(plan.tones.count, 6)
            XCTAssertEqual(plan.tones.filter(\.patch).map(\.colour).sorted(), [4, 5])
            XCTAssertEqual(plan.tones.last?.to ?? 0, 350, accuracy: 0.001)
            // The paper and the ink are the browns', not a patch's.
            let alone = LineStrip.plan(Array(kiyonaga.prefix(4)), width: 350, seed: 5, tool: tool)
            XCTAssertEqual(plan.paper, alone.paper)
            XCTAssertEqual(plan.ink, alone.ink)
            // The lines over a patch are thin enough for its colour to be seen.
            for tone in plan.tones where tone.patch { XCTAssertLessThanOrEqual(tone.cover, LineStrip.over.most + 0.001) }

            let strip = LineStrip(shares: kiyonaga, width: 350, seed: 5, tool: tool)
            XCTAssertEqual(strip.length, LineStrip.time(6), accuracy: 0.001)
            let bare = strip.frame(age: PrintPaint.appear), whole = strip.frame(age: strip.length)
            /// How far the middle of a tone is from the paper in colour (red against blue), on the average.
            func tint(_ frame: PaintFrame, _ tone: LineStrip.Tone) -> Double {
                var sum = 0.0, count = 0.0
                for x in stride(from: tone.from + 3, to: tone.to - 3, by: 0.5) {
                    for y in stride(from: 5.0, to: 21.0, by: 0.5) {
                        let (i, j) = dot(x, y), colour = frame.colour(i, j)
                        sum += (colour.red - colour.blue) - (plan.paper[0] - plan.paper[2])
                        count += 1
                    }
                }
                return sum / count
            }
            for tone in plan.tones {
                // Paper alone at first; at the end a patch is its own colour, a tone is the paper under grey lines.
                XCTAssertLessThan(abs(tint(bare, tone)), 6, "\(tool)")
                if tone.patch {
                    XCTAssertGreaterThan(tint(whole, tone), 35, "\(tool) \(tone.colour)")
                } else {
                    XCTAssertLessThan(abs(tint(whole, tone)), 14, "\(tool) \(tone.colour)")
                }
            }
            // The patches are printed before the lines are far along, one after another.
            let early = strip.frame(age: PrintPaint.appear + LineStrip.printed.after + LineStrip.printed.takes)
            let patches = plan.tones.filter(\.patch)
            XCTAssertGreaterThan(tint(early, patches[0]), 35, "\(tool)")
            XCTAssertLessThan(tint(early, patches[1]), tint(whole, patches[1]) - 10, "\(tool)")
            // Done is done.
            XCTAssertEqual(strip.frame(age: strip.length + 3).bytes, whole.bytes)
            XCTAssertEqual(LineStrip(shares: kiyonaga, width: 350, seed: 5, tool: tool).frame(age: 9).bytes, whole.bytes)
        }
    }

    func testAColourPrintIsItsInksPressedOneAfterAnother() {
        for press in [InkPress.wood, .stone] {
            let strip = InkStrip(shares: wave, width: 350, seed: 5, press: press)
            XCTAssertEqual(strip.length, InkStrip.time(6), accuracy: 0.001)
            XCTAssertEqual(covered(strip.frame(age: 0)), 0)
            // Each ink in its share's place, a little out of register.
            let spans = Paint.spans(wave, width: 350)
            XCTAssertEqual(strip.places.count, 6)
            for (place, span) in zip(strip.places, spans) {
                XCTAssertEqual(place.from, span.0, accuracy: 0.001)
                XCTAssertEqual(place.to, span.1, accuracy: 0.001)
                XCTAssertLessThanOrEqual(abs(place.shift.x), 1.7)
                XCTAssertLessThanOrEqual(abs(place.shift.y), 1.6)
            }
            XCTAssertGreaterThan(Set(strip.places.map { Int($0.shift.x * 100) }).count, 3)
            func colour(_ frame: PaintFrame, _ x: Double, _ y: Double) -> [Double] {
                let (i, j) = dot(x, y), c = frame.colour(i, j)
                return [c.red, c.green, c.blue]
            }
            func far(_ a: [Double], _ b: [Double]) -> Double { zip(a, b).map { abs($0 - $1) }.max() ?? 0 }
            // The paper first, then the first ink, the third not yet.
            let early = strip.frame(age: PrintPaint.appear + InkStrip.takes), whole = strip.frame(age: strip.length)
            let third = (spans[2].0 + spans[2].1) / 2, first = (spans[0].0 + spans[0].1) / 2
            XCTAssertLessThan(far(colour(early, third, 13), InkStrip.paper), 14, "\(press)")
            XCTAssertLessThan(far(colour(early, first, 13), colour(whole, first, 13)), 3, "\(press)")
            // In the end each ink's own colour in the middle of its place, a little of the paper through it.
            for (share, span) in zip(wave, spans) {
                let seen = colour(whole, (span.0 + span.1) / 2, 13)
                XCTAssertLessThan(far(seen, share.rgb), 46, "\(press) \(share.rgb) \(seen)")
                XCTAssertLessThan(PrintPaint.lightness(seen), PrintPaint.lightness(InkStrip.paper))
            }
            // The paper beyond the inks, and nothing beyond the paper.
            XCTAssertLessThan(far(colour(whole, 175, -3.5), InkStrip.paper), 14)
            XCTAssertEqual(whole.cover(dot(175, -3.5).0, dot(175, -3.5).1), 1, accuracy: 0.01)
            XCTAssertEqual(whole.cover(dot(175, -14).0, dot(175, -14).1), 0, accuracy: 0.01)
            XCTAssertEqual(strip.frame(age: 30).bytes, whole.bytes)
        }
        // The stone's print has the printer's register marks at its ends; the block's has none.
        let stone = InkStrip(shares: wave, width: 350, seed: 5, press: .stone).frame(age: 9)
        let wood = InkStrip(shares: wave, width: 350, seed: 5, press: .wood).frame(age: 9)
        let mark = dot(350 + 3.6 + 2.3 * 0.6, 13)
        XCTAssertGreaterThan(wood.colour(mark.0, mark.1).red, 200)
        XCTAssertLessThan(stone.colour(mark.0, mark.1).red, wood.colour(mark.0, mark.1).red - 40)
        XCTAssertEqual(covered(InkStrip(shares: [], width: 350, seed: 5, press: .wood).frame(age: 1)), 0)
    }

    func testAPaintsSwatchOfAPrintOrADrawingIsASlipOfItsPaper() {
        let middle = Int(Paint.half) * PrintPaint.scale
        var painters = [(String, PaintPainter)]()
        for tool in [LineTool.burin, .pen, .pencil] { painters.append(("\(tool)", LinePatch(rgb: [40, 60, 120], index: 1, seed: 5, tool: tool))) }
        for press in [InkPress.wood, .stone] { painters.append(("\(press)", InkStamp(rgb: [40, 60, 120], index: 1, seed: 5, press: press))) }
        for (name, painter) in painters {
            XCTAssertEqual(painter.wide, Int(2 * Paint.half) * PrintPaint.scale, name)
            XCTAssertGreaterThan(painter.length, 0.4, name)
            XCTAssertLessThan(painter.length, 1.6, name)
            XCTAssertEqual(covered(painter.frame(age: 0)), 0, name)
            let whole = painter.frame(age: painter.length)
            // A slip of paper about the swatch's size, with the paint on it: blue over cream.
            XCTAssertEqual(whole.cover(middle, middle), 1, accuracy: 0.01, name)
            XCTAssertEqual(whole.cover(2, 2), 0, accuracy: 0.01, name)
            var blue = 0, paper = 0
            for j in stride(from: middle - 24, through: middle + 24, by: 1) {
                for i in stride(from: middle - 24, through: middle + 24, by: 1) {
                    let c = whole.colour(i, j)
                    if c.red - c.blue < 10 { blue += 1 }
                    if c.red > 200, c.red > c.blue + 12 { paper += 1 }
                }
            }
            XCTAssertGreaterThan(blue, 300, name)
            if name == "wood" || name == "stone" { XCTAssertGreaterThan(blue, 1600, name) } else { XCTAssertGreaterThan(paper, 20, name) }
            let corner = whole.colour(middle - 33, middle)
            XCTAssertGreaterThan(corner.red, 200, name)
        }
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

    /// Mateusz 2026-11-12 10:47: „przeróbmy akwarele i pastele tak, żeby
    /// akcenty leżały "na wierzchu"”; 11:02: „akwarela, gwasz - chyba
    /// akcenty trzeba robić na czystym papierze - zostawiać niezamalowane
    /// kółeczko”.
    func testWatercolourFillsTheBarWithItsBigColoursAndLeavesPaperForTheSmall() {
        let strip = WaterStrip(shares: jatte, width: 350, seed: 5)
        XCTAssertEqual(strip.wide, 382 * Paint.scale)
        XCTAssertEqual(strip.high, 58 * Paint.scale)
        XCTAssertEqual(covered(strip.frame(age: 0)), 0)
        // The four big colours are washes over the whole bar, the three small ones accents.
        let mains = Array(jatte.prefix(4)), spans = WaterStrip.spans(mains, width: 350)
        XCTAssertEqual(spans.last?.1 ?? 0, 350, accuracy: 0.001)
        XCTAssertEqual(strip.touches.map(\.rgb), [jatte[4].rgb, jatte[5].rgb, jatte[6].rgb])
        /// A place in a wash that is clear of the accents.
        func clear(_ span: (Double, Double)) -> Double {
            stride(from: span.0 + 8, to: span.1 - 8, by: 2).first { x in strip.touches.allSatisfy { abs($0.x - x) > $0.round + 4 } } ?? span.0 + 8
        }
        // Half a second in only the first stroke is down.
        let early = strip.frame(age: 0.3)
        XCTAssertGreaterThan(early.cover(pixel(clear((6, 40)), 13).0, pixel(clear((6, 40)), 13).1), 0.8)
        XCTAssertEqual(early.cover(pixel(spans[3].0 + 10, 13).0, pixel(spans[3].0 + 10, 13).1), 0)
        let dry = strip.frame(age: strip.length)
        for (i, span) in spans.enumerated() {
            let at = pixel(clear(span), 13)
            XCTAssertGreaterThan(dry.cover(at.0, at.1), 0.85, "colour \(i)")
            let colour = dry.colour(at.0, at.1)
            XCTAssertEqual(colour.red, mains[i].rgb[0], accuracy: 45, "colour \(i)")
            XCTAssertEqual(colour.green, mains[i].rgb[1], accuracy: 45, "colour \(i)")
            XCTAssertEqual(colour.blue, mains[i].rgb[2], accuracy: 45, "colour \(i)")
        }
        // The washes go round each accent's place: when they are down it is clean paper still.
        let washed = strip.frame(age: (strip.touches.first?.at ?? 0) - 0.01)
        for (n, touch) in strip.touches.enumerated() {
            XCTAssertTrue((16...19).contains(2 * touch.round), "accent \(n)")
            XCTAssertGreaterThan(touch.x - touch.round, 5)
            XCTAssertLessThan(touch.x + touch.round, 345)
            XCTAssertGreaterThan(touch.y - touch.round, 1)
            XCTAssertLessThan(touch.y + touch.round, Paint.bar - 1)
            for other in strip.touches.dropFirst(n + 1) { XCTAssertGreaterThan(abs(other.x - touch.x), other.round + touch.round + 4) }
            let middle = pixel(touch.x, touch.y)
            XCTAssertEqual(washed.cover(middle.0, middle.1), 0, "accent \(n)")
            // Paint on both sides of it.
            for side in [-1.0, 1.0] {
                let at = pixel(touch.x + side * (touch.round + 2.5), touch.y)
                XCTAssertGreaterThan(washed.cover(at.0, at.1), 0.8, "accent \(n), \(side)")
            }
            // Then its own paint in it, pure: nothing is under it.
            XCTAssertGreaterThan(dry.cover(middle.0, middle.1), 0.85, "accent \(n)")
            let colour = dry.colour(middle.0, middle.1)
            XCTAssertEqual(colour.red, touch.rgb[0], accuracy: 30, "accent \(n)")
            XCTAssertEqual(colour.green, touch.rgb[1], accuracy: 30, "accent \(n)")
            XCTAssertEqual(colour.blue, touch.rgb[2], accuracy: 30, "accent \(n)")
            // On one side it stops short of the wash, and paper stays between them.
            let off = (touch.lean.x * touch.lean.x + touch.lean.y * touch.lean.y).squareRoot()
            XCTAssertTrue((2.6...3.6).contains(off), "accent \(n)")
            XCTAssertGreaterThan(abs(touch.lean.x), abs(touch.lean.y), "accent \(n)")
            func along(_ far: Double) -> (Int, Int) { pixel(touch.x + far * touch.lean.x / off, touch.y + far * touch.lean.y / off) }
            let bare = stride(from: 0.5, through: 3, by: 0.5).map { dry.cover(along($0 - touch.round).0, along($0 - touch.round).1) }.min() ?? 1
            XCTAssertLessThan(bare, 0.2, "accent \(n)")
            // On the other it lies over the wash and has run into it (Mateusz 2026-11-12 11:21: „plamka
            // akcentu może częściowo nachodzić/zlewać się z resztą paska”): the wash there has taken its colour.
            let taken = stride(from: 0.5, through: 3, by: 0.5).compactMap { far -> Double? in
                let at = along(touch.round + far)
                guard washed.cover(at.0, at.1) > 0.85, dry.cover(at.0, at.1) > 0.85 else { return nil }
                let was = washed.colour(at.0, at.1), now = dry.colour(at.0, at.1)
                return abs(now.red - was.red) + abs(now.green - was.green) + abs(now.blue - was.blue)
            }.max() ?? 0
            XCTAssertGreaterThan(taken, 40, "accent \(n)")
        }
        // The accents come one after another when the washes are down.
        XCTAssertEqual(strip.touches.map(\.at), strip.touches.map(\.at).sorted())
        XCTAssertGreaterThan(strip.touches[0].at, 3 * WaterStrip.apart + WaterStrip.stroke)
        XCTAssertEqual(strip.last, (strip.touches.last?.at ?? 0) + WaterStrip.accents.spread, accuracy: 0.001)
        // A work of big colours only is washes side by side, as it was.
        let plain = WaterStrip(shares: Array(jatte.prefix(3)), width: 350, seed: 5)
        XCTAssertTrue(plain.touches.isEmpty)
        XCTAssertEqual(plain.last, 2 * WaterStrip.apart + WaterStrip.stroke, accuracy: 0.001)
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

    /// Mateusz 2026-11-12 13:46: „"3d" farby olejnej jest zbyt duże, trochę
    /// musimy je uspokoić. Co prawda świetnie wygląda np. u Van Gogha, ale
    /// źle sprawdza się w baroku czy gotyku. chyba że jesteśmy w stanie to
    /// zróżnicować i dostosować do obrazu (tego jak gładko czy ostro jest
    /// malowany)?”
    func testTheOilPaintIsAsHighAsTheWorkIsPainted() {
        // By the style a museum names, by tempera, else by the year.
        XCTAssertEqual(Paint.relief(year: 1889, styles: ["Post-Impressionism"]), Paint.calm.thick)
        XCTAssertEqual(Paint.relief(year: 1905, styles: ["Fauvism"]), Paint.calm.thick)
        XCTAssertEqual(Paint.relief(year: 1874, styles: ["Impressionism", "19th century"]), Paint.calm.loose)
        XCTAssertEqual(Paint.relief(year: 1660, styles: ["Baroque", "Dutch Golden Age"]), Paint.calm.smooth)
        XCTAssertEqual(Paint.relief(year: 1931, styles: ["Surrealism"]), Paint.calm.smooth)
        XCTAssertEqual(Paint.relief(year: nil, medium: "Tempera and gold on panel"), Paint.calm.smooth)
        XCTAssertEqual(Paint.relief(year: 1440), Paint.calm.smooth)
        XCTAssertEqual(Paint.relief(year: 1650), Paint.calm.smooth)
        XCTAssertEqual(Paint.relief(year: 1830), Paint.calm.even)
        XCTAssertEqual(Paint.relief(year: 1875), Paint.calm.loose)
        XCTAssertEqual(Paint.relief(year: 1889), Paint.calm.late)
        XCTAssertEqual(Paint.relief(year: nil), Paint.calm.plain)
        XCTAssertLessThan(Paint.calm.smooth, Paint.calm.even)
        XCTAssertLessThan(Paint.calm.even, Paint.calm.plain)
        XCTAssertLessThan(Paint.calm.plain, Paint.calm.loose)
        XCTAssertLessThan(Paint.calm.loose, Paint.calm.late)
        XCTAssertLessThanOrEqual(Paint.calm.late, Paint.calm.thick)
        // The same paint in the same places; the lower it is, the less its light and shade.
        let thick = OilStrip(shares: jatte, width: 350, seed: 5, dark: false, relief: Paint.calm.thick).frame(age: 99)
        let smooth = OilStrip(shares: jatte, width: 350, seed: 5, dark: false, relief: Paint.calm.smooth).frame(age: 99)
        /// How much the paint's lightness changes from a pixel to the one under it, on the average.
        func rough(_ frame: PaintFrame) -> Double {
            var sum = 0.0, count = 0.0
            for y in 0..<(frame.high - 1) {
                for x in 0..<frame.wide {
                    let q = 4 * (y * frame.wide + x), under = q + 4 * frame.wide
                    guard frame.bytes[q + 3] == 255, frame.bytes[under + 3] == 255 else { continue }
                    let here = Double(frame.bytes[q]) + Double(frame.bytes[q + 1]) + Double(frame.bytes[q + 2])
                    let there = Double(frame.bytes[under]) + Double(frame.bytes[under + 1]) + Double(frame.bytes[under + 2])
                    sum += abs(here - there)
                    count += 1
                }
            }
            return sum / max(count, 1)
        }
        func solid(_ frame: PaintFrame) -> Int {
            var count = 0
            for k in 0..<(frame.wide * frame.high) where frame.bytes[4 * k + 3] == 255 { count += 1 }
            return count
        }
        XCTAssertEqual(solid(thick), solid(smooth))
        XCTAssertLessThan(rough(smooth), 0.6 * rough(thick))
        XCTAssertGreaterThan(rough(smooth), 0)
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
        // (Smaller than it was at first: 13:46 the next day, „rozlewa się za bardzo”.)
        XCTAssertGreaterThan(faint(soaked), faint(down) + 150)
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
        // In watercolour a round of clean paper with its paint in it, most of the bar's height across.
        let water = WaterStrip(shares: street, width: 350, seed: 5)
        XCTAssertEqual(water.touches.map(\.rgb), [street[4].rgb, street[5].rgb])
        for touch in water.touches { XCTAssertGreaterThanOrEqual(2 * touch.round, 16) }
        // In pastel a patch of strokes pressed hard, low on the bar and out under its foot (Mateusz 2026-11-12
        // 11:02: „akcent - mocniej docisnąć. może być trochę niżej i wystawać pod linię ogólnego gradientu”).
        let pastel = DryPlan(shares: street, width: 350, seed: 5)
        XCTAssertFalse(pastel.strokes.filter { $0.colour < 4 }.contains(where: \.press))
        let hatching = pastel.strokes.filter { $0.colour < 4 && abs($0.to.y - $0.from.y) > Paint.bar }
        XCTAssertTrue(hatching.allSatisfy { ($0.to.x - $0.from.x) * ($0.to.y - $0.from.y) < 0 })
        for i in [4, 5] {
            let patch = pastel.strokes.filter { $0.colour == i }
            XCTAssertGreaterThanOrEqual(patch.count, 8)
            XCTAssertTrue(patch.allSatisfy(\.press))
            XCTAssertTrue(patch.allSatisfy { $0.alpha > 0.5 })
            // The other way than the hatching under it (11:21: „po skosie w drugą stronę (tak jak poprzednio)”).
            XCTAssertTrue(patch.allSatisfy { ($0.to.x - $0.from.x) * ($0.to.y - $0.from.y) > 0 })
            let ends = patch.flatMap { [$0.from, $0.to] }
            XCTAssertGreaterThanOrEqual((ends.map(\.x).max() ?? 0) - (ends.map(\.x).min() ?? 0), 16)
            XCTAssertGreaterThan(ends.map(\.y).max() ?? 0, Paint.bar + 4)
            XCTAssertLessThan(ends.map(\.y).max() ?? 0, Paint.bar + 9)
            XCTAssertGreaterThan(ends.map(\.y).min() ?? 0, 0.2 * Paint.bar)
        }
        // Colours side by side each have a place as wide as a finger's tip at least; the others make room by their shares.
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
        let firstDone = plan.strokes.filter { $0.colour == 0 }.map { Double($0.turn) * DryPlan.apart + $0.part * DryPlan.stroke }.max() ?? 0
        XCTAssertLessThan(firstDone, Double(jatte.count - 1) * DryPlan.apart)
        // The small colours are hatched over the others, when those are down.
        let over = plan.strokes.filter(\.press), under = plan.strokes.filter { !$0.press }
        XCTAssertEqual(Set(over.map(\.colour)), [4, 5, 6])
        XCTAssertGreaterThan(over.map(\.turn).min() ?? 0, under.map(\.turn).max() ?? 9)
        XCTAssertEqual((plan.strokes.map(\.turn).max() ?? 0) + 1, jatte.count)
        // The others fill the bar from end to end.
        XCTAssertLessThan(under.map { min($0.from.x, $0.to.x) }.min() ?? 9, 2)
        XCTAssertGreaterThan(under.map { max($0.from.x, $0.to.x) }.max() ?? 0, 348)
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

    /// Mateusz 2026-11-12 10:47: „fotografia - gradientowy pasek z lekkim
    /// ziarnem”.
    func testAPhotographIsItsTonesInOneGradientUnderGrain() {
        let tones = shares([("#C9C2B4", 0.3), ("#2A2826", 0.25), ("#8A847A", 0.3), ("#565049", 0.15)])
        let strip = PhotoStrip(shares: tones, width: 350, seed: 7)
        // From the darkest to the lightest, each about its share's middle.
        XCTAssertEqual(strip.stops.count, 4)
        XCTAssertEqual(strip.stops.map(\.at), strip.stops.map(\.at).sorted())
        let lights = strip.stops.map { PrintPaint.lightness($0.rgb) }
        XCTAssertEqual(lights, lights.sorted())
        XCTAssertEqual(strip.stops[0].at, 350 * 0.125, accuracy: 3)
        // No seams: the tone grows lighter all the way along.
        var last = -1.0
        for x in stride(from: 0.0, through: 350, by: 2) {
            let light = PrintPaint.lightness(strip.tone(at: x))
            XCTAssertGreaterThanOrEqual(light, last - 0.0001, "\(x)")
            last = light
        }
        // There at once, and still.
        XCTAssertEqual(PaintStyle.photo.barTime(tones, width: 350), PrintPaint.appear)
        let whole = strip.frame(age: strip.length), later = strip.frame(age: strip.length + 3)
        XCTAssertEqual(whole.bytes, later.bytes)
        let S = Double(PrintPaint.scale)
        func at(_ x: Double, _ y: Double) -> Int { 4 * (Int((y + Paint.pad) * S) * whole.wide + Int((x + Paint.pad) * S)) }
        // Whole inside, nothing outside, round at the corners.
        XCTAssertEqual(whole.bytes[at(175, 13) + 3], 255)
        XCTAssertEqual(whole.bytes[at(175, -3) + 3], 0)
        XCTAssertEqual(whole.bytes[at(0.2, 0.2) + 3], 0)
        // Grain: neighbours of one tone differ a little, never much.
        var least = 255, most = 0
        for k in 0..<30 {
            let green = Int(whole.bytes[at(330 + Double(k) / 3, 6 + Double(k) / 2) + 1])
            least = min(least, green)
            most = max(most, green)
        }
        XCTAssertGreaterThan(most - least, 6)
        XCTAssertLessThan(most - least, 60)
        // Its paints' swatches: small squares of the same grain.
        let chip = PhotoChip(rgb: [140, 132, 122], index: 0, seed: 7)
        let made = chip.frame(age: chip.length)
        XCTAssertEqual(made.bytes[4 * (made.high / 2 * made.wide + made.wide / 2) + 3], 255)
        XCTAssertEqual(made.bytes[3], 0)
    }

    /// Mateusz 2026-11-12 10:47: „rzeźba - bez paska”.
    func testASculptureIsToldByItsKindOrByWhatItIsMadeOf() {
        for kind in ["Sculpture", "Sculpture-Bronze", "Rzeźba", "Statuettes", "Busts", "Reliefs", "beeldhouwwerk", "Skulptur", "Netsuke",
                     "płaskorzeźba"] {
            XCTAssertTrue(PaintStyle.sculpted(medium: "", classification: kind), kind)
        }
        // Painted or not: a sculpture's colours are not a picture's.
        XCTAssertTrue(PaintStyle.sculpted(medium: "Polychromed wood", classification: "Sculpture"))
        for medium in ["Bronze", "brąz", "odlew z brązu", "Marble", "marmur kararyjski", "Terracotta", "Painted plaster", "gips patynowany",
                       "Alabaster", "Limestone", "Ivory"] {
            XCTAssertTrue(PaintStyle.sculpted(medium: medium), medium)
        }
        // What is painted, drawn or printed is none, whatever it lies on.
        for (medium, kind) in [("Oil on canvas", "Paintings"), ("Watercolor on ivory", ""), ("Oil on marble", ""), ("", ""), ("", "Painting"),
                               ("Woodcut", "Relief print"), ("tusz, papier brązowy", ""), ("papier brązowy", ""), ("Gelatin silver print", ""),
                               ("Pen and brown ink", "Drawings"), ("Porcelain", "Ceramics")] {
            XCTAssertFalse(PaintStyle.sculpted(medium: medium, classification: kind), "\(medium) \(kind)")
        }
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
            // A photograph is not made colour by colour: it is there.
            if style == .photo {
                XCTAssertEqual(bar, PrintPaint.appear)
                continue
            }
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
        XCTAssertEqual(PaintStyle.pen.barTime(jatte, width: 350), LineStrip(shares: jatte, width: 350, seed: 5, tool: .pen).last, accuracy: 0.001)
        XCTAssertEqual(PaintStyle.litho.barTime(jatte, width: 350), InkStrip(shares: jatte, width: 350, seed: 5, press: .stone).last, accuracy: 0.001)
    }
}
