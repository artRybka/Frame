import Foundation

/// People on the server (server: users.py, web/users_api.py): the owner
/// holds the server's own token; a household member ("Domownik") joined
/// with an invitation and has their own hearts, playlists and
/// notifications, without Konfiguracja.
struct Me: Codable, Hashable, Sendable {
    var id: String
    var name: String
    /// "owner" or "member".
    var role: String
    /// This phone, when it joined with an invitation (nil: the server's token).
    var deviceId: String?
    /// Studies this person may still order today (nil: no limit).
    var studiesLeft: Int?
    /// Whether the server can have people (it has a token of its own).
    var people: Bool

    var isOwner: Bool { role != "member" }

    static let owner = Me(id: "owner", name: "Właściciel", role: "owner", deviceId: nil, studiesLeft: nil, people: false)
}

struct JoinRequest: Encodable, Sendable {
    var code: String
    var device: String
}

struct Joined: Decodable, Sendable {
    /// The phone's own token, given once: it goes to the Keychain.
    var token: String
    var me: Me
}

struct PersonDevice: Codable, Hashable, Identifiable, Sendable {
    var id: String
    var name: String
    var addedAt: String
    var lastSeenAt: String?
}

struct Person: Codable, Hashable, Identifiable, Sendable {
    var id: String
    var name: String
    var role: String
    var devices: [PersonDevice]
    var playlists: Int
    var favorites: Int

    var isOwner: Bool { role != "member" }
}

struct PendingInvite: Codable, Hashable, Identifiable, Sendable {
    var id: String
    var name: String
    var userId: String?
    var expiresAt: String
}

struct People: Codable, Hashable, Sendable {
    /// False without the server's own token: nobody can be invited.
    var people: Bool
    var users: [Person]
    var invites: [PendingInvite]
    var studyLimit: Int
}

struct InviteRequest: Encodable, Sendable {
    var name: String
    var userId: String?
}

struct NewInvite: Decodable, Sendable {
    /// The one-time code, shown once (in the QR code and the link).
    var code: String
    var invite: PendingInvite
}

struct PersonRename: Encodable, Sendable {
    var name: String
}

struct PeopleSettings: Encodable, Sendable {
    var studyLimit: Int
}

/// What an invitation's link carries: the code, where the server is and
/// who invites. `com.artrybka.frame://join?code=…&home=…&remote=…&from=…&frame=…`
struct Invitation: Hashable, Identifiable, Sendable {
    var code: String
    var home: String
    var remote: String
    var from: String
    var frame: String

    var id: String { code }

    static let scheme = "com.artrybka.frame"

    init(code: String, home: String, remote: String, from: String, frame: String) {
        self.code = code
        self.home = home
        self.remote = remote
        self.from = from
        self.frame = frame
    }

    init?(url: URL) {
        guard url.scheme == Self.scheme, url.host == "join",
              let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems
        else { return nil }
        func value(_ name: String) -> String { items.first { $0.name == name }?.value ?? "" }
        guard !value("code").isEmpty, !value("home").isEmpty || !value("remote").isEmpty else { return nil }
        self.init(code: value("code"), home: value("home"), remote: value("remote"), from: value("from"), frame: value("frame"))
    }

    var url: URL {
        var components = URLComponents()
        components.scheme = Self.scheme
        components.host = "join"
        components.queryItems = [
            URLQueryItem(name: "code", value: code),
            URLQueryItem(name: "home", value: home),
            URLQueryItem(name: "remote", value: remote),
            URLQueryItem(name: "from", value: from),
            URLQueryItem(name: "frame", value: frame),
        ].filter { !($0.value ?? "").isEmpty }
        return components.url ?? URL(string: "\(Self.scheme)://join")!
    }
}

extension FrameBackend {
    // The demo: one person, the owner, and invitations that lead nowhere.
    func me() async throws -> Me { .owner }
    func leave() async throws {}
    func people() async throws -> People {
        People(
            people: true,
            users: [Person(id: "owner", name: "Właściciel", role: "owner", devices: [], playlists: 6, favorites: 12)],
            invites: [],
            studyLimit: 5
        )
    }
    func invite(_ request: InviteRequest) async throws -> NewInvite {
        let expires = ISO8601DateFormatter().string(from: .now.addingTimeInterval(1800))
        return NewInvite(
            code: "demo-\(UUID().uuidString.prefix(8))",
            invite: PendingInvite(id: "demo", name: request.name, userId: request.userId, expiresAt: expires)
        )
    }
    func cancelInvite(id: String) async throws -> People { try await people() }
    func removeDevice(id: String) async throws -> People { try await people() }
    func removePerson(id: String) async throws -> People { try await people() }
    func renamePerson(id: String, name: String) async throws -> People { try await people() }
    func savePeopleSettings(_ settings: PeopleSettings) async throws -> People { try await people() }
}
