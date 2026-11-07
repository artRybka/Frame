"""Rests of the hosts that turned us away, after the NAS's log of 2026-11-07:
kept across restarts, longer for a wall that comes back, and a break for a
host answering only server errors."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from frame_server.library import loc_index
from frame_server.library.hosts import (
    FAIL_STREAK,
    FAILING_REST,
    PROBE_EVERY,
    REST,
    HostGuard,
    Resting,
)

CHALLENGE = httpx.Headers({"server": "cloudflare", "cf-mitigated": "challenge"})
MET = "https://collectionapi.metmuseum.org/public/collection/v1/objects/1"
LOC = "https://www.loc.gov/collections/prokudin-gorskii/?fo=json"
SMK = "https://api.smk.dk/api/v1/art/search/?keys=x"
MNK = "https://cdn-zbiory.mnk.pl/thumbs/1.jpg"


class Clocks:
    """A monotonic clock and a wall clock moving together."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.day = 1_800_000_000.0

    def tick(self, seconds: float) -> None:
        self.now += seconds
        self.day += seconds


def _guard(clocks: Clocks, pace: dict[str, float]) -> HostGuard:
    guard = HostGuard(pace)
    guard.clock = lambda: clocks.now
    guard.wall = lambda: clocks.day
    guard.sleep = clocks.tick
    return guard


def _client(guard: HostGuard, answer: list[httpx.Response], sent: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(str(request.url))
        resp = answer[0]
        return httpx.Response(resp.status_code, headers=resp.headers, content=resp.content)

    return httpx.Client(transport=httpx.MockTransport(handler), event_hooks=guard.hooks())


def test_a_rest_outlives_a_restart(tmp_path: Path) -> None:
    """Each update of the server asked the LoC at once, and each request
    during its block started the hour again (2026-11-07)."""
    clocks = Clocks()
    path = tmp_path / "rests.json"
    guard = _guard(clocks, {"www.loc.gov": 0.0})
    guard.keep_rests(path)
    sent: list[str] = []
    walled = [httpx.Response(403, headers=CHALLENGE)]
    with _client(guard, walled, sent) as http, pytest.raises(Resting):
        http.get(LOC)
    assert guard.resting("www.loc.gov") == pytest.approx(3600)
    # Ten minutes on the server starts again, with another monotonic clock.
    clocks.tick(600)
    clocks.now = 5.0
    again = _guard(clocks, {"www.loc.gov": 0.0})
    again.keep_rests(path)
    assert again.resting("www.loc.gov") == pytest.approx(3000)
    with _client(again, [httpx.Response(200)], sent) as http:
        with pytest.raises(Resting):
            http.get(LOC)
        # No request a minute to see either: the LoC's block is fixed.
        clocks.tick(PROBE_EVERY)
        with pytest.raises(Resting):
            http.get(LOC)
    assert len(sent) == 1


def test_a_wall_soon_after_the_last_rests_twice_as_long(tmp_path: Path) -> None:
    """The AIC let us in after each rest and turned us away again within
    minutes, eight times in a day: the rest started afresh every time."""
    clocks = Clocks()
    guard = _guard(clocks, {"api.smk.dk": 0.0})
    guard.keep_rests(tmp_path / "rests.json")
    answer = [httpx.Response(403, headers=CHALLENGE)]
    sent: list[str] = []
    with _client(guard, answer, sent) as http:
        with pytest.raises(Resting):
            http.get(SMK)
        assert guard.resting("api.smk.dk") == pytest.approx(REST)
        clocks.tick(REST + 1)
        answer[0] = httpx.Response(200)
        assert http.get(SMK).status_code == 200
        assert guard.resting("api.smk.dk") == 0
        # Walled again ten minutes later: half an hour.
        clocks.tick(600)
        answer[0] = httpx.Response(403, headers=CHALLENGE)
        with pytest.raises(Resting):
            http.get(SMK)
        assert guard.resting("api.smk.dk") == pytest.approx(2 * REST)
        # A wall a day later starts from a quarter of an hour again.
        clocks.tick(24 * 3600)
        answer[0] = httpx.Response(200)
        assert http.get(SMK).status_code == 200
        answer[0] = httpx.Response(403, headers=CHALLENGE)
        with pytest.raises(Resting):
            http.get(SMK)
        assert guard.resting("api.smk.dk") == pytest.approx(REST)


def test_a_host_answering_only_errors_gets_a_break() -> None:
    """MNK's picture server answered 502 to two requests in three and was
    asked on and on (2026-11-07)."""
    clocks = Clocks()
    guard = _guard(clocks, {})
    answer = [httpx.Response(502)]
    sent: list[str] = []
    with _client(guard, answer, sent) as http:
        for _ in range(FAIL_STREAK):
            assert http.get(MNK).status_code == 502
        with pytest.raises(Resting):
            http.get(MNK)
        assert len(sent) == FAIL_STREAK
        assert guard.resting("cdn-zbiory.mnk.pl") == pytest.approx(FAILING_REST)
        # A minute on one goes to see; it answers, and the break ends.
        clocks.tick(PROBE_EVERY)
        answer[0] = httpx.Response(200)
        assert http.get(MNK).status_code == 200
        assert guard.resting("cdn-zbiory.mnk.pl") == 0
        # Errors here and there don't add up to a break.
        for n in range(3 * FAIL_STREAK):
            answer[0] = httpx.Response(502 if n % 2 else 200)
            http.get(MNK)
        assert guard.resting("cdn-zbiory.mnk.pl") == 0


def test_the_loc_s_collections_are_built_only_at_night(tmp_path: Path, monkeypatch) -> None:
    """Built behind a draw, the index asked the LoC during its block twice
    on 2026-11-07."""
    built: list[Path] = []
    index = loc_index._Index()
    monkeypatch.setattr(index, "_build", built.append)
    assert index.get(tmp_path) is None
    assert built == []
    index.refresh(tmp_path)
    assert built == [loc_index.index_path(tmp_path)]
