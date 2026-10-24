"""MULTI: several photos on one board, each in its own mat window.

A grid is drawn for the landscape canvas on a coarse C×R lattice over the
area inside the outer mat margin; each cell is ``(col, row, cols, rows)``
and is inset by half the gap on every side, so windows sit one gap apart.
A portrait canvas uses the same grids transposed.

"Automatic" picks, for the photos at hand, the grid whose windows' shapes
match the photos' shapes best: portrait photos go to tall windows,
landscape ones to wide windows.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

from .layout import AutoCrop, Crop, Fit, Plan, Rect, Window, crop_box

MIN_PHOTOS = 2
MAX_PHOTOS = 8
GAP_SHARE = 0.55  # the gap between windows, as a share of the outer margin
MIN_MARGIN = 0.03  # outer margin, fraction of the canvas's short side
NEAR_BEST = 1.15  # automatic: grids this close to the best fit are equally good


@dataclass(frozen=True)
class Grid:
    id: str  # "A", "B", ... within its count
    name: str
    cols: int
    rows: int
    cells: tuple[tuple[float, float, float, float], ...]

    @property
    def key(self) -> str:
        return f"{len(self.cells)}{self.id}"


def _g(gid: str, name: str, cols: int, rows: int, *cells: tuple[float, ...]) -> Grid:
    return Grid(gid, name, cols, rows, tuple((c[0], c[1], c[2], c[3]) for c in cells))


GRIDS: dict[int, tuple[Grid, ...]] = {
    2: (
        _g("A", "Para pionów", 6, 1, (1, 0, 2, 1), (3, 0, 2, 1)),
        _g("B", "Duży i mały", 12, 12, (0, 0, 8, 12), (8, 3, 4, 6)),
    ),
    3: (
        _g("A", "Tryptyk", 3, 1, (0, 0, 1, 1), (1, 0, 1, 1), (2, 0, 1, 1)),
        _g("B", "Jeden i dwa", 3, 2, (0, 0, 2, 2), (2, 0, 1, 1), (2, 1, 1, 1)),
        _g("C", "Pion i dwa poziomy", 12, 12, (0, 0, 4, 12), (4, 0, 8, 6), (4, 6, 8, 6)),
    ),
    4: (
        _g("A", "Siatka 2×2", 8, 2, (1, 0, 3, 1), (4, 0, 3, 1), (1, 1, 3, 1), (4, 1, 3, 1)),
        _g("B", "Rząd pionów", 4, 12, (0, 2, 1, 8), (1, 2, 1, 8), (2, 2, 1, 8), (3, 2, 1, 8)),
        _g("C", "Duży i trzy", 12, 12, (0, 0, 9, 12), (9, 0, 3, 4), (9, 4, 3, 4), (9, 8, 3, 4)),
    ),
    5: (
        _g(
            "A", "Środek i cztery rogi", 4, 2,
            (1, 0, 2, 2), (0, 0, 1, 1), (0, 1, 1, 1), (3, 0, 1, 1), (3, 1, 1, 1),
        ),
        _g(
            "B", "Pion i cztery", 12, 12,
            (0, 0, 4, 12), (4, 0, 4, 6), (8, 0, 4, 6), (4, 6, 4, 6), (8, 6, 4, 6),
        ),
    ),
    6: (
        _g(
            "A", "Siatka 3×2", 3, 2,
            (0, 0, 1, 1), (1, 0, 1, 1), (2, 0, 1, 1), (0, 1, 1, 1), (1, 1, 1, 1), (2, 1, 1, 1),
        ),
        _g(
            "B", "Duży i pięć", 16, 12,
            (2, 0, 8, 8), (10, 0, 4, 4), (10, 4, 4, 4), (2, 8, 4, 4), (6, 8, 4, 4), (10, 8, 4, 4),
        ),
    ),
    7: (
        _g(
            "A", "Środek i boki", 4, 3,
            (1, 0, 2, 3), (0, 0, 1, 1), (0, 1, 1, 1), (0, 2, 1, 1),
            (3, 0, 1, 1), (3, 1, 1, 1), (3, 2, 1, 1),
        ),
        _g(
            "B", "Cztery nad trzema", 8, 2,
            (0, 0, 2, 1), (2, 0, 2, 1), (4, 0, 2, 1), (6, 0, 2, 1),
            (1, 1, 2, 1), (3, 1, 2, 1), (5, 1, 2, 1),
        ),
    ),
    8: (
        _g(
            "A", "Siatka 4×2", 4, 2,
            (0, 0, 1, 1), (1, 0, 1, 1), (2, 0, 1, 1), (3, 0, 1, 1),
            (0, 1, 1, 1), (1, 1, 1, 1), (2, 1, 1, 1), (3, 1, 1, 1),
        ),
        _g(
            "B", "Duży i siedem", 48, 12,
            (0, 0, 24, 7), (24, 0, 12, 3.5), (36, 0, 12, 3.5), (24, 3.5, 12, 3.5),
            (36, 3.5, 12, 3.5), (0, 7, 16, 5), (16, 7, 16, 5), (32, 7, 16, 5),
        ),
    ),
}  # fmt: skip


def grid_rects(grid: Grid, canvas: tuple[int, int], margin: float) -> list[Rect]:
    """The grid's windows on the canvas, in cell order."""
    cw, ch = canvas
    portrait = ch > cw
    outer = round(min(cw, ch) * max(margin, MIN_MARGIN))
    gap = round(outer * GAP_SHARE)
    iw, ih = cw - 2 * outer, ch - 2 * outer
    cols, rows = (grid.rows, grid.cols) if portrait else (grid.cols, grid.rows)
    rects: list[Rect] = []
    for cell in grid.cells:
        c, r, w, h = (cell[1], cell[0], cell[3], cell[2]) if portrait else cell
        x0 = round(outer + c / cols * iw + gap / 2)
        y0 = round(outer + r / rows * ih + gap / 2)
        x1 = round(outer + (c + w) / cols * iw - gap / 2)
        y1 = round(outer + (r + h) / rows * ih - gap / 2)
        rects.append((x0, y0, x1 - x0, y1 - y0))
    return rects


