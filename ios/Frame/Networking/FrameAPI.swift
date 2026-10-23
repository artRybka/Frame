import Foundation

/// Client for the frame server API (see server/src/frame_server/web/app.py).
struct FrameAPI: Sendable {
    enum APIError: LocalizedError {
        case http(status: Int, body: String)
        case invalidResponse

        var errorDescription: String? {
            switch self {
            case let .http(status, body): "HTTP \(status): \(body)"
            case .invalidResponse: String(localized: "Nieprawidłowa odpowiedź serwera")
            }
        }
    }

    let baseURL: URL
    let token: String?

    static func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    // MARK: Endpoints

    func health() async throws -> Health {
        try await get("/api/health")
    }

    func nowPlaying() async throws -> NowPlaying {
        try await get("/api/now")
    }

    func deviceStatus() async throws -> DeviceStatus {
        try await get("/api/device/status")
    }

    func pushAgain() async throws -> DisplayResponse {
        try await send(request("/api/device/push", method: "POST"))
    }

    func display(image: Data, filename: String, preset: RenderPreset, title: String) async throws
        -> DisplayResponse
    {
        var form = MultipartForm()
        form.addField("preset", preset.rawValue)
        form.addField("title", title)
        form.addFile("file", filename: filename, mimeType: "image/jpeg", data: image)
        var req = request("/api/display", method: "POST")
        req.setValue(form.contentType, forHTTPHeaderField: "Content-Type")
        req.httpBody = form.body()
        req.timeoutInterval = 180
        return try await send(req)
    }

    func data(path: String) async throws -> Data {
        let (data, response) = try await URLSession.shared.data(for: request(path))
        try Self.check(response, data)
        return data
    }

    // MARK: Plumbing

    func request(_ path: String, method: String = "GET") -> URLRequest {
        var req = URLRequest(url: baseURL.appending(path: path))
        req.httpMethod = method
        if let token {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return req
    }

    private func get<T: Decodable>(_ path: String) async throws -> T {
        try await send(request(path))
    }

    private func send<T: Decodable>(_ req: URLRequest) async throws -> T {
        let (data, response) = try await URLSession.shared.data(for: req)
        try Self.check(response, data)
        return try Self.makeDecoder().decode(T.self, from: data)
    }

    private static func check(_ response: URLResponse, _ data: Data) throws {
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200 ..< 300).contains(http.statusCode) else {
            throw APIError.http(status: http.statusCode, body: String(decoding: data, as: UTF8.self))
        }
    }
}

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
