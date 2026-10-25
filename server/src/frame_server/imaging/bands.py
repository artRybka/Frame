"""Per-pixel work in bands of rows, on all cores.

numpy streams every intermediate of a whole 2560x1440 float picture through
memory; in bands of a few dozen rows they stay in the CPU cache, which alone
is several times quicker, and numpy lets go of the GIL, so the bands also
run side by side. Each pixel is computed exactly as before: the result is
the same to the bit.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import numpy as np

BAND = 64  # rows

# Never wait on this pool from inside one of its own tasks: it could deadlock.
pool = ThreadPoolExecutor(max_workers=os.cpu_count() or 1, thread_name_prefix="pixels")


def by_rows(fn: Callable[[np.ndarray], np.ndarray], image: np.ndarray) -> np.ndarray:
    """``fn(image)`` for an ``fn`` that treats every pixel on its own."""
    height = image.shape[0]
    first = fn(image[:BAND])
    out = np.empty((height, *first.shape[1:]), dtype=first.dtype)
    out[:BAND] = first

    def band(y: int) -> None:
        out[y : y + BAND] = fn(image[y : y + BAND])

    for _ in pool.map(band, range(BAND, height, BAND)):
        pass
    return out
