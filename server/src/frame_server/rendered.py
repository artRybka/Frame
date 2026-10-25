"""Finished renders kept for a while, so a picture drawn ahead of its turn
(or drawn again with the same settings) is published without the wait.

A render takes seconds on a NAS; the player draws the next picture while the
current one is on the frame, and the change then only writes files.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from collections.abc import Callable, Sequence
from concurrent.futures import Future
from dataclasses import dataclass

#: Renders kept: the next picture, the current one and one spare.
KEEP = 3


@dataclass(frozen=True)
class Rendered:
    data: bytes  # what the panel gets
    ext: str
    preview_png: bytes  # what the app shows


def render_key(images: Sequence[bytes], *parts: str) -> str:
    """Identifies a render by its pictures' contents and everything else
    that shapes it (settings, palette, format)."""
    digest = hashlib.blake2b(digest_size=20)
    for image in images:
        digest.update(hashlib.blake2b(image, digest_size=20).digest())
    for part in parts:
        digest.update(b"\0" + part.encode())
    return digest.hexdigest()


class RenderCache:
    """Thread-safe; a render asked for while the same one is under way waits
    for it instead of starting again."""

    def __init__(self, keep: int = KEEP) -> None:
        self.keep = keep
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, Future[Rendered]] = OrderedDict()

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._entries

    def get(self, key: str, make: Callable[[], Rendered]) -> Rendered:
        with self._lock:
            future = self._entries.get(key)
            mine = future is None
            if future is None:
                future = self._entries[key] = Future()
                self._evict()
            else:
                self._entries.move_to_end(key)
        if mine:
            try:
                future.set_result(make())
            except BaseException as err:
                with self._lock:
                    if self._entries.get(key) is future:
                        del self._entries[key]
                future.set_exception(err)
                raise
        return future.result()

    def _evict(self) -> None:
        # Oldest first; one still being drawn stays (someone waits for it).
        for key in list(self._entries):
            if len(self._entries) <= self.keep:
                return
            if self._entries[key].done():
                del self._entries[key]
