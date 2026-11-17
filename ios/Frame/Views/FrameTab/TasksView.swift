import SwiftUI

/// Konfiguracja → Zadania (Mateusz 2026-11-17: "przebudowania całego menu
/// „Claude” oraz „Zadania nocne” i wprowadzenia prostego konfigurowania
/// zadań planowanych i na żądanie. Z ustawieniem ilości, kwoty, czasu i
/// trybu"; he chose the list grouped by when, each task with its own page):
/// the month's money on top, what runs now, then every task by when it
/// runs. The switches of what Claude does for each work stand in their
/// groups; the tasks of the month's rest open a page of their own (when,
/// how many and for how much, the mode, "Uruchom teraz"). The server's own
/// night work is one row, its page as before.
struct TasksSection: View {
    @Environment(AppModel.self) private var model
    let settings: AiSettings

    private var uses: [LeftoverUse] { settings.leftoverState?.uses ?? [] }

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            if !settings.keySet {
                Label("Brak klucza Anthropic. Dodasz go w Kluczach i certyfikatach.", systemImage: "key")
                    .font(.caption)
                    .foregroundStyle(Theme.warn)
            }
            BudgetCard(settings: settings)
            ForEach(uses.filter { $0.run?.running == true }) { use in
                Card {
                    Label(
                        use.run?.night == true ? "Teraz, nocą: \(use.label)" : "Teraz: \(use.label)",
                        systemImage: "bolt.fill"
                    )
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Theme.ink)
                    OnDemandRow(use: use, free: settings.leftoverState?.nowFreeUsd)
                }
            }
            group("Od razu", "Dla każdego nowego dzieła i tego, czego szukasz") {
                switches(Self.instant(settings))
            }
            group("Odkrywaj", "Studium dnia i propozycje kuratora") {
                switches(Self.discover(settings))
            }
            .id("study")
            group("Co noc", "Od 1:30, w pakietach Batch za pół ceny, w tej kolejności") {
                switches(Self.night(settings))
                taskRows(uses.filter { $0.when == .night }, divided: true)
            }
            .id("night")
            group("Z resztki okresu", restSubtitle) {
                restSwitch
                taskRows(uses.filter { ($0.when ?? .rest) == .rest }, divided: true)
            }
            .id("rest")
            let asked = uses.filter { $0.when == .demand }
            if !asked.isEmpty {
                group("Tylko na żądanie", "Nic samo; uruchamiasz na stronie zadania") {
                    taskRows(asked, divided: false)
                }
            }
            let off = uses.filter { $0.when == .off }
            if !off.isEmpty {
                group("Wyłączone", "Ani nocą, ani na żądanie") {
                    taskRows(off, divided: false)
                }
                .id("off")
            }
            group("Bez Claude", "Praca samego serwera, bez kosztu") {
                ServerWorkRow()
            }
            .id("server")
        }
        .navigationDestination(for: TaskLink.self) { link in TaskPage(key: link.key) }
        .task {
            // Batches and runs move on while the page is open; a run going
            // is followed more closely.
            while !Task.isCancelled {
                let going = model.aiSettings?.leftoverState?.uses?.contains { $0.run?.running == true } == true
                try? await Task.sleep(for: .seconds(going ? 5 : 20))
                guard !Task.isCancelled else { return }
                await model.loadAiSettings()
            }
        }
    }

    private func group(
        _ title: String, _ subtitle: String, @ViewBuilder content: () -> some View
    ) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: title, subtitle: subtitle)
            Card { content() }
        }
    }

    // MARK: The month's rest

    private var restSubtitle: String {
        guard settings.leftover == true else { return "Wyłączone: włączysz niżej" }
        let days = settings.leftoverDays ?? 3
        if let state = settings.leftoverState {
            return "Ostatnie \(days) dni okresu, od \(AiSection.dayMonth(state.opens)), z tego, co zostaje ponad zapas"
        }
        return "Ostatnie \(days) dni okresu, z tego, co zostaje ponad zapas"
    }

    private var restSwitch: some View {
        Toggle(isOn: Binding(
            get: { settings.leftover ?? false },
            set: { on in Task { await model.saveAiSettings(AiSettingsUpdate(leftover: on)) } }
        )) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Wykorzystaj resztkę miesiąca")
                Text("Ile dni i jaki zapas, ustawisz na stronie Claude.")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
            }
        }
        .tint(Theme.ink)
    }

    // MARK: Rows

    @ViewBuilder
    private func switches(_ rows: [SwitchTask]) -> some View {
        ForEach(Array(rows.enumerated()), id: \.element.title) { index, row in
            if index > 0 { Divider() }
            TaskSwitchRow(row: row, settings: settings)
        }
    }

    @ViewBuilder
    private func taskRows(_ shown: [LeftoverUse], divided: Bool) -> some View {
        ForEach(Array(shown.enumerated()), id: \.element.key) { index, use in
            if divided || index > 0 { Divider() }
            TaskRow(use: use, settings: settings)
                .contextMenu { orderMenu(use) }
        }
    }

    /// "Wyżej", "Niżej": the order the night pays the tasks in.
    @ViewBuilder
    private func orderMenu(_ use: LeftoverUse) -> some View {
        let order = uses.map(\.key)
        if let index = order.firstIndex(of: use.key) {
            if index > 0 {
                Button("Wyżej", systemImage: "arrow.up") { move(index, to: index - 1, in: order) }
            }
            if index < order.count - 1 {
                Button("Niżej", systemImage: "arrow.down") { move(index, to: index + 1, in: order) }
            }
        }
    }

    private func move(_ from: Int, to: Int, in order: [String]) {
        var order = order
        order.swapAt(from, to)
        Task { await model.saveAiSettings(AiSettingsUpdate(leftoverOrder: order)) }
    }

    // MARK: The switches, by when they work

    static func instant(_ s: AiSettings) -> [SwitchTask] {
        var rows = [
            SwitchTask(
                title: "Polskie tytuły i opisy",
                value: s.plText, cost: "pl_text"
            ) { AiSettingsUpdate(plText: $0) },
            SwitchTask(
                title: "Słowa kluczowe dla dzieł",
                value: s.keywordsArtworks, cost: "keywords", costLabel: "dzieła i zdjęcia"
            ) { AiSettingsUpdate(keywordsArtworks: $0) },
            SwitchTask(
                title: "Słowa kluczowe dla zdjęć",
                value: s.keywordsPhotos
            ) { AiSettingsUpdate(keywordsPhotos: $0) },
        ]
        if let words = s.searchWords {
            rows.append(SwitchTask(
                title: "Tłumaczenie słów w Szukaj",
                value: words, cost: "search_words"
            ) { AiSettingsUpdate(searchWords: $0) })
        }
        // Gemini's looks of each work (Mateusz 2026-11-17: "Czy tu nie
        // brakuje tworzenia „odcisków” z Gemini?"); its page keeps it too
        if let looks = s.looks {
            rows.append(SwitchTask(
                title: "Odciski wyglądu (Gemini)",
                value: looks, cost: "looks"
            ) { AiSettingsUpdate(looks: $0) })
        }
        return rows
    }

    /// Odkrywaj (Mateusz 2026-11-17: "sprowadźmy do 2 przełączników -
    /// studium dnia oraz propozycji kuratora. Zadania składające się na
    /// studium są z nim ściśle powiązane i nie da się ich wyłączyć"): facts
    /// from the web, how it was painted and its way to the museum are the
    /// study's own, always on (`ai.config.STUDY_PARTS` on the server).
    static func discover(_ s: AiSettings) -> [SwitchTask] {
        let rows: [SwitchTask?] = [
            s.daily.map {
                SwitchTask(title: "Studium dnia", value: $0, cost: "daily") { AiSettingsUpdate(daily: $0) }
            },
            s.curator.map {
                SwitchTask(title: "Propozycje kuratora", value: $0, cost: "curator") { AiSettingsUpdate(curator: $0) }
            },
        ]
        return rows.compactMap { $0 }
    }

    static func night(_ s: AiSettings) -> [SwitchTask] {
        let rows: [SwitchTask?] = [
            s.gatekeeper.map {
                SwitchTask(
                    title: "Strażnik katalogu",
                    value: $0, cost: "gatekeeper"
                ) { AiSettingsUpdate(gatekeeper: $0) }
            },
            s.twinsJudge.map {
                SwitchTask(
                    title: "Sędzia powtórek",
                    value: $0, cost: "twins_judge"
                ) { AiSettingsUpdate(twinsJudge: $0) }
            },
            s.crops.map {
                SwitchTask(
                    title: "Kadrowanie zdjęć dzieł",
                    value: $0, cost: "crops"
                ) { AiSettingsUpdate(crops: $0) }
            },
            s.varnishBlue.map {
                SwitchTask(
                    title: "Błękit pod werniksem",
                    value: $0, cost: "varnish_blue"
                ) { AiSettingsUpdate(varnishBlue: $0) }
            },
            s.audit.map {
                SwitchTask(
                    title: "Nocny przegląd",
                    value: $0, cost: "audit"
                ) { AiSettingsUpdate(audit: $0) }
            },
        ]
        return rows.compactMap { $0 }
    }

    // MARK: Words

    /// "10 USD" of 10, "2,50 USD" of 2.5.
    static func amount(_ usd: Double) -> String {
        usd == usd.rounded() ? "\(Int(usd)) USD" : Money.usd(usd)
    }

    /// What the list's chip says of when a task runs.
    static func whenChip(_ when: TaskWhen) -> String {
        switch when {
        case .rest: "Resztka okresu"
        case .night: "Co noc"
        case .demand: "Na żądanie"
        case .off: "Wyłączone"
        }
    }

    /// "noc do 10 USD · okres do 50 USD · czeka 125 323 · w okresie 13,16 USD".
    static func line(_ use: LeftoverUse) -> String {
        guard use.able else { return "Wyłączone przełącznikiem wyżej." }
        var parts: [String] = []
        let when = use.when ?? .rest
        if when == .rest || when == .night {
            if let night = use.nightUsd { parts.append("noc do \(amount(night))") }
            if let period = use.periodUsd { parts.append("okres do \(amount(period))") }
        }
        if use.key == "studies" {
            if let waiting = use.waiting, waiting > 0 { parts.append("kandydaci \(AiSection.count(waiting))") }
        } else if let waiting = use.waiting {
            parts.append(waiting == 0 ? "nic nie czeka" : "czeka \(AiSection.count(waiting))")
        } else if use.isCatalogueText {
            parts.append("liczę, ile czeka…")
        }
        if let spent = use.periodSpentUsd, spent > 0 {
            parts.append("w okresie \(AiSection.usd(spent))")
        }
        return parts.joined(separator: " · ")
    }
}

