"""The drawn contour of a picture: long thin lines darker than what they run
through (Matisse's black, Gauguin's blue), as opposed to the shadows of a
dark picture.

Mateusz 2026-11-13 00:31 (the card of Matisse's „Akt z białym szalem”, whose
bar showed only reds and pinks): „aż się prosi na pasku koloru czarna kreska
konturu”; 06:52: „Kontury kolorowe także. C, ale kreska od góry trochę
krótsza niż dolna.” The colour analysis (``colors.analyse``) cannot see a
line: k-means on 64 pixels averages it with the shadows beside it, and it is
never a large colour. So it is looked for here, on the thumbnail, apart.

How (sketch 38, measured on 86 paintings: no line for any of 41 old masters,
the Danish golden age or Hammershøi; one for Matisse, Bernard, Beckmann,
Kirchner, Van Gogh's Bedroom):

- a line is where the picture with its thin darks filled in (a closing of
  the OKLab lightness, as wide as the widest line) is clearly lighter than
  the picture: a dark line (``DARK_*``), or a coloured one only a little
  darker but of a colour of its own beside what it runs through
  (``COLOURED_*``);
- it is long (``LONG``), not a fleck, a crack or a letter, and not the edge
  of a mount or a frame;
- it is *free*: no dark mass round it. In a dark picture narrow darks are
  the shadows of folds and fingers, so the darker the picture, the more
  free line it takes (``need``).
"""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from ..imaging.color import linear_to_oklab, linear_to_u8, oklab_to_linear, u8_to_linear
from ..imaging.layout import load_image
from .models import Contour

#: Raise it when the rule changes: the library's pictures are measured
#: again once (``Player.contours``).
CONTOUR_VERSION = 1
#: Measured on the library's thumbnail at most this long a side.
SIZE = 640
#: Left out round the picture: its edge, a black border, a mount's line.
TRIM = 0.025
#: The widest line, of the short side: the closing's size.
WIDEST = 0.03
#: A dark line: this much darker than round it, and at most this light.
DARK_HAT, DARK_LIGHT = 0.16, 0.5
#: A coloured line: less darker, lighter, but coloured and of a colour of
#: its own (OKLab a,b this far from the ring round it), not a darker shade
#: of what it runs through.
COLOURED_HAT, COLOURED_LIGHT, COLOURED_CHROMA, COLOURED_OWN = 0.07, 0.62, 0.045, 0.03
#: A line spans and runs at least this much of the short side.
SPAN, LONG = 0.06, 0.08
#: Near the edge (of the short side): a line mostly there is a frame's.
EDGE = 0.06
#: A dark mass: this dark; a line is free where less than ``CROWD`` of a
#: window three closings wide round it is dark mass.
MASS_LIGHT, CROWD = 0.4, 0.25
#: How much free line (in short sides) makes a contour: ``BASE`` and
#: ``PER_MASS`` for each whole of the picture in dark mass.
BASE, PER_MASS = 2.5, 3.0
#: The line's colour: its darkest quarter, deepened (a thumbnail softens a
#: line into what is beside it).
DARKEST, DEEPEN = 25.0, 0.78


def contour(img: Image.Image, tags: list[str] | None = None) -> Contour | None:
    """The picture's drawn contour, or None. A picture of one tint has
    none: its lines are all it has (``"monochrome"`` in ``tags``)."""
    if tags and "monochrome" in tags:
        return None
    lab = _lab(img)
    found = lines(lab)
    if found is None:
        return None
    free, mass, width = found
    light = lab[..., 0]
    short = min(light.shape)
    length = free.sum() / max(width, 1.0) / short
    if length < need(mass):
        return None
    core = free & (light <= np.percentile(light[free], DARKEST))
    colour = lab[core].mean(0)
    colour[0] *= DEEPEN
    rgb = linear_to_u8(np.clip(oklab_to_linear(colour), 0, 1))
    return Contour(
        hex="#{:02x}{:02x}{:02x}".format(*rgb),
        length=round(float(length), 1),
        width=round(float(width / short * 100), 2),
    )


