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
from dataclasses import dataclass, field, replace
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
#: The tasks the last night did not get to (their names).
LEFT_KEY = "night_left"
#: The package of the tidying (:data:`GROUPS`): its batches are ordered
#: before its first task, and those of its tasks the last night did not get
#: to go first the next.
TIDYING = "duplicates"
#: New works are taken in for this long a night at most (seconds; the
#: batch under way is finished). Mateusz 2026-11-11, after the audit: the
#: tidying first; on 2026-11-11 the catalogue took 1 h 43 min of the night
#: and the copies got five minutes.
CATALOGUE_FOR = 45 * 60.0
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

#: Works whose technique is looked up in one night, at most ...
MEDIA_A_NIGHT = 600
#: ... each taking this long at most (seconds).
MEDIUM_WAIT = 60.0

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

    def within(self, seconds: float | None) -> Night:
        """This night as a task sees it that may take ``seconds`` of it at
        most (None: as long as the night lasts)."""
        if seconds is None:
            return self
        return replace(self, deadline=min(self.deadline, time.monotonic() + seconds))


@dataclass
class NightTask:
    name: str
    run: Callable[[Night], object]
    #: What the app calls it (Konfiguracja → Zadania nocne).
    label: str = ""
    #: Asks Claude (through the Batch API, at the owner's key's cost).
    paid: bool = False
    #: Its package in the app (:data:`GROUPS`).
    group: str = ""
    #: Seconds of the night it may take at most (None: what is left).
    budget: float | None = None
    #: Orders its batch before the tidying's first task (the night's own
    #: run only), so that the answer is there when its turn comes.
    ahead: Callable[[], object] | None = None


#: The tasks' packages in Konfiguracja → Zadania nocne, each started at once
#: (Mateusz 2026-11-11: "pakiety działań, np. związanych z duplikatami,
#: utrzymaniem katalogu, bo teraz lista jest długa"): key, name, what it does.
GROUPS: list[tuple[str, str, str]] = [
    (
        "catalogue",
        "Utrzymanie katalogu",
        "Nowe dzieła, porządki w plikach, kopie razem, ostrzejsze kopie i oryginały Twoich dzieł.",
    ),
    (
        "duplicates",
        "Powtórki i jakość",
        "Powtórki i detale, sędzia powtórek, strażnik katalogu, nocny przegląd "
        "i kadrowanie zdjęć dzieł. "
        "Najpierw Ulubione, playlisty i Odkrywaj.",
    ),
    (
        "descriptions",
        "Opisy i fakty",
        "Polskie teksty i słowa kluczowe, kim są artyści, gdzie wiszą dzieła, miasta i miejsca.",
    ),
    (
        "discover",
        "Odkrywaj i ramka",
        "Studium dnia, Dziś dla Ciebie, karty Odkrywaj, Propozycje dnia, playlisty, "
        "kolejka ramki i urodziny artystów.",
    ),
    (
        "indexes",
        "Spisy muzeów",
        "Lokalne spisy kolekcji (Met, NGA, Luwr, Rijksmuseum i inne), "
        "odświeżane, gdy przyjdzie pora.",
    ),
]


@dataclass
class Run:
    """The tasks running now, at night or asked for by day."""

    tasks: list[str]
    asked: bool
    started_at: str  # ISO, UTC
    stop: threading.Event = field(default_factory=threading.Event)
    current: str | None = None
    done: list[str] = field(default_factory=list)


@dataclass
class Done:
    """A task's answer told in words for the app ("41 kopii, 14 detali"),
    with how many it did."""

    count: int
    text: str


def _outcome(value: object) -> dict[str, Any]:
    """A task's answer as the app shows it: how many it did (``count``,
    for an int) and whether it found nothing to do (False or 0); a
    :class:`Done` says it in words too (``summary``)."""
    if isinstance(value, Done):
        return {"count": value.count, "nothing": value.count == 0, "summary": value.text}
    count = value if isinstance(value, int) and not isinstance(value, bool) else None
    return {"count": count, "nothing": value is False or count == 0}


def plural(n: int, one: str, few: str, many: str) -> str:
    """ "1 kopia", "3 kopie", "5 kopii": a count with its Polish form."""
    if n == 1:
        return f"{n} {one}"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} {few}"
    return f"{n} {many}"


