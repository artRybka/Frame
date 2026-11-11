"""Studies of works: those the owner asks for on a work's card ("Przygotuj
studium dzieła"), and every day's study at the top of Odkrywaj (``daily``),
whose page becomes the work's study once written (:meth:`Study.adopt`).

The works asked about are kept, so their studies are kept too and opening
one again costs nothing. Once Claude has written a study, its fragments
("Detale") are cut from the original before the study is ready, so it opens
whole.
"""

from __future__ import annotations

import logging
import statistics
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from .ai.client import AiUnavailable
from .ai.study import KIND, StudyJob
from .library.vocabulary import other_art

if TYPE_CHECKING:
    from .ai import AiWorker
    from .ai.daily import DailyJob, Essay
    from .daily import Daily
    from .library import Item
    from .library.models import Note

log = logging.getLogger(__name__)

STATE_KEY = "study_items"

Status = Literal[
    "off", "none", "later", "waiting", "sources", "writing", "details", "ready", "failed"
]
#: The study is on its way.
PENDING: tuple[Status, ...] = ("waiting", "sources", "writing", "details")
FAILED = "Claude nie napisał studium tego dzieła."

#: The parts a study asked for now goes through, in order: each question to
#: Claude and each longer piece of work, told to the app and the Lock Screen
#: so a long step still moves (Mateusz 2026-11-07: "krok 2 to 99% czasu").
#: The app groups them into its four steps (Źródła · Tekst · Kompozycja ·
#: Detale); ``status`` keeps the three older words for older apps.
PARTS = (
    "sources",
    "text",
    "text_again",
    "details_check",
    "composition",
    "composition_check",
    "composition_motion",
    "composition_text",
    "cutting",
    "later",
)
#: Each part as the older apps' status: the long middle is "writing".
STATUS_OF: dict[str, Status] = {
    "waiting": "waiting",
    "sources": "sources",
    "cutting": "details",
    "later": "details",
    **{part: "writing" for part in PARTS[1:8]},
}
#: How long each part takes before any study was timed here (seconds).
TYPICAL_PARTS: dict[str, float] = {
    "sources": 5,
    "text": 90,
    "text_again": 0,
    "details_check": 15,
    "composition": 40,
    "composition_check": 5,
    "composition_motion": 15,
    "composition_text": 20,
    "cutting": 10,
    "later": 5,
}
#: The parts of the last studies written start to end, timed (state key).
TIMINGS_KEY = "study_timings"
#: How many are kept to say how long the next one takes.
TIMINGS_KEPT = 12


@dataclass(frozen=True)
class Progress:
    """How far a study asked for now is: its part (:data:`PARTS`, or
    "waiting"), since when it is written (after any wait for Claude) and
    when it should be done, judged by the last studies; both None while it
    waits for Claude."""

    part: str
    started: float | None = None
    until: float | None = None


@dataclass
class _Track:
    part: str
    since: float
    started: float | None = None
    spent: dict[str, float] = field(default_factory=dict)
    #: Set when a part was missed (e.g. the server asked from a batch): not timed.
    whole: bool = True


