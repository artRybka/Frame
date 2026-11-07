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

from frame_server.library.aic import aic_width
from frame_server.library.hosts import (
    PROBE_EVERY,
    REST,
    WIKIMEDIA,
    WIKIMEDIA_MEDIA,
    HostGuard,
    Resting,
    as_asked,
    is_urgent,
    lane,
    retry_after,
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


def test_a_resting_host_is_asked_once_a_minute_whether_it_answers_again() -> None:
    """A wall that challenged one request (a full-size original, 2026-11-04)
    may let the next ones through: one request a minute still goes, and
    once one is answered the host is asked as before, not after the rest."""
    guard, clock = _guard({"www.artic.edu": 0.0})
    answer = [httpx.Response(403, headers=CHALLENGE)]
    sent: list[str] = []
    thumb = "https://www.artic.edu/iiif/2/abc/full/600,/0/default.jpg"
    with _client(guard, answer, sent) as http:
        with pytest.raises(Resting):
            http.get(thumb)
        with pytest.raises(Resting):
            http.get(thumb)
        assert len(sent) == 1
        # A minute on: one goes, still walled; the rest is not made longer.
        clock.now += PROBE_EVERY
        with pytest.raises(Resting):
            http.get(thumb)
        with pytest.raises(Resting):
            http.get(thumb)
        assert len(sent) == 2
        assert guard.resting("www.artic.edu") == pytest.approx(REST - PROBE_EVERY)
        # Another minute: it answers, and the host is free again.
        clock.now += PROBE_EVERY
        answer[0] = httpx.Response(200, content=b"jpeg")
        assert http.get(thumb).status_code == 200
        assert guard.resting("www.artic.edu") == 0
        assert http.get(thumb).status_code == 200
        assert len(sent) == 4


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


def test_aic_asks_only_the_widths_its_iiif_server_gives() -> None:
    """Its API docs allow 112, 200, 400, 600, 800, 843 (1200, 1686 for public
    domain), 843 recommended; ``full/full`` woke its Cloudflare (2026-11-04),
    and a width beyond the picture's its server refuses. The original of a
    larger picture comes in the website's download size, fit into 3000×3000
    (2026-11-05), unless 1686 is wider (a tall narrow scroll)."""

    def record(width: int | None, height: int = 3000) -> dict:
        thumb = {"width": width, "height": height} if width else {}
        return {
            "id": 22961,
            "title": "Hanging scroll",
            "image_id": "abc",
            "thumbnail": thumb,
            "is_public_domain": True,
        }

    aic = ArtInstituteChicago(httpx.Client())

    def sizes(width: int | None, height: int = 3000) -> tuple[str, str]:
        item = aic._map(record(width, height))
        assert item is not None
        return item.thumb_url.split("/full/")[1], item.image_url.split("/full/")[1]

    assert sizes(562) == ("400,/0/default.jpg", "400,/0/default.jpg")
    assert sizes(843) == ("843,/0/default.jpg", "843,/0/default.jpg")
    assert sizes(1200) == ("843,/0/default.jpg", "1200,/0/default.jpg")
    assert sizes(1500) == ("843,/0/default.jpg", "1200,/0/default.jpg")
    assert sizes(6679) == ("843,/0/default.jpg", "!3000,3000/0/default.jpg")
    assert sizes(2975, 2250) == ("843,/0/default.jpg", "!3000,3000/0/default.jpg")
    assert sizes(1800, 1000) == ("843,/0/default.jpg", "!3000,3000/0/default.jpg")
    assert sizes(1800, 4000) == ("843,/0/default.jpg", "1686,/0/default.jpg")  # 1350 at 3000
    assert sizes(None) == ("843,/0/default.jpg", "1686,/0/default.jpg")
    assert aic_width(843, 90) == 112  # smaller than any: the smallest


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


def test_wikimedia_wikis_count_as_one_host() -> None:
    """Wikimedia's robot policy limits programs without an account across
    all wikis together: Commons, Wikidata and every Wikipedia share a lane."""
    assert lane("commons.wikimedia.org") == lane("www.wikidata.org") == WIKIMEDIA
    assert lane("pl.wikipedia.org") == WIKIMEDIA
    # Media files: a lane of their own, originals and renditions together.
    assert lane("upload.wikimedia.org") == lane("thumb.wikimedia.org") == WIKIMEDIA_MEDIA
    assert lane("api.artic.edu") == "api.artic.edu"


def test_a_limited_lane_sends_one_request_at_a_time() -> None:
    """The Action API (and the AIC) one request at a time: the next waits
    until the one under way is answered, whichever wiki it goes to."""
    guard = HostGuard({}, {WIKIMEDIA: 1})
    under_way = 0
    most = 0
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

    hosts = ["commons.wikimedia.org", "www.wikidata.org", "pl.wikipedia.org"] * 3
    with (
        guard.client(transport=httpx.MockTransport(handler)) as http,
        ThreadPoolExecutor(6) as pool,
    ):
        codes = list(pool.map(lambda h: http.get(f"https://{h}/w/api.php").status_code, hosts))
    assert codes == [200] * len(hosts) and most == 1


def test_a_failed_request_gives_its_slot_back() -> None:
    guard = HostGuard({}, {"api.artic.edu": 1})
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectTimeout("slow", request=request)
        return httpx.Response(200, json={})

    with guard.client(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(httpx.ConnectTimeout):
            http.get(AIC_SEARCH)
        done = ThreadPoolExecutor(1).submit(http.get, AIC_SEARCH)
        assert done.result(timeout=5).status_code == 200


def test_a_redirect_within_the_lane_does_not_wait_for_itself() -> None:
    """Special:FilePath on Commons sends on to the file: the slot goes back
    with the redirect, before the next hop asks for one."""
    guard = HostGuard({}, {WIKIMEDIA: 1, WIKIMEDIA_MEDIA: 1})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "commons.wikimedia.org":
            if "FilePath" in request.url.path:
                return httpx.Response(302, headers={"location": "https://www.wikidata.org/x"})
            return httpx.Response(302, headers={"location": "https://upload.wikimedia.org/a.jpg"})
        if request.url.host == "www.wikidata.org":
            return httpx.Response(302, headers={"location": "https://commons.wikimedia.org/y"})
        return httpx.Response(200, content=b"jpeg")

    with guard.client(transport=httpx.MockTransport(handler), follow_redirects=True) as http:
        done = ThreadPoolExecutor(1).submit(
            http.get, "https://commons.wikimedia.org/wiki/Special:FilePath/a.jpg"
        )
        assert done.result(timeout=5).content == b"jpeg"
    assert guard._busy == {WIKIMEDIA: 0, WIKIMEDIA_MEDIA: 0}


def test_a_429_is_waited_out_as_the_host_asks() -> None:
    """Every source asks for its Retry-After to be kept: the host is not
    asked until then, not even the once-a-minute look."""
    guard, clock = _guard({})
    answer = [httpx.Response(429, headers={"retry-after": "120"})]
    sent: list[str] = []
    url = "https://api.si.edu/openaccess/api/v1.0/search"
    with _client(guard, answer, sent) as http:
        assert http.get(url).status_code == 429
        assert guard.resting("api.si.edu") == pytest.approx(120)
        clock.now += PROBE_EVERY
        with pytest.raises(Resting):
            http.get(url)
        assert len(sent) == 1
        clock.now += 61
        answer[0] = httpx.Response(200, json={})
        assert http.get(url).status_code == 200
        assert len(sent) == 2
    # Without a Retry-After nothing is assumed; a date works too.
    plain = httpx.Response(429, request=httpx.Request("GET", url))
    assert retry_after(plain) is None
    dated = httpx.Response(429, headers={"retry-after": "Wed, 21 Oct 2015 07:28:00 GMT"})
    assert retry_after(dated) == 0.0


def test_the_library_of_congress_is_left_alone_for_its_hour() -> None:
    """loc.gov blocks for an hour and may start counting again on a request
    meanwhile (2026-11-07, the home address challenged): no look a minute,
    and a 429 without Retry-After counts as that hour too."""
    from frame_server.library.hosts import LONG_BLOCKS, PACE

    assert PACE["www.loc.gov"] >= 3.0  # 20 a minute at most
    assert PACE["tile.loc.gov"] >= 0.4  # 150 a minute at most
    guard, clock = _guard({"www.loc.gov": 0.0})
    answer = [httpx.Response(403, headers=CHALLENGE)]
    sent: list[str] = []
    url = "https://www.loc.gov/photos/?fo=json"
    with _client(guard, answer, sent) as http:
        with pytest.raises(Resting):
            http.get(url)
        assert guard.resting("www.loc.gov") == pytest.approx(LONG_BLOCKS["www.loc.gov"])
        clock.now += PROBE_EVERY
        with pytest.raises(Resting):
            http.get(url)
        assert len(sent) == 1  # no look meanwhile
        clock.now += LONG_BLOCKS["www.loc.gov"]
        answer[0] = httpx.Response(429)
        assert http.get(url).status_code == 429
        assert guard.resting("www.loc.gov") == pytest.approx(LONG_BLOCKS["www.loc.gov"])
