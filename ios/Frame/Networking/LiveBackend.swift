import Foundation

/// HTTP client for the frame server (server/src/frame_server/web/*).
struct LiveBackend: FrameBackend {
    let baseURL: URL
    let token: String?
    var isDemo: Bool { false }

    static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    static func encoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }

    // MARK: Player & status

    func health() async throws -> Health { try await get("/api/health") }

    func status(refresh: Bool) async throws -> StatusView {
        try await get("/api/status", query: [URLQueryItem(name: "refresh", value: refresh ? "true" : "false")])
    }

    func player() async throws -> PlayerView { try await get("/api/player") }
    func next() async throws { try await send("/api/player/next", method: "POST") }
    func previous() async throws { try await send("/api/player/previous", method: "POST") }

    func hold(_ spec: HoldSpec) async throws -> PlayerView {
        try await send("/api/player/hold", method: "POST", body: ["hold": spec.wireValue])
    }

    func releaseHold() async throws -> PlayerView {
        try await send("/api/player/hold", method: "DELETE")
    }

    // MARK: Library

    func items(_ q: LibraryQuery) async throws -> ItemPage {
        var query = [
            URLQueryItem(name: "q", value: q.text),
            URLQueryItem(name: "sort", value: q.sort),
            URLQueryItem(name: "offset", value: String(q.offset)),
            URLQueryItem(name: "limit", value: String(q.limit)),
        ]
        query += q.artists.map { URLQueryItem(name: "artist", value: $0) }
        query += q.styles.map { URLQueryItem(name: "style", value: $0) }
        query += q.subjects.map { URLQueryItem(name: "subject", value: $0) }
        query += q.colors.map { URLQueryItem(name: "color", value: $0) }
        query += q.kinds.map { URLQueryItem(name: "kind", value: $0.rawValue) }
        if q.favoritesOnly { query.append(URLQueryItem(name: "favorites", value: "true")) }
        return try await get("/api/library/items", query: query)
    }

    func item(id: String) async throws -> Item { try await get("/api/library/items/\(escape(id))") }

    func setFavorite(id: String, _ favorite: Bool) async throws -> Item {
        try await send("/api/library/items/\(escape(id))", method: "PATCH", body: ["favorite": favorite])
    }

    func setExcluded(id: String, _ excluded: Bool) async throws -> Item {
        try await send("/api/library/items/\(escape(id))", method: "PATCH", body: ["excluded": excluded])
    }

    func show(itemID: String, hold: HoldSpec) async throws {
        try await send("/api/library/items/\(escape(itemID))/show", method: "POST", body: ["hold": hold.wireValue])
    }

    func facets() async throws -> Facets { try await get("/api/library/facets") }

    func framing(itemID: String, orientation: String) async throws -> FramingView {
        try await get(
            "/api/library/items/\(escape(itemID))/framing",
            query: [URLQueryItem(name: "orientation", value: orientation)]
        )
    }

    private struct FramingUpdate: Encodable {
        let orientation: String
        let crops: [Crop]
    }

    func saveFraming(itemID: String, orientation: String, crops: [Crop]) async throws -> FramingView {
        try await send(
            "/api/library/items/\(escape(itemID))/framing", method: "PUT",
            body: FramingUpdate(orientation: orientation, crops: crops)
        )
    }

    func resetFraming(itemID: String, orientation: String) async throws -> FramingView {
        let path = "/api/library/items/\(escape(itemID))/framing"
        var req = request(path, method: "DELETE", query: [URLQueryItem(name: "orientation", value: orientation)])
        req.timeoutInterval = 60
        return try await perform(req)
    }

    // MARK: Playlists

    func playlists() async throws -> [PlaylistSummary] { try await get("/api/playlists") }
    func playlist(id: Int) async throws -> PlaylistDetail { try await get("/api/playlists/\(id)") }

    func savePlaylist(_ playlist: Playlist) async throws -> PlaylistDetail {
        if let id = playlist.id {
            return try await send("/api/playlists/\(id)", method: "PUT", body: playlist)
        }
        return try await send("/api/playlists", method: "POST", body: playlist)
    }

    func deletePlaylist(id: Int) async throws { try await send("/api/playlists/\(id)", method: "DELETE") }

    func addToPlaylist(id: Int, itemIDs: [String]) async throws -> PlaylistDetail {
        try await send("/api/playlists/\(id)/items", method: "POST", body: ["item_ids": itemIDs])
    }

    func previewRules(_ rules: PlaylistRules) async throws -> RulesPreview {
        try await send("/api/playlists/preview", method: "POST", body: rules)
    }

    func play(playlistID: Int) async throws { try await send("/api/playlists/\(playlistID)/play", method: "POST") }

    // MARK: Settings

    func settings() async throws -> FrameSettings { try await get("/api/settings") }

    func saveSettings(_ settings: FrameSettings) async throws -> FrameSettings {
        try await send("/api/settings", method: "PUT", body: settings)
    }

    // MARK: Museums

    func museums() async throws -> [Museum] { try await get("/api/museums") }

    func searchMuseum(source: String, query: String, page: Int) async throws -> RemotePage {
        try await get(
            "/api/museums/\(source)/search",
            query: [URLQueryItem(name: "q", value: query), URLQueryItem(name: "page", value: String(page))]
        )
    }

    func importArtwork(source: String, sourceID: String) async throws -> Item {
        try await send("/api/museums/\(source)/import", method: "POST", body: ["source_id": sourceID])
    }

    private struct JobRef: Decodable { let jobId: String }

    private struct ImportSearchBody: Encodable {
        let query: String
        let limit: Int
    }

    func importSearch(source: String, query: String, limit: Int) async throws -> String {
        let ref: JobRef = try await send(
            "/api/museums/\(source)/import-search", method: "POST", body: ImportSearchBody(query: query, limit: limit)
        )
        return ref.jobId
    }

    func packs() async throws -> [LibraryPack] { try await get("/api/library/packs") }

    func importPack(key: String) async throws -> String {
        let ref: JobRef = try await send("/api/library/packs/\(key)/import", method: "POST")
        return ref.jobId
    }

    func drawRandom(_ request: DrawRequest) async throws -> String {
        let ref: JobRef = try await send("/api/library/draw", method: "POST", body: request)
        return ref.jobId
    }

    func job(id: String) async throws -> JobStatus { try await get("/api/jobs/\(id)") }

    // MARK: Album

    func album() async throws -> AlbumInfo { try await get("/api/album") }
    func syncAlbum() async throws { try await send("/api/album/sync", method: "POST") }

    // MARK: Device

    func sendPhoto(_ data: Data, title: String, preset: String, hold: HoldSpec) async throws -> DisplayResponse {
        var form = MultipartForm()
        form.addField("preset", preset)
        form.addField("title", title)
        form.addField("hold", hold.wireValue)
        form.addFile("file", filename: "photo.jpg", mimeType: "image/jpeg", data: data)
        var req = request("/api/display", method: "POST")
        req.setValue(form.contentType, forHTTPHeaderField: "Content-Type")
        req.httpBody = form.body()
        req.timeoutInterval = 240
        return try await perform(req)
    }

    func uploadPhoto(_ upload: PhotoUpload) async throws -> Item {
        var form = MultipartForm()
        form.addField("kind", "photo")
        form.addField("title", upload.title)
        if let takenAt = upload.takenAt { form.addField("taken_at", takenAt) }
        if let latitude = upload.latitude, let longitude = upload.longitude {
            form.addField("latitude", String(latitude))
            form.addField("longitude", String(longitude))
        }
        form.addFile("file", filename: "photo.jpg", mimeType: "image/jpeg", data: upload.data)
        var req = request("/api/library/upload", method: "POST")
        req.setValue(form.contentType, forHTTPHeaderField: "Content-Type")
        req.httpBody = form.body()
        req.timeoutInterval = 120
        return try await perform(req)
    }

    func wake() async throws { try await send("/api/device/wake", method: "POST") }
    func sleep() async throws { try await send("/api/device/sleep", method: "POST") }

    // MARK: Images

    func request(for image: ImageRef) -> URLRequest? {
        var req: URLRequest
        switch image {
        case let .thumb(id): req = request("/api/library/items/\(escape(id))/thumb")
        case let .image(id): req = request("/api/library/items/\(escape(id))/image")
        case let .framePreview(id, settings):
            req = request("/api/library/items/\(escape(id))/preview", query: framingQuery(settings))
        case let .path(path): req = request(path)
        case let .url(url): req = URLRequest(url: url)
        }
        req.timeoutInterval = 120
        return req
    }

    /// Only what shapes the render; the rest of the settings would just
    /// split the caches.
    private struct Framing: Encodable {
        let orientation: String
        let rotation: Int
        let art: Presentation
        let photo: Presentation
    }

    private func framingQuery(_ settings: FrameSettings?) -> [URLQueryItem] {
        guard let settings else { return [] }
        let encoder = Self.encoder()
        encoder.outputFormatting = .sortedKeys  // same settings, same URL
        let framing = Framing(
            orientation: settings.orientation, rotation: settings.rotation,
            art: settings.art, photo: settings.photo
        )
        guard let data = try? encoder.encode(framing) else { return [] }
        return [URLQueryItem(name: "settings", value: String(decoding: data, as: UTF8.self))]
    }

    // MARK: Plumbing

    private func escape(_ id: String) -> String {
        id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/"))) ?? id
    }

    func request(_ path: String, method: String = "GET", query: [URLQueryItem] = []) -> URLRequest {
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) ?? URLComponents()
        let base = components.percentEncodedPath.hasSuffix("/") ? String(components.percentEncodedPath.dropLast()) : components.percentEncodedPath
        components.percentEncodedPath = base + path
        if !query.isEmpty { components.queryItems = query }
        var req = URLRequest(url: components.url ?? baseURL)
        req.httpMethod = method
        req.timeoutInterval = 60
        if let token {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return req
    }

    private func get<T: Decodable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        try await perform(request(path, query: query))
    }

    private func send(_ path: String, method: String) async throws {
        let _: EmptyResponse = try await perform(request(path, method: method))
    }

    private func send<T: Decodable>(_ path: String, method: String) async throws -> T {
        try await perform(request(path, method: method))
    }

    private func send<B: Encodable>(_ path: String, method: String, body: B) async throws {
        let _: EmptyResponse = try await send(path, method: method, body: body)
    }

    private func send<B: Encodable, T: Decodable>(_ path: String, method: String, body: B) async throws -> T {
        var req = request(path, method: method)
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try Self.encoder().encode(body)
        return try await perform(req)
    }

    private func perform<T: Decodable>(_ req: URLRequest) async throws -> T {
        let (data, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse else { throw BackendError.invalidResponse }
        guard (200 ..< 300).contains(http.statusCode) else {
            throw BackendError.http(status: http.statusCode, body: String(decoding: data, as: UTF8.self))
        }
        if T.self == EmptyResponse.self { return EmptyResponse() as! T }  // swiftlint:disable:this force_cast
        return try Self.decoder().decode(T.self, from: data)
    }
}

/// Placeholder for endpoints whose response body we ignore.
struct EmptyResponse: Decodable {}

/// multipart/form-data body builder.
struct MultipartForm {
    let boundary = "frame-\(UUID().uuidString)"
    private var parts: [Data] = []

    var contentType: String { "multipart/form-data; boundary=\(boundary)" }

    mutating func addField(_ name: String, _ value: String) {
        var part = Data()
        part.append("--\(boundary)\r\n")
        part.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n")
        part.append("\(value)\r\n")
        parts.append(part)
    }

    mutating func addFile(_ name: String, filename: String, mimeType: String, data: Data) {
        var part = Data()
        part.append("--\(boundary)\r\n")
        part.append("Content-Disposition: form-data; name=\"\(name)\"; filename=\"\(filename)\"\r\n")
        part.append("Content-Type: \(mimeType)\r\n\r\n")
        part.append(data)
        part.append("\r\n")
        parts.append(part)
    }

    func body() -> Data {
        var out = Data()
        parts.forEach { out.append($0) }
        out.append("--\(boundary)--\r\n")
        return out
    }
}

private extension Data {
    mutating func append(_ string: String) {
        append(Data(string.utf8))
    }
}
