"""Manners towards museum servers: requests to one host spaced out, and a
host whose bot wall turned us away left alone for a while.

The Art Institute of Chicago sits behind Cloudflare, the Met behind Imperva.
Both turn an address that sends bursts of requests away with 403 for every
request, the polite ones too, and keep doing so while the requests go on.

What the owner waits for (a theme opened in the app, a search, a card's
picture) is asked :func:`urgently`: it takes the next free turn at a host
before the background's requests still waiting (imports, sharper copies),
which can be dozens at the AIC's one request a second.

Each source's own rules for programs (checked 2026-11-04, PLAN 3.3m3) set
the numbers below: the AIC's API docs ("Scraping Images", 60 requests a
minute, one picture at a time), Wikimedia's robot policy (the wikis' Action
API one request at a time and below five a second for all wikis together,
media at most two at a time), WikiArt's free package (four a second, 400 an
hour) and everyone's ``Retry-After`` on a 429.
"""

from __future__ import annotations

import contextlib
import heapq
import itertools
import logging
import threading
import time
from collections.abc import Callable, Iterator
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

log = logging.getLogger(__name__)

#: The Wikimedia wikis' API, counted as one host: Wikimedia limits programs
#: without an account across all wikis together (its robot policy).
WIKIMEDIA = "wikimedia-api"
WIKIMEDIA_HOSTS = frozenset({"commons.wikimedia.org", "www.wikidata.org", "meta.wikimedia.org"})
#: Wikimedia's media files, counted as one host: originals come from
#: upload.wikimedia.org, Special:FilePath's renditions from thumb.wikimedia.org.
WIKIMEDIA_MEDIA = "wikimedia-media"
MEDIA_HOSTS = frozenset({"upload.wikimedia.org", "thumb.wikimedia.org"})


def lane(host: str) -> str:
    """What ``host``'s pace and limit count against: itself, the Wikimedia
    wikis together (Commons, Wikidata, every Wikipedia), or Wikimedia's
    media hosts together."""
    if host in WIKIMEDIA_HOSTS or host.endswith(".wikipedia.org"):
        return WIKIMEDIA
    if host in MEDIA_HOSTS:
        return WIKIMEDIA_MEDIA
    return host


#: The hosts asked in bulk (or :func:`lane`), and the least time between two
#: requests to one, in seconds. The AIC API asks for at most 60 requests a
#: minute; the Met for at most 80 a second; Wikimedia for below 5 a second;
#: WikiArt's free keys take 400 an hour. The Met's pace is a guess well below
#: what its bot wall took offence at.
PACE = {
    "api.artic.edu": 1.0,
    # Its IIIF server: one picture at a time, a second apart, as the AIC's
    # API docs ask ("Scraping Images"; one at a time: LIMITS).
    "www.artic.edu": 1.0,
    "collectionapi.metmuseum.org": 0.25,
    "images.metmuseum.org": 0.25,
    # Commons searches, Wikidata facts, Wikipedia intros: all one lane.
    WIKIMEDIA: 0.25,
    "www.wikiart.org": 1.0,
}
#: The most requests under way at once to a host (or :func:`lane`), where
#: its owners ask for fewer than the server's threads would send. Only
#: clients made by :meth:`HostGuard.client` keep to it.
LIMITS = {
    # "Avoid running multiple scrapers in parallel"; one picture at a time.
    "api.artic.edu": 1,
    "www.artic.edu": 1,
    # Unauthenticated clients: one request at a time to the Action API, at
    # most two downloads at a time of media files.
    WIKIMEDIA: 1,
    WIKIMEDIA_MEDIA: 2,
}
#: The longest a host's ``Retry-After`` (on a 429) is kept to: api.data.gov
#: blocks a key for an hour; longer waits are taken as an hour too.
THROTTLED_MAX = 3600.0
#: How long a host that turned us away is not asked; doubled each time it
#: still does, up to REST_MAX, and forgotten once it answers again.
REST = 15 * 60.0
REST_MAX = 4 * 3600.0
#: While a host rests, one request this often still goes, to see whether it
#: answers again: a wall that challenged one kind of request (a full-size
#: original) or forgot us early lets the pictures through at once instead
#: of after the whole rest. One a minute is far below anything that woke it.
PROBE_EVERY = 60.0

_asking = threading.local()


