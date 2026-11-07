"""Local lists asked for again only as much as needed (Mateusz 2026-11-07:
"może da się to robić tylko addytywnie"): the Met's file only when it
changed, the Louvre's Commons sizes only of new files."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from frame_server.library import louvre, met_index, nga
from frame_server.library.met_index import MetIndex, build, etag_path, index_path

CSV_HEAD = (
    "Object ID,Is Public Domain,Is Highlight,Department,Title,Artist Display Name,"
    "Object Begin Date,Object End Date,Classification\n"
)
ETAG = '"7adc37e4"'


def _csv(*titles: str) -> str:
    return CSV_HEAD + "".join(
        f"{n},True,False,European Paintings,{t},,1880,1890,Paintings\n"
        for n, t in enumerate(titles, 1)
    )


def _met_client(monkeypatch: pytest.MonkeyPatch, body: list[str], asked: list[str]) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(request.headers.get("if-none-match", ""))
        if request.headers.get("if-none-match") == ETAG:
            return httpx.Response(304)
        return httpx.Response(200, headers={"etag": ETAG}, text=body[0])

    import frame_server.library.museums as museums

    monkeypatch.setattr(
        museums, "client", lambda: httpx.Client(transport=httpx.MockTransport(answer))
    )


def test_the_met_file_is_read_again_only_when_it_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = [_csv("Cypresses", "Wheat Field")]
    asked: list[str] = []
    _met_client(monkeypatch, body, asked)
    index = met_index._Index()
    assert index.refresh(tmp_path) is True
    path = index_path(tmp_path)
    assert etag_path(path).read_text() == ETAG and asked == [""]
    assert MetIndex(path).search("cypresses")[0] == 1

    # Three months on, the same file: nothing read, the index fresh again.
    old = time.time() - met_index.REFRESH_SECONDS
    os.utime(path, (old, old))
    assert index.refresh(tmp_path) is True
    assert asked == ["", ETAG]
    assert time.time() - path.stat().st_mtime < 60
    assert not path.with_suffix(".tmp").exists()
    assert index.refresh(tmp_path) is False  # fresh: not even asked
    assert len(asked) == 2

    # A changed file is read whole.
    body[0] = _csv("Cypresses", "Wheat Field", "Irises")
    etag_path(path).write_text('"older"')
    os.utime(path, (old, old))
    assert index.refresh(tmp_path) is True
    assert MetIndex(path).search("irises")[0] == 1


def test_works_without_a_picture_stay_marked_after_a_rebuild(tmp_path: Path) -> None:
    path = index_path(tmp_path)
    path.parent.mkdir(parents=True)
    rows: list[dict[str, Any]] = [
        {
            "Object ID": str(n),
            "Is Public Domain": "True",
            "Department": "European Paintings",
            "Title": "Cypresses",
        }
        for n in (1, 2, 3)
    ]
    assert build(path, iter(rows)) == 3
    MetIndex(path).no_picture("2")
    assert build(path, iter(rows)) == 3
    assert MetIndex(path).search("cypresses") == (2, ["1", "3"])


def test_the_lists_are_asked_for_less_often() -> None:
    assert met_index.REFRESH_SECONDS == 90 * 24 * 3600
    assert nga.REFRESH_SECONDS == 30 * 24 * 3600
    assert louvre.SIZES_AGAIN >= 180 * 24 * 3600


SPARQL_HEAD = "ark,work,workLabel,file,creatorLabel,died\n"


def _wikidata(*rows: tuple[str, str]) -> str:
    return SPARQL_HEAD + "".join(
        f"{ark},http://www.wikidata.org/entity/Q{ark},Work {ark},"
        f"http://commons.wikimedia.org/wiki/Special:FilePath/{file},Someone,\n"
        for ark, file in rows
    )


def test_the_louvre_asks_commons_only_about_new_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listed = [_wikidata(("1", "A.jpg"), ("2", "B.jpg"))]
    sized: list[list[str]] = []

    def sizes(http: httpx.Client, files: list[str], sleep: Any = None) -> dict[str, int]:
        sized.append(files)
        return {f: 900 for f in files if f != "B.jpg"}  # B is gone from Commons

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.host == "query.wikidata.org":
            return httpx.Response(200, text=listed[0])
        return httpx.Response(404)

    monkeypatch.setattr(louvre, "commons_sizes", sizes)
    monkeypatch.setattr(louvre, "look", lambda http, ark: None)
    path = louvre.list_path(tmp_path)
    with httpx.Client(transport=httpx.MockTransport(answer)) as http:
        louvre.build(path, http)
        assert sized == [["A.jpg", "B.jpg"]]
        listed[0] = _wikidata(("1", "A.jpg"), ("2", "B.jpg"), ("3", "C.jpg"))
        louvre.build(path, http)
        assert sized[1:] == [["C.jpg"]]  # neither A nor the missing B again
        data = louvre._read(path)
        assert data["sizes"] == {"A.jpg": 900, "B.jpg": 0, "C.jpg": 900}
        assert data["works"]["3"]["commons"] == 900
        # Twice a year every file is asked about again.
        data["sized_at"] -= louvre.SIZES_AGAIN
        louvre._write(path, data)
        louvre.build(path, http)
        assert sized[2:] == [["A.jpg", "B.jpg", "C.jpg"]]
