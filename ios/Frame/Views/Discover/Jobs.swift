import SwiftUI

/// Polls a server import until it finishes, reporting progress on the way.
@MainActor
func watchJob(
    _ id: String, backend: any FrameBackend, progress: (JobStatus) -> Void
) async throws -> JobStatus {
    while true {
        let status = try await backend.job(id: id)
        progress(status)
        if status.finished { return status }
        try await Task.sleep(for: .seconds(1.5))
    }
}

