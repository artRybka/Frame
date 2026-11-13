"""What a light sheet shows, read from its pixels (Mateusz 2026-11-13,
"Studium dzieła" not for every work): a sheet nearly empty but for one
small sketch, notes scattered thinly over a page, a print in the middle of
a wide margin.

How much of a sheet is marked (``colors.ink_share``) cannot tell a page of
notes from a finished Ingres portrait in graphite: both are pale. Where the
marks lie can, at the extremes. Measured on the Art Institute's drawings
and the owner's three examples (2026-11-13; ink share, the share of the
sheet the marks span, the largest group's share of them):

==========================  ======  ======  =======
work                        ink     span    largest
==========================  ======  ======  =======
Church, Dyliżans (empty)    0.013   0.11    1.00
Church, Betesda (notes)     0.0045  0.38    0.25
Ingres, Robin (portrait)    0.013   0.80    0.78
Ingres, Gounod (portrait)   0.014   0.75    0.70
Ingres, a sheet of studies  0.041   0.86    0.41
Lucas, mezzotint (plate)    0.25    0.37    0.99
==========================  ======  ======  =======

Only the extremes are told here (:attr:`Sheet.empty`, :attr:`Sheet.scattered`);
a pale sheet between them is a question for the model (``ai.study_fit``).
A print whose plate is a dense rectangle inside a wide margin keeps its
study, drawn on the plate alone (:attr:`Sheet.plate`).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np
from PIL import Image

from .colors import INK_DISTANCE, PAPER_LIGHT, linear_to_oklab, u8_to_linear

#: The side the sheet is read at, and the museum's edge left out (a mount,
#: the scan's border).
SIDE = 384
EDGE = 0.04
#: The cells the sheet is divided into along its long side; one is marked
#: when more of it than :data:`CELL_INK` is.
CELLS = 32
CELL_INK = 0.04
#: A sheet marked less than this is pale (``colors.PALE_INK`` with a margin:
#: Ingres's portraits are 0.013 to 0.036).
PALE = 0.05
#: Nearly empty: pale, and every mark within this share of the sheet.
EMPTY_SPAN = 0.15
#: Notes scattered thinly: very pale, in this many groups or more, the
#: largest holding less than this share of what is marked.
SCATTERED_INK = 0.03
SCATTERED_GROUPS = 4
SCATTERED_LARGEST = 0.3
#: A plate: one group, filled densely, covering less than this share of
#: the sheet (Millet's etching on its whole sheet, 0.66, is no plate).
PLATE_AREA = 0.6
PLATE_FILL = 0.8
PLATE_DENSITY = 0.5
#: A row or column of the plate is marked over this share of it.
PLATE_EDGE = 0.25


@dataclass(frozen=True)
class Sheet:
    """A light sheet as its marks lie on it."""

    #: The share of the sheet marked.
    ink: float
    #: The share of the sheet the marks span (their bounding box).
    span: float
    #: Groups of marks (two cells or more).
    groups: int
    #: The largest group's share of the marked cells.
    largest: float
    #: The plate of a print inside a wide margin: x, y, w, h (fractions).
    plate: tuple[float, float, float, float] | None = None

    @property
    def pale(self) -> bool:
        return self.ink < PALE

    @property
    def empty(self) -> bool:
        """A sheet with almost nothing on it: one small sketch in a corner."""
        return self.pale and self.plate is None and self.span < EMPTY_SPAN

    @property
    def scattered(self) -> bool:
        """Notes and figures scattered thinly over a sheet."""
        return (
            self.ink < SCATTERED_INK
            and self.groups >= SCATTERED_GROUPS
            and self.largest < SCATTERED_LARGEST
        )


def read(img: Image.Image) -> Sheet | None:
    """The sheet ``img`` shows; None when it is no light sheet (a painting,
    a dark print)."""
    small = img.convert("RGB")
    small.thumbnail((SIDE, SIDE))
    width, height = small.size
    margin = int(min(width, height) * EDGE)
    small = small.crop((margin, margin, width - margin, height - margin))
    lab = linear_to_oklab(u8_to_linear(np.asarray(small)))
    paper = np.median(lab.reshape(-1, 3), axis=0)
    if paper[0] < PAPER_LIGHT:
        return None
    ink = np.linalg.norm(lab - paper, axis=2) > INK_DISTANCE
    share = float(ink.mean())
    rows, cols = ink.shape
    if cols >= rows:
        gh, gw = max(1, round(CELLS * rows / cols)), CELLS
    else:
        gh, gw = CELLS, max(1, round(CELLS * cols / rows))
    cells = np.array(
        [
            [
                ink[
                    i * rows // gh : (i + 1) * rows // gh, j * cols // gw : (j + 1) * cols // gw
                ].mean()
                for j in range(gw)
            ]
            for i in range(gh)
        ]
    )
    marked = cells > CELL_INK
    count = int(marked.sum())
    if not count:
        return Sheet(round(share, 4), 0.0, 0, 0.0)
    ys, xs = np.nonzero(marked)
    span = (xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1) / (gh * gw)
    groups = _groups(marked)
    largest = groups[0]
    box = _plate(ink, cells, largest, (gh, gw))
    plate = None
    if box is not None:  # in the whole picture's fractions, its edge put back
        px0, py0, px1, py1 = box
        plate = (
            round((px0 + margin) / width, 4),
            round((py0 + margin) / height, 4),
            round((px1 - px0) / width, 4),
            round((py1 - py0) / height, 4),
        )
    return Sheet(
        ink=round(share, 4),
        span=round(float(span), 3),
        groups=sum(1 for g in groups if len(g) >= 2),
        largest=round(len(largest) / count, 3),
        plate=plate,
    )


def _groups(marked: np.ndarray) -> list[list[tuple[int, int]]]:
    """The marked cells by group (touching, corners too), the largest first."""
    gh, gw = marked.shape
    seen = np.zeros_like(marked, dtype=bool)
    found: list[list[tuple[int, int]]] = []
    for i, j in zip(*np.nonzero(marked), strict=True):
        if seen[i, j]:
            continue
        seen[i, j] = True
        queue, group = deque([(int(i), int(j))]), []
        while queue:
            a, b = queue.popleft()
            group.append((a, b))
            for da in (-1, 0, 1):
                for db in (-1, 0, 1):
                    x, y = a + da, b + db
                    if 0 <= x < gh and 0 <= y < gw and marked[x, y] and not seen[x, y]:
                        seen[x, y] = True
                        queue.append((x, y))
        found.append(group)
    return sorted(found, key=len, reverse=True)


def _plate(
    ink: np.ndarray, cells: np.ndarray, group: list[tuple[int, int]], grid: tuple[int, int]
) -> tuple[int, int, int, int] | None:
    """The plate, when ``group`` is one dense rectangle inside a wide
    margin: its edges found again in the pixels (left, top, right, bottom)."""
    gh, gw = grid
    top, bottom = min(c[0] for c in group), max(c[0] for c in group)
    left, right = min(c[1] for c in group), max(c[1] for c in group)
    area = (bottom - top + 1) * (right - left + 1)
    if area / (gh * gw) >= PLATE_AREA or len(group) / area < PLATE_FILL:
        return None
    if cells[top : bottom + 1, left : right + 1].mean() < PLATE_DENSITY:
        return None
    rows, cols = ink.shape
    # The cells' box with a cell around it, read again pixel by pixel.
    y0, y1 = max(0, (top - 1) * rows // gh), min(rows, (bottom + 2) * rows // gh)
    x0, x1 = max(0, (left - 1) * cols // gw), min(cols, (right + 2) * cols // gw)
    part = ink[y0:y1, x0:x1]
    along = np.nonzero(part.mean(axis=1) > PLATE_EDGE)[0]
    across = np.nonzero(part.mean(axis=0) > PLATE_EDGE)[0]
    if not len(along) or not len(across):
        return None
    return (
        int(x0 + across[0]),
        int(y0 + along[0]),
        int(x0 + across[-1] + 1),
        int(y0 + along[-1] + 1),
    )


__all__ = ["Sheet", "read"]
