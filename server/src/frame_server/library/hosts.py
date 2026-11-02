"""Manners towards museum servers: requests to one host spaced out, and a
host whose bot wall turned us away left alone for a while.

The Art Institute of Chicago sits behind Cloudflare, the Met behind Imperva.
Both turn an address that sends bursts of requests away with 403 for every
request, the polite ones too, and keep doing so while the requests go on.

What the owner waits for (a theme opened in the app, a search, a card's
picture) is asked :func:`urgently`: it takes the next free turn at a host
before the background's requests still waiting (imports, sharper copies),
which can be dozens at the AIC's one request a second.
"""

from __future__ import annotations

import contextlib
import heapq
import itertools
import logging
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx

log = logging.getLogger(__name__)

#: The hosts asked in bulk, and the least time between two requests to one,
#: in seconds. The AIC API asks for at most 60 requests a minute; the others
#: are a guess well below what their bot walls took offence at.
PACE = {
    "api.artic.edu": 1.0,
    "www.artic.edu": 0.25,
    "collectionapi.metmuseum.org": 0.25,
    "images.metmuseum.org": 0.25,
    # Asked for the Commons copy of a picture a museum refused.
    "www.wikidata.org": 0.5,
}
#: How long a host that turned us away is not asked; doubled each time it
#: still does, up to REST_MAX, and forgotten once it answers again.
REST = 15 * 60.0
REST_MAX = 4 * 3600.0

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


class HostGuard:
    def __init__(self, pace: dict[str, float] | None = None) -> None:
        self.pace = PACE if pace is None else pace
        self.clock: Callable[[], float] = time.monotonic
        self.sleep: Callable[[float], None] = time.sleep
        self._lock = threading.Lock()
        #: When the next request to a host may go (by host).
        self._next: dict[str, float] = {}
        #: Requests waiting for their turn (by host): (0 urgent / 1 not, order).
        self._waiting: dict[str, list[tuple[int, int]]] = {}
        self._turns = threading.Condition(self._lock)
        self._order = itertools.count()
        #: Until when a host is left alone, and for how long it was (by host).
        self._resting: dict[str, tuple[float, float]] = {}

    def resting(self, host: str) -> float:
        """Seconds until ``host`` is asked again; 0 when it may be now."""
        with self._lock:
            until, _ = self._resting.get(host, (0.0, 0.0))
            return max(until - self.clock(), 0.0)

    def before(self, request: httpx.Request) -> None:
        host = request.url.host
        wait = self.resting(host)
        if wait:
            raise Resting(
                f"{host} turned us away; not asked for {wait / 60:.0f} min", request=request
            )
        pace = self.pace.get(host)
        if not pace:
            return
        self._turn(host, pace)
        wait = self.resting(host)
        if wait:  # walled while this one waited its turn
            raise Resting(
                f"{host} turned us away; not asked for {wait / 60:.0f} min", request=request
            )

    def _turn(self, host: str, pace: float) -> None:
        """Waits until this request may go to ``host``: ``pace`` seconds
        after the one before, urgent ones first, the rest in order."""
        ticket = (0 if is_urgent() else 1, next(self._order))
        with self._turns:
            heapq.heappush(self._waiting.setdefault(host, []), ticket)
        try:
            while True:
                with self._turns:
                    waiting = self._waiting[host]
                    if waiting[0] != ticket:
                        # Woken when the first in line goes, or a minute on.
                        self._turns.wait(60.0)
                        continue
                    now = self.clock()
                    at = self._next.get(host, 0.0)
                    if now >= at:
                        heapq.heappop(waiting)
                        self._next[host] = now + pace
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
        if host not in self.pace:
            return  # a single picture's host: its refusal is the picture's
        if not walled(response):
            with self._lock:
                self._resting.pop(host, None)
            return
        with self._lock:
            until, rest = self._resting.get(host, (0.0, 0.0))
            now = self.clock()
            if until <= now:  # not one of the requests already under way
                rest = min(rest * 2, REST_MAX) if rest else REST
                self._resting[host] = (now + rest, rest)
                log.warning(
                    "%s turned us away (%s %s); leaving it alone for %.0f min",
                    host,
                    response.status_code,
                    response.headers.get("cf-mitigated") or "bot wall",
                    rest / 60,
                )
        raise Resting(f"{host} turned us away", request=response.request)

    def hooks(self) -> dict[str, list[Any]]:
        return {"request": [self.before], "response": [self.after]}


#: Shared by every client of the process: the museums see one address.
guard = HostGuard()
