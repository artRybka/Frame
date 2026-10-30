"""Museum hosts: requests spaced out, a host whose bot wall turned us away
left alone for a while (the AIC's Cloudflare, the Met's Imperva)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from frame_server.library.hosts import REST, HostGuard, Resting, walled
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
