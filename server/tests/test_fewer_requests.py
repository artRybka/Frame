"""Fewer requests to the museums (Mateusz 2026-11-07, after the LoC and the
Met turned the home address away): what each request was for, a quiet start,
one request for a page several want, the log kept over a restart."""

from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

from frame_server import logbuffer
from frame_server.library import policy
from frame_server.library.hosts import (
    APP,
    BACKGROUND,
    HostGuard,
    as_asked,
    asking_for,
    purpose,
    urgently,
    walled,
)
from frame_server.web.purposes import purpose_of


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200)


def test_requests_are_counted_by_what_they_were_for(tmp_path: Path) -> None:
    hosts = HostGuard({}, {})
    hosts.keep_tally(tmp_path / "hosts" / "tally.json")
    with hosts.client(transport=httpx.MockTransport(_ok)) as http:
        with asking_for("Szukaj", app=True):
            http.get("https://api.smk.dk/a")
            http.get("https://api.smk.dk/b")
        http.get("https://api.smk.dk/c")  # the background
        with urgently():
            http.get("https://api.smk.dk/d")
    today = next(iter(hosts.purposes().values()))
    assert today["api.smk.dk"] == {"Szukaj": 2, BACKGROUND: 1, APP: 1}
    smk = next(r for r in hosts.by_source() if r["name"] == "Statens Museum for Kunst")
    assert smk["why_today"] == smk["why_week"] == {"Szukaj": 2, BACKGROUND: 1, APP: 1}
    # Written down with the tally, read back after a restart.
    hosts.keep_tally(tmp_path / "hosts" / "tally.json")
    hosts._count("api.smk.dk", sent=1, why="noc")
    hosts._tally_saved = 0.0
    hosts._count("api.smk.dk", sent=1, why="noc")
    saved = json.loads((tmp_path / "hosts" / "purposes.json").read_text())
    assert next(iter(saved.values()))["api.smk.dk"]["noc"] == 2
    again = HostGuard({}, {})
    again.keep_tally(tmp_path / "hosts" / "tally.json")
    assert next(iter(again.purposes().values()))["api.smk.dk"]["noc"] == 2


def test_the_server_s_own_threads_say_what_they_ask_for() -> None:
    found: list[str] = []

    def look() -> None:
        found.append(purpose())

    for name in ("night", "searched", "search-page", "sharper", "something"):
        thread = threading.Thread(target=look, name=name)
        thread.start()
        thread.join()
    assert found == ["noc", "katalog", "odświeżanie", "kopie", BACKGROUND]


def test_the_purpose_follows_work_into_worker_threads() -> None:
    with ThreadPoolExecutor(1) as pool, asking_for("Odkrywaj", app=True):
        assert pool.submit(as_asked(purpose)).result() == "Odkrywaj"
    assert purpose() == BACKGROUND


def test_the_app_s_requests_are_named_by_their_address() -> None:
    assert purpose_of("/api/themes/winter/stream") == "Odkrywaj"
    assert purpose_of("/api/discover/search/stream") == "Szukaj"
    assert purpose_of("/api/library/items/met:1/thumb") == "miniatury"
    assert purpose_of("/api/library/items/met:1") == "karta dzieła"
    assert purpose_of("/api/study/met:1") == "studium"
    assert purpose_of("/panel/next") == "ramka"
    assert purpose_of("/api/settings") is None


def test_the_background_waits_out_a_quiet_start() -> None:
    """486 requests in the nine minutes after an update (2026-11-07)."""
    hosts = HostGuard({}, {})
    clock = Clock()
    hosts.clock = lambda: clock.now
    hosts.sleep = clock.sleep
    hosts.calm(600.0)
    with hosts.client(transport=httpx.MockTransport(_ok)) as http:
        with asking_for("Odkrywaj", app=True):
            http.get("https://api.smk.dk/app")
        with urgently():
            http.get("https://api.smk.dk/urgent")
        with asking_for("kopie"):  # the app's card waits for a sharper copy
            http.get("https://api.smk.dk/copy")
        assert clock.slept == []  # what the app waits for goes at once
        http.get("https://api.smk.dk/background")
    assert sum(clock.slept) == pytest.approx(600.0)
    hosts.calm(0.0)
    clock.slept.clear()
    with hosts.client(transport=httpx.MockTransport(_ok)) as http:
        http.get("https://api.smk.dk/later")
    assert clock.slept == []


def test_the_aic_api_s_plain_403_is_its_wall() -> None:
    """Nine plain 403s from api.artic.edu on 2026-11-07, and it was asked on."""
    request = httpx.Request("POST", "https://api.artic.edu/api/v1/artworks/search")
    assert walled(httpx.Response(403, request=request))
    picture = httpx.Request("GET", "https://www.artic.edu/iiif/2/x/full/843,/0/default.jpg")
    assert not walled(httpx.Response(403, request=picture))  # a picture asked too wide


