import SwiftUI

/// Konfiguracja → Dostęp spoza domu: Tailscale built into the app (`Tailnet`,
/// decision D16). The owner pastes the household's Tailscale key here, every
/// phone takes it from the server; a household member sees how their phone's
/// connection is doing (`editable: false`, in "Mój dostęp").
struct TailnetSection: View {
    @Environment(AppModel.self) private var model
    var editable = true
    @State private var key = ""
    @State private var saving = false
    @State private var retrying = false
    @State private var showLog = false
    @State private var log = ""

    private static let keysPage = URL(string: "https://login.tailscale.com/admin/settings/keys")

    private var keySet: Bool { model.tailnetKey?.keySet == true }

    private var enabled: Binding<Bool> {
        Binding(get: { model.tailnet != .paused }, set: { model.setTailnetEnabled($0) })
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Dostęp spoza domu", subtitle: "Tailscale wbudowany w aplikację")
            Card {
                Text("Poza domem Frame łączy się z serwerem własnym połączeniem Tailscale, bez aplikacji Tailscale i bez VPN, więc działa obok innego VPN. Używa adresu „Spoza domu”, gdy to adres Tailscale (100.x.y.z albo nazwa .ts.net).")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .fixedSize(horizontal: false, vertical: true)
                Divider()
                status
                if keySet || model.tailnet != .off {
                    Divider()
                    Toggle(isOn: enabled) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Tailscale w aplikacji")
                            Text("Na tym telefonie. Wyłączony: Frame łączy się przez VPN aplikacji Tailscale, jeśli jest włączony.")
                                .font(.caption)
                                .foregroundStyle(Theme.inkSoft)
                        }
                    }
                    .tint(Theme.ink)
                }
                if editable {
                    Divider()
                    keyEditor
                }
                if model.tailnet != .off {
                    Divider()
                    DisclosureGroup(isExpanded: $showLog) {
                        ScrollView(.horizontal) {
                            Text(log.isEmpty ? "Pusto: Tailscale jeszcze nie startował." : log)
                                .font(.caption2.monospaced())
                                .foregroundStyle(Theme.inkSoft)
                                .textSelection(.enabled)
                                .padding(.top, 6)
                        }
                    } label: {
                        Text("Dziennik Tailscale").font(.subheadline)
                    }
                    .tint(Theme.ink)
                    .onChange(of: showLog) { _, open in
                        if open { log = Tailnet.recentLog() }
                    }
                }
            }
        }
        .task { await model.syncTailnet() }
    }

    @ViewBuilder
    private var status: some View {
        switch model.tailnet {
        case .off:
            line(
                keySet ? "Adres „Spoza domu” nie jest adresem Tailscale." : "Brak klucza Tailscale: poza domem potrzebna jest aplikacja Tailscale.",
                icon: "circle.dashed", color: Theme.inkSoft
            )
        case .paused:
            line("Wyłączony na tym telefonie.", icon: "pause.circle", color: Theme.inkSoft)
        case .idle:
            line("Gotowy. Połączy się, gdy serwer będzie potrzebny spoza domu.", icon: "circle", color: Theme.inkSoft)
        case .starting:
            HStack(spacing: 8) {
                ProgressView().controlSize(.small)
                Text("Łączę z Tailscale…")
            }
            .font(.subheadline)
            .foregroundStyle(Theme.inkSoft)
        case let .running(address):
            line(
                ["Połączono z Tailscale", address, Tailnet.shared.nodeName].compactMap { $0 }.joined(separator: " · "),
                icon: "checkmark.circle.fill", color: Theme.good
            )
        case let .failed(message):
            VStack(alignment: .leading, spacing: 8) {
                line(message, icon: "exclamationmark.triangle.fill", color: Theme.bad)
                Button {
                    Task {
                        retrying = true
                        await model.retryTailnet()
                        retrying = false
                    }
                } label: {
                    HStack {
                        Text("Połącz ponownie")
                        if retrying { ProgressView() }
                    }
                }
                .font(.subheadline.weight(.semibold))
                .disabled(retrying)
            }
        }
    }

    private func line(_ text: String, icon: String, color: Color) -> some View {
        Label {
            Text(text).fixedSize(horizontal: false, vertical: true)
        } icon: {
            Image(systemName: icon)
        }
        .font(.subheadline)
        .foregroundStyle(color)
    }

    @ViewBuilder
    private var keyEditor: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Klucz Tailscale").font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                Spacer()
                if keySet, let tail = model.tailnetKey?.keyTail {
                    Label("…\(tail)", systemImage: "checkmark.circle.fill")
                        .font(.subheadline.monospaced())
                        .foregroundStyle(Theme.good)
                }
            }
            Text("W panelu Tailscale (Settings → Keys) utwórz klucz „Reusable”, najlepiej z tagiem, np. tag:frame-app: wtedy połączenie nie wygasa. Telefony domowników dostaną klucz z serwera same, nie potrzebują konta Tailscale.")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
                .fixedSize(horizontal: false, vertical: true)
            SecureField(keySet ? "zapisany · wpisz nowy, by zmienić" : "tskey-auth-…", text: $key)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
            HStack {
                Button {
                    Task {
                        saving = true
                        if await model.saveTailnetKey(key) { key = "" }
                        saving = false
                    }
                } label: {
                    HStack {
                        Text("Zapisz i połącz")
                        if saving { ProgressView() }
                    }
                }
                .fontWeight(.semibold)
                .disabled(key.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || saving)
                Spacer()
                if let page = Self.keysPage {
                    Link("Utwórz klucz", destination: page)
                        .font(.subheadline)
                }
            }
            if keySet {
                Button("Usuń klucz", role: .destructive) {
                    Task { await model.deleteTailnetKey() }
                }
                .font(.subheadline)
            }
        }
    }
}
