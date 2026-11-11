"""Local cache of library images: small thumbnails and display-size originals."""

from __future__ import annotations

import contextlib
import json
import logging
import math
import os
import re
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from PIL import Image

from ..fsutil import dir_bytes, own_files
from ..imaging.layout import load_image
from ..imaging.margins import trim_margins
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
IMAGE_MAX = 2560
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
#: A fragment's picture is kept this large (``kept_side``): a tile of a
#: Commons tile set is looked at closely, 2560 showed a twelfth of its
#: width (Mateusz 2026-11-10).
TILE_MAX = COMMONS_WIDTH
#: Sources whose works' sizes are their files' own and whose addresses ask
#: for a size (IIIF ``full/!2560,2560``, the Smithsonian's ``max=2560``): an
#: elongated work (:data:`WIDE`) is asked in the size it is kept in.
SIZED = ("nga", "yale", "smk", "si", "courtauld")
_IIIF_FIT = re.compile(rf"/full/!{IMAGE_MAX},{IMAGE_MAX}/")
_SI_MAX = re.compile(rf"([?&]max=){IMAGE_MAX}\b")
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


def display_copy(item: Item) -> str:
    """The address of ``item``'s original, or of Commons' smaller rendition
    of it when the file is far larger than the frame needs; a sharper copy
    from another source (``item.sharper``) instead, when it has one."""
    if item.sharper is not None:
        return item.sharper.url
    return own_copy(item)


def own_copy(item: Item) -> str:
    """:func:`display_copy` of the work's own source, never another's: in
    the size it is kept in when elongated (:func:`wide_copy`)."""
    return wide_copy(item) or usual_copy(item)


def usual_copy(item: Item) -> str:
    """The work's own address as the source gives it, or Commons' rendition
    of a file far larger than the frame needs."""
    url = item.image_url
    if item.width and item.width > COMMONS_WIDTH:
        return commons_rendition(url, COMMONS_WIDTH, item.width) or url
    return url


def wide_copy(item: Item) -> str:
    """An elongated work's own address asking for more than its usual
    (:func:`usual_copy`) does, in the size it is kept in (:func:`kept_size`);
    "" for any other work, or a source that gives no more."""
    width, height, url = item.width, item.height, item.image_url
    if not width or not height or not wide(width, height):
        return ""
    long = max(kept_size(width, height))
    if long <= IMAGE_MAX:
        return ""
    if item.source in SIZED:
        if _IIIF_FIT.search(url):
            return _IIIF_FIT.sub(f"/full/!{long},{long}/", url)
        if _SI_MAX.search(url):
            return _SI_MAX.sub(rf"\g<1>{long}", url)
    if (
        item.source == "wmc"
        and width > COMMONS_WIDTH
        and long > COMMONS_WIDTH
        and width * height <= COMMONS_WHOLE
        and extension(url) in ("jpg", "jpeg", "png")
    ):
        return url
    return ""


def thumb_copy(item: Item) -> str:
    """An elongated work's address asking for its thumbnail in the size it
    is kept in (:func:`thumb_size`), from a source whose addresses ask for a
    size (:data:`SIZED`, Commons); "" for any other work or source."""
    width, height, url = item.width, item.height, item.image_url
    if not width or not height or not wide(width, height):
        return ""
    w, h = thumb_size(width, height)
    long = max(w, h)
    if item.source in SIZED:
        if _IIIF_FIT.search(url):
            return _IIIF_FIT.sub(f"/full/!{long},{long}/", url)
        if _SI_MAX.search(url):
            return _SI_MAX.sub(rf"\g<1>{long}", url)
    if item.source == "wmc" and (rendition := commons_rendition(url, w, width)):
        return rendition
    return ""


class ImageCache:
    def __init__(self, root: Path, http: Callable[[], httpx.Client]) -> None:
        self.thumbs = root / "thumbs"
        self.images = root / "images"
        self.thumbs.mkdir(parents=True, exist_ok=True)
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

    def image_path(self, item: Item) -> Path:
        return self.images / f"{item.file_stem}.jpg"

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
        at most)."""
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
                img = load_image(local) if local.is_file() else self._thumbnail(item, urgent)
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
            first.append(usual)  # the larger size refused (wide_copy)
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
        None when it is not here."""
        try:
            return self.image_path(item).stat().st_mtime
        except OSError:
            return None

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
                _save_jpeg(img, path, kept_side(item), 92)
                self._remember_size(item, img)
        self._forget_gone(item)
        return path

    def adopt(self, item: Item, img: Image.Image) -> Path:
        """Keep ``img`` (a sharper copy, :mod:`frame_server.sharper`) as the
        work's original, and its thumbnail from it: the one from before
        showed the old picture in the app's lists (other tones, a frame
        around it) long after the change (Mateusz, 2026-11-04)."""
        path = self.image_path(item)
        with self._lock(f"i:{item.id}"):
            _save_jpeg(img, path, IMAGE_MAX, 92)
            self._remember_size(item, img)
            self._failed.pop(item.id, None)
        with self._lock(f"t:{item.id}"):
            _save_jpeg(img, self.thumb_path(item), THUMB_MAX, 85)
        self._forget_gone(item)
        return path

    def wide_again(self, items: Iterable[Item]) -> int:
        """Once after the update that keeps elongated pictures larger
        (:data:`WIDE`): the kept originals of such works, cut to
        :data:`OLD_KEPT` or less before, downloaded again; the one here
        stays when the source gives no more or fails. How many grew."""
        grown = 0
        for item in items:
            path = self.image_path(item)
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
                    _save_jpeg(img, path, IMAGE_MAX, 92)
                    self._remember_size(item, img)
            except (httpx.HTTPError, OSError) as err:
                log.info("elongated %s kept as it was: %s", item.id, err)
                continue
            grown += 1
        return grown

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
        n = 0
        while n < len(urls):
            url = urls[n]
            n += 1
            try:
                # Not an image (a "verify you are human" page): load_image raises.
                return self._download(url, urgent, trim=_trimmed(item.id))
            except (httpx.HTTPError, OSError) as err:
                refused = refused and _refused(err)
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
        return max(len(others) - spare, 0)

    def remove(self, item: Item) -> None:
        self.thumb_path(item).unlink(missing_ok=True)
        self.image_path(item).unlink(missing_ok=True)
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
