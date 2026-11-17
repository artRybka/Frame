import SwiftUI

/// Konfiguracja → Claude: Anthropic's API working for the library. What the
/// model may do, the monthly limit and how far it got; the key is in
/// Konfiguracja → Klucze i certyfikaty (`part: .key`). The models are fixed
/// per task on the server.
///
/// Konfiguracja → Gemini (`part: .gemini`): Google's image model, with a
/// month's limit and spending of its own (Mateusz 2026-11-12 23:20: "Dla
/// Gemini trzeba dać osobny segment w Konfiguracja (tak jak Claude) i tam
/// ustawić osobno limit").
///
/// Since 2026-11-16 ("prezentowane pozycje są niejasne… część miała
/// zastosowanie doraźne… podaj koszt dla każdej pozycji za ostatnie dni"):
/// both pages start with what each thing cost in the last days, the
/// switches stand in three groups with a line each and their own money
/// under them, and the one-off orders (earlier studies, texts kept, the
/// whole library described) are gone: the month's rest does them.
struct AiSection: View {
    enum Part {
        /// The switches, the limit and the progress.
        case settings
        /// The Anthropic key, and Google's.
        case key
        /// The image model: its switches, its own limit and spending.
        case gemini
    }

    @Environment(AppModel.self) private var model
    let settings: AiSettings
    var part: Part = .settings
    @State private var key = ""
    @State private var savingKey = false
    @State private var geminiKey = ""
    @State private var savingGeminiKey = false
    /// CI and Mac screenshots: `-review YES` opens „Do sprawdzenia".
    @State private var showReview = UserDefaults.standard.bool(forKey: "review")

    private static let limits: [Double] = [1, 2, 5, 10, 20, 50, 100, 150, 200]

    var body: some View {
        switch part {
        case .settings: settingsBody
        case .key: keyBody
        case .gemini: geminiBody
        }
    }

