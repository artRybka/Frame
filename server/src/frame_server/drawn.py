"""The study sheets drawn by the image model (``ai.drawn``): made once in
the background, kept on disk.

A drawn sheet costs about 0.15 USD and every answer of the model differs,
so one is made once for a take and never thrown away by the server (a take
put aside for another keeps its sheet, should the owner go back to it).
What is kept for a take (``<work>-<key>-…`` in ``drawn/``):

- ``page.jpg``: the study on the app's light page, with the page's margin
  on each side of the field, where one wash and one line run out;
- ``m<n>.png``: the pencil line of the take's n-th titled mark alone
  (the field's size; the app gives it its colour);
- ``meta.json``: the marks' colours, where their numbers stand, what the
  answers cost.

Which takes get one, and when (Mateusz 2026-11-12 22:32: "Nowe od razu,
zapisane przez Batch po aktualizacji dla obniżenia kosztu lub poprzez
"Wykonaj ponowną analizę" od razu"):

- at once, one after another: the takes of pages written since the sheets
  began to be drawn (:data:`SINCE`), and a take the owner had made anew
  (``ai.drawn.AT_ONCE``);
- through Google's Batch, at half the price and within a day: the takes
  of the pages saved before, some at a time, the newest page's first. A
  batch is two rounds: the studies, then over each study its lines and
  what runs out of it (``batch.json`` holds where it is, so that a
  restart loses nothing).

Until a take's sheet is there the app shows the sheet made here
(``sheets``). A take whose sheet could not be drawn twice (the model
will not redraw some works) is left with that one.
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
import zlib
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image

from .ai.check import page_views
from .ai.client import AiUnavailable
from .ai.composition import PAGES, cropped
from .ai.drawn import (
    AT_ONCE,
    KIND,
    SPILL,
    TYPICAL_USD,
    Sheet,
    draw,
    lines_ask,
    put_together,
    study_prompt,
)
from .ai.gemini import Ask, GeminiRejected, NoCredit, NotDrawn, Painter
from .ai.jobs import listed, relist, text_hash
from .imaging import drawn as imaging
from .imaging.layout import load_image
from .library.repo import now_iso

if TYPE_CHECKING:
    from .ai.daily import View
    from .library import ImageCache, Item, Library

log = logging.getLogger(__name__)

#: Raised when the sheets should all be drawn anew (never lightly: each is paid for).
LOOK = 1
#: The picture a sheet is drawn from is at most this long.
SOURCE_SIDE = 2000
#: Since when the pages are new ones (state): when the sheets were first drawn.
SINCE = "drawn_since"
#: The background lets the server start first, rests between two sheets,
#: looks again this often when none is wanted; a sheet that could not be
#: drawn, or the key's trouble, is tried again after this long.
START = 120.0
REST = 5.0
IDLE = 60.0
AGAIN = 3600.0
#: A take's sheet is tried this many times, then left.
TRIES = 2
#: The saved pages' takes handed to Google's Batch at a time, how often
#: its answers are looked for, and about what a sheet costs there.
BATCH_TAKES = 20
BATCH_LOOK = 600.0
BATCH_USD = TYPICAL_USD / 2
#: Why no sheet is drawn now, as the app is told (``AiView.gemini_error``).
NO_CREDIT = "no_credit"
KEY_REJECTED = "key_rejected"
LIMIT = "limit"

Take = tuple["Item", "View"]


class DrawnSheets:
    def __init__(self, library: Library, images: ImageCache, painter: Painter) -> None:
        self.library = library
        self.images = images
        self.painter = painter
        self.dir = images.thumbs.parent / "drawn"
        #: Why none is drawn now (one of the words above), and until when.
        self.error: str | None = None
        self._until = 0.0
        #: What is kept, as read (a kept sheet does not change).
        self._kept: dict[str, dict[str, Any]] = {}
        #: Takes whose sheet could not be drawn, and when.
        self._failed: dict[str, float] = {}
        #: How many times each was tried in vain (``tries.json``), once read.
        self._tried: dict[str, int] | None = None
        #: When the batch's answers were last looked for.
        self._looked = 0.0
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- what is kept ---------------------------------------------------------

    @staticmethod
    def key(view: View) -> str:
        """What a take's drawn sheet is made of, as a few letters: the
        picture's field and where its titled marks lie. Not their words: a
        text put right does not have the sheet paid for again."""
        field = view.field.model_dump_json() if view.field is not None else ""
        marks = "|".join(
            f"{m.shape}:" + ",".join(f"{p.x:.4f} {p.y:.4f}" for p in m.points)
            for m in view.marks
            if m.title
        )
        return text_hash(LOOK, field, marks)[:10]

    def _stem(self, item: Item, key: str) -> str:
        return f"{item.file_stem}-{key}"

    def meta(self, item: Item, view: View) -> dict[str, Any] | None:
        """What is kept of the take's drawn sheet; None when it has none."""
        stem = self._stem(item, self.key(view))
        if stem in self._kept:
            return self._kept[stem]
        try:
            kept = json.loads((self.dir / f"{stem}-meta.json").read_text())
        except (OSError, ValueError):
            return None
        if not isinstance(kept, dict):
            return None
        self._kept[stem] = kept
        return kept

    def part(self, item: Item, key: str, part: str) -> Path | None:
        """The file of a part of a sheet: ``page``, or ``m1``… (a mark's
        line); None when there is none."""
        if part == "page":
            name = "page.jpg"
        elif part[:1] == "m" and part[1:].isdigit():
            name = f"{part}.png"
        else:
            return None
        path = self.dir / f"{self._stem(item, key)}-{name}"
        return path if path.is_file() else None

    def _keep(self, item: Item, view: View, sheet: Sheet) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        stem = self._stem(item, self.key(view))
        files: dict[str, bytes] = {"page.jpg": sheet.page}
        for n, layer in enumerate(sheet.layers, start=1):
            if layer is not None:
                files[f"m{n}.png"] = layer
        titled = [n for n, m in enumerate(view.marks) if m.title]
        meta = {
            "look": LOOK,
            "made": now_iso(),
            "size": list(sheet.size),
            #: Which of the take's marks each line is (its place among them).
            "marks": titled[: len(sheet.layers)],
            "layers": [layer is not None for layer in sheet.layers],
            "colours": sheet.colours,
            "numbers": [[[round(x, 4), round(y, 4)] for x, y in spots] for spots in sheet.numbers],
            "cost": sheet.cost,
        }
        files["meta.json"] = json.dumps(meta).encode()  # last: with it the sheet is there
        for name, data in files.items():
            self._write(f"{stem}-{name}", data)

    def _write(self, name: str, data: bytes) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / name
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    # -- which are wanted -----------------------------------------------------

    def enabled(self) -> bool:
        return self.painter.config.drawn

    def _resting(self) -> bool:
        return time.monotonic() < self._until

    def _rest(self, why: str | None, seconds: float = AGAIN) -> None:
        self.error = why
        self._until = time.monotonic() + seconds

    def again(self) -> None:
        """The key or the limit changed: what stood in the way may be gone."""
        self.error = None
        self._until = 0.0
        self._failed.clear()
        self._wake.set()

    def _tries(self) -> dict[str, int]:
        if self._tried is None:
            try:
                kept = json.loads((self.dir / "tries.json").read_text())
            except (OSError, ValueError):
                kept = {}
            self._tried = kept if isinstance(kept, dict) else {}
        return self._tried

    def _fail(self, stem: str, why: object, count: bool = True) -> None:
        """A take's sheet could not be drawn: tried again in an hour, and
        (``count``: the model's doing, not the picture's or the network's)
        no more once tried :data:`TRIES` times."""
        log.warning("sheet %s not drawn: %s", stem, why)
        self._failed[stem] = time.monotonic()
        if count:
            tries = self._tries()
            tries[stem] = tries.get(stem, 0) + 1
            self._write("tries.json", json.dumps(tries).encode())

    def _left(self, stem: str) -> bool:
        return self._tries().get(stem, 0) >= TRIES

    def _waits(self, stem: str) -> bool:
        when = self._failed.get(stem)
        return when is not None and time.monotonic() - when < AGAIN

    def _since(self) -> str:
        since = self.library.get_state(SINCE)
        if not since:
            since = now_iso()
            self.library.set_state(SINCE, since)
        return str(since)

    def _shown(self, item_id: str, key: str) -> View | None:
        """The take ``key`` names among those the work's pages show."""
        for kind in PAGES:
            note = self.library.note(item_id, kind)
            for view in page_views(note.data) if note is not None else []:
                if self.key(view) == key:
                    return view
        return None

    def _takes(self) -> list[tuple[bool, Item, View]]:
        """The takes the pages show that have no sheet and are not left
        without: the newest page's first, each with whether it is drawn at
        once (a new page's, one the owner had made anew)."""
        since = self._since()
        anew = listed(self.library, AT_ONCE)
        found: dict[str, tuple[str, bool, Item, View]] = {}
        for kind in PAGES:
            for item_id, note in self.library.notes(kind).items():
                views = page_views(note.data)
                item = self.library.get(item_id) if views else None
                if item is None:
                    continue
                stem = self._stem(item, self.key(views[0]))
                if stem in found or self._left(stem) or self.meta(item, views[0]) is not None:
                    continue
                made = str(note.created_at)
                found[stem] = (made, made >= since or item_id in anew, item, views[0])
        newest = sorted(found.values(), key=lambda entry: entry[0], reverse=True)
        return [(now, item, view) for _, now, item, view in newest]

    def at_once(self) -> list[Take]:
        """The takes whose sheet is drawn now, in their order."""
        return [
            (item, view)
            for now, item, view in self._takes()
            if now and not self._waits(self._stem(item, self.key(view)))
        ]

    def saved(self) -> list[Take]:
        """The takes of the pages saved before, which go through the
        Batch: those not in it yet."""
        state = self._batch()
        there = {(item_id, key) for item_id, key in state["takes"]} if state else set()
        return [
            (item, view)
            for now, item, view in self._takes()
            if not now and (item.id, self.key(view)) not in there
        ]

    def pending(self, item: Item, view: View) -> bool:
        """Whether the take's sheet is being drawn now (a minute or two):
        the app looks again."""
        if not self.enabled() or self._resting() or self.meta(item, view) is not None:
            return False
        stem = self._stem(item, self.key(view))
        if self._left(stem) or self._waits(stem):
            return False
        if item.id in listed(self.library, AT_ONCE):
            return True
        since = self._since()
        notes = (self.library.note(item.id, kind) for kind in PAGES)
        return any(note is not None and str(note.created_at) >= since for note in notes)

    def counts(self) -> tuple[int, int]:
        """How many saved pages' takes still wait for the Batch, and how
        many are in it now (Konfiguracja)."""
        if not self.enabled():
            return 0, 0
        state = self._batch()
        return len(self.saved()), len(state["takes"]) if state else 0

    # -- drawn at once ----------------------------------------------------------

    def _work(self, item: Item, view: View) -> Image.Image:
        """The work as the model gets it: its field alone, when the take has one."""
        source, _ = self.images.picture(item)
        img = load_image(source.read_bytes()).convert("RGB")
        img.thumbnail((SOURCE_SIDE, SOURCE_SIDE), Image.Resampling.LANCZOS)
        if view.field is not None:
            img = cropped(img, view.field)
        return imaging.sent(img)

    @staticmethod
    def _seed(item: Item) -> int:
        return zlib.crc32(item.id.encode())

    def make(self, item: Item, view: View) -> None:
        """Draws the take's sheet now and keeps it (three paid answers)."""
        paint = partial(self.painter.paint, KIND)
        sheet = draw(self._work(item, view), view.inside(), paint, seed=self._seed(item))
        self._keep(item, view, sheet)
        log.info("sheet of %s drawn: %s", item.id, sheet.cost)

    def _now(self, item: Item, view: View) -> bool:
        stem = self._stem(item, self.key(view))
        try:
            self.make(item, view)
        except NoCredit:
            self._rest(NO_CREDIT)
            return False
        except GeminiRejected:
            self._rest(KEY_REJECTED)
            return False
        except AiUnavailable as err:  # the month's limit; the key taken away meanwhile
            log.info("sheets not drawn now: %s", err)
            self._rest(LIMIT)
            return False
        except NotDrawn as err:  # this answer
            self._fail(stem, err)
            return True
        except Exception as err:  # this one's picture, the network
            self._fail(stem, err, count=False)
            return True
        self.error = None
        relist(self.library, AT_ONCE, item.id, on=False)
        return True

    # -- through the Batch ------------------------------------------------------

    def _batch(self) -> dict[str, Any] | None:
        """Where the open batch is: its round ("study", "lines"), Google's
        name for it ("" when the round is still to be handed over), its
        takes (work, key) and what their answers cost so far."""
        try:
            state = json.loads((self.dir / "batch.json").read_text())
        except (OSError, ValueError):
            return None
        return state if isinstance(state, dict) and state.get("takes") else None

    def _set_batch(self, state: dict[str, Any] | None) -> None:
        if state is None or not state["takes"]:
            with contextlib.suppress(OSError):
                (self.dir / "batch.json").unlink()
        else:
            self._write("batch.json", json.dumps(state).encode())

    def _hand(self, asks: list[Ask]) -> str | None:
        """The questions handed to the Batch: its name; None when they
        cannot be now (told, and tried again later)."""
        try:
            return self.painter.batch(KIND, asks)
        except NoCredit:
            self._rest(NO_CREDIT)
        except GeminiRejected:
            self._rest(KEY_REJECTED)
        except AiUnavailable as err:
            log.info("sheets not handed to the batch now: %s", err)
            self._rest(LIMIT)
        except Exception as err:  # the network, Google's trouble
            log.warning("sheets not handed to the batch: %s", err)
            self._rest(None, BATCH_LOOK)
        return None

    def _study_file(self, stem: str) -> Path:
        return self.dir / f"{stem}-study.png"

    def _begin(self) -> bool:
        """Hands the studies of some saved pages' takes to the Batch."""
        afford = int(self.painter.claude.budget_left() / BATCH_USD)
        saved = self.saved()[: min(BATCH_TAKES, max(afford, 0))]
        if not saved:
            if afford <= 0 and self.saved():
                self._rest(LIMIT)
            return False
        asks, takes = [], []
        for item, view in saved:
            stem = self._stem(item, self.key(view))
            try:
                work = self._work(item, view)
            except Exception as err:  # the picture cannot be had
                self._fail(stem, err, count=False)
                continue
            asks.append(Ask(stem, study_prompt(view.inside()), [work]))
            takes.append([item.id, self.key(view)])
        name = self._hand(asks) if asks else None
        if name is not None:
            self._set_batch({"round": "study", "name": name, "takes": takes, "cost": {}})
            self._looked = time.monotonic()
            log.info("%d sheets' studies handed to the batch", len(takes))
        return False

    def _each(self, state: dict[str, Any]) -> list[tuple[str, Item, View]]:
        """The batch's takes that the pages still show."""
        found = []
        for item_id, key in state["takes"]:
            item = self.library.get(item_id)
            view = self._shown(item_id, key) if item is not None else None
            if item is not None and view is not None and self.meta(item, view) is None:
                found.append((self._stem(item, key), item, view))
        return found

    def _studies_in(self, state: dict[str, Any], answers: dict[str, Any]) -> None:
        """The studies came: each that is its work's is kept for the
        second round."""
        takes, cost = [], {}
        for stem, item, view in self._each(state):
            answer = answers.get(stem)
            if not isinstance(answer, tuple):
                self._fail(stem, answer or "no answer")
                continue
            study, usd = answer
            try:
                _, off = imaging.measure(self._work(item, view), study)
            except Exception as err:
                self._fail(stem, err, count=False)
                continue
            if off > imaging.FAR_OFF:
                self._fail(stem, f"the study lies {off:.1f}% off the work")
                continue
            self.dir.mkdir(parents=True, exist_ok=True)
            study.save(self._study_file(stem), "PNG")
            takes.append([item.id, self.key(view)])
            cost[stem] = {"underlay": usd}
        self._set_batch({"round": "lines", "name": "", "takes": takes, "cost": cost})

    def _second(self, state: dict[str, Any]) -> None:
        """Hands the second round to the Batch: over each study the take's
        lines, and what runs out of it."""
        asks = []
        for stem, _, view in self._each(state):
            try:
                study = Image.open(self._study_file(stem)).convert("RGB")
            except OSError as err:
                self._fail(stem, err, count=False)
                continue
            ask = lines_ask(study, view.inside())
            if ask is not None:
                asks.append(Ask(f"{stem}/lines", ask[0], [study]))
            asks.append(Ask(f"{stem}/spill", SPILL, [imaging.padded(study)[0]]))
        if not asks:
            self._set_batch(None)
            return
        name = self._hand(asks)
        if name is not None:
            self._set_batch({**state, "name": name})
            self._looked = time.monotonic()

    def _lines_in(self, state: dict[str, Any], answers: dict[str, Any]) -> None:
        """The second round came: the sheets are put together and kept."""
        for stem, item, view in self._each(state):
            cost = dict(state["cost"].get(stem) or {})
            lines, spill = answers.get(f"{stem}/lines"), answers.get(f"{stem}/spill")
            inside = view.inside()
            try:
                study = Image.open(self._study_file(stem)).convert("RGB")
                wanted = lines_ask(study, inside) is not None
                if wanted and not isinstance(lines, tuple):
                    raise NotDrawn(f"no lines: {lines or 'no answer'}")
                marked = None
                if wanted and isinstance(lines, tuple):
                    marked, cost["lines"] = lines
                spilt = None
                if isinstance(spill, tuple):
                    spilt, cost["spill"] = spill
                work = self._work(item, view)
                sheet = put_together(work, inside, study, marked, spilt, cost, self._seed(item))
            except NotDrawn as err:
                self._fail(stem, err)
                continue
            except Exception as err:
                self._fail(stem, err, count=False)
                continue
            self._keep(item, view, sheet)
            log.info("sheet of %s drawn through the batch: %s", item.id, sheet.cost)
        for item_id, key in state["takes"]:
            done = self.library.get(item_id)
            if done is not None:
                with contextlib.suppress(OSError):
                    self._study_file(self._stem(done, key)).unlink()
        self._set_batch(None)

    def _batched(self) -> bool:
        """A step of the Batch; False when there is nothing to do now."""
        state = self._batch()
        if state is None:
            return self._begin()
        if not state["name"]:  # its second round is still to be handed over
            self._second(state)
            return False
        if time.monotonic() - self._looked < BATCH_LOOK and self._looked:
            return False
        self._looked = time.monotonic()
        try:
            answers = self.painter.batched(KIND, state["name"])
        except NotDrawn as err:  # the batch is lost: its takes go into another
            log.warning("the sheets' batch is lost: %s", err)
            self._set_batch(None)
            return False
        except AiUnavailable as err:
            log.info("the sheets' batch not looked at: %s", err)
            self._rest(LIMIT if not isinstance(err, NoCredit | GeminiRejected) else KEY_REJECTED)
            return False
        except Exception as err:  # the network
            log.warning("the sheets' batch not looked at: %s", err)
            return False
        if answers is None:
            return False
        if state["round"] == "study":
            self._studies_in(state, answers)
        else:
            self._lines_in(state, answers)
        return True

    # -- the background ---------------------------------------------------------

    def ahead(self) -> bool:
        """Draws one sheet that is wanted now, else takes a step of the
        Batch; False when there is nothing to do now."""
        if not self.enabled() or self._resting():
            return False
        now = self.at_once()
        if now:
            return self._now(*now[0])
        return self._batched()

    def start(self) -> None:
        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="drawn", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self._thread = None

    def _run(self) -> None:
        if self._stop.wait(START):
            return
        while not self._stop.is_set():
            try:
                busy = self.ahead()
            except Exception:
                log.exception("sheets drawn")
                busy = False
            if busy:
                self._stop.wait(REST)
            else:
                self._wake.wait(IDLE)
            self._wake.clear()
