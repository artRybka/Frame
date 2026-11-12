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
