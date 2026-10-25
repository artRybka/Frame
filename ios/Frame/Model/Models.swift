import CoreGraphics
import Foundation

// Mirrors the server models (server/src/frame_server/library/models.py,
// player.py, schedule.py, status.py). JSON keys are snake_case on the wire.

struct ColorSwatch: Codable, Hashable, Sendable {
    let hex: String
    let weight: Double
}

enum ItemKind: String, Codable, Hashable, Sendable, CaseIterable {
    case artwork, own, photo
}

struct PhotoInfo: Codable, Hashable, Sendable {
    var takenAt: String?
    var latitude: Double?
    var longitude: Double?
    var contributor: String?
    var caption: String?
}

struct Item: Codable, Identifiable, Hashable, Sendable {
    let id: String
    var kind: ItemKind
    var source: String
    var sourceId: String
    var title: String
    var artist: String
    var artistBio: String
    var dateText: String
    var year: Int?
    var medium: String
    var classification: String
    var styles: [String]
    var subjects: [String]
    var culture: String
    var museum: String
    var credit: String
    var license: String
    var url: String
    var description: String
    var imageUrl: String
    var thumbUrl: String
    var width: Int?
    var height: Int?
    var colors: [ColorSwatch]
    var colorTags: [String]
    var suitability: Double?
    var favorite: Bool
    var excluded: Bool
    var addedAt: String
    var lastShownAt: String?
    var showCount: Int
    var photo: PhotoInfo?

    var summary: ItemSummary {
        ItemSummary(
            id: id, kind: kind, source: source, title: title, artist: artist, dateText: dateText,
            year: year, colors: colors, width: width, height: height, favorite: favorite,
            suitability: suitability
        )
    }
}

struct ItemSummary: Codable, Identifiable, Hashable, Sendable {
    let id: String
    var kind: ItemKind
    var source: String
    var title: String
    var artist: String
    var dateText: String
    var year: Int?
    var colors: [ColorSwatch]
    var width: Int?
    var height: Int?
    var favorite: Bool
    var suitability: Double?

    /// Width / height, defaulting to landscape when unknown.
    var aspectRatio: Double {
        guard let width, let height, width > 0, height > 0 else { return 4.0 / 3.0 }
        return Double(width) / Double(height)
    }
}

struct ItemPage: Codable, Sendable {
    let total: Int
    let items: [ItemSummary]
}

struct FacetValue: Codable, Hashable, Sendable, Identifiable {
    let value: String
    let count: Int
    var id: String { value }
}

struct Facets: Codable, Sendable {
    var artists: [FacetValue]
    var styles: [FacetValue]
    var subjects: [FacetValue]
    var colors: [FacetValue]
    var sources: [FacetValue]
    var kinds: [FacetValue]

    static let empty = Facets(artists: [], styles: [], subjects: [], colors: [], sources: [], kinds: [])
}

struct PlaylistRules: Codable, Hashable, Sendable {
    var query: String = ""
    var artists: [String] = []
    var styles: [String] = []
    var subjects: [String] = []
    /// Styles, subjects, periods and techniques of the server's vocabulary,
    /// e.g. "subject:sea", "years:1880-1914".
    var terms: [String] = []
    var colors: [String] = []
    var kinds: [ItemKind] = []
    var sources: [String] = []
    var yearFrom: Int?
    var yearTo: Int?
    var favoritesOnly: Bool = false
    var minSuitability: Double?
    /// Works taken out of a smart playlist although they match its rules.
    var excludeIds: [String] = []

    /// Whether there are no rules; exceptions (`excludeIds`) don't count.
    var isEmpty: Bool {
        query.isEmpty && artists.isEmpty && styles.isEmpty && subjects.isEmpty && terms.isEmpty
            && colors.isEmpty
            && kinds.isEmpty && sources.isEmpty && yearFrom == nil && yearTo == nil
            && !favoritesOnly && minSuitability == nil
    }
}

