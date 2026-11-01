"""Shapes of museum works whose source gives no size, measured on their
thumbnails so that the app's grid does not show them all as landscape."""

from __future__ import annotations

import io
import threading
from pathlib import Path

import httpx
from PIL import Image

from frame_server.library.images import ImageCache
from frame_server.library.importer import Importer
from frame_server.library.models import Item
from frame_server.library.repo import Library


def _jpeg(width: int, height: int) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (200, 80, 40)).save(out, "JPEG")
    return out.getvalue()


def _item(n: int, width: int | None = None, height: int | None = None) -> Item:
    return Item(
        id=f"europeana:{n}",
        source="europeana",
        source_id=str(n),
        title=f"Work {n}",
        thumb_url=f"https://api.europeana.eu/thumbnail/v3/{n}?size=w400",
        width=width,
        height=height,
    )


def _importer(tmp_path: Path, handler: object) -> Importer:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    cache = ImageCache(tmp_path / "cache", lambda: httpx.Client(transport=transport))
    return Importer(Library(tmp_path / "lib.db"), cache, None)  # type: ignore[arg-type]


def test_works_without_size_are_measured_on_small_thumbnails(tmp_path: Path) -> None:
    seen: list[str] = []
    shapes = {"1": (30, 60), "2": (80, 40)}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        n = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, content=_jpeg(*shapes[n]))

    importer = _importer(tmp_path, handler)
    items = [_item(1), _item(2), _item(3, 300, 100)]
    importer.measure(items)

    assert importer.known_aspect(items[0]) == 0.5
    assert importer.known_aspect(items[1]) == 2.0
    assert importer.known_aspect(items[2]) == 3.0  # the source's own size
    assert len(seen) == 2
    assert all("size=w200" in url for url in seen)
    # Known now: not asked again.
    importer.measure(items)
    assert len(seen) == 2


def test_measuring_waits_only_so_long(tmp_path: Path) -> None:
    release = threading.Event()

    def handler(request: httpx.Request) -> httpx.Response:
        release.wait(5)
        return httpx.Response(200, content=_jpeg(30, 60))

    importer = _importer(tmp_path, handler)
    item = _item(1)
    importer.measure([item], seconds=0.05)
    assert importer.known_aspect(item) is None
    release.set()


def test_a_thumbnail_that_fails_leaves_the_shape_unknown(tmp_path: Path) -> None:
    importer = _importer(tmp_path, lambda request: httpx.Response(404))
    item = _item(1)
    importer.measure([item])
    assert importer.known_aspect(item) is None


def test_kept_thumbnail_and_library_copy_tell_the_shape(tmp_path: Path) -> None:
    importer = _importer(tmp_path, lambda request: httpx.Response(500))
    kept = _item(1)
    importer.cache.thumb_path(kept).write_bytes(_jpeg(60, 30))
    assert importer.known_aspect(kept) == 2.0

    held = _item(2)
    importer.library.upsert(held.model_copy(update={"width": 100, "height": 400}))
    assert importer.known_aspect(held) == 0.25
