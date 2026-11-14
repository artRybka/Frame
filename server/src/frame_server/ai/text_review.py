"""The Polish texts written before the five styles and before Haiku told
whether a museum's text is about the work, looked over at the owner's tap
(Konfiguracja → Claude, "Przejrzyj zapisane opisy", Mateusz 2026-11-14).

Two steps, each its own switch, both through the Batch API:

- "Sprawdź tłumaczenia": Haiku asked of every translation kept without that
  answer whether the museum's text is about the work. Where it is not (an
  artist's life, a series, a collection), Sonnet writes a note in its place;
  the translation stays shown until the note is in.
- "Przepisz notki w nowych stylach": the notes written before the styles
  written anew by Sonnet, each in the next of the five.

A text whose new answer did not come, or came unusable, stays as it was.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

import httpx

from ..library.models import ItemKind, Note
from .client import HAIKU, SONNET, AiUnavailable, cost, request
from .jobs import Usage
from .night_order import NightOrder
from .pl_text import KIND as PL_TEXT
from .pl_text import NOTE_USAGE, clean, description

if TYPE_CHECKING:
    from ..library import Item, Library
    from .client import Claude
    from .pl_text import PlTextJob

log = logging.getLogger(__name__)

#: What the spending is counted under.
KIND = "text_review"
STATE = "text_review"
#: A check: the museum's text in, one word out (with a little thinking).
CHECK_USAGE = Usage(input_tokens=700, cache_read_input_tokens=0, output_tokens=150)
#: Questions in one batch: a check is a few hundred words; a note carries
#: its picture, so fewer go together.
CHECKS_PER_BATCH = 2000
NOTES_PER_BATCH = 500
#: How often the thread looks at its batches, and waits when it has none.
POLL = 300.0
IDLE = 3600.0

CHECK_SYSTEM = """Dostajesz dane dzieła sztuki i tekst, który muzeum podaje jako jego opis. \
Oceń, czy ten tekst mówi o tym konkretnym dziele.

