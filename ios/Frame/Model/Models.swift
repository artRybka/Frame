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
    var colors: [String] = []
    var kinds: [ItemKind] = []
    var sources: [String] = []
    var yearFrom: Int?
    var yearTo: Int?
    var favoritesOnly: Bool = false
    var minSuitability: Double?

    var isEmpty: Bool {
        query.isEmpty && artists.isEmpty && styles.isEmpty && subjects.isEmpty && colors.isEmpty
            && kinds.isEmpty && sources.isEmpty && yearFrom == nil && yearTo == nil
            && !favoritesOnly && minSuitability == nil
    }
}

enum PlaylistKind: String, Codable, Hashable, Sendable {
    case smart, manual
}

/// Body for creating or updating a playlist.
struct Playlist: Codable, Hashable, Sendable {
    var id: Int?
    var name: String
    var description: String = ""
    var kind: PlaylistKind = .smart
    var rules = PlaylistRules()
    var itemIds: [String] = []
}

struct PlaylistSummary: Codable, Identifiable, Hashable, Sendable {
    let id: Int
    var name: String
    var description: String
    var kind: PlaylistKind
    var rules: PlaylistRules
    var itemCount: Int
    var coverItemIds: [String]
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
    var mode: String
    var playlist: PlaylistSummary?
    var current: NowShowing?
    var upcoming: [ItemSummary]
    var history: [ItemSummary]
    var hold: Hold?
    var lastChangeAt: String?
    var nextChangeAt: String?
    var busy: Bool
    var lastError: String?
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
    var mode: String  // "art" | "album"
    var playlistId: Int?
    var intervalMinutes: Int
    var intervalMinutesBattery: Int
    var quietStart: String?
    var quietEnd: String?
    var shuffle: Bool
    var avoidRepeatDays: Int
    var orientation: String  // "landscape" | "portrait"
    var rotation: Int
    var art: Presentation
    var photo: Presentation
    var albumUrl: String
    var timezone: String
    var statusPollMinutes: Int
    /// Only seen at home: also accept freely licensed, not public-domain works.
    var privateUse: Bool? = nil

    /// Changes whenever the way pictures are framed on the panel changes;
    /// used to refresh cached "on the frame" previews.
    var presentationKey: String {
        [orientation, String(rotation), art.key, photo.key].joined(separator: "|")
    }

    static let defaults = FrameSettings(
        mode: "art", playlistId: nil, intervalMinutes: 1440, intervalMinutesBattery: 1440,
        quietStart: "22:00", quietEnd: "07:00", shuffle: true, avoidRepeatDays: 14,
        orientation: "landscape", rotation: 90,
        art: Presentation(preset: "painting", fit: "auto", margin: 0.05, label: false),
        photo: Presentation(preset: "photo", fit: "fill", margin: 0, label: false),
        albumUrl: "", timezone: "Europe/Warsaw", statusPollMinutes: 15
    )
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
    var favoritesOnly = false
    var sort = "artist"
    var offset = 0
    var limit = 200

    var activeFilterCount: Int {
        artists.count + styles.count + subjects.count + colors.count + kinds.count
            + (favoritesOnly ? 1 : 0)
    }
}

struct AlbumSync: Codable, Hashable, Sendable {
    var at: String
    var count: Int
    var name: String
}

/// `GET /api/album`
struct AlbumInfo: Codable, Hashable, Sendable {
    var url: String
    var lastSync: AlbumSync?
    var photos: Int
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
}

/// `GET /api/library/items/{id}/framing`
struct FramingView: Codable, Hashable, Sendable {
    let orientation: String
    let fit: String  // resolved: "fit" | "fill" | "details" | "description"
    let width: Int
    let height: Int
    var windows: [FramingWindow]
}
