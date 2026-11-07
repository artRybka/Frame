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
        with asking_for("szukaj", app=True):
            http.get("https://api.smk.dk/a")
            http.get("https://api.smk.dk/b")
        http.get("https://api.smk.dk/c")  # the background
        with urgently():
            http.get("https://api.smk.dk/d")
    today = next(iter(hosts.purposes().values()))
    assert today["api.smk.dk"] == {"szukaj": 2, BACKGROUND: 1, APP: 1}
    smk = next(r for r in hosts.by_source() if r["name"] == "Statens Museum for Kunst")
    assert smk["why_today"] == smk["why_week"] == {"szukaj": 2, BACKGROUND: 1, APP: 1}
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
    with ThreadPoolExecutor(1) as pool, asking_for("odkrywaj", app=True):
        assert pool.submit(as_asked(purpose)).result() == "odkrywaj"
    assert purpose() == BACKGROUND


def test_the_app_s_requests_are_named_by_their_address() -> None:
    assert purpose_of("/api/themes/winter/stream") == "odkrywaj"
    assert purpose_of("/api/discover/search/stream") == "szukaj"
    assert purpose_of("/api/library/items/met:1/thumb") == "miniatury"
    assert purpose_of("/api/library/items/met:1") == "karta"
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
        with asking_for("odkrywaj", app=True):
            http.get("https://api.smk.dk/app")
        with urgently():
            http.get("https://api.smk.dk/urgent")
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
