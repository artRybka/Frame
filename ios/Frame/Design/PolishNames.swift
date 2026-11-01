import Foundation
import Observation

/// "Polskie imiona artystów" in Konfiguracja, a switch for fun: artists'
/// first names in their Polish forms wherever the app shows an artist
/// (Paul Cézanne as Paweł Cézanne, Vincent van Gogh as Wincenty van Gogh).
/// Only on screen: searches, playlists' rules and the server keep the
/// names as the museums give them. Off by default, kept on this phone.
@MainActor
@Observable
final class NameStyle {
    static let shared = NameStyle()
    static let key = "polishFirstNames"

    var polishFirstNames: Bool {
        didSet { UserDefaults.standard.set(polishFirstNames, forKey: Self.key) }
    }

    private init() {
        polishFirstNames = UserDefaults.standard.bool(forKey: Self.key)
    }
}

extension Names {
    /// An artist as the app shows them: with Polish first names when the
    /// switch is on. Reads the switch, so a view showing it follows it.
    @MainActor
    static func artist(_ name: String) -> String {
        NameStyle.shared.polishFirstNames ? PolishNames.artist(name) : name
    }

    /// A theme's name, which for the artist of the week and "Bo lubisz" is
    /// an artist's.
    @MainActor
    static func theme(_ theme: ArtTheme) -> String {
        theme.key.hasPrefix("week-artist-") || theme.key.hasPrefix("like-") ? artist(theme.name) : theme.name
    }
}

extension SearchToken {
    /// The chip's name on screen (an artist's with Polish first names).
    @MainActor
    var shownName: String { kind == "artist" ? Names.artist(name) : name }
}