/// A task's page on the stack of Konfiguracja.
struct TaskLink: Hashable {
    let key: String
}

/// A switch of what Claude does, as the list shows it.
/// A switch in Zadania: its name and what it cost, nothing more (Mateusz
/// 2026-11-17: "Nie dodawaj eksplikacji pod pozycjami - same nazwy i ew.
/// koszt").
struct SwitchTask {
    let title: String
    let value: Bool
    /// Its row's key in "Koszty", and how that row names what it counts.
    var cost: String? = nil
    var costLabel: String? = nil
    let update: (Bool) -> AiSettingsUpdate
}

/// A switch, and under it what it cost in the last days.
private struct TaskSwitchRow: View {
    @Environment(AppModel.self) private var model
    let row: SwitchTask
    let settings: AiSettings

    var body: some View {
        Toggle(isOn: Binding(
            get: { row.value },
            set: { new in Task { await model.saveAiSettings(row.update(new)) } }
        )) {
            VStack(alignment: .leading, spacing: 2) {
                Text(row.title)
                if let costNote {
                    Text(costNote)
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(Theme.ink.opacity(0.75))
                        .padding(.top, 1)
                }
            }
        }
        .tint(Theme.ink)
    }

    /// "7 dni: 0,42 USD".
    private var costNote: String? {
        guard let key = row.cost, let days = settings.costDays else { return nil }
        // Claude's rows, or Gemini's (the looks)
        let rows = (settings.claudeCosts ?? []) + (settings.geminiCosts ?? [])
        let usd = rows.first { $0.key == key }?.daysUsd ?? 0
        let what = row.costLabel.map { "\(days) dni (\($0))" } ?? "\(days) dni"
        return "\(what): \(AiSection.usd(usd))"
    }
}

