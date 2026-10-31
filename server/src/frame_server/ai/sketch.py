"""The composition's marks drawn over the picture for Claude to check, and
what the server measures of them.

The app draws the marks in pencil (``CompositionSketch.swift``); here they
are drawn plainly in a bright colour with numbers, so that the model that
checks them (``ai.check``) sees where each one really landed. Next to the
picture it gets numbers it cannot judge by eye: a line's angle, where a
horizon lies against the golden section and the thirds, whether a line
runs corner to corner.
"""

from __future__ import annotations

import io
import itertools
import math
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from .daily import Mark, Spot, View

#: The golden section and the thirds, as the app draws them.
GOLDEN = (0.382, 0.618)
THIRDS = (1 / 3, 2 / 3)
#: How near a thing has to lie to a grid line to be "on" it, and to be
#: near enough for the grid to stay (fractions of the side).
ON_LINE = 0.02
NEAR_LINE = 0.05
#: How near a line's end has to come to a corner to run "from corner to corner".
NEAR_CORNER = 0.04
#: A line within this many degrees of level or upright counts as level or upright.
LEVEL_DEGREES = 4.0

INK = (255, 0, 170)
EDGE = (255, 255, 255)
GRID = (0, 200, 255)


def _xy(spot: Spot, size: tuple[int, int]) -> tuple[float, float]:
    return spot.x * size[0], spot.y * size[1]


def _font(px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=px)
    except TypeError:  # an old Pillow without scalable default font
        return ImageFont.load_default()


def _loop_box(mark: Mark, size: tuple[int, int]) -> tuple[float, float, float, float]:
    cx, cy = _xy(mark.points[0], size)
    corner = mark.points[1] if len(mark.points) > 1 else mark.points[0]
    kx, ky = _xy(corner, size)
    rx, ry = max(abs(kx - cx), 6.0), max(abs(ky - cy), 6.0)
    return cx - rx, cy - ry, cx + rx, cy + ry


def _strokes(mark: Mark, size: tuple[int, int]) -> list[list[tuple[float, float]]]:
    """The mark's polylines in pixels (a loop is drawn apart)."""
    points = [_xy(p, size) for p in mark.points]
    if mark.shape == "triangle":
        return [[*points, points[0]]]
    if mark.shape == "rect":
        (ax, ay), (bx, by) = points[0], points[-1]
        return [[(ax, ay), (bx, ay), (bx, by), (ax, by), (ax, ay)]]
    if mark.shape == "underline":
        return [[points[0], points[-1]]]
    return [points]


def _arrow_head(line: list[tuple[float, float]], length: float) -> list[tuple[float, float]]:
    (x0, y0), (x1, y1) = line[-2], line[-1]
    angle = math.atan2(y1 - y0, x1 - x0)
    left = (x1 - length * math.cos(angle - 0.45), y1 - length * math.sin(angle - 0.45))
    right = (x1 - length * math.cos(angle + 0.45), y1 - length * math.sin(angle + 0.45))
    return [left, (x1, y1), right]


def _number_spot(mark: Mark, size: tuple[int, int], radius: float) -> tuple[float, float]:
    if mark.shape == "loop":
        _x0, y0, x1, _ = _loop_box(mark, size)
        spot = (x1 + radius * 0.6, y0 - radius * 0.6)
    elif mark.shape in ("arrow", "line", "rhythm", "underline"):
        x, y = _xy(mark.points[0], size)
        spot = (x - radius * 1.2, y - radius * 1.2)
    else:
        a = mark.anchor()
        spot = _xy(a, size)
    return (
        min(max(spot[0], radius + 1), size[0] - radius - 1),
        min(max(spot[1], radius + 1), size[1] - radius - 1),
    )


