"""The pen's strokes laid on the picture's own edges.

The few strokes of the study sheet's pen come from a model that saw the
picture (``ai.pen``): it knows what is a ship and what a wave, but it puts
its points a little beside what it means, and some of its lines follow
nothing at all. On the sheet that reads as chaos (Mateusz 2026-11-12
14:50: "szczegółowość rysunku pozostawia sporo do życzenia. Może być
oczywiście schematyczna, ale teraz nieraz jest chaotyczna").

So what the model says is taken as where to look, and the line itself is
measured: each stroke is moved onto the edge of the picture that runs
beside it (within :data:`REACH`), as one smooth line, not point by point;
where it finds no edge at its ends it is cut back to where the form ends,
and a stroke that lies on no edge for most of its way is not drawn.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt

Array = npt.NDArray[Any]
#: A stroke: its points (fractions of the picture), whether it keeps its
#: corners, whether it closes.
Line = tuple[Sequence[tuple[float, float]], bool, bool]

#: The picture is read this long (pixels): finer is the paint's own texture.
LONG = 720
#: How far from where it was put a stroke may be moved (of the longer side).
REACH = 0.028
#: A closed form's stroke is moved by no more than this much of the form's
#: lesser side.
SMALL = 0.3
#: Steps: along a stroke, and across it where an edge is looked for (pixels).
ALONG = 3.0
ACROSS = 1.0
#: What an edge is worth against staying near where the stroke was put
#: (:data:`NEAR`, at the end of the reach) and against bending between one
#: step and the next (:data:`STIFF`, a pixel a step).
NEAR = 0.3
STIFF = 1.0
#: What an edge is measured against: the strong edges of the whole picture
#: (this much of them, where nothing lies around) and the edges around the
#: place (their mean within :data:`AROUND` pixels, this many times).
CALM = 0.3
ROUGH = 2.0
AROUND = 14.0
#: An edge is one from this strength (of the picture's strong edges, its
#: 95th percentile of the places that have any).
EDGE = 0.3
#: A stroke is drawn when it lies on an edge for this much of its way, and
#: its ends are cut back to where it does; what is left must be this long
#: (of the longer side) unless it closes.
HELD = 0.55
SHORT = 0.05
#: A stroke that runs for more than this much of its way within
#: :data:`BESIDE` pixels of one drawn before it says the same thing twice.
TWICE = 0.6
BESIDE = 5.0
#: How finely the moved stroke is put down again (pixels off the line it
#: was moved to), and the most points it then has.
FINE = 1.8
POINTS = 24


def edges(rgb: Array) -> tuple[Array, float]:
    """The edges of the picture, :data:`LONG` pixels long, and its scale to
    the picture: at each place how strongly the picture changes and which
    way (three numbers, xx, xy, yy: across a line of direction ``n`` the
    change is the root of ``n·J·n``), against the strong edges of the whole
    picture and against what lies around the place, so that one stroke of
    the brush among a thousand in a rough sea is not an edge, and the faint
    rim of a cloud in a still sky is."""
    scale = LONG / max(rgb.shape[:2])
    small = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    # (the paint's texture taken off, the forms' edges kept)
    flat = cv2.pyrMeanShiftFiltering(cv2.cvtColor(small, cv2.COLOR_RGB2BGR), 6, 22, maxLevel=1)
    lab = cv2.cvtColor(cv2.GaussianBlur(flat, (0, 0), 1.2), cv2.COLOR_BGR2LAB).astype(np.float32)
    lab[..., 0] *= 100 / 255
    turn = np.zeros((*lab.shape[:2], 3), np.float32)
    for channel in range(3):
        gx = cv2.Sobel(lab[..., channel], cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(lab[..., channel], cv2.CV_32F, 0, 1, ksize=3)
        turn += np.stack([gx * gx, gx * gy, gy * gy], axis=2)
    whole = np.sqrt(turn[..., 0] + turn[..., 2])
    some = whole[whole > 4.0]
    strong = max(float(np.percentile(some, 95)) if some.size > 50 else 1.0, 12.0)
    around = cv2.GaussianBlur(whole, (0, 0), AROUND) / strong
    against = strong * (CALM + ROUGH * around)
    return turn / (against * against)[..., None], scale


def _smooth(points: Array, closed: bool) -> Array:
    """The line as the nib draws it through its points (Chaikin)."""
    if closed:
        points = np.concatenate([points, points[:1]])
    for _ in range(3):
        if len(points) < 3:
            break
        a, b = points[:-1], points[1:]
        cut = np.empty((2 * len(a), 2), np.float32)
        cut[0::2], cut[1::2] = 0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b
        if closed:
            points = np.concatenate([cut, cut[:1]])
        else:
            points = np.concatenate([points[:1], cut, points[-1:]])
    return points


def _stepped(points: Array, step: float) -> Array:
    """The line in even steps."""
    seg = np.hypot(*np.diff(points, axis=0).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    if s[-1] < step:
        return points
    t = np.linspace(0, s[-1], max(int(s[-1] / step) + 1, 2))
    return np.stack([np.interp(t, s, points[:, 0]), np.interp(t, s, points[:, 1])], axis=1)


def _moved(strength: Array, line: Array, reach: float) -> tuple[Array, Array]:
    """The line moved across itself onto the edge beside it, as one smooth
    line (the best way through the places it may pass, by how strong the
    edge is there, how near, and how little it bends), and how strong the
    edge is under each of its points."""
    h, w = strength.shape[:2]
    d = np.gradient(line, axis=0)
    d /= np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-6)[:, None]
    normal = np.stack([-d[:, 1], d[:, 0]], axis=1)
    offs = np.arange(-reach, reach + 1e-6, ACROSS, dtype=np.float32)
    at = line[:, None, :] + normal[:, None, :] * offs[None, :, None]
    turn = cv2.remap(
        strength,
        at[..., 0].astype(np.float32),
        at[..., 1].astype(np.float32),
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    # how strongly the picture changes across the stroke there: an edge
    # that runs along it, not one that crosses it
    nx, ny = normal[:, None, 0], normal[:, None, 1]
    across = nx * nx * turn[..., 0] + 2 * nx * ny * turn[..., 1] + ny * ny * turn[..., 2]
    gain = np.sqrt(np.maximum(across, 0))
    inside = (at[..., 0] >= 0) & (at[..., 0] <= w - 1) & (at[..., 1] >= 0) & (at[..., 1] <= h - 1)
    worth = np.minimum(gain, 1.0) - NEAR * (offs / max(reach, 1e-6)) ** 2
    worth = np.where(inside, worth, worth - 0.2)
    bend = STIFF * ((offs[:, None] - offs[None, :]) / ALONG) ** 2
    n, k = worth.shape
    best = worth[0].copy()
    back = np.zeros((n, k), np.int32)
    for i in range(1, n):
        through = best[None, :] - bend  # to [this place, from that one]
        back[i] = np.argmax(through, axis=1)
        best = through[np.arange(k), back[i]] + worth[i]
    way = np.zeros(n, np.int32)
    way[-1] = int(np.argmax(best))
    for i in range(n - 1, 0, -1):
        way[i - 1] = back[i, way[i]]
    rows = np.arange(n)
    return at[rows, way], gain[rows, way]


def _runs(held: Array) -> tuple[int, int]:
    """The stroke without its ends that lie on nothing: from the first of
    its points on an edge to the last (a gap of a few steps in between is
    the edge lost for a moment, not the form's end)."""
    on = np.flatnonzero(held)
    return (int(on[0]), int(on[-1]) + 1) if on.size else (0, 0)


def follow(rgb: Array, lines: Sequence[Line], reach: float = REACH) -> list[Line | None]:
    """Each stroke on the picture's own edge, or None where it lies on
    none or runs where a stroke before it already does: the same strokes,
    in order (so what matters most is given first)."""
    strength, scale = edges(rgb)
    size = np.array([rgb.shape[1], rgb.shape[0]], np.float32) * scale
    drawn_on = np.zeros(strength.shape[:2], np.uint8)
    out: list[Line | None] = []
    for points, sharp, closed in lines:
        given = np.array(points, np.float32).reshape(-1, 2) * size
        closed = closed and len(given) > 2
        kept = None
        if len(given) > 1:
            # (a small form's sides must not both be moved onto one edge)
            least = float(np.min(np.ptp(given, axis=0))) if closed else np.inf
            kept = _followed(strength, given, sharp, closed, min(reach * LONG, SMALL * least))
        if kept is not None and _twice(drawn_on, kept, closed):
            kept = None
        if kept is None:
            out.append(None)
            continue
        way = np.round(kept * 4).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(drawn_on, [way], closed, 1, round(2 * BESIDE), cv2.LINE_8, 2)
        spots = [(float(x / size[0]), float(y / size[1])) for x, y in kept]
        out.append((spots, sharp, closed))
    return out


def _twice(drawn_on: Array, line: Array, closed: bool) -> bool:
    """Whether the stroke runs, for most of its way, where one was drawn."""
    walked = _stepped(np.concatenate([line, line[:1]]) if closed else line, ALONG)
    at = np.round(walked).astype(np.int32)
    h, w = drawn_on.shape
    inside = (at[:, 0] >= 0) & (at[:, 0] < w) & (at[:, 1] >= 0) & (at[:, 1] < h)
    met = drawn_on[at[inside, 1], at[inside, 0]]
    return bool(met.size and met.mean() > TWICE)


def _followed(
    strength: Array, given: Array, sharp: bool, closed: bool, reach: float
) -> Array | None:
    """One stroke moved onto its edge and put down again in a few points
    (pixels of the picture as read), or None when it lies on none."""
    straight = sharp or len(given) == 2
    drawn = given if straight else _smooth(given, closed)
    if straight and closed:
        drawn = np.concatenate([drawn, drawn[:1]])
    line = _stepped(drawn, ALONG)
    if len(line) < 4:
        return None
    moved, gain = _moved(strength, line, reach)
    on = gain >= EDGE
    # (a step lost between two that hold is the edge lost for a moment, not
    # the form's end)
    first, last = (
        (0, len(moved)) if closed else _runs(np.convolve(on, np.ones(5) / 5, "same") >= 0.5)
    )
    long = (last - first) * ALONG
    if last - first < 4 or on[first:last].mean() < HELD or (not closed and long < SHORT * LONG):
        return None
    if straight:
        # which of its sides each step is on
        ends = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(drawn, axis=0).T))])
        side = np.searchsorted(ends, np.linspace(0, ends[-1], len(line)), side="right") - 1
        side = np.minimum(side, len(drawn) - 2)
        return _sides(moved[first:last], side[first:last], closed)
    kept = moved[first : last - 1] if closed else moved[first:last]
    fine = FINE
    while True:
        few = cv2.approxPolyDP(kept.reshape(-1, 1, 2).astype(np.float32), fine, closed)
        if len(few) <= POINTS:
            break
        fine *= 1.3
    few = few.reshape(-1, 2)
    return few if len(few) >= (3 if closed else 2) else None


