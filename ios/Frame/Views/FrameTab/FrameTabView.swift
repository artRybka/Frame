import SwiftUI

/// The frame itself: battery, charging, connection; schedule, presentation,
/// screen and server settings.
struct FrameTabView: View {
    @Environment(AppModel.self) private var model
    @State private var draft: FrameSettings?
    @State private var refreshing = false

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
                    }
                    ServerSection()
                }
                .padding(.horizontal, Theme.gutter)
                .padding(.bottom, 40)
            }
            .background(Theme.paper)
            .navigationTitle("Ramka")
            .toolbar {
                if let draft, draft != model.settings {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Zapisz") { Task { await model.saveSettings(draft) } }
                            .fontWeight(.semibold)
                    }
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Cofnij") { self.draft = model.settings }
                    }
                }
            }
            .refreshable { await refresh() }
            .onAppear { if draft == nil { draft = model.settings } }
            .onChange(of: model.settings) { _, new in draft = new }
        }
    }

    private var binding: Binding<FrameSettings> {
        Binding(
            get: { draft ?? .defaults },
            set: { draft = $0 }
        )
    }

    private func refresh() async {
        refreshing = true
        defer { refreshing = false }
        await model.refreshStatus(live: true)
        await model.refreshAll()
    }

    // MARK: Device

    private var deviceHero: some View {
        HStack(spacing: 18) {
            ZStack {
                RoundedRectangle(cornerRadius: 3)
                    .fill(Theme.moulding)
                    .overlay(RoundedRectangle(cornerRadius: 3).strokeBorder(Theme.mouldingEdge, lineWidth: 0.5))
                    .frame(width: 104, height: model.isPortrait ? 150 : 66)
                Group {
                    if let preview = model.player?.current?.previewUrl {
                        ArtImage(ref: .path(preview), maxPixel: 400)
                    } else {
                        Rectangle().fill(Theme.matWhite)
                    }
                }
                .frame(width: 96, height: model.isPortrait ? 142 : 58)
                .clipped()
            }
            .shadow(color: .black.opacity(0.18), radius: 10, y: 6)
            VStack(alignment: .leading, spacing: 4) {
                Eyebrow(device?.model.map { "Samsung \($0)" } ?? "Samsung EM32DX")
                Text(device?.name ?? "Moja ramka")
                    .font(.serif(26, weight: .semibold))
                    .foregroundStyle(Theme.ink)
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
        if !device.configured { return "Ekran nie jest skonfigurowany na serwerze" }
        switch device.reachable {
        case .some(true): return "Połączona · \(When.ago(device.lastSeen) ?? "teraz")"
        case .some(false): return "Nie odpowiada — śpi lub poza siecią"
        case .none: return "Nie sprawdzono"
        }
    }

    private var connectionColor: Color {
        switch device?.reachable {
        case .some(true): Theme.good
        case .some(false): Theme.bad
        case .none: Theme.inkSoft
        }
    }

    private var statusGrid: some View {
        LazyVGrid(columns: [GridItem(.flexible(), spacing: 14), GridItem(.flexible(), spacing: 14)], spacing: 14) {
            StatusTile(title: "Bateria") {
                BatteryRing(level: device?.batteryLevel, charging: device?.charging == true)
            }
            StatusTile(title: "Zasilanie") {
                VStack(alignment: .leading, spacing: 6) {
                    Image(systemName: device?.charging == true ? "bolt.fill" : "powerplug.portrait")
                        .font(.title2)
                        .foregroundStyle(device?.charging == true ? Theme.warn : Theme.inkSoft)
                        .symbolEffect(.pulse, options: .repeating, isActive: device?.charging == true)
                    Text(powerText).font(.headline).foregroundStyle(Theme.ink)
                    Text(device?.charging == true ? "bateria się ładuje" : "zmiany rzadziej, by oszczędzać")
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
                VStack(alignment: .leading, spacing: 6) {
                    Image(systemName: device?.networkStandby == true ? "wifi" : "wifi.slash")
                        .font(.title2)
                        .foregroundStyle(device?.networkStandby == true ? Theme.good : Theme.inkSoft)
                    Text(device?.networkStandby == true ? "Czuwanie Wi-Fi" : "Głęboki sen")
                        .font(.headline)
                        .foregroundStyle(Theme.ink)
                    Text(device?.firmware.map { "firmware \($0)" } ?? "firmware —")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .lineLimit(1)
                }
            }
        }
    }

    private var powerText: String {
        switch device?.powerSource {
        case "ac": device?.charging == true ? "Ładowanie" : "Zasilacz"
        case "battery": "Na baterii"
        default: "Nieznane"
        }
    }

    private var deviceActions: some View {
        HStack(spacing: 10) {
            Button {
                Task { await refresh() }
            } label: {
                Label(refreshing ? "Sprawdzam…" : "Sprawdź stan", systemImage: "arrow.clockwise")
            }
            .buttonStyle(SecondaryButtonStyle())
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

    private let intervals: [(Int, String)] = [
        (60, "co godzinę"), (180, "co 3 godziny"), (360, "co 6 godzin"), (720, "2× dziennie"),
        (1440, "raz dziennie"), (2880, "co 2 dni"), (4320, "co 3 dni"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Harmonogram", subtitle: "Co i jak często pokazuje ramka")
            Picker("Tryb", selection: $settings.mode) {
                Text("Obrazy").tag("art")
                Text("Album iCloud").tag("album")
            }
            .pickerStyle(.segmented)

            Card {
                if settings.mode == "art" {
                    row("Playlista") {
                        Picker("Playlista", selection: $settings.playlistId) {
                            Text("Cała biblioteka").tag(Int?.none)
                            ForEach(model.playlists) { Text($0.name).tag(Int?.some($0.id)) }
                        }
                    }
                    Divider()
                } else {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Link do albumu").foregroundStyle(Theme.inkSoft).font(.subheadline)
                        TextField("https://www.icloud.com/sharedalbum/#…", text: $settings.albumUrl)
                            .textInputAutocapitalization(.never)
                            .keyboardType(.URL)
                            .font(.subheadline)
                        Text("W Zdjęciach: album udostępniony → Osoby → Witryna publiczna → Udostępnij link.")
                            .font(.caption)
                            .foregroundStyle(Theme.inkSoft)
                        AlbumStatus()
                    }
                    Divider()
                }
                row("Przy zasilaczu") { intervalPicker($settings.intervalMinutes) }
                Divider()
                row("Na baterii") { intervalPicker($settings.intervalMinutesBattery) }
                Divider()
                Toggle("Losowa kolejność", isOn: $settings.shuffle)
                Divider()
                Toggle("Cisza nocna", isOn: quietEnabled)
                if settings.quietStart != nil {
                    HStack {
                        DatePicker("Od", selection: time(\.quietStart, fallback: "22:00"), displayedComponents: .hourAndMinute)
                        DatePicker("Do", selection: time(\.quietEnd, fallback: "07:00"), displayedComponents: .hourAndMinute)
                    }
                    .font(.subheadline)
                    Text("Zmiany zaczynają się codziennie o końcu ciszy nocnej. Na baterii ramka śpi wtedy z wyłączonym Wi-Fi i budzi się sama o tej godzinie, a zdjęcia wysłane w nocy pojawią się rano.")
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

    private func intervalPicker(_ value: Binding<Int>) -> some View {
        Picker("", selection: value) {
            ForEach(intervals, id: \.0) { minutes, label in
                Text(label).tag(minutes)
            }
            if !intervals.contains(where: { $0.0 == value.wrappedValue }) {
                Text("\(value.wrappedValue) min").tag(value.wrappedValue)
            }
        }
        .labelsHidden()
    }

    private var quietEnabled: Binding<Bool> {
        Binding(
            get: { settings.quietStart != nil },
            set: { on in
                settings.quietStart = on ? "22:00" : nil
                settings.quietEnd = on ? "07:00" : nil
            }
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

    private var isMulti: Bool { target == .photo && presentation.fit.wrappedValue == "multi" }

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
            if let item = previewItem {
                let portrait = settings.orientation == "portrait"
                VStack(spacing: 10) {
                    FramedArtwork(
                        ref: .framePreview(item.id, settings: previewed ?? settings),
                        aspectRatio: portrait ? 9.0 / 16.0 : 16.0 / 9.0,
                        moulding: 5
                    )
                    .frame(maxWidth: portrait ? 190 : .infinity)
                    Text("Tak będzie wyglądał obraz, który jest teraz na ramce. Zmiany trafią na ramkę po zapisaniu.")
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
                    HStack(spacing: 14) {
                        ForEach(MatSwatch.names, id: \.self) { name in
                            MatSwatch(name: name, selected: presentation.mat.wrappedValue == name) {
                                presentation.mat.wrappedValue = name
                            }
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
                HStack {
                    Text("Styl obrazu")
                    Spacer()
                    Picker("Styl obrazu", selection: presentation.preset) {
                        ForEach(["photo", "painting", "graphic", "bw"], id: \.self) { Text(Names.preset($0)).tag($0) }
                    }
                    .labelsHidden()
                }
                Text(Names.presetExplanation(presentation.preset.wrappedValue))
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
        ("fit", "Passe-partout"), ("fill", "Wypełnij"), ("details", "Detale"), ("description", "Opis"),
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
        case "details": "Cały obraz, obok dwa detale w okienkach passe-partout: szerszy i bliższy, z różnych miejsc obrazu. Gdy proporcje obrazu są bliskie ramce, obraz jest mniejszy, żeby zmieściły się detale."
        case "description": "Jak „Detale”, ale zamiast drugiego detalu krótki opis nadrukowany na passe-partout: tytuł, autor, data i kilka zdań o obrazie."
        case "auto": "Wypełnienie, gdy proporcje pasują; passe-partout, gdy trochę się różnią; detale, gdy bardzo."
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
        case "details":
            HStack(spacing: 4) {
                Rectangle().fill(art).frame(width: 16)
                VStack(spacing: 4) {
                    Rectangle().fill(art.opacity(0.7))
                    Rectangle().fill(art.opacity(0.7))
                }
                .padding(.vertical, 5)
                .padding(.trailing, 5)
            }
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

    static let names = ["white", "cream", "grey", "black", "picture"]

    static func color(_ name: String) -> Color {
        switch name {
        case "cream": Color(hex: 0xF6EFD9)
        case "grey": Color(hex: 0xAEADAA)
        case "black": Color(hex: 0x1F1E1C)
        case "picture": Color(hex: 0xE9DCCB)  // stands in for "a tint of the picture"
        default: Color(hex: 0xFBFAF7)
        }
    }

    static func title(_ name: String) -> String {
        switch name {
        case "cream": "Kremowe"
        case "grey": "Szare"
        case "black": "Czarne"
        case "picture": "Z obrazu"
        default: "Białe"
        }
    }

    /// Muted tints in a ring: the mat takes its colour from each picture.
    private var fill: AnyShapeStyle {
        guard name == "picture" else { return AnyShapeStyle(Self.color(name)) }
        let tints = [0xE8C9C0, 0xEADCC0, 0xD3DEC8, 0xC6D6DE, 0xD6CBDD, 0xE8C9C0].map { Color(hex: UInt32($0)) }
        return AnyShapeStyle(AngularGradient(colors: tints, center: .center))
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

/// Last shared-album sync and a button to sync now.
struct AlbumStatus: View {
    @Environment(AppModel.self) private var model
    @State private var info: AlbumInfo?
    @State private var syncing = false

    var body: some View {
        HStack {
            if let sync = info?.lastSync {
                VStack(alignment: .leading, spacing: 2) {
                    Text(sync.name.isEmpty ? "Album" : sync.name).font(.subheadline.weight(.medium))
                    Text("\(info?.photos ?? 0) zdjęć · synchronizacja \(When.ago(sync.at) ?? "")")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
            } else {
                Text("Jeszcze nie synchronizowano").font(.caption).foregroundStyle(Theme.inkSoft)
            }
            Spacer()
            Button {
                Task {
                    syncing = true
                    do {
                        try await model.backend.syncAlbum()
                        model.toast = "Synchronizuję album…"
                        try? await Task.sleep(for: .seconds(3))
                        info = try? await model.backend.album()
                    } catch {
                        model.show(error)
                    }
                    syncing = false
                }
            } label: {
                if syncing {
                    ProgressView()
                } else {
                    Label("Synchronizuj", systemImage: "arrow.triangle.2.circlepath")
                        .font(.subheadline.weight(.semibold))
                }
            }
            .disabled(syncing)
        }
        .padding(.top, 4)
        .task { info = try? await model.backend.album() }
    }
}
