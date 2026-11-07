import SwiftUI

/// The pages of Konfiguracja, in the order of the list behind the gear
/// (Mateusz 2026-11-07: one long page of eleven cards was chaos). What the
/// Ramka tab already shows (the frame's state, Wi-Fi, the server's version
/// and its update, the app's restart) is not repeated here.
enum SettingsPage: String, Hashable, CaseIterable {
    case display, notifications, household
    case sources, ai, library
    case frame, server, keys
    case diagnostics

    /// The list's blocks, from the everyday to what is set once.
    enum Block: CaseIterable {
        case daily, art, setup, tools

        var title: String? {
            switch self {
            case .daily: "Na co dzień"
            case .art: "Dzieła i biblioteka"
            case .setup: "Ramka i serwer"
            case .tools: nil
            }
        }

        var pages: [SettingsPage] {
            switch self {
            case .daily: [.display, .notifications, .household]
            case .art: [.sources, .ai, .library]
            case .setup: [.frame, .server, .keys]
            case .tools: [.diagnostics]
            }
        }

        /// The icon's square, from the app icon's colours.
        var tint: Color {
            switch self {
            case .daily: Color(hex: 0xA84B37)
            case .art: Color(hex: 0xC48A2C)
            case .setup: Color(hex: 0x2559CC)
            case .tools: Color(hex: 0x8A8378)
            }
        }
    }

    var title: String {
        switch self {
        case .display: "Wyświetlanie"
        case .notifications: "Powiadomienia"
        case .household: "Domownicy"
        case .sources: "Źródła dzieł"
        case .ai: "Claude"
        case .library: "Miejsce na serwerze"
        case .frame: "Ramka"
        case .server: "Serwer"
        case .keys: "Klucze i certyfikaty"
        case .diagnostics: "Diagnostyka"
        }
    }

    var icon: String {
        switch self {
        case .display: "sun.max.fill"
        case .notifications: "bell.fill"
        case .household: "person.2.fill"
        case .sources: "building.columns.fill"
        case .ai: "text.book.closed.fill"
        case .library: "internaldrive.fill"
        case .frame: "photo.artframe"
        case .server: "server.rack"
        case .keys: "key.fill"
        case .diagnostics: "wrench.and.screwdriver.fill"
        }
    }

    var block: Block { Block.allCases.first { $0.pages.contains(self) } ?? .tools }

    /// CI screenshots: `-screen connection -settingsPage keys` opens that page.
    static var launch: SettingsPage? {
        UserDefaults.standard.string(forKey: "settingsPage").flatMap(SettingsPage.init(rawValue:))
    }
}

/// Behind the gear in "Ramka" (the owner's): one short row per page, each
/// with what matters most on it.
struct ConnectionSettingsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var path: [SettingsPage] = SettingsPage.launch.map { [$0] } ?? []

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    ForEach(SettingsPage.Block.allCases, id: \.self) { block in
                        SettingsBlockView(block: block)
                    }
                }
                .pageWidth()
                .padding(.horizontal, Theme.gutter)
                .padding(.top, 8)
                .padding(.bottom, 40)
            }
            .paperPage()
            .navigationTitle("Konfiguracja")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Gotowe") { dismiss() }
                }
            }
            .navigationDestination(for: SettingsPage.self) { page in
                SettingsPageView(page: page)
            }
        }
        // On the stack, not the list: the list's tasks stop when a page
        // opens over it (and never start when one opens right away).
        .task { await model.loadLibraryStorage() }
        .task { await model.loadPanelApp() }
        .task { await model.loadServerUpdate() }
        .task { await model.loadAiSettings() }
        .task { await model.loadSourceKeys() }
        .task { await model.loadNotifications() }
        .task { await model.syncTailnet() }
    }
}

/// One block of the list: its small-caps title and a card of rows.
private struct SettingsBlockView: View {
    let block: SettingsPage.Block

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let title = block.title {
                Eyebrow(title)
                    .padding(.leading, 14)
            }
            VStack(spacing: 0) {
                ForEach(Array(block.pages.enumerated()), id: \.element) { index, page in
                    if index > 0 {
                        Divider().padding(.leading, 58)
                    }
                    SettingsRow(page: page)
                }
            }
            .background(Theme.card, in: RoundedRectangle(cornerRadius: Theme.corner, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: Theme.corner, style: .continuous)
                    .strokeBorder(Theme.hairline.opacity(0.7))
            )
        }
    }
}

/// A row of the list: the page's icon and name, and its summary.
private struct SettingsRow: View {
    @Environment(AppModel.self) private var model
    @AppStorage(ArtGlow.key) private var glow = true
    @AppStorage(ArtGlow.gainKey) private var gain = ArtGlow.defaultGain
    let page: SettingsPage

