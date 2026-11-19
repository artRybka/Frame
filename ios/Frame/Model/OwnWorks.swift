import Foundation

// "Dodaj własne dzieło" (Mateusz 2026-11-15): the photograph sent first, the
// work found in it, hints read off it, then the work added with what he
// wrote. Mirrors server `own_works.py` and `web/own_api.py`.

/// A photograph waiting for its work to be added: corners of the work on it
/// (0–1 across and down), nil when none was found or it was not asked.
struct OwnIncoming: Codable, Hashable, Sendable {
    var token: String
    var width: Int
    var height: Int
    var corners: [[Double]]? = nil
    /// "rectangle", "round", "irregular"; "" when not asked. Only a
    /// rectangle is cut (`non-rectangular-works`).
    var shape: String = ""
    /// The corners of a colour chart (ColorChecker) photographed beside
    /// the work; nil without one. The server set the photograph's colours
    /// by it (Mateusz 2026-11-16 22:25 UTC: "dodajmy obsługę. Oczywiście
    /// nie jako obowiązkową, ale opcjonalna").
    var chart: [[Double]]? = nil
    /// The phone may make the scan of this photograph itself and send it
    /// (`PhoneScan`): not where a chart set its colours on the server.
    /// nil from a server that takes no such scan (to 1.145.254).
    var phone: Bool? = nil
    /// Where a chart did: the phone may make the scan all the same, of
    /// its own photographs put in the chart's colours first, by the
    /// tables the server gives of it (`FrameBackend.ownChartTables`). nil
    /// from a server that gives none (to 1.145.256): it makes the scan.
    var tables: Bool? = nil
    /// The bend of the lens that took it, where the server knows it: the
    /// work is kept without it. The phone takes it out of what it shows
    /// him (`OwnPicture.straight`; the corners he sets on that go to the
    /// server as they are on the photograph taken) and of the scan it
    /// makes (`PhoneScan.make`). nil where it is not known, and from a
    /// server that straightens the work itself (to 1.145.258).
    var straight: OwnBend? = nil

    var aspect: Double { height > 0 ? Double(width) / Double(height) : 0.75 }
}

/// How a lens bends what it draws, as the server says it (`LensBend` in
/// `own_works.py`, `imaging/lens.py`): the one measured term `k1` about the
/// photograph's middle, or the camera's own `table` (how much further from
/// the lens's middle a point is drawn, at radii evenly from that middle,
/// `centre` 0–1 across and down the photograph, to its farthest corner).
struct OwnBend: Codable, Hashable, Sendable {
    var k1: Double = 0
    var table: [Double] = []
    var centre: [Double] = [0.5, 0.5]

    init(k1: Double = 0, table: [Double] = [], centre: [Double] = [0.5, 0.5]) {
        self.k1 = k1
        self.table = table
        self.centre = centre
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        k1 = try values.decodeIfPresent(Double.self, forKey: .k1) ?? 0
        table = try values.decodeIfPresent([Double].self, forKey: .table) ?? []
        centre = try values.decodeIfPresent([Double].self, forKey: .centre) ?? [0.5, 0.5]
    }

    var centreX: Double { centre.count == 2 ? centre[0] : 0.5 }
    var centreY: Double { centre.count == 2 ? centre[1] : 0.5 }

    /// As it goes back to the server with a scan straightened by it.
    var told: [String: Any] { ["k1": k1, "table": table, "centre": [centreX, centreY]] }
}

/// The first photograph with the glare taken out by the side ones (the
/// scan of three, Mateusz 2026-11-16): how many could be laid over it and
/// how much of it they gave (0–1; 0, nothing changed). `doubt`: the
/// photographs do not show one flat work (a relief, a mirror in it), and
/// the photograph from the front is the one proposed of the two (Mateusz
/// 2026-11-17 22:43 UTC: "w sytuacji gdzie podejrzewasz płaskorzeźbę albo
/// dzieło które wymaga pojedynczego zdjęcia ustawiaj je jako domyślne").
struct OwnMerged: Codable, Hashable, Sendable {
    var token: String
    var width: Int
    var height: Int
    var used: Int = 0
    var replaced: Double = 0
    /// nil from a server before it gave the choice (1.145.229).
    var doubt: Bool? = nil
}

/// What was read off the picture (Sonnet), for the description's chips.
struct OwnHints: Codable, Hashable, Sendable {
    var signature: String = ""
    var artist: String = ""
    var date: String = ""
    var technique: String = ""
    var support: String = ""
    var title: String = ""
    var sure: Bool = false

