import SwiftUI

/// The heart and "…" of a work, top right: on its card and on its study.
/// "…" holds "Dodaj do playlisty" (the host shows the sheet), "Nie pokazuj
/// na ramce", the museum's page and "Zapisz w Zdjęciach".
struct ItemToolbar: ToolbarContent {
    let model: AppModel
    let item: Item
    /// Told the work as it now is: at once on a tap, then as the server has it
    /// (or back as it was when the server refused).
    let changed: (Item) -> Void
    @Binding var addingToPlaylist: Bool
    @Binding var savingPhoto: Bool
    /// "Szukaj lepszej kopii": the sheet of the picture's copies elsewhere.
    @Binding var findingCopies: Bool
    /// The long side of the picture shown now, when the server has told it.
    var pictureSide: Int? = nil
    /// "Przywróć zdjęcie muzeum", while a copy stands in for the work's own.
    var keepOwn: () -> Void = {}

    /// A museum's work, which other sources may have too.
    private var hasCopies: Bool { item.kind == .artwork && item.look == nil }

    var body: some ToolbarContent {
        ToolbarItemGroup(placement: .topBarTrailing) {
            Button {
                // At once: a museum's work joins the library first, which
                // takes the server a while.
                let before = item
                var after = item
                after.favorite.toggle()
                changed(after)
                Task {
                    changed(await model.setFavorite(before.id, after.favorite) ?? before)
                }
            } label: {
                Image(systemName: item.favorite ? "heart.fill" : "heart")
                    .foregroundStyle(item.favorite ? Theme.vermilion : Theme.ink)
                    .contentTransition(.symbolEffect(.replace))
            }
            .accessibilityLabel(item.favorite ? "Usuń z ulubionych" : "Dodaj do ulubionych")
            Menu {
                Button("Dodaj do playlisty", systemImage: "text.badge.plus") { addingToPlaylist = true }
                Button(
                    item.excluded ? "Przywróć dzieło" : "Ukryj dzieło",
                    systemImage: item.excluded ? "eye" : "eye.slash"
                ) {
                    Task {
                        if let updated = await model.setExcluded(item.id, !item.excluded) {
                            changed(updated)
                        }
                    }
                }
                if hasCopies || !item.url.isEmpty { Divider() }
                if hasCopies {
                    Button { findingCopies = true } label: {
                        Label {
                            Text("Szukaj lepszej kopii")
                            Text(copiesNote)
                        } icon: {
                            Image(systemName: "plus.magnifyingglass")
                        }
                    }
                    if item.sharper != nil {
                        Button("Przywróć zdjęcie muzeum", systemImage: "arrow.uturn.backward", action: keepOwn)
                    }
                }
                if let url = URL(string: item.url), !item.url.isEmpty {
                    Link(destination: url) { Label("Otwórz w muzeum", systemImage: "safari") }
                }
                // Last, under the museum link.
                Button("Zapisz w Zdjęciach", systemImage: "square.and.arrow.down") {
                    savingPhoto = true
                    Task {
                        await model.saveToPhotos(item)
                        savingPhoto = false
                    }
                }
                .disabled(savingPhoto)
            } label: {
                Image(systemName: "ellipsis.circle").foregroundStyle(Theme.ink)
            }
            .accessibilityLabel("Więcej")
        }
    }

    /// Under "Szukaj lepszej kopii": how large the picture is now.
    private var copiesNote: String {
        if let sharper = item.sharper { return "Teraz \(max(sharper.width, sharper.height)) px" }
        if let side = pictureSide, side > 0 { return "Teraz \(side) px" }
        return "W innych muzeach i bazach"
    }
}
