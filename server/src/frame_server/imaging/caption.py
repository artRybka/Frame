"""Museum-style caption drawn in pure ink (no dithering, no anti-aliasing)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .color import FloatArray
from .layout import Rect, caption_size

FONT_CANDIDATES = {
    "sans": (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ),
    "serif": (
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/dejavu/DejaVuSerif.ttf",
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
    ),
    "serif-bold": (
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSerif-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    ),
}

Font = ImageFont.FreeTypeFont | ImageFont.ImageFont


@lru_cache(maxsize=16)
def font(size: int, style: str = "sans") -> Font:
    for candidate in (*FONT_CANDIDATES[style], *FONT_CANDIDATES["sans"]):
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size=size)


def fit_text(draw: ImageDraw.ImageDraw, text: str, fnt: Font, max_width: int) -> str:
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
    line = fit_text(draw, text, fnt, width)
    draw.text((right - draw.textlength(line, font=fnt), top), line, font=fnt, fill=1)
    return np.asarray(text_img, dtype=bool)


#: The caption card on a filled picture: its padding (in caption sizes) and
#: its soft shadow, in panel pixels: blurred over about ``CARD_SHADOW`` and
#: cast mostly downwards, like a card lifted a little off the picture (4 px
#: was all but invisible on the panel; Mateusz 2026-11-03: larger, most of
#: all below).
CARD_PADDING = (0.9, 0.55)
CARD_SHADOW = 16
CARD_SHADOW_OFFSET = (4, 14)
CARD_SHADOW_DEPTH = 0.7


def card_layout(canvas: tuple[int, int], at: tuple[int, int, int], text: str) -> tuple[Rect, str]:
    """The white card for ``text`` whose bottom right corner is ``at`` =
    (right x, bottom y, max width), and the line printed on it."""
    right, bottom, width = at
    size = caption_size(canvas)
    fnt = font(size)
    pad_x, pad_y = round(size * CARD_PADDING[0]), round(size * CARD_PADDING[1])
    draw = ImageDraw.Draw(Image.new("1", (1, 1)))
    line = fit_text(draw, text, fnt, width - 2 * pad_x)
    ascent, descent = fnt.getmetrics() if isinstance(fnt, ImageFont.FreeTypeFont) else (size, 0)
    w = round(draw.textlength(line, font=fnt)) + 2 * pad_x
    h = ascent + descent + 2 * pad_y
    return (right - w, bottom - h, w, h), line


def card_masks(
    canvas: tuple[int, int], at: tuple[int, int, int], text: str
) -> tuple[np.ndarray, np.ndarray]:
    """Boolean masks of the white card and of the black letters on it."""
    cw, ch = canvas
    (x, y, w, h), line = card_layout(canvas, at, text)
    card = np.zeros((ch, cw), dtype=bool)
    card[y : y + h, x : x + w] = True
    size = caption_size(canvas)
    pad_x, pad_y = round(size * CARD_PADDING[0]), round(size * CARD_PADDING[1])
    text_img = Image.new("1", (cw, ch), 0)
    draw = ImageDraw.Draw(text_img)
    draw.fontmode = "1"
    draw.text((x + pad_x, y + pad_y), line, font=font(size), fill=1)
    return card, np.asarray(text_img, dtype=bool)


def shade_card(
    target: FloatArray, canvas: tuple[int, int], at: tuple[int, int, int], text: str
) -> None:
    """The card's soft shadow on the picture under it (``target`` in linear
    light); the card itself is printed over it in pure white."""
    (x, y, w, h), _ = card_layout(canvas, at, text)
    ch, cw = target.shape[:2]
    dx, dy = CARD_SHADOW_OFFSET
    reach = CARD_SHADOW * 2 + max(dx, dy)
    x0, y0 = max(0, x - reach), max(0, y - reach)
    x1, y1 = min(cw, x + w + reach), min(ch, y + h + reach)
    shape = Image.new("L", (x1 - x0, y1 - y0), 0)
    left, top = x - x0 + dx, y - y0 + dy
    ImageDraw.Draw(shape).rectangle((left, top, left + w - 1, top + h - 1), fill=255)
    soft = np.asarray(shape.filter(ImageFilter.GaussianBlur(CARD_SHADOW / 2)), np.float32) / 255
    target[y0:y1, x0:x1] *= (1 - CARD_SHADOW_DEPTH * soft)[..., None]
