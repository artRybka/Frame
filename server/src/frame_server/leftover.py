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

Since Mateusz 2026-11-15 ("Lista z kolejnością") the studies are one of
the uses the rest may go on (:data:`USES`), each switched on or off and put
in an order in Konfiguracja; the night pays them from the top while the
money lasts. A use with more to do than a night allows (:attr:`Use.cap`)
keeps what its coming nights in the window will need, so a use below it
gets only what is left over then (as the catalogue's texts waited for the
studies before).

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
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import partial
from typing import TYPE_CHECKING, Any

from .ai import refresh as refresh_module
from .ai import text_review as review_module
from .ai.config import TaskSettings
from .ai.study import KIND
from .cared import REST
from .daily import score
from .library import ItemKind, PlaylistRules
from .library.artists import same_hand

if TYPE_CHECKING:
    from .ai import AiWorker
    from .ai.audit import Audit
    from .ai.client import Claude
    from .ai.config import AiConfig, AiConfigStore, TaskUpdate
    from .ai.crops import Crops
    from .ai.refresh import StudyRefresh
    from .ai.text_review import TextReview
    from .daily import Daily
    from .library import Item, Library
    from .on_demand import OnDemand
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
#: The catalogue's keywords and Polish texts (Haiku through the Batch API).
DESCRIPTIONS = ("keywords", "pl_text")

#: What the rest may go on, in the order it has unless the owner sets
#: another (Mateusz 2026-11-15): the cheap work on what he has first.
REFRESH, CROPS, REVIEW, STUDIES, KEYWORDS, POLISH, AUDIT = (
    "refresh",
    "crops",
    "text_review",
    "studies",
    "keywords",
    "pl_text",
    "audit",
)
#: The saved texts' review is the Polish texts' since 2026-11-17 (Mateusz:
#: "Przegląd zapisanych opisów - czy to nie powielenie nocnego przeglądu i
#: częściowo zaszłość?"): the works without a text first, then the older
#: texts written anew.
USES = (REFRESH, CROPS, STUDIES, KEYWORDS, POLISH, AUDIT)
#: Tasks that are also the night's own portion, its switch in ``AiConfig``
#: (Mateusz 2026-11-17: "„Nocny przegląd” chyba trzeba połączyć z „Większy
#: nocny przegląd”"): every night the switch's portion, and in the period's
#: last days more from the rest when the owner wants it (``more_at_end``).
BASE = {CROPS: "crops", AUDIT: "audit"}
#: The catalogue's tidying (Mateusz 2026-11-17, "Porządki katalogu"): the
#: gatekeeper and the judge of copies, each its switch in ``AiConfig``, run
#: every night, only when the owner asks, or not at all; nothing of the
#: rest goes on them.
TIDY = "tidy"
TIDY_SWITCHES = ("gatekeeper", "twins_judge")
#: Every task Zadania lists.
TASKS = (TIDY, *USES)
#: The night's tasks a task's "Uruchom teraz" starts when it has no run of
#: its own on demand (``on_demand``): through the Batch API, as at night.
NIGHT_TASKS = {TIDY: ["gatekeeper", "twins judge"], AUDIT: ["audit"]}
#: The catalogue's keywords and its Polish texts, each a task of its own
#: since Mateusz 2026-11-17 ("czy to nie dwa, odrębne procesy?"); the use
#: they were one of before, whose settings and place both take on.
TEXTS = (KEYWORDS, POLISH)
OLD_TEXTS = "descriptions"
LABELS = {
    REFRESH: (
        "Uzupełnienie studiów",
        "Fakty z sieci do studiów sprzed nich; tekst przepisany tam, gdzie wnoszą dużo.",
    ),
    CROPS: (
        "Kadrowanie",
        "Zdjęcia z muzeów przycięte do samego dzieła, bez ramy, sztalugi i tektury wokół, "
        "najpierw Ulubione i playlisty.",
    ),
    REVIEW: (
        "Przegląd zapisanych opisów",
        "Tłumaczenia, które nie mówią o dziele, i notki sprzed pięciu stylów.",
    ),
    STUDIES: (
        "Nowe studia",
        "Dzieła typowane przez kuratora Studium dnia, najpierw z Ulubionych i playlist.",
    ),
    KEYWORDS: (
        "Słowa kluczowe",
        "Dzieła katalogu, które ich jeszcze nie mają, najpierw Ulubione i playlisty. "
        "Po nich szukają Szukaj i inteligentne playlisty.",
    ),
    POLISH: (
        "Polskie opisy",
        "Polski tytuł i opis dzieł katalogu, które ich jeszcze nie mają, "
        "najpierw Ulubione i playlisty; potem starsze teksty pisane od nowa.",
    ),
    AUDIT: (
        "Przegląd dzieł",
        "Losowe dzieła: tytuł, data, opis i obraz; co nie pasuje, trafia do „Do sprawdzenia”.",
    ),
    TIDY: (
        "Porządki katalogu",
        "Strażnik odkłada znaczki, strony z tekstem i zdjęcia sal, które przyszły jako dzieła; "
        "sędzia rozstrzyga, czy dwa podobne obrazy to kopia, detal czy to samo dzieło.",
    ),
}
#: How the night's summary names them.
SHORT = {
    REFRESH: "uzupełnione studia",
    CROPS: "kadrowanie",
    REVIEW: "przegląd opisów",
    STUDIES: "nowe studia",
    KEYWORDS: "słowa kluczowe katalogu",
    POLISH: "polskie opisy katalogu",
    AUDIT: "nocny przegląd",
}
#: What the other uses are counted under in the spending, left out of what
#: the studies are measured to cost.
OTHER_KINDS = (
    refresh_module.KIND,
    review_module.KIND,
    "crops",
    "audit",
    *DESCRIPTIONS,
)
#: The crops: Opus's corners (about a cent a work through the Batch API)
#: and Haiku's look around the work (a hundredth of a cent), more a night
#: at most, from the month's rest.
CROP_USD, CROP_JUDGE_USD = 0.01, 0.0002
CROPS_A_NIGHT, CROP_LOOKS_A_NIGHT = 540, 2400
#: How long the count of the catalogue's texts waiting is kept (s).
TEXTS_FRESH = 600.0
#: The audit: Haiku and its critic about a work (a fifth of a cent).
AUDIT_USD = 0.002
AUDITS_A_NIGHT = 270
#: What the owner may choose as the catalogue's texts a night
#: (``AiConfig.leftover_texts_a_night``, Mateusz 2026-11-15).
TEXTS_A_NIGHT_OPTIONS = (250, 500, 1000, 2000, 5000, 10000)

