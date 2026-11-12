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
    from .daily import Key, Mark, Spot, View
    from .lines import Found

#: The golden section and the thirds, as the app draws them.
GOLDEN = (0.382, 0.618)
THIRDS = (1 / 3, 2 / 3)
HALVES = (0.5,)
#: The grid lines of each grid a take may lie on: across the width (x) and
#: down the height (y). "3x2" is thirds across and halves down.
CUTS: dict[str, tuple[tuple[float, ...], tuple[float, ...]]] = {
    "golden": (GOLDEN, GOLDEN),
    "thirds": (THIRDS, THIRDS),
    "halves": (HALVES, HALVES),
    "3x2": (THIRDS, HALVES),
    "2x3": (HALVES, THIRDS),
}
#: A golden spiral's radius shrinks by φ every quarter turn.
PHI = (1 + math.sqrt(5)) / 2
SPIRAL_GROWTH = math.log(PHI) / (math.pi / 2)
#: How near a thing has to lie to a grid line to be "on" it, and to be
#: near enough for the grid to stay (fractions of the side).
ON_LINE = 0.02
NEAR_LINE = 0.05
#: How near a line's end has to come to a corner to run "from corner to corner".
NEAR_CORNER = 0.04
#: A line within this many degrees of level or upright counts as level or upright.
LEVEL_DEGREES = 4.0

#: A rhythm's strokes are drawn this much longer than the forms they stand on.
STRETCH = 1.2

INK = (255, 0, 170)
EDGE = (255, 255, 255)
GRID = (0, 200, 255)
#: The places the composition rests on (P1…) and the picture's own lines (L1…).
KEY = (255, 220, 0)
FOUND = (0, 230, 255)
SLANT = (255, 120, 0)


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


def spiral(
    start: tuple[float, float], through: tuple[float, float], eye: tuple[float, float]
) -> list[tuple[float, float]]:
    """A golden spiral in pixels from ``start`` into its ``eye``, turning the
    way ``through`` lies from the line between them (as the app draws it)."""
    dx, dy = start[0] - eye[0], start[1] - eye[1]
    radius = math.hypot(dx, dy)
    if radius < 2:
        return []
    cross = dx * (through[1] - eye[1]) - dy * (through[0] - eye[0])
    turn = -1.0 if cross < 0 else 1.0
    angle = math.atan2(dy, dx)
    end = math.log(radius / 1.5) / SPIRAL_GROWTH
    steps = max(int(end / (math.pi / 12)), 2)
    found = []
    for step in range(steps + 1):
        theta = end * step / steps
        r = radius * math.exp(-SPIRAL_GROWTH * theta)
        found.append(
            (
                eye[0] + r * math.cos(angle + turn * theta),
                eye[1] + r * math.sin(angle + turn * theta),
            )
        )
    return found


