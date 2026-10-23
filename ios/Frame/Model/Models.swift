import Foundation

/// `GET /api/now` — what the frame is showing.
struct NowPlaying: Decodable, Equatable, Sendable {
    let fileId: String
    let fileName: String
    let created: String
    let title: String
    let description: String
    let source: String
    let previewUrl: String
}

/// `GET /api/health`
struct Health: Decodable, Sendable {
    let ok: Bool
    let version: String
    let palette: String
}

/// `GET /api/device/status`
struct DeviceStatus: Decodable, Sendable {
    struct Battery: Decodable, Sendable {
        let level: Int
        let raw: String
    }

    let serial: String
    let software: String
    let model: String
    let name: String
    let battery: Battery
    let networkStandby: Bool
}

/// `POST /api/display`, `POST /api/device/push`
struct DisplayResponse: Decodable, Sendable {
    let pushed: Bool
    let fetched: Bool?
    let message: String?
}

enum RenderPreset: String, CaseIterable, Identifiable, Sendable {
    case photo, painting, graphic, bw

    var id: String { rawValue }

    var label: String {
        switch self {
        case .photo: String(localized: "Zdjęcie")
        case .painting: String(localized: "Obraz")
        case .graphic: String(localized: "Grafika")
        case .bw: String(localized: "Czarno-białe")
        }
    }
}