extension PlaylistRules {
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        query = try c.decode(String.self, forKey: .query)
        artists = try c.decode([String].self, forKey: .artists)
        styles = try c.decode([String].self, forKey: .styles)
        subjects = try c.decode([String].self, forKey: .subjects)
        terms = try c.decodeIfPresent([String].self, forKey: .terms) ?? []  // older servers
        colors = try c.decode([String].self, forKey: .colors)
        kinds = try c.decode([ItemKind].self, forKey: .kinds)
        sources = try c.decode([String].self, forKey: .sources)
        yearFrom = try c.decodeIfPresent(Int.self, forKey: .yearFrom)
        yearTo = try c.decodeIfPresent(Int.self, forKey: .yearTo)
        favoritesOnly = try c.decode(Bool.self, forKey: .favoritesOnly)
        minSuitability = try c.decodeIfPresent(Double.self, forKey: .minSuitability)
        excludeIds = try c.decodeIfPresent([String].self, forKey: .excludeIds) ?? []  // older servers
    }
}

enum PlaylistKind: String, Codable, Hashable, Sendable {
    case smart, manual
    case album  // mirrors a shared iCloud album
}

/// In which order an album playlist shows its photos.
enum AlbumOrder: String, Codable, Hashable, Sendable, CaseIterable, Identifiable {
    case random, newest, oldest, added

    var id: Self { self }

    var title: String {
        switch self {
        case .random: "Losowo"
        case .newest: "Najnowsze"
        case .oldest: "Najstarsze"
        case .added: "Ostatnio dodane"
        }
    }

    var explanation: String {
        switch self {
        case .random: "Zdjęcia w losowej kolejności, bez powtórek, dopóki nie pokażą się wszystkie."
        case .newest: "Od zrobionych najpóźniej do najstarszych. Nowe zdjęcia w albumie idą na początek."
        case .oldest: "Od najstarszych zdjęć do najnowszych, jak w kronice."
        case .added: "Najpierw te, które ktoś niedawno dodał do albumu."
        }
    }
}

/// The shared iCloud album an album playlist mirrors.
struct AlbumSource: Codable, Hashable, Sendable {
    var url: String
    var order: AlbumOrder = .random
}

/// `POST /api/albums/check`
struct AlbumCheck: Codable, Hashable, Sendable {
    let name: String
    let count: Int
}

/// Body for creating or updating a playlist.
struct Playlist: Codable, Hashable, Sendable {
    var id: Int?
    var name: String
    var description: String = ""
    var kind: PlaylistKind = .smart
    var rules = PlaylistRules()
    var itemIds: [String] = []
    var album: AlbumSource?
    /// The Discover theme the playlist was made from.
    var theme: String?
}

struct PlaylistSummary: Codable, Identifiable, Hashable, Sendable {
    let id: Int
    var name: String
    var description: String
    var kind: PlaylistKind
    var rules: PlaylistRules
    var itemCount: Int
    var coverItemIds: [String]
    var album: AlbumSource?
    var albumSync: AlbumSync?
    var theme: String?
}

struct PlaylistDetail: Codable, Sendable {
    let playlist: PlaylistSummary
    let itemIds: [String]
    let items: [ItemSummary]
}

struct RulesPreview: Codable, Sendable {
    let count: Int
    let items: [ItemSummary]
}

struct Hold: Codable, Hashable, Sendable {
    var until: String?
    var forever: Bool
}

/// How long a picture stays on the frame after "show now".
enum HoldSpec: Hashable, Sendable, CaseIterable, Identifiable {
    case untilNextChange, oneHour, threeHours, oneDay, forever

    var id: Self { self }

    var label: String {
        switch self {
        case .untilNextChange: "Do następnej zmiany"
        case .oneHour: "Na godzinę"
        case .threeHours: "Na 3 godziny"
        case .oneDay: "Na dobę"
        case .forever: "Na stałe"
        }
    }

    /// Value of the server's `hold` parameter.
    var wireValue: String {
        switch self {
        case .untilNextChange: "next"
        case .oneHour: "60"
        case .threeHours: "180"
        case .oneDay: "1440"
        case .forever: "forever"
        }
    }
}

struct NowShowing: Codable, Hashable, Sendable {
    var title: String
    var description: String
    var source: String
    var created: String
    var previewUrl: String
    var item: Item?
}

struct PlayerView: Codable, Sendable {
    var playlist: PlaylistSummary?
    var current: NowShowing?
    var upcoming: [ItemSummary]
    var history: [ItemSummary]
    var hold: Hold?
    var lastChangeAt: String?
    var nextChangeAt: String?
    var busy: Bool
    var lastError: String?
    var progress: DisplayProgress?  // nil from older servers
}

