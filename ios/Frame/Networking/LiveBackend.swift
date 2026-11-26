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

    /// Connections of their own for the requests that wait at the server.
    /// A work's card asks who holds it, for its technique, a sharper copy,
    /// its description and its Polish title at once, each waiting up to
    /// half a minute, and the shared session has four connections to the
    /// server: a heart or "Pokaż na ramce" tapped meanwhile stood behind
    /// them (the audit of 2026-11-14).
    private static let patient: URLSession = {
        let configuration = URLSessionConfiguration.default
        configuration.httpMaximumConnectionsPerHost = 8
        return URLSession(configuration: configuration)
    }()

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

    /// Short: `AppModel` tries again (and asks for the address anew) when
    /// it does not answer, rather than waiting a minute on one try.
    func health() async throws -> Health {
        var req = request("/api/health")
        req.timeoutInterval = 12
        return try await perform(req)
    }

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
        // "Słowa" put in order of how near works look to the words, which
        // the server reads in English: a phrase translated here first
        // ("parowiec na rzece", Mateusz 2026-11-20: "Tak, zrób proszę.").
        if q.seen, q.offset == 0, q.text.contains(where: \.isWhitespace) { await teach([q.text]) }
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
        query += q.excludeSources.map { URLQueryItem(name: "skip", value: $0) }
        query += q.places.map { URLQueryItem(name: "place", value: $0) }
        query += q.excludePlaces.map { URLQueryItem(name: "skip_place", value: $0) }
        if let from = q.yearFrom { query.append(URLQueryItem(name: "year_from", value: String(from))) }
        if let to = q.yearTo { query.append(URLQueryItem(name: "year_to", value: String(to))) }
        if q.favoritesOnly { query.append(URLQueryItem(name: "favorites", value: "true")) }
        if q.keptOnly { query.append(URLQueryItem(name: "kept", value: "true")) }
        if !q.look.isEmpty { query.append(URLQueryItem(name: "look", value: q.look)) }
        // "Słowa": also the works that show what the words say.
        if q.seen, !q.text.isEmpty { query.append(URLQueryItem(name: "seen", value: "true")) }
        if !q.title.isEmpty { query.append(URLQueryItem(name: "title", value: q.title)) }
        if !q.like.isEmpty { query.append(URLQueryItem(name: "like", value: q.like)) }
        if !q.like.isEmpty, !q.likeBy.isEmpty { query.append(URLQueryItem(name: "like_by", value: q.likeBy)) }
        // "Barwy" beside "Treść" or "Forma".
        if !q.like.isEmpty, q.likeColours, q.likeBy != LikeBy.colours.rawValue {
            query.append(URLQueryItem(name: "like_colours", value: "true"))
        }
        if !q.like.isEmpty, q.likeFurther > 0 {
            query.append(URLQueryItem(name: "like_further", value: String(q.likeFurther)))
        }
        if let playlist = q.playlist { query.append(URLQueryItem(name: "playlist", value: String(playlist))) }
        if q.playlist != nil, !q.typed.isEmpty { query.append(URLQueryItem(name: "typed", value: q.typed)) }
        return try await get("/api/library/items", query: query)
    }

    func item(id: String) async throws -> Item { try await get("/api/library/items/\(escape(id))") }

    func hiddenItems() async throws -> ItemPage { try await get("/api/library/hidden") }

    func polish(itemID: String, wait: Int, early: Bool) async throws -> PolishView {
        var query = [URLQueryItem(name: "wait", value: String(wait))]
        if early { query.append(URLQueryItem(name: "early", value: "true")) }
        return try await perform(request("/api/library/items/\(escape(itemID))/polish", query: query), patient: true)
    }

    func holder(itemID: String, wait: Int) async throws -> HolderView {
        var req = request(
            "/api/library/items/\(escape(itemID))/holder", method: "POST",
            query: [URLQueryItem(name: "wait", value: String(wait))]
        )
        req.timeoutInterval = TimeInterval(wait + 30)
        return try await perform(req, patient: true)
    }

    func recovery(itemID: String, made: String) async throws -> RecoveryView {
        var req = request(
            "/api/library/items/\(escape(itemID))/recovery",
            query: [URLQueryItem(name: "made", value: made)]
        )
        req.timeoutInterval = 60
        return try await perform(req, patient: true)
    }

    func colours(itemID: String, made: String) async throws -> ColoursView {
        var req = request(
            "/api/library/items/\(escape(itemID))/colours",
            query: [URLQueryItem(name: "made", value: made)]
        )
        req.timeoutInterval = 60
        return try await perform(req, patient: true)
    }

    func clean(itemID: String, made: String) async throws -> Item {
        // The original is made again from the museum's photograph and its
        // colours measured: seconds on a NAS, more when it is downloaded first.
        var req = request(
            "/api/library/items/\(escape(itemID))/cleaned", method: "PUT",
            query: [URLQueryItem(name: "made", value: made)]
        )
        req.timeoutInterval = 120
        return try await perform(req)
    }

    func unclean(itemID: String) async throws -> Item {
        var req = request("/api/library/items/\(escape(itemID))/cleaned", method: "DELETE")
        req.timeoutInterval = 120
        return try await perform(req)
    }

    func medium(itemID: String, wait: Int) async throws -> MediumView {
        var req = request(
            "/api/library/items/\(escape(itemID))/medium", method: "POST",
            query: [URLQueryItem(name: "wait", value: String(wait))]
        )
        req.timeoutInterval = TimeInterval(wait + 30)
        return try await perform(req, patient: true)
    }

    func fragments(itemID: String) async throws -> FragmentsView {
        var req = request("/api/library/items/\(escape(itemID))/fragments")
        req.timeoutInterval = 60  // the museum may be asked first
        return try await perform(req, patient: true)
    }

    func details(itemID: String) async throws -> DetailsView {
        var req = request("/api/library/items/\(escape(itemID))/details")
        req.timeoutInterval = 60  // the museum may be asked first
        return try await perform(req, patient: true)
    }

    func sharpen(itemID: String, wait: Int) async throws -> SharperView {
        var req = request(
            "/api/library/items/\(escape(itemID))/sharpen", method: "POST",
            query: [URLQueryItem(name: "wait", value: String(wait))]
        )
        req.timeoutInterval = TimeInterval(wait + 30)
        return try await perform(req, patient: true)
    }

    func setCut(itemID: String, update: CutUpdate) async throws -> Item {
        var req = request("/api/library/items/\(escape(itemID))/cut", method: "PUT")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try Self.encoder().encode(update)
        req.timeoutInterval = 120
        return try await perform(req)
    }

    func removeCut(itemID: String) async throws -> Item {
        try await send("/api/library/items/\(escape(itemID))/cut", method: "DELETE")
    }

    func copies(itemID: String) async throws -> AsyncThrowingStream<CopyLine, Error> {
        var req = request("/api/library/items/\(escape(itemID))/copies")
        req.timeoutInterval = 120
        let (bytes, response) = try await stream(req)
        guard let http = response as? HTTPURLResponse else { throw BackendError.invalidResponse }
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
                        continuation.yield(try decoder.decode(CopyLine.self, from: Data(line.utf8)))
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

    func chooseCopy(itemID: String, copyID: String) async throws -> Item {
        var req = request("/api/library/items/\(escape(itemID))/copy", method: "PUT")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try Self.encoder().encode(["item_id": copyID])
        req.timeoutInterval = 120  // the copy is downloaded first
        return try await perform(req)
    }

    func copySpot(itemID: String, copyID: String, x: Double?, y: Double?) async throws -> CopySpot {
        var query: [URLQueryItem] = []
        if let x, let y {
            query = [URLQueryItem(name: "x", value: String(x)), URLQueryItem(name: "y", value: String(y))]
        }
        var req = request("/api/library/items/\(escape(itemID))/copies/\(escape(copyID))/spot", query: query)
        req.timeoutInterval = 120
        return try await perform(req)
    }

    func describe(itemID: String, wait: Int) async throws -> SeenView {
        var req = request(
            "/api/library/items/\(escape(itemID))/describe", method: "POST",
            query: [URLQueryItem(name: "wait", value: String(wait))]
        )
        req.timeoutInterval = TimeInterval(wait + 30)
        return try await perform(req, patient: true)
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

    func framing(itemID: String, orientation: String, automatic: Bool) async throws -> FramingView {
        var query = [URLQueryItem(name: "orientation", value: orientation)]
        if automatic { query.append(URLQueryItem(name: "automatic", value: "true")) }
        return try await get("/api/library/items/\(escape(itemID))/framing", query: query)
    }

    func board(itemID: String, settings: FrameSettings, ownLook: Bool) async throws -> PhotoBoard {
        var query = framingQuery(settings)
        if !ownLook {
            query.append(URLQueryItem(name: "own_look", value: "false"))
            query += multiPhotosQuery(settings)
        }
        return try await get("/api/library/items/\(escape(itemID))/board", query: query)
    }

    /// Prezentacja (a preview without the photo's own look) tries Multi
    /// grids on the photos the owner chose for it.
    private func multiPhotosQuery(_ settings: FrameSettings?) -> [URLQueryItem] {
        guard let settings, settings.photo.fit == "multi", let photos = settings.multiPhotos, !photos.isEmpty
        else { return [] }
        return [URLQueryItem(name: "photos", value: photos.joined(separator: ","))]
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

    func arrangePlaylists(ids: [Int]) async throws -> [PlaylistSummary] {
        try await send("/api/playlists/order", method: "PUT", body: ["ids": ids])
    }

    func playlistOrder() async throws -> [Int] {
        let order: [String: [Int]] = try await get("/api/playlists/order")
        return order["ids"] ?? []
    }

    func sortPlaylist(id: Int, sort: PlaylistSort) async throws -> PlaylistDetail {
        try await send("/api/playlists/\(id)/sort", method: "PUT", body: sort)
    }

    func addToPlaylist(id: Int, itemIDs: [String]) async throws -> PlaylistDetail {
        try await send("/api/playlists/\(id)/items", method: "POST", body: ["item_ids": itemIDs])
    }

    func removeFromPlaylist(id: Int, itemID: String) async throws -> PlaylistDetail {
        try await send("/api/playlists/\(id)/items/\(escape(itemID))", method: "DELETE")
    }

    func playlistsHolding(itemID: String) async throws -> [PlaylistHolding] {
        try await get("/api/items/\(escape(itemID))/playlists")
    }

    func play(playlistID: Int) async throws { try await send("/api/playlists/\(playlistID)/play", method: "POST") }

    func playSuggestions() async throws { try await send("/api/suggestions/play", method: "POST") }
    func playOwnWorks() async throws { try await send("/api/own/play", method: "POST") }
    func daySuggestions() async throws -> DayPicks { try await get("/api/suggestions/day") }
    func gallery(count: Int) async throws -> [RemoteItem] {
        try await get("/api/gallery", query: [URLQueryItem(name: "count", value: String(count))])
    }

    // MARK: Settings

    func settings() async throws -> FrameSettings { try await get("/api/settings") }

    func saveSettings(_ settings: FrameSettings) async throws -> FrameSettings {
        try await send("/api/settings", method: "PUT", body: settings)
    }

    // MARK: Discover

    /// Worked out from the whole catalogue: right after the server started
    /// it may take a minute or more (the search index is being made). On
    /// the waits' connections, so that "Teraz" and the playlists asked
    /// meanwhile do not stand behind them (2026-11-14: six of these held
    /// the shared four connections for minutes after an update).
    /// Given three minutes, not one: asked again after a minute, the server
    /// worked them out once more for nobody.
    func suggestions() async throws -> [SuggestionRow] {
        var req = request("/api/suggestions")
        req.timeoutInterval = 180
        return try await perform(req, patient: true)
    }

    func themes() async throws -> [ArtTheme] {
        var req = request("/api/themes")
        req.timeoutInterval = 180
        return try await perform(req, patient: true)
    }

    func dailyAgain() async throws -> DailyWork.Brief { try await send("/api/daily/again", method: "POST") }

    func weekArtistAgain() async throws -> ArtTheme { try await send("/api/themes/week-artist/again", method: "POST") }

    func daily(day: String?, wait: Int, lists: Bool) async throws -> DailyWork {
        var query = [URLQueryItem(name: "wait", value: String(wait))]
        if let day { query.append(URLQueryItem(name: "day", value: day)) }
        if !lists { query.append(URLQueryItem(name: "lists", value: "false")) }
        var req = request("/api/daily", query: query)
        req.timeoutInterval = TimeInterval(wait + 30)
        return try await perform(req, patient: true)
    }

    func study(itemID: String, wait: Int, lists: Bool) async throws -> StudyView {
        var query = [URLQueryItem(name: "wait", value: String(wait))]
        if !lists { query.append(URLQueryItem(name: "lists", value: "false")) }
        var req = request("/api/study/\(escape(itemID))", query: query)
        req.timeoutInterval = TimeInterval(wait + 30)
        return try await perform(req, patient: true)
    }

    func studies() async throws -> [StudyBrief] { try await get("/api/studies") }

    func prepareStudy(itemID: String, again: Bool, later: Bool) async throws -> StudyView {
        var query: [URLQueryItem] = []
        if again { query.append(URLQueryItem(name: "again", value: "true")) }
        if later { query.append(URLQueryItem(name: "later", value: "true")) }
        return try await perform(request("/api/study/\(escape(itemID))", method: "POST", query: query))
    }

    func compositionAgain(itemID: String) async throws -> CompositionAgain {
        try await send("/api/study/\(escape(itemID))/composition", method: "POST")
    }

    func compositionState(itemID: String) async throws -> CompositionAgain {
        try await get("/api/study/\(escape(itemID))/composition")
    }

    func pickComposition(itemID: String, shown: Int) async throws -> CompositionAgain {
        try await send(
            "/api/study/\(escape(itemID))/composition", method: "PUT", body: CompositionPick(shown: shown)
        )
    }

    func detailsAgain(itemID: String) async throws -> DetailsAgain {
        try await send("/api/study/\(escape(itemID))/details", method: "POST")
    }

    func detailsState(itemID: String) async throws -> DetailsAgain {
        try await get("/api/study/\(escape(itemID))/details")
    }

    func followStudy(itemID: String, activityToken: String, sandbox: Bool) async throws {
        try await send(
            "/api/study/\(escape(itemID))/activity", method: "PUT",
            body: StudyActivityToken(token: activityToken, sandbox: sandbox)
        )
    }

    func followSend(title: String, activityToken: String, sandbox: Bool) async throws {
        try await send(
            "/api/notifications/send-activity", method: "PUT",
            body: SendActivityToken(token: activityToken, title: title, sandbox: sandbox)
        )
    }

    func themePage(key: String, page: Int) async throws -> ArtThemePage {
        try await get("/api/themes/\(key)", query: [URLQueryItem(name: "page", value: String(page))])
    }

    func themeLines(key: String, page: Int) async throws -> AsyncThrowingStream<ThemeLine, Error> {
        let query = [URLQueryItem(name: "page", value: String(page))]
        let (bytes, response) = try await stream(request("/api/themes/\(key)/stream", query: query))
        guard let http = response as? HTTPURLResponse else { throw BackendError.invalidResponse }
        if http.statusCode == 404 {
            // A server from before the stream (or a theme that is gone): a page at once.
            bytes.task.cancel()
            let found = try await themePage(key: key, page: page)
            let lines = [
                ThemeLine(items: found.items),
                ThemeLine(end: true, more: found.more, nextPage: found.nextPage ?? page + 1),
            ]
            return AsyncThrowingStream { continuation in
                for line in lines { continuation.yield(line) }
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
                        continuation.yield(try decoder.decode(ThemeLine.self, from: Data(line.utf8)))
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

    func themePlaylist(key: String, play: Bool) async throws -> ThemePlaylist {
        try await send("/api/themes/\(key)/playlist", method: "POST", body: ["play": play])
    }

    func vocabulary() async throws -> [TermInfo] { try await get("/api/vocabulary") }

    func terms(_ text: String, playlist: Int?) async throws -> [TermHit] {
        // While typing: a phrase's translation sent ahead, not waited for
        // (the server asks for how its words look as they are suggested).
        // Not halfway through a word ("taniec n"): the server translates
        // none such either (`TRANSLATED_FROM`).
        if text.contains(where: \.isWhitespace),
           (text.split(whereSeparator: \.isWhitespace).last?.count ?? 0) >= 3 {
            let phrase = text
            Task { await self.teach([phrase]) }
        }
        var query = [URLQueryItem(name: "q", value: text)]
        if let playlist { query.append(URLQueryItem(name: "playlist", value: String(playlist))) }
        return try await get("/api/terms", query: query)
    }

    func looksStatus() async throws -> LooksStatus { try await get("/api/looks") }

    func lookPhoto(_ picture: Data) async throws -> LooksPhoto {
        if let numbered = await phoneNumbered(picture) { return numbered }
        var form = MultipartForm()
        form.addFile("file", filename: "photo.jpg", mimeType: "image/jpeg", data: picture)
        var req = request("/api/looks/photo", method: "POST")
        req.setValue(form.contentType, forHTTPHeaderField: "Content-Type")
        req.httpBody = form.body()
        req.timeoutInterval = 60
        return try await perform(req)
    }

    /// The photograph numbered on the phone (`PhoneLook`), only its numbers
    /// sent; nil when it cannot be: a server from before it, Google's numbers
    /// answering there, the model not here yet (fetched meanwhile).
    private func phoneNumbered(_ picture: Data) async -> LooksPhoto? {
        guard let status: PhoneLook.Status = try? await get("/api/looks/phone"),
              let numbers = await PhoneLook.shared.numbers(picture, status: status, fetch: { [self] in
                  try await self.phoneModel()
              })
        else { return nil }
        struct Numbers: Encodable { var model: String; var look: String; var palette: [[Float]]? }
        // Its colours too, for "Barwy" (made here, Mateusz 2026-11-21).
        let palette = PhonePalette.colours(picture)
        return try? await send(
            "/api/looks/photo/numbers", method: "POST",
            body: Numbers(model: status.model, look: PhoneLook.encoded(numbers), palette: palette)
        )
    }

    /// The phone's look model's tar, fetched into a file of its own.
    private func phoneModel() async throws -> URL {
        var req = request("/api/looks/phone/model")
        req.timeoutInterval = 120
        let kept = FileManager.default.temporaryDirectory.appending(path: "PhoneLook-\(UUID().uuidString).tar")
        let status = try await route.follow(req) { req in
            try await Tailnet.shared.send(req) { session in
                let (file, response) = try await session.download(for: req)
                try FileManager.default.moveItem(at: file, to: kept)
                return (response as? HTTPURLResponse)?.statusCode ?? 200
            }
        }
        guard (200 ..< 300).contains(status) else {
            try? FileManager.default.removeItem(at: kept)
            throw BackendError.http(status: status, body: "")
        }
        return kept
    }

    func looksLike(itemID: String, limit: Int) async throws -> LooksAnswer {
        try await get(
            "/api/library/items/\(escape(itemID))/looks",
            query: [URLQueryItem(name: "limit", value: String(limit))]
        )
    }

    func museumHint(_ text: String) async throws -> MuseumHint {
        await teach([text])
        return try await get("/api/terms/museums", query: [URLQueryItem(name: "q", value: text)])
    }

    func searchMuseums(_ rules: PlaylistRules, sources: [String], page: Int) async throws -> RemotePage {
        await teach(SearchPhrases.tokens(Self.museumWords(rules).words))
        return try await get("/api/discover/search", query: museumQuery(rules, sources: sources, page: page))
    }

    /// Polish words of `phrases` translated on the phone (`PhoneWords`) and
    /// sent before the search that asks for them; waited for at most
    /// `PhoneWords.patience`, a later translation still goes for the next
    /// search. A server from before it answers 404: nothing changes.
    private func teach(_ phrases: [String]) async {
        let phrases = phrases.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
        guard !phrases.isEmpty else { return }
        let backend = self
        let sending = Task {
            let words = await PhoneWords.shared.translated(phrases)
            guard !words.isEmpty else { return }
            let _: EmptyResponse? = try? await backend.send("/api/search/words", method: "POST", body: TaughtWords(words: words))
        }
        await withTaskGroup(of: Void.self) { group in
            group.addTask { await sending.value }
            group.addTask { try? await Task.sleep(for: PhoneWords.patience) }
            await group.next()
            group.cancelAll()
        }
    }

    private struct TaughtWords: Encodable { let words: [PhoneWords.Word] }

    func museumAnswers(_ rules: PlaylistRules, sources: [String], page: Int) async throws
        -> AsyncThrowingStream<MuseumAnswer, Error>
    {
        if page <= 1 { await teach(SearchPhrases.tokens(Self.museumWords(rules).words)) }
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
        let (words, look) = Self.museumWords(rules)
        var query = [
            URLQueryItem(name: "q", value: words),
            URLQueryItem(name: "page", value: String(page)),
        ]
        query += sources.map { URLQueryItem(name: "source", value: $0) }
        query += rules.excludeSources.map { URLQueryItem(name: "skip", value: $0) }
        query += rules.places.map { URLQueryItem(name: "place", value: $0) }
        query += rules.excludePlaces.map { URLQueryItem(name: "skip_place", value: $0) }
        query += rules.artists.map { URLQueryItem(name: "artist", value: $0) }
        query += rules.terms.map { URLQueryItem(name: "term", value: $0) }
        query += rules.colors.map { URLQueryItem(name: "color", value: $0) }
        if let from = rules.yearFrom { query.append(URLQueryItem(name: "year_from", value: String(from))) }
        if let to = rules.yearTo { query.append(URLQueryItem(name: "year_to", value: String(to))) }
        // A title asked by its words; a look by searches Haiku makes of
        // it, what the museums bring judged by how it looks (2026-11-13).
        if !rules.title.isEmpty { query.append(URLQueryItem(name: "title", value: rules.title)) }
        if !look.isEmpty {
            query.append(URLQueryItem(name: "look", value: look))
        } else if SearchToken.isPhoto(rules.like) {
            // A photograph searched: its key is the look, the server asks
            // the museums by its nearest works' subjects (2026-11-21).
            query.append(URLQueryItem(name: "look", value: rules.like))
        }
        return query
    }

    /// The museums' words and look: "Słowa" of two words or more are asked
    /// as a look was ("mglisty poranek": searches Haiku makes of them, what
    /// the museums bring judged by how it looks), one word as it is
    /// (Mateusz 2026-11-19).
    static func museumWords(_ rules: PlaylistRules) -> (words: String, look: String) {
        let phrases = SearchPhrases.tokens(rules.query)
        let count = phrases.reduce(0) { $0 + $1.split(whereSeparator: \.isWhitespace).count }
        guard rules.seen, rules.look.isEmpty, rules.title.isEmpty, count >= 2 else { return (rules.query, rules.look) }
        return ("", phrases.joined(separator: " "))
    }

    // MARK: Museums

    func museums() async throws -> [Museum] { try await get("/api/museums") }

    func places(query: String) async throws -> [PlaceHit] {
        try await get("/api/places", query: [URLQueryItem(name: "q", value: query)])
    }

    func placePicture(key: String) async throws -> PlacePicture {
        let path = key.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/"))) ?? key
        return try await get("/api/places/\(path)/picture")
    }

    func importArtwork(source: String, sourceID: String) async throws -> Item {
        try await send("/api/museums/\(source)/import", method: "POST", body: ["source_id": sourceID])
    }

    private struct JobRef: Decodable { let jobId: String }

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

    func sendOwnPhoto(_ data: Data, lens: OwnLens?) async throws -> OwnIncoming {
        var form = MultipartForm()
        form.addFile("file", filename: "photo.jpg", mimeType: "image/jpeg", data: data)
        if let told = lens?.told { form.addField("lens", told) }
        var req = request("/api/own/photos", method: "POST")
        req.setValue(form.contentType, forHTTPHeaderField: "Content-Type")
        req.httpBody = form.body()
        req.timeoutInterval = 120
        return try await perform(req)
    }

    func findOwnWork(token: String) async throws -> OwnIncoming {
        var req = request("/api/own/photos/\(escape(token))/find", method: "POST")
        req.timeoutInterval = 120
        return try await perform(req)
    }

    func ownFound(token: String, corners: [[Double]]?, surround: [[Double]]?, owner: Bool) async throws {
        var body: [String: Any] = ["owner": owner]
        if let corners { body["corners"] = corners }
        if let surround { body["surround"] = surround }
        var req = request("/api/own/photos/\(escape(token))/found", method: "POST")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let _: OwnIncoming = try await perform(req)
    }

    func sendOwnSide(token: String, _ data: Data, angle: Double?) async throws {
        var form = MultipartForm()
        form.addFile("file", filename: "side.jpg", mimeType: "image/jpeg", data: data)
        var query: [URLQueryItem] = []
        if let angle, angle.isFinite {
            // (The server takes -90…90.)
            let within = max(-90, min(90, angle))
            query.append(URLQueryItem(name: "angle", value: String(format: "%.1f", locale: Locale(identifier: "en_US_POSIX"), within)))
        }
        var req = request("/api/own/photos/\(escape(token))/sides", method: "POST", query: query)
        req.setValue(form.contentType, forHTTPHeaderField: "Content-Type")
        req.httpBody = form.body()
        req.timeoutInterval = 120
        let _: [String: Int] = try await perform(req)
    }

    func mergeOwnPhotos(token: String, outline: [[Double]]?, trace: [String: Double]) async throws -> OwnMerged {
        var req = request("/api/own/photos/\(escape(token))/merge", method: "POST")
        // He is given the two to choose between: the scan is made also of
        // a work that is no flat one, and comes in doubt.
        var ask: [String: Any] = ["choice": true]
        // What the camera followed: where the work is when the model has no answer.
        if let outline { ask["outline"] = outline }
        let noted = trace.filter { $0.value.isFinite }
        if !noted.isEmpty { ask["trace"] = noted }
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: ask)
        req.timeoutInterval = 180
        return try await perform(req)
    }

    func sendOwnScan(token: String, note: Data, picture: Data?) async throws -> OwnMerged {
        var form = MultipartForm()
        form.addField("note", String(decoding: note, as: UTF8.self))
        if let picture { form.addFile("file", filename: "scan.jpg", mimeType: "image/jpeg", data: picture) }
        var req = request("/api/own/photos/\(escape(token))/merged", method: "POST")
        req.setValue(form.contentType, forHTTPHeaderField: "Content-Type")
        req.httpBody = form.body()
        req.timeoutInterval = 180
        return try await perform(req)
    }

    func ownChartTables(token: String) async throws -> Data {
        var req = request("/api/own/photos/\(escape(token))/chart")
        req.timeoutInterval = 60
        let (data, response) = try await load(req)
        guard let http = response as? HTTPURLResponse else { throw BackendError.invalidResponse }
        guard (200 ..< 300).contains(http.statusCode) else {
            throw BackendError.http(status: http.statusCode, body: String(decoding: data, as: UTF8.self))
        }
        return data
    }

    func keepOwnFirstPhoto(token: String) async throws {
        try await send("/api/own/photos/\(escape(token))/single", method: "POST")
    }

    func fine(itemID: String) async throws -> FineView {
        try await perform(request("/api/library/items/\(escape(itemID))/fine"))
    }

    func ownPhoto(token: String, side: Int) async throws -> Data {
        var req = request("/api/own/photos/\(escape(token))", query: [URLQueryItem(name: "side", value: String(side))])
        req.timeoutInterval = 120
        let (data, response) = try await load(req)
        guard let http = response as? HTTPURLResponse else { throw BackendError.invalidResponse }
        guard (200 ..< 300).contains(http.statusCode) else {
            throw BackendError.http(status: http.statusCode, body: String(decoding: data, as: UTF8.self))
        }
        return data
    }

    func ownHints(token: String, corners: [[Double]]?) async throws -> OwnHints {
        var req = request("/api/own/hints", method: "POST")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try Self.encoder().encode(OwnPhotoCut(token: token, corners: corners))
        req.timeoutInterval = 90
        return try await perform(req)
    }

    func addOwnWork(_ work: NewOwnWork) async throws -> Item {
        var req = request("/api/own/works", method: "POST")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try Self.encoder().encode(work)
        req.timeoutInterval = 120
        return try await perform(req)
    }

    func describeOwnWork(itemID: String, _ text: OwnDescription) async throws -> Item {
        try await send("/api/own/works/\(escape(itemID))", method: "PUT", body: text)
    }

    func retakeOwnWork(itemID: String, _ photo: OwnPhotoCut) async throws -> Item {
        var req = request("/api/own/works/\(escape(itemID))/photo", method: "PUT")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try Self.encoder().encode(photo)
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

    func uploadPanelCertificates(_ upload: PanelCertificatesUpload) async throws -> PanelAppView {
        var form = MultipartForm()
        form.addFile("author", filename: "author.p12", mimeType: "application/x-pkcs12", data: upload.author)
        form.addFile("distributor", filename: "distributor.p12", mimeType: "application/x-pkcs12", data: upload.distributor)
        form.addField("password", upload.password)
        if upload.newAuthor { form.addField("new_author", "true") }
        var req = request("/api/device/app/certificates", method: "PUT")
        req.setValue(form.contentType, forHTTPHeaderField: "Content-Type")
        req.httpBody = form.body()
        return try await perform(req)
    }

    func panelScreenshot() async throws -> PanelScreenshot { try await get("/api/device/screenshot") }

    func askPanelScreenshot() async throws -> PanelScreenshot {
        try await send("/api/device/screenshot", method: "POST")
    }

    /// The server looks at every picture for it: on the waits' connections.
    func libraryStorage() async throws -> LibraryStorage {
        try await perform(request("/api/library/storage"), patient: true)
    }

    func sourceRequests() async throws -> SourceRequests { try await get("/api/diagnostics/sources") }

    func keptScans() async throws -> [KeptScan] { try await get("/api/debug/own-scans") }

    /// 48 MP is some 150 MB as it comes: minutes on a slow link.
    func keptScanPixels(token: String, name: String) async throws -> Data {
        var req = request("/api/debug/own-scans/\(escape(token))/\(escape(name))/pixels")
        req.timeoutInterval = 300
        let (data, response) = try await load(req)
        guard let http = response as? HTTPURLResponse else { throw BackendError.invalidResponse }
        guard (200 ..< 300).contains(http.statusCode) else {
            throw BackendError.http(status: http.statusCode, body: String(decoding: data.prefix(2000), as: UTF8.self))
        }
        return data
    }

    func phoneCropAsk(itemID: String) async throws -> PhoneCropAsk {
        try await get("/api/crops/phone/\(escape(itemID))")
    }

    func phoneCropFound(itemID: String, _ found: PhoneCropFound) async throws -> PhoneCropResult {
        // The cut work's pictures are made again before the answer.
        var req = request("/api/crops/phone/\(escape(itemID))", method: "POST")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try Self.encoder().encode(found)
        req.timeoutInterval = 120
        return try await perform(req)
    }

    func museumPhoto(itemID: String, side: Int) async throws -> Data {
        guard var req = request(for: .museumPhoto(itemID, side: side, version: "")) else { throw BackendError.notFound }
        req.timeoutInterval = 120
        let (data, response) = try await load(req)
        guard let http = response as? HTTPURLResponse else { throw BackendError.invalidResponse }
        guard (200 ..< 300).contains(http.statusCode) else {
            throw BackendError.http(status: http.statusCode, body: String(decoding: data.prefix(2000), as: UTF8.self))
        }
        return data
    }

    func cropReview() async throws -> CropReview { try await get("/api/crops/review") }

    func cropFine(itemID: String) async throws -> CropReview {
        try await perform(request("/api/crops/review/\(escape(itemID))/fine", method: "POST"))
    }

    func cropUnfine(itemID: String) async throws -> CropReview {
        try await perform(request("/api/crops/review/\(escape(itemID))/fine", method: "DELETE"))
    }

    func cropTeach(kind: Int, limit: Int) async throws -> CropTeach {
        try await get("/api/crops/teach", query: [
            URLQueryItem(name: "kind", value: String(kind)), URLQueryItem(name: "limit", value: String(limit)),
        ])
    }

    func cropTell(itemID: String, _ answer: CropTeach.Answer?) async throws -> CropTeach {
        guard let answer else {
            return try await perform(request("/api/crops/teach/\(escape(itemID))", method: "DELETE"))
        }
        var req = request("/api/crops/teach/\(escape(itemID))", method: "POST")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(["answer": answer.rawValue])
        return try await perform(req)
    }

    func sendPhoneScan(token: String, name: String, _ data: Data) async throws {
        var req = request("/api/debug/own-scans/\(escape(token))/\(escape(name))", method: "PUT")
        req.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        req.httpBody = data
        req.timeoutInterval = 300
        let _: [String: Int] = try await perform(req)
    }

    func catalogueCounts() async throws -> CatalogueCounts { try await get("/api/library/catalogue") }

    func nightTasks() async throws -> NightTasks { try await get("/api/night") }

    func startNightTasks(_ start: NightStart) async throws -> NightTasks {
        try await send("/api/night/run", method: "POST", body: start)
    }

    func stopNightTasks() async throws -> NightTasks { try await send("/api/night/stop", method: "POST") }

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

    func setAccess(id: String, _ access: PersonAccess) async throws -> People {
        try await send("/api/users/\(escape(id))/access", method: "PUT", body: access)
    }

    /// An invitation redeemed (no token yet: the code is the proof).
    func join(code: String, device: String) async throws -> Joined {
        try await send("/api/join", method: "POST", body: JoinRequest(code: code, device: device))
    }

    func saveAiSettings(_ update: AiSettingsUpdate) async throws -> AiSettings {
        try await send("/api/ai", method: "PUT", body: update)
    }

    func startOnDemand(key: String, usd: Double) async throws -> AiSettings {
        struct Body: Encodable { let key: String; let usd: Double }
        return try await send("/api/ai/on-demand", method: "POST", body: Body(key: key, usd: usd))
    }

    func stopOnDemand(key: String) async throws -> AiSettings {
        try await send("/api/ai/on-demand/\(escape(key))/stop", method: "POST")
    }

    func saveTask(key: String, update: TaskUpdate) async throws -> AiSettings {
        try await send("/api/ai/tasks/\(escape(key))", method: "PUT", body: update)
    }

    func aiReview() async throws -> AiReview { try await get("/api/ai/review") }

    func tidyChanges() async throws -> TidyChanges { try await get("/api/night/changes") }

    func keepApart(_ apart: TidyApart) async throws -> TidyChanges {
        try await send("/api/night/changes/apart", method: "POST", body: apart)
    }

    func bringBack(itemID: String) async throws -> AiReview {
        try await send("/api/ai/review/\(escape(itemID))/bring-back", method: "POST")
    }

    func dismissReview(itemID: String) async throws -> AiReview {
        try await send("/api/ai/review/\(escape(itemID))", method: "DELETE")
    }

    func suggestReviewFixes(itemID: String) async throws -> AiReview {
        try await send("/api/ai/review/\(escape(itemID))/suggest", method: "POST")
    }

    func applyReviewFix(itemID: String, field: String, value: String, valuePl: String?) async throws -> AiReview {
        struct Body: Encodable { let field: String; let value: String; let valuePl: String? }
        return try await send(
            "/api/ai/review/\(escape(itemID))/fix", method: "POST",
            body: Body(field: field, value: value, valuePl: valuePl)
        )
    }

    func dropReviewProblem(itemID: String, field: String) async throws -> AiReview {
        try await send("/api/ai/review/\(escape(itemID))/problems/\(escape(field))", method: "DELETE")
    }

    func hideReviewed(itemID: String) async throws -> AiReview {
        try await send("/api/ai/review/\(escape(itemID))/hide", method: "POST")
    }

    func proposePolish(itemID: String) async throws -> PolishDraft {
        try await send("/api/ai/review/\(escape(itemID))/polish", method: "POST")
    }

    func savePolish(itemID: String, draft: PolishDraft) async throws -> AiReview {
        try await send("/api/ai/review/\(escape(itemID))/polish", method: "PUT", body: draft)
    }

    func saveAiKey(_ key: String) async throws -> AiSettings {
        try await send("/api/ai/key", method: "PUT", body: AiKeyUpdate(key: key))
    }

    func deleteAiKey() async throws -> AiSettings { try await send("/api/ai/key", method: "DELETE") }

    func saveGeminiKey(_ key: String) async throws -> AiSettings {
        try await send("/api/ai/gemini-key", method: "PUT", body: AiKeyUpdate(key: key))
    }

    func deleteGeminiKey() async throws -> AiSettings { try await send("/api/ai/gemini-key", method: "DELETE") }

    func sourceKeys() async throws -> [SourceKey] { try await get("/api/sources/keys") }

    func saveSourceKey(_ source: String, key: String) async throws -> [SourceKey] {
        try await send("/api/sources/keys/\(source)", method: "PUT", body: AiKeyUpdate(key: key))
    }

    func deleteSourceKey(_ source: String) async throws -> [SourceKey] {
        try await send("/api/sources/keys/\(source)", method: "DELETE")
    }

    func tailnet() async throws -> TailnetKey { try await get("/api/tailnet") }

    func saveTailnetKey(_ key: String) async throws -> TailnetKey {
        try await send("/api/tailnet/key", method: "PUT", body: AiKeyUpdate(key: key))
    }

    func deleteTailnetKey() async throws -> TailnetKey { try await send("/api/tailnet/key", method: "DELETE") }

    func saveTailnetAddress(_ address: String) async throws -> TailnetKey {
        try await send("/api/tailnet/address", method: "PUT", body: ["address": address])
    }

    func restore(itemID: String) async throws -> Item {
        var req = request("/api/library/items/\(escape(itemID))/restore", method: "POST")
        req.timeoutInterval = 300  // a minute or two on the NAS, one work at a time
        return try await perform(req)
    }

    func restorePro(itemID: String) async throws -> ProOrder {
        var req = request("/api/library/items/\(escape(itemID))/restore/pro", method: "POST")
        req.timeoutInterval = 120  // the picture downloaded and sent to Google's Batch
        return try await perform(req)
    }

    func restorer() async throws -> RestorerState { try await get("/api/ai/restorer") }

    func restorer(playlistID: Int) async throws -> RestorerState {
        try await get("/api/ai/restorer/playlists/\(playlistID)")
    }

    func restorePlaylist(id: Int) async throws -> RestorerState {
        var req = request("/api/ai/restorer/playlists/\(id)", method: "POST")
        req.timeoutInterval = 300  // every picture downloaded and sent in batches
        return try await perform(req)
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
        case let .tile(id):
            req = request("/api/library/items/\(escape(id))/thumb", query: [URLQueryItem(name: "tile", value: "true")])
        case let .image(id): req = request("/api/library/items/\(escape(id))/image")
        case let .original(id, version):
            req = request("/api/library/items/\(escape(id))/image", query: [URLQueryItem(name: "v", value: version)])
        case let .framePreview(id, settings, framing, ownLook):
            var query = framingQuery(settings)
            if !ownLook {
                query.append(URLQueryItem(name: "own_look", value: "false"))
                query += multiPhotosQuery(settings)
            }
            let encoder = Self.encoder()
            encoder.outputFormatting = .sortedKeys
            if let framing, let data = try? encoder.encode(framing) {
                query.append(URLQueryItem(name: "framing", value: String(decoding: data, as: UTF8.self)))
            }
            req = request("/api/library/items/\(escape(id))/preview", query: query)
        case let .museumPhoto(id, side, version):
            req = request(
                "/api/library/items/\(escape(id))/full",
                query: [URLQueryItem(name: "side", value: String(side)), URLQueryItem(name: "v", value: version)]
            )
        case let .framed(id, side, version):
            req = request(
                "/api/library/items/\(escape(id))/framed",
                query: [URLQueryItem(name: "side", value: String(side)), URLQueryItem(name: "v", value: version)]
            )
        case let .beforeCleaning(id, version):
            req = request(
                "/api/library/items/\(escape(id))/cleaned/before",
                query: [URLQueryItem(name: "v", value: version)]
            )
        case let .treated(id, restored, cleaned, version, made):
            var query = [
                URLQueryItem(name: "restored", value: restored ? "true" : "false"),
                URLQueryItem(name: "cleaned", value: cleaned ? "true" : "false"),
                URLQueryItem(name: "v", value: version),
            ]
            if let made { query.append(URLQueryItem(name: "made", value: made)) }
            req = request("/api/library/items/\(escape(id))/treated", query: query)
        case let .fine(id, tile, version):
            req = request(
                "/api/library/items/\(escape(id))/fine/\(escape(tile))",
                query: [URLQueryItem(name: "v", value: version)]
            )
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

    /// `patient`: a request that waits at the server (`Self.patient`).
    private func perform<T: Decodable>(_ req: URLRequest, patient: Bool = false) async throws -> T {
        let (data, response) = try await load(req, patient: patient)
        guard let http = response as? HTTPURLResponse else { throw BackendError.invalidResponse }
        guard (200 ..< 300).contains(http.statusCode) else {
            throw BackendError.http(status: http.statusCode, body: String(decoding: data, as: UTF8.self))
        }
        if T.self == EmptyResponse.self { return EmptyResponse() as! T }  // swiftlint:disable:this force_cast
        return try Self.decoder().decode(T.self, from: data)
    }

    /// Sends the request. One cut short by the app going away (or sent as
    /// it came back, before the network woke up) goes again once the app
    /// is back, if nothing can happen twice (`Replays.mayResend`); otherwise
    /// it ends as `BackendError.interrupted`, not as a server that did not answer.
    private func load(_ req: URLRequest, patient: Bool = false) async throws -> (Data, URLResponse) {
        let route = self.route
        let session: URLSession = patient ? Self.patient : .shared
        let (data, response) = try await again(req) { req in
            try await reach(req) {
                try await route.follow($0) { try await Tailnet.shared.data(for: $0, else: session, waits: patient) }
            }
        }
        Replays.shared.saw(response)
        return (data, response)
    }

    /// Like `load`, for a response read as it comes.
    private func stream(_ req: URLRequest) async throws -> (URLSession.AsyncBytes, URLResponse) {
        let (bytes, response) = try await again(req) {
            try await reach($0) { request in try await Tailnet.shared.send(request) { try await $0.bytes(for: request) } }
        }
        Replays.shared.saw(response)
        return (bytes, response)
    }

    /// A change goes with a key of its own (`Replays`), and with iOS's
    /// extra half minute to finish if the app goes away meanwhile.
    private func again<T>(_ req: URLRequest, _ send: (URLRequest) async throws -> T) async throws -> T {
        let req = Replays.keyed(req)
        guard Replays.isChange(req) else { return try await resend(req, send) }
        let time = await BackgroundTime(name: "change")
        do {
            let value = try await resend(req, send)
            await time.end()
            return value
        } catch {
            await time.end()
            throw error
        }
    }

    private func resend<T>(_ req: URLRequest, _ send: (URLRequest) async throws -> T) async throws -> T {
        var retries = 0
        while true {
            let mark = Absence.shared.mark()
            do {
                return try await send(req)
            } catch let error as URLError where Absence.shared.interrupted(error, since: mark) {
                guard Replays.shared.mayResend(req, after: error) else { throw BackendError.interrupted }
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
                  Replays.shared.mayResend(req, after: error),
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
