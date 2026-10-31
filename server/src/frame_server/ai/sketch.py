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
import math
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from .daily import Mark, Spot, View

#: The golden section and the thirds, as the app draws them.
GOLDEN = (0.382, 0.618)
THIRDS = (1 / 3, 2 / 3)
HALVES = (0.5,)
#: The grid lines of each grid a take may lie on ("2×2" is the halves).
CUTS: dict[str, tuple[float, ...]] = {"golden": GOLDEN, "thirds": THIRDS, "halves": HALVES}
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
    elif mark.shape in ("arrow", "line", "underline"):
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
    for cut in CUTS.get(view.grid, ()):
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
        f"trójpodział {thirds:.3f}: o {abs(value - thirds):.3f}; "
        f"połowa: o {abs(value - 0.5):.3f})"
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
    if mark.shape == "line" and len(points) == 3:  # an open triangle, a wedge
        arms = [_degrees(points[1], p, size) for p in (points[0], points[2])]
        a = mark.points[1]
        text = (
            f"wierzchołek ({_px(a, size)}: x {_nearest(a.x)}, y {_nearest(a.y)}), "
            f"ramiona pod kątem {arms[0]:.0f}° i {arms[1]:.0f}°"
        )
        return text + (", biegnie poza obraz" if _outside(points) else "")
    if mark.shape in ("line", "arrow", "underline") and len(points) >= 2:
        a, b = points[0], points[-1]
        degrees = _degrees(a, b, size) % 180
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
        if _outside(points):
            parts.append("biegnie poza obraz")
        return ", ".join(parts)
    centre = mark.anchor()
    text = f"środek: x {_nearest(centre.x)}, y {_nearest(centre.y)}"
    return text + (", wychodzi poza obraz" if _outside(points) else "")


def _degrees(a: Spot, b: Spot, size: tuple[int, int]) -> float:
    """The direction from ``a`` to ``b`` on the picture, anticlockwise from
    the right, 0–360."""
    return math.degrees(math.atan2(-(b.y - a.y) * size[1], (b.x - a.x) * size[0])) % 360


def _px(spot: Spot, size: tuple[int, int]) -> str:
    return f"{spot.x * size[0]:.0f}, {spot.y * size[1]:.0f}"


def _outside(points: list[Spot]) -> bool:
    return any(not (0 <= p.x <= 1 and 0 <= p.y <= 1) for p in points)


def _crossing(a: Spot, b: Spot, c: Spot, d: Spot) -> tuple[float, float] | None:
    """Where segment ``a``–``b`` crosses segment ``c``–``d``, if they do."""
    rx, ry, sx, sy = b.x - a.x, b.y - a.y, d.x - c.x, d.y - c.y
    cross = rx * sy - ry * sx
    if abs(cross) < 1e-9:
        return None
    t = ((c.x - a.x) * sy - (c.y - a.y) * sx) / cross
    u = ((c.x - a.x) * ry - (c.y - a.y) * rx) / cross
    if not (0 <= t <= 1 and 0 <= u <= 1):
        return None
    return a.x + t * rx, a.y + t * ry


def _segments(mark: Mark) -> list[tuple[Spot, Spot]]:
    if mark.shape not in ("line", "triangle"):
        return []
    points = [*mark.points, mark.points[0]] if mark.shape == "triangle" else mark.points
    return [(points[n], points[n + 1]) for n in range(len(points) - 1)]


def crossings(view: View) -> list[tuple[int, int, float, float]]:
    """Where two of the view's lines (or triangle sides) cross on the
    picture: the numbers of the two marks and the place."""
    found: list[tuple[int, int, float, float]] = []
    marks = list(enumerate(view.marks, start=1))
    for n, first in marks:
        for m, second in marks[n:]:
            for a, b in _segments(first):
                for c, d in _segments(second):
                    spot = _crossing(a, b, c, d)
                    if spot and 0 <= spot[0] <= 1 and 0 <= spot[1] <= 1:
                        found.append((n, m, *spot))
    return found[:6]


def key_points(view: View) -> list[tuple[float, float]]:
    """The places a grid can hold: a level or upright line's height or
    width (as a place on one axis), the middle of a loop or frame, a
    triangle's or wedge's corners, where two lines cross."""
    spots: list[tuple[float, float]] = []
    for mark in view.marks:
        points = mark.points
        if mark.shape == "triangle" or (mark.shape == "line" and len(points) == 3):
            spots += [(p.x, p.y) for p in points if 0 <= p.x <= 1 and 0 <= p.y <= 1]
        if mark.shape in ("loop", "rect", "triangle"):
            centre = mark.anchor()
            spots.append((centre.x, centre.y))
    return spots + [(x, y) for _, _, x, y in crossings(view)]


def measures(view: View, size: tuple[int, int]) -> list[str]:
    lines = [f"{n}. {m.shape} „{m.title}”: {measure(m, size)}" for n, m in enumerate(view.marks, 1)]
    for n, m, x, y in crossings(view):
        lines.append(
            f"Przecięcie śladów {n} i {m} w ({x * size[0]:.0f}, {y * size[1]:.0f}): "
            f"x {_nearest(x)}, y {_nearest(y)}"
        )
    return lines


def grid_fits(view: View) -> bool:
    """Whether something of the view lies on or near a line of its grid: a
    level or upright line, a loop's or frame's middle, a triangle's or a
    wedge's corner, two lines' crossing."""
    cuts = CUTS.get(view.grid, ())
    if not cuts:
        return True
    places: list[float] = []
    for mark in view.marks:
        if mark.shape in ("line", "underline") and len(mark.points) == 2:
            a, b = mark.points
            if abs(a.y - b.y) <= 0.02:
                places.append((a.y + b.y) / 2)
            if abs(a.x - b.x) <= 0.02:
                places.append((a.x + b.x) / 2)
    places += [v for spot in key_points(view) for v in spot]
    return any(abs(value - cut) <= NEAR_LINE for value in places for cut in cuts)
