"""Museum-style caption drawn in pure ink (no dithering, no anti-aliasing)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .layout import caption_size

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


def caption_mask(canvas: tuple[int, int], at: tuple[int, int, int], text: str) -> np.ndarray:
    """Boolean mask of the caption, right-aligned at ``at`` = (right x, top y,
    max width), like a museum label under the picture."""
    cw, ch = canvas
    right, top, width = at
    fnt = font(caption_size(canvas))
    text_img = Image.new("1", (cw, ch), 0)
    draw = ImageDraw.Draw(text_img)
    draw.fontmode = "1"
    line = _fit_text(draw, text, fnt, width)
    draw.text((right - draw.textlength(line, font=fnt), top), line, font=fnt, fill=1)
    return np.asarray(text_img, dtype=bool)
