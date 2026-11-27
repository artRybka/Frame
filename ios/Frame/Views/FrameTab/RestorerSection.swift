import SwiftUI

/// Konfiguracja → Gemini → "Restauracja dzieł" (Mateusz 2026-11-12):
/// works whose picture is small for the frame (under 1600 px, `LowRes`)
/// drawn again larger, by the server's own model since 2026-11-26 (free),
/// or by Google's as "Restaurator Pro" (Nano Banana 2.1 through its Batch,
/// within each person's day). Ordered from a playlist's "…" or a work's
/// card; here only what waits and what was drawn.
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
        if state.pro == false {
            Label("Restauracja potrzebuje klucza Gemini. Dodasz go w Kluczach i certyfikatach.", systemImage: "key")
                .font(.caption)
                .foregroundStyle(Theme.warn)
            Divider()
        }
        Text(bound:
            "Małe zdjęcia dzieł iPhone sam przerysowuje naszym modelem do ok. 2000 px, w barwach oryginału, gdy otwierasz kartę dzieła, bez opłat i bez oznaczeń. Restauracja rysuje modelem Google, w ciągu doby: szczegóły są dorysowane, dlatego takie dzieła mają złote iskierki i trafiają do playlisty Restaurator. Zamawiasz ją w menu „…” dzieła."
        )
        .font(.caption)
        .foregroundStyle(Theme.inkSoft)
        .fixedSize(horizontal: false, vertical: true)
        if state.waiting > 0 {
            row("W kolejce", Names.pictures(state.waiting))
        }
        row("Odnowione", Names.pictures(state.restored), symbol: LowRes.restoredSymbol)
        if let settings = model.aiSettings, let days = settings.costDays, let rows = settings.geminiCosts {
            row("Restauracja, \(days) dni", AiSection.usd(rows.first { $0.key == "restorer" }?.daysUsd ?? 0))
        }
    }

    private func row(_ title: String, _ value: String, symbol: String? = nil) -> some View {
        HStack {
            Text(bound: title).font(.subheadline).foregroundStyle(Theme.ink)
            Spacer()
            if let symbol {
                Image(systemName: symbol).font(.caption).foregroundStyle(LowRes.tint)
            }
            Text(bound: value)
                .font(.subheadline.monospacedDigit())
                .foregroundStyle(Theme.inkSoft)
        }
    }
}