def _sides(moved: Array, side: Array, closed: bool) -> Array | None:
    """A stroke of straight sides: each side the straight line through
    where its steps were moved to, its corners where two sides meet."""
    fitted = []
    for k in np.unique(side):
        steps = moved[side == k]
        if len(steps) < 3:
            continue
        vx, vy, x0, y0 = cv2.fitLine(
            steps.astype(np.float32), cv2.DIST_HUBER, 0, 0.01, 0.01
        ).ravel()
        fitted.append((np.array([x0, y0]), np.array([vx, vy]), steps[0], steps[-1]))
    if not fitted or (closed and len(fitted) < 3):
        return None

    def onto(spot: Array, line: tuple[Array, Array, Array, Array]) -> Array:
        base, way = line[0], line[1]
        return np.asarray(base + way * float((spot - base) @ way))

    def meet(a: tuple[Array, Array, Array, Array], b: tuple[Array, Array, Array, Array]) -> Array:
        cross = float(a[1][0] * b[1][1] - a[1][1] * b[1][0])
        between = (a[3] + b[2]) / 2
        if abs(cross) < 0.2:  # nearly one line: where the one ends and the other begins
            return np.asarray((onto(between, a) + onto(between, b)) / 2)
        gap = b[0] - a[0]
        along = float(gap[0] * b[1][1] - gap[1] * b[1][0]) / cross
        corner = a[0] + a[1] * along
        # (two sides that meet far from where the stroke turned do not meet)
        return np.asarray(corner if np.hypot(*(corner - between)) < 4 * BESIDE else between)

    corners = [meet(a, b) for a, b in itertools.pairwise(fitted)]
    if closed:  # (from the corner the stroke was begun at)
        corners.insert(0, meet(fitted[-1], fitted[0]))
    else:
        corners = [onto(fitted[0][2], fitted[0]), *corners, onto(fitted[-1][3], fitted[-1])]
    return np.array(corners, np.float32)


