"""Manners towards museum servers: requests to one host spaced out, and a
host whose bot wall turned us away left alone for a while.

The Art Institute of Chicago sits behind Cloudflare, the Met behind Imperva.
Both turn an address that sends bursts of requests away with 403 for every
request, the polite ones too, and keep doing so while the requests go on.

What the owner waits for (a theme opened in the app, a search, a card's
picture) is asked :func:`urgently`: it takes the next free turn at a host
before the background's requests still waiting (imports, sharper copies),
which can be dozens at the AIC's one request a second.

The numbers come from each source's own rules for programs, gathered in
:mod:`.policy`: paces, how many at once, fixed blocks, and quotas over an
hour or a day (Paris Musées, the Smithsonian, Openverse, WikiArt), of which
the background leaves a share for what the owner waits for. Everyone's
``Retry-After`` on a 429 is kept to. Once a day the log says how many
requests went to each host and how many were turned away.
"""

from __future__ import annotations

import contextlib
import contextvars
import heapq
import itertools
import json
import logging
import os
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx

from .policy import (
    BUDGETS,
    CALM_START,
    DEFAULT_LIMIT,
    LIMITS,
    LONG_BLOCKS,
    MEDIA_HOSTS,
    PACE,
    SOURCES,
    WALL_403,
    WIKIMEDIA,
    WIKIMEDIA_HOSTS,
    WIKIMEDIA_MEDIA,
    Budget,
    Source,
    owner_of,
)

log = logging.getLogger(__name__)


def lane(host: str) -> str:
    """What ``host``'s pace and limit count against: itself, the Wikimedia
    wikis together (Commons, Wikidata, every Wikipedia), or Wikimedia's
    media hosts together."""
    if host in WIKIMEDIA_HOSTS or host.endswith(".wikipedia.org"):
        return WIKIMEDIA
    if host in MEDIA_HOSTS:
        return WIKIMEDIA_MEDIA
    return host


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

#: Whether this request is one the owner waits for (:func:`urgently`).
_urgent: contextvars.ContextVar[bool] = contextvars.ContextVar("urgent", default=False)
#: What a request is for, as Diagnostyka counts it (:func:`asking_for`).
_why: contextvars.ContextVar[str | None] = contextvars.ContextVar("why", default=None)
#: Whether the app (or the panel) asked for it: such requests never wait for
#: the quiet after a start (:meth:`HostGuard.calm`).
_app: contextvars.ContextVar[bool] = contextvars.ContextVar("app", default=False)

#: What requests are counted as when nobody said: asked from the app's
#: requests, or by the server's own work in the background.
APP = "aplikacja"
BACKGROUND = "tło"


@contextlib.contextmanager
def urgently() -> Iterator[None]:
    """Requests this thread sends meanwhile go before the background's."""
    token = _urgent.set(True)
    try:
        yield
    finally:
        _urgent.reset(token)


def is_urgent() -> bool:
    return _urgent.get()


@contextlib.contextmanager
def asking_for(why: str, app: bool | None = None) -> Iterator[None]:
    """Requests sent meanwhile are counted as ``why`` (Szukaj, Odkrywaj, the
    night, the catalogue...); ``app``: whether the app waits for them."""
    token = _why.set(why)
    marked = _app.set(app) if app is not None else None
    try:
        yield
    finally:
        _why.reset(token)
        if marked is not None:
            _app.reset(marked)


#: The server's own threads and what their requests are for, where they
#: did not say (:func:`asking_for`): by the thread's name, or the name of the
#: function it runs.
THREAD_PURPOSES: tuple[tuple[str, str], ...] = (
    ("night", "noc"),
    ("searched", "katalog"),
    ("job-", "katalog"),
    ("search-page", "odświeżanie"),
    ("sharper", "kopie"),
    ("holder", "muzeum dzieła"),
    ("real-size", "rozmiary"),
    ("artist-works", "dzieła autora"),
    ("later-works", "dzieła autora"),
    ("study-details", "studium"),
    ("daily", "studium dnia"),
    ("ai-", "opisy"),
    ("kept", "oryginały"),
    ("-index", "spisy muzeów"),
    ("work_out_cards", "karty Odkrywaj"),
    ("_fetch_day_row", "odkrywaj"),
    ("_work_out_page", "odkrywaj"),
)


