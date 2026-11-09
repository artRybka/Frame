"""Szukaj's chips: one chip is one phrase, each further chip narrows the
search, never "any of them" (Mateusz, 2026-11-09)."""

from __future__ import annotations

import sqlite3
from typing import ClassVar

from frame_server.library import Item, Library, PlaylistRules
from frame_server.library.importer import Importer
from frame_server.library.museums import MUSEUMS, Museum
from frame_server.library.phrases import fts, has_phrase, phrases, quote, tokens
from frame_server.library.repo import matches
from frame_server.library.search import MuseumSearch
from frame_server.library.wording import Wording


def _item(n: int, **fields: object) -> Item:
    return Item(id=f"aic:{n}", source="aic", source_id=str(n), **fields)  # type: ignore[arg-type]


def test_a_query_keeps_its_phrases() -> None:
    assert tokens('"nocna straż" portret') == ["nocna straż", "portret"]
    # Saved before phrases: every word on its own, as it meant then.
    assert tokens("nocna straż") == ["nocna", "straż"]
    assert tokens('  "nocna   straż"  "nocna straż" "" ') == ["nocna straż"]
    assert quote(["nocna straż", "portret", " "]) == '"nocna straż" portret'
    assert tokens(quote(["nocna straż", "portret"])) == ["nocna straż", "portret"]
    assert phrases('"nocna straż" portret') == ["nocna straż"]


def test_a_phrase_is_its_words_next_to_each_other() -> None:
    assert has_phrase("night watch", "The Night Watch")
    assert has_phrase("night watch", "Ronde de nuit: night watches")
    assert has_phrase("nocna straż", "Kompania kapitana Cocqa, zwana Nocną strażą")
    assert has_phrase("nocna straż", "obraz nocnej straży")
    # Another word made from it, or the words apart: no.
    assert not has_phrase("night watch", "Nachtwächter (Night Watchman)")
    assert not has_phrase("night watch", "At night the lover watches the garden")
    assert not has_phrase("night watch", "watch night")


def test_the_indexes_are_asked_for_the_phrase() -> None:
    assert fts('"night watch" rembrandt') == '"night watch" "rembrandt"'
    assert fts("night watch") == '"night" "watch"'
    db = sqlite3.connect(":memory:")
    db.execute("CREATE VIRTUAL TABLE t USING fts5(text, tokenize = 'porter unicode61')")
    db.executemany(
        "INSERT INTO t VALUES (?)",
        [("The Night Watch",), ("Night Watchman",), ("At night the lover watches",)],
    )
    found = db.execute("SELECT text FROM t WHERE t MATCH ?", (fts('"night watch"'),)).fetchall()
    assert [f[0] for f in found] == ["The Night Watch"]


def test_the_catalogue_wants_the_phrase_and_every_chip() -> None:
    watch = _item(1, title="Nocna straż", description="Portret zbiorowy strażników nocą")
    apart = _item(2, title="Straż", description="Pejzaż nocą, nocna mgła")
    rules = PlaylistRules(query=quote(["nocna straż"]))
    assert matches(watch, rules)
    assert not matches(apart, rules)
    # Every further chip narrows.
    assert matches(watch, PlaylistRules(query=quote(["nocna straż", "portret"])))
    assert not matches(watch, PlaylistRules(query=quote(["nocna straż", "pejzaż"])))
    # A playlist saved before phrases: each word anywhere, as before.
    assert matches(apart, PlaylistRules(query="nocna straż"))


class Watches(Museum):
    """A museum whose search finds the words anywhere."""

    key = "aic"
    name = "Watches"
    page_size = 100
    asked: ClassVar[list[str]] = []

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        Watches.asked.append(query)
        titles = [
            "Nachtwächter (Night Watchman)",
            "The Actor as a Night Watch",
            "The lover watches the garden at night",
            "The Night Watch",
        ]
        items = [self._item(str(n), title=t) for n, t in enumerate(titles)]
        return len(items), items[(page - 1) * limit : page * limit]

    def fetch(self, source_id: str) -> Item | None:
        return None


class Importing(Importer):
    def measure(self, items, seconds=0.0) -> None:  # type: ignore[no-untyped-def]
        pass


def _ask(tmp_path, rules: PlaylistRules, phrased: bool) -> list[Item]:  # type: ignore[no-untyped-def]
    saved = dict(MUSEUMS)
    MUSEUMS.clear()
    MUSEUMS.update(aic=Watches)
    Watches.asked = []
    Watches.phrases = phrased
    try:
        library = Library(tmp_path / "lib.db")
        importer = Importing(library, None, None)  # type: ignore[arg-type]
        importer.translate = lambda text, wait: (
            Wording(text, en="night watch", fr="ronde de nuit")
            if text == "nocna straż"
            else Wording(text)
        )
        _total, items, _failed, _after = MuseumSearch.of(rules, limit=8).ask(importer, ["aic"], 1)
    finally:
        MUSEUMS.clear()
        MUSEUMS.update(saved)
        Watches.phrases = False
    return items


def test_museums_get_the_phrase_translated_and_its_works_are_checked(tmp_path) -> None:
    items = _ask(tmp_path, PlaylistRules(query=quote(["nocna straż"])), phrased=True)
    assert Watches.asked[0] == '"night watch"'
    assert [i.title for i in items] == ["The Actor as a Night Watch", "The Night Watch"]
    # A museum that doesn't keep to quotes gets the words bare.
    items = _ask(tmp_path, PlaylistRules(query=quote(["nocna straż", "actor"])), phrased=False)
    assert Watches.asked[0] == "night watch actor"
    # The phrase checked here; a single word is the museum's to find.
    assert [i.title for i in items] == ["The Actor as a Night Watch", "The Night Watch"]


def test_single_words_are_left_to_the_museum(tmp_path) -> None:
    items = _ask(tmp_path, PlaylistRules(query="watch"), phrased=True)
    assert Watches.asked == ["watch"]
    assert len(items) == 4
