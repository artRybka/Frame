"""Jobs a language model does for library items, and the worker that runs them.

A :class:`NoteJob` says, for one kind of note (``"keywords"``,
``"pl_text"``), which items want one, what to ask and what to do with the
answer. The :class:`AiWorker` asks on two threads of its own:

- ``need_now(item_id, kind)``: an item the frame or the app needs now, on a
  thread that does nothing else, so it never waits for the background; the
  result is a future;
- in the background, one at a time: items a job wants and that have no
  up-to-date note;
- ``describe_library(kind)``: the whole library through the Batch API (half
  price, answers within 24 hours), in chunks of :data:`BATCH_SIZE`;
- ``ask_later(item_id, kind)``: one item's note made for less, by and by
  (:class:`Deferred`): its long questions go through the Batch API one by
  one, the short ones are asked at once (Mateusz 2026-11-04: "Przygotuj na
  później", and every day's study a day ahead).

An answer is kept as a :class:`~frame_server.library.Note` until the item's
source text or the job's prompt change. A refusal or an unreadable answer is
kept too, so it is not asked again and again.
"""

from __future__ import annotations

import contextlib
import hashlib
import itertools
import logging
import queue
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import anthropic
import httpx
from pydantic import BaseModel

from ..library.models import Note
from .client import OPUS, AiUnavailable, Answer, cost

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
#: A look goes through every note and item: when the last one found
#: nothing and the library, its notes and the jobs stayed as they were, the
#: next waits this long (2026-11-02: not a whole look every minute).
SWEEP_IDLE_SECONDS = 900.0
#: How often to ask whether running batches are done (an order for later's
#: one question is often answered within minutes).
POLL_SECONDS = 300.0
LATER_POLL_SECONDS = 120.0
#: After a failure that is not the item's fault (network, throttling).
PAUSE_SECONDS = 600.0
#: Priorities: lower goes first.
NOW, BACKGROUND = 0, 10
#: Notes ordered for later (:meth:`AiWorker.ask_later`): the answers they
#: have had so far, by "kind|item id".
LATER_KEY = "ai_later"
#: The questions an order for later sends through the Batch API (the
#: others are asked at once: they cost little).
DEFERRED_MODELS = (OPUS,)


class Deferred(BaseException):
    """A question of a note ordered for later, put into a batch: the note is
    made again from its start once the answer is in, every question it
    asked before answered from what was kept. A ``BaseException``, so the
    jobs' own ``except Exception`` (a check that failed must not lose a
    page) let it through."""

    def __init__(self, params: dict[str, Any], seq: int) -> None:
        super().__init__(f"question {seq} put off")
        self.params = params
        self.seq = seq


#: Lists of works kept in the library's state (the owner's "Popraw detale",
#: "Wykonaj ponowną analizę") are changed by the app's requests and by the
#: worker at once: read, changed and written under one lock, or one undoes
#: the other (2026-11-07: "Popraw detale" asked for 42 works one after
#: another left "Roman Interior" waiting for good, put back on the list by
#: a request that read it before the worker took it off).
_LISTS = threading.Lock()


def listed(library: Library, key: str) -> set[str]:
    """The works in the state's list ``key``."""
    found = library.get_state(key, [])
    return {str(i) for i in found} if isinstance(found, list) else set()


