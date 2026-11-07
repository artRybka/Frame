"""One policy per source (library/policy.py): paces, limits, quotas with a
share kept for what the owner waits for, and the day's tally of requests."""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

from frame_server.library import policy
from frame_server.library.hosts import (
    LIMITS,
    LONG_BLOCKS,
    PACE,
    WIKIMEDIA,
    WIKIMEDIA_MEDIA,
    HostGuard,
    OverBudget,
    Resting,
    guard,
    urgently,
)
from frame_server.library.images import HOST_LIMITS
from frame_server.library.policy import Budget

PARIS = "https://apicollections.parismusees.paris.fr/graphql"


def test_the_tables_keep_the_numbers_the_sources_ask_for() -> None:
    """The numbers of 1.115.0's tables, now read from one place."""
    assert PACE["www.artic.edu"] == 1.0
    assert PACE["api.artic.edu"] == 1.2
    assert PACE["collectionapi.metmuseum.org"] == 0.5
    assert PACE[WIKIMEDIA] == 0.25
    assert PACE["www.loc.gov"] >= 3.0 and PACE["tile.loc.gov"] >= 0.4
    assert PACE["nominatim.openstreetmap.org"] == 1.0
    assert LIMITS[WIKIMEDIA] == 1 and LIMITS[WIKIMEDIA_MEDIA] == 2
    assert LIMITS["api.artic.edu"] == LIMITS["www.artic.edu"] == 1
    assert LIMITS["collectionapi.metmuseum.org"] == 1
    assert LONG_BLOCKS == {"www.loc.gov": 3600.0, "collectionapi.metmuseum.org": 1800.0}
    assert policy.BUDGETS["collectionapi.metmuseum.org"].count == 1500
    assert PACE["lux.collections.yale.edu"] == PACE["manifests.collections.yale.edu"] == 0.5
    assert "api.artic.edu" in policy.WALL_403
    assert HOST_LIMITS == {
        "upload.wikimedia.org": 2,
        "thumb.wikimedia.org": 2,
        "commons.wikimedia.org": 2,
        "www.artic.edu": 1,
    }
    # The Rijksmuseum and Yale ask a request a work: limits of their own.
    assert LIMITS["id.rijksmuseum.nl"] == 2
    assert LIMITS["manifests.collections.yale.edu"] == 4


def test_every_source_says_where_its_rules_are_or_that_it_has_none() -> None:
    names = [s.name for s in policy.SOURCES]
    assert len(names) == len(set(names))
    hosts = [h for s in policy.SOURCES for h in s.hosts]
    assert len(hosts) == len(set(hosts))  # one source's rules per host
    for source in policy.SOURCES:
        assert source.rules == "" or source.rules.startswith("https://")
        assert len(source.checked) == 10
    assert policy.source_of("www.loc.gov") is not None
    assert policy.source_of("example.org") is None


def test_the_shared_guard_keeps_quotas_and_a_limit_for_every_host() -> None:
    assert guard.default_limit == policy.DEFAULT_LIMIT
    # Never fewer than the downloads took before (four, two more urgently).
    assert policy.DEFAULT_LIMIT >= policy.DEFAULT_IMAGES + policy.URGENT_EXTRA
    assert guard.budgets["apicollections.parismusees.paris.fr"].count == 1000
    assert guard.budgets["api.si.edu"].window == policy.HOUR
    assert guard.budgets["api.openverse.org"].anonymous_only


def test_a_host_without_a_limit_of_its_own_gets_the_default() -> None:
    hosts = HostGuard({}, {}, default_limit=2)
    under_way = most = 0
    lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal under_way, most
        with lock:
            under_way += 1
            most = max(most, under_way)
        time.sleep(0.05)
        with lock:
            under_way -= 1
        return httpx.Response(200, json={})

    with (
        hosts.client(transport=httpx.MockTransport(handler)) as http,
        ThreadPoolExecutor(6) as pool,
    ):
        codes = list(pool.map(lambda _: http.get("https://api.smk.dk/x").status_code, range(8)))
    assert codes == [200] * 8 and most == 2


class Wall:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


def _budgeted(budget: Budget) -> tuple[HostGuard, Wall, list[str]]:
    hosts = HostGuard({}, {}, budgets={"apicollections.parismusees.paris.fr": budget})
    wall = Wall()
    hosts.wall = wall
    return hosts, wall, []


