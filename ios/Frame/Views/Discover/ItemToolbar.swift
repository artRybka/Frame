import SwiftUI

/// The heart, "Do playlisty" (the host shows `AddToPlaylistSheet`) and "…"
/// of a work, top right: on its card and on its study (Mateusz 2026-11-13:
/// the playlists out of "…" onto their own button). "…" holds "Ukryj
/// dzieło", the copies and "Zapisz w Zdjęciach" (no museum's page nor
/// "Przywróć zdjęcie muzeum" since Mateusz 2026-11-20; the latter stays on
/// top of the copies' sheet).
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
    /// "Restauracja dzieła" (once "Kreatywny restaurator"), under the
    /// colours' correction: for a picture small for the frame (`LowRes`),
    /// drawn again by the image model.
    var restore: (() -> Void)? = nil
    /// "Popraw kadr" / "Przytnij zdjęcie": the corners of the work on its
    /// museum photograph, on a screen of their own (Mateusz 2026-11-14).
    var correctCut: (() -> Void)? = nil
    /// "Cofnij kadrowanie": the museum's photograph whole again.
    var undoCut: (() -> Void)? = nil
    /// "Zdejmij werniks" / "Odżółć papier" (`ColourRecovery`, "Korekta
    /// barw"): the work shown cleaned from now on, of `recoveryKind`; the
    /// same entry gives it up while the work is shown so (`cleaned`).
    var recover: (() -> Void)? = nil
    var recoveryKind = ColourRecovery.Kind.varnish
    var cleaned = false
    /// A work of his own (Mateusz 2026-11-15): "Edytuj opis", "Zrób zdjęcie
    /// ponownie" and "Usuń z katalogu", asked first (`deletingOwn`).
    var editOwn: (() -> Void)? = nil
    var retakeOwn: (() -> Void)? = nil
    var deleteOwn: (() -> Void)? = nil
    var deletingOwn: Binding<Bool>? = nil

    /// A museum's work, which other sources may have too. Another copy
    /// changes the picture for the whole household: the owner's to pick
    /// (Mateusz 2026-11-20).
    private var hasCopies: Bool { item.kind == .artwork && item.look == nil && model.isOwner }

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
                // Hidden for this person only, a guest too (Mateusz 2026-11-20:
                // „żeby działało dla każdego użytkownika indywidualnie”).
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
                if editOwn != nil || retakeOwn != nil {
                    Divider()
                    if let editOwn {
                        Button("Edytuj opis", systemImage: "pencil", action: editOwn)
                    }
                    if let retakeOwn {
                        Button(action: retakeOwn) {
                            Label {
                                Text("Zrób zdjęcie ponownie")
                                Text("Opis zostaje")
                            } icon: {
                                Image(systemName: "camera")
                            }
                        }
                    }
                }
                if correctCut != nil || undoCut != nil {
                    Divider()
                    if let correctCut {
                        Button(action: correctCut) {
                            Label {
                                Text(bound: item.isCropped ? "Popraw kadr" : "Przytnij zdjęcie")
                                if item.isCropped {
                                    Text(bound: item.cut?.byOwner == true ? "Przycięte przez Ciebie" : "Przycięte automatycznie")
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
                                Text(bound: item.isOwnWork ? "Całe zdjęcie" : "Całe zdjęcie z muzeum")
                            } icon: {
                                Image(systemName: "arrow.uturn.backward")
                            }
                        }
                    }
                }
                if recover != nil || restore != nil { Divider() }
                if let recover {
                    Button(action: recover) {
                        Label {
                            Text(bound: ColourRecovery.menuTitle(recoveryKind, on: cleaned))
                            Text(bound: ColourRecovery.menuNote(recoveryKind, on: cleaned))
                        } icon: {
                            if cleaned {
                                Image(systemName: "arrow.uturn.backward")
                            } else {
                                CleanedMark.image
                            }
                        }
                    }
                }
                // Right under the colours' correction, as the other way of
                // giving the work back (Mateusz 2026-11-16).
                if let restore {
                    Button(action: restore) {
                        Label {
                            Text(bound: LowRes.restoredName)
                            Text("Model AI dorysuje szczegóły")
                        } icon: {
                            Image(systemName: LowRes.restoredSymbol)
                        }
                    }
                }
                if hasCopies { Divider() }
                if hasCopies {
                    Button { findingCopies = true } label: {
                        Label {
                            Text("Szukaj lepszej kopii")
                            Text(bound: copiesNote)
                        } icon: {
                            Image(systemName: "plus.magnifyingglass")
                        }
                    }
                }
                savePhoto
                if deleteOwn != nil {
                    Divider()
                    Button("Usuń z katalogu", systemImage: "trash", role: .destructive) {
                        deletingOwn?.wrappedValue = true
                    }
                }
            } label: {
                Image(systemName: "ellipsis.circle").foregroundStyle(Theme.ink)
            }
            .accessibilityLabel("Więcej")
            // On the menu that asks: on iOS 26 a popover pointing at it.
            .confirmationDialog(
                "Usunąć „\(item.title.isEmpty ? "Bez tytułu" : item.title)” z katalogu?",
                isPresented: deletingOwn ?? .constant(false),
                titleVisibility: .visible
            ) {
                Button("Usuń", role: .destructive) { deleteOwn?() }
            } message: {
                Text(bound: "Zdjęcie i opis znikną z serwera, także z playlist. Tego nie da się cofnąć.")
            }
        }
    }

    /// "Zapisz w Zdjęciach", last: the work as this person sees it (its
    /// colours corrected when they are), and for a work in a frame or
    /// passe-partout, a choice of the work alone or in it (Mateusz
    /// 2026-11-20, sketch A: one entry opening a short menu).
    @ViewBuilder private var savePhoto: some View {
        if item.framed != nil, item.kind == .artwork {
            Menu {
                Button(action: { save(framed: false) }) {
                    Label {
                        Text("Samo dzieło")
                        if let note = PhotoSaver.colourNote(item) { Text(bound: note) }
                    } icon: {
                        Image(systemName: "photo")
                    }
                }
                Button(action: { save(framed: true) }) {
                    Label {
                        Text(bound: "W ramie")
                        Text(bound: PhotoSaver.framedNote(item))
                    } icon: {
                        Image(systemName: "photo.artframe")
                    }
                }
            } label: {
                Label("Zapisz w Zdjęciach", systemImage: "square.and.arrow.down")
            }
            .disabled(savingPhoto)
        } else {
            Button(action: { save(framed: false) }) {
                Label {
                    Text(bound: "Zapisz w Zdjęciach")
                    if let note = PhotoSaver.colourNote(item) { Text(bound: note) }
                } icon: {
                    Image(systemName: "square.and.arrow.down")
                }
            }
            .disabled(savingPhoto)
        }
    }

    private func save(framed: Bool) {
        savingPhoto = true
        Task {
            await model.saveToPhotos(item, framed: framed)
            savingPhoto = false
        }
    }

    /// Under "Szukaj lepszej kopii": how large the picture is now.
    private var copiesNote: String {
        if let sharper = item.sharper { return "Teraz \(max(sharper.width, sharper.height)) px" }
        if let side = pictureSide, side > 0 { return "Teraz \(side) px" }
        return "W innych muzeach i bazach"
    }
}
