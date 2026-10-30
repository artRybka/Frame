import SwiftUI

/// The frame itself: battery, charging, connection; schedule, presentation
/// and screen settings. How to reach the panel and the server, and where the
/// art comes from, sit behind the gear at the top.
struct FrameTabView: View {
    @Environment(AppModel.self) private var model
    @State private var draft: FrameSettings?
    /// The settings `draft` was taken from: what changes elsewhere meanwhile
    /// (a playlist presented, the frame renamed) comes into it.
    @State private var base: FrameSettings?
    @State private var refreshing = false
    @State private var lastLook: Date?
    @State private var renaming = false
    @State private var newName = ""
    @State private var showingConnection = LaunchRoute.screen == "connection"
    @State private var confirmingOff = false
    @State private var confirmingUpdate = false
    @State private var checkingUpdate = false
    /// The Sieć tile was tapped: it says "Sprawdzam…" until the look is done
    /// (opening the tab only turns its badge).
    @State private var checking = false

    private var device: DeviceStatus? { model.status?.device }

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 28) {
                        deviceHero
                        statusGrid
                        appNotice
                        if draft != nil {
                            ScheduleSection(settings: binding).id("schedule")
                            PresentationSection(settings: binding).id("presentation")
                            ScreenSection(settings: binding).id("orientation")
                        }
                    }
                    .padding(.horizontal, Theme.gutter)
                    .padding(.bottom, 40)
                }
                .onChange(of: draft != nil, initial: true) { _, ready in
                    // CI screenshots
                    guard ready else { return }
                    let screen = LaunchRoute.screen
                    if screen.hasPrefix("schedule") { proxy.scrollTo("schedule", anchor: .top) }
                    if screen.hasPrefix("presentation") { proxy.scrollTo("presentation", anchor: .top) }
                    if screen == "orientation" { proxy.scrollTo("orientation", anchor: .top) }
                }
            }
            .background(Theme.paper)
            .navigationTitle("Ramka")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showingConnection = true
                    } label: {
                        Image(systemName: "gearshape")
                    }
                    .accessibilityLabel("Konfiguracja ekranu i serwera")
                }
                if let draft, draft != model.settings {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Zapisz") {
                            Task {
                                await model.saveSettings(edited(draft))
                                // As the server keeps it (e.g. times sorted).
                                self.draft = model.settings
                                base = model.settings
                            }
                        }
                        .fontWeight(.semibold)
                    }
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Cofnij") {
                            self.draft = model.settings
                            base = model.settings
                        }
                    }
                }
            }
            // In a task of its own: SwiftUI cancels the refresh's task when the
            // view changes under it ("Sprawdzam…"), and the requests with it.
            .sheet(isPresented: $showingConnection) { ConnectionSettingsView() }
            .refreshable { await Task { await refresh() }.value }
            .onAppear {
                follow(model.settings)
                look()
                Task { await model.loadServerUpdate() }
            }
            .onChange(of: model.settings) { _, new in follow(new) }
            .alert("Nazwa ramki", isPresented: $renaming) {
                TextField(panelName, text: $newName)
                    .textInputAutocapitalization(.sentences)
                Button("Zapisz") { Task { await model.renameFrame(newName) } }
                if model.settings?.name != nil {
                    Button("Nazwa z ekranu") { Task { await model.renameFrame("") } }
                }
                Button("Anuluj", role: .cancel) {}
            } message: {
                Text("Tak ramka będzie się nazywać w aplikacji.")
            }
        }
    }

    /// What the panel calls itself (set in Samsung's own app).
    private var panelName: String { device?.name.flatMap { $0.isEmpty ? nil : $0 } ?? "Moja ramka" }

    private var frameName: String { model.settings?.name ?? panelName }

    /// The draft on the settings as they are now. Changes not saved yet
    /// stay; the rest follows (e.g. the playlist presented from Playlists).
    private func follow(_ settings: FrameSettings?) {
        guard let settings, settings != base else { return }
        if let draft, let base {
            self.draft = draft.rebased(from: base, onto: settings)
        } else {
            draft = Self.screenshotDraft(settings)
        }
        base = settings
    }

    /// CI screenshots: the schedule with a few times and the quiet hours on, or photos three to a board.
    private static func screenshotDraft(_ settings: FrameSettings) -> FrameSettings {
        var settings = settings
        switch LaunchRoute.screen {
        case "schedule":
            settings.changeTimes = ["07:00", "13:00", "19:30"]
            settings.quietStart = "22:00"
        case "schedule-economy":
            settings.powerMode = "economy"
            settings.changeTimes = ["07:00", "19:00"]
            settings.checkEveryHours = 4
            settings.checkQuietStart = "22:00"
            settings.checkQuietEnd = "07:00"
        case "presentation-photo":
            settings.photo.fit = "multi"
            settings.photo.multiCount = 3
            settings.photo.margin = Panel.margin(mm: 30)
        default:
            break
        }
        return settings
    }

    /// `draft`'s own changes, made on the settings as the app has them now.
    private func edited(_ draft: FrameSettings) -> FrameSettings {
        guard let base, let current = model.settings else { return draft }
        return draft.rebased(from: base, onto: current)
    }

    private var binding: Binding<FrameSettings> {
        Binding(
            get: { draft ?? .defaults },
            set: { draft = $0 }
        )
    }

    /// `checking`: a tap on the Sieć tile, which also wakes a frame asleep
    /// in the network; pulling to refresh only looks.
    private func refresh(checking: Bool = false) async {
        refreshing = true
        self.checking = checking
        lastLook = .now
        defer {
            refreshing = false
            self.checking = false
        }
        if checking {
            await model.checkStatus()
        } else {
            await model.refreshStatus(live: true)
        }
        self.checking = false  // the tile shows what it found; the rest loads behind
        await model.refreshAll()
        await model.loadServerUpdate()
    }

    /// Opening the tab looks at the frame without waking it: the server asks
    /// it over MDC and, if it sleeps, whether it is still on the Wi-Fi. Not
    /// again within half a minute.
    private func look() {
        guard !refreshing, device?.configured == true else { return }
        if let lastLook, Date.now.timeIntervalSince(lastLook) < 30 { return }
        lastLook = .now
        Task {
            refreshing = true
            defer { refreshing = false }
            await model.refreshStatus(live: true)
        }
    }

    // MARK: Device

    private var deviceHero: some View {
        HStack(spacing: 18) {
            // The screen's own proportions (2560 × 1440), as in "Teraz".
            FramedArtwork(
                ref: model.player?.current.map { ImageRef.path($0.previewUrl) },
                aspectRatio: model.isPortrait ? 9.0 / 16.0 : 16.0 / 9.0,
                placeholder: Theme.matWhite,
                moulding: 4
            )
            .frame(width: model.isPortrait ? 108 : 150)
            VStack(alignment: .leading, spacing: 4) {
                Eyebrow(model.settings?.name != nil ? panelName : "Samsung \(device?.model ?? "EM32DX")")
                Button {
                    newName = model.settings?.name ?? ""
                    renaming = true
                } label: {
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text(frameName)
                            .font(.serif(26, weight: .semibold))
                            .foregroundStyle(Theme.ink)
                            .multilineTextAlignment(.leading)
                        Image(systemName: "pencil")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(Theme.inkSoft)
                    }
                }
                .buttonStyle(.plain)
                .accessibilityLabel("\(frameName), zmień nazwę")
                Text(connectionText)
                    .font(.subheadline)
                    .foregroundStyle(connectionColor)
            }
            Spacer(minLength: 0)
        }
        .padding(.top, 8)
    }

    /// The one sentence on what the frame does and how it wakes; the tiles
    /// under it only name the state (Sieć) and the power source (Zasilanie).
    private var connectionText: String {
        guard let device else { return "Brak danych" }
        if !device.configured { return "Podaj adres i PIN ekranu pod trybikiem u góry" }
        if let silent = appSilence { return "Ekran odpowiada · aplikacja milczy \(silent)" }
        switch device.powerState {
        case "online": return "Połączona · \(When.ago(device.lastSeen) ?? "teraz")"
        case "standby":
            return device.onNetwork == true ? "Śpi w sieci · wysyłka ją obudzi" : "Śpi · czeka na sygnał budzenia"
        case "deep_sleep":
            if device.switchedOff == true { return "Wyłączona · włączysz ją przyciskiem na ramce" }
            if let alarm = When.at(device.wakeAt) { return "Śpi bez Wi-Fi · budzik \(alarm), wcześniej przycisk" }
            return "Śpi bez Wi-Fi · obudzi ją przycisk na ramce"
        case "offline":
            return device.onNetwork == false ? "Nie ma jej w sieci Wi-Fi" : "Nie odpowiada — śpi lub poza siecią"
        default: break  // a server before 0.12
        }
        switch device.reachable {
        case .some(true): return "Połączona · \(When.ago(device.lastSeen) ?? "teraz")"
        case .some(false): return "Nie odpowiada — śpi lub poza siecią"
        case .none: return "Nie sprawdzono"
        }
    }

    /// The frame answers the server over MDC, but its app has not asked for
    /// a picture for a while ("od 51 min"): nothing gets through then, so
    /// "Połączona" would mislead.
    private var appSilence: String? {
        guard device?.configured == true else { return nil }
        return When.since(device?.appSilentSince)
    }

    private var connectionColor: Color {
        if appSilence != nil { return Theme.warn }
        switch device?.powerState {
        case "online": return Theme.good
        case "standby", "deep_sleep": return Theme.inkSoft
        case "offline": return Theme.bad
        default: break
        }
        switch device?.reachable {
        case .some(true): return Theme.good
        case .some(false): return Theme.bad
        case .none: return Theme.inkSoft
        }
    }

    /// The Frame app on the panel is how pictures reach it: say so when it
    /// does not run yet, or when its certificates are about to expire.
    @ViewBuilder private var appNotice: some View {
        if let device, device.configured {
            if let pending = modePendingText(device) {
                NoticeRow(icon: "clock.arrow.circlepath", color: Theme.accent, text: pending)
            }
            if let expires = device.certificatesExpireAt {
                NoticeRow(
                    icon: "exclamationmark.shield",
                    color: Theme.warn,
                    text: certificatesText(expires)
                )
            }
            if let silent = appSilence {
                NoticeRow(
                    icon: "exclamationmark.triangle",
                    color: Theme.warn,
                    text: "Dopóki aplikacja Frame na ramce milczy, nowy obraz nie dotrze. Serwer próbuje ją uruchomić; możesz też stuknąć kafelek Zasilanie → Uruchom aplikację ponownie."
                )
            } else if device.panelApp == false {
                NoticeRow(
                    icon: "app.badge",
                    color: Theme.inkSoft,
                    text: "Ramka nie uruchomiła jeszcze aplikacji Frame. Serwer sam ją uruchomi, gdy ramka się obudzi; możesz też zrobić to pod trybikiem, w sekcji Aplikacja ramki."
                )
            }
        }
    }

    private var statusGrid: some View {
        LazyVGrid(columns: [GridItem(.flexible(), spacing: 14), GridItem(.flexible(), spacing: 14)], spacing: 14) {
            StatusTile(title: "Bateria") {
                BatteryRing(level: device?.batteryLevel, charging: device?.charging == true, note: batteryNote)
            }
            powerTile
            serverTile
            networkTile
        }
    }

    /// The Zasilanie tile: the power source; a tap opens the power menu.
    private var powerTile: some View {
        Menu {
            Button("Obudź ramkę", systemImage: "sun.max") { Task { await model.wake() } }
            Button("Uśpij ramkę", systemImage: "moon.zzz") { Task { await model.sleepFrame() } }
            Menu {
                ForEach(Self.restChoices, id: \.hours) { choice in
                    Button(choice.label) { Task { await model.restFrame(hours: choice.hours) } }
                }
            } label: {
                Label("Głęboki sen", systemImage: "moon.stars")
            }
            Button("Uruchom aplikację ponownie", systemImage: "arrow.triangle.2.circlepath") {
                Task { await model.installPanelApp() }
            }
            Button("Uruchom ramkę ponownie", systemImage: "arrow.clockwise.circle") {
                Task { await model.restartFrame() }
            }
            // The app reboots the panel: a silent one would not.
            .disabled(appSilence != nil)
            Divider()
            Button("Wyłącz ramkę", systemImage: "power", role: .destructive) { confirmingOff = true }
        } label: {
            StatusTile(title: "Zasilanie", badge: TileBadge(systemImage: "power")) {
                VStack(alignment: .leading, spacing: 6) {
                    Image(systemName: powerIcon)
                        .font(.title2)
                        .foregroundStyle(device?.charging == true ? Theme.warn : Theme.inkSoft)
                        .symbolEffect(.pulse, options: .repeating, isActive: device?.charging == true)
                    Text(powerText).font(.headline).foregroundStyle(Theme.ink)
                    Text(powerNote)
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
            }
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .accessibilityHint("Otwiera menu zasilania ramki")
        .alert("Wyłączyć ramkę?", isPresented: $confirmingOff) {
            Button("Wyłącz", role: .destructive) { Task { await model.restFrame(hours: nil) } }
            Button("Anuluj", role: .cancel) {}
        } message: {
            Text("Ramka zaśnie bez Wi-Fi i bez budzika: obraz zostanie, ale nie zmieni się, a z aplikacji nie da się jej obudzić. Włączysz ją dopiero przyciskiem z tyłu ramki.")
        }
    }

    /// The Sieć tile: the state and the network; a tap checks the frame,
    /// waking it when it sleeps in the network.
    private var networkTile: some View {
        let state = network
        let busy = checking || model.wakingForStatus
        return Button {
            // Not disabled while the tab looks by itself: that would dim it.
            guard !refreshing else { return }
            Task { await refresh(checking: true) }
        } label: {
            StatusTile(title: "Sieć", badge: TileBadge(systemImage: "arrow.clockwise", working: refreshing)) {
                VStack(alignment: .leading, spacing: 6) {
                    if busy {
                        ProgressView()
                            .frame(height: 24)
                    } else if let arcs = state.arcs {
                        WifiStrengthIcon(arcs: arcs, color: state.color)
                            .accessibilityLabel(device?.wifi?.strength ?? "Wi-Fi")
                    } else {
                        Image(systemName: state.icon)
                            .font(.title2)
                            .foregroundStyle(state.color)
                    }
                    Text(busy ? checkLabel : state.title)
                        .font(.headline)
                        .foregroundStyle(Theme.ink)
                    if !state.note.isEmpty {
                        Text(state.note)
                            .font(.caption)
                            .foregroundStyle(Theme.inkSoft)
                            .lineLimit(2)
                    }
                }
            }
        }
        .buttonStyle(.plain)
        .accessibilityHint("Sprawdza stan ramki i budzi ją, gdy śpi w sieci")
    }

    /// The Sieć tile: what the frame is doing, as far as the server can tell
    /// (the title: Online, Czuwanie, Głęboki sen...), with the network when
    /// the Frame app reads the Wi-Fi. Online, the Wi-Fi icon's arcs show how
    /// strong the signal is, yellow when weak.
    private var network: (icon: String, color: Color, title: String, note: String, arcs: Int?) {
        let (icon, color, title, note) = networkState
        let wifi = device?.wifi
        if wifi?.wrongNetwork == true {
            let note = wifi?.ssid.map { "połączona z \($0)" } ?? "inny adres niż zwykle"
            return ("wifi.exclamationmark", Theme.bad, "Obca sieć", note, nil)
        }
        guard device?.powerState == "online", let wifi, let arcs = wifi.arcs else {
            return (icon, color, title, note, nil)
        }
        return (icon, arcs <= 1 ? Theme.warn : color, title, wifi.ssid ?? note, arcs)
    }

    /// The Sieć tile's state; the note is only the network's name, the
    /// header says what the state means.
    private var networkState: (icon: String, color: Color, title: String, note: String) {
        guard let device, device.configured else {
            return ("wifi", Theme.inkSoft, "—", "ekran nie jest ustawiony")
        }
        let ssid = device.wifi?.ssid ?? ""
        switch device.powerState {
        case "online":
            return ("wifi", Theme.good, "Online", ssid)
        case "standby":
            return ("moon.zzz", Theme.accent, "Czuwanie", ssid)
        case "deep_sleep":
            return ("wifi.slash", Theme.inkSoft, "Bez Wi-Fi", ssid)
        case "offline":
            if device.onNetwork == false {
                return ("wifi.exclamationmark", Theme.bad, "Poza siecią", ssid)
            }
            return ("wifi.exclamationmark", Theme.bad, "Brak odpowiedzi", ssid)
        default:
            return ("wifi", Theme.inkSoft, "Nie sprawdzono", "")
        }
    }

    /// The Serwer tile: the server's version and whether a newer one is out.
    /// A tap updates (after asking) or looks for one; where the app cannot
    /// update the server (Home Assistant, no helper) it opens the settings.
    private var serverTile: some View {
        let state = server
        return Button {
            guard let update = model.serverUpdate, update.updater, !update.addon else {
                showingConnection = true
                return
            }
            if update.offersUpdate {
                confirmingUpdate = true
            } else if !update.busy, !model.updatingServer {
                Task {
                    checkingUpdate = true
                    await model.checkServerUpdate()
                    checkingUpdate = false
                }
            }
        } label: {
            StatusTile(title: "Serwer", badge: serverBadge) {
                VStack(alignment: .leading, spacing: 6) {
                    // The update's arrow and the spinner are the badge's.
                    Image(systemName: state.working || state.icon == "arrow.down.circle.fill" ? "server.rack" : state.icon)
                        .font(.title2)
                        .foregroundStyle(state.color)
                    Text(state.title)
                        .font(.headline)
                        .monospacedDigit()
                        .foregroundStyle(Theme.ink)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(state.note)
                            .foregroundStyle(state.color == Theme.accent ? Theme.accent : Theme.inkSoft)
                        if let detail = state.detail {
                            Text(detail).foregroundStyle(Theme.inkSoft)
                        }
                    }
                    .font(.caption)
                    .lineLimit(2)
                }
            }
        }
        .buttonStyle(.plain)
        .confirmationDialog(
            "Aktualizować serwer do wersji \(model.serverUpdate?.latestVersion ?? "najnowszej")?",
            isPresented: $confirmingUpdate,
            titleVisibility: .visible
        ) {
            Button("Aktualizuj serwer") { Task { await model.updateServer() } }
        } message: {
            Text("Serwer zniknie na około minutę. Gdyby nowa wersja nie wystartowała, wróci obecna.")
        }
    }

    /// What a tap on the Serwer tile does: update (the blue arrow), look
    /// for an update, or open the settings where the app cannot update it.
    private var serverBadge: TileBadge {
        guard let update = model.serverUpdate, update.updater, !update.addon else {
            return TileBadge(systemImage: "chevron.right")
        }
        if model.updatingServer || checkingUpdate || update.busy {
            return TileBadge(systemImage: "arrow.clockwise", working: true)
        }
        if update.offersUpdate { return TileBadge(systemImage: "arrow.down", prominent: true) }
        return TileBadge(systemImage: "arrow.clockwise")
    }

    /// The Serwer tile's state; `detail` goes on a line of its own under `note`.
    private var server: (icon: String, color: Color, title: String, note: String, detail: String?, working: Bool) {
        let version = model.serverUpdate?.version ?? model.status?.server.version ?? "—"
        guard let update = model.serverUpdate else {
            return ("server.rack", Theme.inkSoft, version, "wersja serwera", nil, false)
        }
        if update.addon {
            return ("server.rack", Theme.inkSoft, version, "aktualizuje Home Assistant", nil, false)
        }
        if !update.updater {
            return ("server.rack", Theme.inkSoft, version, "aktualizacja na NAS-ie", nil, false)
        }
        let latest = update.latestVersion ?? "nowsza"
        if model.updatingServer || update.state == "updating" {
            return ("arrow.triangle.2.circlepath", Theme.accent, "\(version) → \(latest)", "aktualizuję", "wróci za minutę", true)
        }
        if checkingUpdate || update.state == "checking" || update.pending == "check" {
            return ("arrow.triangle.2.circlepath", Theme.inkSoft, version, "sprawdzam…", nil, true)
        }
        let checked = When.ago(update.checkedAt).map { "sprawdzono \($0)" }
        if update.offersUpdate {
            return ("arrow.down.circle.fill", Theme.accent, version, "jest \(latest)", nil, false)
        }
        if update.state == "failed" {
            return ("exclamationmark.triangle", Theme.warn, version, "nie udało się", checked, false)
        }
        return ("server.rack", Theme.inkSoft, version, "aktualny", checked, false)
    }

    /// Under the battery level: how long it lasts at the rate measured on
    /// battery; on the charger whether it charges (Zasilanie says "Zasilacz").
    private var batteryNote: String {
        if device?.charging == true { return "ładuje się" }
        switch device?.powerSource {
        case "ac": return (device?.batteryLevel ?? 0) >= 95 ? "naładowana" : ""
        case "battery":
            guard let days = device?.batteryDays else { return "mierzę zużycie" }
            if days > 60 { return "ok. \(Int(days / 30)) mies." }
            if days >= 2 { return "ok. \(Int(days)) dni" }
            return "ok. \(max(1, Int(days * 24))) godz."
        default: return ""
        }
    }

    private var powerIcon: String {
        if device?.charging == true { return "bolt.fill" }
        guard device?.powerSource == "battery" else { return "powerplug.portrait" }
        return switch device?.batteryLevel ?? 100 {
        case ..<13: "battery.0percent"
        case ..<38: "battery.25percent"
        case ..<63: "battery.50percent"
        case ..<88: "battery.75percent"
        default: "battery.100percent"
        }
    }

    private var powerText: String {
        switch device?.powerSource {
        case "ac": "Zasilacz"
        case "battery": "Na baterii"
        default: "Nieznane"
        }
    }

    /// On the charger the frame never sleeps; on battery how it sleeps is
    /// the mode's (the header says what it does now).
    private var powerNote: String {
        switch device?.powerSource {
        case "ac": return "nie śpi, zmiany od razu"
        case "battery": return model.settings?.isEconomy == true ? "tryb Oszczędny" : "tryb Online"
        default: return "zmiany według harmonogramu"
        }
    }

    private var checkLabel: String {
        model.wakingForStatus ? "Budzę ramkę…" : "Sprawdzam…"
    }

    /// "Głęboki sen" lengths: up to three days.
    private static let restChoices: [(hours: Int, label: String)] = [
        (6, "6 godzin"), (12, "12 godzin"), (24, "1 dzień"), (48, "2 dni"), (72, "3 dni"),
    ]
}

