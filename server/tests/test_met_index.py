"""The Met's open data searched at home (2026-11-07: a page of the Met's
search was 25 requests, and its bot wall turned the home address away)."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import httpx

from frame_server.library import met_index
from frame_server.library.met_index import MetIndex, build, index_path
from frame_server.library.museums import MET_LOCAL_MIN, Access, MetropolitanMuseum


def _row(object_id: int, title: str, **changes: str) -> dict[str, str]:
    return {
        "Object ID": str(object_id),
        "Is Public Domain": "True",
        "Is Highlight": "False",
        "Department": "European Paintings",
        "Title": title,
        "Artist Display Name": "",
        "Object Begin Date": "1880",
        "Object End Date": "1890",
        "Classification": "Paintings",
        **changes,
    }


ROWS = [
    _row(1, "Wheat Field with Cypresses", **{"Artist Display Name": "Vincent van Gogh"}),
    _row(2, "Cypresses", **{"Artist Display Name": "Vincent van Gogh", "Is Highlight": "True"}),
    _row(3, "Water Lilies", **{"Artist Display Name": "Claude Monet", "Is Public Domain": "False"}),
    _row(4, "A Tile", Department="Islamic Art", City="Iznik", **{"Object Begin Date": "1560"}),
    _row(5, "Cypresses at Night", Department="Photographs", Tags="Trees|Night"),
    _row(6, "Old", **{"Object Begin Date": "1500", "Object End Date": "1510"}),
]


def _index(tmp_path: Path) -> MetIndex:
    path = index_path(tmp_path)
    path.parent.mkdir(parents=True)
    assert build(path, iter(ROWS)) == 5  # the public-domain works
    return MetIndex(path)


def test_words_found_best_first(tmp_path: Path) -> None:
    index = _index(tmp_path)
    total, ids = index.search("cypresses")
    assert total == 3 and ids[0] == "2"  # the Met's highlight first
    assert index.search("van gogh cypresses")[0] == 2  # every word must be there
    assert index.search("monet") == (0, [])  # not in the public domain
    assert index.search("iznik")[1] == ["4"]  # where it was made
    assert index.search("night trees")[1] == ["5"]  # tags
    assert index.search('cypress" OR "x')[0] == 0  # typed text stays text


def test_filters(tmp_path: Path) -> None:
    index = _index(tmp_path)
    assert index.search("cypresses", department=19)[1] == ["5"]
    assert index.search("*", begin=1505, end=1600)[1] == ["4", "6"]  # overlaps
    assert index.search("*", highlight=True)[1] == ["2"]
    assert index.search("*", offset=1, limit=2) == (5, ["2", "4"])


def test_works_without_a_picture_are_left_out(tmp_path: Path) -> None:
    index = _index(tmp_path)
    index.no_picture("1")
    assert index.search("cypresses")[0] == 2
    assert index.showable(["1", "2", "3", "99", "x"]) == ["2"]


def _met(tmp_path: Path, asked: list[httpx.Request], search: list[int]) -> MetropolitanMuseum:
    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"total": len(search), "objectIDs": search})
        object_id = int(request.url.path.rsplit("/", 1)[1])
        record: dict[str, Any] = {
            "objectID": object_id,
            "isPublicDomain": True,
            "primaryImageSmall": ""
            if object_id == 1
            else f"https://images.metmuseum.org/{object_id}.jpg",
            "title": f"Work {object_id}",
        }
        return httpx.Response(200, json=record)

    http = httpx.Client(transport=httpx.MockTransport(answer))
    return MetropolitanMuseum(http, access=Access(data_dir=tmp_path))


def test_the_met_is_asked_only_for_the_works_found(tmp_path: Path, monkeypatch: Any) -> None:
    _index(tmp_path)
    monkeypatch.setattr("frame_server.library.museums.MET_LOCAL_MIN", 1)
    asked: list[httpx.Request] = []
    met = _met(tmp_path, asked, [])
    total, items = met.search("cypresses")
    assert not any(r.url.path.endswith("/search") for r in asked)
    assert {r.url.path.rsplit("/", 1)[1] for r in asked} == {"1", "2", "5"}
    assert total == 3 and sorted(i.id for i in items) == ["met:2", "met:5"]
    # Work 1 showed no picture: not found, not asked again.
    asked.clear()
    assert met.search("cypresses")[0] == 2 and len(asked) == 0


def test_too_few_found_asks_the_mets_search(tmp_path: Path) -> None:
    assert MET_LOCAL_MIN > 3
    _index(tmp_path)
    asked: list[httpx.Request] = []
    met = _met(tmp_path, asked, [3, 2, 77])
    total, items = met.search("cypresses")
    assert asked[0].url.path.endswith("/search") and total == 3
    # Of the Met's own results only the public-domain works are asked.
    assert [r.url.path.rsplit("/", 1)[1] for r in asked[1:]] == ["2"]
    assert [i.id for i in items] == ["met:2"]


def test_the_index_is_built_once_in_the_background(tmp_path: Path, monkeypatch: Any) -> None:
    started: list[Path] = []
    index = met_index._Index()
    monkeypatch.setattr(index, "_start", started.append)
    assert index.get(tmp_path) is None and started == [index_path(tmp_path)]
    _index(tmp_path)
    first = index.get(tmp_path)
    assert first is not None and index.get(tmp_path) is first and len(started) == 1
    old = time.time() - met_index.REFRESH_SECONDS - 10
    os.utime(index_path(tmp_path), (old, old))
    assert index.get(tmp_path) is not None and len(started) == 2  # read again behind


def test_a_failed_build_waits(tmp_path: Path, monkeypatch: Any) -> None:
    index = met_index._Index()

    def broken(path: Path, rows: Any) -> int:
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(met_index, "build", broken)
    monkeypatch.setattr(met_index, "_rows", lambda http, *args: iter(()))
    assert index.refresh(tmp_path) is False
    assert index.failed_at > 0 and not index._claim()


def test_an_artist_is_looked_for_in_the_artist_texts_only(tmp_path: Path) -> None:
    """Mateusz 2026-11-09: museums asked by their author field, not for
    works only naming the artist ("Cypresses, after van Gogh")."""
    rows = [*ROWS, _row(7, "Cypresses, after Vincent van Gogh")]
    path = index_path(tmp_path)
    path.parent.mkdir(parents=True)
    build(path, iter(rows))
    index = MetIndex(path)
    assert index.search("vincent van gogh")[0] == 3
    assert sorted(index.search(artist="Vincent van Gogh")[1]) == ["1", "2"]
    assert index.search("wheat", artist="Vincent van Gogh")[1] == ["1"]
