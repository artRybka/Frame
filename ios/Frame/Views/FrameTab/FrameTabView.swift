import SwiftUI

/// The frame itself: battery, charging, connection; schedule, presentation
/// and screen settings. How to reach the panel and the server sits behind the
/// gear at the top.
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

    private var device: DeviceStatus? { model.status?.device }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 28) {
                    deviceHero
                    statusGrid
                    appNotice
                    deviceActions
                    if draft != nil {
                        ScheduleSection(settings: binding)
                        PresentationSection(settings: binding)
                        ScreenSection(settings: binding)
                        SourcesSection(settings: binding)
                    }
                }
                .padding(.horizontal, Theme.gutter)
                .padding(.bottom, 40)
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
            draft = settings
        }
        base = settings
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

    /// `waking`: the "Sprawdź stan" button, which also tries to wake a
    /// sleeping frame; pulling to refresh only looks.
    private func refresh(waking: Bool = false) async {
        refreshing = true
        lastLook = .now
        defer { refreshing = false }
        if waking {
            await model.checkStatus()
        } else {
            await model.refreshStatus(live: true)
        }
        await model.refreshAll()
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

    private var connectionText: String {
        guard let device else { return "Brak danych" }
        if !device.configured { return "Podaj adres i PIN ekranu pod trybikiem u góry" }
        switch device.powerState {
        case "online": return "Połączona · \(When.ago(device.lastSeen) ?? "teraz")"
        case "standby":
            return device.onNetwork == true ? "Śpi w sieci, czeka na sygnał budzenia" : "Śpi, czeka na sygnał budzenia"
        case "deep_sleep": return "Głęboki sen, bez Wi-Fi"
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

    private var connectionColor: Color {
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
            if device.panelApp == false {
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
                BatteryRing(level: device?.batteryLevel, charging: device?.charging == true)
            }
            StatusTile(title: "Zasilanie") {
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
            StatusTile(title: "Obraz") {
                VStack(alignment: .leading, spacing: 6) {
                    Image(systemName: "clock.arrow.2.circlepath")
                        .font(.title2)
                        .foregroundStyle(Theme.accent)
                    Text(When.schedule(model.player?.nextChangeAt) ?? "—")
                        .font(.headline)
                        .foregroundStyle(Theme.ink)
                    Text(device?.pendingPush == true ? "obraz czeka na pobudkę ramki" : "następna zmiana")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
            }
            StatusTile(title: "Sieć") {
                let state = network
                VStack(alignment: .leading, spacing: 6) {
                    Image(systemName: state.icon)
                        .font(.title2)
                        .foregroundStyle(state.color)
                    Text(state.title)
                        .font(.headline)
                        .foregroundStyle(Theme.ink)
                    Text(state.note)
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .lineLimit(2)
                }
            }
        }
    }

    /// The Sieć tile: what the frame is doing, as far as the server can tell
    /// (the title: Online, Czuwanie, Głęboki sen...), with the network and
    /// how strong its signal is when the Frame app reads the Wi-Fi. A plain
    /// Wi-Fi icon, yellow for a weak signal.
    private var network: (icon: String, color: Color, title: String, note: String) {
        let (icon, color, title, note) = networkState
        let wifi = device?.wifi
        if wifi?.wrongNetwork == true {
            let note = wifi?.ssid.map { "połączona z \($0)" } ?? "inny adres niż zwykle"
            return ("wifi.exclamationmark", Theme.bad, "Obca sieć", note)
        }
        guard device?.powerState == "online", let wifi, let signal = wifi.signal else {
            return (icon, color, title, note)
        }
        let word = signal < 0.35 ? "słaby" : signal < 0.65 ? "średni" : "dobry"
        let place = [wifi.ssid, "sygnał \(word)"].compactMap { $0 }.joined(separator: " · ")
        return (icon, signal < 0.35 ? Theme.warn : color, title, place)
    }

    private var networkState: (icon: String, color: Color, title: String, note: String) {
        guard let device, device.configured else {
            return ("wifi", Theme.inkSoft, "—", "ekran nie jest ustawiony")
        }
        switch device.powerState {
        case "online":
            return ("wifi", Theme.good, "Online", "odpowiada · \(When.ago(device.lastSeen) ?? "teraz")")
        case "standby":
            let note = device.onNetwork == true ? "śpi, ale jest w sieci Wi-Fi" : "śpi, Wi-Fi czeka na sygnał budzenia"
            return ("moon.zzz", Theme.accent, "Czuwanie", note)
        case "deep_sleep":
            let note = device.wakesAt.map { "budzik o \($0), wcześniej przycisk na ramce" } ?? "Wi-Fi wyłączone, budzi przycisk"
            return ("wifi.slash", Theme.inkSoft, "Głęboki sen", note)
        case "offline":
            if device.onNetwork == false {
                return ("wifi.exclamationmark", Theme.bad, "Poza siecią", "nie ma jej w Wi-Fi")
            }
            return ("wifi.exclamationmark", Theme.bad, "Nie odpowiada", "śpi lub poza siecią")
        default:
            break
        }
        // A server before 0.12 only says whether network standby is on.
        if device.reachable == nil { return ("wifi", Theme.inkSoft, "Nie sprawdzono", "—") }
        return device.networkStandby == true
            ? ("wifi", Theme.good, "Czuwanie Wi-Fi", "budzi go sygnał Wi-Fi")
            : ("wifi.slash", Theme.inkSoft, "Głęboki sen", "Wi-Fi wyłączone")
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
        case "ac": device?.charging == true ? "Ładowanie" : "Zasilacz"
        case "battery": "Na baterii"
        default: "Nieznane"
        }
    }

    /// What the power source changes: the schedule is the same either way,
    /// only quiet hours on battery are spent in deep sleep.
    private var powerNote: String {
        if device?.charging == true { return "bateria się ładuje" }
        let quiet = model.settings?.quietStart != nil
        switch device?.powerSource {
        case "ac": return quiet ? "zdjęcia trafiają od razu, także w nocy" : "zdjęcia trafiają od razu"
        case "battery": return quiet ? "w ciszy nocnej śpi bez Wi-Fi" : "zmiany według harmonogramu"
        default: return "zmiany według harmonogramu"
        }
    }

    private var checkLabel: String {
        if model.wakingForStatus { return "Budzę ramkę…" }
        return refreshing ? "Sprawdzam…" : "Sprawdź stan"
    }

    private var deviceActions: some View {
        HStack(spacing: 10) {
            Button {
                Task { await refresh(waking: true) }
            } label: {
                Label(checkLabel, systemImage: model.wakingForStatus ? "sun.max" : "arrow.clockwise")
            }
            .buttonStyle(SecondaryButtonStyle())
            .disabled(refreshing)
            Menu {
                Button("Obudź ramkę", systemImage: "sun.max") { Task { await model.wake() } }
                Button("Uśpij ramkę", systemImage: "moon.zzz") { Task { await model.sleepFrame() } }
            } label: {
                Label("Zasilanie", systemImage: "power")
                    .font(.headline)
                    .foregroundStyle(Theme.ink)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 15)
                    .background(Theme.card, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(Theme.hairline))
            }
        }
    }
}

struct StatusTile<Content: View>: View {
    let title: String
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Eyebrow(title)
            content
            Spacer(minLength: 0)
        }
        .padding(16)
        .frame(maxWidth: .infinity, minHeight: 150, alignment: .topLeading)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).strokeBorder(Theme.hairline.opacity(0.7)))
    }
}

