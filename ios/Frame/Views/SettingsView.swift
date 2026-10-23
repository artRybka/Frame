import SwiftUI

struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @State private var testResult: String?

    var body: some View {
        @Bindable var model = model
        NavigationStack {
            Form {
                Section {
                    TextField("Adres serwera", text: $model.serverURL)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    SecureField("Token API", text: $model.apiToken)
                    Button("Zapisz i sprawdź połączenie") {
                        model.saveSettings()
                        Task { await testConnection() }
                    }
                    if let testResult {
                        Text(testResult).font(.footnote).foregroundStyle(.secondary)
                    }
                } header: {
                    Text("Serwer ramki")
                } footer: {
                    Text("Np. http://homeassistant.local:8099 (add-on Frame w Home Assistant).")
                }

                Section("Ekran") {
                    if let status = model.deviceStatus {
                        LabeledContent("Model", value: status.model)
                        LabeledContent("Nazwa", value: status.name)
                        LabeledContent("Bateria", value: "\(status.battery.level)%")
                        LabeledContent("Firmware", value: status.software)
                        LabeledContent("Network standby", value: status.networkStandby ? "wł." : "wył.")
                    }
                    Button("Odczytaj stan ekranu") {
                        Task { await model.loadDeviceStatus() }
                    }
                }
            }
            .navigationTitle("Ustawienia")
        }
    }

    private func testConnection() async {
        guard let api = model.api else {
            testResult = String(localized: "Nieprawidłowy adres.")
            return
        }
        do {
            let health = try await api.health()
            testResult = String(localized: "Połączono: serwer \(health.version), paleta \(health.palette)")
        } catch {
            testResult = error.localizedDescription
        }
    }
}
