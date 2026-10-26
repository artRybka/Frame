import SwiftUI

/// The frame itself: battery, charging, connection; schedule, presentation
/// and screen settings. How to reach the panel and the server sits behind the
/// gear at the top.
struct FrameTabView: View {
    @Environment(AppModel.self) private var model
    @State private var draft: FrameSettings?
    @State private var refreshing = false
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
                    .accessibilityLabel("Połączenie z ekranem i serwerem")
                }
                if let draft, draft != model.settings {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Zapisz") {
                            Task {
                                await model.saveSettings(draft)
                                self.draft = model.settings  // as the server keeps it (e.g. times sorted)
                            }
                        }
                        .fontWeight(.semibold)
                    }
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Cofnij") { self.draft = model.settings }
                    }
                }
            }
            // In a task of its own: SwiftUI cancels the refresh's task when the
            // view changes under it ("Sprawdzam…"), and the requests with it.
            .sheet(isPresented: $showingConnection) { ConnectionSettingsView() }
            .refreshable { await Task { await refresh() }.value }
            .onAppear { if draft == nil { draft = model.settings } }
            .onChange(of: model.settings) { old, new in
                // Changes not saved yet stay; a new name comes in either way.
                if draft == nil || draft == old { draft = new } else { draft?.name = new?.name }
            }
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
        defer { refreshing = false }
        if waking {
            await model.checkStatus()
        } else {
            await model.refreshStatus(live: true)
        }
        await model.refreshAll()
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
        case "standby": return "Śpi, czeka na sygnał budzenia"
        case "deep_sleep": return "Głęboki sen, bez Wi-Fi"
        case "offline": return "Nie odpowiada — poza siecią lub wyłączona"
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

    /// The Sieć tile: what the frame is doing, as far as the server can tell.
    private var network: (icon: String, color: Color, title: String, note: String) {
        guard let device, device.configured else {
            return ("wifi", Theme.inkSoft, "—", "ekran nie jest ustawiony")
        }
        switch device.powerState {
        case "online":
            return ("wifi", Theme.good, "Online", "odpowiada · \(When.ago(device.lastSeen) ?? "teraz")")
        case "standby":
            return ("moon.zzz", Theme.accent, "Czuwanie", "śpi, Wi-Fi czeka na sygnał budzenia")
        case "deep_sleep":
            let note = device.wakesAt.map { "Wi-Fi wyłączone, budzik o \($0)" } ?? "Wi-Fi wyłączone, budzi przycisk"
            return ("wifi.slash", Theme.inkSoft, "Głęboki sen", note)
        case "offline":
            return ("wifi.exclamationmark", Theme.bad, "Nie odpowiada", "poza siecią lub wyłączona")
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
                row("Zmiana") {
                    Picker("Zmiana", selection: $settings.changeEveryDays) {
                        ForEach(everyDays, id: \.0) { days, label in Text(label).tag(days) }
                    }
                    .labelsHidden()
                }
                Divider()
                changeTimesEditor
                Divider()
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
                Divider()
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
            .tint(Theme.accent)
        }
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
            Text(settings.changeTimes.count > 1 ? "Godziny zmiany" : "Godzina zmiany").foregroundStyle(Theme.ink)
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

/// Behind the gear in "Ramka": how the server reaches the panel and how the
/// app reaches the server; set once, rarely touched again.
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
                    ServerSection()
                }
                .padding(.horizontal, Theme.gutter)
                .padding(.top, 8)
                .padding(.bottom, 40)
            }
            .background(Theme.paper)
            .scrollDismissesKeyboard(.interactively)
            .navigationTitle("Połączenie")
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
                field("Adres IP ekranu", error: hostValue == nil ? "To nie wygląda na adres IP" : nil) {
                    TextField("np. 192.168.1.152", text: $host)
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
                    TextField("http://homeassistant.local:8099", text: $model.serverURL)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
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
            Label(model.demoMode ? "Tryb demo" : "Połączono", systemImage: "checkmark.circle.fill")
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
}
