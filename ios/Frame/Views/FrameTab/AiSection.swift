import SwiftUI

/// Konfiguracja: Claude (Anthropic's API) working for the library. The key,
/// what the model may do, the monthly limit and how far it got. The models
/// are fixed per task on the server: Haiku for keywords and translations,
/// Sonnet for notes on works without a description.
struct AiSection: View {
    @Environment(AppModel.self) private var model
    let settings: AiSettings
    @State private var key = ""
    @State private var savingKey = false
    @State private var estimating = false
    @State private var estimate: AiEstimate?

    private static let limits: [Double] = [1, 2, 5, 10, 20, 50, 100, 150, 200]

    private var limitOptions: [Double] {
        Set(Self.limits + [settings.monthlyLimitUsd]).sorted()
    }

    private var budgetLeft: Double { max(settings.monthlyLimitUsd - settings.spentUsd, 0) }

    private var keywordsOn: Bool { settings.keywordsArtworks || settings.keywordsPhotos }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Model językowy (Claude)", subtitle: "Słowa kluczowe i polskie opisy dzieł")
            Card {
                keyFields
                Divider()
                toggle(
                    "Polskie tytuły i opisy",
                    hint: "Tłumaczy Haiku. Dziełom bez opisu notkę pisze Sonnet.",
                    value: settings.plText
                ) { AiSettingsUpdate(plText: $0) }
                Divider()
                toggle(
                    "Słowa kluczowe dla dzieł",
                    hint: "Co przedstawia dzieło, dla Szukaj i inteligentnych playlist (Haiku).",
                    value: settings.keywordsArtworks
                ) { AiSettingsUpdate(keywordsArtworks: $0) }
                Divider()
                toggle(
                    "Słowa kluczowe dla zdjęć",
                    hint: "Miniatury Twoich zdjęć są wysyłane do Anthropic.",
                    value: settings.keywordsPhotos
                ) { AiSettingsUpdate(keywordsPhotos: $0) }
                if let daily = settings.daily {
                    Divider()
                    toggle(
                        "Studium dnia",
                        hint: "Nowe studium dzieła na górze Odkrywaj, raz dziennie (Opus, ok. 3 USD miesięcznie).",
                        value: daily
                    ) { AiSettingsUpdate(daily: $0) }
                }
                Divider()
                spending
                Divider()
                progress
            }
        }
        .task {
            // Batches and the background move on while Konfiguracja is open.
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(20))
                guard !Task.isCancelled else { return }
                await model.loadAiSettings()
            }
        }
        .confirmationDialog(
            estimate.map { "Opisać \(Names.pictures($0.items))?" } ?? "",
            isPresented: Binding(get: { estimate != nil }, set: { if !$0 { estimate = nil } }),
            titleVisibility: .visible,
            presenting: estimate
        ) { _ in
            Button("Opisz bibliotekę") { Task { await model.describeLibrary() } }
            Button("Anuluj", role: .cancel) {}
        } message: { estimate in
            Text("Około \(Money.usd(estimate.usd)) w pakietach Anthropic (połowa zwykłej ceny). Odpowiedzi przychodzą w ciągu doby. Pozostało w limicie \(Money.usd(budgetLeft)).")
        }
    }

    // MARK: Key

    @ViewBuilder
    private var keyFields: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Klucz API Anthropic").font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                Spacer()
                if settings.keySet, let tail = settings.keyTail {
                    Label("…\(tail)", systemImage: "checkmark.circle.fill")
                        .font(.subheadline.monospaced())
                        .foregroundStyle(Theme.good)
                }
            }
            SecureField(settings.keySet ? "zapisany · wpisz nowy, by zmienić" : "sk-ant-…", text: $key)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
            Text("Z console.anthropic.com → API Keys. Serwer sprawdza klucz przed zapisaniem i nie odsyła go do aplikacji.")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
        }
        Button {
            Task {
                savingKey = true
                if await model.saveAiKey(key) { key = "" }
                savingKey = false
            }
        } label: {
            HStack {
                Text("Zapisz i sprawdź")
                if savingKey { ProgressView() }
            }
        }
        .fontWeight(.semibold)
        .disabled(key.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || savingKey)
        if settings.keySet && !settings.keyFromApp {
            Text("Klucz z frame.env lub opcji add-onu. Zapisany tutaj będzie miał pierwszeństwo.")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
        }
        if settings.keyFromApp {
            Button("Usuń klucz", role: .destructive) {
                Task { await model.deleteAiKey() }
            }
            .font(.subheadline)
        }
    }

    // MARK: Switches and money

    private func toggle(
        _ title: String, hint: String, value: Bool, update: @escaping (Bool) -> AiSettingsUpdate
    ) -> some View {
        let binding = Binding(
            get: { value },
            set: { new in Task { await model.saveAiSettings(update(new)) } }
        )
        return Toggle(isOn: binding) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                Text(hint).font(.caption).foregroundStyle(Theme.inkSoft)
            }
        }
        .tint(Theme.ink)
    }

    @ViewBuilder
    private var spending: some View {
        let limit = Binding(
            get: { settings.monthlyLimitUsd },
            set: { usd in Task { await model.saveAiSettings(AiSettingsUpdate(monthlyLimitUsd: usd)) } }
        )
        HStack {
            Text("Miesięczny limit").font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
            Spacer()
            Picker("Miesięczny limit", selection: limit) {
                ForEach(limitOptions, id: \.self) { usd in
                    Text(Money.usd(usd)).tag(usd)
                }
            }
            .labelsHidden()
            .tint(Theme.ink)
        }
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("W tym miesiącu").font(.subheadline).foregroundStyle(Theme.ink)
                Spacer()
                Text(Money.usd(settings.spentUsd))
                    .font(.subheadline.monospacedDigit())
                    .foregroundStyle(Theme.inkSoft)
            }
            ProgressView(value: min(settings.spentUsd / max(settings.monthlyLimitUsd, 0.01), 1))
                .tint(settings.spentUsd >= settings.monthlyLimitUsd ? Theme.bad : Theme.ink)
            Text("Po przekroczeniu limitu serwer nie pyta modelu do końca miesiąca.")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
        }
    }

    // MARK: Progress

    @ViewBuilder
    private var progress: some View {
        progressRow("Słowa kluczowe", settings.keywordsProgress)
        if let plText = settings.plTextProgress {
            progressRow("Polskie opisy", plText)
        }
        if let error = settings.error {
            Label("Wstrzymane: \(error). Serwer spróbuje ponownie za kilka minut.", systemImage: "pause.circle")
                .font(.caption)
                .foregroundStyle(Theme.bad)
        }
        Button {
            Task {
                estimating = true
                estimate = await model.keywordsEstimate()
                estimating = false
                if let found = estimate, found.items == 0 {
                    estimate = nil
                    model.notices.info("Cała biblioteka ma już słowa kluczowe")
                } else if let found = estimate, found.usd > budgetLeft {
                    estimate = nil
                    model.notices.warn(
                        "Opisanie biblioteki to około \(Money.usd(found.usd))",
                        "Więcej niż zostało w limicie (\(Money.usd(budgetLeft)))."
                    )
                }
            }
        } label: {
            HStack {
                Text("Opisz całą bibliotekę")
                if estimating { ProgressView() }
            }
        }
        .fontWeight(.semibold)
        .disabled(!settings.keySet || !keywordsOn || estimating || settings.keywordsProgress.preparing)
        Text("Otwarte dzieło lub zdjęcie serwer opisuje od razu, poza kolejnością. W tle opisuje Twoje zdjęcia i dzieła z ulubionych, playlist i ekranu. Ten przycisk dokłada cały katalog Odkrywaj, taniej, w pakietach.")
            .font(.caption)
            .foregroundStyle(Theme.inkSoft)
    }

    private func progressRow(_ title: String, _ progress: AiSettings.Progress) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(title).font(.subheadline).foregroundStyle(Theme.ink)
                Spacer()
                Text("\(Names.pictures(progress.done)) gotowe")
                    .font(.subheadline.monospacedDigit())
                    .foregroundStyle(Theme.inkSoft)
            }
            ForEach(details(progress), id: \.self) { line in
                Text(line).font(.caption).foregroundStyle(Theme.inkSoft)
            }
        }
    }

    private func details(_ progress: AiSettings.Progress) -> [String] {
        var lines: [String] = []
        if progress.preparing {
            lines.append("Przygotowuję pakiet dla Anthropic…")
        }
        if progress.batchItems > 0 {
            lines.append("W pakiecie: \(progress.batchDone) z \(progress.batchItems), odpowiedzi w ciągu doby")
        }
        if progress.waiting > 0 {
            lines.append("Czeka w tle: \(progress.waiting)")
        }
        if progress.refused > 0 {
            lines.append("Bez odpowiedzi modelu: \(progress.refused)")
        }
        return lines
    }
}

enum Money {
    /// "0,42 USD".
    static func usd(_ value: Double) -> String {
        value.formatted(.currency(code: "USD").locale(Locale(identifier: "pl_PL")))
    }
}
