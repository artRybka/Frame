import Foundation

// "Kolor i światło" painted in the work's own technique (Mateusz
// 2026-11-11 11:09: „Musielibyśmy stworzyć osobne style malowania dla
// olejnych/akrylu/tempery razem i dla kolorowych szkiców - tak żeby paleta
// odpowiadała rzeczywistej technice dzieła”). This file is the paint
// itself, worked out a pixel at a time: no SwiftUI and no CoreGraphics, so
// that it can be checked anywhere. `PaintedColour.swift` puts it on the page.

/// How a work's colours are shown under "Kolor i światło": painted, drawn
/// or printed, as the work is.
enum PaintStyle: String, Sendable, CaseIterable {
    /// Oil, acrylic, tempera: pulls of a loaded brush, a touch of it for each paint.
    case oil
    /// Watercolour, gouache: strokes that run into each other on wet paper.
    case water
    /// Pastel, crayon, chalk: hatching that catches the tooth of the paper.
    case dry
    /// A print of one colour (engraving, etching, woodcut): a scale of its
    /// tones in the engraver's lines (`LineStrip`, `PrintCore.swift`).
    case burin
    /// A drawing in pen and ink: the same scale in a pen's lines.
    case pen
    /// A drawing in pencil or charcoal, a lithograph of one colour: the
    /// same scale in a soft point's lines.
    case pencil
    /// A print in colours from blocks (a colour woodcut): its inks'
    /// impressions (`InkStrip`).
    case woodblock
    /// A print in colours from the stone or the screen (a colour
    /// lithograph, a poster): its inks' impressions, with the crayon's grain.
    case litho
    /// A photograph: its tones as one gradient under the film's grain
    /// (`PhotoStrip`; Mateusz 2026-11-12 10:47: „fotografia - gradientowy
    /// pasek z lekkim ziarnem”).
    case photo

    /// The tool of a work of lines; nil for any other.
    var tool: LineTool? {
        switch self {
        case .burin: .burin
        case .pen: .pen
        case .pencil: .pencil
        default: nil
        }
    }

    /// What a colour print is printed from; nil for any other.
    var press: InkPress? {
        switch self {
        case .woodblock: .wood
        case .litho: .stone
        default: nil
        }
    }

    /// What a work's medium says it is made with, in the languages the
    /// museums write in; nil when it names something that is none of
    /// these (porcelain, ink and colours on silk): such a work keeps the
    /// flat palette. A work whose museum says nothing at all of how it is
    /// made is taken for a painting in oil (Mateusz 2026-11-12 12:25, of
    /// Vermeer's "View of Delft", which came with no medium: „Chyba musimy
    /// założyć że w takiej sytuacji dajemy farbę”), unless it is of one
    /// colour (rather a print or a drawing) or filed as a drawing or an
    /// object; and so is one that names only what a painting is on (a
    /// panel, cardboard). Of several paints (pastel
    /// over watercolour) the first named; chalk named after pen or ink is
    /// under a drawing in ink. A museum that names no paint (the Getty
    /// gives only "Painting"; Mateusz 2026-11-11 13:50: „może w takiej
    /// sytuacji da jednak jakoś radę ustalić ze to obraz olejny”): what is
    /// on canvas is in oil or acrylic, and so is a painting whose medium
    /// names nothing that says otherwise (paper, silk, ink, fresco).
    ///
    /// What is printed or drawn is not painted (Mateusz 2026-11-12 07:26:
    /// „dla rycin, rysunków, grafik, plakatów chciałbym opracować inny
    /// wygląd paska kolorów”). `mono`: the work is of one colour (the
    /// server's "monochrome", or its colours are one colour's tones for
    /// the most part, `PrintPaint.mostlyOne`): a print of one colour is a
    /// scale of tones in lines, with a patch of colour it has beside them
    /// printed on it; one in colours is its inks; a lithograph of one colour
    /// is the crayon's. A drawing in ink is a pen's (a painting in ink
    /// and colours stays flat), one in pencil or charcoal a soft point's;
    /// a drawing that names no tool goes by its ink, `warm` (brown) a
    /// pen's. Paint named wins over the pencil under it (pencil and
    /// watercolour is a watercolour), a print over the paint on it.
    static func of(medium: String, classification: String = "", mono: Bool = false, warm: Bool = false) -> PaintStyle? {
        let words = Self.words(medium)
        let kind = Self.words(classification)
        let all = words + kind
        func has(_ list: [String], _ begins: [String], _ whole: Set<String> = []) -> Bool {
            list.contains { word in whole.contains(word) || begins.contains { word.hasPrefix($0) } }
        }
        // An "oil print" is a photograph, not an oil painting and not a print.
        let printed = zip(words, words.dropFirst()).contains { photographed.contains($0) && $1.hasPrefix("print") }
        if printed || has(all, photographs, ["foto", "photo"]) { return .photo }
        if has(all, stone) { return mono ? .pencil : .litho }
        if has(all, prints, ["ets", "druk"]) { return mono ? .burin : .woodblock }
        var inked = false
        for word in words {
            for (style, begins, whole) in named where whole.contains(word) || begins.contains(where: { word.hasPrefix($0) }) {
                // Chalk under a drawing in pen and ink is not what it is made in.
                if style == .dry, inked { continue }
                return style
            }
            if ink.contains(word) || inkBegins.contains(where: { word.hasPrefix($0) }) { inked = true }
        }
        if words.contains(where: { word in canvas.contains { word.hasPrefix($0) } || word == "tela" }) { return .oil }
        let painting = has(kind, paintings)
        // Ink and colours on silk is a painting, not a drawing in pen.
        if inked { return !mono && (painting || has(words, colours)) ? nil : .pen }
        if has(words, soft) { return .pencil }
        if painting { return has(words, notOil) ? nil : .oil }
        if mono, has(all, drawings) { return warm ? .pen : .pencil }
        // Nothing says how it is made, or only what it is painted on: paint.
        let unsaid = words.isEmpty || (words.allSatisfy { word in boards.contains { word.hasPrefix($0) } || fillers.contains(word) }
            && has(words, boards))
        if unsaid, !mono, !has(kind, drawings), !has(kind, objects) { return .oil }
        return nil
    }

    /// Whether a work is a sculpture, by its museum's type or by what it
    /// is made of when nothing says how it is painted: the colours of its
    /// photograph are the stone's and the backdrop's, and it has no bar
    /// of colours at all (Mateusz 2026-11-12 10:47: „rzeźba - bez paska”).
    /// A "relief print" is a print.
    static func sculpted(medium: String, classification: String = "") -> Bool {
        let kind = words(classification)
        func has(_ list: [String], _ begins: [String]) -> Bool {
            list.contains { word in begins.contains { word.hasPrefix($0) } }
        }
        if has(kind, sculptures), !has(kind, prints) { return true }
        guard of(medium: medium, classification: classification) == nil else { return false }
        // Not "brązowy": brown paper is no bronze.
        return has(words(medium), carved) || words(medium).contains { $0 == "braz" || $0 == "brazu" }
    }

    /// A sculpture, as the museums file it.
    private static let sculptures = ["sculpt", "skulpt", "statu", "rzezb", "plaskorzezb", "beeld", "bust", "popiersi", "relief", "figurin",
                                     "netsuke", "bronzes", "terracott"]
    /// What a sculpture is made of.
    private static let carved = ["bronze", "marble", "marmur", "marbre", "marmor", "terracott", "terakot", "plaster", "gips",
                                 "alabast", "limestone", "sandstone", "granit", "piaskow", "wapien", "ivory"]

    /// How far through the painting of the bar the first paint's swatch
    /// begins: they do not wait for the bar's end (Mateusz 2026-11-11
    /// 18:39: „muszą się pojawiać trochę wcześniej”).
    static let swatchesFrom = 0.5

    /// How long the bar's paint takes to be down: `shares` on a bar
    /// `width` wide (no colours: no bar, no time).
    func barTime(_ shares: [PaintShare], width: Double) -> Double {
        guard !shares.isEmpty else { return 0 }
        switch self {
        case .oil: return OilStrip.pulls(shares, width: width, seed: 0).map { $0.at + $0.takes }.max() ?? 0
        case .water: return WaterStrip.time(shares, width: width)
        case .dry: return Double(shares.count - 1) * DryPlan.apart + DryPlan.stroke
        case .burin, .pen, .pencil: return LineStrip.time(shares.count)
        case .woodblock, .litho: return InkStrip.time(shares.count)
        case .photo: return PrintPaint.appear
        }
    }

    /// How long after the bar's first stroke paint `index`'s swatch
    /// begins, when the bar's paint takes `bar` (0: no bar).
    func swatchDelay(bar: Double, index: Int) -> Double {
        let gap = switch self {
        case .oil: 0.26
        case .water: 0.22
        case .dry: 0.24
        case .burin, .pen, .pencil: 0.24
        case .woodblock, .litho: 0.26
        case .photo: 0.24
        }
        return Self.swatchesFrom * bar + gap * Double(index)
    }

