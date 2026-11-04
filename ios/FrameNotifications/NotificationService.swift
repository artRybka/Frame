import Foundation
import UserNotifications

/// Adds the work's picture to a notification from the server before iOS
/// shows it (the payload has `mutable-content` and `pictures`, see
/// `NotificationPicture`). Without one that loads in time the notification
/// comes as it was sent.
final class NotificationService: UNNotificationServiceExtension {
    private let lock = NSLock()
    private var handler: ((UNNotificationContent) -> Void)?
    private var content: UNMutableNotificationContent?
    private var work: Task<Void, Never>?

    override func didReceive(
        _ request: UNNotificationRequest,
        withContentHandler contentHandler: @escaping (UNNotificationContent) -> Void
    ) {
        let content = (request.content.mutableCopy() as? UNMutableNotificationContent) ?? UNMutableNotificationContent()
        lock.withLock {
            handler = contentHandler
            self.content = content
        }
        let urls = NotificationPicture.urls(in: request.content.userInfo)
        guard !urls.isEmpty else { return deliver() }
        let session = NotificationPicture.session()
        work = Task { [weak self] in
            let picture = await NotificationPicture.load(urls) { url in
                await NotificationPicture.download(url, with: session)
            }
            session.invalidateAndCancel()
            if let picture, let attachment = try? NotificationPicture.attachment(picture) {
                self?.lock.withLock { self?.content?.attachments = [attachment] }
            }
            self?.deliver()
        }
    }

    override func serviceExtensionTimeWillExpire() {
        work?.cancel()
        deliver()  // as it is, without the picture
    }

    /// Once, whichever comes first: the picture or the end of the time.
    private func deliver() {
        let (handler, content) = lock.withLock {
            defer { self.handler = nil }
            return (self.handler, self.content)
        }
        if let handler, let content { handler(content) }
    }
}
