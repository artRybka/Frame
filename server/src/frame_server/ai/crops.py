"""Museum photographs cut down to the work in them (Mateusz 2026-11-14:
"automatyczne wykadrowanie z możliwością korekty lub przywrócenia").

The national museums of Warsaw and Kraków, and others now and then,
photograph works as they stand: in a gilt frame on an easel, on a grey
board, a print on its sheet pasted onto a card. The phone's own model finds
the work in such a photograph (:mod:`..phone_crops`, Mateusz 2026-11-20:
„Celem jest całkowite uniknięcie Opus”); here the cut is kept and the
work's pictures made again from it (:meth:`Crops.apply`), and the owner's
corrections ("Popraw kadr", "Przywróć zdjęcie muzeum") are put on. Until
2026-11-23 Haiku and Opus looked at the photographs at night and when a
card opened; that was taken out once the phone did it (Mateusz: „Kadrowanie
dzieła robi teraz iPhone … wyłączyć poprzednie funkcje”). The cuts they set
stay as they are.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image

from ..imaging.cut import Quad, framed_geometry
from ..imaging.layout import Crop
from ..library.images import OWN_SOURCES
from ..library.models import Cut, Framing, ItemKind
from .critic_night import REST

if TYPE_CHECKING:
    from ..library import ImageCache, Importer, Item, Library

log = logging.getLogger(__name__)

#: Sources that photograph works as they stand, looked at first.
FIRST_SOURCES = ("mnw", "mnk")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _box(quad: Quad | None) -> tuple[float, float, float, float]:
    """The box (left, top, right, bottom) around ``quad``, the whole
    photograph for None."""
    if quad is None:
        return 0.0, 0.0, 1.0, 1.0
    xs, ys = [x for x, _ in quad], [y for _, y in quad]
    return min(xs), min(ys), max(xs), max(ys)


def _crop_moved(crop: Crop | None, old: Quad | None, new: Quad | None) -> Crop | None:
    """``crop`` (a part of the photograph cut to ``old``, None: whole) as
    the same part of the photograph cut to ``new``: its centre moved, its
    zoom changed by as much as the picture is smaller or larger."""
    if crop is None:
        return None
    ox0, oy0, ox1, oy1 = _box(old)
    nx0, ny0, nx1, ny1 = _box(new)
    if min(ox1 - ox0, oy1 - oy0, nx1 - nx0, ny1 - ny0) <= 0:
        return crop
    x = ox0 + crop.x * (ox1 - ox0)
    y = oy0 + crop.y * (oy1 - oy0)
    share = ((nx1 - nx0) + (ny1 - ny0)) / ((ox1 - ox0) + (oy1 - oy0))
    return crop.model_copy(
        update={
            "x": min(1.0, max(0.0, (x - nx0) / (nx1 - nx0))),
            "y": min(1.0, max(0.0, (y - ny0) / (ny1 - ny0))),
            "zoom": min(8.0, max(1.0, crop.zoom * share)),
        }
    )


def framing_moved(
    framing: dict[str, Framing], old: Quad | None, new: Quad | None
) -> dict[str, Framing]:
    """The owner's framings, set on the photograph cut to ``old`` (None:
    whole), as the same parts of it cut to ``new``: a cut keeps what he
    chose to show, the model's (Wyspiański's „Macierzyństwo”, 2026-11-15:
    a close-up of the mother's face kept the thin wooden frame of the copy
    he picked from being cut away) and his own corrected corners alike
    (they wiped his framings until the audit of 2026-11-15)."""
    return {
        side: Framing(
            fill=_crop_moved(f.fill, old, new),
            detail=_crop_moved(f.detail, old, new),
            picture=_crop_moved(f.picture, old, new),
            fit=_crop_moved(f.fit, old, new),
        )
        for side, f in framing.items()
    }


#: :func:`strips_fit`: a strip may end this far inside the sheet Opus saw
#: (his corners are a hundredth or so off), and must end this far outside


def _owners_frame(cut: Cut) -> dict[str, Any]:
    """The frame's edge the owner set on ``cut`` (:attr:`Cut.surround_by`),
    kept when the work is cut anew."""
    return {
        "surround": cut.surround,
        "surround_kind": cut.surround_kind,
        "surround_by": "owner",
        "surround_asked": True,
    }


def _framed_by_owner(cut: Cut, frame: Quad) -> Cut:
    """``cut`` with the outer edge of the card's "W ramie" the owner set
    ("Popraw kadr" → "Rama"): the frame's or the passe-partout's edge,
    never changed by the model again."""
    kind = cut.surround_kind or "frame"
    mine = {"surround": frame, "surround_kind": kind, "surround_by": "owner"}
    return cut.model_copy(update={**mine, "surround_asked": True})


def _unframed_by_owner(cut: Cut) -> Cut:
    """``cut`` with no frame nor passe-partout around the work: what was
    around it is background to throw away (Mateusz 2026-11-20: „kadrujemy
    dzieło, ale nie ma ono ramy ani passepartout”), never found again."""
    mine = {"surround": None, "surround_kind": "", "surround_by": "owner"}
    return cut.model_copy(update={**mine, "surround_asked": True})


def shown_in(item: Item) -> Callable[[float], float | None] | None:
    """The shape a work is shown in when it is not the one its corners
    give: a work of the owner's own, in the shape of his size
    (``OwnWork.ratio``, as ``ImageCache`` cuts it)."""
    return item.own.ratio if item.own is not None else None


def framed(cut: Cut, ratio: Callable[[float], float | None] | None = None) -> Cut:
    """``cut`` with the card's "W ramie" as it is now (:attr:`Cut.framed_kind`,
    :attr:`Cut.framed_aspect`, :attr:`Cut.framed_inner`); ``ratio``: the
    shape the work is shown in when it is not the corners' (:func:`shown_in`)."""
    by, shown = cut.framed_by(), cut.shown()
    found = None
    if by is not None and shown is not None:
        found = framed_geometry(by[0], shown, cut.aspect, ratio)
    if by is None or found is None:
        none: dict[str, Any] = {"framed_kind": "", "framed_aspect": 0.0, "framed_inner": None}
        return cut.model_copy(update=none)
    return cut.model_copy(
        update={"framed_kind": by[1], "framed_aspect": found[0], "framed_inner": found[1]}
    )


