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

/// Themed packs of museum works that grow the library in one tap.
struct LibraryPacksSection: View {
    @Environment(AppModel.self) private var model
    @State private var packs: [LibraryPack] = []
    @State private var running: [String: JobStatus?] = [:]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if !packs.isEmpty {
                Eyebrow("Rozszerz bibliotekę")
                ForEach(packs) { pack in
                    Card(padding: 14) {
                        HStack(alignment: .top, spacing: 12) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(pack.name).font(.serif(17, weight: .medium))
                                Text(pack.description)
                                    .font(.footnote)
                                    .foregroundStyle(Theme.inkSoft)
                                    .fixedSize(horizontal: false, vertical: true)
                                if let job = running[pack.key] {
                                    Text(jobProgress(job))
                                        .font(.caption.weight(.semibold))
                                        .foregroundStyle(Theme.accent)
                                }
                            }
                            Spacer(minLength: 0)
                            addButton(pack)
                        }
                    }
                }
                Text("Dzieła, które już masz, są pomijane, więc pakiet można dodać ponownie.")
                    .font(.footnote)
                    .foregroundStyle(Theme.inkSoft)
            }
        }
        .task {
            guard packs.isEmpty else { return }
            packs = (try? await model.backend.packs()) ?? []
            for pack in packs where pack.importing {
                Task { await add(pack) }
            }
        }
    }

    private func addButton(_ pack: LibraryPack) -> some View {
        Button {
            Task { await add(pack) }
        } label: {
            HStack(spacing: 6) {
                if running[pack.key] != nil {
                    ProgressView().controlSize(.mini)
                } else {
                    Image(systemName: "plus")
                }
                Text("do \(pack.size)")
            }
            .font(.caption.weight(.semibold))
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(Theme.accent.opacity(0.12), in: Capsule())
        }
        .disabled(running[pack.key] != nil)
    }

    private func add(_ pack: LibraryPack) async {
        guard running[pack.key] == nil else { return }
        running[pack.key] = .some(nil)
        defer { running[pack.key] = nil }
        do {
            let id = try await model.backend.importPack(key: pack.key)
            let job = try await watchJob(id, backend: model.backend) { running[pack.key] = $0 }
            model.toast = "\(pack.name): \(job.done) dzieł w bibliotece"
            await model.refreshFacets()
        } catch {
            model.show(error)
        }
    }
}