/// A task of the month's rest in the list: its name, when and how it runs,
/// its amounts and what waits; it opens its page.
private struct TaskRow: View {
    let use: LeftoverUse
    let settings: AiSettings

    var body: some View {
        NavigationLink(value: TaskLink(key: use.key)) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(use.label)
                        .foregroundStyle(running ? Theme.ink : (use.able ? Theme.ink : Theme.inkSoft))
                    HStack(spacing: 4) {
                        TaskChip(text: TasksSection.whenChip(when), strong: when != .off && use.able)
                        if when == .rest || when == .night {
                            TaskChip(text: use.mode == .normal ? "Zwykły" : "Batch ½")
                            if let night = use.aNight { TaskChip(text: "do \(AiSection.count(night))") }
                        }
                        if running { TaskChip(text: "Teraz", strong: true) }
                    }
                    let line = TasksSection.line(use)
                    if !line.isEmpty {
                        Text(line)
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(Theme.inkSoft)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                Spacer(minLength: 8)
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Theme.inkSoft)
                    .padding(.top, 4)
            }
            .padding(.vertical, 2)
            .contentShape(.rect)
        }
        .buttonStyle(.plain)
    }

    private var when: TaskWhen { use.when ?? (use.on ? .rest : .off) }
    private var running: Bool { use.run?.running == true }
}

