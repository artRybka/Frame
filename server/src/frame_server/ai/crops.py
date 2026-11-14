"""Museum photographs cut down to the work in them (Mateusz 2026-11-14:
"automatyczne wykadrowanie z możliwością korekty lub przywrócenia").

The national museums of Warsaw and Kraków, and others now and then,
photograph works as they stand: in a gilt frame on an easel, on a grey
board, a print on its sheet pasted onto a card. Two questions, as the
night's other checks ask theirs (:class:`.critic_night.CriticNight`):

- the judge, Haiku, looks at the thumbnail and names what is around the
  work (``surround``): a hundredth of a cent a work, so the whole catalogue
  is looked at, Favourites, playlists and Discover first;
- where a frame, an easel, a board or a backdrop is, Opus names the layers
  from the outside in and their corners (a picture and a copy with a grid:
  the smaller models place them badly), about 2 cents a work, half that
  through the Batch API. Its corners are set on the picture's own edges
  (:func:`..imaging.cut.snap`) and the work is cut (``Item.cut``,
  ``ImageCache.recut``) only when Opus is sure of them.

Paper is never cut by itself (a poster's printed line, a page around an
illustration, a print's margin were the trial's only mistakes): a print or
drawing keeps its sheet; without it ("Sama odbitka") only when the owner
asks, then Opus is asked at once. The same is done when a card opens on a
work not looked at yet (:meth:`Crops.soon`). The owner corrects the corners
or gives the cut up in the app; a work he has set is never cut again by
itself.
"""

from __future__ import annotations

import base64
import io
import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageDraw

from ..imaging.cut import Quad, snap, valid, worth_cutting
from ..imaging.layout import load_image
from ..library.images import OWN_SOURCES
from ..library.models import Cut, ItemKind
from .client import HAIKU, OPUS, image_block, request
from .critic_night import REST, CriticNight
from .gatekeeper import facts

if TYPE_CHECKING:
    from ..library import Importer, Item

log = logging.getLogger(__name__)

KIND = "crops"
SWITCH = "crops"

#: What can be around a work in its photograph (the judge's words).
SURROUND = ("backdrop", "easel", "frame", "mount", "paper_margin", "page_text", "colour_chart")
#: Around the work and never part of it: Opus is asked for the corners.
CUT_AROUND = frozenset({"backdrop", "easel", "frame", "mount", "colour_chart"})
#: A print's or a page's paper: kept unless the owner says otherwise.
PAPER = frozenset({"paper_margin", "page_text"})
#: Sources that photograph works as they stand, looked at first.
FIRST_SOURCES = ("mnw", "mnk")

#: The judge's thumbnail, and Opus's picture (the trial's sizes).
JUDGE_SIDE = 640
PHOTO_SIDE = 1400

JUDGE = (
    "A museum photograph of one artwork. Which of these, if any, are visible around the "
    "artwork itself, taking at least a thin strip at an edge of the photograph: backdrop "
    "(wall, cloth, grey or white board behind), easel, picture frame, mount or passe-partout, "
    "blank paper margin around a print or drawing, printed page text around an illustration, "
    "colour chart. An empty list if the artwork runs to the photograph's edges."
)
JUDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["surround"],
    "properties": {
        "surround": {"type": "array", "items": {"type": "string", "enum": list(SURROUND)}}
    },
}

LAYERS = ("frame_outer", "frame_inner", "mount", "sheet", "plate", "canvas")
CORNERS = """This is a museum's photograph of one catalogued artwork. Around the work there \
may be things that are not the work: the backdrop or wall, an easel, a picture frame (gilded \
or plain), a cardboard mount or passe-partout, the sheet a print was pulled on, conservation \
strips, a colour chart.

List the nested rectangles you can see, from the outside in, each as its four corners \
(top-left, top-right, bottom-right, bottom-left) in the coordinates of the grid drawn on the \
second copy (0-1000 across, 0-1000 down, over the whole photograph). Put each corner exactly \
on the visible edge; if the photograph is taken at an angle, the corners need not form a \
rectangle. Kinds: "frame_outer", "frame_inner" (the frame's opening, where the painted \
surface starts), "mount" (board/passe-partout), "sheet" (the paper of a print, drawing, \
poster or page), "plate" (a print's plate mark or the printed/drawn image area), "canvas" \
(an unframed painting's edge). The backdrop is never listed: it is the photograph.

Then choose:
- "work": the index of the rectangle that is the artwork itself as one would hang it without \
frame: for a painting the painted surface (inside the frame); for a print, drawing or poster \
the image area if the paper around it is blank margin; the whole sheet if the image runs to \
the paper's edge or the paper carries part of the work (a signature, a printed title or text, \
a deliberate margin belonging to the design).
- "with_paper": the index of the sheet if a viewer might want to keep the paper margin \
(prints with a plate mark), else null.
- "confident": true only if the edges are clearly visible.
Answer in JSON only."""
CORNERS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["layers", "work", "with_paper", "confident", "note"],
    "properties": {
        "layers": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "corners"],
                "properties": {
                    "kind": {"type": "string", "enum": list(LAYERS)},
                    "corners": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "number"}},
                    },
                },
            },
        },
        "work": {"type": ["integer", "null"]},
        "with_paper": {"type": ["integer", "null"]},
        "confident": {"type": "boolean"},
        "note": {"type": "string"},
    },
}


