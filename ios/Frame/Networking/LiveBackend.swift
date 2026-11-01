import Foundation

/// HTTP client for the frame server (server/src/frame_server/web/*).
struct LiveBackend: FrameBackend {
    let route: ServerRoute
    let token: String?
    var isDemo: Bool { false }
    var baseURL: URL { route.baseURL }

    init(route: ServerRoute, token: String?) {
        self.route = route
        self.token = token
    }

    init(baseURL: URL, token: String?) {
        self.init(route: ServerRoute(home: baseURL), token: token)
    }

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
    func progress() async throws -> DisplayProgress { try await get("/api/progress") }
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
        query += q.terms.map { URLQueryItem(name: "term", value: $0) }
        query += q.sources.map { URLQueryItem(name: "source", value: $0) }
        if let from = q.yearFrom { query.append(URLQueryItem(name: "year_from", value: String(from))) }
        if let to = q.yearTo { query.append(URLQueryItem(name: "year_to", value: String(to))) }
        if q.favoritesOnly { query.append(URLQueryItem(name: "favorites", value: "true")) }
        if q.keptOnly { query.append(URLQueryItem(name: "kept", value: "true")) }
        return try await get("/api/library/items", query: query)
    }

    func item(id: String) async throws -> Item { try await get("/api/library/items/\(escape(id))") }

    func polish(itemID: String, wait: Int, early: Bool) async throws -> PolishView {
        var query = [URLQueryItem(name: "wait", value: String(wait))]
        if early { query.append(URLQueryItem(name: "early", value: "true")) }
        return try await get("/api/library/items/\(escape(itemID))/polish", query: query)
    }

    func sharpen(itemID: String, wait: Int) async throws -> SharperView {
        var req = request(
            "/api/library/items/\(escape(itemID))/sharpen", method: "POST",
            query: [URLQueryItem(name: "wait", value: String(wait))]
        )
        req.timeoutInterval = TimeInterval(wait + 30)
        return try await perform(req)
    }

    func describe(itemID: String, wait: Int) async throws -> SeenView {
        var req = request(
            "/api/library/items/\(escape(itemID))/describe", method: "POST",
            query: [URLQueryItem(name: "wait", value: String(wait))]
        )
        req.timeoutInterval = TimeInterval(wait + 30)
        return try await perform(req)
    }

    func setFavorite(id: String, _ favorite: Bool) async throws -> Item {
        try await send("/api/library/items/\(escape(id))", method: "PATCH", body: ["favorite": favorite])
    }

    func setExcluded(id: String, _ excluded: Bool) async throws -> Item {
        try await send("/api/library/items/\(escape(id))", method: "PATCH", body: ["excluded": excluded])
    }

    func setLook(itemID: String, _ look: Look) async throws -> Item {
        try await send("/api/library/items/\(escape(itemID))", method: "PATCH", body: ["look": look])
    }

    func deleteItem(id: String) async throws {
        try await send("/api/library/items/\(escape(id))", method: "DELETE")
    }

    func show(itemID: String, hold: HoldSpec) async throws {
        try await send("/api/library/items/\(escape(itemID))/show", method: "POST", body: ["hold": hold.wireValue])
    }

    func queueNext(itemID: String) async throws {
        try await send("/api/library/items/\(escape(itemID))/queue", method: "POST")
    }

    func dequeue(itemID: String) async throws -> PlayerView {
        try await send("/api/player/queue/\(escape(itemID))", method: "DELETE")
    }

    func skip(itemID: String) async throws -> PlayerView {
        try await send("/api/player/skip/\(escape(itemID))", method: "POST")
    }

    func facets() async throws -> Facets { try await get("/api/library/facets") }

    func framing(itemID: String, orientation: String, automatic: Bool) async throws -> FramingView {
        var query = [URLQueryItem(name: "orientation", value: orientation)]
        if automatic { query.append(URLQueryItem(name: "automatic", value: "true")) }
        return try await get("/api/library/items/\(escape(itemID))/framing", query: query)
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

    func removeFromPlaylist(id: Int, itemID: String) async throws -> PlaylistDetail {
        try await send("/api/playlists/\(id)/items/\(escape(itemID))", method: "DELETE")
    }

    func previewRules(_ rules: PlaylistRules) async throws -> RulesPreview {
        try await send("/api/playlists/preview", method: "POST", body: rules)
    }

    func play(playlistID: Int) async throws { try await send("/api/playlists/\(playlistID)/play", method: "POST") }

    func playSuggestions() async throws { try await send("/api/suggestions/play", method: "POST") }

    // MARK: Settings

    func settings() async throws -> FrameSettings { try await get("/api/settings") }

    func saveSettings(_ settings: FrameSettings) async throws -> FrameSettings {
        try await send("/api/settings", method: "PUT", body: settings)
    }

    // MARK: Discover

    func suggestions() async throws -> [SuggestionRow] { try await get("/api/suggestions") }

    func themes() async throws -> [ArtTheme] { try await get("/api/themes") }

    func dailyAgain() async throws -> DailyWork.Brief { try await send("/api/daily/again", method: "POST") }

    func weekArtistAgain() async throws -> ArtTheme { try await send("/api/themes/week-artist/again", method: "POST") }

    func daily(day: String?, wait: Int) async throws -> DailyWork {
        var query = [URLQueryItem(name: "wait", value: String(wait))]
        if let day { query.append(URLQueryItem(name: "day", value: day)) }
        var req = request("/api/daily", query: query)
        req.timeoutInterval = TimeInterval(wait + 30)
        return try await perform(req)
    }

    func study(itemID: String, wait: Int, lists: Bool) async throws -> StudyView {
        var query = [URLQueryItem(name: "wait", value: String(wait))]
        if !lists { query.append(URLQueryItem(name: "lists", value: "false")) }
        var req = request("/api/study/\(escape(itemID))", query: query)
        req.timeoutInterval = TimeInterval(wait + 30)
        return try await perform(req)
    }

    func studies() async throws -> [StudyBrief] { try await get("/api/studies") }

    func prepareStudy(itemID: String, again: Bool) async throws -> StudyView {
        let query = again ? [URLQueryItem(name: "again", value: "true")] : []
        return try await perform(request("/api/study/\(escape(itemID))", method: "POST", query: query))
    }

    func followStudy(itemID: String, activityToken: String, sandbox: Bool) async throws {
        try await send(
            "/api/study/\(escape(itemID))/activity", method: "PUT",
            body: StudyActivityToken(token: activityToken, sandbox: sandbox)
        )
    }

    func themePage(key: String, page: Int) async throws -> ArtThemePage {
        try await get("/api/themes/\(key)", query: [URLQueryItem(name: "page", value: String(page))])
    }

    func themePlaylist(key: String, play: Bool) async throws -> ThemePlaylist {
        try await send("/api/themes/\(key)/playlist", method: "POST", body: ["play": play])
    }

    func vocabulary() async throws -> [TermInfo] { try await get("/api/vocabulary") }

    func terms(_ text: String) async throws -> [TermHit] {
        try await get("/api/terms", query: [URLQueryItem(name: "q", value: text)])
    }

    func museumHint(_ text: String) async throws -> MuseumHint {
        try await get("/api/terms/museums", query: [URLQueryItem(name: "q", value: text)])
    }

    func searchMuseums(_ rules: PlaylistRules, sources: [String], page: Int) async throws -> RemotePage {
        try await get("/api/discover/search", query: museumQuery(rules, sources: sources, page: page))
    }

    func museumAnswers(_ rules: PlaylistRules, sources: [String], page: Int) async throws
        -> AsyncThrowingStream<MuseumAnswer, Error>
    {
        let query = museumQuery(rules, sources: sources, page: page)
        let (bytes, response) = try await stream(request("/api/discover/search/stream", query: query))
        guard let http = response as? HTTPURLResponse else { throw BackendError.invalidResponse }
        if http.statusCode == 404 {
            // A server from before the stream: every museum's works at once.
            bytes.task.cancel()
            let found = try await searchMuseums(rules, sources: sources, page: page)
            let answer = MuseumAnswer(
                source: sources.count == 1 ? sources[0] : "all", total: found.total, items: found.items,
                failed: found.failed, next: found.items.isEmpty ? nil : page + 1
            )
            return AsyncThrowingStream { continuation in
                continuation.yield(answer)
                continuation.finish()
            }
        }
        guard (200 ..< 300).contains(http.statusCode) else {
            bytes.task.cancel()
            throw BackendError.http(status: http.statusCode, body: "")
        }
        let mark = Absence.shared.mark()
        return AsyncThrowingStream { continuation in
            let reading = Task {
                do {
                    let decoder = Self.decoder()
                    for try await line in bytes.lines where !line.isEmpty {
                        continuation.yield(try decoder.decode(MuseumAnswer.self, from: Data(line.utf8)))
                    }
                    continuation.finish()
                } catch where Absence.shared.interrupted(error, since: mark) {
                    continuation.finish()  // the app went away mid-answer: what came is kept
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in reading.cancel() }
        }
    }

    private func museumQuery(_ rules: PlaylistRules, sources: [String], page: Int) -> [URLQueryItem] {
        var query = [
            URLQueryItem(name: "q", value: rules.query),
            URLQueryItem(name: "page", value: String(page)),
        ]
        query += sources.map { URLQueryItem(name: "source", value: $0) }
        query += rules.artists.map { URLQueryItem(name: "artist", value: $0) }
        query += rules.terms.map { URLQueryItem(name: "term", value: $0) }
        query += rules.colors.map { URLQueryItem(name: "color", value: $0) }
        if let from = rules.yearFrom { query.append(URLQueryItem(name: "year_from", value: String(from))) }
        if let to = rules.yearTo { query.append(URLQueryItem(name: "year_to", value: String(to))) }
        return query
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

    private struct FillBody: Encodable {
        let rules: PlaylistRules
        let count: Int
    }

    func fillLibrary(rules: PlaylistRules, count: Int) async throws -> String {
        let ref: JobRef = try await send(
            "/api/library/fill", method: "POST", body: FillBody(rules: rules, count: count)
        )
        return ref.jobId
    }

    func job(id: String) async throws -> JobStatus { try await get("/api/jobs/\(id)") }

    // MARK: Album

    func checkAlbum(url: String) async throws -> AlbumCheck {
        try await send("/api/albums/check", method: "POST", body: ["url": url])
    }

    func syncAlbum(playlistID: Int) async throws -> String {
        let ref: JobRef = try await send("/api/playlists/\(playlistID)/sync", method: "POST")
        return ref.jobId
    }

    // MARK: Device

    func uploadPhoto(_ upload: PhotoUpload) async throws -> Item {
        var form = MultipartForm()
        form.addField("kind", "photo")
        form.addField("title", upload.title)
        if let takenAt = upload.takenAt { form.addField("taken_at", takenAt) }
        if let latitude = upload.latitude, let longitude = upload.longitude {
            form.addField("latitude", String(latitude))
            form.addField("longitude", String(longitude))
        }
        if let look = upload.look, let json = try? Self.encoder().encode(look) {
            form.addField("look", String(decoding: json, as: UTF8.self))
        }
        form.addFile("file", filename: "photo.jpg", mimeType: "image/jpeg", data: upload.data)
        var req = request("/api/library/upload", method: "POST")
        req.setValue(form.contentType, forHTTPHeaderField: "Content-Type")
        req.httpBody = form.body()
        req.timeoutInterval = 120
        return try await perform(req)
    }

    func panelConfig() async throws -> PanelConfig { try await get("/api/device/config") }

    func savePanelConfig(_ update: PanelConfigUpdate) async throws -> PanelConfig {
        try await send("/api/device/config", method: "PUT", body: update)
    }

    func resetPanelConfig() async throws -> PanelConfig {
        try await send("/api/device/config", method: "DELETE")
    }

    func panelApp() async throws -> PanelAppView { try await get("/api/device/app") }

    func installPanelApp() async throws -> PanelAppView {
        // A sleeping panel is woken first (one to three minutes on battery).
        var req = request("/api/device/app/install", method: "POST")
        req.timeoutInterval = 240
        return try await perform(req)
    }

    func libraryStorage() async throws -> LibraryStorage { try await get("/api/library/storage") }

    func saveLibraryLimits(_ update: LibraryStorageUpdate) async throws -> LibraryStorage {
        try await send("/api/library/storage", method: "PUT", body: update)
    }

    func serverUpdate() async throws -> ServerUpdate { try await get("/api/server/update") }

    func checkServerUpdate() async throws -> ServerUpdate {
        try await send("/api/server/update/check", method: "POST")
    }

    func updateServer() async throws -> ServerUpdate {
        try await send("/api/server/update", method: "POST")
    }

    func notifications(device: String?) async throws -> NotificationSettings {
        try await get("/api/notifications", query: device.map { [URLQueryItem(name: "device", value: $0)] } ?? [])
    }

    func registerPush(token: String, _ update: PushDeviceUpdate) async throws -> NotificationSettings {
        try await send("/api/notifications/devices/\(escape(token))", method: "PUT", body: update)
    }

    func uploadPushKey(filename: String, data: Data, device: String?) async throws -> NotificationSettings {
        var form = MultipartForm()
        if let device { form.addField("device", device) }
        form.addFile("file", filename: filename, mimeType: "application/octet-stream", data: data)
        var req = request("/api/notifications/key", method: "PUT")
        req.setValue(form.contentType, forHTTPHeaderField: "Content-Type")
        req.httpBody = form.body()
        return try await perform(req)
    }

    func deletePushKey(device: String?) async throws -> NotificationSettings {
        try await perform(request(
            "/api/notifications/key", method: "DELETE",
            query: device.map { [URLQueryItem(name: "device", value: $0)] } ?? []
        ))
    }

    func testPush(device: String) async throws -> PushTestResult {
        try await send("/api/notifications/test", method: "POST", body: PushTestRequest(device: device))
    }

    func aiSettings() async throws -> AiSettings { try await get("/api/ai") }

    // MARK: People

    func me() async throws -> Me { try await get("/api/me") }
    func leave() async throws { try await send("/api/me/device", method: "DELETE") }
    func people() async throws -> People { try await get("/api/users") }

    func invite(_ request: InviteRequest) async throws -> NewInvite {
        try await send("/api/users/invites", method: "POST", body: request)
    }

    func cancelInvite(id: String) async throws -> People {
        try await send("/api/users/invites/\(escape(id))", method: "DELETE")
    }

    func removeDevice(id: String) async throws -> People {
        try await send("/api/users/devices/\(escape(id))", method: "DELETE")
    }

    func removePerson(id: String) async throws -> People {
        try await send("/api/users/\(escape(id))", method: "DELETE")
    }

    func renamePerson(id: String, name: String) async throws -> People {
        try await send("/api/users/\(escape(id))", method: "PUT", body: PersonRename(name: name))
    }

    func savePeopleSettings(_ settings: PeopleSettings) async throws -> People {
        try await send("/api/users/settings", method: "PUT", body: settings)
    }

    /// An invitation redeemed (no token yet: the code is the proof).
    func join(code: String, device: String) async throws -> Joined {
        try await send("/api/join", method: "POST", body: JoinRequest(code: code, device: device))
    }

    func saveAiSettings(_ update: AiSettingsUpdate) async throws -> AiSettings {
        try await send("/api/ai", method: "PUT", body: update)
    }

    func saveAiKey(_ key: String) async throws -> AiSettings {
        try await send("/api/ai/key", method: "PUT", body: AiKeyUpdate(key: key))
    }

    func deleteAiKey() async throws -> AiSettings { try await send("/api/ai/key", method: "DELETE") }

    func sourceKeys() async throws -> [SourceKey] { try await get("/api/sources/keys") }

    func saveSourceKey(_ source: String, key: String) async throws -> [SourceKey] {
        try await send("/api/sources/keys/\(source)", method: "PUT", body: AiKeyUpdate(key: key))
    }

    func deleteSourceKey(_ source: String) async throws -> [SourceKey] {
        try await send("/api/sources/keys/\(source)", method: "DELETE")
    }

    func keywordsEstimate() async throws -> AiEstimate { try await get("/api/ai/keywords/estimate") }

    func describeLibrary() async throws -> AiStarted {
        try await send("/api/ai/keywords/describe-library", method: "POST")
    }

    func wake(sleepAfter: Bool) async throws -> WakeResult {
        // The server sends magic packets for a while and then looks for the
        // panel (on battery it answers one to three minutes in).
        let query = sleepAfter ? [URLQueryItem(name: "sleep_after", value: "true")] : []
        var req = request("/api/device/wake", method: "POST", query: query)
        req.timeoutInterval = 240
        return try await perform(req)
    }

    func pushAgain() async throws -> DisplayResponse {
        // The server waits up to two minutes for the panel's download.
        var req = request("/api/device/push", method: "POST", query: [URLQueryItem(name: "wait", value: "120")])
        req.timeoutInterval = 180
        return try await perform(req)
    }

    func sleep() async throws { try await send("/api/device/sleep", method: "POST") }

    func restart() async throws -> WakeResult {
        // Like "Obudź ramkę": magic packets for up to three minutes first.
        var req = request("/api/device/restart", method: "POST")
        req.timeoutInterval = 240
        return try await perform(req)
    }

    func rest(hours: Int?) async throws -> RestResult {
        let query = hours.map { [URLQueryItem(name: "hours", value: String($0))] }
            ?? [URLQueryItem(name: "off", value: "true")]
        return try await perform(request("/api/device/sleep", method: "POST", query: query))
    }

    // MARK: Images

    func request(for image: ImageRef) -> URLRequest? {
        var req: URLRequest
        switch image {
        case let .thumb(id): req = request("/api/library/items/\(escape(id))/thumb")
        case let .image(id): req = request("/api/library/items/\(escape(id))/image")
        case let .original(id, version):
            req = request("/api/library/items/\(escape(id))/image", query: [URLQueryItem(name: "v", value: version)])
        case let .framePreview(id, settings, framing, ownLook):
            var query = framingQuery(settings)
            if !ownLook { query.append(URLQueryItem(name: "own_look", value: "false")) }
            let encoder = Self.encoder()
            encoder.outputFormatting = .sortedKeys
            if let framing, let data = try? encoder.encode(framing) {
                query.append(URLQueryItem(name: "framing", value: String(decoding: data, as: UTF8.self)))
            }
            req = request("/api/library/items/\(escape(id))/preview", query: query)
        case let .path(path):
            // A query ("?n=0&v=…") goes as the query, not into the path.
            let parts = path.split(separator: "?", maxSplits: 1).map(String.init)
            let query = parts.count > 1 ? URLComponents(string: "?" + parts[1])?.queryItems ?? [] : []
            req = request(parts.first ?? path, query: query)
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
        let (data, response) = try await load(req)
        guard let http = response as? HTTPURLResponse else { throw BackendError.invalidResponse }
        guard (200 ..< 300).contains(http.statusCode) else {
            throw BackendError.http(status: http.statusCode, body: String(decoding: data, as: UTF8.self))
        }
        if T.self == EmptyResponse.self { return EmptyResponse() as! T }  // swiftlint:disable:this force_cast
        return try Self.decoder().decode(T.self, from: data)
    }

    /// Sends the request. One cut short by the app going away (or sent as
    /// it came back, before the network woke up) goes again once the app
    /// is back, if nothing can happen twice; otherwise it ends as
    /// `BackendError.interrupted`, not as a server that did not answer.
    private func load(_ req: URLRequest) async throws -> (Data, URLResponse) {
        try await again(req) { try await reach($0) { try await URLSession.shared.data(for: $0) } }
    }

    /// Like `load`, for a response read as it comes.
    private func stream(_ req: URLRequest) async throws -> (URLSession.AsyncBytes, URLResponse) {
        try await again(req) { try await reach($0) { try await URLSession.shared.bytes(for: $0) } }
    }

    private func again<T>(_ req: URLRequest, _ send: (URLRequest) async throws -> T) async throws -> T {
        var retries = 0
        while true {
            let mark = Absence.shared.mark()
            do {
                return try await send(req)
            } catch let error as URLError where Absence.shared.interrupted(error, since: mark) {
                guard req.httpMethod == "GET" || ServerRoute.neverArrived(error) else { throw BackendError.interrupted }
                guard retries < 2 else { throw error }
                retries += 1
                await Absence.shared.whenBack(pause: Double(retries))
                try Task.checkCancellation()
            }
        }
    }

    /// When the address in use does not answer (left home, or came back),
    /// finds the one that does and, if nothing can happen twice, sends the
    /// request there once more.
    private func reach<T>(_ req: URLRequest, _ send: (URLRequest) async throws -> T) async throws -> T {
        do {
            return try await send(req)
        } catch let error as URLError where route.hasRemote && ServerRoute.unreachable(error) {
            guard await route.resolve() != nil,
                  req.httpMethod == "GET" || ServerRoute.neverArrived(error),
                  let moved = route.rebased(req)
            else { throw error }
            return try await send(moved)
        }
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
