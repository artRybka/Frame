"""Local cache of library images: small thumbnails and display-size originals."""

from __future__ import annotations

import contextlib
import os
import threading
from collections.abc import Callable, Iterable
from pathlib import Path

import httpx
from PIL import Image

from ..imaging.layout import load_image
from .models import Item

THUMB_MAX = 640
IMAGE_MAX = 2560
#: Thumbnails of works that are not in the library (browsed, previewed).
THUMB_SPARE = 500


def _save_jpeg(img: Image.Image, path: Path, max_side: int, quality: int) -> None:
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    tmp = path.with_suffix(".tmp")
    img.save(tmp, "JPEG", quality=quality, optimize=True)
    tmp.replace(path)


class ImageCache:
    def __init__(self, root: Path, http: Callable[[], httpx.Client]) -> None:
        self.thumbs = root / "thumbs"
        self.images = root / "images"
        self.thumbs.mkdir(parents=True, exist_ok=True)
        self.images.mkdir(parents=True, exist_ok=True)
        self.http = http
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock(self, key: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def thumb_path(self, item: Item) -> Path:
        return self.thumbs / f"{item.file_stem}.jpg"

    def image_path(self, item: Item) -> Path:
        return self.images / f"{item.file_stem}.jpg"

    def _download(self, url: str) -> Image.Image:
        with self.http() as http:
            resp = http.get(url)
            resp.raise_for_status()
        return load_image(resp.content)

    def ensure_thumb(self, item: Item) -> Path:
        path = self.thumb_path(item)
        if path.is_file():
            return path
        with self._lock(f"t:{item.id}"):
            if not path.is_file():
                local = self.image_path(item)
                img = load_image(local) if local.is_file() else self._download(item.thumb_url)
                _save_jpeg(img, path, THUMB_MAX, 85)
        return path

    def has_image(self, item: Item) -> bool:
        return self.image_path(item).is_file()

    def ensure_image(self, item: Item) -> Path:
        path = self.image_path(item)
        if path.is_file():
            with contextlib.suppress(OSError):
                os.utime(path)  # recently used: pruned last
            return path
        with self._lock(f"i:{item.id}"):
            if not path.is_file():
                _save_jpeg(self._download(item.image_url or item.thumb_url), path, IMAGE_MAX, 92)
        return path

    def store(self, item: Item, data: bytes) -> tuple[int, int]:
        """Keep an uploaded original; returns its size after EXIF rotation."""
        img = load_image(data)
        _save_jpeg(img, self.image_path(item), IMAGE_MAX, 92)
        self.thumb_path(item).unlink(missing_ok=True)
        self.ensure_thumb(item)
        return img.size

    def prune(self, limit_bytes: int, keep: Iterable[Item]) -> int:
        """Delete the least recently used originals until all of them fit in
        ``limit_bytes``; returns how many went. Originals of ``keep`` stay:
        pictures about to be shown and those that cannot be downloaded again."""
        sizes = {p: p.stat().st_size for p in self.images.glob("*.jpg")}
        total = sum(sizes.values())
        kept = {self.image_path(i) for i in keep}
        removed = 0
        for path in sorted(sizes.keys() - kept, key=lambda p: p.stat().st_mtime):
            if total <= limit_bytes:
                break
            path.unlink(missing_ok=True)
            total -= sizes[path]
            removed += 1
        return removed

    def prune_thumbs(self, keep: Iterable[Item], spare: int = THUMB_SPARE) -> int:
        """Delete all but the ``spare`` newest thumbnails of works outside
        ``keep`` (works browsed but never kept); returns how many went."""
        kept = {self.thumb_path(i) for i in keep}
        others = sorted(
            (p for p in self.thumbs.glob("*.jpg") if p not in kept),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in others[spare:]:
            path.unlink(missing_ok=True)
        return max(len(others) - spare, 0)

    def remove(self, item: Item) -> None:
        self.thumb_path(item).unlink(missing_ok=True)
        self.image_path(item).unlink(missing_ok=True)
