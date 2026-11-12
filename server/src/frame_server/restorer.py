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

One work at a time from its card ("…" → "Kreatywny restaurator", about
25 s), or the owner's favourites under the threshold at once from
Konfiguracja through the Batch API (half the price, within 24 hours,
looked at every :data:`POLL` seconds). A picture the model would not draw
(``image_recitation``: it took a known painting for one it may not copy)
is noted and never sent again.
"""

from __future__ import annotations

import io
import logging
import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from PIL import Image

from .ai.gemini import MODEL, Ask, NotDrawn
from .library import Item, ItemKind
from .library.low_res import LOW_SIDE, low_side
from .library.models import Note
from .library.viewer import OWNER_ID

if TYPE_CHECKING:
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
#: Works in one batch: their pictures go in the request (inline, under
#: the API's 20 MB).
PER_BATCH = 24
#: Seconds between looks at the batches still waiting.
POLL = 600.0
#: About what one drawing costs, USD (2K through the Batch API: half of
#: the 0.06 the trial paid).
BATCH_USD = 0.03
#: The library state key of the batches waiting.
BATCHES = "restorer.batches"

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
    ) -> None:
        self.library = library
        self.images = images
        self.sharper = sharper
        self.painter = painter
        self.clock = clock
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- what can be drawn -------------------------------------------------------------

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
        return {
            item_id
            for item_id, note in self.library.notes(KIND).items()
            if note.data.get("status") == "refused"
        }

    def waiting(self) -> set[str]:
        return {i for batch in self._batches() for i in batch.get("ids", [])}

    def candidates(self) -> list[Item]:
        """The owner's favourites whose picture is known to be small for the
        frame (``low_res.low_side``), not drawn yet, nor refused, nor
        waiting in a batch."""
        skip = self.refused() | self.waiting()
        found = []
        for item_id in sorted(self.library.favorites(OWNER_ID)):
            item = self.library.get(item_id)
            if item is None or item.id in skip or self.restored(item) or item.excluded:
                continue
            if item.look is None and low_side(item) > 0:
                found.append(item)
        return found

    def estimate(self) -> tuple[int, float]:
        n = len(self.candidates())
        return n, round(n * BATCH_USD, 2)

    def counts(self) -> tuple[int, int]:
        """Works waiting in batches, and works drawn again."""
        drawn = sum(1 for i in self.library.all_items() if self.restored(i))
        return len(self.waiting()), drawn

    # -- one work ---------------------------------------------------------------------

    def _picture(self, item: Item) -> Image.Image:
        path = self.images.ensure_image(item, urgent=True)
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
        try:
            drawn, usd = self.painter.paint(KIND, PROMPT, [picture], size=SIZE)
        except NotDrawn as err:
            if refusal(err):
                self._note(stored.id, "refused", why=str(err)[:300], code=err.code)
                raise NotRestored("refused", str(err)) from err
            raise NotRestored("not_drawn", str(err)) from err
        return self._keep(stored, picture, drawn, usd)

    def _keep(self, item: Item, picture: Image.Image, drawn: Image.Image, usd: float) -> Item:
        try:
            fitted = fit(picture.size, drawn)
        except NotRestored as err:
            self._note(item.id, "skewed", why=str(err), usd=usd)
            raise
        buf = io.BytesIO()
        fitted.save(buf, "JPEG", quality=95)
        updated = self.sharper.bring(item, buf.getvalue(), ORIGIN, restored=True)
        self._note(item.id, "done", usd=usd, size=list(fitted.size), own=list(picture.size))
        log.info("restorer: %s %s → %s (%.3f USD)", item.id, picture.size, fitted.size, usd)
        return updated

    def _note(self, item_id: str, status: str, **data: Any) -> None:
        self.library.save_note(
            Note(
                item_id=item_id,
                kind=KIND,
                model=MODEL,
                prompt_version="1",
                data={"status": status, "at": self.clock().isoformat(), **data},
            )
        )

    # -- the favourites through the Batch API -----------------------------------------

    def _batches(self) -> list[dict[str, Any]]:
        batches = self.library.get_state(BATCHES, [])
        return batches if isinstance(batches, list) else []

    def order_favourites(self) -> int:
        """The favourites under the threshold sent in batches; how many."""
        with self._lock:
            items = self.candidates()
            batches = self._batches()
            sent = 0
            for chunk in _chunks(items, PER_BATCH):
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
                name = self.painter.batch(KIND, asks)
                batches.append(
                    {
                        "name": name,
                        "ids": list(pictures),
                        "sizes": {k: list(v.size) for k, v in pictures.items()},
                        "at": self.clock().isoformat(),
                    }
                )
                self.library.set_state(BATCHES, batches)
                sent += len(pictures)
                log.info("restorer: batch %s with %d works", name, len(pictures))
        if sent:
            self._wake.set()
        return sent

    def poll(self) -> int:
        """The batches done taken in; how many works were drawn."""
        drawn = 0
        with self._lock:
            batches = self._batches()
            left = []
            for batch in batches:
                try:
                    answers = self.painter.batched(KIND, str(batch["name"]))
                except NotDrawn as err:  # lost: its works may be sent again
                    log.info("restorer: batch %s lost: %s", batch["name"], err)
                    continue
                if answers is None:
                    left.append(batch)
                    continue
                drawn += self._take(batch, answers)
            if len(left) != len(batches):
                self.library.set_state(BATCHES, left)
        return drawn

    def _take(
        self, batch: dict[str, Any], answers: dict[str, tuple[Image.Image, float] | NotDrawn]
    ) -> int:
        drawn = 0
        for item_id, answer in answers.items():
            item = self.library.get(item_id)
            if item is None:
                continue
            if isinstance(answer, NotDrawn):
                if refusal(answer):
                    self._note(item.id, "refused", why=str(answer)[:300], code=answer.code)
                else:
                    log.info("restorer: %s not drawn: %s", item.id, answer)
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
                self._keep(item, picture, answer[0], answer[1])
            except (NotRestored, ValueError) as err:
                log.info("restorer: %s not kept: %s", item.id, err)
                continue
            drawn += 1
        return drawn

    # -- the background ---------------------------------------------------------------

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="restorer", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            if self._batches() and self.painter.enabled():
                try:
                    self.poll()
                except Exception:
                    log.exception("restorer: batches not looked at")
            self._wake.wait(POLL)
            self._wake.clear()


#: Google's words for a picture its model will not draw again, whatever is
#: asked (it takes the work for a protected one, or its content for one it
#: may not show): never sent again.
REFUSALS = ("recitation", "prohibited", "safety", "blocklist", "spii")


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


def _chunks(items: list[Item], n: int) -> Iterator[list[Item]]:
    for at in range(0, len(items), n):
        yield items[at : at + n]


__all__ = ["LOW_SIDE", "NotRestored", "Restorer", "fit", "refusal"]
