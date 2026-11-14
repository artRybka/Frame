"""Local cache of library images: small thumbnails and display-size originals."""

from __future__ import annotations

import contextlib
import json
import logging
import math
import os
import re
import secrets
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from PIL import Image

from ..fsutil import dir_bytes, own_files
from ..imaging.cut import same_picture, warp
from ..imaging.layout import load_image
from ..imaging.margins import trim_margins
from ..imaging.mount import inside_mount
from .aic import aic_fallback
from .fragments import PART, split_part
from .hosts import HostGuard, Resting, guard, is_urgent, urgently, walled
from .markup import commons_rendition, extension
from .models import Item
from .policy import DEFAULT_IMAGES, IMAGE_LIMITS, URGENT_EXTRA

log = logging.getLogger(__name__)

THUMB_MAX = 640
#: An elongated thumbnail (:data:`WIDE`) keeps its short side THUMB_MAX /
#: WIDE instead, as long as its long side stays within this: a handscroll
#: 24 times as long as it is tall came 640 × 26 px, and the square tile cut
#: from it was a blur (Mateusz, 2026-11-11). 320 × 8192 px at most, a few
#: hundred kB.
THUMB_LONG = 8192
#: The long side an original is kept with at most (Mateusz 2026-11-11:
#: "Bierzmy lepszą jakość jeżeli taka jest dostępna i muzeum pozwala.
#: Oczywiście z limitem. Powiedzmy 4k px?"): more than the frame's 2560 px
#: (:data:`FRAME_SIDE`), for the app's viewer and a study's details.
IMAGE_MAX = 4000
#: What it was until 1.145.33: originals cut to it are had again larger
#: (:meth:`ImageCache.larger_again`), and museums' addresses kept with the
#: works still ask for it (:func:`sized_copy` asks for more).
OLD_MAX = 2560
#: Pictures longer than this many times their width (or the other way
#: round) are kept larger than :data:`IMAGE_MAX` on the long side: a
#: Japanese handscroll 30 times as long as it is tall was kept 2560 × 86 and
#: came out mush on the card and in a crop (Mateusz, 2026-11-09). Up to
#: this nothing changes; past it the short side keeps IMAGE_MAX / WIDE ...
WIDE = 2.0
#: ... as long as the picture has no more pixels than a square
#: IMAGE_MAX × IMAGE_MAX one (6.5 Mpx: the frame's work on it takes as long),
IMAGE_AREA = IMAGE_MAX * IMAGE_MAX
#: ... nor a long side past this (the app's viewer, a JPEG's own limit is 65535).
LONG_MOST = 16384
#: The long side pictures were kept at most before :data:`WIDE` (Cleveland's
#: "print" files, the largest JPEGs it gives, are 3400 px long): kept ones
#: that long or shorter are had again once (:meth:`ImageCache.wide_again`).
OLD_KEPT = 3400
#: Thumbnails of works that are not in the library (browsed, previewed).
THUMB_SPARE = 5000
#: Downloads at once from one host (library/policy.py): Commons answers more
#: than two parallel media requests with 429, the AIC asks for one picture at
#: a time, museum CDNs throttle bursts too. What the owner looks at now (the
#: card's original, a preview) gets URGENT_EXTRA more, so it never waits for
#: the background's; hosts with a limit of their own get none.
HOST_LIMITS = IMAGE_LIMITS
HOST_LIMIT = DEFAULT_IMAGES
#: Answers worth another try (throttled or briefly down), and how many tries.
RETRY_STATUS = {408, 429, 500, 502, 503, 504}
ATTEMPTS = 3
#: How long an original that could not be downloaded is not asked for
#: again: every preview and every turn in the queue would wait for it.
FAILED_FOR = 1800.0
#: How long a work whose picture every address refuses (gone from the
#: museum, a web page in its place) is left out of lists before it is
#: tried again: museums put pictures back, or move them.
GONE_FOR = 7 * 86400.0
#: Commons originals wider than this come as Commons' own rendition of this
#: width: a museum's scan can be 100 MB and 200 megapixels, far more than
#: the frame's 2560 px, and too large for Pillow to open at all.
COMMONS_WIDTH = 3840
#: How far back an original kept only because it was looked at is dated
#: (:meth:`ImageCache.looked_at`): older than any the owner saw.
LOOKED_AGE = 365 * 24 * 3600.0
#: A fragment's picture is kept this large (``kept_side``): a tile of a
#: Commons tile set is looked at closely, 2560 showed a twelfth of its
#: width (Mateusz 2026-11-10).
TILE_MAX = COMMONS_WIDTH
#: A picture whose long side is shorter than this is worth a sharper copy
#: (the frame is 2560 px long).
WEAK_SIDE = 2000
#: The frame's longer side: a picture as long shows the work whole on it.
FRAME_SIDE = 2560
#: Sources whose works' sizes are their files' own and whose addresses ask
#: for a size (IIIF ``full/!2560,2560``, the Smithsonian's ``max=2560``):
#: a work is asked in the size it is kept in (:func:`kept_size`), never in
#: more than its file has (Yale's server enlarges a small scan to the size
#: asked, the Courtauld's refuses).
SIZED = ("nga", "yale", "smk", "si", "courtauld")
#: Sources whose IIIF server enlarges a smaller scan to the size asked and
#: whose works' sizes are not known: asked whole (the Wellcome Collection's
#: scans are 3600 px at most; ``!4000,4000`` of one 2004 × 2440 came
#: 3285 × 4000, 2026-11-11).
WHOLE = ("wellcome",)
#: Sources whose IIIF server works out a size it was not asked for before
#: for many seconds and hands the whole file over at once: asked whole and
#: cut down here, but for a file of more than :data:`COMMONS_WHOLE` pixels
#: (as much as is opened whole here; one in 25 of Yale's is larger).
#: Yale, 2026-11-12, six works: ``!4000,4000`` in 9, 16, 37 and 44 s, the
#: whole file (2 to 5 MB) in half a second each; in the night a 500 now
#: and then, after which the host rested and its thumbnails and imports
#: were turned away 524 times.
SLOW_SIZES = ("yale",)
#: A size the server's own readers ask for in a work's address (the AIC's
#: ``!3000,3000``, its museum's limit, is none).
_OURS = f"(?:{OLD_MAX}|{IMAGE_MAX})"
_IIIF_FIT = re.compile(rf"/full/!{_OURS},{_OURS}/")
_SI_MAX = re.compile(rf"([?&]max=){_OURS}\b")
#: An elongated Commons file this many pixels or fewer is downloaded whole
#: when Commons' widest rendition (:data:`COMMONS_WIDTH`) is narrower than
#: the picture is kept: a scroll 30 000 × 1 000 px is 30 Mpx, a few MB.
COMMONS_WHOLE = 50_000_000
#: How long what the owner waits for waits for the background's download of
#: the same picture before it downloads its own: the background's may wait
#: out the app's use (:meth:`HostGuard.wait_calm`) with the picture's lock
#: held, and a Szukaj tile waited for it with no end (2026-11-07).
URGENT_LOCK_WAIT = 3.0
#: Sources of the owner's own pictures (uploads, iCloud albums, the frame's
#: placeholder): kept as they are, never trimmed of margins
#: (:func:`~frame_server.imaging.margins.trim_margins`), a white wall or a
#: snowy field at a photo's edges is the photo.
OWN_SOURCES = ("upload", "icloud", "cli", "frame")
#: Sources whose readers say how large a work's picture is. For a work of
#: any other the size kept is its thumbnail's (``Importer._analysed``): the
#: picture's proportions, and no word on how large the original is (the
#: Met's 600 px, the Rijksmuseum's 640: 46 000 works of the catalogue,
#: 2026-11-11). Cleveland says its web picture's size, not the one shown.
SAY_SIZE = frozenset({*SIZED, "aic", "wmc", "wikiart", "openverse", *OWN_SOURCES})
#: Where :meth:`ImageCache._download` leaves the size of the file it read,
#: in the picture's ``info``.
BYTES = "frame_bytes"