def draw(picture: Image.Image, view: View) -> Image.Image:
    """The picture with the view's grid and marks, each mark numbered from 1
    in the view's order."""
    img = picture.convert("RGB").copy()
    size = img.size
    pen = max(2, round(max(size) / 450))
    canvas = ImageDraw.Draw(img)
    cuts = GOLDEN if view.grid == "golden" else THIRDS if view.grid == "thirds" else ()
    for cut in cuts:
        x, y = cut * size[0], cut * size[1]
        canvas.line([(x, 0), (x, size[1])], fill=GRID, width=max(1, pen // 2))
        canvas.line([(0, y), (size[0], y)], fill=GRID, width=max(1, pen // 2))
    for mark in view.marks:
        if mark.shape == "loop":
            box = _loop_box(mark, size)
            canvas.ellipse(box, outline=EDGE, width=pen + 2)
            canvas.ellipse(box, outline=INK, width=pen)
            continue
        for line in _strokes(mark, size):
            if len(line) < 2:
                continue
            canvas.line(line, fill=EDGE, width=pen + 2, joint="curve")
            canvas.line(line, fill=INK, width=pen, joint="curve")
            if mark.shape == "arrow":
                head = _arrow_head(line, pen * 6)
                canvas.line(head, fill=EDGE, width=pen + 2)
                canvas.line(head, fill=INK, width=pen)
        if mark.shape == "rhythm":
            dot = pen * 2.2
            for x, y in (_xy(p, size) for p in mark.points):
                canvas.ellipse((x - dot, y - dot, x + dot, y + dot), fill=INK, outline=EDGE)
    radius = max(9.0, max(size) / 70)
    font = _font(round(radius * 1.3))
    for number, mark in enumerate(view.marks, start=1):
        x, y = _number_spot(mark, size, radius)
        canvas.ellipse((x - radius, y - radius, x + radius, y + radius), fill=EDGE, outline=INK)
        canvas.text((x, y), str(number), fill=(0, 0, 0), font=font, anchor="mm")
    return img


def jpeg(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    return out.getvalue()


def _nearest(value: float) -> str:
    """Where ``value`` (a fraction of a side) lies against the grids."""
    golden = min(GOLDEN, key=lambda g: abs(g - value))
    thirds = min(THIRDS, key=lambda t: abs(t - value))
    return (
        f"{value:.3f} (złoty podział {golden:.3f}: o {abs(value - golden):.3f}; "
        f"trójpodział {thirds:.3f}: o {abs(value - thirds):.3f})"
    )


def _corner(spot: Spot) -> str | None:
    for name, (cx, cy) in {
        "lewy górny": (0, 0),
        "prawy górny": (1, 0),
        "lewy dolny": (0, 1),
        "prawy dolny": (1, 1),
    }.items():
        if abs(spot.x - cx) <= NEAR_CORNER and abs(spot.y - cy) <= NEAR_CORNER:
            return name
    return None


def measure(mark: Mark, size: tuple[int, int]) -> str:
    """What the server measures of one mark, in a line of Polish."""
    points = mark.points
    if mark.shape in ("line", "arrow", "underline") and len(points) >= 2:
        a, b = points[0], points[-1]
        dx, dy = (b.x - a.x) * size[0], (b.y - a.y) * size[1]
        degrees = math.degrees(math.atan2(-dy, dx)) % 180
        parts = [f"kąt {degrees:.0f}°"]
        if min(degrees, 180 - degrees) <= LEVEL_DEGREES:
            parts.append(f"poziomo na wysokości {_nearest((a.y + b.y) / 2)}")
        elif abs(degrees - 90) <= LEVEL_DEGREES:
            parts.append(f"pionowo na szerokości {_nearest((a.x + b.x) / 2)}")
        ends = [_corner(a), _corner(b)]
        if all(ends):
            parts.append(f"z rogu do rogu ({ends[0]} – {ends[1]})")
        elif any(ends):
            parts.append(f"jeden koniec w rogu ({next(e for e in ends if e)})")
        else:
            parts.append("żaden koniec nie leży w rogu")
        return ", ".join(parts)
    if mark.shape == "rhythm":
        gaps = [
            math.hypot((q.x - p.x) * size[0], (q.y - p.y) * size[1])
            for p, q in itertools.pairwise(points)
        ]
        return f"{len(points)} uderzeń, odstępy (px): " + ", ".join(f"{g:.0f}" for g in gaps)
    centre = mark.anchor()
    return f"środek: x {_nearest(centre.x)}, y {_nearest(centre.y)}"


def measures(view: View, size: tuple[int, int]) -> list[str]:
    return [f"{n}. {m.shape} „{m.title}”: {measure(m, size)}" for n, m in enumerate(view.marks, 1)]


def grid_fits(view: View) -> bool:
    """Whether some mark of the view lies on a line of its grid: a level or
    upright line on it, or the middle of a loop, frame or triangle."""
    cuts = GOLDEN if view.grid == "golden" else THIRDS if view.grid == "thirds" else ()
    if not cuts:
        return True
    for mark in view.marks:
        places: list[tuple[str, float]] = []
        if mark.shape in ("line", "underline") and len(mark.points) >= 2:
            a, b = mark.points[0], mark.points[-1]
            if abs(a.y - b.y) <= 0.02:
                places.append(("y", (a.y + b.y) / 2))
            if abs(a.x - b.x) <= 0.02:
                places.append(("x", (a.x + b.x) / 2))
        elif mark.shape in ("loop", "rect", "triangle"):
            centre = mark.anchor()
            places += [("x", centre.x), ("y", centre.y)]
        if any(abs(value - cut) <= NEAR_LINE for _, value in places for cut in cuts):
            return True
    return False
