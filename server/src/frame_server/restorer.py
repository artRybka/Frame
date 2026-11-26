"""The restorer ("Restauracja dzieła"): a work whose picture is small for
the frame (``low_res.LOW_SIDE``) drawn again larger.

Since 2026-11-26 by our own model on the server (Mateusz 08:14 UTC: "Nasz
nowy model to główny i domyślny restaurator. Rezygnujemy z tego co daje
fal."): ArtSR G3 (:mod:`.imaging.artsr`), four times larger, led by how the
work looks and by its kind, free and refusing nothing. Of 32 works with a
large original it kept nearest to them of all tried. One work from its card
at once (a minute or two on the NAS, one at a time), many from a playlist's
"…" or the owner's favourites one after another in the background.

"Restaurator Pro" is Google's model (Nano Banana 2.1, :data:`MODEL`; Pro
after :data:`FIRST_TRIES` that failed, :func:`model_for`) through the Batch
API, one work at a time, ordered by anyone from its card within a daily
limit of their own (``users.User.pro_a_day``; 2.1 chosen over Pro on the
comparisons of 2026-11-26, 08:31 UTC: "2.1 dla Restauratora PRO"). Whoever
ordered it is told when it is drawn ("Restauracja gotowa"). A picture the
model would not draw (``image_recitation``) is asked for again,
:data:`REFUSED_TRIES` times in all, then noted and never sent again.

Every drawing is kept the way a copy the owner brought is
(:meth:`Sharper.bring`): for good, in the work's own id, as his pick
(``SharperCopy.chosen``; ``SharperCopy.pro`` for Pro's), so the night's
looks for sharper copies leave it be; "Przywróć zdjęcie muzeum" goes back
to the museum's picture. It comes back in the colours of the picture it
was drawn from (:func:`recoloured`): the model's detail on the museum's
tones, :data:`DRAWN` of it. Each restored work goes first in the
"Restaurator" playlist of whoever asked for it (:meth:`Restorer.file`).
"""

from __future__ import annotations

import io
import logging
import threading
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np
from PIL import Image, ImageFilter

from .ai.gemini import MODEL, PRO, Ask, NotDrawn
from .imaging import artsr
from .imaging.color import linear_to_oklab, linear_to_u8, oklab_to_linear, u8_to_linear
from .imaging.cut import cut_aspect, warp
from .imaging.descreen import descreened
from .library import Item, ItemKind
from .library.low_res import LOW_SIDE, low_side
from .library.models import Note, Playlist, PlaylistKind
from .library.viewer import OWNER_ID

if TYPE_CHECKING:
    from .ai.gemini import Painter
    from .library import ImageCache, Library
    from .sharper import Sharper

log = logging.getLogger(__name__)