    /// Lower case, no accents, split at what is no letter.
    static func words(_ text: String) -> [String] {
        text.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "en_US_POSIX"))
            .lowercased()
            .replacingOccurrences(of: "ł", with: "l")
            .split(whereSeparator: { !$0.isLetter })
            .map(String.init)
    }

    private static let photographs = ["photogra", "fotogra", "gelatin", "albumen", "daguerr", "bromoil", "cyanotyp", "chromogenic",
                                      "inkjet", "collotyp", "calotyp", "tintyp", "ambrotyp", "platinotyp", "salted"]
    /// What a photograph's print is named by.
    private static let photographed: Set<String> = ["oil", "carbon", "silver", "platinum", "palladium", "salt", "paper", "pigment"]
    /// Printed from the stone or through a screen, and what is printed so: posters.
    private static let stone = ["lithogra", "litogra", "chromolit", "screenprint", "silkscreen", "serigra", "sitodruk", "offset",
                                "kleurendruk", "farbdruck", "poster", "plakat", "affiche", "afisz"]
    /// Printed from a plate or a block.
    private static let prints = ["print", "etching", "engrav", "woodcut", "woodblock", "linocut", "linoryt", "aquatint", "akwatint",
                                 "mezzotint", "drypoint", "monotyp", "drzeworyt", "akwafort", "miedzioryt", "staloryt", "rycin", "sztych",
                                 "grafik", "estamp", "gravure", "houtsne", "radier", "holzschnitt", "kupferstich", "xilogra", "xylogra",
                                 "incisione", "grabado", "farbholz", "kleurenhout"]
    /// A soft point.
    private static let soft = ["pencil", "graphit", "grafit", "charcoal", "fusain", "bleistift", "kohle", "potlood", "houtskool", "lapiz",
                               "matita", "carboncino", "silverpoint", "metalpoint", "olowk", "olowek", "wegiel", "wegl"]
    /// What says there are colours beside the ink.
    private static let colours = ["color", "colour", "kolor", "barw", "couleur", "farb", "kleur", "pigment", "gold", "zlot"]
    /// A drawing, as the museums file it.
    private static let drawings = ["drawing", "rysun", "tekening", "zeichnung", "dessin", "disegn", "dibuj"]

    private static let ink: Set<String> = ["ink", "inks", "inkt", "pen", "encre", "plume", "tinte", "feder", "tinta", "atrament", "sepia", "bistre", "bister"]
    private static let inkBegins = ["tusz", "pior", "inchiostr"]

    /// What only oil or acrylic is painted on.
    private static let canvas = ["canvas", "plotn", "toile", "doek", "leinwand", "lienzo", "laerred"]
    /// What a painting is on besides canvas, named alone ("panel (wood by form)").
    private static let boards = ["panel", "paneel", "panneau", "oak", "wood", "cardboard", "karton", "tektur", "deska", "desce", "deski"]
    /// Words beside it that say nothing.
    private static let fillers: Set<String> = ["on", "by", "form", "na", "op", "sur", "auf"]
    /// What is no picture, as the museums file it: its colours stay flat.
    private static let objects = ["ceram", "keram", "porcel", "potter", "earthenware", "stoneware", "fajans", "faienc", "glass", "szkl",
                                  "silver", "srebr", "metal", "textil", "tekst", "tkanin", "furnit", "mebl", "bell", "clock", "zegar",
                                  "manuscr", "rekopis", "book", "ksiaz", "jewel", "bizut", "coin", "monet", "medal", "numizm", "numism",
                                  "costum", "arms", "armor", "armour", "weapon", "vessel", "naczyn", "vase", "wazon", "tapestr", "gobelin",
                                  "carpet", "dywan", "mosai", "mozai", "decorativ", "rzemios", "object", "przedmiot", "enamel", "emali",
                                  "lacquer", "ivory", "stamp", "znacz", "postcard", "pocztow", "document", "dokument", "map", "instrument",
                                  "architect", "model"]
    /// A painting, as the museums file it.
    private static let paintings = ["paint", "peint", "malarstw", "obraz", "schilderij", "gemald", "maleri", "pittur", "dipint", "pintur"]
    /// What a painting is on or in when it is no oil painting.
    private static let notOil = ["paper", "papier", "papir", "papel", "carta", "silk", "jedwab", "soie", "seide", "parchment", "vellum",
                                 "pergamin", "ivory", "fresc", "fresk", "mosai", "mozai", "enamel", "emali", "glass", "szkl", "porcel",
                                 "lacquer", "tapestr", "gobelin", "scroll"]

    private static let named: [(PaintStyle, [String], Set<String>)] = [
        (.oil, ["olej", "huile", "olie", "olfarb", "oelfarb", "akryl", "acryl", "acril", "tempera", "tempery", "temperow"],
         ["oil", "oils", "ol", "oel", "olio", "oleo"]),
        (.water, ["watercol", "aquarel", "akwarel", "acuarel", "acquerel", "waterverf", "akvarel", "gouach", "gwasz", "guazzo",
                  "bodycol", "dekverf", "deckfarb"], []),
        (.dry, ["pastel", "kred", "chalk", "craie", "kreide", "krijt", "sanguin", "sangwin"], ["crayon", "crayons"]),
    ]
}

/// A picture a pixel at a time: red, green, blue and how much of it is
/// there (not multiplied in), a byte each, row after row from the top.
struct PaintFrame: Sendable {
    var wide: Int
    var high: Int
    var bytes: [UInt8]

    init(wide: Int, high: Int) {
        self.wide = wide
        self.high = high
        bytes = [UInt8](repeating: 0, count: max(0, wide * high * 4))
    }

    /// How much is there at a pixel, 0…1.
    func cover(_ x: Int, _ y: Int) -> Double {
        guard x >= 0, y >= 0, x < wide, y < high else { return 0 }
        return Double(bytes[4 * (y * wide + x) + 3]) / 255
    }

    /// The colour at a pixel, 0…255 each.
    func colour(_ x: Int, _ y: Int) -> (red: Double, green: Double, blue: Double) {
        let q = 4 * (y * wide + x)
        return (Double(bytes[q]), Double(bytes[q + 1]), Double(bytes[q + 2]))
    }
}

/// What the three ways of painting share.
enum Paint {
    /// Pixels to a point: the paint is soft, and a third pixel would cost
    /// twice the work for nothing the eye finds.
    static let scale = 2
    /// The palette bar's height, and how far round it (and round a paint's
    /// swatch) the picture goes on: paint runs over the edge.
    static let bar = 26.0
    static let pad = 16.0
    /// The least of the bar a colour takes where each has a place of its
    /// own along it (watercolour, pastel): an accent of a hundredth of
    /// the picture is still a patch one sees, not a hairline (Mateusz
    /// 2026-11-11 22:54: „akcenty na linii kolorów większe (teraz są zbyt
    /// drobne)”).
    static let least = 20.0

    /// Each colour's place along a bar `width` wide: as wide as its share
    /// of the picture, a small one `least` wide, the others making room
    /// for it by their shares.
    static func spans(_ shares: [PaintShare], width: Double) -> [(Double, Double)] {
        let floor = min(least, width / Double(max(1, shares.count)))
        var widths = shares.map { _ in floor }
        var small = Set<Int>()
        while true {
            let rest = shares.indices.filter { !small.contains($0) }
            let room = width - floor * Double(small.count)
            let weight = max(rest.reduce(0) { $0 + shares[$1].weight }, 0.000_001)
            var more = false
            for i in rest {
                widths[i] = room * shares[i].weight / weight
                if widths[i] < floor - 0.000_001 {
                    small.insert(i)
                    more = true
                }
            }
            if !more { break }
        }
        for i in small { widths[i] = floor }
        var x = 0.0
        return widths.map { w in
            defer { x += w }
            return (x, x + w)
        }
    }
    /// Under this much of the bar a colour is an accent: laid on top of
    /// the others, not among them (Mateusz 2026-11-11 18:59, of the oil:
    /// „Akcenty z końca jako pacnięcia na wierzchu”; 2026-11-12 10:47:
    /// „przeróbmy akwarele i pastele tak, żeby akcenty leżały "na
    /// wierzchu"”). The others keep at least `ground` of the picture.
    static let touch = 44.0
    static let ground = 0.55

    /// Which of the colours are accents on a bar `width` wide: the
    /// smallest first, while enough of the picture stays under them and
    /// one colour at least.
    static func accents(_ shares: [PaintShare], width: Double) -> [Bool] {
        let total = max(shares.reduce(0) { $0 + $1.weight }, 0.000_001)
        var accent = shares.map { _ in false }, kept = total, left = shares.count
        for i in shares.indices.sorted(by: { shares[$0].weight < shares[$1].weight }) {
            guard width * shares[i].weight / total < touch, left > 1, (kept - shares[i].weight) / total >= ground else { break }
            accent[i] = true
            kept -= shares[i].weight
            left -= 1
        }
        return accent
    }

    /// Where accents `longs` long go along a bar `width` wide: spread
    /// over it, each at the nearest place to its own that is clear of
    /// the `seams` between the colours under it and of the other accents.
    static func spots(_ longs: [Double], width: Double, seams: [Double], random: inout PaintRandom) -> [Double] {
        var spots = [(at: Double, long: Double)]()
        for (n, long) in longs.enumerated() {
            let wish = width * (0.1 + 0.8 * (Double(n) + 0.5 + 0.5 * (random.next() - 0.5)) / Double(longs.count))
            func free(_ spot: Double) -> Bool {
                let from = spot - long / 2, to = spot + long / 2
                if from < 5 || to > width - 5 { return false }
                for seam in seams where seam > from - 4 && seam < to + 4 { return false }
                for other in spots where abs(other.at - spot) < (other.long + long) / 2 + 9 { return false }
                return true
            }
            var spot = min(max(wish, long / 2 + 5), width - long / 2 - 5)
            for step in 0..<60 {
                let right = wish + 3 * Double(step), left = wish - 3 * Double(step)
                if free(right) {
                    spot = right
                    break
                }
                if free(left) {
                    spot = left
                    break
                }
            }
            spots.append((spot, long))
        }
        return spots.map(\.at)
    }

    /// A paint's swatch, and half the square its picture takes.
    static let swatch = 26.0
    static let half = 23.0

    /// A number in 0..<1 for a cell: the same for the same cell and seed.
    static func hash(_ x: Double, _ y: Double, _ seed: Double) -> Double {
        var a = (x * 0.1031 + seed * 0.0173).truncatingRemainder(dividingBy: 1)
        var b = (y * 0.1031 + seed * 0.0173).truncatingRemainder(dividingBy: 1)
        if a < 0 { a += 1 }
        if b < 0 { b += 1 }
        var c = a
        let d = a * (b + 33.33) + b * (c + 33.33) + c * (a + 33.33)
        a += d
        b += d
        c += d
        let r = ((a + b) * c).truncatingRemainder(dividingBy: 1)
        return r < 0 ? r + 1 : r
    }

    /// Smooth noise in 0…1.
    static func noise(_ x: Double, _ y: Double, _ seed: Double) -> Double {
        let cx = x.rounded(.down), cy = y.rounded(.down)
        let fx = x - cx, fy = y - cy
        let ux = fx * fx * (3 - 2 * fx), uy = fy * fy * (3 - 2 * fy)
        let a = hash(cx, cy, seed), b = hash(cx + 1, cy, seed), c = hash(cx, cy + 1, seed), d = hash(cx + 1, cy + 1, seed)
        return (a + (b - a) * ux) * (1 - uy) + (c + (d - c) * ux) * uy
    }

    static func ease(_ x: Double) -> Double {
        let x = min(1, max(0, x))
        return x * x * (3 - 2 * x)
    }

