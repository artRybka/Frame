"""Museums asked for an artist's works by their own author field, not by
the name among the words (Mateusz 2026-11-09: "dlaczego na później?"):
fewer pages of works that only name them."""

from __future__ import annotations

import json
from typing import Any, ClassVar

import httpx

from frame_server.library import Item, Library, PlaylistRules
from frame_server.library.importer import Importer
from frame_server.library.museums import (
    MUSEUMS,
    Access,
    ArtInstituteChicago,
    ClevelandMuseum,
    Europeana,
    Museum,
    StatensMuseum,
    asked_by,
    by_artist,
    plain_text,
    surname_first,
)
from frame_server.library.search import museum_text


def test_the_artist_is_asked_apart_from_the_words() -> None:
    text = museum_text(PlaylistRules(query="sea", artists=["Claude Monet"]), 1)
    assert asked_by(text) == ("Claude Monet", "sea")
    assert plain_text(text) == "sea Claude Monet"
    assert museum_text(PlaylistRules(query="sea"), 1) == "sea"
    assert asked_by("sea") is None and plain_text("sea") == "sea"
    assert by_artist(" Claude  Monet ") == "@by:Claude Monet\t"
    assert surname_first("Vilhelm Hammershøi") == "Hammershøi, Vilhelm"
    assert surname_first("Vincent van Gogh") == "Gogh, Vincent van"
    assert surname_first("Rembrandt") == "Rembrandt"


def _asked(museum: type[Museum], answer: dict[str, Any] | None = None) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=answer or {})

    found = museum(httpx.Client(transport=httpx.MockTransport(handler)), access=Access())
    found.search_by("Vincent van Gogh", "", 8, 1)
    return seen


def test_each_museum_is_asked_by_its_author_field() -> None:
    aic = json.loads(_asked(ArtInstituteChicago)[0].content)
    assert aic["query"]["bool"]["must"][0] == {
        "match": {"artist_title": {"query": "Vincent van Gogh", "operator": "and"}}
    }
    assert _asked(ClevelandMuseum)[0].url.params["artists"] == "Vincent van Gogh"
    assert _asked(Europeana)[0].url.params["query"] == 'who:"Vincent van Gogh"'
    assert "[creator:Gogh, Vincent van]" in _asked(StatensMuseum)[0].url.params["filters"]


class ByField(Museum):
    """A museum whose author field knows only "Rembrandt van Rijn"."""

    key = "aic"
    name = "By field"
    asked: ClassVar[list[str]] = []

    def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
        ByField.asked.append(f"words: {query}")
        return 1, [self._item("w", title="Named", artist="Someone")]

    def search_by(
        self, artist: str, words: str = "", limit: int = 20, page: int = 1
    ) -> tuple[int, list[Item]]:
        ByField.asked.append(f"artist: {artist}")
        if artist != "Rembrandt van Rijn":
            return 0, []
        return 1, [self._item("r", title="Self-Portrait", artist=artist)]

    def fetch(self, source_id: str) -> Item | None:
        return None

    def _item(self, source_id: str, **fields: Any) -> Item:
        return Item(id=f"aic:{source_id}", source="aic", source_id=source_id, **fields)


def test_the_name_among_the_words_when_the_field_finds_nothing(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setitem(MUSEUMS, "aic", ByField)
    importer = Importer(Library(tmp_path / "lib.db"), None, None)  # type: ignore[arg-type]
    ByField.asked = []
    _, items = importer.search("aic", by_artist("Rembrandt van Rijn"), 8, 1)
    assert [i.title for i in items] == ["Self-Portrait"]
    assert ByField.asked == ["artist: Rembrandt van Rijn"]  # no second question
    ByField.asked = []
    _, items = importer.search("aic", by_artist("Rembrandt Harmensz. van Rijn", "sea"), 8, 1)
    assert ByField.asked == [
        "artist: Rembrandt Harmensz. van Rijn",
        "words: sea Rembrandt Harmensz. van Rijn",
    ]