struct StatusTile<Content: View>: View {
    let title: String
    /// In the corner of a tile that does something when tapped.
    var badge: TileBadge?
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Eyebrow(title)
            content
            Spacer(minLength: 0)
        }
        .padding(16)
        .frame(maxWidth: .infinity, minHeight: 150, alignment: .topLeading)
        .overlay(alignment: .topTrailing) {
            if let badge { badge.padding(10) }
        }
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).strokeBorder(Theme.hairline.opacity(0.7)))
        .contentShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
    }
}

/// The round mark in a tile's corner saying what a tap does: ⏻ the power
/// menu, ↻ a check, a blue arrow an update; a spinner while it works.
struct TileBadge: View {
    let systemImage: String
    var prominent = false
    var working = false

    var body: some View {
        ZStack {
            Circle().fill(prominent ? Theme.accent : Theme.mat)
            if working {
                ProgressView().controlSize(.small)
            } else {
                Image(systemName: systemImage)
                    .font(.footnote.weight(.bold))
                    .foregroundStyle(prominent ? Theme.card : Theme.ink)
            }
        }
        .frame(width: 30, height: 30)
        .accessibilityHidden(true)
    }
}

struct BatteryRing: View {
    let level: Int?
    let charging: Bool
    /// Under the level: how long it lasts, "na zasilaczu"...
    let note: String

