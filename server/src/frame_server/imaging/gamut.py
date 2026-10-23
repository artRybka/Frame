"""Gamut of a dithered ink palette and mapping of colours into it.

Dithering mixes inks linearly in light, so the colours the panel can show
are the convex hull of the perceived ink colours in linear RGB. Asking the
ditherer for a colour outside that hull only produces noise (it chases an
error it can never pay back), so out-of-gamut colours are first pulled in
along constant OKLab lightness and hue.
"""

from __future__ import annotations

import itertools
from functools import lru_cache

import numpy as np

from .color import FloatArray, linear_to_oklab, oklab_to_linear
from .palette import Palette

_EPS = 1e-6


def hull_planes(points: FloatArray) -> tuple[FloatArray, FloatArray]:
    """Facet planes (normals, offsets) of the convex hull of a few 3-D points.

    Brute force over point triples; fine for a handful of inks. A point x is
    inside when ``normals @ x <= offsets`` for every plane.
    """
    pts = np.asarray(points, dtype=np.float64)
    normals, offsets = [], []
    for i, j, k in itertools.combinations(range(len(pts)), 3):
        n = np.cross(pts[j] - pts[i], pts[k] - pts[i])
        norm = np.linalg.norm(n)
        if norm < _EPS:
            continue
        n /= norm
        d = n @ pts[i]
        side = pts @ n - d
        if np.all(side <= _EPS):
            normals.append(n)
            offsets.append(d)
        elif np.all(side >= -_EPS):
            normals.append(-n)
            offsets.append(-d)
    return np.array(normals, dtype=np.float32), np.array(offsets, dtype=np.float32)


def inside(
    linear: FloatArray, planes: tuple[FloatArray, FloatArray], tol: float = 1e-4
) -> np.ndarray:
    normals, offsets = planes
    return np.all(linear @ normals.T <= offsets + tol, axis=-1)


@lru_cache(maxsize=16)
def chroma_limit_lut(palette: Palette, n_light: int = 64, n_hue: int = 96) -> tuple:
    """Max reachable OKLab chroma on an (L, hue) grid, by bisection."""
    planes = hull_planes(palette.perceived_linear())
    lab = palette.perceived_oklab()
    lo_l, hi_l = float(lab[:, 0].min()), float(lab[:, 0].max())
    light = np.linspace(lo_l, hi_l, n_light, dtype=np.float32)
    hue = np.linspace(0.0, 2 * np.pi, n_hue, endpoint=False, dtype=np.float32)
    ll, hh = np.meshgrid(light, hue, indexing="ij")
    lo = np.zeros_like(ll)
    if len(planes[0]) < 4:
        # Fewer than four non-coplanar inks (e.g. black + white): no volume,
        # treat the palette as achromatic.
        return light, lo
    hi = np.full_like(ll, 0.4)
    for _ in range(24):
        mid = (lo + hi) / 2
        probe = np.stack([ll, mid * np.cos(hh), mid * np.sin(hh)], axis=-1)
        ok = inside(oklab_to_linear(probe), planes)
        lo = np.where(ok, mid, lo)
        hi = np.where(ok, hi, mid)
    return light, lo.astype(np.float32)


def max_chroma(palette: Palette, light: FloatArray, hue: FloatArray) -> FloatArray:
    """Bilinear lookup of the gamut boundary chroma for each (L, hue)."""
    grid_l, lut = chroma_limit_lut(palette)
    n_light, n_hue = lut.shape
    lf = np.clip((light - grid_l[0]) / (grid_l[-1] - grid_l[0]), 0, 1) * (n_light - 1)
    hf = (np.mod(hue, 2 * np.pi) / (2 * np.pi)) * n_hue
    l0 = np.minimum(np.floor(lf).astype(int), n_light - 2)
    h0 = np.floor(hf).astype(int) % n_hue
    h1 = (h0 + 1) % n_hue
    tl, th = lf - l0, hf - np.floor(hf)
    top = lut[l0, h0] * (1 - th) + lut[l0, h1] * th
    bottom = lut[l0 + 1, h0] * (1 - th) + lut[l0 + 1, h1] * th
    return (top * (1 - tl) + bottom * tl).astype(np.float32)


def compress_chroma(lab: FloatArray, palette: Palette, knee: float) -> FloatArray:
    """Soft-compress chroma into the gamut at constant lightness and hue.

    Chroma below ``knee`` x boundary is untouched; above it is rolled off so
    the boundary is approached asymptotically. ``knee >= 1`` clips hard.
    """
    light, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    chroma = np.hypot(a, b)
    hue = np.arctan2(b, a)
    limit = np.maximum(max_chroma(palette, light, hue), 1e-5)
    ratio = chroma / limit
    if knee >= 1:
        new_ratio = np.minimum(ratio, 1.0)
    else:
        span = 1.0 - knee
        new_ratio = np.where(ratio <= knee, ratio, knee + span * np.tanh((ratio - knee) / span))
    scale = np.where(chroma > 1e-6, new_ratio * limit / np.maximum(chroma, 1e-6), 0.0)
    return np.stack([light, a * scale, b * scale], axis=-1).astype(np.float32)


def gamut_coverage(linear: FloatArray, palette: Palette) -> float:
    """Fraction of pixels already inside the panel gamut (content suitability hint)."""
    planes = hull_planes(palette.perceived_linear())
    lab = linear_to_oklab(linear)
    lo_l, hi_l = palette.neutral_range()
    lab[..., 0] = lo_l + (hi_l - lo_l) * np.clip(lab[..., 0], 0, 1)
    return float(inside(oklab_to_linear(lab), planes).mean())