class Study:
    def __init__(self, daily: Daily, ai: AiWorker, job: StudyJob) -> None:
        self.daily = daily
        self.library = daily.library
        self.ai = ai
        self.job = job
        job.requested = self.requested
        job.candidates = daily.candidates
        self._lock = threading.Lock()
        self._asking: dict[str, Future[Note | None]] = {}
        self._cutting: set[str] = set()
        #: Why the last question about a work failed, in Polish.
        self._errors: dict[str, str] = {}
        #: Told of each step of a study asked for: on its way ("waiting",
        #: "sources", "writing", "details"), then "ready" (fragments cut) or
        #: "failed" with why; from worker threads (notifications, Live Activity).
        self.on_step: Callable[[Item, Status, str], None] | None = None
        #: Where each study asked for now is (:class:`Progress`).
        self._tracks: dict[str, _Track] = {}
        job.on_stage = self._staged
        daily.on_written = self.adopt
        ai.on_later = self._made_later

    def requested(self, item_id: str) -> bool:
        return item_id in self.library.get_state(STATE_KEY, [])

    def essay(self, item: Item) -> Essay | None:
        return self.job.essay(item)

    def written(self) -> list[tuple[Item, Essay, date | None]]:
        """The works with a page written about them, the last written first:
        those the owner asked a study of, and every work of the day (with
        its day). A work that was both is there once, with its day."""
        found: dict[str, tuple[tuple[str, int], Item, Essay, date | None]] = {}

        def add(item_id: str, job: DailyJob, day: date | None, order: int) -> None:
            item = self.library.get(item_id)
            if item is None or item.excluded:
                return
            essay = job.essay(item)
            note = self.library.note(item_id, job.kind) if essay is not None else None
            if essay is None or note is None:
                return
            key = (note.created_at, order)
            known = found.get(item_id)
            if known is not None:
                key = max(key, known[0])
                day = day or known[3]
            found[item_id] = (key, item, essay, day)

        for order, item_id in enumerate(self.library.get_state(STATE_KEY, [])):
            add(item_id, self.job, None, order)
        for item_id in set(self.daily.history().values()):
            day = self.daily.day_of(item_id)
            if day is None or day <= date.today():  # tomorrow's is shown tomorrow
                add(item_id, self.daily.job, day, -1)
        ranked = sorted(found.values(), key=lambda entry: entry[0], reverse=True)
        return [(item, essay, day) for _, item, essay, day in ranked]

    def adopt(self, item: Item) -> bool:
        """The day's page written about ``item`` made its study, as if asked
        for (no new question, no "why today"); False when it has a study
        already or there is no such page."""
        with self._lock:
            if self.job.essay(item) is not None or self.daily.job.essay(item) is None:
                return False
            if not self.job.take(
                item, self.library.note(item.id, self.daily.job.kind), keep_date=True
            ):
                return False
            ids = list(self.library.get_state(STATE_KEY, []))
            if item.id not in ids:
                self.library.set_state(STATE_KEY, [*ids, item.id])
        return True

    def ask(self, item: Item, again: bool = False) -> Future[Note | None] | None:
        """Asks Claude for the work's study unless it has one (``again``:
        a new one); None when Claude is off."""
        if not self.job.enabled():
            return None
        with self._lock:
            if item.id in self._asking:
                return self._asking[item.id]
            ids = list(self.library.get_state(STATE_KEY, []))
            if item.id not in ids:
                self.library.set_state(STATE_KEY, [*ids, item.id])
            if again:
                self.library.delete_notes(KIND, item.id)
            self._errors.pop(item.id, None)
            future = self._borrowed(item) if not again else None
            future = future or self.ai.need_now(item.id, KIND)
            waiting = not future.done() and item.id not in self._cutting
            if not future.done():
                self._asking[item.id] = future
        if waiting:
            self._part(item, self.job.stages.get(item.id, "waiting"))
        future.add_done_callback(lambda done: self._written(item.id, done))
        return future

    def ask_later(self, item: Item) -> bool:
        """Orders the work's study for later, for less ("Przygotuj na
        później", Mateusz 2026-11-04): Claude's long questions go through
        the Batch API at half price, mostly within minutes to hours; "Studium
        gotowe" says when it is. False when Claude is off or it has one."""
        if not self.job.enabled() or self.job.essay(item) is not None:
            return False
        with self._lock:
            ids = list(self.library.get_state(STATE_KEY, []))
            if item.id not in ids:
                self.library.set_state(STATE_KEY, [*ids, item.id])
            self._errors.pop(item.id, None)
        if (borrowed := self._borrowed(item)) is not None:  # the day's page: its study now
            self._written(item.id, borrowed)
            return True
        return self.ai.ask_later(item.id, KIND) or self.ai.later(KIND, item.id)

    def _made_later(self, kind: str, item: Item) -> None:
        """A note ordered for later is made: a study is cut and told ready
        (or failed), a day's page becomes its work's study."""
        if kind == KIND:
            future: Future[Note | None] = Future()
            future.set_result(self.library.note(item.id, KIND))
            self._written(item.id, future)
        elif kind == self.daily.job.kind:
            self.daily.written_later(item)

    def _borrowed(self, item: Item) -> Future[Note | None] | None:
        """A work of the day already has its page: that is its study, with
        no new question (and no new cost)."""
        if self.job.essay(item) is not None or self.daily.job.essay(item) is None:
            return None
        if not self.job.take(item, self.library.note(item.id, self.daily.job.kind)):
            return None
        future: Future[Note | None] = Future()
        future.set_result(self.library.note(item.id, KIND))
        return future

    def _written(self, item_id: str, future: Future[Note | None]) -> None:
        """Claude answered (or failed): the fragments are cut now."""
        item = self.library.get(item_id)
        with self._lock:
            self._asking.pop(item_id, None)
            self.job.stages.pop(item_id, None)
            if (err := future.exception()) is not None:
                self._errors[item_id] = _words(err)
                step: tuple[Status, str] = ("failed", self._errors[item_id])
            elif item is None:
                return
            elif (essay := self.job.essay(item)) is None:
                step = ("failed", FAILED)
            elif item_id in self._cutting:
                return  # told when the cutting under way ends
            elif not essay.details and not essay.legacy:
                step = ("ready", "")
            else:
                self._cutting.add(item_id)
                step = ("details", "")
        if item is not None and step[0] == "details":
            self._part(item, "cutting")
        elif item is not None:
            self._step(item, *step)
        if step[0] == "details" and item is not None:
            threading.Thread(
                target=self._cut, args=(item,), name="study-details", daemon=True
            ).start()

    def making(self, item_id: str) -> bool:
        """Whether the study is being written, or its details cut and its
        later works looked up (:meth:`_cut`): the page leaves those to it."""
        with self._lock:
            return item_id in self._asking or item_id in self._cutting

    def _cut(self, item: Item) -> None:
        try:
            self.detail(item, 0)
        except Exception:
            log.exception("details of the study of %s", item.id)
        try:
            # What it led to, with pictures, before the study opens.
            essay = self.job.essay(item)
            later = self.daily.later
            if later is not None and essay is not None and later.missing(item.id, essay.legacy):
                self._part(item, "later")
                later.look(item, essay.legacy)
        except Exception:
            log.exception("later works in the study of %s", item.id)
        finally:
            with self._lock:
                self._cutting.discard(item.id)
            self._step(item, "ready")

    def _staged(self, item_id: str, stage: str) -> None:
        """A part of Claude's question (``StudyJob``), when asked for here."""
        if item_id in self._asking and (item := self.library.get(item_id)) is not None:
            self._part(item, stage)

    def _part(self, item: Item, part: str) -> None:
        """The study moved on to ``part`` (:data:`PARTS`, or "waiting"):
        timed, and told with the older apps' word for it."""
        now = time.time()
        with self._lock:
            track = self._tracks.get(item.id)
            if track is None:
                track = self._tracks[item.id] = _Track(part, now)
                # Picked up past its start (a batch's answer): not timed.
                track.whole = part in ("waiting", "sources")
            elif track.part != part:
                track.spent[track.part] = track.spent.get(track.part, 0.0) + now - track.since
                track.part, track.since = part, now
            if track.started is None and part != "waiting":
                track.started = now
        self._step(item, STATUS_OF.get(part, "writing"))

    def _step(self, item: Item, status: Status, error: str = "") -> None:
        if status not in PENDING:
            self._done(item.id, timed=status == "ready")
        if self.on_step is None:
            return
        try:
            self.on_step(item, status, error)
        except Exception:
            log.exception("study step %s of %s", status, item.id)

    def _done(self, item_id: str, *, timed: bool) -> None:
        """The study is over: a whole one is kept to time the next ones."""
        with self._lock:
            track = self._tracks.pop(item_id, None)
        if track is None or not timed or not track.whole or track.part == "waiting":
            return
        spent = {**track.spent, track.part: track.spent.get(track.part, 0.0)}
        spent[track.part] += time.time() - track.since
        spent.pop("waiting", None)
        kept = [t for t in self.library.get_state(TIMINGS_KEY, []) if isinstance(t, dict)]
        record = {part: round(spent.get(part, 0.0), 1) for part in PARTS}
        self.library.set_state(TIMINGS_KEY, [*kept, record][-TIMINGS_KEPT:])
        log.info(
            "study of %s took %.0f s (%s)",
            item_id,
            sum(record.values()),
            ", ".join(f"{k} {v:.0f}" for k, v in record.items() if v),
        )

    def expected(self) -> dict[str, float]:
        """How long each part takes (seconds): the median of the last
        studies timed here, :data:`TYPICAL_PARTS` before any."""
        kept = [t for t in self.library.get_state(TIMINGS_KEY, []) if isinstance(t, dict)]
        if not kept:
            return dict(TYPICAL_PARTS)
        return {
            part: float(statistics.median(float(t.get(part, 0.0) or 0.0) for t in kept))
            for part in PARTS
        }

    def progress(self, item_id: str) -> Progress | None:
        """How far the study asked for now is; None when none is."""
        with self._lock:
            track = self._tracks.get(item_id)
            if track is None:
                return None
            part, since, started = track.part, track.since, track.started
        if started is None or part not in PARTS:
            return Progress(part)
        expected = self.expected()
        left = expected[part] + sum(expected[p] for p in PARTS[PARTS.index(part) + 1 :])
        if part == "text_again":  # as long as the first answer took
            left += expected["text"]
        return Progress(part, started, since + left)

    def status(self, item: Item | None) -> tuple[Status, str]:
        """Where the work's study is, and why it failed when it did."""
        if item is not None and item.id not in self._asking:
            self.adopt(item)  # a day's page the background has not made one yet
        if item is not None and self.job.essay(item) is not None:
            return ("details" if item.id in self._cutting else "ready"), ""
        if item is not None and item.id in self._asking:
            return STATUS_OF.get(self.job.stages.get(item.id, "waiting"), "writing"), ""
        if item is not None and other_art(item):
            return "off", ""  # "Sztuki inne" have no study (Mateusz 2026-11-06)
        if item is not None and self.ai.later(KIND, item.id):
            return "later", ""
        if item is not None and (error := self._errors.get(item.id)):
            return "failed", error
        if item is not None and self.requested(item.id) and self.job.failed(item):
            return "failed", FAILED
        return ("none" if self.job.enabled() else "off"), ""

    def detail(self, item: Item, index: int) -> Path | None:
        essay = self.job.essay(item)
        return self.daily.detail(item, index, essay) if essay is not None else None


def _words(err: BaseException) -> str:
    if isinstance(err, AiUnavailable):
        if "limit" in str(err):
            return "Wyczerpany miesięczny limit wydatków na Claude’a."
        return "Claude jest niedostępny: brak klucza albo klucz odrzucony."
    return "Nie udało się zapytać Claude’a. Spróbuj ponownie za chwilę."
