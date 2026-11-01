import CoreImage.CIFilterBuiltins
import SwiftUI

/// An invitation's link opened on this phone: who invites, to which frame,
/// and "Dołącz".
struct JoinView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let invitation: Invitation
    @State private var joining = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    Image(systemName: "photo.artframe")
                        .font(.system(size: 44))
                        .foregroundStyle(Theme.ink)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 24)
                    Text(headline)
                        .font(.serif(24, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity)
                    Card {
                        Label("Twoje własne Ulubione i playlisty", systemImage: "heart")
                        Label("Wysyłasz dzieła i zdjęcia na wspólną ramkę", systemImage: "photo.on.rectangle")
                        Label("Własne powiadomienia", systemImage: "bell")
                    }
                    .foregroundStyle(Theme.ink)
                    Text("Połącz się z domowym Wi-Fi (albo z Tailscale poza domem). Zaproszenie działa raz i przez 30 minut.")
                        .font(.footnote)
                        .foregroundStyle(Theme.inkSoft)
                    Button {
                        Task {
                            joining = true
                            let joined = await model.join(invitation)
                            joining = false
                            if joined { dismiss() }
                        }
                    } label: {
                        HStack {
                            Text("Dołącz")
                            if joining { ProgressView().tint(Theme.paper) }
                        }
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(joining)
                }
                .pageWidth()
                .padding(.horizontal, Theme.gutter)
                .padding(.bottom, 40)
            }
            .paperPage()
            .navigationTitle("Dołącz do ramki")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Anuluj") {
                        model.invitation = nil
                        dismiss()
                    }
                }
            }
        }
    }

    private var headline: String {
        let frame = invitation.frame.isEmpty ? "ramki" : "ramki „\(invitation.frame)”"
        return invitation.from.isEmpty ? "Zaproszenie do \(frame)" : "\(invitation.from) zaprasza Cię do \(frame)"
    }
}

/// Konfiguracja → Domownicy (the owner's): who uses the frame on which
/// phone, invitations, and how many studies a member may order a day.
struct HouseholdSection: View {
    @Environment(AppModel.self) private var model
    @State private var people: People?
    @State private var inviting = false
    @State private var newName = ""
    @State private var shown: ShownInvite?
    @State private var removing: Person?
    @State private var failed: String?

