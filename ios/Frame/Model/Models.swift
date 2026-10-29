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
    /// A photo sent once from the camera roll ("Zdjęcie na ramkę"): shown
    /// with its own look, and never in a list or a rotation.
    var look: Look? = nil

    var summary: ItemSummary {
        ItemSummary(
            id: id, kind: kind, source: source, title: title, artist: artist, dateText: dateText,
            year: year, colors: colors, width: width, height: height, favorite: favorite,
            suitability: suitability
        )
    }
}

/// A work's Polish title and texts, written on the server by the language
/// model ("Polskie tytuły i opisy").
struct PolishText: Codable, Hashable, Sendable {
    var title: String
    var frame: String
    var full: String
    var medium: String
    var date: String
    /// "Holender, 1853–1890".
    var artistNote: String
    /// "translation" of the museum's description, or a "note" written from
    /// the picture and what is known about it.
    var written: String
    /// For a note: what it was written from ("obraz", "dane muzeum"...).
    var sources: [String]

    var isNote: Bool { written == "note" }
}

/// A work's Polish texts for its card.
struct PolishView: Codable, Hashable, Sendable {
    /// "ready"; "waiting" (being written, ask again); "none" (the model
    /// could not); "off" (no key, switched off, or no museum work).
    var status: String
    var text: PolishText?
}

/// What the model saw in a work or photo, for its card.
struct SeenView: Codable, Hashable, Sendable {
    /// As in PolishView.
    var status: String
    /// Polish words: things, places, the mood.
    var words: [String]
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
    /// The Polish title, in "Teraz" once the work has one.
    var titlePl: String?

    /// The title "Teraz" shows: Polish when there is one.
    var shownTitle: String { titlePl ?? title }

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

    /// "Ulubione", the owner's hearts: always there, never deleted.
    var isFavorites: Bool { kind == .smart && rules.favoritesOnly }
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

    var isFavorites: Bool { kind == .smart && rules.favoritesOnly }
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
    /// The work's Polish title and texts, once written; nil from older servers.
    var polish: PolishText?
}

struct PlayerView: Codable, Sendable {
    var playlist: PlaylistSummary?
    var current: NowShowing?
    var upcoming: [ItemSummary]
    /// Those of `upcoming` added with "Dodaj do kolejki"; nil from older servers.
    var queued: [String]? = nil
    var history: [ItemSummary]
    var hold: Hold?
    var lastChangeAt: String?
    var nextChangeAt: String?
    var busy: Bool
    var lastError: String?
    var progress: DisplayProgress?  // nil from older servers
    var delivery: Delivery? = nil  // nil from older servers
}

/// Whether `current` reached the panel: the server knows which picture the
/// panel downloaded last, and why a push did not get there.
struct Delivery: Codable, Hashable, Sendable {
    var state: String  // shown, sending, waiting, failed, unknown
    /// What the panel shows instead of `current`.
    var onFrame: NowShowing?
    var shownAt: String?
    var failedAt: String?
    var failure: String?  // "timeout" or "error"
    var message: String?
    /// Waiting in deep sleep (Wi-Fi off): HH:MM of the panel's alarm, and
    /// the moment it rings (servers before the economy mode: nil).
    var asleepUntil: String?
    var asleepUntilAt: String?
    /// Economy mode: a wake the frame did not show up for.
    var missedWakeAt: String?
    /// Waiting with the Wi-Fi off (economy, quiet hours); false: asleep with
    /// the Wi-Fi on and Wake-on-LAN did not reach it (missing before 0.27).
    var deepSleep: Bool?
    /// The frame does not run the Frame app and the server cannot build it:
    /// the Samsung certificates are missing on the server.
    var noApp: Bool?

    var isShown: Bool { state == "shown" || state == "unknown" }
    var isWaiting: Bool { state == "waiting" }
    var isFailed: Bool { state == "failed" }