    var isEmpty: Bool { signature.isEmpty && artist.isEmpty && date.isEmpty && title.isEmpty && technique.isEmpty }
}

/// What the owner wrote of the work.
struct OwnDescription: Encodable, Hashable, Sendable {
    var title: String = ""
    var artist: String = ""
    var dateText: String = ""
    /// What it is made with and on, a field each ("olej", "płótno";
    /// Mateusz 2026-11-19 20:38 UTC: "zrób dwa osobne pola i składaj z nich
    /// potem pole technika na karcie dzieła").
    var technique: String = ""
    var support: String = ""
    /// His note ("O dziele").
    var description: String = ""
    var hangs: String = ""
    var origin: String = ""
    var heightCm: Double? = nil
    var widthCm: Double? = nil

    /// The card's "Technika", written of the two ("olej na płótnie").
    var medium: String { OwnTechnique.line(technique: technique, support: support) }

    init(
        title: String = "", artist: String = "", dateText: String = "", technique: String = "",
        support: String = "", description: String = "", hangs: String = "", origin: String = "",
        heightCm: Double? = nil, widthCm: Double? = nil
    ) {
        self.title = title
        self.artist = artist
        self.dateText = dateText
        self.technique = technique
        self.support = support
        self.description = description
        self.hangs = hangs
        self.origin = origin
        self.heightCm = heightCm
        self.widthCm = widthCm
    }

    /// "Edytuj opis": as the card has it.
    init(_ item: Item) {
        let made = OwnTechnique.parts(of: item)
        self.init(
            title: item.title, artist: item.artist, dateText: item.dateText, technique: made.technique,
            support: made.support, description: item.description, hangs: item.own?.hangs ?? "",
            origin: item.own?.origin ?? "", heightCm: item.own?.heightCm, widthCm: item.own?.widthCm
        )
    }

    private enum CodingKeys: String, CodingKey {
        case title, artist, dateText, medium, technique, support, description, hangs, origin, heightCm, widthCm
    }

    /// With the line beside the two: the card shows the line, and a server
    /// that keeps the line alone (to 1.145.266) has the technique all the same.
    func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        try values.encode(title, forKey: .title)
        try values.encode(artist, forKey: .artist)
        try values.encode(dateText, forKey: .dateText)
        try values.encode(medium, forKey: .medium)
        try values.encode(technique, forKey: .technique)
        try values.encode(support, forKey: .support)
        try values.encode(description, forKey: .description)
        try values.encode(hangs, forKey: .hangs)
        try values.encode(origin, forKey: .origin)
        try values.encodeIfPresent(heightCm, forKey: .heightCm)
        try values.encodeIfPresent(widthCm, forKey: .widthCm)
    }
}

/// The photograph sent and the corners of the work on it; `by` "auto" when
/// they are the server's unchanged, "owner" when he moved them.
struct OwnPhotoCut: Codable, Hashable, Sendable {
    var token: String
    var corners: [[Double]]?
    var by: String = "auto"
    var shape: String = ""
    /// The white balance he set where no colour chart was beside the work
    /// (-1 cooler … 1 warmer; 0, as taken): the server keeps the work's
    /// photograph in it (Mateusz 2026-11-17 16:27 UTC).
    var balance: Double = 0
}

struct NewOwnWork: Encodable, Hashable, Sendable {
    var token: String
    var corners: [[Double]]?
    var by: String = "auto"
    var shape: String = ""
    var balance: Double = 0
    var text: OwnDescription
}

/// The technique and the support, a field of his words each; the server's
/// words for the hints in Polish, and the card's line written of the two
/// ("olej na płótnie").
enum OwnTechnique {
    static let techniques: [(key: String, name: String)] = [
        ("oil", "olej"), ("acrylic", "akryl"), ("watercolour", "akwarela"), ("gouache", "gwasz"),
        ("tempera", "tempera"), ("pastel", "pastel"), ("pencil", "ołówek"), ("charcoal", "węgiel"),
        ("ink", "tusz"), ("lithograph", "litografia"), ("etching", "akwaforta"), ("woodcut", "drzeworyt"),
        ("linocut", "linoryt"), ("screenprint", "serigrafia"), ("photograph", "fotografia"),
        ("mixed", "technika mieszana"),
    ]
    /// The supports the hints name: the menu by the field.
    static let supports: [(key: String, name: String)] = [
        ("canvas", "płótno"), ("paper", "papier"), ("board", "tektura"), ("panel", "deska"),
    ]
    /// The supports whose "na …" is known: the line is "olej na płótnie"
    /// of these, "olej, płyta HDF" of any other. None of the "na …" ends
    /// in another (`parts` reads them off a line's end).
    static let laid: [(name: String, on: String)] = [
        ("płótno", "na płótnie"), ("papier", "na papierze"), ("tektura", "na tekturze"), ("deska", "na desce"),
        ("karton", "na kartonie"), ("sklejka", "na sklejce"), ("płyta", "na płycie"),
        ("płyta pilśniowa", "na płycie pilśniowej"), ("papier czerpany", "na papierze czerpanym"),
        ("jedwab", "na jedwabiu"), ("szkło", "na szkle"), ("drewno", "na drewnie"), ("blacha", "na blasze"),
        ("pergamin", "na pergaminie"), ("len", "na lnie"), ("juta", "na jucie"), ("bawełna", "na bawełnie"),
        ("miedź", "na miedzi"),
    ]