    struct ShownInvite: Identifiable {
        let id = UUID()
        let title: String
        let link: Invitation
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Domownicy", subtitle: "Kto jeszcze korzysta z ramki, bez dostępu do Konfiguracji")
            Card {
                if let people {
                    if !people.people {
                        Text("Serwer nie ma tokenu FRAME_API_TOKEN: bez niego każdy w sieci ma pełny dostęp, więc zaproszenia są wyłączone. Dopisz token w frame.env i uruchom kontener ponownie.")
                            .font(.caption)
                            .foregroundStyle(Theme.warn)
                    } else {
                        ForEach(people.users) { person in
                            personRow(person, limit: people.studyLimit)
                            Divider()
                        }
                        ForEach(people.invites) { invite in
                            inviteRow(invite)
                            Divider()
                        }
                        Button {
                            newName = ""
                            inviting = true
                        } label: {
                            Label("Zaproś osobę", systemImage: "person.badge.plus")
                        }
                        .fontWeight(.semibold)
                        Button {
                            Task { await invite(name: "", userID: "owner", title: "Mój nowy telefon") }
                        } label: {
                            Label("Dodaj mój telefon", systemImage: "plus.circle")
                        }
                        Divider()
                        Stepper(value: Binding(
                            get: { people.studyLimit },
                            set: { limit in Task { await save { try await $0.savePeopleSettings(PeopleSettings(studyLimit: limit)) } } }
                        ), in: 0 ... 50) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Studia dziennie: \(people.studyLimit)")
                                Text("Ile studiów dzieł domownik może zamówić w ciągu dnia (z Twojego klucza Claude).")
                                    .font(.caption)
                                    .foregroundStyle(Theme.inkSoft)
                            }
                        }
                    }
                } else if let failed {
                    Text(failed).font(.caption).foregroundStyle(Theme.inkSoft)
                } else {
                    ProgressView().frame(maxWidth: .infinity)
                }
            }
        }
        .task { await load() }
        .alert("Zaproś osobę", isPresented: $inviting) {
            TextField("Imię", text: $newName)
                .textInputAutocapitalization(.words)
            Button("Utwórz zaproszenie") {
                let name = newName.trimmingCharacters(in: .whitespaces)
                Task { await invite(name: name, userID: nil, title: "Zaproszenie dla: \(name)") }
            }
            .disabled(newName.trimmingCharacters(in: .whitespaces).isEmpty)
            Button("Anuluj", role: .cancel) {}
        } message: {
            Text("Ta osoba zobaczy ramkę, będzie mieć własne Ulubione i playlisty, ale nie Konfigurację.")
        }
        .sheet(item: $shown, onDismiss: { Task { await load() } }) { shown in
            InviteSheet(title: shown.title, link: shown.link)
        }
        .confirmationDialog(
            "Usunąć \(removing?.name ?? "")?",
            isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } }),
            titleVisibility: .visible,
            presenting: removing
        ) { person in
            Button("Usuń", role: .destructive) {
                Task { await save { try await $0.removePerson(id: person.id) } }
            }
        } message: { _ in
            Text("Telefony tej osoby przestaną działać, a jej serca i prywatne playlisty znikną. Wspólne playlisty zostaną, już jako Twoje.")
        }
    }

    @ViewBuilder
    private func personRow(_ person: Person, limit: Int) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Image(systemName: person.isOwner ? "person.crop.circle.badge.checkmark" : "person.crop.circle")
                    .foregroundStyle(Theme.inkSoft)
                VStack(alignment: .leading, spacing: 2) {
                    Text(person.isOwner ? "\(person.name) (Ty)" : person.name)
                        .font(.subheadline.weight(.semibold))
                    Text("\(person.favorites) w Ulubionych · \(person.playlists) playlist")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
                Spacer()
                if !person.isOwner {
                    Menu {
                        Button("Nowy telefon", systemImage: "plus.circle") {
                            Task { await invite(name: "", userID: person.id, title: "Nowy telefon: \(person.name)") }
                        }
                        Button("Usuń z ramki", systemImage: "person.badge.minus", role: .destructive) {
                            removing = person
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                }
            }
            ForEach(person.devices) { device in
                HStack {
                    Image(systemName: "iphone").font(.caption).foregroundStyle(Theme.inkSoft)
                    Text(device.name.isEmpty ? "Telefon" : device.name).font(.caption)
                    if let seen = When.ago(device.lastSeenAt) {
                        Text("· \(seen)").font(.caption).foregroundStyle(Theme.inkSoft)
                    }
                    Spacer()
                    Button("Odbierz dostęp", role: .destructive) {
                        Task { await save { try await $0.removeDevice(id: device.id) } }
                    }
                    .font(.caption)
                }
            }
        }
    }

    private func inviteRow(_ invite: PendingInvite) -> some View {
        HStack {
            Image(systemName: "envelope").foregroundStyle(Theme.inkSoft)
            Text(invite.name.isEmpty ? "Zaproszenie na nowy telefon" : "Zaproszenie dla: \(invite.name)")
                .font(.caption)
            Spacer()
            Button("Anuluj") {
                Task { await save { try await $0.cancelInvite(id: invite.id) } }
            }
            .font(.caption)
        }
    }

    private func load() async {
        do {
            people = try await model.backend.people()
            failed = nil
        } catch {
            failed = "Ten serwer nie zna jeszcze domowników: zaktualizuj go."
        }
    }

    private func save(_ change: (any FrameBackend) async throws -> People) async {
        do {
            people = try await change(model.backend)
        } catch {
            model.show(error)
        }
    }

    private func invite(name: String, userID: String?, title: String) async {
        do {
            let made = try await model.backend.invite(InviteRequest(name: name, userId: userID))
            shown = ShownInvite(title: title, link: model.invitationLink(code: made.code))
        } catch {
            model.show(error)
        }
    }
}

