import SwiftUI

/// Konfiguracja → Gemini → "Kreatywny restaurator" (Mateusz 2026-11-12):
/// works whose picture is small for the frame (under 1600 px, `LowRes`)
/// drawn again larger by Google's image model (Nano Banana 2.1, Pro when it fails twice). Since
/// 2026-11-13 they are ordered from a playlist's "…" (Ulubione's too:
/// "to także przenieś pod "..." w playliście ulubione"), one work from its
/// card's "…"; here only what waits in Google's batches and what was drawn.
/// The key is Gemini's, in Klucze i certyfikaty.
struct RestorerSection: View {
    @Environment(AppModel.self) private var model
    @State private var state: RestorerState?

    var body: some View {
        // A stack, not a Group: a Group with nothing in it runs no task, and
        // the section waited for its numbers for ever.
        VStack(alignment: .leading, spacing: 16) {
            if let state {
                SectionHeader(title: "Restauracja dzieł", subtitle: "Dzieła w niskiej rozdzielczości")
                Card { content(state) }
            }
        }
        .frame(maxWidth: .infinity, minHeight: 1, alignment: .leading)
        .task {
            // Batches come back while Konfiguracja is open.
            while !Task.isCancelled {
                if let fresh = await model.restorerState() { state = fresh }
                try? await Task.sleep(for: .seconds(30))
            }
        }
    }

    @ViewBuilder
    private func content(_ state: RestorerState) -> some View {
        if !state.enabled {
            Label("Brak klucza Gemini. Dodasz go w Kluczach i certyfikatach.", systemImage: "key")
                .font(.caption)
                .foregroundStyle(Theme.warn)
            Divider()
        }
        Text(
            "Przerysowuje małe zdjęcia dzieł do ok. 2000 px, w barwach oryginału. Szczegóły są dorysowane, dlatego takie dzieła mają bursztynowe iskierki. Zamawiasz w menu „…” playlisty albo dzieła."
        )
        .font(.caption)
        .foregroundStyle(Theme.inkSoft)
        .fixedSize(horizontal: false, vertical: true)
        if state.waiting > 0 {
            row("W pakietach Google", Names.pictures(state.waiting))
        }
        row("Odnowione", Names.pictures(state.restored), symbol: LowRes.restoredSymbol)
        if let settings = model.aiSettings, let days = settings.costDays, let rows = settings.geminiCosts {
            row("Ostatnie \(days) dni", AiSection.usd(rows.first { $0.key == "restorer" }?.daysUsd ?? 0))
        }
    }

    private func row(_ title: String, _ value: String, symbol: String? = nil) -> some View {
        HStack {
            Text(title).font(.subheadline).foregroundStyle(Theme.ink)
            Spacer()
            if let symbol {
                Image(systemName: symbol).font(.caption).foregroundStyle(LowRes.tint)
            }
            Text(value)
                .font(.subheadline.monospacedDigit())
                .foregroundStyle(Theme.inkSoft)
        }
    }
}
