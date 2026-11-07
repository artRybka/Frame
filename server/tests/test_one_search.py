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
    # The museum's own text said "guitar"; ours has neither word nor style.
    item = _item(1, title="Still Life", year=1913)
    assert not matches(item, rules)
    found = item.model_copy(update={"found_for": [rules.search_key()]})
    assert matches(found, rules)
    # Another search, or a museum left out: no.
    assert not matches(found, PlaylistRules(query="lutnia", terms=["style:cubism"]))
    assert not matches(found, rules.model_copy(update={"exclude_sources": ["aic"]}))
    assert not matches(found.model_copy(update={"excluded": True}), rules)


def test_periods_are_checked_on_the_work_also_when_found() -> None:
    # 17th and 19th century: the museums are asked for 1601-1900, which
    # takes in the 18th century too.
    rules = PlaylistRules(query="gitara", terms=["period:17c", "period:19c"])
    key = rules.search_key()
    assert matches(_item(1, year=1650, found_for=[key]), rules)
    assert not matches(_item(2, year=1750, found_for=[key]), rules)
    search = MuseumSearch.of(rules)
    assert search.fits(_item(1, year=1650)) and not search.fits(_item(2, year=1750))


def test_the_library_remembers_the_searches(tmp_path) -> None:
    library = Library(tmp_path / "lib.db")
    library.upsert(_item(1, title="Still Life"))
    rules = PlaylistRules(query="gitara")
    assert library.query(rules)[0] == 0
    library.found("aic:1", rules.search_key())
    assert [i.id for i in library.query(rules)[1]] == ["aic:1"]
    # Taken in again from the museum: the search stays.
    library.upsert(_item(1, title="Still Life", found_for=["s:other"]))
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
        items = [self._item(str(n), title=f"Still Life {n}", year=1910 + n) for n in range(6)]
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
        # Already in the library, without the word: the search makes it fit.
        library.upsert(_item(0, title="Still Life 0", year=1910))
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
    assert job.item_ids == ["aic:0", "aic:1", "aic:2", "aic:3"]
    total, found = library.query(rules, sort="year")
    assert total == 4 and [i.id for i in found] == job.item_ids
