import SwiftUI

/// The study of the day and the artist of the week drawn again by hand,
/// when the server's pick does not suit: the owner holds the tile in
/// Odkrywaj. The household has no such menu (as with "Wykonaj ponowną
/// analizę"). The server keeps the new one for the day (the week) and never
/// draws the old one back that day (week). Only the button in the menu,
/// no hint and no question about the cost (Mateusz 2026-11-05).
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

    func body(content: Content) -> some View {
        if model.isOwner {
            content
                .contentShape(.contextMenuPreview, RoundedRectangle(cornerRadius: Theme.corner, style: .continuous))
                .contextMenu {
                    Button("Wylosuj inne", systemImage: "shuffle") { draw() }
                        .disabled(model.drawingDaily)
                }
                .accessibilityAction(named: "Wylosuj inne Studium dnia") { draw() }
        } else {
            content
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
                    Button("Wylosuj innego", systemImage: "shuffle") { draw() }
                        .disabled(model.drawingWeekArtist)
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
