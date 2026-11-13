"""Studia z zapasu: what is left of Claude's month goes on more studies
(Mateusz 2026-11-13: "Gdy miesięczny okres dobiega końca, a zostają jeszcze
środki to chciałbym je wykorzystać do przygotowania większej ilości studium
… te studia, które już wcześniej były typowane przez kuratora jako kandydaci
do studium dnia. Lub przy użyciu tych samych kryteriów.").

The owner's credit is renewed each month; what the app's limit leaves at
the end of the period is lost. In its last days (``AiConfig.leftover_days``)
the night orders studies "na później" (:meth:`Study.ask_later`: the long
questions through the Batch API, at half the price, the same models and
steps as any study and as the study of the day) for what the limit leaves
above a reserve (``leftover_reserve_usd``): the limit, less what the period
cost so far, less what the studies on their way will cost.

Which works, in this order:

1. those the curator of the study of the day found fit and did not choose
   (``daily.RUNNERS_KEY``), the newest first;
2. new shortlists by the study of the day's rules, put to the same curator
   (one Sonnet question for ten works, ``ai.study_pick``): first among the
   works the owner cares about (``cared``: Favourites, playlists, Odkrywaj),
   then among the catalogue's. The works it finds fit and no study takes
   tonight wait as in 1.

What no study takes (the works or the nights ran out) goes on the
catalogue's keywords and Polish texts (Mateusz 2026-11-13, "4"): the works
cared about first, through the Batch API (:meth:`AiWorker.order_rest`).

One work per artist a night, at most :data:`A_NIGHT`, none in the period's
last day (a batch may take a day, and what it costs then would count in the
next period). The works are those the study of the day may have
(``Daily.studyable``): no sketch, design, manuscript, photograph or poor
copy, none set aside before, none with a study already. The studies made so
tell nobody (Mateusz 2026-11-13: "dla tych automatycznych bez
powiadomień"): they are in "Studia dzieł" like any other.
"""

from __future__ import annotations

import logging
import math
import random
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from .ai.study import KIND
from .cared import REST
from .daily import score
from .library import ItemKind, PlaylistRules
from .library.artists import same_hand

if TYPE_CHECKING:
    from .ai import AiWorker
    from .ai.client import Claude
    from .ai.config import AiConfigStore
    from .daily import Daily
    from .library import Item, Library
    from .player import Player
    from .study import Study

log = logging.getLogger(__name__)

STATE_KEY = "leftover_studies"
#: What a study is reckoned to cost before one was measured here (USD):
#: the page, its details and composition by Opus through the Batch (half
#: price), the facts from the web by Sonnet at once (~0.30), the smaller
#: questions; the image model's sheet is counted in its own month.
STUDY_USD = 0.80
#: A measured cost is held within these (the measure takes in whatever
#: else the night asked about, so it errs high).
MEASURED_MIN, MEASURED_MAX = 0.30, 3.0
#: Studies ordered a night at most.
A_NIGHT = 25
#: Nothing is ordered this close to the period's end.
LAST_HOURS = 24
#: Shortlists put to the curator a night at most (about 0.03 USD each).
SHORTLISTS = 12

RUNNER, CURATOR = "runner", "curator"
#: What the rest goes on after the studies: the catalogue's keywords and
#: Polish texts (Haiku through the Batch API).
DESCRIPTIONS = ("keywords", "pl_text")


def studies(n: int) -> str:
    """ "1 studium", "3 studia", "12 studiów"."""
    if n == 1:
        return "1 studium"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} studia"
    return f"{n} studiów"


