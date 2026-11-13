"""Sharper copies of works whose own picture is poor.

A museum may give a small picture (the Art Institute of Chicago's 1686 px),
a heavily squeezed file, or none the server can download. When the owner
opens such a work's card, or it becomes the work of the day, other sources
are asked for the same picture: the work's file on Wikimedia Commons (its
P18 on Wikidata), the catalogue's other copies of it, and a search of every
source by its title and artist. A copy stands in for the work's own picture
only when it is the same picture whole (many keypoints laid one over the
other, not a detail, not a page or a slide around it, not turned), in its
colours (no black-and-white plate of a painting, no colourised print), not
a reproduction by its own description, and clearly larger or less
squeezed. The work keeps its texts and its id; only its picture changes
(``Item.sharper``), for the card, the frame and the study's details.

When the work's own source gives no picture at all as its card opens (the
National Museum in Kraków's image server cutting every original short,
Mateusz 2026-11-08), a copy stands in for it: Wikimedia Commons first (the
work's own file by its Wikidata record, then a search of Commons), and the
first copy that is the same picture takes its place at once; only when
Commons has none are the other sources asked. Such a copy is marked a
stand-in (``SharperCopy.stand_in``) and stays: the museum is not asked for
its own picture again (Mateusz, 2026-11-08: the picture is on the server's
disk already; "Przywróć zdjęcie muzeum" brings the own back by hand).

A work whose picture is an art history archive's photograph of it
(Europeana's Foto Marburg: colour slides decades old, their dyes faded to
blue and white, Mateusz 2026-11-09) takes any other copy of the same picture
whole as large as its own, in other colours too: the museums' scans have the
painting's colours, the slide has lost them. Such a photograph is never a
copy itself (Mateusz 2026-11-09: two van Goghs from Foto Marburg took
another Marburg slide, as faded, before Commons was asked). Of the copies
that pass, the largest is taken, and one still too small for the frame is
looked past again after :data:`WEAK_AGAIN`.

A work Commons keeps in a tile set (``{{Tile set available}}``: Bosch's
"Garden of Earthly Delights", Rembrandt's "Night Watch"; some 70 files)
takes that file in its place even when its own picture is good: the
full-screen viewer then goes far closer in on its tiles (Mateusz
2026-11-09). Found by the work's Wikidata item when it is looked at, and
once for the catalogue's works after the update (:meth:`Sharper.tiled_once`).
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from collections.abc import Callable, Iterator
from concurrent.futures import Future
from concurrent.futures import TimeoutError as Late
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal, NamedTuple

import httpx
import numpy as np
from PIL import Image

from .imaging.color import linear_to_oklab, u8_to_linear
from .imaging.layout import load_image
from .library import Item, ItemKind
from .library.colors import tint_spread
from .library.duplicates import same_work, surname
from .library.images import (
    BYTES,
    OWNED,
    OWNED_SOURCE,
    WEAK_SIDE,
    display_copy,
    kept_long,
    own_copy,
)
from .library.likeness import Likeness
from .library.models import Note, SharperCopy
from .library.verdict import Place, against
from .library.vocabulary import (
    archive_own,
    artist_matches,
    is_art_archive_photo,
    is_grey_copy,
    is_photograph,
)

if TYPE_CHECKING:
    from .library import Importer, Library
    from .library.images import ImageCache

log = logging.getLogger(__name__)

KIND = "sharper"
#: 2: works found fine are looked at again, for a copy in a tile set.
VERSION = "sharper-2"
#: The version of the look at an art archive's photograph: those looked at
#: before they took copies in other colours are looked at again.
ARCHIVE_VERSION = "sharper-archive-1"

#: A picture shorter than ``images.WEAK_SIDE`` is worth a sharper copy, and
#: so is one squeezed below this many bits per pixel (a painting's
#: JPEG at a fair quality takes 1.5 to 4).
WEAK_BITS = 0.6
#: A copy stands in only when its long side (up to the frame's) is this
#: many times the work's own, ...
GAIN = 1.25
#: ... or, as large, when the work's own is squeezed and the copy takes at
#: least this many times its bits per pixel.
LESS_SQUEEZED = 2.0
#: A copy smaller than this is no gain over the work's thumbnail.
LEAST_SIDE = 1000
#: A copy squeezed below this many bits per pixel is mush, however large
#: (even flat paintings take more at a fair quality).
MUSH = 0.2
#: A copy's colours: no greyer than this share of the work's own tint
#: spread (a black-and-white plate of a painting) ...
GREYER = 0.5
#: ... nor coloured where the work has none (a colourised print) ...
GREY = 0.012
#: ... nor this many times as colourful (tint spread): the average colour
#: misses a faded slide, its white sky and red ground averaging out close to
#: the painting's yellow sky and violet ground (Foto Marburg's olive grove
#: against WikiArt's: 0.056 apart, spread 0.020 against 0.077; its yellow
#: house, schoolboy and postman 2.7 to 3.3 times; two good photographs of
#: one painting 1.1, Mateusz 2026-11-09) ...
LIVELIER = 2.0
#: ... nor far off in its average colour (OKLab distance; photographs of
#: one painting under other lights differ by a few hundredths).
COLOUR_OFF = 0.08
#: Results asked from each source.
HITS = 6
#: Copies whose thumbnails are compared, and whose pictures are downloaded.
COMPARED = 10
DOWNLOADED = 3
#: A work with no sharper copy anywhere is asked about again after this.
AGAIN = timedelta(days=30)
#: A work whose copy is still weak (smaller than the frame wants) is
#: looked at again after this.
WEAK_AGAIN = timedelta(days=1)
#: Looked for at once.
THREADS = 2
#: How long the work of the day waits for its look.
DAILY_WAIT = 300.0
#: Works whose last look is kept in memory (also those not in the library).
REMEMBERED = 2000
#: A work whose own source gave no picture is looked at for a stand-in
#: again after this (the source may be back; Commons may have it since).
STAND_IN_AGAIN = timedelta(hours=6)
#: Thumbnails made again from the copies in the works' place, once
#: (:meth:`Sharper.thumbs_again`).
THUMBS_KEY = "copy_thumbs"
THUMBS_VERSION = 1
#: The works shown in an art archive's faded slide looked at once after the
#: update, not night by night (Mateusz 2026-11-09: "odpal już podmiany",
#: :meth:`Sharper.archives_once`).
ARCHIVES_KEY = "archive_copies"
#: 2: works shown in an archive's photograph taken as a copy are looked at
#: again, without it.
ARCHIVES_VERSION = 2
#: Where an art archive's photographs are, for a copy no longer in the
#: library (Foto Marburg's Bildindex, KIK-IRPA's BALaT).
ARCHIVE_HOSTS = ("bildindex.de", "fotomarburg.de", "kikirpa.be")
#: One look at such a work takes this long at most (seconds).
ARCHIVE_WAIT = 600.0
#: The catalogue's works of Commons' tile sets taken once after the update.
TILES_KEY = "tiled_copies"
TILES_VERSION = 1
#: A copy in a tile set takes the place of a picture this many times as
#: large (kept, as the frame's server keeps it), not much smaller.
TILED_SIDE = 0.9

Status = Literal["looking", "found", "none", "fine", "off"]


class Quality(NamedTuple):
    """A picture as its source gives it: the long side in pixels (0: no
    picture but the thumbnail), bits per pixel of its file (None when not
    known) and how many times longer than wide it is (1.0 when not known)."""

    side: int
    bits: float | None = None
    ratio: float = 1.0

    @classmethod
    def of(cls, width: int, height: int, size: int) -> Quality:
        pixels = width * height
        bits = size * 8 / pixels if size and pixels else None
        return cls.sized(width, height, bits)

    @classmethod
    def sized(cls, width: int, height: int, bits: float | None = None) -> Quality:
        long, short = max(width, height), min(width, height)
        return cls(long, bits, long / short if short > 0 else 1.0)

    def kept(self, ratio: float | None = None) -> int:
        """The long side the frame's server keeps of it
        (:func:`~frame_server.library.images.kept_size`): an elongated
        picture keeps more than IMAGE_MAX. ``ratio``: the work's, when
        this one does not know it."""
        return kept_long(self.side, max(self.ratio, ratio or 1.0))

    @classmethod
    def of_image(cls, img: Image.Image) -> Quality:
        return cls.of(*img.size, int(img.info.get(BYTES) or 0))

    @property
    def weak(self) -> bool:
        return self.side < WEAK_SIDE or (self.bits is not None and self.bits < WEAK_BITS)

    def better(self, own: Quality, faded: bool = False) -> bool:
        """This picture shows the work clearly better than ``own`` does.
        ``faded``: ``own`` is an art archive's old photograph
        (:func:`archive_own`), which any copy about as large beats."""
        if self.bits is not None and self.bits < MUSH:
            return False
        ratio = max(self.ratio, own.ratio)  # copies of one work: the same shape
        side, own_side = self.kept(ratio), own.kept(ratio)
        if side < LEAST_SIDE:
            return False
        if side >= own_side * GAIN:
            return True
        if faded and side >= own_side * 0.95:
            return True
        return (
            side >= own_side * 0.95
            and own.bits is not None
            and own.bits < WEAK_BITS
            and self.bits is not None
            and self.bits >= own.bits * LESS_SQUEEZED
        )


class Tone(NamedTuple):
    spread: float
    mean: tuple[float, float, float]  # OKLab


def tone(path: Path) -> Tone:
    with Image.open(path) as img:
        spread = tint_spread(img)
        small = load_image(img).copy()
    small.thumbnail((64, 64))
    lab = linear_to_oklab(u8_to_linear(np.asarray(small)).reshape(-1, 3)).mean(axis=0)
    return Tone(spread, (float(lab[0]), float(lab[1]), float(lab[2])))


ColourNote = Literal["grey", "coloured", "colour-off"]


def colour_note(own: Tone, copy: Tone) -> ColourNote | None:
    """How ``copy``'s colours differ from ``own``'s: "grey" (a black-and-white
    plate of a coloured work), "coloured" (a grey work coloured in),
    "colour-off" (in other light altogether, or far more colourful: one of
    them faded); None when they are its own."""
    if own.spread >= GREY and copy.spread < own.spread * GREYER:
        return "grey"
    if own.spread < GREY and copy.spread >= max(GREY * 2, own.spread * 3):
        return "coloured"
    if copy.spread >= own.spread * LIVELIER:
        return "colour-off"
    distance = float(np.linalg.norm(np.subtract(own.mean, copy.mean)))
    return None if distance <= COLOUR_OFF else "colour-off"


def same_colours(own: Tone, copy: Tone, faded: bool = False) -> bool:
    """``copy`` is in ``own``'s colours: not a grey copy of a coloured work,
    nor a coloured one of a grey work, nor in other light altogether (but
    for ``faded``: ``own`` is an archive's old slide, whose colours are off
    themselves)."""
    note = colour_note(own, copy)
    return note is None or (faded and note == "colour-off")


def version(item: Item) -> str:
    """The version of the look at ``item``."""
    return ARCHIVE_VERSION if is_art_archive_photo(item) else VERSION


def _now() -> datetime:
    return datetime.now(UTC)


class Sharper:
    def __init__(
        self,
        library: Library,
        importer: Importer,
        images: ImageCache,
        commons_file: Callable[[Item], str] | None = None,
    ) -> None:
        self.library = library
        self.importer = importer
        self.images = images
        self.likeness = Likeness(images)
        #: The work's Commons file name (Wikidata's P18), "" when none.
        self.commons_file = commons_file
        #: Every source at once: ``Importer.search_all``.
        self.search: Callable[[str, int], tuple[int, list[Item], list[str]]] = lambda query, n: (
            importer.search_all(query, n)
        )
        #: Wikimedia Commons alone, asked first for a stand-in.
        self.search_commons: Callable[[str, int], list[Item]] = lambda query, n: (
            importer.search_all(query, n, keys=["wmc"])[1] if "wmc" in importer.sources() else []
        )
        #: The Commons files with a tile set that show a work (found by its
        #: Wikidata item, ``Copies.tiled_copies``), and whether a picture
        #: (by item id) is one; set by the service.
        self.tiled_copies: Callable[[Item], list[Item]] | None = None
        self.is_tiled: Callable[[str], bool] = lambda item_id: False
        #: Where a study's details are cut (cut again from a sharper copy).
        self.details_dir = images.thumbs.parent / "details"
        self.clock: Callable[[], datetime] = _now
        self._turns = threading.Semaphore(THREADS)
        self._lock = threading.Lock()
        self._looking: dict[str, Future[Status]] = {}
        #: The last look's end, by item id: what it found, and when.
        self._known: OrderedDict[str, tuple[Status, datetime]] = OrderedDict()
        #: When a stand-in was last looked for, by item id.
        self._stood: OrderedDict[str, datetime] = OrderedDict()

    # -- what is known ---------------------------------------------------------

    def status(self, item: Item) -> Status | None:
        """What is known without looking: "off" for what has no other copy
        (photos, own works), "found" for a work with a sharper copy, "fine"
        or "none" as last found out; None when it is to be looked into."""
        if item.kind != ItemKind.ARTWORK or item.look is not None:
            return "off"
        stored = self.library.get(item.id)
        copy = (stored or item).sharper
        if copy is not None:
            return "found" if not self.weak_copy(stored or item) else self._weak_status(item)
        with self._lock:
            known = self._known.get(item.id)
        if known is None:
            note = self.library.note(item.id, KIND)
            if note is None:
                return None
            if note.data.get("status") == "kept":
                # The owner's choice stands, but for a tile set: looked at
                # once more for one (``_look`` keeps the choice otherwise).
                return "fine" if note.prompt_version == version(item) else None
            if note.prompt_version != version(item):
                return None
            try:
                at = datetime.fromisoformat(str(note.data.get("at")))
            except ValueError:
                return None
            status = str(note.data.get("status"))
        else:
            status, at = known
        if status in ("fine", "kept"):  # "kept": the owner chose the work's own
            return "fine"
        if status == "none" and self.clock() - at < AGAIN:
            return "none"
        return None

    @staticmethod
    def weak_copy(item: Item) -> bool:
        """``item`` shows a copy the server found that is still smaller
        than the frame wants: the owner's pick and stand-ins stay as they
        are."""
        copy = item.sharper
        if copy is None or copy.chosen or copy.stand_in:
            return False
        return Quality.sized(copy.width, copy.height).weak

    def _weak_status(self, item: Item) -> Status | None:
        """ "found" while a weak copy was looked past lately, else None."""
        with self._lock:
            known = self._known.get(item.id)
        at: datetime | None
        if known is not None:
            at = known[1]
        else:
            note = self.library.note(item.id, KIND)
            try:
                at = datetime.fromisoformat(str(note.data.get("at"))) if note else None
            except ValueError:
                at = None
        if at is not None and self.clock() - at < WEAK_AGAIN:
            return "found"
        return None

    def soon(self, item: Item) -> Future[Status]:
        """Looks for a sharper copy in the background, unless it is known;
        the same look for every asker while it runs. A work known to be fine
        (or to have no sharper copy) whose original is not here is looked at
        still: when its source gives no picture now, a copy stands in."""
        known = self.status(item)
        if known is not None and not (known in ("fine", "none") and self._may_stand_in(item)):
            done: Future[Status] = Future()
            done.set_result(known)
            return done
        with self._lock:
            running = self._looking.get(item.id)
            if running is not None:
                return running
            future: Future[Status] = Future()
            self._looking[item.id] = future
        threading.Thread(
            target=self._look_then_done, args=(item, future, known), name="sharper", daemon=True
        ).start()
        return future

    def look(self, item: Item, wait: float = DAILY_WAIT) -> Status:
        """Looks for a sharper copy now (the work of the day, before its
        page is written); what was found, "looking" after ``wait`` seconds."""
        try:
            return self.soon(item).result(wait)
        except Late:
            return "looking"

    def _look_then_done(
        self, item: Item, future: Future[Status], known: Status | None = None
    ) -> None:
        status: Status = known or "none"
        try:
            with self._turns:
                status = self._look(item, known)
        except Exception:
            log.exception("sharper copy of %s", item.id)
        finally:
            with self._lock:
                self._looking.pop(item.id, None)
            future.set_result(status)

    # -- looking -----------------------------------------------------------------

    def _look(self, item: Item, known: Status | None = None) -> Status:
        """Looks for a sharper copy, or for a stand-in when the work's own
        source gives no picture now; ``known``: what an earlier look found
        (the own came: it stands)."""
        own, failing = self._own_now(item)
        if failing:
            return self._stand_in(item, own) if self._may_stand_in(item) else known or "none"
        if own is None:
            return "none"  # not even its thumbnail: the network, not the work
        if known is not None:
            return known
        faded = archive_own(item)
        if self._take_tiled(item, own):
            return "found"
        note = self.library.note(item.id, KIND)
        if note is not None and note.data.get("status") == "kept":
            stored = self.library.get(item.id) or item
            self._remember(item, "kept", "", self.own_size(stored))  # the owner's choice stands
            return "fine"
        if not own.weak and not faded:
            self._remember(item, "fine")
            return "fine"
        log.info("picture of %s is poor (%s); looking for a sharper copy", item.id, own)
        downloaded = 0
        # The largest of the copies that pass, not the first: a slightly
        # larger one from the catalogue must not shut out Commons' scan.
        best: tuple[int, Item, Image.Image] | None = None
        for copy in self.candidates(item)[:COMPARED]:
            if downloaded == DOWNLOADED:
                break
            if not self._promising(copy, own, faded) or not self.same_picture(item, copy):
                continue
            downloaded += 1
            try:
                img = self.images.sample(display_copy(copy))
            except (httpx.HTTPError, OSError) as err:
                log.info("sharper copy %s of %s: %s", copy.id, item.id, err)
                continue
            quality = Quality.of_image(img)
            if not quality.better(own, faded):
                log.info("copy %s of %s is no better (%s)", copy.id, item.id, quality)
                continue
            if best is None or quality.kept(own.ratio) > best[0]:
                best = (quality.kept(own.ratio), copy, img)
            if not quality.weak:
                break  # as large as the frame wants: no need to look further
        if best is not None:
            self._adopt(item, best[1], best[2])
            return "found"
        stored = self.library.get(item.id) or item
        if stored.sharper is not None:  # its weak copy stays, looked past again later
            self._remember(item, "found", stored.sharper.item_id, self.own_size(stored))
            return "found"
        self._remember(item, "none")
        return "none"

    def shows_tiles(self, item: Item) -> bool:
        """``item``'s picture shown now is a Commons file with a tile set."""
        shown = item.sharper.item_id if item.sharper is not None else item.id
        return self.is_tiled(shown)

    def _take_tiled(self, item: Item, own: Quality, copies: list[Item] | None = None) -> bool:
        """A Commons file in a tile set of ``item``'s work (``copies``, else
        found by its Wikidata item) in place of its picture, when it is the
        same picture whole in its colours and not much smaller; whether one
        was taken. Also over the owner's pick of the museum's picture or of
        another copy (Mateusz 2026-11-09: "ten w ultra-rozdzielczości będzie
        po prostu lepszy")."""
        stored = self.library.get(item.id) or item
        if self.shows_tiles(stored):
            return False
        if copies is None:
            if self.tiled_copies is None:
                return False
            try:
                copies = self.tiled_copies(stored)
            except Exception:
                log.exception("tile sets of %s", item.id)
                return False
        for copy in copies:
            if copy.id == item.id or not self._eligible(stored, copy):
                continue
            if not self.same_picture(stored, copy):
                log.info("tile set %s is not the picture of %s", copy.id, item.id)
                continue
            try:
                img = self.images.sample(display_copy(copy))
            except (httpx.HTTPError, OSError) as err:
                log.info("tile set %s of %s: %s", copy.id, item.id, err)
                continue
            quality = Quality.of_image(img)
            ratio = max(quality.ratio, own.ratio)
            if own.side and quality.kept(ratio) < own.kept(ratio) * TILED_SIDE:
                log.info("tile set %s of %s is too small (%s)", copy.id, item.id, quality)
                continue
            self._adopt(stored, copy, img)
            log.info("tile set %s in place of the picture of %s", copy.id, item.id)
            return True
        return False

    def tiled_once(self, files: Callable[[], list[Item]]) -> int:
        """Once after the update: the catalogue's works of Commons' tile
        sets (``files``: one copy per file) take them; how many did."""
        if self.library.get_state(TILES_KEY, 0) >= TILES_VERSION:
            return 0
        try:
            found = files()
        except Exception:
            log.exception("tile sets not listed")
            return 0
        works = self.library.works()
        taken = 0
        for copy in found:
            index = works.group_of(copy)
            if index is None:
                continue
            for work in list(works.groups[index]):
                if work.id == copy.id or work.kind != ItemKind.ARTWORK or work.part_of:
                    continue
                with self._turns:
                    own, failing = self._own_now(work)
                    if own is None or failing:
                        continue
                    taken += self._take_tiled(work, own, [copy])
        self.library.set_state(TILES_KEY, TILES_VERSION)
        log.info("tile sets: %d of the catalogue's works took one (%d files)", taken, len(found))
        return taken

    def _own_now(self, item: Item) -> tuple[Quality | None, bool]:
        """:meth:`own`, and whether the work's own source gave no original
        now (down, cut short, turning us away): then the quality is its
        thumbnail's (side 0), None when not even that came."""
        try:
            self.images.ensure_image(item)
        except (httpx.HTTPError, OSError) as err:
            log.info("original of %s: %s", item.id, err)
        else:
            size = self.images.source_size(item)
            return (Quality(0) if size is None else Quality.of(*size)), False
        try:
            self.images.ensure_thumb(item)
        except (httpx.HTTPError, OSError) as err:
            log.info("thumbnail of %s: %s", item.id, err)
            return None, True
        return Quality(0), True

    def own(self, item: Item) -> Quality | None:
        """The work's own picture: as its source gave it; side 0 when only its
        thumbnail can be had; None when not even that."""
        try:
            _, original = self.images.picture(item)
        except (httpx.HTTPError, OSError) as err:
            log.info("picture of %s: %s", item.id, err)
            return None
        size = self.images.source_size(item) if original else None
        return Quality(0) if size is None else Quality.of(*size)

    def candidates(self, item: Item, commons: bool = True) -> list[Item]:
        """Other copies of the work to compare, likeliest first: its Commons
        file (unless ``commons`` is False: asked already), the catalogue's
        copies, then what the sources find for its title and artist, the
        largest first."""
        found: list[Item] = []
        if commons and self.commons_file is not None and (name := self.commons_file(item)):
            try:
                if (copy := self.importer.commons_file(name)) is not None:
                    found.append(copy)
            except (httpx.HTTPError, ValueError) as err:
                log.info("Commons file of %s: %s", item.id, err)
        works = self.library.works()
        index = works.group_of(item)
        if index is not None:
            found += [i for i in works.groups[index] if i.id != item.id]
        if item.title.strip():
            query = f"{item.title[:80]} {surname(item.artist)}".strip()
            try:
                hits = self.search(query, HITS)[1]
            except (httpx.HTTPError, ValueError) as err:
                log.info("sources on %r: %s", query, err)
                hits = []
            hits = [h for h in hits if self._by_artist(item, h)]
            hits.sort(key=lambda h: -max(h.width or 0, h.height or 0))
            found += hits
        seen: set[str] = {item.id}
        out = []
        for copy in found:
            if copy.id in seen or not self._eligible(item, copy):
                continue
            seen.add(copy.id)
            out.append(copy)
        return out

    @staticmethod
    def _by_artist(item: Item, copy: Item) -> bool:
        if same_work(item, copy):
            return True
        if not item.artist or not copy.artist:
            return False
        return artist_matches(copy.artist, [item.artist]) or artist_matches(
            item.artist, [copy.artist]
        )

    @staticmethod
    def _eligible(item: Item, copy: Item) -> bool:
        """Nothing a reproduction by its own description, a photograph of
        a work that is none, a photo sent once, nor an art archive's
        photograph (faded slides, Mateusz 2026-11-09)."""
        return (
            copy.kind == ItemKind.ARTWORK
            and not is_art_archive_photo(copy)
            and copy.look is None
            and copy.sharper is None
            and not against(copy, Place.COMPARED)
            and (is_photograph(item) or not is_photograph(copy))
            and bool(display_copy(copy))
        )

    @staticmethod
    def _promising(copy: Item, own: Quality, faded: bool = False) -> bool:
        """Not smaller than needed by what its source says (when it says)."""
        side = max(copy.width or 0, copy.height or 0)
        return not side or Quality(side).better(Quality(own.side), faded)

    def same_picture(self, item: Item, copy: Item) -> bool:
        """``copy`` is ``item``'s picture whole and in its colours, by their
        thumbnails."""
        try:
            own_thumb = self.images.ensure_thumb(item)
            copy_thumb = self.images.ensure_thumb(copy)
        except (httpx.HTTPError, OSError) as err:
            log.info("thumbnails of %s and %s: %s", item.id, copy.id, err)
            return False
        if not self.likeness.whole(item, copy):
            return False
        try:
            return same_colours(tone(own_thumb), tone(copy_thumb), archive_own(item))
        except OSError:
            return False

    # -- standing in ---------------------------------------------------------------

    def _may_stand_in(self, item: Item) -> bool:
        """Whether ``item`` may want a stand-in: a museum work with no copy
        in its place, whose original is not here, not looked for lately."""
        if item.kind != ItemKind.ARTWORK or item.look is not None:
            return False
        if (self.library.get(item.id) or item).sharper is not None:
            return False
        if self.images.has_image(item):
            return False
        with self._lock:
            last = self._stood.get(item.id)
        return last is None or self.clock() - last >= STAND_IN_AGAIN

    def _stand_in(self, item: Item, own: Quality | None) -> Status:
        """A copy in place of the work's picture, which its source does not
        give now: the first that is the same picture, Commons first.
        ``own``: the thumbnail's quality (side 0) when it came, else None:
        then only a copy that is certainly this work will do (its own file
        by its record, or the same title, artist and shape)."""
        with self._lock:
            self._stood[item.id] = self.clock()
            self._stood.move_to_end(item.id)
            while len(self._stood) > REMEMBERED:
                self._stood.popitem(last=False)
        log.info("no picture of %s from its source; looking for a stand-in", item.id)
        least = own or Quality(0)
        seen: set[str] = {item.id}
        downloaded = 0
        for certain, copy in self._stand_ins(item):
            if downloaded == DOWNLOADED:
                break
            if copy.id in seen or copy.source == item.source or not self._eligible(item, copy):
                continue  # the own source's other copies come from where it fails
            seen.add(copy.id)
            if own is not None:
                if not self.same_picture(item, copy):
                    continue
            elif not (certain or same_work(item, copy)):
                continue
            downloaded += 1
            try:
                img = self.images.sample(display_copy(copy))
            except (httpx.HTTPError, OSError) as err:
                log.info("stand-in %s of %s: %s", copy.id, item.id, err)
                continue
            if not Quality.of_image(img).better(least):
                log.info("stand-in %s of %s is too small (%s)", copy.id, item.id, img.size)
                continue
            self._adopt(item, copy, img, stand_in=True)
            return "found"
        log.info("no stand-in for %s anywhere", item.id)
        return "none"

    def _stand_ins(self, item: Item) -> Iterator[tuple[bool, Item]]:
        """Copies to stand in for ``item``'s picture, in the order asked:
        its own file on Commons (certain: found by its record), what a
        search of Commons finds, then the catalogue's copies and every
        other source. Each is asked only when the ones before had none."""
        if self.commons_file is not None and (name := self.commons_file(item)):
            try:
                if (copy := self.importer.commons_file(name)) is not None:
                    yield True, copy
            except (httpx.HTTPError, ValueError) as err:
                log.info("Commons file of %s: %s", item.id, err)
        if not item.title.strip():
            return
        query = f"{item.title[:80]} {surname(item.artist)}".strip()
        try:
            hits = self.search_commons(query, HITS)
        except (httpx.HTTPError, ValueError) as err:
            log.info("Commons on %r: %s", query, err)
            hits = []
        for copy in sorted(
            (h for h in hits if self._by_artist(item, h)),
            key=lambda h: -max(h.width or 0, h.height or 0),
        ):
            yield False, copy
        for copy in self.candidates(item, commons=False):
            yield False, copy

    # -- keeping it ----------------------------------------------------------------

    def _adopt(
        self,
        item: Item,
        copy: Item,
        img: Image.Image,
        chosen: bool = False,
        stand_in: bool = False,
        restored: bool = False,
    ) -> Item:
        stored = self.library.get(item.id)
        if stored is None:  # a museum work only looked at: kept for a while
            stored = self.importer.add(item.model_copy(update={"pooled": True}))
        own = self.own_size(stored)
        width, height = img.size
        sharper = SharperCopy(
            url=display_copy(copy),
            item_id=copy.id,
            source=copy.source,
            museum=copy.museum,
            width=width,
            height=height,
            chosen=chosen,
            thumb_url=copy.thumb_url,
            stand_in=stand_in,
            restored=restored,
        )
        updated = self.library.update(item.id, sharper=sharper) or stored
        self.images.adopt(updated, img)
        updated = self._measure_again(updated)
        self._cut_again(item)
        self._remember(item, "chosen" if chosen else "found", copy.id, own)
        log.info(
            "%s copy of %s: %s (%d×%d) from %s",
            "chosen" if chosen else "stand-in" if stand_in else "sharper",
            item.id,
            copy.id,
            width,
            height,
            copy.museum,
        )
        return updated

    def choose(self, item: Item, copy: Item) -> Item:
        """The owner's pick of ``copy`` for ``item``'s picture, in place of
        its own or another copy; the look in the background leaves it be."""
        img = self.images.sample(display_copy(copy), urgent=True)
        return self._adopt(item, copy, img, chosen=True)

    def bring(self, item: Item, data: bytes, origin: str = "", restored: bool = False) -> Item:
        """A copy the owner brought for ``item``'s picture (a picture's
        bytes: one bought in Alamy, a scan; Mateusz, 2026-11-12), kept for
        good and shown in place of its own, as a copy he picked. ``origin``:
        where it is from, as the card names it. ``restored``: drawn again
        by the image model (:mod:`frame_server.restorer`). Raises ValueError
        for what is no picture."""
        stored = self.library.get(item.id) or item
        url, img = self.images.keep_owned(stored, data)
        copy = Item(
            id=f"{OWNED_SOURCE}:{url.removeprefix(OWNED)}",
            source=OWNED_SOURCE,
            source_id=url.removeprefix(OWNED),
            title=stored.title,
            artist=stored.artist,
            museum=origin.strip()[:60] or "Własna kopia",
            image_url=url,
        )
        return self._adopt(stored, copy, img, chosen=True, restored=restored)

    def keep_own(self, item: Item) -> Item:
        """Back to the work's own picture, as the owner asked: no copy is
        looked for again."""
        stored = self.library.get(item.id) or item
        own = self.own_size(stored)
        if stored.sharper is not None:
            stored = self.library.update(item.id, sharper=None) or stored
            self.images.drop_picture(stored)  # the own downloaded again, its thumbnail too
            try:
                self.images.ensure_thumb(stored, urgent=True)
            except (httpx.HTTPError, OSError) as err:  # had when a list next asks
                log.info("own thumbnail of %s: %s", item.id, err)
            else:
                stored = self._measure_again(stored)
            self._cut_again(item)
        self._remember(stored, "kept", "", own)
        return stored

    def own_again(self, item: Item) -> Item:
        """The work's own picture downloaded again from its source, in place
        of a smaller one kept from before (an AIC work's download size,
        Mateusz 2026-11-05) or of a copy standing in for it."""
        stored = self.library.get(item.id) or item
        own = self.own_size(stored)
        img = self.images.sample(own_copy(stored), urgent=True)
        if stored.sharper is not None:
            stored = self.library.update(item.id, sharper=None) or stored
        self.images.adopt(stored, img)
        stored = self._measure_again(stored)
        self._cut_again(item)
        self._remember(stored, "kept", "", own)
        log.info("own picture of %s again: %d×%d", item.id, *img.size)
        return stored

    def own_size(self, item: Item) -> tuple[int, int, int] | None:
        """The work's own picture as its source gave it: from the cache
        while it holds the own, else as noted when a copy took its place."""
        if item.sharper is None:
            return self.images.source_size(item)
        note = self.library.note(item.id, KIND)
        own = note.data.get("own") if note is not None else None
        if isinstance(own, list) and len(own) == 3:
            return int(own[0]), int(own[1]), int(own[2])
        return None

    def archive_works(self) -> list[Item]:
        """The library's works shown in an art archive's colour photograph,
        not looked at since they take copies in other colours."""
        return [
            i
            for i in self.library.all_items()
            if archive_own(i) and not i.excluded and not is_grey_copy(i) and self.status(i) is None
        ]

    def archive_copy(self, item: Item) -> bool:
        """``item`` shows an art archive's photograph the server took as a
        copy (not the owner's pick)."""
        copy = item.sharper
        if copy is None or copy.chosen:
            return False
        kept = self.library.get(copy.item_id)
        if kept is not None:
            return is_art_archive_photo(kept)
        return any(host in copy.url for host in ARCHIVE_HOSTS)

    def drop_archive_copies(self) -> list[Item]:
        """The works shown in an archive's photograph taken as a copy, back
        to their own picture, to be looked at again."""
        dropped = []
        for item in self.library.all_items():
            if item.sharper is None or not self.archive_copy(item):
                continue
            taken = item.sharper.item_id
            stored = self.library.update(item.id, sharper=None) or item
            self.images.drop_picture(stored)
            with self._lock:
                self._known.pop(item.id, None)
            self.library.save_note(
                Note(item_id=item.id, kind=KIND, model="", prompt_version="", data={})
            )
            self._cut_again(item)
            log.info("archive copy of %s let go: %s", item.id, taken)
            dropped.append(stored)
        return dropped

    def archives_once(self) -> int:
        """Once after the update: every work shown in an art archive's faded
        slide (its own, or one taken as a copy before) looked at for another
        copy, one after another; how many. A look too slow leaves the rest
        for the next start (and the night)."""
        if self.library.get_state(ARCHIVES_KEY, 0) >= ARCHIVES_VERSION:
            return 0
        dropped = self.drop_archive_copies()
        works = self.archive_works()
        works += [i for i in dropped if all(i.id != w.id for w in works)]
        log.info("archive slides: looking for other copies of %d works", len(works))
        found = 0
        for n, item in enumerate(works):
            try:
                status = self.soon(item).result(ARCHIVE_WAIT)
            except Late:
                log.info("archive slides: %d of %d looked at, the rest later", n, len(works))
                return n
            found += status == "found"
        self.library.set_state(ARCHIVES_KEY, ARCHIVES_VERSION)
        log.info("archive slides: %d of %d works took another copy", found, len(works))
        return len(works)

    def thumbs_again(self) -> int:
        """Once: the thumbnails of works whose picture a copy took before
        thumbnails followed it, made from the copy (or had again), and their
        colours measured from it; returns how many."""
        if self.library.get_state(THUMBS_KEY, 0) >= THUMBS_VERSION:
            return 0
        done = 0
        for item in self.library.query(include_excluded=True)[1]:
            if item.sharper is None:
                continue
            if self.images.thumb_again(item):
                self._measure_again(item)
            done += 1
        self.library.set_state(THUMBS_KEY, THUMBS_VERSION)
        if done:
            log.info("thumbnails of %d works made again from their copies", done)
        return done

    def _measure_again(self, item: Item) -> Item:
        """The work's colours (dots, colour tags, the frame's preset) from
        its thumbnail as it is now: another picture, other tones."""
        try:
            return self.importer.measure_again(item)
        except OSError as err:  # a broken thumbnail: the colours from before
            log.info("colours of %s: %s", item.id, err)
            return item

    def _cut_again(self, item: Item) -> None:
        for old in self.details_dir.glob(f"{item.file_stem}-*.jpg"):
            old.unlink(missing_ok=True)  # the study's details, from the new picture

    def _remember(
        self,
        item: Item,
        status: Status | Literal["chosen", "kept"],
        copy: str = "",
        own: tuple[int, int, int] | None = None,
    ) -> None:
        known: Status = "found" if status == "chosen" else "fine" if status == "kept" else status
        with self._lock:
            self._known[item.id] = (known, self.clock())
            self._known.move_to_end(item.id)
            while len(self._known) > REMEMBERED:
                self._known.popitem(last=False)
        if self.library.get(item.id) is None:
            return  # a museum work only looked at: remembered in memory only
        self.library.save_note(
            Note(
                item_id=item.id,
                kind=KIND,
                model="",
                prompt_version=version(item),
                data={
                    "status": status,
                    "at": self.clock().isoformat(),
                    "copy": copy,
                    **({"own": list(own)} if own is not None else {}),
                },
            )
        )