"about_work": true, gdy tekst mówi o tym dziele (co przedstawia, jak powstało, jego dzieje, \
choćby jednym zdaniem). false, gdy to tylko ogólny tekst: życiorys artysty, opis serii, zbioru, \
epoki, miejsca albo techniki, bez niczego o samym dziele."""

CHECK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"about_work": {"type": "boolean"}},
    "required": ["about_work"],
    "additionalProperties": False,
}


def check_usd() -> float:
    return cost(HAIKU, CHECK_USAGE, batch=True)


def note_usd() -> float:
    return cost(SONNET, NOTE_USAGE, batch=True)


class TextReview(NightOrder):
    """Looks over the Polish texts kept, at the owner's tap."""

    name = "text review"

    def __init__(self, library: Library, claude: Claude, job: PlTextJob) -> None:
        self.library = library
        self.claude = claude
        self.job = job
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    # -- what is kept ----------------------------------------------------------

    def _state(self) -> dict[str, Any]:
        return dict(self.library.get_state(STATE, {}) or {})

    def _save(self, state: dict[str, Any]) -> None:
        self.library.set_state(STATE, state)

    def _texts(self) -> dict[str, Note]:
        return {
            item_id: note
            for item_id, note in self.library.notes(PL_TEXT).items()
            if "title" in note.data
        }

    @staticmethod
    def _written(note: Note) -> str:
        return str(note.data.get("written") or "translation")

    def by_step(self) -> dict[str, list[str]]:
        """The texts kept, by what the review would do with them: the
        translations without Haiku's word on their museum text
        ("unchecked"), those found not to be about the work and still
        without their note ("general"), the notes written before the five
        styles ("unstyled"), and the rest of the translations ("fine")."""
        out: dict[str, list[str]] = {"unchecked": [], "general": [], "unstyled": [], "fine": []}
        for item_id, note in self._texts().items():
            if self._written(note) == "note":
                if not note.data.get("style"):
                    out["unstyled"].append(item_id)
                continue
            about = note.data.get("about_work")
            out["unchecked" if about is None else "general" if about is False else "fine"].append(
                item_id
            )
        return out

    def _busy(self, state: dict[str, Any]) -> set[str]:
        """Works in an order now or waiting to be sent."""
        out: set[str] = set()
        for order in state.get("orders", []):
            out.update(order["items"])
        for ids in (state.get("queue") or {}).values():
            out.update(ids)
        return out

    def view(self) -> dict[str, Any]:
        """What Konfiguracja shows."""
        state = self._state()
        busy = self._busy(state)
        texts = self.by_step()
        unchecked, general, unstyled = (
            [i for i in texts[name] if i not in busy]
            for name in ("unchecked", "general", "unstyled")
        )
        orders = state.get("orders", [])
        queue = state.get("queue") or {}

        def doing(step: str) -> int:
            asked = sum(len(o["items"]) for o in orders if o["step"] == step)
            return asked + len(queue.get(step, []))

        return {
            "translations": len(texts["unchecked"]) + len(texts["general"]) + len(texts["fine"]),
            "unchecked": len(unchecked),
            "general": len(general),
            "unstyled": len(unstyled),
            "running": bool(orders or any(queue.values())),
            "checking": doing("check"),
            "writing": doing("note"),
            "checked": int(state.get("checked", 0)),
            "found": int(state.get("found", 0)),
            "written": int(state.get("written", 0)),
            "spent_usd": round(float(state.get("usd", 0.0)), 4),
            "check_usd": round(len(unchecked) * check_usd(), 4),
            "note_usd": round(note_usd(), 4),
            "general_usd": round(len(general) * note_usd(), 4),
            "restyle_usd": round(len(unstyled) * note_usd(), 4),
        }

    # -- the orders ------------------------------------------------------------

    def _item(self, item_id: str) -> Item | None:
        item = self.library.get(item_id)
        if item is None or item.kind != ItemKind.ARTWORK:
            return None
        return item

    def start(self, check: bool = True, restyle: bool = False) -> int:
        """The owner's tap: the translations not checked yet (``check``),
        those found not to be about the work, and the notes before the
        styles (``restyle``) queued for the thread to send. How many; 0 when
        an order is under way or nothing waits."""
        with self._lock:
            state = self._state()
            if state.get("orders") or any((state.get("queue") or {}).values()):
                return 0
            texts = self.by_step()
            queue: dict[str, list[str]] = {"check": [], "note": []}
            if check:
                queue["check"] = texts["unchecked"]
                queue["note"] = texts["general"]
            if restyle:
                queue["note"] += texts["unstyled"]
            count = len(queue["check"]) + len(queue["note"])
            if not count:
                return 0
            state["queue"] = queue
            self._save(state)
        log.info(
            "text review: %d checks and %d notes queued", len(queue["check"]), len(queue["note"])
        )
        self._wake.set()
        return count

    def check_request(self, item: Item) -> dict[str, Any]:
        lines = [f"Tytuł: {item.title}"]
        if item.artist:
            lines.append(f"Artysta: {item.artist}")
        if item.date_text:
            lines.append(f"Data: {item.date_text}")
        text = "\n".join([*lines, "", "Tekst muzeum:", description(item)])
        return request(
            model=HAIKU,
            system=CHECK_SYSTEM,
            content=[{"type": "text", "text": text}],
            schema=CHECK_SCHEMA,
            max_tokens=1000,
        )

    def _params(self, step: str, item: Item) -> dict[str, Any] | None:
        if step == "check":
            if not description(item):
                return None
            return self.check_request(item)
        try:
            return self.job.note_params(item, general=bool(description(item)))
        except (OSError, httpx.HTTPError) as err:
            log.warning("text review: no note for %s (%s)", item.id, err)
            return None

    def send_queued(self) -> int:
        """The queue sent, a batch at a time (the notes' pictures and facts
        are read here, so not at the tap). How many questions went."""
        sent = 0
        for step, size in (("check", CHECKS_PER_BATCH), ("note", NOTES_PER_BATCH)):
            while not self._stop.is_set():
                with self._lock:
                    state = self._state()
                    ids = list((state.get("queue") or {}).get(step, []))
                if not ids:
                    break
                chunk, rest = ids[:size], ids[size:]
                requests: list[dict[str, Any]] = []
                items: list[str] = []
                for item_id in chunk:
                    item = self._item(item_id)
                    params = self._params(step, item) if item is not None else None
                    if params is None:
                        continue
                    requests.append({"custom_id": f"{step[0]}{len(items)}", "params": params})
                    items.append(item_id)
                batch = self.send(requests) if requests else None
                with self._lock:
                    state = self._state()
                    queue = dict(state.get("queue") or {})
                    if requests and batch is None:
                        # Not sent (the limit, no key): what is left waits for a new tap.
                        state.pop("queue", None)
                        self._save(state)
                        return sent
                    queue[step] = rest
                    state["queue"] = queue
                    if batch is not None:
                        orders = list(state.get("orders", []))
                        orders.append({"batch": batch, "step": step, "items": items})
                        state["orders"] = orders
                        sent += len(items)
                        log.info("text review: %d %ss asked (batch %s)", len(items), step, batch)
                    self._save(state)
        return sent

    # -- the answers -----------------------------------------------------------

    def collect(self) -> bool | None:
        """The answers of the orders that ended put in: True when one was,
        False while they run, None without an order."""
        orders = self._state().get("orders", [])
        if not orders:
            return None
        done = False
        for order in orders:
            results = self.answers(order["batch"])
            if results is None:
                continue
            if order["step"] == "check":
                self._checked(order, dict(results))
            else:
                self._written_notes(order, dict(results))
            done = True
        return done

    def _finish(self, batch: str, counts: dict[str, int], usd: float, notes: list[str]) -> None:
        with self._lock:
            state = self._state()
            state["orders"] = [o for o in state.get("orders", []) if o["batch"] != batch]
            for name, n in counts.items():
                state[name] = int(state.get(name, 0)) + n
            state["usd"] = float(state.get("usd", 0.0)) + usd
            if notes:
                queue = dict(state.get("queue") or {})
                queue["note"] = [*queue.get("note", []), *notes]
                state["queue"] = queue
            self._save(state)

    def _checked(self, order: dict[str, Any], by_id: dict[str, Any]) -> None:
        usd, checked, found = 0.0, 0, []
        for n, item_id in enumerate(order["items"]):
            message = by_id.get(f"c{n}")
            if message is None:
                continue
            answer = self.claude.answer(KIND, HAIKU, message, batch=True)
            usd += answer.cost_usd
            if answer.data is None or not isinstance(answer.data.get("about_work"), bool):
                continue
            note = self.library.note(item_id, PL_TEXT)
            if note is None or "title" not in note.data:
                continue
            about = bool(answer.data["about_work"])
            self.library.save_note(
                note.model_copy(update={"data": {**note.data, "about_work": about}})
            )
            checked += 1
            if not about:
                found.append(item_id)
        self._finish(order["batch"], {"checked": checked, "found": len(found)}, usd, found)
        log.info(
            "text review: %d translations checked, %d not about the work, %.2f USD",
            checked,
            len(found),
            usd,
        )

    def _written_notes(self, order: dict[str, Any], by_id: dict[str, Any]) -> None:
        usd, written = 0.0, 0
        for n, item_id in enumerate(order["items"]):
            message = by_id.get(f"n{n}")
            item = self._item(item_id)
            if message is None or item is None:
                continue
            answer = self.claude.answer(KIND, SONNET, message, batch=True)
            usd += answer.cost_usd
            data = answer.data
            if data is None or "style" not in data:
                continue
            data["general"] = bool(description(item))
            text = clean(data, item, self.job.facts(item))
            if text is None:
                continue  # unusable: the text kept stays
            self.library.save_note(
                Note(
                    item_id=item_id,
                    kind=PL_TEXT,
                    model=SONNET,
                    prompt_version=self.job.prompt_version,
                    source_hash=self.job.source_hash(item),
                    data=text.model_dump(),
                )
            )
            written += 1
        self._finish(order["batch"], {"written": written}, usd, [])
        log.info("text review: %d notes written, %.2f USD", written, usd)

    # -- the thread ----------------------------------------------------------

    def start_thread(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="text-review", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def look(self) -> bool:
        """One look: the ended orders put in, the queue sent. Whether
        anything is under way."""
        self.collect()
        self.send_queued()
        state = self._state()
        return bool(state.get("orders") or any((state.get("queue") or {}).values()))

    def _run(self) -> None:
        while not self._stop.is_set():
            pause = IDLE
            try:
                if self.look():
                    pause = POLL
            except AiUnavailable as err:
                log.info("text review: %s", err)
            except Exception:
                log.exception("text review: a round failed")
            self._wake.wait(pause)
            self._wake.clear()