@contextlib.contextmanager
def urgently() -> Iterator[None]:
    """Requests this thread sends meanwhile go before the background's."""
    before = is_urgent()
    _asking.urgent = True
    try:
        yield
    finally:
        _asking.urgent = before


def is_urgent() -> bool:
    return bool(getattr(_asking, "urgent", False))


def urgent_call[**P, T](fn: Callable[P, T]) -> Callable[P, T]:
    """``fn`` asked :func:`urgently`, wherever it runs (a worker thread)."""

    def call(*args: P.args, **kwargs: P.kwargs) -> T:
        with urgently():
            return fn(*args, **kwargs)

    return call


def as_asked[**P, T](fn: Callable[P, T]) -> Callable[P, T]:
    """``fn``, to run in another thread as urgently as in this one."""
    return urgent_call(fn) if is_urgent() else fn


_held = threading.local()


def retry_after(resp: httpx.Response) -> float | None:
    """The seconds a response asks to wait (``Retry-After``: a number or an
    HTTP date); None when it does not say."""
    value = resp.headers.get("retry-after", "").strip()
    if not value:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(when.timestamp() - time.time(), 0.0)


class Resting(httpx.TransportError):
    """The host's bot wall turned us away lately; it is not asked until the
    wall has had time to forget us. Like a host that is down, the request is
    worth trying again later."""


def walled(resp: httpx.Response) -> bool:
    """Whether a 403 is a bot wall's (Cloudflare's challenge or block page,
    Imperva's), not the server's own answer (the AIC's IIIF server says 403
    to a picture asked larger than it is)."""
    if resp.status_code != 403:
        return False
    headers = resp.headers
    if "cf-mitigated" in headers or "x-iinfo" in headers:
        return True
    if "imperva" in headers.get("x-cdn", "").lower():
        return True
    cloudflare = headers.get("server", "").lower() == "cloudflare"
    return cloudflare and headers.get("content-type", "").startswith("text/html")


class GuardedClient(httpx.Client):
    """A client whose requests keep to :data:`LIMITS` too: a slot taken
    when a request gets its turn is given back with its answer, or when it
    fails without one."""

    def __init__(self, guard: HostGuard, **kwargs: Any) -> None:
        super().__init__(event_hooks=guard.hooks(), **kwargs)
        self._host_guard = guard

    def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:
        before = getattr(_held, "lanes", None)
        _held.lanes = []
        try:
            return super().send(request, **kwargs)
        finally:
            for key in _held.lanes:
                self._host_guard.release(key)
            _held.lanes = before


