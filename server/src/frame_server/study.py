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
import threading
from collections.abc import Callable
from concurrent.futures import Future
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from .ai.client import AiUnavailable
from .ai.study import KIND, StudyJob

if TYPE_CHECKING:
    from .ai import AiWorker
    from .ai.daily import DailyJob, Essay
    from .daily import Daily
    from .library import Item
    from .library.models import Note

log = logging.getLogger(__name__)

STATE_KEY = "study_items"

Status = Literal["off", "none", "waiting", "sources", "writing", "details", "ready", "failed"]
#: The study is on its way.
PENDING: tuple[Status, ...] = ("waiting", "sources", "writing", "details")
FAILED = "Claude nie napisał studium tego dzieła."


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
        job.on_stage = self._staged
        daily.on_written = self.adopt

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
            add(item_id, self.daily.job, self.daily.day_of(item_id), -1)
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
            self._step(item, self.job.stages.get(item.id, "waiting"))  # type: ignore[arg-type]
        future.add_done_callback(lambda done: self._written(item.id, done))
        return future

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
        if item is not None:
            self._step(item, *step)
        if step[0] == "details" and item is not None:
            threading.Thread(
                target=self._cut, args=(item,), name="study-details", daemon=True
            ).start()

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
                later.look(item, essay.legacy)
        except Exception:
            log.exception("later works in the study of %s", item.id)
        finally:
            with self._lock:
                self._cutting.discard(item.id)
            self._step(item, "ready")

    def _staged(self, item_id: str, stage: str) -> None:
        """A step of Claude's question (``StudyJob.params``), when asked for here."""
        if item_id in self._asking and (item := self.library.get(item_id)) is not None:
            self._step(item, stage)  # type: ignore[arg-type]

    def _step(self, item: Item, status: Status, error: str = "") -> None:
        if self.on_step is None:
            return
        try:
            self.on_step(item, status, error)
        except Exception:
            log.exception("study step %s of %s", status, item.id)

    def status(self, item: Item | None) -> tuple[Status, str]:
        """Where the work's study is, and why it failed when it did."""
        if item is not None and item.id not in self._asking:
            self.adopt(item)  # a day's page the background has not made one yet
        if item is not None and self.job.essay(item) is not None:
            return ("details" if item.id in self._cutting else "ready"), ""
        if item is not None and item.id in self._asking:
            return self.job.stages.get(item.id, "waiting"), ""  # type: ignore[return-value]
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