    private var fraction: Double { Double(level ?? 0) / 100 }
    private var color: Color {
        guard let level else { return Theme.inkSoft }
        if charging { return Theme.warn }
        return level <= 15 ? Theme.bad : level <= 35 ? Theme.warn : Theme.good
    }

    var body: some View {
        HStack(spacing: 14) {
            ZStack {
                Circle().stroke(Theme.mat, lineWidth: 9)
                Circle()
                    .trim(from: 0, to: fraction)
                    .stroke(color, style: StrokeStyle(lineWidth: 9, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                    .animation(.easeOut(duration: 0.8), value: fraction)
                if charging {
                    Image(systemName: "bolt.fill").font(.callout).foregroundStyle(color)
                }
            }
            .frame(width: 64, height: 64)
            VStack(alignment: .leading, spacing: 2) {
                Text(level.map { "\($0)%" } ?? "—")
                    .font(.serif(28, weight: .semibold))
                    .monospacedDigit()
                    .foregroundStyle(Theme.ink)
                Text(note).font(.caption).foregroundStyle(Theme.inkSoft)
            }
        }
    }
}

/// The Wi-Fi icon with as many arcs lit as the signal is strong (0–3) and
/// the rest faint, as on the iPhone; the size of a `.title2` symbol.
struct WifiStrengthIcon: View {
    let arcs: Int
    let color: Color

    private static let radii: [CGFloat] = [7, 12.5, 18]

    var body: some View {
        ZStack {
            Circle()
                .fill(color)
                .frame(width: 5.4, height: 5.4)
                .position(x: 15, y: 21)
            ForEach(Self.radii.indices, id: \.self) { index in
                // From up-left to up-right: a Circle's trim starts at three
                // o'clock and runs clockwise.
                Circle()
                    .trim(from: 0.625, to: 0.875)
                    .stroke(index < arcs ? color : Theme.hairline, style: StrokeStyle(lineWidth: 3.4, lineCap: .round))
                    .frame(width: Self.radii[index] * 2, height: Self.radii[index] * 2)
                    .position(x: 15, y: 21)
            }
        }
        .frame(width: 30, height: 24)
    }
}

// MARK: - Settings sections

struct ScheduleSection: View {
    @Environment(AppModel.self) private var model
    @Binding var settings: FrameSettings

    private let everyDays: [(Int, String)] = [(1, "codziennie"), (2, "co 2 dni"), (3, "co 3 dni")]
    private let maxTimes = 12

    private var albums: [PlaylistSummary] { model.playlists.filter { $0.kind == .album } }
    private var playingAlbum: PlaylistSummary? { albums.first { $0.id == settings.playlistId } }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Harmonogram")

            Card {
                powerModePicker
                Divider()
                row("Zmiana") {
                    Picker("Zmiana", selection: $settings.changeEveryDays) {
                        ForEach(everyDays, id: \.0) { days, label in Text(label).tag(days) }
                    }
                    .labelsHidden()
                }
                Divider()
                changeTimesEditor
                Divider()
                if settings.isEconomy {
                    checksPicker
                    Divider()
                }
                pills
                if settings.isEconomy {
                    checkQuietHours
                    wakeStrip
                } else {
                    quietHours
                }
            }
            .tint(Theme.accent)
        }
    }