    /// 0 up to `a`, 1 from `b`, smoothly between.
    static func step(_ a: Double, _ b: Double, _ x: Double) -> Double { ease((x - a) / (b - a)) }

    /// "#7C8F45" as red, green and blue, 0…255 each; nil for anything else.
    static func rgb(_ hex: String) -> [Double]? {
        let digits = hex.hasPrefix("#") ? String(hex.dropFirst()) : hex
        guard digits.count == 6, let value = Int(digits, radix: 16) else { return nil }
        return [Double((value >> 16) & 255), Double((value >> 8) & 255), Double(value & 255)]
    }

    /// A small number for a work, the same each time: no two works are
    /// painted alike, and one is painted the same way every time.
    static func seed(_ id: String) -> Int {
        var sum = 7
        for scalar in id.unicodeScalars { sum = (sum * 31 + Int(scalar.value)) % 9973 }
        return 1 + sum % 60
    }

    static func byte(_ value: Double) -> UInt8 { UInt8(max(0, min(255, value))) }
}

/// Numbers one after another from a seed, each in 0..<1, always the same.
struct PaintRandom {
    private var seed: Int

    init(_ seed: Int) { self.seed = max(1, seed % 2_147_483_647) }

    mutating func next() -> Double {
        seed = (seed * 16807) % 2_147_483_647
        return Double(seed - 1) / 2_147_483_646
    }
}

/// One of the picture's colours and its share of the picture.
struct PaintShare: Sendable, Hashable {
    var rgb: [Double]
    var weight: Double
}

/// Something painted over time: the palette bar or one paint's swatch.
/// `frame(age:)` is asked from one place at a time.
protocol PaintPainter: AnyObject {
    /// The picture's size in pixels.
    var wide: Int { get }
    var high: Int { get }
    /// How long it takes, in seconds: after that nothing in it changes.
    var length: Double { get }
    /// The picture `age` seconds after the brush first came down.
    func frame(age: Double) -> PaintFrame
}

// MARK: - Watercolour

/// The palette as watercolour (sketch 26): each colour a stroke of a wet
/// brush, one after another from the left; where two meet they run into
/// each other and mix; as it dries the pigment gathers at the edges and
/// the paper soaks a little up past them.
final class WaterStrip: PaintPainter, @unchecked Sendable {
    let wide: Int
    let high: Int
    let length: Double
    /// When the last stroke is down.
    let last: Double

    /// The washes: the colours that are no accents, side by side.
    private let shares: [PaintShare]
    /// The accents: touches of a loaded brush on top of the washes.
    let touches: [Touch]
    private let width: Double
    private let seed: Double
    private var fields: Fields?

    private struct Fields {
        var away: [[Float]], along: [[Float]], wander: [[Float]]
        var low: [Float], grain: [Float], soak: [Float], fine: [Float]
        /// Each touch: the pixels it may reach, and how far each is from its edge (points; under 0 inside).
        var touched: [(left: Int, right: Int, top: Int, bottom: Int, away: [Float])]
        /// How far each pixel is from the edge of the nearest round of paper left clean (points; under 0 inside).
        var hole: [Float]
    }

    /// An accent: a small round of paper the washes leave clean, and
    /// the accent's own paint in it (Mateusz 2026-11-12 11:02: „akcenty
    /// trzeba robić na czystym papierze - zostawiać niezamalowane
    /// kółeczko”). The drop is not set square in its round: on one side
    /// it goes over the wash and runs into it, on the other more paper
    /// stays (11:21: „plamka akcentu może częściowo nachodzić/zlewać się
    /// z resztą paska”).
    struct Touch: Sendable {
        var rgb: [Double]
        /// Its middle along the bar and down it, and how big the round of clean paper is.
        var x: Double, y: Double, round: Double
        /// How far off the round's middle the drop's middle is.
        var lean: (x: Double, y: Double)
        /// When it comes down.
        var at: Double
        var turns: (Double, Double)
    }

    static let apart = 0.3, stroke = 0.42
    /// How long after the last wash the accents come, how far apart, and how long one takes to spread.
    static let accents = (after: 0.5, apart: 0.3, spread: 0.4)
    /// The round of clean paper: its radius for the smallest accent, how
    /// much more for the biggest, how much smaller than it the accent's
    /// drop is, and how far off its middle the drop lies.
    static let round = (least: 8.0, more: 1.5, gap: 0.2, off: (least: 2.6, more: 1.0))

    init(shares all: [PaintShare], width: Double, seed: Int) {
        let accent = Paint.accents(all, width: width)
        let shares = all.indices.filter { !accent[$0] }.map { all[$0] }, small = all.indices.filter { accent[$0] }.map { all[$0] }
        self.shares = shares
        self.width = width
        self.seed = Double(seed)
        wide = Int((width + 2 * Paint.pad).rounded()) * Paint.scale
        high = Int(Paint.bar + 2 * Paint.pad) * Paint.scale
        let total = max(all.reduce(0) { $0 + $1.weight }, 0.000_001)
        var random = PaintRandom(seed + 29)
        let rounds = small.map { Self.round.least + Self.round.more * min(1, width * $0.weight / total / Paint.touch) }
        let seams = Self.spans(shares, width: width).dropFirst().map(\.0)
        let spots = Paint.spots(rounds.map { 2 * $0 + 4 }, width: width, seams: Array(seams), random: &random)
        touches = small.indices.map { n in
            // To one side or the other, not up or down: the washes are beside it.
            let turn = (random.next() < 0.5 ? 0 : Double.pi) + 1.2 * (random.next() - 0.5)
            let off = Self.round.off.least + Self.round.off.more * random.next()
            return Touch(rgb: small[n].rgb, x: spots[n], y: Paint.bar / 2 + 1.2 * (random.next() - 0.5), round: rounds[n],
                  lean: (off * cos(turn), off * sin(turn)),
                  at: Self.washed(shares.count) + Self.accents.after + Double(n) * Self.accents.apart,
                  turns: (random.next() * 6.28, random.next() * 6.28))
        }
        last = Self.time(all, width: width)
        length = last + 7
    }

    /// When the last of `count` washes is down.
    private static func washed(_ count: Int) -> Double { Double(max(0, count - 1)) * apart + stroke }

    /// How long the bar's paint takes to be down: the washes one after
    /// another, then the accents in their rounds of paper.
    static func time(_ shares: [PaintShare], width: Double) -> Double {
        let small = Paint.accents(shares, width: width).filter { $0 }.count
        let washes = washed(shares.count - small)
        return small == 0 ? washes : washes + accents.after + Double(small - 1) * accents.apart + accents.spread
    }

    /// Each colour's place along the bar.
    static func spans(_ shares: [PaintShare], width: Double) -> [(Double, Double)] {
        Paint.spans(shares, width: width)
    }

    private func prepare() -> Fields {
        let S = Double(Paint.scale), pad = Paint.pad, Hs = Paint.bar, n = wide * high, m = shares.count
        let xs = Self.spans(shares, width: width)
        var fields = Fields(away: Array(repeating: [Float](repeating: 0, count: n), count: m),
                            along: Array(repeating: [Float](repeating: 0, count: n), count: m),
                            wander: Array(repeating: [Float](repeating: 0, count: n), count: m),
                            low: [Float](repeating: 0, count: n), grain: [Float](repeating: 0, count: n),
                            soak: [Float](repeating: 0, count: n), fine: [Float](repeating: 0, count: n), touched: [],
                            hole: [Float](repeating: 99, count: n))
        for (j, touch) in touches.enumerated() {
            let reach = touch.round + 12, dj = Double(j)
            let left = max(0, Int((touch.x - reach + pad) * S)), right = min(wide - 1, Int((touch.x + reach + pad) * S))
            let top = max(0, Int((touch.y - reach + pad) * S)), bottom = min(high - 1, Int((touch.y + reach + pad) * S))
            var away = [Float]()
            guard left <= right, top <= bottom else {
                fields.touched.append((0, -1, 0, -1, away))
                continue
            }
            away.reserveCapacity((right - left + 1) * (bottom - top + 1))
            for row in top...bottom {
                for column in left...right {
                    let x = -pad + (Double(column) + 0.5) / S, y = -pad + (Double(row) + 0.5) / S
                    let far = ((x - touch.x) * (x - touch.x) + (y - touch.y) * (y - touch.y)).squareRoot()
                    let th = atan2(y - touch.y, x - touch.x)
                    // The brush went round it by eye: not quite a circle.
                    let left0 = touch.round * (1 + 0.05 * sin(2 * th + touch.turns.1) + 0.035 * sin(3 * th + touch.turns.0))
                    let held = far - left0 + 0.9 * (Paint.noise(x / 3.5, y / 3.5, 340 + 11 * dj + seed) - 0.5)
                    let k = row * wide + column
                    if Float(held) < fields.hole[k] { fields.hole[k] = Float(held) }
                    // The accent's own drop, a little smaller than its round and off its middle.
                    let ox = x - touch.x - touch.lean.x, oy = y - touch.y - touch.lean.y, turn = atan2(oy, ox)
                    let mine = (touch.round - Self.round.gap) * (1 + 0.07 * sin(2 * turn + touch.turns.0) + 0.05 * sin(3 * turn + touch.turns.1))
                    away.append(Float((ox * ox + oy * oy).squareRoot() - mine + 1.1 * (Paint.noise(x / 4, y / 4, 300 + 11 * dj + seed) - 0.5)))
                }
            }
            fields.touched.append((left, right, top, bottom, away))
        }
        for k in 0..<n {
            let x = -pad + (Double(k % wide) + 0.5) / S, y = -pad + (Double(k / wide) + 0.5) / S
            fields.low[k] = Float(Paint.noise(x / 18, y / 18, 31 + seed))
            fields.grain[k] = Float(Paint.noise(x / 1.5, y / 1.5, 41 + seed))
            fields.soak[k] = Float(Paint.noise(x / 12, y / 12, 51 + seed))
            fields.fine[k] = Float(Paint.noise(x / 2.2, y / 2.2, 61 + seed))
            for i in 0..<m {
                let a = xs[i].0 - (i > 0 ? 2.5 : 0), b = xs[i].1 + (i < m - 1 ? 2.5 : 0)
                // Far from the stroke nothing of it is ever seen.
                if x < a - 18 || x > b + 18 {
                    fields.away[i][k] = 99
                    continue
                }
                let c = min(8, (b - a) / 2)
                let qx = abs(x - (a + b) / 2) - (b - a) / 2 + c, qy = abs(y - Hs / 2) - Hs / 2 + c
                let di = Double(i)
                // A stroke of the brush: its edge wanders, and it sags a little along its foot.
                let box = (max(qx, 0) * max(qx, 0) + max(qy, 0) * max(qy, 0)).squareRoot() + min(max(qx, qy), 0) - c
                let edge = 3 * (Paint.noise(x / 12, y / 12, 100 + 7 * di + seed) - 0.5)
                    + 1.2 * (Paint.noise(x / 3.5, y / 3.5, 101 + 7 * di + seed) - 0.5)
                    - 1.6 * Paint.step(Hs * 0.55, Hs, y) * Paint.noise(x / 9, 2.5, 102 + 7 * di + seed)
                fields.away[i][k] = Float(box + edge)
                fields.along[i][k] = Float(min(1, max(0, (x - a) / (b - a))))
                fields.wander[i][k] = Float(Paint.noise(x / 6.5, y / 6.5, 200 + 13 * di + seed) - 0.5)
            }
        }
        return fields
    }

