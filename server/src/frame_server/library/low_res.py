"""Works whose picture is small for the frame ("niska rozdzielczość",
Mateusz 2026-11-12): a mark after the title on their tiles and on their
card, so a playlist's weak pictures are seen before the frame shows them.

Only a size that is known counts: a sharper copy's; else the original's
as it was downloaded (``ImageCache.known_size``), which wins over the one
its source says (``images.said_side``): WikiArt said 433 × 600 of
Wyspiański's „Macierzyństwo”, whose file is 1441 × 1999, and the card
marked it „600 px” (Mateusz 2026-11-15). A thumbnail's size is never one
(the Met's 600 px): a work of a source that says none has no mark until
its original is here, and the works of playlists and Ulubione have theirs.

How long a picture is is told here once (:func:`known_sizes`:
``ImageCache.long_side``) for every list of works to mark them without
asking.
"""

from __future__ import annotations

from collections.abc import Callable

from ..imaging.cut import long_share
from .images import OWN_SOURCES, said_side
from .models import Item, ItemKind

#: A picture whose long side is shorter than this is marked: the frame's
#: 2560 px enlarge it 1.6 times or more, and its softness shows on the
#: panel from close by (de Chirico's on WikiArt are under 1000 px).
LOW_SIDE = 1600
#: A picture shorter than this is offered to our restorer (Mateusz
#: 2026-11-26: "Rozszerzmy zdjęcia kwalifikujące się do 1800px"); the
#: mark of a small picture stays at :data:`LOW_SIDE`.
RESTORE_SIDE = 1800

Sides = Callable[[Item], int | None]

_sides: Sides | None = None


def known_sizes(sides: Sides | None) -> None:
    """Where a picture's long side is read (``ImageCache.long_side``); None
    forgets it (then only :func:`~.images.said_side` counts)."""
    global _sides
    _sides = sides


def low_side(item: Item, size: tuple[int, int] | None = None, below: int = LOW_SIDE) -> int:
    """The long side of ``item``'s picture when it is known and shorter than
    :data:`LOW_SIDE`, else 0. Museum works only (not the owner's photos,
    nor a tile of a work). ``size``: the original's, when the caller has
    read it already. ``below``: the side it is to be shorter than."""
    if item.kind != ItemKind.ARTWORK or item.part_of or item.source in OWN_SOURCES:
        return 0
    side = said_side(item) if item.sharper is not None else None
    if side is None and size is not None and min(size) > 0:
        side = max(size)
    if side is None and _sides is not None:
        side = _sides(item)
    if side is None:
        side = said_side(item)
    shown = item.cut_shown()
    if side is not None and shown is not None and item.cut is not None:
        # Sizes are the museum photograph's; the work cut out of it is less.
        side = round(side * long_share(shown, (round(item.cut.aspect * 1000), 1000)))
    return side if side is not None and 0 < side < below else 0


def restore_side(item: Item, size: tuple[int, int] | None = None) -> int:
    """The long side of ``item``'s picture when our restorer is offered for
    it (shorter than :data:`RESTORE_SIDE`), else 0."""
    return low_side(item, size, below=RESTORE_SIDE)
