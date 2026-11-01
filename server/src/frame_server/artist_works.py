"""Other works by a study's artist ("Inne prace artysty"), at the end of the
page: the catalogue's first, the owner's favourites ahead, in an order kept
for the work; when the catalogue has too few, the museums are asked once
for the artist and what they have is kept with the work. Each work comes
once: copies of it from other sources, under a title in another language
too, are told by their pictures (:mod:`.library.likeness`); none is a copy
of the work the page is about.
"""

from __future__ import annotations

import logging
import random
import threading
import zlib
from collections.abc import Callable
from typing import TYPE_CHECKING

import httpx

from .library import Item, ItemKind, PlaylistRules
from .library.artists import is_artist
from .library.duplicates import same_work
from .library.likeness import Likeness
from .library.models import Note
from .library.vocabulary import artist_matches, fold, is_photograph

if TYPE_CHECKING:
    from .library import Library
    from .library.images import ImageCache

log = logging.getLogger(__name__)

KIND = "by_artist"
VERSION = "by-artist-1"
#: Works shown.
SHOWN = 6
#: The catalogue's works by the artist looked among.
POOL = 200
#: Results asked from each museum when the catalogue has too few.
MUSEUM_HITS = 8


def _key(item: Item) -> str:
    return fold(item.title).strip()


class ArtistWorks:
    def __init__(
        self,
        library: Library,
        search: Callable[[str, int], tuple[int, list[Item], list[str]]],
        images: ImageCache | None = None,
    ) -> None:
        self.library = library
        self.images = images
        self.likeness = Likeness(images) if images is not None else None
        #: Every museum at once: ``Importer.search_all``.
        self.search = search
        self._lock = threading.Lock()
        self._looking: set[str] = set()

    def works(self, item: Item, skip: set[str] | None = None) -> list[Item]:
        """Up to :data:`SHOWN` other works by ``item``'s artist, none of
        ``skip`` (ids shown elsewhere on the page), nor a work twice or the
        work itself in another copy; none for an unknown or anonymous
        artist."""
        if not is_artist(item.artist):
            return []
        rules = PlaylistRules(kinds=[ItemKind.ARTWORK], artists=[item.artist])
        found = self.library.query(rules, sort="random", seed=self._seed(item), limit=POOL)[1]
        found.sort(key=lambda i: not i.favorite)  # stable: the order drawn stays
        picked: list[Item] = []
        skip = skip or set()
        titles = {_key(item)}
        seen = [item]
        for other in [*found, *self.from_museums(item.id)]:
            if len(picked) == SHOWN:
                break
            if (
                other.id == item.id
                or other.id in skip
                or other.look is not None
                or other.excluded
                or is_photograph(other)
                or not other.artist
                or not artist_matches(other.artist, [item.artist])
                or _key(other) in titles
                or any(self.copies(other, s) for s in seen)
            ):
                continue
            titles.add(_key(other))
            seen.append(other)
            picked.append(other)
        return picked

    def copies(self, a: Item, b: Item) -> bool:
        """``a`` and ``b`` are one work: by the catalogue's rules (title,
        artist, year, shape, address) or by their pictures."""
        if same_work(a, b):
            return True
        return self.likeness is not None and self.likeness.same(a, b)

    @staticmethod
    def _seed(item: Item) -> int:
        return zlib.crc32(item.id.encode())

    def from_museums(self, item_id: str) -> list[Item]:
        """What the museums had for the artist, when asked."""
        note = self.library.note(item_id, KIND)
        if note is None or note.prompt_version != VERSION:
            return []
        return [Item.model_validate(raw) for raw in note.data.get("items", [])]

    def asked(self, item_id: str) -> bool:
        note = self.library.note(item_id, KIND)
        return note is not None and note.prompt_version == VERSION

    def look_soon(self, item: Item, shown: int) -> bool:
        """Asks the museums in the background when fewer than :data:`SHOWN`
        works are shown and they were not asked yet; True while they are."""
        if shown >= SHOWN or not is_artist(item.artist) or self.asked(item.id):
            return False
        with self._lock:
            if item.id in self._looking:
                return True
            self._looking.add(item.id)
        threading.Thread(
            target=self._look_then_done, args=(item,), name="artist-works", daemon=True
        ).start()
        return True

    def _look_then_done(self, item: Item) -> None:
        try:
            self.look(item)
        except Exception:
            log.exception("other works by the artist of %s", item.id)
        finally:
            with self._lock:
                self._looking.discard(item.id)

    def look(self, item: Item) -> list[Item]:
        """Asks the museums for the artist once and keeps what is by them
        (also nothing: not asked again)."""
        try:
            hits = self.search(item.artist, MUSEUM_HITS)[1]
        except (httpx.HTTPError, ValueError) as err:
            log.info("museums on %r: %s", item.artist, err)
            hits = []
        rng = random.Random(self._seed(item))
        found = [
            h
            for h in hits
            if h.id != item.id and h.artist and artist_matches(h.artist, [item.artist])
        ]
        rng.shuffle(found)
        if self.images is not None:
            for hit in found:  # the app shows them anyway; here to compare
                try:
                    self.images.ensure_thumb(hit)
                except Exception as err:  # told apart by title only
                    log.info("thumbnail of %s: %s", hit.id, err)
        self.library.save_note(
            Note(
                item_id=item.id,
                kind=KIND,
                model="",
                prompt_version=VERSION,
                data={"items": [h.model_dump(mode="json") for h in found]},
            )
        )
        return found