    /// Shuffle and quiet hours side by side; the quiet hours' times are in a
    /// row under them.
    private var pills: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                if let album = playingAlbum?.album {
                    TogglePill(title: album.order.title, systemImage: "photo.stack", isOn: .constant(false))
                        .disabled(true)
                } else {
                    TogglePill(title: "Losowo", systemImage: "shuffle", isOn: $settings.shuffle)
                }
                if settings.isEconomy {
                    // Economy has its own quiet hours, for the checks only.
                    TogglePill(title: "Cisza nocna", systemImage: "moon.stars", isOn: checkQuietEnabled)
                        .disabled(!hasChecks || settings.checkQuietEnd == nil)
                } else {
                    TogglePill(title: "Cisza nocna", systemImage: "moon.stars", isOn: quietEnabled)
                }
            }
            if playingAlbum?.album != nil {
                Text("Album ma własną kolejność zdjęć; zmienisz ją w jego playliście.")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
            }
        }
    }

    @ViewBuilder private var quietHours: some View {
        if settings.quietStart != nil {
            HStack(spacing: 8) {
                Text("Cisza nocna od").foregroundStyle(Theme.inkSoft)
                DatePicker("Od", selection: time(\.quietStart, fallback: "22:00"), displayedComponents: .hourAndMinute)
                    .labelsHidden()
                Text("do \(settings.quietEnd ?? "—")").foregroundStyle(Theme.inkSoft)
                Spacer(minLength: 0)
            }
            .font(.subheadline)
            Text("Trwa do najbliższej zmiany. Na baterii ramka śpi wtedy bez Wi-Fi, a zdjęcia wysłane w nocy pokaże rano.")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
        }
    }

    /// Online: the frame listens on the Wi-Fi while asleep. Economy: on
    /// battery it sleeps with the Wi-Fi off and wakes itself by its clock
    /// (on the charger it works as online).
    private var powerModePicker: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Tryb pracy").foregroundStyle(Theme.ink)
            Picker("Tryb pracy", selection: powerMode) {
                Text("Online").tag("online")
                Text("Oszczędny").tag("economy")
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            // After "Zapisz": the sleeping frame switches only when it wakes.
            if let device = model.status?.device, device.modePending == settings.powerMode,
               let pending = modePendingText(device) {
                NoticeRow(icon: "clock.arrow.circlepath", color: Theme.accent, text: pending)
            }
        }
    }

    private var powerMode: Binding<String> {
        Binding(
            get: { settings.powerMode ?? "online" },
            set: { mode in
                settings.powerMode = mode
                if settings.checkEveryHours == nil { settings.checkEveryHours = 0 }
            }
        )
    }

    private let checkOptions: [(Int, String)] = [
        (0, "wyłączone"), (1, "co godzinę"), (2, "co 2 godziny"), (3, "co 3 godziny"), (4, "co 4 godziny"),
        (6, "co 6 godzin"),
    ]

    private var hasChecks: Bool { (settings.checkEveryHours ?? 0) > 0 }

    /// Economy: short wakes between the changes, only for what was sent from the app.
    private var checksPicker: some View {
        row("Sprawdzenia") {
            Picker("Sprawdzenia", selection: checkEvery) {
                ForEach(checkOptions, id: \.0) { hours, label in Text(label).tag(hours) }
            }
            .labelsHidden()
        }
    }

    private var wakeStrip: some View {
        VStack(alignment: .leading, spacing: 8) {
            WakeStrip(
                changes: settings.changeMinutes,
                checks: settings.checkMinutes,
                quiet: hasChecks ? settings.checkQuiet : nil
            )
            Text(wakeNote)
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
        }
    }

    /// Economy: the night without checks, from–to; the changes still wake the frame.
    @ViewBuilder private var checkQuietHours: some View {
        if hasChecks, settings.checkQuietEnd != nil, settings.checkQuietStart != nil {
            // Two times in a row: "Od" alone when 12-hour times leave no room.
            ViewThatFits(in: .horizontal) {
                checkQuietRow("Cisza nocna od")
                checkQuietRow("Od")
            }
            .font(.subheadline)
        }
    }

    private func checkQuietRow(_ label: String) -> some View {
        HStack(spacing: 8) {
            Text(label).foregroundStyle(Theme.inkSoft).fixedSize()
            DatePicker("Od", selection: time(\.checkQuietStart, fallback: "22:00"), displayedComponents: .hourAndMinute)
                .labelsHidden()
            Text("do").foregroundStyle(Theme.inkSoft).fixedSize()
            DatePicker("do", selection: time(\.checkQuietEnd, fallback: "07:00"), displayedComponents: .hourAndMinute)
                .labelsHidden()
            Spacer(minLength: 0)
        }
    }

    private var checkQuietEnabled: Binding<Bool> {
        Binding(
            get: { hasChecks && settings.checkQuietStart != nil },
            set: { on in settings.checkQuietStart = on ? "22:00" : nil }
        )
    }

    private var checkEvery: Binding<Int> {
        Binding(get: { settings.checkEveryHours ?? 0 }, set: { settings.checkEveryHours = $0 })
    }

    private var wakeNote: String {
        let changes = settings.changeMinutes.count
        let checks = settings.checkMinutes.count
        let count = changes + checks
        // About a minute and a half of Wi-Fi for a change (joining, the
        // picture, back to sleep), half a minute for a check with nothing to show.
        let minutes = max(1, Int((Double(changes) * 1.5 + Double(checks) * 0.5).rounded()))
        let summary = "\(count) \(Names.wakes(count)) dziennie, Wi-Fi łącznie ok. \(minutes) min na dobę."
        guard let every = settings.checkEveryHours, every > 0 else { return summary }
        guard checks > 0 else {
            return "Przy tej ciszy nocnej nie wypada żadne sprawdzenie. "
                + "Wybierz krótszy odstęp albo skróć ciszę nocną. \(summary)"
        }
        let often = every == 1 ? "co godzinę" : "co \(every) \(Names.hours(every))"
        let quiet = settings.checkQuiet != nil ? ", poza ciszą nocną" : ""
        return "Sprawdza \(often) o pełnych godzinach doby\(quiet). "
            + "Obraz zmienia się tylko, gdy wysłałeś coś z aplikacji. \(summary)"
    }

    private func row<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        HStack {
            Text(title).foregroundStyle(Theme.ink)
            Spacer()
            content()
        }
    }

    /// The times of day the picture changes at, side by side: tapping one
    /// opens a wheel to change it, with "Usuń godzinę" under it.
    private var changeTimesEditor: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(changeTimesTitle).foregroundStyle(Theme.ink)
                Spacer()
                if settings.changeTimes.count < maxTimes {
                    Button {
                        settings.changeTimes = Self.sorted(
                            settings.changeTimes + [Self.nextFreeTime(after: settings.changeTimes)]
                        )
                    } label: {
                        Image(systemName: "plus.circle").font(.title3)
                    }
                    .buttonStyle(.borderless)
                    .accessibilityLabel("Dodaj godzinę")
                }
            }
            FlowLayout(spacing: 8) {
                ForEach(settings.changeTimes.indices, id: \.self) { index in
                    ChangeTimeChip(
                        label: settings.changeTimes[index],
                        time: changeTime(at: index),
                        remove: settings.changeTimes.count > 1 ? { removeTime(at: index) } : nil
                    )
                }
            }
        }
    }

    private func removeTime(at index: Int) {
        guard settings.changeTimes.count > 1, settings.changeTimes.indices.contains(index) else { return }
        settings.changeTimes.remove(at: index)
    }

    private var changeTimesTitle: String {
        if settings.isEconomy { return "Pobudki i zmiany" }
        return settings.changeTimes.count > 1 ? "Godziny zmiany" : "Godzina zmiany"
    }

    private func changeTime(at index: Int) -> Binding<Date> {
        Binding(
            get: { Self.date(settings.changeTimes.indices.contains(index) ? settings.changeTimes[index] : "07:00") },
            set: { date in
                // Sorted (and duplicates dropped) by the server on save, so
                // the row being edited does not jump away under the finger.
                guard settings.changeTimes.indices.contains(index) else { return }
                settings.changeTimes[index] = Self.hhmm(date)
            }
        )
    }

    static func sorted(_ times: [String]) -> [String] {
        Array(Set(times)).sorted()
    }

    /// A sensible new time: three hours after the last one, wrapping at midnight.
    static func nextFreeTime(after times: [String]) -> String {
        let minutes = times.compactMap { t -> Int? in
            let parts = t.split(separator: ":").compactMap { Int($0) }
            return parts.count == 2 ? parts[0] * 60 + parts[1] : nil
        }
        var candidate = ((minutes.max() ?? 7 * 60) + 180) % (24 * 60)
        while minutes.contains(candidate) { candidate = (candidate + 60) % (24 * 60) }
        return String(format: "%02d:%02d", candidate / 60, candidate % 60)
    }

    private static func date(_ hhmm: String) -> Date {
        let parts = hhmm.split(separator: ":").compactMap { Int($0) }
        return Calendar.current.date(
            bySettingHour: parts.first ?? 0, minute: parts.dropFirst().first ?? 0, second: 0, of: .now
        ) ?? .now
    }

    private static func hhmm(_ date: Date) -> String {
        let comps = Calendar.current.dateComponents([.hour, .minute], from: date)
        return String(format: "%02d:%02d", comps.hour ?? 0, comps.minute ?? 0)
    }

    private var quietEnabled: Binding<Bool> {
        Binding(
            get: { settings.quietStart != nil },
            set: { on in settings.quietStart = on ? "22:00" : nil }
        )
    }

    private func time(_ key: WritableKeyPath<FrameSettings, String?>, fallback: String) -> Binding<Date> {
        Binding(
            get: {
                let parts = (settings[keyPath: key] ?? fallback).split(separator: ":").compactMap { Int($0) }
                return Calendar.current.date(
                    bySettingHour: parts.first ?? 0, minute: parts.dropFirst().first ?? 0, second: 0, of: .now
                ) ?? .now
            },
            set: { date in
                let comps = Calendar.current.dateComponents([.hour, .minute], from: date)
                settings[keyPath: key] = String(format: "%02d:%02d", comps.hour ?? 0, comps.minute ?? 0)
            }
        )
    }
}

/// An on/off switch as a capsule with an icon: accent when on.
struct TogglePill: View {
    let title: String
    let systemImage: String
    @Binding var isOn: Bool
    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        Button { isOn.toggle() } label: {
            HStack(spacing: 6) {
                Image(systemName: systemImage).font(.subheadline.weight(.semibold))
                Text(title)
                    .font(.subheadline.weight(.medium))
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 8)
            .padding(.vertical, 9)
            .foregroundStyle(isOn ? Theme.accent : Theme.ink)
            .background(isOn ? Theme.accent.opacity(0.17) : Theme.mat, in: Capsule())
            .opacity(isEnabled ? 1 : 0.42)
        }
        .buttonStyle(.plain)
        .sensoryFeedback(.selection, trigger: isOn)
        .accessibilityValue(isOn ? "włączona" : "wyłączona")
        .accessibilityAddTraits(isOn ? .isSelected : [])
    }
}

/// One change time; tapping it opens a wheel, and "Usuń godzinę" when
/// there is more than one.
struct ChangeTimeChip: View {
    let label: String
    @Binding var time: Date
    var remove: (() -> Void)?
    @State private var editing = false

    var body: some View {
        Button { editing = true } label: {
            Text(label)
                .monospacedDigit()
                .padding(.horizontal, 13)
                .padding(.vertical, 8)
                .foregroundStyle(Theme.ink)
                .background(Theme.mat, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .strokeBorder(Theme.accent, lineWidth: editing ? 2 : 0)
                )
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Godzina \(label)")
        .popover(isPresented: $editing) {
            VStack(spacing: 0) {
                DatePicker("Godzina", selection: $time, displayedComponents: .hourAndMinute)
                    .datePickerStyle(.wheel)
                    .labelsHidden()
                    .frame(width: 260)
                if let remove {
                    Divider()
                    Button(role: .destructive) {
                        editing = false
                        remove()
                    } label: {
                        Label("Usuń godzinę", systemImage: "trash")
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 16)
                            .padding(.vertical, 12)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(Theme.vermilion)
                }
            }
            .presentationCompactAdaptation(.popover)
        }
    }
}

struct PresentationSection: View {
    @Environment(AppModel.self) private var model
    @Binding var settings: FrameSettings
    @State private var target = LaunchRoute.screen == "presentation-photo" ? Target.photo : .art
    /// `settings` after a short pause, so a slider drag renders once.
    @State private var previewed: FrameSettings?
    /// What the preview shows for a kind the frame is not showing now: the
    /// last of that kind on the frame, else one drawn from the library.
    @State private var standIns: [Target: String] = [:]
    /// Kinds the library has nothing of.
    @State private var emptyKinds: Set<Target> = []

