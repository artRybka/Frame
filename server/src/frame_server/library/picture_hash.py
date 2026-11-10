"""A picture's difference hash: copies of one scan found whoever made them.

Copies of a work are laid over each other per artist (``twins``), but an
artist is written many ways ("Johannes Vermeer van Delft", "rijksmuseum" as
Openverse's maker, nobody at all), and a copy under another name is never
compared. A 256-bit difference hash of the thumbnail (brighter or darker
than the next pixel, on a 17×16 grey grid) tells the same scan anywhere:
on Vermeer's thumbnails, copies of one scan differ in 7–37 bits, other
works in 107–153, a detail or a frame around the painting in 124–132
(Mateusz 2026-11-10). Two pictures this close are then laid over each other
(``likeness``) before they count as one work.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from ..imaging.layout import load_image

#: The grid's side: 16×16 differences, 256 bits.
SIDE = 16
#: No telling (a missing or broken file).
NONE = "-"


def picture_hash(path: Path) -> str:
    """The hash of the picture at ``path`` as 64 hex digits; :data:`NONE`
    when it can't be read."""
    try:
        img = load_image(path).convert("L")
    except Exception:  # a broken file: no telling
        return NONE
    small = np.asarray(img.resize((SIDE + 1, SIDE), Image.Resampling.LANCZOS), dtype=np.int16)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return np.packbits(bits).tobytes().hex()


def words(hashes: list[str]) -> np.ndarray:
    """Hashes as rows of four 64-bit words, for :func:`distances`."""
    if not hashes:
        return np.zeros((0, 4), dtype=np.uint64)
    raw = b"".join(bytes.fromhex(h) for h in hashes)
    return np.frombuffer(raw, dtype=">u8").astype(np.uint64).reshape(-1, 4)


def distances(one: np.ndarray, rows: np.ndarray) -> np.ndarray:
    """How many bits each of ``rows`` differs from ``one`` (a row of
    :func:`words`)."""
    if not len(rows):
        return np.zeros(0, dtype=np.int64)
    return np.bitwise_count(rows ^ one).sum(axis=1).astype(np.int64)


def distance(a: str, b: str) -> int:
    """Bits two hashes differ in."""
    return int(distances(words([a])[0], words([b]))[0])
