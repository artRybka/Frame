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

The owner can also start the tasks by day (Konfiguracja → Zadania nocne,
Mateusz 2026-11-10): one of them or the whole night, at once, without
waiting for the app to be left alone; one run at a time, the night's
included.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from datetime import time as clock
from typing import TYPE_CHECKING, Any
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
#: Each task's last run: when, how long, how it ended (by task name).
RUNS_KEY = "night_runs"
#: Tasks started by day run this long at most.
ASKED_FOR = timedelta(hours=2)
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
    #: Started by the owner by day: the app in use does not hold it up.
    asked: bool = False

    def open(self) -> bool:
        """Whether there is time left for more work."""
        return not self.stop.is_set() and time.monotonic() < self.deadline

    def quiet(self) -> bool:
        """Waits until nobody uses the app (but for a run the owner asked
        for) and nothing goes to the frame; False when the night ended
        meanwhile."""
        while self.open():
            if (self.asked or idle_for() >= QUIET_FOR) and not self.busy():
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
    #: What the app calls it (Konfiguracja → Zadania nocne).
    label: str = ""
    #: Asks Claude (through the Batch API, at the owner's key's cost).
    paid: bool = False


@dataclass
class Run:
    """The tasks running now, at night or asked for by day."""

    tasks: list[str]
    asked: bool
    started_at: str  # ISO, UTC
    stop: threading.Event = field(default_factory=threading.Event)
    current: str | None = None
    done: list[str] = field(default_factory=list)