/// A picture on its way to the frame (GET /api/progress): processing on the
/// server, loading onto the panel, the panel redrawing its e-paper. The
/// redraw is estimated: the panel does not say when it is done.
struct DisplayProgress: Codable, Hashable, Sendable {
    var stage: String
    var phase: String?
    var active: Bool
    var title: String
    var fraction: Double
    var secondsLeft: Int?
    var startedAt: String?
    var finishedAt: String?
    var message: String?

    static let idle = DisplayProgress(stage: "idle", active: false, title: "", fraction: 0)

    /// The three parts of the bar, in order.
    static let phases: [(key: String, label: String)] = [
        ("processing", "Przetwarzanie"), ("loading", "Ładowanie"), ("displaying", "Wyświetlanie"),
    ]

    var isDone: Bool { stage == "done" }
    var isFailed: Bool { stage == "failed" }
    var isWaiting: Bool { stage == "waiting" }

    /// Index of the current part of the bar; past the last one when done.
    var phaseIndex: Int? {
        if isDone { return Self.phases.count }
        return phase.flatMap { key in Self.phases.firstIndex { $0.key == key } }
    }

    var stageLabel: String {
        switch stage {
        case "rendering": "Przygotowuję obraz dla e-papieru"
        case "sending": "Łączę się z ramką"
        case "waking": "Budzę ramkę"
        case "downloading": "Ramka pobiera obraz"
        case "refreshing": "Ramka odświeża ekran"
        case "done": "Obraz jest na ramce"
        case "waiting": "Obraz poczeka, aż ramka się obudzi"
        case "failed": "Nie udało się wysłać obrazu"
        default: ""
        }
    }

    var timeLeftLabel: String? {
        guard active, let left = secondsLeft, left > 1 else { return nil }
        if left < 90 { return "ok. \(left) s" }
        return "ok. \((left + 30) / 60) min"
    }
}

struct DeviceStatus: Codable, Hashable, Sendable {
    var configured: Bool
    var reachable: Bool?
    var checkedAt: String?
    var lastSeen: String?
    var batteryLevel: Int?
    var charging: Bool?
    var powerSource: String?
    var batteryRaw: String?
    var networkStandby: Bool?
    var firmware: String?
    var model: String?
    var serial: String?
    var name: String?
    var error: String?
    var lastPushAt: String?
    var lastFetchAt: String?
    var pendingPush: Bool?
    var wakesAt: String?
}

/// How the server reaches the panel (Ramka → Ekran); the PIN is never sent back.
struct PanelConfig: Codable, Hashable, Sendable {
    var host: String?
    var mac: String?
    var port: Int
    var pinSet: Bool
    /// Saved in the app; otherwise taken from frame.env or the add-on options.
    var fromApp: Bool
}

struct PanelConfigUpdate: Encodable, Sendable {
    var host: String?
    /// Left out keeps the PIN on the server, "" removes it.
    var pin: String?
    var mac: String?
    var port: Int

    /// Optionals are always written, so an empty MAC clears it on the server.
    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(host, forKey: .host)
        try container.encodeIfPresent(pin, forKey: .pin)
        try container.encode(mac, forKey: .mac)
        try container.encode(port, forKey: .port)
    }

    private enum CodingKeys: String, CodingKey { case host, pin, mac, port }
}

/// The same checks the server makes, to point at a typo before saving.
enum PanelAddress {
    /// A bare address: "http://192.168.1.152/" becomes 192.168.1.152; nil if it cannot be one.
    static func host(_ text: String) -> String? {
        var host = text.trimmingCharacters(in: .whitespaces)
        if let scheme = host.range(of: "://") { host = String(host[scheme.upperBound...]) }
        host = String(host.prefix { $0 != "/" })
        let allowed = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-")
        guard host.unicodeScalars.allSatisfy(allowed.contains) else { return nil }
        return host
    }

    /// Any common spelling as AA:BB:CC:DD:EE:FF, "" for none; nil if it cannot be one.
    static func mac(_ text: String) -> String? {
        let hex = text.filter { !" :-.".contains($0) }.uppercased()
        if hex.isEmpty { return "" }
        guard hex.count == 12, hex.allSatisfy(\.isHexDigit) else { return nil }
        var pairs: [String] = []
        var rest = Substring(hex)
        while !rest.isEmpty {
            pairs.append(String(rest.prefix(2)))
            rest = rest.dropFirst(2)
        }
        return pairs.joined(separator: ":")
    }
}

