"""Thumbnail downloads: throttled answers are tried again, a few per host."""

from __future__ import annotations

import io
import threading
import time
from pathlib import Path

import httpx
import pytest
from PIL import Image

from frame_server.library.images import ImageCache
from frame_server.library.models import Item


def _jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 80, 40)).save(out, "JPEG")
    return out.getvalue()


def _item(n: int, host: str = "upload.wikimedia.org") -> Item:
    return Item(
        id=f"commons:{n}",
        source="commons",
        source_id=str(n),
        title=f"Work {n}",
        thumb_url=f"https://{host}/thumb/{n}.jpg",
    )


def test_throttled_thumbnail_is_tried_again(tmp_path: Path) -> None:
    answers = [
        httpx.Response(429, headers={"Retry-After": "1"}),
        httpx.Response(200, content=_jpeg()),
    ]
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return answers.pop(0)

    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    waits: list[float] = []
    cache.sleep = waits.append
    path = cache.ensure_thumb(_item(1))
    assert path.is_file()
    assert len(seen) == 2
    assert waits == [1.0]


def test_gives_up_after_a_few_tries(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    cache.sleep = lambda _: None
    with pytest.raises(httpx.HTTPStatusError):
        cache.ensure_thumb(_item(2))
    assert calls == 3
    assert not cache.thumb_path(_item(2)).exists()


def test_missing_thumbnail_is_not_retried(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404)

    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(httpx.HTTPStatusError):
        cache.ensure_thumb(_item(3))
    assert calls == 1


@pytest.mark.parametrize(("host", "limit"), [("upload.wikimedia.org", 2), ("www.artic.edu", 4)])
def test_parallel_downloads_per_host_are_limited(tmp_path: Path, host: str, limit: int) -> None:
    running = 0
    peak = 0
    lock = threading.Lock()
    picture = _jpeg()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.05)
        with lock:
            running -= 1
        return httpx.Response(200, content=picture)

    cache = ImageCache(tmp_path, lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    threads = [
        threading.Thread(target=cache.ensure_thumb, args=(_item(n, host),)) for n in range(10)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak == limit
    assert len(list(cache.thumbs.glob("*.jpg"))) == 10