def assign(rects: Sequence[Rect], aspects: Sequence[float]) -> tuple[list[int], float]:
    """Which photo goes in which window, and how badly the shapes differ.

    Sorting both by shape and pairing in order is the best match for this
    cost; among equal shapes the earlier photo gets the larger window.
    Returns photo index per window, and the area-weighted mismatch.
    """
    cells = sorted(range(len(rects)), key=lambda i: (rects[i][2] / rects[i][3], -_area(rects[i])))
    photos = sorted(range(len(aspects)), key=lambda i: (aspects[i], i))
    order = [0] * len(rects)
    total_area = sum(_area(r) for r in rects)
    cost = 0.0
    for cell, photo in zip(cells, photos, strict=True):
        order[cell] = photo
        w, h = rects[cell][2], rects[cell][3]
        cost += abs(math.log(w / h / aspects[photo])) * _area(rects[cell]) / total_area
    return order, cost


def _area(rect: Rect) -> int:
    return rect[2] * rect[3]


def choose(
    aspects: Sequence[float],
    canvas: tuple[int, int],
    margin: float,
    pinned: str = "auto",
    seed: str = "",
) -> tuple[Grid, list[Rect], list[int]]:
    """A grid for these photos: the pinned one if it exists for their count,
    else one that fits their shapes. Among grids that fit about equally well
    the choice is random, but always the same for the same ``seed`` (the
    photos' ids), so redrawing a board keeps its grid."""
    options = GRIDS[len(aspects)]
    scored = []
    for grid in options:
        rects = grid_rects(grid, canvas, margin)
        order, cost = assign(rects, aspects)
        if grid.id == pinned:
            return grid, rects, order
        scored.append((cost, grid, rects, order))
    best = min(s[0] for s in scored)
    near = [s for s in scored if s[0] <= best * NEAR_BEST + 0.02]
    digest = hashlib.sha1((seed or repr(aspects)).encode(), usedforsecurity=False).hexdigest()
    _, grid, rects, order = random.Random(digest).choice(near)
    return grid, rects, order


def plan_multi(
    sizes: Sequence[tuple[int, int]],
    canvas: tuple[int, int],
    margin: float,
    pinned: str = "auto",
    seed: str = "",
    auto: Sequence[AutoCrop | None] | None = None,
) -> tuple[Plan, list[int]]:
    """The board: one window per photo, each cropped to its window (by the
    photo's interest analysis in ``auto``, else centred). Returns the plan
    and, per window, which photo it shows."""
    aspects = [w / h for w, h in sizes]
    _, rects, order = choose(aspects, canvas, margin, pinned, seed)
    windows = []
    for rect, photo in zip(rects, order, strict=True):
        aspect = rect[2] / rect[3]
        picker = auto[photo] if auto else None
        found = picker(aspect, [1.0]) if picker else []
        crop = found[0] if found else Crop()
        windows.append(Window(rect, crop_box(sizes[photo], aspect, crop), "picture", crop))
    return Plan(Fit.MULTI, canvas, windows), order
