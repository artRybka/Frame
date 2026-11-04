"""Works put in a mixed order for a row or a page to look at: no two of
one painter, or from one museum, side by side while another can stand
between them, and two of one kind (painting, print, drawing) in a row only
when it can't be helped. The app weaves the sets it streams the same way
(``WorkWeave``)."""

from __future__ import annotations

from .models import Item
from .vocabulary import fold

#: How many works back a painter or a museum is avoided (when there are
#: others to choose from).
SPACING = 3


def _painter(item: Item) -> str:
    return fold(item.artist).strip() or f"#{item.id}"


def _museum(item: Item) -> str:
    return fold(item.held_by or item.museum).strip() or f"@{item.source}"


def _kind(item: Item) -> str:
    return fold(item.classification).strip() or f"#{item.id}"


def mixed(items: list[Item]) -> list[Item]:
    """``items`` reordered: each next work is the one whose painter, then
    museum, then kind was seen longest ago (or not in the last few), and of
    those the first in the order given, which is kept as far as it can be."""
    left = list(items)
    done: list[Item] = []
    while left:
        painters = [_painter(i) for i in done[-SPACING:]]
        museums = [_museum(i) for i in done[-SPACING:]]
        kinds = [_kind(i) for i in done[-1:]]

        def back(key: str, recent: list[str]) -> int:
            """How far back ``key`` was (0: not in ``recent``)."""
            for n, seen in enumerate(reversed(recent), start=1):
                if seen == key:
                    return SPACING + 1 - n
            return 0

        index = min(
            range(len(left)),
            key=lambda n: (
                back(_painter(left[n]), painters),
                back(_museum(left[n]), museums),
                back(_kind(left[n]), kinds),
                n,
            ),
        )
        done.append(left.pop(index))
    return done