#: When a use runs (``AiConfig.tasks``, Mateusz 2026-11-17, "Zadania"): in
#: the period's last days (as before), every night, only when the owner
#: runs it now, or never.
IN_REST, EVERY_NIGHT, ONLY_ASKED, NEVER = "rest", "night", "demand", "off"
WHENS = (IN_REST, EVERY_NIGHT, ONLY_ASKED, NEVER)
#: Works a night the owner may choose, each use's (none: it has no number
#: of a night).
A_NIGHT_CHOICES: dict[str, tuple[int, ...]] = {
    KEYWORDS: TEXTS_A_NIGHT_OPTIONS,
    POLISH: TEXTS_A_NIGHT_OPTIONS,
    CROPS: (100, 270, 540, 1000, 2000),
    STUDIES: (5, 10, 25, 50),
    AUDIT: (100, 270, 500, 1000),
}
#: What a night and a period may spend on a use, as the app offers it (USD).
NIGHT_USD_CHOICES = (1.0, 2.0, 5.0, 10.0, 20.0, 50.0)
PERIOD_USD_CHOICES = (5.0, 10.0, 20.0, 50.0, 100.0, 200.0)
#: What may ask now instead of through the Batch API (``on_demand.USES``).
NORMAL = (*TEXTS, CROPS)


def task(config: AiConfig, key: str) -> TaskSettings:
    """``key``'s settings, its ``when`` filled in: off when the owner's
    older list has it off, else the period's last days. A task with the
    night's own portion is every night while its switch is on
    (:data:`BASE`); the catalogue's tidying as its switches."""
    if key == TIDY:
        return _tidy(config)
    if key in BASE:
        return _with_base(config, key)
    return _kept(config, key)


def _kept(config: AiConfig, key: str) -> TaskSettings:
    kept = config.tasks.get(key)
    off = key in config.leftover_off
    if kept is None and key in TEXTS:
        # as the one task the catalogue's texts were before
        kept = config.tasks.get(OLD_TEXTS)
        off = off or OLD_TEXTS in config.leftover_off
    kept = kept or TaskSettings()
    if kept.when is not None:
        return kept
    return kept.model_copy(update={"when": NEVER if off else IN_REST})


