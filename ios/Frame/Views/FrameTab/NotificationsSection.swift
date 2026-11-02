import SwiftUI
import UniformTypeIdentifiers
import UserNotifications

/// Konfiguracja → Powiadomienia: what the server tells this phone over APNs,
/// the APNs key it signs with (uploaded once from Files), and a test.
struct NotificationsSection: View {
    @Environment(AppModel.self) private var model
    @Environment(\.openURL) private var openURL
    @State private var importing = false
    @State private var testing = false
    @State private var testResult: TestResult?
    @State private var confirmDelete = false

    private enum TestResult: Equatable {
        case sent, failed(String)
    }

    private var push: PushCenter { PushCenter.shared }
    private var settings: NotificationSettings? { model.notificationSettings }
    private var allowed: Bool { push.authorization == .authorized || push.authorization == .provisional }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Powiadomienia", subtitle: "Z serwera ramki, także poza domem")
            Card {
                permission
                if allowed, let settings {
                    if let device = settings.device {
                        ForEach(settings.kinds) { kind in
                            Divider()
                            Toggle(isOn: Binding(
                                get: { device.kinds.contains(kind.key) },
                                set: { on in Task { await model.setNotification(kind.key, on: on) } }
                            )) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(kind.title)
                                    Text(kind.hint).font(.caption).foregroundStyle(Theme.inkSoft)
                                }
                            }
                            .tint(Theme.ink)
                        }
                    } else {
                        Divider()
                        HStack(spacing: 8) {
                            ProgressView()
                            Text("Zapisuję telefon na serwerze…").font(.subheadline).foregroundStyle(Theme.inkSoft)
                        }
                    }
                }
                if let error = push.registrationError {
                    Text("iOS nie dał tokenu APNs: \(error)")
                        .font(.caption)
                        .foregroundStyle(Theme.bad)
                }
                if settings != nil, model.isOwner {
                    Divider()
                    keyRow
                } else if settings != nil, settings?.key == nil {
                    // A household member: the key is the owner's to add.
                    Text("Serwer nie ma jeszcze klucza APNs: poproś właściciela ramki, żeby go dodał.")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
                if allowed, settings?.key != nil, settings?.device != nil {
                    Divider()
                    testRow
                }
            }
        }
        .fileImporter(isPresented: $importing, allowedContentTypes: [UTType(filenameExtension: "p8") ?? .data, .data]) { result in
            if case let .success(url) = result {
                Task { await model.uploadPushKey(from: url) }
            }
        }
        .confirmationDialog("Usunąć klucz APNs z serwera?", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Usuń klucz", role: .destructive) { Task { await model.deletePushKey() } }
            Button("Anuluj", role: .cancel) {}
        } message: {
            Text("Serwer przestanie wysyłać powiadomienia, dopóki nie dodasz klucza ponownie.")
        }
        .task { await model.loadNotifications() }
    }

    @ViewBuilder
    private var permission: some View {
        switch push.authorization {
        case .denied:
            VStack(alignment: .leading, spacing: 6) {
                Label("Wyłączone w Ustawieniach iOS", systemImage: "bell.slash")
                Button("Otwórz Ustawienia") {
                    if let url = URL(string: UIApplication.openSettingsURLString) { openURL(url) }
                }
                .fontWeight(.semibold)
            }
        case .notDetermined:
            VStack(alignment: .leading, spacing: 6) {
                Text("Bateria, błąd wysyłki, zmiana dzieła, nowa wersja serwera, Studium dnia, gotowe studium, Artysta tygodnia i urodziny ulubionych artystów.")
                    .font(.subheadline)
                    .foregroundStyle(Theme.inkSoft)
                Button {
                    Task { await model.enableNotifications() }
                } label: {
                    Label("Włącz powiadomienia", systemImage: "bell.badge")
                }
                .fontWeight(.semibold)
            }
        default:
            Label("Włączone na tym telefonie", systemImage: "bell.fill")
                .foregroundStyle(Theme.good)
        }
    }

    @ViewBuilder
    private var keyRow: some View {
        if let key = settings?.key {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Klucz APNs \(key.keyId)")
                    Text("Zespół \(key.teamId)").font(.caption).foregroundStyle(Theme.inkSoft)
                }
                Spacer()
                Menu {
                    Button("Zastąp innym plikiem") { importing = true }
                    Button("Usuń z serwera", role: .destructive) { confirmDelete = true }
                } label: {
                    Image(systemName: "ellipsis.circle")
                }
            }
        } else {
            VStack(alignment: .leading, spacing: 6) {
                Text("Serwer potrzebuje klucza APNs z konta Apple Developer (Keys → Apple Push Notifications service, plik AuthKey_….p8). Wystarczy raz.")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                Button {
                    importing = true
                } label: {
                    Label("Dodaj klucz z Plików", systemImage: "key")
                }
                .fontWeight(.semibold)
            }
        }
    }

    private var testRow: some View {
        VStack(alignment: .leading, spacing: 6) {
            Button {
                Task {
                    testing = true
                    let error = await model.testNotification()
                    testResult = error.map(TestResult.failed) ?? .sent
                    testing = false
                }
            } label: {
                HStack {
                    Text("Wyślij próbne powiadomienie")
                    if testing { ProgressView() }
                }
            }
            .disabled(testing)
            switch testResult {
            case .sent?:
                Label("Apple przyjął powiadomienie. Powinno zaraz przyjść.", systemImage: "checkmark.circle.fill")
                    .font(.caption)
                    .foregroundStyle(Theme.good)
            case let .failed(message)?:
                Label(message, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(Theme.bad)
            case nil:
                EmptyView()
            }
        }
    }
}
