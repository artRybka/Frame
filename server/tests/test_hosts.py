"""Museum hosts: requests spaced out, a host whose bot wall turned us away
left alone for a while (the AIC's Cloudflare, the Met's Imperva)."""

from __future__ import annotations

import itertools
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

from frame_server.library.hosts import (
    REST,
    HostGuard,
    Resting,
    as_asked,
    is_urgent,
    urgently,
    walled,
)
from frame_server.library.images import ImageCache
from frame_server.library.models import Item, ItemKind
from frame_server.library.museums import ArtInstituteChicago, MetropolitanMuseum

AIC_SEARCH = "https://api.artic.edu/api/v1/artworks/search"
MET_OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects/1"

CHALLENGE = httpx.Headers(
    {"server": "cloudflare", "cf-mitigated": "challenge", "content-type": "text/html"}
)
IMPERVA = httpx.Headers({"x-cdn": "Imperva", "x-iinfo": "48-1 NNNN", "content-type": "text/html"})
#: The AIC's IIIF server (behind Cloudflare too) on a picture asked too wide.
TOO_WIDE = httpx.Headers({"server": "cloudflare", "content-type": "text/plain"})


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def _guard(pace: dict[str, float] | None = None) -> tuple[HostGuard, Clock]:
    guard = HostGuard(pace or {"api.artic.edu": 0.0, "collectionapi.metmuseum.org": 0.0})
    clock = Clock()
    guard.clock = lambda: clock.now
    guard.sleep = clock.sleep
    return guard, clock


