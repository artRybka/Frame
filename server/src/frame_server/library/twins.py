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
at up to three sizes (``large_keypoints``); a picture whose pairs were not
all laid over for want of time or downloads is tried again next round
(``Item.twins_large``). The other way round, a large photograph with a
work whole inside it and much around (its frame, the museum's wall) is a
photograph of the work (``Item.scene_of``), left out like a detail.

One scan under two makers' names ("Johannes Vermeer van Delft", a
misattribution) never meets in one artist's works: each picture's hash
(``picture_hash``) is laid against every other's, and two that close whose
thumbnails lie over each other whole are copies; two museums' own works
never become one, not even through a third picture.

What the pictures cannot settle is kept for the judge (``suspects``): two
pictures that lie over each other without a rule for how (not one picture
whole, a part of a work not surely whole, a frame), and two hashes that
close whose pictures do not lie over each other whole (one scan in two
colours, a print after a painting). A model judges them at night
(``ai.twins_judge.NightJudge``), and :meth:`Twins.apply` writes what it
found.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from functools import lru_cache
from itertools import pairwise
from typing import TYPE_CHECKING, Any

import numpy as np

from ..imaging.layout import load_image
from .artists import known_names
from .duplicates import STOPWORDS, surname
from .images import Gone, display_copy
from .likeness import (
    FEATURES,
    SAME,
    WHOLE_COVER,
    WHOLE_MATCHES,
    WHOLE_TURN,
    Keypoints,
    cover,
    inside,
    keypoints,
    mapping,
    turn,
)
from .models import COLLECTIONS, Item, ItemKind
from .phrases import fold
from .picture_hash import NONE as NO_HASH
from .picture_hash import distances as hash_distances
from .picture_hash import picture_hash
from .picture_hash import words as hash_words
from .vocabulary import is_copy

if TYPE_CHECKING:
    from pathlib import Path

    from PIL import Image

    from .images import ImageCache
    from .repo import Library

log = logging.getLogger(__name__)

#: Bump when the look changes, so every picture is looked at again (3: the
#: pairs the pictures cannot settle are kept for the judge).
VERSION = 3
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
#: A search's artists are looked at for this long at most (seconds), ...
SEARCH_BUDGET = 120.0
#: ... once the app has had this long to fetch the thumbnails of what it
#: found (seconds; a picture without one is looked at another time).
SEARCH_DELAY = 20.0
#: Thumbnails a round fetches itself for new pictures without one.
THUMBS_A_ROUND = 200
#: At night: this long at most (seconds), a quiet moment between artists.
NIGHT_BUDGET = 2400.0
#: The rank of a work nobody cares about (``cared``).
REST = 2
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
#: artists at night (those the frame has shown are here already), or for
#: a search's. A picture whose pairs were not all laid over for want of
#: these or of time is tried again next round (``Item.twins_large``).
LARGE_DOWNLOADS = 120
SEARCH_DOWNLOADS = 40
#: Bump when the look in large pictures changes.
LARGE_VERSION = 1
#: Two pictures' hashes (``picture_hash``) this close (bits of 256) are
#: laid over each other whoever the sources say made them: one scan is
#: 6-37 apart, other works 107 and more (Vermeer, 2026-11-10), ...
HASH_NEAR = 48
#: ... that many pairs a round at most.
HASH_PAIRS = 2000
#: A work's picture smaller than this (long side) says no more than its
#: thumbnail.
LARGE_MIN = 1600
#: The pairs the pictures cannot settle, for the judge (library state):
#: ``"<a>|<b>"`` (ids in order, :func:`pair_key`) -> ``{"why": "fit" |
#: "hash", "at": iso}``, the newest :data:`SUSPECTS_MAX`.
SUSPECTS_KEY = "twins_suspects"
SUSPECTS_MAX = 3000
#: What the judge may write (:meth:`Twins.apply`).
APPLIED = ("same", "b_detail_of_a", "b_photo_of_a", "a_detail_of_b", "a_photo_of_b")
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


