"""The creative restorer ("Kreatywny restaurator", Mateusz 2026-11-12): a
work whose picture is small for the frame (``low_res.LOW_SIDE``) drawn again
larger by Google's image model (Nano Banana 2.1) from the picture it shows.

A trial on de Chirico's WikiArt pictures (800 px, 2026-11-12) gave some
2000 px in the same proportions, everything where it was (within 0.2%),
with crisp edges, brushwork and canvas: invented, not recovered (its fine
detail agrees with the real file's as 0.4 does, a plain enlargement's as
0.75), so the card says so ("Kreatywny restaurator" under "Zdjęcie
dzieła") and the work's tiles carry amber sparkles in place of the low
resolution's dots.

The drawing is kept the way a copy the owner brought is
(:meth:`Sharper.bring`): for good, in the work's own id, as his pick
(``SharperCopy.chosen``), so the night's looks for sharper copies leave it
be and nothing takes it for another work; "Przywróć zdjęcie muzeum" goes
back to the museum's picture. The gatekeeper does not ask about it
(``gatekeeper.asked_by_rules``): it is the owner's.

Since 2026-11-22 the drawing is SeedVR2's on fal.ai when Konfiguracja
holds fal's key (:mod:`.ai.fal`; Mateusz 09:14 UTC, after two rounds of
trials: nothing moved, nothing invented, about 0.004 USD a work): the
same detail drawn larger, refusing nothing, so the works Google would not
draw are drawn too. Google's model stays the spare: without fal's key,
or when fal gives no picture for a work from its card.

One work at a time from its card ("…" → "Kreatywny restaurator", about
25 s), or many at once through the Batch API: the owner's favourites
under the threshold from Konfiguracja, or a playlist's from its "…"
(Mateusz 2026-11-13) (half the price, within 24 hours,
looked at every :data:`POLL` seconds). A picture the model would not draw
(``image_recitation``: it took a known painting for one it may not copy)
is asked for again, :data:`REFUSED_TRIES` times in all (a refusal costs
nothing: Google answers it with an error and no bill; Mateusz 2026-11-13,
Delacroix's "Rzeź na Chios"), then noted and never sent again. The first
:data:`FIRST_TRIES` go to Nano Banana 2.1, the rest to the dearer Nano
Banana Pro (:func:`model_for`; Mateusz 2026-11-16: "gdy pierwsze 2 zawiodą
odpalajmy pro"), which takes works 2.1 refuses and keeps nearer the
picture; a drawing 2.1 gave that cannot be used (none, or in other
proportions) is asked of it again, then of Pro, once.

The drawing comes back in the colours of the picture it was drawn from
(:func:`recoloured`; Mateusz 2026-11-16: "Bywa że restauracja dzieła
zmienia nieznacznie kolorystykę"): the model's detail on the museum's
tones.
"""

from __future__ import annotations

import io
import logging
import threading
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import cv2
import httpx
import numpy as np
from PIL import Image

from .ai import fal
from .ai.client import AiUnavailable
from .ai.gemini import MODEL, PRO, Ask, NotDrawn
from .imaging.color import linear_to_oklab, linear_to_u8, oklab_to_linear, u8_to_linear
from .library import Item, ItemKind
from .library.low_res import LOW_SIDE, low_side
from .library.models import Note
from .library.viewer import OWNER_ID

if TYPE_CHECKING:
    from .ai.fal import Upscaler
    from .ai.gemini import Painter
    from .library import ImageCache, Library
    from .sharper import Sharper

log = logging.getLogger(__name__)