def purpose() -> str:
    """What the requests sent now are for: as said (:func:`asking_for`),
    else by the thread that sends them."""
    said = _why.get()
    if said:
        return said
    if _app.get() or is_urgent():
        return APP
    name = threading.current_thread().name
    for part, why in THREAD_PURPOSES:
        if part in name:
            return why
    return BACKGROUND


def from_app() -> bool:
    return _app.get() or is_urgent()


def urgent_call[**P, T](fn: Callable[P, T]) -> Callable[P, T]:
    """``fn`` asked :func:`urgently`, wherever it runs (a worker thread)."""

    def call(*args: P.args, **kwargs: P.kwargs) -> T:
        with urgently():
            return fn(*args, **kwargs)

    return call


def for_purpose[**P, T](why: str, fn: Callable[P, T]) -> Callable[P, T]:
    """``fn`` with its requests counted as ``why``, wherever it runs."""

    def call(*args: P.args, **kwargs: P.kwargs) -> T:
        with asking_for(why):
            return fn(*args, **kwargs)

    return call


def as_asked[**P, T](fn: Callable[P, T]) -> Callable[P, T]:
    """``fn``, to run in another thread as this one asks: as urgently, for
    the same purpose, for the app or not."""
    urgent, why, app = _urgent.get(), _why.get(), _app.get()
    if not (urgent or why or app):
        return fn

    def call(*args: P.args, **kwargs: P.kwargs) -> T:
        tokens = (_urgent.set(urgent), _why.set(why), _app.set(app))
        try:
            return fn(*args, **kwargs)
        finally:
            _app.reset(tokens[2])
            _why.reset(tokens[1])
            _urgent.reset(tokens[0])

    return call


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


class OverBudget(Resting):
    """The host's quota for the hour or the day is spent (for the background,
    its share of it): asked again once older requests fall out of the window."""


#: Quotas spent are written down at most this often (seconds), so that a
#: restart does not start them afresh.
BUDGET_SAVE_EVERY = 30.0
#: A spent quota is told in the log at most this often per host (seconds).
BUDGET_LOG_EVERY = 600.0
#: A tally's numbers: requests sent, turned away by a bot wall, throttled
#: (429), failed (401, 403, 5xx), refused by the server itself (a resting
#: host, a spent quota), and the bytes the answers said they hold.
TALLY_FIELDS = ("sent", "walled", "throttled", "failed", "refused", "bytes")
#: Days of tallies kept (Diagnostyka shows a week).
TALLY_DAYS = 7
#: The tallies are written at most this often (seconds), and when a day ends.
TALLY_SAVE_EVERY = 60.0