def beats(points: list[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    """A rhythm's strokes: one along each repeated form (a pair of points),
    all parallel to their common direction and a little longer than the
    forms (as the app draws them: straightened, no line between them)."""
    pairs = [(points[n], points[n + 1]) for n in range(0, len(points) - 1, 2)]
    ux = uy = 0.0
    for (ax, ay), (bx, by) in pairs:
        dx, dy = bx - ax, by - ay
        if dy < 0 or (dy == 0 and dx < 0):  # every one pointing the same way
            dx, dy = -dx, -dy
        length = math.hypot(dx, dy) or 1.0
        ux, uy = ux + dx / length, uy + dy / length
    norm = math.hypot(ux, uy) or 1.0
    ux, uy = ux / norm, uy / norm
    found = []
    for (ax, ay), (bx, by) in pairs:
        mx, my = (ax + bx) / 2, (ay + by) / 2
        half = math.hypot(bx - ax, by - ay) / 2 * STRETCH
        found.append([(mx - ux * half, my - uy * half), (mx + ux * half, my + uy * half)])
    return found


def smooth(points: list[tuple[float, float]], samples: int = 10) -> list[tuple[float, float]]:
    """A Catmull-Rom curve through the points (as the app draws a path)."""
    if len(points) < 3:
        return points
    found = []
    for n in range(len(points) - 1):
        p0, p1 = points[max(n - 1, 0)], points[n]
        p2, p3 = points[n + 1], points[min(n + 2, len(points) - 1)]
        for step in range(samples):
            t = step / samples
            found.append(
                tuple(
                    0.5
                    * (
                        2 * p1[k]
                        + (p2[k] - p0[k]) * t
                        + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t * t
                        + (3 * p1[k] - p0[k] - 3 * p2[k] + p3[k]) * t**3
                    )
                    for k in (0, 1)
                )
            )
    found.append(points[-1])
    return found  # type: ignore[return-value]


def speed_lines(path: list[tuple[float, float]], gap: float) -> list[list[tuple[float, float]]]:
    """Two short strokes beside the start of a movement's path, trailing it."""
    found = []
    for side, a, b in ((1.0, 0.0, 0.45), (-1.0, 0.08, 0.38)):
        first = int(len(path) * a)
        last = max(int(len(path) * b), first + 2)
        line = []
        for n in range(first, min(last, len(path))):
            (x0, y0), (x1, y1) = path[max(n - 1, 0)], path[min(n + 1, len(path) - 1)]
            angle = math.atan2(y1 - y0, x1 - x0) + math.pi / 2
            dx, dy = side * gap * math.cos(angle), side * gap * math.sin(angle)
            line.append((path[n][0] + dx, path[n][1] + dy))
        if len(line) >= 2:
            found.append(line)
    return found


#: An echo's ring (its radius, of the picture's longer side) and the broken
#: line between two rings: how far it bows and how long a dash and its gap are.
ECHO_RING = 0.03
ECHO_BOW = 0.07
ECHO_DASH = 0.023


def echo_rings(
    points: list[tuple[float, float]], size: tuple[int, int]
) -> list[list[tuple[float, float]]]:
    """A small ring at each of an echo's places."""
    r = max(size) * ECHO_RING
    return [
        [
            (x + r * math.cos(2 * math.pi * n / 24), y + r * math.sin(2 * math.pi * n / 24))
            for n in range(25)
        ]
        for x, y in points
    ]


def echo_dashes(
    points: list[tuple[float, float]], size: tuple[int, int]
) -> list[list[tuple[float, float]]]:
    """The broken, slightly bowed line from each of an echo's rings to the
    next: its dashes, from ring to ring."""
    r = max(size) * ECHO_RING
    gap = r + max(size) * 0.005
    found: list[list[tuple[float, float]]] = []
    for (ax, ay), (bx, by) in itertools.pairwise(points):
        length = math.hypot(bx - ax, by - ay)
        span = length - 2 * gap
        if span <= 0:
            continue
        ux, uy = (bx - ax) / length, (by - ay) / length
        bow = ECHO_BOW * length
        count = max(int(span / (max(size) * ECHO_DASH)), 2)
        for k in range(count):
            dash = []
            for t in (k / count, (k + 0.275) / count, (k + 0.55) / count):
                d = gap + t * span
                lift = bow * math.sin(math.pi * d / length)
                dash.append((ax + ux * d + uy * lift, ay + uy * d - ux * lift))
            found.append(dash)
    return found


def _strokes(mark: Mark, size: tuple[int, int]) -> list[list[tuple[float, float]]]:
    """The mark's polylines in pixels (a loop is drawn apart)."""
    points = [_xy(p, size) for p in mark.points]
    if mark.shape == "spiral" and len(points) == 3:
        return [spiral(*points)]
    if mark.shape == "rhythm":
        return beats(points)
    if mark.shape == "rays":
        return [[end, points[0]] for end in points[1:]]
    if mark.shape == "motion":
        path = smooth(points)
        return [path, *speed_lines(path, max(2, round(max(size) / 450)) * 5)]
    if mark.shape == "triangle":
        return [[*points, points[0]]]
    if mark.shape == "rect":
        (ax, ay), (bx, by) = points[0], points[-1]
        return [[(ax, ay), (bx, ay), (bx, by), (ax, by), (ax, ay)]]
    if mark.shape == "underline":
        return [[points[0], points[-1]]]
    if mark.shape == "echo":
        return [*echo_rings(points, size), *echo_dashes(points, size)]
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
    elif mark.shape == "spiral":
        x, y = _xy(mark.points[-1], size)
        spot = (x + radius * 1.3, y - radius * 1.3)
    elif mark.shape in ("arrow", "line", "underline", "motion"):
        x, y = _xy(mark.points[0], size)
        spot = (x - radius * 1.2, y - radius * 1.2)
    elif mark.shape == "rays":
        x, y = _xy(mark.points[1], size)
        spot = (x - radius * 1.2, y - radius * 1.2)
    elif mark.shape == "rhythm":
        (x, y), _ = beats([_xy(p, size) for p in mark.points])[0]
        spot = (x - radius * 1.2, y - radius * 1.2)
    elif mark.shape == "echo":
        x, y = _xy(mark.points[0], size)
        ring = max(size) * ECHO_RING
        spot = (x + ring + radius * 0.8, y - ring - radius * 0.4)
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
    across, down = CUTS.get(view.grid, ((), ()))
    for cut in across:
        canvas.line(
            [(cut * size[0], 0), (cut * size[0], size[1])], fill=GRID, width=max(1, pen // 2)
        )
    for cut in down:
        canvas.line(
            [(0, cut * size[1]), (size[0], cut * size[1])], fill=GRID, width=max(1, pen // 2)
        )
    for mark in view.marks:
        if mark.shape == "loop":
            box = _loop_box(mark, size)
            canvas.ellipse(box, outline=EDGE, width=pen + 2)
            canvas.ellipse(box, outline=INK, width=pen)
            continue
        for n, line in enumerate(_strokes(mark, size)):
            if len(line) < 2:
                continue
            canvas.line(line, fill=EDGE, width=pen + 2, joint="curve")
            canvas.line(line, fill=INK, width=pen, joint="curve")
            if mark.shape == "arrow" or (mark.shape == "motion" and n == 0):
                head = _arrow_head(line, pen * (9 if mark.shape == "motion" else 6))
                canvas.line(head, fill=EDGE, width=pen + 2)
                canvas.line(head, fill=INK, width=pen)
    radius = max(9.0, max(size) / 70)
    font = _font(round(radius * 1.3))
    for number, mark in enumerate(view.marks, start=1):
        x, y = _number_spot(mark, size, radius)
        canvas.ellipse((x - radius, y - radius, x + radius, y + radius), fill=EDGE, outline=INK)
        canvas.text((x, y), str(number), fill=(0, 0, 0), font=font, anchor="mm")
    return img


def draw_keys(picture: Image.Image, keys: list[Key]) -> Image.Image:
    """The picture with the places a take rests on as yellow rings, P1…"""
    img = picture.convert("RGB").copy()
    canvas = ImageDraw.Draw(img)
    radius = max(8, img.width // 90)
    font = _font(radius + 4)
    for n, key in enumerate(keys, start=1):
        x, y = key.x * img.width, key.y * img.height
        box = (x - radius, y - radius, x + radius, y + radius)
        canvas.ellipse(box, outline=(0, 0, 0), width=max(2, radius // 3) + 2)
        canvas.ellipse(box, outline=KEY, width=max(2, radius // 3))
        canvas.text(
            (x + radius + 3, y - radius),
            f"P{n}",
            fill=KEY,
            font=font,
            stroke_width=2,
            stroke_fill=(0, 0, 0),
        )
    return img


def draw_found(picture: Image.Image, found: Found) -> Image.Image:
    """The picture with its own lines (``ai.lines``): level and upright ones
    turquoise and named L1…, slants orange."""
    img = picture.convert("RGB").copy()
    w, h = img.size
    canvas = ImageDraw.Draw(img, "RGBA")
    font = _font(max(14, w // 45))
    for s in found.slants:
        canvas.line(
            [(s.x1 * w, s.y1 * h), (s.x2 * w, s.y2 * h)], fill=SLANT, width=max(2, w // 400)
        )
    for e in found.edges:
        if e.axis == "y":
            ends = [(e.start * w, e.pos * h), (e.end * w, e.pos * h)]
            at = (e.start * w + 6, e.pos * h + 4)
        else:
            ends = [(e.pos * w, e.start * h), (e.pos * w, e.end * h)]
            at = (e.pos * w + 6, e.start * h + 6)
        canvas.line(ends, fill=FOUND, width=max(3, w // 300))
        canvas.text(at, e.name, fill=FOUND, font=font, stroke_width=2, stroke_fill=(0, 0, 0))
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
    if mark.shape == "spiral" and len(points) == 3:
        return _spiral_measure(mark, size)
    if mark.shape == "line" and len(points) == 3:  # an open triangle, a wedge
        arms = [_degrees(points[1], p, size) for p in (points[0], points[2])]
        a = mark.points[1]
        text = (
            f"wierzchołek ({_px(a, size)}: x {_nearest(a.x)}, y {_nearest(a.y)}), "
            f"ramiona pod kątem {arms[0]:.0f}° i {arms[1]:.0f}°"
        )
        return text + (", biegnie poza obraz" if _outside(points) else "")
    if mark.shape == "rhythm":
        return _rhythm_measure(mark, size)
    if mark.shape == "rays":
        eye = points[0]
        text = (
            f"punkt zbiegu ({_px(eye, size)}: x {_nearest(eye.x)}, y {_nearest(eye.y)}), "
            f"{_many(len(points) - 1, 'promienie', 'promieni')} pod kątem "
            + ", ".join(f"{_degrees(eye, p, size):.0f}°" for p in points[1:])
        )
        return text + (", wychodzi poza obraz" if _outside(points) else "")
    if mark.shape in ("line", "arrow", "underline", "motion") and len(points) >= 2:
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
        parts += _armature(a, b, size)
        if _outside(points):
            parts.append("biegnie poza obraz")
        return ", ".join(parts)
    if mark.shape == "echo":
        return "miejsca: " + "; ".join(_px(p, size) for p in points)
    centre = mark.anchor()
    text = f"środek: x {_nearest(centre.x)}, y {_nearest(centre.y)}"
    return text + (", wychodzi poza obraz" if _outside(points) else "")


CORNERS = {
    "lewego górnego": (0.0, 0.0),
    "prawego górnego": (1.0, 0.0),
    "lewego dolnego": (0.0, 1.0),
    "prawego dolnego": (1.0, 1.0),
}


def _armature(a: Spot, b: Spot, size: tuple[int, int]) -> list[str]:
    """How a line lies against the picture's own lines: its diagonals, the
    lines from the other corners at right angles to them (golden
    triangles) and the sides of the squares on its short sides (rabatment)."""
    w, h = size
    ax, ay, bx, by = a.x * w, a.y * h, b.x * w, b.y * h
    length = math.hypot(bx - ax, by - ay)
    if length < 1:
        return []
    degrees = math.degrees(math.atan2(-(by - ay), bx - ax)) % 180
    diagonal = math.degrees(math.atan2(h, w))
    reach = NEAR_CORNER * math.hypot(w, h)

    def off(angle: float) -> float:
        return min(abs(degrees - angle) % 180, 180 - abs(degrees - angle) % 180)

    def through() -> str | None:
        for name, (cx, cy) in CORNERS.items():
            gap = abs((bx - ax) * (ay - cy * h) - (ax - cx * w) * (by - ay)) / length
            if gap <= reach:
                return name
        return None

    found: list[str] = []
    corner = through()
    if min(off(diagonal), off(180 - diagonal)) <= LEVEL_DEGREES:
        side = min(off(diagonal), off(180 - diagonal))
        found.append(
            f"biegnie po przekątnej obrazu (o {side:.0f}°)"
            if corner
            else f"równolegle do przekątnej obrazu (o {side:.0f}°)"
        )
    elif min(off(90 + diagonal), off(90 - diagonal)) <= LEVEL_DEGREES and corner:
        side = min(off(90 + diagonal), off(90 - diagonal))
        found.append(f"prostopadle do przekątnej z rogu {corner} (złoty trójkąt, o {side:.0f}°)")
    if abs(degrees - 90) <= LEVEL_DEGREES and w > h:
        x = (a.x + b.x) / 2
        if min(abs(x - h / w), abs(x - (1 - h / w))) <= ON_LINE:
            found.append("na linii rabatu (bok kwadratu z krótszego boku obrazu)")
    if min(degrees, 180 - degrees) <= LEVEL_DEGREES and h > w:
        y = (a.y + b.y) / 2
        if min(abs(y - w / h), abs(y - (1 - w / h))) <= ON_LINE:
            found.append("na linii rabatu (bok kwadratu z krótszego boku obrazu)")
    return found


def _many(count: int, few: str, many: str) -> str:
    """A count in Polish: 2–4 (22–24, …) take one form, the rest another."""
    return f"{count} {few if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14) else many}"


def _rhythm_measure(mark: Mark, size: tuple[int, int]) -> str:
    """A rhythm's beats: how many, where they stand, how far apart."""
    strokes = beats([_xy(p, size) for p in mark.points])
    middles = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in strokes]
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) / STRETCH for a, b in strokes]
    gaps = [math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in itertools.pairwise(middles)]
    (ax, ay), (bx, by) = strokes[0]
    degrees = math.degrees(math.atan2(-(by - ay), bx - ax)) % 180
    return (
        f"{_many(len(strokes), 'kreski', 'kresek')} pod kątem {degrees:.0f}°, środki w "
        + " ".join(f"({x:.0f}, {y:.0f})" for x, y in middles)
        + f", długości {', '.join(f'{v:.0f}' for v in lengths)} px, odstępy "
        + ", ".join(f"{v:.0f}" for v in gaps)
        + " px"
    )


def _spiral_measure(mark: Mark, size: tuple[int, int]) -> str:
    start, through, eye = (_xy(p, size) for p in mark.points)
    path = spiral(start, through, eye)
    turns = math.log(math.hypot(start[0] - eye[0], start[1] - eye[1]) / 1.5) / (
        SPIRAL_GROWTH * 2 * math.pi
    )
    cross = (start[0] - eye[0]) * (through[1] - eye[1]) - (start[1] - eye[1]) * (
        through[0] - eye[0]
    )
    way = "zgodnie z ruchem wskazówek zegara" if cross >= 0 else "przeciwnie do wskazówek zegara"
    quarter = max(1, round(len(path) / max(turns * 4, 1)))
    marks = ", ".join(f"({x:.0f}, {y:.0f})" for x, y in path[quarter : quarter * 5 : quarter])
    e = mark.points[-1]
    text = (
        f"oko w ({_px(e, size)}: x {_nearest(e.x)}, y {_nearest(e.y)}), skręca {way}, "
        f"kolejne ćwierć obroty w {marks}"
    )
    return text + (", zaczyna się poza obrazem" if _outside(mark.points[:1]) else "")


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
        if mark.shape in ("loop", "rect", "triangle", "spiral"):
            centre = mark.anchor()
            spots.append((centre.x, centre.y))
        if mark.shape == "rays" and 0 <= points[0].x <= 1 and 0 <= points[0].y <= 1:
            spots.append((points[0].x, points[0].y))
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
    wedge's corner, a spiral's eye, two lines' crossing."""
    across, down = CUTS.get(view.grid, ((), ()))
    if not across and not down:
        return True
    view = view.inside()  # the grid divides the picture's field
    xs: list[float] = []
    ys: list[float] = []
    for mark in view.marks:
        if mark.shape in ("line", "underline") and len(mark.points) == 2:
            a, b = mark.points
            if abs(a.y - b.y) <= 0.02:
                ys.append((a.y + b.y) / 2)
            if abs(a.x - b.x) <= 0.02:
                xs.append((a.x + b.x) / 2)
    for x, y in key_points(view):
        xs.append(x)
        ys.append(y)
    for key in view.keys:  # what the grid was chosen by (``ai.grid``)
        xs += [key.x] if "x" in key.axis else []
        ys += [key.y] if "y" in key.axis else []
    return any(abs(x - cut) <= NEAR_LINE for x in xs for cut in across) or any(
        abs(y - cut) <= NEAR_LINE for y in ys for cut in down
    )