    /// "Teraz" over the picture that did not reach the frame.
    var headline: String {
        switch state {
        case "sending": return "W drodze na ramkę"
        case "waiting":
            if noApp == true { return "Ramka nie ma aplikacji Frame" }
            if let missed = When.clock(missedWakeAt) { return "Ramka nie obudziła się o \(missed)" }
            if let wake = When.at(asleepUntilAt) { return "Pojawi się \(wake)" }
            return "Czeka na ramkę"
        case "failed": return "Nie dotarł na ramkę"
        default: return "Teraz na ramce"
        }
    }

    static let noCertificates = "Na serwerze brakuje certyfikatów Samsunga, więc nie zbuduje aplikacji dla ramki. Skopiuj raz author.p12, distributor.p12 i password.txt do folderu data/panel-app/certs serwera (np. File Station)."

    /// Why it is not on the frame (yet).
    var explanation: String {
        let why: String
        switch state {
        case "waiting":
            let button = "Wcześniej: naciśnij krótko przycisk z tyłu ramki."
            if noApp == true {
                why = Self.noCertificates
            } else if missedWakeAt != nil, let wake = When.at(asleepUntilAt) {
                why = "Spróbuje znowu \(wake). \(button)"
            } else if asleepUntilAt != nil, deepSleep == false {
                why = "Ramka śpi i nie odpowiedziała na sygnał budzenia. Pobierze obraz przy najbliższej pobudce. \(button)"
            } else if asleepUntilAt != nil {
                why = "Ramka śpi bez Wi-Fi, żeby oszczędzać baterię. \(button)"
            } else {
                why = asleepUntil.map { "Ramka śpi do \($0), obraz trafi na nią po przebudzeniu." }
                    ?? "Ramka nie odpowiada, obraz trafi na nią, gdy się obudzi. \(button)"
            }
        case "failed":
            let when = When.schedule(failedAt).map { " (\($0))" } ?? ""
            switch failure {
            case "timeout": why = "Wysyłka\(when) nie udała się: ramka nie pobrała obrazu."
            case "error": why = "Wysyłka\(when) nie udała się: błąd połączenia z ramką."
            default: why = "Ramka nie pobrała jeszcze tego obrazu."
            }
        default:
            why = " "
        }
        return why
    }
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
    /// The same alarm as a moment, for "Teraz" (missing before 0.26).
    var wakeAt: String?
    /// "online" | "standby" | "deep_sleep" | "offline"; missing from servers before 0.12.
    var powerState: String?
    /// Not answering, yet still on the Wi-Fi (answers ARP): asleep, not gone.
    /// Nil when not asked or when the server cannot tell; missing before 0.15.
    var onNetwork: Bool?
    /// The frame runs the Frame app: it asks for its pictures and wakes by
    /// its own alarm. False: not seen asking yet, the server is starting it.
    var panelApp: Bool?
    /// Its Wi-Fi as the Frame app last read it; nil before the app reported
    /// it and from servers before 0.26.
    var wifi: PanelWifi?
    /// The Samsung certificates the app is signed with expire soon (or did).
    var certificatesExpireAt: String?
    /// The power mode ("online", "economy") set while the frame sleeps: it
    /// takes it on at its next wake. Nil when nothing waits.
    var modePending: String?
}

/// The frame's Wi-Fi, read by the Frame app on the panel at every wake.
struct PanelWifi: Codable, Hashable, Sendable {
    var readAt: String
    /// 0–1; from `level` (0–5) when the panel gives bars.
    var signal: Double?
    var level: Int?
    var ssid: String?
    var ip: String?
    /// MHz: 2437 is 2.4 GHz (channel 6).
    var frequency: Int?
    /// Where the server looks for the frame, and the network it was last
    /// on at that address.
    var expectedIp: String?
    var homeSsid: String?
    /// On another network: the server reaches it neither over MDC nor with
    /// Wake-on-LAN.
    var wrongNetwork: Bool?

    var band: String? {
        switch frequency ?? 0 {
        case 2400..<2500: "2,4 GHz"
        case 4900..<5925: "5 GHz"
        case 5925..<7200: "6 GHz"
        default: nil
        }
    }

    var strength: String? {
        guard let signal else { return nil }
        let word = signal < 0.35 ? "słaby" : signal < 0.65 ? "średni" : "dobry"
        if let level { return "sygnał \(word) (\(level)/5)" }
        return "sygnał \(word) (\(Int((signal * 100).rounded())) %)"
    }