    func frame(age: Double) -> PaintFrame {
        var out = PaintFrame(wide: wide, high: high)
        let age = min(age, length)
        guard age > 0, !shares.isEmpty else { return out }
        if fields == nil { fields = prepare() }
        guard let fields else { return out }
        let m = shares.count, n = wide * high
        let logs = shares.map { $0.rgb.map { log(max(4, $0)) } }
        var runs = [Double](), drys = [Double]()
        for i in 0..<m {
            runs.append(Paint.ease((age - Double(i) * Self.apart - 0.3) / 3))
            drys.append(Paint.ease((age - Double(i) * Self.apart - 1.2) / 2.4))
        }
        for k in 0..<n {
            let low = Double(fields.low[k]), grain = Double(fields.grain[k])
            var A = 0.0, sum = 0.0, edge = 1e9, near = 0, dry = 0.0, r = 0.0, g = 0.0, b = 0.0, w1 = 0.0, w2 = 0.0
            for i in 0..<m {
                let sd = Double(fields.away[i][k])
                if sd > 12 { continue }
                let came = age - Double(i) * Self.apart - Self.stroke * Double(fields.along[i][k]) - 0.05 * (low - 0.5)
                if came <= 0 { continue }
                let inside = (1 - Paint.step(-0.5, 0.5, sd)) * Paint.step(0, 0.04, came)
                let reach = 1 + 8 * runs[i]
                let p = 1 - Paint.step(-reach, reach, sd + (15 * Double(fields.wander[i][k]) + 4 * (Double(fields.fine[k]) - 0.5)) * runs[i])
                if inside > A { A = inside }
                if sd < edge {
                    edge = sd
                    near = i
                    dry = drys[i]
                }
                if p > 0 {
                    sum += p
                    r += p * logs[i][0]
                    g += p * logs[i][1]
                    b += p * logs[i][2]
                    if p > w1 {
                        w2 = w1
                        w1 = p
                    } else if p > w2 {
                        w2 = p
                    }
                }
            }
            // The paper past the edge soaks a little of the nearest paint up, in places.
            var halo = 0.0
            if A < 1, edge < 9, dry > 0 {
                let deep = dry * Paint.step(0.42, 0.62, Double(fields.soak[k])) * (2.6 + 2.4 * low)
                if deep > 0 {
                    halo = Paint.step(0, 0.5, deep) * (1 - Paint.step(deep - 0.7, deep + 0.3, edge)) * 0.26 * (1 - 0.3 * (grain - 0.5))
                }
            }
            // The paper left clean for an accent: the wash goes round it.
            let held = Double(fields.hole[k])
            let al = max(A * (0.96 - 0.04 * dry), halo) * Paint.step(-0.45, 0.45, held)
            if al <= 0 { continue }
            let cr: Double, cg: Double, cb: Double
            if sum > 0 {
                cr = exp(r / sum)
                cg = exp(g / sum)
                cb = exp(b / sum)
            } else {
                cr = exp(logs[near][0])
                cg = exp(logs[near][1])
                cb = exp(logs[near][2])
            }
            // Two paints together are a little darker than either.
            let both = sum > 0 ? 4 * (w1 / sum) * (w2 / sum) : 0
            let rim = Paint.step(-3.6, -0.8, max(edge, -held)) * dry
            let shade = (1 - 0.13 * both) * (1 - 0.16 * rim) * (1 + 0.1 * (low - 0.5) * dry) * (1 - 0.1 * (grain - 0.5))
            let q = 4 * k
            out.bytes[q] = Paint.byte(cr * shade)
            out.bytes[q + 1] = Paint.byte(cg * shade)
            out.bytes[q + 2] = Paint.byte(cb * shade)
            out.bytes[q + 3] = Paint.byte(255 * al)
        }
        for (j, touch) in touches.enumerated() { lay(touch, fields.touched[j], age: age - touch.at, index: Double(j), fields: fields, into: &out) }
        // Dry: nothing of it changes any more, and what it was worked out from can go.
        if age >= length { self.fields = nil }
        return out
    }

    /// An accent in its round of clean paper: a drop of its own paint,
    /// pure where nothing is under it. On one side it stops short of the
    /// wash about it and paper stays between them; on the other it goes
    /// over the wash and, while both are wet, runs out into it and mixes
    /// with it. It dries with the pigment gathered at its rim.
    private func lay(_ touch: Touch, _ place: (left: Int, right: Int, top: Int, bottom: Int, away: [Float]), age: Double, index: Double,
                     fields: Fields, into out: inout PaintFrame) {
        guard age > 0, place.left <= place.right else { return }
        let S = Double(Paint.scale), pad = Paint.pad
        let grow = 1 - pow(1 - min(1, age / Self.accents.spread), 2.4), dry = Paint.ease((age - 0.8) / 2.2), runs = Paint.ease((age - 0.15) / 1.6)
        let least = touch.round - Self.round.gap
        var p = 0
        for row in place.top...place.bottom {
            for column in place.left...place.right {
                let away = Double(place.away[p]) + (1 - grow) * least
                p += 1
                if away > 6 { continue }
                let k = row * wide + column, q = 4 * k
                let x = -pad + (Double(column) + 0.5) / S, y = -pad + (Double(row) + 0.5) / S
                let under = Double(out.bytes[q + 3]) / 255
                let low = Double(fields.low[k]), grain = Double(fields.grain[k])
                // Where it runs: into the wash it lies on, further in places, never over bare paper.
                let damp = (0.45 + 0.55 * Paint.step(0.4, 0.66, Paint.noise(x / 6, y / 6, 320 + 11 * index + seed))) * runs * under
                let soft = 0.5 + 3.2 * damp
                let inside = 1 - Paint.step(-soft, soft, away - 2.2 * damp)
                if inside <= 0.004 { continue }
                let rim = Paint.step(-3.0, -0.7, away) * dry * (1 - 0.8 * damp)
                let shade = (1 - 0.2 * rim) * (1 + 0.07 * (1 - Paint.step(-5, -2, away)) * dry) * (1 + 0.1 * (low - 0.5) * dry) * (1 - 0.1 * (grain - 0.5))
                let much = inside * (0.95 - 0.04 * dry)
                for c in 0..<3 {
                    let below = Double(out.bytes[q + c])
                    // Over the wash the two paints mix, the more the nearer the drop's edge.
                    let wash = 0.1 + 0.26 * Paint.step(-3, 0.5, away) * runs
                    let glaze = under > 0 ? exp((1 - wash) * log(max(4, touch.rgb[c])) + wash * log(max(4, below))) : touch.rgb[c]
                    let mine = glaze * shade
                    out.bytes[q + c] = Paint.byte(under > 0 ? below + (mine - below) * much : mine)
                }
                out.bytes[q + 3] = Paint.byte(255 * max(under, much))
            }
        }
    }
}

/// One paint as a dab of watercolour: it spreads from the middle, then
/// dries with a darker rim and, in places, a ring the paper soaked up.
/// A likely paint, not one the sources name, is the same dab (Mateusz
/// 2026-11-11 18:39: „zawsze duże (nawet gdy niepewne)”).
final class WaterDab: PaintPainter, @unchecked Sendable {
    let wide = Int(2 * Paint.half) * Paint.scale
    let high = Int(2 * Paint.half) * Paint.scale
    let length = 6.0

    private let rgb: [Double]
    private let seed: Double
    private let turns: (Double, Double, Double)

    init(rgb: [Double], index: Int, seed: Int) {
        self.rgb = rgb
        self.seed = Double(seed + index)
        var random = PaintRandom(seed + 300 + index)
        turns = (random.next() * 6.28, random.next() * 6.28, random.next() * 6.28)
    }

    func frame(age: Double) -> PaintFrame {
        var out = PaintFrame(wide: wide, high: high)
        let age = min(length, age)
        guard age > 0 else { return out }
        let S = Double(Paint.scale), half = Paint.half, full = 11.2
        let grow = 1 - pow(1 - min(1, age / 0.55), 2.4)
        let dry = Paint.ease((age - 0.9) / 2.2), soak = Paint.ease((age - 1.1) / 2.6)
        for k in 0..<(wide * high) {
            let x = -half + (Double(k % wide) + 0.5) / S, y = -half + (Double(k / wide) + 0.5) / S
            let th = atan2(y, x), dist = (x * x + y * y).squareRoot()
            if dist > full * 1.2 + 8 { continue }
            let round = full * (1 + 0.07 * sin(2 * th + turns.0) + 0.05 * sin(3 * th + turns.1) + 0.035 * sin(5 * th + turns.2))
            let ragged = 1.6 * (Paint.noise(x / 4, y / 4, 11 + seed) - 0.5)
            let low = Paint.noise(x / 9, y / 9, 31 + seed), grain = Paint.noise(x / 1.5, y / 1.5, 41 + seed)
            let e = dist - round * grow + ragged * grow
            let inside = 1 - Paint.step(-0.5, 0.5, e)
            let deep = soak * Paint.step(0.42, 0.62, Paint.noise(x / 12, y / 12, 51 + seed)) * (3 + 2.6 * low)
            let ring = deep > 0 ? Paint.step(0, 0.5, deep) * (1 - Paint.step(deep - 0.7, deep + 0.3, e)) : 0
            let lip = ring * Paint.step(deep - 1.5, deep - 0.4, e)
            let al = max(inside * (0.96 - 0.05 * dry), ring * (0.3 + 0.18 * lip) * (1 - 0.3 * (grain - 0.5)))
            if al <= 0 { continue }
            let rim = Paint.step(-3.4, -0.9, e) * dry
            let shade = (1 - 0.17 * rim) * (1 + 0.1 * (1 - Paint.step(-6, -2, e)) * dry) * (1 + 0.12 * (low - 0.5) * dry) * (1 - 0.12 * (grain - 0.5))
            let q = 4 * k
            out.bytes[q] = Paint.byte(rgb[0] * shade)
            out.bytes[q + 1] = Paint.byte(rgb[1] * shade)
            out.bytes[q + 2] = Paint.byte(rgb[2] * shade)
            out.bytes[q + 3] = Paint.byte(255 * al)
        }
        return out
    }
}