class HostGuard:
    def __init__(
        self, pace: dict[str, float] | None = None, limits: dict[str, int] | None = None
    ) -> None:
        self.pace = PACE if pace is None else pace
        self.limits = LIMITS if limits is None else limits
        self.clock: Callable[[], float] = time.monotonic
        self.sleep: Callable[[float], None] = time.sleep
        self._lock = threading.Lock()
        #: When the next request to a host may go (by host).
        self._next: dict[str, float] = {}
        #: Requests waiting for their turn (by host): (0 urgent / 1 not, order).
        self._waiting: dict[str, list[tuple[int, int]]] = {}
        #: Requests under way that count against a limit (by lane).
        self._busy: dict[str, int] = {}
        self._turns = threading.Condition(self._lock)
        self._order = itertools.count()
        #: Until when a host is left alone, and for how long it was (by host).
        self._resting: dict[str, tuple[float, float]] = {}
        #: When a resting host may be asked once more, to see (by host).
        self._probe_at: dict[str, float] = {}

    def resting(self, host: str) -> float:
        """Seconds until ``host`` is asked again; 0 when it may be now."""
        with self._lock:
            until, _ = self._resting.get(host, (0.0, 0.0))
            return max(until - self.clock(), 0.0)

    def _left(self, host: str) -> float:
        """Like :meth:`resting`, but lets one request through every
        :data:`PROBE_EVERY` (it says 0 to that one)."""
        with self._lock:
            until, _ = self._resting.get(host, (0.0, 0.0))
            now = self.clock()
            left = max(until - now, 0.0)
            if left and now >= self._probe_at.get(host, 0.0):
                self._probe_at[host] = now + PROBE_EVERY
                log.info(
                    "%s rests %.0f min more; one request to see if it answers", host, left / 60
                )
                return 0.0
            return left

    def before(self, request: httpx.Request) -> None:
        host = request.url.host
        wait = self._left(host)
        if wait:
            raise Resting(
                f"{host} turned us away; not asked for {wait / 60:.0f} min", request=request
            )
        probe = self.resting(host) > 0
        key = lane(host)
        pace = self.pace.get(key, 0.0)
        held = getattr(_held, "lanes", None)
        limit = self.limits.get(key) if held is not None and key not in held else None
        if not pace and not limit:
            return
        self._turn(key, pace, limit)
        if limit:
            assert held is not None
            held.append(key)
        wait = 0.0 if probe else self.resting(host)
        if wait:  # walled while this one waited its turn
            raise Resting(
                f"{host} turned us away; not asked for {wait / 60:.0f} min", request=request
            )

    def release(self, key: str) -> None:
        """Gives back the slot a request to ``key`` took (:data:`LIMITS`)."""
        with self._turns:
            if self._busy.get(key, 0) > 0:
                self._busy[key] -= 1
            self._turns.notify_all()

    def client(self, **kwargs: Any) -> httpx.Client:
        """A client keeping to this guard's paces, rests and limits."""
        return GuardedClient(self, **kwargs)

    def _turn(self, host: str, pace: float, limit: int | None = None) -> None:
        """Waits until this request may go to ``host``: ``pace`` seconds
        after the one before and, with a ``limit``, while fewer than that are
        under way; urgent ones first, the rest in order."""
        ticket = (0 if is_urgent() else 1, next(self._order))
        with self._turns:
            heapq.heappush(self._waiting.setdefault(host, []), ticket)
        try:
            while True:
                with self._turns:
                    waiting = self._waiting[host]
                    if waiting[0] != ticket or (limit and self._busy.get(host, 0) >= limit):
                        # Woken when the first in line goes or a slot is
                        # given back, or a minute on.
                        self._turns.wait(60.0)
                        continue
                    now = self.clock()
                    at = self._next.get(host, 0.0)
                    if now >= at:
                        heapq.heappop(waiting)
                        self._next[host] = now + pace
                        if limit:
                            self._busy[host] = self._busy.get(host, 0) + 1
                        self._turns.notify_all()
                        return
                # First in line: sleeps until the host may be asked (an
                # urgent one coming meanwhile goes first, this one after).
                self.sleep(at - now)
        except BaseException:
            with self._turns:
                waiting = self._waiting[host]
                if ticket in waiting:
                    waiting.remove(ticket)
                    heapq.heapify(waiting)
                self._turns.notify_all()
            raise

    def after(self, response: httpx.Response) -> None:
        host = response.request.url.host
        key = lane(host)
        held = getattr(_held, "lanes", None)
        if held and key in held:
            held.remove(key)  # answered: the next one may go
            self.release(key)
        if response.status_code == 429:
            self._throttled(host, response)
            return
        if key not in self.pace:
            return  # a single picture's host: its refusal is the picture's
        if not walled(response):
            with self._lock:
                rested = self._resting.pop(host, None)
                self._probe_at.pop(host, None)
            if rested is not None and rested[0] > self.clock():
                log.warning("%s answers again; asked as before", host)
            return
        with self._lock:
            until, rest = self._resting.get(host, (0.0, 0.0))
            now = self.clock()
            if until <= now:  # not one of the requests already under way
                rest = min(rest * 2, REST_MAX) if rest else REST
                self._resting[host] = (now + rest, rest)
                self._probe_at[host] = now + PROBE_EVERY
                log.warning(
                    "%s turned us away (%s %s); leaving it alone for %.0f min",
                    host,
                    response.status_code,
                    response.headers.get("cf-mitigated") or "bot wall",
                    rest / 60,
                )
        raise Resting(f"{host} turned us away", request=response.request)

    def _throttled(self, host: str, response: httpx.Response) -> None:
        """A 429 that says how long to wait: ``host`` is not asked until
        then (not even once a minute to see), as every source asks."""
        wait = retry_after(response)
        if not wait:
            return
        wait = min(wait, THROTTLED_MAX)
        with self._lock:
            now = self.clock()
            until, rest = self._resting.get(host, (0.0, 0.0))
            if until >= now + wait:
                return
            self._resting[host] = (now + wait, rest)
            self._probe_at[host] = now + wait
        log.warning("%s asks us to wait %.0f s (429); not asked until then", host, wait)

    def hooks(self) -> dict[str, list[Any]]:
        return {"request": [self.before], "response": [self.after]}


#: Shared by every client of the process: the museums see one address.
guard = HostGuard()