struct ServerStatus: Codable, Hashable, Sendable {
    var version: String
    var uptimeS: Int
    var libraryCount: Int
    var playlists: Int
    var jobsRunning: Int
    var palette: String
}

struct StatusView: Codable, Sendable {
    var device: DeviceStatus
    var server: ServerStatus
}

struct Presentation: Codable, Hashable, Sendable {
    var preset: String
    var fit: String  // "fit" | "fill" | "details" | "description" | "auto"; photos: "fit" | "fill" | "multi"
    var mat: String = "white"  // "white" | "cream" | "grey" | "black" | "picture"
    var margin: Double
    var label: Bool
    /// "multi": photos on one board (2–8), or a random number each time,
    /// and the grid's letter (MultiGrid.all) or "auto" (by the photos' shapes).
    var multiCount: Int = 4
    var multiRandom: Bool = false
    var multiGrid: String = "auto"

    var key: String { "\(preset),\(fit),\(mat),\(margin),\(label),\(multiCount),\(multiRandom),\(multiGrid)" }

    init(preset: String, fit: String, mat: String = "white", margin: Double, label: Bool) {
        self.preset = preset
        self.fit = fit
        self.mat = mat
        self.margin = margin
        self.label = label
    }

    private enum CodingKeys: String, CodingKey {
        case preset, fit, mat, margin, label, multiCount, multiRandom, multiGrid
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        preset = try c.decode(String.self, forKey: .preset)
        fit = try c.decode(String.self, forKey: .fit)
        mat = try c.decodeIfPresent(String.self, forKey: .mat) ?? "white"  // older servers
        margin = try c.decode(Double.self, forKey: .margin)
        label = try c.decode(Bool.self, forKey: .label)
        multiCount = try c.decodeIfPresent(Int.self, forKey: .multiCount) ?? 4
        multiRandom = try c.decodeIfPresent(Bool.self, forKey: .multiRandom) ?? false
        multiGrid = try c.decodeIfPresent(String.self, forKey: .multiGrid) ?? "auto"
    }
}

struct FrameSettings: Codable, Hashable, Sendable {
    /// The playlist the frame plays (an album playlist shows its photos); nil: Suggestions.
    var playlistId: Int?
    /// Times of day ("HH:MM") the picture changes at, the same on the
    /// charger and on battery; every day or every 2nd/3rd day.
    var changeTimes: [String]
    var changeEveryDays: Int
    /// Quiet hours run from here until the next change time (the morning one).
    var quietStart: String?
    var shuffle: Bool
    var avoidRepeatDays: Int
    var orientation: String  // "landscape" | "portrait"
    var rotation: Int
    var art: Presentation
    var photo: Presentation
    var timezone: String
    var statusPollMinutes: Int
    /// Only seen at home: also accept freely licensed, not public-domain works.
    var privateUse: Bool? = nil
    /// WikiArt as a source, only to test the panel; its works leave the
    /// library when switched off.
    var wikiart: Bool? = nil

    /// Changes whenever the way pictures are framed on the panel changes;
    /// used to refresh cached "on the frame" previews.
    var presentationKey: String {
        [orientation, String(rotation), art.key, photo.key].joined(separator: "|")
    }

    static let defaults = FrameSettings(
        playlistId: nil, changeTimes: ["07:00"], changeEveryDays: 1,
        quietStart: "22:00", shuffle: true, avoidRepeatDays: 14,
        orientation: "landscape", rotation: 90,
        art: Presentation(preset: "auto", fit: "auto", margin: 0.05, label: false),
        photo: Presentation(preset: "auto", fit: "fill", margin: 0, label: false),
        timezone: "Europe/Warsaw", statusPollMinutes: 15
    )
}

