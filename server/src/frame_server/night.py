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
from concurrent.futures import TimeoutError as FutureTimeout
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
#: Sharper copies are looked for, at night, for this many next pictures.
SHARPER_AHEAD = 20
#: Works shown in an art archive's old photograph (Foto Marburg's faded
#: slides) looked at for another copy in one night, at most.
ARCHIVES_A_NIGHT = 40
#: One look for a sharper copy takes this long at most (seconds).
SHARPER_WAIT = 600.0

#: Works whose museum is looked up in one night, at most ...
HOLDERS_A_NIGHT = 300
#: ... each taking this long at most (seconds).
HOLDER_WAIT = 60.0

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
        started = time.monotonic()
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
        if not self._stop.is_set():
            self.service.library.set_state(DONE_KEY, night_of.isoformat())
            log.info("night: done in %.0f s", time.monotonic() - started)
        return night

    def stop(self) -> None:
        self._stop.set()


def tasks(service: FrameService) -> list[NightTask]:
    """The night's tasks, in order: first what changes the catalogue, then
    what is worked out from it."""
    from .library import courtauld, dumps, loc_index, louvre, met_index, nga
    from .notifications import births_at_night
    from .web import discover_api

    player, library = service.player, service.library

    def tidy(night: Night) -> None:
        player.trim_cache()

    def daily(night: Night) -> None:
        service.daily.tick()

    def grouping(night: Night) -> None:
        library.works()  # copies of one work together, after the turnover
        library.term_index()  # the suggestions while typing

    def playlists(night: Night) -> None:
        library.recount()

    def frame_line(night: Night) -> None:
        player.catch_up()

    def sharper(night: Night) -> int:
        """The frame's next pictures from sharper copies, where there are;
        then the library's works shown in an art archive's old photograph,
        from any other copy (their slides' colours have faded)."""
        looked = 0
        archives = service.sharper.archive_works()[:ARCHIVES_A_NIGHT]
        for item in [*player.upcoming(SHARPER_AHEAD), *archives]:
            if service.sharper.status(item) is not None:
                continue  # known
            if not night.quiet():
                break
            try:
                service.sharper.soon(item).result(SHARPER_WAIT)
            except FutureTimeout:
                break  # a museum this slow: the rest another night
            looked += 1
        return looked

    def museums(night: Night) -> int:
        """Which museums the library's works from Commons, Openverse and
        WikiArt are in, for those nobody looked up yet."""
        looked = 0
        for item in service.library.all_items():
            if looked == HOLDERS_A_NIGHT or not night.quiet():
                break
            if service.holders.known(item) is not None:
                continue
            try:
                service.holders.soon(item).result(HOLDER_WAIT)
            except FutureTimeout:
                break
            looked += 1
        return looked

    def places(night: Night) -> int:
        """The towns of photos from the camera roll and older albums (their
        coordinates come with the original)."""
        return service.places.fill()

    def dump(key: str) -> Callable[[Night], object]:
        """A museum's published dump read again every two months
        (library/dumps.py), for the sources on offer only."""

        def refresh(night: Night) -> bool:
            if key not in service.importer.sources():
                return False
            return dumps.refresh_at_night(key, service.settings.data_dir)

        return refresh

    def themes(night: Night) -> None:
        discover_api.work_out_cards(service, force=True)

    def suggestions(night: Night) -> None:
        discover_api.suggestion_rows(service)  # the owner's
        # Everyone's Propozycje dnia for the new day, the frame's first.
        users = [service.player.suggestions_user, *(u.id for u in service.users.users())]
        for user in dict.fromkeys(users):
            service.player.day_picks(user)

    return [
        NightTask("tidy", tidy),
        NightTask("catalogue", player.grow_at_night),
        NightTask("grouping", grouping),
        NightTask("nga", lambda night: nga.refresh_at_night(service.settings.data_dir)),
        NightTask("courtauld", lambda night: courtauld.refresh_at_night(service.settings.data_dir)),
        NightTask("louvre", lambda night: louvre.refresh_at_night(service.settings.data_dir)),
        NightTask("met", lambda night: met_index.refresh_at_night(service.settings.data_dir)),
        NightTask("loc", lambda night: loc_index.refresh_at_night(service.settings.data_dir)),
        *(NightTask(f"{key} dump", dump(key)) for key in dumps.DUMPS),
        NightTask("births", lambda night: births_at_night(service, night)),
        NightTask("artist people", lambda night: service.artist_people.at_night(night.quiet)),
        NightTask("daily", daily),
        NightTask("playlists", playlists),
        NightTask("frame line", frame_line),
        NightTask("sharper", sharper),
        NightTask("museums", museums),
        NightTask("museum places", lambda night: service.museum_places.at_night(night.quiet)),
        NightTask("places", places),
        # Waits for its batch while the night is quiet (an hour at most),
        # so that "themes" works out the new cards' covers.
        NightTask("curator", service.curator.at_night),
        NightTask("themes", themes),
        NightTask("suggestions", suggestions),
        # Last: downloads, gently, in whatever time the night has left.
        NightTask("kept originals", service.kept.at_night),
    ]
