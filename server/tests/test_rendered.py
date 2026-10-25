from __future__ import annotations

import threading
import time

import pytest

from frame_server.rendered import RenderCache, Rendered, render_key


def _rendered(tag: str) -> Rendered:
    return Rendered(tag.encode(), "png", b"preview")


def test_key_follows_pictures_and_settings() -> None:
    key = render_key([b"a"], "settings", "palette")
    assert key == render_key([b"a"], "settings", "palette")
    assert key != render_key([b"b"], "settings", "palette")
    assert key != render_key([b"a"], "other", "palette")
    assert render_key([b"a", b"b"]) != render_key([b"ab"])


def test_cache_renders_once_and_forgets_the_oldest() -> None:
    cache = RenderCache(keep=2)
    calls: list[str] = []

    def make(tag: str):
        return lambda: calls.append(tag) or _rendered(tag)

    assert cache.get("a", make("a")).data == b"a"
    assert cache.get("a", make("again")).data == b"a"
    cache.get("b", make("b"))
    cache.get("c", make("c"))
    assert calls == ["a", "b", "c"]
    assert "a" not in cache and "b" in cache and "c" in cache


def test_a_render_under_way_is_waited_for() -> None:
    cache = RenderCache()
    started, calls = threading.Event(), []

    def slow() -> Rendered:
        calls.append(1)
        started.set()
        time.sleep(0.2)
        return _rendered("slow")

    worker = threading.Thread(target=cache.get, args=("k", slow))
    worker.start()
    started.wait()
    assert cache.get("k", lambda: _rendered("second")).data == b"slow"
    worker.join()
    assert calls == [1]


def test_a_failed_render_is_not_kept() -> None:
    cache = RenderCache()

    def fail() -> Rendered:
        raise ValueError("broken picture")

    with pytest.raises(ValueError):
        cache.get("k", fail)
    assert "k" not in cache
    assert cache.get("k", lambda: _rendered("ok")).data == b"ok"
