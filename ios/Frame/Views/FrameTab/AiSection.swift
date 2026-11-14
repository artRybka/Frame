import SwiftUI

/// Konfiguracja → Claude: Anthropic's API working for the library. What the
/// model may do, the monthly limit and how far it got; the key is in
/// Konfiguracja → Klucze i certyfikaty (`part: .key`). The models are fixed
/// per task on the server: Haiku for keywords and translations, Sonnet for
/// notes on works without a description.
///
/// Konfiguracja → Gemini (`part: .gemini`): Google's image model, with a
/// month's limit and spending of its own (Mateusz 2026-11-12 23:20: "Dla
/// Gemini trzeba dać osobny segment w Konfiguracja (tak jak Claude) i tam
/// ustawić osobno limit").
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
    @State private var estimating = false
    @State private var estimate: AiEstimate?
    @State private var askRefresh = false
    @State private var startingRefresh = false

    private static let limits: [Double] = [1, 2, 5, 10, 20, 50, 100, 150, 200]

    private var budgetLeft: Double { max(settings.monthlyLimitUsd - settings.spentUsd, 0) }

    private var keywordsOn: Bool { settings.keywordsArtworks || settings.keywordsPhotos }

    var body: some View {
        switch part {
        case .settings: settingsBody
        case .key: keyBody
        case .gemini: geminiBody
        }
    }

    private var geminiBody: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Gemini (Google)", subtitle: "Arkusze kompozycji, etapy malowania i szukanie wyglądem")
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
                        note: "Po przekroczeniu limitu serwer nie pyta modelu graficznego do końca miesiąca. Wydatki Claude liczą się osobno."
                    ) { AiSettingsUpdate(geminiMonthlyLimitUsd: $0) }
                    if let drawn = settings.drawn {
                        Divider()
                        toggle(
                            "Arkusze kompozycji z modelu graficznego",
                            hint: Self.drawnHint(settings),
                            value: drawn
                        ) { AiSettingsUpdate(drawn: $0) }
                        if settings.geminiKeySet == true, let note = Self.drawnNote(settings, on: drawn) {
                            Label(note.text, systemImage: note.icon)
                                .font(.caption)
                                .foregroundStyle(note.bad ? Theme.bad : Theme.inkSoft)
                        }
                    }
                    if let looks = settings.looks {
                        Divider()
                        toggle(
                            "Szukanie wyglądem",
                            hint: "Szukaj po tym, jak dzieło wygląda: opisem, zdjęciem i „Podobne wyglądem”. "
                                + "Dzieła z muzeów przygotowuje raz, przez Batch (ok. 0,006 centa za dzieło), pytanie to ułamek centa. Twoje zdjęcia nie trafiają do Google.",
                            value: looks
                        ) { AiSettingsUpdate(looks: $0) }
                        if settings.geminiKeySet == true, let note = Self.looksNote(settings, on: looks) {
                            Label(note.text, systemImage: note.icon)
                                .font(.caption)
                                .foregroundStyle(note.bad ? Theme.bad : Theme.inkSoft)
                        }
                    }
                } else {
                    Label("Ten serwer nie ma jeszcze modelu graficznego. Zaktualizuj serwer.", systemImage: "arrow.down.circle")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
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
            SectionHeader(title: "Model językowy (Claude)", subtitle: "Słowa kluczowe i polskie opisy dzieł")
            Card {
                if !settings.keySet {
                    Label("Brak klucza Anthropic. Dodasz go w Kluczach i certyfikatach.", systemImage: "key")
                        .font(.caption)
                        .foregroundStyle(Theme.warn)
                    Divider()
                }
                spending
                Divider()
                toggle(
                    "Polskie tytuły i opisy",
                    hint: "Tłumaczy Haiku. Dziełom bez opisu notkę pisze Sonnet.",
                    value: settings.plText
                ) { AiSettingsUpdate(plText: $0) }
                Divider()
                toggle(
                    "Słowa kluczowe dla dzieł",
                    hint: "Dla Szukaj i inteligentnych playlist.",
                    value: settings.keywordsArtworks
                ) { AiSettingsUpdate(keywordsArtworks: $0) }
                Divider()
                toggle(
                    "Słowa kluczowe dla zdjęć",
                    hint: "Miniatury zdjęć idą do Anthropic.",
                    value: settings.keywordsPhotos
                ) { AiSettingsUpdate(keywordsPhotos: $0) }
                if let daily = settings.daily {
                    Divider()
                    toggle(
                        "Studium dnia",
                        hint: "Raz dziennie na górze Odkrywaj, ok. 4 USD miesięcznie.",
                        value: daily
                    ) { AiSettingsUpdate(daily: $0) }
                }
                if let searchWords = settings.searchWords {
                    Divider()
                    toggle(
                        "Tłumaczenie słów w Szukaj",
                        hint: "Np. gitara jako guitar dla muzeów zagranicznych, a opis wyglądu jako hasła dla muzeów.",
                        value: searchWords
                    ) { AiSettingsUpdate(searchWords: $0) }
                }
                if let curator = settings.curator {
                    Divider()
                    toggle(
                        "Kurator Odkrywaj",
                        hint: "Dwie karty w „Dziś dla Ciebie”, do ok. 3 USD miesięcznie.",
                        value: curator
                    ) { AiSettingsUpdate(curator: $0) }
                }
                if let twinsJudge = settings.twinsJudge {
                    Divider()
                    toggle(
                        "Sędzia powtórek",
                        hint: "W nocy ocenia kopie i detale, których nie rozpoznały obrazy. Grosze miesięcznie.",
                        value: twinsJudge
                    ) { AiSettingsUpdate(twinsJudge: $0) }
                }
                if let gatekeeper = settings.gatekeeper {
                    Divider()
                    toggle(
                        "Strażnik katalogu",
                        hint: "W nocy odkłada znaczki, strony z tekstem i zdjęcia sal z Commons i Europeany. Do ok. 0,6 USD miesięcznie.",
                        value: gatekeeper
                    ) { AiSettingsUpdate(gatekeeper: $0) }
                }
                if let crops = settings.crops {
                    Divider()
                    toggle(
                        "Kadrowanie zdjęć dzieł",
                        hint: "Przycina zdjęcia z muzeów do samego dzieła, gdy widać ramę, sztalugę albo tło. Haiku wybiera dzieła, Opus ustawia narożniki. Ok. 1–2 centy za przycięte dzieło.",
                        value: crops
                    ) { AiSettingsUpdate(crops: $0) }
                }
                if let audit = settings.audit {
                    Divider()
                    toggle(
                        "Nocny przegląd",
                        hint: "Co noc 30 losowych dzieł: tytuł, data, polski opis i obraz. Ok. 0,3 USD miesięcznie.",
                        value: audit
                    ) { AiSettingsUpdate(audit: $0) }
                }
                if let journey = settings.journey {
                    Divider()
                    toggle(
                        "Droga dzieła",
                        hint: "W studium dzieła droga od pracowni do muzeum, z danych muzeum. Ok. 0,2 centa za dzieło.",
                        value: journey
                    ) { AiSettingsUpdate(journey: $0) }
                }
                if let webFacts = settings.webFacts {
                    Divider()
                    toggle(
                        "Fakty z sieci w studium",
                        hint: "Przed napisaniem studium Claude szuka w sieci badań, losów i wystaw dzieła i wplata je w tekst. Ok. 2–10 centów za studium.",
                        value: webFacts
                    ) { AiSettingsUpdate(webFacts: $0) }
                }
                if let stages = settings.stages {
                    Divider()
                    toggle(
                        "Jak powstawał (Studium)",
                        hint: "Gdy w sieci jest badanie techniczne dzieła, Claude opisuje w kilku zdaniach, jak powstawało. Ułamek centa za dzieło.",
                        value: stages
                    ) { AiSettingsUpdate(stages: $0) }
                }
                if let refresh = settings.studyRefresh,
                   refresh.running || refresh.waiting > 0 || refresh.found > 0 {
                    Divider()
                    studyRefreshRow(refresh)
                }
                if let count = settings.reviewCount {
                    Divider()
                    NavigationLink {
                        AiReviewView()
                    } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Do sprawdzenia").foregroundStyle(Theme.ink)
                                Text("Co strażnik odłożył i co znalazł nocny przegląd.")
                                    .font(.caption)
                                    .foregroundStyle(Theme.inkSoft)
                            }
                            Spacer()
                            if count > 0 {
                                Text("\(count)")
                                    .font(.subheadline.monospacedDigit())
                                    .foregroundStyle(Theme.inkSoft)
                            }
                        }
                    }
                    .buttonStyle(.plain)
                }
                Divider()
                progress
            }
            if settings.leftover != nil {
                SectionHeader(title: "Resztka miesiąca", subtitle: "Studia z tego, co zostaje z limitu")
                Card { leftoverRows }
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
        return "Szkic akwarelą i piórkiem oraz kolorowe linie rysuje model Google. "
            + "Nowe studium od razu, ok. \(now); zapisane wcześniej przez Batch, ok. \(batch) za arkusz."
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

    private var spending: some View {
        spendingRows(
            limit: settings.monthlyLimitUsd, spent: settings.spentUsd,
            note: "Po przekroczeniu limitu serwer nie pyta modelu do końca miesiąca."
        ) { AiSettingsUpdate(monthlyLimitUsd: $0) }
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
                Text("W tym miesiącu").font(.subheadline).foregroundStyle(Theme.ink)
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
    @ViewBuilder
    private var leftoverRows: some View {
        toggle(
            "Studia z resztki miesiąca",
            hint: "W ostatnich dniach okresu to, co zostaje z limitu ponad zapas, idzie nocą na nowe studia: najpierw dzieła typowane przez kuratora Studium dnia, potem według jego kryteriów, zaczynając od Ulubionych i playlist. Co zostanie, idzie na słowa kluczowe i polskie opisy katalogu. Przez Batch, bez powiadomień.",
            value: settings.leftover ?? false
        ) { AiSettingsUpdate(leftover: $0) }
        Divider()
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

    // MARK: Earlier studies

    /// "Uzupełnij wcześniejsze studia" (Mateusz 2026-11-13): the studies
    /// written before the facts from the web get them through Claude's
    /// Batch; only those the facts add much to get a new text.
    @ViewBuilder
    private func studyRefreshRow(_ refresh: StudyRefresh) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Uzupełnij wcześniejsze studia").foregroundStyle(Theme.ink)
            Text(refreshHint(refresh))
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
                .fixedSize(horizontal: false, vertical: true)
            if !refresh.running && refresh.waiting > 0 {
                Button {
                    askRefresh = true
                } label: {
                    HStack {
                        Text("Uzupełnij \(refresh.waiting) \(Names.studies(refresh.waiting))")
                        if startingRefresh { ProgressView() }
                    }
                }
                .fontWeight(.semibold)
                .disabled(!settings.keySet || startingRefresh)
                .confirmationDialog(
                    "Uzupełnić \(refresh.waiting) \(Names.studies(refresh.waiting))?",
                    isPresented: $askRefresh,
                    titleVisibility: .visible
                ) {
                    Button("Uzupełnij") {
                        Task {
                            startingRefresh = true
                            await model.startStudyRefresh()
                            startingRefresh = false
                        }
                    }
                    Button("Anuluj", role: .cancel) {}
                } message: {
                    Text("Fakty ok. \(Money.usd(refresh.factsUsd)), nowe teksty do \(Money.usd(refresh.rewriteUsd)), w pakietach Anthropic. Wyniki w ciągu kilku godzin.")
                }
            }
        }
    }

    private func refreshHint(_ refresh: StudyRefresh) -> String {
        if refresh.running {
            if refresh.rewriting > 0 {
                return "W toku: nowe teksty z faktami dla \(refresh.rewriting) \(Self.ofStudies(refresh.rewriting)). Wyniki w ciągu kilku godzin."
            }
            return "W toku: Claude szuka faktów do \(refresh.asked) \(Self.ofStudies(refresh.asked)). Wyniki w ciągu kilku godzin."
        }
        var done = ""
        if refresh.found > 0 {
            done = " Dotąd: fakty do \(refresh.found) \(Self.ofStudies(refresh.found)), nowe teksty: \(refresh.rewritten) (\(Money.usd(refresh.spentUsd)))."
        }
        if refresh.waiting == 0 {
            return "Wszystkie studia mają już fakty z sieci." + done
        }
        return "\(refresh.waiting) \(Names.studies(refresh.waiting)) bez faktów z sieci. Claude znajdzie, czego w nich brakuje, i przepisze tylko te, którym fakty wiele dodadzą. Kompozycja, detale i Droga dzieła zostają." + done
    }

    /// "studium" or "studiów" after "do 1", "dla 5".
    private static func ofStudies(_ count: Int) -> String { count == 1 ? "studium" : "studiów" }

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
        .task {
            // CI screenshots: where the dialog points.
            guard LaunchRoute.confirm == "describe" else { return }
            try? await Task.sleep(for: .seconds(3))
            estimate = AiEstimate(items: 19022, usd: 2.66)
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
        Text("Dokłada cały katalog Odkrywaj, taniej, w pakietach.")
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
            lines.append("Czeka na noc: \(progress.waiting) (w pakiecie, za pół ceny)")
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