KIND = "restorer"
#: Where the drawing is from, as the card names it.
ORIGIN = "Kreatywny restaurator"
ORIGIN_PRO = "Restauracja PRO"
#: Google's output: some 2048 px on the long side; ours is brought to it.
SIZE = "2K"
#: A picture this long or longer gains nothing from a drawing of 2K.
LONGEST = 2048
#: Our model is given the picture at most this long (four times it is
#: twice :data:`LONGEST`): a minute or two on the NAS, not several.
MODEL_INPUT = 1024
#: The proportions of the drawing may differ from the picture's by this
#: share and are then set right; by more it is not taken.
SKEW_FIXED = 0.005
SKEW_MAX = 0.04
#: How coarse the colours taken back from the museum's picture are, in its
#: own pixels (:func:`recoloured`): finer than this is the drawing's own
#: detail; coarse enough that the drawing a pixel off the picture does not
#: fringe its edges.
COLOUR_SIGMA = 2.0
#: The picture's finest grain, in its own pixels, left out of the plain
#: enlargement laid under the drawing (:func:`recoloured`): a scan of a
#: printed reproduction carries its screen there, too fine to be found
#: (``imaging.descreen``) and brought back as a net over the drawing
#: (Mateusz 2026-11-26, van Gogh's "Der Bauer" on a Leipzig postcard:
#: „Trzeba w ramach restauracji usuwać raster wynikający ze skanu
#: reprodukcji”). What the model drew stays as sharp.
GRAIN_SIGMA = 1.0
#: How much of what the model drew finer than the picture is kept
#: (:func:`recoloured`): the rest is the picture enlarged plainly. All of
#: it was too much made up (Mateusz 2026-11-22, Janinet's print: "Czy
#: możemy ograniczyć odrobinę „zmyślanie” przy restauracji?"); half kept
#: half the change and a contour drawn thinner, the texture still there,
#: but the work "trochę za miękki" (19:40): seven tenths.
DRAWN = 0.7
#: The same of Restaurator Pro's drawing: all of it, only its colours put
#: back (Mateusz 2026-11-26 16:09 UTC: „przy Gemini dałbym sobie spokój z
#: podkładem 30% oryginału chyba ze dla korekty i dostosowania koloru”).
DRAWN_PRO = 1.0
#: The drawing and its picture are laid on each other this small (its
#: longer side) before the colours and the plain enlargement are put over;
#: they must then match at least so well (correlation of their tones),
#: moved and scaled by no more than :data:`LAID_SHIFT` of the side.
LAID_SIDE = 800
LAID_MATCH = 0.85
LAID_SHIFT = 0.06
#: A drawing's note says it is in the picture's colours and tempered by
#: :data:`DRAWN` (``colours``): the ones kept before are made so once
#: (:meth:`Restorer.recolour_kept`).
COLOURS = 3
#: What each ``colours`` of a kept drawing kept of what was drawn: a
#: drawing kept softer is given back its detail by the difference.
KEPT = {1: 1.0, 2: 0.5}
#: Seconds between looks at Pro's batches still waiting.
POLL = 600.0
#: About what one drawing of Pro costs, USD (2K through the Batch API).
BATCH_USD = 0.03
#: The same of Google's dearer model (:data:`PRO`), after 2.1 failed.
PRO_BATCH_USD = 0.07
#: The library state key of Pro's batches waiting.
BATCHES = "restorer.batches"
#: The works waiting for our model in the background: ``{"id", "by"}``.
QUEUE = "restorer.queue"
#: A picture Google's model will not draw is asked for this many times in
#: all (Mateusz 2026-11-13: "ponawiaj próbę 5 razy"): it now and then takes
#: the same question, and a refusal is not paid for.
REFUSED_TRIES = 5
#: Tries of Nano Banana 2.1 (:data:`MODEL`) before Pro (:data:`PRO`) is
#: asked (:func:`model_for`).
FIRST_TRIES = 2
#: The playlist each person's restored works go into (Mateusz 2026-11-26:
#: "w playlistach utwórzmy proszę folder „Restaurator” gdzie będą trafiać
#: wszystkie restaurowane dzieła"), under :func:`restorer_key`.
PLAYLIST_NAME = "Restaurator"
PLAYLIST_KEY = "restorer_playlist"
#: The works restored before the playlist was there, put in the owner's once.
FILLED_KEY = "restorer_playlist_filled"
#: The drawings of a whole photograph cut to their work once (:meth:`Restorer.cut_kept`).
CUT_KEY = "restorer.cut_kept"