def test_the_met_is_asked_gently_and_left_alone_when_it_walls() -> None:
    met = "collectionapi.metmuseum.org"
    assert policy.PACE[met] == 0.5 and policy.LIMITS[met] == 1
    assert policy.LONG_BLOCKS[met] == 1800.0
    assert policy.BUDGETS[met].count == 1500
    hosts = HostGuard({met: 0.0}, {})
    clock = Clock()
    hosts.clock = lambda: clock.now
    hosts.sleep = clock.sleep
    sent: list[str] = []

    def wall(request: httpx.Request) -> httpx.Response:
        sent.append(str(request.url))
        return httpx.Response(403, headers={"x-cdn": "Imperva"})

    with hosts.client(transport=httpx.MockTransport(wall)) as http:
        with pytest.raises(httpx.TransportError):
            http.get(f"https://{met}/public/collection/v1/objects/1")
        clock.now += 120  # no probe a minute on
        with pytest.raises(httpx.TransportError):
            http.get(f"https://{met}/public/collection/v1/objects/2")
    assert len(sent) == 1
    assert hosts.resting(met) == pytest.approx(1800 - 120)


def test_a_page_several_want_at_once_is_asked_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import frame_server.library.importer as importer_module
    from frame_server.library import Library
    from frame_server.library.importer import Importer
    from frame_server.library.models import Item, ItemKind
    from frame_server.library.museums import Access

    calls: list[int] = []
    started = threading.Event()
    release = threading.Event()

    class Slow:
        def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
            calls.append(page)
            started.set()
            release.wait(5)
            item = Item(
                id="smk:1",
                source="smk",
                source_id="1",
                kind=ItemKind.ARTWORK,
                title="One",
                image_url="https://example.org/1.jpg",
                thumb_url="https://example.org/1t.jpg",
            )
            return 1, [item]

    monkeypatch.setattr(importer_module, "museum", lambda key, http, access: Slow())
    importer = Importer(
        Library(tmp_path / "lib.db"),
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        access=lambda: Access(data_dir=tmp_path),
    )
    monkeypatch.setattr(importer, "without_grey", lambda items: items)
    memo = ("smk", "monet", 24, 1, "any", False)
    with ThreadPoolExecutor(3) as pool:
        first = pool.submit(importer._ask, memo)
        assert started.wait(5)
        others = [pool.submit(importer._ask, memo) for _ in range(2)]
        time.sleep(0.1)
        release.set()
        answers = [f.result(5) for f in [first, *others]]
    assert calls == [1]
    assert all(total == 1 and [i.id for i in items] == ["smk:1"] for total, items in answers)


def test_the_log_is_kept_on_disk_and_read_back_after_a_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "logs"
    folder.mkdir()
    (folder / logbuffer.FILE).write_text(
        "2026-11-07 07:35:01,000 WARNING frame_server.library.hosts: www.loc.gov turned us away\n"
        "2026-11-07 07:35:02,000 ERROR x: failed\nTraceback (most recent call last):\n  boom\n"
    )
    buffer = logbuffer.LogBuffer()
    monkeypatch.setattr(logbuffer, "_buffer", buffer)
    monkeypatch.setattr(logbuffer, "_file", None)
    root = logging.getLogger()
    try:
        logbuffer.keep_on_disk(folder)
        logging.getLogger("frame_server.test").warning("after the start")
        lines = buffer.lines(10)
        assert "www.loc.gov turned us away" in lines[0]
        assert lines[1].endswith("boom")
        assert "after the start" in lines[-1]
        assert logbuffer._file is not None
        logbuffer._file.flush()
        assert "after the start" in (folder / logbuffer.FILE).read_text()
    finally:
        for logger in (root, logging.getLogger("uvicorn.error")):
            for handler in (buffer, logbuffer._file):
                if handler is not None and handler in logger.handlers:
                    logger.removeHandler(handler)
        if logbuffer._file is not None:
            logbuffer._file.close()


def test_wikidata_s_facts_outlive_an_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """428 Wikidata requests on 2026-11-07: every update asked them again."""
    from frame_server.library.models import Item
    from frame_server.library.records import Records
    from frame_server.library.wikidata import Facts, Wikidata

    asked: list[str] = []

    def find(http: httpx.Client, prop: str, value: str) -> str | None:
        asked.append(value)
        return None if value == "2" else f"Q{value}"

    monkeypatch.setattr(Wikidata, "_find", staticmethod(find))
    monkeypatch.setattr(
        Wikidata,
        "_facts",
        staticmethod(
            lambda http, qid: Facts(qid=qid, title_pl="Słoneczniki", depicts_pl=("kwiat",))
        ),
    )
    kept = Records(tmp_path / "records.sqlite")
    one = Item(id="met:1", source="met", source_id="1", title="Sunflowers")
    none = Item(id="met:2", source="met", source_id="2", title="Nothing")
    first = Wikidata(kept)
    facts = first.facts(None, one)  # type: ignore[arg-type]
    assert facts == Facts(qid="Q1", title_pl="Słoneczniki", depicts_pl=("kwiat",))
    assert first.facts(None, none) is None  # type: ignore[arg-type]
    again = Wikidata(kept)  # after an update
    assert again.facts(None, one) == facts  # type: ignore[arg-type]
    assert again.facts(None, none) is None  # type: ignore[arg-type]
    assert asked == ["1", "2"]


