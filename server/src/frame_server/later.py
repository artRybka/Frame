"""What a work led to ("Co z niego wyrosło"), with pictures: each later
work Claude names in a page (the work of the day, a study) is looked up
once in the museums, and what was found is kept; its picture opens its card.

A museum's copy is taken only when its author is the one named and its
title shares a word with the one named.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

import httpx
from pydantic import BaseModel

from .ai.jobs import text_hash
from .library import Item
from .library.models import Note
from .library.vocabulary import artist_matches, fold

if TYPE_CHECKING:
    from .ai.daily import Legacy
    from .library import Library

log = logging.getLogger(__name__)

KIND = "later"
VERSION = "later-2"
#: Results asked from each museum for one later work.
MUSEUM_HITS = 4
#: Title words this short say nothing ("the", "of", "la").
WORD_MIN = 4


class LaterLink(BaseModel):
    """What was found for one later work."""

    #: A museum's copy of it (not in the library).
    item: Item | None = None


def entry_key(entry: Legacy) -> str:
    return text_hash(entry.who, entry.title, entry.search)[:12]


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", fold(text)) if len(w) >= WORD_MIN and not w.isdigit()}


def same_work(hit: Item, entry: Legacy) -> bool:
    """``hit`` is by the author named and its title shares a word with the
    title named (the original one in ``search`` or the Polish one)."""
    if not hit.artist or not artist_matches(hit.artist, [entry.who]):
        return False
    named = (_words(entry.search) | _words(entry.title)) - _words(entry.who)
    return bool(named & _words(hit.title))


class LaterWorks:
    def __init__(
        self,
        library: Library,
        search: Callable[[str, int], tuple[int, list[Item], list[str]]],
    ) -> None:
        self.library = library
        #: Every museum at once: ``Importer.search_all``.
        self.search = search
        self._lock = threading.Lock()
        self._looking: set[str] = set()

    def known(self, item_id: str) -> dict[str, LaterLink]:
        """What was found for the later works of ``item_id``'s pages, by
        :func:`entry_key`."""
        note = self.library.note(item_id, KIND)
        if note is None or note.prompt_version != VERSION:
            return {}
        return {k: LaterLink.model_validate(v) for k, v in note.data.items()}

    def missing(self, item_id: str, entries: list[Legacy]) -> list[Legacy]:
        known = self.known(item_id)
        return [e for e in entries if entry_key(e) not in known]

    def look_soon(self, item: Item, entries: list[Legacy]) -> bool:
        """Looks the later works up in the background unless they are known;
        True while they are being looked up."""
        if not self.missing(item.id, entries):
            return False
        with self._lock:
            if item.id in self._looking:
                return True
            self._looking.add(item.id)
        threading.Thread(
            target=self._look_then_done, args=(item, entries), name="later-works", daemon=True
        ).start()
        return True

    def _look_then_done(self, item: Item, entries: list[Legacy]) -> None:
        try:
            self.look(item, entries)
        except Exception:
            log.exception("later works of %s", item.id)
        finally:
            with self._lock:
                self._looking.discard(item.id)

    def look(self, item: Item, entries: list[Legacy]) -> dict[str, LaterLink]:
        """Looks up the later works not known yet and keeps what was found
        (also nothing: not asked again)."""
        known = self.known(item.id)
        for entry in entries:
            key = entry_key(entry)
            if key not in known:
                known[key] = self._find(item, entry)
        self.library.save_note(
            Note(
                item_id=item.id,
                kind=KIND,
                model="",
                prompt_version=VERSION,
                data={k: v.model_dump(mode="json") for k, v in known.items()},
            )
        )
        return known

    def _find(self, item: Item, entry: Legacy) -> LaterLink:
        return LaterLink(item=self._museum(item, entry))

    def _museum(self, item: Item, entry: Legacy) -> Item | None:
        if not entry.search:
            return None
        try:
            hits = self.search(entry.search, MUSEUM_HITS)[1]
        except (httpx.HTTPError, ValueError) as err:
            log.info("museums on %r: %s", entry.search, err)
            return None
        return next((h for h in hits if h.id != item.id and same_work(h, entry)), None)