/// "Co noc", "Batch ½", "do 540".
struct TaskChip: View {
    let text: String
    var strong = false

    var body: some View {
        Text(text)
            .font(.caption2.weight(.semibold))
            .lineLimit(1)
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .foregroundStyle(strong ? Theme.paper : Theme.ink)
            .background(strong ? Theme.ink : Theme.mat, in: Capsule())
    }
}

/// The server's own night work, its page as before.
private struct ServerWorkRow: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        NavigationLink(value: SettingsPage.night) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Prace serwera co noc").foregroundStyle(Theme.ink)
                    Text("Nowe dzieła z muzeów, pliki, kopie razem, ostrzejsze kopie, Odkrywaj i Propozycje dnia.")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .fixedSize(horizontal: false, vertical: true)
                    if let note {
                        Text(note.text)
                            .font(.caption)
                            .foregroundStyle(note.warn ? Theme.warn : Theme.ink.opacity(0.75))
                    }
                }
                Spacer(minLength: 8)
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Theme.inkSoft)
                    .padding(.top, 4)
            }
            .contentShape(.rect)
        }
        .buttonStyle(.plain)
    }

    private var note: (text: String, warn: Bool)? {
        guard let night = model.nightTasks else { return nil }
        if let running = night.running {
            return ("Teraz: \(night.label(running.current) ?? "trwa")", false)
        }
        if night.tasks.contains(where: { $0.last?.failed == true }) { return ("Ostatnio był błąd", true) }
        return nil
    }
}

/// The period's money: spent, ordered and held, free, and the reserve.
private struct BudgetCard: View {
    let settings: AiSettings

