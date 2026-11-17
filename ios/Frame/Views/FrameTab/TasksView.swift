import SwiftUI

/// Konfiguracja → Zadania (Mateusz 2026-11-17: "przebudowania całego menu
/// „Claude” oraz „Zadania nocne” i wprowadzenia prostego konfigurowania
/// zadań planowanych i na żądanie. Z ustawieniem ilości, kwoty, czasu i
/// trybu"): the month's money on top, what runs now, then every task by
/// what it does. The AI's tasks carry a sparkle and open a page of their
/// own (when, how many and for how much, the mode, "Uruchom teraz"); the
/// server's own night work stands among them, each row with how it last
/// went and a button to start it now.
struct TasksSection: View {
    @Environment(AppModel.self) private var model
    let settings: AiSettings
    @State private var confirmAll = false

    private var uses: [LeftoverUse] { settings.leftoverState?.uses ?? [] }
    private var night: NightTasks? { model.nightTasks }

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
            if let night, let running = night.running {
                RunningCard(night: night, running: running)
            }
            // Named by what they do, each with every when and mode on its
            // page (Mateusz 2026-11-17: "nazwy określające nie to kiedy coś
            // się odbywa, tylko co robi… Jeżeli jakieś czynności się
            // zazębiają lub można je połączyć bo są drobne - to uprośćmy");
            // the server's own work stands among them, the AI's marked with
            // a sparkle ("dać do listy powyżej i tylko iskierkami oznaczyć co
            // robi AI a co nie").
            ForEach(Self.groups, id: \.title) { group in
                let shown = group.keys.compactMap { key in uses.first { $0.key == key } }
                let daily = group.title == "Odkrywaj" ? Self.discover(settings) : []
                let server = Self.serverRows(group, night)
                if !shown.isEmpty || !daily.isEmpty || !server.isEmpty {
                    self.group(group.title, nil) {
                        switches(daily)
                        taskRows(shown, divided: !daily.isEmpty)
                        serverRows(server, divided: !daily.isEmpty || !shown.isEmpty)
                        if group.title == "Katalog", night != nil {
                            Divider()
                            changesLink
                        }
                    }
                }
            }
            let known = Set(Self.groups.flatMap(\.keys))
            let others = uses.filter { !known.contains($0.key) }
            let otherWork = Self.otherServerRows(night)
            if !others.isEmpty || !otherWork.isEmpty {
                group("Inne", nil) {
                    taskRows(others, divided: false)
                    serverRows(otherWork, divided: !others.isEmpty)
                }
            }
            group("Resztka okresu", restSubtitle) { restSwitch }
                .id("rest")
            if let night {
                group("Cała noc", "Co noc od \(night.nightStart) do \(night.nightEnd), po kolei") {
                    allNightButton(night)
                }
                .id("server")
            }
        }
        .navigationDestination(for: TaskLink.self) { link in TaskPage(key: link.key) }
        .task {
            // Batches and runs move on while the page is open; a run going
            // is followed more closely.
            await model.loadNightTasks()
            while !Task.isCancelled {
                let going = model.aiSettings?.leftoverState?.uses?.contains { $0.run?.running == true } == true
                    || model.nightTasks?.running != nil
                try? await Task.sleep(for: .seconds(going ? 4 : 20))
                guard !Task.isCancelled else { return }
                await model.loadAiSettings()
                await model.loadNightTasks()
            }
        }
    }

    /// The tasks by what they do, in this order: Claude's and Gemini's
    /// (`keys`, the uses), then the server's own night work.
    static let groups: [TaskGroup] = [
        TaskGroup(title: "Katalog", keys: ["tidy", "audit"], server: [
            ServerWork(names: ["catalogue"]),
            ServerWork(names: ["twins"]),
            ServerWork(names: ["grouping"]),
            ServerWork(names: ["tidy"]),
            ServerWork(package: "indexes", label: "Spisy muzeów"),
        ]),
        TaskGroup(title: "Obraz", keys: ["crops", "looks"], server: [
            ServerWork(names: ["sharper"]),
            ServerWork(names: ["tile sets"]),
            ServerWork(names: ["kept originals"]),
        ]),
        TaskGroup(title: "Opisy i fakty", keys: ["pl_text", "keywords"], server: [
            ServerWork(names: ["artist people"]),
            ServerWork(names: ["museums", "museum places"], label: "Gdzie wiszą dzieła"),
            ServerWork(names: ["media"]),
            ServerWork(names: ["read again"]),
            ServerWork(names: ["places"]),
        ]),
        TaskGroup(title: "Odkrywaj", keys: ["studies", "refresh"], server: [
            ServerWork(names: ["themes"]),
            ServerWork(names: ["suggestions"]),
            ServerWork(names: ["births"]),
            ServerWork(names: ["frame line", "playlists"], label: "Kolejka ramki i playlisty"),
        ]),
    ]

    /// `group`'s server rows the server has, each with its tasks.
    static func serverRows(_ group: TaskGroup, _ night: NightTasks?) -> [ServerRow] {
        guard let night else { return [] }
        return group.server.compactMap { work in
            let names: [String]
            if let package = work.package {
                names = night.groups?.first { $0.key == package }?.tasks ?? []
            } else {
                names = work.names
            }
            let entries = names.compactMap { name in night.tasks.first { $0.name == name } }
            guard let first = entries.first else { return nil }
            return ServerRow(label: work.label ?? first.label, entries: entries)
        }
    }

    /// The server's work no group names, Claude's left out (its tasks stand
    /// above, as uses).
    static func otherServerRows(_ night: NightTasks?) -> [ServerRow] {
        guard let night else { return [] }
        var named = Set<String>()
        for group in groups {
            for row in serverRows(group, night) { named.formUnion(row.entries.map(\.name)) }
        }
        return night.tasks
            .filter { !$0.paid && !named.contains($0.name) }
            .map { ServerRow(label: $0.label, entries: [$0]) }
    }

    private func group(
        _ title: String, _ subtitle: String?, @ViewBuilder content: () -> some View
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
            return "Ostatnie \(days) dni, od \(AiSection.dayMonth(state.opens)), z tego, co zostaje ponad zapas"
        }
        return "Ostatnie \(days) dni, z tego, co zostaje ponad zapas"
    }

    private var restSwitch: some View {
        Toggle(isOn: Binding(
            get: { settings.leftover ?? false },
            set: { on in Task { await model.saveAiSettings(AiSettingsUpdate(leftover: on)) } }
        )) {
            Text(bound: "Wykorzystaj resztkę okresu")
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

    @ViewBuilder
    private func serverRows(_ rows: [ServerRow], divided: Bool) -> some View {
        if let night {
            ForEach(Array(rows.enumerated()), id: \.element.label) { index, row in
                if divided || index > 0 { Divider() }
                ServerTaskRow(row: row, running: night.running)
            }
        }
    }

    private var changesLink: some View {
        NavigationLink {
            TidyChangesView()
        } label: {
            HStack {
                Text(bound: "Co zmieniła noc").foregroundStyle(Theme.ink)
                Spacer(minLength: 8)
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Theme.inkSoft)
            }
            .contentShape(.rect)
        }
        .buttonStyle(.plain)
    }

    private func allNightButton(_ night: NightTasks) -> some View {
        Button {
            confirmAll = true
        } label: {
            Label("Uruchom całą noc teraz", systemImage: "moon.stars.fill")
                .font(.subheadline.weight(.semibold))
                .frame(maxWidth: .infinity)
        }
        .buttonStyle(.bordered)
        .tint(Theme.ink)
        .disabled(night.running != nil)
        .confirmationDialog("Uruchomić całą noc?", isPresented: $confirmAll, titleVisibility: .visible) {
            Button("Uruchom wszystko (\(night.tasks.count))") {
                Task { await model.startNightTasks() }
            }
            Button("Anuluj", role: .cancel) {}
        } message: {
            Text(bound: "Zadania pójdą po kolei, tak jak w nocy, najwyżej przez 2 godziny. Te z iskierką pytają AI: koszt z Twojego klucza.")
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

    /// What a task takes in besides its own work, each with its switch
    /// (the works at once as they come, the owner's photographs, the colour
    /// under varnish, the words of Szukaj; the catalogue's two checks).
    static func extras(_ key: String, _ s: AiSettings) -> [SwitchTask] {
        let rows: [SwitchTask?]
        switch key {
        case "pl_text":
            rows = [SwitchTask(title: "Nowe dzieła od razu", value: s.plText) { AiSettingsUpdate(plText: $0) }]
        case "keywords":
            rows = [
                SwitchTask(title: "Nowe dzieła od razu", value: s.keywordsArtworks) {
                    AiSettingsUpdate(keywordsArtworks: $0)
                },
                SwitchTask(title: "Twoje zdjęcia", value: s.keywordsPhotos) { AiSettingsUpdate(keywordsPhotos: $0) },
                s.varnishBlue.map {
                    SwitchTask(title: "Błękit pod werniksem", value: $0, cost: "varnish_blue") {
                        AiSettingsUpdate(varnishBlue: $0)
                    }
                },
                s.searchWords.map {
                    SwitchTask(title: "Tłumaczenie słów w Szukaj", value: $0, cost: "search_words") {
                        AiSettingsUpdate(searchWords: $0)
                    }
                },
            ]
        case "looks":
            rows = [s.looks.map { SwitchTask(title: "Nowe dzieła od razu", value: $0) { AiSettingsUpdate(looks: $0) } }]
        case "tidy":
            rows = [
                s.gatekeeper.map {
                    SwitchTask(title: "Strażnik katalogu", value: $0, cost: "gatekeeper") {
                        AiSettingsUpdate(gatekeeper: $0)
                    }
                },
                s.twinsJudge.map {
                    SwitchTask(title: "Sędzia powtórek", value: $0, cost: "twins_judge") {
                        AiSettingsUpdate(twinsJudge: $0)
                    }
                },
            ]
        default:
            rows = []
        }
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
        case .rest: "Koniec okresu"
        case .night: "Co noc"
        case .demand: "Na żądanie"
        case .off: "Wyłączone"
        }
    }

    /// When and how a task runs, as chips: "Co noc", "Batch ½",
    /// "+ koniec okresu"; the first is the when.
    static func chips(_ use: LeftoverUse) -> [String] {
        let when = use.when ?? (use.on ? .rest : .off)
        var chips = [whenChip(when)]
        guard when != .off else { return chips }
        chips.append(use.mode == .normal ? "Zwykły" : "Batch ½")
        if when == .night, use.moreAtEnd == true { chips.append("+ koniec okresu") }
        return chips
    }

    /// The rows of "Koszty" a task's cost is the sum of (what it takes in
    /// besides its own work too).
    static let costRows: [String: [String]] = [
        "pl_text": ["pl_text"],
        "keywords": ["keywords", "varnish_blue", "search_words"],
        "crops": ["crops"],
        "looks": ["looks"],
        "tidy": ["gatekeeper", "twins_judge"],
        "audit": ["audit"],
    ]

    /// What a task cost in the last days, from "Koszty" ("7 dni: 0,43 USD");
    /// a task without rows of its own (the studies share theirs with
    /// Odkrywaj) what it cost this period ("w okresie 13,16 USD").
    static func costLine(_ use: LeftoverUse, settings: AiSettings) -> String {
        guard use.able else { return "Wyłączone przełącznikiem na stronie zadania." }
        let rows = (settings.claudeCosts ?? []) + (settings.geminiCosts ?? [])
        if let keys = costRows[use.key], let days = settings.costDays {
            let usd = rows.filter { keys.contains($0.key) }.reduce(0) { $0 + $1.daysUsd }
            return "\(days) dni: \(AiSection.usd(usd))"
        }
        return "w okresie \(AiSection.usd(use.periodSpentUsd ?? use.doneUsd))"
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
    /// The AI's sparkle; not on a task's own page, where all is the AI's.
    var marked = true

    var body: some View {
        Toggle(isOn: Binding(
            get: { row.value },
            set: { new in Task { await model.saveAiSettings(row.update(new)) } }
        )) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 5) {
                    Text(bound: row.title)
                    if marked { TaskAiMark() }
                }
                if let costNote {
                    Text(bound: costNote)
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

/// A task in the list: its name, how it runs and what it cost, nothing
/// more (Mateusz 2026-11-17: "same nazwy i ew. koszt"); it opens its page.
private struct TaskRow: View {
    let use: LeftoverUse
    let settings: AiSettings

    var body: some View {
        NavigationLink(value: TaskLink(key: use.key)) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 5) {
                    HStack(spacing: 5) {
                        Text(bound: use.label)
                            .foregroundStyle(running ? Theme.ink : (use.able ? Theme.ink : Theme.inkSoft))
                        TaskAiMark()
                    }
                    let chips = TasksSection.chips(use)
                    if !chips.isEmpty || running {
                        HStack(spacing: 4) {
                            ForEach(Array(chips.enumerated()), id: \.offset) { index, chip in
                                TaskChip(text: chip, strong: index == 0 && chip != TasksSection.whenChip(.off))
                            }
                            if running { TaskChip(text: "Teraz", strong: true) }
                        }
                    }
                    let line = TasksSection.costLine(use, settings: settings)
                    if !line.isEmpty {
                        Text(bound: line)
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
        Text(bound: text)
            .font(.caption2.weight(.semibold))
            .lineLimit(1)
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .foregroundStyle(strong ? Theme.paper : Theme.ink)
            .background(strong ? Theme.ink : Theme.mat, in: Capsule())
    }
}

/// A group of Zadania: what it does, its AI tasks and the server's own.
struct TaskGroup {
    let title: String
    /// Its uses (Claude's and Gemini's tasks).
    let keys: [String]
    let server: [ServerWork]
}

/// The server's own work in a group: one night task, small ones together,
/// or a whole package (the museums' indexes).
struct ServerWork {
    var names: [String] = []
    var package: String? = nil
    /// nil: the first task's own name.
    var label: String? = nil
}

/// A server row as shown: its name and its tasks.
struct ServerRow {
    let label: String
    let entries: [NightTasks.Entry]
}

/// The server's own work: its name, how it last went, a button to start
/// it now. No sparkle: no AI.
private struct ServerTaskRow: View {
    @Environment(AppModel.self) private var model
    @State private var confirm = false
    let row: ServerRow
    let running: NightTasks.Running?

    private var names: [String] { row.entries.map(\.name) }
    private var isCurrent: Bool { running?.current.map { names.contains($0) } == true }
    private var isWaiting: Bool {
        guard let running else { return false }
        return names.contains { running.tasks.contains($0) && !running.done.contains($0) } && !isCurrent
    }

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                Text(bound: row.label).foregroundStyle(Theme.ink)
                if let last = Self.lastText(row.entries) {
                    Text(bound: last.text)
                        .font(.caption)
                        .foregroundStyle(last.warn ? Theme.warn : Theme.inkSoft)
                        .lineLimit(2)
                }
            }
            Spacer(minLength: 8)
            if isCurrent {
                ProgressView().frame(width: 30, height: 30)
            } else if isWaiting {
                Image(systemName: "clock")
                    .foregroundStyle(Theme.inkSoft)
                    .frame(width: 30, height: 30)
                    .accessibilityLabel("czeka w kolejce")
            } else {
                Button {
                    confirm = true
                } label: {
                    Image(systemName: "play.fill")
                        .font(.footnote.weight(.semibold))
                        .frame(width: 30, height: 30)
                }
                .buttonStyle(.bordered)
                .buttonBorderShape(.circle)
                .tint(Theme.ink)
                .disabled(running != nil)
                .accessibilityLabel("Uruchom teraz: \(row.label)")
                .confirmationDialog(row.label, isPresented: $confirm, titleVisibility: .visible) {
                    Button("Uruchom teraz") {
                        Task { await model.startNightTasks(names, title: row.label) }
                    }
                    Button("Anuluj", role: .cancel) {}
                }
            }
        }
        .padding(.vertical, 2)
    }

    /// "dziś, 03:12 · 41 kopii, 14 detali", "nic do zrobienia", "błąd".
    static func lastText(_ entries: [NightTasks.Entry]) -> (text: String, warn: Bool)? {
        let runs = entries.compactMap(\.last)
        guard let latest = runs.max(by: { $0.at < $1.at }) else { return ("Jeszcze nie było", false) }
        if runs.contains(where: \.failed) { return ((When.past(latest.at) ?? "") + " · błąd", true) }
        var parts = [When.past(latest.at) ?? ""]
        if entries.count == 1 {
            if let summary = latest.summary, !summary.isEmpty {
                parts.append(summary)
            } else if latest.nothing {
                parts.append("nic do zrobienia")
            }
        } else if runs.allSatisfy(\.nothing) {
            parts.append("nic do zrobienia")
        }
        if latest.asked { parts.append("na żądanie") }
        return (parts.filter { !$0.isEmpty }.joined(separator: " · "), false)
    }
}

/// The AI's mark: a sparkle after the name.
struct TaskAiMark: View {
    var body: some View {
        Image(systemName: "sparkle")
            .font(.caption)
            .foregroundStyle(Theme.inkSoft)
            .accessibilityLabel("AI")
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
                Text(bound: period).font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                Spacer()
                Text(bound: "limit \(Money.usd(settings.monthlyLimitUsd))")
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
                    Text(bound: "Limit, okres, zapas i koszty").foregroundStyle(Theme.ink)
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
            Text(bound: text)
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
        // a portion every night and more at the period's end: the amounts
        // are the end's
        let more = when == .night && use.moreAtEnd != nil
        let showsAmounts = !use.isCheck && (when == .rest || when == .night)
        Card {
            Text(bound: use.about)
                .font(.subheadline)
                .foregroundStyle(Theme.inkSoft)
                .fixedSize(horizontal: false, vertical: true)
            if !use.isCheck {
                HStack(alignment: .top) {
                    stat(waitingText(use), use.key == "studies" ? "kandydaci" : "czeka")
                    stat(AiSection.count(use.done), "w tym okresie")
                    stat(AiSection.usd(use.periodSpentUsd ?? use.doneUsd), "koszt w okresie")
                }
            }
            if !use.able {
                Label("Wyłączone przełącznikiem na liście Zadań.", systemImage: "exclamationmark.circle")
                    .font(.caption)
                    .foregroundStyle(Theme.warn)
            }
        }
        let extras = TasksSection.extras(use.key, settings)
        if !extras.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                SectionHeader(title: "Obejmuje")
                Card {
                    ForEach(Array(extras.enumerated()), id: \.element.title) { index, row in
                        if index > 0 { Divider() }
                        TaskSwitchRow(row: row, settings: settings, marked: false)
                    }
                }
            }
            .id("extras")
        }
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: "Kiedy")
            Card {
                let allowed = use.whens ?? TaskWhen.allCases
                let choices = [TaskWhen.night, .rest, .demand, .off].filter {
                    allowed.contains($0) && ($0 != .demand || use.nowEachUsd != nil)
                }
                ForEach(Array(choices.enumerated()), id: \.element) { index, choice in
                    if index > 0 { Divider() }
                    whenRow(choice, chosen: when, settings: settings)
                }
            }
        }
        .id("when")
        if more {
            VStack(alignment: .leading, spacing: 10) {
                SectionHeader(title: "Na koniec okresu")
                Card {
                    Toggle(isOn: Binding(
                        get: { use.moreAtEnd ?? true },
                        set: { new in save(TaskUpdate(moreAtEnd: new)) }
                    )) {
                        Text(bound: "Więcej z resztki okresu")
                    }
                    .tint(Theme.ink)
                }
            }
            .id("more")
        }
        if showsAmounts {
            VStack(alignment: .leading, spacing: 10) {
                SectionHeader(
                    title: "Ile i za ile",
                    subtitle: "Pierwsze, co się skończy, zatrzymuje zadanie"
                )
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
                    Text(bound: amountsNote(settings, use))
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
                            Text(bound: "Batch, ½ ceny").tag(TaskMode.batch)
                            Text(bound: "Zwykły, od razu").tag(TaskMode.normal)
                        }
                        .pickerStyle(.segmented)
                    }
                    Text(bound: Self.modeNote(use))
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
                    Text(bound: Self.whenTitle(choice)).foregroundStyle(Theme.ink)
                    Text(bound: Self.whenHint(choice, settings: settings))
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
            Text(bound: title).foregroundStyle(Theme.ink)
            Spacer()
            Menu {
                Picker(title, selection: Binding(get: { value }, set: set)) {
                    ForEach(options, id: \.self) { Text(bound: label($0)).tag($0) }
                }
            } label: {
                HStack(spacing: 3) {
                    Text(bound: label(value))
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
            Text(bound: value).font(.headline.monospacedDigit()).foregroundStyle(Theme.ink)
            Text(bound: label).font(.caption).foregroundStyle(Theme.inkSoft)
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