def _tidy(config: AiConfig) -> TaskSettings:
    """The gatekeeper and the judge: off while both switches are off, else
    as the owner set it here (every night unless he chose "when asked")."""
    on = any(getattr(config, switch) for switch in TIDY_SWITCHES)
    kept = config.tasks.get(TIDY)
    if not on:
        return TaskSettings(when=NEVER)
    if kept is not None and kept.when == ONLY_ASKED:
        return TaskSettings(when=ONLY_ASKED)
    return TaskSettings(when=EVERY_NIGHT)


def _with_base(config: AiConfig, key: str) -> TaskSettings:
    """A task with the night's own portion as one: its switch (off or not),
    when its portion runs, and its use of the rest (``more_at_end``).
    Settings kept before they were one are read so: the switch on is every
    night, more at the end when the rest's use was on."""
    kept = _kept(config, key)
    base = bool(getattr(config, BASE[key]))
    if kept.more_at_end is None:  # the switch and the rest's use apart
        more = kept.when in (IN_REST, EVERY_NIGHT)
        return kept.model_copy(update={"when": EVERY_NIGHT if base else NEVER, "more_at_end": more})
    if not base and kept.when != NEVER:  # switched off elsewhere
        return kept.model_copy(update={"when": NEVER})
    if base and kept.when == NEVER:  # switched on elsewhere
        return kept.model_copy(update={"when": EVERY_NIGHT})
    return kept


def rest_when(config: AiConfig, key: str) -> str:
    """When the rest may go on ``key``: a task with the night's own portion
    every night takes from it only in the period's last days, if the owner
    wants more then."""
    settings = task(config, key)
    when = settings.when or IN_REST
    if key in BASE and when == EVERY_NIGHT:
        return IN_REST if settings.more_at_end else NEVER
    return when


def whens(key: str) -> list[str]:
    """What the owner may choose for ``key``: "when asked" only for what
    can be run now (on demand, or the night's own tasks)."""
    if key == TIDY:
        return [EVERY_NIGHT, ONLY_ASKED, NEVER]
    if key in NORMAL or key in NIGHT_TASKS:
        return list(WHENS)
    return [IN_REST, EVERY_NIGHT, NEVER]


def set_task(store: AiConfigStore, key: str, update: TaskUpdate) -> TaskSettings:
    """The owner's change of ``key``; raises ValueError for what it cannot
    be. The older list of those off is kept in step (``leftover_off``), and
    the switches of what is one with its task (``BASE``, ``TIDY``)."""
    if key not in TASKS:
        raise ValueError("Nie ma takiego zadania.")
    config = store.config
    changes = update.model_dump(exclude_none=True)
    if changes.get("when") is not None and changes["when"] not in whens(key):
        raise ValueError("To zadanie nie ma takiej pory.")
    if key == TIDY:
        if set(changes) - {"when"}:
            raise ValueError("Porządki katalogu mają tylko porę.")
        when = changes.get("when", task(config, key).when)
        tasks = dict(config.tasks)
        tasks[TIDY] = TaskSettings(when=when)
        switches = {s: bool(getattr(config, s)) for s in TIDY_SWITCHES}
        if when == NEVER:
            switches = dict.fromkeys(TIDY_SWITCHES, False)
        elif not any(switches.values()):
            switches = dict.fromkeys(TIDY_SWITCHES, True)
        store.set_tasks(tasks, **switches)
        return task(store.config, key)
    if "more_at_end" in changes and key not in BASE:
        raise ValueError("To zadanie nie ma nocnej porcji.")
    for name in ("a_night", "night_usd", "period_usd"):
        if name in changes and not changes[name]:
            changes[name] = None  # 0: no limit of its own
    if changes.get("mode") == "normal" and key not in NORMAL:
        raise ValueError("To zadanie działa tylko przez Batch.")
    if changes.get("a_night") is not None and key not in A_NIGHT_CHOICES:
        raise ValueError("To zadanie nie ma liczby na noc.")
    settings = task(config, key).model_copy(update=changes)
    tasks = dict(config.tasks)
    also: dict[str, object] = {}
    if OLD_TEXTS in tasks or OLD_TEXTS in config.leftover_off or OLD_TEXTS in config.leftover_order:
        # the catalogue's texts' one task becomes two, each as it was
        for text in TEXTS:
            tasks[text] = task(config, text)
        tasks.pop(OLD_TEXTS, None)
        order = list(config.leftover_order)
        if OLD_TEXTS in order:
            at = order.index(OLD_TEXTS)
            order[at : at + 1] = [k for k in TEXTS if k not in order]
        also["leftover_order"] = order
    if key in BASE:
        # one with its switch: on unless off; when its portion runs is the
        # night's job's to ask (``AiConfigStore.task_when``)
        if settings.more_at_end is None:
            settings = settings.model_copy(update={"more_at_end": True})
        also[BASE[key]] = settings.when != NEVER
    tasks[key] = settings
    store.set_tasks(tasks, **also)
    config = store.config
    off = [k for k in USES if rest_when(config, k) == NEVER]
    store.set_tasks(dict(config.tasks), leftover_off=off)
    return settings