def _listed(parts: list[object], empty: str) -> str:
    """The parts said (a count of 0 or none left out), else ``empty``."""
    return ", ".join(p for p in parts if isinstance(p, str) and p) or empty


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
            tasks = self.in_turn()
            run = Run([t.name for t in tasks], asked=False, started_at=_utc_now())
            night = self._go(run, tasks, deadline)
            if not self._stop.is_set():
                self.service.library.set_state(DONE_KEY, night_of.isoformat())
        return night

    def in_turn(self) -> list[NightTask]:
        """The night's tasks in tonight's order: the tidying's tasks the
        last night did not get to take the places of those it did (a night
        cut short would else give every night to the first of them)."""
        left = set(self.service.library.get_state(LEFT_KEY, []) or [])
        tidying = [t for t in self.tasks if t.group == TIDYING]
        waiting = [t for t in tidying if t.name in left]
        if not waiting or len(waiting) == len(tidying):
            return list(self.tasks)
        turns = iter(waiting + [t for t in tidying if t.name not in left])
        return [next(turns) if t.group == TIDYING else t for t in self.tasks]

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
        ordered = run.asked  # by day each task orders its own
        left: list[str] = []
        try:
            for at, task in enumerate(tasks):
                if not night.quiet():
                    log.info("night: %s and the rest left for the next night", task.name)
                    left = [t.name for t in tasks[at:]]
                    break
                if not ordered and task.group == TIDYING:
                    ordered = True
                    self._order_ahead(tasks[at:])
                run.current = task.name
                began = time.monotonic()
                grouped = _groupings(self.service)
                failed = False
                result: object = None
                try:
                    result = task.run(night.within(task.budget))
                except Exception:
                    failed = True
                    log.exception("night: %s failed", task.name)
                night.took[task.name] = took = time.monotonic() - began
                again = _regrouped(self.service, grouped)
                log.info("night: %s in %.1f s%s", task.name, took, again)
                run.done.append(task.name)
                self._remember(task.name, took, failed, result, run.asked)
            if not run.asked:
                self.service.library.set_state(LEFT_KEY, left)
            if not stop.is_set():
                log.info("night: done in %.0f s", time.monotonic() - started)
        finally:
            run.current = None
            self.current = None
        return night

    @staticmethod
    def _order_ahead(tasks: list[NightTask]) -> None:
        """The batches of the tasks to come ordered now: their answers are
        there by the time the pictures have been looked at."""
        for task in tasks:
            if task.ahead is None:
                continue
            try:
                task.ahead()
            except Exception:
                log.exception("night: %s could not order ahead", task.name)

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
                    "group": t.group or None,
                    "last": runs.get(t.name),
                }
                for t in self.tasks
            ],
            "groups": [
                {
                    "key": key,
                    "label": label,
                    "about": about,
                    "tasks": [t.name for t in self.tasks if t.group == key],
                }
                for key, label, about in GROUPS
                if any(t.group == key for t in self.tasks)
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


def _groupings(service: FrameService) -> tuple[int, float, int, float]:
    return (*service.library.regrouped(), *service.library.regrouped_in_part())


def _regrouped(service: FrameService, before: tuple[int, float, int, float]) -> str:
    """ ", the works regrouped 5 time(s) in 17.2 s, 41 change(s) regrouped
    in part in 0.3 s" since ``before``, for the log of a task (the app's
    requests waited for each whole regrouping, for none in part); empty
    when neither."""
    made, seconds, parts, part_seconds = _groupings(service)
    told = ""
    if made > before[0]:
        told += f", the works regrouped {made - before[0]} time(s) in {seconds - before[1]:.1f} s"
    if parts > before[2]:
        took = part_seconds - before[3]
        told += f", {parts - before[2]} change(s) regrouped in part in {took:.1f} s"
    return told


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

    def leftover(night: Night) -> Done:
        return Done(*service.leftover.at_night(night.quiet))

    def grouping(night: Night) -> None:
        library.works()  # copies of one work together, after the turnover
        library.hearts_to_best()  # a heart follows the work to its best copy
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
        archives = service.cared.first(service.sharper.archive_works(), lambda i: [i.id])
        archives = archives[:ARCHIVES_A_NIGHT]
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
        # Favourites, playlists and Discover first (Mateusz 2026-11-11).
        items = service.cared.first(service.library.all_items(), lambda i: [i.id])
        for item in items:
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

    def media(night: Night) -> int:
        """How the library's works are made, for those whose source does
        not say and nobody looked up yet (frame_server.media)."""
        looked = 0
        # Favourites, playlists and Discover first (Mateusz 2026-11-11).
        items = service.cared.first(service.library.all_items(), lambda i: [i.id])
        for item in items:
            if looked == MEDIA_A_NIGHT or not night.quiet():
                break
            if service.media.known(item) is not None:
                continue
            try:
                service.media.soon(item).result(MEDIUM_WAIT)
            except FutureTimeout:
                break
            looked += 1
        return looked

    def read_again(night: Night) -> int:
        """Works kept with a type or maker an older reading of their
        museum's record got wrong, read again (``Importer.read_again``)."""
        return service.importer.read_again(night.quiet)

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

    def twins(night: Night) -> Done:
        began = _utc_now()
        seen = service.twins.at_night(night.quiet)
        made = service.twins.log.since(began)
        parts: list[object] = [
            plural(seen, "obraz obejrzany", "obrazy obejrzane", "obrazów obejrzanych"),
            made["copy"] and plural(made["copy"], "kopia", "kopie", "kopii"),
            made["detail"] and plural(made["detail"], "detal", "detale", "detali"),
            made["scene"]
            and plural(
                made["scene"], "zdjęcie na ścianie", "zdjęcia na ścianie", "zdjęć na ścianie"
            ),
        ]
        return Done(seen, _listed(parts, ""))

    def twins_judge(night: Night) -> Done:
        began = _utc_now()
        service.twins_judge.at_night(night)
        tally = service.twins_judge.tally
        made = service.twins.log.since(began)
        written = made["judge"]
        parts: list[object] = [
            written and plural(written, "para połączona", "pary połączone", "par połączonych"),
            tally.get("kept") and plural(tally["kept"], "para osobno", "pary osobno", "par osobno"),
            tally.get("rejected")
            and plural(
                tally["rejected"],
                "odrzucona przez krytyka",
                "odrzucone przez krytyka",
                "odrzuconych przez krytyka",
            ),
        ]
        return Done(written, _listed(parts, "nic nowego od sędziego"))

    def critic_night(job: Any, written_words: tuple[str, str, str]) -> Callable[[Night], Done]:
        def run(night: Night) -> Done:
            job.at_night(night)
            tally = job.tally
            looked = tally.get("nothing", 0) + tally.get("claims", 0)
            written = tally.get("written", 0)
            parts: list[object] = [
                looked
                and plural(looked, "dzieło obejrzane", "dzieła obejrzane", "dzieł obejrzanych"),
                written and plural(written, *written_words),
                tally.get("rejected")
                and plural(
                    tally["rejected"],
                    "odrzucone przez krytyka",
                    "odrzucone przez krytyka",
                    "odrzuconych przez krytyka",
                ),
            ]
            return Done(written, _listed(parts, "nic nowego"))

        return run

    dump_labels = {
        "aic": "Spis Art Institute of Chicago",
        "cma": "Spis Cleveland Museum of Art",
        "si": "Spis Smithsonian",
        "wellcome": "Spis Wellcome Collection",
    }
    cat, dup, text, disc, idx = "catalogue", "duplicates", "descriptions", "discover", "indexes"
    return [
        NightTask("tidy", tidy, "Porządki w plikach", group=cat),
        # Keywords, Polish texts and the sheets' pen sketches drawn anew
        # (``ai.redraw``) nobody waits for, through the Batch API at half
        # the price (their answers come in by day).
        NightTask(
            "language model",
            lambda night: service.ai.order_night(),
            "Słowa kluczowe i polskie teksty",
            paid=True,
            group=text,
        ),
        NightTask(
            "nga",
            lambda night: nga.refresh_at_night(service.settings.data_dir),
            "Spis National Gallery of Art",
            group=idx,
        ),
        NightTask(
            "courtauld",
            lambda night: courtauld.refresh_at_night(service.settings.data_dir),
            "Spis Courtauld Gallery",
            group=idx,
        ),
        NightTask(
            "louvre",
            lambda night: louvre.refresh_at_night(service.settings.data_dir),
            "Spis Luwru",
            group=idx,
        ),
        NightTask(
            "met",
            lambda night: met_index.refresh_at_night(service.settings.data_dir),
            "Spis Metropolitan Museum",
            group=idx,
        ),
        NightTask(
            "loc",
            lambda night: loc_index.refresh_at_night(service.settings.data_dir),
            "Spis Biblioteki Kongresu",
            group=idx,
        ),
        *(
            NightTask(f"{key} dump", dump(key), dump_labels.get(key, ""), group=idx)
            for key in dumps.DUMPS
        ),
        NightTask(
            "births", lambda night: births_at_night(service, night), "Urodziny artystów", group=disc
        ),
        NightTask(
            "artist people",
            lambda night: service.artist_people.at_night(night.quiet),
            "Kim są artyści",
            group=text,
        ),
        NightTask("daily", daily, "Studium dnia", paid=True, group=disc),
        # In the period's last days, what Claude's limit leaves goes on more
        # studies (leftover.py), through the Batch API.
        NightTask("leftover", leftover, "Studia z zapasu", paid=True, group=disc),
        NightTask("playlists", playlists, "Liczniki playlist", group=disc),
        NightTask("frame line", frame_line, "Kolejka ramki", group=disc),
        NightTask("sharper", sharper, "Ostrzejsze kopie", group=cat),
        NightTask("museums", museums, "Gdzie wiszą dzieła", group=text),
        NightTask("media", media, "Technika dzieł", group=text),
        NightTask("read again", read_again, "Rodzaj i autor czytane ponownie", group=text),
        NightTask(
            "museum places",
            lambda night: service.museum_places.at_night(night.quiet),
            "Miasta muzeów",
            group=text,
        ),
        NightTask("places", places, "Miejsca zdjęć", group=text),
        # Waits for its batch while the night is quiet (an hour at most),
        # so that "themes" works out the new cards' covers.
        NightTask("curator", service.curator.at_night, "Dziś dla Ciebie", paid=True, group=disc),
        NightTask("themes", themes, "Karty Odkrywaj", group=disc),
        NightTask("suggestions", suggestions, "Propozycje dnia", group=disc),
        # The tidying, Favourites, playlists and Discover first (cared.py),
        # before the catalogue takes anything in and before "rijks"
        # (2026-11-11: the catalogue took 1 h 43 min and the index the rest;
        # the copies got 5 minutes, the gatekeeper and the audit never ran).
        # The three that ask Claude order their batches before the first of
        # these four begins (``ahead``) and collect them when their turn
        # comes; those the last night did not get to go first
        # (``NightQueue.in_turn``).
        # Copies under other titles and details, by their pictures: what the
        # night has time for (40 minutes at most), the rest the next.
        NightTask("twins", twins, "Powtórki i detale", group=dup),
        # The catalogue's gatekeeper before the judge: what it sets aside
        # as no artwork the judge is not asked about (ai/gatekeeper.py).
        NightTask(
            "gatekeeper",
            critic_night(service.gatekeeper, ("odłożone", "odłożone", "odłożonych")),
            "Strażnik katalogu",
            paid=True,
            group=dup,
            ahead=service.gatekeeper.ahead,
        ),
        # What the pictures could not settle, tonight's included: Haiku,
        # then Haiku as the critic, a quarter of an hour at most for each
        # batch (a later answer is collected the next night).
        NightTask(
            "twins judge",
            twins_judge,
            "Sędzia powtórek",
            paid=True,
            group=dup,
            ahead=service.twins_judge.ahead,
        ),
        # The night audit, with its critic (ai/audit.py).
        NightTask(
            "audit",
            critic_night(service.audit, ("do sprawdzenia", "do sprawdzenia", "do sprawdzenia")),
            "Nocny przegląd dzieł",
            paid=True,
            group=dup,
            ahead=service.audit.ahead,
        ),
        # Museum photographs cut down to the work: Haiku picks the works
        # with a frame, an easel or a board around them, Opus sets the
        # corners (ai/crops.py).
        NightTask(
            "crops",
            critic_night(service.crops, ("przycięte", "przycięte", "przyciętych")),
            "Kadrowanie zdjęć dzieł",
            paid=True,
            group=dup,
            ahead=service.crops.ahead,
        ),
        # Once a month: Commons' files with a tile set ("Pod lupą").
        NightTask("tile sets", service.player.tile_sets_at_night, "Kafle „Pod lupą”", group=cat),
        # Downloads, gently, a limited number a night.
        NightTask("kept originals", service.kept.at_night, "Oryginały Twoich dzieł", group=cat),
        # New works once the tidying is done, three quarters of an hour at
        # most; then the groups of copies and Szukaj's hints made anew, so
        # that the morning's first look does not wait for them.
        NightTask(
            "catalogue",
            player.grow_at_night,
            "Nowe dzieła do katalogu",
            group=cat,
            budget=CATALOGUE_FOR,
        ),
        NightTask("grouping", grouping, "Odświeżenie grup kopii i podpowiedzi Szukaj", group=cat),
        # Last: the Rijksmuseum's index, in whatever time the night has left
        # (2.5 hours at most, NIGHT_SECONDS), until it is whole.
        NightTask("rijks", rijks, "Spis Rijksmuseum", group=idx),
    ]