class Leftover:
    def __init__(
        self,
        library: Library,
        config: AiConfigStore,
        claude: Claude,
        ai: AiWorker,
        daily: Daily,
        study: Study,
        player: Player,
        cared: Callable[[], dict[str, int]],
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.library = library
        self.config = config
        self.claude = claude
        self.ai = ai
        self.daily = daily
        self.study = study
        self.player = player
        #: The works cared about, by id, with their rank (``Cared.ranks``).
        self.cared = cared
        self.now = now or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()

    # -- the state -----------------------------------------------------------

    def _state(self) -> dict[str, Any]:
        """This period's orders: {"period": its first day, "orders": {id:
        {"at", "from"}}, "made": [ids], "failed": [ids], "batch": {"spent",
        "ids"} (the last night's, to measure), "per_study": USD or None}."""
        start, _ = self.claude.spending.period(self.now())
        state = dict(self.library.get_state(STATE_KEY, {}))
        if state.get("period") != start.isoformat():
            # A new period: its own orders (the measure is kept).
            state = {
                "period": start.isoformat(),
                "orders": {},
                "made": [],
                "failed": [],
                "per_study": state.get("per_study"),
            }
        return state

    def _save(self, state: dict[str, Any]) -> None:
        self.library.set_state(STATE_KEY, state)

    def ordered(self, item_id: str) -> bool:
        """``item_id``'s study was ordered here (this period)."""
        return item_id in self._state().get("orders", {})

    def settle(self, item_id: str, status: str) -> bool:
        """A study ordered here is made ("ready") or not ("failed"); False
        when it was not ordered here."""
        with self._lock:
            state = self._state()
            if item_id not in state.get("orders", {}):
                return False
            key = "made" if status == "ready" else "failed"
            done = list(state.get(key) or [])
            if item_id not in done:
                state[key] = [*done, item_id]
                self._save(state)
        return True

    def _in_flight(self, state: dict[str, Any]) -> list[str]:
        """The studies ordered here not made yet, nor given up."""
        settled = set(state.get("made") or []) | set(state.get("failed") or [])
        waiting: list[str] = []
        for item_id in state.get("orders", {}):
            if item_id in settled:
                continue
            item = self.library.get(item_id)
            if item is None:
                continue
            if self.study.job.essay(item) is not None:
                continue  # made, not told yet
            if self.ai.later(KIND, item_id) or self.study.making(item_id):
                waiting.append(item_id)
        return waiting

    # -- money and time ------------------------------------------------------

    def per_study(self, state: dict[str, Any] | None = None) -> float:
        """What a study is reckoned to cost: measured here, else
        :data:`STUDY_USD`."""
        measured = (state or self._state()).get("per_study")
        return float(measured) if measured else STUDY_USD

    def window(self) -> tuple[datetime, datetime, datetime]:
        """When the studies may be ordered this period (from, until) and
        when it ends."""
        config = self.config.config
        _, end = self.claude.spending.period(self.now())
        ends = datetime(end.year, end.month, end.day, tzinfo=UTC)
        return (
            ends - timedelta(days=config.leftover_days),
            ends - timedelta(hours=LAST_HOURS),
            ends,
        )

    def free_usd(self, state: dict[str, Any] | None = None) -> float:
        """What may still go on studies: the limit, less the reserve, less
        what the period cost and what the studies on their way will."""
        state = state or self._state()
        config = self.config.config
        coming = len(self._in_flight(state)) * self.per_study(state)
        coming += self.ai.batched_usd(DESCRIPTIONS)
        return (
            config.monthly_limit_usd
            - config.leftover_reserve_usd
            - self.claude.spending.total(self.now())
            - coming
        )

    def _measure(self, state: dict[str, Any]) -> None:
        """The last night's studies all done: what they cost, each."""
        batch = state.get("batch")
        if not batch:
            return
        ids = set(batch.get("ids") or [])
        if ids & set(self._in_flight(state)):
            return  # some still on their way
        made = len(ids & set(state.get("made") or []))
        if made:
            spent = self.claude.spending.total(self.now()) - float(batch.get("spent") or 0.0)
            spent -= float(batch.get("other") or 0.0)  # the catalogue's descriptions
            each = min(max(spent / made, MEASURED_MIN), MEASURED_MAX)
            state["per_study"] = round(each, 4)
            log.info("leftover studies: %d made, about %.2f USD each", made, each)
        state.pop("batch", None)

    # -- the night ---------------------------------------------------------

    def enabled(self) -> bool:
        return bool(self.config.config.leftover and self.study.job.enabled())

    def at_night(self, quiet: Callable[[], bool] = lambda: True) -> tuple[int, str]:
        """Orders what the period's rest pays for: how many, and what it
        did in Polish."""
        if not self.enabled():
            return 0, "wyłączone"
        now = self.now()
        opens, closes, _ = self.window()
        if now < opens:
            return 0, f"od {opens.date():%d.%m}"
        if now >= closes:
            return 0, "ostatnia doba okresu"
        with self._lock:
            state = self._state()
            self._measure(state)
            self._save(state)
        each = self.per_study(state)
        free = self.free_usd(state)
        count = min(A_NIGHT, math.floor(free / each)) if free > 0 else 0
        picked = self.candidates(count, quiet) if count > 0 else []
        spent = self.claude.spending.total(now)
        ordered: list[str] = []
        for item, source in picked:
            if not self.study.ask_later(item):
                continue
            ordered.append(item.id)
            with self._lock:
                state = self._state()
                state["orders"][item.id] = {"at": now.isoformat(), "from": source}
                self._save(state)
        self.daily.drop_runners_up(set(ordered))
        # What no study will take goes on the catalogue's keywords and
        # Polish texts (Mateusz 2026-11-13, "4"): when the studies ran out
        # of works or money tonight, or on the window's last night.
        rest = free - len(ordered) * each
        last = now + timedelta(days=1) >= closes
        described = 0
        described_usd = 0.0
        if rest > 0 and (len(ordered) < count or count == 0 or last):
            before = self.ai.batched_usd(DESCRIPTIONS)
            described = self.ai.order_rest(DESCRIPTIONS, rest, self._cared_first)
            described_usd = max(self.ai.batched_usd(DESCRIPTIONS) - before, 0.0)
        if ordered:
            with self._lock:
                state = self._state()
                if not state.get("batch"):
                    state["batch"] = {"spent": spent, "ids": ordered, "other": described_usd}
                self._save(state)
        log.info(
            "leftover studies: %.2f USD free, %d ordered (%s); %d questions about the "
            "catalogue (about %.2f USD)",
            free,
            len(ordered),
            ", ".join(ordered) or "none",
            described,
            described_usd,
        )
        parts = []
        if ordered:
            parts.append(f"zamówione {studies(len(ordered))}, ok. {len(ordered) * each:.2f} USD")
        if described:
            parts.append(f"opisy katalogu: {described}, ok. {described_usd:.2f} USD")
        if not parts:
            if free < each:
                return 0, f"brak wolnych środków ({max(free, 0):.2f} USD)"
            return 0, "brak kandydatów"
        return len(ordered), "; ".join(parts)

    def _cared_first(self, items: list[Item]) -> list[Item]:
        """The works cared about first, kept ones before shown ones."""
        ranks = self.cared()
        return sorted(items, key=lambda i: ranks.get(i.id, REST))

    # -- which works -------------------------------------------------------

    def candidates(
        self, count: int, quiet: Callable[[], bool] = lambda: True
    ) -> list[tuple[Item, str]]:
        """Up to ``count`` works for a study, one per artist, with where
        each came from (:data:`RUNNER`, :data:`CURATOR`)."""
        daily = self.daily
        fits = daily.studyable()
        picked: list[tuple[Item, str]] = []
        hands: list[str] = []

        def free_hand(item: Item) -> bool:
            return not any(same_hand(item.artist, a) for a in hands)

        def take(item: Item, source: str) -> None:
            picked.append((item, source))
            hands.append(item.artist)

        stale: set[str] = set()
        for item_id in reversed(list(daily.runners_up())):
            if len(picked) >= count:
                break
            item = self.library.get(item_id)
            if item is None or item.excluded or not fits(item):
                stale.add(item_id)
            elif free_hand(item):
                take(item, RUNNER)
        daily.drop_runners_up(stale)
        if len(picked) >= count or daily.claude is None:
            return picked

        today = self.now().date()
        rng = random.Random(today.toordinal())
        taste = self.player.taste()
        asked: set[str] = set()
        lists = 0
        for pool in (self._cared_pool, self._catalogue_pool):
            ranked: list[Item] | None = None
            while len(picked) < count and lists < SHORTLISTS and quiet():
                if ranked is None:
                    ranked = pool(today, fits, taste, rng)
                ranked = [i for i in ranked if i.id not in asked and free_hand(i)]
                shortlist = daily.shortlist(ranked)
                if not shortlist:
                    break
                lists += 1
                asked |= {i.id for i, _ in shortlist}
                choice = daily.judge(shortlist, "leftover studies")
                if choice is None:  # the curator does not answer tonight
                    return picked
                spare = []
                for item in choice.fit:
                    if len(picked) < count and free_hand(item):
                        take(item, CURATOR)
                    else:
                        spare.append(item)
                daily.keep_runners_up(spare, today)
        return picked

    def _cared_pool(
        self,
        today: date,
        fits: Callable[[Item], bool],
        taste: list[str],
        rng: random.Random,
    ) -> list[Item]:
        """The works cared about the study may be of: kept ones first, each
        rank by the study of the day's rules."""
        ranks = self.cared()
        if not ranks:
            return []
        works = self.library.query(PlaylistRules(kinds=[ItemKind.ARTWORK]), proposing=True)[1]
        pool = [i for i in works if i.id in ranks and fits(i)]
        values = {i.id: score(i, today, taste, rng) for i in pool}
        return sorted(pool, key=lambda i: (ranks[i.id], -values[i.id]))

    def _catalogue_pool(
        self,
        today: date,
        fits: Callable[[Item], bool],
        taste: list[str],
        rng: random.Random,
    ) -> list[Item]:
        """The catalogue's works drawn as for the study of the day."""
        pool = [i for i in self.daily.pool(today, []) if fits(i)]
        values = {i.id: score(i, today, taste, rng) for i in pool}
        return sorted(pool, key=lambda i: values[i.id], reverse=True)

    # -- for the app ---------------------------------------------------------

    def view(self) -> dict[str, Any]:
        state = self._state()
        opens, closes, ends = self.window()
        start, _ = self.claude.spending.period(self.now())
        in_flight = self._in_flight(state)
        return {
            "period_start": start.isoformat(),
            "period_end": (ends - timedelta(days=1)).date().isoformat(),
            "opens": opens.date().isoformat(),
            "closes": (closes - timedelta(seconds=1)).date().isoformat(),  # its last day
            "open": opens <= self.now() < closes,
            "free_usd": round(max(self.free_usd(state), 0.0), 2),
            "per_study_usd": round(self.per_study(state), 2),
            "measured": bool(state.get("per_study")),
            "ordered": len(state.get("orders", {})),
            "in_flight": len(in_flight),
            "made": len(state.get("made") or []),
            "failed": len(state.get("failed") or []),
            "candidates": len(self.daily.runners_up()),
        }
