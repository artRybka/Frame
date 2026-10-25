"""Error-diffusion dithering onto an arbitrary small palette.

Error is accumulated in linear light (inks mix like light on the paper);
the nearest ink is picked either in OKLab (perceptual, default) or in
linear RGB. Kernels are the classic ones; serpentine scanning and error
clamping keep "worms" and colour bleeding in check.
"""

from __future__ import annotations

from enum import StrEnum

import numba
import numpy as np

from .color import OKLAB_M1, OKLAB_M2, FloatArray, linear_to_oklab


class Kernel(StrEnum):
    FLOYD_STEINBERG = "floyd-steinberg"
    ATKINSON = "atkinson"
    JARVIS = "jarvis"
    STUCKI = "stucki"
    BURKES = "burkes"
    SIERRA = "sierra"
    SIERRA_LITE = "sierra-lite"


# (dy, dx, weight) relative to the current pixel, for left-to-right scanning.
_KERNELS: dict[Kernel, tuple[list[tuple[int, int, float]], float]] = {
    Kernel.FLOYD_STEINBERG: ([(0, 1, 7), (1, -1, 3), (1, 0, 5), (1, 1, 1)], 16),
    # Atkinson diffuses only 6/8 of the error: crisper, more contrast, loses
    # some shadow/highlight detail. Good for illustrations.
    Kernel.ATKINSON: (
        [(0, 1, 1), (0, 2, 1), (1, -1, 1), (1, 0, 1), (1, 1, 1), (2, 0, 1)],
        8,
    ),
    Kernel.JARVIS: (
        [
            (0, 1, 7), (0, 2, 5),
            (1, -2, 3), (1, -1, 5), (1, 0, 7), (1, 1, 5), (1, 2, 3),
            (2, -2, 1), (2, -1, 3), (2, 0, 5), (2, 1, 3), (2, 2, 1),
        ],
        48,
    ),
    Kernel.STUCKI: (
        [
            (0, 1, 8), (0, 2, 4),
            (1, -2, 2), (1, -1, 4), (1, 0, 8), (1, 1, 4), (1, 2, 2),
            (2, -2, 1), (2, -1, 2), (2, 0, 4), (2, 1, 2), (2, 2, 1),
        ],
        42,
    ),
    Kernel.BURKES: (
        [(0, 1, 8), (0, 2, 4), (1, -2, 2), (1, -1, 4), (1, 0, 8), (1, 1, 4), (1, 2, 2)],
        32,
    ),
    Kernel.SIERRA: (
        [
            (0, 1, 5), (0, 2, 3),
            (1, -2, 2), (1, -1, 4), (1, 0, 5), (1, 1, 4), (1, 2, 2),
            (2, -1, 2), (2, 0, 3), (2, 1, 2),
        ],
        32,
    ),
    Kernel.SIERRA_LITE: ([(0, 1, 2), (1, -1, 1), (1, 0, 1)], 4),
}  # fmt: skip


def kernel_arrays(kernel: Kernel) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    taps, divisor = _KERNELS[Kernel(kernel)]
    dy = np.array([t[0] for t in taps], dtype=np.int64)
    dx = np.array([t[1] for t in taps], dtype=np.int64)
    w = np.array([t[2] / divisor for t in taps], dtype=np.float32)
    return dy, dx, w


@numba.njit(cache=True, inline="always")
def _oklab(r: float, g: float, b: float, m1: np.ndarray, m2: np.ndarray) -> tuple:
    r, g, b = max(r, 0.0), max(g, 0.0), max(b, 0.0)
    l_ = (m1[0, 0] * r + m1[0, 1] * g + m1[0, 2] * b) ** (1 / 3)
    m_ = (m1[1, 0] * r + m1[1, 1] * g + m1[1, 2] * b) ** (1 / 3)
    s_ = (m1[2, 0] * r + m1[2, 1] * g + m1[2, 2] * b) ** (1 / 3)
    return (
        m2[0, 0] * l_ + m2[0, 1] * m_ + m2[0, 2] * s_,
        m2[1, 0] * l_ + m2[1, 1] * m_ + m2[1, 2] * s_,
        m2[2, 0] * l_ + m2[2, 1] * m_ + m2[2, 2] * s_,
    )


