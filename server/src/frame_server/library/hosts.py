"""Manners towards museum servers: requests to one host spaced out, and a
host whose bot wall turned us away left alone for a while.

The Art Institute of Chicago sits behind Cloudflare, the Met behind Imperva.
Both turn an address that sends bursts of requests away with 403 for every
request, the polite ones too, and keep doing so while the requests go on.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
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
}
#: How long a host that turned us away is not asked; doubled each time it
#: still does, up to REST_MAX, and forgotten once it answers again.
REST = 15 * 60.0
REST_MAX = 4 * 3600.0


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
        with self._lock:
            now = self.clock()
            at = max(now, self._next.get(host, 0.0))
            self._next[host] = at + pace
        if at > now:
            self.sleep(at - now)

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
