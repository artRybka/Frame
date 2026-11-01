import SwiftUI

/// Konfiguracja → Odkrywaj: the study of the day and the artist of the week
/// drawn again by hand, when the server's pick does not suit. The server
/// keeps the new one for the day (the week) and never draws the old one
/// back that day (week).
struct DiscoverPicksSection: View {
    @Environment(AppModel.self) private var model
    @State private var drawingDaily = false
    @State private var drawingArtist = false
    @State private var confirmDaily = false

    /// Claude writes the new study of the day (when the switch is on).
    private var writesStudy: Bool {
        guard let ai = model.aiSettings else { return false }
        return ai.keySet && ai.daily == true
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Odkrywaj", subtitle: "Gdy dzisiejszy wybór nie pasuje")
            Card {
                row(
                    "Studium dnia",
                    now: model.daily?.title,
                    hint: "Serwer wybierze inne dzieło na dziś, innego artysty. Jutro wybierze jak zwykle.",
                    button: "Wylosuj inne",
                    busy: drawingDaily
                ) {
                    if writesStudy { confirmDaily = true } else { drawDaily() }
                }
                Divider()
                row(
                    "Artysta tygodnia",
                    now: model.weekArtist?.name,
                    hint: "Serwer wybierze innego artystę do końca tygodnia. Inne karty „Dziś dla Ciebie” zostają.",
                    button: "Wylosuj innego",
                    busy: drawingArtist
                ) {
                    drawingArtist = true
                    Task {
                        await model.drawWeekArtistAgain()
                        drawingArtist = false
                    }
                }
            }
        }
        .task { await model.refreshDiscover() }
        .confirmationDialog("Wylosować inne Studium dnia?", isPresented: $confirmDaily, titleVisibility: .visible) {
            Button("Wylosuj inne") { drawDaily() }
            Button("Anuluj", role: .cancel) {}
        } message: {
            Text("Claude napisze studium nowego dzieła od razu, jak co dzień (Opus, około 0,25 USD z miesięcznego limitu). Dotychczasowe studium zostaje w „Studia dzieł”.")
        }
    }

    private func drawDaily() {
        drawingDaily = true
        Task {
            await model.drawDailyAgain()
            drawingDaily = false
        }
    }

    private func row(
        _ title: String,
        now: String?,
        hint: String,
        button: String,
        busy: Bool,
        action: @escaping () -> Void
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                if let now {
                    Text("Teraz: \(now)")
                        .font(.subheadline)
                        .foregroundStyle(Theme.ink)
                        .lineLimit(2)
                }
                Text(hint).font(.caption).foregroundStyle(Theme.inkSoft)
            }
            Button(action: action) {
                HStack(spacing: 8) {
                    Label(button, systemImage: "shuffle")
                    if busy { ProgressView() }
                }
            }
            .fontWeight(.semibold)
            .disabled(busy)
        }
    }
}