class Crops:
    """The cuts of the museum works' photographs: kept, and set by the owner."""

    importer: Importer | None = None

    def __init__(self, library: Library, images: ImageCache) -> None:
        self.library = library
        self.images = images
        #: The works cared about, by id (``cared.Cared``): looked at first.
        self.cared: Callable[[], Mapping[str, int]] = dict

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

    @classmethod
    def open_to_cut(cls, item: Item) -> bool:
        """The model may cut it: no cut for the picture shown, or only its
        paper seen around it and nothing cut (a sheet on a thin strip of
        board the judge took for the paper's margin)."""
        cut = item.cut
        return cls.stale(item) or (
            cut is not None
            and cut.by == "auto"
            and cut.work is None
            and cut.plate is None
            and not cut.not_rectangle
        )

    def ranked(self, found: list[Item]) -> list[Item]:
        """``found`` in the order they are looked at: the works cared
        about, then those shown, the museums of Warsaw and Kraków, the
        newest."""
        found = list(found)
        found.sort(key=lambda i: i.added_at or "", reverse=True)
        found.sort(key=lambda i: i.source not in FIRST_SOURCES)
        found.sort(key=lambda i: not (not i.pooled or i.favorite or i.show_count > 0))
        cared = self.cared()
        found.sort(key=lambda i: cared.get(i.id, REST))
        return found

    def apply(self, item: Item, cut: Cut | None) -> Item:
        """``cut`` kept for the work and its pictures made again from it:
        the original, the thumbnail, the colours, the study's details."""
        if cut is not None and item.cut is not None and item.cut.surround_by == "owner":
            cut = cut.model_copy(update=_owners_frame(item.cut))
        cut = framed(cut.without_twin(), shown_in(item)) if cut is not None else None
        changes: dict[str, Any] = {"cut": cut}
        if item.framing:
            # His framings were set on the picture as it was shown: they
            # show the same parts of it cut anew (or whole again).
            before = item.cut_shown()
            after = cut.shown() if cut is not None and cut.picture == item.picture_key() else None
            if before != after:
                changes["framing"] = framing_moved(item.framing, before, after)
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
        self,
        item: Item,
        corners: Quad | None = None,
        paper: bool | None = None,
        frame: Quad | None = None,
        no_frame: bool = False,
    ) -> Item:
        """The owner's corners (of the work as shown, with its paper or
        without), or his "Pokaż z marginesem / bez marginesu" (without the
        sheet only where a plate is known: nobody is asked for one since
        2026-11-23). ``frame``: the
        outer edge of the frame or passe-partout as he set it (the card's
        "W ramie"); alone, the work's pictures stay as they are.
        ``no_frame``: nothing around the work is a frame ("Bez ramy").

        A restored work is cut on its drawing: a cut set on the museum's
        photograph before (its corners, its frame) is not this picture's
        and is not carried over (Mateusz 2026-11-26)."""
        if (
            item.sharper is not None
            and item.sharper.restored
            and item.cut is not None
            and item.cut.picture != item.picture_key()
        ):
            item = item.model_copy(update={"cut": None})
        alone = (frame is not None or no_frame) and corners is None and paper is None
        if alone and item.cut is not None and item.cut.shown() is not None and not self.stale(item):
            if no_frame or frame is None:
                mine = _unframed_by_owner(item.cut)
            else:
                mine = _framed_by_owner(item.cut, frame)
            cut = framed(mine, shown_in(item))
            log.info("crops: %s frame's edge set by the owner", item.id)
            return self.library.update(item.id, cut=cut) or item
        old = item.cut if item.cut is not None and not self.stale(item) else None
        with Image.open(self.images.museum_photo(item, urgent=True)) as img:
            aspect = round(img.width / img.height, 5)
        cut = (old or Cut()).model_copy(
            update={"by": "owner", "aspect": aspect, "picture": item.picture_key(), "at": _now()}
        )
        if paper is not None:
            cut.paper = paper
        if corners is not None:
            cut.work = corners  # the sheet of a print or drawing (``Cut.shown``)
        if no_frame:
            cut = _unframed_by_owner(cut)
        elif frame is not None:
            cut = _framed_by_owner(cut, frame)
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
        return self.apply(item, cut)