    enum Target: String, CaseIterable {
        case art = "Sztuka"
        case photo = "Zdjęcia"
    }

    private var presentation: Binding<Presentation> {
        target == .art ? $settings.art : $settings.photo
    }

    private var isMulti: Bool { target == .photo && presentation.fit.wrappedValue == "multi" }

    /// The passe-partout's width in millimetres on the panel, in 5 mm steps.
    private var marginMillimetres: Binding<Double> {
        Binding(
            get: { (Panel.millimetres(presentation.margin.wrappedValue) / 5).rounded() * 5 },
            set: { presentation.margin.wrappedValue = Panel.margin(mm: $0) }
        )
    }

    private var matSwatches: some View {
        ForEach(MatSwatch.names, id: \.self) { name in
            MatSwatch(name: name, selected: presentation.mat.wrappedValue == name) {
                presentation.mat.wrappedValue = name
            }
        }
    }

    /// The picture on the frame, when the selected presentation applies to it.
    private var currentID: String? {
        guard let item = model.player?.current?.item else { return nil }
        return (item.kind == .photo) == (target == .photo) ? item.id : nil
    }

    private var previewID: String? { currentID ?? standIns[target] }

    /// A picture of `target`'s kind to preview: the last one on the frame,
    /// else a random one of the library, the owner's works first.
    private func drawStandIn() async {
        let target = target
        let photo = target == .photo
        if let last = model.player?.history.first(where: { ($0.kind == .photo) == photo }) {
            standIns[target] = last.id
            return
        }
        var query = LibraryQuery()
        query.kinds = photo ? [.photo] : [.artwork, .own]
        query.keptOnly = !photo
        query.sort = photo ? "recent" : "suitability"
        var pool: [String] = []
        do {
            pool = try await model.backend.items(query).items.map(\.id)
            if pool.isEmpty, query.keptOnly {
                query.keptOnly = false
                pool = try await model.backend.items(query).items.map(\.id)
            }
            // Photos sent once are not in the library's lists, only in theirs.
            if photo, let sent = model.playlists.first(where: { $0.name == PlaylistSummary.sentName }) {
                pool += (try? await model.backend.playlist(id: sent.id).itemIds) ?? []
            }
        } catch {
            return  // no server now: the next visit tries again
        }
        if pool.isEmpty {
            emptyKinds.insert(target)
        } else {
            emptyKinds.remove(target)
            standIns[target] = pool.randomElement()
        }
    }

    /// The frame with the picture on it, or, for the other kind, with one of
    /// that kind to try the settings on.
    private var preview: some View {
        let portrait = settings.orientation == "portrait"
        let empty = previewID == nil && emptyKinds.contains(target)
        return FramedArtwork(
            ref: previewID.map { ImageRef.framePreview($0, settings: previewed ?? settings, ownLook: false) },
            aspectRatio: portrait ? 9.0 / 16.0 : 16.0 / 9.0,
            placeholder: MatSwatch.color(presentation.mat.wrappedValue),
            moulding: 5
        ) {
            if empty {
                Text(target == .photo ? "Brak zdjęć w bibliotece" : "Brak dzieł w bibliotece")
                    .font(.caption)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(Theme.inkSoft)
                    .padding(8)
            }
        }
        .frame(maxWidth: portrait ? 190 : .infinity)
        .frame(maxWidth: .infinity)
        .padding(.vertical, 6)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Prezentacja")
            Picker("Dla", selection: $target) {
                ForEach(Target.allCases, id: \.self) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            preview
                .task(id: settings) {
                    try? await Task.sleep(for: .milliseconds(450))
                    if !Task.isCancelled { previewed = settings }
                }
                .task(id: "\(target.rawValue) \(model.player != nil)") {  // the history comes with the player
                    if model.player != nil, currentID == nil, standIns[target] == nil { await drawStandIn() }
                }
            Card {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Kadrowanie").foregroundStyle(Theme.ink)
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3), spacing: 8) {
                        ForEach(target == .photo ? FitOption.photoModes : FitOption.modes, id: \.fit) { mode in
                            FitOption(
                                title: mode.title, fit: mode.fit, mat: MatSwatch.color(presentation.mat.wrappedValue),
                                selected: presentation.fit.wrappedValue == mode.fit
                            ) {
                                presentation.fit.wrappedValue = mode.fit
                                if mode.fit == "fit", presentation.margin.wrappedValue == 0 {
                                    presentation.margin.wrappedValue = Panel.margin(mm: 20)
                                }
                                if mode.fit == "multi", presentation.margin.wrappedValue < Panel.margin(mm: 20) {
                                    presentation.margin.wrappedValue = Panel.margin(mm: 30)
                                }
                            }
                        }
                    }
                }
                if isMulti {
                    Divider()
                    MultiSettings(presentation: presentation, portrait: settings.orientation == "portrait")
                }
                Divider()
                VStack(alignment: .leading, spacing: 10) {
                    Text("Passe-partout").foregroundStyle(Theme.ink)
                    HStack(spacing: 0) { matSwatches }
                }
                if presentation.fit.wrappedValue != "fill" {
                    Divider()
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Szerokość passe-partout")
                            Spacer()
                            Text("\(Int(Panel.millimetres(presentation.margin.wrappedValue).rounded())) mm")
                                .monospacedDigit()
                                .foregroundStyle(Theme.inkSoft)
                        }
                        Slider(value: marginMillimetres, in: 0 ... 80, step: 5)
                    }
                }
                if target == .art {
                    Divider()
                    Toggle("Podpis na ramce", isOn: presentation.label)
                }
            }
            .tint(Theme.accent)
        }
    }
}

/// Miniature showing how a fit mode places a portrait picture on the frame.
struct FitOption: View {
    let title: String
    let fit: String
    var mat: Color = Theme.matWhite
    let selected: Bool
    let action: () -> Void

    static let modes: [(fit: String, title: String)] = [
        ("fit", "Passe-partout"), ("fill", "Wypełnij"), ("description", "Opis"),
    ]

    /// Photos have their own framings (server: schedule.PHOTO_FITS).
    static let photoModes: [(fit: String, title: String)] = [
        ("fit", "Passe-partout"), ("fill", "Wypełnij"), ("multi", "Multi"),
    ]

    var body: some View {
        Button(action: action) {
            VStack(spacing: 8) {
                ZStack {
                    Rectangle().fill(mat)
                    miniature
                }
                .aspectRatio(1, contentMode: .fit)  // square: the same for portrait and landscape frames
                .frame(height: 52)
                .whiteFrame(3, corner: 1)
                .selectionRing(selected)
                Text(title)
                    .font(.caption2.weight(.medium))
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                    .foregroundStyle(Theme.ink)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 6)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(title)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    @ViewBuilder private var miniature: some View {
        let art = Theme.accent.opacity(0.75)
        switch fit {
        case "fill":
            Rectangle().fill(art)
        case "description":
            HStack(spacing: 4) {
                Rectangle().fill(art).frame(width: 14)
                VStack(alignment: .leading, spacing: 2) {
                    Rectangle().fill(art.opacity(0.7))
                    Spacer(minLength: 2)
                    ForEach([1.0, 0.9, 0.95, 0.6], id: \.self) { share in
                        GeometryReader { geo in
                            Rectangle().fill(Theme.ink.opacity(0.55)).frame(width: geo.size.width * share, height: 1.5)
                        }
                        .frame(height: 1.5)
                    }
                }
                .padding(.vertical, 5)
                .padding(.trailing, 5)
            }
        case "multi":
            HStack(spacing: 4) {
                Rectangle().fill(art)
                VStack(spacing: 4) {
                    Rectangle().fill(art.opacity(0.8))
                    Rectangle().fill(art.opacity(0.8))
                }
                .frame(width: 12)
            }
            .padding(8)
        default:
            Rectangle().fill(art).padding(10)
        }
    }
}

extension View {
    /// The chosen miniature: an accent outline a little off its frame, no tile around it.
    func selectionRing(_ selected: Bool) -> some View {
        overlay(
            RoundedRectangle(cornerRadius: 3)
                .strokeBorder(selected ? Theme.accent : .clear, lineWidth: 2)
                .padding(-5)
        )
    }
}

/// One passe-partout colour to choose.
struct MatSwatch: View {
    let name: String
    let selected: Bool
    let action: () -> Void

    static let names = ["white", "cream", "grey", "black", "picture", "picture_dark"]

    static func color(_ name: String) -> Color {
        switch name {
        case "cream": Color(hex: 0xFBF3D3)  // the white swatch as mat._cream tints it
        case "grey": Color(hex: 0xAEADAA)
        case "black": Color(hex: 0x1F1E1C)
        case "picture": Color(hex: 0xE9DCCB)  // stands in for "a tint of the picture"
        case "picture_dark": Color(hex: 0x3A302C)  // the same, on a deep board
        default: Color(hex: 0xFBFAF7)
        }
    }

    static func title(_ name: String) -> String {
        switch name {
        case "cream": "Kremowe"
        case "grey": "Szare"
        case "black": "Czarne"
        case "picture": "Jasne"
        case "picture_dark": "Ciemne"
        default: "Białe"
        }
    }

    /// Tints in a ring, muted or deep: the mat takes its colour from each picture.
    private var fill: AnyShapeStyle {
        let ring: [UInt32]
        switch name {
        case "picture": ring = [0xE8C9C0, 0xEADCC0, 0xD3DEC8, 0xC6D6DE, 0xD6CBDD, 0xE8C9C0]
        case "picture_dark": ring = [0x45302D, 0x403628, 0x2D3A31, 0x2B3444, 0x382F40, 0x45302D]
        default: return AnyShapeStyle(Self.color(name))
        }
        return AnyShapeStyle(AngularGradient(colors: ring.map { Color(hex: $0) }, center: .center))
    }

    var body: some View {
        Button(action: action) {
            VStack(spacing: 6) {
                RoundedRectangle(cornerRadius: 6)
                    .fill(fill)
                    .frame(width: 40, height: 30)
                    .overlay(
                        // The window cut at 45°: a light inner edge.
                        RoundedRectangle(cornerRadius: 2)
                            .strokeBorder(.white.opacity(name == "white" ? 0 : 0.8), lineWidth: 1.5)
                            .padding(8)
                    )
                    .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(Theme.inkSoft.opacity(0.35), lineWidth: 0.75))
                    .padding(3)
                    .overlay(RoundedRectangle(cornerRadius: 9).strokeBorder(selected ? Theme.accent : .clear, lineWidth: 2))
                Text(Self.title(name))
                    .font(.caption2.weight(.medium))
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                    .foregroundStyle(selected ? Theme.ink : Theme.inkSoft)
            }
            .frame(maxWidth: .infinity)  // six in one row
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Passe-partout \(Self.title(name).lowercased())")
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

/// How the frame hangs. A portrait frame is the panel turned 90° to the right.
struct ScreenSection: View {
    @Binding var settings: FrameSettings

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Orientacja")
            Card {
                HStack(spacing: 8) {
                    OrientationPill(title: "Pozioma", portrait: false, selected: settings.orientation == "landscape") {
                        settings.orientation = "landscape"
                    }
                    OrientationPill(title: "Pionowa", portrait: true, selected: settings.orientation == "portrait") {
                        settings.orientation = "portrait"
                        settings.rotation = 90
                    }
                }
            }
        }
    }
}

/// A frame hanging one way or the other, to pick: a pill like the
/// schedule's, led by a small frame of that shape.
private struct OrientationPill: View {
    let title: String
    let portrait: Bool
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                RoundedRectangle(cornerRadius: 1.5)
                    .strokeBorder(lineWidth: 1.75)
                    .frame(width: portrait ? 11 : 18, height: portrait ? 18 : 11)
                    .frame(width: 18, height: 18)
                Text(title)
                    .font(.subheadline.weight(.medium))
                    .lineLimit(1)
            }
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 8)
            .padding(.vertical, 9)
            .foregroundStyle(selected ? Theme.accent : Theme.ink)
            .background(selected ? Theme.accent.opacity(0.17) : Theme.mat, in: Capsule())
        }
        .buttonStyle(.plain)
        .sensoryFeedback(.selection, trigger: selected)
        .accessibilityLabel(title)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