#: A maker's town after their name ("Johannes Vermeer van Delft"), and
#: what museums add in brackets ("(Dutch, Delft 1632–1675 Delft)").
_TOWN = re.compile(r"\s+(?:van|von|de|da|di|del|of)\s+[A-Z][\w'-]+\s*$")
_BRACKETS = re.compile(r"\s*[(\[].*?[)\]]\s*")


def artist_key(artist: str) -> str:
    """Who made it, so that only one artist's works are laid over each
    other: their person in the catalogue, else their surname; "" for nobody.

    A name with a town after it is the person without the town, when the
    catalogue knows no one by the whole of it: "Johannes Vermeer van Delft"
    (Europeana's "Die Malkunst") was "Delft", apart from every other
    Vermeer (Mateusz 2026-11-10); so is one with the museum's remarks in
    brackets ("Johannes Vermeer (Dutch, Delft 1632–1675 Delft)"). One word
    left is no name ("Rembrandt van Rijn" stays whole)."""
    first = _AFTER.sub("", artist).strip()
    if first and surname(first):
        artist = first
    known = known_names()
    person = known.person(artist)
    bare = _BRACKETS.sub(" ", artist.split("\n")[0]).strip()
    short = _TOWN.sub("", bare).strip()
    if short == bare or len(short.split()) < 2:
        short = bare
    # The whole name's own person, unless Wikidata says who the name
    # without its brackets or town is.
    if person is None or person not in known.items:
        for name in dict.fromkeys((bare, short)):
            other = known.person(name)
            if other is not None and (person is None or other in known.items):
                return f"person:{other}"
    if person is not None:
        return f"person:{person}"
    name = surname(short)
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
    second is a part of the first); ``inside`` whether the smaller one's
    frame lies within the larger picture."""

    __slots__ = ("area", "cover", "inside", "matches", "turn")

    def __init__(
        self, matches: int, area: float, cover: float, turn: float, inside: bool = False
    ) -> None:
        self.matches = matches
        self.area = area
        self.cover = cover
        self.turn = turn
        self.inside = inside

    @property
    def whole(self) -> bool:
        return 1 / WHOLE <= self.area <= WHOLE

    @property
    def same(self) -> bool:
        """One picture in place of the other: many matches, the frames
        covering each other, hardly turned (``likeness.Likeness.whole``)."""
        return (
            self.matches >= WHOLE_MATCHES
            and self.whole
            and self.cover >= WHOLE_COVER
            and self.turn <= WHOLE_TURN
        )


class _Round:
    """What one look may still spend: large pictures to download and
    thumbnails to fetch."""

    def __init__(self, downloads: int, thumbs: int) -> None:
        self.downloads = downloads
        self.thumbs = thumbs
        #: Pictures no source has a thumbnail of: nothing to look at.
        self.gone: set[str] = set()


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
        #: Seconds a search's look waits for the app to fetch its thumbnails.
        self.search_delay = SEARCH_DELAY
        self._round = _Round(0, 0)
        #: The works cared about, by id: 0 kept, 1 shown (``cared.Cared``);
        #: the night looks at them first (Mateusz 2026-11-11).
        self.cared: Callable[[], Mapping[str, int]] = dict

    # -- when ------------------------------------------------------------------

    def after_search(self, items: Iterable[Item]) -> None:
        """The artists of a search's works looked at in the background, those
        with pictures not looked at yet."""
        keys = {
            key
            for i in items
            if (i.twins_seen < VERSION or i.twins_large < LARGE_VERSION or not i.picture_hash)
            and candidate(i)
            and (key := artist_key(i.artist))
        }
        with self._asked_lock:
            keys -= self._asked
            if not keys:
                return
            self._asked |= keys
        threading.Thread(target=self._search_round, args=(keys,), name="twins", daemon=True).start()

    def _search_round(self, keys: set[str]) -> None:
        try:
            if self.search_delay > 0:
                time.sleep(self.search_delay)
            self.look(keys, budget=SEARCH_BUDGET, downloads=SEARCH_DOWNLOADS)
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
        downloads: int = LARGE_DOWNLOADS,
    ) -> int:
        """Looks at the pictures not looked at yet of the artists ``keys``
        (None: all, the fewest new pictures first) for ``budget`` seconds;
        returns how many pictures were looked at."""
        with self._lock:
            started = self.clock()
            self._round = _Round(downloads, THUMBS_A_ROUND)
            # The night's round: Favourites, playlists and Discover first.
            cared: Mapping[str, int] = self.cared() if keys is None else {}
            everyone, by_artist = self._candidates(keys)
            # Hashes first, a quarter of the time at most: across artists.
            mine = None if keys is None else {i.id for w in by_artist.values() for i in w}
            hashed, joined = self._hashes(everyone, mine, started + budget / 4, quiet, cared)
            if joined:  # copies named anew: the works as they are now
                everyone, by_artist = self._candidates(keys)
            due = [
                (key, works)
                for key, works in by_artist.items()
                if len(works) <= MAX_WORKS and any(_due(i) for i in works)
            ]
            due.sort(
                key=lambda kw: (
                    min((cared.get(i.id, REST) for i in kw[1] if _due(i)), default=REST),
                    sum(i.twins_seen < VERSION for i in kw[1]),
                    kw[0],
                )
            )
            seen = copies = details = 0
            for _key, works in due:
                if self.clock() - started > budget or not quiet():
                    break
                done = self._artist(works, started + budget)
                seen += done[0]
                copies += done[1]
                details += done[2]
            copies += joined
            if seen or joined:
                log.info(
                    "twins: %d pictures of %d artists looked at in %.0f s: %d copies, "
                    "%d details or framed photographs; %d hashed",
                    seen,
                    len(due),
                    self.clock() - started,
                    copies,
                    details,
                    hashed,
                )
            return seen

    def _candidates(self, keys: set[str] | None) -> tuple[list[Item], dict[str, list[Item]]]:
        """Every picture that may be a copy, and those of the artists
        ``keys`` (None: all) by artist."""
        by_artist: dict[str, list[Item]] = defaultdict(list)
        everyone: list[Item] = []
        for item in self.library.query(include_excluded=True)[1]:
            if not candidate(item):
                continue
            everyone.append(item)
            key = artist_key(item.artist)
            if key and (keys is None or key in keys):
                by_artist[key].append(item)
        return everyone, by_artist

    def _thumb(self, item: Item) -> Path | None:
        """``item``'s thumbnail, fetched while the round may (a search's
        works are looked at before the app has asked for all of theirs);
        None when it is not here (yet)."""
        path = self.images.thumb_path(item)
        if path.is_file():
            return path
        if self._round.thumbs <= 0:
            return None
        self._round.thumbs -= 1
        try:
            return self.images.ensure_thumb(item)
        except Gone:
            self._round.gone.add(item.id)
            return None
        except Exception as err:  # resting, refused: not now
            log.info("twins: thumbnail of %s: %s", item.id, err)
            return None

    def _artist(self, works: list[Item], until: float) -> tuple[int, int, int]:
        """One artist's new pictures laid over all their works'; how many
        were looked at, how many copies and details were found."""
        new = [i for i in works if i.twins_seen < VERSION]
        grouped = self.library.works()
        points: dict[str, Keypoints | None] = {}
        #: Pictures whose thumbnail is not here: looked at another time.
        missing: set[str] = set()

        def of(item: Item) -> Keypoints | None:
            if item.id not in points:
                path = self.images.thumb_path(item)
                if not path.is_file() and item in new:
                    path = self._thumb(item) or path
                if not path.is_file():
                    missing.add(item.id)
                    points[item.id] = None
                    return None
                try:
                    points[item.id] = keypoints(path)
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
            if item.id in missing:
                if item.id in self._round.gone:
                    looked.append(item)  # nothing to look at, ever
                continue  # its own thumbnail not here: not looked at yet
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
        large, scenes, large_done = self._large_details(works, looked, fits, grouped, until, of)
        copies, details = self._write(works, looked, fits, large, scenes, large_done)
        return len(looked), copies, details

    def _large_details(
        self,
        works: list[Item],
        looked: list[Item],
        fits: dict[tuple[str, str], Fit],
        grouped: Any,
        until: float,
        of: Callable[[Item], Keypoints | None],
    ) -> tuple[dict[str, str], dict[str, str], set[str]]:
        """Details too small for the thumbnails: the pictures that lie over
        nothing, laid over the large pictures of the artist's surely whole
        works whose titles share a word with theirs; and the other way
        round, those works' thumbnails over a large photograph (the painting
        on the museum's wall). Returns detail -> work, photograph -> work,
        and the pictures done with (none of their pairs left for lack of a
        download or of time: those are tried again next time)."""
        looked_ids = {i.id for i in looked}
        paired = {i for pair in fits for i in pair}
        sure = {i.id for i in works if _surely_whole(i)}
        sure.update(i for (a, b), fit in fits.items() if fit.whole for i in (a, b))
        roots = {i.copy_of for i in works if i.copy_of}
        waiting = [
            i
            for i in works
            if i.twins_large < LARGE_VERSION and (i.twins_seen >= VERSION or i.id in looked_ids)
        ]
        done = {
            i.id
            for i in waiting
            if i.id in paired
            or i.source in COLLECTIONS
            or i.copy_of
            or i.id in roots
            or i.id in sure
            or not title_words(i.title)
        }
        if not sure:
            return {}, {}, {i.id for i in waiting}
        words: dict[int | str, frozenset[str]] = {}

        def work_words(item: Item) -> frozenset[str]:
            at = grouped.group_index(item.id)
            key: int | str = item.id if at is None else at
            if key not in words:
                copies = [item] if at is None else grouped.groups[at]
                words[key] = frozenset().union(*(title_words(c.title) for c in copies))
            return words[key]

        pairs: list[tuple[int, Item, Item]] = []
        for small in waiting:
            if small.id in done:
                continue
            mine = title_words(small.title)
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
        large: dict[str, list[Keypoints]] = {}
        later: set[str] = set()  # a pair of theirs not laid over: next time

        def sets_of(item: Item) -> list[Keypoints] | None:
            """The item's large picture's keypoints (none when it can't be
            had); None when it can't be downloaded in this round."""
            if item.id not in large:
                img, downloaded, refused = self._large_picture(item, self._round.downloads > 0)
                self._round.downloads -= downloaded
                if refused:
                    return None
                large[item.id] = large_keypoints(img) if img is not None else []
            return large[item.id]

        found: dict[str, str] = {}
        scenes: dict[str, str] = {}
        for at, (_shared, small, big) in enumerate(pairs):
            if small.id in found or small.id in scenes:
                continue
            if at >= LARGE_PAIRS or self.clock() > until:
                later.add(small.id)
                continue
            mine_points = of(small)
            if mine_points is None:
                continue
            sets = sets_of(big)
            if sets is None:
                later.add(small.id)
                continue
            if any(lies_within(mine_points, s) for s in sets):
                log.info("twins: %s is a detail of %s (large picture)", small.id, big.id)
                found[small.id] = big.id
                continue
            # The work on a large photograph of its room or frame.
            if max(small.width or 0, small.height or 0) < LARGE_MIN:
                continue
            theirs = of(big)
            if theirs is None:
                continue
            around = sets_of(small)
            if around is None:
                later.add(small.id)
                continue
            if any(lies_within(theirs, s) for s in around):
                log.info("twins: %s is a photograph of %s (large picture)", small.id, big.id)
                scenes[small.id] = big.id
        done.update(i.id for i in waiting if i.id not in later)
        return found, scenes, done

    def _large_picture(
        self, item: Item, may_download: bool
    ) -> tuple[Image.Image | None, int, bool]:
        """``item``'s picture as the frame has it, else downloaded when
        ``may_download``; whether it was, and whether it was not for lack
        of ``may_download`` (then it is wanted another time)."""
        path = self.images.image_path(item)
        try:
            if path.is_file():
                return load_image(path), 0, False
            if not may_download:
                return None, 0, True
            return self.images.sample(display_copy(item)), 1, False
        except Exception as err:  # gone, refused, broken: no opinion
            log.info("twins: large picture of %s: %s", item.id, err)
            return None, int(may_download), False

    def _write(
        self,
        works: list[Item],
        looked: list[Item],
        fits: dict[tuple[str, str], Fit],
        large: dict[str, str] | None = None,
        large_scenes: dict[str, str] | None = None,
        large_done: set[str] | None = None,
    ) -> tuple[int, int]:
        by_id = {i.id: i for i in works}
        whole_twin: set[str] = set()
        for (a, b), fit in fits.items():
            if fit.whole:
                whole_twin.update((a, b))

        def sure(item_id: str) -> bool:
            item = by_id[item_id]
            return item.source in COLLECTIONS or item_id in whole_twin or bool(item.copy_of)

        # Details: the smaller of two, when the larger is surely whole; and
        # photographs of a work with its frame or wall around it: the larger
        # of two, when the smaller is surely the whole work and lies within
        # it, too far from covering it for a copy with a margin.
        detail_of: dict[str, str] = {}
        scene_of: dict[str, str] = {}
        for (a, b), fit in fits.items():
            if fit.whole:
                continue
            big, small = (a, b) if fit.area > 1 else (b, a)
            area = fit.area if fit.area > 1 else 1 / fit.area
            if area < DETAIL:
                continue
            if sure(big) and by_id[small].source not in COLLECTIONS:
                detail_of.setdefault(small, big)
            elif (
                sure(small)
                and by_id[big].source not in COLLECTIONS
                and fit.inside
                and fit.cover < COPY_COVER
            ):
                scene_of.setdefault(big, small)
        for small, big in (large or {}).items():
            detail_of.setdefault(small, big)
        for photo, work in (large_scenes or {}).items():
            scene_of.setdefault(photo, work)
        for photo in scene_of:
            detail_of.pop(photo, None)
        apart = set(detail_of) | set(scene_of)
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
            if a in apart or b in apart:
                continue
            if fit.cover >= COPY_COVER and fit.turn <= COPY_TURN:
                join(f"copy:{a}", f"copy:{b}")
                found += 1
        # What the pictures matched without a rule for how: for the judge.
        self._suspect(
            [
                (a, b)
                for (a, b) in fits
                if a not in apart
                and b not in apart
                and find(f"copy:{a}") != find(f"copy:{b}")
                and not (by_id[a].source in COLLECTIONS and by_id[b].source in COLLECTIONS)
            ],
            "fit",
        )
        members: dict[str, list[Item]] = defaultdict(list)
        for item in works:
            if item.id not in apart:
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
        for photo, work in scene_of.items():
            changes.setdefault(photo, {})["scene_of"] = work
        for item in looked:
            changes.setdefault(item.id, {})["twins_seen"] = VERSION
        for item_id in large_done or ():
            changes.setdefault(item_id, {})["twins_large"] = LARGE_VERSION
        with self.library.batch():
            for item_id, fields in changes.items():
                self.library.update(item_id, **fields)
        return found, len(detail_of) + len(scene_of)

    # -- across artists ----------------------------------------------------------

    def _hashes(
        self,
        everyone: list[Item],
        mine: set[str] | None,
        until: float,
        quiet: Callable[[], bool],
        cared: Mapping[str, int] | None = None,
    ) -> tuple[int, int]:
        """Each picture's hash worked out once (those of ``mine``, None:
        all), and laid against every other hash: two pictures this close
        whose thumbnails lie over each other as one are copies of one work,
        whoever the sources say made them. How many were hashed and how
        many copies found."""
        fresh: list[Item] = []
        hashes: dict[str, str] = {}
        for item in everyone:
            if item.picture_hash and item.picture_hash != NO_HASH:
                hashes[item.id] = item.picture_hash
            elif not item.picture_hash and (mine is None or item.id in mine):
                fresh.append(item)
        cared = cared or {}
        if cared:  # the works cared about hashed first, and their pairs
            fresh.sort(key=lambda i: cared.get(i.id, REST))
        written: dict[str, str] = {}
        for item in fresh:
            if self.clock() > until or not quiet():
                break
            path = self.images.thumb_path(item)
            if not path.is_file():
                continue  # hashed once it is here
            written[item.id] = picture_hash(path)
        if not written:
            return 0, 0
        by_id = {i.id: i for i in everyone}
        known = [i for i in hashes if i not in written]
        new = [i for i, h in written.items() if h != NO_HASH]
        order = known + new
        rows = hash_words([hashes.get(i) or written[i] for i in order])
        grouped = self.library.works()
        close: list[tuple[str, str]] = []
        for at in range(len(known), len(order)):
            near = np.flatnonzero(hash_distances(rows[at], rows[:at]) <= HASH_NEAR)
            a = order[at]
            for index in near:
                b = order[int(index)]
                ia, ib = by_id[a], by_id[b]
                if ia.source in COLLECTIONS and ib.source in COLLECTIONS:
                    continue  # two museums' own works
                g = grouped.group_index(a)
                if g is not None and g == grouped.group_index(b):
                    continue
                close.append((a, b))
        if cared:
            close.sort(key=lambda ab: min(cared.get(ab[0], REST), cared.get(ab[1], REST)))
        joined = 0
        unsure: list[tuple[str, str]] = []
        for a, b in close[:HASH_PAIRS]:
            ia, ib = by_id[a], by_id[b]
            pa, pb = self.images.thumb_path(ia), self.images.thumb_path(ib)
            if not (pa.is_file() and pb.is_file()):
                continue
            try:
                ka, kb = keypoints(pa), keypoints(pb)
            except Exception:  # a broken file: no opinion
                continue
            fit = _fit(ka, kb) if ka is not None and kb is not None else None
            if fit is None or not fit.same:
                unsure.append((a, b))  # that close, yet not one picture whole
                continue
            family = {i.id: i for i in self._copies(ia, grouped) + self._copies(ib, grouped)}
            museums = [i for i in family.values() if i.source in COLLECTIONS]
            if len(museums) > 1:
                continue  # two museums' own works are never one
            log.info("twins: %s and %s are one picture (hash)", a, b)
            found, _ = self._write(list(family.values()), [], {(a, b): fit})
            joined += found
            grouped = self.library.works()
        self._suspect(unsure, "hash")
        with self.library.batch():
            for item_id, value in written.items():
                self.library.update(item_id, picture_hash=value)
        return len(written), joined

    # -- the judge's pairs -------------------------------------------------------

    def _suspect(self, pairs: list[tuple[str, str]], why: str) -> None:
        """``pairs`` kept for the judge (the newest :data:`SUSPECTS_MAX`)."""
        if not pairs:
            return
        kept = self.suspects()
        at = datetime.now(UTC).isoformat(timespec="seconds")
        for a, b in pairs:
            key = pair_key(a, b)
            kept.pop(key, None)  # anew: the newest last
            kept[key] = {"why": why, "at": at}
        if len(kept) > SUSPECTS_MAX:
            kept = dict(list(kept.items())[-SUSPECTS_MAX:])
        self.library.set_state(SUSPECTS_KEY, kept)
        log.info("twins: %d pairs left to the judge (%s)", len(pairs), why)

    def suspects(self) -> dict[str, dict[str, Any]]:
        """The pairs the pictures could not settle, the oldest first."""
        return dict(self.library.get_state(SUSPECTS_KEY, {}) or {})

    def drop_suspects(self, keys: Iterable[str]) -> None:
        """Judged (or gone): not asked about again."""
        with self._lock:
            kept = self.suspects()
            for key in keys:
                kept.pop(key, None)
            self.library.set_state(SUSPECTS_KEY, kept)

    def apply(self, a_id: str, b_id: str, relation: str) -> bool:
        """What the judge found about ``a`` and ``b`` written as the pictures
        would have (one of :data:`APPLIED`): copies of one work, or one a part
        or a photograph of the other. A museum's own work is never set aside,
        and two museums' works never become one. Whether it was written."""
        if relation not in APPLIED:
            return False
        if relation.startswith("a_"):  # "a_detail_of_b": b is the whole
            a_id, b_id = b_id, a_id
            relation = "b_" + relation[2:-1] + "a"
        with self._lock:
            a, b = self.library.get(a_id), self.library.get(b_id)
            if a is None or b is None:
                return False
            if relation == "same":
                grouped = self.library.works()
                family = {i.id: i for i in self._copies(a, grouped) + self._copies(b, grouped)}
                if sum(i.source in COLLECTIONS for i in family.values()) > 1:
                    return False  # two museums' own works are never one
                one = Fit(WHOLE_MATCHES, 1.0, 1.0, 0.0)
                self._write(list(family.values()), [], {(a.id, b.id): one})
                return True
            if b.source in COLLECTIONS:
                return False  # a museum's own work is no detail or photograph
            field = "detail_of" if relation == "b_detail_of_a" else "scene_of"
            self.library.update(b.id, **{field: a.copy_of or a.id})
            return True

    def _copies(self, item: Item, grouped: Any) -> list[Item]:
        """``item`` and the copies of its work its pictures were found to be
        (``Item.copy_of``), as the library has them now."""
        item = self.library.get(item.id) or item
        root = item.copy_of or item.id
        at = grouped.group_index(item.id)
        found = {item.id: item}
        for other in [] if at is None else grouped.groups[at]:
            other = self.library.get(other.id) or other
            if (other.copy_of or other.id) == root:
                found[other.id] = other
        return list(found.values())