    /// Why it is on the wrong network, in a sentence; nil when it is not.
    var warning: String? {
        guard wrongNetwork == true else { return nil }
        if let ssid, let homeSsid, ssid != homeSsid {
            return "Ramka połączyła się z siecią \(ssid) zamiast \(homeSsid): serwer jej nie obudzi ani nie wyśle obrazu. Wybierz \(homeSsid) w ustawieniach Wi-Fi ekranu."
        }
        if let ip, let expectedIp {
            return "Ramka ma adres \(ip), a serwer szuka jej pod \(expectedIp). Popraw adres poniżej albo przywróć stały adres w routerze."
        }
        return "Ramka jest w innej sieci niż zwykle."
    }
}

/// The Frame app on the panel (Samsung "Custom" content source): the only
/// way pictures reach the frame.
struct PanelAppView: Codable, Hashable, Sendable {
    var active: Bool
    var package: PanelAppPackage?
    var state: PanelAppState
    /// The Samsung certificates on the server; missing before 0.27.
    var certificates: [PanelCertificate]?
    /// Set when they expire within two months (or already have).
    var certificatesExpireAt: String?
}

/// The package the server built and signed for the panel.
struct PanelAppPackage: Codable, Hashable, Sendable {
    var version: String
    var size: Int
    var uploadedAt: String
}

/// One of the two Samsung certificates (author, distributor).
struct PanelCertificate: Codable, Hashable, Sendable {
    var role: String
    var subject: String
    var expiresAt: String
}

struct PanelAppState: Codable, Hashable, Sendable {
    var active: Bool
    var seenAt: String?
    var build: String?
    var asleep: Bool?
    var wakeAt: String?
    var standby: Bool?
    var missedWake: String?
    var installedAt: String?
}

/// "Obudź ramkę": whether the magic packets went out and the panel answered.
struct WakeResult: Codable, Hashable, Sendable {
    var sent: Bool
    var woke: Bool?  // missing from servers before 0.11
    var asleepUntil: String?
    var reason: String?
    /// "no_certificates" | "no_mac": why nothing could be tried (0.27+).
    var problem: String?
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

/// How much disk the library takes on the server and how much it may take
/// (Ramka → trybik → Konfiguracja). Sizes in bytes; limits in MB, as the
/// server counts them (1 MB = 1 MiB).
struct LibraryStorage: Codable, Hashable, Sendable {
    struct Usage: Codable, Hashable, Sendable {
        /// Thumbnails of the catalogue browsed in the app.
        var catalogueBytes: Int64
        /// Display-size originals the server can download again: museum
        /// works and shared-album photos.
        var originalsBytes: Int64
        /// Uploads and photos it cannot: always kept, outside the limits.
        var ownBytes: Int64
        /// Pictures prepared for the panel and their previews.
        var panelBytes: Int64
        var databaseBytes: Int64
        var totalBytes: Int64
        var freeBytes: Int64?
        var measuredAt: Double
    }

    var usage: Usage
    var catalogueMb: Int
    /// From frame.env or the add-on options.
    var catalogueDefaultMb: Int
    var catalogueFromApp: Bool
    var originalsMb: Int
    var originalsDefaultMb: Int
    var originalsFromApp: Bool
}

/// One limit or both; the default value goes back to frame.env.
struct LibraryStorageUpdate: Encodable, Sendable {
    var catalogueMb: Int?
    var originalsMb: Int?
}

/// Claude (Anthropic's API) working for the library: keywords for what
/// pictures show and Polish texts. The key itself never comes back.
struct AiSettings: Codable, Hashable, Sendable {
    struct Progress: Codable, Hashable, Sendable {
        /// Items with an up-to-date answer.
        var done: Int
        /// Items the server will still ask about in the background.
        var waiting: Int
        /// Refused or unreadable answers, not asked again.
        var refused: Int
        /// Questions in batches ("Opisz bibliotekę") not yet answered.
        var batchItems: Int
        var batchDone: Int
        var preparing: Bool
    }