struct BatteryRing: View {
    let level: Int?
    let charging: Bool

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
                Text(estimate).font(.caption).foregroundStyle(Theme.inkSoft)
            }
        }
    }

    /// Rough: ~200 days at one change a day on a full battery (Samsung's figure).
    private var estimate: String {
        guard let level, !charging else { return charging ? "ładuje się" : "" }
        let days = Int(Double(level) / 100 * 200)
        return days > 60 ? "ok. \(days / 30) mies." : "ok. \(days) dni"
    }
}

// MARK: - Settings sections

struct ScheduleSection: View {
    @Environment(AppModel.self) private var model
    @Binding var settings: FrameSettings

    private let everyDays: [(Int, String)] = [(1, "codziennie"), (2, "co 2 dni"), (3, "co 3 dni")]
    private let maxTimes = 12

    private var artPlaylists: [PlaylistSummary] { model.playlists.filter { $0.kind != .album } }
    private var albums: [PlaylistSummary] { model.playlists.filter { $0.kind == .album } }
    private var playingAlbum: PlaylistSummary? { albums.first { $0.id == settings.playlistId } }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Harmonogram", subtitle: "Co i jak często pokazuje ramka")

            Card {
                row("Playlista") {
                    Picker("Playlista", selection: $settings.playlistId) {
                        Text("Propozycje").tag(Int?.none)
                        if !artPlaylists.isEmpty {
                            Section("Sztuka") {
                                ForEach(artPlaylists) { Text($0.name).tag(Int?.some($0.id)) }
                            }
                        }
                        if !albums.isEmpty {
                            Section("Albumy iCloud") {
                                ForEach(albums) { Label($0.name, systemImage: "icloud").tag(Int?.some($0.id)) }
                            }
                        }
                    }
                }
                Divider()
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
                if let album = playingAlbum?.album {
                    row("Kolejność") {
                        Text(album.order.title).foregroundStyle(Theme.inkSoft)
                    }
                    Text("Album ma własną kolejność zdjęć; zmienisz ją w jego playliście.")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                } else {
                    Toggle("Losowa kolejność", isOn: $settings.shuffle)
                }
                // Economy has its own quiet hours, for the checks (above).
                if !settings.isEconomy {
                    Divider()
                    quietHours
                }
            }
            .tint(Theme.accent)
        }
    }

    @ViewBuilder private var quietHours: some View {
        Toggle("Cisza nocna", isOn: quietEnabled)
        if settings.quietStart != nil {
            HStack {
                DatePicker("Od", selection: time(\.quietStart, fallback: "22:00"), displayedComponents: .hourAndMinute)
                Spacer()
                Text("do \(settings.quietEnd ?? "—")").foregroundStyle(Theme.inkSoft)
            }
            .font(.subheadline)
            Text("Cisza trwa do najbliższej zmiany obrazu. Na baterii ramka śpi wtedy z wyłączonym Wi-Fi i budzi się sama na tę zmianę, a zdjęcia wysłane w nocy pojawią się rano. Przy zasilaczu trafiają na ramkę od razu.")
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
            Text(settings.isEconomy
                ? "Ramka śpi bez Wi-Fi między pobudkami. Wysłane dzieło pojawi się przy najbliższej."
                : "Wysłane dzieło pojawia się po około minucie.")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
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
        (0, "Nie sprawdzaj"), (1, "godzinę"), (2, "2 godziny"), (3, "3 godziny"), (4, "4 godziny"), (6, "6 godzin"),
    ]

    /// Economy: short wakes between the changes, only for what was sent from the app.
    private var checksPicker: some View {
        VStack(alignment: .leading, spacing: 8) {
            row("Sprawdzaj też co") {
                Picker("Sprawdzaj też co", selection: checkEvery) {
                    ForEach(checkOptions, id: \.0) { hours, label in Text(label).tag(hours) }
                }
                .labelsHidden()
            }
            if (settings.checkEveryHours ?? 0) > 0, settings.checkQuietEnd != nil {
                checkQuietHours
            }
            WakeStrip(
                changes: settings.changeMinutes,
                checks: settings.checkMinutes,
                quiet: (settings.checkEveryHours ?? 0) > 0 ? settings.checkQuiet : nil
            )
            Text(wakeNote)
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
        }
    }

    /// Economy: the night without checks, from–to; the changes still wake the frame.
    @ViewBuilder private var checkQuietHours: some View {
        Toggle("Cisza nocna", isOn: checkQuietEnabled)
        if settings.checkQuietStart != nil {
            HStack {
                DatePicker("Od", selection: time(\.checkQuietStart, fallback: "22:00"), displayedComponents: .hourAndMinute)
                Spacer()
                DatePicker("do", selection: time(\.checkQuietEnd, fallback: "07:00"), displayedComponents: .hourAndMinute)
            }
            .font(.subheadline)
            Text("W tym czasie ramka nie sprawdza, budzi się tylko na zmiany.")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
        }
    }

    private var checkQuietEnabled: Binding<Bool> {
        Binding(
            get: { settings.checkQuietStart != nil },
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

    /// The times of day the picture changes at: one or more, sorted.
    private var changeTimesEditor: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(changeTimesTitle).foregroundStyle(Theme.ink)
            ForEach(settings.changeTimes.indices, id: \.self) { index in
                HStack {
                    DatePicker(
                        "Godzina \(index + 1)", selection: changeTime(at: index), displayedComponents: .hourAndMinute
                    )
                    .labelsHidden()
                    Spacer()
                    if settings.changeTimes.count > 1 {
                        Button(role: .destructive) {
                            settings.changeTimes.remove(at: index)
                        } label: {
                            Image(systemName: "minus.circle.fill")
                        }
                        .buttonStyle(.borderless)
                        .accessibilityLabel("Usuń godzinę \(settings.changeTimes[index])")
                    }
                }
            }
            if settings.changeTimes.count < maxTimes {
                Button {
                    settings.changeTimes = Self.sorted(settings.changeTimes + [Self.nextFreeTime(after: settings.changeTimes)])
                } label: {
                    Label("Dodaj godzinę", systemImage: "plus.circle")
                }
                .buttonStyle(.borderless)
                .font(.subheadline)
            }
        }
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

struct PresentationSection: View {
    @Environment(AppModel.self) private var model
    @Binding var settings: FrameSettings
    @State private var target = Target.art
    /// `settings` after a short pause, so a slider drag renders once.
    @State private var previewed: FrameSettings?

    enum Target: String, CaseIterable {
        case art = "Sztuka"
        case photo = "Zdjęcia"
    }

    private var presentation: Binding<Presentation> {
        target == .art ? $settings.art : $settings.photo
    }

    /// Off: one style picked by hand, starting from the usual one for the target.
    private var autoStyle: Binding<Bool> {
        Binding(
            get: { presentation.preset.wrappedValue == "auto" },
            set: { presentation.preset.wrappedValue = $0 ? "auto" : (target == .photo ? "photo" : "painting") }
        )
    }

    private var isMulti: Bool { target == .photo && presentation.fit.wrappedValue == "multi" }

    private var matSwatches: some View {
        ForEach(MatSwatch.names, id: \.self) { name in
            MatSwatch(name: name, selected: presentation.mat.wrappedValue == name) {
                presentation.mat.wrappedValue = name
            }
        }
    }

    /// The picture on the frame, when the selected presentation applies to it.
    private var previewItem: Item? {
        guard let item = model.player?.current?.item else { return nil }
        return (item.kind == .photo) == (target == .photo) ? item : nil
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Prezentacja", subtitle: "Jak obraz wygląda na ramce")
            Picker("Dla", selection: $target) {
                ForEach(Target.allCases, id: \.self) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            Text(target == .art
                ? "Dla playlist z dziełami z muzeów i własnymi pracami oraz dla Propozycji."
                : "Dla albumów iCloud i zdjęć z rolki aparatu.")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
            if let item = previewItem {
                let portrait = settings.orientation == "portrait"
                VStack(spacing: 10) {
                    FramedArtwork(
                        ref: .framePreview(item.id, settings: previewed ?? settings),
                        aspectRatio: portrait ? 9.0 / 16.0 : 16.0 / 9.0,
                        moulding: 5
                    )
                    .frame(maxWidth: portrait ? 190 : .infinity)
                    Text("Tak wyglądałby obraz, który jest teraz na ramce. Po zapisaniu ramka pokaże nowy wygląd od następnego obrazu.")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 6)
                .task(id: settings) {
                    try? await Task.sleep(for: .milliseconds(450))
                    if !Task.isCancelled { previewed = settings }
                }
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
                                    presentation.margin.wrappedValue = 0.05
                                }
                                if mode.fit == "multi", presentation.margin.wrappedValue < 0.05 {
                                    presentation.margin.wrappedValue = 0.07
                                }
                            }
                        }
                    }
                    Text(FitOption.explanation(presentation.fit.wrappedValue, photo: target == .photo))
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if isMulti {
                    Divider()
                    MultiSettings(presentation: presentation, portrait: settings.orientation == "portrait")
                }
                Divider()
                VStack(alignment: .leading, spacing: 10) {
                    Text("Passe-partout").foregroundStyle(Theme.ink)
                    // Six swatches: one row where they fit, else two rows of three.
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 10) { matSwatches }
                        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3), spacing: 10) {
                            matSwatches
                        }
                    }
                }
                if presentation.fit.wrappedValue != "fill" {
                    Divider()
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Szerokość passe-partout")
                            Spacer()
                            Text("\(Int((presentation.margin.wrappedValue * 100).rounded())) %")
                                .monospacedDigit()
                                .foregroundStyle(Theme.inkSoft)
                        }
                        Slider(value: presentation.margin, in: 0 ... 0.2, step: 0.01)
                    }
                }
                if !isMulti {
                    Divider()
                    Toggle("Podpis na ramce", isOn: presentation.label)
                    Text(target == .art ? "Np. „Claude Monet — Lilie wodne, 1906”, drukiem na passe-partout; przy wypełnieniu na wąskim pasku u dołu."
                                        : "Data i podpis zdjęcia na passe-partout albo na pasku u dołu.")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
                Divider()
                Toggle("Styl obrazu automatycznie", isOn: autoStyle)
                if !autoStyle.wrappedValue {
                    HStack {
                        Text("Styl obrazu")
                        Spacer()
                        Picker("Styl obrazu", selection: presentation.preset) {
                            ForEach(Names.manualPresets, id: \.self) { Text(Names.preset($0)).tag($0) }
                        }
                        .labelsHidden()
                    }
                }
                Text(Names.presetExplanation(presentation.preset.wrappedValue, photo: target == .photo))
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .fixedSize(horizontal: false, vertical: true)
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
        ("auto", "Auto"),
    ]

    /// Photos have their own framings (server: schedule.PHOTO_FITS).
    static let photoModes: [(fit: String, title: String)] = [
        ("fit", "Passe-partout"), ("fill", "Wypełnij"), ("multi", "Multi"),
    ]

    static func explanation(_ fit: String, photo: Bool = false) -> String {
        if photo {
            switch fit {
            case "fit": return "Całe zdjęcie w okienku passe-partout. Kadr i proporcje okienka zmienisz w „Teraz”."
            case "multi": return "Kilka zdjęć na jednej planszy, każde w swoim okienku passe-partout, przycięte do niego automatycznie."
            case "fill": break
            default: return "Wybierz jeden z trybów dla zdjęć."
            }
        }
        return switch fit {
        case "fill": "Cały ekran; kadr sam ustawia się na tym, co najciekawsze (twarze, szczegóły). Poprawisz go w „Teraz”."
        case "description": "Obraz, obok jego detal w okienku passe-partout i krótki opis nadrukowany na passe-partout: tytuł, autor, data i kilka zdań o obrazie. Gdy proporcje obrazu są bliskie ramce, obraz jest mniejszy, żeby zmieściły się detal i opis. Kadr obrazu i detalu poprawisz w „Teraz”."
        case "auto": "Wypełnienie, gdy proporcje pasują; passe-partout, gdy trochę się różnią; opis z detalem, gdy bardzo."
        default: "Cały obraz w okienku passe-partout. Kadr i proporcje okienka zmienisz w „Teraz”."
        }
    }

    var body: some View {
        Button(action: action) {
            VStack(spacing: 8) {
                ZStack {
                    Rectangle().fill(mat)
                    miniature
                }
                .frame(height: 44)
                .whiteFrame(3, corner: 1)
                Text(title)
                    .font(.caption2.weight(.medium))
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                    .foregroundStyle(Theme.ink)
            }
            .padding(6)
            .background(selected ? Theme.accent.opacity(0.1) : .clear, in: RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(selected ? Theme.accent : Theme.hairline, lineWidth: selected ? 2 : 1))
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
                Rectangle().fill(art).frame(width: 16)
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
        case "auto":
            Rectangle().fill(art).padding(.horizontal, 6)
        case "multi":
            HStack(spacing: 4) {
                Rectangle().fill(art)
                VStack(spacing: 4) {
                    Rectangle().fill(art.opacity(0.8))
                    Rectangle().fill(art.opacity(0.8))
                }
                .frame(width: 14)
            }
            .padding(.vertical, 6)
            .padding(.horizontal, 10)
        default:
            Rectangle().fill(art).padding(.vertical, 6).padding(.horizontal, 18)
        }
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
                    .frame(width: 44, height: 32)
                    .overlay(
                        // The window cut at 45°: a light inner edge.
                        RoundedRectangle(cornerRadius: 2)
                            .strokeBorder(.white.opacity(name == "white" ? 0 : 0.8), lineWidth: 1.5)
                            .padding(9)
                    )
                    .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(Theme.inkSoft.opacity(0.35), lineWidth: 0.75))
                    .padding(3)
                    .overlay(RoundedRectangle(cornerRadius: 9).strokeBorder(selected ? Theme.accent : .clear, lineWidth: 2))
                Text(Self.title(name))
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(selected ? Theme.ink : Theme.inkSoft)
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Passe-partout \(Self.title(name).lowercased())")
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

