"""Blank margins museums put around their pictures, cut off.

Some museums serve a painting's photograph on a flat white (or black)
sheet: the V&A's older scans have a white band a tenth of the picture wide
on every side (Berchem's "Landscape with figures", 2006BH7540). On the
frame and in the app it read as a mat inside the mat (Mateusz,
2026-11-08). The band is a digital fill, perfectly flat, so it is told
from the picture by flatness: a line counts as margin when nearly all its
pixels are within a few levels of pure white or pure black.

Only when both sides of one axis have such a margin (top and bottom, or
left and right) is anything cut: a photograph's burnt-out sky or a black
night at one edge is the picture, not a margin. What is left must be most
of the picture, so a sketch on white paper keeps its sheet.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

#: How far (levels, any channel) a margin pixel may be from its colour:
#: JPEG noise around a flat fill, never a painted sky.
TOLERANCE = 10
#: Share of a line's pixels that must be margin (a museum's stamp or a
#: speck of dust in the band does not end it).
LINE_SHARE = 0.995
#: After the flat fill, up to this many lines of JPEG ringing count as
#: margin when this share of their pixels is within RINGING_TOLERANCE.
RINGING = 8
RINGING_TOLERANCE = 48
RINGING_SHARE = 0.9
#: Margin colours: a line's median this light (every channel) is white
#: fill, this dark is black fill.
WHITE_FROM = 238
BLACK_UP_TO = 18
#: Each side of what is left must be at least this share of the picture.
LEAST_KEPT = 0.4
#: Cut this much more (share of the side) on each side that had a margin:
#: the picture's edge is soft, a light halo of the fill around it.
EDGE = 0.004


def _fill(line: np.ndarray) -> np.ndarray | None:
    """The fill colour of an outermost line, None when it is not flat
    white or black."""
    colour = np.median(line, axis=0)
    if colour.min() >= WHITE_FROM:
        return np.full(3, 255, dtype=np.int16)
    if colour.max() <= BLACK_UP_TO:
        return np.zeros(3, dtype=np.int16)
    return None


def _depth(lines: np.ndarray, fill: np.ndarray | None) -> int:
    """How many lines (from the first) are margin of ``fill``, with the
    JPEG ringing where it meets the picture; ``lines`` is (line, pixel,
    channel)."""
    if fill is None:
        return 0
    # A margin deeper than this leaves too little anyway (LEAST_KEPT).
    deepest = int(len(lines) * (1 - LEAST_KEPT)) + 1
    depth = 0
    while depth < deepest:  # a block at a time: most margins are thin
        block = lines[depth : min(depth + 32, deepest)]
        off = np.abs(block.astype(np.int16) - fill).max(axis=2)
        flat = np.flatnonzero((off <= TOLERANCE).mean(axis=1) < LINE_SHARE)
        if flat.size:
            depth += int(flat[0])
            break
        depth += len(block)
    if depth == 0 or depth >= deepest:
        return depth
    off = np.abs(lines[depth : depth + RINGING].astype(np.int16) - fill).max(axis=2)
    # The 8×8 JPEG blocks that hold the picture's edge ripple around it:
    # still mostly the fill's colour, only not within TOLERANCE.
    ringing = (off <= RINGING_TOLERANCE).mean(axis=1)
    rippled = np.flatnonzero(ringing < RINGING_SHARE)
    return depth + (int(rippled[0]) if rippled.size else len(ringing))


def margins(img: Image.Image) -> tuple[int, int, int, int] | None:
    """The box (left, top, right, bottom) of the picture inside its blank
    margins, None when there are none to cut."""
    a = np.asarray(img.convert("RGB"))
    h, w = a.shape[:2]
    if w < 16 or h < 16:
        return None
    top = _depth(a, _fill(a[0]))
    bottom = _depth(a[::-1], _fill(a[-1]))
    # Columns only within the rows that are left: a wide top band would
    # otherwise count towards every column.
    rows = a[top : h - bottom] if top + bottom < h else a
    cols = rows.transpose(1, 0, 2)
    left = _depth(cols, _fill(cols[0]))
    right = _depth(cols[::-1], _fill(cols[-1]))
    if not ((top and bottom) or (left and right)):
        return None
    edge_x = int(np.ceil(EDGE * w))
    edge_y = int(np.ceil(EDGE * h))
    box = (
        left + edge_x if left else 0,
        top + edge_y if top else 0,
        w - right - edge_x if right else w,
        h - bottom - edge_y if bottom else h,
    )
    if box[2] - box[0] < LEAST_KEPT * w or box[3] - box[1] < LEAST_KEPT * h:
        return None
    return box


def trim_margins(img: Image.Image) -> Image.Image:
    """``img`` without its blank margins (:func:`margins`), keeping its
    ``info``; ``img`` itself when it has none."""
    box = margins(img)
    if box is None:
        return img
    cut = img.crop(box)
    cut.info.update(img.info)
    return cut