    private var geminiBody: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Gemini (Google)", subtitle: "Arkusze kompozycji, szukanie wyglądem, restauracja dzieł")
            Card {
                if let limit = settings.geminiMonthlyLimitUsd {
                    if settings.geminiKeySet != true {
                        Label("Brak klucza Google. Dodasz go w Kluczach i certyfikatach.", systemImage: "key")
                            .font(.caption)
                            .foregroundStyle(Theme.warn)
                        Divider()
                    }
                    spendingRows(
                        limit: limit, spent: settings.geminiSpentUsd ?? 0,
                        note: "Po przekroczeniu limitu Gemini czeka do następnego miesiąca. Claude liczy się osobno."
                    ) { AiSettingsUpdate(geminiMonthlyLimitUsd: $0) }
                } else {
                    Label("Ten serwer nie ma jeszcze modelu graficznego. Zaktualizuj serwer.", systemImage: "arrow.down.circle")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
            }
            if let rows = settings.geminiCosts {
                costSection(rows, since: Self.monthStart())
            }
            if settings.geminiMonthlyLimitUsd != nil, settings.drawn != nil || settings.looks != nil {
                SectionHeader(title: "Co robi Gemini")
                Card {
                    if let drawn = settings.drawn {
                        toggle(
                            "Arkusze kompozycji",
                            hint: Self.drawnHint(settings),
                            value: drawn,
                            cost: "drawn"
                        ) { AiSettingsUpdate(drawn: $0) }
                        if settings.geminiKeySet == true, let note = Self.drawnNote(settings, on: drawn) {
                            Label(note.text, systemImage: note.icon)
                                .font(.caption)
                                .foregroundStyle(note.bad ? Theme.bad : Theme.inkSoft)
                        }
                    }
                    if let looks = settings.looks {
                        if settings.drawn != nil { Divider() }
                        toggle(
                            "Szukanie wyglądem",
                            hint: "Szukaj opisem wyglądu, zdjęciem i „Podobne wyglądem”. Twoje zdjęcia nie trafiają do Google.",
                            value: looks,
                            cost: "looks"
                        ) { AiSettingsUpdate(looks: $0) }
                        if settings.geminiKeySet == true, let note = Self.looksNote(settings, on: looks) {
                            Label(note.text, systemImage: note.icon)
                                .font(.caption)
                                .foregroundStyle(note.bad ? Theme.bad : Theme.inkSoft)
                        }
                    }
                }
            }
        }
        .task {
            // The Batch moves on while Konfiguracja is open.
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(20))
                guard !Task.isCancelled else { return }
                await model.loadAiSettings()
            }
        }
    }

    private var keyBody: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Claude", subtitle: "Klucz API Anthropic")
            Card {
                keyFields
            }
            if settings.geminiKeySet != nil {
                SectionHeader(title: "Google (Gemini)", subtitle: "Klucz API modelu graficznego")
                Card {
                    geminiKeyFields
                }
            }
        }
    }

    private var settingsBody: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Claude (Anthropic)", subtitle: "Opisy, studia i nocne porządki")
            Card {
                if !settings.keySet {
                    Label("Brak klucza Anthropic. Dodasz go w Kluczach i certyfikatach.", systemImage: "key")
                        .font(.caption)
                        .foregroundStyle(Theme.warn)
                    Divider()
                }
                spendingRows(
                    limit: settings.monthlyLimitUsd, spent: settings.spentUsd,
                    note: "Po przekroczeniu limitu Claude czeka do dnia odnowienia."
                ) { AiSettingsUpdate(monthlyLimitUsd: $0) }
                if let error = settings.error {
                    Label("Wstrzymane: \(error). Serwer spróbuje ponownie za kilka minut.", systemImage: "pause.circle")
                        .font(.caption)
                        .foregroundStyle(Theme.bad)
                }
            }
            if let rows = settings.claudeCosts {
                costSection(rows, since: settings.periodStart)
            }
            // What Claude does, when and for how much: Zadania (Mateusz
            // 2026-11-17).
            Card {
                NavigationLink(value: SettingsPage.tasks) {
                    HStack(spacing: 12) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Zadania").foregroundStyle(Theme.ink)
                            Text("Co robi Claude, kiedy, ile i za ile; Uruchom teraz")
                                .font(.caption)
                                .foregroundStyle(Theme.inkSoft)
                        }
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(Theme.inkSoft)
                    }
                    .contentShape(.rect)
                }
                .buttonStyle(.plain)
            }
            .id("switches")
            if settings.leftover != nil {
                SectionHeader(title: "Okres i zapas", subtitle: "Od kiedy liczy się limit i ile z niego zostaje")
                    .id("leftover")
                Card { leftoverRows }
            }
        }
        .navigationDestination(isPresented: $showReview) { AiReviewView() }
        .task {
            // Batches and the background move on while Konfiguracja is open.
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(20))
                guard !Task.isCancelled else { return }
                await model.loadAiSettings()
            }
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
            Text("Z console.anthropic.com → API Keys.")
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
        if settings.keyFromApp {
            Button("Usuń klucz", role: .destructive) {
                Task { await model.deleteAiKey() }
            }
            .font(.subheadline)
        }
    }

    /// Google's key for the image model (Mateusz 2026-11-01: keys go in
    /// through a field in Konfiguracja, never the server's environment).
    @ViewBuilder
    private var geminiKeyFields: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Klucz API Google (Gemini)").font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                Spacer()
                if settings.geminiKeySet == true, let tail = settings.geminiKeyTail {
                    Label("…\(tail)", systemImage: "checkmark.circle.fill")
                        .font(.subheadline.monospaced())
                        .foregroundStyle(Theme.good)
                }
            }
            SecureField(settings.geminiKeySet == true ? "zapisany · wpisz nowy, by zmienić" : "AIza…", text: $geminiKey)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
            Text("Z aistudio.google.com → API keys. Model graficzny rysuje arkusze analizy kompozycji.")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
        }
        Button {
            Task {
                savingGeminiKey = true
                if await model.saveGeminiKey(geminiKey) { geminiKey = "" }
                savingGeminiKey = false
            }
        } label: {
            HStack {
                Text("Zapisz i sprawdź")
                if savingGeminiKey { ProgressView() }
            }
        }
        .fontWeight(.semibold)
        .disabled(geminiKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || savingGeminiKey)
        if settings.geminiKeySet == true {
            Button("Usuń klucz", role: .destructive) {
                Task { await model.deleteGeminiKey() }
            }
            .font(.subheadline)
        }
    }

    /// What the drawn sheets are and about what they cost.
    static func drawnHint(_ settings: AiSettings) -> String {
        let now = Money.usd(settings.drawnUsd ?? 0.15)
        let batch = Money.usd(settings.drawnBatchUsd ?? 0.075)
        return "Szkic akwarelą i piórkiem z kolorowymi liniami w studium. "
            + "Nowe od razu, ok. \(now) za arkusz; zapisane wcześniej przez Batch, ok. \(batch)."
    }

    /// What stands under the switch: the key missing, why none is drawn
    /// now, or how the saved studies' sheets are getting on.
    static func drawnNote(_ settings: AiSettings, on: Bool) -> (text: String, icon: String, bad: Bool)? {
        guard on else { return nil }
        if settings.geminiKeySet != true {
            return ("Brak klucza Google. Dodasz go w Kluczach i certyfikatach.", "key", true)
        }
        switch settings.geminiError {
        case "no_credit":
            return ("Na koncie Google skończyły się środki. Doładuj je w Google AI Studio.", "exclamationmark.circle", true)
        case "key_rejected":
            return ("Google odrzucił klucz. Wpisz go ponownie w Kluczach i certyfikatach.", "exclamationmark.circle", true)
        case "limit":
            return ("Miesięczny limit Gemini jest wyczerpany, arkusze poczekają.", "pause.circle", true)
        default: break
        }
        let waiting = settings.drawnWaiting ?? 0, batch = settings.drawnInBatch ?? 0
        guard waiting + batch > 0 else { return nil }
        let cost = Money.usd(Double(waiting + batch) * (settings.drawnBatchUsd ?? 0.075))
        return (
            "Zapisane studia bez arkusza: \(waiting + batch), w tym w Batch: \(batch). Razem ok. \(cost).",
            "clock", false
        )
    }

    /// Under Szukanie wyglądem: how many of the museums' works can be found
    /// so, or why none get their numbers now.
    static func looksNote(_ settings: AiSettings, on: Bool) -> (text: String, icon: String, bad: Bool)? {
        guard on else { return nil }
        if settings.looksError != nil {
            return ("Google teraz nie odpowiada, serwer spróbuje ponownie za pół godziny.", "pause.circle", true)
        }
        guard let done = settings.looksDone, let total = settings.looksTotal, total > 0 else { return nil }
        if done >= total { return ("Gotowe: \(Names.works(total)) z muzeów.", "checkmark.circle", false) }
        return ("Gotowe \(done) z \(total) dzieł z muzeów, reszta w tle.", "clock", false)
    }

    // MARK: Switches and money

    /// A switch with its line, and under it what it cost in the last days
    /// (`cost`: its row's key in "Koszty") and how far its work got.
    private func toggle(
        _ title: String, hint: String, value: Bool, cost: String? = nil, costLabel: String? = nil,
        progress: AiSettings.Progress? = nil, update: @escaping (Bool) -> AiSettingsUpdate
    ) -> some View {
        let binding = Binding(
            get: { value },
            set: { new in Task { await model.saveAiSettings(update(new)) } }
        )
        let notes = [cost.flatMap { costNote($0, label: costLabel) }, progress.flatMap(Self.progressNote)]
            .compactMap { $0 }
        return Toggle(isOn: binding) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                Text(hint).font(.caption).foregroundStyle(Theme.inkSoft)
                    .fixedSize(horizontal: false, vertical: true)
                if !notes.isEmpty {
                    Text(notes.joined(separator: " · "))
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(Theme.ink.opacity(0.75))
                        .padding(.top, 1)
                }
            }
        }
        .tint(Theme.ink)
    }

    /// "7 dni: 0,42 USD" for the switch's row in "Koszty" (none: nothing spent).
    private func costNote(_ key: String, label: String?) -> String? {
        guard let days = settings.costDays else { return nil }
        let rows = (settings.claudeCosts ?? []) + (settings.geminiCosts ?? [])
        let usd = rows.first { $0.key == key }?.daysUsd ?? 0
        let what = label.map { "\(days) dni (\($0))" } ?? "\(days) dni"
        return "\(what): \(Self.usd(usd))"
    }

    /// "gotowe 3691 · czeka 9": how far the background got.
    static func progressNote(_ progress: AiSettings.Progress) -> String? {
        var parts = ["gotowe \(count(progress.done))"]
        if progress.preparing { parts.append("przygotowuję pakiet") }
        if progress.batchItems > 0 { parts.append("w pakiecie \(progress.batchDone) z \(progress.batchItems)") }
        if progress.waiting > 0 { parts.append("czeka \(count(progress.waiting))") }
        return parts.joined(separator: " · ")
    }

    /// Money as a line tells it: nothing is "0 USD", under a cent is not
    /// "0,00 USD".
    static func usd(_ value: Double) -> String {
        if value <= 0 { return "0 USD" }
        return value < 0.01 ? "poniżej 1 centa" : Money.usd(value)
    }

    /// "Koszty": each thing's money over the last days and the period so far,
    /// the dearest first, and the sum (Mateusz 2026-11-16: "czytelnie podaj
    /// koszt dla każdej pozycji za ostatnie dni").
    @ViewBuilder
    private func costSection(_ rows: [AiCost], since: String?) -> some View {
        let days = settings.costDays ?? 7
        SectionHeader(title: "Koszty", subtitle: "Ostatnie \(days) dni i cały okres")
        Card {
            if rows.isEmpty {
                Text("Jeszcze nic nie kosztowało.")
                    .font(.subheadline)
                    .foregroundStyle(Theme.inkSoft)
            } else {
                CostTable(rows: Self.sorted(rows), days: days, since: since.map(Self.dayMonth))
            }
        }
    }

    /// The dearest of the last days first, then of the period; "Inne" last.
    static func sorted(_ rows: [AiCost]) -> [AiCost] {
        rows.sorted { a, b in
            if (a.key == "other") != (b.key == "other") { return b.key == "other" }
            if a.daysUsd != b.daysUsd { return a.daysUsd > b.daysUsd }
            return a.periodUsd > b.periodUsd
        }
    }

    /// "2026-11-01" of the month today is in: Gemini's month is the calendar's.
    static func monthStart(_ now: Date = .now) -> String {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC") ?? .current
        let parts = calendar.dateComponents([.year, .month], from: now)
        return String(format: "%04d-%02d-01", parts.year ?? 2026, parts.month ?? 1)
    }

    /// A model's month: its limit to choose, and how much of it is spent.
    @ViewBuilder
    private func spendingRows(
        limit: Double, spent: Double, note: String, update: @escaping (Double) -> AiSettingsUpdate
    ) -> some View {
        let chosen = Binding(
            get: { limit },
            set: { usd in Task { await model.saveAiSettings(update(usd)) } }
        )
        HStack {
            Text("Miesięczny limit").font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
            Spacer()
            Picker("Miesięczny limit", selection: chosen) {
                ForEach(Set(Self.limits + [limit]).sorted(), id: \.self) { usd in
                    Text(Money.usd(usd)).tag(usd)
                }
            }
            .labelsHidden()
            .tint(Theme.ink)
        }
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("W tym okresie").font(.subheadline).foregroundStyle(Theme.ink)
                Spacer()
                Text(Money.usd(spent))
                    .font(.subheadline.monospacedDigit())
                    .foregroundStyle(Theme.inkSoft)
            }
            ProgressView(value: min(spent / max(limit, 0.01), 1))
                .tint(spent >= limit ? Theme.bad : Theme.ink)
            Text(note)
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
        }
    }

    // MARK: The month's rest

    private static let reserves: [Double] = [0, 5, 10, 20, 30, 50]

    /// "Resztka miesiąca na studia" (Mateusz 2026-11-13): in the period's
    /// last days the night orders studies of works the curator found fit
    /// for what the limit leaves above the reserve, then the catalogue's
    /// keywords and Polish texts; through the Batch, telling nobody.
    /// The period and the month's rest's days and reserve; what the rest
    /// goes on is set in Zadania (Mateusz 2026-11-17).
    @ViewBuilder
    private var leftoverRows: some View {
        pickerRow(
            "Dzień odnowienia",
            hint: "Od tego dnia miesiąca liczy się limit i wydatki Claude, tak jak odnawiają się środki na koncie.",
            value: settings.periodDay ?? 1,
            options: Array(1...28),
            label: { "\($0)." }
        ) { AiSettingsUpdate(periodDay: $0) }
        Divider()
        pickerRow(
            "Ostatnie dni okresu",
            hint: "Od kiedy serwer zamawia. W ostatniej dobie już nic, żeby Batch zdążył.",
            value: settings.leftoverDays ?? 3,
            options: Array(2...10),
            label: { "\($0)" }
        ) { AiSettingsUpdate(leftoverDays: $0) }
        Divider()
        pickerRow(
            "Zapas",
            hint: "Tyle zostaje z limitu na resztę okresu i na to, czego serwer nie liczy (np. ten sam klucz gdzie indziej).",
            value: settings.leftoverReserveUsd ?? 10,
            options: Set(Self.reserves + [settings.leftoverReserveUsd ?? 10]).sorted(),
            label: { Money.usd($0) }
        ) { AiSettingsUpdate(leftoverReserveUsd: $0) }
        if let state = settings.leftoverState {
            Divider()
            Label(Self.leftoverNote(state, settings: settings), systemImage: state.open ? "clock" : "calendar")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// "125 323": a count as Polish writes it.
    static func count(_ n: Int) -> String {
        n.formatted(.number.grouping(.automatic).locale(Locale(identifier: "pl_PL")))
    }

    /// "czeka 412 · ok. 4,12 USD · do 540 na noc", what it did this period;
    /// a use with more waiting than a night takes tells the night's part
    /// ("czeka 125 323 · tej nocy 1000, ok. 6,58 USD"), not the whole.
    static func useNote(_ use: LeftoverUse) -> String {
        if !use.able { return "Wyłączone w ustawieniach wyżej." }
        var parts: [String] = []
        if use.key == "studies" {
            parts.append("ok. \(Money.usd(use.eachUsd)) za studium")
            if let waiting = use.waiting, waiting > 0 { parts.append("kandydaci kuratora: \(waiting)") }
        } else if use.waiting == nil && use.isCatalogueText {
            parts.append("liczę, ile czeka w katalogu…")
        } else if let waiting = use.waiting {
            if waiting == 0 {
                parts.append("nic nie czeka")
            } else if let tonight = use.tonight, let usd = use.tonightUsd, tonight < waiting {
                parts.append("czeka \(count(waiting)) · tej nocy \(count(tonight)), ok. \(Money.usd(usd))")
            } else if let usd = use.waitingUsd {
                parts.append("czeka \(count(waiting)) · ok. \(Money.usd(usd))")
            }
        }
        if let night = use.aNight, use.aNightOptions == nil { parts.append("do \(count(night)) na noc") }
        if use.done > 0 { parts.append("w tym okresie \(use.done), ok. \(Money.usd(use.doneUsd))") }
        return parts.joined(separator: " · ")
    }

    private func pickerRow<Value: Hashable>(
        _ title: String, hint: String, value: Value, options: [Value],
        label: @escaping (Value) -> String, update: @escaping (Value) -> AiSettingsUpdate
    ) -> some View {
        let chosen = Binding(
            get: { value },
            set: { new in Task { await model.saveAiSettings(update(new)) } }
        )
        return HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).foregroundStyle(Theme.ink)
                Text(hint).font(.caption).foregroundStyle(Theme.inkSoft)
            }
            Spacer()
            Picker(title, selection: chosen) {
                ForEach(options, id: \.self) { option in
                    Text(label(option)).tag(option)
                }
            }
            .labelsHidden()
            .tint(Theme.ink)
        }
    }

    /// "28.11" of "2026-11-28".
    static func dayMonth(_ iso: String) -> String {
        let parts = iso.split(separator: "-")
        guard parts.count == 3 else { return iso }
        return "\(parts[2]).\(parts[1])"
    }

    /// Where the month's rest is: when it begins, or what it does now.
    static func leftoverNote(_ state: LeftoverState, settings: AiSettings) -> String {
        var parts: [String] = []
        let each = "\(Money.usd(state.perStudyUsd)) za studium" + (state.measured ? " (zmierzone)" : "")
        if state.open {
            parts.append("Teraz: wolne ok. \(Money.usd(state.freeUsd)), ok. \(each).")
        } else if let end = settings.periodEnd {
            parts.append("Zamawia od \(dayMonth(state.opens)) do \(dayMonth(state.closes)), okres kończy się \(dayMonth(end)). Ok. \(each).")
        }
        if state.ordered > 0 {
            var line = "W tym okresie zamówione: \(state.ordered), gotowe: \(state.made)"
            if state.inFlight > 0 { line += ", w drodze: \(state.inFlight)" }
            if state.failed > 0 { line += ", nieudane: \(state.failed)" }
            parts.append(line + ".")
        }
        if state.candidates > 0 {
            parts.append("Kandydaci kuratora czekający na studium: \(state.candidates).")
        }
        return parts.joined(separator: " ")
    }
}

