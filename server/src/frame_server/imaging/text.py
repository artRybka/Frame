"""A short description printed on the mat, like a museum wall text.

Title in serif, the artist and date below, a thin rule, then the text,
wrapped to the space: as many whole sentences as fit, an ellipsis only if
not even the first one does. Pure ink,
no anti-aliasing, like the caption.
"""

from __future__ import annotations

import re

import numpy as np
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field

from .caption import Font, fit_text, font
from .layout import Rect

MAX_BODY = 900  # characters worth considering; the space decides the rest
# Sizes and gaps as fractions of the canvas's short side; the body text is
# small, like a wall label, under a title and credit line that stand out.
TITLE_SIZE = 0.036
META_SIZE = 0.021
BODY_SIZE = 0.015
MEASURE = 0.5  # widest line, about 70 characters of body text


class TextBlock(BaseModel):
    title: str = ""
    meta: list[str] = Field(default_factory=list)  # e.g. artist; date · medium
    body: str = ""


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt: Font, width: int) -> list[str]:
    lines: list[str] = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=fnt) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
        fits = draw.textlength(word, font=fnt) <= width
        line = word if fits else fit_text(draw, word, fnt, width)
    if line:
        lines.append(line)
    return lines


def _ellipsis(draw: ImageDraw.ImageDraw, line: str, fnt: Font, width: int) -> str:
    while line and draw.textlength(line.rstrip(" ,.;:") + " …", font=fnt) > width:
        line = line.rsplit(" ", 1)[0] if " " in line else line[:-1]
    return line.rstrip(" ,.;:") + " …"


def sentences(text: str) -> list[str]:
    """Split after . ! ? when the next word starts with a capital (so "c. 1890"
    and "e.g. this" stay whole)."""
    out: list[str] = []
    for piece in re.split(r"(?<=[.!?])\s+", " ".join(text.split())):
        if out and not piece.lstrip("\"“(‘'")[:1].isupper():
            out[-1] += " " + piece
        else:
            out.append(piece)
    return out


def whole_sentences(draw: ImageDraw.ImageDraw, text: str, fnt: Font, width: int, lines: int) -> str:
    """The longest run of leading sentences that wraps into ``lines`` lines."""
    chosen: list[str] = []
    for sentence in sentences(text):
        if sum(map(len, chosen)) + len(sentence) > MAX_BODY:
            break
        if len(wrap(draw, " ".join([*chosen, sentence]), fnt, width)) > lines:
            break
        chosen.append(sentence)
    if chosen:
        return " ".join(chosen)
    return " ".join(text.split())[:MAX_BODY]  # not even one sentence fits: ellipsis


def text_block_mask(canvas: tuple[int, int], rect: Rect, block: TextBlock) -> np.ndarray:
    cw, ch = canvas
    x, y, w, h = rect
    short = min(cw, ch)
    w = min(w, round(short * MEASURE))
    title_font = font(round(short * TITLE_SIZE), "serif-bold")
    meta_font = font(round(short * META_SIZE), "sans")
    body_font = font(round(short * BODY_SIZE), "serif")
    img = Image.new("1", (cw, ch), 0)
    draw = ImageDraw.Draw(img)
    draw.fontmode = "1"
    bottom = y + h

    def step_of(fnt: Font, leading: float) -> int:
        return round((fnt.size if hasattr(fnt, "size") else 20) * leading)

    def lines_of(text: str, fnt: Font, limit: int, leading: float, cursor: int) -> int:
        step = step_of(fnt, leading)
        lines = wrap(draw, text, fnt, w)
        room = max(0, (bottom - cursor) // step)
        shown = lines[: min(limit, room)]
        if len(shown) < len(lines) and shown:
            shown[-1] = _ellipsis(draw, shown[-1], fnt, w)
        for line in shown:
            draw.text((x, cursor), line, font=fnt, fill=1)
            cursor += step
        return cursor

    cursor = y
    if block.title:
        cursor = lines_of(block.title, title_font, 2, 1.2, cursor)
        cursor += round(short * 0.007)
    for line in block.meta:
        if line:
            cursor = lines_of(line, meta_font, 1, 1.4, cursor)
    rule = max(2, round(short * 0.001))
    if block.body and cursor + rule + round(short * 0.03) < bottom:
        cursor += round(short * 0.008)
        draw.rectangle([x, cursor, x + round(w * 0.12), cursor + rule - 1], fill=1)
        cursor += rule + round(short * 0.01)
        room = max(0, (bottom - cursor) // step_of(body_font, 1.42))
        body = whole_sentences(draw, block.body, body_font, w, room)
        lines_of(body, body_font, room, 1.42, cursor)
    return np.asarray(img, dtype=bool)