def test_a_kept_thumbnail_is_sent_without_asking_the_museum(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from frame_server.config import Settings
    from frame_server.web import create_app

    settings = Settings(data_dir=tmp_path, seed_library=False, scheduler=False, api_token="secret")
    app = create_app(settings)
    with TestClient(app) as client:
        thumbs = tmp_path / "library" / "thumbs"
        thumbs.mkdir(parents=True, exist_ok=True)
        (thumbs / "met_436535.jpg").write_bytes(b"\xff\xd8kept\xff\xd9")
        answer = client.get(
            "/api/library/items/met:436535/thumb", headers={"Authorization": "Bearer secret"}
        )
    assert answer.status_code == 200 and answer.content == b"\xff\xd8kept\xff\xd9"


def test_the_background_waits_while_the_app_is_in_use_and_goes_at_half_pace() -> None:
    hosts = HostGuard({"api.smk.dk": 1.0}, {})
    hosts.background_slower = 2.0
    clock = Clock()
    hosts.clock = lambda: clock.now
    hosts.sleep = clock.sleep
    in_use = [True, True, False]
    hosts.app_in_use = lambda: in_use.pop(0) if in_use else False
    with hosts.client(transport=httpx.MockTransport(_ok)) as http:
        http.get("https://api.smk.dk/a")  # waits twice, then goes
        assert clock.slept == [10.0, 10.0]
        clock.slept.clear()
        http.get("https://api.smk.dk/b")  # two seconds after, not one
        assert clock.slept == [pytest.approx(2.0)]
        clock.slept.clear()
        with asking_for("Szukaj", app=True):
            hosts.app_in_use = lambda: True
            http.get("https://api.smk.dk/c")  # the app: its own pace, no waiting
        assert clock.slept == [pytest.approx(2.0)]  # what is left of b's pause


def _loc_result(number: str, title: str, year: str, collection: str = "") -> dict[str, object]:
    return {
        "number_lccn": [number],
        "title": title,
        "date": year,
        "image_url": [
            f"https://tile.loc.gov/storage-services/service/pnp/prok/0{number}/0{number}r.jpg",
            f"https://tile.loc.gov/storage-services/service/pnp/prok/0{number}/0{number}v.jpg",
        ],
        "item": {
            "rights_advisory": ["No known restrictions on publication."],
            "medium": ["1 photographic print"],
            "created_published_date": year,
            "subject_headings": [f"{collection} subject"],
            "contributor_names": ["Prokudin-Gorskiĭ, Sergeĭ Mikhaĭlovich, 1863-1944, photographer"],
        },
    }


def test_the_loc_s_collections_are_read_at_home(tmp_path: Path) -> None:
    """www.loc.gov blocked the home address two mornings running."""
    from frame_server.library import loc_index
    from frame_server.library.loc import LibraryOfCongress
    from frame_server.library.museums import Access, Discovery

    path = loc_index.index_path(tmp_path)
    path.parent.mkdir(parents=True)
    count = loc_index.build(
        path,
        {
            "prokudin-gorskii": iter(
                [
                    _loc_result("2018679001", "Alim Khan, Emir of Bukhara", "1911"),
                    _loc_result("2018679002", "Study of a peasant woman", "1909"),
                ]
            ),
            "photochrom-prints": iter([_loc_result("2008678001", "Venice, Grand Canal", "1890")]),
        },
    )
    assert count == 3
    asked: list[str] = []

    def nothing(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return httpx.Response(500)

    http = httpx.Client(transport=httpx.MockTransport(nothing))
    loc = LibraryOfCongress(http, access=Access(data_dir=tmp_path))
    total, items = loc.search("collection:prokudin-gorskii")
    assert total == 2 and [i.source_id for i in items] == ["2018679001", "2018679002"]
    total, items = loc.search("collection:prokudin-gorskii emir")
    assert total == 1 and items[0].title.startswith("Alim Khan")
    assert items[0].artist == "Sergeĭ Mikhaĭlovich Prokudin-Gorskiĭ"
    found = loc.fetch("2008678001")
    assert found is not None and found.year == 1890
    # A draw from the background: the kept collections only.
    total, items = loc.discover(Discovery(kind="photograph", year_to=1900), limit=10, page=2)
    assert [i.source_id for i in items] == ["2008678001"]
    # Words over all its photographs: the LoC's own search, for the app only.
    with pytest.raises(httpx.TransportError):
        loc.search("Dorothea Lange")
    assert asked == []
    with urgently(), pytest.raises(httpx.HTTPStatusError):
        loc.search("Dorothea Lange")
    assert len(asked) == 1