def pair_key(a: str, b: str) -> str:
    """A pair as the judge's lists keep it: the ids in order."""
    return f"{a}|{b}" if a <= b else f"{b}|{a}"


def _due(item: Item) -> bool:
    """Still to be looked at: its thumbnail or the large pictures."""
    return item.twins_seen < VERSION or item.twins_large < LARGE_VERSION


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


def _laid_within(size: tuple[int, int], found: Any, large: tuple[int, int]) -> bool:
    """A frame of ``size`` laid by ``found`` lies within ``large``'s, by
    :data:`EDGE` of its sides."""
    width, height = size
    corners = np.array([[0, 0, 1], [width, 0, 1], [width, height, 1], [0, height, 1]], float)
    laid = corners @ np.asarray(found, float).T
    lw, lh = large
    return bool(
        laid[:, 0].min() >= -EDGE * lw
        and laid[:, 1].min() >= -EDGE * lh
        and laid[:, 0].max() <= (1 + EDGE) * lw
        and laid[:, 1].max() <= (1 + EDGE) * lh
    )


def lies_within(small: Keypoints, large: Keypoints) -> bool:
    """``small`` is a part of ``large``: one mapping lays many of its
    keypoints over the large picture's, unturned, its frame within the
    large picture's and at most 1/:data:`DETAIL` of it."""
    count, found = mapping(small, large)
    if count < SAME or found is None or turn(found) > COPY_TURN:
        return False
    if inside(small, large, found) > 1 / DETAIL:
        return False
    return _laid_within(small.size, found, large.size)


def _fit(a: Keypoints, b: Keypoints) -> Fit | None:
    """How ``a`` lies over ``b``; None when they are not one picture."""
    count, found = mapping(a, b)
    if count < SAME or found is None:
        return None
    area = inside(a, b, found)
    if not math.isfinite(area) or area <= 0:
        return None
    if area < 1:
        within = _laid_within(a.size, found, b.size)
    else:
        import cv2

        back = cv2.invertAffineTransform(np.asarray(found, float))
        within = _laid_within(b.size, back, a.size)
    return Fit(count, area, cover(a, b, found), turn(found), within)