    var keySet: Bool
    /// The key's last characters, to tell which one is saved.
    var keyTail: String?
    /// Saved in the app, not taken from frame.env or the add-on options.
    var keyFromApp: Bool
    var plText: Bool
    var keywordsArtworks: Bool
    var keywordsPhotos: Bool
    var monthlyLimitUsd: Double
    /// This month.
    var spentUsd: Double
    var keywordsProgress: Progress
    /// Nil until the server writes Polish texts.
    var plTextProgress: Progress?
    /// Why the server paused asking, if it did.
    var error: String?
}

/// Only what is set changes.
struct AiSettingsUpdate: Encodable, Sendable {
    var plText: Bool?
    var keywordsArtworks: Bool?
    var keywordsPhotos: Bool?
    var monthlyLimitUsd: Double?
}

struct AiKeyUpdate: Encodable, Sendable {
    var key: String
}

/// What "Opisz bibliotekę" would ask about, and about what it costs.
struct AiEstimate: Codable, Hashable, Sendable {
    var items: Int
    var usd: Double
}

struct AiStarted: Codable, Hashable, Sendable {
    var items: Int
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
    /// A bare address: "http://203.0.113.152/" becomes 203.0.113.152; nil if it cannot be one.
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
    var fit: String  // "fit" | "fill" | "description" | "auto"; photos: "fit" | "fill" | "multi"
    var mat: String = "white"  // "white" | "cream" | "grey" | "black" | "picture" | "picture_dark"
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

/// How a photo sent once ("Zdjęcie na ramkę") is shown, in place of the
/// settings' presentation for photos; its style is always automatic.
struct Look: Codable, Hashable, Sendable {
    var fit = "fill"  // "fill" | "fit" (in a passe-partout)
    var mat = "white"
    var margin = 0.05

    var key: String { "\(fit),\(mat),\(margin)" }

