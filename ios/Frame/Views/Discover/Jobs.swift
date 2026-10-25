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

/// "X of Y" while an import runs.
func jobProgress(_ job: JobStatus?) -> String {
    guard let job, job.total > 0 else { return "Wyszukiwanie…" }
    return "Dodawanie \(job.done + job.failed) z \(job.total)…"
}

