"""Works whose picture is small for the frame ("niska rozdzielczość",
Mateusz 2026-11-12): a mark after the title on their tiles and on their
card, so a playlist's weak pictures are seen before the frame shows them.

Only a size that is known counts (``images.said_side``: a sharper copy's,
or one its source says; else the original's as it was downloaded,
``ImageCache.known_size``). A thumbnail's size is never one (the Met's
600 px): a work of a source that says none has no mark until its original
is here, and the works of playlists and Ulubione have theirs.

The sizes downloaded are told here once (:func:`known_sizes`) for every
list of works to mark them without asking.
"""

from __future__ import annotations

from collections.abc import Callable

from .images import OWN_SOURCES, said_side
from .models import Item, ItemKind

#: A picture whose long side is shorter than this is marked: the frame's
#: 2560 px enlarge it 1.6 times or more, and its softness shows on the
#: panel from close by (de Chirico's on WikiArt are under 1000 px).
LOW_SIDE = 1600

Sizes = Callable[[Item], tuple[int, int] | None]

_sizes: Sizes | None = None


def known_sizes(sizes: Sizes | None) -> None:
    """Where the originals' sizes as downloaded are read
    (``ImageCache.known_size``); None forgets it."""
    global _sizes
    _sizes = sizes


def low_side(item: Item, size: tuple[int, int] | None = None) -> int:
    """The long side of ``item``'s picture when it is known and shorter than
    :data:`LOW_SIDE`, else 0. Museum works only (not the owner's photos,
    nor a tile of a work). ``size``: the original's, when the caller has
    read it already."""
    if item.kind != ItemKind.ARTWORK or item.part_of or item.source in OWN_SOURCES:
        return 0
    side = said_side(item)
    if side is None:
        if size is None and _sizes is not None:
            size = _sizes(item)
        if size is not None and size[0] > 0 and size[1] > 0:
            side = max(size)
    return side if side is not None and 0 < side < LOW_SIDE else 0
