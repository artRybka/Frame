import SwiftUI
import UIKit

/// Konfiguracja → Diagnostyka → "Kadrowanie zdjęć z muzeów": the phone's
/// model looks at a batch of the works' photographs one after another, not
/// only those whose card he opens (Mateusz 2026-11-20: "z ustawienia w
/// Konfiguracji > Diagnostyka gdzie mógłby robić to większą seria"). What it
/// cut, and what it left to him, wait in Playlisty → "Kadrowane".
struct MuseumCropSection: View {
    @Environment(AppModel.self) private var model
    @State private var batch = MuseumCropBatch()

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Kadrowanie zdjęć z muzeów", subtitle: "Na iPhonie")
            Card {
                Text(bound: "Model na iPhonie odcina ramę, sztalugę albo tło wokół dzieła, gdy jest pewny i dzieło jest sfotografowane prawie na wprost. Resztę zostawia bez kadru do ręcznej poprawki. Wyniki czekają w Playlisty → „Kadrowane”.")
                    .font(.subheadline)
                    .foregroundStyle(Theme.inkSoft)
                Divider()
                if let left = batch.left {
                    Text(bound: left == 0 ? "Wszystkie dzieła są obejrzane" : "Czeka \(Names.works(left))")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(Theme.ink)
                } else {
                    ProgressView()
                }
                if batch.running || batch.done > 0 {
                    ProgressView(value: Double(batch.done), total: Double(max(batch.planned, 1)))
                    Text(bound: batch.summary)
                        .font(.subheadline.monospacedDigit())
                        .foregroundStyle(Theme.inkSoft)
                }
                if let told = batch.told {
                    Text(bound: told)
                        .font(.subheadline)
                        .foregroundStyle(Theme.warn)
                }
            }
            if batch.running {
                Button {
                    batch.stop()
                } label: {
                    Label("Przerwij", systemImage: "stop.circle")
                        .font(.subheadline.weight(.medium))
                }
                .buttonStyle(.bordered)
            } else {
                Menu {
                    ForEach(MuseumCropBatch.sizes, id: \.self) { size in
                        Button(MuseumCropBatch.label(size).bound) {
                            Task { await batch.run(size, with: model.backend) }
                        }
                    }
                } label: {
                    Label("Kadruj partię", systemImage: "crop")
                        .font(.subheadline.weight(.medium))
                }
                .buttonStyle(.bordered)
                .disabled(batch.left == 0)
            }
            Text(bound: "Zostaw aplikację otwartą: zdjęcia idą z serwera, a kadry wracają na serwer. Ekran nie wygaśnie w trakcie.")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
        }
        .task { await batch.count(with: model.backend) }
    }
}

/// "Kadruj partię": the works waiting, looked at one after another.
@MainActor @Observable
final class MuseumCropBatch {
    static let sizes = [50, 200, 1000]
    /// Works asked of the server at a time.
    static let page = 25

    static func label(_ size: Int) -> String { size >= 1000 ? "Wszystkie (do 1000)" : Names.works(size) }

    private(set) var left: Int?
    private(set) var running = false
    private(set) var planned = 0
    private(set) var done = 0
    private(set) var cut = 0
    private(set) var whole = 0
    private(set) var unsure = 0
    private(set) var failed = 0
    private(set) var seconds = 0.0
    private(set) var told: String?
    private var stopping = false

    var summary: String {
        var parts = ["\(done) z \(planned)", "wykadrowane \(cut)", "do ręcznej poprawki \(unsure)", "bez kadru \(whole)"]
        if failed > 0 { parts.append("nie udało się \(failed)") }
        if done > 0 { parts.append(String(format: "%.1f s na zdjęcie", seconds / Double(done)).replacingOccurrences(of: ".", with: ",")) }
        return parts.joined(separator: " · ")
    }

    func count(with backend: any FrameBackend) async {
        left = try? await backend.phoneCropsWaiting(limit: 1).left
    }

    func stop() { stopping = true }

    func run(_ size: Int, with backend: any FrameBackend) async {
        guard !running else { return }
        running = true
        stopping = false
        told = nil
        (planned, done, cut, whole, unsure, failed, seconds) = (min(size, left ?? size), 0, 0, 0, 0, 0, 0)
        UIApplication.shared.isIdleTimerDisabled = true
        defer {
            UIApplication.shared.isIdleTimerDisabled = false
            running = false
        }
        var skipped = Set<String>()
        while done < planned, !stopping {
            let waiting: PhoneCropsWaiting
            do {
                waiting = try await backend.phoneCropsWaiting(limit: Self.page + skipped.count)
            } catch {
                told = error.localizedDescription
                break
            }
            left = waiting.left
            let works = waiting.works.filter { !skipped.contains($0.id) }
            if works.isEmpty { break }
            for work in works {
                if done >= planned || stopping { break }
                let began = ProcessInfo.processInfo.systemUptime
                do {
                    let ask = PhoneCropAsk(
                        look: work.look, kind: work.kind, model: work.model, picture: work.picture, side: waiting.side
                    )
                    if let result = try await MuseumCrop.look(itemID: work.id, backend: backend, asked: ask),
                       !result.verdict.isEmpty {
                        switch result.verdict {
                        case "cut": cut += 1
                        case "whole": whole += 1
                        default: unsure += 1
                        }
                    } else {
                        skipped.insert(work.id)
                        failed += 1
                    }
                } catch {
                    skipped.insert(work.id)
                    failed += 1
                    told = error.localizedDescription
                }
                seconds += ProcessInfo.processInfo.systemUptime - began
                done += 1
            }
        }
        await count(with: backend)
    }
}
