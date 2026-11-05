import SwiftUI

/// The study of the day and the artist of the week drawn again by hand,
/// when the server's pick does not suit: the owner holds the tile in
/// Odkrywaj. The household has no such menu (as with "Wykonaj ponowną
/// analizę"). The server keeps the new one for the day (the week) and never
/// draws the old one back that day (week).
extension View {
    /// On the study of the day's tile.
    func drawDailyAgainMenu() -> some View {
        modifier(DrawDailyAgainMenu())
    }

    /// On a theme's card: only the artist of the week's gets the menu.
    func drawWeekArtistAgainMenu(_ theme: ArtTheme) -> some View {
        modifier(DrawWeekArtistAgainMenu(theme: theme))
    }
}

private struct DrawDailyAgainMenu: ViewModifier {
    @Environment(AppModel.self) private var model
    @State private var confirm = false

    func body(content: Content) -> some View {
        if model.isOwner {
            content
                .contentShape(.contextMenuPreview, RoundedRectangle(cornerRadius: Theme.corner, style: .continuous))
                .contextMenu {
                    Section("Inne dzieło na dziś, innego artysty. Jutro serwer wybierze jak zwykle.") {
                        Button("Wylosuj inne", systemImage: "shuffle") { ask() }
                            .disabled(model.drawingDaily)
                    }
                }
                .accessibilityAction(named: "Wylosuj inne Studium dnia") { ask() }
                .confirmationDialog("Wylosować inne Studium dnia?", isPresented: $confirm, titleVisibility: .visible) {
                    Button("Wylosuj inne") { draw() }
                    Button("Anuluj", role: .cancel) {}
                } message: {
                    Text("Claude napisze studium nowego dzieła od razu, jak co dzień (Opus, około 0,25 USD z miesięcznego limitu). Dotychczasowe studium zostaje w „Studia dzieł”.")
                }
        } else {
            content
        }
    }

    /// Asks first when Claude will write the new study (it costs).
    private func ask() {
        Task {
            if model.aiSettings == nil { await model.loadAiSettings() }
            if let ai = model.aiSettings, ai.keySet, ai.daily == true {
                confirm = true
            } else {
                draw()
            }
        }
    }

    private func draw() {
        Task { await model.drawDailyAgain() }
    }
}

private struct DrawWeekArtistAgainMenu: ViewModifier {
    @Environment(AppModel.self) private var model
    let theme: ArtTheme

    func body(content: Content) -> some View {
        if model.isOwner, theme.key.hasPrefix(ArtTheme.weekArtistPrefix) {
            content
                .contentShape(.contextMenuPreview, RoundedRectangle(cornerRadius: 12, style: .continuous))
                .contextMenu {
                    Section("Inny artysta do końca tygodnia. Inne karty „Dziś dla Ciebie” zostają.") {
                        Button("Wylosuj innego", systemImage: "shuffle") { draw() }
                            .disabled(model.drawingWeekArtist)
                    }
                }
                .accessibilityAction(named: "Wylosuj innego Artystę tygodnia") { draw() }
        } else {
            content
        }
    }

    private func draw() {
        Task { await model.drawWeekArtistAgain() }
    }
}