def relist(library: Library, key: str, item_id: str, *, on: bool) -> None:
    """``item_id`` put on the state's list ``key`` (``on``) or taken off it."""
    with _LISTS:
        ids = listed(library, key)
        ids = ids | {item_id} if on else ids - {item_id}
        library.set_state(key, sorted(ids))


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

    #: Whether answers asked one at a time are streamed to :meth:`partial`.
    streams = False

    def partial(self, item: Item, piece: str) -> None:  # noqa: B027 - optional hook
        """A piece of the answer's text as it is written (``streams`` only):
        e.g. a title shown before the rest is ready."""

    def revise(
        self, item: Item, params: dict[str, Any], answer: Answer, ask: Callable[..., Answer]
    ) -> Answer:
        """The answer before it is kept, asked about once alone (not in a
        batch): e.g. checked by a second question (``ask(params)``)."""
        return answer

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
    #: An order for later (:meth:`AiWorker.advance`), not a question now.
    later: bool = field(compare=False, default=False)


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
        self._queue: queue.PriorityQueue[_Task] = queue.PriorityQueue()  # background
        self._now: queue.Queue[_Task] = queue.Queue()
        self._seq = itertools.count()
        self._pending: set[tuple[str, str]] = set()
        self._skipped: set[tuple[str, str]] = set()  # thumbnail failed: not this run
        self._preparing: set[str] = set()
        self._asked: dict[tuple[str, str], tuple[threading.Lock, int]] = {}
        self._paused_until = 0.0
        self._next_sweep = 0.0
        self._next_poll = 0.0
        #: What the last look found nothing in (:meth:`_sweep_key`), and when.
        self._swept_from: tuple[object, ...] | None = None
        self._swept_at = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        #: Told of a note ordered for later once it is made: ``(kind, item)``.
        self.on_later: Callable[[str, Item], None] | None = None

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
        self._now.put(_Task(NOW, next(self._seq), kind, item_id, future))
        return future

    def run_one(self, kind: str, item_id: str) -> Note | None:
        """Ask about one item now, on the caller's thread. One ordered for
        later is finished now: what its batches answered is not asked again."""
        with self._asking(kind, item_id):  # the other thread may be asking already
            job, item = self.jobs[kind], self.library.get(item_id)
            if item is None or not job.enabled():
                return None
            note = self.library.note(item_id, kind)
            if job.fresh(item, note):
                self._drop_later(kind, item_id)
                return note
            ask = self._replaying(kind, item_id, defer=False)
            params = job.params(item)
            if self.later(kind, item_id):
                answer = ask(params)
            elif job.streams:
                answer = self.claude.ask(
                    kind, params, on_text=lambda piece: job.partial(item, piece)
                )
            else:
                answer = self.claude.ask(kind, params)
            answer = job.revise(item, params, answer, ask)
            kept = self._keep(job, item, answer)
            self._drop_later(kind, item_id)
            return kept

    # -- for later, for less ------------------------------------------------

    def _later(self) -> dict[str, dict[str, Any]]:
        return dict(self.library.get_state(LATER_KEY, {}))

    def later(self, kind: str, item_id: str) -> bool:
        """The item's note is ordered for later and not made yet."""
        return f"{kind}|{item_id}" in self._later()

    def later_ids(self, kind: str) -> set[str]:
        return {k.split("|", 1)[1] for k in self._later() if k.split("|", 1)[0] == kind}

    def ask_later(self, item_id: str, kind: str) -> bool:
        """Orders the item's note for later, for less: its long questions go
        through the Batch API (half price, mostly within minutes to hours),
        one after another as each answer comes. False when the job is off,
        the item is not for it or it has a note already."""
        job, item = self.jobs.get(kind), self.library.get(item_id)
        if job is None or item is None or not job.enabled() or not job.in_library(item):
            return False
        if job.fresh(item, self.library.note(item_id, kind)) or self.later(kind, item_id):
            return False
        with self._lock:
            later = self._later()
            later[f"{kind}|{item_id}"] = {"answers": [], "batch": ""}
            self.library.set_state(LATER_KEY, later)
        self._queue.put(_Task(BACKGROUND, next(self._seq), kind, item_id, later=True))
        return True

    def _drop_later(self, kind: str, item_id: str) -> None:
        with self._lock:
            later = self._later()
            if later.pop(f"{kind}|{item_id}", None) is not None:
                self.library.set_state(LATER_KEY, later)

    def _save_answer(self, kind: str, item_id: str, seq: int, answer: Answer) -> None:
        """The answer to an order's question ``seq``, kept for its next go."""
        with self._lock:
            later = self._later()
            entry = later.get(f"{kind}|{item_id}")
            if entry is None:
                return
            answers = list(entry.get("answers") or [])[:seq]
            if len(answers) < seq:  # a question before it is missing: asked again
                return
            answers.append(
                {
                    "data": answer.data,
                    "refused": answer.refused,
                    "cost_usd": answer.cost_usd,
                    "model": answer.model,
                }
            )
            later[f"{kind}|{item_id}"] = {**entry, "answers": answers, "batch": ""}
            self.library.set_state(LATER_KEY, later)

    def _replaying(self, kind: str, item_id: str, *, defer: bool) -> Callable[..., Answer]:
        """The ``ask`` of an order for later: each question in turn answered
        from what was kept, else asked now (``defer``: a long one put into a
        batch, :class:`Deferred`), and what it answered kept."""
        entry = self._later().get(f"{kind}|{item_id}")
        kept = list(entry.get("answers") or []) if entry else []
        seq = itertools.count()

        def ask(params: dict[str, Any]) -> Answer:
            n = next(seq)
            if n < len(kept) and kept[n].get("model", "").startswith(params["model"]):
                k = kept[n]
                return Answer(
                    k.get("data"), bool(k.get("refused")), k.get("cost_usd", 0.0), k["model"]
                )
            if defer and params["model"] in DEFERRED_MODELS:
                raise Deferred(params, n)
            answer = self.claude.ask(kind, params)
            if entry is not None:
                self._save_answer(kind, item_id, n, answer)
            return answer

        return ask

    def advance(self, kind: str, item_id: str) -> Note | None:
        """An order for later taken a step further: made from its start with
        the answers it has, until a long question not answered yet goes into
        a batch (None), or the note is made."""
        with self._asking(kind, item_id):
            job, item = self.jobs.get(kind), self.library.get(item_id)
            entry = self._later().get(f"{kind}|{item_id}")
            if entry is None or entry.get("batch"):
                return None  # made already, or waiting for its batch
            if job is None or item is None or not job.enabled() or not job.in_library(item):
                self._drop_later(kind, item_id)  # gone, off, or no longer wanted
                return None
            note = self.library.note(item_id, kind)
            if not job.fresh(item, note):
                ask = self._replaying(kind, item_id, defer=True)
                try:
                    params = job.params(item)
                    answer = job.revise(item, params, ask(params), ask)
                except Deferred as put_off:
                    self._defer(kind, item_id, put_off)
                    return None
                note = self._keep(job, item, answer)
            self._drop_later(kind, item_id)
        if self.on_later is not None:
            try:
                self.on_later(kind, item)
            except Exception:
                log.exception("%s for %s: made for later, then", kind, item_id)
        return note

    def _defer(self, kind: str, item_id: str, put_off: Deferred) -> None:
        # ``timeout`` is the client's own (a long answer), no part of the request.
        params = {k: v for k, v in put_off.params.items() if k != "timeout"}
        batch_id = self.claude.create_batch([{"custom_id": "q", "params": params}])
        log.info("%s for %s: question %d in batch %s", kind, item_id, put_off.seq, batch_id)
        with self._lock:
            later = self._later()
            key = f"{kind}|{item_id}"
            if key in later:
                answers = list(later[key].get("answers") or [])[: put_off.seq]
                later[key] = {**later[key], "answers": answers, "batch": batch_id}
                self.library.set_state(LATER_KEY, later)
        record = {
            "id": batch_id,
            "kind": kind,
            "model": put_off.params["model"],
            "prompt_version": self.jobs[kind].prompt_version,
            "ids": {"q": item_id},
            "done": 0,
            "later": put_off.seq,
        }
        self._save_batches([*self._batches(), record])
        self._next_poll = min(self._next_poll, time.monotonic() + LATER_POLL_SECONDS)

    def _collect_later(self, record: dict[str, Any]) -> int:
        """An order's question answered in its batch: kept, and the order
        taken on (or, failed, asked again on its next go)."""
        kind, seq = record["kind"], int(record["later"])
        item_id = record["ids"].get("q", "")
        for _, message in self.claude.batch_results(record["id"]):
            if message is not None:
                model = str(getattr(message, "model", "") or record["model"])
                answer = self.claude.answer(kind, model, message, batch=True)
                self._save_answer(kind, item_id, seq, answer)
        with self._lock:  # failed: no answer kept, the next go sends it again
            later = self._later()
            key = f"{kind}|{item_id}"
            if key in later and later[key].get("batch") == record["id"]:
                later[key] = {**later[key], "batch": ""}
                self.library.set_state(LATER_KEY, later)
        return 1 if self._try_advance(kind, item_id) is not None else 0

    def _try_advance(self, kind: str, item_id: str) -> Note | None:
        """:meth:`advance`, an order given up on the item's own trouble (no
        picture, a bad answer); Anthropic's or the network's is raised, and
        the order waits for the worker's pause to end."""
        try:
            return self.advance(kind, item_id)
        except (AiUnavailable, anthropic.APIError):
            raise
        except Exception:
            log.exception("%s for %s: order for later given up", kind, item_id)
            self._drop_later(kind, item_id)
            return None

    def _advance_all(self) -> None:
        """Orders for later not waiting for a batch (just ordered, their
        batch failed, the server restarted): taken on."""
        for key, entry in self._later().items():
            if not entry.get("batch"):
                self._try_advance(*key.split("|", 1))

    @contextlib.contextmanager
    def _asking(self, kind: str, item_id: str) -> Iterator[None]:
        key = (kind, item_id)
        with self._lock:
            lock, users = self._asked.get(key, (threading.Lock(), 0))
            self._asked[key] = (lock, users + 1)
        try:
            with lock:
                yield
        finally:
            with self._lock:
                lock, users = self._asked[key]
                if users > 1:
                    self._asked[key] = (lock, users - 1)
                else:
                    del self._asked[key]

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
        if not self._threads:
            self._threads = [
                threading.Thread(target=self._run, name="ai-worker", daemon=True),
                threading.Thread(target=self._run_now, name="ai-now", daemon=True),
            ]
            for thread in self._threads:
                thread.start()

    def stop(self) -> None:
        self._stop.set()

    def wake(self) -> None:
        """The owner changed something (key, switches): try again now."""
        self._paused_until = 0.0
        self._next_sweep = 0.0
        self._next_poll = 0.0
        self._swept_from = None
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

    def _run_now(self) -> None:
        """What the frame or the app waits for: one question at a time, but
        never behind a background one or a batch being put together."""
        while not self._stop.is_set():
            try:
                task = self._now.get(timeout=5.0)
            except queue.Empty:
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
                self._advance_all()
                key = self._sweep_key()
                if key != self._swept_from or now - self._swept_at >= SWEEP_IDLE_SECONDS:
                    found = self.sweep()
                    self._swept_from = None if found else key
                    self._swept_at = now
        except AiUnavailable as err:
            self._pause(str(err))
        except anthropic.APIError as err:
            self._pause(f"Anthropic: {err}")

    def _do(self, task: _Task) -> None:
        key = (task.kind, task.item_id)
        try:
            if task.priority >= BACKGROUND and time.monotonic() < self._paused_until:
                result = None
            elif task.later:
                result = self._try_advance(task.kind, task.item_id)
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

    def _sweep_key(self) -> tuple[object, ...]:
        """While this stays, a look that found nothing would find nothing."""
        enabled = tuple(job.enabled() for job in self.jobs.values())
        return (self.library.stamp(), self.library.notes_version, enabled, len(self._skipped))

    def _pause(self, reason: str) -> None:
        self._swept_from = None  # looked again once the pause is over
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
            later = self.later_ids(job.kind)
            for item in self._stale(job, job.wanted):
                key = (job.kind, item.id)
                if key in self._skipped or key in in_batches or item.id in later:
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
        if records:  # with the batches put in meanwhile (an order's next question)
            polled = {r["id"] for r in records}
            self._save_batches(left + [r for r in self._batches() if r["id"] not in polled])
        return saved

    def _collect(self, record: dict[str, Any]) -> int:
        job = self.jobs.get(record["kind"])
        if job is None:
            return 0
        if "later" in record:
            return self._collect_later(record)
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