extension FrameSettings {
    private enum CodingKeys: String, CodingKey {
        case playlistId, changeTimes, changeEveryDays, quietStart, shuffle, avoidRepeatDays
        case orientation, rotation, art, photo, timezone, statusPollMinutes, privateUse, wikiart
        case quietEnd  // older servers: decoded only
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        playlistId = try c.decodeIfPresent(Int.self, forKey: .playlistId)
        // Older servers have intervals instead: their changes start at the end of quiet hours.
        let quietEnd = try c.decodeIfPresent(String.self, forKey: .quietEnd)
        changeTimes = try c.decodeIfPresent([String].self, forKey: .changeTimes) ?? [quietEnd ?? "07:00"]
        changeEveryDays = try c.decodeIfPresent(Int.self, forKey: .changeEveryDays) ?? 1
        quietStart = try c.decodeIfPresent(String.self, forKey: .quietStart)
        shuffle = try c.decode(Bool.self, forKey: .shuffle)
        avoidRepeatDays = try c.decode(Int.self, forKey: .avoidRepeatDays)
        orientation = try c.decode(String.self, forKey: .orientation)
        rotation = try c.decode(Int.self, forKey: .rotation)
        art = try c.decode(Presentation.self, forKey: .art)
        photo = try c.decode(Presentation.self, forKey: .photo)
        timezone = try c.decode(String.self, forKey: .timezone)
        statusPollMinutes = try c.decode(Int.self, forKey: .statusPollMinutes)
        privateUse = try c.decodeIfPresent(Bool.self, forKey: .privateUse)
        wikiart = try c.decodeIfPresent(Bool.self, forKey: .wikiart)
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(playlistId, forKey: .playlistId)
        try c.encode(changeTimes, forKey: .changeTimes)
        try c.encode(changeEveryDays, forKey: .changeEveryDays)
        try c.encode(quietStart, forKey: .quietStart)  // null turns quiet hours off
        try c.encode(shuffle, forKey: .shuffle)
        try c.encode(avoidRepeatDays, forKey: .avoidRepeatDays)
        try c.encode(orientation, forKey: .orientation)
        try c.encode(rotation, forKey: .rotation)
        try c.encode(art, forKey: .art)
        try c.encode(photo, forKey: .photo)
        try c.encode(timezone, forKey: .timezone)
        try c.encode(statusPollMinutes, forKey: .statusPollMinutes)
        try c.encodeIfPresent(privateUse, forKey: .privateUse)
        try c.encodeIfPresent(wikiart, forKey: .wikiart)
    }

    /// When quiet hours end: the first change time after their start.
    var quietEnd: String? {
        guard let start = quietStart, let first = changeTimes.sorted().first else { return nil }
        let end = changeTimes.sorted().first { $0 > start } ?? first
        return end == start ? nil : end
    }
}

struct Museum: Codable, Hashable, Sendable, Identifiable {
    let key: String
    let name: String
    var id: String { key }
}

struct RemoteItem: Codable, Hashable, Sendable, Identifiable {
    var item: Item
    var inLibrary: Bool
    var id: String { item.id }

    /// The server's copy once it has one, else straight from the museum.
    var thumb: ImageRef {
        if inLibrary { return .thumb(id) }
        return URL(string: item.thumbUrl).map(ImageRef.url) ?? .thumb(id)
    }
}

/// A row of Discover, `GET /api/suggestions`.
struct SuggestionRow: Codable, Hashable, Sendable, Identifiable {
    let key: String  // "for-you" | "theme" | "best"
    let title: String
    var subtitle: String
    /// The theme to browse further (the theme of the day).
    var theme: String?
    var items: [RemoteItem]
    var id: String { key }
}

/// An idea for a playlist, `GET /api/themes`: browsed live from the
/// museums, or made into a smart playlist with its rules.
struct ArtTheme: Codable, Hashable, Sendable, Identifiable {
    let key: String
    let name: String
    let description: String
    /// "Kierunki i style", "Tematy", …
    var group: String?
    /// Works in the catalogue that fit, and four of them for the cover.
    var count: Int?
    var cover: [RemoteItem]?
    /// The playlist already made from it.
    var playlistId: Int?
    var rules: PlaylistRules?
    var id: String { key }
}

/// `POST /api/themes/{key}/playlist`
struct ThemePlaylist: Codable, Sendable {
    let playlist: PlaylistSummary
    /// Fetching its first works from the museums, if that started.
    var jobId: String?
}

/// A style, subject, period or technique, `GET /api/vocabulary`.
struct TermInfo: Codable, Hashable, Sendable, Identifiable {
    let key: String
    let kind: String  // style | subject | period | technique
    let name: String
    var words: [String] = []
    var yearFrom: Int?
    var yearTo: Int?
    var id: String { key }
}

