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

    var aspect: Double { height > 0 ? Double(width) / Double(height) : 0.75 }
}

/// The first photograph with the glare taken out by the side ones (the
/// scan of three, Mateusz 2026-11-16): how many could be laid over it and
/// how much of it they gave (0–1; 0, nothing changed).
struct OwnMerged: Codable, Hashable, Sendable {
    var token: String
    var width: Int
    var height: Int
    var used: Int = 0
    var replaced: Double = 0
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
struct OwnDescription: Codable, Hashable, Sendable {
    var title: String = ""
    var artist: String = ""
    var dateText: String = ""
    /// Technique and support as one line ("olej na płótnie").
    var medium: String = ""
    /// His note ("O dziele").
    var description: String = ""
    var hangs: String = ""
    var origin: String = ""
    var heightCm: Double? = nil
    var widthCm: Double? = nil

    init(
        title: String = "", artist: String = "", dateText: String = "", medium: String = "",
        description: String = "", hangs: String = "", origin: String = "",
        heightCm: Double? = nil, widthCm: Double? = nil
    ) {
        self.title = title
        self.artist = artist
        self.dateText = dateText
        self.medium = medium
        self.description = description
        self.hangs = hangs
        self.origin = origin
        self.heightCm = heightCm
        self.widthCm = widthCm
    }

    /// "Edytuj opis": as the card has it.
    init(_ item: Item) {
        self.init(
            title: item.title, artist: item.artist, dateText: item.dateText, medium: item.medium,
            description: item.description, hangs: item.own?.hangs ?? "", origin: item.own?.origin ?? "",
            heightCm: item.own?.heightCm, widthCm: item.own?.widthCm
        )
    }
}

/// The photograph sent and the corners of the work on it; `by` "auto" when
/// they are the server's unchanged, "owner" when he moved them.
struct OwnPhotoCut: Codable, Hashable, Sendable {
    var token: String
    var corners: [[Double]]?
    var by: String = "auto"
    var shape: String = ""
}

struct NewOwnWork: Codable, Hashable, Sendable {
    var token: String
    var corners: [[Double]]?
    var by: String = "auto"
    var shape: String = ""
    var text: OwnDescription
}

/// The technique and the support as chips, the server's words for the
/// hints in Polish; "olej na płótnie" written from the two.
enum OwnTechnique {
    static let techniques: [(key: String, name: String)] = [
        ("oil", "olej"), ("acrylic", "akryl"), ("watercolour", "akwarela"), ("gouache", "gwasz"),
        ("tempera", "tempera"), ("pastel", "pastel"), ("pencil", "ołówek"), ("charcoal", "węgiel"),
        ("ink", "tusz"), ("lithograph", "litografia"), ("etching", "akwaforta"), ("woodcut", "drzeworyt"),
        ("linocut", "linoryt"), ("screenprint", "serigrafia"), ("photograph", "fotografia"),
        ("mixed", "technika mieszana"),
    ]
    static let supports: [(key: String, name: String, on: String)] = [
        ("canvas", "płótno", "na płótnie"), ("paper", "papier", "na papierze"),
        ("board", "tektura", "na tekturze"), ("panel", "deska", "na desce"),
    ]

    static func name(_ key: String) -> String? { techniques.first { $0.key == key }?.name }
    static func support(_ key: String) -> String? { supports.first { $0.key == key }?.name }

    /// "olej na płótnie", "akwarela", "na papierze".
    static func medium(technique: String?, support: String?) -> String {
        let made = technique.flatMap(name) ?? ""
        let on = support.flatMap { key in supports.first { $0.key == key }?.on } ?? ""
        return [made, on].filter { !$0.isEmpty }.joined(separator: " ")
    }

    /// The chips back from a line written before ("Edytuj opis").
    static func read(_ medium: String) -> (technique: String?, support: String?)? {
        let text = medium.lowercased().trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return (nil, nil) }
        let technique = techniques.first { text.hasPrefix($0.name) }
        let rest = technique.map { String(text.dropFirst($0.name.count)).trimmingCharacters(in: .whitespaces) } ?? text
        let support = supports.first { rest == $0.on }
        guard rest.isEmpty || support != nil else { return nil }  // his own words: kept as typed
        return (technique?.key, support?.key)
    }
}

extension Names {
    /// Over the title of a work of his own: "Moja kolekcja · Salon".
    static func ownCollection(_ hangs: String?) -> String {
        let place = (hangs ?? "").trimmingCharacters(in: .whitespaces)
        return place.isEmpty ? "Moja kolekcja" : "Moja kolekcja · \(place)"
    }
}