// MARK: - Oil

/// Paint with a little height, in a calm light from the upper left
/// (Mateusz 2026-11-11 12:02: „Mniej błyszczące, mniej przestrzenne.
/// Trochę spokojniej”), and the shadow it throws on the paper.
enum OilLight {
    static let light = (-0.5, -0.72, 0.48)
    static let steep = 0.95

    /// `height`, `cover` and the paint's colour a pixel each → the picture.
    static func shade(height: [Float], red: [Float], green: [Float], blue: [Float], cover: [Float],
                      wide: Int, high: Int, dark: Bool) -> PaintFrame {
        var out = PaintFrame(wide: wide, high: high)
        let S = Double(Paint.scale), L = light
        var mid = (L.0, L.1, L.2 + 1)
        let long = (mid.0 * mid.0 + mid.1 * mid.1 + mid.2 * mid.2).squareRoot()
        mid = (mid.0 / long, mid.1 / long, mid.2 / long)
        func at(_ x: Int, _ y: Int) -> Double { x < 0 || y < 0 || x >= wide || y >= high ? 0 : Double(height[y * wide + x]) }
        func cov(_ x: Int, _ y: Int) -> Double { x < 0 || y < 0 || x >= wide || y >= high ? 0 : Double(cover[y * wide + x]) }
        let paper = dark ? 0.0 : 38.0
        for y in 0..<high {
            for x in 0..<wide {
                let k = y * wide + x, q = 4 * k, a = Double(cover[k])
                // The shadow the paint throws on the paper, away from the light.
                var sh = 0.0
                if a < 1 {
                    let d = S
                    sh = 0.55 * cov(x - Int((0.7 * d).rounded()), y - Int((1.1 * d).rounded()))
                        + 0.25 * cov(x - Int((1.3 * d).rounded()), y - Int((1.9 * d).rounded()))
                        + 0.2 * cov(x - Int((0.4 * d).rounded()), y - Int((0.6 * d).rounded()))
                    sh *= (dark ? 0.34 : 0.17) * (1 - a)
                }
                if a <= 0, sh <= 0 { continue }
                if a <= 0 {
                    out.bytes[q] = Paint.byte(paper)
                    out.bytes[q + 1] = Paint.byte(paper)
                    out.bytes[q + 2] = Paint.byte(paper)
                    out.bytes[q + 3] = Paint.byte(255 * sh)
                    continue
                }
                let gx = (at(x + 1, y) - at(x - 1, y)) * S / 2 * steep, gy = (at(x, y + 1) - at(x, y - 1)) * S / 2 * steep
                let nl = (gx * gx + gy * gy + 1).squareRoot(), nx = -gx / nl, ny = -gy / nl, nz = 1 / nl
                let dif = max(0, nx * L.0 + ny * L.1 + nz * L.2)
                let spec = pow(max(0, nx * mid.0 + ny * mid.1 + nz * mid.2), 18)
                let lit = 0.74 + 0.5 * dif, gl = 255 * 0.07 * spec
                let r = min(255, Double(red[k]) * lit + gl), g = min(255, Double(green[k]) * lit + gl), b = min(255, Double(blue[k]) * lit + gl)
                // At its edge the paint is over its own shadow.
                let al = a + (1 - a) * sh
                out.bytes[q] = Paint.byte(r * a / al + paper * (1 - a / al))
                out.bytes[q + 1] = Paint.byte(g * a / al + paper * (1 - a / al))
                out.bytes[q + 2] = Paint.byte(b * a / al + paper * (1 - a / al))
                out.bytes[q + 3] = Paint.byte(255 * al)
            }
        }
        return out
    }
}

/// The palette in oil (sketch 30; Mateusz 12:12, with photographs of real
/// swatches: „mniej równomierne pociągnięcia. Przy mniejszych - muśnięcia
/// / pacnięcia”). A pull of a loaded brush comes down full and opaque,
/// with an uneven round start; it goes on as long as the paint lasts,
/// narrower, its sides wandering; and it ends dry, the bristles skipping
/// over the tooth of the ground. No two are alike.
///
/// The bar (sketch 31; Mateusz 2026-11-11 18:59, accepted 19:22) is the
/// picture's main colours laid as one band, each pull begun in the wet
/// paint of the one before so that colour goes over into colour, its
/// small colours as touches on top, and under it all the paper soaks the
/// oil up. See `pulls(_:width:seed:)` and `soak(_:stain:age:)`.
final class OilStrip: PaintPainter, @unchecked Sendable {
    let wide: Int
    let high: Int
    let length: Double
    /// When the last pull is done.
    let last: Double
    let pulls: [Pull]

    private let shares: [PaintShare]
    private let seed: Double
    private let dark: Bool
    /// A paint's swatch: the paper round it soaks a little of its oil up.
    private let soaks: Bool
    private var laid: [Laid]?
    private var done: PaintFrame?
    /// The bar: what its paint leaves in the paper round it.
    private var stain: Stain?
    /// The bar with all its paint down, before the paper soaks any up.
    private var wet: PaintFrame?
    private let width: Double

    static let apart = 0.27, stroke = 0.44
    /// About how long one pull of a colour is; a wider colour is laid in
    /// several, each begun `back` over the one before, in its wet paint.
    static let stride = 64.0, back = 16.0
    /// Under this a colour is an accent: a touch of the brush on top of
    /// the others, not a pull among them.
    static let touch = Paint.touch
    /// How long after the last pull the accents come, and how far apart.
    static let accents = (after: 0.12, apart: 0.24)

    /// One pull: where it begins and ends along the bar, and what makes it
    /// its own: how it leans, how wide it is, how long the paint lasts,
    /// how fast it gives out, how much it narrows.
    struct Pull: Sendable {
        var a: Double, e: Double
        var touch: Bool
        var tilt: Double, dy: Double, wide: Double, full: Double, fall: Double, taper: Double
        var p1: Double, p2: Double, sway: Double, blob: Double
        /// Its paint, and the wet paint it begins in (nil: none).
        var rgb: [Double] = [], under: [Double]?
        /// How far its bristles carry the paint they picked up: the least, and how much further the best of them.
        var carry = (5.0, 13.0)
        /// How much of that paint is on the brush as it begins; it is gone by the middle of the pull.
        var blend = 0.0
        /// How much of a mark its coming down leaves: all of it on bare ground, little in wet paint.
        var mark = 1.0
        /// An accent: on top of the other paint.
        var on = false
        /// When it begins and how long it takes.
        var at = 0.0, takes = 0.0
    }

    /// What the paint leaves in the paper round it, a pixel each: how
    /// near the paint is, how much further the oil gets there than
    /// elsewhere, and the paint's colour near there.
    private struct Stain {
        var near: [Float], wander: [Float]
        var red: [Float], green: [Float], blue: [Float]
    }

    /// A pull as it lies when all of it is down: only where there is paint.
    private struct Laid {
        var index: [Int32] = []
        var along: [Float] = [], cover: [Float] = [], height: [Float] = [], body: [Float] = []
        var red: [Float] = [], green: [Float] = [], blue: [Float] = []
    }

    init(shares: [PaintShare], width: Double, seed: Int, dark: Bool) {
        self.shares = shares
        self.seed = Double(seed)
        self.dark = dark
        soaks = false
        self.width = width
        wide = Int((width + 2 * Paint.pad).rounded()) * Paint.scale
        high = Int(Paint.bar + 2 * Paint.pad) * Paint.scale
        pulls = Self.pulls(shares, width: width, seed: seed)
        last = pulls.map { $0.at + $0.takes }.max() ?? 0
        length = last + Self.lag + Self.soak
    }

    /// One paint's swatch: a single touch of the brush, as the bar's
    /// small colours are (Mateusz 2026-11-11 13:50: „kropki kolorów farb
    /// olejnych / akryli etc. rób pacnieciami jak na pasku przy
    /// niewielkiej ilości koloru”), a little bigger than the dot out of
    /// the tube it was before, and the paper round it soaks a little of
    /// the oil up (13:51: „mogą być trochę większe niż obecne kropki.
    /// Wokół nich tło może trochę nasiąkać jak przy farbach olejnych”).
    /// A likely paint, not one the sources name, is as big a touch
    /// (18:39: „zawsze duże (nawet gdy niepewne)”).
    init(touch rgb: [Double], index: Int, seed: Int, dark: Bool) {
        shares = [PaintShare(rgb: rgb, weight: 1)]
        self.seed = Double(seed + 131 + 9 * index)
        self.dark = dark
        soaks = true
        width = Paint.swatch
        wide = Int(Paint.swatch + 2 * Paint.pad) * Paint.scale
        high = Int(Paint.bar + 2 * Paint.pad) * Paint.scale
        last = Self.dab
        length = last + Self.soak
        var pull = Self.touch(seed: seed + 300 + index)
        pull.rgb = rgb
        pull.takes = Self.dab
        pulls = [pull]
    }

    /// How long the paper round the paint goes on soaking, and how long
    /// after the paint is down it begins to show.
    static let soak = 3.2, lag = 0.25
    /// How long a touch of the brush takes.
    static let dab = 0.3

    /// The one touch of a paint's swatch, across its 26 points.
    static func touch(seed: Int) -> Pull {
        var random = PaintRandom(seed)
        var pull = varied(a: -3, e: 21.5, touch: true, random: &random)
        pull.wide += 1.2
        return pull
    }