/// What typed words could mean, `GET /api/terms?q=`.
struct TermHit: Codable, Hashable, Sendable, Identifiable {
    let kind: String  // artist | style | subject | period | technique | word
    let key: String
    let name: String
    var detail: String = ""
    var count: Int = 0
    var id: String { kind + ":" + key }

    var token: SearchToken { SearchToken(kind: kind, key: key, name: name) }
}

/// What the museums have for words the catalogue doesn't know, `GET /api/terms/museums?q=`.
struct MuseumHint: Codable, Sendable {
    let total: Int
    let artists: [TermHit]
    let items: [RemoteItem]
    var failed: [String]?
}

/// One chip of a search or of a smart playlist's rules.
struct SearchToken: Hashable, Sendable, Identifiable {
    /// artist | word | style | subject | period | technique, or for rules of
    /// older playlists: legacy-style | legacy-subject (museum facet values).
    let kind: String
    let key: String
    let name: String
    var id: String { kind + ":" + key }

    var kindName: String {
        switch kind {
        case "artist": "Artysta"
        case "style", "legacy-style": "Styl"
        case "subject", "legacy-subject": "Temat"
        case "period": "Epoka"
        case "technique": "Technika"
        default: "Słowo"
        }
    }

    var icon: String {
        switch kind {
        case "artist": "person"
        case "style", "legacy-style": "paintpalette"
        case "subject", "legacy-subject": "tag"
        case "period": "calendar"
        case "technique": "scribble.variable"
        default: "text.magnifyingglass"
        }
    }
}

extension PlaylistRules {
    /// The rules' artists, terms and words as chips; `names` gives the
    /// Polish names of terms.
    func tokens(names: [String: String]) -> [SearchToken] {
        var tokens = artists.map { SearchToken(kind: "artist", key: $0, name: $0) }
        tokens += terms.map { key in
            let kind = key.hasPrefix("years:") ? "period" : String(key.prefix { $0 != ":" })
            return SearchToken(kind: kind, key: key, name: names[key] ?? Self.yearsName(key) ?? key)
        }
        tokens += styles.map { SearchToken(kind: "legacy-style", key: $0, name: $0) }
        tokens += subjects.map { SearchToken(kind: "legacy-subject", key: $0, name: $0) }
        if !query.trimmingCharacters(in: .whitespaces).isEmpty {
            tokens.append(SearchToken(kind: "word", key: query, name: query))
        }
        return tokens
    }

    /// Puts chips back into the rules.
    mutating func setTokens(_ tokens: [SearchToken]) {
        artists = tokens.filter { $0.kind == "artist" }.map(\.key)
        terms = tokens.filter { ["style", "subject", "period", "technique"].contains($0.kind) }.map(\.key)
        styles = tokens.filter { $0.kind == "legacy-style" }.map(\.key)
        subjects = tokens.filter { $0.kind == "legacy-subject" }.map(\.key)
        query = tokens.filter { $0.kind == "word" }.map(\.key).joined(separator: " ")
    }

    /// "years:1880-1914" as "1880–1914".
    static func yearsName(_ key: String) -> String? {
        guard key.hasPrefix("years:") else { return nil }
        return key.dropFirst("years:".count).replacingOccurrences(of: "-", with: "–")
    }

    /// A name for a playlist made from these rules.
    func suggestedName(names: [String: String]) -> String {
        tokens(names: names).prefix(3).map(\.name).joined(separator: " · ")
    }
}

/// `GET /api/themes/{key}?page=`
struct ArtThemePage: Codable, Sendable {
    let items: [RemoteItem]
    let more: Bool
}

struct RemotePage: Codable, Sendable {
    let total: Int
    let items: [RemoteItem]
    /// Museums that did not answer a search of all of them.
    var failed: [String]?
}

/// A themed batch of museum works, `GET /api/library/packs`.
struct LibraryPack: Codable, Hashable, Sendable, Identifiable {
    let key: String
    let name: String
    let description: String
    /// Most works the pack can add.
    let size: Int
    var importing: Bool
    var id: String { key }
}

/// Random works to add, `POST /api/library/draw`.
struct DrawRequest: Codable, Hashable, Sendable {
    var count = 100
    var yearFrom: Int?
    var yearTo: Int?
    /// English, as the museums name styles, e.g. "Impressionism".
    var style = ""
    var kind = "any"  // any | painting | print | drawing | poster
    var minSuitability = 0.0
}