/// Konfiguracja: where the server takes art from. Saved as soon as switched.
struct SourcesSection: View {
    @Environment(AppModel.self) private var model
    let settings: FrameSettings

    private var privateUse: Binding<Bool> {
        Binding(get: { settings.privateUse ?? false }, set: { on in save { $0.privateUse = on } })
    }

    private var wikiart: Binding<Bool> {
        Binding(get: { settings.wikiart ?? false }, set: { on in save { $0.wikiart = on } })
    }

    private func save(_ change: (inout FrameSettings) -> Void) {
        var new = settings
        change(&new)
        Task { await model.saveSettings(new) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Źródła dzieł")
            Card {
                Text("Muzea, Wikimedia Commons, Europeana i Openverse dają dzieła wolne do pokazywania: domenę publiczną (w UE 70 lat po śmierci twórcy), a przy użytku prywatnym także licencje Creative Commons.")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                Divider()
                Toggle(isOn: privateUse) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Użytek prywatny")
                        Text(
                            privateUse.wrappedValue
                                ? "Z Wikimedia Commons, Europeany i Openverse także dzieła na wolnych licencjach (np. CC BY-SA), z podanym autorem. Muzea nadal dają tylko domenę publiczną."
                                : "Tylko dzieła w domenie publicznej (CC0). Opisy w oryginale, po angielsku."
                        )
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                    }
                }
                .tint(Theme.accent)
                Divider()
                Toggle(isOn: wikiart) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("WikiArt (tylko testy)")
                        Text("Wyłącznie do testów panelu na nowszej sztuce. WikiArt pokazuje dzieła chronione prawem autorskim bez licencji, więc nie trafiają one do Propozycji, a po wyłączeniu przełącznika znikają z biblioteki.")
                            .font(.caption)
                            .foregroundStyle(Theme.inkSoft)
                    }
                }
                .tint(Theme.accent)
            }
        }
    }
}

/// The frame's Wi-Fi as the Frame app on the panel last read it: how strong
/// the signal is, the network, its address and band, and a warning when it
/// is not where the server looks for it.
struct PanelWifiRow: View {
    let wifi: PanelWifi

    private var wrong: Bool { wifi.wrongNetwork == true }

    private var details: String {
        [wifi.ip, wifi.band, When.ago(wifi.readAt)].compactMap { $0 }.joined(separator: " · ")
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Group {
                if !wrong, let arcs = wifi.arcs {
                    WifiStrengthIcon(arcs: arcs, color: arcs <= 1 ? Theme.warn : Theme.good)
                        .accessibilityLabel(wifi.strength ?? "Wi-Fi")
                } else {
                    Image(systemName: wrong ? "wifi.exclamationmark" : "wifi")
                        .font(.title2)
                        .foregroundStyle(wrong ? Theme.bad : Theme.good)
                }
            }
            .frame(width: 32)
            VStack(alignment: .leading, spacing: 3) {
                Text(wifi.ssid.map { "Wi-Fi ramki: \($0)" } ?? "Wi-Fi ramki")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Theme.ink)
                Text(details)
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                if let warning = wifi.warning {
                    Text(warning)
                        .font(.caption)
                        .foregroundStyle(Theme.bad)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .accessibilityElement(children: .combine)
    }
}

/// Behind the gear in "Ramka": how the server reaches the panel, how the
/// app reaches the server, where the art comes from, how much disk the
/// library may take and the language model's key; set once, rarely touched
/// again.
struct ConnectionSettingsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 28) {
                    if let panel = model.panelConfig {
                        PanelSection(config: panel)
                    }
                    if let app = model.panelApp {
                        PanelAppSection(app: app)
                    }
                    ServerSection()
                    if let settings = model.settings {
                        SourcesSection(settings: settings)
                    }
                    if let storage = model.libraryStorage {
                        LibrarySizeSection(storage: storage)
                    }
                    if let ai = model.aiSettings {
                        AiSection(settings: ai)
                    }
                }
                .padding(.horizontal, Theme.gutter)
                .padding(.top, 8)
                .padding(.bottom, 40)
            }
            .background(Theme.paper)
            .scrollDismissesKeyboard(.interactively)
            .task { await model.loadLibraryStorage() }
            .task { await model.loadPanelApp() }
            .task { await model.loadServerUpdate() }
            .task { await model.loadAiSettings() }
            .navigationTitle("Konfiguracja")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Gotowe") { dismiss() }
                }
            }
        }
    }
}

/// How the server reaches the panel: its address, the MDC PIN and the MAC
/// for Wake-on-LAN, saved on the server (over frame.env / add-on options).
struct PanelSection: View {
    @Environment(AppModel.self) private var model
    let config: PanelConfig
    @State private var host = ""
    @State private var pin = ""
    @State private var mac = ""
    @State private var saving = false

    private var hostValue: String? { PanelAddress.host(host) }
    private var macValue: String? { PanelAddress.mac(mac) }
    private var changed: Bool {
        hostValue != (config.host ?? "") || macValue != (config.mac ?? "") || !pin.isEmpty
    }
    private var valid: Bool { !(hostValue ?? "").isEmpty && macValue != nil }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Połączenie z ekranem", subtitle: "Gdzie serwer szuka ramki w sieci")
            Card {
                if let wifi = model.status?.device.wifi {
                    PanelWifiRow(wifi: wifi)
                    Divider()
                }
                field("Adres IP ekranu", error: hostValue == nil ? "To nie wygląda na adres IP" : nil) {
                    TextField("np. 203.0.113.152", text: $host)
                        .keyboardType(.numbersAndPunctuation)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
                Divider()
                field("Kod PIN", hint: "PIN do sterowania (MDC), ekran pokazuje go przy parowaniu w aplikacji Samsung E-Paper.") {
                    SecureField(config.pinSet ? "ustawiony · puste zostawia bez zmian" : "np. 000000", text: $pin)
                        .keyboardType(.numberPad)
                }
                Divider()
                field(
                    "Adres MAC",
                    hint: "Do budzenia ekranu (Wake-on-LAN). Puste pole wyłącza budzenie.",
                    error: macValue == nil ? "MAC to 12 znaków szesnastkowych, np. A4:30:7A:01:02:FF" : nil
                ) {
                    TextField("AA:BB:CC:DD:EE:FF", text: $mac)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                }
                Divider()
                Button {
                    Task { await save() }
                } label: {
                    HStack {
                        Text("Zapisz i sprawdź")
                        if saving { ProgressView() }
                    }
                }
                .fontWeight(.semibold)
                .disabled(!changed || !valid || saving)
                Text(config.fromApp
                    ? "Ustawione w aplikacji, mają pierwszeństwo przed frame.env i opcjami add-onu."
                    : "Wartości z frame.env lub opcji add-onu. Zapisane tutaj będą miały pierwszeństwo.")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                if let device = model.status?.device, let firmware = device.firmware {
                    Text("Ekran \(device.model ?? "EM32DX") · firmware \(firmware)")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
                if config.fromApp {
                    Button("Przywróć wartości z serwera") {
                        Task {
                            saving = true
                            await model.resetPanelConfig()
                            saving = false
                        }
                    }
                    .font(.subheadline)
                    .disabled(saving)
                }
            }
        }
        .onAppear { load(config) }
        .onChange(of: config) { _, new in load(new) }
    }