    var body: some View {
        let limit = max(settings.monthlyLimitUsd, 0.01)
        let spent = min(settings.spentUsd, limit)
        let planned = min(settings.leftoverState?.plannedUsd ?? 0, max(limit - spent, 0))
        let reserve = min(settings.leftoverReserveUsd ?? 0, max(limit - spent - planned, 0))
        let free = max(limit - spent - planned - reserve, 0)
        Card {
            HStack(alignment: .firstTextBaseline) {
                Text(period).font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                Spacer()
                Text("limit \(Money.usd(settings.monthlyLimitUsd))")
                    .font(.subheadline)
                    .foregroundStyle(Theme.inkSoft)
            }
            GeometryReader { geo in
                let width = geo.size.width
                HStack(spacing: 0) {
                    Rectangle().fill(spentColor).frame(width: width * CGFloat(spent / limit))
                    Rectangle().fill(Theme.ink.opacity(0.4)).frame(width: width * CGFloat(planned / limit))
                    Rectangle().fill(Theme.mat)
                    Rectangle().fill(Theme.warn.opacity(0.55)).frame(width: width * CGFloat(reserve / limit))
                }
                .clipShape(Capsule())
            }
            .frame(height: 10)
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 14) {
                    legend(spentColor, "wydane \(Money.usd(settings.spentUsd))")
                    if planned > 0.004 { legend(Theme.ink.opacity(0.4), "zamówione \(Money.usd(planned))") }
                }
                HStack(spacing: 14) {
                    legend(Theme.mat, "wolne \(Money.usd(free))")
                    if reserve > 0 { legend(Theme.warn.opacity(0.55), "zapas \(Money.usd(reserve))") }
                }
            }
            .font(.caption.monospacedDigit())
            .foregroundStyle(Theme.inkSoft)
            Divider()
            NavigationLink(value: SettingsPage.ai) {
                HStack {
                    Text("Limit, okres, zapas i koszty").foregroundStyle(Theme.ink)
                    Spacer()
                    Image(systemName: "chevron.right")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(Theme.inkSoft)
                }
                .font(.subheadline)
                .contentShape(.rect)
            }
            .buttonStyle(.plain)
        }
    }

    private var spentColor: Color { settings.spentUsd >= settings.monthlyLimitUsd ? Theme.bad : Theme.ink }

    private var period: String {
        guard let start = settings.periodStart, let end = settings.periodEnd else { return "Ten okres" }
        return "Okres \(AiSection.dayMonth(start)) – \(AiSection.dayMonth(end))"
    }

    private func legend(_ color: Color, _ text: String) -> some View {
        HStack(spacing: 5) {
            Circle().fill(color).frame(width: 8, height: 8)
                .overlay(Circle().strokeBorder(Theme.hairline))
            Text(text)
        }
    }
}

/// One task of the month's rest: what it is and what waits, when it runs,
/// how many and for how much, how it asks, and "Uruchom teraz".
struct TaskPage: View {
    @Environment(AppModel.self) private var model
    let key: String

