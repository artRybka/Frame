import SwiftUI

/// Konfiguracja → Claude → "Kreatywny restaurator" (Mateusz 2026-11-12):
/// the favourites whose picture is small for the frame (under 1600 px,
/// `LowRes`) drawn again larger by Google's image model (Nano Banana 2.1)
/// in its batches, at half the price, within a day. One work at a time is
/// in its card's "…". The key is Gemini's, in Klucze i certyfikaty.
struct RestorerSection: View {
    @Environment(AppModel.self) private var model
    @State private var state: RestorerState?
    @State private var asking: RestorerState?
    @State private var ordering = false

    var body: some View {
        Group {
            if let state {
                VStack(alignment: .leading, spacing: 16) {
                    SectionHeader(title: "Kreatywny restaurator", subtitle: "Ulubione w niskiej rozdzielczości")
                    Card { content(state) }
                }
            }
        }
        .task {
            // Batches come back while Konfiguracja is open.
            while !Task.isCancelled {
                if let fresh = await model.restorerState() { state = fresh }
                if LaunchRoute.confirm == "restore", asking == nil, let state, state.items > 0 {
                    try? await Task.sleep(for: .seconds(6))  // after the page scrolled to it
                    asking = state  // CI screenshots: where the dialog points
                }
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
            "Model graficzny Google przerysowuje małe zdjęcia dzieł z Ulubionych do ok. 2000 px. Szczegóły są dorysowane, nie odzyskane, więc takie dzieła mają bursztynowe iskierki. Pojedyncze dzieło odnowisz w menu „…” na jego karcie."
        )
        .font(.caption)
        .foregroundStyle(Theme.inkSoft)
        .fixedSize(horizontal: false, vertical: true)
        row("Do odnowienia", Names.pictures(state.items))
        if state.waiting > 0 {
            row("W pakietach Google", Names.pictures(state.waiting))
        }
        row("Odnowione", Names.pictures(state.restored), symbol: LowRes.restoredSymbol)
        Button {
            asking = state
        } label: {
            HStack {
                Image(systemName: LowRes.restoredSymbol)
                Text("Odnów Ulubione")
                if ordering { ProgressView() }
            }
        }
        .fontWeight(.semibold)
        .disabled(!state.enabled || state.items == 0 || ordering)
        .confirmationDialog(
            asking.map { "Odnowić \(Names.pictures($0.items))?" } ?? "",
            isPresented: Binding(get: { asking != nil }, set: { if !$0 { asking = nil } }),
            titleVisibility: .visible,
            presenting: asking
        ) { _ in
            Button("Odnów") {
                Task {
                    ordering = true
                    if let fresh = await model.restoreFavourites() { self.state = fresh }
                    ordering = false
                }
            }
            Button("Anuluj", role: .cancel) {}
        } message: { asking in
            Text(
                "Około \(Money.usd(asking.usd)) w pakietach Google (połowa zwykłej ceny). Odnowione zdjęcia przychodzą w ciągu doby. „Przywróć zdjęcie muzeum” na karcie cofa zmianę."
            )
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