def restorer_key(user_id: str) -> str:
    return PLAYLIST_KEY if user_id == OWNER_ID else f"{PLAYLIST_KEY}:{user_id}"


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
- No border, frame, margin, signature or watermark that is not in the picture.
- If the photograph is of a printed reproduction (a postcard, a book's plate, a poster), the \
printer's dot screen, its rosettes and moiré and the paper's grain are not the painting: render \
the painting's own continuous tones and brushwork without them."""


class NotRestored(ValueError):
    """The work cannot be drawn again: ``code`` says why ("refused": the
    model would not draw it; "skewed": drawn in other proportions;
    "large": its picture is large enough; "not_drawn": no picture came
    back this time; "restored": drawn already; "not_art")."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


#: Told when a work ordered of Pro is over: the work, who ordered it, and
#: whether it was drawn (False: refused for good, or drawn unusably).
Done = Callable[[Item, str, bool], None]


class Restorer:
    def __init__(
        self,
        library: Library,
        images: ImageCache,
        sharper: Sharper,
        painter: Painter,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        model: artsr.ArtSR | None = None,
    ) -> None:
        self.library = library
        self.images = images
        self.sharper = sharper
        self.painter = painter
        self.model = model or artsr.ArtSR()
        #: How a picture looks to SigLIP 2 (``seen.SeenModel.pictures``),
        #: which leads our model; set by the service.
        self.look_of: Callable[[Image.Image], np.ndarray] | None = None
        #: Told when a work ordered of Pro is over (the notification).
        self.on_pro: Done | None = None
        self.clock = clock
        self._lock = threading.Lock()
        #: Our model draws one picture at a time: the NAS has others to serve.
        self._drawing = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- what can be drawn -------------------------------------------------------------

    def enabled(self) -> bool:
        """Whether our model is here (it comes with the server)."""
        return self.model.here()

    def pro_enabled(self) -> bool:
        """Whether Restaurator Pro can draw: Google's key in Konfiguracja."""
        return self.painter.enabled()

    @staticmethod
    def restored(item: Item) -> bool:
        return item.sharper is not None and item.sharper.restored

    @staticmethod
    def restored_pro(item: Item) -> bool:
        return item.sharper is not None and item.sharper.restored and item.sharper.pro

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
        times (Pro is not asked for them again)."""
        return {
            item_id
            for item_id, note in self.library.notes(KIND).items()
            if note.data.get("status") == "refused" and _tries(note.data) >= REFUSED_TRIES
        }

    def _refusals(self, item_id: str) -> int:
        """How many times Google's model would not draw the work so far, or
        drew it unusably (:data:`FAILED`)."""
        note = self.library.note(item_id, KIND)
        if note is None or note.data.get("status") not in ("refused", FAILED):
            return 0
        return _tries(note.data)

    def _queue(self) -> list[dict[str, str]]:
        queue = self.library.get_state(QUEUE, [])
        return [q for q in queue if isinstance(q, dict)] if isinstance(queue, list) else []

    def waiting(self) -> set[str]:
        """The works waiting: for our model in the background, or for Pro."""
        return {q["id"] for q in self._queue()} | self.waiting_pro()

    def waiting_pro(self) -> set[str]:
        return {i for batch in self._batches() for i in batch.get("ids", [])}

    def candidates(self, items: Iterable[Item] | None = None) -> list[Item]:
        """The works whose picture is known to be small for the frame
        (``low_res.low_side``), not drawn yet nor waiting: of ``items`` (a
        playlist's), or of the owner's favourites."""
        skip = self.waiting()
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
        """How many works our model would draw: for nothing."""
        return len(self.candidates(items)), 0.0

    def counts(self) -> tuple[int, int]:
        """Works waiting, and works drawn again."""
        drawn = sum(1 for i in self.library.all_items() if self.restored(i))
        return len(self.waiting()), drawn

    # -- one work ---------------------------------------------------------------------

    def _picture(self, item: Item) -> Image.Image:
        if self.restored(item):
            # Drawn already (ours, ordered again of Pro): drawn again from
            # the museum's picture, never from the drawing, cut as the
            # work is shown.
            return descreened(self.images.work_before_drawn(item, urgent=True).convert("RGB"))
        if item.cleaned_shown() is not None:
            # A work shown cleaned (``Item.cleaned``) is drawn from the
            # picture as it came: the drawing is cleaned after, the same.
            return descreened(self.images.before_cleaning(item, urgent=True).convert("RGB"))
        # Without its original (a dead link), the thumbnail the card shows
        # (``ImageCache.picture``) is what is drawn larger.
        path, _original = self.images.picture(item, urgent=True)
        with Image.open(path) as img:
            # A scan of a printed page loses its dots first: drawn larger,
            # they were a net over the whole work (``imaging.descreen``).
            return descreened(img.convert("RGB"))

    def restore(self, item: Item, by: str = OWNER_ID) -> Item:
        """``item`` drawn again now by our model (a minute or two on the
        NAS), kept in place of its picture and put in ``by``'s
        "Restaurator". Raises :class:`NotRestored`."""
        stored = self.library.get(item.id) or item
        self.check(stored)
        if self.restored(stored):
            raise NotRestored("restored", "drawn again already")
        picture = self._picture(stored)
        drawn = self.draw(stored, picture)
        with self._lock:
            now = self.library.get(item.id) or stored
            if self.restored(now):  # Pro's came meanwhile
                return now
            return self._keep(now, picture, drawn, 0.0, artsr.NAME, by=by)

    def draw(self, item: Item, picture: Image.Image) -> Image.Image:
        """Our model's drawing of ``picture``, :data:`LONGEST` long."""
        given = picture
        if max(given.size) > MODEL_INPUT:
            k = MODEL_INPUT / max(given.size)
            given = given.resize(
                (max(1, round(given.width * k)), max(1, round(given.height * k))),
                Image.Resampling.LANCZOS,
            )
        with self._drawing:
            look = self._look(picture)
            drawn = self.model.larger(given, look, artsr.kind_of(item))
        k = LONGEST / max(drawn.size)
        return drawn.resize(
            (round(drawn.width * k), round(drawn.height * k)), Image.Resampling.LANCZOS
        )

    def _look(self, picture: Image.Image) -> np.ndarray:
        if self.look_of is None:
            raise NotRestored("not_drawn", "how the work looks is not known here")
        return np.asarray(self.look_of(picture), dtype=np.float32).reshape(-1)

    def _keep(
        self,
        item: Item,
        picture: Image.Image,
        drawn: Image.Image,
        usd: float,
        model: str,
        *,
        by: str = OWNER_ID,
        pro: bool = False,
    ) -> Item:
        try:
            share = DRAWN_PRO if pro else DRAWN
            fitted = recoloured(picture, fit(picture.size, drawn), share)
        except NotRestored as err:
            self._note(item.id, "skewed", why=str(err), usd=usd, model=model)
            raise
        buf = io.BytesIO()
        fitted.save(buf, "JPEG", quality=95)
        origin = ORIGIN_PRO if pro else ORIGIN
        updated = self.sharper.bring(item, buf.getvalue(), origin, restored=True, pro=pro)
        self._note(
            item.id,
            "done",
            usd=usd,
            size=list(fitted.size),
            own=list(picture.size),
            colours=COLOURS,
            model=model,
            pro=pro,
            by=by,
        )
        self.file(item.id, by)
        log.info(
            "restorer: %s %s → %s by %s (%.3f USD)", item.id, picture.size, fitted.size, model, usd
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

    # -- "Restaurator" in Playlisty ---------------------------------------------------

    def playlist(self, user: str) -> Playlist | None:
        """``user``'s "Restaurator", when made."""
        playlist_id = self.library.get_state(restorer_key(user), None)
        found = self.library.playlist(playlist_id) if playlist_id is not None else None
        return found if found is not None and found.owner == user else None

    def file(self, item_id: str, user: str = OWNER_ID) -> None:
        """The work in ``user``'s "Restaurator" (made when first needed,
        and again if they deleted it), as added last: shown first."""
        playlist = self.playlist(user) or Playlist(
            name=PLAYLIST_NAME, kind=PlaylistKind.MANUAL, owner=user
        )
        ids = [*(i for i in playlist.item_ids if i != item_id), item_id]
        saved = self.library.save_playlist(playlist.model_copy(update={"item_ids": ids}))
        self.library.set_state(restorer_key(user), saved.id)

    def file_kept(self) -> int:
        """The works restored before "Restaurator" was there put in the
        owner's, in the order they were drawn, once; how many."""
        if self.library.get_state(FILLED_KEY, False):
            return 0
        notes = self.library.notes(KIND)
        kept = sorted(
            (i for i in self.library.all_items() if self.restored(i)),
            key=lambda i: str(notes[i.id].data.get("at", "")) if i.id in notes else "",
        )
        for item in kept:
            self.file(item.id, OWNER_ID)
        self.library.set_state(FILLED_KEY, True)
        return len(kept)

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
                was = KEPT.get(int(note.data.get("colours") or 1), 1.0) if note else 1.0
                fitted = recoloured(
                    descreened(self.images.before_drawn(item)), drawing, DRAWN / was
                )
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
                    self.sharper.bring(
                        stored, buf.getvalue(), stored.sharper.museum or ORIGIN, restored=True
                    )
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

    # -- the drawings of a whole photograph cut to their work ---------------------------

    def cut_kept(self) -> int:
        """The drawings kept of a museum's whole photograph, while the work
        was cut on it (Restaurator Pro ordered after our model, before
        1.145.392), cut down to the work once: shown whole, with the frame
        or the board around it, and framed twice in "W ramie" (Mateusz
        2026-11-26). Nothing is drawn again or paid for. One that cannot be
        had now is tried at the next start; how many were cut."""
        if self.library.get_state(CUT_KEY, False):
            return 0
        done = missed = 0
        for item in list(self.library.all_items()):
            if self._stop.is_set():
                return done
            sharper, cut = item.sharper, item.cut
            if not self.restored(item) or sharper is None or cut is None:
                continue
            quad = cut.shown()
            if quad is None or cut.picture == item.picture_key():
                continue  # whole, or cut on the drawing itself
            work = cut_aspect(quad, cut.aspect)
            if work <= 0 or abs(work - cut.aspect) <= 0.01 * cut.aspect:
                continue  # the work is the photograph's shape: which it is, unknown
            url = sharper.url
            try:
                drawing = self.images.sample(url)
            except Exception as err:
                log.info("restorer: %s not had to be cut: %s", item.id, err)
                missed += 1
                continue
            shape = drawing.width / drawing.height
            if abs(shape - cut.aspect) * 3 > abs(shape - work):
                continue  # drawn of the work already (nearer its shape)
            fitted = warp(drawing, quad)
            buf = io.BytesIO()
            fitted.save(buf, "JPEG", quality=95)
            with self._lock:
                stored = self.library.get(item.id)
                if stored is None or stored.sharper is None or stored.sharper.url != url:
                    continue  # drawn again or put back meanwhile
                try:
                    self.sharper.bring(
                        stored,
                        buf.getvalue(),
                        stored.sharper.museum or ORIGIN,
                        restored=True,
                        pro=stored.sharper.pro,
                    )
                except ValueError as err:
                    log.info("restorer: %s not cut: %s", item.id, err)
                    missed += 1
                    continue
            done += 1
            log.info(
                "restorer: %s's drawing cut to the work, %s → %s",
                item.id,
                drawing.size,
                fitted.size,
            )
        if not missed:
            self.library.set_state(CUT_KEY, True)
        return done

    # -- many at once, by our model in the background ---------------------------------

    def order_favourites(self, by: str = OWNER_ID) -> int:
        """The favourites under the threshold drawn in the background; how many."""
        return self.order(None, by)

    def order(self, items: Iterable[Item] | None = None, by: str = OWNER_ID) -> int:
        """The works under the threshold (of ``items``, a playlist's; else
        the owner's favourites) drawn by our model one after another in the
        background; how many were added."""
        with self._lock:
            found = self.candidates(items)
            queue = self._queue()
            queue.extend({"id": i.id, "by": by} for i in found)
            self.library.set_state(QUEUE, queue)
        if found:
            log.info("restorer: %d works waiting for our model", len(found))
            self._wake.set()
        return len(found)

    def drain(self) -> int:
        """The works waiting for our model drawn, one at a time, until none
        is left or the server stops; how many."""
        drawn = 0
        while not self._stop.is_set():
            queue = self._queue()
            if not queue:
                break
            first = queue[0]
            item = self.library.get(first["id"])
            try:
                if item is not None and not self.restored(item):
                    self.restore(item, first.get("by") or OWNER_ID)
                    drawn += 1
            except Exception as err:  # its picture refused now: left
                log.info("restorer: %s not drawn: %s", first["id"], err)
            with self._lock:
                left = [q for q in self._queue() if q["id"] != first["id"]]
                self.library.set_state(QUEUE, left)
        return drawn

    # -- Restaurator Pro, one work through Google's Batch API -------------------------

    def _batches(self) -> list[dict[str, Any]]:
        batches = self.library.get_state(BATCHES, [])
        return batches if isinstance(batches, list) else []

    def order_pro(self, item: Item, by: str = OWNER_ID) -> bool:
        """``item`` sent to Google's model through the Batch API for ``by``
        (within a day, half the price); False when it waits already.
        Raises :class:`NotRestored` (drawn by Pro already, refused for
        good, not a museum work) and the painter's errors (no key, no
        credit)."""
        stored = self.library.get(item.id) or item
        self.check(stored)
        if self.restored_pro(stored):
            raise NotRestored("restored", "drawn by Restaurator Pro already")
        if stored.id in self.refused():
            raise NotRestored("refused", "the model would not draw it")
        if stored.id in self.waiting_pro():
            return False
        self._send_pro([stored], {stored.id: by})
        return True

    def _send_pro(self, items: list[Item], by: dict[str, str]) -> int:
        """``items`` sent in a batch of the model their tries lead to."""
        sent = 0
        with self._lock:
            batches = self._batches()
            by_model: dict[str, list[Item]] = {}
            for item in items:
                by_model.setdefault(model_for(self._refusals(item.id)), []).append(item)
            for model, chunk in by_model.items():
                pictures = {i.id: self._picture(i) for i in chunk}
                asks = [Ask(i, PROMPT, [p], SIZE) for i, p in pictures.items()]
                name = self.painter.batch(KIND, asks, model=model)
                batches.append(
                    {
                        "name": name,
                        "model": model,
                        "pro": True,
                        "ids": list(pictures),
                        "by": {i: by.get(i, OWNER_ID) for i in pictures},
                        "sizes": {k: list(v.size) for k, v in pictures.items()},
                        "at": self.clock().isoformat(),
                    }
                )
                self.library.set_state(BATCHES, batches)
                sent += len(pictures)
                log.info("restorer: Pro's batch %s of %s, %d works", name, model, len(pictures))
        if sent:
            self._wake.set()
        return sent

    def poll(self) -> int:
        """Pro's batches done taken in; how many works were drawn. The works
        refused fewer than :data:`REFUSED_TRIES` times are sent again."""
        drawn = 0
        again: dict[str, str] = {}
        over: list[tuple[str, str, bool]] = []
        with self._lock:
            batches = self._batches()
            left = []
            for batch in batches:
                if not batch.get("pro"):
                    # fal's or a favourites' batch of Google's from before
                    # 2026-11-26: those works go to our model instead.
                    self._requeue(batch)
                    continue
                try:
                    model = str(batch.get("model") or MODEL)
                    answers = self.painter.batched(KIND, str(batch["name"]), model=model)
                except NotDrawn as err:  # lost: sent again
                    log.info("restorer: batch %s lost: %s", batch["name"], err)
                    again.update({i: _by(batch, i) for i in batch.get("ids", [])})
                    continue
                if answers is None:
                    left.append(batch)
                    continue
                drawn += self._take(batch, answers, again, over)
            if left != batches:
                self.library.set_state(BATCHES, left)
        if again:
            items = [i for i in map(self.library.get, again) if i is not None]
            try:
                self._send_pro(items, again)
            except Exception as err:
                log.info("restorer: works not sent to Pro again: %s", err)
                over.extend((i.id, again[i.id], False) for i in items)
        for item_id, by, ok in over:
            self._told(item_id, by, ok)
        return drawn

    def _requeue(self, batch: dict[str, Any]) -> None:
        queue = self._queue()
        known = {q["id"] for q in queue}
        queue.extend({"id": i, "by": OWNER_ID} for i in batch.get("ids", []) if i not in known)
        self.library.set_state(QUEUE, queue)

    def _told(self, item_id: str, by: str, ok: bool) -> None:
        item = self.library.get(item_id)
        if item is None or self.on_pro is None:
            return
        try:
            self.on_pro(item, by, ok)
        except Exception:
            log.exception("restorer: %s not told", item_id)

    def _take(
        self,
        batch: dict[str, Any],
        answers: dict[str, tuple[Image.Image, float] | NotDrawn],
        again: dict[str, str],
        over: list[tuple[str, str, bool]],
    ) -> int:
        """The batch's drawings kept; the works refused fewer than
        :data:`REFUSED_TRIES` times, or drawn unusably by 2.1, go into
        ``again`` (to Pro after :data:`FIRST_TRIES`); ``over``: who to tell."""
        model = str(batch.get("model") or MODEL)
        drawn = 0
        for item_id, answer in answers.items():
            item = self.library.get(item_id)
            if item is None:
                continue
            by = _by(batch, item_id)
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
                        again[item.id] = by
                    else:
                        over.append((item.id, by, False))
                else:
                    log.info("restorer: %s not drawn by %s: %s", item.id, model, answer)
                    self._failed(item.id, model, str(answer), again, over, by)
                continue
            if self.restored_pro(item):
                continue  # drawn by Pro meanwhile
            if item.sharper is not None and item.sharper.chosen and not self.restored(item):
                continue  # the owner picked another copy meanwhile
            size = batch.get("sizes", {}).get(item.id)
            try:
                picture = self._picture(item)
            except Exception as err:
                log.info("restorer: %s not had again: %s", item.id, err)
                continue
            if size and tuple(size) != picture.size:
                # Its picture changed meanwhile (another copy, a new cut, or
                # the whole photograph sent before 1.145.392): drawn anew.
                again[item.id] = by
                continue
            try:
                self._keep(item, picture, answer[0], answer[1], model, by=by, pro=True)
            except (NotRestored, ValueError) as err:
                log.info("restorer: %s not kept: %s", item.id, err)
                self._failed(item.id, model, str(err), again, over, by)
                continue
            drawn += 1
            over.append((item.id, by, True))
        return drawn

    def _failed(
        self,
        item_id: str,
        model: str,
        why: str,
        again: dict[str, str],
        over: list[tuple[str, str, bool]],
        by: str,
    ) -> None:
        """A drawing of the Batch that cannot be used (none, or in other
        proportions): one of 2.1 counts as a try and is asked again (of
        Pro after :data:`FIRST_TRIES`); one of Pro is the end."""
        if model == PRO:
            over.append((item_id, by, False))
            return
        tries = self._refusals(item_id) + 1
        self._note(item_id, FAILED, why=why[:300], tries=tries, model=model)
        again[item_id] = by

    # -- the background ---------------------------------------------------------------

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="restorer", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _run(self) -> None:
        for step in (self.file_kept, self.recolour_kept, self.cut_kept):
            try:
                step()
            except Exception:
                log.exception("restorer: %s not done", step.__name__)
        while not self._stop.is_set():
            if self._batches() and (
                self.pro_enabled() or any(not b.get("pro") for b in self._batches())
            ):
                try:
                    self.poll()
                except Exception:
                    log.exception("restorer: batches not looked at")
            if self.enabled():
                try:
                    self.drain()
                except Exception:
                    log.exception("restorer: the works waiting not drawn")
            self._wake.wait(POLL)
            self._wake.clear()


def _by(batch: dict[str, Any], item_id: str) -> str:
    """Who ordered ``item_id`` of the batch (the owner before it was noted)."""
    by = batch.get("by")
    return str(by.get(item_id) or OWNER_ID) if isinstance(by, dict) else OWNER_ID


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


def recoloured(picture: Image.Image, drawn: Image.Image, share: float = DRAWN) -> Image.Image:
    """``drawn`` in the colours of the picture it was drawn from (Mateusz
    2026-11-16: "Bywa że „restauracja dzieła” zmienia nieznacznie
    kolorystykę. Czy możemy po ‚stworzeniu’ jakości przenieść kolorystykę
    z oryginału?"). In OKLab, the drawing's tones and colours at the
    picture's own scale (blurred by :data:`COLOUR_SIGMA` of its pixels) are
    replaced by the picture's; of what is finer, the detail the model
    drew, ``share`` is kept over the picture enlarged plainly."""
    size = drawn.size
    sigma = COLOUR_SIGMA * max(size) / max(picture.size)
    plain = picture.convert("RGB").filter(ImageFilter.GaussianBlur(GRAIN_SIGMA))
    own = plain.resize(size, Image.Resampling.LANCZOS)
    museum = linear_to_oklab(u8_to_linear(np.asarray(own))).astype(np.float32)
    lab = linear_to_oklab(u8_to_linear(np.asarray(drawn.convert("RGB")))).astype(np.float32)
    laid = _laid(museum[..., 0], lab[..., 0])
    if laid is None:
        # Not the picture it was drawn from, or not where it lies: neither
        # its colours nor its plain enlargement are put over the drawing
        # (Mondrian's ginger pot came back doubled, Mateusz 2026-11-22).
        log.info("restorer: the drawing does not lie on its picture, kept as drawn")
        return drawn.convert("RGB")
    museum = np.asarray(
        cv2.warpAffine(
            museum,
            laid,
            (size[0], size[1]),
            flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
            borderMode=cv2.BORDER_REFLECT,
        ),
        dtype=np.float32,
    )
    lab += cv2.GaussianBlur(museum, (0, 0), sigma) - cv2.GaussianBlur(lab, (0, 0), sigma)
    lab = museum + share * (lab - museum)
    rgb = linear_to_u8(np.clip(oklab_to_linear(lab), 0.0, 1.0))
    return Image.fromarray(rgb, "RGB")


def _laid(museum: np.ndarray, drawn: np.ndarray) -> np.ndarray | None:
    """Where the museum's picture (enlarged to the drawing's size) lies on
    the drawing, as the affine map from the drawing's pixels to its; None
    when the two do not match (:data:`LAID_MATCH`). The model may draw a
    picture a few pixels larger or moved (its sizes rounded), and a plain
    enlargement put over it a few pixels off doubles every edge."""
    h, w = drawn.shape
    k = min(1.0, LAID_SIDE / max(h, w))
    small = (max(8, round(w * k)), max(8, round(h * k)))

    def prepared(a: np.ndarray) -> np.ndarray:
        b = cv2.resize(a, small, interpolation=cv2.INTER_AREA)
        return cv2.GaussianBlur(b, (0, 0), 1.0)

    a, b = prepared(drawn), prepared(museum)
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        _, warp = cv2.findTransformECC(  # type: ignore[call-overload]
            a,
            b,
            warp,
            cv2.MOTION_AFFINE,
            (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-5),
            None,
            5,
        )
    except cv2.error:
        return None
    moved = cv2.warpAffine(
        b,
        warp,
        small,
        flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_REFLECT,
    )
    da, dm = a - a.mean(), moved - moved.mean()
    match = float((da * dm).sum() / (np.sqrt((da * da).sum() * (dm * dm).sum()) + 1e-9))
    shift = float(np.abs(warp[:, 2]).max()) / max(small)
    if match < LAID_MATCH or shift > LAID_SHIFT or abs(warp[0, 0] - 1) > LAID_SHIFT:
        return None
    full = warp.copy()
    full[:, 2] /= k
    return full


def _chunks(items: list[Item], n: int) -> Iterator[list[Item]]:
    for at in range(0, len(items), n):
        yield items[at : at + n]


__all__ = ["LOW_SIDE", "NotRestored", "Restorer", "fit", "recoloured", "refusal", "restorer_key"]
