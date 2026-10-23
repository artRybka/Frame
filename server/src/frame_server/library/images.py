"""Local cache of library images: small thumbnails and display-size originals."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

import httpx
from PIL import Image

from ..imaging.layout import load_image
from .models import Item

THUMB_MAX = 640
IMAGE_MAX = 2560


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
        self._http = http
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
        with self._http() as http:
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

    def ensure_image(self, item: Item) -> Path:
        path = self.image_path(item)
        if path.is_file():
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

    def remove(self, item: Item) -> None:
        self.thumb_path(item).unlink(missing_ok=True)
        self.image_path(item).unlink(missing_ok=True)