/// A background import on the server, `GET /api/jobs/{id}`.
struct JobStatus: Codable, Hashable, Sendable {
    let id: String
    var total: Int
    var done: Int
    var failed: Int
    var skipped: Int?
    var finished: Bool
    var error: String
    var itemIds: [String]
}

struct DisplayResponse: Codable, Sendable {
    var pushed: Bool
    var fetched: Bool?
    var message: String?
}

struct Health: Codable, Sendable {
    let ok: Bool
    let version: String
    let palette: String
}

/// Library listing filters (all optional).
struct LibraryQuery: Hashable, Sendable {
    var text = ""
    var artists: [String] = []
    var styles: [String] = []
    var subjects: [String] = []
    var colors: [String] = []
    var kinds: [ItemKind] = []
    /// Terms of the server's vocabulary, as in `PlaylistRules.terms`.
    var terms: [String] = []
    var sources: [String] = []
    var yearFrom: Int?
    var yearTo: Int?
    var favoritesOnly = false
    /// Only works the owner kept, not those the server added to the catalogue.
    var keptOnly = false
    var sort = "artist"
    var offset = 0
    var limit = 200

    var activeFilterCount: Int {
        artists.count + styles.count + subjects.count + colors.count + kinds.count + terms.count
            + (favoritesOnly ? 1 : 0) + (keptOnly ? 1 : 0)
    }

    /// Works of the catalogue and library that fit `rules`.
    init(rules: PlaylistRules, sort: String = "suitability", limit: Int = 60) {
        text = rules.query
        artists = rules.artists
        styles = rules.styles
        subjects = rules.subjects
        colors = rules.colors
        kinds = rules.kinds
        terms = rules.terms
        sources = rules.sources
        yearFrom = rules.yearFrom
        yearTo = rules.yearTo
        self.sort = sort
        self.limit = limit
    }

    init() {}
}

/// The last synchronisation of an album playlist with its album.
struct AlbumSync: Codable, Hashable, Sendable {
    var at: String
    var name: String
    var count: Int
    var added: Int?
    var error: String?
}

// MARK: Framing (server/src/frame_server/web/library_api.py)

/// Which part of a picture a window shows: centre as fractions of the
/// picture, zoom 1 = the largest part of the window's shape.
struct Crop: Codable, Hashable, Sendable {
    var x: Double = 0.5
    var y: Double = 0.5
    var zoom: Double = 1
    /// Passe-partout only: the window's shape (width / height); nil keeps the picture's.
    var aspect: Double?
}

struct FramingWindow: Codable, Hashable, Sendable {
    let role: String  // "picture" (passe-partout) | "fill" | "detail"
    let aspect: Double
    var crop: Crop
    let custom: Bool
    /// Where the window is on the canvas: x, y, width, height as fractions
    /// of it. Nil from older servers.
    var rect: [Double]?
    /// Passe-partout: where a window of another shape would be centred.
    var area: [Double]?

    var frame: CGRect? { Self.unit(rect) }
    var areaFrame: CGRect? { Self.unit(area) }

    private static func unit(_ values: [Double]?) -> CGRect? {
        guard let values, values.count == 4 else { return nil }
        return CGRect(x: values[0], y: values[1], width: values[2], height: values[3])
    }
}

/// Crops for one orientation, by mode (server: library.models.Framing). Sent
/// with a preview to try crops before they are saved.
struct FramingCrops: Codable, Hashable, Sendable {
    var fill: Crop?
    var details: [Crop]?
    var detail: Crop?  // "description": its one close-up
    var fit: Crop?  // "fit": the part shown and the window's shape

    /// `crops` as edited in a framing view of resolved mode `mode`.
    init(mode: String, crops: [Crop]) {
        switch mode {
        case "fill": fill = crops.first
        case "details": details = crops.count == 2 ? crops : nil
        case "description": detail = crops.first
        case "fit": fit = crops.first
        default: break
        }
    }

    init(fill: Crop? = nil, details: [Crop]? = nil, detail: Crop? = nil, fit: Crop? = nil) {
        self.fill = fill
        self.details = details
        self.detail = detail
        self.fit = fit
    }
}

/// `GET /api/library/items/{id}/framing`
struct FramingView: Codable, Hashable, Sendable {
    let orientation: String
    let fit: String  // resolved: "fit" | "fill" | "details" | "description"
    let width: Int
    let height: Int
    var windows: [FramingWindow]
}