    var body: some View {
        NavigationLink(value: page) {
            HStack(spacing: 12) {
                Image(systemName: page.icon)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(page.block == .art ? Theme.ink : Color.white)
                    .frame(width: 30, height: 30)
                    .background(page.block.tint, in: RoundedRectangle(cornerRadius: 7, style: .continuous))
                Text(page.title)
                    .foregroundStyle(Theme.ink)
                Spacer(minLength: 8)
                if let summary {
                    Text(summary.text)
                        .font(.subheadline)
                        .foregroundStyle(summary.warn ? Theme.warn : Theme.inkSoft)
                        .lineLimit(1)
                }
                Image(systemName: "chevron.right")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(Theme.inkSoft.opacity(0.6))
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 11)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    /// What matters most on the page, in a few words; `warn` when it needs a look.
    private var summary: (text: String, warn: Bool)? {
        switch page {
        case .display:
            return (glow ? ArtGlow.label(gain) : "Bez rozjaśnienia", false)
        case .notifications:
            if PushCenter.shared.authorization == .denied { return ("Wyłączone", true) }
            guard let settings = model.notificationSettings, let device = settings.device else { return nil }
            let on = settings.kinds.filter { device.kinds.contains($0.key) }.count
            return ("\(on) z \(settings.kinds.count)", false)
        case .household, .diagnostics:
            return nil
        case .sources:
            guard let settings = model.settings else { return nil }
            return (settings.privateUse == true ? "Użytek prywatny" : "Domena publiczna", false)
        case .ai:
            guard let ai = model.aiSettings else { return nil }
            return ai.keySet ? (Money.usd(ai.spentUsd), false) : ("Brak klucza", true)
        case .library:
            guard let storage = model.libraryStorage else { return nil }
            return (ByteSize.bytes(storage.usage.totalBytes), false)
        case .frame:
            guard let app = model.panelApp else { return nil }
            if app.package == nil { return ("Brak aplikacji", true) }
            if let package = app.package, PanelAppSection.waitsForButton(package: package.version, onFrame: app.state.build) {
                return ("Nowa wersja czeka", true)
            }
            return app.state.build.map { ("Aplikacja \($0)", false) }
        case .server:
            if model.demoMode { return ("Bez serwera", true) }
            switch model.connection {
            case .connected: return (model.serverPath == .remote ? "Spoza domu" : "W domu", false)
            case .failed: return ("Brak połączenia", true)
            case .unknown: return nil
            }
        case .keys:
            if model.panelApp?.certificatesExpireAt != nil { return ("Certyfikaty wygasają", true) }
            let keys = KeyCount(model: model)
            guard keys.total > 0 else { return nil }
            return ("\(keys.set) z \(keys.total)", false)
        }
    }
}

/// How many of the keys and certificates the server knows of are in place.
private struct KeyCount {
    var set = 0
    var total = 0

    @MainActor
    init(model: AppModel) {
        if let ai = model.aiSettings { add(ai.keySet) }
        if let push = model.notificationSettings { add(push.key != nil) }
        if let tailnet = model.tailnetKey { add(tailnet.keySet) }
        for source in model.sourceKeys { add(source.keySet) }
        if let app = model.panelApp { add(app.certificates?.isEmpty == false) }
    }

    private mutating func add(_ present: Bool) {
        total += 1
        if present { set += 1 }
    }
}

/// One page of Konfiguracja.
struct SettingsPageView: View {
    @Environment(AppModel.self) private var model
    let page: SettingsPage

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                content
            }
            .pageWidth()
            .padding(.horizontal, Theme.gutter)
            .padding(.top, 8)
            .padding(.bottom, 40)
        }
        .paperPage()
        .scrollDismissesKeyboard(.interactively)
        .navigationTitle(page.title)
        .navigationBarTitleDisplayMode(.inline)
    }

    @ViewBuilder
    private var content: some View {
        switch page {
        case .display:
            ViewerSection()
            FunSection()
        case .notifications:
            NotificationsSection(parts: [.phone])
        case .household:
            HouseholdSection()
        case .sources:
            if let settings = model.settings {
                SourcesSection(settings: settings)
            } else {
                waiting
            }
        case .ai:
            if let ai = model.aiSettings {
                AiSection(settings: ai)
            } else {
                waiting
            }
        case .library:
            if let storage = model.libraryStorage {
                LibrarySizeSection(storage: storage)
            } else {
                waiting
            }
        case .frame:
            if let app = model.panelApp {
                PanelAppSection(app: app)
            }
            if let panel = model.panelConfig {
                PanelSection(config: panel)
            } else if model.panelApp == nil {
                waiting
            }
        case .server:
            ServerSection()
            if !model.demoMode {
                TailnetSection(parts: [.connection])
            }
        case .keys:
            if let ai = model.aiSettings {
                AiSection(settings: ai, part: .key)
            }
            NotificationsSection(parts: [.key])
            TailnetSection(parts: [.key])
            SourceKeysSection()
            if let app = model.panelApp {
                PanelCertificatesSection(app: app)
            }
        case .diagnostics:
            TailnetSection(parts: [.log])
            NotificationsSection(parts: [.test])
        }
    }

    @ViewBuilder
    private var waiting: some View {
        if model.demoMode {
            Text("Dostępne po połączeniu z serwerem.")
                .font(.subheadline)
                .foregroundStyle(Theme.inkSoft)
                .frame(maxWidth: .infinity)
                .padding(.top, 40)
        } else {
            ProgressView()
                .frame(maxWidth: .infinity)
                .padding(.top, 40)
        }
    }
}
