"""The server's night: heavy work in one queue while nobody looks.

The server is one Python process: work that goes through the whole
catalogue takes its time from the app's requests (at the app's start they
waited for each other up to 16 s, 2026-11-02). And every change of the
catalogue makes what was worked out from it (playlists' counts, Discover's
cards, the frame's line) stale, to be worked out again when someone looks.

So (Mateusz, 2026-11-02): the work that changes the catalogue or goes
through it whole runs at night, one task after another; by day the server
works out only what someone opens or changes. A task waits while the app is
in use or a picture goes to the frame, and the log says how long each took
("night: <task> in <n> s"). A night missed (the NAS off) is made up a few
minutes after the start, with the same waits.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from datetime import time as clock
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from .service import FrameService

log = logging.getLogger(__name__)

#: The night's work starts at this time of the frame's time zone ...
NIGHT_START = clock(1, 30)
#: ... and what is not done by this time waits for the next night.
NIGHT_END = clock(6, 0)
#: A task waits while the app was used this recently (seconds) ...
QUIET_FOR = 120.0
#: ... looking again this often.
QUIET_LOOK = 10.0
#: A night missed is made up this long after a start (seconds) ...
CATCH_UP_AFTER = 300.0
#: ... taking this long at most.
CATCH_UP_FOR = timedelta(hours=2)
#: The night last worked through (its date: the day it began).
DONE_KEY = "night_done"

#: When the app last asked the server something (time.monotonic()).
_last_used = float("-inf")


def used() -> None:
    """The app asked the server something: the night's work waits."""
    global _last_used
    _last_used = time.monotonic()


def idle_for() -> float:
    """Seconds since the app last asked the server something."""
    return time.monotonic() - _last_used


@dataclass
class Night:
    """One night's run, as its tasks see it."""

    stop: threading.Event
    #: Until when (time.monotonic()).
    deadline: float
    #: Something else that must not be slowed down (a picture going to the frame).
    busy: Callable[[], bool] = lambda: False
    took: dict[str, float] = field(default_factory=dict)

    def open(self) -> bool:
        """Whether there is time left for more work."""
        return not self.stop.is_set() and time.monotonic() < self.deadline

    def quiet(self) -> bool:
        """Waits until nobody uses the app and nothing goes to the frame;
        False when the night ended meanwhile."""
        while self.open():
            if idle_for() >= QUIET_FOR and not self.busy():
                return True
            self.stop.wait(QUIET_LOOK)
        return False

    def sleep(self, seconds: float) -> bool:
        """Waits ``seconds``; False when stopped."""
        return not self.stop.wait(seconds)


@dataclass
class NightTask:
    name: str
    run: Callable[[Night], object]


class NightQueue:
    def __init__(
        self,
        service: FrameService,
        tasks: list[NightTask],
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.service = service
        self.tasks = tasks
        self._now = now or (lambda: datetime.now(self.tz()))
        self._stop = threading.Event()
        self.running = False

    def tz(self) -> ZoneInfo:
        return self.service.player.settings.tz()

    # -- when ----------------------------------------------------------------

    def last_night(self, now: datetime) -> date:
        """The night that began last (its date)."""
        day = now.date()
        return day if now.time() >= NIGHT_START else day - timedelta(days=1)

    def until_next(self, now: datetime) -> float:
        """Seconds until the next night begins."""
        start = datetime.combine(now.date(), NIGHT_START, now.tzinfo)
        if start <= now:
            start = datetime.combine(now.date() + timedelta(days=1), NIGHT_START, now.tzinfo)
        return (start - now).total_seconds()

    def left(self, now: datetime) -> float:
        """Seconds left of tonight's work (0 by day)."""
        if not NIGHT_START <= now.time() < NIGHT_END:
            return 0.0
        end = datetime.combine(now.date(), NIGHT_END, now.tzinfo)
        return (end - now).total_seconds()

    def missed(self, now: datetime) -> bool:
        """The last night was not worked through (the server was off)."""
        done = self.service.library.get_state(DONE_KEY, "")
        return done < self.last_night(now).isoformat()

    # -- running ---------------------------------------------------------------

    def run(self) -> None:
        """Makes up a missed night a few minutes after the start, then works
        every night."""
        if self._stop.wait(CATCH_UP_AFTER):
            return
        now = self._now()
        if self.missed(now):
            seconds = self.left(now) or CATCH_UP_FOR.total_seconds()
            self.work(self.last_night(now), seconds)
        while not self._stop.wait(self.until_next(self._now())):
            now = self._now()
            self.work(self.last_night(now), self.left(now) or 60.0)

    def work(self, night_of: date, seconds: float) -> Night:
        """Every task once, while there is time; tonight is then done."""
        night = Night(self._stop, time.monotonic() + seconds, busy=lambda: self.service.player.busy)
        self.running = True
        started = time.monotonic()
        try:
            for task in self.tasks:
                if not night.quiet():
                    log.info("night: %s and the rest left for the next night", task.name)
                    break
                began = time.monotonic()
                try:
                    task.run(night)
                except Exception:
                    log.exception("night: %s failed", task.name)
                night.took[task.name] = took = time.monotonic() - began
                log.info("night: %s in %.1f s", task.name, took)
        finally:
            self.running = False
        if not self._stop.is_set():
            self.service.library.set_state(DONE_KEY, night_of.isoformat())
            log.info("night: done in %.0f s", time.monotonic() - started)
        return night

    def stop(self) -> None:
        self._stop.set()


def tasks(service: FrameService) -> list[NightTask]:
    """The night's tasks, in order: first what changes the catalogue, then
    what is worked out from it."""
    from .library import nga
    from .notifications import births_at_night

    player, library = service.player, service.library

    def tidy(night: Night) -> None:
        player.trim_cache()

    def daily(night: Night) -> None:
        service.daily.tick()

    def playlists(night: Night) -> None:
        library.recount()

    return [
        NightTask("tidy", tidy),
        NightTask("catalogue", player.grow_at_night),
        NightTask("nga", lambda night: nga.refresh_at_night(service.settings.data_dir)),
        NightTask("births", lambda night: births_at_night(service, night)),
        NightTask("daily", daily),
        NightTask("playlists", playlists),
    ]
