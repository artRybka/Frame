import SwiftUI

/// Konfiguracja → Aplikacja ramki → „Pokaż ekran ramki”: a screenshot of
/// the frame's screen as its app drew it. The app takes it at its next
/// question on the charger (every 10 s there), at least a minute after its
/// last drawing (one taken sooner was still white, 2026-11-04). It is
/// 640×360 in smooth colours: what the page shows, not the e-paper's dots.
struct PanelScreenshotSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss

    private enum Phase: Equatable {
        case asking
        case waiting
        case notOnCharger
        case done
        case late
        case failed(String)
    }

    /// The waiting for one asked for: the minute after a drawing, the next
    /// question, the upload.
    private static let patience: Duration = .seconds(150)

    @State private var shot: PanelScreenshot?
    @State private var phase: Phase = .asking
    /// Another try, from the toolbar.
    @State private var round = 0

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    picture
                    status
                    Text("Tak obraz wygląda w pamięci ramki, pomniejszony do 640×360. Na e-papierze kolory są spokojniejsze i złożone z kropek farb.")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
                .pageWidth()
                .padding(.horizontal, Theme.gutter)
                .padding(.top, 8)
                .padding(.bottom, 40)
            }
            .paperPage()
            .navigationTitle("Ekran ramki")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Gotowe") { dismiss() }
                }
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        round += 1
                    } label: {
                        Label("Zrób nowy zrzut", systemImage: "arrow.clockwise")
                    }
                    .disabled(phase == .asking || phase == .waiting)
                }
            }
        }
        .task(id: round) { await take() }
    }

    @ViewBuilder
    private var picture: some View {
        if let taken = shot?.takenAt {
            VStack(alignment: .leading, spacing: 6) {
                ArtImage(
                    ref: .path("/api/device/screenshot.jpg?t=\(taken)"),
                    placeholder: Theme.mat,
                    maxPixel: 1280,
                    contentMode: .fit
                )
                .aspectRatio(16.0 / 9.0, contentMode: .fit)
                .clipShape(RoundedRectangle(cornerRadius: 6))
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(Theme.ink.opacity(0.12)))
                .accessibilityLabel("Zrzut ekranu ramki")
                if let clock = When.clock(taken), let ago = When.ago(taken) {
                    Text("Zrzut z \(clock), \(ago)")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
            }
        } else if phase != .asking && phase != .waiting {
            Text("Na serwerze nie ma jeszcze żadnego zrzutu.")
                .foregroundStyle(Theme.inkSoft)
        }
    }

    @ViewBuilder
    private var status: some View {
        switch phase {
        case .asking, .waiting:
            HStack(spacing: 8) {
                ProgressView()
                Text("Ramka robi zrzut. Jeśli przed chwilą zmieniała obraz, czeka z nim minutę.")
                    .font(.subheadline)
                    .foregroundStyle(Theme.ink)
            }
        case .notOnCharger:
            Text("Ramka nie jest na zasilaczu, więc teraz zrzutu nie zrobi. Zrobi go sama, gdy ją podłączysz.")
                .font(.subheadline)
                .foregroundStyle(Theme.warn)
        case .late:
            Text("Ramka nie przysłała zrzutu. Spróbuj za chwilę.")
                .font(.subheadline)
                .foregroundStyle(Theme.warn)
        case let .failed(why):
            Text(why)
                .font(.subheadline)
                .foregroundStyle(Theme.bad)
        case .done:
            EmptyView()
        }
    }

    private func take() async {
        phase = .asking
        do {
            let before = try await model.backend.panelScreenshot()
            shot = before
            let asked = try await model.backend.askPanelScreenshot()
            guard asked.onCharger else {
                phase = .notOnCharger
                return
            }
            phase = .waiting
            let deadline = ContinuousClock.now + Self.patience
            while ContinuousClock.now < deadline {
                try await Task.sleep(for: .seconds(3))
                let now = try await model.backend.panelScreenshot()
                if now.takenAt != nil, now.takenAt != before.takenAt, now.askedAt == nil {
                    shot = now
                    phase = .done
                    return
                }
            }
            phase = .late
        } catch is CancellationError {
            return
        } catch {
            let (title, detail) = Notices.words(for: error)
            phase = .failed([title, detail].compactMap { $0 }.joined(separator: ". "))
        }
    }
}
