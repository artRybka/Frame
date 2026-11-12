"""Szukaj and a smart playlist of the same choices are one search (Mateusz,
2026-11-07): the museums are asked alike, and what they found fits the
choices in the catalogue too."""

from __future__ import annotations

from typing import ClassVar

from frame_server.library import Item, Library, PlaylistRules
from frame_server.library.importer import Importer, Job
from frame_server.library.museums import MUSEUMS, Museum
from frame_server.library.repo import matches
from frame_server.library.search import MuseumSearch, fill
from frame_server.library.wording import Wording


def _item(n: int, **fields: object) -> Item:
    return Item(id=f"aic:{n}", source="aic", source_id=str(n), **fields)  # type: ignore[arg-type]


def test_the_search_key_is_what_the_museums_are_asked() -> None:
    a = PlaylistRules(query="Gitara  ", artists=["B", "A"], terms=["period:17c", "style:baroque"])
    b = PlaylistRules(query="gitara", artists=["A", "B"], terms=["style:baroque", "period:17c"])
    assert a.search_key() == b.search_key() != ""
    # Museums chosen or left out are checked on their own.
    assert PlaylistRules(query="gitara", sources=["met"]).search_key() == (
        PlaylistRules(query="gitara", exclude_sources=["yale"]).search_key()
    )
    assert PlaylistRules(query="gitara").search_key() != PlaylistRules(query="lutnia").search_key()
    assert PlaylistRules(sources=["met"]).search_key() == ""
    assert PlaylistRules(sources=["met"]).search_key() == PlaylistRules().search_key()


def test_a_work_the_search_found_fits_its_choices() -> None:
    rules = PlaylistRules(query="gitara", terms=["style:cubism"])
    # The museum was asked "guitar"; ours has neither the typed word nor
    # the style.
    item = _item(1, title="Still Life with a Guitar", year=1913)
    said = [["gitara", "guitar"]]
    assert not matches(item, rules)
    found = item.model_copy(update={"found_for": [rules.search_key()]})
    assert matches(found, rules, said=said)
    # Without the words, as typed or as asked, the museum's say is not
    # enough (Mateusz 2026-11-09: Yale's three sheep for "vermeer").
    assert not matches(found, rules)
    sheep = found.model_copy(update={"title": "Three Sheep"})
    assert not matches(sheep, rules, said=said)
    # Another search, or a museum left out: no.
    assert not matches(found, PlaylistRules(query="lutnia", terms=["style:cubism"]))
    assert not matches(found, rules.model_copy(update={"exclude_sources": ["aic"]}))
    assert not matches(found.model_copy(update={"excluded": True}), rules)


def test_one_technique_is_checked_on_the_work_also_when_found() -> None:
    """Malarstwo with Monet: museums asked for an artist bring every kind of
    his works; what their type or material says another technique is out,
    in Szukaj and in the catalogue (Mateusz 2026-11-10: AIC's caricatures,
    "Drawing and Watercolor", "graphite on tan paper")."""
    rules = PlaylistRules(artists=["Claude Monet"], terms=["technique:painting"])
    key = rules.search_key()

    def found(n: int, classification: str, medium: str = "") -> Item:
        return _item(
            n,
            artist="Claude Monet",
            classification=classification,
            medium=medium,
            found_for=[key],
        )

    caricature = found(1, "Drawing and Watercolor", "Graphite on tan wove paper")
    assert not matches(caricature, rules)
    assert not MuseumSearch.of(rules).fits(caricature)
    assert matches(found(2, "Painting", "Oil on canvas"), rules)
    # The type first: an oil sketch the museum files under drawings is one.
    assert not matches(found(3, "Drawing", "Oil on paper"), rules)
    # Its material when the type says nothing; oil beside graphite.
    assert matches(found(4, "", "Oil and graphite on canvas"), rules)
    assert not matches(found(5, "", "Etching"), rules)
    assert not matches(found(6, "Print", "akwaforta, papier"), rules)
    assert matches(found(7, "Painting", "olej, płótno"), rules)
    # Saying nothing of its technique: the museum's search is trusted.
    assert matches(found(8, "Image"), rules)
    # Grafika: Degas's monotypes and Polish types are prints.
    prints = PlaylistRules(artists=["Edgar Degas"], terms=["technique:print"])
    degas = _item(
        9, artist="Edgar Degas", classification="Monotype", found_for=[prints.search_key()]
    )
    assert matches(degas, prints)
    assert not matches(degas.model_copy(update={"classification": "Painting"}), prints)


def test_periods_are_checked_on_the_work_also_when_found() -> None:
    # 17th and 19th century: the museums are asked for 1601-1900, which
    # takes in the 18th century too.
    rules = PlaylistRules(query="gitara", terms=["period:17c", "period:19c"])
    key = rules.search_key()
    said = [["gitara", "guitar"]]
    assert matches(_item(1, title="Guitar", year=1650, found_for=[key]), rules, said=said)
    assert not matches(_item(2, title="Guitar", year=1750, found_for=[key]), rules, said=said)
    search = MuseumSearch.of(rules)
    assert search.fits(_item(1, year=1650)) and not search.fits(_item(2, year=1750))