    static func name(_ key: String) -> String? { techniques.first { $0.key == key }?.name }
    static func support(_ key: String) -> String? { supports.first { $0.key == key }?.name }

    /// The card's line of the two: "olej na płótnie" where the support's
    /// "na …" is known or he wrote it so himself, "olej, płyta HDF" (as
    /// museums list it) where not; one of the two alone as it is
    /// ("akwarela", "na papierze").
    static func line(technique: String, support: String) -> String {
        let made = technique.trimmingCharacters(in: .whitespacesAndNewlines)
        let under = support.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !under.isEmpty else { return made }
        let low = under.lowercased()
        let on = low.hasPrefix("na ") ? under : laid.first { $0.name == low }?.on
        guard !made.isEmpty else { return on ?? under }
        return on.map { "\(made) \($0)" } ?? "\(made), \(under)"
    }

    /// The two back from a line written when it was one field ("Edytuj
    /// opis" of a work described before): "olej na płótnie" is "olej" and
    /// "płótno". A line that ends in no support known stays whole as the
    /// technique ("olej i złoto na desce lipowej"): the line written of
    /// the two is then the line he wrote.
    static func parts(_ medium: String) -> (technique: String, support: String) {
        let text = medium.trimmingCharacters(in: .whitespacesAndNewlines)
        let low = text.lowercased()
        guard low.count == text.count else { return (text, "") }
        for known in laid where low == known.on || low.hasSuffix(" " + known.on) {
            return (String(text.dropLast(known.on.count)).trimmingCharacters(in: .whitespaces), known.name)
        }
        return (text, "")
    }

    /// The two of a work: as he wrote them where the server keeps them,
    /// read off its line where it does not (or kept none yet).
    static func parts(of item: Item) -> (technique: String, support: String) {
        let made = item.own?.technique ?? "", under = item.own?.support ?? ""
        return made.isEmpty && under.isEmpty ? parts(item.medium) : (made, under)
    }
}

/// The authors of his earlier works, offered while he writes one (Mateusz
/// 2026-11-19 20:38 UTC: "proponuj z już wcześniej dodanych Własnych dzieł
/// gdy zaczynam wpisywać (po 3 znakach)").
enum OwnAuthors {
    /// So many letters written before any is offered.
    static let from = 3
    /// So many offered at the most.
    static let most = 4

    /// Each author of his works once, as written the last time (the works
    /// come the last added first).
    static func known(_ works: [ItemSummary]) -> [String] {
        var seen = Set<String>()
        return works.map { $0.artist.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty && seen.insert(fold($0)).inserted }
    }

    /// Those a word of whose name begins with what is written ("ryb" finds
    /// "Mateusz Rybicki"), the letters' case and marks aside; none before
    /// three letters, nor the one written whole already.
    static func offered(for written: String, among authors: [String]) -> [String] {
        let typed = fold(written)
        guard typed.count >= from else { return [] }
        let found = authors.filter { name in
            let folded = fold(name)
            guard folded != typed else { return false }
            return folded.hasPrefix(typed) || folded.contains(" " + typed) || folded.contains("-" + typed)
        }
        return Array(found.prefix(most))
    }

    private static func fold(_ text: String) -> String {
        text.trimmingCharacters(in: .whitespaces)
            .folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil)
            .replacingOccurrences(of: "ł", with: "l")  // no mark to fold: a letter of its own
    }
}

extension Names {
    /// Over the title of a work of his own: "Moja kolekcja · Salon".
    static func ownCollection(_ hangs: String?) -> String {
        let place = (hangs ?? "").trimmingCharacters(in: .whitespaces)
        return place.isEmpty ? "Moja kolekcja" : "Moja kolekcja · \(place)"
    }
}
