import SwiftUI

/// Konfiguracja → Diagnostyka → "Szukanie wyglądem": how many works have
/// their numbers made on the server by SigLIP (Mateusz 2026-11-23: Google's
/// numbers taken out, „Odciski SIGLip”). No switch and no key: it was a
/// switch on the Gemini page while Google made them.
struct LooksSection: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        if let note = Self.note(model.aiSettings) {
            VStack(alignment: .leading, spacing: 16) {
                SectionHeader(title: "Szukanie wyglądem", subtitle: "Na serwerze")
                Card {
                    Text(bound: "Odciski wyglądu robi serwer, bez Google i bez kosztów: szukanie opisem wyglądu, zdjęciem i „Podobne do”.")
                        .font(.subheadline)
                        .foregroundStyle(Theme.inkSoft)
                    Divider()
                    Label(note.text.bound, systemImage: note.icon)
                        .font(.subheadline)
                        .foregroundStyle(Theme.ink)
                }
            }
        }
    }

    /// How many works can be found by how they look; nil from older servers.
    static func note(_ settings: AiSettings?) -> (text: String, icon: String)? {
        guard let done = settings?.looksDone, let total = settings?.looksTotal, total > 0 else { return nil }
        if done >= total { return ("Gotowe: \(Names.works(total))", "checkmark.circle") }
        return ("Gotowe \(done) z \(total) dzieł, reszta w tle", "clock")
    }
}
