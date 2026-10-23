"""Museum-style caption drawn in pure ink (no dithering, no anti-aliasing)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
)

Font = ImageFont.FreeTypeFont | ImageFont.ImageFont


@lru_cache(maxsize=8)
def font(size: int) -> Font:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size=size)


def _fit_text(draw: ImageDraw.ImageDraw, text: str, fnt: Font, max_width: int) -> str:
    if draw.textlength(text, font=fnt) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=fnt) > max_width:
        text = text[:-1]
    return text.rstrip() + "…"


def caption_masks(
    canvas: tuple[int, int],
    picture: tuple[int, int, int, int],
    text: str,
    *,
    on_white_mat: bool,
) -> tuple[np.ndarray, np.ndarray]:
    """Boolean masks (text, card) in canvas coordinates.

    With a white passe-partout below the picture the caption sits in it,
    right-aligned with the picture like a museum label. Otherwise it goes on
    a small white card in the bottom-right corner.
    """
    cw, ch = canvas
    x, y, w, h = picture
    size = max(18, round(min(cw, ch) * 0.02))
    fnt = font(size)
    text_img = Image.new("1", (cw, ch), 0)
    card_img = Image.new("1", (cw, ch), 0)
    draw = ImageDraw.Draw(text_img)
    draw.fontmode = "1"
    pad = round(size * 0.6)

    below = ch - (y + h)
    if on_white_mat and below >= size * 2:
        line = _fit_text(draw, text, fnt, w)
        width = draw.textlength(line, font=fnt)
        draw.text((x + w - width, y + h + pad), line, font=fnt, fill=1)
    else:
        line = _fit_text(draw, text, fnt, int(cw * 0.6))
        width = draw.textlength(line, font=fnt)
        _, top, _, bottom = draw.textbbox((0, 0), line, font=fnt)
        box_w, box_h = int(width) + 2 * pad, (bottom - top) + 2 * pad
        x1, y1 = cw - pad * 2, ch - pad * 2
        x0, y0 = x1 - box_w, y1 - box_h
        ImageDraw.Draw(card_img).rectangle([x0, y0, x1, y1], fill=1)
        draw.text((x0 + pad, y0 + pad - top), line, font=fnt, fill=1)
    return np.asarray(text_img, dtype=bool), np.asarray(card_img, dtype=bool)
