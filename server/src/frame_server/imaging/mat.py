"""The passe-partout: a paper mat with windows cut at 45°.

Painted in the panel's perceived colours after tone mapping, so the mat's
colour does not depend on the picture's tone settings. The bevel is the
board's own colour: with the light from the upper left the top and left
bevels fall in shadow (a little darker), the bottom and right ones catch the
light (a little lighter), and the mat throws a thin shadow onto the picture
along its top and left edges.

"picture" (the app's "Jasne") tints the mat in the picture's own hue, as a
framer would: the hue that carries the most colour (area times saturation),
made light and muted; nearly colourless pictures get a warm or cool
off-white. "picture_dark" ("Ciemne") is the same hue on a deep, muted
board with a white core: its bevels are white, lit and shaded. "black" has a
dark grey core, so the cut still shows on the panel.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from .color import FloatArray, linear_to_oklab, oklab_to_linear
from .gamut import compress_chroma
from .layout import Fit, Plan
from .palette import EM32DX, Palette

MAT_COLORS = ("white", "cream", "grey", "black", "picture", "picture_dark")
PICTURE_MATS = ("picture", "picture_dark")  # tinted by the picture
HUE_BINS = 36
TINT_LIGHT = (0.9, 0.024, 0.3)  # light mat: lightness (black 0, white 1), max chroma, share
TINT_DARK = (0.24, 0.035, 0.5)  # dark mat: deep and muted
# The black board's core, lit and shaded: how far toward white (cube-root
# lightness). The board's own black would leave the cut all but invisible.
BLACK_CORE = (0.34, 0.22)
NEUTRAL_CHROMA = 0.02  # pictures below this mean chroma count as colourless
BEVEL = 0.006  # bevel width, fraction of the canvas's short side
SHADOW = 0.006  # shadow on the picture, same unit
CREAM_YELLOW = 0.3  # the cream board: white with this share of yellow ink, and no other ink
# (not 0.2 to 0.25: Floyd-Steinberg draws streaks and patches of yellow there)
GRAIN = 0.003  # paper grain, relative brightness swing: barely there
GRAIN_CELL = 8  # grain size in pixels: soft clouds, not specks
# The crease where the bevel meets the face (crease_dots): its dots along the
# line, one character per pixel: an ink's initial or "." for none (E14).
CREASE_ON_LIGHT = "k."
CREASE_ON_DARK = "w.b."  # white alone stands out too much on a dark board
CREASE_INKS = {"k": "black", "w": "white", "b": "blue", "r": "red", "g": "green", "y": "yellow"}


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
        return _cream(palette)
    return white.copy()


def _cream(palette: Palette) -> FloatArray:
    """White and a little yellow: on the panel just these two inks, the
    yellow a warm ochre there. The ideal inks of the app's previews would
    make it lemon, so they get the panel's cream as it looks beside its white."""
    white = palette.perceived_linear()[palette.white_index()]
    yellow = _ink(palette, "yellow")
    if yellow is None:
        return white.copy()
    if all(c.device == c.perceived for c in palette.colors):  # Palette.nominal()
        panel_white = EM32DX.perceived_linear()[EM32DX.white_index()]
        on_panel = _cream(EM32DX)
        return np.asarray(np.clip(white * on_panel / panel_white, 0.0, 1.0), dtype=np.float32)
    return white * (1 - CREAM_YELLOW) + yellow * CREAM_YELLOW


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