def _client(guard: HostGuard, answer: list[httpx.Response], sent: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(str(request.url))
        resp = answer[0]
        return httpx.Response(resp.status_code, headers=resp.headers, content=resp.content)

    return httpx.Client(transport=httpx.MockTransport(handler), event_hooks=guard.hooks())


def test_bot_walls_are_told_from_the_servers_own_refusals() -> None:
    assert walled(httpx.Response(403, headers=CHALLENGE))
    assert walled(httpx.Response(403, headers=IMPERVA))
    assert not walled(httpx.Response(403, headers=TOO_WIDE, text="scales in excess of 100%"))
    assert not walled(httpx.Response(200, headers=IMPERVA))


def test_walled_host_is_left_alone_for_a_while() -> None:
    guard, clock = _guard()
    answer = [httpx.Response(403, headers=CHALLENGE)]
    sent: list[str] = []
    with _client(guard, answer, sent) as http:
        aic = ArtInstituteChicago(http)
        with pytest.raises(Resting):
            aic.search("monet")
        assert len(sent) == 1
        # Every museum query fails at once, without asking the wall again.
        for _ in range(5):
            with pytest.raises(Resting):
                aic.search("monet")
        assert len(sent) == 1
        # The Met is another host: still asked.
        with pytest.raises(Resting):
            MetropolitanMuseum(http).fetch("1")
        assert sent[-1] == MET_OBJECT
        # Still walled after the rest: twice as long a rest.
        clock.now += REST + 1
        with pytest.raises(Resting):
            aic.search("monet")
        assert len(sent) == 3
        assert guard.resting("api.artic.edu") == pytest.approx(2 * REST)
        # It answers again: forgotten.
        clock.now += 2 * REST + 1
        answer[0] = httpx.Response(200, json={"data": [], "pagination": {"total": 0}})
        assert aic.search("monet") == (0, [])
        assert guard.resting("api.artic.edu") == 0


def test_server_refusal_does_not_rest_the_host() -> None:
    guard, _ = _guard({"www.artic.edu": 0.0})
    answer = [httpx.Response(403, headers=TOO_WIDE, text="scales in excess of 100%")]
    sent: list[str] = []
    url = "https://www.artic.edu/iiif/2/abc/full/600,/0/default.jpg"
    with _client(guard, answer, sent) as http:
        for _ in range(3):
            assert http.get(url).status_code == 403
    assert len(sent) == 3 and guard.resting("www.artic.edu") == 0


def test_hosts_not_asked_in_bulk_keep_their_403() -> None:
    guard, _ = _guard()
    answer = [httpx.Response(403, headers=CHALLENGE)]
    sent: list[str] = []
    with _client(guard, answer, sent) as http:
        assert http.get("https://www.mauritshuis.nl/x.jpg").status_code == 403
        assert http.get("https://www.mauritshuis.nl/x.jpg").status_code == 403
    assert len(sent) == 2


def test_requests_to_one_host_are_spaced_out() -> None:
    guard, clock = _guard({"api.artic.edu": 1.0})
    answer = [httpx.Response(200, json={"data": {}})]
    sent: list[str] = []
    with _client(guard, answer, sent) as http:
        for _ in range(3):
            http.get("https://api.artic.edu/api/v1/artworks/1")
        http.get("https://openaccess-api.clevelandart.org/api/artworks/1")
    assert clock.slept == [1.0, 1.0]  # the first at once, Cleveland unpaced


def test_resting_host_is_not_tried_again_by_the_image_cache(tmp_path: Path) -> None:
    guard, _ = _guard({"www.artic.edu": 0.0})
    answer = [httpx.Response(403, headers=CHALLENGE)]
    sent: list[str] = []
    cache = ImageCache(tmp_path, lambda: _client(guard, answer, sent))
    slept: list[float] = []
    cache.sleep = slept.append
    item = Item(
        id="aic:1",
        kind=ItemKind.ARTWORK,
        source="aic",
        source_id="1",
        thumb_url="https://www.artic.edu/iiif/2/abc/full/600,/0/default.jpg",
    )
    with pytest.raises(Resting):
        cache.ensure_thumb(item)
    assert len(sent) == 1 and slept == []
    # Down for now, not gone: the original is asked for again later.
    with pytest.raises(Resting):
        cache.ensure_image(item)
    assert not cache.unavailable(item)


def test_aic_never_asks_a_picture_wider_than_it_is() -> None:
    def record(width: int) -> dict:
        return {
            "id": 22961,
            "title": "Hanging scroll",
            "image_id": "abc",
            "thumbnail": {"width": width, "height": 3000},
            "is_public_domain": True,
        }

    aic = ArtInstituteChicago(httpx.Client())
    narrow = aic._map(record(562))
    assert narrow is not None
    assert narrow.thumb_url.endswith("/abc/full/full/0/default.jpg")
    assert narrow.image_url.endswith("/abc/full/full/0/default.jpg")
    middle = aic._map(record(1200))
    assert middle is not None
    assert middle.thumb_url.endswith("/abc/full/600,/0/default.jpg")
    assert middle.image_url.endswith("/abc/full/full/0/default.jpg")
    wide = aic._map(record(6679))
    assert wide is not None and wide.image_url.endswith("/abc/full/1686,/0/default.jpg")


def test_a_met_object_that_does_not_load_leaves_the_others() -> None:
    guard, _ = _guard()
    search = "https://collectionapi.metmuseum.org/public/collection/v1.1/search"
    obj = {
        "objectID": 2,
        "title": "Kept",
        "isPublicDomain": True,
        "primaryImageSmall": "https://images/small.jpg",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith(search):
            return httpx.Response(200, json={"total": 2, "objectIDs": [1, 2]})
        if url.endswith("/objects/1"):
            return httpx.Response(502)
        return httpx.Response(200, json=obj)

    with httpx.Client(transport=httpx.MockTransport(handler), event_hooks=guard.hooks()) as http:
        total, items = MetropolitanMuseum(http).search("x")
    assert total == 2 and [i.title for i in items] == ["Kept"]


def test_a_walled_met_fails_the_whole_page() -> None:
    guard, _ = _guard()

    def handler(request: httpx.Request) -> httpx.Response:
        if "/search" in str(request.url):
            return httpx.Response(200, json={"total": 2, "objectIDs": [1, 2]})
        return httpx.Response(403, headers=IMPERVA)

    transport = httpx.MockTransport(handler)
    with (
        httpx.Client(transport=transport, event_hooks=guard.hooks()) as http,
        pytest.raises(Resting),
    ):
        MetropolitanMuseum(http).search("x")


def test_what_the_owner_waits_for_goes_before_the_background() -> None:
    """A theme opened in the app does not wait behind a burst of imports:
    an urgent request takes the next turn at the host, the others follow
    in order, still spaced out."""
    guard = HostGuard({"api.artic.edu": 0.15})
    order: list[str] = []
    times: list[float] = []

    def send(name: str, urgent: bool) -> None:
        request = httpx.Request("GET", AIC_SEARCH)
        if urgent:
            with urgently():
                guard.before(request)
        else:
            guard.before(request)
        order.append(name)
        times.append(time.monotonic())

    send("first", False)  # the host was just asked
    background = [threading.Thread(target=send, args=(f"import {n}", False)) for n in range(1, 4)]
    for thread in background:
        thread.start()
        time.sleep(0.02)  # in this order
    owner = threading.Thread(target=send, args=("theme", True))
    owner.start()
    for thread in [*background, owner]:
        thread.join(5)
    assert order == ["first", "theme", "import 1", "import 2", "import 3"]
    gaps = [b - a for a, b in itertools.pairwise(times)]
    assert min(gaps) >= 0.14  # still paced


def test_urgency_follows_work_into_worker_threads() -> None:
    with ThreadPoolExecutor(1) as pool:
        assert pool.submit(as_asked(is_urgent)).result() is False
        with urgently():
            assert pool.submit(as_asked(is_urgent)).result() is True
            assert pool.submit(is_urgent).result() is False  # not passed on by itself
    assert is_urgent() is False
