"""The works the owner cares about, looked at first by the night's tidying
(Mateusz 2026-11-11: "prace sprzątania co do zasady w pierwszej kolejności
dotyczyły tych dzieł, które są w moich ulubionych, playlistach oraz w karcie
Odkrywaj").

Copies and details (``twins`` and its judge), the catalogue's gatekeeper,
the night audit, sharper copies and the museums the works hang in each have
more to do than a night allows: what they pick first is, in this order,

0. what someone keeps: anyone's Favourites and the works of manual and
   album playlists;
1. what someone will see: the first works of smart playlists, Discover's
   cards (covers and the themes' pages kept) and Propozycje dnia;
2. the rest of the catalogue, in each task's own order.

Worked out at most every :data:`FRESH_FOR` seconds (a smart playlist is a
query of the whole catalogue), and only by the tasks that sort with it.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, TypeVar

from .library import PlaylistKind

if TYPE_CHECKING:
    from .service import FrameService

log = logging.getLogger(__name__)

#: The rank of a work kept, of one shown, of the rest.
KEPT, SHOWN, REST = 0, 1, 2
#: Works of a smart playlist counted, its first ones (a smart playlist may
#: hold most of the catalogue).
SMART_HEAD = 1000
#: Seconds the works are not worked out again.
FRESH_FOR = 1800.0

T = TypeVar("T")


class Cared:
    def __init__(self, service: FrameService) -> None:
        self.service = service
        self._lock = threading.Lock()
        self._at = float("-inf")
        self._ranks: dict[str, int] = {}
        self.clock: Callable[[], float] = time.monotonic

    def ranks(self) -> dict[str, int]:
        """The works cared about, by id: :data:`KEPT` or :data:`SHOWN`."""
        with self._lock:
            if self.clock() - self._at >= FRESH_FOR:
                self._ranks = self._work_out()
                self._at = self.clock()
            return self._ranks

    def forget(self) -> None:
        """Worked out again when next asked."""
        with self._lock:
            self._at = float("-inf")

    def rank(self, item_id: str) -> int:
        return self.ranks().get(item_id, REST)

    def ids(self) -> frozenset[str]:
        return frozenset(self.ranks())

    def first(self, things: Iterable[T], key: Callable[[T], Iterable[str]]) -> list[T]:
        """``things`` with those of the works cared about first, each kept
        in its own order (``key``: a thing's works, e.g. both of a pair)."""
        ranks = self.ranks()
        if not ranks:
            return list(things)
        return sorted(things, key=lambda t: min((ranks.get(i, REST) for i in key(t)), default=REST))

    def _work_out(self) -> dict[str, int]:
        library = self.service.library
        ranks: dict[str, int] = {}

        def mark(ids: Iterable[str], rank: int) -> None:
            for item_id in ids:
                if ranks.get(item_id, REST) > rank:
                    ranks[item_id] = rank

        for hearts in library.fans().values():
            mark(hearts, KEPT)
        for playlist in library.playlists():
            if playlist.is_favorites:
                continue  # hearts, above
            if playlist.kind != PlaylistKind.SMART:
                mark(playlist.item_ids, KEPT)
                continue
            try:
                items = library.playlist_items(playlist)
            except Exception:  # one playlist's rules: no reason to stop
                log.exception("cared: playlist %s", playlist.id)
                continue
            mark((i.id for i in items[:SMART_HEAD]), SHOWN)
        try:
            from .web.discover_api import shown_ids

            mark(shown_ids(self.service), SHOWN)
        except Exception:
            log.exception("cared: Discover's works")
        kept = sum(1 for r in ranks.values() if r == KEPT)
        log.info("cared: %d works kept, %d shown", kept, len(ranks) - kept)
        return ranks
