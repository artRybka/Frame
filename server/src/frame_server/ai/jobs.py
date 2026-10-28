"""Jobs a language model does for library items, and the worker that runs them.

A :class:`NoteJob` says, for one kind of note (``"keywords"``,
``"pl_text"``), which items want one, what to ask and what to do with the
answer. The :class:`AiWorker` asks one question at a time on its own thread:

- ``need_now(item_id, kind)``: an item the frame or the app needs now, first
  in line; the result is a future;
- in the background, items a job wants and that have no up-to-date note;
- ``describe_library(kind)``: the whole library through the Batch API (half
  price, answers within 24 hours), in chunks of :data:`BATCH_SIZE`.

An answer is kept as a :class:`~frame_server.library.Note` until the item's
source text or the job's prompt change. A refusal or an unreadable answer is
kept too, so it is not asked again and again.
"""

from __future__ import annotations

import hashlib
import itertools
import logging
import queue
import threading
import time
from abc import ABC, abstractmethod
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import anthropic
import httpx
from pydantic import BaseModel

from ..library.models import Note
from .client import AiUnavailable, Answer, cost

if TYPE_CHECKING:
    from ..library import ImageCache, Item, Library
    from .client import Claude
    from .config import AiConfigStore

log = logging.getLogger(__name__)

BATCHES_KEY = "ai_batches"
#: Questions in one batch: base64 thumbnails keep it far below the API's 256 MB.
BATCH_SIZE = 1000
#: How often to look for items wanting a note, and at most how many to queue.
SWEEP_SECONDS = 60.0
SWEEP_ITEMS = 20
#: How often to ask whether running batches are done.
POLL_SECONDS = 300.0
#: After a failure that is not the item's fault (network, throttling).
PAUSE_SECONDS = 600.0
#: Priorities: lower goes first.
NOW, BACKGROUND = 0, 10


def text_hash(*parts: object) -> str:
    """A short hash of the text an answer was made from."""
    raw = "\x1f".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Usage:
    """Tokens of a typical question, to estimate what a batch costs."""

    input_tokens: int
    cache_read_input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0


class NoteJob(ABC):
    kind: str
    model: str
    prompt_version: str
    typical: Usage = Usage(input_tokens=600, cache_read_input_tokens=2000, output_tokens=400)

    def __init__(self, library: Library, images: ImageCache, config: AiConfigStore) -> None:
        self.library = library
        self.images = images
        self.config = config

    def enabled(self) -> bool:
        return self.config.enabled(self.kind)

    @abstractmethod
    def wanted(self, item: Item) -> bool:
        """Whether the item should get a note in the background."""

    def in_library(self, item: Item) -> bool:
        """Whether "describe the library" includes the item."""
        return self.wanted(item)

    @abstractmethod
    def source_hash(self, item: Item) -> str:
        """Changes when the item's text the question uses changes."""

    @abstractmethod
    def params(self, item: Item) -> dict[str, Any]:
        """The question (``client.request(...)``); may download the thumbnail."""

    def apply(self, item: Item, note: Note) -> None:  # noqa: B027 - optional hook
        """After a note was saved: e.g. copy what it found onto the item."""

    def fresh(self, item: Item, note: Note | None) -> bool:
        return (
            note is not None
            and note.prompt_version == self.prompt_version
            and note.source_hash == self.source_hash(item)
        )

    def estimate_usd(self, items: int, batch: bool = True) -> float:
        return items * cost(self.model, self.typical, batch)

    def estimate_items(self, items: list[Item], batch: bool = True) -> float:
        """What asking about ``items`` costs; a job whose model depends on the
        item counts each one."""
        return self.estimate_usd(len(items), batch)


class Progress(BaseModel):
    """One job's state, for the app."""

    done: int  # items with an up-to-date note
    waiting: int  # items the background will still ask about
    refused: int  # notes without an answer (refused or unreadable)
    batch_items: int  # questions in batches not yet ended
    batch_done: int
    preparing: bool  # a "describe the library" being put together


@dataclass(order=True)
class _Task:
    priority: int
    seq: int
    kind: str = field(compare=False)
    item_id: str = field(compare=False)
    future: Future[Note | None] | None = field(compare=False, default=None)