/// "Koszty": what each thing cost over the last days and the period so far,
/// in USD, and the sum under a rule.
struct CostTable: View {
    let rows: [AiCost]
    let days: Int
    /// "1.11": the period's first day.
    let since: String?

    var body: some View {
        Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 9) {
            GridRow {
                Text("USD")
                Text("\(days) dni").gridColumnAlignment(.trailing)
                Text(since.map { "od \($0)" } ?? "okres").gridColumnAlignment(.trailing)
            }
            .font(.caption.weight(.semibold))
            .foregroundStyle(Theme.inkSoft)
            ForEach(rows) { row in
                GridRow {
                    Text(row.label)
                        .font(.subheadline)
                        .foregroundStyle(Theme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    amount(row.daysUsd).foregroundStyle(Theme.ink)
                    amount(row.periodUsd).foregroundStyle(Theme.inkSoft)
                }
            }
            Divider()
            GridRow {
                Text("Razem").font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                amount(rows.map(\.daysUsd).reduce(0, +)).fontWeight(.semibold).foregroundStyle(Theme.ink)
                amount(rows.map(\.periodUsd).reduce(0, +)).foregroundStyle(Theme.inkSoft)
            }
        }
    }

    private func amount(_ usd: Double) -> some View {
        Text(Self.short(usd))
            .font(.subheadline.monospacedDigit())
            .lineLimit(1)
            .fixedSize()
    }

    /// "0,42", "<0,01", "–": the table's own column says USD.
    static func short(_ usd: Double) -> String {
        if usd <= 0 { return "–" }
        if usd < 0.01 { return "<0,01" }
        return usd.formatted(.number.precision(.fractionLength(2)).locale(Locale(identifier: "pl_PL")))
    }
}

enum Money {
    /// "0,42 USD".
    static func usd(_ value: Double) -> String {
        value.formatted(.currency(code: "USD").locale(Locale(identifier: "pl_PL")))
    }
}
