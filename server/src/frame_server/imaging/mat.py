"""The passe-partout: a paper mat with windows cut at 45°.

Painted in the panel's perceived colours after tone mapping, so the mat's
colour does not depend on the picture's tone settings. A real mat's core
shows on the bevel; with the light from the upper left the top and left
bevels fall in shadow, the bottom and right ones catch the light, and the
mat throws a thin shadow onto the picture along its top and left edges.
"""

from __future__ import annotations

import numpy as np

from .color import FloatArray
from .layout import Plan
from .palette import Palette

MAT_COLORS = ("white", "cream", "grey", "black")
BEVEL = 0.006  # bevel width, fraction of the canvas's short side
SHADOW = 0.006  # shadow on the picture, same unit


def _ink(palette: Palette, name: str) -> FloatArray | None:
    return palette.perceived_linear()[palette.index(name)] if name in palette.names else None


def mat_color(name: str, palette: Palette) -> FloatArray:
    """The mat's colour in the panel's perceived linear RGB."""
    white = palette.perceived_linear()[palette.white_index()]
    black = palette.perceived_linear()[palette.black_index()]
    if name == "black":
        return black.copy()
    if name == "grey":
        return black + (white - black) * 0.42
    if name == "cream":
        yellow = _ink(palette, "yellow")
        return white.copy() if yellow is None else white * 0.9 + yellow * 0.1
    return white.copy()


def _texture(shape: tuple[int, int], seed: int = 7) -> FloatArray:
    """Soft paper grain, the same every time (renders are reproducible)."""
    h, w = shape
    rng = np.random.default_rng(seed)
    coarse = rng.normal(0.0, 1.0, (h // 6 + 2, w // 6 + 2)).astype(np.float32)
    ys = np.linspace(0, coarse.shape[0] - 1.001, h)
    xs = np.linspace(0, coarse.shape[1] - 1.001, w)
    y0, x0 = ys.astype(int), xs.astype(int)
    fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
    a = coarse[y0][:, x0]
    b = coarse[y0][:, x0 + 1]
    c = coarse[y0 + 1][:, x0]
    d = coarse[y0 + 1][:, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def paint_mat(target: FloatArray, plan: Plan, palette: Palette, mat: str) -> None:
    """Paint the mat, bevels and shadows into ``target`` (panel linear RGB)."""
    mask = plan.mat_mask()
    if not mask.any():
        return
    cw, ch = plan.canvas
    short = min(cw, ch)
    white = palette.perceived_linear()[palette.white_index()]
    black = palette.perceived_linear()[palette.black_index()]
    if mat != "edge":  # "edge" keeps the picture's border colour composed earlier
        base = mat_color(mat, palette)
        if mat in ("cream", "grey"):
            grain = 1.0 + 0.02 * _texture((ch, cw))[mask]
            target[mask] = np.clip(base[None, :] * grain[:, None], 0.0, 1.0)
        else:
            target[mask] = base  # pure ink: no grain, it would only add dots

    bevel = max(3, round(short * BEVEL))
    shadow = max(3, round(short * SHADOW))
    core_lit = white
    core_shaded = white + (black - white) * 0.28
    for x, y, w, h in (window.rect for window in plan.windows):
        # Edges on the canvas border have no mat beyond them.
        open_edges = {"left": x > 0, "top": y > 0, "right": x + w < cw, "bottom": y + h < ch}
        x0, y0 = max(x - bevel, 0), max(y - bevel, 0)
        x1, y1 = min(x + w + bevel, cw), min(y + h + bevel, ch)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        out = np.stack([x - xx, yy * 0 + (y - yy), xx - (x + w - 1), yy - (y + h - 1)])
        dist = out.max(axis=0)  # Chebyshev distance outside the window
        side = out.argmax(axis=0)  # which edge: mitred 45° corners
        ring = (dist > 0) & (dist <= bevel) & mask[y0:y1, x0:x1]
        region = target[y0:y1, x0:x1]
        for index, (name, colour) in enumerate(
            (("left", core_shaded), ("top", core_shaded), ("right", core_lit), ("bottom", core_lit))
        ):
            if open_edges[name]:
                region[ring & (side == index)] = colour
        # The mat's shadow on the picture, under its top and left edges.
        ramp = np.linspace(0.78, 1.0, shadow, dtype=np.float32)
        if open_edges["top"]:
            n = min(shadow, h)
            target[y : y + n, x : x + w] *= ramp[:n, None, None]
        if open_edges["left"]:
            n = min(shadow, w)
            target[y : y + h, x : x + n] *= ramp[None, :n, None]
