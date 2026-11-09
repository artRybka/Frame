"""Who the catalogue's artists are, from Wikidata (Mateusz 2026-11-09:
"vermeer" in Szukaj gave "Jan Vermeer" twice, "Jan Vermeer van Haarlem" and
"Johannes Vermeer" as a keyword)."""

from __future__ import annotations

import json
from collections.abc import Callable
from types import SimpleNamespace
from urllib.parse import parse_qs

import httpx

from frame_server.artist_people import ArtistPeople, fits
from frame_server.library import Item, Library
from frame_server.library.artists import ArtistNames, is_artist
from frame_server.library.models import PlaylistRules
from frame_server.web.discover_api import _term_hits

#: Wikidata as it answers: the search's hits by name, each item's facts.
SEARCH = {
    "Johannes Vermeer": [("Q41264", "Dutch painter (1632–1675)")],
    "Jan Vermeer": [
        ("Q41264", "Dutch painter (1632–1675)"),
        ("Q1680603", "Dutch painter (1628–1691)"),
    ],
    "Jan Vermeer van Haarlem": [("Q1680603", "Dutch painter (1628–1691)")],
    "Jan Vermeer van Haarlem the Elder": [("Q1680603", "Dutch painter (1628–1691)")],
    "Nobody Known": [("Q999", "family name")],
}
FACTS = {
    "Q41264": (True, 1632, 1675, "Johannes Vermeer", "Jan Vermeer"),
    "Q1680603": (True, 1628, 1691, "Jan Vermeer van Haarlem", "Jan Vermeer van Haarlem"),
    "Q999": (False, None, None, "Known", ""),
}


def _wikidata(asked: list[str]) -> httpx.Client:
    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.wikidata.org":
            name = request.url.params["search"]
            asked.append(name)
            hits = [{"id": q, "description": d} for q, d in SEARCH.get(name, [])]
            return httpx.Response(200, json={"search": hits})
        query = parse_qs(request.content.decode())["query"][0]
        rows = []
        for qid, (human, born, died, en, pl) in FACTS.items():
            if f"wd:{qid}" not in query:
                continue
            row = {
                "item": {"value": f"http://www.wikidata.org/entity/{qid}"},
                "human": {"value": "true" if human else "false"},
                "en": {"value": en},
            }
            if born:
                row["born"] = {"value": str(born)}
                row["died"] = {"value": str(died)}
            if pl:
                row["pl"] = {"value": pl}
            rows.append(row)
        return httpx.Response(200, content=json.dumps({"results": {"bindings": rows}}))

    return httpx.Client(transport=httpx.MockTransport(answer))


def _works(lib: Library, artist: str, years: list[int | None], source: str = "rijks") -> None:
    for year in years:
        n = len(lib.all_items())
        lib.upsert(
            Item(
                id=f"{source}:{n}",
                source=source,
                source_id=str(n),
                title=f"Work {n}",
                artist=artist,
                year=year,
            )
        )


