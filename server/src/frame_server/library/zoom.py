"""Works to look at far closer than the frame shows them ("Pod lupą",
Mateusz 2026-11-09): Commons files that have a tile set (``fragments``:
"The Night Watch" in tiles of a 40 000 px scan), shown by the work itself
or by a copy in its place (``Item.sharper``). Their tiles load while the
full-screen viewer zooms in, up to 24 times.

The list of such files is read from Commons once a month (``fragments``)
and kept here for every list of works to mark them without asking.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable

from .models import Item

_lock = threading.Lock()
_pages: frozenset[str] = frozenset()


def known(pages: Iterable[str]) -> None:
    """The Commons page ids with a tile set, as last listed."""
    global _pages
    found = frozenset(str(p) for p in pages)
    with _lock:
        _pages = found


def pages() -> frozenset[str]:
    with _lock:
        return _pages


def zooms(item: Item) -> bool:
    """``item``'s picture shown is a Commons file with a tile set."""
    if item.part_of:
        return False
    shown = item.sharper.item_id if item.sharper is not None else item.id
    source, _, page = shown.partition(":")
    return source == "wmc" and page in pages()