#: (address, picture as read, download another address) -> the picture.
Repair = Callable[[str, Image.Image, Callable[[str], bytes]], Image.Image]


class Unavailable(OSError):
    """The original cannot be had from anywhere: the host refuses programs
    (a "verify you are human" page), the file is gone, or it was tried
    lately and failed."""


class TooLarge(OSError):
    """A picture with more pixels than Pillow opens (a decompression bomb
    to it): the thumbnail stands in for it."""


class Gone(Unavailable):
    """No picture of the work at all: every address refused even the
    thumbnail. The work is left out of lists for :data:`GONE_FOR`."""


def kept_size(width: int, height: int) -> tuple[int, int]:
    """The size a picture of ``width`` × ``height`` is kept in (never larger
    than it is): its long side :data:`IMAGE_MAX`, or for one more elongated
    than :data:`WIDE` its short side IMAGE_MAX / WIDE within
    :data:`IMAGE_AREA` and :data:`LONG_MOST`."""
    if width <= 0 or height <= 0:
        return width, height
    long, short = max(width, height), min(width, height)
    ratio = long / short
    if ratio <= WIDE:
        scale = IMAGE_MAX / long
    else:
        side = min(IMAGE_MAX / WIDE, math.sqrt(IMAGE_AREA / ratio), LONG_MOST / ratio)
        scale = side / short
    if scale >= 1.0:
        return width, height
    return max(round(width * scale), 1), max(round(height * scale), 1)


def thumb_size(width: int, height: int) -> tuple[int, int]:
    """The size a thumbnail of a picture ``width`` × ``height`` is kept in
    (never larger than it is): its long side :data:`THUMB_MAX`, or for one
    more elongated than :data:`WIDE` its short side THUMB_MAX / WIDE within
    :data:`THUMB_LONG`."""
    if width <= 0 or height <= 0:
        return width, height
    long, short = max(width, height), min(width, height)
    ratio = long / short
    side = THUMB_MAX / ratio if ratio <= WIDE else min(THUMB_MAX / WIDE, THUMB_LONG / ratio)
    scale = side / short
    if scale >= 1.0:
        return width, height
    return max(round(width * scale), 1), max(round(height * scale), 1)


def thin_thumb(width: int, height: int) -> bool:
    """Whether an elongated picture this size is thinner than its thumbnail
    is kept (:func:`thumb_size`): the source has a larger one to make it
    from. A tenth less is close enough."""
    if not wide(width, height):
        return False
    want = min(thumb_size(width * 100, height * 100))
    return min(width, height) < 0.9 * want


def kept_long(long: int, ratio: float = 1.0) -> int:
    """The long side a picture ``long`` px long and ``ratio`` times as long
    as it is wide is kept with (:func:`kept_size`)."""
    if long <= 0:
        return 0
    short = max(round(long / max(ratio, 1.0)), 1)
    return max(kept_size(long, short))


def wide(width: int | None, height: int | None) -> bool:
    """Whether a picture this size is kept larger than :data:`IMAGE_MAX`."""
    if not width or not height:
        return False
    return max(width, height) > WIDE * min(width, height)


def kept_side(item: Item) -> int:
    """The long side ``item``'s original is kept with: a fragment of a work
    (a tile looked at in the full-screen viewer, "Pod lupą") as large as
    Commons' widest rendition, :data:`TILE_MAX`; any other
    :data:`IMAGE_MAX` (more for an elongated one, :func:`kept_size`)."""
    return TILE_MAX if split_part(item.id) is not None else IMAGE_MAX