    /// A pull from `a` to `e`, its own in everything else.
    private static func varied(a: Double, e: Double, touch: Bool, random: inout PaintRandom) -> Pull {
        // The order the numbers are drawn in is the sketch's.
        let tilt = (touch ? 0.2 : 0.05) * (random.next() * 2 - 1)
        let dy = (touch ? 2.2 : 1.5) * (random.next() * 2 - 1)
        let wide = Paint.bar / 2 - (touch ? 1.5 : 0.4) - 1.8 * random.next()
        let full = touch ? 0.3 + 0.2 * random.next() : 0.2 + 0.32 * random.next()
        let fall = 0.8 + 0.8 * random.next()
        let taper = 0.2 + 0.32 * random.next()
        let p1 = random.next() * 6.28, p2 = random.next() * 6.28
        let sway = 0.5 + 1.1 * random.next()
        let blob = 0.75 + 0.5 * random.next()
        return Pull(a: a, e: e, touch: touch, tilt: tilt, dy: dy, wide: wide, full: full, fall: fall, taper: taper,
                    p1: p1, p2: p2, sway: sway, blob: blob)
    }

    /// Two paints mixed: `much` of `other` in `paint`.
    static func mixed(_ paint: [Double], _ other: [Double], _ much: Double) -> [Double] {
        zip(paint, other).map { exp(log(max(4, $0)) + (log(max(4, $1)) - log(max(4, $0))) * much) }
    }

    /// The pulls along a bar `width` wide, in the order they are made:
    /// the picture's main colours from the left, each as wide as its
    /// share and each pull begun in the wet paint of the one before, so
    /// one colour goes over into the next the way a painter lays a
    /// gradient with single pulls (Mateusz 2026-11-11 18:59: „bliżej
    /// siebie, mogą się trochę mieszać ze sobą i dawać płynniejsze
    /// przejście. Tak jakby malarz poszczególnymi pociągnięciami malował
    /// gradient”); then the small colours as touches on top („Akcenty z
    /// końca jako pacnięcia na wierzchu”).
    static func pulls(_ shares: [PaintShare], width: Double, seed: Int) -> [Pull] {
        guard !shares.isEmpty else { return [] }
        let total = max(shares.reduce(0) { $0 + $1.weight }, 0.000_001)
        // The smallest first, while enough of the picture stays in the pulls.
        let accent = Paint.accents(shares, width: width)
        let mains = shares.indices.filter { !accent[$0] }, small = shares.indices.filter { accent[$0] }
        let ground = max(mains.reduce(0) { $0 + shares[$1].weight }, 0.000_001), room = width - 6
        var random = PaintRandom(seed + 17), x = 0.0, at = 0.0
        var pulls = [Pull]()
        for (n, i) in mains.enumerated() {
            let w = room * shares[i].weight / ground, count = max(1, Int((w / stride).rounded()))
            for j in 0..<count {
                // No two pulls of a colour are as long.
                func edge(_ q: Int) -> Double {
                    q == 0 || q == count ? Double(q) : Double(q) + 0.36 * (Paint.hash(Double(q), Double(i), Double(seed) + 23) - 0.5)
                }
                let from = x + w * edge(j) / Double(count), to = x + w * edge(j + 1) / Double(count)
                var pull = varied(a: pulls.isEmpty ? from : from - back, e: to, touch: false, random: &random)
                // Where two colours meet, the pull next to the other colour has some of it on the brush.
                var rgb = shares[i].rgb
                if j == 0, n > 0, count >= 2 {
                    rgb = mixed(rgb, shares[mains[n - 1]].rgb, 0.32)
                } else if j == count - 1, n < mains.count - 1, count >= 3 {
                    rgb = mixed(rgb, shares[mains[n + 1]].rgb, 0.2)
                }
                pull.rgb = rgb
                pull.under = pulls.last?.rgb
                pull.carry = (10, 28)
                pull.blend = 0.5
                pull.mark = pulls.isEmpty ? 1 : 0.4
                pull.dy *= 0.6
                pull.at = at
                pull.takes = stroke
                pulls.append(pull)
                at += apart
            }
            x += w
        }
        // Only the last pull runs dry and thin: the others are gone over before they do.
        for k in pulls.indices.dropLast() {
            pulls[k].full = 0.55 + 0.5 * pulls[k].full
            pulls[k].taper *= 0.45
        }
        let seams = pulls.dropFirst().map(\.a)
        at += stroke - apart + accents.after
        var spots = [(at: Double, long: Double)]()
        for (n, i) in small.enumerated() {
            let wish = room * (0.1 + 0.8 * (Double(n) + 0.5 + 0.5 * (random.next() - 0.5)) / Double(small.count))
            let long = 30 + 12 * min(1, width * shares[i].weight / total / touch)
            // On the body of a pull, not across the place where one begins, and clear of the other accents:
            // the nearest such place to where it would be.
            func free(_ spot: Double) -> Bool {
                let from = spot - long / 2, to = spot + long / 2
                if from < 4 || to > room - 16 { return false }
                for seam in seams where seam + 3 > from - 5 && seam + 3 < to + 10 { return false }
                for other in spots where abs(other.at - spot) < (other.long + long) / 2 + 9 { return false }
                return true
            }
            var spot = wish
            for step in 0..<40 {
                let right = wish + 3 * Double(step), left = wish - 3 * Double(step)
                if free(right) {
                    spot = right
                    break
                }
                if free(left) {
                    spot = left
                    break
                }
            }
            spots.append((spot, long))
            var pull = varied(a: spot - long / 2, e: spot + long / 2, touch: true, random: &random)
            pull.rgb = shares[i].rgb
            pull.on = true
            pull.wide *= 0.92
            pull.at = at
            pull.takes = dab
            pulls.append(pull)
            at += accents.apart
        }
        return pulls
    }

    private func ridge(_ i: Double, _ v: Double) -> Double {
        0.5 * Paint.noise(v / 0.62, 3.7 * i, 71 + seed) + 0.5 * Paint.noise(v / 1.9, 3.7 * i, 72 + seed)
    }

    /// Every pull as it lies when all of it is down.
    private func lay() -> [Laid] {
        let S = Double(Paint.scale), pad = Paint.pad, Hs = Paint.bar
        var all = [Laid]()
        for (i, P) in pulls.enumerated() {
            var laid = Laid()
            let di = Double(i), len = P.e - P.a, cy = Hs / 2 + P.dy, c = P.rgb
            let x0 = max(0, Int(((P.a - 6 + pad) * S).rounded(.down))), x1 = min(wide, Int(((P.e + 13 + pad) * S).rounded(.up)))
            guard x1 > x0 else {
                all.append(laid)
                continue
            }
            for py in 0..<high {
                for px in x0..<x1 {
                    let x = -pad + (Double(px) + 0.5) / S, y = -pad + (Double(py) + 0.5) / S, u = x - P.a
                    let mid = cy + P.tilt * (x - (P.a + P.e) / 2) + P.sway * sin(x / 23 + P.p1) + 0.4 * sin(x / 9 + P.p2)
                    let v = y - mid, gone = min(1.3, max(0, u / len))
                    // How much paint is left on the brush here: all of it at first, then less and less.
                    let spent = max(0, (gone - P.full) / (1.22 - P.full))
                    let load = max(0, 1 - pow(spent, P.fall)) * (1 - 0.45 * Paint.step(1, 1.25, gone))
                    // Its sides: fuller just after the start, narrower as it goes, each wandering on its own, more as the brush dries.
                    let prof = (0.8 + 0.2 * Paint.ease(u / 5)) * (1 - P.taper * Paint.ease((gone - 0.25) / 0.8)), rag = 1.1 + 1.5 * gone
                    let below = v > 0 ? 3.0 : 0
                    let wide = P.wide * prof + rag * (Paint.noise(x / 7, 1.5 + below, 91 + di + seed) - 0.5)
                        + 0.5 * (Paint.noise(x / 2.2, 5.5 + below, 93 + di + seed) - 0.5)
                    let side = wide - abs(v)
                    if side < -0.6 { continue }
                    let br = ridge(di, v), slow = Paint.noise(x / 17, v / 2.4, 81 + 5 * di + seed)
                    // The start: round and uneven, where the brush came down.
                    let across = min(1, abs(v) / max(1, wide))
                    let start = 5.5 * P.blob * (0.35 + 0.65 * P.mark) * (1 - max(0, 1 - pow(across, 2.4)).squareRoot()) + 1.6 * (Paint.noise(v / 2.6, 7.7 * di, 97 + seed) - 0.5)
                    if u - start < -0.6 { continue }
                    // Where the paint takes: everywhere while the brush is full; as it dries only where a
                    // bristle still carries some (streaks along the pull) and where the ground stands up
                    // to it (its tooth).
                    let streaks = Paint.noise(u / 15, v / 0.75, 141 + 3 * di + seed)
                    let tooth = 0.6 * Paint.noise(x / 0.85, y / 0.85, 151 + seed) + 0.4 * Paint.noise(x / 2.3, y / 2.3, 152 + seed)
                    let need = 0.44 * streaks + 0.56 * tooth
                    let here = load * (1 - 0.3 * across * across) + 0.14 * (Paint.noise(u / 8, 2.1 * di, 161 + seed) - 0.5) * Paint.step(0, 0.3, gone)
                    let takes = Paint.step(need - 0.09, need + 0.09, here * 1.32 - 0.02)
                    let cover = Paint.step(-0.5, 0.5, side) * Paint.step(-0.5, 0.5, u - start) * takes
                    if cover <= 0 { continue }
                    // How high it stands: more where there is more of it, most where the brush came down; ridges along the bristles.
                    let sidelip = exp(-pow((side - 1.3) / 1.25, 2))
                    let down = exp(-pow((u - 3.4 * P.blob) / 3.6, 2)) * Paint.step(0, 2, side)
                    var hgt = ((0.55 + 0.3 * slow) + 0.34 * (br - 0.5) * (0.4 + 0.6 * slow) + 0.4 * sidelip) * (0.18 + 0.82 * here) + 0.8 * down * P.blob * P.mark
                    hgt = max(0.05, hgt) * Paint.step(0, 1.5, side) * Paint.step(0, 1.6, u - start) + 0.1
                    let streak = 1 + 0.1 * (Paint.noise(v / 1.1, 2.3 * di + x / 60, 131 + seed) - 0.5) + 0.06 * (slow - 0.5)
                    var cr = c[0], cg = c[1], cb = c[2]
                    // Over the pull before, which is still wet, the two paints mix: the bristles that picked
                    // the other one up carry it on a little way, each as far as it took.
                    if let under = P.under {
                        let carry = Paint.noise(v / 1.0, 2.9 * di, 111 + seed), far = P.carry.0 + P.carry.1 * pow(carry, 1.8), dd = u / far
                        let streaks = (1 - Paint.step(0.35, 1, dd)) * (0.4 + 0.6 * Paint.step(0.25, 0.6, carry)) * 0.78
                        let w = 1 - (1 - streaks) * (1 - P.blend * (1 - Paint.step(0, 0.55 * len, u)))
                        if w > 0 {
                            let mix = Self.mixed(c, under, w)
                            cr = mix[0]
                            cg = mix[1]
                            cb = mix[2]
                        }
                    }
                    laid.index.append(Int32(py * self.wide + px))
                    laid.along.append(Float(u))
                    laid.cover.append(Float(cover))
                    laid.height.append(Float(hgt))
                    // Thin paint lets the ground through.
                    laid.body.append(Float(0.62 + 0.38 * min(1, here * 1.7)))
                    laid.red.append(Float(cr * streak))
                    laid.green.append(Float(cg * streak))
                    laid.blue.append(Float(cb * streak))
                }
            }
            all.append(laid)
        }
        return all
    }