class AiWorker:
    def __init__(
        self, library: Library, images: ImageCache, claude: Claude, config: AiConfigStore
    ) -> None:
        self.library = library
        self.images = images
        self.claude = claude
        self.config = config
        self.jobs: dict[str, NoteJob] = {}
        self.error: str | None = None
        self._queue: queue.PriorityQueue[_Task] = queue.PriorityQueue()
        self._seq = itertools.count()
        self._pending: set[tuple[str, str]] = set()
        self._skipped: set[tuple[str, str]] = set()  # thumbnail failed: not this run
        self._preparing: set[str] = set()
        self._paused_until = 0.0
        self._next_sweep = 0.0
        self._next_poll = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def register(self, job: NoteJob) -> NoteJob:
        self.jobs[job.kind] = job
        return job

    # -- asking ------------------------------------------------------------

    def need_now(self, item_id: str, kind: str) -> Future[Note | None]:
        """The item's note, asked ahead of everything else if it has none
        (None when the job is off, the item is gone or the job is not for
        it). ``await asyncio.wrap_future(...)`` it from async code."""
        future: Future[Note | None] = Future()
        job, item = self.jobs.get(kind), self.library.get(item_id)
        if job is None or item is None or not job.enabled() or not job.in_library(item):
            future.set_result(None)
            return future
        note = self.library.note(item_id, kind)
        if job.fresh(item, note):
            future.set_result(note)
            return future
        self._queue.put(_Task(NOW, next(self._seq), kind, item_id, future))
        return future

    def run_one(self, kind: str, item_id: str) -> Note | None:
        """Ask about one item now, on the caller's thread."""
        job, item = self.jobs[kind], self.library.get(item_id)
        if item is None or not job.enabled():
            return None
        note = self.library.note(item_id, kind)
        if job.fresh(item, note):
            return note
        params = job.params(item)
        return self._keep(job, item, self.claude.ask(kind, params))

    def _keep(self, job: NoteJob, item: Item, answer: Answer) -> Note:
        if answer.data is not None:
            data = answer.data
        else:
            data = {"refused": True} if answer.refused else {"failed": True}
        note = self.library.save_note(
            Note(
                item_id=item.id,
                kind=job.kind,
                model=answer.model,
                prompt_version=job.prompt_version,
                source_hash=job.source_hash(item),
                data=data,
            )
        )
        if answer.data is not None:
            job.apply(item, note)
        return note

    # -- the thread --------------------------------------------------------

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="ai-worker", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def wake(self) -> None:
        """The owner changed something (key, switches): try again now."""
        self._paused_until = 0.0
        self._next_sweep = 0.0
        self._next_poll = 0.0
        self._skipped.clear()
        self.error = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                task = self._queue.get(timeout=5.0)
            except queue.Empty:
                self.tick()
                continue
            self._do(task)

    def tick(self) -> None:
        """Periodic work: prepare and poll batches, look for items to ask about."""
        now = time.monotonic()
        try:
            for kind in list(self._preparing):
                self._prepare_batch(kind)
            if now >= self._next_poll:
                self._next_poll = now + POLL_SECONDS
                self.poll_batches()
            if now >= self._next_sweep and now >= self._paused_until:
                self._next_sweep = now + SWEEP_SECONDS
                self.sweep()
        except AiUnavailable as err:
            self._pause(str(err))
        except anthropic.APIError as err:
            self._pause(f"Anthropic: {err}")

    def _do(self, task: _Task) -> None:
        key = (task.kind, task.item_id)
        try:
            if task.priority >= BACKGROUND and time.monotonic() < self._paused_until:
                result = None
            else:
                result = self.run_one(task.kind, task.item_id)
                if result is not None and self.error:
                    self.error = None
        except (AiUnavailable, anthropic.APIError) as err:
            self._pause(str(err) if isinstance(err, AiUnavailable) else f"Anthropic: {err}")
            if task.future is not None:
                task.future.set_exception(err)
            return
        except (OSError, httpx.HTTPError) as err:  # the thumbnail: the item's problem
            log.warning("%s for %s: no picture (%s)", task.kind, task.item_id, err)
            self._skipped.add(key)
            if task.future is not None:
                task.future.set_exception(err)
            return
        except Exception as err:
            log.exception("%s for %s failed", task.kind, task.item_id)
            self._skipped.add(key)
            if task.future is not None:
                task.future.set_exception(err)
            return
        finally:
            with self._lock:
                self._pending.discard(key)
        if task.future is not None:
            task.future.set_result(result)

    def _pause(self, reason: str) -> None:
        log.warning("language model paused: %s", reason)
        self.error = reason
        self._paused_until = time.monotonic() + PAUSE_SECONDS

    # -- background --------------------------------------------------------

    def _stale(self, job: NoteJob, wanted: Any) -> list[Item]:
        """Items ``wanted`` picks that have no up-to-date note."""
        notes = self.library.notes(job.kind)
        return [
            i for i in self.library.all_items() if wanted(i) and not job.fresh(i, notes.get(i.id))
        ]

    def sweep(self) -> int:
        """Queue a few items wanting a note; how many were queued."""
        queued = 0
        in_batches = self._batched()
        for job in self.jobs.values():
            if not job.enabled():
                continue
            for item in self._stale(job, job.wanted):
                key = (job.kind, item.id)
                if key in self._skipped or key in in_batches:
                    continue
                with self._lock:
                    if key in self._pending:
                        continue
                    self._pending.add(key)
                self._queue.put(_Task(BACKGROUND, next(self._seq), job.kind, item.id))
                queued += 1
                if queued >= SWEEP_ITEMS:
                    return queued
        return queued

    def progress(self, kind: str) -> Progress:
        job = self.jobs[kind]
        notes = self.library.notes(kind)
        done = waiting = refused = 0
        for item in self.library.all_items():
            note = notes.get(item.id)
            if job.fresh(item, note):
                done += 1
                assert note is not None
                if "refused" in note.data or "failed" in note.data:
                    refused += 1
            elif job.wanted(item):
                waiting += 1
        batches = [b for b in self._batches() if b["kind"] == kind]
        return Progress(
            done=done,
            waiting=waiting if job.enabled() else 0,
            refused=refused,
            batch_items=sum(len(b["ids"]) for b in batches),
            batch_done=sum(b.get("done", 0) for b in batches),
            preparing=kind in self._preparing,
        )

    # -- the whole library through the Batch API --------------------------

    def estimate(self, kind: str) -> tuple[int, float]:
        """Items "describe the library" would ask about, and about what it costs."""
        job = self.jobs[kind]
        in_batches = self._batched()
        items = [i for i in self._stale(job, job.in_library) if (kind, i.id) not in in_batches]
        return len(items), job.estimate_items(items)

    def describe_library(self, kind: str) -> int:
        """Start asking about every item of the library without a note;
        returns how many. Raises AiUnavailable without a key or when it would
        cost more than this month has left."""
        job = self.jobs[kind]
        if not job.enabled():
            raise AiUnavailable("the job is off or there is no API key")
        count, usd = self.estimate(kind)
        if usd > self.claude.budget_left():
            raise AiUnavailable(
                f"about {usd:.2f} USD, more than this month's limit leaves "
                f"({max(self.claude.budget_left(), 0):.2f} USD)"
            )
        if count:
            self._preparing.add(kind)
            self._next_poll = time.monotonic() + POLL_SECONDS
        return count

    def _prepare_batch(self, kind: str) -> None:
        """Send the next chunk of the library; done when nothing is left."""
        job = self.jobs[kind]
        in_batches = self._batched()
        items = [i for i in self._stale(job, job.in_library) if (kind, i.id) not in in_batches]
        if not items or not job.enabled():
            self._preparing.discard(kind)
            return
        ids: dict[str, str] = {}
        requests = []
        for n, item in enumerate(items[:BATCH_SIZE]):
            try:
                params = job.params(item)
            except (OSError, httpx.HTTPError) as err:
                log.warning("%s for %s: no picture (%s)", kind, item.id, err)
                continue
            custom_id = f"i{n}"
            ids[custom_id] = item.id
            requests.append({"custom_id": custom_id, "params": params})
        if not requests:
            self._preparing.discard(kind)
            return
        batch_id = self.claude.create_batch(requests)
        log.info("%s: batch %s with %d questions", kind, batch_id, len(requests))
        record = {
            "id": batch_id,
            "kind": kind,
            "model": job.model,
            "prompt_version": job.prompt_version,
            "ids": ids,
            "done": 0,
        }
        self._save_batches([*self._batches(), record])
        if len(items) <= BATCH_SIZE:
            self._preparing.discard(kind)

    def poll_batches(self) -> int:
        """Collect the answers of ended batches; how many notes were saved."""
        saved = 0
        records = self._batches()
        left = []
        for record in records:
            ended, done = self.claude.batch_ended(record["id"])
            record["done"] = done
            if not ended:
                left.append(record)
                continue
            saved += self._collect(record)
        if records:
            self._save_batches(left)
        return saved

    def _collect(self, record: dict[str, Any]) -> int:
        job = self.jobs.get(record["kind"])
        if job is None:
            return 0
        saved = 0
        for custom_id, message in self.claude.batch_results(record["id"]):
            item = self.library.get(record["ids"].get(custom_id, ""))
            if item is None or message is None:  # gone, or failed: the background retries
                continue
            # A job may ask different models: the answer says which one it was.
            model = str(getattr(message, "model", "") or record["model"])
            answer = self.claude.answer(job.kind, model, message, batch=True)
            if record["prompt_version"] == job.prompt_version:
                self._keep(job, item, answer)
                saved += 1
        return saved

    def _batches(self) -> list[dict[str, Any]]:
        return list(self.library.get_state(BATCHES_KEY, []))

    def _save_batches(self, records: list[dict[str, Any]]) -> None:
        self.library.set_state(BATCHES_KEY, records)

    def _batched(self) -> set[tuple[str, str]]:
        return {(b["kind"], i) for b in self._batches() for i in b["ids"].values()}
