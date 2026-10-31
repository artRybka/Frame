"""Studies of works the owner asks for on a work's card ("Przygotuj studium
dzieła"): the work of the day's page for any work (``ai.study``).

The works asked about are kept, so their studies are kept too and opening
one again costs nothing. Once Claude has written a study, its fragments
("Detale") are cut from the original before the study is ready, so it opens
whole.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import Future
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from .ai.client import AiUnavailable
from .ai.study import KIND, StudyJob

if TYPE_CHECKING:
    from .ai import AiWorker
    from .ai.daily import Essay
    from .daily import Daily
    from .library import Item
    from .library.models import Note

log = logging.getLogger(__name__)

STATE_KEY = "study_items"

Status = Literal["off", "none", "waiting", "sources", "writing", "details", "ready", "failed"]
#: The study is on its way.
PENDING: tuple[Status, ...] = ("waiting", "sources", "writing", "details")


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

    def requested(self, item_id: str) -> bool:
        return item_id in self.library.get_state(STATE_KEY, [])

    def essay(self, item: Item) -> Essay | None:
        return self.job.essay(item)

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
            future = self.ai.need_now(item.id, KIND)
            if not future.done():
                self._asking[item.id] = future
        future.add_done_callback(lambda done: self._written(item.id, done))
        return future

    def _written(self, item_id: str, future: Future[Note | None]) -> None:
        """Claude answered (or failed): the fragments are cut now."""
        with self._lock:
            self._asking.pop(item_id, None)
            self.job.stages.pop(item_id, None)
            if (err := future.exception()) is not None:
                self._errors[item_id] = _words(err)
                return
            item = self.library.get(item_id)
            essay = self.job.essay(item) if item is not None else None
            if item is None or essay is None or not essay.details or item_id in self._cutting:
                return
            self._cutting.add(item_id)
        threading.Thread(target=self._cut, args=(item,), name="study-details", daemon=True).start()

    def _cut(self, item: Item) -> None:
        try:
            self.detail(item, 0)
        except Exception:
            log.exception("details of the study of %s", item.id)
        finally:
            with self._lock:
                self._cutting.discard(item.id)

    def status(self, item: Item | None) -> tuple[Status, str]:
        """Where the work's study is, and why it failed when it did."""
        if item is not None and self.job.essay(item) is not None:
            return ("details" if item.id in self._cutting else "ready"), ""
        if item is not None and item.id in self._asking:
            return self.job.stages.get(item.id, "waiting"), ""  # type: ignore[return-value]
        if item is not None and (error := self._errors.get(item.id)):
            return "failed", error
        if item is not None and self.requested(item.id) and self.job.failed(item):
            return "failed", "Claude nie napisał studium tego dzieła."
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
