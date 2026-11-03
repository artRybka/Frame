"""Where one photograph of a work lies on another.

Two copies of the same painting (a museum's and a sharper one picked
later, ``frame_server.sharper``) differ in size, in what of the frame or
the margin they show and in colour. A page's boxes were drawn on one of
them; to cut its details from the other, the boxes are carried over by
the scale and the shift that lay the first on the second.

Both are compared as edges (the gradient's strength), small: the first
at a range of scales against the second, each by a normalised cross
correlation over every shift (masked, so that a copy with a margin is
compared only where the two overlap), the best one kept.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

#: The second copy's longer side when compared (pixels).
SIDE = 200
#: The first copy's size against the second's, tried: from a copy with a
#: wide margin to one cut close.
SCALES = np.exp(np.linspace(np.log(0.55), np.log(1.8), 80))
#: The least of the smaller picture that must overlap the other.
OVERLAP = 0.6
#: A fit worse than this is no fit.
LEAST = 0.35


@dataclass(frozen=True)
class Fit:
    """``(x, y)`` on the first copy, as fractions of its sides, lies at
    ``(sx * x + tx, sy * y + ty)`` on the second."""

    sx: float
    sy: float
    tx: float
    ty: float
    #: How well the edges matched (normalised cross correlation, up to 1).
    score: float

    def box(self, x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
        return self.sx * x + self.tx, self.sy * y + self.ty, self.sx * w, self.sy * h


def _edges(img: Image.Image, size: tuple[int, int]) -> np.ndarray:
    grey = np.asarray(img.convert("L").resize(size, Image.Resampling.BILINEAR), dtype=np.float64)
    gy, gx = np.gradient(grey)
    return np.hypot(gx, gy)


def _correlate(a: np.ndarray, b: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Sum over the overlap of ``a`` shifted by every offset times ``b``:
    entry ``[i, j]`` for ``a`` placed at ``(i - a.rows + 1, j - a.cols + 1)``."""
    fa = np.fft.rfft2(a[::-1, ::-1], shape)
    fb = np.fft.rfft2(b, shape)
    return np.fft.irfft2(fa * fb, shape)


def _best(a: np.ndarray, b: np.ndarray) -> tuple[float, int, int]:
    """The best masked normalised cross correlation of ``a`` over ``b``, and
    where ``a``'s top left corner then lies on ``b``."""
    ha, wa = a.shape
    hb, wb = b.shape
    shape = (ha + hb - 1, wa + wb - 1)
    ones_a, ones_b = np.ones_like(a), np.ones_like(b)
    n = _correlate(ones_a, ones_b, shape)
    sa = _correlate(a, ones_b, shape)
    sb = _correlate(ones_a, b, shape)
    saa = _correlate(a * a, ones_b, shape)
    sbb = _correlate(ones_a, b * b, shape)
    sab = _correlate(a, b, shape)
    least = OVERLAP * min(ha * wa, hb * wb)
    n = np.round(n)
    ok = n >= least
    safe = np.where(ok, n, 1.0)
    cov = sab - sa * sb / safe
    var = (saa - sa * sa / safe) * (sbb - sb * sb / safe)
    score = np.where(ok & (var > 1e-9), cov / np.sqrt(np.maximum(var, 1e-9)), -1.0)
    i, j = np.unravel_index(int(np.argmax(score)), score.shape)
    return float(score[i, j]), int(i) - ha + 1, int(j) - wa + 1


def _search(
    first: Image.Image, second: Image.Image, side: int, scales: np.ndarray
) -> tuple[float, float, int, int, tuple[int, int], tuple[int, int]] | None:
    w2, h2 = second.size
    k = side / max(w2, h2)
    size2 = (max(round(w2 * k), 8), max(round(h2 * k), 8))
    b = _edges(second, size2)
    w1, h1 = first.size
    best = None
    for scale in scales:
        # ``first``'s longer side at ``scale`` times the second's.
        f = scale * max(size2) / max(w1, h1)
        size1 = (max(round(w1 * f), 8), max(round(h1 * f), 8))
        if size1[0] > 3 * size2[0] or size1[1] > 3 * size2[1]:
            continue
        score, top, left = _best(_edges(first, size1), b)
        if best is None or score > best[0]:
            best = (score, float(scale), top, left, size1, size2)
    return best


def align(first: Image.Image, second: Image.Image) -> Fit | None:
    """Where ``first`` lies on ``second``; None when the two do not match
    well enough to say. Coarse over all :data:`SCALES`, then fine around
    the best."""
    first, second = first.convert("RGB"), second.convert("RGB")
    first.thumbnail((4 * SIDE, 4 * SIDE))
    second.thumbnail((4 * SIDE, 4 * SIDE))
    coarse = _search(first, second, SIDE // 2, SCALES[::2])
    if coarse is None:
        return None
    fine = _search(first, second, SIDE, coarse[1] * np.exp(np.linspace(-0.05, 0.05, 11)))
    if fine is None or fine[0] < LEAST:
        return None
    score, _, top, left, size1, size2 = fine
    return Fit(
        sx=size1[0] / size2[0],
        sy=size1[1] / size2[1],
        tx=left / size2[0],
        ty=top / size2[1],
        score=score,
    )