def _outcome(value: object) -> dict[str, Any]:
    """A task's answer as the app shows it: how many it did (``count``,
    for an int) and whether it found nothing to do (False or 0)."""
    count = value if isinstance(value, int) and not isinstance(value, bool) else None
    return {"count": count, "nothing": value is False or count == 0}


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
        #: One run at a time: the night's, or one the owner asked for.
        self._running = threading.Lock()
        self.current: Run | None = None

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
        """Every task once, while there is time; tonight is then done. A run
        the owner asked for is waited for first."""
        deadline = time.monotonic() + seconds  # not moved by a run waited for
        with self._running:
            run = Run([t.name for t in self.tasks], asked=False, started_at=_utc_now())
            night = self._go(run, self.tasks, deadline)
            if not self._stop.is_set():
                self.service.library.set_state(DONE_KEY, night_of.isoformat())
        return night

    def start(self, names: list[str] | None = None) -> Run | None:
        """The tasks ``names`` (all of them, in the night's order, for None)
        started now, in the background, without waiting for the app to be
        left alone; None while a run goes on. Unknown names: ValueError."""
        known = {t.name: t for t in self.tasks}
        unknown = [n for n in names or [] if n not in known]
        if unknown:
            raise ValueError(", ".join(unknown))
        if names is None:
            chosen = list(self.tasks)
        else:
            wanted = set(names)
            chosen = [t for t in self.tasks if t.name in wanted]
        if not self._running.acquire(blocking=False):
            return None
        run = Run([t.name for t in chosen], asked=True, started_at=_utc_now())
        self.current = run

        def go() -> None:
            try:
                self._go(run, chosen, time.monotonic() + ASKED_FOR.total_seconds())
            finally:
                self._running.release()

        log.info("night: %s asked for now", ", ".join(run.tasks) or "nothing")
        threading.Thread(target=go, name="night-now", daemon=True).start()
        return run

    def cancel(self) -> bool:
        """Stops a run the owner asked for after its current task's step;
        False when none goes on (the night's own goes on)."""
        run = self.current
        if run is None or not run.asked:
            return False
        run.stop.set()
        return True

    def _go(self, run: Run, tasks: list[NightTask], deadline: float) -> Night:
        self.current = run
        stop = run.stop
        if self._stop.is_set():
            stop.set()
        night = Night(
            stop,
            deadline,
            busy=lambda: self.service.player.busy,
            asked=run.asked,
        )
        started = time.monotonic()
        try:
            for task in tasks:
                if not night.quiet():
                    log.info("night: %s and the rest left for the next night", task.name)
                    break
                run.current = task.name
                began = time.monotonic()
                failed = False
                result: object = None
                try:
                    result = task.run(night)
                except Exception:
                    failed = True
                    log.exception("night: %s failed", task.name)
                night.took[task.name] = took = time.monotonic() - began
                log.info("night: %s in %.1f s", task.name, took)
                run.done.append(task.name)
                self._remember(task.name, took, failed, result, run.asked)
            if not stop.is_set():
                log.info("night: done in %.0f s", time.monotonic() - started)
        finally:
            run.current = None
            self.current = None
        return night

    def _remember(self, name: str, took: float, failed: bool, result: object, asked: bool) -> None:
        library = self.service.library
        runs = dict(library.get_state(RUNS_KEY, {}) or {})
        runs[name] = {
            "at": _utc_now(),
            "took": round(took, 1),
            "failed": failed,
            **_outcome(result),
            "asked": asked,
        }
        library.set_state(RUNS_KEY, runs)

    def view(self) -> dict[str, Any]:
        """The tasks for the app: their order and last runs, what runs now
        and when the night is."""
        runs = self.service.library.get_state(RUNS_KEY, {}) or {}
        run = self.current
        return {
            "tasks": [
                {
                    "name": t.name,
                    "label": t.label or t.name,
                    "paid": t.paid,
                    "last": runs.get(t.name),
                }
                for t in self.tasks
            ],
            "running": None
            if run is None
            else {
                "tasks": run.tasks,
                "asked": run.asked,
                "started_at": run.started_at,
                "current": run.current,
                "done": run.done,
                "stopping": run.stop.is_set(),
            },
            "night_start": NIGHT_START.strftime("%H:%M"),
            "night_end": NIGHT_END.strftime("%H:%M"),
            "last_night": self.service.library.get_state(DONE_KEY, None),
        }

    def stop(self) -> None:
        self._stop.set()
        run = self.current
        if run is not None:
            run.stop.set()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def tasks(service: FrameService) -> list[NightTask]:
    """The night's tasks, in order: first what changes the catalogue, then
    what is worked out from it."""
    from .library import courtauld, dumps, loc_index, louvre, met_index, nga, rijks_index
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

    def rijks(night: Night) -> int:
        """The Rijksmuseum's collection read over OAI-PMH a few hours a
        night until whole, then what changed every two months
        (library/rijks_index.py)."""
        if "rijks" not in service.importer.sources():
            return 0
        return rijks_index.read_at_night(service.settings.data_dir, night.quiet, night.sleep)

    def themes(night: Night) -> None:
        discover_api.work_out_cards(service, force=True)

    def suggestions(night: Night) -> None:
        discover_api.suggestion_rows(service)  # the owner's
        # Everyone's Propozycje dnia for the new day, the frame's first.
        users = [service.player.suggestions_user, *(u.id for u in service.users.users())]
        for user in dict.fromkeys(users):
            service.player.day_picks(user)

    dump_labels = {
        "aic": "Spis Art Institute of Chicago",
        "cma": "Spis Cleveland Museum of Art",
        "si": "Spis Smithsonian",
        "wellcome": "Spis Wellcome Collection",
    }
    return [
        NightTask("tidy", tidy, "Porządki w plikach"),
        NightTask("catalogue", player.grow_at_night, "Nowe dzieła do katalogu"),
        NightTask("grouping", grouping, "Kopie razem i podpowiedzi Szukaj"),
        # Keywords and Polish texts nobody waits for, through the Batch API
        # at half the price (their answers come in by day).
        NightTask(
            "language model",
            lambda night: service.ai.order_night(),
            "Słowa kluczowe i polskie teksty",
            paid=True,
        ),
        NightTask(
            "nga",
            lambda night: nga.refresh_at_night(service.settings.data_dir),
            "Spis National Gallery of Art",
        ),
        NightTask(
            "courtauld",
            lambda night: courtauld.refresh_at_night(service.settings.data_dir),
            "Spis Courtauld Gallery",
        ),
        NightTask(
            "louvre",
            lambda night: louvre.refresh_at_night(service.settings.data_dir),
            "Spis Luwru",
        ),
        NightTask(
            "met",
            lambda night: met_index.refresh_at_night(service.settings.data_dir),
            "Spis Metropolitan Museum",
        ),
        NightTask(
            "loc",
            lambda night: loc_index.refresh_at_night(service.settings.data_dir),
            "Spis Biblioteki Kongresu",
        ),
        *(NightTask(f"{key} dump", dump(key), dump_labels.get(key, "")) for key in dumps.DUMPS),
        NightTask("births", lambda night: births_at_night(service, night), "Urodziny artystów"),
        NightTask(
            "artist people",
            lambda night: service.artist_people.at_night(night.quiet),
            "Kim są artyści",
        ),
        NightTask("daily", daily, "Studium dnia", paid=True),
        NightTask("playlists", playlists, "Liczniki playlist"),
        NightTask("frame line", frame_line, "Kolejka ramki"),
        NightTask("sharper", sharper, "Ostrzejsze kopie"),
        NightTask("museums", museums, "Gdzie wiszą dzieła"),
        NightTask(
            "museum places",
            lambda night: service.museum_places.at_night(night.quiet),
            "Miasta muzeów",
        ),
        NightTask("places", places, "Miejsca zdjęć"),
        # Waits for its batch while the night is quiet (an hour at most),
        # so that "themes" works out the new cards' covers.
        NightTask("curator", service.curator.at_night, "Dziś dla Ciebie", paid=True),
        NightTask("themes", themes, "Karty Odkrywaj"),
        NightTask("suggestions", suggestions, "Propozycje dnia"),
        # What the pictures of the nights before could not settle: Haiku,
        # then Haiku as the critic, a quarter of an hour at most for each
        # batch (a later answer is collected the next night). Before
        # "rijks": after it the night is often over (2026-11-11: "twins"
        # began at 04:55, the judge was left for the next night).
        NightTask("twins judge", service.twins_judge.at_night, "Sędzia powtórek", paid=True),
        # Hours at most (NIGHT_SECONDS), after what the morning needs.
        NightTask("rijks", rijks, "Spis Rijksmuseum"),
        # Copies under other titles and details, by their pictures: what the
        # night has time for, the rest the next (library/twins.py).
        NightTask("twins", lambda night: service.twins.at_night(night.quiet), "Powtórki i detale"),
        # The catalogue's gatekeeper and the night audit: the same, each
        # with its critic (ai/gatekeeper.py, ai/audit.py).
        NightTask("gatekeeper", service.gatekeeper.at_night, "Strażnik katalogu", paid=True),
        NightTask("audit", service.audit.at_night, "Nocny przegląd dzieł", paid=True),
        # Once a month: Commons' files with a tile set ("Pod lupą").
        NightTask("tile sets", service.player.tile_sets_at_night, "Kafle „Pod lupą”"),
        # Last: downloads, gently, in whatever time the night has left.
        NightTask("kept originals", service.kept.at_night, "Oryginały Twoich dzieł"),
    ]