def test_the_library_remembers_the_searches(tmp_path) -> None:
    library = Library(tmp_path / "lib.db")
    library.wording = lambda text: ("guitar",) if text == "gitara" else ()
    library.upsert(_item(1, title="Still Life with a Guitar"))
    library.upsert(_item(2, title="Still Life with a Lute"))
    rules = PlaylistRules(query="gitara")
    # The word as the museums are asked it finds the catalogue's works too
    # (Mateusz 2026-11-09: "uliczka" and Vermeer's "The Little Street").
    assert [i.id for i in library.query(rules)[1]] == ["aic:1"]
    assert library.query(PlaylistRules(query="lutnia"))[0] == 0
    library.found("aic:1", rules.search_key())
    assert [i.id for i in library.query(rules)[1]] == ["aic:1"]
    # Taken in again from the museum: the search stays.
    library.upsert(_item(1, title="Still Life with a Guitar", found_for=["s:other"]))
    stored = library.get("aic:1")
    assert stored is not None
    assert stored.found_for == [rules.search_key(), "s:other"]


class Guitars(Museum):
    key = "aic"
    name = "Guitars"
    page_size = 100
    asked: ClassVar[list[str]] = []

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        Guitars.asked.append(query)
        items = [self._item(str(n), title=f"Guitar {n}", year=1910 + n) for n in range(6)]
        return len(items), items[(page - 1) * limit : page * limit]

    def fetch(self, source_id: str) -> Item | None:
        return None


class Importing(Importer):
    def _analysed(self, item: Item) -> Item:
        return item

    def measure(self, items, seconds=0.0) -> None:  # type: ignore[no-untyped-def]
        pass


def test_a_smart_playlist_fetches_what_szukaj_finds(tmp_path) -> None:
    saved = dict(MUSEUMS)
    MUSEUMS.clear()
    MUSEUMS.update(aic=Guitars)
    Guitars.asked = []
    try:
        library = Library(tmp_path / "lib.db")
        library.wording = lambda text: ("guitar", "guitare") if text == "gitara" else ()
        # Already in the library, without the typed word: it fits by the
        # word the museums are asked, as in Szukaj.
        library.upsert(_item(0, title="Guitar 0", year=1910))
        importer = Importing(library, None, None)  # type: ignore[arg-type]
        importer.cache = type("Cache", (), {"remove": lambda self, item: None})()
        importer.translate = lambda text, wait: Wording(text, en="guitar", fr="guitare")
        rules = PlaylistRules(query="gitara")
        job = Job(id="j", description="fill")
        fill(importer, rules, 4, job)
    finally:
        MUSEUMS.clear()
        MUSEUMS.update(saved)
    # Asked in the museum's language, as Szukaj asks it.
    assert Guitars.asked and set(Guitars.asked) == {"guitar"}
    assert job.done == 4
    # The one it had fits already: four more.
    assert job.item_ids == ["aic:1", "aic:2", "aic:3", "aic:4"]
    total, found = library.query(rules, sort="year")
    assert total == 5 and [i.id for i in found] == ["aic:0", *job.item_ids]


def test_a_cards_playlist_is_topped_up_as_szukaj_finds_unless_of_artists(monkeypatch) -> None:
    """Stage 6b: on the museums, 2026-11-11, "Morze i statki" drawn by style
    brought two portraits among ten works, asked as Szukaj asks ten works of
    the sea; a card of artists keeps its artists' turns, no search asks
    for the museums' highlights, and a card of colours as Szukaj finds took
    seven minutes for two works."""
    from frame_server.library import search

    went: list[str] = []

    class Recording:
        def fill(self, rules, count, job, pooled=False) -> None:  # type: ignore[no-untyped-def]
            went.append("drawn")

    monkeypatch.setattr(search, "fill", lambda *args, **kwargs: went.append("as Szukaj"))
    job = Job(id="j", description="card")
    for rules in (
        PlaylistRules(terms=["subject:sea", "subject:ships"]),  # Morze i statki
        PlaylistRules(terms=["period:17c"]),  # Złoty wiek
        PlaylistRules(query="autumn"),  # Jesień
        PlaylistRules(artists=["Turner", "Caspar David Friedrich"]),  # Romantyzm
        PlaylistRules(terms=["tag:highlight"]),  # Arcydzieła muzeów
        PlaylistRules(  # Ciepłe barwy
            terms=["technique:painting", "technique:drawing"], colors=["warm"]
        ),
    ):
        search.fill_card(Recording(), rules, 10, job, pooled=True)  # type: ignore[arg-type]
    assert went == ["as Szukaj", "as Szukaj", "as Szukaj", "drawn", "drawn", "drawn"]


