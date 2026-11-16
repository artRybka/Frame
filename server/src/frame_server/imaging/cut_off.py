"""Pictures a museum keeps cut off: the file ends early, and the decoder
fills the rest with flat grey.

The Muzeum Narodowe w Warszawie keeps Podoliński's copper plate
"Zmartwychwstanie Jezusa Chrystusa" (mnw:861190) as a JPEG of 3656 × 6000
px in 196 KB, with no end. A baseline JPEG decodes from the top down: the
first 7 % of its rows came out, the rest is the decoder's mid-grey (128 in
every channel). The museum made its thumbnail from that file, grey too,
and the work's card showed a grey board with a strip of copper on top
(Mateusz, 2026-11-16).

The fill is told from a picture by where it lies and how flat it is: the
bottom lines, every pixel within a few levels of 128, for a good share of
the picture's height, while its top is not such grey. A grey sheet a
museum pads a picture with lies on both sides, so it is never taken for a
cut-off file; a picture that is that grey all over is no picture either.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

#: The grey decoders fill a cut-off JPEG with (libjpeg, Pillow, ImageIO).
GREY = 128
#: How far (levels, any channel) a fill pixel may be from it: JPEG noise
#: once the thumbnail is saved again, never a painted grey.
TOLERANCE = 4
#: Share of a line's pixels that must be fill.
LINE_SHARE = 0.995
#: At least this share of the picture's height must be fill at the bottom:
#: a cut-off file loses most of the picture, a studio's grey floor is not
#: that flat for that long.
LEAST = 0.1
#: Lines looked at, at most (the original's thousands are not needed).
LINES = 512


def cut_off(img: Image.Image) -> bool:
    """Whether ``img`` is a picture whose file ended early: its bottom (or
    all of it) the decoder's flat grey."""
    w, h = img.size
    if w < 16 or h < 16:
        return False
    small = img if img.mode == "RGB" else img.convert("RGB")
    if (step := max(w, h) // LINES) > 1:
        small = small.reduce(step)  # box means: the fill stays its grey
    a = np.asarray(small)
    off = np.abs(a.astype(np.int16) - GREY).max(axis=2)
    flat = (off <= TOLERANCE).mean(axis=1) >= LINE_SHARE
    if flat.all():
        return True
    if flat[0]:
        return False  # grey at the top too: a sheet around it, not a cut
    depth = int(np.argmin(flat[::-1]))  # the flat lines from the bottom
    return depth >= max(2, LEAST * len(flat))