def _read_whole(path: Path) -> bytes | None:
    """The file's bytes, None when it is not there: opened, measured and
    read in three calls (``Path.read_bytes`` makes eight, and each is a
    turn to wait for while another thread works)."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except (FileNotFoundError, IsADirectoryError):
        return None
    try:
        size = os.fstat(fd).st_size
        data = os.read(fd, size + 1)
        while len(data) < size:  # a short read: the rest
            more = os.read(fd, size - len(data))
            if not more:
                break
            data += more
        return data
    finally:
        os.close(fd)


def _save_jpeg(img: Image.Image, path: Path, max_side: int, quality: int) -> None:
    img = img.convert("RGB")
    if max_side == IMAGE_MAX:  # an original: elongated ones keep more (WIDE)
        size = kept_size(*img.size)
        if size != img.size:
            img = img.resize(size, Image.Resampling.LANCZOS)
    elif max_side == THUMB_MAX:  # a thumbnail: elongated ones stay thicker
        size = thumb_size(*img.size)
        if size != img.size:
            img = img.resize(size, Image.Resampling.LANCZOS)
    else:
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    # Its own file per thread: an urgent asker may write the same picture
    # beside the background's (:meth:`ImageCache._holding`).
    tmp = path.with_name(f"{path.stem}.{threading.get_ident()}.tmp")
    img.save(tmp, "JPEG", quality=quality, optimize=True)
    tmp.replace(path)


def _retry_after(resp: httpx.Response, attempt: int) -> float:
    try:
        wait = float(resp.headers.get("retry-after", ""))
    except ValueError:
        wait = 2.0 * attempt
    return min(max(wait, 0.5), 8.0)


def _refused(err: Exception) -> bool:
    """Whether another try would get the same: the host answered, but not
    with the picture (gone, forbidden, a web page instead of an image)."""
    if isinstance(err, httpx.HTTPStatusError):
        status = err.response.status_code
        return 400 <= status < 500 and status not in RETRY_STATUS
    return not isinstance(err, httpx.HTTPError)  # read, but not as a picture


def _too_large(err: Exception) -> bool:
    """An IIIF server's answer to a size larger than the file, when it does
    not enlarge (400)."""
    return isinstance(err, httpx.HTTPStatusError) and err.response.status_code == 400


def _missing(err: Exception) -> bool:
    """Whether the address has no picture of the work for good: gone (404,
    410), refused by the server itself (not by a bot wall, which forgets
    us), or something else than a picture in its place."""
    if isinstance(err, httpx.HTTPStatusError):
        resp = err.response
        if resp.status_code in (404, 410):
            return True
        return resp.status_code in (400, 401, 403) and not walled(resp)
    return not isinstance(err, httpx.HTTPError)


def _trimmed(item_id: str) -> bool:
    """Whether the work's pictures lose a museum's blank margins: not the
    owner's own (:data:`OWN_SOURCES`), nor a fragment of a work (a tile
    must keep its edges to lie in its place on the whole)."""
    return item_id.partition(":")[0] not in OWN_SOURCES and split_part(item_id) is None


def said_side(item: Item) -> int | None:
    """The long side of the picture ``item`` is shown from, when it is
    known: a sharper copy's, else the one its source says; None for a
    source that says none (:data:`SAY_SIZE`)."""
    if item.sharper is not None:
        return max(item.sharper.width, item.sharper.height)
    if item.source in SAY_SIZE and item.width and item.height:
        return max(item.width, item.height)
    return None


def display_copy(item: Item) -> str:
    """The address of ``item``'s original, or of Commons' smaller rendition
    of it when the file is far larger than the frame needs; a sharper copy
    from another source (``item.sharper``) instead, when it has one."""
    if item.sharper is not None:
        return item.sharper.url
    return own_copy(item)


def own_copy(item: Item) -> str:
    """:func:`display_copy` of the work's own source, never another's: in
    the size it is kept in (:func:`sized_copy`)."""
    return sized_copy(item) or usual_copy(item)


def usual_copy(item: Item) -> str:
    """The work's own address as the source gives it, or Commons' rendition
    of a file far larger than the frame needs."""
    url = item.image_url
    if item.width and item.width > COMMONS_WIDTH:
        return commons_rendition(url, COMMONS_WIDTH, item.width) or url
    return url


def sized_copy(item: Item) -> str:
    """The work's own address asking for the size it is kept in
    (:func:`kept_size`, :data:`IMAGE_MAX` for most), where the address asks
    for a size or Commons has the elongated file whole; "" for any other
    work (:func:`usual_copy` is its address then).

    A source that says its files' sizes (:data:`SIZED`) is asked for no
    more than the file has, or for the whole file where a size takes its
    server long (:data:`SLOW_SIZES`); one that enlarges (:data:`WHOLE`) for
    the whole file; any other for IMAGE_MAX, and for the whole file when
    that is refused (:func:`whole_copy`)."""
    width, height, url = item.width, item.height, item.image_url
    fit, si = _IIIF_FIT.search(url), _SI_MAX.search(url)
    if fit or si:
        long = IMAGE_MAX
        if item.source in SIZED and width and height:
            if item.source in SLOW_SIZES and fit and width * height <= COMMONS_WHOLE:
                return _IIIF_FIT.sub("/full/full/", url)
            long = max(kept_size(width, height))
        elif item.source in WHOLE and fit:
            return _IIIF_FIT.sub("/full/max/", url)
        if fit:
            return _IIIF_FIT.sub(f"/full/!{long},{long}/", url)
        return _SI_MAX.sub(rf"\g<1>{long}", url)
    if not width or not height or not wide(width, height):
        return ""
    if (
        item.source == "wmc"
        and width > COMMONS_WIDTH
        and max(kept_size(width, height)) > COMMONS_WIDTH
        and width * height <= COMMONS_WHOLE
        and extension(url) in ("jpg", "jpeg", "png")
    ):
        return url
    return ""


def whole_copy(item: Item) -> str:
    """The address of the work's whole file, for a source whose files'
    sizes are not known and whose address asks for a size: an IIIF server
    that does not enlarge answers 400 to ``!4000,4000`` of a smaller scan
    (the Getty's, 2026-11-11), which is then small enough to have whole."""
    known = item.source in SIZED and bool(item.width and item.height)
    if known or item.source in WHOLE or not _IIIF_FIT.search(item.image_url):
        return ""
    return _IIIF_FIT.sub("/full/max/", item.image_url)


def thumb_copy(item: Item) -> str:
    """An elongated work's address asking for its thumbnail in the size it
    is kept in (:func:`thumb_size`), from a source whose addresses ask for a
    size (:data:`SIZED`, Commons), or for the whole file where a size takes
    the server long (:data:`SLOW_SIZES`); "" for any other work or source."""
    width, height, url = item.width, item.height, item.image_url
    if not width or not height or not wide(width, height):
        return ""
    w, h = thumb_size(width, height)
    long = max(w, h)
    if item.source in SIZED:
        if _IIIF_FIT.search(url):
            if item.source in SLOW_SIZES and width * height <= COMMONS_WHOLE:
                # Yale's server did not answer !8192,8192 and !4674,4674 in
                # time (the night of 2026-11-13: twice, and the host rested).
                return _IIIF_FIT.sub("/full/full/", url)
            return _IIIF_FIT.sub(f"/full/!{long},{long}/", url)
        if _SI_MAX.search(url):
            return _SI_MAX.sub(rf"\g<1>{long}", url)
    if item.source == "wmc" and (rendition := commons_rendition(url, w, width)):
        return rendition
    return ""


#: The address of a copy the owner brought for a work (one bought in Alamy,
#: a scan of his own): a file in ``owned/``, kept for good, never pruned.
OWNED = "owned:"
#: The source such a copy is noted with (``SharperCopy.source``).
OWNED_SOURCE = "owned"
#: The longest side such a copy is kept in.
OWNED_MAX = 8000


class ImageCache:
    def __init__(self, root: Path, http: Callable[[], httpx.Client]) -> None:
        self.thumbs = root / "thumbs"
        self.images = root / "images"
        #: Copies the owner brought (:data:`OWNED`).
        self.owned = root / "owned"
        #: Thumbnails as the cover tiles show them (:meth:`tile`), by the
        #: thumbnail's name; never without their thumbnail.
        self.tiles = root / "tiles"
        #: Museum photographs of works cut down to the work (``Item.cut``),
        #: as they came, by the original's name: "Pełny kadr", and the
        #: corners set again from them.
        self.full = root / "full"
        self.full.mkdir(parents=True, exist_ok=True)
        self.thumbs.mkdir(parents=True, exist_ok=True)
        self.tiles.mkdir(parents=True, exist_ok=True)
        self.images.mkdir(parents=True, exist_ok=True)
        self.http = http
        #: Sources whose originals need more than a plain download (by source).
        self.fetchers: dict[str, Callable[[Item], bytes]] = {}
        #: Other addresses of a picture, tried when its own fail (by source):
        #: an aggregator's copy of a museum's file. Called with the item and
        #: whether a thumbnail will do.
        self.mirrors: dict[str, Callable[[Item, bool], list[str]]] = {}
        #: Hosts that serve some pictures wrong, and how to set them right:
        #: called with the address, the picture as read and a way to
        #: download another address (the Courtauld's CMYK scans come white).
        self.repairs: dict[str, Repair] = {}
        #: When an original last failed to download (by item id).
        self._failed: dict[str, float] = {}
        self.clock: Callable[[], float] = time.monotonic
        #: Works with no picture anywhere, and since when (wall clock, so it
        #: lasts across restarts; by item id).
        self.wall: Callable[[], float] = time.time
        self._gone_path = root / "gone.json"
        self._gone: dict[str, float] = self._load_gone()
        #: Pictures as their sources gave them, before they were cut down to
        #: the frame's size: [width, height, bytes] (by item id).
        self._sizes_path = root / "sizes.json"
        self._sizes: dict[str, list[int]] = self._load_sizes()
        self._locks: dict[str, threading.Lock] = {}
        self._gates: dict[str, HostGate] = {}
        self._guard = threading.Lock()
        self.sleep: Callable[[float], None] = time.sleep
        #: The museums' manners (:mod:`.hosts`): which hosts rest now.
        self.hosts: HostGuard = guard

    def _lock(self, key: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    @contextlib.contextmanager
    def _holding(self, key: str, url: str, urgent: bool) -> Iterator[None]:
        """One download of a picture at a time (``key``), but what the owner
        waits for never waits long behind the background's: that one waits
        out the quiet and the app's use (:meth:`HostGuard.wait_calm`) before
        it takes the lock, and may still wait inside if the app comes back
        meanwhile; after :data:`URGENT_LOCK_WAIT` the urgent one downloads
        its own copy. The thumbnail of a Commons photograph in Szukaj stayed
        empty for minutes while the background held it (2026-11-07)."""
        urgent = urgent or is_urgent()
        if not urgent:
            self.hosts.wait_calm(urlsplit(url).hostname or "")
        lock = self._lock(key)
        held = lock.acquire(timeout=URGENT_LOCK_WAIT if urgent else -1)
        if not held:
            log.info("picture %s still on its way in the background; asked again now", key)
        try:
            yield
        finally:
            if held:
                lock.release()

    def thumb_path(self, item: Item) -> Path:
        return self.thumbs / f"{item.file_stem}.jpg"

    def kept_thumb(self, item_id: str) -> Path | None:
        """The thumbnail of ``item_id`` when it is here (no need to know the
        work: after an update, a museum work's record is not asked again
        only to send a thumbnail already kept)."""
        path = self.thumbs / f"{Item.stem_of(item_id)}.jpg"
        return path if path.is_file() else None

    def thumb_bytes(self, item_id: str, *, tile: bool = False) -> bytes | None:
        """The kept thumbnail of ``item_id`` as it is sent (``tile``: as a
        cover tile shows it), None when there is none here yet; a copy the
        owner brought has its made (:meth:`owned_thumb`).

        All of it in one go, for one thread: while the server is busy
        (a search, the night's work) every step between a request and its
        answer waits its turn, about 5 ms each, and a file sent piece by
        piece took 23 ms a thumbnail where this takes 8 (the audit of
        2026-11-14). So no ``is_file`` first, and the file is read whole
        with as few calls as there are."""
        path = self.thumbs / f"{Item.stem_of(item_id)}.jpg"
        if not tile:
            data = _read_whole(path)
            if data is not None:
                return data
        kept = path if tile and path.is_file() else self.owned_thumb(item_id)
        if kept is None:
            return None
        return _read_whole(self.tile(kept) if tile else kept)

    def owned_thumb(self, copy_id: str) -> Path | None:
        """The thumbnail of a copy the owner brought (``owned:<file>``, a
        drawing of the creative restorer too), made from its file in
        ``owned/``; None for another id or a file not here. "Szukaj lepszej
        kopii" shows the copy in a work's place by its own id, and it had
        no thumbnail (Mateusz 2026-11-13)."""
        if not copy_id.startswith(OWNED_SOURCE + ":"):
            return None
        source = self.owned / Path(copy_id.removeprefix(OWNED_SOURCE + ":")).name
        if not source.is_file():
            return None
        path = self.thumbs / f"{Item.stem_of(copy_id)}.jpg"
        with self._lock(f"t:{copy_id}"):
            if not path.is_file():
                _save_jpeg(load_image(source), path, THUMB_MAX, 85)
        return path

    def image_path(self, item: Item) -> Path:
        return self.images / f"{item.file_stem}.jpg"

    def full_path(self, item: Item) -> Path:
        """The museum's photograph of a work whose original is cut down to
        the work (:meth:`recut`); there only while the cut applies."""
        return self.full / f"{item.file_stem}.jpg"

    def _photo_path(self, item: Item) -> Path:
        """The original as the museum gave it: the photograph kept beside a
        cut one, else the original itself."""
        full = self.full_path(item)
        return full if full.is_file() else self.image_path(item)

    @staticmethod
    def _quad(item: Item, size: tuple[int, int]) -> list[tuple[float, float]] | None:
        """The corners a picture of ``size`` is cut to for ``item``, None
        when it is shown whole (no cut, or another picture than the cut's)."""
        shown = item.cut_shown()
        if shown is None or item.cut is None or not same_picture(item.cut.aspect, size):
            return None
        return shown

    def _keep_original(self, item: Item, img: Image.Image, side: int) -> Path:
        """``img``, the museum's photograph as downloaded, kept as the work's
        original: cut down to the work when its cut applies, the photograph
        kept beside it (:meth:`full_path`)."""
        path = self.image_path(item)
        quad = self._quad(item, img.size)
        if quad is None:
            _save_jpeg(img, path, side, 92)
            self.full_path(item).unlink(missing_ok=True)
        else:
            _save_jpeg(img, self.full_path(item), side, 92)
            _save_jpeg(warp(img, quad), path, side, 92)
        return path

    def recut(self, item: Item) -> bool:
        """The original and the thumbnail kept here made again after the
        work's cut changed (set, corrected, the paper switched, given up):
        from the museum's photograph kept beside a cut original, else from
        the original itself. A work with no original here loses its
        thumbnail, had again (and cut) from its address when next asked
        for. Whether an original was here."""
        path, full = self.image_path(item), self.full_path(item)
        here = False
        with self._lock(f"i:{item.id}"):
            source = full if full.is_file() else path if path.is_file() else None
            if source is not None:
                try:
                    img = load_image(source)
                except OSError as err:
                    log.warning("cut of %s not made: %s", item.id, err)
                else:
                    here = True
                    quad = self._quad(item, img.size)
                    if quad is None:
                        if source == full:
                            os.replace(full, path)  # the photograph whole again
                    else:
                        if source == path:
                            os.replace(path, full)  # kept as it came
                        _save_jpeg(warp(img, quad), path, kept_side(item), 92)
        with self._lock(f"t:{item.id}"):
            thumb = self.thumb_path(item)
            if here and path.is_file():
                try:
                    _save_jpeg(load_image(path), thumb, THUMB_MAX, 85)
                except OSError:
                    thumb.unlink(missing_ok=True)
            else:
                thumb.unlink(missing_ok=True)
            (self.tiles / thumb.name).unlink(missing_ok=True)
        return here

    def museum_photo(self, item: Item, urgent: bool = False) -> Path:
        """The museum's photograph of the work, whole ("Pełny kadr"; what
        the corners are set on): kept beside a cut original, else the
        original, downloaded if need be."""
        full = self.full_path(item)
        if full.is_file():
            return full
        path = self.ensure_image(item, urgent)
        return full if full.is_file() else path  # cut as it came in, or whole

    def tile(self, thumb: Path) -> Path:
        """The thumbnail ``thumb`` as a cover tile shows it: the work
        without the paper, mount or backdrop around it
        (:func:`~frame_server.imaging.mount.inside_mount`; Goya's etchings
        were a small plate on a wide sheet in the tiles of Odkrywaj,
        Mateusz 2026-11-12). Worked out again when the thumbnail is newer
        (another copy); a work with nothing around it gets its thumbnail's
        copy, so the next ask is a file read too."""
        path = self.tiles / thumb.name
        with contextlib.suppress(OSError):
            if path.stat().st_mtime >= thumb.stat().st_mtime:
                return path
        with Image.open(thumb) as img:
            img.load()
            cut = inside_mount(img)
            tmp = path.with_name(f"{path.stem}.{threading.get_ident()}.tmp")
            if cut is img:
                tmp.write_bytes(thumb.read_bytes())
            else:
                cut.convert("RGB").save(tmp, "JPEG", quality=85)
        os.replace(tmp, path)
        return path

    def _gate(self, host: str) -> HostGate:
        with self._guard:
            if host not in self._gates:
                limit = HOST_LIMITS.get(host, HOST_LIMIT)
                extra = 0 if host in HOST_LIMITS else URGENT_EXTRA
                self._gates[host] = HostGate(limit, extra)
            return self._gates[host]

    def _fetch(self, url: str, urgent: bool = False) -> bytes:
        """A few downloads per host at a time, ``urgent`` ones first; throttled
        ones are tried again after the wait the host asks for (a few seconds
        at most). A copy the owner brought is read from its file."""
        if url.startswith(OWNED):
            return (self.owned / Path(url.removeprefix(OWNED)).name).read_bytes()
        urgent = urgent or is_urgent()
        host = urlsplit(url).hostname or ""
        if not urgent:  # not holding the host's turn while the background waits
            self.hosts.wait_calm(host)
        gate = self._gate(host)
        asking = urgently() if urgent else contextlib.nullcontext()
        with gate.turn(urgent), asking, self.http() as http:
            for attempt in range(1, ATTEMPTS + 1):
                try:
                    resp = http.get(url)
                except Resting:
                    raise  # asked again once the host's wall forgets us
                except httpx.TransportError:
                    if attempt == ATTEMPTS:
                        raise
                    self.sleep(attempt)
                    continue
                if resp.status_code in RETRY_STATUS and attempt < ATTEMPTS:
                    self.sleep(_retry_after(resp, attempt))
                    continue
                resp.raise_for_status()
                return resp.content
        raise AssertionError("unreachable")

    def _download(self, url: str, urgent: bool = False, trim: bool = True) -> Image.Image:
        """The picture at ``url``, set right when its host serves some wrong
        (:attr:`repairs`); ``trim``: without a museum's blank margins."""
        data = self._fetch(url, urgent)
        try:
            img = load_image(data)
        except Image.DecompressionBombError as err:
            raise TooLarge(f"{url}: {err}") from err
        img.info[BYTES] = len(data)
        repair = self.repairs.get(urlsplit(url).hostname or "")
        if repair is not None:
            img = repair(url, img, lambda other: self._fetch(other, urgent))
        # A museum's flat white or black sheet around the picture (the V&A's
        # older scans): a mat inside the mat on the frame (2026-11-08).
        return trim_margins(img) if trim else img

    def sample(self, url: str, urgent: bool = False) -> Image.Image:
        """A picture downloaded to be looked at, not kept."""
        return self._download(url, urgent)

    def looked_at(self, item: Item) -> Image.Image:
        """``item``'s original downloaded to be looked at (the twins' large
        pictures), and kept as the work's original while there is room: it
        is the file the work's card and the frame would ask for, and the
        next look reads it from the disk. Dated :data:`LOOKED_AGE` back,
        it is the first to go when room runs out, before any original the
        owner saw (:meth:`prune`)."""
        img = self.sample(display_copy(item))
        path = self.image_path(item)
        with contextlib.suppress(OSError), self._lock(f"i:{item.id}"):
            if not path.is_file():
                self._keep_original(item, img, kept_side(item))
                self._remember_size(item, img)
                old = time.time() - LOOKED_AGE
                os.utime(path, (old, old))
        return img

    def ensure_thumb(self, item: Item, urgent: bool = False) -> Path:
        """The thumbnail, downloaded if need be. When its own address fails,
        the original's and the mirrors' are tried; when every one refuses
        for good, the work is gone (:class:`Gone`) for a while."""
        path = self.thumb_path(item)
        if path.is_file():
            return path
        with self._holding(f"t:{item.id}", item.thumb_url, urgent):
            if not path.is_file():
                local = self.image_path(item)
                if local.is_file():
                    img = load_image(local)
                else:
                    img = self._thumbnail(item, urgent)
                    if (quad := self._quad(item, img.size)) is not None:
                        img = warp(img, quad)  # the work, as its original is kept
                _save_jpeg(img, path, THUMB_MAX, 85)
        self._forget_gone(item)
        return path

    def thumb_waits(self, item: Item) -> float:
        """Seconds until the thumbnail can be had, when it is not here and
        the host it comes from turned us away lately (:class:`Resting`);
        0 when it is here or may be asked for now. Lists leave such works
        out: the app would show an empty tile, and the phone at home asks
        from the same address the wall turned away."""
        if not item.thumb_url or self.thumb_path(item).is_file() or self.has_image(item):
            return 0.0
        return self.hosts.resting(urlsplit(item.thumb_url).hostname or "")

    def _addresses(self, item: Item, thumb: bool) -> list[str]:
        """The picture's own addresses (a sharper copy's first), without
        the mirrors (:meth:`_mirrored`)."""
        image_url = own_copy(item)
        first = [item.thumb_url, image_url] if thumb else [image_url or item.thumb_url]
        if not thumb and (allowed := aic_fallback(image_url, item.width)):
            first.append(allowed)  # the download size refused: the API's widest
        if not thumb and image_url != (usual := usual_copy(item)):
            first.append(usual)  # the larger size refused (sized_copy)
        if item.sharper is not None:  # the sharper copy first, the own after
            copy = [item.sharper.thumb_url, item.sharper.url] if thumb else [item.sharper.url]
            first[:0] = copy
        return list(dict.fromkeys(u for u in first if u))

    def _mirrored(self, item: Item, thumb: bool, urls: list[str]) -> list[str]:
        """``urls`` and, after them, the mirrors' addresses of the picture:
        asked only once the own failed (a mirror may ask Wikidata, which is
        no business of a download that works)."""
        mirrors = self.mirrors.get(item.source)
        more = mirrors(item, thumb) if mirrors else []
        return list(dict.fromkeys([*urls, *(u for u in more if u)]))

    def _thumbnail(self, item: Item, urgent: bool) -> Image.Image:
        """The thumbnail from the work's addresses; for an elongated work
        whose thumbnail address gives too thin a picture (Cleveland's 900 ×
        37 px "web" one of a handscroll), from a larger address of it."""
        img = self._small_thumbnail(item, urgent)
        if not thin_thumb(*img.size):
            return img
        trim = _trimmed(item.id)
        larger = [] if item.sharper is not None else [thumb_copy(item)]
        if item.sharper is not None or item.source not in self.fetchers:
            larger += self._addresses(item, thumb=False)
        for url in dict.fromkeys(u for u in larger if u and u != item.thumb_url):
            try:
                other = self._download(url, urgent, trim=trim)
            except (httpx.HTTPError, OSError) as err:
                log.info("larger thumbnail of %s from %s failed: %s", item.id, url, err)
                continue
            if min(other.size) > min(img.size):
                return other
        return img

    def _small_thumbnail(self, item: Item, urgent: bool) -> Image.Image:
        urls = self._addresses(item, thumb=True)
        mirrored = not urls  # none of its own: the mirrors at once
        if mirrored:
            urls = self._mirrored(item, True, urls)
        refused = True
        resting: Resting | None = None
        n = 0
        while n < len(urls):
            url = urls[n]
            n += 1
            try:
                return self._download(url, urgent, trim=_trimmed(item.id))
            except (httpx.HTTPError, OSError) as err:
                refused = refused and _missing(err)
                if isinstance(err, Resting):
                    resting = resting or err
                if n == len(urls) and not mirrored:
                    mirrored = True
                    urls = self._mirrored(item, True, urls)
                if n < len(urls):
                    log.info("thumbnail of %s from %s failed: %s; next address", item.id, url, err)
                    continue
                if resting is not None and err is not resting:
                    # A mirror failed too: the museum's wall is why there is
                    # none, and it says when to ask again.
                    raise resting from err
                if not refused:
                    raise
                self._mark_gone(item)
                raise Gone(f"no picture of {item.id} anywhere: {err}") from err
        self._mark_gone(item)
        raise Gone(f"no address for a picture of {item.id}")

    # Sizes of the pictures as their sources gave them

    def _load_sizes(self) -> dict[str, list[int]]:
        try:
            data = json.loads(self._sizes_path.read_text())
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {
            str(k): [int(n) for n in v]
            for k, v in data.items()
            if isinstance(v, list) and len(v) == 3 and all(isinstance(n, int) for n in v)
        }

    def _remember_size(self, item: Item, img: Image.Image) -> None:
        width, height = img.size
        size = [width, height, int(img.info.get(BYTES) or 0)]
        with self._guard:
            self._sizes[item.id] = size
            with contextlib.suppress(OSError):
                tmp = self._sizes_path.with_suffix(".tmp")
                tmp.write_text(json.dumps(self._sizes))
                tmp.replace(self._sizes_path)

    def known_size(self, item: Item) -> tuple[int, int] | None:
        """The original's size as its source gave it, when it was kept at
        its download (no look at the disk)."""
        with self._guard:
            known = self._sizes.get(item.id)
        return None if known is None else (known[0], known[1])

    def long_side(self, item: Item) -> int | None:
        """The long side of the picture ``item`` is shown from, when it is
        known: :func:`said_side`, else the original's as downloaded
        (:meth:`known_size`); never a thumbnail's. The mark of a small
        picture (``low_res``) and the order by quality read it."""
        side = said_side(item)
        if side is None and (size := self.known_size(item)) is not None and min(size) > 0:
            side = max(size)
        return side

    def source_size(self, item: Item) -> tuple[int, int, int] | None:
        """The original as its source gave it: (width, height, bytes; 0 when
        not known), for one downloaded here; None when it is not here."""
        path = self.image_path(item)
        if not path.is_file():
            return None
        with self._guard:
            known = self._sizes.get(item.id)
        if known is not None:
            return known[0], known[1], known[2]
        try:  # downloaded before sizes were kept: its own size, cut down
            with Image.open(path) as img:
                width, height = img.size
        except OSError:
            return None
        return width, height, 0

    # Works with no picture

    def _load_gone(self) -> dict[str, float]:
        try:
            data = json.loads(self._gone_path.read_text())
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k): float(v) for k, v in data.items() if isinstance(v, int | float)}

    def _save_gone(self) -> None:
        with contextlib.suppress(OSError):
            tmp = self._gone_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._gone))
            tmp.replace(self._gone_path)

    def _mark_gone(self, item: Item) -> None:
        with self._guard:
            self._gone[item.id] = self.wall()
            self._save_gone()
        log.warning("no picture of %s anywhere; left out of lists for a while", item.id)

    def _forget_gone(self, item: Item) -> None:
        if item.id not in self._gone:
            return
        with self._guard:
            if self._gone.pop(item.id, None) is not None:
                self._save_gone()

    def gone(self, item_id: str) -> bool:
        """Whether no address had a picture of the work lately: it is left
        out of lists, and tried again after :data:`GONE_FOR`."""
        return item_id in self.gone_ids()

    def gone_ids(self) -> set[str]:
        """The works with no picture anywhere, as :meth:`gone`."""
        with self._guard:
            since = self.wall() - GONE_FOR
            stale = [k for k, at in self._gone.items() if at < since]
            for key in stale:
                del self._gone[key]
            if stale:
                self._save_gone()
            return set(self._gone)

    def has_image(self, item: Item) -> bool:
        return self.image_path(item).is_file()

    def used_at(self, item: Item) -> float | None:
        """When the original was last downloaded or asked for (wall clock),
        None when it is not here, or here only because the server looked at
        it (:meth:`looked_at`)."""
        try:
            used = self.image_path(item).stat().st_mtime
        except OSError:
            return None
        return used if time.time() - used < LOOKED_AGE else None

    def unavailable(self, item: Item) -> bool:
        """Whether the original failed to download lately (and is not here),
        or the work has no picture anywhere."""
        if self.has_image(item):
            return False
        if self.gone(item.id):
            return True
        failed = self._failed.get(item.id)
        if failed is None:
            return False
        if self.clock() - failed > FAILED_FOR:
            self._failed.pop(item.id, None)
            return False
        return True

    def ensure_image(self, item: Item, urgent: bool = False) -> Path:
        """The display-size original, downloaded if need be; ``urgent``: the
        owner or a change waits for it, it goes before background downloads.

        When the original's own address fails, its mirrors are tried. When
        every address refuses for good, ``Unavailable`` is raised and, for a
        while, raised again at once; a host that is only down or busy raises
        its own error and is asked again next time."""
        path = self.image_path(item)
        if path.is_file():
            with contextlib.suppress(OSError):
                os.utime(path)  # recently used: pruned last
            return path
        if self.unavailable(item):
            raise Unavailable(f"original of {item.id} unavailable (failed lately)")
        with self._holding(f"i:{item.id}", own_copy(item) or item.thumb_url, urgent):
            if not path.is_file():
                img = self._original(item, urgent)
                self._failed.pop(item.id, None)
                self._keep_original(item, img, kept_side(item))
                self._remember_size(item, img)
        self._forget_gone(item)
        return path

    def keep_owned(self, item: Item, data: bytes) -> tuple[str, Image.Image]:
        """Keep the copy the owner brought for ``item`` (a picture's bytes)
        for good; its address (:data:`OWNED`) and the picture. Raises
        ValueError for what is no picture."""
        try:
            img = load_image(data)
        except (OSError, ValueError, Image.DecompressionBombError) as err:
            raise ValueError(f"not a picture: {err}") from err
        name = re.sub(r"[^A-Za-z0-9_-]+", "_", item.id)[:80] + f"-{secrets.token_hex(4)}.jpg"
        self.owned.mkdir(parents=True, exist_ok=True)
        _save_jpeg(img, self.owned / name, OWNED_MAX, 95)
        return OWNED + name, img

    def adopt(self, item: Item, img: Image.Image) -> Path:
        """Keep ``img`` (a sharper copy, :mod:`frame_server.sharper`) as the
        work's original, and its thumbnail from it: the one from before
        showed the old picture in the app's lists (other tones, a frame
        around it) long after the change (Mateusz, 2026-11-04)."""
        path = self.image_path(item)
        with self._lock(f"i:{item.id}"):
            self._keep_original(item, img, IMAGE_MAX)
            self._remember_size(item, img)
            self._failed.pop(item.id, None)
        with self._lock(f"t:{item.id}"):
            _save_jpeg(load_image(path), self.thumb_path(item), THUMB_MAX, 85)
            (self.tiles / self.thumb_path(item).name).unlink(missing_ok=True)
        self._forget_gone(item)
        return path

    def wide_again(self, items: Iterable[Item]) -> int:
        """Once after the update that keeps elongated pictures larger
        (:data:`WIDE`): the kept originals of such works, cut to
        :data:`OLD_KEPT` or less before, downloaded again; the one here
        stays when the source gives no more or fails. How many grew."""
        grown = 0
        for item in items:
            path = self._photo_path(item)
            if item.source in OWN_SOURCES or not path.is_file():
                continue
            try:
                with Image.open(path) as kept:
                    size = kept.size
            except OSError:
                continue
            if not wide(*size) or max(size) > OLD_KEPT:
                continue
            try:
                with self._lock(f"i:{item.id}"):
                    img = self._original(item, False)
                    width, height = kept_size(*img.size)
                    if width * height <= size[0] * size[1]:
                        continue  # the source gives no more
                    self._keep_original(item, img, IMAGE_MAX)
                    self._remember_size(item, img)
            except (httpx.HTTPError, OSError) as err:
                log.info("elongated %s kept as it was: %s", item.id, err)
                continue
            grown += 1
        return grown

    def originals_here(self) -> set[str]:
        """The file stems (``Item.file_stem``) of the originals kept here,
        from one look at their folder."""
        try:
            with os.scandir(self.images) as folder:
                return {entry.name[:-4] for entry in folder if entry.name.endswith(".jpg")}
        except OSError:
            return set()

    def cut_before(self, item: Item) -> bool:
        """Whether the original here was cut to the old limit
        (:data:`OLD_MAX`): its source had more, and may be asked for it."""
        path = self._photo_path(item)
        if item.source in OWN_SOURCES or split_part(item.id) is not None:
            return False
        known = self.known_size(item)
        if (known is not None and max(known) < OLD_MAX) or not path.is_file():
            return False  # its source gave less (no look at the disk)
        try:
            with Image.open(path) as kept:
                size = kept.size
        except OSError:
            return False
        return max(size) == OLD_MAX

    def larger_again(self, item: Item) -> int:
        """The original of ``item``, kept cut to :data:`OLD_MAX`, downloaded
        again in the size originals are kept in now; the one here stays
        when the source gives no more. The bytes it grew by (0: it stays).
        Errors of the download are the caller's."""
        photo, path = self._photo_path(item), self.image_path(item)
        with self._lock(f"i:{item.id}"):
            try:
                with Image.open(photo) as kept:
                    size = kept.size
                before = path.stat().st_size
            except OSError:
                return 0
            img = self._original(item, False)
            width, height = kept_size(*img.size)
            if width * height <= size[0] * size[1]:
                return 0  # the source gives no more
            used = path.stat().st_mtime
            self._keep_original(item, img, kept_side(item))
            os.utime(path, (used, used))  # as lately used as it was
            self._remember_size(item, img)
            return max(path.stat().st_size - before, 1)

    def thin_thumbs_again(self) -> int:
        """Once after the update that keeps elongated thumbnails thicker
        (:func:`thumb_size`): such thumbnails thinner than they are made now
        made again from the original kept here, else let go to be had again
        from the work's addresses when next asked for (the owner's own are
        made from the original only). How many."""
        own = tuple(f"{source}_" for source in OWN_SOURCES)
        changed = 0
        for path in sorted(self.thumbs.glob("*.jpg")):
            try:
                with Image.open(path) as kept:
                    size = kept.size
            except OSError:
                continue
            if not thin_thumb(*size):
                continue
            local = self.images / path.name
            larger = False
            if local.is_file():
                # No lock: the file is replaced whole (_save_jpeg).
                try:
                    original = load_image(local)
                    if larger := min(original.size) > min(size):
                        _save_jpeg(original, path, THUMB_MAX, 85)
                except OSError as err:
                    log.info("thumbnail %s not made again: %s", path.name, err)
            if not larger:
                if path.name.startswith(own):
                    continue
                path.unlink(missing_ok=True)
            changed += 1
        return changed

    def trim_kept(self) -> int:
        """Cut the blank margins off the pictures kept from before
        (:func:`trim_margins`), originals and thumbnails, in place; how many
        changed. The owner's own are left alone (:data:`OWN_SOURCES`)."""
        own = tuple(f"{source}_" for source in OWN_SOURCES)
        changed = 0
        # No locks: a file is replaced whole (_save_jpeg), and a picture
        # downloaded meanwhile comes trimmed already, with nothing to cut.
        for folder, side, quality in (
            (self.images, IMAGE_MAX, 92),
            (self.thumbs, THUMB_MAX, 85),
        ):
            for path in sorted(folder.glob("*.jpg")):
                if path.name.startswith(own) or PART in path.stem:
                    continue
                try:
                    with Image.open(path) as kept:
                        kept.load()
                        img = trim_margins(kept)
                        if img is kept:
                            continue
                        _save_jpeg(img, path, side, quality)
                except OSError as err:
                    log.warning("margins of %s left: %s", path.name, err)
                    continue
                changed += 1
        return changed

    def drop_fragments(self, thumbs: bool = True) -> int:
        """Forget the kept pictures of works' fragments (had again when
        asked for): those kept before 2026-11-09 lost their margins, and a
        trimmed tile does not lie in its place on the whole; those before
        2026-11-10 were kept at 2560 px (``TILE_MAX``)."""
        dropped = 0
        for folder in (self.images, self.thumbs) if thumbs else (self.images,):
            for path in folder.glob(f"*{PART}*.jpg"):
                if split_part(path.stem) is None:
                    continue
                path.unlink(missing_ok=True)
                dropped += 1
        return dropped

    def drop_picture(self, item: Item) -> None:
        """Forget the work's original and thumbnail (another picture takes
        their place): both are had again from its addresses."""
        with self._lock(f"i:{item.id}"):
            self.image_path(item).unlink(missing_ok=True)
            self.full_path(item).unlink(missing_ok=True)
        with self._lock(f"t:{item.id}"):
            self.thumb_path(item).unlink(missing_ok=True)

    def thumb_again(self, item: Item) -> bool:
        """The thumbnail made again from the original kept here, else
        dropped to be had again from the work's addresses (the picture
        changed under it); True when made here."""
        local = self.image_path(item)
        with self._lock(f"t:{item.id}"):
            try:
                img = load_image(local)
            except OSError:
                self.thumb_path(item).unlink(missing_ok=True)
                return False
            _save_jpeg(img, self.thumb_path(item), THUMB_MAX, 85)
            return True

    def _original(self, item: Item, urgent: bool) -> Image.Image:
        fetch = self.fetchers.get(item.source)
        if fetch is not None and item.sharper is None:
            data = fetch(item)
            img = load_image(data)
            img.info[BYTES] = len(data)
            return img
        urls = self._addresses(item, thumb=False)
        mirrored = not urls  # none of its own: the mirrors at once
        if mirrored:
            urls = self._mirrored(item, False, urls)
        refused = True
        sized = sized_copy(item)
        n = 0
        while n < len(urls):
            url = urls[n]
            n += 1
            try:
                # Not an image (a "verify you are human" page): load_image raises.
                return self._download(url, urgent, trim=_trimmed(item.id))
            except (httpx.HTTPError, OSError) as err:
                refused = refused and _refused(err)
                whole = whole_copy(item) if url == sized and _too_large(err) else ""
                if whole and whole not in urls:
                    urls.insert(n, whole)  # smaller than asked: the whole file
                if n == len(urls) and not mirrored:
                    mirrored = True
                    urls = self._mirrored(item, False, urls)
                if n < len(urls):
                    log.info("original of %s from %s failed: %s; next address", item.id, url, err)
                    continue
                if not refused:
                    raise
                self._failed[item.id] = self.clock()
                raise Unavailable(f"original of {item.id} unavailable: {err}") from err
        # A work with no address at all (2026-11-06: it ended the thread
        # fetching the kept works' originals, which then never ran again).
        raise Unavailable(f"no address for the original of {item.id}")

    def picture(self, item: Item, urgent: bool = False) -> tuple[Path, bool]:
        """The original, or its thumbnail when the original cannot be had
        (blurred, but better than nothing for the app to show); the flag
        tells whether it is the original."""
        try:
            return self.ensure_image(item, urgent), True
        except (httpx.HTTPError, OSError):
            return self.ensure_thumb(item, urgent), False

    def store(self, item: Item, data: bytes) -> tuple[int, int]:
        """Keep an uploaded original; returns its size after EXIF rotation."""
        img = load_image(data)
        _save_jpeg(img, self.image_path(item), IMAGE_MAX, 92)
        self.thumb_path(item).unlink(missing_ok=True)
        self.ensure_thumb(item)
        return img.size

    def prune(
        self,
        limit_bytes: int,
        keep: Iterable[Item],
        own: Iterable[Item] = (),
        last: Iterable[Item] = (),
    ) -> int:
        """Delete the least recently used originals until they fit in
        ``limit_bytes``, those of ``last`` (Favourites, playlists) only after
        all the others; returns how many went. Originals of ``keep``
        (pictures about to be shown) stay; those of ``own`` (only copies)
        stay and do not count."""
        outside = {self.image_path(i) for i in own}
        files: dict[Path, os.stat_result] = {}
        for path in own_files(self.images, "*.jpg"):
            if path not in outside:
                with contextlib.suppress(FileNotFoundError):
                    files[path] = path.stat()
        total = sum(st.st_size for st in files.values())
        kept = {self.image_path(i) for i in keep}
        late = {self.image_path(i) for i in last}
        order = sorted(files.keys() - kept, key=lambda p: (p in late, files[p].st_mtime))
        removed = 0
        for path in order:
            if total <= limit_bytes:
                break
            path.unlink(missing_ok=True)
            (self.full / path.name).unlink(missing_ok=True)  # its photograph whole
            total -= files[path].st_size
            removed += 1
        return removed

    def thumbs_size(self) -> int:
        """Bytes of the catalogue's thumbnails: one stat per file (a glob and
        two stats took over a minute on the NAS's cold disk after a start,
        2026-11-04)."""
        return dir_bytes(self.thumbs, ".jpg")

    def prune_thumbs(self, keep: Iterable[Item], spare: int = THUMB_SPARE) -> int:
        """Delete all but the ``spare`` newest thumbnails of works outside
        ``keep`` (works browsed but never kept); returns how many went."""
        kept = {self.thumb_path(i) for i in keep}
        others = sorted(
            (p for p in own_files(self.thumbs, "*.jpg") if p not in kept),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in others[spare:]:
            path.unlink(missing_ok=True)
            (self.tiles / path.name).unlink(missing_ok=True)
        return max(len(others) - spare, 0)

    def remove(self, item: Item) -> None:
        self.thumb_path(item).unlink(missing_ok=True)
        (self.tiles / self.thumb_path(item).name).unlink(missing_ok=True)
        self.image_path(item).unlink(missing_ok=True)
        self.full_path(item).unlink(missing_ok=True)
        with self._guard:
            self._sizes.pop(item.id, None)


class HostGate:
    """At most ``limit`` downloads from one host at once. An urgent one goes
    before every background one still waiting, and may use ``extra`` places
    more: what the owner looks at never waits behind a burst of thumbnails."""

    def __init__(self, limit: int, extra: int = 0) -> None:
        self.limit = limit
        self.extra = extra
        self._running = 0
        self._urgent_waiting = 0
        self._cond = threading.Condition()

    def _free(self, urgent: bool) -> bool:
        if urgent:
            return self._running < self.limit + self.extra
        return self._running < self.limit and self._urgent_waiting == 0

    @contextlib.contextmanager
    def turn(self, urgent: bool = False) -> Iterator[None]:
        with self._cond:
            self._urgent_waiting += urgent
            try:
                self._cond.wait_for(lambda: self._free(urgent))
            finally:
                self._urgent_waiting -= urgent
            self._running += 1
        try:
            yield
        finally:
            with self._cond:
                self._running -= 1
                self._cond.notify_all()
