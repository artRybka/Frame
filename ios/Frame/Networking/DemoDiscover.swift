import Foundation

/// A small part of the server's vocabulary and themes
/// (server/src/frame_server/library/vocabulary.py, themes.py), enough for
/// the demo library.
enum DemoDiscover {
    static let terms: [TermInfo] = [
        term("style:impressionism", "style", "Impresjonizm", ["impressionism", "impressionist"]),
        term("style:post-impressionism", "style", "Postimpresjonizm", ["post-impressionism", "pointillism"]),
        term("style:ukiyo-e", "style", "Ukiyo-e", ["ukiyo-e", "japanese", "edo period"]),
        term("style:art-nouveau", "style", "Secesja", ["art nouveau", "poster"]),
        term("subject:landscape", "subject", "Pejzaż", ["landscape"]),
        term("subject:sea", "subject", "Morze", ["seascape", "sea", "water", "sailing", "boat"]),
        term("subject:flowers", "subject", "Kwiaty", ["flower", "bouquet", "water lilies"]),
        term("subject:trees", "subject", "Drzewa i las", ["tree", "forest"]),
        term("subject:women", "subject", "Kobiety", ["woman", "women", "lady"]),
        term("subject:city", "subject", "Miasto i ulica", ["urban", "city", "street", "building"]),
        term("subject:mountains", "subject", "Góry", ["mountain", "fuji", "hills"]),
        term("subject:winter", "subject", "Zima i śnieg", ["snow", "winter"]),
        TermInfo(key: "period:17c", kind: "period", name: "XVII wiek", yearFrom: 1600, yearTo: 1699),
        TermInfo(key: "period:18c", kind: "period", name: "XVIII wiek", yearFrom: 1700, yearTo: 1799),
        TermInfo(key: "period:1800-1850", kind: "period", name: "1800–1850", yearFrom: 1800, yearTo: 1849),
        TermInfo(key: "period:1850-1900", kind: "period", name: "1850–1900", yearFrom: 1850, yearTo: 1899),
        TermInfo(key: "period:belle-epoque", kind: "period", name: "Belle Époque", yearFrom: 1880, yearTo: 1914),
        term("technique:painting", "technique", "Obrazy", ["painting", "oil on"]),
        term("technique:print", "technique", "Grafika", ["print", "woodblock", "lithograph"]),
        term("technique:poster", "technique", "Plakaty", ["poster"]),
        term("technique:manuscripts", "technique", "Rękopisy i miniatury", ["manuscript"]),
    ]

    static let themes: [ArtTheme] = [
        theme(
            "impressionism", "Impresjonizm i postimpresjonizm", "Monet, Cézanne, van Gogh, Seurat.",
            group: "Kierunki i style",
            rules: PlaylistRules(artists: ["Claude Monet", "Cezanne", "van Gogh", "Seurat"])
        ),
        theme(
            "dutch", "Malarstwo holenderskie", "Vermeer, Rembrandt, Hals, Steen, Ruisdael.",
            group: "Kierunki i style", rules: PlaylistRules(artists: ["Vermeer", "Bosschaert", "Rembrandt"])
        ),
        theme(
            "ukiyo-e", "Japońskie drzeworyty", "Hokusai, Hiroshige, Utamaro i inni mistrzowie ukiyo-e.",
            group: "Grafika i plakat", rules: PlaylistRules(artists: ["Hiroshige", "Hokusai", "Utamaro"])
        ),
        theme(
            "posters", "Plakaty i secesja", "Toulouse-Lautrec, Mucha i plakat przełomu wieków.",
            group: "Grafika i plakat", rules: PlaylistRules(artists: ["Toulouse-Lautrec", "Mucha"])
        ),
        theme(
            "sea", "Morze i statki", "Fale, porty i żagle.", group: "Tematy",
            rules: PlaylistRules(terms: ["subject:sea"])
        ),
        theme(
            "flowers", "Kwiaty", "Bukiety i kwitnące ogrody.", group: "Tematy",
            rules: PlaylistRules(terms: ["subject:flowers"])
        ),
        theme(
            "mountains", "Góry", "Alpy, Tatry i Fudżi.", group: "Tematy",
            rules: PlaylistRules(terms: ["subject:mountains"])
        ),
        theme(
            "blue", "W odcieniach błękitu", "Niebo, woda i indygo.", group: "Kolor i nastrój",
            rules: PlaylistRules(colors: ["blue"])
        ),
        theme(
            "belle-epoque", "Belle Époque", "Paryż i Europa w latach 1880–1914.", group: "Epoki",
            rules: PlaylistRules(terms: ["period:belle-epoque"])
        ),
    ]

    private static func term(_ key: String, _ kind: String, _ name: String, _ words: [String]) -> TermInfo {
        TermInfo(key: key, kind: kind, name: name, words: words)
    }

    private static func theme(
        _ key: String, _ name: String, _ description: String, group: String, rules: PlaylistRules
    ) -> ArtTheme {
        var rules = rules
        rules.kinds = [.artwork]
        return ArtTheme(key: key, name: name, description: description, group: group, rules: rules)
    }

    static func term(_ key: String) -> TermInfo? {
        if let found = terms.first(where: { $0.key == key }) { return found }
        guard key.hasPrefix("years:") else { return nil }
        let bounds = key.dropFirst("years:".count).split(separator: "-", omittingEmptySubsequences: false)
        guard bounds.count == 2 else { return nil }
        return TermInfo(
            key: key, kind: "period", name: PlaylistRules.yearsName(key) ?? key,
            yearFrom: Int(bounds[0]), yearTo: Int(bounds[1])
        )
    }

    static func isManuscript(_ item: Item) -> Bool {
        let text = [item.classification, item.title, item.medium].joined(separator: " ").lowercased()
        return ["manuscript", "folio", "book of hours", "leaf from", "page from"].contains { text.contains($0) }
    }

    /// Whether every kind of term in `keys` has one that fits `item`.
    static func matches(_ item: Item, terms keys: [String]) -> Bool {
        let text = ([item.title, item.classification, item.medium, item.culture] + item.styles + item.subjects)
            .joined(separator: " ").lowercased()
        let groups = Dictionary(grouping: keys.compactMap { term($0) }, by: \.kind)
        return groups.values.allSatisfy { terms in
            terms.contains { term in
                if term.key == "technique:manuscripts" { return isManuscript(item) }
                if term.yearFrom != nil || term.yearTo != nil {
                    guard let year = item.year else { return false }
                    return year >= (term.yearFrom ?? Int.min) && year <= (term.yearTo ?? Int.max)
                }
                return term.words.contains { text.contains($0) }
            }
        }
    }

    /// "Hokusai" fits "Katsushika Hokusai".
    static func artistMatches(_ artist: String, _ wanted: [String]) -> Bool {
        let have = words(artist)
        return !have.isEmpty && wanted.contains { name in
            let need = words(name)
            return !need.isEmpty && need.isSubset(of: have)
        }
    }

    static func words(_ text: String) -> Set<String> {
        let folded = text.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil)
        return Set(folded.split { !$0.isLetter && !$0.isNumber }.map(String.init))
    }

    static func fold(_ text: String) -> String {
        text.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil)
            .replacingOccurrences(of: "ł", with: "l")
    }
}
