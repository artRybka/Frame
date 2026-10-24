"""Test charts for device experiments and colour calibration.

All charts are produced at the native 2560x1440 resolution and must be sent
to the panel without any further processing (``frame push --raw``).

* palette     – six large pure-ink patches + paper-reference frame, for
                measuring the perceived palette from a photo (Etap 1).
* passthrough – pixel-exact patterns of pure inks (1/2/4 px checkerboards,
                lines). If the panel shows them unchanged, pre-dithered
                images survive its pipeline (experiment E5).
* ramps       – continuous-tone gradients; shows what the panel's own
                processing does with non-ink colours (E5, strategy choice).
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .layout import PANEL_HEIGHT, PANEL_WIDTH
from .palette import SPECTRA6, Palette

W, H = PANEL_WIDTH, PANEL_HEIGHT


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _draw(img: Image.Image) -> ImageDraw.ImageDraw:
    draw = ImageDraw.Draw(img)
    draw.fontmode = "1"  # no anti-aliasing: text stays pure black ink
    return draw


def _fiducials(draw: ImageDraw.ImageDraw, size: int = 80) -> None:
    """Corner markers (black square with a white core) to locate the chart in a photo."""
    for x, y in ((0, 0), (W - size, 0), (0, H - size), (W - size, H - size)):
        draw.rectangle([x, y, x + size - 1, y + size - 1], fill=(0, 0, 0))
        q = size // 3
        draw.rectangle([x + q, y + q, x + 2 * q - 1, y + 2 * q - 1], fill=(255, 255, 255))


def palette_patches(palette: Palette = SPECTRA6) -> list[tuple[str, tuple[int, int, int, int]]]:
    """Ink patches of the palette chart: (ink name, (x0, y0, x1, y1)), x1/y1 exclusive."""
    cols, rows = 3, 2
    margin, gap = 200, 60
    pw = (W - 2 * margin - (cols - 1) * gap) // cols
    ph = (H - 2 * margin - (rows - 1) * gap) // rows
    patches = []
    for i, color in enumerate(palette.colors):
        x0 = margin + (i % cols) * (pw + gap)
        y0 = margin + (i // cols) * (ph + gap)
        patches.append((color.name, (x0, y0, x0 + pw, y0 + ph)))
    return patches


def palette_chart(palette: Palette = SPECTRA6) -> Image.Image:
    img = Image.new("RGB", (W, H), (255, 255, 255))
    draw = _draw(img)
    _fiducials(draw)
    margin = 200
    font = _font(36)
    for i, (color, (_, (x0, y0, x1, y1))) in enumerate(
        zip(palette.colors, palette_patches(palette), strict=True)
    ):
        pw, ph = x1 - x0, y1 - y0
        draw.rectangle([x0, y0, x0 + pw - 1, y0 + ph - 1], fill=color.device)
        # Thin black outline so the white patch is findable too.
        draw.rectangle([x0 - 4, y0 - 4, x0 + pw + 3, y0 + ph + 3], outline=(0, 0, 0), width=2)
        draw.text((x0, y0 - 50), f"{i}: {color.name}", fill=(0, 0, 0), font=font)
    draw.text(
        (margin, H - 130),
        "Frame palette chart: photograph it straight on, in daylight, without glare",
        fill=(0, 0, 0),
        font=_font(30),
    )
    return img


def _pattern(kind: str, size: int, a: tuple, b: tuple, w: int, h: int) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    if kind == "checker":
        mask = ((xx // size) + (yy // size)) % 2 == 0
    elif kind == "vlines":
        mask = (xx // size) % 2 == 0
    else:  # hlines
        mask = (yy // size) % 2 == 0
    out = np.empty((h, w, 3), dtype=np.uint8)
    out[mask] = a
    out[~mask] = b
    return out


def passthrough_chart(palette: Palette = SPECTRA6) -> Image.Image:
    arr = np.full((H, W, 3), 255, dtype=np.uint8)
    inks = {c.name: c.device for c in palette.colors}
    pairs = [
        ("black", "white"),
        ("red", "yellow"),
        ("blue", "white"),
        ("green", "white"),
        ("red", "blue"),
        ("black", "yellow"),
    ]
    tile_w, tile_h = 300, 260
    x_start, y_start, gap = 140, 180, 30
    labels: list[tuple[int, int, str]] = []
    rows = [("checker", 1), ("checker", 2), ("vlines", 1), ("hlines", 1)]
    for r, (kind, size) in enumerate(rows):
        for c, (pa, pb) in enumerate(pairs):
            x0 = x_start + c * (tile_w + gap)
            y0 = y_start + r * (tile_h + gap)
            arr[y0 : y0 + tile_h, x0 : x0 + tile_w] = _pattern(
                kind, size, inks[pa], inks[pb], tile_w, tile_h
            )
            if r == 0:
                labels.append((x0, y0 - 50, f"{pa}/{pb}"))
        row_label_x = x_start + len(pairs) * (tile_w + gap)
        labels.append((row_label_x, y_start + r * (tile_h + gap) + 110, f"{kind} {size}px"))
    img = Image.fromarray(arr)
    draw = _draw(img)
    _fiducials(draw)
    font = _font(34)
    for x, y, text in labels:
        draw.text((x, y), text, fill=(0, 0, 0), font=font)
    return img


def ramps_chart() -> Image.Image:
    arr = np.full((H, W, 3), 255, dtype=np.uint8)
    t = np.linspace(0.0, 1.0, W - 400, dtype=np.float32)
    ramps: list[tuple[str, Callable[[np.ndarray], np.ndarray]]] = [
        ("grey", lambda v: np.stack([v, v, v], -1)),
        ("red", lambda v: np.stack([v, np.zeros_like(v), np.zeros_like(v)], -1)),
        ("green", lambda v: np.stack([np.zeros_like(v), v, np.zeros_like(v)], -1)),
        ("blue", lambda v: np.stack([np.zeros_like(v), np.zeros_like(v), v], -1)),
        ("skin", lambda v: np.stack([v, 0.78 * v, 0.66 * v], -1)),
        ("hue", lambda v: _hue_sweep(v)),
        ("sky", lambda v: np.stack([0.45 + 0.4 * v, 0.62 + 0.3 * v, 0.85 + 0.15 * v], -1)),
    ]
    band_h, gap, y = 150, 30, 120
    labels = []
    for name, fn in ramps:
        row = np.clip(fn(t) * 255 + 0.5, 0, 255).astype(np.uint8)
        arr[y : y + band_h, 200 : 200 + len(t)] = row[None, :, :]
        labels.append((30, y + band_h // 2 - 20, name))
        y += band_h + gap
    img = Image.fromarray(arr)
    draw = _draw(img)
    _fiducials(draw)
    font = _font(34)
    for x, yy, text in labels:
        draw.text((x, yy), text, fill=(0, 0, 0), font=font)
    return img


def _hue_sweep(v: np.ndarray) -> np.ndarray:
    h = v * 6.0
    i = np.floor(h).astype(int) % 6
    f = h - np.floor(h)
    q, t_ = 1 - f, f
    one, zero = np.ones_like(v), np.zeros_like(v)
    table = [
        (one, t_, zero),
        (q, one, zero),
        (zero, one, t_),
        (zero, q, one),
        (t_, zero, one),
        (one, zero, q),
    ]
    out = np.zeros((*v.shape, 3), dtype=np.float32)
    for k, (r, g, b) in enumerate(table):
        m = i == k
        out[m] = np.stack([r[m], g[m], b[m]], -1)
    return out


def welcome_card(orientation_hint: str = "") -> Image.Image:
    """Placeholder content: pure black text on white."""
    img = Image.new("RGB", (W, H), (255, 255, 255))
    draw = _draw(img)
    draw.text((W // 2, H // 2 - 40), "Frame", fill=(0, 0, 0), font=_font(160), anchor="mm")
    draw.text(
        (W // 2, H // 2 + 110),
        orientation_hint or "Waiting for the first picture",
        fill=(0, 0, 0),
        font=_font(48),
        anchor="mm",
    )
    return img


CHARTS: dict[str, Callable[[], Image.Image]] = {
    "palette": palette_chart,
    "passthrough": passthrough_chart,
    "ramps": ramps_chart,
}