    /// To start with: the settings' presentation for photos, or the whole
    /// frame where that is several photos to a board.
    init(_ photo: Presentation) {
        fit = photo.fit == "fit" ? "fit" : "fill"
        mat = photo.mat
        margin = max(photo.margin, 0.05)
    }
}

extension Presentation {
    /// This presentation for photos as a photo sent once with `look` gets it.
    func with(_ look: Look) -> Presentation {
        var presentation = self
        presentation.preset = "auto"
        presentation.fit = look.fit
        presentation.mat = look.mat
        presentation.margin = look.margin
        presentation.label = false
        return presentation
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
    /// The frame's name in the app; nil: the name the panel reports.
    var name: String? = nil
    /// "online" or "economy" ("Oszczędny": on battery the frame sleeps with
    /// the Wi-Fi off between its own wakes); nil: a server before it.
    var powerMode: String? = nil
    /// Economy: also wake every so many hours after each change until the
    /// next one, to show what was sent from the app; 0: only at the changes.
    var checkEveryHours: Int? = nil
    /// Economy: no checks from here until `checkQuietEnd` (the changes still
    /// wake the frame); nil: checks all night too.
    var checkQuietStart: String? = nil
    /// nil: a server before economy quiet hours.
    var checkQuietEnd: String? = nil

    var isEconomy: Bool { powerMode == "economy" }

    /// Changes whenever the way pictures are framed on the panel changes;
    /// used to refresh cached "on the frame" previews.
    var presentationKey: String {
        [orientation, String(rotation), art.key, photo.key].joined(separator: "|")
    }

    /// Changes when the screen is turned; only then the server redraws the
    /// picture on the frame. A new presentation waits for the next picture.
    var screenKey: String { [orientation, String(rotation)].joined(separator: "|") }

    static let defaults = FrameSettings(
        playlistId: nil, changeTimes: ["07:00"], changeEveryDays: 1,
        quietStart: "22:00", shuffle: true, avoidRepeatDays: 14,
        orientation: "landscape", rotation: 90,
        art: Presentation(preset: "auto", fit: "auto", margin: 0.05, label: false),
        photo: Presentation(preset: "auto", fit: "fill", margin: 0, label: false),
        timezone: "Europe/Warsaw", statusPollMinutes: 15, powerMode: "online", checkEveryHours: 0,
        checkQuietStart: "22:00", checkQuietEnd: "07:00"
    )
}

extension FrameSettings {
    /// These settings, an edit of `base`, made on `current` instead: what
    /// the edit did not touch follows `current`. A draft opened before a
    /// playlist was presented elsewhere must not bring the old one back.
    func rebased(from base: FrameSettings, onto current: FrameSettings) -> FrameSettings {
        var out = self
        func follow<T: Equatable>(_ field: WritableKeyPath<FrameSettings, T>) {
            if self[keyPath: field] == base[keyPath: field] { out[keyPath: field] = current[keyPath: field] }
        }
        follow(\.playlistId)
        follow(\.changeTimes)
        follow(\.changeEveryDays)
        follow(\.quietStart)
        follow(\.shuffle)
        follow(\.avoidRepeatDays)
        follow(\.orientation)
        follow(\.rotation)
        follow(\.art)
        follow(\.photo)
        follow(\.timezone)
        follow(\.statusPollMinutes)
        follow(\.privateUse)
        follow(\.wikiart)
        follow(\.name)
        follow(\.powerMode)
        follow(\.checkEveryHours)
        follow(\.checkQuietStart)
        follow(\.checkQuietEnd)
        return out
    }
}

extension FrameSettings {
    private enum CodingKeys: String, CodingKey {
        case playlistId, changeTimes, changeEveryDays, quietStart, shuffle, avoidRepeatDays
        case orientation, rotation, art, photo, timezone, statusPollMinutes, privateUse, wikiart, name
        case powerMode, checkEveryHours, checkQuietStart, checkQuietEnd
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
        name = try c.decodeIfPresent(String.self, forKey: .name)
        powerMode = try c.decodeIfPresent(String.self, forKey: .powerMode)
        checkEveryHours = try c.decodeIfPresent(Int.self, forKey: .checkEveryHours)
        checkQuietStart = try c.decodeIfPresent(String.self, forKey: .checkQuietStart)
        checkQuietEnd = try c.decodeIfPresent(String.self, forKey: .checkQuietEnd)
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
        try c.encodeIfPresent(name, forKey: .name)
        try c.encodeIfPresent(powerMode, forKey: .powerMode)
        try c.encodeIfPresent(checkEveryHours, forKey: .checkEveryHours)
        if let end = checkQuietEnd {
            try c.encode(checkQuietStart, forKey: .checkQuietStart)  // null: checks all night
            try c.encode(end, forKey: .checkQuietEnd)
        }
    }

    /// Economy: the short wakes between the changes, every `checkEveryHours`
    /// from midnight (0:00, 4:00, 8:00, …), but not at a change time nor in
    /// `checkQuiet`, as minutes after midnight. As the server counts them
    /// (`schedule.check_times`).
    var checkMinutes: [Int] {
        guard isEconomy, let every = checkEveryHours, every > 0 else { return [] }
        let changes = Set(changeMinutes)
        return stride(from: 0, to: 24 * 60, by: every * 60)
            .filter { !changes.contains($0) && !inCheckQuiet($0) }
    }

    /// Economy: when there are no checks, in minutes after midnight (`end`
    /// may be before `start`: across midnight).
    var checkQuiet: (start: Int, end: Int)? {
        guard let start = checkQuietStart.flatMap(Self.minutes),
              let end = Self.minutes(checkQuietEnd ?? "07:00"), start != end else { return nil }
        return (start, end)
    }

    private func inCheckQuiet(_ minutes: Int) -> Bool {
        guard let quiet = checkQuiet else { return false }
        return quiet.start < quiet.end
            ? (quiet.start ..< quiet.end).contains(minutes)
            : minutes >= quiet.start || minutes < quiet.end
    }

    private static func minutes(_ hhmm: String) -> Int? {
        let parts = hhmm.split(separator: ":").compactMap { Int($0) }
        return parts.count == 2 ? parts[0] * 60 + parts[1] : nil
    }