def picture_tint(
    pixels: FloatArray, white: FloatArray, black: FloatArray, dark: bool = False
) -> FloatArray:
    """A mat colour from the picture's ``pixels`` (linear RGB, any shape),
    between ``black`` and ``white`` in lightness: a light board, or with
    ``dark`` a deep one."""
    flat = pixels.reshape(-1, 3)
    lab = linear_to_oklab(flat[:: max(1, len(flat) // 40000)])
    a, b = lab[:, 1], lab[:, 2]
    chroma = np.hypot(a, b)
    lw, lb = float(linear_to_oklab(white)[0]), float(linear_to_oklab(black)[0])
    tone, max_c, share = TINT_DARK if dark else TINT_LIGHT
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


def _picture_mat(target: FloatArray, plan: Plan, palette: Palette, dark: bool) -> FloatArray:
    """The tint from what the panel shows of the picture (with several
    photos, of all of them), within its gamut."""
    windows = plan.windows if plan.fit == Fit.MULTI else plan.windows[:1]
    pixels = np.concatenate(
        [target[y : y + h, x : x + w].reshape(-1, 3) for x, y, w, h in (w.rect for w in windows)]
    )
    white = palette.perceived_linear()[palette.white_index()]
    black = palette.perceived_linear()[palette.black_index()]
    tint = picture_tint(pixels, white, black, dark)
    lab = compress_chroma(linear_to_oklab(tint)[None, :], palette, knee=0.7)
    return np.clip(oklab_to_linear(lab)[0], 0.0, 1.0).astype(np.float32)


@lru_cache(maxsize=2)  # one per orientation
def _texture(shape: tuple[int, int], seed: int = 7) -> FloatArray:
    """Faint, smooth paper grain, the same every time (renders are reproducible).

    Kept between renders: read only."""
    h, w = shape
    rng = np.random.default_rng(seed)
    coarse = rng.normal(0.0, 1.0, (h // GRAIN_CELL + 2, w // GRAIN_CELL + 2)).astype(np.float32)
    ys = np.linspace(0, coarse.shape[0] - 1.001, h)
    xs = np.linspace(0, coarse.shape[1] - 1.001, w)
    y0, x0 = ys.astype(int), xs.astype(int)
    fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
    a = coarse[y0][:, x0]
    b = coarse[y0][:, x0 + 1]
    c = coarse[y0 + 1][:, x0]
    d = coarse[y0 + 1][:, x0 + 1]
    grain = (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy
    grain.flags.writeable = False
    return grain


def bevel_width(plan: Plan) -> int:
    return max(3, round(min(plan.canvas) * BEVEL))


def crease_dots(plan: Plan, pattern: str) -> dict[str, np.ndarray]:
    """Dots where the bevels meet the face, all around each window: a mask
    per ink name, ``pattern`` repeated along the line.

    On a light board the lit bevels are as light as the face and the cut
    would vanish; the line all around keeps the cut even. Set after
    dithering, like lettering: a grey line would turn into red, green and
    blue dots, and the picture's error would leak into it.
    """
    cw, ch = plan.canvas
    line = np.zeros((ch, cw), dtype=bool)
    mask = plan.mat_mask()
    if mask.any():
        d = bevel_width(plan)
        for x, y, w, h in (window.rect for window in plan.windows):
            # The outer edge of the bevel ring, mitred corners included.
            x0, y0, x1, y1 = max(x - d, 0), max(y - d, 0), min(x + w + d, cw), min(y + h + d, ch)
            if y - d >= 0:
                line[y - d, x0:x1] = True
            if y + h - 1 + d < ch:
                line[y + h - 1 + d, x0:x1] = True
            if x - d >= 0:
                line[y0:y1, x - d] = True
            if x + w - 1 + d < cw:
                line[y0:y1, x + w - 1 + d] = True
        line &= mask
    ys, xs = np.nonzero(line)
    step = (xs + ys) % len(pattern)
    marks: dict[str, np.ndarray] = {}
    for i, c in enumerate(pattern):
        if c in CREASE_INKS:
            dots = marks.setdefault(CREASE_INKS[c], np.zeros((ch, cw), dtype=bool))
            dots[ys[step == i], xs[step == i]] = True
    return marks


def paint_mat(
    target: FloatArray, plan: Plan, palette: Palette, mat: str, shade: bool = True
) -> FloatArray | None:
    """Paint the mat, bevels and (with ``shade``) the shadows on the
    pictures into ``target`` (panel linear RGB).

    Returns the board's colour, or None when the picture covers the canvas.
    """
    mask = plan.mat_mask()
    if not mask.any():
        return None
    cw, ch = plan.canvas
    white = palette.perceived_linear()[palette.white_index()]
    black = palette.perceived_linear()[palette.black_index()]
    if mat != "edge":  # "edge" keeps the picture's border colour composed earlier
        if mat in PICTURE_MATS:
            base = _picture_mat(target, plan, palette, dark=mat == "picture_dark")
        else:
            base = mat_color(mat, palette)
        if mat in ("cream", "grey", *PICTURE_MATS):
            grain = 1.0 + GRAIN * _texture((ch, cw))[mask]
            target[mask] = np.clip(base[None, :] * grain[:, None], 0.0, 1.0)
        else:
            target[mask] = base  # pure ink: no grain, it would only add dots

    bevel = bevel_width(plan)
    # The cut is the board itself, lit or shaded: a little lighter or darker.
    board = target[mask].mean(axis=0) if mat == "edge" else base
    if mat == "picture_dark":  # a white core
        core_lit, core_shaded = white, _toward(white, black, 0.18)
    elif mat == "black":  # a dark grey core
        core_lit, core_shaded = (_toward(board, white, amount) for amount in BLACK_CORE)
    else:
        core_lit = _toward(board, white, 0.2)
        core_shaded = _toward(board, black, 0.15)
    for x, y, w, h in (window.rect for window in plan.windows):
        # Edges on the canvas border have no mat beyond them.
        open_edges = {"left": x > 0, "top": y > 0, "right": x + w < cw, "bottom": y + h < ch}
        x0, y0 = max(x - bevel, 0), max(y - bevel, 0)
        x1, y1 = min(x + w + bevel, cw), min(y + h + bevel, ch)
        # The bevel lies around the window: only these four bands can hold it.
        bands = (
            (x0, y0, x1, y),
            (x0, y + h, x1, y1),
            (x0, y, x, y + h),
            (x + w, y, x1, y + h),
        )
        for bx0, by0, bx1, by1 in bands:
            if bx1 <= bx0 or by1 <= by0:
                continue
            yy, xx = np.mgrid[by0:by1, bx0:bx1]
            out = np.stack([x - xx, yy * 0 + (y - yy), xx - (x + w - 1), yy - (y + h - 1)])
            dist = out.max(axis=0)  # Chebyshev distance outside the window
            side = out.argmax(axis=0)  # which edge: mitred 45° corners
            ring = (dist > 0) & (dist <= bevel) & mask[by0:by1, bx0:bx1]
            region = target[by0:by1, bx0:bx1]
            for index, (name, colour) in enumerate(
                (
                    ("left", core_shaded),
                    ("top", core_shaded),
                    ("right", core_lit),
                    ("bottom", core_lit),
                )
            ):
                if open_edges[name]:
                    region[ring & (side == index)] = colour
    if shade:
        shade_pictures(target, plan)
    return board


def shade_pictures(target: FloatArray, plan: Plan) -> None:
    """The mat's shadow on the pictures, under the top and left edges of
    each window (``target`` in linear light)."""
    shadow = max(3, round(min(plan.canvas) * SHADOW))
    ramp = np.linspace(0.78, 1.0, shadow, dtype=np.float32)
    for x, y, w, h in (window.rect for window in plan.windows):
        if y > 0:
            n = min(shadow, h)
            target[y : y + n, x : x + w] *= ramp[:n, None, None]
        if x > 0:
            n = min(shadow, w)
            target[y : y + h, x : x + n] *= ramp[None, :n, None]