def test_an_artist_search_keeps_only_their_own_works() -> None:
    # Museums find whatever names him: Guillaumin's self-portrait, an
    # anonymous sheet, a print after him (Mateusz, 2026-11-07).
    rules = PlaylistRules(artists=["Vincent van Gogh"])
    key = rules.search_key()
    search = MuseumSearch.of(rules)
    his = [
        _item(1, artist="Vincent van Gogh"),
        _item(2, artist="Gogh, Vincent van"),
        _item(3, artist="Vincent van Gogh (Dutch, 1853-1890)"),
        _item(4, artist="Attributed to Vincent van Gogh"),
    ]
    others = [
        _item(5, artist="Armand Guillaumin"),
        _item(6, artist="Anonymous"),
        _item(7, artist=""),
        _item(8, artist="Paul Gachet, after Vincent van Gogh"),
        _item(9, artist="Copy after Vincent van Gogh"),
        _item(10, artist="Theo van Gogh"),
    ]
    for item in his:
        assert search.fits(item), item.artist
        assert matches(item.model_copy(update={"found_for": [key]}), rules), item.artist
    for item in others:
        assert not search.fits(item), item.artist
        # Remembered from an earlier search: no longer counted in.
        assert not matches(item.model_copy(update={"found_for": [key]}), rules), item.artist


class Mentions(Museum):
    """A museum whose search for an artist brings works naming him first."""

    key = "aic"
    name = "Mentions"
    page_size = 100
    asked: ClassVar[list[int]] = []

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        Mentions.asked.append(page)
        artists = ["Armand Guillaumin"] * 8 + ["Vincent van Gogh"] * 8
        items = [self._item(str(n), title=f"Work {n}", artist=a) for n, a in enumerate(artists)]
        return len(items), items[(page - 1) * limit : page * limit]

    def fetch(self, source_id: str) -> Item | None:
        return None


def test_an_artist_search_looks_further_for_their_works(tmp_path) -> None:
    saved = dict(MUSEUMS)
    MUSEUMS.clear()
    MUSEUMS.update(aic=Mentions)
    Mentions.asked = []
    try:
        library = Library(tmp_path / "lib.db")
        importer = Importing(library, None, None)  # type: ignore[arg-type]
        search = MuseumSearch.of(PlaylistRules(artists=["Vincent van Gogh"]), limit=8)
        _total, items, failed, after = search.ask(importer, ["aic"], 1)
    finally:
        MUSEUMS.clear()
        MUSEUMS.update(saved)
    # The first page names him only; the second has his works.
    assert Mentions.asked == [1, 2]
    assert len(items) == 8 and {i.artist for i in items} == {"Vincent van Gogh"}
    assert not failed and after == 3


def test_a_search_hands_on_the_works_that_do_not_fit(tmp_path) -> None:
    # Asked for already: the catalogue may still want them (Mateusz,
    # 2026-11-07, "szkoda byłoby tracić te odpytania").
    saved = dict(MUSEUMS)
    MUSEUMS.clear()
    MUSEUMS.update(aic=Mentions)
    Mentions.asked = []
    spare: list[Item] = []
    try:
        library = Library(tmp_path / "lib.db")
        importer = Importing(library, None, None)  # type: ignore[arg-type]
        search = MuseumSearch.of(PlaylistRules(artists=["Vincent van Gogh"]), limit=8)
        _total, items, _failed, _after = search.ask(importer, ["aic"], 1, spare.extend)
    finally:
        MUSEUMS.clear()
        MUSEUMS.update(saved)
    assert {i.artist for i in items} == {"Vincent van Gogh"}
    assert len(spare) == 8 and {i.artist for i in spare} == {"Armand Guillaumin"}


def test_works_not_shown_join_the_catalogue_after_the_shown_ones(tmp_path) -> None:
    library = Library(tmp_path / "lib.db")

    class Cache:
        def thumb_path(self, item: Item):  # type: ignore[no-untyped-def]
            return tmp_path / f"{item.source_id}.jpg"

    importer = Importing(library, Cache(), None)  # type: ignore[arg-type]
    taken: list[list[str]] = []
    importer._start_searched = lambda: None  # type: ignore[method-assign]
    importer._take = lambda streams, *a, **k: taken.append([i.id for i in streams[0]])  # type: ignore[method-assign]
    for n in (1, 2, 4):
        (tmp_path / f"{n}.jpg").write_bytes(b"jpeg")
    # Only those whose thumbnail is here: they cost no request.
    importer.keep_spare([_item(1), _item(2), _item(3)])
    # Shown meanwhile: it goes first, and once.
    importer.keep_searched([_item(4), _item(2)], found="s:1")
    importer._take_searched()
    assert taken == [["aic:4", "aic:2"], ["aic:1"]]
    # Seen once, not queued again.
    importer.keep_spare([_item(1), _item(4)])
    assert not importer._spare
