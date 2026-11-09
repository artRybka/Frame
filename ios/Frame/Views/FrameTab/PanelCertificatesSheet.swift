import SwiftUI
import UniformTypeIdentifiers

/// Konfiguracja → Aplikacja ramki → „Wgraj nowe certyfikaty”: the renewed
/// Samsung certificates (author.p12, distributor.p12) picked in Files and
/// their password, sent to the server, which checks them and signs the
/// frame's app with them at once. The files and the password stay on the
/// server only; the renewal itself is done in Tizen Studio on the Mac.
struct PanelCertificatesSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss

    private enum Role: String {
        case author, distributor
    }

    private struct Picked {
        var name: String
        var data: Data
    }

    @State private var author: Picked?
    @State private var distributor: Picked?
    @State private var password = ""
    @State private var picking = false
    @State private var pickingFor: Role = .author
    @State private var sending = false
    @State private var problem: String?
    @State private var authorChanged: String?

    private var ready: Bool {
        author != nil && distributor != nil && !password.isEmpty && !sending
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Nowe pliki wydaje Certificate Manager w Tizen Studio na Macu: profil frame, ten sam DUID ramki i stary certyfikat autora. Przenieś author.p12 i distributor.p12 na telefon, najlepiej przez AirDrop do Plików, i wybierz je tutaj.")
                        .font(.subheadline)
                        .foregroundStyle(Theme.inkSoft)
                    Card {
                        fileRow("Certyfikat autora", role: .author, picked: author)
                        Divider()
                        fileRow("Certyfikat dystrybutora", role: .distributor, picked: distributor)
                        Divider()
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Hasło certyfikatów").font(.subheadline.weight(.semibold)).foregroundStyle(Theme.ink)
                            SecureField("To samo co w Certificate Managerze", text: $password)
                                .textContentType(.password)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()
                        }
                    }
                    if let problem {
                        Text(problem)
                            .font(.caption)
                            .foregroundStyle(Theme.bad)
                    }
                    Text("Serwer sprawdzi hasło i daty, zachowa pliki tylko u siebie i od razu podpisze nimi aplikację ramki. Ramka zainstaluje ją przy najbliższym pytaniu o obraz.")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
                .pageWidth()
                .padding(.horizontal, Theme.gutter)
                .padding(.top, 8)
                .padding(.bottom, 40)
            }
            .paperPage()
            .scrollDismissesKeyboard(.interactively)
            .navigationTitle("Certyfikaty Samsunga")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Anuluj") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    if sending {
                        ProgressView()
                    } else {
                        Button("Wgraj") { Task { await send(newAuthor: false) } }
                            .fontWeight(.semibold)
                            .disabled(!ready)
                            .confirmationDialog(
                                "Inny certyfikat autora",
                                isPresented: Binding(get: { authorChanged != nil }, set: { if !$0 { authorChanged = nil } }),
                                titleVisibility: .visible
                            ) {
                                Button("Wgraj mimo to", role: .destructive) { Task { await send(newAuthor: true) } }
                                Button("Anuluj", role: .cancel) {}
                            } message: {
                                Text("Ten author.p12 ma inny klucz niż certyfikat na serwerze. Ramka może uznać aplikację za inną i jej nie zainstalować. Przy odnawianiu zostaw w Certificate Managerze stary certyfikat autora.")
                            }
                    }
                }
            }
            .fileImporter(
                isPresented: $picking,
                allowedContentTypes: [UTType(filenameExtension: "p12") ?? .data, .data]
            ) { result in
                if case let .success(url) = result { take(url, for: pickingFor) }
            }
        }
        .presentationDetents([.large])
    }

    private func fileRow(_ title: String, role: Role, picked: Picked?) -> some View {
        Button {
            problem = nil
            pickingFor = role
            picking = true
        } label: {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).foregroundStyle(Theme.ink)
                    Text(picked?.name ?? "\(role.rawValue).p12 z Plików")
                        .font(.caption)
                        .foregroundStyle(picked == nil ? Theme.inkSoft : Theme.good)
                }
                Spacer()
                Image(systemName: picked == nil ? "doc.badge.plus" : "checkmark.circle.fill")
                    .foregroundStyle(picked == nil ? Theme.ink : Theme.good)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    /// Reads the picked file at once (the security scope does not last); a
    /// file named after the other role goes there instead.
    private func take(_ url: URL, for role: Role) {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        guard let data = try? Data(contentsOf: url) else {
            problem = "Nie udało się odczytać pliku \(url.lastPathComponent)."
            return
        }
        let name = url.lastPathComponent
        let lower = name.lowercased()
        let target: Role = lower.contains("distributor") ? .distributor : lower.contains("author") ? .author : role
        switch target {
        case .author: author = Picked(name: name, data: data)
        case .distributor: distributor = Picked(name: name, data: data)
        }
    }

    private func send(newAuthor: Bool) async {
        guard let author, let distributor else { return }
        sending = true
        problem = nil
        let upload = PanelCertificatesUpload(
            author: author.data, distributor: distributor.data, password: password, newAuthor: newAuthor
        )
        let error = await model.uploadPanelCertificates(upload)
        sending = false
        switch error {
        case nil:
            dismiss()
        case let .authorChanged(said):
            problem = said.prefix(1).uppercased() + said.dropFirst()
            authorChanged = said
        case let .failed(why):
            problem = why
        }
    }
}