# -- the picture's own contours, drawn ------------------------------------------
#
# A dozen strokes by a model, however well laid on the picture's edges, are
# marks and rounded lumps, not a drawing (Mateusz 2026-11-12 15:50: "nadal
# jest zbyt ogólny. Chciałbym żeby był bardziej szczegółowy. Dokładny.
# Rysował dzieło, a nie kilka zaznaczeń i obłych brył"). What is exact is
# the picture itself: so the pen draws the picture's own contours, and the
# model's strokes only say where its subject is. First the forms (the long
# contours), then the detail beside them (shorter ones: a face, a hand, a
# row of buttons), as much as a place takes; away from the subject only a
# few of the longest lines (Mateusz 14:50: "dokładny tam gdzie dzieło tego
# wymaga ... a pominięty lub bardzo ogólny w reszcie dzieła").

#: A stroke that guides the drawing: its points (fractions of the picture),
#: whether it closes, whether it is of the picture's subject.
Guide = tuple[Sequence[tuple[float, float]], bool, bool]
#: A line drawn: its points (fractions of the picture) and how heavy (0…1).
Drawn = tuple[list[tuple[float, float]], float]

#: The contours are read from the picture this long (pixels).
DRAW_LONG = 1000
#: The paint's texture is taken off first (mean shift: pixels, colour).
FLAT = (8, 22)
#: An edge among edges counts for less (as in :func:`edges`): against the
#: picture's strong edges (this much of them) and their mean around the
#: place (this many times, within this much of the longer side).
DRAW_CALM = 0.45
DRAW_ROUGH = 1.6
DRAW_AROUND = 0.03
#: Where a contour begins and what carries it on (of a strong edge).
CONTOUR = (0.22, 0.5)
#: Two contours are one when their ends are this near (pixels) and they go
#: on the same way (the cosine between them at least this).
JOIN_REACH = 7.0
JOIN_TURN = 0.75
#: A contour is a form from this length (of the longer side), a detail from
#: this; away from the subject only one this long is drawn, and so many.
FORM = 0.075
DETAIL = 0.016
FAR = 0.11
FAR_MOST = 6
#: A contour weaker than this (of a strong edge, among what is around) is
#: not drawn.
FAINT = 0.3
#: Nor one that by itself is less than this of a strong edge (the weave of
#: the canvas in a dark, still ground, which nothing around outweighs).
BARE = 0.28
#: A detail is drawn beside a form: within about this much of the longer
#: side of one.
BESIDE_FORM = 0.045
#: How much line a place takes (pixels of line a pixel of the picture,
#: within about :data:`INK_AROUND` of the longer side).
INK_MOST = 0.2
INK_AROUND = 0.03
#: The most lines of a drawing, and the most points of one.
DRAW_MOST = 160
DRAW_POINTS = 48
#: Around a guide's stroke of the subject, this much of the longer side is
#: the subject.
SUBJECT_AROUND = 0.05
#: A line along the picture's border (within this much of the longer side
#: for most of its way) is the frame's.
BORDER = 0.02