def uses(config: AiConfig) -> list[tuple[str, bool]]:
    """The uses in the owner's order, each on (the night may order it) or
    off; those his list lacks in their own place."""
    order: list[str] = []
    for k in dict.fromkeys(config.leftover_order):
        if k == OLD_TEXTS:  # the two in its place
            order.extend(t for t in TEXTS if t not in config.leftover_order)
        elif k in USES:
            order.append(k)
    for n, key in enumerate(USES):
        if key not in order:
            # after the one before it in USES, or first
            before = [k for k in USES[:n] if k in order]
            order.insert(order.index(before[-1]) + 1 if before else 0, key)
    return [(key, rest_when(config, key) in (IN_REST, EVERY_NIGHT)) for key in order]


@dataclass
class Use:
    """One thing the rest may go on, as the night and the app see it."""

    key: str
    #: About what one of it costs (USD).
    each: float
    #: How many wait for it (None: more than tell).
    waiting: Callable[[], int | None]
    #: Its own switch is on (and what it needs is there).
    able: Callable[[], bool]
    #: Orders what ``usd`` pays for tonight: how many, about what they will
    #: cost, and whether it has more to do than it took.
    run: Callable[[float], tuple[int, float, bool]]
    #: How many a night at most (None: no limit of a night).
    cap: int | None = None
    #: What the owner may set ``cap`` to in the app (None: fixed).
    caps: tuple[int, ...] | None = None


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
        refresh: StudyRefresh | None = None,
        review: TextReview | None = None,
        crops: Crops | None = None,
        audit: Audit | None = None,
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
        self.refresh = refresh
        self.review = review
        self.crops = crops
        self.audit = audit
        self._lock = threading.Lock()
        #: The catalogue's texts waiting, as last worked out (when, count, USD).
        self._texts_kept: tuple[float, dict[str, tuple[int, float]]] | None = None
        self._counting = False
        #: The runs on demand (``frame_server.on_demand``), set once made:
        #: what they may still spend is not the night's, and the night
        #: leaves a use running now alone.
        self.on_demand: OnDemand | None = None

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
        """What may still go on the uses: the limit, less the reserve, less
        what the period cost and what is on its way will."""
        state = state or self._state()
        config = self.config.config
        coming = len(self._in_flight(state)) * self.per_study(state)
        coming += self.ai.batched_usd(DESCRIPTIONS)
        coming += self._coming_usd()
        if self.on_demand is not None:
            coming += self.on_demand.held_usd()
        return (
            config.monthly_limit_usd
            - config.leftover_reserve_usd
            - self.claude.spending.total(self.now())
            - coming
        )

    def _coming_usd(self) -> float:
        """What the other uses ordered and their answers will cost."""
        usd = 0.0
        if self.refresh is not None:
            view = self.refresh.view()
            usd += view["asked"] * refresh_module.EACH_USD
            usd += view["rewriting"] * refresh_module.REWRITE_USD
        if self.review is not None:
            view = self.review.view()
            usd += view["checking"] * review_module.check_usd(review_module.CHECK_NOTE_SHARE)
            usd += view["writing"] * review_module.note_usd()
        return usd

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
            now = self.now()
            spent = self.claude.spending.total(now) - float(batch.get("spent") or 0.0)
            if "kinds" in batch:
                # what the other uses' answers cost since
                then, kinds = batch["kinds"], self.claude.spending.by_kind(now)
                spent -= sum(
                    max(kinds.get(k, 0.0) - float(then.get(k, 0.0)), 0.0) for k in OTHER_KINDS
                )
            else:
                spent -= float(batch.get("other") or 0.0)  # the catalogue's descriptions
            each = min(max(spent / made, MEASURED_MIN), MEASURED_MAX)
            state["per_study"] = round(each, 4)
            log.info("leftover studies: %d made, about %.2f USD each", made, each)
        state.pop("batch", None)

    # -- the night ---------------------------------------------------------

    def enabled(self) -> bool:
        return bool(self.config.config.leftover and self.config.api_key)

    def nights_left(self) -> int:
        """The window's nights after tonight's."""
        _, closes, _ = self.window()
        return max(math.ceil((closes - self.now()) / timedelta(days=1)) - 1, 0)

    def at_night(self, quiet: Callable[[], bool] = lambda: True) -> tuple[int, str]:
        """Orders what the owner's tasks may take tonight, use by use in his
        order: those set for every night, and in the period's last days
        those set for its rest; how many studies, and what it did in
        Polish. Each takes at most its own amounts (a night's, what is left
        of the period's) and what the limit leaves above the reserve."""
        if not self.config.api_key:
            return 0, "wyłączone"
        config = self.config.config
        now = self.now()
        opens, closes, _ = self.window()
        window = bool(config.leftover) and opens <= now < closes
        planned = [
            (use, task(config, use.key), rest_when(config, use.key))
            for use, _ in self._uses()
            if rest_when(config, use.key) == EVERY_NIGHT
            or (window and rest_when(config, use.key) == IN_REST)
        ]
        if not planned:
            if not config.leftover:
                return 0, "wyłączone"
            if now < opens:
                return 0, f"od {opens.date():%d.%m}"
            if now >= closes:
                return 0, "ostatnia doba okresu"
            return 0, "nic do zrobienia"
        with self._lock:
            state = self._state()
            self._measure(state)
            self._save(state)
        free = budget = self.free_usd(state)
        self._texts_estimate(wait=True)  # the catalogue's texts counted now
        nights = self.nights_left()
        self._quiet = quiet
        self._studied = 0
        parts: list[str] = []
        done_by: dict[str, tuple[int, float]] = {}
        for use, settings, when in planned:
            if not use.able():
                continue
            if self.on_demand is not None and self.on_demand.running(use.key):
                continue  # asked now, for the owner's amount
            room = budget
            if settings.night_usd:
                room = min(room, settings.night_usd)
            spent_before = self.period_spent(use.key)
            if settings.period_usd:
                room = min(room, settings.period_usd - spent_before)
            if room < use.each:
                continue
            if settings.mode == "normal" and use.key in NORMAL:
                held = self._ask_now(use, room)
                if held:
                    budget -= held
                    parts.append(f"{SHORT[use.key]}: od razu, do {held:.2f} USD")
                continue
            done, usd, more = use.run(room)
            budget -= usd
            if done:
                done_by[use.key] = (done, usd)
                if use.key == STUDIES:
                    parts.append(f"zamówione {studies(done)}, ok. {usd:.2f} USD")
                else:
                    parts.append(f"{SHORT[use.key]}: {done}, ok. {usd:.2f} USD")
            if more and use.cap and nights and when == IN_REST:
                # what this use will want on the window's coming nights
                waiting = use.waiting()
                left = use.cap * nights if waiting is None else max(waiting - done, 0)
                keep = min(left, use.cap * nights) * use.each
                if settings.night_usd:
                    keep = min(keep, settings.night_usd * nights)
                if settings.period_usd:
                    keep = min(keep, max(settings.period_usd - spent_before - usd, 0.0))
                budget -= keep
            if budget <= 0:
                break
        for key, (done, usd) in done_by.items():
            self.count(key, done, usd)
        log.info(
            "month's rest: %.2f USD free, %s",
            free,
            "; ".join(f"{k} {n} (about {u:.2f} USD)" for k, (n, u) in done_by.items()) or "nothing",
        )
        if not parts:
            if free < self.per_study(state):
                return 0, f"brak wolnych środków ({max(free, 0):.2f} USD)"
            return 0, "nic do zrobienia"
        return self._studied, "; ".join(parts)

    def _ask_now(self, use: Use, usd: float) -> float:
        """``use`` asked now, not through the Batch API (its mode
        "Zwykły"), for ``usd`` and its number a night: what the run holds,
        0 when it could not start."""
        if self.on_demand is None:
            return 0.0
        from .on_demand import MAX_USD, MIN_USD, OnDemandError

        usd = min(round(usd, 2), MAX_USD)
        if usd < MIN_USD:
            return 0.0
        try:
            self.on_demand.start(use.key, usd, limit=use.cap, night=True)
        except OnDemandError as err:
            log.info("month's rest: %s not asked now: %s", use.key, err)
            return 0.0
        return usd

    def count(self, key: str, done: int, usd: float) -> None:
        """What ``key`` did, kept in the period's tally (the night's orders
        and the runs on demand alike)."""
        if done <= 0 and usd <= 0:
            return
        with self._lock:
            state = self._state()
            tally = dict(state.get("tally") or {})
            count, spent = tally.get(key) or (0, 0.0)
            tally[key] = (int(count) + done, round(float(spent) + usd, 4))
            state["tally"] = tally
            self._save(state)

    def period_spent(self, key: str) -> float:
        """What ``key`` cost this period: its tally, and what a run of it
        going now spent so far."""
        _, spent = (self._state().get("tally") or {}).get(key) or (0, 0.0)
        usd = float(spent)
        if self.on_demand is not None and self.on_demand.running(key):
            view = self.on_demand.view(key)
            if view is not None:
                usd += float(view["spent_usd"])
        return usd

    def _uses(self) -> list[tuple[Use, bool]]:
        made = {u.key: u for u in self._made_uses()}
        return [(made[key], on) for key, on in uses(self.config.config) if key in made]

    def _made_uses(self) -> list[Use]:
        config = self.config
        found: list[Use] = []
        refresh, review, crops, audit = self.refresh, self.review, self.crops, self.audit
        if refresh is not None:

            def refresh_run(usd: float) -> tuple[int, float, bool]:
                waiting = len(refresh.waiting())
                n = refresh.start(math.floor(usd / refresh_module.EACH_USD), self._cared_ids)
                return n, n * refresh_module.EACH_USD, n < waiting

            found.append(
                Use(
                    REFRESH,
                    refresh_module.EACH_USD,
                    lambda: len(refresh.waiting()),
                    lambda: config.enabled("web_facts") and self.study.job.enabled(),
                    refresh_run,
                )
            )
        if crops is not None:

            def crops_run(usd: float) -> tuple[int, float, bool]:
                waiting = crops.waiting_claims()
                corners = min(waiting, self._cap(CROPS, CROPS_A_NIGHT), math.floor(usd / CROP_USD))
                # Haiku's look around the works, for the next nights' corners
                # (those the night's own share does not reach)
                unseen = len(crops.candidates(crops.asked())) - crops.base_limit(False)
                rest = usd - corners * CROP_USD
                looks = min(CROP_LOOKS_A_NIGHT, unseen, math.floor(rest / CROP_JUDGE_USD))
                looks = max(looks, 0)
                crops.give_extra(looks, corners, self._period_end())
                usd = corners * CROP_USD + looks * CROP_JUDGE_USD
                return corners + looks, usd, waiting > corners

            found.append(
                Use(
                    CROPS,
                    CROP_USD,
                    crops.waiting_claims,
                    lambda: config.enabled("crops") and not crops.on_phone(),
                    crops_run,
                    cap=self._cap(CROPS, CROPS_A_NIGHT),
                )
            )
        found.append(
            Use(
                STUDIES,
                self.per_study(),
                lambda: None,
                self.study.job.enabled,
                self._order_studies,
                cap=self._cap(STUDIES, A_NIGHT),
            )
        )
        for text in TEXTS:
            if text not in self.ai.jobs:
                continue
            waiting: Callable[[], int | None] = partial(self._texts_waiting, text)
            run: Callable[[float], tuple[int, float, bool]] = partial(self._order_texts, text)
            if text == POLISH and review is not None:
                # the older texts looked over after the works without one
                waiting = partial(self._polish_waiting, review)
                run = partial(self._polish_run, review)
            found.append(
                Use(
                    text,
                    self._text_usd(text),
                    waiting,
                    partial(config.enabled, text),
                    run,
                    cap=self._cap(text, config.config.leftover_texts_a_night),
                    caps=TEXTS_A_NIGHT_OPTIONS,
                )
            )
        if audit is not None:

            def audit_run(usd: float) -> tuple[int, float, bool]:
                n = min(self._cap(AUDIT, AUDITS_A_NIGHT), math.floor(usd / AUDIT_USD))
                audit.give_extra(n, 0, self._period_end())
                return n, n * AUDIT_USD, True

            found.append(
                Use(
                    AUDIT,
                    AUDIT_USD,
                    lambda: None,
                    lambda: config.enabled("audit"),
                    audit_run,
                    cap=self._cap(AUDIT, AUDITS_A_NIGHT),
                )
            )
        return found

    def _cap(self, key: str, default: int) -> int:
        """``key``'s works a night: the owner's number, else its own."""
        return task(self.config.config, key).a_night or default

    def _period_end(self) -> date:
        _, _, ends = self.window()
        return ends.date()

    def _order_studies(self, usd: float) -> tuple[int, float, bool]:
        """Studies for ``usd``: how many, their cost, whether works remain."""
        now = self.now()
        state = self._state()
        each = self.per_study(state)
        count = min(self._cap(STUDIES, A_NIGHT), math.floor(usd / each))
        if count <= 0:
            return 0, 0.0, True
        picked = self.candidates(count, getattr(self, "_quiet", lambda: True))
        spent, kinds = self.claude.spending.total(now), self.claude.spending.by_kind(now)
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
        if ordered:
            with self._lock:
                state = self._state()
                if not state.get("batch"):
                    state["batch"] = {"spent": spent, "kinds": kinds, "ids": ordered}
                self._save(state)
        self._studied = len(ordered)
        return len(ordered), len(ordered) * each, len(picked) >= count

    def _order_texts(self, kind: str, usd: float) -> tuple[int, float, bool]:
        """The catalogue's keywords or Polish texts (``kind``) for ``usd``,
        at most the owner's number of works a night (Mateusz 2026-11-15:
        125 323 works waiting, and the night gave them all the rest at
        once): how many works, about what they cost, whether more wait."""
        cap = self._cap(kind, self.config.config.leftover_texts_a_night)
        before = self.ai.batched_usd((kind,))
        _, works = self.ai.order_rest((kind,), usd, self._cared_first, cap)
        self._texts_kept = None
        return works, max(self.ai.batched_usd((kind,)) - before, 0.0), works >= cap

    def _polish_run(self, review: TextReview, usd: float) -> tuple[int, float, bool]:
        """The Polish texts: the works without one first; with what is left,
        the older texts looked over and written anew (``ai.text_review``)."""
        n, cost, more = self._order_texts(POLISH, usd)
        rest = usd - cost
        if more or rest <= 0:
            return n, cost, more
        waiting, _ = review.waiting()
        if not waiting:
            return n, cost, False
        m, spent = review.order(rest, self._cared_ids)
        return n + m, cost + spent, m < waiting

    def _polish_waiting(self, review: TextReview) -> int | None:
        """The works without a Polish text and the older texts to look over."""
        texts = self._texts_waiting(POLISH)
        return None if texts is None else texts + review.waiting()[0]

    def _texts_waiting(self, kind: str) -> int | None:
        found = self._texts_estimate()
        return None if found is None or kind not in found else found[kind][0]

    def _text_usd(self, kind: str) -> float:
        """About what a work's keywords or Polish text (``kind``) cost
        through the Batch API."""
        found = self._texts_estimate()
        if found is not None and kind in found and found[kind][0]:
            return found[kind][1] / found[kind][0]
        job = self.ai.jobs.get(kind)
        return (job.estimate_usd(1, True) if job is not None else 0.0) or 0.001

    def _texts_estimate(self, wait: bool = False) -> dict[str, tuple[int, float]] | None:
        """The catalogue's works without their keywords, and without their
        Polish text, all of them (as the night orders them,
        ``AiWorker.order_rest``, not only the few the background asks
        about), and about what asking costs, by kind (Mateusz 2026-11-15,
        seeing "czeka 17": "Bardzo dużo dzieł w bazie nie ma jeszcze polskich
        opisów"). It goes through the whole catalogue (seconds on the NAS)
        and Konfiguracja asks every 20 s, so it is kept for
        :data:`TEXTS_FRESH` seconds and worked out anew on a thread of its
        own; until then the last count, or None. ``wait``: worked out now
        when old (the night)."""
        kept = self._texts_kept
        if kept is not None and time.monotonic() - kept[0] < TEXTS_FRESH:
            return kept[1]
        if wait:
            return self._count_texts()
        with self._lock:
            if not self._counting:
                self._counting = True
                threading.Thread(
                    target=self._count_texts, name="leftover-texts", daemon=True
                ).start()
        return kept[1] if kept is not None else None

    def _count_texts(self) -> dict[str, tuple[int, float]]:
        try:
            found: dict[str, tuple[int, float]] = {}
            for kind in TEXTS:
                if kind not in self.ai.jobs or not self.config.enabled(kind):
                    continue
                ids, cost = self.ai.library_waiting(kind)
                found[kind] = (len(ids), cost)
            self._texts_kept = (time.monotonic(), found)
            return found
        finally:
            self._counting = False

    def _cared_ids(self, ids: list[str]) -> list[str]:
        """``ids`` with the works cared about first."""
        ranks = self.cared()
        return sorted(ids, key=lambda i: ranks.get(i, REST))

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
            # what is ordered and held by the runs going, not spent yet
            "planned_usd": round(max(self._planned_usd(state), 0.0), 2),
            "per_study_usd": round(self.per_study(state), 2),
            "measured": bool(state.get("per_study")),
            "ordered": len(state.get("orders", {})),
            "in_flight": len(in_flight),
            "made": len(state.get("made") or []),
            "failed": len(state.get("failed") or []),
            "candidates": len(self.daily.runners_up()),
            "uses": self.uses_view(state),
        }

    def _planned_usd(self, state: dict[str, Any]) -> float:
        config = self.config.config
        return (
            config.monthly_limit_usd
            - config.leftover_reserve_usd
            - self.claude.spending.total(self.now())
            - self.free_usd(state)
        )

    def uses_view(self, state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """The uses in the owner's order: what each is, whether it is on and
        may run, how many wait and about what they would cost, and what it
        did this period."""
        state = state or self._state()
        tally = state.get("tally") or {}
        config = self.config.config
        out = [self._tidy_view()]
        for use, on in self._uses():
            settings = task(config, use.key)
            label, about = LABELS[use.key]
            try:
                waiting = use.waiting()
            except Exception:  # a count is no reason for Konfiguracja to fail
                log.exception("month's rest: %s could not be counted", use.key)
                waiting = None
            if use.key == STUDIES:
                waiting = len(self.daily.runners_up()) or None
            if use.key == REFRESH and waiting == 0:
                continue  # every study has its facts now: shown when one waits
            count, spent = tally.get(use.key) or (0, 0.0)
            # what a night takes of it (the whole that waits is no night's)
            tonight = None if use.cap is None or waiting is None else min(waiting, use.cap)
            out.append(
                {
                    "key": use.key,
                    "label": label,
                    "about": about,
                    "on": on,
                    "able": bool(use.able()),
                    "waiting": waiting,
                    "each_usd": round(use.each, 4),
                    "waiting_usd": None if waiting is None else round(waiting * use.each, 2),
                    "a_night": use.cap,
                    "a_night_options": None if use.caps is None else list(use.caps),
                    "tonight": tonight,
                    "tonight_usd": None if tonight is None else round(tonight * use.each, 2),
                    "done": int(count),
                    "done_usd": round(float(spent), 2),
                    # the owner's settings (Mateusz 2026-11-17, "Zadania")
                    "when": settings.when,
                    "a_night_choices": list(A_NIGHT_CHOICES.get(use.key, ())) or None,
                    "night_usd": settings.night_usd,
                    "period_usd": settings.period_usd,
                    "mode": settings.mode if use.key in NORMAL else "batch",
                    "modes": ["batch", "normal"] if use.key in NORMAL else ["batch"],
                    "period_spent_usd": round(self.period_spent(use.key), 2),
                    "whens": whens(use.key),
                    "more_at_end": settings.more_at_end if use.key in BASE else None,
                    "night_tasks": NIGHT_TASKS.get(use.key),
                }
            )
        return out

    def _tidy_view(self) -> dict[str, Any]:
        """The catalogue's tidying as a task: every night, when asked, or
        off; what it covers are its two switches."""
        config = self.config.config
        label, about = LABELS[TIDY]
        when = task(config, TIDY).when
        return {
            "key": TIDY,
            "label": label,
            "about": about,
            "on": when != NEVER,
            "able": bool(self.config.api_key),
            "waiting": None,
            "each_usd": 0.0,
            "waiting_usd": None,
            "a_night": None,
            "done": 0,
            "done_usd": 0.0,
            "when": when,
            "mode": "batch",
            "modes": ["batch"],
            "whens": whens(TIDY),
            "night_tasks": NIGHT_TASKS[TIDY],
        }
