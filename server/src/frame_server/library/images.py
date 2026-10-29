"""Local cache of library images: small thumbnails and display-size originals."""

from __future__ import annotations

import contextlib
import os
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from PIL import Image

from ..fsutil import own_files
from ..imaging.layout import load_image
from .models import Item

THUMB_MAX = 640
IMAGE_MAX = 2560
#: Thumbnails of works that are not in the library (browsed, previewed).
THUMB_SPARE = 500
#: Downloads at once from one host. Commons answers more than two parallel
#: media requests with 429; museum CDNs throttle bursts too.
HOST_LIMITS = {"upload.wikimedia.org": 2}
HOST_LIMIT = 4
#: Extra downloads at once for what the owner looks at now (the card's
#: original, a preview), so it never waits for the background's; hosts with
#: a limit of their own in HOST_LIMITS get none.
URGENT_EXTRA = 2
#: Answers worth another try (throttled or briefly down), and how many tries.
RETRY_STATUS = {408, 429, 500, 502, 503, 504}
ATTEMPTS = 3


def _save_jpeg(img: Image.Image, path: Path, max_side: int, quality: int) -> None:
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    tmp = path.with_suffix(".tmp")
    img.save(tmp, "JPEG", quality=quality, optimize=True)
    tmp.replace(path)


def _retry_after(resp: httpx.Response, attempt: int) -> float:
    try:
        wait = float(resp.headers.get("retry-after", ""))
    except ValueError:
        wait = 2.0 * attempt
    return min(max(wait, 0.5), 8.0)


class ImageCache:
    def __init__(self, root: Path, http: Callable[[], httpx.Client]) -> None:
        self.thumbs = root / "thumbs"
        self.images = root / "images"
        self.thumbs.mkdir(parents=True, exist_ok=True)
        self.images.mkdir(parents=True, exist_ok=True)
        self.http = http
        #: Sources whose originals need more than a plain download (by source).
        self.fetchers: dict[str, Callable[[Item], bytes]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._gates: dict[str, HostGate] = {}
        self._guard = threading.Lock()
        self.sleep: Callable[[float], None] = time.sleep

    def _lock(self, key: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def thumb_path(self, item: Item) -> Path:
        return self.thumbs / f"{item.file_stem}.jpg"

    def image_path(self, item: Item) -> Path:
        return self.images / f"{item.file_stem}.jpg"

    def _gate(self, host: str) -> HostGate:
        with self._guard:
            if host not in self._gates:
                limit = HOST_LIMITS.get(host, HOST_LIMIT)
                extra = 0 if host in HOST_LIMITS else URGENT_EXTRA
                self._gates[host] = HostGate(limit, extra)
            return self._gates[host]

    def _download(self, url: str, urgent: bool = False) -> Image.Image:
        """A few downloads per host at a time, ``urgent`` ones first; throttled
        ones are tried again after the wait the host asks for (a few seconds
        at most)."""
        gate = self._gate(urlsplit(url).hostname or "")
        with gate.turn(urgent), self.http() as http:
            for attempt in range(1, ATTEMPTS + 1):
                try:
                    resp = http.get(url)
                except httpx.TransportError:
                    if attempt == ATTEMPTS:
                        raise
                    self.sleep(attempt)
                    continue
                if resp.status_code in RETRY_STATUS and attempt < ATTEMPTS:
                    self.sleep(_retry_after(resp, attempt))
                    continue
                resp.raise_for_status()
                return load_image(resp.content)
        raise AssertionError("unreachable")

    def sample(self, url: str) -> Image.Image:
        """A picture downloaded to be looked at, not kept."""
        return self._download(url)

    def ensure_thumb(self, item: Item, urgent: bool = False) -> Path:
        path = self.thumb_path(item)
        if path.is_file():
            return path
        with self._lock(f"t:{item.id}"):
            if not path.is_file():
                local = self.image_path(item)
                img = (
                    load_image(local) if local.is_file() else self._download(item.thumb_url, urgent)
                )
                _save_jpeg(img, path, THUMB_MAX, 85)
        return path

    def has_image(self, item: Item) -> bool:
        return self.image_path(item).is_file()

    def ensure_image(self, item: Item, urgent: bool = False) -> Path:
        """The display-size original, downloaded if need be; ``urgent``: the
        owner or a change waits for it, it goes before background downloads."""
        path = self.image_path(item)
        if path.is_file():
            with contextlib.suppress(OSError):
                os.utime(path)  # recently used: pruned last
            return path
        with self._lock(f"i:{item.id}"):
            if not path.is_file():
                fetch = self.fetchers.get(item.source)
                img = (
                    load_image(fetch(item))
                    if fetch is not None
                    else self._download(item.image_url or item.thumb_url, urgent)
                )
                _save_jpeg(img, path, IMAGE_MAX, 92)
        return path

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
        return sum(p.stat().st_size for p in own_files(self.thumbs, "*.jpg"))

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
