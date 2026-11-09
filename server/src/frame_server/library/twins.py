"""One work under other titles, and details of works, told by their pictures.

Copies of a work are grouped by their titles (``duplicates``), but the
sources name one painting in their own languages: Vermeer's "Lekcja muzyki"
on Commons, "The music lesson" on WikiArt, "Die Malkunst" on Europeana for
"The Art of Painting"; and Commons keeps details of works as files of their
own, under the work's title ("Alegoria malarstwa", a strip of the painting)
or another (a search for Vermeer showed 71 works in 134 pictures, 23 of
them details; Mateusz 2026-11-09).

So the pictures of each artist's works are laid over each other, the way
``sharper`` tells a copy (``likeness``: ORB keypoints of the thumbnails
under one mapping). Two pictures of one work become one work in the
catalogue (``Item.copy_of``: the copies of a work all name one of them).
A picture that is only part of another, while that other is surely the
whole (a museum's own picture, or one that another copy shows whole), is a
detail (``Item.detail_of``), left out like any copy (``vocabulary.is_copy``).
A picture of a work with more around it (a frame) is no detail: when it is
not clear which of two is the whole, they are only copies.

Each picture is looked at once (``Item.twins_seen``), against the works of
its artist (one person by ``artists.known_names``, else the surname; the
first one named for "attributed to X / after Y"), at night and for the
artists of a search right after it.

A detail far smaller than its work is lost in a thumbnail: a head of "The
Night Watch" on Commons is 1/200 of the painting, 40 px of its thumbnail
(15 such heads, a shield, a drummer and a hand in Szukaj, Mateusz
2026-11-09). So a picture nothing was found for is also laid over the large
picture of each surely whole work of its artist whose titles share a word
with its own ("The Nightwatch Jan Brughman", "The Night Watch"), in windows
at up to three sizes (``large_keypoints``).
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from functools import lru_cache
from itertools import pairwise
from typing import TYPE_CHECKING, Any

import numpy as np

from ..imaging.layout import load_image
from .artists import known_names
from .duplicates import STOPWORDS, surname
from .images import display_copy
from .likeness import FEATURES, SAME, Keypoints, cover, inside, keypoints, mapping, turn
from .models import COLLECTIONS, Item, ItemKind
from .phrases import fold
from .vocabulary import is_copy

if TYPE_CHECKING:
    from PIL import Image

    from .images import ImageCache
    from .repo import Library

log = logging.getLogger(__name__)

#: Bump when the look changes, so every picture is looked at again.
VERSION = 2
#: A picture this many times smaller than the part of another it matches
#: (by area) is a detail of it (when that other is surely whole) ...
DETAIL = 1.3
#: ... while two pictures within this of each other are one picture whole.
WHOLE = 1.15
#: Copies of one work cover each other at least this much (intersection
#: over union; a frame or a margin around one of them leaves less) ...
COPY_COVER = 0.5
#: ... and are turned no more than this (degrees).
COPY_TURN = 5.0
#: Years of copies of one work as their sources date them (begun,
#: finished, "ca."): Vermeer's "Young Woman with a Water Pitcher" is 1657
#: at the Met, 1662 on Commons.
YEAR_SLACK = 10
#: Pairs laid over each other for one artist in one round at most: the
#: rest of their new pictures wait for the next.
PAIRS_A_ROUND = 60_000
#: A search's artists are looked at for this long at most (seconds).
SEARCH_BUDGET = 120.0
#: At night: this long at most (seconds), a quiet moment between artists.
NIGHT_BUDGET = 2400.0
#: An artist with more works than this is not looked at ("Unknown" under
#: another spelling, a school): too many pairs to tell anything.
MAX_WORKS = 4000
#: Long sides a work's large picture is looked at in for details too small
#: for its thumbnail, ...
LARGE_SIDES = (1600, 3200, 4800)
#: ... in windows of this side, overlapping by half (keypoints spread over
#: the whole picture, not only its busiest part).
WINDOW = 800
#: Keypoints looked for in each window: a detail's part of the picture
#: must hold enough of them (a head of "The Night Watch" is 1/200 of it).
WINDOW_FEATURES = 4 * FEATURES
#: A detail laid over the large picture stays within it, by this much of
#: its sides.
EDGE = 0.04
#: Pairs laid over each other that way in one round at most, ...
LARGE_PAIRS = 300
#: ... and large pictures downloaded for them in one round of all the
#: artists (those the frame has shown are here already).
LARGE_DOWNLOADS = 40
#: A work's picture smaller than this (long side) says no more than its
#: thumbnail.
LARGE_MIN = 1600
#: Title words too common to tell one work from another.
COMMON_WORDS = STOPWORDS | {
    "portrait",
    "study",
    "studies",
    "landscape",
    "still",
    "painting",
    "picture",
    "detail",
    "details",
    "fragment",
    "untitled",
    "sketch",
    "drawing",
    "young",
    "woman",
    "women",
    "people",
    "children",
    "figure",
    "figures",
    "scene",
    "image",
    "after",
    "their",
    "there",
    "which",
    "under",
    "attributed",
    "przypisywany",
    "wedlug",
    "obraz",
    "portret",
    "kobieta",
    "mezczyzna",
}
#: Where "attributed to X / after Y" stops naming the maker.
_AFTER = re.compile(
    r"\s*(?:/|;|\b(?:after|wedlug|według|wg\.|naar|nach|d'apr[eè]s)\b).*$", re.IGNORECASE
)


def candidate(item: Item) -> bool:
    """A picture of a work that may be a copy or a detail of another."""
    return (
        item.kind == ItemKind.ARTWORK
        and not item.part_of
        and item.look is None
        and not item.detail_of
        and not is_copy(item)
    )


def artist_key(artist: str) -> str:
    """Who made it, so that only one artist's works are laid over each
    other: their person in the catalogue, else their surname; "" for nobody."""
    first = _AFTER.sub("", artist).strip()
    if first and surname(first):
        artist = first
    person = known_names().person(artist)
    if person is not None:
        return f"person:{person}"
    name = surname(artist)
    return f"surname:{name}" if name else ""


@lru_cache(maxsize=1 << 16)
def title_words(title: str) -> frozenset[str]:
    """The words of a title that may name its work (folded, five letters or
    more, not :data:`COMMON_WORDS`), and each two next to each other joined
    ("Night Watch" for Commons' "Nightwatch")."""
    found = re.findall(r"[^\W\d_]+", fold(title.split("\n")[0]))
    kept = {w for w in found if len(w) >= 5 and w not in COMMON_WORDS}
    kept.update(
        a + b
        for a, b in pairwise(found)
        if len(a + b) >= 8 and a not in COMMON_WORDS and b not in COMMON_WORDS
    )
    return frozenset(kept)


def _apart(a: Item, b: Item) -> bool:
    """Pairs never looked at: two museums' own works (a museum's work is
    not in another), years too far apart unless their titles share a word
    (a copy dated when it was made, or when its work was cut down)."""
    if a.source in COLLECTIONS and b.source in COLLECTIONS:
        return True
    if a.year is None or b.year is None or abs(a.year - b.year) <= YEAR_SLACK:
        return False
    return not title_words(a.title) & title_words(b.title)


class Fit:
    """How two pictures lie over each other: ``area`` is how many times
    the first's whole is the part of the second it covers (above 1: the
    second is a part of the first)."""

    __slots__ = ("area", "cover", "matches", "turn")

    def __init__(self, matches: int, area: float, cover: float, turn: float) -> None:
        self.matches = matches
        self.area = area
        self.cover = cover
        self.turn = turn

    @property
    def whole(self) -> bool:
        return 1 / WHOLE <= self.area <= WHOLE


class Twins:
    """Finds copies and details among each artist's works. Safe to share
    between threads: one round at a time."""

    def __init__(self, library: Library, images: ImageCache) -> None:
        self.library = library
        self.images = images
        self._lock = threading.Lock()
        self._asked: set[str] = set()
        self._asked_lock = threading.Lock()
        self.clock: Callable[[], float] = time.monotonic
        #: Large pictures the round may still download.
        self._downloads = 0

    # -- when ------------------------------------------------------------------

    def after_search(self, items: Iterable[Item]) -> None:
        """The artists of a search's works looked at in the background, those
        with pictures not looked at yet."""
        keys = {
            key
            for i in items
            if i.twins_seen < VERSION and candidate(i) and (key := artist_key(i.artist))
        }
        with self._asked_lock:
            keys -= self._asked
            if not keys:
                return
            self._asked |= keys
        threading.Thread(target=self._search_round, args=(keys,), name="twins", daemon=True).start()

    def _search_round(self, keys: set[str]) -> None:
        try:
            self.look(keys, budget=SEARCH_BUDGET)
        except Exception:
            log.exception("twins: a search's artists")
        finally:
            with self._asked_lock:
                self._asked -= keys

    def at_night(self, quiet: Callable[[], bool] = lambda: True) -> int:
        return self.look(None, budget=NIGHT_BUDGET, quiet=quiet)

    # -- looking ---------------------------------------------------------------

    def look(
        self,
        keys: set[str] | None = None,
        budget: float = NIGHT_BUDGET,
        quiet: Callable[[], bool] = lambda: True,
    ) -> int:
        """Looks at the pictures not looked at yet of the artists ``keys``
        (None: all, the fewest new pictures first) for ``budget`` seconds;
        returns how many pictures were looked at."""
        with self._lock:
            started = self.clock()
            self._downloads = LARGE_DOWNLOADS
            by_artist: dict[str, list[Item]] = defaultdict(list)
            for item in self.library.query(include_excluded=True)[1]:
                key = artist_key(item.artist) if candidate(item) else ""
                if key and (keys is None or key in keys):
                    by_artist[key].append(item)
            due = [
                (key, works)
                for key, works in by_artist.items()
                if len(works) <= MAX_WORKS and any(i.twins_seen < VERSION for i in works)
            ]
            due.sort(key=lambda kw: (sum(i.twins_seen < VERSION for i in kw[1]), kw[0]))
            seen = copies = details = 0
            for _key, works in due:
                if self.clock() - started > budget or not quiet():
                    break
                done = self._artist(works, started + budget)
                seen += done[0]
                copies += done[1]
                details += done[2]
            if seen:
                log.info(
                    "twins: %d pictures of %d artists looked at in %.0f s: %d copies, %d details",
                    seen,
                    len(due),
                    self.clock() - started,
                    copies,
                    details,
                )
            return seen

    def _artist(self, works: list[Item], until: float) -> tuple[int, int, int]:
        """One artist's new pictures laid over all their works'; how many
        were looked at, how many copies and details were found."""
        new = [i for i in works if i.twins_seen < VERSION]
        grouped = self.library.works()
        points: dict[str, Keypoints | None] = {}

        def of(item: Item) -> Keypoints | None:
            if item.id not in points:
                try:
                    path = self.images.thumb_path(item)
                    points[item.id] = keypoints(path) if path.is_file() else None
                except Exception as err:  # a broken file: no opinion
                    log.info("twins: keypoints of %s: %s", item.id, err)
                    points[item.id] = None
            return points[item.id]

        fits: dict[tuple[str, str], Fit] = {}
        looked: list[Item] = []
        pairs = 0
        done: set[str] = set()
        for item in new:
            if self.clock() > until or pairs >= PAIRS_A_ROUND:
                break
            mine = of(item)
            for other in works:
                if other.id == item.id or other.id in done or _apart(item, other):
                    continue
                at = grouped.group_index(item.id)
                if at is not None and at == grouped.group_index(other.id):
                    continue  # one work already
                theirs = of(other) if mine is not None else None
                if mine is None or theirs is None:
                    continue
                pairs += 1
                fit = _fit(mine, theirs)
                if fit is not None:
                    fits[(item.id, other.id)] = fit
            done.add(item.id)
            looked.append(item)
        large = self._large_details(works, looked, fits, grouped, until)
        copies, details = self._write(works, looked, fits, large)
        return len(looked), copies, details

    def _large_details(
        self,
        works: list[Item],
        looked: list[Item],
        fits: dict[tuple[str, str], Fit],
        grouped: Any,
        until: float,
    ) -> dict[str, str]:
        """Details too small for the thumbnails: the pictures looked at that
        lie over nothing, laid over the large pictures of the artist's surely
        whole works whose titles share a word with theirs; detail -> work."""
        paired = {i for pair in fits for i in pair}
        sure = {i.id for i in works if _surely_whole(i)}
        sure.update(i for (a, b), fit in fits.items() if fit.whole for i in (a, b))
        if not sure:
            return {}
        words: dict[int | str, frozenset[str]] = {}

        def work_words(item: Item) -> frozenset[str]:
            at = grouped.group_index(item.id)
            key: int | str = item.id if at is None else at
            if key not in words:
                copies = [item] if at is None else grouped.groups[at]
                words[key] = frozenset().union(*(title_words(c.title) for c in copies))
            return words[key]

        pairs: list[tuple[int, Item, Item]] = []
        for small in looked:
            if small.id in paired or small.source in COLLECTIONS:
                continue
            mine = title_words(small.title)
            if not mine:
                continue
            at = grouped.group_index(small.id)
            for big in works:
                if big.id not in sure or big.id == small.id:
                    continue
                if at is not None and at == grouped.group_index(big.id):
                    continue
                shared = len(mine & work_words(big))
                if shared:
                    pairs.append((shared, small, big))
        pairs.sort(key=lambda p: (-p[0], p[1].id, p[2].id))
        large: dict[str, list[Keypoints] | None] = {}
        found: dict[str, str] = {}
        for _shared, small, big in pairs[:LARGE_PAIRS]:
            if self.clock() > until:
                break
            if small.id in found:
                continue
            if big.id not in large:
                img, downloaded = self._large_picture(big, self._downloads > 0)
                self._downloads -= downloaded
                large[big.id] = large_keypoints(img) if img is not None else None
            sets = large[big.id]
            path = self.images.thumb_path(small)
            if not sets or not path.is_file():
                continue
            try:
                mine_points = keypoints(path)
            except Exception as err:  # a broken file: no opinion
                log.info("twins: keypoints of %s: %s", small.id, err)
                continue
            if mine_points is not None and any(lies_within(mine_points, s) for s in sets):
                log.info("twins: %s is a detail of %s (large picture)", small.id, big.id)
                found[small.id] = big.id
        return found

    def _large_picture(self, item: Item, may_download: bool) -> tuple[Image.Image | None, int]:
        """``item``'s picture as the frame has it, else downloaded when
        ``may_download``; and whether it was."""
        path = self.images.image_path(item)
        try:
            if path.is_file():
                return load_image(path), 0
            if not may_download:
                return None, 0
            return self.images.sample(display_copy(item)), 1
        except Exception as err:  # gone, refused, broken: no opinion
            log.info("twins: large picture of %s: %s", item.id, err)
            return None, int(may_download)

    def _write(
        self,
        works: list[Item],
        looked: list[Item],
        fits: dict[tuple[str, str], Fit],
        large: dict[str, str] | None = None,
    ) -> tuple[int, int]:
        by_id = {i.id: i for i in works}
        whole_twin: set[str] = set()
        for (a, b), fit in fits.items():
            if fit.whole:
                whole_twin.update((a, b))
        # Details: the smaller of two, when the larger is surely whole.
        detail_of: dict[str, str] = {}
        for (a, b), fit in fits.items():
            if fit.whole:
                continue
            big, small = (a, b) if fit.area > 1 else (b, a)
            area = fit.area if fit.area > 1 else 1 / fit.area
            sure = by_id[big].source in COLLECTIONS or big in whole_twin or by_id[big].copy_of
            if area >= DETAIL and sure and by_id[small].source not in COLLECTIONS:
                detail_of.setdefault(small, big)
        for small, big in (large or {}).items():
            detail_of.setdefault(small, big)
        # Copies: everything else that lies over each other, together.
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def join(x: str, y: str) -> None:
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[max(rx, ry)] = min(rx, ry)

        for item in works:
            if item.copy_of:
                join(f"copy:{item.id}", f"copy:{item.copy_of}")
        found = 0
        for (a, b), fit in fits.items():
            if a in detail_of or b in detail_of:
                continue
            if fit.cover >= COPY_COVER and fit.turn <= COPY_TURN:
                join(f"copy:{a}", f"copy:{b}")
                found += 1
        members: dict[str, list[Item]] = defaultdict(list)
        for item in works:
            if item.id not in detail_of:
                members[find(f"copy:{item.id}")].append(item)
        changes: dict[str, dict[str, Any]] = {}
        for group in members.values():
            if len(group) < 2:
                continue
            # The copy they all name: the one most of them name already.
            named = [i.copy_of for i in group if i.copy_of]
            root = max(set(named), key=named.count) if named else min(i.id for i in group)
            for item in group:
                want = "" if item.id == root else root
                if item.copy_of != want:
                    changes.setdefault(item.id, {})["copy_of"] = want
        for small, big in detail_of.items():
            changes.setdefault(small, {})["detail_of"] = big
        for item in looked:
            changes.setdefault(item.id, {})["twins_seen"] = VERSION
        with self.library.batch():
            for item_id, fields in changes.items():
                self.library.update(item_id, **fields)
        return found, len(detail_of)


def _surely_whole(item: Item) -> bool:
    """A large picture of a work whole: a museum's own, or one that is one
    of several copies of a work (``Item.copy_of``) or has a sharper copy."""
    if item.kind != ItemKind.ARTWORK or item.part_of or item.detail_of:
        return False
    if item.sharper is None and 0 < max(item.width or 0, item.height or 0) < LARGE_MIN:
        return False
    return item.source in COLLECTIONS or bool(item.copy_of) or item.sharper is not None


def large_keypoints(img: Image.Image) -> list[Keypoints]:
    """Keypoints of a large picture at :data:`LARGE_SIDES` (no larger than
    it is), found in overlapping windows of :data:`WINDOW` and kept in the
    picture's coordinates at that size; none for a picture no larger than
    a window."""
    try:
        import cv2
    except ImportError:  # pragma: no cover - a dependency, but optional here
        return []
    from PIL import Image as PILImage

    grey = img.convert("L")
    longest = max(grey.size)
    if longest <= WINDOW:
        return []
    orb = cv2.ORB_create(nfeatures=WINDOW_FEATURES)  # type: ignore[attr-defined]
    found: list[Keypoints] = []
    for side in sorted({min(s, longest) for s in LARGE_SIDES}):
        scale = side / longest
        size = (max(1, round(grey.width * scale)), max(1, round(grey.height * scale)))
        pixels = np.asarray(grey.resize(size, PILImage.Resampling.LANCZOS))
        points: list[Any] = []
        descriptors: list[Any] = []
        lefts, tops = _starts(size[0]), _starts(size[1])
        for row, top in enumerate(tops):
            for column, left in enumerate(lefts):
                window = pixels[top : top + WINDOW, left : left + WINDOW]
                spots, described = orb.detectAndCompute(np.ascontiguousarray(window), None)
                if described is None:
                    continue
                for spot, row_bits in zip(spots, described, strict=True):
                    x, y = spot.pt[0] + left, spot.pt[1] + top
                    # Each point once, from the window it is nearest the
                    # middle of: twice over, it would be its own rival in
                    # the matching (Lowe's ratio test).
                    if _nearest(x, lefts) == column and _nearest(y, tops) == row:
                        points.append((x, y))
                        descriptors.append(row_bits)
        if len(points) >= SAME:
            found.append(Keypoints(np.array(points, dtype=np.float32), np.array(descriptors), size))
    return found


def _nearest(at: float, starts: list[int]) -> int:
    """The window whose middle is nearest ``at`` along one side."""
    return min(range(len(starts)), key=lambda i: abs(starts[i] + WINDOW / 2 - at))


def _starts(length: int) -> list[int]:
    """Where the windows along one side start: half a window apart, the
    last one at the edge."""
    if length <= WINDOW:
        return [0]
    starts = list(range(0, length - WINDOW, WINDOW // 2))
    return [*starts, length - WINDOW]


def lies_within(small: Keypoints, large: Keypoints) -> bool:
    """``small`` is a part of ``large``: one mapping lays many of its
    keypoints over the large picture's, unturned, its frame within the
    large picture's and at most 1/:data:`DETAIL` of it."""
    count, found = mapping(small, large)
    if count < SAME or found is None or turn(found) > COPY_TURN:
        return False
    if inside(small, large, found) > 1 / DETAIL:
        return False
    width, height = small.size
    corners = np.array([[0, 0, 1], [width, 0, 1], [width, height, 1], [0, height, 1]], float)
    laid = corners @ np.asarray(found, float).T
    lw, lh = large.size
    return bool(
        laid[:, 0].min() >= -EDGE * lw
        and laid[:, 1].min() >= -EDGE * lh
        and laid[:, 0].max() <= (1 + EDGE) * lw
        and laid[:, 1].max() <= (1 + EDGE) * lh
    )


def _fit(a: Keypoints, b: Keypoints) -> Fit | None:
    """How ``a`` lies over ``b``; None when they are not one picture."""
    count, found = mapping(a, b)
    if count < SAME or found is None:
        return None
    area = inside(a, b, found)
    if not math.isfinite(area) or area <= 0:
        return None
    return Fit(count, area, cover(a, b, found), turn(found))