    private var settings: AiSettings? { model.aiSettings }
    private var use: LeftoverUse? { settings?.leftoverState?.uses?.first { $0.key == key } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                if let settings, let use {
                    content(settings, use)
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 40)
                }
            }
            .pageWidth()
            .padding(.horizontal, Theme.gutter)
            .padding(.top, 8)
            .padding(.bottom, 40)
        }
        .paperPage()
        .navigationTitle(use?.label ?? "Zadanie")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            while !Task.isCancelled {
                let going = use?.run?.running == true
                try? await Task.sleep(for: .seconds(going ? 5 : 20))
                guard !Task.isCancelled else { return }
                await model.loadAiSettings()
            }
        }
    }

    @ViewBuilder
    private func content(_ settings: AiSettings, _ use: LeftoverUse) -> some View {
        let when = use.when ?? (use.on ? .rest : .off)
        Card {
            Text(use.about)
                .font(.subheadline)
                .foregroundStyle(Theme.inkSoft)
                .fixedSize(horizontal: false, vertical: true)
            HStack(alignment: .top) {
                stat(waitingText(use), use.key == "studies" ? "kandydaci" : "czeka")
                stat(AiSection.count(use.done), "w tym okresie")
                stat(AiSection.usd(use.periodSpentUsd ?? use.doneUsd), "koszt w okresie")
            }
            if !use.able {
                Label("Wyłączone przełącznikiem na liście Zadań.", systemImage: "exclamationmark.circle")
                    .font(.caption)
                    .foregroundStyle(Theme.warn)
            }
        }
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: "Kiedy")
            Card {
                let choices = TaskWhen.allCases.filter { $0 != .demand || use.nowEachUsd != nil }
                ForEach(Array(choices.enumerated()), id: \.element) { index, choice in
                    if index > 0 { Divider() }
                    whenRow(choice, chosen: when, settings: settings)
                }
            }
        }
        .id("when")
        if when == .rest || when == .night {
            VStack(alignment: .leading, spacing: 10) {
                SectionHeader(title: "Ile i za ile", subtitle: "Pierwsze, co się skończy, zatrzymuje zadanie")
                Card {
                    if let choices = use.aNightChoices, let night = use.aNight {
                        menuRow(
                            "Na noc najwyżej", value: night, options: Array(Set(choices + [night])).sorted(),
                            label: { "\(AiSection.count($0)) \(unit(use, $0))" }
                        ) { new in save(TaskUpdate(aNight: new)) }
                        Divider()
                    }
                    menuRow(
                        "Kwota na noc", value: use.nightUsd ?? 0,
                        options: amounts(settings.leftoverState?.nightUsdChoices, use.nightUsd),
                        label: { $0 == 0 ? "bez limitu" : TasksSection.amount($0) }
                    ) { new in save(TaskUpdate(nightUsd: new)) }
                    Divider()
                    menuRow(
                        "Kwota na okres", value: use.periodUsd ?? 0,
                        options: amounts(settings.leftoverState?.periodUsdChoices, use.periodUsd),
                        label: { $0 == 0 ? "bez limitu" : TasksSection.amount($0) }
                    ) { new in save(TaskUpdate(periodUsd: new)) }
                    Text(amountsNote(settings, use))
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .id("amounts")
            VStack(alignment: .leading, spacing: 10) {
                SectionHeader(title: "Tryb")
                Card {
                    if let modes = use.modes, modes.count > 1 {
                        Picker("Tryb", selection: Binding(
                            get: { use.mode ?? .batch },
                            set: { new in save(TaskUpdate(mode: new)) }
                        )) {
                            Text("Batch, ½ ceny").tag(TaskMode.batch)
                            Text("Zwykły, od razu").tag(TaskMode.normal)
                        }
                        .pickerStyle(.segmented)
                    }
                    Text(Self.modeNote(use))
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .id("mode")
        }
        if use.nowEachUsd != nil, when != .off, use.able {
            VStack(alignment: .leading, spacing: 10) {
                SectionHeader(title: "Na żądanie", subtitle: "Od razu, po pełnej cenie, za kwotę, którą podasz")
                Card {
                    OnDemandRow(use: use, free: settings.leftoverState?.nowFreeUsd, prominent: true)
                }
            }
            .id("ondemand")
        }
    }

    private func save(_ update: TaskUpdate) {
        Task { await model.saveTask(key: key, update) }
    }

    private func whenRow(_ choice: TaskWhen, chosen: TaskWhen, settings: AiSettings) -> some View {
        Button {
            save(TaskUpdate(when: choice))
        } label: {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(Self.whenTitle(choice)).foregroundStyle(Theme.ink)
                    Text(Self.whenHint(choice, settings: settings))
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer()
                if chosen == choice {
                    Image(systemName: "checkmark")
                        .fontWeight(.semibold)
                        .foregroundStyle(Theme.ink)
                }
            }
            .contentShape(.rect)
        }
        .buttonStyle(.plain)
    }

    private func menuRow<Value: Hashable>(
        _ title: String, value: Value, options: [Value],
        label: @escaping (Value) -> String, set: @escaping (Value) -> Void
    ) -> some View {
        HStack {
            Text(title).foregroundStyle(Theme.ink)
            Spacer()
            Menu {
                Picker(title, selection: Binding(get: { value }, set: set)) {
                    ForEach(options, id: \.self) { Text(label($0)).tag($0) }
                }
            } label: {
                HStack(spacing: 3) {
                    Text(label(value))
                    Image(systemName: "chevron.up.chevron.down").imageScale(.small)
                }
                .font(.subheadline.weight(.medium).monospacedDigit())
                .foregroundStyle(Theme.ink)
                .contentShape(.rect)
            }
            .menuStyle(.button)
            .buttonStyle(.plain)
        }
    }

    private func stat(_ value: String, _ label: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value).font(.headline.monospacedDigit()).foregroundStyle(Theme.ink)
            Text(label).font(.caption).foregroundStyle(Theme.inkSoft)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func waitingText(_ use: LeftoverUse) -> String {
        guard let waiting = use.waiting else { return "–" }
        return AiSection.count(waiting)
    }

    /// "dzieł", "studiów".
    private func unit(_ use: LeftoverUse, _ n: Int) -> String {
        guard use.key == "studies" else { return n == 1 ? "dzieło" : "dzieł" }
        return n == 1 ? "studium" : "studiów"
    }

    /// "Bez limitu" first, then the server's choices and the one set.
    private func amounts(_ choices: [Double]?, _ set: Double?) -> [Double] {
        let offered = choices ?? [1, 2, 5, 10, 20, 50]
        return [0] + Array(Set(offered + (set.map { [$0] } ?? []))).sorted()
    }

    private func amountsNote(_ settings: AiSettings, _ use: LeftoverUse) -> String {
        var parts = ["Zawsze w granicach miesięcznego limitu i zapasu."]
        if let tonight = use.tonight, let usd = use.tonightUsd, use.waiting != nil {
            parts.append("Tej nocy ok. \(AiSection.count(tonight)) za ok. \(Money.usd(usd)).")
        }
        if use.nowEachUsd != nil {
            parts.append("Uruchomienie na żądanie ma własną kwotę i liczy się do okresu.")
        }
        return parts.joined(separator: " ")
    }

    static func whenTitle(_ when: TaskWhen) -> String {
        switch when {
        case .rest: "W ostatnich dniach okresu"
        case .night: "Co noc"
        case .demand: "Tylko na żądanie"
        case .off: "Wyłączone"
        }
    }

    static func whenHint(_ when: TaskWhen, settings: AiSettings) -> String {
        switch when {
        case .rest:
            let days = settings.leftoverDays ?? 3
            var hint = "Z tego, co zostaje z limitu ponad zapas, w ostatnich \(days) dniach"
            if let state = settings.leftoverState { hint += " (od \(AiSection.dayMonth(state.opens)))" }
            if settings.leftover != true { hint += ". Resztka jest teraz wyłączona" }
            return hint + "."
        case .night:
            return "Od 1:30, w kolejności zadań, póki starcza kwot niżej i limitu."
        case .demand:
            return "Nic samo; uruchamiasz niżej."
        case .off:
            return "Ani nocą, ani na żądanie."
        }
    }

    /// What each mode means for this task, with what a work costs so.
    static func modeNote(_ use: LeftoverUse) -> String {
        let example = use.nightUsd ?? 10
        func per(_ each: Double) -> String {
            guard each > 0 else { return "" }
            let works = Int(example / each)
            return " Ok. \(OnDemandSheet.each(each)) za dzieło: \(TasksSection.amount(example)) to ok. \(OnDemandRow.works(works))."
        }
        if use.mode == .normal, let now = use.nowEachUsd {
            return "Nocą serwer pyta od razu, dzieło po dziele, po pełnej cenie (dwa razy drożej), i kończy przed świtem." + per(now)
        }
        let batch = "Przez Batch za pół ceny: odpowiedzi w ciągu kilku godzin."
        return use.key == "studies" ? batch + " Ok. \(Money.usd(use.eachUsd)) za studium." : batch + per(use.eachUsd)
    }
}