def test_wikidata_tells_who_is_who(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    _works(lib, "Johannes Vermeer", [1660, 1665, 1670])
    _works(lib, "Jan Vermeer", [1658, 1666], source="commons")
    _works(lib, "Vermeer, Johannes", [1662])
    _works(lib, "Jan Vermeer van Haarlem", [1670, 1680])
    _works(lib, "Jan Vermeer van Haarlem the Elder", [1650, 1660])
    _works(lib, "Nobody Known", [1900, 1901])
    asked: list[str] = []
    people = ArtistPeople(lib, lambda: _wikidata(asked))
    assert people.after_start() == 5
    assert "Nobody Known" in asked
    ids = people.ids()
    assert ids["Jan Vermeer"][0] == ids["Johannes Vermeer"][0] == "Q41264"
    assert ids["Jan Vermeer van Haarlem"][0] == "Q1680603"
    assert ids["Nobody Known"][0] == ""
    assert people.people()["Q41264"]["pl"] == "Jan Vermeer"

    # One row for Vermeer of Delft, under Wikidata's name; van Haarlem apart.
    index = lib.term_index()
    rows = index.artists("vermeer")
    assert rows[0] == ("Johannes Vermeer", 6)
    assert ("Jan Vermeer van Haarlem", 4) in rows
    assert len(rows) == 2
    assert lib.query(PlaylistRules(artists=["Jan Vermeer"]))[0] == 6

    # Asked once: nothing again until a miss is due.
    asked.clear()
    assert people.after_start() == 0
    assert asked == []


def test_two_wikidata_people_are_never_joined() -> None:
    works = {"Jan Vermeer": [1, 2], "Jan Vermeer van Haarlem": [3]}
    # Without Wikidata, the shorter name in exactly one longer one joins it.
    assert ArtistNames(works).shown("Jan Vermeer") == ArtistNames(works).shown(
        "Jan Vermeer van Haarlem"
    )
    known = ArtistNames(works, {"Jan Vermeer": "Q41264", "Jan Vermeer van Haarlem": "Q1680603"})
    assert known.person("Jan Vermeer") != known.person("Jan Vermeer van Haarlem")
    # Spellings of one item are one person, however different their words.
    joined = ArtistNames(
        {"Rembrandt": [1], "Rembrandt Harmenszoon van Rijn": [2, 3], "Rembrandt Peale": [4]},
        {"Rembrandt": "Q5598", "Rembrandt Harmenszoon van Rijn": "Q5598"},
        {"Q5598": "Rembrandt"},
    )
    assert joined.shown("Rembrandt Harmenszoon van Rijn") == "Rembrandt"
    assert joined.person("Rembrandt Peale") != joined.person("Rembrandt")


def test_a_life_fits_the_works_years() -> None:
    assert fits(1632, 1675, [1655, 1660, 1670])
    assert not fits(1820, 1890, [1655, 1660])
    assert fits(1600, None, [1650])
    assert not fits(None, None, [1650])


def test_museum_codes_are_no_artists() -> None:
    assert not is_artist("MTB-PE-817")
    assert not is_artist("#PredmetAutor:6058030")
    assert not is_artist("AnonimowyUnknown author Imitator of Rembrandt")
    assert is_artist("Johannes Vermeer")
    assert is_artist("Master of 1499")


def test_a_keyword_that_is_an_artist_is_not_suggested_again(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    for n, keywords in enumerate([["Johannes Vermeer"], ["johannes vermeer's"], ["vermeer blue"]]):
        lib.upsert(
            Item(
                id=f"a:{n}",
                source="a",
                source_id=str(n),
                title=f"Work {n}",
                artist="Johannes Vermeer",
                keywords=keywords,
            )
        )
    hits = _term_hits(SimpleNamespace(library=lib), "vermeer", 10)  # type: ignore[arg-type]
    words = [h.name for h in hits if h.kind == "word"]
    assert words == ["vermeer blue", "vermeer"]
    assert [h.name for h in hits if h.kind == "artist"] == ["Johannes Vermeer"]


def _failing(
    asked: list[str], fail: Callable[[httpx.Request], bool], code: int = 502
) -> httpx.Client:
    """Wikidata as :func:`_wikidata`, but answering ``code`` to the requests
    ``fail`` picks."""
    inner = _wikidata(asked)

    def answer(request: httpx.Request) -> httpx.Response:
        if fail(request):
            return httpx.Response(code, request=request)
        return inner.send(request)

    return httpx.Client(transport=httpx.MockTransport(answer))


def _vermeers(lib: Library) -> None:
    _works(lib, "Johannes Vermeer", [1660, 1665, 1670])
    _works(lib, "Jan Vermeer", [1658, 1666], source="commons")
    _works(lib, "Jan Vermeer van Haarlem", [1670, 1680])
    _works(lib, "Jan Vermeer van Haarlem the Elder", [1650, 1660])
    _works(lib, "Nobody Known", [1900, 1901])


def test_a_passing_wikidata_error_is_asked_again(tmp_path) -> None:
    """One 502 of query.wikidata.org ended the first round after 2200 of
    3000 spellings (Mateusz 2026-11-09): it is asked again after a wait."""
    lib = Library(tmp_path / "lib.db")
    _vermeers(lib)
    sparql: list[int] = []

    def once(request: httpx.Request) -> bool:
        if request.url.host != "query.wikidata.org":
            return False
        sparql.append(1)
        return len(sparql) == 1

    people = ArtistPeople(lib, lambda: _failing([], once))
    slept: list[float] = []
    people.sleep = slept.append
    assert people.after_start() == 4
    assert slept == [15.0]
    assert len(people.ids()) == 5


def test_a_failing_batch_is_left_and_the_round_goes_on(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("frame_server.artist_people.BATCH", 1)
    lib = Library(tmp_path / "lib.db")
    _vermeers(lib)

    def jan(request: httpx.Request) -> bool:
        return request.url.params.get("search") == "Jan Vermeer"

    people = ArtistPeople(lib, lambda: _failing([], jan, code=503))
    slept: list[float] = []
    people.sleep = slept.append
    assert people.after_start() == 3
    assert slept == [15.0, 60.0]
    ids = people.ids()
    assert "Jan Vermeer" not in ids  # asked next time
    assert ids["Johannes Vermeer"][0] == "Q41264"
    assert ids["Jan Vermeer van Haarlem the Elder"][0] == "Q1680603"
    assert "Nobody Known" in ids


def test_wikidata_failing_on_and_on_ends_the_round(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("frame_server.artist_people.BATCH", 1)
    lib = Library(tmp_path / "lib.db")
    _vermeers(lib)
    asked: list[str] = []
    sent: list[int] = []

    def always(request: httpx.Request) -> bool:
        sent.append(1)
        return True

    people = ArtistPeople(lib, lambda: _failing(asked, always))
    people.sleep = lambda _: None
    assert people.after_start() == 0
    assert len(sent) == 3 * 3  # three batches, each tried three times
    assert people.ids() == {}


def test_a_429_ends_the_round_at_once(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    _vermeers(lib)
    sent: list[int] = []

    def always(request: httpx.Request) -> bool:
        sent.append(1)
        return True

    people = ArtistPeople(lib, lambda: _failing([], always, code=429))
    slept: list[float] = []
    people.sleep = slept.append
    assert people.after_start() == 0
    assert sent == [1]
    assert slept == []