struct ScreenSection: View {
    @Binding var settings: FrameSettings

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Ekran")
            Card {
                Picker("Orientacja", selection: $settings.orientation) {
                    Label("Pozioma", systemImage: "rectangle").tag("landscape")
                    Label("Pionowa", systemImage: "rectangle.portrait").tag("portrait")
                }
                .pickerStyle(.segmented)
                if settings.orientation == "portrait" {
                    Picker("Obrót", selection: $settings.rotation) {
                        Text("90° w prawo").tag(90)
                        Text("90° w lewo").tag(270)
                    }
                    .pickerStyle(.segmented)
                    Text("Jak powieszono ramkę. Gdy obraz jest do góry nogami, zmień kierunek.")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
            }
        }
    }
}

struct SourcesSection: View {
    @Binding var settings: FrameSettings

    private var privateUse: Binding<Bool> {
        Binding(get: { settings.privateUse ?? false }, set: { settings.privateUse = $0 })
    }

    private var wikiart: Binding<Bool> {
        Binding(get: { settings.wikiart ?? false }, set: { settings.wikiart = $0 })
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Źródła dzieł", subtitle: "Skąd serwer bierze sztukę")
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
        [wifi.strength, wifi.ip, wifi.band, When.ago(wifi.readAt)].compactMap { $0 }.joined(separator: " · ")
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: wrong ? "wifi.exclamationmark" : "wifi")
                .font(.title2)
                .foregroundStyle(wrong ? Theme.bad : (wifi.signal ?? 1) < 0.35 ? Theme.warn : Theme.good)
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
/// app reaches the server, how much disk the library may take and the
/// language model's key; set once, rarely touched again.
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