    /// The change times as minutes after midnight, sorted.
    var changeMinutes: [Int] {
        Array(Set(changeTimes.compactMap(Self.minutes))).sorted()
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
    /// What copies of one work from several sources share (artist's surname
    /// and title); empty when the server can't tell.
    var work: String? = nil
    /// The library's copy of the work, when this one is from a more
    /// reliable source (the catalogue shows that copy already).
    var twin: String? = nil
    /// In a search's later answers: the worse copy, come before, that this
    /// one takes the place of.
    var replaces: String? = nil
    var id: String { item.id }

    /// The same work, maybe from another source (copies' years differ by
    /// two at most).
    func isSameWork(as other: RemoteItem) -> Bool {
        if id == other.id { return true }
        guard let work, !work.isEmpty, work == other.work, item.source != other.item.source else {
            return false
        }
        if let year = item.year, let otherYear = other.item.year { return abs(year - otherYear) <= 2 }
        return true
    }

    /// The server's copy once it has one, else straight from the museum.
    var thumb: ImageRef {
        if inLibrary { return .thumb(id) }
        return URL(string: item.thumbUrl).map(ImageRef.url) ?? .thumb(id)
    }

    /// The server's copy, when the museum refuses the thumbnail.
    var thumbFallback: ImageRef? {
        thumb == .thumb(id) ? nil : .thumb(id)
    }
}

extension Array where Element == RemoteItem {
    /// These and the works of the next page not here yet: the server leaves
    /// copies out within a page, this across pages. A better copy takes the
    /// place of the one it `replaces`.
    func adding(_ more: [RemoteItem]) -> [RemoteItem] {
        var result = self
        for candidate in more {
            if let old = candidate.replaces, let index = result.firstIndex(where: { $0.id == old }) {
                if !result.contains(where: { $0.id == candidate.id }) { result[index] = candidate }
            } else if !result.contains(where: { $0.isSameWork(as: candidate) }) {
                result.append(candidate)
            }
        }
        return result
    }
}

/// A row of Discover, `GET /api/suggestions`.
struct SuggestionRow: Codable, Hashable, Sendable, Identifiable {
    let key: String  // "for-you" | "like:<theme>" | "theme"
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
    /// artist | word | style | subject | period | technique | museum | color
    /// (the last two in Discover's search only), or for rules of
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
        case "museum": "Muzeum"
        case "color": "Kolor"
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
        case "museum": "building.columns"
        case "color": "circle.fill"
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
    /// The page to ask for next: the server skips searches that found
    /// nothing (an older server sends none, then it is the following one).
    var nextPage: Int?
}

struct RemotePage: Codable, Sendable {
    let total: Int
    let items: [RemoteItem]
    /// Museums that did not answer a search of all of them.
    var failed: [String]?
}

/// A page of one museum's works for Discover's search, a line of
/// `GET /api/discover/search/stream`.
struct MuseumAnswer: Codable, Sendable {
    /// The museum's key ("all" when a server answers for every museum at once).
    let source: String
    let total: Int
    let items: [RemoteItem]
    var failed: [String]?
    /// The page to ask the museum for more; nil when it has no more.
    var next: Int?
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
    let role: String  // "picture" (passe-partout, opis) | "fill" | "detail"
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
    var detail: Crop?  // "description": its close-up
    var picture: Crop?  // "description": the part of the picture shown
    var fit: Crop?  // "fit": the part shown and the window's shape

    /// `crops` as edited in a framing view of resolved mode `mode`.
    init(mode: String, crops: [Crop]) {
        switch mode {
        case "fill": fill = crops.first
        case "description" where crops.count == 2:  // the picture, then its close-up
            picture = crops[0]
            detail = crops[1]
        case "description": detail = crops.first
        case "fit": fit = crops.first
        default: break
        }
    }

    init(fill: Crop? = nil, detail: Crop? = nil, picture: Crop? = nil, fit: Crop? = nil) {
        self.fill = fill
        self.detail = detail
        self.picture = picture
        self.fit = fit
    }
}

/// `GET /api/library/items/{id}/framing`
struct FramingView: Codable, Hashable, Sendable {
    let orientation: String
    let fit: String  // resolved: "fit" | "fill" | "description"
    let width: Int
    let height: Int
    var windows: [FramingWindow]
}
