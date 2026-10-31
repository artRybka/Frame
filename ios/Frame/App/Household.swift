import Foundation
import UIKit

/// People on the frame: joining with an invitation, leaving, and the
/// owner's Konfiguracja → Domownicy (server: users.py).
extension AppModel {
    /// The owner sees Konfiguracja; a household member does not. Before the
    /// server answered (and on an older server or in the demo): the owner.
    var isOwner: Bool { me?.isOwner ?? true }

    /// An invitation's link opened (QR code, AirDrop, Wiadomości).
    func open(invitation url: URL) -> Bool {
        guard let found = Invitation(url: url) else { return false }
        invitation = found
        return true
    }

    /// "Dołącz do ramki": the code for this phone's own token, kept in the
    /// Keychain with the server's addresses; then the app as usual.
    func join(_ invitation: Invitation) async -> Bool {
        let home = URL(string: invitation.home.trimmingCharacters(in: .whitespaces))
        let remote = URL(string: invitation.remote.trimmingCharacters(in: .whitespaces))
        guard let first = home ?? remote else { return false }
        let route = ServerRoute(home: first, remote: home == nil ? nil : remote)
        if route.hasRemote, await route.resolve() == nil {
            notices.info("Serwer nie odpowiada", "Połącz się z domowym Wi-Fi albo włącz Tailscale.")
            return false
        }
        do {
            let joined = try await LiveBackend(route: route, token: nil)
                .join(code: invitation.code, device: UIDevice.current.name)
            serverURL = home?.absoluteString ?? first.absoluteString
            remoteURL = home == nil ? "" : (remote?.absoluteString ?? "")
            apiToken = joined.token
            demoMode = false
            self.invitation = nil
            accessLost = false
            await applyConnection()
            notices.done("Witaj, \(joined.me.name)", "Ramka „\(invitation.frame.isEmpty ? "Frame" : invitation.frame)” jest teraz także Twoja.")
            return true
        } catch {
            show(error)
            return false
        }
    }

    /// "Odłącz ten telefon": its token stops working and the app goes back
    /// to the demo, ready for a new invitation.
    func leaveFrame() async {
        try? await backend.leave()
        apiToken = ""
        serverURL = ""
        remoteURL = ""
        demoMode = true
        accessLost = false
        await applyConnection()
    }

    /// The link (and QR code) of an invitation: the code with this server's
    /// addresses, who invites and the frame's name.
    func invitationLink(code: String) -> Invitation {
        Invitation(
            code: code,
            home: serverURL,
            remote: remoteURL,
            from: me?.name ?? "",
            frame: settings?.name ?? status?.device.name ?? ""
        )
    }
}