    private func field<Content: View>(
        _ title: String, hint: String? = nil, error: String? = nil, @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
            content()
            if let error {
                Text(error).font(.caption).foregroundStyle(Theme.bad)
            } else if let hint {
                Text(hint).font(.caption).foregroundStyle(Theme.inkSoft)
            }
        }
    }

    private func load(_ config: PanelConfig) {
        host = config.host ?? ""
        mac = config.mac ?? ""
        pin = ""
    }

    private func save() async {
        saving = true
        defer { saving = false }
        let update = PanelConfigUpdate(
            host: hostValue,
            pin: pin.isEmpty ? nil : pin,
            mac: macValue?.isEmpty == false ? macValue : nil,
            port: config.port
        )
        await model.savePanelConfig(update)
    }
}

/// "Certyfikaty aplikacji ramki wygasają 27 października 2027…".
/// A power mode changed while the frame sleeps: it takes it on only when it
/// wakes (in deep sleep nothing reaches it), so the app says when.
func modePendingText(_ device: DeviceStatus) -> String? {
    guard let mode = device.modePending else { return nil }
    let name = mode == "economy" ? "Oszczędny" : "Online"
    let when = When.at(device.wakeAt).map { " (\($0))" } ?? ""
    let asleep = device.powerState == "deep_sleep" ? " Teraz śpi bez Wi-Fi i zmiana do niej nie dotrze." : ""
    return "Ramka przejdzie w tryb \(name) przy najbliższej pobudce\(when) albo po naciśnięciu guzika na ramce.\(asleep)"
}

func certificatesText(_ expires: String) -> String {
    let date = When.date(expires)
    let day = date?.formatted(.dateTime.day().month(.wide).year().locale(Locale(identifier: "pl_PL"))) ?? expires
    if let date, date < .now {
        return "Certyfikaty aplikacji ramki wygasły \(day). Odnów je w Certificate Managerze Tizen Studio i wgraj ponownie na serwer, inaczej ramka nie przyjmie nowej wersji aplikacji."
    }
    return "Certyfikaty aplikacji ramki wygasają \(day). Odnów je w Certificate Managerze Tizen Studio i wgraj ponownie na serwer."
}

/// A one-line note under the status tiles.
struct NoticeRow: View {
    let icon: String
    let color: Color
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: icon).foregroundStyle(color)
            Text(text).font(.caption).foregroundStyle(Theme.ink)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// The Frame app on the panel, the only way pictures reach the frame: the
/// package the server built and signed, what the frame runs, the
/// certificates, and a button that starts it again.
struct PanelAppSection: View {
    @Environment(AppModel.self) private var model
    let app: PanelAppView
    @State private var installing = false

    private var certificatesUntil: String? {
        let dates = (app.certificates ?? []).compactMap { When.date($0.expiresAt) }
        return dates.min()?.formatted(.dateTime.day().month(.wide).year().locale(Locale(identifier: "pl_PL")))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Aplikacja ramki", subtitle: "Ramka sama się budzi i pobiera obrazy")
            Card {
                VStack(alignment: .leading, spacing: 4) {
                    Text(app.active ? "Ramka działa w aplikacji Frame" : "Ramka nie uruchomiła jeszcze aplikacji")
                        .foregroundStyle(Theme.ink)
                    if app.active, let seen = When.ago(app.state.seenAt) {
                        Text("Ostatnio pytała o obraz \(seen)")
                            .font(.caption)
                            .foregroundStyle(Theme.inkSoft)
                    } else if !app.active {
                        Text("Serwer uruchamia ją sam, gdy ramka nie śpi.")
                            .font(.caption)
                            .foregroundStyle(Theme.inkSoft)
                    }
                }
                Divider()
                if let package = app.package {
                    Text("Wersja \(package.version) zbudowana na serwerze\(app.state.build.map { ", na ramce \($0)" } ?? "").")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                } else {
                    Text("Na serwerze nie ma jeszcze certyfikatów Samsunga, więc nie zbuduje aplikacji. Skopiuj raz author.p12, distributor.p12 i password.txt do folderu data/panel-app/certs serwera (np. File Station) albo uruchom scripts/panel-app/upload-certs.sh na Macu.")
                        .font(.caption)
                        .foregroundStyle(Theme.warn)
                }
                if let expires = app.certificatesExpireAt {
                    Text(certificatesText(expires))
                        .font(.caption)
                        .foregroundStyle(Theme.warn)
                } else if let until = certificatesUntil {
                    Text("Certyfikaty ważne do \(until).")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
                Divider()
                Button {
                    Task {
                        installing = true
                        await model.installPanelApp()
                        installing = false
                    }
                } label: {
                    HStack {
                        Text(app.active ? "Uruchom aplikację ponownie" : "Uruchom aplikację na ramce")
                        if installing { ProgressView() }
                    }
                }
                .fontWeight(.semibold)
                .disabled(installing || app.package == nil)
            }
        }
    }
}

struct ServerSection: View {
    @Environment(AppModel.self) private var model
    @State private var testing = false

    var body: some View {
        @Bindable var model = model
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Serwer ramki", subtitle: "Add-on Home Assistant lub kontener na Synology")
            Card {
                Toggle(isOn: $model.demoMode) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Tryb demo")
                        Text("Przykładowe dzieła bez serwera").font(.caption).foregroundStyle(Theme.inkSoft)
                    }
                }
                .tint(Theme.accent)
                if !model.demoMode {
                    Divider()
                    AddressField(title: "W domu", prompt: "http://homeassistant.local:8099", text: $model.serverURL)
                    Divider()
                    AddressField(title: "Spoza domu", prompt: "Tailscale, np. http://100.64.0.5:8099", text: $model.remoteURL)
                    Text("Opcjonalny. Aplikacja sama wybiera adres, który odpowiada, a domowy ma pierwszeństwo.")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                    Divider()
                    SecureField("Token API", text: $model.apiToken)
                }
                Divider()
                Button {
                    Task {
                        testing = true
                        await model.applyConnection()
                        testing = false
                    }
                } label: {
                    HStack {
                        Text(model.demoMode ? "Zastosuj" : "Połącz")
                        if testing { ProgressView() }
                    }
                }
                .fontWeight(.semibold)
                connectionLine
                if let server = model.status?.server {
                    Text("Serwer \(server.version) · \(Names.works(server.libraryCount)) · \(server.playlists) playlist")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
                if let update = model.serverUpdate {
                    Divider()
                    ServerUpdateRow(update: update)
                }
            }
        }
    }

    @ViewBuilder
    private var connectionLine: some View {
        switch model.connection {
        case .connected:
            Label(connectedText, systemImage: "checkmark.circle.fill")
                .font(.subheadline)
                .foregroundStyle(Theme.good)
        case let .failed(message):
            Label(message, systemImage: "exclamationmark.triangle.fill")
                .font(.subheadline)
                .foregroundStyle(Theme.bad)
        case .unknown:
            EmptyView()
        }
    }

    private var connectedText: String {
        if model.demoMode { return "Tryb demo" }
        switch model.serverPath {
        case .remote: return "Połączono spoza domu"
        case .home where !model.remoteURL.isEmpty: return "Połączono w domu"
        default: return "Połączono"
        }
    }
}

/// "Aktualizuj serwer": the newest server image, put in place by the
/// `frame-updater` helper next to the server on Synology.
private struct ServerUpdateRow: View {
    @Environment(AppModel.self) private var model
    let update: ServerUpdate
    @State private var checking = false
    @State private var confirming = false

    private var working: Bool { checking || model.updatingServer || update.busy }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Text("Wersja serwera").font(.subheadline).foregroundStyle(Theme.ink)
                Spacer()
                Text(update.version)
                    .font(.subheadline.monospacedDigit())
                    .foregroundStyle(Theme.inkSoft)
            }
            if update.addon {
                caption("Add-on aktualizuje Home Assistant: Ustawienia → Dodatki → Frame.")
            } else if !update.updater {
                caption("Aby aktualizować serwer stąd, raz dodaj pomocnika na NAS-ie: Container Manager → Projekt → frame → Zatrzymaj, potem Konfiguracja YAML → Edytuj, wklej aktualny docker-compose.yml i Kompiluj. Do tego czasu aktualizuje Projekt → frame → Kompiluj.")
            } else {
                status
                Button {
                    if update.offersUpdate {
                        confirming = true
                    } else {
                        Task {
                            checking = true
                            await model.checkServerUpdate()
                            checking = false
                        }
                    }
                } label: {
                    HStack {
                        Text(update.offersUpdate ? "Aktualizuj serwer" : "Sprawdź aktualizacje")
                        if working { ProgressView() }
                    }
                }
                .fontWeight(.semibold)
                .disabled(working)
                .confirmationDialog(
                    "Aktualizować serwer do wersji \(update.latestVersion ?? "najnowszej")?",
                    isPresented: $confirming,
                    titleVisibility: .visible
                ) {
                    Button("Aktualizuj serwer") { Task { await model.updateServer() } }
                } message: {
                    Text("Serwer zniknie na około minutę. Gdyby nowa wersja nie wystartowała, wróci obecna.")
                }
            }
        }
    }

    @ViewBuilder
    private var status: some View {
        if model.updatingServer || update.state == "updating" {
            caption("Aktualizuję. Serwer wróci za około minutę.")
        } else if update.state == "checking" || update.pending == "check" {
            caption("Sprawdzam, czy jest nowsza wersja…")
        } else if update.offersUpdate {
            Text("Dostępna wersja \(update.latestVersion ?? "nowsza")")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(Theme.accent)
        } else if let checked = When.ago(update.checkedAt) {
            caption("Aktualna, sprawdzono \(checked)")
        }
        if update.state == "failed", let error = update.error {
            Text(error).font(.caption).foregroundStyle(Theme.warn)
        } else if let last = update.lastUpdate, last.ok, let at = When.ago(last.at) {
            caption("Zaktualizowano \(at)\(last.toVersion.map { " do \($0)" } ?? "").")
        }
    }

    private func caption(_ text: String) -> some View {
        Text(text)
            .font(.caption)
            .foregroundStyle(Theme.inkSoft)
    }
}

