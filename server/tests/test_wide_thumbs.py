"""Thumbnails of elongated works kept thick enough for a square tile
(images.thumb_size): a handscroll's came 640 × 26 px and its tile was a blur
(Mateusz, 2026-11-11)."""

from __future__ import annotations

import io
from pathlib import Path

import httpx
from PIL import Image

from frame_server.library.images import (
    THUMB_LONG,
    THUMB_MAX,
    ImageCache,
    thin_thumb,
    thumb_copy,
    thumb_size,
)
from frame_server.library.models import Item


def _jpeg(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 180, 150)).save(buf, "JPEG")
    return buf.getvalue()


def _cache(tmp_path: Path, files: dict[str, tuple[int, int]], asked: list[str]) -> ImageCache:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        asked.append(url)
        if url not in files:
            return httpx.Response(404)
        jpeg = _jpeg(*files[url])
        return httpx.Response(200, content=jpeg, headers={"content-type": "image/jpeg"})

    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    cache.sleep = lambda _seconds: None  # type: ignore[method-assign]
    return cache


def test_ordinary_thumbnails_keep_the_long_side() -> None:
    assert thumb_size(4000, 3000) == (640, 480)
    assert thumb_size(3000, 4000) == (480, 640)
    assert thumb_size(5120, 2560) == (640, 320)  # 2:1, the edge
    assert thumb_size(500, 400) == (500, 400)  # never enlarged


def test_elongated_thumbnails_keep_the_short_side() -> None:
    # Cleveland's print of "Flowers of Four Seasons", 24:1: kept whole.
    assert thumb_size(3400, 140) == (3400, 140)
    # The same scroll larger: 320 px tall, not 26.
    assert thumb_size(21870, 900) == (7776, 320)
    # Tall ones too.
    assert thumb_size(1000, 9000) == (320, 2880)
    # The long side has a limit.
    width, height = thumb_size(76716, 2577)
    assert width <= THUMB_LONG and height == round(2577 * THUMB_LONG / 76716)
    assert thin_thumb(640, 26)
    assert not thin_thumb(640, 480)  # not elongated
    assert not thin_thumb(7776, 320)
    assert not thin_thumb(THUMB_LONG, 275)  # as thick as the limit allows


def test_sized_sources_are_asked_for_a_thicker_thumbnail() -> None:
    iiif = "https://example.org/iiif/x/full/!2560,2560/0/default.jpg"
    item = Item(
        id="nga:1", source="nga", source_id="1", image_url=iiif,
        thumb_url="https://example.org/iiif/x/full/600,/0/default.jpg", width=16555, height=720,
    )  # fmt: skip
    assert thumb_copy(item) == "https://example.org/iiif/x/full/!7358,7358/0/default.jpg"
    item.width, item.height = 4000, 3000
    assert thumb_copy(item) == ""  # ordinary: its thumbnail address will do


def test_a_thin_thumbnail_comes_from_a_larger_address(tmp_path: Path) -> None:
    web, larger = "https://cdn/1977.4_web.jpg", "https://cdn/1977.4_print.jpg"
    asked: list[str] = []
    cache = _cache(tmp_path, {web: (900, 37), larger: (3400, 140)}, asked)
    item = Item(
        id="cma:149109", source="cma", source_id="149109",
        image_url=larger, thumb_url=web, width=900, height=37,
    )  # fmt: skip
    with Image.open(cache.ensure_thumb(item)) as thumb:
        assert thumb.size == (3400, 140)
    assert asked == [web, larger]


def test_an_ordinary_thumbnail_asks_nothing_more(tmp_path: Path) -> None:
    thumb, image = "https://cdn/t.jpg", "https://cdn/i.jpg"
    asked: list[str] = []
    cache = _cache(tmp_path, {thumb: (600, 450), image: (4000, 3000)}, asked)
    item = Item(id="met:1", source="met", source_id="1", image_url=image, thumb_url=thumb)
    with Image.open(cache.ensure_thumb(item)) as kept:
        assert kept.size == (600, 450)
    assert asked == [thumb]


def test_a_thin_thumbnail_stays_when_nothing_larger_comes(tmp_path: Path) -> None:
    thumb, image = "https://cdn/t.jpg", "https://cdn/i.jpg"
    asked: list[str] = []
    cache = _cache(tmp_path, {thumb: (900, 37)}, asked)  # the original is refused
    item = Item(id="met:2", source="met", source_id="2", image_url=image, thumb_url=thumb)
    with Image.open(cache.ensure_thumb(item)) as kept:
        assert kept.size == (900, 37)
    assert asked == [thumb, image]


def test_thin_thumbnails_kept_from_before_are_made_again_once(tmp_path: Path) -> None:
    cache = _cache(tmp_path, {}, [])
    item = Item(id="cma:1", source="cma", source_id="1", image_url="", thumb_url="")
    other = Item(id="cma:2", source="cma", source_id="2", image_url="", thumb_url="")
    own = Item(id="icloud:3", source="icloud", source_id="3", image_url="", thumb_url="")
    square = Item(id="cma:4", source="cma", source_id="4", image_url="", thumb_url="")
    # A scroll with its original here, one without, the owner's panorama
    # without, and an ordinary work.
    Image.new("RGB", (THUMB_MAX, 26)).save(cache.thumb_path(item))
    Image.new("RGB", (13968, 469)).save(cache.image_path(item))
    Image.new("RGB", (THUMB_MAX, 26)).save(cache.thumb_path(other))
    Image.new("RGB", (THUMB_MAX, 100)).save(cache.thumb_path(own))
    Image.new("RGB", (THUMB_MAX, THUMB_MAX)).save(cache.thumb_path(square))
    assert cache.thin_thumbs_again() == 2
    with Image.open(cache.thumb_path(item)) as thumb:
        assert thumb.size == thumb_size(13968, 469)
        assert min(thumb.size) > 250
    assert not cache.thumb_path(other).exists()  # had again when asked for
    assert cache.thumb_path(own).exists()
    assert cache.thumb_path(square).exists()
