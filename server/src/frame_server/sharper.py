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
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from collections.abc import Callable
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
from .library.images import BYTES, IMAGE_MAX, display_copy
from .library.likeness import Likeness
from .library.models import Note, SharperCopy
from .library.vocabulary import artist_matches, is_copy, is_photograph, is_reproduction

if TYPE_CHECKING:
    from .library import Importer, Library
    from .library.images import ImageCache

log = logging.getLogger(__name__)

KIND = "sharper"
VERSION = "sharper-1"

#: A picture whose long side is shorter than this is worth a sharper copy
#: (the frame is 2560 px long) ...
WEAK_SIDE = 2000
#: ... and so is one squeezed below this many bits per pixel (a painting's
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
#: Looked for at once.
THREADS = 2
#: How long the work of the day waits for its look.
DAILY_WAIT = 300.0
#: Works whose last look is kept in memory (also those not in the library).
REMEMBERED = 2000

Status = Literal["looking", "found", "none", "fine", "off"]


class Quality(NamedTuple):
    """A picture as its source gives it: the long side in pixels (0: no
    picture but the thumbnail) and bits per pixel of its file (None when
    not known)."""

    side: int
    bits: float | None = None

    @classmethod
    def of(cls, width: int, height: int, size: int) -> Quality:
        pixels = width * height
        return cls(max(width, height), size * 8 / pixels if size and pixels else None)

    @classmethod
    def of_image(cls, img: Image.Image) -> Quality:
        return cls.of(*img.size, int(img.info.get(BYTES) or 0))

    @property
    def weak(self) -> bool:
        return self.side < WEAK_SIDE or (self.bits is not None and self.bits < WEAK_BITS)

    def better(self, own: Quality) -> bool:
        """This picture shows the work clearly better than ``own`` does."""
        if self.bits is not None and self.bits < MUSH:
            return False
        side, own_side = min(self.side, IMAGE_MAX), min(own.side, IMAGE_MAX)
        if side < LEAST_SIDE:
            return False
        if side >= own_side * GAIN:
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


