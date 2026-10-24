"""The passe-partout: a paper mat with windows cut at 45°.

Painted in the panel's perceived colours after tone mapping, so the mat's
colour does not depend on the picture's tone settings. The bevel is the
board's own colour: with the light from the upper left the top and left
bevels fall in shadow (a little darker), the bottom and right ones catch the
light (a little lighter), and the mat throws a thin shadow onto the picture
along its top and left edges.

"picture" tints the mat in the picture's own hue, as a framer would: the
hue that carries the most colour (area times saturation), made light and
muted, or deep and muted for a dark picture; nearly colourless pictures get
a warm or cool off-white.
"""

from __future__ import annotations

import numpy as np

from .color import FloatArray, linear_to_oklab, oklab_to_linear
from .gamut import compress_chroma
from .layout import Fit, Plan
from .palette import Palette

MAT_COLORS = ("white", "cream", "grey", "black", "picture")
HUE_BINS = 36
TINT_LIGHT = (0.9, 0.024, 0.3)  # light mat: lightness (black 0, white 1), max chroma, share
TINT_DARK = (0.24, 0.035, 0.5)  # dark picture: a deep mat
NEUTRAL_CHROMA = 0.02  # pictures below this mean chroma count as colourless
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


def _toward(colour: FloatArray, target: FloatArray, amount: float) -> FloatArray:
    """Move ``colour`` part of the way to ``target``, evenly to the eye
    (cube-root lightness), so a black board's lit bevel stays a dark sheen."""
    a, b = np.cbrt(colour), np.cbrt(target)
    return np.asarray((a + (b - a) * amount) ** 3, dtype=np.float32)


def _relative_light(colour: FloatArray, palette: Palette) -> float:
    white = palette.perceived_linear()[palette.white_index()]
    black = palette.perceived_linear()[palette.black_index()]
    lw, lb, lc = (float(linear_to_oklab(c)[0]) for c in (white, black, colour))
    return (lc - lb) / max(lw - lb, 1e-6)


def is_dark(colour: FloatArray, palette: Palette) -> bool:
    """Whether letters on a board of ``colour`` should be white."""
    return _relative_light(colour, palette) < 0.5


def picture_tint(pixels: FloatArray, white: FloatArray, black: FloatArray) -> FloatArray:
    """A mat colour from the picture's ``pixels`` (linear RGB, any shape),
    between ``black`` and ``white`` in lightness."""
    flat = pixels.reshape(-1, 3)
    lab = linear_to_oklab(flat[:: max(1, len(flat) // 40000)])
    light, a, b = lab[:, 0], lab[:, 1], lab[:, 2]
    chroma = np.hypot(a, b)
    lw, lb = float(linear_to_oklab(white)[0]), float(linear_to_oklab(black)[0])
    relative = (float(np.median(light)) - lb) / max(lw - lb, 1e-6)
    tone, max_c, share = TINT_DARK if relative < 0.35 else TINT_LIGHT
    if float(chroma.mean()) < NEUTRAL_CHROMA:
        # Colourless: lean the off-white the way the picture leans, barely.
        hue = float(np.arctan2(b.mean(), a.mean()))
        target_c = min(0.012, float(np.hypot(a.mean(), b.mean())))
    else:
        # The hue carrying the most colour, then the mean of its neighbourhood.
        hues = np.arctan2(b, a)
        bins = ((hues + np.pi) / (2 * np.pi) * HUE_BINS).astype(int) % HUE_BINS
        hist = np.bincount(bins, weights=chroma, minlength=HUE_BINS)
        hist = hist + 0.5 * (np.roll(hist, 1) + np.roll(hist, -1))
        centre = (int(hist.argmax()) + 0.5) / HUE_BINS * 2 * np.pi - np.pi
        near = np.abs(np.angle(np.exp(1j * (hues - centre)))) < np.radians(30)
        hue = float(np.arctan2(b[near].sum(), a[near].sum()))
        strength = float((chroma[near] ** 2).sum() / max(chroma[near].sum(), 1e-6))
        target_c = min(max_c, share * strength)
    lab_mat = np.array(
        [lb + tone * (lw - lb), target_c * np.cos(hue), target_c * np.sin(hue)], dtype=np.float32
    )
    return np.clip(oklab_to_linear(lab_mat), 0.0, 1.0).astype(np.float32)


def _picture_mat(target: FloatArray, plan: Plan, palette: Palette) -> FloatArray:
    """The tint from what the panel shows of the picture (with several
    photos, of all of them), within its gamut."""
    windows = plan.windows if plan.fit == Fit.MULTI else plan.windows[:1]
    pixels = np.concatenate(
        [target[y : y + h, x : x + w].reshape(-1, 3) for x, y, w, h in (w.rect for w in windows)]
    )
    white = palette.perceived_linear()[palette.white_index()]
    black = palette.perceived_linear()[palette.black_index()]
    tint = picture_tint(pixels, white, black)
    lab = compress_chroma(linear_to_oklab(tint)[None, :], palette, knee=0.7)
    return np.clip(oklab_to_linear(lab)[0], 0.0, 1.0).astype(np.float32)


def _texture(shape: tuple[int, int], seed: int = 7) -> FloatArray:
    """Soft paper grain, the same every time (renders are reproducible)."""
    h, w = shape
    rng = np.random.default_rng(seed)
    coarse = rng.normal(0.0, 1.0, (h // 3 + 2, w // 3 + 2)).astype(np.float32)
    ys = np.linspace(0, coarse.shape[0] - 1.001, h)
    xs = np.linspace(0, coarse.shape[1] - 1.001, w)
    y0, x0 = ys.astype(int), xs.astype(int)
    fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
    a = coarse[y0][:, x0]
    b = coarse[y0][:, x0 + 1]
    c = coarse[y0 + 1][:, x0]
    d = coarse[y0 + 1][:, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def paint_mat(target: FloatArray, plan: Plan, palette: Palette, mat: str) -> FloatArray | None:
    """Paint the mat, bevels and shadows into ``target`` (panel linear RGB).

    Returns the board's colour, or None when the picture covers the canvas.
    """
    mask = plan.mat_mask()
    if not mask.any():
        return None
    cw, ch = plan.canvas
    short = min(cw, ch)
    white = palette.perceived_linear()[palette.white_index()]
    black = palette.perceived_linear()[palette.black_index()]
    if mat != "edge":  # "edge" keeps the picture's border colour composed earlier
        base = _picture_mat(target, plan, palette) if mat == "picture" else mat_color(mat, palette)
        if mat in ("cream", "grey", "picture"):
            grain = 1.0 + 0.012 * _texture((ch, cw))[mask]
            target[mask] = np.clip(base[None, :] * grain[:, None], 0.0, 1.0)
        else:
            target[mask] = base  # pure ink: no grain, it would only add dots

    bevel = max(3, round(short * BEVEL))
    shadow = max(3, round(short * SHADOW))
    # The cut is the board itself, lit or shaded: a little lighter or darker.
    board = target[mask].mean(axis=0) if mat == "edge" else base
    core_lit = _toward(board, white, 0.2)
    core_shaded = _toward(board, black, 0.15)
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
    return board
