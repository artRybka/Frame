import SwiftUI

/// Konfiguracja → Aplikacja ramki → „Pokaż ekran ramki”: a screenshot of
/// the frame's screen as its app drew it. The app takes it at its next
/// question on the charger (every 10 s there), at least a minute after its
/// last drawing (one taken sooner was still white, 2026-11-04). On battery
/// it is ordered for the next wake, which then lasts a little longer
/// (2026-11-05). It is 640×360 in smooth colours: what the page shows, not
/// the e-paper's dots.
struct PanelScreenshotSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss

    private enum Phase: Equatable {
        case asking
        case waiting
        /// On battery: the next wake (ISO) can take one when ordered.
        case canOrder(String?)
        case ordered(String?)
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
        case let .canOrder(wake):
            VStack(alignment: .leading, spacing: 12) {
                Text("Ramka śpi na baterii, więc teraz zrzutu nie zrobi.")
                    .font(.subheadline)
                    .foregroundStyle(Theme.ink)
                Button {
                    Task { await order() }
                } label: {
                    Label("Zamów zrzut przy następnej pobudce", systemImage: "camera.viewfinder")
                }
                .buttonStyle(PrimaryButtonStyle())
                Text("Zrobi go przy najbliższej pobudce\(Self.at(wake)) i poczuwa wtedy do 3 minut dłużej, co kosztuje trochę baterii.")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
            }
        case let .ordered(wake):
            Text("Zrzut zamówiony. Ramka zrobi go przy najbliższej pobudce\(Self.at(wake)) i wtedy pojawi się tutaj. Na zasilaczu zrobi go od razu.")
                .font(.subheadline)
                .foregroundStyle(Theme.ink)
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

    /// " o 14:00" for the next wake, when the server knows it.
    private static func at(_ wake: String?) -> String {
        When.clock(wake).map { " o \($0)" } ?? ""
    }

    /// On battery: for the next wake, not now.
    private func order() async {
        phase = .asking
        do {
            let asked = try await model.backend.askPanelScreenshot()
            phase = .ordered(asked.wakeAt)
        } catch is CancellationError {
            return
        } catch {
            let (title, detail) = Notices.words(for: error)
            phase = .failed([title, detail].compactMap { $0 }.joined(separator: ". "))
        }
    }

    private func take() async {
        phase = .asking
        do {
            let before = try await model.backend.panelScreenshot()
            shot = before
            guard before.onCharger else {
                // Asleep on battery: ordered only on purpose (it costs a
                // longer wake), not just by looking.
                phase = before.askedAt == nil ? .canOrder(before.wakeAt) : .ordered(before.wakeAt)
                return
            }
            let asked = try await model.backend.askPanelScreenshot()
            guard asked.onCharger else {
                phase = .ordered(asked.wakeAt)
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