def same_colours(own: Tone, copy: Tone) -> bool:
    """``copy`` is in ``own``'s colours: not a grey copy of a coloured work,
    nor a coloured one of a grey work, nor in other light altogether."""
    if own.spread >= GREY and copy.spread < own.spread * GREYER:
        return False
    if own.spread < GREY and copy.spread >= max(GREY * 2, own.spread * 3):
        return False
    distance = float(np.linalg.norm(np.subtract(own.mean, copy.mean)))
    return distance <= COLOUR_OFF


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
        #: Where a study's details are cut (cut again from a sharper copy).
        self.details_dir = images.thumbs.parent / "details"
        self.clock: Callable[[], datetime] = _now
        self._turns = threading.Semaphore(THREADS)
        self._lock = threading.Lock()
        self._looking: dict[str, Future[Status]] = {}
        #: The last look's end, by item id: what it found, and when.
        self._known: OrderedDict[str, tuple[Status, datetime]] = OrderedDict()

    # -- what is known ---------------------------------------------------------

    def status(self, item: Item) -> Status | None:
        """What is known without looking: "off" for what has no other copy
        (photos, own works), "found" for a work with a sharper copy, "fine"
        or "none" as last found out; None when it is to be looked into."""
        if item.kind != ItemKind.ARTWORK or item.look is not None:
            return "off"
        stored = self.library.get(item.id)
        if (stored or item).sharper is not None:
            return "found"
        with self._lock:
            known = self._known.get(item.id)
        if known is None:
            note = self.library.note(item.id, KIND)
            if note is None or note.prompt_version != VERSION:
                return None
            try:
                at = datetime.fromisoformat(str(note.data.get("at")))
            except ValueError:
                return None
            status = str(note.data.get("status"))
        else:
            status, at = known
        if status == "fine":
            return "fine"
        if status == "none" and self.clock() - at < AGAIN:
            return "none"
        return None

    def soon(self, item: Item) -> Future[Status]:
        """Looks for a sharper copy in the background, unless it is known;
        the same look for every asker while it runs."""
        known = self.status(item)
        if known is not None:
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
            target=self._look_then_done, args=(item, future), name="sharper", daemon=True
        ).start()
        return future

    def look(self, item: Item, wait: float = DAILY_WAIT) -> Status:
        """Looks for a sharper copy now (the work of the day, before its
        page is written); what was found, "looking" after ``wait`` seconds."""
        try:
            return self.soon(item).result(wait)
        except Late:
            return "looking"

    def _look_then_done(self, item: Item, future: Future[Status]) -> None:
        status: Status = "none"
        try:
            with self._turns:
                status = self._look(item)
        except Exception:
            log.exception("sharper copy of %s", item.id)
        finally:
            with self._lock:
                self._looking.pop(item.id, None)
            future.set_result(status)

    # -- looking -----------------------------------------------------------------

    def _look(self, item: Item) -> Status:
        own = self.own(item)
        if own is None:
            return "none"  # not even its thumbnail: the network, not the work
        if not own.weak:
            self._remember(item, "fine")
            return "fine"
        log.info("picture of %s is poor (%s); looking for a sharper copy", item.id, own)
        downloaded = 0
        for copy in self.candidates(item)[:COMPARED]:
            if downloaded == DOWNLOADED:
                break
            if not self._promising(copy, own) or not self.same_picture(item, copy):
                continue
            downloaded += 1
            try:
                img = self.images.sample(display_copy(copy))
            except (httpx.HTTPError, OSError) as err:
                log.info("sharper copy %s of %s: %s", copy.id, item.id, err)
                continue
            quality = Quality.of_image(img)
            if not quality.better(own):
                log.info("copy %s of %s is no better (%s)", copy.id, item.id, quality)
                continue
            self._adopt(item, copy, img)
            return "found"
        self._remember(item, "none")
        return "none"

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

    def candidates(self, item: Item) -> list[Item]:
        """Other copies of the work to compare, likeliest first: its Commons
        file, the catalogue's copies, then what the sources find for its
        title and artist, the largest first."""
        found: list[Item] = []
        if self.commons_file is not None and (name := self.commons_file(item)):
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
        a work that is none, a photo sent once."""
        return (
            copy.kind == ItemKind.ARTWORK
            and copy.look is None
            and copy.sharper is None
            and not is_copy(copy)
            and not is_reproduction(copy)
            and (is_photograph(item) or not is_photograph(copy))
            and bool(display_copy(copy))
        )

    @staticmethod
    def _promising(copy: Item, own: Quality) -> bool:
        """Not smaller than needed by what its source says (when it says)."""
        side = max(copy.width or 0, copy.height or 0)
        return not side or Quality(side).better(Quality(own.side))

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
            return same_colours(tone(own_thumb), tone(copy_thumb))
        except OSError:
            return False

    # -- keeping it ----------------------------------------------------------------

    def _adopt(self, item: Item, copy: Item, img: Image.Image) -> None:
        stored = self.library.get(item.id)
        if stored is None:  # a museum work only looked at: kept for a while
            stored = self.importer.add(item.model_copy(update={"pooled": True}))
        width, height = img.size
        sharper = SharperCopy(
            url=display_copy(copy),
            item_id=copy.id,
            source=copy.source,
            museum=copy.museum,
            width=width,
            height=height,
        )
        updated = self.library.update(item.id, sharper=sharper) or stored
        self.images.adopt(updated, img)
        for old in self.details_dir.glob(f"{item.file_stem}-*.jpg"):
            old.unlink(missing_ok=True)  # cut again from the sharper copy
        self._remember(item, "found", copy.id)
        log.info(
            "sharper copy of %s: %s (%d×%d) from %s", item.id, copy.id, width, height, copy.museum
        )

    def _remember(self, item: Item, status: Status, copy: str = "") -> None:
        with self._lock:
            self._known[item.id] = (status, self.clock())
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
                prompt_version=VERSION,
                data={"status": status, "at": self.clock().isoformat(), "copy": copy},
            )
        )