def _block(img: Image.Image) -> dict[str, Any]:
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88)
    data = base64.standard_b64encode(out.getvalue()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def gridded(img: Image.Image) -> Image.Image:
    """``img`` with a 0–1000 grid drawn over it: the corners are read off it."""
    out = img.copy()
    draw = ImageDraw.Draw(out)
    w, h = out.size
    for k in range(0, 1001, 50):
        x, y = k * (w - 1) / 1000, k * (h - 1) / 1000
        major = k % 100 == 0
        colour = (255, 0, 255) if major else (0, 200, 255)
        width = 2 if major else 1
        draw.line([(x, 0), (x, h)], fill=colour, width=width)
        draw.line([(0, y), (w, y)], fill=colour, width=width)
        if major:
            draw.text((x + 3, 3), str(k), fill=colour)
            draw.text((3, y + 3), str(k), fill=colour)
    return out


def _quad(layer: Any) -> Quad | None:
    try:
        corners = [(float(x) / 1000, float(y) / 1000) for x, y in layer["corners"]]
    except (KeyError, TypeError, ValueError):
        return None
    return valid(corners)


def read_layers(data: dict[str, Any]) -> tuple[Quad | None, Quad | None] | None:
    """Opus's answer as the corners shown (the work, a print with its
    sheet) and a print's without the sheet (or None); None when there is
    nothing to cut to. A sheet is always what is shown: paper is cut away
    only by the owner."""
    layers = data.get("layers")
    work = data.get("work")
    if not isinstance(layers, list) or not isinstance(work, int) or not 0 <= work < len(layers):
        return None
    quads = [_quad(layer) if isinstance(layer, dict) else None for layer in layers]
    kinds = [layer.get("kind") if isinstance(layer, dict) else None for layer in layers]
    work_quad = quads[work]
    if work_quad is None:
        return None
    paper = data.get("with_paper")
    sheet = paper if isinstance(paper, int) and 0 <= paper < len(layers) else None
    if sheet is None:
        sheet = next((n for n, k in enumerate(kinds) if k == "sheet"), None)
    if sheet is None or sheet == work or quads[sheet] is None:
        return work_quad, None
    return quads[sheet], work_quad


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Crops(CriticNight):
    kind = KIND
    switch = SWITCH
    version = 1
    judge_model = HAIKU
    critic_model = OPUS
    #: The judge: about 0.01 cent a work through the Batch API, 600 a night
    #: some 2 USD a month while the catalogue's backlog lasts.
    per_night = 600
    #: Opus: about a cent a work through the Batch API.
    critic_per_night = 60

    importer: Importer | None = None
    _pool: ThreadPoolExecutor | None = None

    def _setup(self) -> None:
        if self._pool is None:
            self._pool = ThreadPoolExecutor(2, thread_name_prefix="crops")
            self._running: dict[str, Future[bool]] = {}
            self._guard = threading.Lock()

    # -- which works --------------------------------------------------------------

    @staticmethod
    def wanted(item: Item) -> bool:
        """A museum work whose photograph may have something around it."""
        return (
            item.kind == ItemKind.ARTWORK
            and item.source not in OWN_SOURCES
            and not item.part_of
            and item.look is None
            and not item.excluded
            and not item.seen_as
            and not (item.sharper is not None and item.sharper.restored)
            and bool(item.thumb_url or item.image_url or item.sharper is not None)
        )

    @staticmethod
    def stale(item: Item) -> bool:
        """No cut for the picture shown: none, or the model's for another
        picture (a sharper copy took its place). The owner's stays his."""
        cut = item.cut
        if cut is None:
            return True
        return cut.by == "auto" and cut.picture != item.picture_key()

    def candidates(self, asked: dict[str, Any]) -> list[Item]:
        found = [
            i
            for i in self.library.all_items()
            if i.cut is None and i.id not in asked and self.wanted(i)
        ]
        found.sort(key=lambda i: i.added_at or "", reverse=True)
        found.sort(key=lambda i: i.source not in FIRST_SOURCES)
        found.sort(key=lambda i: not (not i.pooled or i.favorite or i.show_count > 0))
        cared = self.cared()
        found.sort(key=lambda i: cared.get(i.id, REST))
        return found

    def _round(self, state: dict[str, Any]) -> tuple[bool, list[tuple[Item, dict[str, Any]]]]:
        critic, found = super()._round(state)
        return critic, found[: self.critic_per_night] if critic else found

    # -- the questions ------------------------------------------------------------

    def question(self, item: Item) -> dict[str, Any]:
        content = [
            image_block(self.images, item, max_side=JUDGE_SIDE),
            {"type": "text", "text": JUDGE},
        ]
        return request(
            model=self.judge_model,
            system="You look at museum photographs of artworks.",
            content=content,
            schema=JUDGE_SCHEMA,
        )

    def claim(self, item: Item, data: dict[str, Any]) -> dict[str, Any] | None:
        around = sorted({s for s in data.get("surround") or [] if s in SURROUND})
        if CUT_AROUND & set(around):
            return {"around": around}
        if PAPER & set(around) and item.cut is None:
            # Only paper: nothing cut, but the card offers "Sama odbitka".
            self.library.update(item.id, cut=Cut(around=around, picture=item.picture_key()))
        return None

    def photo(self, item: Item) -> Image.Image:
        """The museum's photograph of the work, whole (downloaded if need be)."""
        return load_image(self.images.museum_photo(item)).convert("RGB")

    def critic_question(self, item: Item, claim: dict[str, Any]) -> dict[str, Any]:
        img = self.photo(item)
        img.thumbnail((PHOTO_SIDE, PHOTO_SIDE), Image.Resampling.LANCZOS)
        around = ", ".join(claim.get("around") or []) or "?"
        text = f"{CORNERS}\n\n{facts(item)}\nSeen around it at a glance: {around}."
        return request(
            model=self.critic_model,
            system="You find artworks in museum photographs.",
            content=[_block(img), _block(gridded(img)), {"type": "text", "text": text}],
            schema=CORNERS_SCHEMA,
            max_tokens=8000,
            effort="medium",
        )

    def corners(self, item: Item, data: dict[str, Any], sure: bool = True) -> dict[str, Any] | None:
        """Opus's answer as corners set on the photograph's edges: the
        work shown ("work", None for the whole photograph), a print's
        without its sheet ("plate") and the photograph's "aspect". None when
        there is nothing to cut to (or Opus is unsure, with ``sure``)."""
        if sure and data.get("confident") is not True:
            return None
        read = read_layers(data)
        if read is None:
            return None
        img = self.photo(item)
        shown = snap(img, read[0]) if read[0] is not None else None
        plate = snap(img, read[1]) if read[1] is not None else None
        if shown is not None and not worth_cutting(shown):
            shown = None  # the sheet is the photograph: only the plate is cut
        if shown is None and plate is None:
            return None
        return {
            "work": shown,
            "plate": plate,
            "aspect": round(img.width / img.height, 5),
            "note": str(data.get("note") or "")[:300],
        }

    def confirmed(self, item: Item, claim: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        try:
            found = self.corners(item, data)
        except OSError as err:
            log.info("crops: the photograph of %s: %s", item.id, err)
            return {}
        return {**claim, **found} if found and found["work"] is not None else {}

    def write(self, item: Item, claim: dict[str, Any]) -> bool:
        stored = self.library.get(item.id)
        if stored is None or not self.stale(stored) or stored.framing:
            return False  # the owner's own cut, or his framings: his
        cut = Cut(
            work=claim.get("work"),
            plate=claim.get("plate"),
            around=list(claim.get("around") or []),
            aspect=float(claim.get("aspect") or 0.0),
            picture=stored.picture_key(),
            at=_now(),
        )
        self.apply(stored, cut)
        return True

    # -- putting a cut on -----------------------------------------------------------

    def apply(self, item: Item, cut: Cut | None) -> Item:
        """``cut`` kept for the work and its pictures made again from it:
        the original, the thumbnail, the colours, the study's details."""
        changes: dict[str, Any] = {"cut": cut}
        if item.framing and cut is not None and cut.by == "owner":
            changes["framing"] = {}  # set on the picture before: another now
        updated = self.library.update(item.id, **changes) or item.model_copy(update=changes)
        self.images.recut(updated)
        if self.importer is not None:
            try:
                updated = self.importer.measure_again(updated)
            except OSError as err:
                log.info("colours of %s: %s", item.id, err)
        details = Path(self.images.thumbs.parent) / "details"
        for old in details.glob(f"{item.file_stem}-*.jpg"):
            old.unlink(missing_ok=True)
        log.info("cut of %s: %s", item.id, "whole" if cut is None or not cut.shown() else cut.by)
        return updated

    def set_by_owner(
        self, item: Item, corners: Quad | None = None, paper: bool | None = None
    ) -> Item:
        """The owner's corners (of the work as shown, with its paper or
        without), or his "Z papierem / Sama odbitka". Without the sheet when
        no plate is known yet: Opus is asked for it now."""
        old = item.cut if item.cut is not None and not self.stale(item) else None
        with Image.open(self.images.museum_photo(item, urgent=True)) as img:
            aspect = round(img.width / img.height, 5)
        cut = (old or Cut()).model_copy(
            update={"by": "owner", "aspect": aspect, "picture": item.picture_key(), "at": _now()}
        )
        if paper is not None:
            cut.paper = paper
            if not paper and cut.plate is None:
                found = self.ask_corners(item, sure=False)
                if found is not None:
                    cut.plate = found["plate"] or found["work"]
                    if cut.work is None and found["plate"] is not None:
                        cut.work = found["work"]
        if corners is not None:
            if not cut.paper and cut.plate is not None:
                cut.plate = corners
            else:
                cut.work = corners
        return self.apply(item, cut)

    def give_up(self, item: Item) -> Item:
        """ "Przywróć zdjęcie muzeum": the photograph whole, for good."""
        old = item.cut or Cut()
        cut = Cut(
            around=old.around,
            aspect=old.aspect,
            picture=item.picture_key(),
            by="owner",
            at=_now(),
        )
        self.forget_written(item.id)
        return self.apply(item, cut)

    def ask_corners(self, item: Item, sure: bool = True) -> dict[str, Any] | None:
        """Opus asked now (the card, the owner's switch)."""
        answer = self.claude.ask(KIND, self.critic_question(item, {"around": []}))
        if answer.refused or not answer.data:
            return None
        return self.corners(item, answer.data, sure=sure)

    # -- when a card opens ----------------------------------------------------------

    def soon(self, item: Item) -> Future[bool]:
        """The work looked at in the background (:meth:`now`), once at a
        time: whether its cut changed."""
        self._setup()
        assert self._pool is not None
        with self._guard:
            running = self._running.get(item.id)
            if running is not None and not running.done():
                return running
            future = self._pool.submit(self.now, item)
            self._running[item.id] = future
            if len(self._running) > 200:
                self._running = {k: f for k, f in self._running.items() if not f.done()}
            return future

    def now(self, item: Item) -> bool:
        """A card opened: a work not looked at yet (or whose picture changed
        since) is looked at now, the judge and then Opus, as at night.
        Whether it was cut."""
        stored = self.library.get(item.id) or item
        if not self.config.enabled(self.switch) or not self.wanted(stored):
            return False
        if not self.stale(stored):
            return False
        asked = self.asked().get(stored.id)
        if asked is not None and stored.cut is None and asked.get("p", "") == stored.picture_key():
            return False
        try:
            judged = self.claude.ask(KIND, self.question(stored))
            claim = None if judged.refused else self.claim(stored, judged.data or {})
            found = None
            if claim:
                answer = self.claude.ask(KIND, self.critic_question(stored, claim))
                if not answer.refused:
                    found = self.confirmed(stored, claim, answer.data or {}) or None
        except Exception as err:  # no key, the limit, a picture gone: the night's again
            log.info("crops: %s not looked at now (%s)", stored.id, err)
            return False
        state = self.state()
        asked_all = state.get("asked") or {}
        asked_all[stored.id] = {
            "v": self.version,
            "at": _now()[:10],
            "p": stored.picture_key(),
            "critic": bool(found),
        }
        state["asked"] = asked_all
        (state.get("claims") or {}).pop(stored.id, None)
        self._save(state)
        if found and self.write(stored, found):
            state = self.state()
            state["written"] = [{"id": stored.id, "at": _now(), **found}, *self.written()]
            self._save(state)
            return True
        return False