    func frame(age: Double) -> PaintFrame {
        if let done, age >= length { return done }
        let age = min(age, length)
        guard age > 0, !pulls.isEmpty else { return PaintFrame(wide: wide, high: high) }
        if laid == nil { laid = lay() }
        guard let laid else { return PaintFrame(wide: wide, high: high) }
        var out: PaintFrame
        if soaks {
            let paint = painted(laid, age: age)
            out = OilLight.shade(height: paint.height, red: paint.red, green: paint.green, blue: paint.blue, cover: paint.cover,
                                 wide: wide, high: high, dark: dark)
            soak(&out, cover: paint.cover, age: age - last)
        } else {
            if stain == nil { stain = stained(painted(laid, age: length)) }
            if let wet, age >= last {
                out = wet
            } else {
                let paint = painted(laid, age: age)
                out = OilLight.shade(height: paint.height, red: paint.red, green: paint.green, blue: paint.blue, cover: paint.cover,
                                     wide: wide, high: high, dark: dark)
                if age >= last { wet = out }
            }
            if let stain { soak(&out, stain: stain, age: age) }
        }
        if age >= length {
            done = out
            self.laid = nil
            stain = nil
            wet = nil
        }
        return out
    }

    private struct Down {
        var height: [Float], cover: [Float], red: [Float], green: [Float], blue: [Float]
    }

    /// The paint that is down at `age`: how high it stands, how much of
    /// it there is and its colour, a pixel each.
    private func painted(_ laid: [Laid], age: Double) -> Down {
        let n = wide * high
        var H = [Float](repeating: 0, count: n), A = [Float](repeating: 0, count: n)
        var R = [Float](repeating: 0, count: n), G = [Float](repeating: 0, count: n), B = [Float](repeating: 0, count: n)
        for (i, P) in pulls.enumerated() {
            let part = min(1, (age - P.at) / P.takes)
            if part <= 0 { continue }
            let reach = P.e - P.a + 11, head = -3 + (reach + 6) * Paint.ease(part)
            let pull = laid[i]
            for j in pull.index.indices {
                let u = Double(pull.along[j])
                if u > head + 1 { continue }
                let cover = Double(pull.cover[j]) * Paint.step(-1, 1, head - u)
                if cover <= 0 { continue }
                let k = Int(pull.index[j]), hgt = Double(pull.height[j])
                let body = cover * Double(pull.body[j]), was = Double(A[k]), on = body + was * (1 - body)
                if was > 0 {
                    R[k] = Float((Double(pull.red[j]) * body + Double(R[k]) * was * (1 - body)) / on)
                    G[k] = Float((Double(pull.green[j]) * body + Double(G[k]) * was * (1 - body)) / on)
                    B[k] = Float((Double(pull.blue[j]) * body + Double(B[k]) * was * (1 - body)) / on)
                    // An accent stands on the paint under it.
                    H[k] = P.on ? Float(Double(H[k]) * (1 - 0.3 * cover) + 0.75 * hgt * cover)
                        : Float(max(Double(H[k]) * (1 - 0.5 * cover), hgt * cover))
                    A[k] = Float(on)
                } else {
                    H[k] = Float(hgt * cover)
                    A[k] = Float(body)
                    R[k] = pull.red[j]
                    G[k] = pull.green[j]
                    B[k] = pull.blue[j]
                }
            }
        }
        return Down(height: H, cover: A, red: R, green: G, blue: B)
    }

    /// `values`, each the mean of those up to `reach` pixels from it,
    /// taken twice.
    private func blurred(_ values: [Float], reach: Int) -> [Float] {
        var near = values
        var turn = [Float](repeating: 0, count: near.count)
        for _ in 0..<2 {
            for y in 0..<high {
                var sum: Float = 0
                for x in -reach..<wide + reach {
                    if x + reach < wide, x + reach >= 0 { sum += near[y * wide + x + reach] }
                    if x - reach - 1 >= 0, x - reach - 1 < wide { sum -= near[y * wide + x - reach - 1] }
                    if x >= 0, x < wide { turn[y * wide + x] = sum / Float(2 * reach + 1) }
                }
            }
            for x in 0..<wide {
                var sum: Float = 0
                for y in -reach..<high + reach {
                    if y + reach < high, y + reach >= 0 { sum += turn[(y + reach) * wide + x] }
                    if y - reach - 1 >= 0, y - reach - 1 < high { sum -= turn[(y - reach - 1) * wide + x] }
                    if y >= 0, y < high { near[y * wide + x] = sum / Float(2 * reach + 1) }
                }
            }
        }
        return near
    }

    /// How far out of the bar's paint its oil gets, in points (the blur's reach).
    static let seep = 4.0

    /// What the bar's paint, all of it down, leaves in the paper.
    private func stained(_ paint: Down) -> Stain {
        let reach = Int(Self.seep) * Paint.scale, S = Double(Paint.scale)
        let near = blurred(paint.cover, reach: reach)
        func tint(_ colour: [Float]) -> [Float] {
            let spread = blurred(zip(colour, paint.cover).map { $0 * $1 }, reach: reach)
            return zip(spread, near).map { $1 > 0.001 ? $0 / $1 : 0 }
        }
        var wander = [Float](repeating: 0, count: wide * high)
        for k in 0..<(wide * high) where near[k] > 0.01 {
            let x = (Double(k % wide) + 0.5) / S, y = (Double(k / wide) + 0.5) / S
            wander[k] = Float(0.14 * (Paint.noise(x / 6, y / 5, 171 + seed) - 0.5) + 0.05 * (Paint.noise(x / 1.6, y / 1.6, 173 + seed) - 0.5))
        }
        return Stain(near: near, wander: wander, red: tint(paint.red), green: tint(paint.green), blue: tint(paint.blue))
    }

    /// Under the bar the paper soaks the paint's oil up (Mateusz
    /// 2026-11-11 18:59: „także dodaj „tłustą plamę” na papierze pod
    /// spodem”): a faint stain, a little of the paint's colour in it,
    /// that creeps out from under each pull once it is down, to an
    /// uneven edge, and stops.
    private func soak(_ out: inout PaintFrame, stain: Stain, age: Double) {
        let S = Double(Paint.scale)
        let oil = dark ? [128.0, 112, 84] : [170.0, 148, 104], share = dark ? 0.5 : 0.36
        let most = dark ? 0.2 : 0.24
        // When the pull over a place is down: they go from the left.
        let sweep = pulls.filter { !$0.on }.map { $0.at + $0.takes }.max() ?? 0
        for k in 0..<(wide * high) {
            let close = Double(stain.near[k])
            if close <= 0.01 { continue }
            let q = 4 * k, over = Double(out.bytes[q + 3]) / 255
            if over >= 0.995 { continue }
            let x = (Double(k % wide) + 0.5) / S - Paint.pad
            let down = sweep * min(1, max(0, x / max(1, width))) + Self.stroke * 0.5
            let soaked = Paint.ease((age - down - Self.lag) / Self.soak)
            if soaked <= 0 { continue }
            let far = 0.5 - soaked * (0.36 + Double(stain.wander[k]))
            let wet = Paint.step(far - 0.035, far + 0.035, close)
            if wet <= 0 { continue }
            let rim = 1 - Paint.step(far + 0.02, far + 0.16, close)
            let under = most * wet * (0.72 + 0.28 * rim) * (0.5 + 0.5 * soaked), all = over + (1 - over) * under
            let paint = [Double(stain.red[k]), Double(stain.green[k]), Double(stain.blue[k])]
            for c in 0..<3 {
                let colour = paint[c] * share + oil[c] * (1 - share)
                out.bytes[q + c] = Paint.byte((Double(out.bytes[q + c]) * over + colour * under * (1 - over)) / all)
            }
            out.bytes[q + 3] = Paint.byte(255 * all)
        }
    }