KIND = "restorer"
#: Where the drawing is from, as the card names it.
ORIGIN = "Kreatywny restaurator"
#: The model's output: some 2048 px on the long side.
SIZE = "2K"
#: A picture this long or longer gains nothing from the model's 2K.
LONGEST = 2048
#: The proportions of the drawing may differ from the picture's by this
#: share and are then set right; by more it is not taken.
SKEW_FIXED = 0.005
SKEW_MAX = 0.04
#: How coarse the colours taken back from the museum's picture are, in its
#: own pixels (:func:`recoloured`): finer than this is the drawing's own
#: detail; coarse enough that the drawing a pixel off the picture does not
#: fringe its edges.
COLOUR_SIGMA = 2.0
#: A drawing's note says it is in the picture's colours (``colours``):
#: the ones kept before are put in them once (:meth:`Restorer.recolour_kept`).
COLOURS = 1
#: Works in one batch: their pictures go in the request (inline, under
#: the API's 20 MB).
PER_BATCH = 24
#: Seconds between looks at the batches still waiting.
POLL = 600.0
#: About what one drawing costs, USD (2K through the Batch API: half of
#: the 0.06 the trial paid).
BATCH_USD = 0.03
#: The same of Pro (:data:`PRO`; the trial paid 0.14 at once).
PRO_BATCH_USD = 0.07
#: Seconds between looks while fal's pictures are waiting.
FAL_POLL = 20.0
#: The library state key of the batches waiting.
BATCHES = "restorer.batches"
#: A picture the model will not draw is asked for this many times in all,
#: from its card at once, through the Batch in as many batches (Mateusz
#: 2026-11-13: "ponawiaj próbę 5 razy"): Google now and then takes the
#: same question, and a refusal is not paid for.
REFUSED_TRIES = 5
#: Tries of Nano Banana 2.1 (:data:`MODEL`) before Pro (:data:`PRO`) is
#: asked (:func:`model_for`).
FIRST_TRIES = 2

PROMPT = """This is a small, low-resolution digital photograph of a painting. Produce the same \
photograph at a higher resolution: a faithful restoration and upscale, as a museum's \
high-resolution scan of this very painting would look.

Strict rules:
- Change nothing in the picture: the same composition, every shape, edge, figure, shadow, letter \
and object exactly where it is, same proportions, same framing and crop. Add nothing, remove \
nothing.
- Keep the colours and values exactly as they are (no brighter, no more saturated, no different \
white balance, no added contrast).
- Recover what a sharper photograph would show: crisp edges, the painter's brushwork and the \
canvas texture, consistent with the paint visible here. Remove JPEG blocks, ringing and blur.
- Do not smooth the paint into a digital illustration, do not invent fine detail that \
contradicts the painting, do not sharpen into halos.
- No border, frame, margin, signature or watermark that is not in the picture."""