/// How much disk the library takes on the server, and its two limits:
/// beyond them the server trims what it can fetch again.
struct LibrarySizeSection: View {
    @Environment(AppModel.self) private var model
    let storage: LibraryStorage

    private var usage: LibraryStorage.Usage { storage.usage }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Biblioteka na serwerze", subtitle: "Ile miejsca zajmują dzieła i zdjęcia")
            Card {
                VStack(alignment: .leading, spacing: 8) {
                    Text(ByteSize.bytes(usage.totalBytes))
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(Theme.ink)
                    row("Obrazy przygotowane dla ekranu", usage.panelBytes)
                    row("Baza danych", usage.databaseBytes)
                    if let free = usage.freeBytes {
                        row("Wolne na dysku", free)
                    }
                }
                Divider()
                VStack(alignment: .leading, spacing: 8) {
                    LimitRow(
                        title: "Katalog (miniatury)",
                        used: usage.catalogueBytes,
                        limitMb: storage.catalogueMb,
                        defaultMb: storage.catalogueDefaultMb,
                        options: [500, 1000, 1500, 2000, 3000, 5000, 10000, 20000]
                    ) { mb in await model.setLibraryLimit(catalogueMb: mb) }
                    caption("Ponad limit znikają najsłabsze na e-papierze dzieła, które serwer dobrał sam. Ulubione, playlisty, kolejka i pokazane dzieła zostają. Większy katalog to więcej w Odkrywaj.")
                }
                Divider()
                VStack(alignment: .leading, spacing: 8) {
                    LimitRow(
                        title: "Oryginały dzieł",
                        used: usage.originalsBytes,
                        limitMb: storage.originalsMb,
                        defaultMb: storage.originalsDefaultMb,
                        options: [500, 1000, 2000, 3000, 5000, 10000, 20000, 50000]
                    ) { mb in await model.setLibraryLimit(originalsMb: mb) }
                    caption("Oryginał to około 1,5 MB. Ponad limit znikają najdawniej oglądane, a te z Ulubionych i playlist na samym końcu. Usunięty serwer pobierze ponownie z muzeum lub albumu, gdy będzie potrzebny.")
                }
                Divider()
                VStack(alignment: .leading, spacing: 8) {
                    row("Przesłane zdjęcia i prace", usage.ownBytes)
                    caption("Przesłanych plików nie da się pobrać ponownie, więc zostają zawsze i nie wliczają się do limitów.")
                    if !storage.catalogueFromApp || !storage.originalsFromApp {
                        caption("„domyślnie” to wartość z frame.env lub opcji add-onu. Zmieniona tutaj ma pierwszeństwo.")
                    }
                }
            }
        }
    }

    private func caption(_ text: String) -> some View {
        Text(text)
            .font(.caption)
            .foregroundStyle(Theme.inkSoft)
    }

    private func row(_ title: String, _ bytes: Int64) -> some View {
        HStack {
            Text(title).font(.subheadline).foregroundStyle(Theme.ink)
            Spacer()
            Text(ByteSize.bytes(bytes))
                .font(.subheadline.monospacedDigit())
                .foregroundStyle(Theme.inkSoft)
        }
    }
}

/// One limit of the library: what it holds now, a bar, and a picker.
private struct LimitRow: View {
    let title: String
    let used: Int64
    let limitMb: Int
    let defaultMb: Int
    /// Limits to pick from, in MB; the default and the current one join them.
    let options: [Int]
    let save: @MainActor (Int) async -> Void

    private var fill: Double {
        let limit = Double(limitMb) * 1_048_576
        return limit > 0 ? Double(used) / limit : 1
    }

    var body: some View {
        let limit = Binding(
            get: { limitMb },
            set: { mb in Task { await save(mb) } }
        )
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                Spacer()
                Text(ByteSize.bytes(used))
                    .font(.subheadline.monospacedDigit())
                    .foregroundStyle(Theme.inkSoft)
            }
            ProgressView(value: min(fill, 1))
                .tint(fill > 1.02 ? Theme.bad : Theme.accent)
                .accessibilityLabel("\(title): zajęte \(Int((fill * 100).rounded())) procent limitu")
            HStack {
                Text("Maksymalnie").font(.subheadline).foregroundStyle(Theme.ink)
                Spacer()
                Picker("\(title): maksymalnie", selection: limit) {
                    ForEach(Set(options + [defaultMb, limitMb]).sorted(), id: \.self) { mb in
                        Text(mb == defaultMb ? "\(ByteSize.mb(mb)) · domyślnie" : ByteSize.mb(mb))
                            .tag(mb)
                    }
                }
                .labelsHidden()
                .tint(Theme.accent)
            }
        }
    }
}

/// A server address with its label above.
private struct AddressField: View {
    let title: String
    let prompt: String
    @Binding var text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.caption).foregroundStyle(Theme.inkSoft)
            TextField(prompt, text: $text)
                .keyboardType(.URL)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
        }
    }
}

/// A day from midnight to midnight with the economy mode's wakes on it: the
/// changes, the checks between them and the quiet hours without checks; the
/// rest is deep sleep.
struct WakeStrip: View {
    let changes: [Int]  // minutes after midnight
    let checks: [Int]
    var quiet: (start: Int, end: Int)? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(Theme.accent.opacity(0.18)).frame(height: 8)
                    ForEach(quietSpans, id: \.0) { start, end in
                        Stripes()
                            .frame(width: x(end - start, geo.size.width), height: 8)
                            .clipShape(Capsule())
                            .offset(x: x(start, geo.size.width))
                    }
                    ForEach(checks, id: \.self) { minutes in
                        RoundedRectangle(cornerRadius: 1.5)
                            .fill(Theme.vermilion)
                            .frame(width: 3, height: 20)
                            .offset(x: x(minutes, geo.size.width) - 1.5)
                    }
                    ForEach(changes, id: \.self) { minutes in
                        RoundedRectangle(cornerRadius: 3)
                            .fill(Theme.accent)
                            .frame(width: 9, height: 14)
                            .offset(x: x(minutes, geo.size.width) - 4.5)
                    }
                }
                .frame(height: 20)
            }
            .frame(height: 20)
            GeometryReader { geo in
                ForEach(labels(geo.size.width), id: \.minutes) { label in
                    Text(Self.label(label.minutes))
                        .font(.caption2)
                        .monospacedDigit()
                        .foregroundStyle(Theme.inkSoft)
                        .fixedSize()
                        .position(x: label.x, y: 6)
                }
            }
            .frame(height: 12)
            // One line when it fits, else the wakes and the sleep in two.
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 12) {
                    wakeLegend
                    sleepLegend
                }
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 12) { wakeLegend }
                    HStack(spacing: 12) { sleepLegend }
                }
            }
            .font(.caption2)
            .foregroundStyle(Theme.inkSoft)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Pobudki: " + (changes + checks).sorted().map(Self.label).joined(separator: ", "))
    }

    /// The hours under the strip, centred under their marks and kept inside
    /// it: the changes first, then the checks, then 0 and 24; a label that
    /// would touch one already placed is left out.
    private func labels(_ width: CGFloat) -> [(minutes: Int, x: CGFloat)] {
        var placed: [(minutes: Int, x: CGFloat, half: CGFloat)] = []
        for minutes in changes + checks + [0, 24 * 60] where !placed.contains(where: { $0.minutes == minutes }) {
            // caption2 with monospaced digits: about 6.2 pt a character
            let half = (CGFloat(Self.label(minutes).count) * 6.2 + 2) / 2
            let x = min(max(x(minutes, width), half), width - half)
            guard !placed.contains(where: { abs($0.x - x) < $0.half + half + 4 }) else { continue }
            placed.append((minutes, x, half))
        }
        return placed.map { ($0.minutes, $0.x) }
    }

    @ViewBuilder private var wakeLegend: some View {
        legend(Theme.accent, checks.isEmpty ? "pobudka i zmiana" : "zmiana")
        if !checks.isEmpty { legend(Theme.vermilion, "sprawdzenie") }
    }

    @ViewBuilder private var sleepLegend: some View {
        if quiet != nil {
            HStack(spacing: 4) {
                Stripes().frame(width: 9, height: 9).clipShape(RoundedRectangle(cornerRadius: 2))
                Text("cisza nocna")
            }
        }
        legend(Theme.accent.opacity(0.18), "głęboki sen")
    }

    /// The quiet hours as spans within the day (two when they cross midnight).
    private var quietSpans: [(Int, Int)] {
        guard let quiet else { return [] }
        return quiet.start < quiet.end ? [(quiet.start, quiet.end)] : [(quiet.start, 24 * 60), (0, quiet.end)]
    }

    private func x(_ minutes: Int, _ width: CGFloat) -> CGFloat {
        width * CGFloat(minutes) / CGFloat(24 * 60)
    }

    private static func label(_ minutes: Int) -> String {
        minutes % 60 == 0 ? "\(minutes / 60)" : String(format: "%d:%02d", minutes / 60, minutes % 60)
    }

    private func legend(_ color: Color, _ text: String) -> some View {
        HStack(spacing: 4) {
            RoundedRectangle(cornerRadius: 2).fill(color).frame(width: 9, height: 9)
            Text(text)
        }
    }
}

/// Thin diagonal lines: the quiet hours on the wake strip.
struct Stripes: View {
    var body: some View {
        Canvas { context, size in
            var lines = Path()
            for x in stride(from: -size.height, to: size.width, by: 4) {
                lines.move(to: CGPoint(x: x, y: size.height))
                lines.addLine(to: CGPoint(x: x + size.height, y: 0))
            }
            context.stroke(lines, with: .color(Theme.ink.opacity(0.35)), lineWidth: 1.2)
        }
    }
}
