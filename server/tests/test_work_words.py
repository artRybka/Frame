"""A search finds a work by the words of any of its copies, and by the
words as the museums are asked them (Mateusz 2026-11-09: "Jan Vermeer" with
"uliczka" found nothing, though "The Little Street" is in the catalogue;
"zaznaczę tylko że to przykład. Chciałbym żeby działało to uniwersalnie")."""

from __future__ import annotations

from pathlib import Path

from frame_server.library import Item, Library, PlaylistRules


def _item(item_id: str, **fields: object) -> Item:
    source, _, source_id = item_id.partition(":")
    return Item(id=item_id, source=source, source_id=source_id, **fields)  # type: ignore[arg-type]


def _ids(library: Library, **rules: object) -> list[str]:
    return [i.id for i in library.query(PlaylistRules(**rules))[1]]  # type: ignore[arg-type]


def test_a_copys_words_find_the_work_shown_in_its_best_copy(tmp_path: Path) -> None:
    library = Library(tmp_path / "lib.db")
    library.upsert(
        _item(
            "rijks:1",
            title="View of Houses in Delft, Known as 'The Little Street'",
            artist="Johannes Vermeer",
            keywords=["washtub"],
        )
    )
    library.upsert(
        _item("wmc:2", title="Uliczka", artist="Jan Vermeer", pooled=True, copy_of="rijks:1")
    )
    library.upsert(_item("wmc:3", title="Widok Delftu", artist="Jan Vermeer", pooled=True))
    assert _ids(library, query="uliczka") == ["rijks:1"]
    assert _ids(library, query="uliczka", artists=["Johannes Vermeer"]) == ["rijks:1"]
    assert _ids(library, query="washtub") == ["rijks:1"]
    # The other filters still hold for the copy shown.
    assert _ids(library, query="uliczka", artists=["Rembrandt"]) == []
    assert _ids(library, query="uliczka delft") == ["rijks:1"]
    assert _ids(library, query="lutnia") == []


def test_the_words_as_the_museums_are_asked_find_the_catalogues_works(tmp_path: Path) -> None:
    library = Library(tmp_path / "lib.db")
    library.wording = lambda text: ("little street", "ruelle") if text == "uliczka" else ()
    library.upsert(_item("rijks:1", title="The Little Street", artist="Johannes Vermeer"))
    library.upsert(_item("rijks:2", title="The Milkmaid", artist="Johannes Vermeer"))
    library.upsert(_item("met:3", title="Little Girl in a Street", artist="Someone"))
    assert _ids(library, query="uliczka") == ["rijks:1"]
    assert _ids(library, query="uliczka", artists=["Johannes Vermeer"]) == ["rijks:1"]
    assert library.query(PlaylistRules(query="uliczka"), limit=0)[0] == 1


def test_a_hidden_copy_leaves_the_copy_someone_likes(tmp_path: Path) -> None:
    """WikiArt's "The Little Street", hidden on 11-06, took the
    Rijksmuseum's copy Mateusz liked with it once their pictures showed them
    to be one work (2026-11-09). A copy only kept still goes with the work
    hidden (``test_later``)."""
    library = Library(tmp_path / "lib.db")
    library.upsert(_item("rijks:1", title="View of Houses in Delft", artist="Johannes Vermeer"))
    library.set_favorite("owner", "rijks:1", True)
    library.upsert(
        _item(
            "wikiart:2",
            title="The Little Street",
            artist="Johannes Vermeer",
            pooled=True,
            excluded=True,
            copy_of="rijks:1",
        )
    )
    library.upsert(_item("wmc:3", title="Uliczka", artist="Jan Vermeer", pooled=True))
    library.upsert(
        _item("wmc:4", title="Mleczarka", artist="Jan Vermeer", pooled=True, copy_of="wikiart:5")
    )
    library.upsert(
        _item(
            "wikiart:5", title="The Milkmaid", artist="Johannes Vermeer", pooled=True, excluded=True
        )
    )
    assert _ids(library, query="delft") == ["rijks:1"]
    assert _ids(library, query="little street") == ["rijks:1"]
    # A work only the server added stays hidden with all its copies.
    assert _ids(library, query="mleczarka") == []