class NotRestored(ValueError):
    """The work cannot be drawn again: ``code`` says why ("refused": the
    model would not draw it; "skewed": drawn in other proportions;
    "large": its picture is large enough; "not_drawn": no picture came
    back this time; "not_art")."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class Restorer:
    def __init__(
        self,
        library: Library,
        images: ImageCache,
        sharper: Sharper,
        painter: Painter,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        upscaler: Upscaler | None = None,
    ) -> None:
        self.library = library
        self.images = images
        self.sharper = sharper
        self.painter = painter
        #: fal's SeedVR2, the model asked first when it has a key.
        self.upscaler = upscaler
        self.clock = clock
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- what can be drawn -------------------------------------------------------------

    def by_fal(self) -> bool:
        """Whether the drawings are SeedVR2's (fal's key in Konfiguracja)."""
        return self.upscaler is not None and self.upscaler.enabled()

    def enabled(self) -> bool:
        """Whether anything can draw: fal's key or Google's."""
        return self.by_fal() or self.painter.enabled()

    @staticmethod
    def restored(item: Item) -> bool:
        return item.sharper is not None and item.sharper.restored

    def side(self, item: Item) -> int | None:
        """The long side of the picture the work shows, when known."""
        return self.images.long_side(item)

    def check(self, item: Item) -> None:
        """Raises :class:`NotRestored` for a work that is not drawn again."""
        if item.kind != ItemKind.ARTWORK or item.look is not None or item.part_of:
            raise NotRestored("not_art", "only a museum work is drawn again")
        side = self.side(item)
        if side is not None and side >= LONGEST and not self.restored(item):
            raise NotRestored("large", f"its picture is {side} px already")

    def refused(self) -> set[str]:
        """The works Google's model would not draw :data:`REFUSED_TRIES`
        times; none when SeedVR2 draws, which refuses nothing."""
        if self.by_fal():
            return set()
        return {
            item_id
            for item_id, note in self.library.notes(KIND).items()
            if note.data.get("status") == "refused" and _tries(note.data) >= REFUSED_TRIES
        }

    def _refusals(self, item_id: str) -> int:
        """How many times the model would not draw the work so far, or drew
        it unusably (:data:`FAILED`)."""
        note = self.library.note(item_id, KIND)
        if note is None or note.data.get("status") not in ("refused", FAILED):
            return 0
        return _tries(note.data)

    def waiting(self) -> set[str]:
        return {i for batch in self._batches() for i in batch.get("ids", [])}

    def candidates(self, items: Iterable[Item] | None = None) -> list[Item]:
        """The works whose picture is known to be small for the frame
        (``low_res.low_side``), not drawn yet, nor refused, nor waiting in
        a batch: of ``items`` (a playlist's), or of the owner's favourites."""
        skip = self.refused() | self.waiting()
        if items is None:
            found_ids = sorted(self.library.favorites(OWNER_ID))
            items = (i for i in map(self.library.get, found_ids) if i is not None)
        found: list[Item] = []
        seen: set[str] = set()
        for item in items:
            if item.id in seen or item.id in skip or self.restored(item) or item.excluded:
                continue
            seen.add(item.id)
            if item.look is None and low_side(item) > 0:
                found.append(item)
        return found

    def estimate(self, items: Iterable[Item] | None = None) -> tuple[int, float]:
        found = self.candidates(items)
        if self.by_fal():
            return len(found), round(len(found) * fal.TYPICAL_USD, 3)
        usd = sum(
            BATCH_USD if model_for(self._refusals(i.id)) == MODEL else PRO_BATCH_USD for i in found
        )
        return len(found), round(usd, 2)

    def counts(self) -> tuple[int, int]:
        """Works waiting in batches, and works drawn again."""
        drawn = sum(1 for i in self.library.all_items() if self.restored(i))
        return len(self.waiting()), drawn

    # -- one work ---------------------------------------------------------------------

    def _picture(self, item: Item) -> Image.Image:
        if item.cleaned_shown() is not None:
            # A work shown cleaned (``Item.cleaned``) is drawn from the
            # picture as it came: the drawing is cleaned after, the same.
            return self.images.before_cleaning(item, urgent=True).convert("RGB")
        # Without its original (a dead link), the thumbnail the card shows
        # (``ImageCache.picture``) is what is drawn larger.
        path, _original = self.images.picture(item, urgent=True)
        with Image.open(path) as img:
            return img.convert("RGB")

    def restore(self, item: Item) -> Item:
        """``item`` drawn again now (some 25 s), kept in place of its
        picture. Raises :class:`NotRestored`, and the painter's errors
        (no key, no credit, the model unavailable)."""
        stored = self.library.get(item.id) or item
        self.check(stored)
        if self.restored(stored):  # drawn from the museum's picture, not the drawing
            stored = self.sharper.keep_own(stored)
        picture = self._picture(stored)
        if self.by_fal():
            assert self.upscaler is not None
            try:
                drawn, usd = self.upscaler.upscale(KIND, picture, LONGEST)
                return self._keep(stored, picture, drawn, usd, fal.MODEL)
            except (fal.NotUpscaled, AiUnavailable, httpx.HTTPError) as err:
                if not self.painter.enabled():
                    if isinstance(err, AiUnavailable):
                        raise
                    raise NotRestored("not_drawn", str(err)) from err
                log.info("restorer: %s not drawn by SeedVR2, Google's then: %s", stored.id, err)
        tries = 0
        while True:
            model = model_for(tries)
            tries += 1
            try:
                drawn, usd = self.painter.paint(KIND, PROMPT, [picture], size=SIZE, model=model)
                return self._keep(stored, picture, drawn, usd, model)
            except NotDrawn as err:
                if not refusal(err):
                    if model == PRO:
                        raise NotRestored("not_drawn", str(err)) from err
                    log.info("restorer: %s not drawn by %s: %s", stored.id, model, err)
                    continue
                log.info(
                    "restorer: %s refused by %s (%d of %d)", stored.id, model, tries, REFUSED_TRIES
                )
                if tries >= REFUSED_TRIES:
                    self._note(
                        stored.id,
                        "refused",
                        why=str(err)[:300],
                        code=err.code,
                        tries=tries,
                        model=model,
                    )
                    raise NotRestored("refused", str(err)) from err
            except NotRestored:  # drawn in other proportions
                if model == PRO:
                    raise

    def _keep(
        self, item: Item, picture: Image.Image, drawn: Image.Image, usd: float, model: str = MODEL
    ) -> Item:
        try:
            fitted = recoloured(picture, fit(picture.size, drawn))
        except NotRestored as err:
            self._note(item.id, "skewed", why=str(err), usd=usd, model=model)
            raise
        buf = io.BytesIO()
        fitted.save(buf, "JPEG", quality=95)
        updated = self.sharper.bring(item, buf.getvalue(), ORIGIN, restored=True)
        self._note(
            item.id,
            "done",
            usd=usd,
            size=list(fitted.size),
            own=list(picture.size),
            colours=COLOURS,
            model=model,
        )
        log.info(
            "restorer: %s %s → %s by %s (%.3f USD)",
            item.id,
            picture.size,
            fitted.size,
            model,
            usd,
        )
        return updated

    def _note(self, item_id: str, status: str, *, model: str = MODEL, **data: Any) -> None:
        self.library.save_note(
            Note(
                item_id=item_id,
                kind=KIND,
                model=model,
                prompt_version="1",
                data={"status": status, "at": self.clock().isoformat(), **data},
            )
        )

    # -- the drawings kept before their colours were taken back -----------------------

    def recolour_kept(self) -> int:
        """The drawings kept before :func:`recoloured` put in the colours
        of the museum's picture they were drawn from, once (Mateusz
        2026-11-16: "Tak - poproszę"): nothing is drawn again or paid for,
        the museum's picture is downloaded again. One that cannot be had
        now is tried at the next start; how many were put in them."""
        done = 0
        for item in list(self.library.all_items()):
            if self._stop.is_set():
                break
            if not self.restored(item) or item.sharper is None:
                continue
            note = self.library.note(item.id, KIND)
            if note is not None and note.data.get("colours") == COLOURS:
                continue
            url = item.sharper.url
            try:
                drawing = self.images.sample(url)
                fitted = recoloured(self.images.before_drawn(item), drawing)
            except Exception as err:
                log.info("restorer: %s not recoloured: %s", item.id, err)
                continue
            buf = io.BytesIO()
            fitted.save(buf, "JPEG", quality=95)
            with self._lock:
                stored = self.library.get(item.id)
                if stored is None or stored.sharper is None or stored.sharper.url != url:
                    continue  # drawn again or put back meanwhile
                try:
                    self.sharper.bring(stored, buf.getvalue(), ORIGIN, restored=True)
                except ValueError as err:
                    log.info("restorer: %s not recoloured: %s", item.id, err)
                    continue
                data: dict[str, Any] = dict(note.data) if note is not None else {}
                status = str(data.pop("status", "done"))
                data["colours"] = COLOURS
                self._note(item.id, status, model=note.model if note else MODEL, **data)
            done += 1
            log.info("restorer: %s recoloured", item.id)
        return done

    # -- the favourites through the Batch API -----------------------------------------

    def _batches(self) -> list[dict[str, Any]]:
        batches = self.library.get_state(BATCHES, [])
        return batches if isinstance(batches, list) else []

    def order_favourites(self) -> int:
        """The favourites under the threshold sent in batches; how many."""
        return self.order()

    def order(self, items: Iterable[Item] | None = None) -> int:
        """The works under the threshold (of ``items``, a playlist's; else
        the owner's favourites) sent in batches; how many."""
        with self._lock:
            found = self.candidates(items)
            if self.by_fal():
                return self._order_fal(found)
            batches = self._batches()
            sent = 0
            by_model: dict[str, list[Item]] = {}
            for item in found:
                by_model.setdefault(model_for(self._refusals(item.id)), []).append(item)
            chunks = [(m, c) for m, its in by_model.items() for c in _chunks(its, PER_BATCH)]
            for model, chunk in chunks:
                pictures: dict[str, Image.Image] = {}  # by the work's id
                for item in chunk:
                    try:
                        self.check(item)
                        pictures[item.id] = self._picture(item)
                    except (NotRestored, OSError, ValueError) as err:
                        log.info("restorer: %s left out: %s", item.id, err)
                    except Exception as err:  # a download refused: next time
                        log.info("restorer: %s not had: %s", item.id, err)
                if not pictures:
                    continue
                asks = [Ask(i, PROMPT, [p], SIZE) for i, p in pictures.items()]
                name = self.painter.batch(KIND, asks, model=model)
                batches.append(
                    {
                        "name": name,
                        "model": model,
                        "ids": list(pictures),
                        "sizes": {k: list(v.size) for k, v in pictures.items()},
                        "at": self.clock().isoformat(),
                    }
                )
                self.library.set_state(BATCHES, batches)
                sent += len(pictures)
                log.info("restorer: batch %s of %s with %d works", name, model, len(pictures))
        if sent:
            self._wake.set()
        return sent

    def _order_fal(self, found: list[Item]) -> int:
        """``found`` sent to fal's queue, one picture each, kept as one
        "batch" whose requests :meth:`poll` looks after."""
        assert self.upscaler is not None
        batches = self._batches()
        requests: dict[str, str] = {}
        sizes: dict[str, list[int]] = {}
        for item in found:
            try:
                self.check(item)
                picture = self._picture(item)
                asked = self.upscaler.submit(picture, LONGEST)
            except AiUnavailable:
                raise  # no key, no credit, the month's limit: the rest waits too
            except (NotRestored, OSError, ValueError, fal.NotUpscaled) as err:
                log.info("restorer: %s left out: %s", item.id, err)
                continue
            except Exception as err:  # a download refused: next time
                log.info("restorer: %s not had: %s", item.id, err)
                continue
            requests[item.id] = asked.request_id
            sizes[item.id] = list(picture.size)
        if requests:
            batches.append(
                {
                    "name": f"fal:{self.clock().isoformat()}",
                    "model": fal.MODEL,
                    "ids": list(requests),
                    "requests": requests,
                    "sizes": sizes,
                    "at": self.clock().isoformat(),
                }
            )
            self.library.set_state(BATCHES, batches)
            log.info("restorer: %d works sent to SeedVR2", len(requests))
            self._wake.set()
        return len(requests)

    def _poll_fal(self, batch: dict[str, Any]) -> tuple[int, dict[str, Any] | None]:
        """The pictures of a fal batch that are ready kept; how many, and
        the batch with those still waiting (None when none is)."""
        assert self.upscaler is not None
        requests: dict[str, str] = dict(batch.get("requests") or {})
        drawn = 0
        for item_id, request_id in list(requests.items()):
            status = self.upscaler.state(request_id)
            if status in ("IN_QUEUE", "IN_PROGRESS"):
                continue
            del requests[item_id]
            if status != "COMPLETED":
                log.info("restorer: %s lost by fal (%s)", item_id, status)
                continue
            item = self.library.get(item_id)
            if item is None or self.restored(item):
                continue
            if item.sharper is not None and item.sharper.chosen:
                continue  # the owner picked another copy meanwhile
            try:
                answer = self.upscaler.result(KIND, request_id)
                picture = self._picture(item)
            except fal.NotUpscaled as err:
                log.info("restorer: %s not drawn by SeedVR2: %s", item_id, err)
                self._note(item_id, FAILED, why=str(err)[:300], tries=1, model=fal.MODEL)
                continue
            except Exception as err:
                log.info("restorer: %s not had again: %s", item_id, err)
                continue
            size = batch.get("sizes", {}).get(item_id)
            if size and tuple(size) != picture.size:
                continue  # its picture changed meanwhile: drawn from another
            try:
                self._keep(item, picture, answer[0], answer[1], fal.MODEL)
            except (NotRestored, ValueError) as err:
                log.info("restorer: %s not kept: %s", item_id, err)
                continue
            drawn += 1
        if not requests:
            return drawn, None
        return drawn, {**batch, "requests": requests, "ids": list(requests)}

    def poll(self) -> int:
        """The batches done taken in; how many works were drawn. The works
        the model would not draw yet fewer than :data:`REFUSED_TRIES` times
        are sent again in a new batch."""
        drawn = 0
        again: list[str] = []
        with self._lock:
            batches = self._batches()
            left = []
            for batch in batches:
                if batch.get("model") == fal.MODEL:
                    if not self.by_fal():
                        left.append(batch)  # its key forgotten: kept for when it is back
                        continue
                    try:
                        took, waiting = self._poll_fal(batch)
                    except (AiUnavailable, httpx.HTTPError) as err:
                        log.info("restorer: fal not asked now: %s", err)
                        left.append(batch)
                        continue
                    drawn += took
                    if waiting is not None:
                        left.append(waiting)
                    continue
                try:
                    model = str(batch.get("model") or MODEL)
                    answers = self.painter.batched(KIND, str(batch["name"]), model=model)
                except NotDrawn as err:  # lost: its works may be sent again
                    log.info("restorer: batch %s lost: %s", batch["name"], err)
                    continue
                if answers is None:
                    left.append(batch)
                    continue
                drawn += self._take(batch, answers, again)
            if left != batches:
                self.library.set_state(BATCHES, left)
        if again:
            items = [i for i in map(self.library.get, again) if i is not None]
            try:
                self.order(items)
            except Exception as err:  # the next "Odnów" sends them
                log.info("restorer: refused works not sent again: %s", err)
        return drawn

    def _take(
        self,
        batch: dict[str, Any],
        answers: dict[str, tuple[Image.Image, float] | NotDrawn],
        again: list[str],
    ) -> int:
        """The batch's drawings kept; the works refused fewer than
        :data:`REFUSED_TRIES` times, or drawn unusably by 2.1, go into
        ``again`` (to Pro after :data:`FIRST_TRIES`)."""
        model = str(batch.get("model") or MODEL)
        drawn = 0
        for item_id, answer in answers.items():
            item = self.library.get(item_id)
            if item is None:
                continue
            if isinstance(answer, NotDrawn):
                if refusal(answer):
                    tries = self._refusals(item.id) + 1
                    self._note(
                        item.id,
                        "refused",
                        why=str(answer)[:300],
                        code=answer.code,
                        tries=tries,
                        model=model,
                    )
                    if tries < REFUSED_TRIES:
                        again.append(item.id)
                else:
                    log.info("restorer: %s not drawn by %s: %s", item.id, model, answer)
                    self._failed(item.id, model, str(answer), again)
                continue
            if self.restored(item):
                continue  # drawn from its card meanwhile
            if item.sharper is not None and item.sharper.chosen:
                continue  # the owner picked another copy meanwhile
            size = batch.get("sizes", {}).get(item.id)
            try:
                picture = self._picture(item)
            except Exception as err:
                log.info("restorer: %s not had again: %s", item.id, err)
                continue
            if size and tuple(size) != picture.size:
                continue  # its picture changed meanwhile: drawn from another
            try:
                self._keep(item, picture, answer[0], answer[1], model)
            except (NotRestored, ValueError) as err:
                log.info("restorer: %s not kept: %s", item.id, err)
                self._failed(item.id, model, str(err), again)
                continue
            drawn += 1
        return drawn

    def _failed(self, item_id: str, model: str, why: str, again: list[str]) -> None:
        """A drawing of the Batch that cannot be used (none, or in other
        proportions): one of 2.1 counts as a try and is asked again (of
        Pro after :data:`FIRST_TRIES`); one of Pro waits for the owner."""
        if model == PRO:
            return
        tries = self._refusals(item_id) + 1
        self._note(item_id, FAILED, why=why[:300], tries=tries, model=model)
        again.append(item_id)

    # -- the background ---------------------------------------------------------------

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="restorer", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _run(self) -> None:
        try:
            self.recolour_kept()
        except Exception:
            log.exception("restorer: drawings not recoloured")
        while not self._stop.is_set():
            batches = self._batches()
            if batches and self.enabled():
                try:
                    self.poll()
                except Exception:
                    log.exception("restorer: batches not looked at")
            soon = any(b.get("model") == fal.MODEL for b in self._batches())
            self._wake.wait(FAL_POLL if soon else POLL)
            self._wake.clear()


#: Google's words for a picture its model will not draw again, whatever is
#: asked (it takes the work for a protected one, or its content for one it
#: may not show): never sent again.
REFUSALS = ("recitation", "prohibited", "safety", "blocklist", "spii")


#: A note's status for a drawing of 2.1 that could not be used.
FAILED = "failed"


def model_for(tries: int) -> str:
    """The model asked after ``tries`` that failed: Nano Banana 2.1 the
    first :data:`FIRST_TRIES` times, then Pro."""
    return MODEL if tries < FIRST_TRIES else PRO


def _tries(data: dict[str, Any]) -> int:
    """A refusal's count of tries; one for a note from before it was kept."""
    tries = data.get("tries", 1)
    return tries if isinstance(tries, int) and tries > 0 else 1


def refusal(err: NotDrawn) -> bool:
    return any(word in err.code.lower() for word in REFUSALS)


def fit(size: tuple[int, int], drawn: Image.Image) -> Image.Image:
    """``drawn`` in the proportions of the picture it was drawn from
    (``size``); raises :class:`NotRestored` when they differ by more than
    :data:`SKEW_MAX` or it is no larger."""
    w, h = size
    dw, dh = drawn.size
    if max(dw, dh) <= max(w, h):
        raise NotRestored("small", f"drawn {dw}×{dh}, no larger than {w}×{h}")
    skew = abs((dw / dh) / (w / h) - 1)
    if skew > SKEW_MAX:
        raise NotRestored("skewed", f"drawn {dw}×{dh} for {w}×{h}")
    if skew <= SKEW_FIXED:
        return drawn.convert("RGB")
    if dw / w >= dh / h:  # keep the longer reach, set the other side right
        dh = round(dw * h / w)
    else:
        dw = round(dh * w / h)
    return drawn.convert("RGB").resize((dw, dh), Image.Resampling.LANCZOS)


def recoloured(picture: Image.Image, drawn: Image.Image) -> Image.Image:
    """``drawn`` in the colours of the picture it was drawn from (Mateusz
    2026-11-16: "Bywa że „restauracja dzieła” zmienia nieznacznie
    kolorystykę. Czy możemy po ‚stworzeniu’ jakości przenieść kolorystykę
    z oryginału?"). In OKLab, the drawing's tones and colours at the
    picture's own scale (blurred by :data:`COLOUR_SIGMA` of its pixels) are
    replaced by the picture's; what is finer, the detail the model drew,
    stays as drawn."""
    size = drawn.size
    sigma = COLOUR_SIGMA * max(size) / max(picture.size)
    own = picture.convert("RGB").resize(size, Image.Resampling.LANCZOS)
    museum = linear_to_oklab(u8_to_linear(np.asarray(own))).astype(np.float32)
    lab = linear_to_oklab(u8_to_linear(np.asarray(drawn.convert("RGB")))).astype(np.float32)
    lab += cv2.GaussianBlur(museum, (0, 0), sigma) - cv2.GaussianBlur(lab, (0, 0), sigma)
    rgb = linear_to_u8(np.clip(oklab_to_linear(lab), 0.0, 1.0))
    return Image.fromarray(rgb, "RGB")


def _chunks(items: list[Item], n: int) -> Iterator[list[Item]]:
    for at in range(0, len(items), n):
        yield items[at : at + n]


__all__ = ["LOW_SIDE", "NotRestored", "Restorer", "fit", "recoloured", "refusal"]