def need(mass: float) -> float:
    """The free line (short sides) a picture with ``mass`` of dark mass
    needs for a contour."""
    return BASE + PER_MASS * mass


def lines(lab: np.ndarray) -> tuple[np.ndarray, float, float] | None:
    """The free lines of a picture in OKLab, its share of dark mass and the
    lines' usual width (pixels); None when it has no line."""
    light = lab[..., 0].astype(np.float32)
    high, wide = light.shape
    short = min(high, wide)
    size = max(5, round(short * WIDEST) | 1)
    shape = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    hat = cv2.morphologyEx(light, cv2.MORPH_CLOSE, shape) - light
    chroma = np.hypot(lab[..., 1], lab[..., 2])
    dark, dark_widths = _long((hat >= DARK_HAT) & (light <= DARK_LIGHT), lab, None)
    coloured = (
        (hat >= COLOURED_HAT) & (light <= COLOURED_LIGHT) & (chroma >= COLOURED_CHROMA) & ~dark
    )
    own, own_widths = _long(coloured, lab, COLOURED_OWN)
    found = dark | own
    widths = dark_widths + own_widths
    if not widths:
        return None
    mass = (light <= MASS_LIGHT) & ~found
    crowd = cv2.blur(mass.astype(np.float32), (3 * size, 3 * size))
    free = found & (crowd < CROWD)
    if not free.any():
        return None
    return free, float(mass.mean()), float(np.median(widths))


def _lab(img: Image.Image) -> np.ndarray:
    small = load_image(img).convert("RGB")
    small.thumbnail((SIZE, SIZE), Image.Resampling.BILINEAR)
    wide, high = small.size
    cut = round(min(wide, high) * TRIM)
    small = small.crop((cut, cut, wide - cut, high - cut))
    return np.asarray(linear_to_oklab(u8_to_linear(np.asarray(small))), dtype=np.float32)


def _long(mask: np.ndarray, lab: np.ndarray, own: float | None) -> tuple[np.ndarray, list[float]]:
    """The long lines of ``mask`` and their widths; with ``own``, only those
    whose colour (a,b) is that far from the ring round them."""
    high, wide = mask.shape
    short = min(high, wide)
    edge = int(short * EDGE)
    count, ids, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    reach = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 3)
    keep = np.zeros(count, bool)
    widths: list[float] = []
    for i in range(1, count):
        x, y, w, h, area = (int(v) for v in stats[i])
        if np.hypot(w, h) < short * SPAN:
            continue
        part = ids[y : y + h, x : x + w] == i
        width = 2 * float(np.percentile(reach[y : y + h, x : x + w][part], 90))
        if area / max(width, 1.0) < short * LONG:
            continue
        rows, cols = np.mgrid[y : y + h, x : x + w]
        near = (rows < edge) | (cols < edge) | (rows >= high - edge) | (cols >= wide - edge)
        if (near & part).sum() > 0.5 * part.sum():
            continue
        if own is not None and not _own(ids, i, lab, (x, y, w, h), width, own):
            continue
        keep[i] = True
        widths.append(width)
    return keep[ids], widths


def _own(
    ids: np.ndarray,
    i: int,
    lab: np.ndarray,
    box: tuple[int, int, int, int],
    width: float,
    own: float,
) -> bool:
    """Whether line ``i`` is of a colour of its own beside what is round it."""
    x, y, w, h = box
    high, wide = ids.shape
    pad = max(3, int(width * 1.5))
    y0, y1, x0, x1 = (
        max(0, y - pad),
        min(high, y + h + pad),
        max(0, x - pad),
        min(wide, x + w + pad),
    )
    part = ids[y0:y1, x0:x1] == i
    ring = (
        cv2.dilate(part.astype(np.uint8), np.ones((2 * pad + 1, 2 * pad + 1), np.uint8)).astype(
            bool
        )
        & ~part
    )
    near = lab[y0:y1, x0:x1]
    if not ring.any():
        return False
    return float(np.hypot(*(near[part][:, 1:].mean(0) - near[ring][:, 1:].mean(0)))) >= own