def _client(hosts: HostGuard, sent: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(str(request.url))
        return httpx.Response(200, json={})

    return hosts.client(transport=httpx.MockTransport(handler))


def test_the_background_leaves_the_owner_a_share_of_the_quota() -> None:
    hosts, wall, sent = _budgeted(Budget(10, policy.DAY, reserve=0.4))
    with _client(hosts, sent) as http:
        for _ in range(6):
            http.post(PARIS)
        with pytest.raises(OverBudget):
            http.post(PARIS)  # the background's six are spent
        assert len(sent) == 6
        with urgently():
            for _ in range(4):
                http.post(PARIS)
            with pytest.raises(OverBudget):
                http.post(PARIS)  # the whole quota
        assert len(sent) == 10
        assert hosts.spent("apicollections.parismusees.paris.fr") == 10
        assert hosts.tally()["apicollections.parismusees.paris.fr"]["refused"] == 2
        # A day on, the oldest fall out of the window.
        wall.now += policy.DAY + 1
        http.post(PARIS)
    assert len(sent) == 11


def test_an_over_quota_host_counts_as_resting() -> None:
    """Callers already wait out a resting host (Szukaj says the museum did
    not answer, thumbnails answer 503): a spent quota is one more such."""
    assert issubclass(OverBudget, Resting)


def test_requests_with_credentials_do_not_count_against_an_anonymous_quota() -> None:
    hosts = HostGuard(
        {}, {}, budgets={"api.openverse.org": Budget(1, policy.DAY, 0, anonymous_only=True)}
    )
    sent: list[str] = []
    url = "https://api.openverse.org/v1/images/"
    with _client(hosts, sent) as http:
        for _ in range(3):
            http.get(url, headers={"Authorization": "Bearer x"})
        http.get(url)
        with pytest.raises(OverBudget):
            http.get(url)
    assert len(sent) == 4


def test_quotas_outlive_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "hosts" / "quotas.json"
    hosts, wall, sent = _budgeted(Budget(3, policy.HOUR, reserve=0))
    hosts.keep_budgets(path)
    with _client(hosts, sent) as http:
        http.post(PARIS)
        http.post(PARIS)
    saved = json.loads(path.read_text())
    assert len(saved["apicollections.parismusees.paris.fr"]) >= 1
    path.write_text(json.dumps({"apicollections.parismusees.paris.fr": [wall.now] * 3}))
    again, _, sent_again = _budgeted(Budget(3, policy.HOUR, reserve=0))
    again.wall = wall
    again.keep_budgets(path)
    with _client(again, sent_again) as http, pytest.raises(OverBudget):
        http.post(PARIS)
    assert sent_again == []
    # Hours later the saved ones no longer count.
    wall.now += policy.HOUR + 1
    later, _, _ = _budgeted(Budget(3, policy.HOUR, reserve=0))
    later.wall = wall
    later.keep_budgets(path)
    assert later.spent("apicollections.parismusees.paris.fr") == 0


def test_the_day_s_tally_is_logged_when_the_day_turns(caplog: pytest.LogCaptureFixture) -> None:
    hosts = HostGuard({}, {})
    wall = Wall()
    hosts.wall = wall
    answers = iter(
        [
            httpx.Response(200, headers={"content-length": "2000000"}, content=b""),
            httpx.Response(429),
            httpx.Response(200),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(answers)

    with hosts.client(transport=httpx.MockTransport(handler)) as http:
        http.get("https://api.smk.dk/a")
        http.get("https://api.smk.dk/b")
        assert hosts.tally()["api.smk.dk"] == {
            "sent": 2,
            "walled": 0,
            "throttled": 1,
            "failed": 0,
            "refused": 0,
            "bytes": 2_000_000,
        }
        wall.now += 86400
        with caplog.at_level("INFO", logger="frame_server.library.hosts"):
            http.get("https://api.smk.dk/c")
    told = [r.getMessage() for r in caplog.records if r.getMessage().startswith("hosts ")]
    assert len(told) == 1 and "api.smk.dk 2 sent" in told[0] and "1 throttled" in told[0]
    assert hosts.tally()["api.smk.dk"]["sent"] == 1


def test_every_host_of_a_museum_counts_for_its_source() -> None:
    owner = policy.owner_of
    assert owner("api.artic.edu").name == "Art Institute of Chicago"  # type: ignore[union-attr]
    assert owner("iiif.micr.io").name == "Rijksmuseum"  # type: ignore[union-attr]
    assert owner("pl.wikipedia.org").name == "Wikimedia"  # type: ignore[union-attr]
    assert owner("www.wikidata.org").name == "Wikimedia"  # type: ignore[union-attr]
    assert owner("media.githubusercontent.com").name.startswith("The Met")  # type: ignore[union-attr]
    assert owner("raw.githubusercontent.com").name == "National Gallery of Art"  # type: ignore[union-attr]
    assert owner("framemark.vam.ac.uk").name == "Victoria and Albert Museum"  # type: ignore[union-attr]
    assert owner("live.staticflickr.com") is None
    assert owner("notmetmuseum.org") is None


def test_requests_and_refusals_by_source_over_a_week(tmp_path: Path) -> None:
    """Konfiguracja → Diagnostyka (Mateusz 2026-11-07): how many requests
    went to each source lately, and how many were refused."""
    path = tmp_path / "hosts" / "tally.json"
    hosts = HostGuard(
        {"api.smk.dk": 0.0},
        {},
        budgets={"apicollections.parismusees.paris.fr": Budget(2, policy.DAY, 0)},
    )
    wall = Wall()
    hosts.wall = wall
    hosts.keep_tally(path)
    codes = {"/wall": 403, "/busy": 429, "/down": 503, "/gone": 404}

    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"cf-mitigated": "challenge"} if request.url.path == "/wall" else {}
        return httpx.Response(codes.get(request.url.path, 200), headers=headers)

    with hosts.client(transport=httpx.MockTransport(handler)) as http:
        http.get("https://api.smk.dk/a")
        wall.now += policy.DAY  # yesterday's two, today's the rest
        http.get("https://iiif.micr.io/x/full/max/0/default.jpg")
        http.get("https://data.rijksmuseum.nl/busy")
        http.get("https://data.rijksmuseum.nl/down")
        http.get("https://data.rijksmuseum.nl/gone")
        http.get("https://live.staticflickr.com/1.jpg")
        for _ in range(2):
            http.post(PARIS)
        with pytest.raises(OverBudget):
            http.post(PARIS)
        with pytest.raises(Resting):
            http.get("https://api.smk.dk/wall")
    rows = {r["name"]: r for r in hosts.by_source()}
    rijks = rows["Rijksmuseum"]
    assert rijks["today"]["sent"] == rijks["week"]["sent"] == 4
    assert rijks["today"]["throttled"] == 1 and rijks["today"]["failed"] == 1
    smk = rows["Statens Museum for Kunst"]
    assert smk["week"]["sent"] == 2 and smk["today"]["sent"] == 1
    assert smk["today"]["walled"] == 1 and smk["resting"] > 0
    paris = rows["Paris Musées"]
    assert paris["today"]["refused"] == 1
    assert paris["quota"] == {"spent": 2, "of": 2, "background": 2, "hours": 24.0}
    assert rows[None]["week"]["sent"] == 1  # pictures of no source, last
    assert hosts.by_source()[-1]["name"] is None
    assert len(rows) == len(policy.SOURCES) + 1  # the quiet ones too

    # Written down a minute on; the week outlives a restart, older days go.
    wall.now += 61
    with hosts.client(transport=httpx.MockTransport(handler)) as http:
        http.get("https://api.vam.ac.uk/a")
    saved = json.loads(path.read_text())
    saved["2020-01-01"] = {"api.smk.dk": [9] * 6}
    path.write_text(json.dumps(saved))
    again = HostGuard({}, {})
    again.wall = wall
    again.keep_tally(path)
    kept = {r["name"]: r for r in again.by_source()}
    assert kept["Rijksmuseum"]["week"]["sent"] == 4
    assert kept["Statens Museum for Kunst"]["week"]["sent"] == 2
    assert kept["Victoria and Albert Museum"]["today"]["sent"] == 1
    assert kept["Paris Musées"]["today"]["refused"] == 1
    assert "2020-01-01" not in again.days()  # long before the last seven


def test_the_tally_is_written_down_and_a_week_kept(tmp_path: Path) -> None:
    path = tmp_path / "hosts" / "tally.json"
    hosts = HostGuard({}, {})
    wall = Wall()
    hosts.wall = wall
    hosts.keep_tally(path)
    with hosts.client(transport=httpx.MockTransport(lambda r: httpx.Response(200))) as http:
        for _ in range(10):
            wall.now += policy.DAY
            http.get("https://api.smk.dk/a")
    days = hosts.days()
    assert len(days) == 7 and all(d["api.smk.dk"]["sent"] == 1 for d in days.values())
    saved = json.loads(path.read_text())
    assert len(saved) <= 7 and min(saved) >= min(days)


def test_the_owner_sees_requests_by_source(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from frame_server.config import Settings
    from frame_server.web import create_app

    settings = Settings(data_dir=tmp_path, seed_library=False, scheduler=False, api_token="secret")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/diagnostics/sources").status_code == 401
        answer = client.get(
            "/api/diagnostics/sources", headers={"Authorization": "Bearer secret"}
        ).json()
    assert answer["days"] == 7
    names = [s["name"] for s in answer["sources"]]
    assert "Rijksmuseum" in names and "Louvre" in names
    first = answer["sources"][0]
    assert set(first) == {"name", "today", "week", "quota", "resting", "why_today", "why_week"}
    assert set(first["today"]) == {"sent", "walled", "throttled", "failed", "refused", "bytes"}