def walled(resp: httpx.Response) -> bool:
    """Whether a 403 is a bot wall's (Cloudflare's challenge or block page,
    Imperva's), not the server's own answer (the AIC's IIIF server says 403
    to a picture asked larger than it is)."""
    if resp.status_code != 403:
        return False
    request = resp._request  # a response made by hand has none
    if request is not None and request.url.host in WALL_403:  # 403 only to bursts
        return True
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
        self,
        pace: dict[str, float] | None = None,
        limits: dict[str, int] | None = None,
        default_limit: int | None = None,
        budgets: dict[str, Budget] | None = None,
    ) -> None:
        self.pace = PACE if pace is None else pace
        self.limits = LIMITS if limits is None else limits
        #: Requests at once to a host without a limit of its own.
        self.default_limit = default_limit
        self.budgets: dict[str, Budget] = {} if budgets is None else budgets
        self.clock: Callable[[], float] = time.monotonic
        self.sleep: Callable[[float], None] = time.sleep
        #: The time of day of quotas (they outlive a restart) and of the tally.
        self.wall: Callable[[], float] = time.time
        #: When each counted request of a quota went (by host).
        self._spent: dict[str, deque[float]] = {}
        self._budget_file: Path | None = None
        self._budget_saved = 0.0
        self._budget_told: dict[str, float] = {}
        #: Each kept day's requests by host (:data:`TALLY_FIELDS`).
        self._days: dict[str, dict[str, list[int]]] = {}
        self._tally_day = ""
        self._tally_file: Path | None = None
        self._tally_saved = 0.0
        #: Each kept day's requests by host and by what they were for.
        self._purposes: dict[str, dict[str, dict[str, int]]] = {}
        self._purposes_file: Path | None = None
        #: Until when the background does not ask anyone (:meth:`calm`).
        self.calm_until = 0.0
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

    def calm(self, seconds: float = CALM_START) -> None:
        """For ``seconds`` from now, the background's requests wait and only
        what the app or the panel asks for goes: after an update of the
        server everything the background left off (the catalogue, pages
        asked again, Propozycje) went at once, 486 requests in nine minutes
        (2026-11-07)."""
        self.calm_until = self.clock() + seconds
        log.info("the background asks no museum for %.0f min", seconds / 60)

    def wait_calm(self) -> None:
        """Waits out the quiet after a start, unless the app asks."""
        while not from_app():
            left = self.calm_until - self.clock()
            if left <= 0:
                return
            self.sleep(min(left, 30.0))

    def before(self, request: httpx.Request) -> None:
        host = request.url.host
        self.wait_calm()
        try:
            self._before(request, host)
        except Resting:
            self._count(host, refused=1)
            raise

    def _before(self, request: httpx.Request, host: str) -> None:
        wait = self._left(host)
        if wait:
            raise Resting(
                f"{host} turned us away; not asked for {wait / 60:.0f} min", request=request
            )
        self._spend(host, request)
        probe = self.resting(host) > 0
        key = lane(host)
        pace = self.pace.get(key, 0.0)
        held = getattr(_held, "lanes", None)
        limit = (
            self.limits.get(key, self.default_limit)
            if held is not None and key not in held
            else None
        )
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

    # -- quotas ----------------------------------------------------------------

    def keep_budgets(self, path: Path) -> None:
        """Quotas spent are written to ``path`` (and read from it now), so
        that a restart does not start them afresh."""
        self._budget_file = path
        try:
            saved = json.loads(path.read_text())
        except (OSError, ValueError):
            return
        now = self.wall()
        with self._lock:
            for host, times in saved.items():
                budget = self.budgets.get(host)
                if budget is None or not isinstance(times, list):
                    continue
                kept = sorted(float(t) for t in times if now - float(t) < budget.window)
                self._spent[host] = deque(kept)

    def spent(self, host: str) -> int:
        """Requests to ``host`` counted against its quota's window now."""
        budget = self.budgets.get(host)
        if budget is None:
            return 0
        now = self.wall()
        with self._lock:
            times = self._spent.get(host, deque())
            return sum(1 for t in times if t > now - budget.window)

    def _spend(self, host: str, request: httpx.Request) -> None:
        """Counts this request against ``host``'s quota, or refuses it when
        the quota (the background's share of it) is spent."""
        budget = self.budgets.get(host)
        if budget is None:
            return
        if budget.anonymous_only and "authorization" in request.headers:
            return
        now = self.wall()
        allowed = budget.count if is_urgent() else budget.background
        with self._lock:
            times = self._spent.setdefault(host, deque())
            while times and times[0] <= now - budget.window:
                times.popleft()
            over = len(times) >= allowed
            if over:
                # One more fits when the oldest of the last ``allowed`` falls out.
                wait = times[len(times) - allowed] + budget.window - now if allowed else 0.0
                tell = now - self._budget_told.get(host, 0.0) >= BUDGET_LOG_EVERY
                if tell:
                    self._budget_told[host] = now
            else:
                times.append(now)
            snapshot = None
            if self._budget_file is not None and now - self._budget_saved >= BUDGET_SAVE_EVERY:
                self._budget_saved = now
                snapshot = {h: list(t) for h, t in self._spent.items()}
        if snapshot is not None:
            self._save(self._budget_file, snapshot, "quotas")
        if over:
            who = "" if is_urgent() else "the background's share of "
            if tell:
                log.warning(
                    "%s: %s%d requests in %.0f h spent; not asked for %.0f min",
                    host,
                    who,
                    allowed,
                    budget.window / 3600,
                    wait / 60,
                )
            raise OverBudget(f"{host}: {who}its quota is spent", request=request)

    @staticmethod
    def _save(path: Path | None, snapshot: Any, what: str) -> None:
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(snapshot))
            os.replace(tmp, path)
        except OSError as err:
            log.warning("%s not written to %s: %s", what, path, err)

    # -- the day's tally -----------------------------------------------------

    def keep_tally(self, path: Path) -> None:
        """The last :data:`TALLY_DAYS` days' tallies are written to ``path``
        (and read from it now), so that Diagnostyka shows a week's requests
        across updates of the server."""
        self._tally_file = path
        self._purposes_file = path.with_name("purposes.json")
        try:
            why = json.loads(self._purposes_file.read_text())
        except (OSError, ValueError):
            why = {}
        if isinstance(why, dict):
            with self._lock:
                for day, hosts in why.items():
                    if isinstance(hosts, dict) and day not in self._purposes:
                        self._purposes[day] = {
                            host: {str(k): int(v) for k, v in counts.items()}
                            for host, counts in hosts.items()
                            if isinstance(counts, dict)
                        }
        try:
            saved = json.loads(path.read_text())
        except (OSError, ValueError):
            return
        if not isinstance(saved, dict):
            return
        with self._lock:
            for day, hosts in saved.items():
                if not isinstance(hosts, dict) or day in self._days:
                    continue
                self._days[day] = {
                    host: [int(n) for n in row][: len(TALLY_FIELDS)]
                    + [0] * (len(TALLY_FIELDS) - len(row))
                    for host, row in hosts.items()
                    if isinstance(row, list)
                }
            self._forget_days()

    def _forget_days(self) -> None:
        """Lets go of days before the last :data:`TALLY_DAYS` (today too)."""
        first = time.strftime("%Y-%m-%d", time.localtime(self.wall() - (TALLY_DAYS - 1) * 86400))
        for day in [d for d in self._days if d < first]:
            del self._days[day]
        for day in [d for d in self._purposes if d < first]:
            del self._purposes[day]

    def _count(
        self,
        host: str,
        sent: int = 0,
        walls: int = 0,
        throttled: int = 0,
        failed: int = 0,
        refused: int = 0,
        size: int = 0,
        why: str | None = None,
    ) -> None:
        now = self.wall()
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        with self._lock:
            done: dict[str, list[int]] = {}
            gone = self._tally_day
            turned = day != self._tally_day
            if turned:
                done = self._days.get(gone, {}) if gone else {}
                self._tally_day = day
            row = self._days.setdefault(day, {}).setdefault(host, [0] * len(TALLY_FIELDS))
            if turned:
                self._forget_days()
            for n, value in enumerate((sent, walls, throttled, failed, refused, size)):
                row[n] += value
            if why and sent:
                counts = self._purposes.setdefault(day, {}).setdefault(host, {})
                counts[why] = counts.get(why, 0) + 1
            snapshot = None
            purposes: dict[str, dict[str, dict[str, int]]] = {}
            if self._tally_file is not None and (
                done or now - self._tally_saved >= TALLY_SAVE_EVERY
            ):
                self._tally_saved = now
                snapshot = {
                    d: {h: list(r) for h, r in hosts.items()} for d, hosts in self._days.items()
                }
                purposes = {
                    d: {h: dict(c) for h, c in hosts.items()} for d, hosts in self._purposes.items()
                }
        if snapshot is not None:
            self._save(self._tally_file, snapshot, "tallies")
            self._save(self._purposes_file, purposes, "purposes")
        if done:
            self._tell(gone, done)

    def tally(self) -> dict[str, dict[str, int]]:
        """Today's requests by host (for the log and the debug API)."""
        today = time.strftime("%Y-%m-%d", time.localtime(self.wall()))
        with self._lock:
            return {
                host: dict(zip(TALLY_FIELDS, row, strict=True))
                for host, row in self._days.get(today, {}).items()
            }

    def days(self) -> dict[str, dict[str, dict[str, int]]]:
        """The kept days' requests by host, the oldest day first."""
        with self._lock:
            self._forget_days()
            return {
                day: {h: dict(zip(TALLY_FIELDS, r, strict=True)) for h, r in hosts.items()}
                for day, hosts in sorted(self._days.items())
            }

    def purposes(self) -> dict[str, dict[str, dict[str, int]]]:
        """The kept days' requests by host and by what they were for."""
        with self._lock:
            self._forget_days()
            return {
                day: {h: dict(c) for h, c in hosts.items()}
                for day, hosts in sorted(self._purposes.items())
            }

    def by_source(self) -> list[dict[str, Any]]:
        """Requests of today and of the kept days, by source (Konfiguracja →
        Diagnostyka): what was sent, how many the source refused (bot
        walls, 429, 401/403/5xx), how many the server held back itself (a
        resting host, a spent quota), the quota and the rest still ahead.
        Hosts of no source come last, as one (``name`` None)."""
        days = self.days()
        today = time.strftime("%Y-%m-%d", time.localtime(self.wall()))
        rows: dict[str | None, dict[str, Any]] = {}

        def row(source: Source | None) -> dict[str, Any]:
            key = None if source is None else source.name
            if key not in rows:
                rows[key] = {
                    "name": key,
                    "today": dict.fromkeys(TALLY_FIELDS, 0),
                    "week": dict.fromkeys(TALLY_FIELDS, 0),
                    "quota": None,
                    "resting": 0.0,
                    "why_today": {},
                    "why_week": {},
                }
            return rows[key]

        for source in SOURCES:
            row(source)
        for day, hosts in days.items():
            for host, counts in hosts.items():
                entry = row(owner_of(host))
                for field, value in counts.items():
                    entry["week"][field] += value
                    if day == today:
                        entry["today"][field] += value
        for day, hosts in self.purposes().items():
            for host, counts in hosts.items():
                entry = row(owner_of(host))
                for why, value in counts.items():
                    entry["why_week"][why] = entry["why_week"].get(why, 0) + value
                    if day == today:
                        entry["why_today"][why] = entry["why_today"].get(why, 0) + value
        for host, budget in self.budgets.items():
            entry = row(owner_of(host))
            entry["quota"] = {
                "spent": self.spent(host),
                "of": budget.count,
                "background": budget.background,
                "hours": budget.window / 3600,
            }
        with self._lock:
            now = self.clock()
            resting = {h: until - now for h, (until, _) in self._resting.items() if until > now}
        for host, left in resting.items():
            entry = row(owner_of(host))
            entry["resting"] = max(entry["resting"], round(left))
        others = rows.pop(None, None)
        ordered = sorted(rows.values(), key=lambda r: (-r["week"]["sent"], r["name"]))
        if others is not None and others["week"]["sent"] + others["week"]["refused"]:
            ordered.append(others)
        return ordered

    @staticmethod
    def _tell(day: str, tally: dict[str, list[int]]) -> None:
        for host, (sent, walls, throttled, failed, refused, size) in sorted(
            tally.items(), key=lambda kv: -kv[1][0]
        ):
            log.info(
                "hosts %s: %s %d sent, %d walled, %d throttled, %d failed, %d refused, %.1f MB",
                day,
                host,
                sent,
                walls,
                throttled,
                failed,
                refused,
                size / 1e6,
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
        try:
            size = int(response.headers.get("content-length") or 0)
        except ValueError:
            size = 0
        wall = walled(response)
        code = response.status_code
        self._count(
            host,
            sent=1,
            walls=int(wall),
            throttled=int(code == 429),
            failed=int(not wall and (code in (401, 403) or code >= 500)),
            size=size,
            why=purpose(),
        )
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
                rest = min(rest * 2, REST_MAX) if rest else LONG_BLOCKS.get(host, REST)
                self._resting[host] = (now + rest, rest)
                self._probe_at[host] = now + (rest if host in LONG_BLOCKS else PROBE_EVERY)
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
        wait = retry_after(response) or LONG_BLOCKS.get(host)
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
guard = HostGuard(default_limit=DEFAULT_LIMIT, budgets=BUDGETS)