/// First names in their Polish forms; surnames stay as they are.
enum PolishNames {
    /// "Paul Cézanne" → "Paweł Cézanne", "Gogh, Vincent van" → "Gogh,
    /// Wincenty van", "Workshop of Peter Paul Rubens" → "Workshop of Piotr
    /// Paweł Rubens", "Michelangelo" → "Michał Anioł". Every known first
    /// name before the surname is changed; the surname (the last word, or
    /// what follows "van", "de", "da"…) never is.
    static func artist(_ name: String) -> String {
        let trimmed = name.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return name }
        if let named = whole[fold(trimmed)] { return named }
        // "Surname, First names" from catalogues that sort by surname.
        if let comma = trimmed.range(of: ", ") {
            let head = String(trimmed[..<comma.lowerBound])
            let tail = String(trimmed[comma.upperBound...])
            let headFirst = head.split(separator: " ").first.map(String.init) ?? ""
            let tailFirst = tail.split(separator: " ").first.map(String.init) ?? ""
            if polish(tailFirst) != nil && polish(headFirst) == nil {
                return head + ", " + given(tail, keepingLast: false)
            }
            return given(head, keepingLast: true) + ", " + tail
        }
        return given(trimmed, keepingLast: true)
    }

    /// Changes the known first names in `words`, up to a surname particle;
    /// the last word too unless `keepingLast` (it is the surname then).
    private static func given(_ words: String, keepingLast: Bool) -> String {
        var tokens = words.split(separator: " ", omittingEmptySubsequences: false).map(String.init)
        guard !tokens.isEmpty else { return words }
        if tokens.count == 1 && keepingLast {
            return whole[fold(tokens[0])] ?? words
        }
        let end = keepingLast ? tokens.count - 1 : tokens.count
        for index in 0 ..< end {
            let token = tokens[index]
            let folded = fold(token)
            if stops.contains(folded) || token.contains(where: { $0.isNumber || $0 == "(" }) { break }
            if let changed = polish(token) { tokens[index] = changed }
        }
        return tokens.joined(separator: " ")
    }

    /// The Polish form of one first name: "Pierre-Auguste" → "Piotr August",
    /// nil when it is not a first name known here.
    static func polish(_ token: String) -> String? {
        // Keeps a full stop or comma after the name ("Jan, ").
        var core = token
        var trail = ""
        while let last = core.last, last == "." || last == "," || last == ";" {
            trail = String(last) + trail
            core.removeLast()
        }
        guard !core.isEmpty else { return nil }
        if let found = first[fold(core)] { return found + trail }
        let parts = core.split(separator: "-").map(String.init)
        guard parts.count > 1 else { return nil }
        let changed = parts.map { first[fold($0)] }
        guard changed.contains(where: { $0 != nil }) else { return nil }
        if changed.allSatisfy({ $0 != nil }) {
            return changed.compactMap { $0 }.joined(separator: " ") + trail
        }
        return zip(parts, changed).map { $1 ?? $0 }.joined(separator: "-") + trail
    }

    static func fold(_ text: String) -> String {
        text.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil)
            .replacingOccurrences(of: "ł", with: "l")
            .lowercased()
    }

    /// Words that start a surname or end the names ("van Gogh", "da Vinci",
    /// "Bruegel the Elder", "Monet and Renoir").
    private static let stops: Set<String> = [
        "van", "von", "de", "da", "di", "del", "della", "delle", "dei", "degli", "der", "den",
        "ten", "ter", "te", "le", "la", "les", "du", "des", "d'", "y", "dos", "das", "do", "zu",
        "af", "el", "il", "lo", "the", "and", "&", "i", "et", "und", "e",
    ]

    /// Whole names that change as one: one-word names and the few whose
    /// first name is a woman's here although a man's elsewhere.
    private static let whole: [String: String] = [
        "michelangelo": "Michał Anioł",
        "titian": "Tycjan",
        "tiziano": "Tycjan",
        "raphael": "Rafał",
        "raffaello": "Rafał",
        "leonardo": "Leonard",
        "camille claudel": "Kamila Claudel",
        "claude cahun": "Klaudia Cahun",
    ]

    /// First names (folded: lower case, no accents) and their Polish forms.
    static let first: [String: String] = {
        let groups: [(String, [String])] = [
            // Men
            ("Adam", ["adam", "adamo", "adán"]),
            ("Adolf", ["adolph", "adolphe", "adolfo"]),
            ("Albert", ["albert", "alberto", "albertus", "aelbert"]),
            ("Aleksander", ["alexandre", "alexander", "alessandro", "alejandro", "sandro", "aleksandr", "alexandr", "alexandros"]),
            ("Aleksy", ["alexis", "alexei", "aleksei", "alexey", "alessio"]),
            ("Alfons", ["alphonse", "alfonso", "alphons", "alfons"]),
            ("Alojzy", ["alois", "aloys", "aloysius"]),
            ("Amadeusz", ["amedeo", "amadeus", "amédée"]),
            ("Ambroży", ["ambrosius", "ambroise", "ambrogio", "ambrose"]),
            ("Andrzej", ["andré", "andrew", "andrea", "andreas", "andrés", "andrei", "andrey", "anders", "andries", "andreu"]),
            ("Antoni", ["antoine", "anton", "antonio", "anthony", "antonín", "antonis", "antoon", "anthonie", "antonius"]),
            ("Anzelm", ["anselm", "anselme", "anselmo"]),
            ("Artur", ["arthur", "arturo"]),
            ("August", ["auguste", "august", "augusto", "augustus"]),
            ("Augustyn", ["augustin", "agostino", "agustín", "augustine"]),
            ("Bartłomiej", ["bartholomew", "bartolomé", "bartolomeo", "barthélemy", "bartholomeus", "bartholomäus"]),
            ("Bazyli", ["wassily", "vasily", "wassili", "vassily", "vasili", "basil", "basile"]),
            ("Benedykt", ["benedict", "benedetto", "benoît", "benedikt"]),
            ("Beniamin", ["benjamin", "beniamino"]),
            ("Bernard", ["bernardo", "bernhard", "bernardino"]),
            ("Daniel", ["daniele"]),
            ("Dawid", ["david", "davide"]),
            ("Dominik", ["dominique", "domenico", "doménikos", "domingo", "dominicus"]),
            ("Dydak", ["diego"]),
            ("Dymitr", ["dmitri", "dmitry", "dimitri", "dimitrios"]),
            ("Edward", ["édouard", "edward", "eduard", "edvard", "eduardo", "edoardo"]),
            ("Eliasz", ["elias", "élie", "ilya", "ilia", "elia"]),
            ("Emil", ["émile", "emil", "emilio"]),
            ("Ernest", ["ernst", "ernest", "ernesto"]),
            ("Eugeniusz", ["eugène", "eugen", "eugenio", "eugene"]),
            ("Feliks", ["félix", "felix", "felice"]),
            ("Ferdynand", ["ferdinand", "fernando", "ferdinando"]),
            ("Filip", ["philip", "philippe", "filippo", "felipe", "philipp", "philips", "filips"]),
            ("Franciszek", ["françois", "francis", "franz", "francesco", "francisco", "frans", "františek", "francesc", "franciscus", "ferenc"]),
            ("Fryderyk", ["frédéric", "frederic", "frederick", "friedrich", "federico", "frederik", "fritz"]),
            ("Gabriel", ["gabriele", "gabriël"]),
            ("Gerard", ["gérard", "gerrit", "gerardo", "gerhard", "gerard"]),
            ("Gotfryd", ["gottfried", "godfrey", "godefroy"]),
            ("Grzegorz", ["gregor", "grégoire", "gregorio", "gregory"]),
            ("Gustaw", ["gustave", "gustav", "gustaf", "gustavo"]),
            ("Gwidon", ["guido", "guy"]),
            ("Henryk", ["henri", "henry", "heinrich", "enrico", "enrique", "hendrik", "henrik", "hendrick", "harry"]),
            ("Herman", ["hermann", "herman", "harmen"]),
            ("Hieronim", ["hieronymus", "jerome", "jérôme", "girolamo", "jerónimo", "jeroen"]),
            ("Hugo", ["hugues", "hugh", "ugo"]),
            ("Ignacy", ["ignace", "ignazio", "ignacio", "ignatius", "ignaz"]),
            ("Izaak", ["isaac", "isaak", "isack"]),
            ("Jakub", ["jacques", "jacob", "jacopo", "jakob", "james", "giacomo", "jaime", "jaume", "jacobus", "santiago", "jakub"]),
            ("Jan", ["jean", "johannes", "johann", "john", "giovanni", "juan", "hans", "joão", "ivan", "jens", "johan", "joan", "giovan", "jan"]),
            ("Chrzciciel", ["baptiste", "battista", "bautista", "baptist"]),
            ("Józef", ["joseph", "josef", "giuseppe", "josé", "jozef", "józsef", "josep"]),
            ("Juliusz", ["julius", "jules", "giulio", "julio", "julien"]),
            ("Karol", ["charles", "karl", "carl", "carlo", "carlos", "karel", "károly", "carel"]),
            ("Kasper", ["caspar", "kaspar", "gaspard", "gaspare", "gaspar", "jasper"]),
            ("Kazimierz", ["kazimir", "kasimir", "casimir", "kazimír"]),
            ("Klaudiusz", ["claude", "claudio", "claudius"]),
            ("Konrad", ["conrad", "konrad", "corrado"]),
            ("Konstanty", ["konstantin", "constantin", "constant", "costantino", "constantine"]),
            ("Korneliusz", ["cornelis", "cornelius", "corneille"]),
            ("Krystian", ["christian", "christiaan", "cristiano"]),
            ("Krzysztof", ["christoph", "christopher", "cristoforo", "christophe", "cristóbal", "christoffel", "kristof"]),
            ("Kamil", ["camille", "camillo", "camilo"]),
            ("Kwintyn", ["quentin", "quinten", "quintin"]),
            ("Leon", ["léon", "leon", "leone", "leo", "léo"]),
            ("Leonard", ["léonard", "leonard", "leonhard"]),
            ("Ludwik", ["louis", "ludwig", "luigi", "luis", "lodewijk", "lewis", "ludovico", "lluís", "ludovicus"]),
            ("Łukasz", ["lucas", "luca", "lukas", "luke", "luc"]),
            ("Maciej", ["matthias", "mathias", "mattias"]),
            ("Maksymilian", ["maximilian", "maximilien", "massimiliano", "maximiliano"]),
            ("Marceli", ["marcel", "marcello", "marcelo"]),
            ("Marcin", ["martin", "martino", "martín", "maarten", "marten"]),
            ("Marek", ["marc", "mark", "marco", "marcus", "marcos", "markus"]),
            ("Mateusz", ["matthew", "matteo", "mathieu", "matthäus", "mattia", "matthijs", "mateo", "matheus"]),
            ("Maurycy", ["maurice", "moritz", "maurizio", "mauricio"]),
            ("Melchior", ["melchior", "melchiorre"]),
            ("Michał", ["michel", "michael", "michele", "miguel", "michiel", "mikhail", "mihály", "michal"]),
            ("Mikołaj", ["nicolas", "nicholas", "niccolò", "nicola", "nikolaus", "nicolaes", "nikolai", "nicolaas", "niklaus", "nicolau", "nicolò", "nicolaus", "claes"]),
            ("Odylon", ["odilon"]),
            ("Olbracht", ["albrecht"]),
            ("Oskar", ["oscar", "oskar"]),
            ("Paweł", ["paul", "paolo", "pablo", "pavel", "paulus", "pål", "pau", "paulo"]),
            ("Piotr", ["pierre", "pieter", "peter", "pietro", "pedro", "piet", "petrus", "petr", "piero", "pyotr", "pere"]),
            ("Rafał", ["raphael", "raphaël", "raffaello", "rafael", "raffaele"]),
            ("Roch", ["rocco", "roque"]),
            ("Rudolf", ["rodolphe", "rodolfo", "rudolph"]),
            ("Ryszard", ["richard", "riccardo", "ricardo"]),
            ("Salwator", ["salvator", "salvatore", "salvador"]),
            ("Sebastian", ["sebastiano", "sébastien", "sebastián", "sebastiaan"]),
            ("Szczepan", ["stephen", "steven", "stefano", "étienne", "esteban", "stephan", "istván", "stefan"]),
            ("Szymon", ["simon", "simone", "siméon", "simeon"]),
            ("Teodor", ["théodore", "theodor", "teodoro", "theodore", "fyodor", "fedor", "theo", "théo"]),
            ("Teodoryk", ["dirk", "dieric", "dierick", "dietrich", "thierry"]),
            ("Tobiasz", ["tobias", "tobia"]),
            ("Tomasz", ["thomas", "tommaso", "tomás", "tomas", "tom"]),
            ("Tycjan", ["titian", "tiziano"]),
            ("Ulryk", ["ulrich", "ulrico"]),
            ("Wacław", ["wenceslaus", "václav", "wenzel", "wenceslas"]),
            ("Walenty", ["valentin", "valentine", "valentino"]),
            ("Wawrzyniec", ["lawrence", "laurent", "lorenzo", "lorenz", "laurens", "laurence"]),
            ("Wiktor", ["victor", "vittorio", "víctor", "viktor"]),
            ("Wilhelm", ["william", "wilhelm", "guillaume", "guglielmo", "willem", "guillermo", "vilhelm"]),
            ("Wincenty", ["vincent", "vincenzo", "vicente", "vincenc"]),
            ("Michał Anioł", ["michelangelo"]),
            // Women
            ("Agnieszka", ["agnes", "agnès", "agnese"]),
            ("Angelika", ["angelica", "angelika", "angélique"]),
            ("Anna", ["anne", "ann", "anna", "annie"]),
            ("Artemizja", ["artemisia"]),
            ("Berta", ["berthe", "bertha"]),
            ("Ewa", ["eva", "eve", "ève"]),
            ("Elżbieta", ["élisabeth", "elizabeth", "elisabetta", "elisabeth"]),
            ("Izabela", ["isabel", "isabelle", "isabella", "isabeau"]),
            ("Helena", ["helen", "hélène", "helene", "elena"]),
            ("Joanna", ["jeanne", "johanna", "giovanna", "juana"]),
            ("Judyta", ["judith", "giuditta"]),
            ("Julia", ["julie", "giulia"]),
            ("Katarzyna", ["catherine", "caterina", "katharina", "catharina", "katherine", "kate"]),
            ("Klara", ["clara", "claire", "chiara"]),
            ("Ludwika", ["louise", "luisa", "louisa"]),
            ("Małgorzata", ["margaret", "marguerite", "margarethe", "margherita", "margarita", "margaretha"]),
            ("Maria", ["mary", "marie", "maría", "maria"]),
            ("Rachela", ["rachel", "rachele"]),
            ("Róża", ["rosa", "rose"]),
            ("Zofia", ["sophie", "sofia", "sophia", "sofía"]),
            ("Zuzanna", ["suzanne", "susanna", "susan", "susanne"]),
        ]
        var map: [String: String] = [:]
        for (polish, names) in groups {
            for name in names { map[PolishNames.fold(name)] = polish }
        }
        return map
    }()
}