_NEIGHBOURS = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))


def _thin(rgb: Array) -> tuple[Array, Array, Array]:
    """The picture's contours one pixel thin, and how strong the picture's
    edge is at each place: among what is around, and by itself (both of a
    strong edge of the picture)."""
    flat = cv2.pyrMeanShiftFiltering(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), *FLAT, maxLevel=1)
    lab = cv2.cvtColor(cv2.GaussianBlur(flat, (0, 0), 1.4), cv2.COLOR_BGR2LAB).astype(np.float32)
    lab[..., 0] *= 100 / 255
    best = np.zeros(lab.shape[:2], np.float32)
    bx, by = best.copy(), best.copy()
    for channel in range(3):  # (the channel that changes most there)
        gx = cv2.Sobel(lab[..., channel], cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(lab[..., channel], cv2.CV_32F, 0, 1, ksize=3)
        size = gx * gx + gy * gy
        more = size > best
        best, bx, by = np.where(more, size, best), np.where(more, gx, bx), np.where(more, gy, by)
    change = np.sqrt(best)
    some = change[change > 2.0]
    strong = max(float(np.percentile(some, 95)) if some.size > 100 else 10.0, 10.0)
    around = cv2.GaussianBlur(change / strong, (0, 0), DRAW_AROUND * max(rgb.shape[:2]))
    gain = 1.0 / (DRAW_CALM + DRAW_ROUGH * around)
    unit = 8000.0 / strong  # (into what Canny takes)
    dx = np.clip(bx * gain * unit, -32000, 32000).astype(np.int16)
    dy = np.clip(by * gain * unit, -32000, 32000).astype(np.int16)
    thin = cv2.Canny(dx, dy, CONTOUR[0] * 8000.0, CONTOUR[1] * 8000.0, L2gradient=True)
    return thin > 0, change * gain / strong, change / strong


def _walked(thin: Array) -> list[Array]:
    """The thin contours as lines: each walked from an end, going on the
    way it came where it can."""
    h, w = thin.shape
    left = np.zeros((h + 2, w + 2), bool)
    left[1:-1, 1:-1] = thin
    beside = sum(np.roll(np.roll(left, dy, 0), dx, 1) for dy, dx in _NEIGHBOURS) * left
    ys, xs = np.nonzero(left)
    out: list[Array] = []

    def walk(y: int, x: int) -> list[tuple[int, int]]:
        line: list[tuple[int, int]] = []
        py = px = 0
        while True:
            left[y, x] = False
            line.append((x - 1, y - 1))
            best: tuple[int, int] | None = None
            most = -9.0
            for dy, dx in _NEIGHBOURS:
                if left[y + dy, x + dx]:
                    square = dy == 0 or dx == 0
                    way = (dy * py + dx * px) / (1.0 if square else 1.414) + (0.3 if square else 0)
                    if way > most:
                        best, most = (dy, dx), way
            if best is None:
                return line
            py, px = best
            y, x = y + py, x + px

    for i in np.argsort(beside[ys, xs], kind="stable"):  # ends first
        y, x = int(ys[i]), int(xs[i])
        if not left[y, x]:
            continue
        ahead = walk(y, x)
        left[y, x] = True  # (begun in its middle, or a ring: the other way too)
        back = walk(y, x)
        line = back[::-1] + ahead[1:] if len(back) > 1 else ahead
        if len(line) >= 6:
            out.append(np.array(line, np.float32))
    return out


def _joined(lines: list[Array]) -> list[Array]:
    """Lines whose ends meet and that go on the same way, as one."""
    held: list[Array | None] = list(lines)

    def heading(line: Array, end: bool) -> Array:
        n = min(len(line) - 1, 6)
        way = (line[-1] - line[-1 - n]) if end else (line[0] - line[n])
        return np.asarray(way / max(float(np.hypot(*way)), 1e-6))

    while True:
        ends = [
            (at, end, line[-1] if end else line[0], heading(line, end))
            for at, line in enumerate(held)
            if line is not None
            for end in (False, True)
        ]
        if not ends:
            break
        spots = np.array([e[2] for e in ends])
        used: set[int] = set()
        for at, end, spot, way in ends:
            if at in used:
                continue
            near = np.flatnonzero(np.hypot(*(spots - spot).T) < JOIN_REACH)
            best, least = -1, np.inf
            for b in near:
                other, _, there, back = ends[b]
                if other == at or other in used:
                    continue
                gap = there - spot
                far = float(np.hypot(*gap))
                same = float(way @ -back)
                if same < JOIN_TURN or (far > 1e-6 and float(way @ gap) / far < 0.3):
                    continue
                if far - 3 * same < least:
                    best, least = int(b), far - 3 * same
            if best < 0:
                continue
            other, other_end = ends[best][0], ends[best][1]
            first, second = held[at], held[other]
            assert first is not None and second is not None
            held[at] = np.concatenate(
                [first if end else first[::-1], second[::-1] if other_end else second]
            )
            held[other] = None
            used |= {at, other}
        if not used:
            break
    return [line for line in held if line is not None]


def _eased(line: Array, sigma: float = 2.0) -> Array:
    """The line without the pixels' steps."""
    if len(line) < 5:
        return line
    kernel = cv2.getGaussianKernel(int(sigma * 6) | 1, sigma).ravel()
    pad = len(kernel) // 2
    padded = np.concatenate([np.repeat(line[:1], pad, 0), line, np.repeat(line[-1:], pad, 0)])
    return np.stack(
        [np.convolve(padded[:, 0], kernel, "valid"), np.convolve(padded[:, 1], kernel, "valid")], 1
    ).astype(np.float32)


def _subject(shape: tuple[int, int], guide: Sequence[Guide]) -> Array | None:
    """Where the picture's subject is, by the guide's strokes of it (0…1);
    None when it has none."""
    h, w = shape
    long = max(h, w)
    there = np.zeros((h, w), np.uint8)
    for points, closed, subject in guide:
        if not subject or len(points) < 2:
            continue
        at = (np.array(points, np.float32) * (w, h)).astype(np.int32).reshape(-1, 1, 2)
        if closed and len(at) > 2:
            cv2.fillPoly(there, [at], 255)
        cv2.polylines(there, [at], closed, 255, max(int(SUBJECT_AROUND * long), 3), cv2.LINE_8)
    if not there.any():
        return None
    return np.asarray(cv2.GaussianBlur(there.astype(np.float32) / 255, (0, 0), 0.02 * long))


def drawing(rgb: Array, guide: Sequence[Guide] = ()) -> list[Drawn]:
    """The picture drawn in its own contours: the forms first, the heaviest
    first, then the detail beside them; with a guide, away from the subject
    only a few long lines."""
    scale = DRAW_LONG / max(rgb.shape[:2])
    small = cv2.resize(
        rgb,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
    )
    h, w = small.shape[:2]
    long = max(h, w)
    subject = _subject((h, w), guide)
    thin, strength, change = _thin(small)
    found: list[tuple[Array, float, float, float | None, Array]] = []
    for walked in _joined(_walked(thin)):
        line = _eased(walked)
        length = float(np.hypot(*np.diff(line, axis=0).T).sum())
        if length < DETAIL * long:
            continue
        at = np.clip(np.round(line).astype(np.int32), 0, (w - 1, h - 1))
        edge = np.minimum.reduce([at[:, 0], at[:, 1], w - 1 - at[:, 0], h - 1 - at[:, 1]])
        strong = float(strength[at[:, 1], at[:, 0]].mean())
        bare = float(change[at[:, 1], at[:, 0]].mean())
        if float((edge < BORDER * long).mean()) > 0.5 or strong < FAINT or bare < BARE:
            continue
        inside = float(subject[at[:, 1], at[:, 0]].mean()) if subject is not None else None
        found.append((line, length, strong, inside, at))
    found.sort(key=lambda f: -f[1] * min(f[2], 1.5))
    forms = [f for f in found if (f[3] is None or f[3] > 0.3) and f[1] >= FORM * long]
    away = [f for f in found if f[3] is not None and f[3] <= 0.3 and f[1] >= FAR * long]
    first = forms + away[:FAR_MOST]
    body = np.zeros((h, w), np.uint8)
    for line, *_ in forms:
        cv2.polylines(body, [np.round(line).astype(np.int32).reshape(-1, 1, 2)], False, 255, 1)
    near: Array = cv2.GaussianBlur(body.astype(np.float32) / 255, (0, 0), BESIDE_FORM * long)
    beside = near / max(float(near.max()), 1e-6)
    cell = 8
    ink = np.zeros((h // cell + 1, w // cell + 1), np.float32)

    def put(line: Array, at: Array) -> None:
        step = np.hypot(*np.diff(line, axis=0).T)
        np.add.at(ink, (at[:, 1] // cell, at[:, 0] // cell), np.append(step, step[-1]) / cell**2)

    out: list[tuple[Array, float]] = []
    for line, _, strong, _, at in first:
        put(line, at)
        out.append((line, float(np.clip((strong - 0.2) / 0.8, 0.35, 1))))
    chosen = {id(f[0]) for f in first}
    spread = INK_AROUND * long / cell
    wet = cv2.GaussianBlur(ink, (0, 0), spread)
    for line, _, strong, inside, at in found:
        if len(out) >= DRAW_MOST:
            break
        if id(line) in chosen or (inside is not None and inside < 0.3):
            continue
        by = float(beside[at[:, 1], at[:, 0]].mean())
        if by < 0.25 and (inside is None or inside < 0.6):
            continue
        if float(wet[at[:, 1] // cell, at[:, 0] // cell].mean()) > INK_MOST:
            continue
        put(line, at)
        wet = cv2.GaussianBlur(ink, (0, 0), spread)
        out.append((line, float(np.clip((strong - 0.2) / 0.8, 0.2, 0.7))))
    return [(_few(line, (w, h), DRAW_POINTS, 0.6), weight) for line, weight in out]


def _few(line: Array, size: tuple[int, int], most: int, fine: float) -> list[tuple[float, float]]:
    """The line put down in a few points, as fractions of the picture."""
    while True:
        few = cv2.approxPolyDP(line.reshape(-1, 1, 2).astype(np.float32), fine, False)
        if len(few) <= most:
            break
        fine *= 1.4
    return [(float(x / size[0]), float(y / size[1])) for x, y in few.reshape(-1, 2)]


def run(lines: Sequence[Drawn], size: tuple[int, int]) -> float:
    """How much line a drawing is, in the picture's longer sides."""
    total = 0.0
    for points, _ in lines:
        at = np.array(points, np.float32) * size
        total += float(np.hypot(*np.diff(at, axis=0).T).sum())
    return total / max(size)
