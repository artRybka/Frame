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
        TermInfo(key: "period:ancient", kind: "period", name: "Starożytność", yearTo: 499),
        TermInfo(key: "period:medieval", kind: "period", name: "Średniowiecze", yearFrom: 500, yearTo: 1399),
        TermInfo(key: "period:15c", kind: "period", name: "XV wiek", yearFrom: 1400, yearTo: 1499),
        TermInfo(key: "period:16c", kind: "period", name: "XVI wiek", yearFrom: 1500, yearTo: 1599),
        TermInfo(key: "period:17c", kind: "period", name: "XVII wiek", yearFrom: 1600, yearTo: 1699),
        TermInfo(key: "period:18c", kind: "period", name: "XVIII wiek", yearFrom: 1700, yearTo: 1799),
        TermInfo(key: "period:1800-1850", kind: "period", name: "1800–1850", yearFrom: 1800, yearTo: 1849),
        TermInfo(key: "period:1850-1900", kind: "period", name: "1850–1900", yearFrom: 1850, yearTo: 1899),
        TermInfo(key: "period:1900-1930", kind: "period", name: "1900–1930", yearFrom: 1900, yearTo: 1930),
        TermInfo(key: "period:1930-1945", kind: "period", name: "1930–1945", yearFrom: 1930, yearTo: 1944),
        TermInfo(key: "period:post-1945", kind: "period", name: "1945–1955", yearFrom: 1945, yearTo: 1955),
        TermInfo(key: "period:egypt", kind: "period", name: "Starożytny Egipt", yearFrom: -3100, yearTo: -30, region: "antiquity"),
        TermInfo(key: "period:greece", kind: "period", name: "Starożytna Grecja", yearFrom: -800, yearTo: -31, region: "antiquity"),
        TermInfo(key: "period:rome", kind: "period", name: "Starożytny Rzym", yearFrom: -509, yearTo: 476, region: "antiquity"),
        TermInfo(key: "period:byzantium", kind: "period", name: "Bizancjum", yearFrom: 330, yearTo: 1453, region: "antiquity"),
        TermInfo(key: "period:thirty-years-war", kind: "period", name: "Wojna trzydziestoletnia", yearFrom: 1618, yearTo: 1648, region: "europe"),
        TermInfo(key: "period:enlightenment", kind: "period", name: "Oświecenie", yearFrom: 1715, yearTo: 1789, region: "europe"),
        TermInfo(key: "period:napoleonic", kind: "period", name: "Epoka napoleońska", yearFrom: 1799, yearTo: 1815, region: "europe"),
        TermInfo(key: "period:biedermeier", kind: "period", name: "Biedermeier", yearFrom: 1815, yearTo: 1848, region: "europe"),
        TermInfo(key: "period:victorian", kind: "period", name: "Epoka wiktoriańska", yearFrom: 1837, yearTo: 1901, region: "europe"),
        TermInfo(key: "period:belle-epoque", kind: "period", name: "Belle Époque", yearFrom: 1880, yearTo: 1914, region: "europe"),
        TermInfo(key: "period:great-war", kind: "period", name: "Wielka Wojna", yearFrom: 1914, yearTo: 1918, region: "europe"),
        TermInfo(key: "period:interwar", kind: "period", name: "Międzywojnie", yearFrom: 1918, yearTo: 1939, region: "europe"),
        TermInfo(key: "period:twenties", kind: "period", name: "Lata dwudzieste", yearFrom: 1920, yearTo: 1929, region: "europe"),
        TermInfo(key: "period:ww2", kind: "period", name: "II wojna światowa", yearFrom: 1939, yearTo: 1945, region: "europe"),
        TermInfo(key: "period:pl-golden-age", kind: "period", name: "Złoty wiek", yearFrom: 1506, yearTo: 1572, region: "poland"),
        TermInfo(key: "period:pl-saxon", kind: "period", name: "Czasy saskie", yearFrom: 1697, yearTo: 1763, region: "poland"),
        TermInfo(key: "period:pl-stanislaus", kind: "period", name: "Czasy stanisławowskie", yearFrom: 1764, yearTo: 1795, region: "poland"),
        TermInfo(key: "period:pl-partitions", kind: "period", name: "Zabory", yearFrom: 1795, yearTo: 1918, region: "poland"),
        TermInfo(key: "period:pl-second-republic", kind: "period", name: "II Rzeczpospolita", yearFrom: 1918, yearTo: 1939, region: "poland"),
        TermInfo(key: "period:edo", kind: "period", name: "Edo", yearFrom: 1603, yearTo: 1868, region: "east-asia"),
        TermInfo(key: "period:meiji", kind: "period", name: "Meiji", yearFrom: 1868, yearTo: 1912, region: "east-asia"),
        TermInfo(key: "period:taisho", kind: "period", name: "Taishō", yearFrom: 1912, yearTo: 1926, region: "east-asia"),
        TermInfo(key: "period:ming", kind: "period", name: "Ming", yearFrom: 1368, yearTo: 1644, region: "east-asia"),
        TermInfo(key: "period:qing", kind: "period", name: "Qing", yearFrom: 1644, yearTo: 1912, region: "east-asia"),
        term("technique:painting", "technique", "Malarstwo", ["painting", "oil on"]),
        term("technique:print", "technique", "Grafika", ["print", "woodblock", "lithograph"]),
        term("technique:drawing", "technique", "Rysunki i akwarele", ["drawing", "watercolo", "chalk", "graphite"]),
        term("technique:poster", "technique", "Plakaty", ["poster"]),
        term("technique:manuscripts", "technique", "Rękopisy i miniatury", ["manuscript"]),
        term("technique:photography", "technique", "Fotografia", ["photograph"]),
        term("technique:sculpture", "technique", "Rzeźba", ["sculpture", "statue"]),
        term("technique:decorative", "technique", "Ceramika i rzemiosło", ["ceramic", "porcelain", "textile"]),
    ]

    static let themes: [ArtTheme] = [
        theme(
            "week-artist-utagawa-hiroshige", "Utagawa Hiroshige", "Artysta tygodnia. 9 dzieł na ten tydzień.",
            group: "Dziś dla Ciebie", rules: PlaylistRules(artists: ["Utagawa Hiroshige"])
        ),
        theme(
            "like-claude-monet", "Claude Monet", "Cezanne, van Gogh i Seurat", group: "Bo lubisz",
            rules: PlaylistRules(artists: ["Cezanne", "van Gogh", "Seurat"])
        ),
        theme(
            "like-katsushika-hokusai", "Katsushika Hokusai", "Hiroshige i Utamaro", group: "Bo lubisz",
            rules: PlaylistRules(artists: ["Hiroshige", "Utamaro"])
        ),
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
            "other-photography", "Fotografia", "Od pierwszych odbitek Talbota po kolorowe slajdy lat 40.",
            group: "Sztuki inne", rules: PlaylistRules(terms: ["technique:photography"])
        ),
        theme(
            "other-sculpture", "Rzeźba", "Marmur, brąz i drewno z pięciu tysięcy lat.",
            group: "Sztuki inne", rules: PlaylistRules(terms: ["technique:sculpture"])
        ),
        theme(
            "blue-white", "Błękit i biel", "Kobalt na porcelanie: Jingdezhen, Iznik i Delft.",
            group: "Sztuki inne", rules: PlaylistRules(terms: ["technique:decorative"])
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
            "ancient-egypt", "Starożytny Egipt", "Grobowce w Tebach, ok. 1400 p.n.e.", group: "Epoki",
            rules: PlaylistRules(terms: ["period:egypt", "technique:painting"]),
            section: ("Starożytność i Bizancjum", "3100 p.n.e.–1453")
        ),
        theme(
            "fayum", "Portrety fajumskie", "Enkaustyka na desce, 50–250 n.e.", group: "Epoki",
            rules: PlaylistRules(terms: ["period:ancient", "technique:painting"]),
            section: ("Starożytność i Bizancjum", "3100 p.n.e.–1453")
        ),
        theme(
            "belle-epoque", "Belle Époque", "Paryż i Europa w latach 1880–1914.", group: "Epoki",
            rules: PlaylistRules(terms: ["period:belle-epoque"]),
            section: ("Średniowiecze i dalej", "od 1250")
        ),
    ]

    private static func term(_ key: String, _ kind: String, _ name: String, _ words: [String]) -> TermInfo {
        TermInfo(key: key, kind: kind, name: name, words: words)
    }

    private static func theme(
        _ key: String, _ name: String, _ description: String, group: String, rules: PlaylistRules,
        section: (name: String, years: String)? = nil
    ) -> ArtTheme {
        var rules = rules
        rules.kinds = [.artwork]
        return ArtTheme(
            key: key, name: name, description: description, group: group, rules: rules,
            section: section?.name, sectionYears: section?.years
        )
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
