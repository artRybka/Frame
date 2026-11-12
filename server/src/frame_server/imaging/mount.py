"""The work itself, without the paper or mount around it, for small tiles.

A print or drawing is photographed on its whole sheet, often on its mount
or the photographer's backdrop too: Goya's etchings are a dark plate in
the middle of a wide cream sheet, a sketch is a few lines on a page. In
the cover tiles of Odkrywaj (four small squares on a card) such a picture
was mostly empty paper and looked like an error (Mateusz 2026-11-12).

Unlike the flat digital fill of :mod:`.margins`, paper is not flat: it is
told from the work by being one colour, the colour of the picture's edge.
Where the edge is one light, even colour all round, what differs from it
(the marks on it: ink, chalk, the plate, a pasted sheet) is the work, and
the tile is cut to the box that holds most of them. A backdrop around a
sheet around a picture takes a round each, :data:`ROUNDS` at most.

Only for tiles: the frame, the card and the viewer keep the whole sheet.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

from .color import linear_to_oklab, u8_to_linear

#: Long side the picture is looked at in (pixels): enough for a 1 % margin.
WORK_SIZE = 320
#: Width of the edge strip whose colour is the paper's (share of the short
#: side).
EDGE = 0.04
#: OKLab distance from the paper's colour that counts as a mark on it:
#: above foxing, stains and the shadow at a sheet's edge, below the
#: lightest graphite line.
INK = 0.055
#: The edge counts as one paper when this share of its pixels is within
#: :data:`INK` of its colour (a few marks reaching the edge are allowed).
EVEN_EDGE = 0.75
#: Paper (or a mount, or a backdrop) is at least this light in OKLab
#: (the sheets tried were 0.82–0.96): a painting's dark ground or a grey
#: photographer's backdrop around a painting is never taken for one.
PAPER_LIGHT = 0.62
#: A line (row or column) is part of the work when this share of it is
#: marked, after :data:`BLUR`. A signature or a line of a caption has less
#: than a drawn or printed area across the same line.
LINE_INK = 0.06
#: Gaps (share of the side) of unmarked lines bridged inside the work: the
#: white of a sky or between figures. A caption close under its plate
#: stays with it; the paper down to a museum's number does not.
GAP = 0.025
#: The box keeps most of the marks: of the marked lines' weight, at most
#: this share may fall outside (a collector's stamp, a pencilled number).
OUTSIDE = 0.12
#: Paper left around what is kept (share of the side), so the work keeps a
#: breath of its sheet and no line of it is cut.
PAD = 0.02
#: Cut only when it takes this much (share of a side, on either axis):
#: the tile already enlarges by a few percent (the app's CoverZoom).
LEAST_CUT = 0.08
#: What is left keeps at least this share of each side.
LEAST_KEPT = 0.2
#: Rounds: backdrop, mount, sheet.
ROUNDS = 3
#: Blur (pixels at :data:`WORK_SIZE`) before telling marks from paper: a
#: hatching of fine lines counts as an area, the paper's grain as nothing.
BLUR = 1.5

Box = tuple[float, float, float, float]


def _lab(img: Image.Image) -> np.ndarray:
    small = img.convert("RGB")
    small.thumbnail((WORK_SIZE, WORK_SIZE), Image.Resampling.BILINEAR)
    small = small.filter(ImageFilter.GaussianBlur(BLUR))
    return linear_to_oklab(u8_to_linear(np.asarray(small)))


def _paper(lab: np.ndarray) -> np.ndarray | None:
    """The paper's colour, from the picture's edge: None when the edge is
    not one light, even colour (the picture runs to it)."""
    h, w = lab.shape[:2]
    e = max(2, round(min(h, w) * EDGE))
    edge = np.concatenate(
        [
            lab[:e].reshape(-1, 3),
            lab[-e:].reshape(-1, 3),
            lab[e:-e, :e].reshape(-1, 3),
            lab[e:-e, -e:].reshape(-1, 3),
        ]
    )
    paper = np.median(edge, axis=0)
    if paper[0] < PAPER_LIGHT:
        return None
    if (np.linalg.norm(edge - paper, axis=1) <= INK).mean() < EVEN_EDGE:
        return None
    return paper


def _span(weights: np.ndarray, gap: int) -> tuple[int, int] | None:
    """The run of marked lines (``weights`` ≥ :data:`LINE_INK`, gaps up to
    ``gap`` bridged) that holds the most of the marks; widened by the next
    runs while they hold more than :data:`OUTSIDE` of what is left out."""
    on = weights >= LINE_INK
    if not on.any():
        return None
    runs: list[list[int]] = []
    for i in np.flatnonzero(on):
        if runs and i - runs[-1][1] <= gap + 1:
            runs[-1][1] = int(i)
        else:
            runs.append([int(i), int(i)])
    mass = [float(weights[a : b + 1].sum()) for a, b in runs]
    total = float(weights[on].sum())
    best = int(np.argmax(mass))
    lo, hi = best, best
    # Neighbouring runs join while what would be left out is too much.
    while True:
        kept = sum(mass[lo : hi + 1])
        if total - kept <= OUTSIDE * total:
            break
        left = mass[lo - 1] if lo > 0 else -1.0
        right = mass[hi + 1] if hi + 1 < len(runs) else -1.0
        if left < 0 and right < 0:
            break
        if left >= right:
            lo -= 1
        else:
            hi += 1
    return runs[lo][0], runs[hi][1]


def _round(lab: np.ndarray) -> tuple[int, int, int, int] | None:
    """The box (left, top, right, bottom, in ``lab``'s pixels) of the
    marks on the paper around them, None when the edge is no paper."""
    paper = _paper(lab)
    if paper is None:
        return None
    h, w = lab.shape[:2]
    marked = np.linalg.norm(lab - paper, axis=2) > INK
    rows = _span(marked.mean(axis=1), round(GAP * h))
    if rows is None:
        return None
    top, bottom = rows
    cols = _span(marked[top : bottom + 1].mean(axis=0), round(GAP * w))
    if cols is None:
        return None
    left, right = cols
    # The rows again, within the columns kept: a stamp beside the work
    # no longer holds a row in.
    rows = _span(marked[:, left : right + 1].mean(axis=1), round(GAP * h))
    if rows is not None:
        top, bottom = rows
    return left, top, right + 1, bottom + 1


def work_box(img: Image.Image) -> Box | None:
    """The box of the work inside its paper, mount or backdrop, as shares
    of the picture's width and height (left, top, right, bottom); None
    when there is nothing worth cutting."""
    lab = _lab(img)
    h, w = lab.shape[:2]
    if w < 32 or h < 32:
        return None
    left, top, right, bottom = 0, 0, w, h
    for _ in range(ROUNDS):
        inner = lab[top:bottom, left:right]
        ih, iw = inner.shape[:2]
        if iw < 32 or ih < 32:
            break
        found = _round(inner)
        if found is None:
            break
        cut_l, cut_t, cut_r, cut_b = found
        if cut_l + iw - cut_r < LEAST_CUT / 2 * iw and cut_t + ih - cut_b < LEAST_CUT / 2 * ih:
            break  # nothing more around it
        left, top, right, bottom = left + cut_l, top + cut_t, left + cut_r, top + cut_b
    pad_x, pad_y = PAD * w, PAD * h
    box = (
        max(0.0, (left - pad_x) / w),
        max(0.0, (top - pad_y) / h),
        min(1.0, (right + pad_x) / w),
        min(1.0, (bottom + pad_y) / h),
    )
    kept_x, kept_y = box[2] - box[0], box[3] - box[1]
    if kept_x > 1 - LEAST_CUT and kept_y > 1 - LEAST_CUT:
        return None
    if kept_x < LEAST_KEPT or kept_y < LEAST_KEPT:
        return None
    return box


def inside_mount(img: Image.Image) -> Image.Image:
    """``img`` cut to its work (:func:`work_box`), keeping its ``info``;
    ``img`` itself when there is nothing to cut."""
    box = work_box(img)
    if box is None:
        return img
    w, h = img.size
    cut = img.crop((round(box[0] * w), round(box[1] * h), round(box[2] * w), round(box[3] * h)))
    cut.info.update(img.info)
    return cut
