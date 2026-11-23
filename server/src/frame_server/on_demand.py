"""Na żądanie, w trybie zwykłym: one of the month's rest's uses run now for
an amount the owner gives (Mateusz 2026-11-17: "Dodaj mi opcję wykonania
wskazanych zadań „na żądanie, w trybie zwykłym” za określoną kwotę. Czyli
np. podaję 50 $ na polskie słowa kluczowe i opisy i mogę je puścić od
razu.").

The night sends these through the Batch API (half the price, answers within
hours) and only in the period's last days. A run on demand asks now, one
work after another on a few threads, at the full price: it goes on until the
amount is spent, nothing waits any more, the month's limit less its reserve
(``AiConfig.leftover_reserve_usd``) is reached, or the owner stops it.

What it costs is what its own answers cost (``Spending.meter``: the
questions asked on its threads, nothing the background asks meanwhile); a
work is begun only while what is left of the amount pays for it (each one
reckoned at what the run's works cost so far). The same limits hold as for
any question: ``Claude.ask`` refuses past the month's limit, and a run is
never let past the reserve the night keeps (``Leftover.free_usd``), whose
money a run still to spend is taken out of (and the night leaves a use
running now alone).

One run of a use at a time; runs of different uses may go together. A run
does not outlive the server: one cut short by a restart is told as such.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import anthropic

from .ai.client import AiUnavailable
from .leftover import LABELS, NEVER, TEXTS, task

if TYPE_CHECKING:
    from .ai import AiWorker
    from .ai.client import Claude
    from .ai.config import AiConfigStore
    from .leftover import Leftover
    from .library import Library

log = logging.getLogger(__name__)

STATE_KEY = "on_demand_runs"
#: What may be run on demand, in Konfiguracja's words (``leftover.LABELS``).
USES = TEXTS
#: The questions asked at once.
THREADS = dict.fromkeys(TEXTS, 4)
#: What one run may be given (USD).
MIN_USD, MAX_USD = 1.0, 500.0
#: The normal price over the Batch API's.
FULL_PRICE = 2.0
#: Works done before what they cost is taken as what the next ones will.
MEASURE_AFTER = 5
#: How often the run is written down while it goes (s).
SAVE_SECONDS = 5.0
#: The API failing this many times in a row ends the run.
FAILS_IN_A_ROW = 8
#: The pause after a failed question (s).
PAUSE_SECONDS = 10.0

#: Why a run ended, as the app says it.
SPENT, EMPTY, LIMIT, STOPPED, ERRORS, RESTART, OFF, COUNT = (
    "kwota wykorzystana",
    "nic więcej nie czeka",
    "osiągnięty limit miesiąca (z zapasem)",
    "zatrzymane",
    "błędy API",
    "przerwane: serwer uruchomiony ponownie",
    "wyłączone w ustawieniach",
    "liczba na noc osiągnięta",
)


class OnDemandError(Exception):
    """Why a run cannot start, in Polish for the app."""


@dataclass
class Plan:
    """How a use runs now."""

    #: About what one work costs at the full price, before any is measured.
    each: Callable[[], float]
    #: The works waiting, in the order they are done.
    waiting: Callable[[], list[str]]
    #: Does one work: True when it was changed (cut, described), False when
    #: looked at and left, None when there was nothing to do after all.
    one: Callable[[str], bool | None]
    #: Its switches allow it.
    able: Callable[[], bool]


class _Run:
    def __init__(
        self, key: str, usd: float, record: dict[str, Any], limit: int | None = None
    ) -> None:
        self.key = key
        self.usd = usd
        #: Works at most (a night's run: the task's number a night).
        self.limit = limit
        self.record = record
        self.lock = threading.Lock()
        self.stopping = False
        self.queue: list[str] = []
        self.next = 0
        #: Works begun and not finished, and the money they hold.
        self.busy = 0
        self.fails = 0
        self.saved = 0.0


class OnDemand:
    def __init__(
        self,
        library: Library,
        claude: Claude,
        config: AiConfigStore,
        ai: AiWorker,
        leftover: Leftover,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.library = library
        self.claude = claude
        self.config = config
        self.ai = ai
        self.leftover = leftover
        self.now = now or (lambda: datetime.now(UTC))
        self._runs: dict[str, _Run] = {}
        self._lock = threading.Lock()
        self._settle_restart()

    # -- what may run ----------------------------------------------------------

    def _plans(self) -> dict[str, Plan]:
        plans: dict[str, Plan] = {}
        config, ai = self.config, self.ai

        def text_plan(kind: str) -> Plan:
            def one(item_id: str) -> bool | None:
                item = self.library.get(item_id)
                job = ai.jobs.get(kind)
                if item is None or job is None or not job.enabled() or not job.in_library(item):
                    return None
                if job.fresh(item, self.library.note(item_id, kind)):
                    return None
                ai.run_one(kind, item_id)
                return True

            def waiting() -> list[str]:
                if kind not in ai.jobs or not config.enabled(kind):
                    return []
                return self.leftover._cared_ids(ai.library_waiting(kind)[0])

            return Plan(
                each=lambda: FULL_PRICE * self.leftover._text_usd(kind),
                waiting=waiting,
                one=one,
                able=lambda: config.enabled(kind),
            )

        for kind in TEXTS:
            if kind in ai.jobs:
                plans[kind] = text_plan(kind)
        return plans

    def each_usd(self, key: str) -> float | None:
        """About what one work costs at the full price (None: not here)."""
        plan = self._plans().get(key)
        return None if plan is None else round(plan.each(), 4)

    def running(self, key: str) -> bool:
        with self._lock:
            run = self._runs.get(key)
        return run is not None and "ended" not in run.record

    def held_usd(self) -> float:
        """What the runs going now may still spend (the night leaves it)."""
        with self._lock:
            runs = list(self._runs.values())
        return sum(
            max(r.usd - float(r.record["spent_usd"]), 0.0) for r in runs if "ended" not in r.record
        )

    def free_usd(self) -> float:
        """What a new run may be given: what the night could spend now (the
        limit less the reserve, the period's spending, what is ordered and
        what the runs going now hold)."""
        return max(self.leftover.free_usd(), 0.0)

    # -- a run ---------------------------------------------------------------

    def start(
        self, key: str, usd: float, limit: int | None = None, night: bool = False
    ) -> dict[str, Any]:
        """Starts ``key`` for ``usd`` (and at most ``limit`` works); its
        record. ``night``: the night starts it, the task's mode being
        "Zwykły" (Mateusz 2026-11-17, "Zadania"). Raises
        :class:`OnDemandError` with the reason in Polish."""
        plan = self._plans().get(key)
        if plan is None or key not in USES:
            raise OnDemandError("Tego zadania nie da się uruchomić na żądanie.")
        if not self.config.api_key:
            raise OnDemandError("Brak klucza API Anthropic.")
        if not plan.able():
            raise OnDemandError("To zadanie jest wyłączone w ustawieniach Claude.")
        if task(self.config.config, key).when == NEVER:
            raise OnDemandError("To zadanie jest wyłączone w Zadaniach.")
        if not MIN_USD <= usd <= MAX_USD:
            raise OnDemandError(f"Kwota od {MIN_USD:.0f} do {MAX_USD:.0f} USD.")
        if self.running(key):
            raise OnDemandError("To zadanie już działa.")
        free = self.free_usd()
        if usd > free + 0.005:
            reserve = self.config.config.leftover_reserve_usd
            raise OnDemandError(
                f"Do limitu miesiąca zostało ok. {_usd(free)} (po odjęciu zapasu "
                f"{_usd(reserve)} i tego, co już zamówione)."
            )
        record: dict[str, Any] = {
            "key": key,
            "usd": round(usd, 2),
            "spent_usd": 0.0,
            "done": 0,
            "changed": 0,
            "failed": 0,
            "waiting": None,
            "each_usd": round(plan.each(), 4),
            "started": self.now().isoformat(timespec="seconds"),
        }
        if night:
            record["night"] = True
        if limit:
            record["limit"] = limit
        run = _Run(key, usd, record, limit)
        with self._lock:
            self._runs[key] = run
        self._save(run, force=True)
        threading.Thread(
            target=self._go, args=(run, plan), name=f"on-demand-{key}", daemon=True
        ).start()
        log.info("on demand: %s started for %.2f USD%s", key, usd, " (night)" if night else "")
        return dict(record)

    def stop(self, key: str) -> bool:
        """The run of ``key`` stops after the works it is asking about;
        False when none runs."""
        with self._lock:
            run = self._runs.get(key)
        if run is None or "ended" in run.record:
            return False
        with run.lock:
            run.stopping = True
            run.record["why"] = STOPPED
        return True

    def _go(self, run: _Run, plan: Plan) -> None:
        try:
            run.queue = plan.waiting()
        except Exception:
            log.exception("on demand: %s could not count what waits", run.key)
            run.queue = []
        with run.lock:
            run.record["waiting"] = len(run.queue)
        threads = [
            threading.Thread(
                target=self._work, args=(run, plan), name=f"on-demand-{run.key}-{n}", daemon=True
            )
            for n in range(THREADS.get(run.key, 1))
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        with run.lock:
            run.record.setdefault("why", EMPTY)
            run.record["ended"] = self.now().isoformat(timespec="seconds")
        self._save(run, force=True)
        record = run.record
        self.leftover.count(run.key, int(record["done"]), float(record["spent_usd"]))
        log.info(
            "on demand: %s ended (%s): %d works, %d changed, %d failed, %.2f of %.2f USD",
            run.key,
            record["why"],
            record["done"],
            record["changed"],
            record["failed"],
            record["spent_usd"],
            run.usd,
        )

    def _each(self, run: _Run, plan: Plan) -> float:
        """What the next work is reckoned to cost: the run's so far, once a
        few were done, else the plan's."""
        done = int(run.record["done"])
        if done >= MEASURE_AFTER and run.record["spent_usd"] > 0:
            return max(float(run.record["spent_usd"]) / done, 0.0001)
        return plan.each()

    def _take(self, run: _Run, plan: Plan) -> str | None:
        """The next work to do, or None with why the run ends."""
        reserve = self.config.config.leftover_reserve_usd
        with run.lock:
            if run.stopping:
                return None
            if not plan.able():
                run.record.setdefault("why", OFF)
                return None
            each = self._each(run, plan)
            held = (run.busy + 1) * each
            if float(run.record["spent_usd"]) + held > run.usd:
                run.record.setdefault("why", SPENT)
                return None
            if self.claude.budget_left() - reserve < held:
                run.record.setdefault("why", LIMIT)
                return None
            if run.limit is not None and run.next >= run.limit:
                run.record.setdefault("why", COUNT)
                return None
            if run.next >= len(run.queue):
                run.record.setdefault("why", EMPTY)
                return None
            item_id = run.queue[run.next]
            run.next += 1
            run.busy += 1
            return item_id

    def _work(self, run: _Run, plan: Plan) -> None:
        while True:
            item_id = self._take(run, plan)
            if item_id is None:
                return
            result: bool | None = None
            failed = api = False
            with self.claude.spending.meter() as counted:
                try:
                    result = plan.one(item_id)
                except AiUnavailable as err:
                    log.info("on demand: %s stopped at %s (%s)", run.key, item_id, err)
                    with run.lock:
                        run.stopping = True
                        run.record.setdefault("why", LIMIT)
                except anthropic.APIError as err:
                    log.warning("on demand: %s for %s: %s", run.key, item_id, err)
                    failed = api = True
                except Exception:
                    log.exception("on demand: %s for %s failed", run.key, item_id)
                    failed = True
            with run.lock:
                run.busy -= 1
                run.record["spent_usd"] = round(float(run.record["spent_usd"]) + counted[0], 6)
                if failed:
                    run.record["failed"] += 1
                elif result is not None:
                    run.record["done"] += 1
                    run.record["changed"] += int(bool(result))
                if api:
                    run.fails += 1
                    if run.fails >= FAILS_IN_A_ROW:
                        run.stopping = True
                        run.record.setdefault("why", ERRORS)
                elif not failed:
                    run.fails = 0
            self._save(run)
            if api:
                time.sleep(PAUSE_SECONDS)

    # -- the state -------------------------------------------------------------

    def _state(self) -> dict[str, Any]:
        return dict(self.library.get_state(STATE_KEY, {}))

    def _save(self, run: _Run, force: bool = False) -> None:
        now = time.monotonic()
        with run.lock:
            if not force and now - run.saved < SAVE_SECONDS:
                return
            run.saved = now
            record = dict(run.record)
        with self._lock:
            state = self._state()
            state[run.key] = record
            self.library.set_state(STATE_KEY, state)

    def _settle_restart(self) -> None:
        """Runs the last server left going are told as cut short."""
        state = self._state()
        changed = False
        for record in state.values():
            if isinstance(record, dict) and "ended" not in record:
                record["ended"] = self.now().isoformat(timespec="seconds")
                record["why"] = RESTART
                changed = True
        if changed:
            self.library.set_state(STATE_KEY, state)

    def view(self, key: str) -> dict[str, Any] | None:
        """The run of ``key`` going now, or the last one, as the app shows
        it; None when there was none."""
        with self._lock:
            run = self._runs.get(key)
        if run is not None:
            with run.lock:
                record = dict(run.record)
                left = max(len(run.queue) - run.next, 0) if run.queue else None
        else:
            kept = self._state().get(key)
            if not isinstance(kept, dict):
                return None
            record = kept
            left = None
        return {
            "label": LABELS[key][0],
            "usd": float(record.get("usd", 0.0)),
            "spent_usd": round(float(record.get("spent_usd", 0.0)), 2),
            "done": int(record.get("done", 0)),
            "changed": int(record.get("changed", 0)),
            "failed": int(record.get("failed", 0)),
            "waiting": record.get("waiting"),
            "left": left,
            "running": "ended" not in record,
            "stopping": "ended" not in record and record.get("why") == STOPPED,
            "started": record.get("started"),
            "ended": record.get("ended"),
            "why": record.get("why"),
            "night": bool(record.get("night")),
        }


def _usd(usd: float) -> str:
    """ "12,30 USD"."""
    return f"{usd:.2f} USD".replace(".", ",")