    /// The paper round the paint soaks its oil up: a faint stain, a
    /// little of the paint's colour in it, that creeps out from under the
    /// paint to an uneven edge and stops. `age`: since the touch was down.
    private func soak(_ out: inout PaintFrame, cover: [Float], age: Double) {
        let soaked = Paint.ease(age / Self.soak)
        guard soaked > 0 else { return }
        // How near the paint a pixel is: its cover, blurred twice.
        var near = cover
        var turn = [Float](repeating: 0, count: near.count)
        let reach = 3 * Paint.scale
        for _ in 0..<2 {
            for y in 0..<high {
                var sum: Float = 0
                for x in -reach..<wide + reach {
                    if x + reach < wide, x + reach >= 0 { sum += near[y * wide + x + reach] }
                    if x - reach - 1 >= 0, x - reach - 1 < wide { sum -= near[y * wide + x - reach - 1] }
                    if x >= 0, x < wide { turn[y * wide + x] = sum / Float(2 * reach + 1) }
                }
            }
            for x in 0..<wide {
                var sum: Float = 0
                for y in -reach..<high + reach {
                    if y + reach < high, y + reach >= 0 { sum += turn[(y + reach) * wide + x] }
                    if y - reach - 1 >= 0, y - reach - 1 < high { sum -= turn[(y - reach - 1) * wide + x] }
                    if y >= 0, y < high { near[y * wide + x] = sum / Float(2 * reach + 1) }
                }
            }
        }
        let S = Double(Paint.scale), paint = shares[0].rgb
        let oil = dark ? [128.0, 112, 84] : [170.0, 148, 104], share = dark ? 0.5 : 0.36
        let stain = (0..<3).map { paint[$0] * share + oil[$0] * (1 - share) }
        let most = dark ? 0.2 : 0.24
        for k in 0..<(wide * high) {
            let close = Double(near[k])
            if close <= 0.01 { continue }
            let q = 4 * k, over = Double(out.bytes[q + 3]) / 255
            if over >= 0.995 { continue }
            let x = (Double(k % wide) + 0.5) / S, y = (Double(k / wide) + 0.5) / S
            // It gets further in some places than in others.
            let far = 0.5 - soaked * (0.36 + 0.12 * (Paint.noise(x / 5, y / 5, 171 + seed) - 0.5) + 0.05 * (Paint.noise(x / 1.6, y / 1.6, 173 + seed) - 0.5))
            let wet = Paint.step(far - 0.035, far + 0.035, close)
            if wet <= 0 { continue }
            // A little more of it where it stopped.
            let rim = 1 - Paint.step(far + 0.02, far + 0.16, close)
            let under = most * wet * (0.72 + 0.28 * rim) * (0.5 + 0.5 * soaked), all = over + (1 - over) * under
            for c in 0..<3 {
                out.bytes[q + c] = Paint.byte((Double(out.bytes[q + c]) * over + stain[c] * under * (1 - over)) / all)
            }
            out.bytes[q + 3] = Paint.byte(255 * all)
        }
    }
}


// MARK: - Pastel, crayon, chalk

/// The palette as a coloured sketch (sketch 27; Mateusz 11:51: „Pastel,
/// kredka i kreda - super”): each colour hatched in with quick strokes
/// that lean the same way, one after another from the left. The stick
/// only catches the tooth of the paper, so the strokes are grainy and the
/// paper shows through; where two colours meet their strokes run over
/// each other. This is where each stroke goes; `PaintedColour.swift`
/// draws them.
struct DryPlan: Sendable {
    /// One stroke of the stick, in points from the bar's upper left corner.
    struct Stroke: Sendable {
        var colour: Int
        /// Which colour's turn it is made in, and when in that turn, 0…1.
        var turn: Int
        var part: Double
        var from: (x: Double, y: Double), to: (x: Double, y: Double)
        var bow: Double, wide: Double, alpha: Double
        /// Pressed hard: the stick fills the paper's tooth.
        var press = false
    }

    var strokes: [Stroke]
    /// When the last stroke is begun, and when nothing changes any more.
    var last: Double
    var length: Double

    static let apart = 0.34, stroke = 0.5
    /// An accent's patch: how far down the bar it begins (of the bar's
    /// height) and how far under the bar's foot it goes (Mateusz
    /// 2026-11-12 11:02: „akcent - mocniej docisnąć. może być trochę
    /// niżej i wystawać pod linię ogólnego gradientu”).
    static let accent = (top: 0.38, under: 6.0)
    /// How much of the paper's tooth a stroke pressed hard leaves open.
    static let pressed = 0.5
    /// How long one stroke takes.
    static let quick = 0.07

    /// The colours hatched side by side, the accents hatched over them
    /// afterwards (Mateusz 2026-11-12 10:47: „żeby akcenty leżały "na
    /// wierzchu"”): a small patch each, pressed harder and the other
    /// way, so that it sits on the hatching under it.
    init(shares: [PaintShare], width: Double, seed: Int) {
        let Hs = Paint.bar
        let accent = Paint.accents(shares, width: width)
        let mains = shares.indices.filter { !accent[$0] }, small = shares.indices.filter { accent[$0] }
        let m = mains.count
        let spans = Paint.spans(mains.map { shares[$0] }, width: width)
        var random = PaintRandom(seed + 23)
        var strokes = [Stroke]()
        for (n, i) in mains.enumerated() {
            let x0 = spans[n].0, w = spans[n].1 - spans[n].0
            let a = x0 - (n > 0 ? 6 : 0), e = x0 + w + (n < m - 1 ? 6 : 0)
            let count = max(4, Int(((e - a) / 2.7).rounded()))
            let lean = 7.5 + 2 * (random.next() - 0.5)
            for q in 0..<count {
                let cx = a + (e - a) * (Double(q) + 0.5 + 0.7 * (random.next() - 0.5)) / Double(count)
                let over = 1.5 + 3 * random.next() * random.next(), under = 1.2 + 3 * random.next() * random.next()
                let l = lean + 2.4 * (random.next() - 0.5)
                let bow = 1.6 * (random.next() - 0.5), wide = 2.3 + 1.3 * random.next(), alpha = 0.62 + 0.33 * random.next()
                strokes.append(Stroke(colour: i, turn: n, part: Double(q) / Double(count), from: (cx - l, Hs + under), to: (cx + l, -over),
                                      bow: bow, wide: wide, alpha: alpha))
            }
            // A few lighter ones back over it, the other way: the hand going over the patch again.
            let again = Int((Double(count) / 5).rounded())
            for q in 0..<again {
                let cx = a + 3 + (e - a - 6) * random.next(), l = -(4 + 3 * random.next())
                let y1 = Hs - 1 - 4 * random.next(), y2 = 1 + 4 * random.next()
                let bow = random.next() - 0.5, wide = 1.6 + random.next(), alpha = 0.3 + 0.2 * random.next()
                strokes.append(Stroke(colour: i, turn: n, part: 0.75 + 0.25 * Double(q) / Double(max(1, again)), from: (cx - l, y1), to: (cx + l, y2),
                                      bow: bow, wide: wide, alpha: alpha))
            }
        }
        let total = max(shares.reduce(0) { $0 + $1.weight }, 0.000_001)
        let longs = small.map { 16 + 8 * min(1, width * shares[$0].weight / total / Paint.touch) }
        let spots = Paint.spots(longs.map { $0 + 6 }, width: width, seams: spans.dropFirst().map(\.0), random: &random)
        for (n, i) in small.enumerated() {
            let a = spots[n] - longs[n] / 2, e = spots[n] + longs[n] / 2
            let count = max(6, Int((longs[n] / 2.5).rounded()))
            // The stick pressed hard, and the other way than the hatching under it (Mateusz 2026-11-12 11:21:
            // „akcent rysowany po skosie w drugą stronę (tak jak poprzednio)”).
            let slope = -(0.22 + 0.05 * (random.next() - 0.5))
            let top = Hs * Self.accent.top + 2 * (random.next() - 0.5), foot = Hs + Self.accent.under + 1.5 * (random.next() - 0.5)
            for q in 0..<count {
                let cx = a + (e - a) * (Double(q) + 0.5 + 0.5 * (random.next() - 0.5)) / Double(count)
                // Shorter at the patch's ends.
                let full = 0.72 + 0.28 * sin(Double.pi * (Double(q) + 0.5) / Double(count))
                let y1 = foot - (1 - full) * 5 + 2.6 * (random.next() - 0.5), y2 = top + (1 - full) * 6 + 3.4 * (random.next() - 0.5)
                let l = slope * (y1 - y2) + 0.8 * (random.next() - 0.5)
                let bow = 1.2 * (random.next() - 0.5), wide = 2.7 + 0.9 * random.next(), alpha = 0.9 + 0.1 * random.next()
                strokes.append(Stroke(colour: i, turn: m + n, part: 0.8 * Double(q) / Double(count), from: (cx - l, y1), to: (cx + l, y2),
                                      bow: bow, wide: wide, alpha: alpha, press: true))
            }
            // Gone over once more, to fill the patch.
            for q in 0..<2 {
                let cx = a + 2 + (e - a - 4) * random.next()
                let y1 = foot - 2 - 2 * random.next(), y2 = top + 2 + 3 * random.next(), l = slope * (y1 - y2) + 1.2 * (random.next() - 0.5)
                strokes.append(Stroke(colour: i, turn: m + n, part: 0.8 + 0.2 * Double(q) / 2, from: (cx - l, y1), to: (cx + l, y2),
                                      bow: random.next() - 0.5, wide: 2.4 + 0.8 * random.next(), alpha: 0.55 + 0.15 * random.next(), press: true))
            }
        }
        self.strokes = strokes
        last = Double(max(0, shares.count - 1)) * Self.apart + Self.stroke
        length = last + 1
    }

    /// How much of a stroke is made at `age`: under 0 none, from 1 all.
    func made(_ stroke: Stroke, age: Double) -> Double {
        (age - (Double(stroke.turn) * Self.apart + stroke.part * Self.stroke)) / Self.quick
    }

    /// One paint's scribble: the corners of its zigzag, in points from the
    /// middle of its swatch. A likely paint, not one the sources name,
    /// is hatched on as big a patch (Mateusz 2026-11-11 18:39: „zawsze
    /// duże (nawet gdy niepewne)”).
    static func scribble(index: Int, seed: Int) -> [(x: Double, y: Double)] {
        var random = PaintRandom(seed + 400 + index)
        let turns = 7, reach = 10.5, tall = 9.5
        var points = [(x: Double, y: Double)]()
        for q in 0...turns {
            let u = -reach + 2 * reach * Double(q) / Double(turns) + 1.2 * (random.next() - 0.5), up = q % 2 == 0
            points.append((u + (up ? 2.2 : -2.2), (up ? -tall : tall) * (0.8 + 0.25 * random.next())))
        }
        return points
    }

    /// The tooth of the paper, a pixel each: how much of the stick's
    /// colour stays there, 0…255.
    static func tooth(wide: Int, high: Int, seed: Int) -> [UInt8] {
        let S = Double(Paint.scale), s = Double(seed)
        var out = [UInt8](repeating: 0, count: wide * high)
        for k in 0..<(wide * high) {
            let px = (Double(k % wide) + 0.5) / S, py = (Double(k / wide) + 0.5) / S
            let g = 0.5 * Paint.noise(px / 0.55, py / 0.55, 41 + s) + 0.3 * Paint.noise(px / 1.3, py / 1.3, 42 + s) + 0.2 * Paint.noise(px / 4, py / 4, 43 + s)
            out[k] = Paint.byte(255 * (0.38 + 0.62 * Paint.step(0.36, 0.6, g)))
        }
        return out
    }
}
