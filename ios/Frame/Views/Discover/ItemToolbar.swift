import SwiftUI

/// The heart, "Do playlisty" (the host shows `AddToPlaylistSheet`) and "…"
/// of a work, top right: on its card and on its study (Mateusz 2026-11-13:
/// the playlists out of "…" onto their own button). "…" holds "Ukryj
/// dzieło", the copies, the museum's page and "Zapisz w Zdjęciach".
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
    /// "Wczytaj kupioną kopię" (Kupowanie w Alamy on): the host picks the file.
    var bringCopy: (() -> Void)? = nil
    /// "Kreatywny restaurator", under "Szukaj lepszej kopii": for a picture
    /// small for the frame (`LowRes`), drawn again by the image model.
    var restore: (() -> Void)? = nil
    /// "Popraw kadr" / "Przytnij zdjęcie": the corners of the work on its
    /// museum photograph, on a screen of their own (Mateusz 2026-11-14).
    var correctCut: (() -> Void)? = nil
    /// "Cofnij kadrowanie": the museum's photograph whole again.
    var undoCut: (() -> Void)? = nil

    /// Konfiguracja → Źródła dzieł → Kupowanie w Alamy.
    private var buying: Bool { hasCopies && model.settings?.alamy == true }

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
            Button { addingToPlaylist = true } label: {
                Image(systemName: "text.badge.plus").foregroundStyle(Theme.ink)
            }
            .accessibilityLabel("Dodaj do playlisty")
            Menu {
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
                if correctCut != nil || undoCut != nil {
                    Divider()
                    if let correctCut {
                        Button(action: correctCut) {
                            Label {
                                Text(item.isCropped ? "Popraw kadr" : "Przytnij zdjęcie")
                                if item.isCropped {
                                    Text(item.cut?.byOwner == true ? "Przycięte przez Ciebie" : "Przycięte automatycznie")
                                }
                            } icon: {
                                Cropped.image
                            }
                        }
                    }
                    if let undoCut {
                        Button(action: undoCut) {
                            Label {
                                Text("Cofnij kadrowanie")
                                Text("Całe zdjęcie z muzeum")
                            } icon: {
                                Image(systemName: "arrow.uturn.backward")
                            }
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
                    if let restore {
                        Button(action: restore) {
                            Label {
                                Text("Kreatywny restaurator")
                                Text("Model AI dorysuje szczegóły")
                            } icon: {
                                Image(systemName: LowRes.restoredSymbol)
                            }
                        }
                    }
                    if item.sharper != nil {
                        Button("Przywróć zdjęcie muzeum", systemImage: "arrow.uturn.backward", action: keepOwn)
                    }
                }
                if buying {
                    if let url = AppModel.alamySearch(item) {
                        Link(destination: url) {
                            Label {
                                Text("Kup w Alamy")
                                Text("Licencja osobista od 17 £")
                            } icon: {
                                Image(systemName: "cart")
                            }
                        }
                    }
                    if let bringCopy {
                        Button("Wczytaj kupioną kopię", systemImage: "square.and.arrow.down.on.square", action: bringCopy)
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