@numba.njit(cache=True)
def _diffuse(
    img: np.ndarray,
    pal_lin: np.ndarray,
    pal_match: np.ndarray,
    match_oklab: bool,
    dy: np.ndarray,
    dx: np.ndarray,
    w: np.ndarray,
    serpentine: bool,
    clamp_lo: float,
    clamp_hi: float,
    m1: np.ndarray,
    m2: np.ndarray,
    only: np.ndarray,
) -> np.ndarray:
    h, wd, _ = img.shape
    out = np.zeros((h, wd), dtype=np.uint8)
    buf = img.copy()
    n = pal_lin.shape[0]
    for y in range(h):
        reverse = serpentine and (y % 2 == 1)
        for i in range(wd):
            x = wd - 1 - i if reverse else i
            if not only[y, x]:
                continue
            r = min(max(buf[y, x, 0], clamp_lo), clamp_hi)
            g = min(max(buf[y, x, 1], clamp_lo), clamp_hi)
            b = min(max(buf[y, x, 2], clamp_lo), clamp_hi)
            if match_oklab:
                c0, c1, c2 = _oklab(r, g, b, m1, m2)
            else:
                c0, c1, c2 = r, g, b
            best = 0
            best_d = 1e30
            for k in range(n):
                d0 = c0 - pal_match[k, 0]
                d1 = c1 - pal_match[k, 1]
                d2 = c2 - pal_match[k, 2]
                d = d0 * d0 + d1 * d1 + d2 * d2
                if d < best_d:
                    best_d = d
                    best = k
            out[y, x] = best
            er = r - pal_lin[best, 0]
            eg = g - pal_lin[best, 1]
            eb = b - pal_lin[best, 2]
            for t in range(dy.shape[0]):
                yy = y + dy[t]
                xx = x - dx[t] if reverse else x + dx[t]
                if yy < h and 0 <= xx < wd and only[yy, xx]:
                    buf[yy, xx, 0] += er * w[t]
                    buf[yy, xx, 1] += eg * w[t]
                    buf[yy, xx, 2] += eb * w[t]
    return out


def error_diffusion(
    linear: FloatArray,
    pal_linear: FloatArray,
    kernel: Kernel = Kernel.FLOYD_STEINBERG,
    *,
    serpentine: bool = True,
    match_oklab: bool = True,
    error_clamp: float = 0.25,
    only: np.ndarray | None = None,
) -> np.ndarray:
    """Dither a linear-RGB image (H, W, 3) to palette indices (H, W) uint8.

    ``error_clamp`` bounds how far an accumulated pixel may stray outside
    [0, 1] (in linear units) before it is matched; small values reduce
    smearing from out-of-gamut colours, large values preserve average colour.
    ``only`` (H, W bool) dithers just those pixels, as if the rest were not
    there: no error flows into or out of them, and they are left at 0.
    """
    dy, dx, w = kernel_arrays(kernel)
    pal_lin = np.ascontiguousarray(pal_linear, dtype=np.float32)
    if match_oklab:
        pal_match = np.ascontiguousarray(linear_to_oklab(pal_lin), dtype=np.float32)
    else:
        pal_match = pal_lin
    return _diffuse(
        np.ascontiguousarray(linear, dtype=np.float32),
        pal_lin,
        pal_match,
        match_oklab,
        dy,
        dx,
        w,
        serpentine,
        -error_clamp,
        1.0 + error_clamp,
        OKLAB_M1,
        OKLAB_M2,
        np.ones(linear.shape[:2], dtype=np.bool_) if only is None else only,
    )


def nearest(linear: FloatArray, pal_linear: FloatArray, *, match_oklab: bool = True) -> np.ndarray:
    """No dithering: each pixel snaps to its nearest ink (posterised look)."""
    if match_oklab:
        a, p = linear_to_oklab(linear), linear_to_oklab(pal_linear)
    else:
        a, p = linear, pal_linear
    best = np.zeros(a.shape[:2], dtype=np.uint8)
    best_d = np.full(a.shape[:2], np.inf, dtype=np.float32)
    for k, color in enumerate(p):
        d = ((a - color) ** 2).sum(axis=-1)
        closer = d < best_d
        best[closer], best_d[closer] = k, d[closer]
    return best