/// The invitation as a QR code to scan with the other phone's Camera, and
/// a link to send it (AirDrop, Wiadomości).
struct InviteSheet: View {
    @Environment(\.dismiss) private var dismiss
    let title: String
    let link: Invitation

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    if let code = QRCode.image(link.url.absoluteString) {
                        Image(uiImage: code)
                            .interpolation(.none)
                            .resizable()
                            .scaledToFit()
                            .frame(maxWidth: 260)
                            .padding(16)
                            .background(.white, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                            .accessibilityLabel("Kod QR zaproszenia")
                    }
                    Text("Zeskanuj Aparatem na drugim telefonie z zainstalowaną aplikacją Frame (TestFlight). Kod działa raz, przez 30 minut.")
                        .font(.subheadline)
                        .foregroundStyle(Theme.inkSoft)
                        .multilineTextAlignment(.center)
                    ShareLink(item: link.url, subject: Text("Zaproszenie do ramki"), message: Text("Otwórz na iPhonie z aplikacją Frame.")) {
                        Label("Wyślij link", systemImage: "square.and.arrow.up")
                    }
                    .fontWeight(.semibold)
                }
                .pageWidth()
                .padding(.horizontal, Theme.gutter)
                .padding(.vertical, 24)
            }
            .paperPage()
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Gotowe") { dismiss() }
                }
            }
        }
    }
}

enum QRCode {
    static func image(_ text: String) -> UIImage? {
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(text.utf8)
        filter.correctionLevel = "M"
        guard let output = filter.outputImage?.transformed(by: CGAffineTransform(scaleX: 10, y: 10)),
              let cgImage = CIContext().createCGImage(output, from: output.extent)
        else { return nil }
        return UIImage(cgImage: cgImage)
    }
}

/// A household member's sheet behind the gear, in place of Konfiguracja:
/// who they are on the frame, their notifications, leaving.
struct MyAccessView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var confirmLeave = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 28) {
                    VStack(alignment: .leading, spacing: 16) {
                        SectionHeader(title: "Mój dostęp", subtitle: "Konfigurację ramki zmienia jej właściciel")
                        Card {
                            if let me = model.me {
                                Label(me.name, systemImage: "person.crop.circle")
                                    .font(.subheadline.weight(.semibold))
                                if let left = me.studiesLeft {
                                    Text("Studia dzieł na dziś: zostało \(left)")
                                        .font(.caption)
                                        .foregroundStyle(Theme.inkSoft)
                                }
                            }
                            Divider()
                            address("W domu", model.serverURL)
                            if !model.remoteURL.isEmpty {
                                address("Spoza domu", model.remoteURL)
                            }
                            if let server = model.status?.server {
                                Text("Serwer \(server.version)")
                                    .font(.caption)
                                    .foregroundStyle(Theme.inkSoft)
                            }
                        }
                    }
                    NotificationsSection()
                    FunSection()
                    Button("Odłącz ten telefon", role: .destructive) { confirmLeave = true }
                        .frame(maxWidth: .infinity)
                }
                .pageWidth()
                .padding(.horizontal, Theme.gutter)
                .padding(.top, 8)
                .padding(.bottom, 40)
            }
            .paperPage()
            .navigationTitle("Mój dostęp")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Gotowe") { dismiss() }
                }
            }
            .confirmationDialog("Odłączyć ten telefon od ramki?", isPresented: $confirmLeave, titleVisibility: .visible) {
                Button("Odłącz", role: .destructive) {
                    Task {
                        await model.leaveFrame()
                        dismiss()
                    }
                }
            } message: {
                Text("Aby wrócić, potrzebne będzie nowe zaproszenie. Twoje Ulubione i playlisty zostaną na serwerze.")
            }
        }
    }

    private func address(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(.caption).foregroundStyle(Theme.inkSoft)
            Text(value).font(.subheadline).textSelection(.enabled)
        }
    }
}
