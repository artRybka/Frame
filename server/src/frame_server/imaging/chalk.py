"""The analysis's marks drawn here, in chalk, over a study (``ai.drawn``):
no image model draws them any more, and they cost nothing (Mateusz
2026-11-22 22:10, after five rounds of trial sheets: "Jest super.
Działamy.").

Each titled mark is one layer (how much chalk lies at each pixel, 0…1, the
field large), as the app takes it: it gives the layer its pencil's colour
and sets the mark's number on it. What a mark looks like, as he chose it:

- the chalk: thicker than the study's pen, a grainy edge where the wax
  catches the paper's tooth, pressing harder where a stroke starts, a
  hand's tremor, now and then a stroke gone over twice, nothing ruled;
- LOOP: a free oval round the thing, once round and a bit, the ends
  overlapping and parting (19:12: "obrysy obiektów swobodnym owalem (jak
  szybkie zakreślenie) a nie dokładny obrys kształtu");
- ECHO: a round ring at each place, never an ellipse, as wide as the thing
  is narrow (21:17), the rings joined by a thinner line: two a line, three
  a triangle, four a quadrangle… (22:00);
- RHYTHM: a stroke along each repeated element, drawn on a little past
  it, a check mark at its end; a short rhythm is check marks alone (21:17);
- MOTION: always one smooth arc, thin at its start and fuller near its
  head, an empty triangle for its head, two thinner arcs beside it on its
  outer side, clear of the head, the farther one shorter (21:17, 22:00);
- a LINE that leads somewhere, an ARROW: an open head of two quick strokes,
  one of four ways of drawing it at random (19:26: "Stosujemy losowo
  wszystkie 4 groty"), large enough to be read on a phone;
- TRIANGLE, BOX: long strokes, a little bent, running past the corners.

Every choice of the hand comes from ``seed``: the same take draws the same
sheet.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt

Array = npt.NDArray[Any]

#: Half the width of a chalk stroke, of the sheet's longer side (about 6
#: pixels of a sheet 1500 long; the study's pen is 1 or 2).
WIDTH = 0.0038
#: The hand's tremor across a stroke: a slow wander and a quick shake (of
#: the longer side); a short stroke shakes less.
WANDER = 0.004
SHAKE = 0.0009
#: A stroke is gone over a second time this often (a loop, a line…).
TWICE = 0.3
#: An arrowhead's barbs: this long (of the longer side, whatever the
#: arrow's length: about seven strokes' widths) and at this angle to the line.
HEAD = (0.045, 0.053)
HEAD_ANGLE = (24.0, 35.0)
#: The ways of drawing an arrowhead (:meth:`Hand.head`), one at random.
HEADS = "ABCD"
#: A motion's head (an empty triangle): its length and half-width; the two
#: arcs beside it: how far off, from where to where along it (of its
#: length) and how thick (of a stroke).
MOTION_HEAD = (0.028, 0.0115)
MOTION_ECHOES = ((0.020, 0.10, 0.68, 0.55), (0.036, 0.20, 0.58, 0.5))
#: A motion's arc bulges by this much of its chord at least.
MOTION_BULGE = 0.10
#: A rhythm whose strokes are shorter than this (of the longer side, their
#: median) is drawn in check marks alone; its strokes run on past their
#: element by this much, at most to this far from the sheet's edge.
SHORT = 0.08
RHYTHM_PAST = (0.035, 0.05)
MARGIN = 0.03
#: A check mark's size, of the longer side.
TICK = 0.03
#: An echo's ring: its radius between these (of the longer side), from the
#: thing it rings; the line joining the rings is this thick (of a stroke).
RING = (0.03, 0.07)
JOIN = 0.6
#: A loop is at least this large round its middle (of the field's sides).
LOOP_LEAST = 0.05
#: A line whose words say it leads somewhere ends in a head (Polish stems).
LEADS = ("prowadz", "wiedzie", "kieruj", "w głąb", "spojrz", "biegn", "wskazuj", "ku ", "do ")


@dataclass(frozen=True)
class Stroke:
    """A mark as the chalk draws it: its shape, its points (fractions of
    the field) and its words (whether a line leads somewhere)."""

    shape: str
    points: Sequence[tuple[float, float]]
    text: str = ""


def _spiral(start: Array, through: Array, eye: Array) -> Array:
    """A golden spiral from ``start`` into its ``eye``, turning the way
    ``through`` lies (as ``ai.sketch.spiral``, which the app draws)."""
    growth = math.log((1 + math.sqrt(5)) / 2) / (math.pi / 2)
    dx, dy = start[0] - eye[0], start[1] - eye[1]
    radius = math.hypot(dx, dy)
    if radius < 2:
        return np.zeros((0, 2))
    cross = dx * (through[1] - eye[1]) - dy * (through[0] - eye[0])
    turn = -1.0 if cross < 0 else 1.0
    angle = math.atan2(dy, dx)
    end = math.log(radius / 1.5) / growth
    theta = np.linspace(0, end, max(int(end / (math.pi / 12)), 2) + 1)
    r = radius * np.exp(-growth * theta)
    return np.stack(
        [eye[0] + r * np.cos(angle + turn * theta), eye[1] + r * np.sin(angle + turn * theta)], 1
    )


class Hand:
    """The hand that draws one sheet's marks: its chalk, the paper's tooth
    and every choice it makes, from one seed."""

    def __init__(self, size: tuple[int, int], seed: int) -> None:
        self.w, self.h = size
        self.long = max(size)
        self.rng = np.random.default_rng(seed)
        # the paper's tooth: a fine grain, a softer mottle and the laid lines,
        # shared by every stroke of the sheet
        r = np.random.default_rng(seed + 1)
        fine = cv2.GaussianBlur(r.random((self.h, self.w), np.float32), (0, 0), 0.7)
        mid = cv2.GaussianBlur(r.random((self.h, self.w), np.float32), (0, 0), 2.2)
        laid = cv2.GaussianBlur(
            r.random((self.h, self.w), np.float32), (0, 0), sigmaX=0.6, sigmaY=2.5
        )

        def z(a: Array) -> Array:
            return (a - a.mean()) / (a.std() + 1e-6)

        g = 0.55 * z(fine) + 0.3 * z(mid) + 0.15 * z(laid)
        self.tooth = np.clip(0.5 + g / 4.5, 0, 1).astype(np.float32)
        self.width = WIDTH * self.long

    # -- courses ------------------------------------------------------------------

    def px(self, p: tuple[float, float]) -> Array:
        return np.array([p[0] * self.w, p[1] * self.h], np.float64)

    @staticmethod
    def dense(pts: Array, step: float = 2.0) -> Array:
        out = [pts[0]]
        for a, b in itertools.pairwise(pts):
            n = max(int(np.linalg.norm(b - a) / step), 1)
            out += [a + (b - a) * t for t in np.linspace(0, 1, n + 1)[1:]]
        return np.array(out)

    @staticmethod
    def smooth(pts: Array, n: int = 60) -> Array:
        """A Catmull-Rom curve through the points."""
        if len(pts) < 3:
            return pts
        p = np.vstack([2 * pts[0] - pts[1], pts, 2 * pts[-1] - pts[-2]])
        out = []
        for i in range(1, len(p) - 2):
            p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
            for t in np.linspace(0, 1, max(n // (len(pts) - 1), 6), endpoint=False):
                out.append(
                    0.5
                    * (
                        2 * p1
                        + (-p0 + p2) * t
                        + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                        + (-p0 + 3 * p1 - 3 * p2 + p3) * t**3
                    )
                )
        out.append(pts[-1])
        return np.array(out)

    def tremble(self, path: Array, amount: float = 1.0) -> Array:
        """A hand's tremor: a slow wander across the stroke and a little quick shake."""
        path = self.dense(path, 2.0)
        if len(path) < 3:
            return path
        d = np.gradient(path, axis=0)
        nrm = np.stack([-d[:, 1], d[:, 0]], 1) / (np.linalg.norm(d, axis=1, keepdims=True) + 1e-6)
        n = len(path)
        span = float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())
        amount = amount * min(1.0, 0.35 + span / (0.25 * self.long))
        noise = self.rng.standard_normal((n, 1)).astype(np.float32)
        slow = cv2.GaussianBlur(noise, (1, 0), max(n / 6, 2)).ravel()
        slow = slow / (np.abs(slow).max() + 1e-6) * WANDER * self.long
        noise = self.rng.standard_normal((n, 1)).astype(np.float32)
        fast = cv2.GaussianBlur(noise, (1, 0), 3).ravel()
        fast = fast / (np.abs(fast).max() + 1e-6) * SHAKE * self.long
        out: Array = path + nrm * ((slow + fast) * amount)[:, None]
        return out

    def bow(self, a: Array, b: Array, past: float = 0.0, bend: float = 0.02) -> Array:
        """A long quick stroke from a to b: a little bent, running on
        ``past`` (of its length) beyond both ends."""
        v = b - a
        a2 = a - v * past * self.rng.uniform(0.5, 1.2)
        b2 = b + v * past * self.rng.uniform(0.5, 1.2)
        n = np.array([-v[1], v[0]]) / (np.linalg.norm(v) + 1e-6)
        mid = (a2 + b2) / 2 + n * np.linalg.norm(v) * bend * self.rng.uniform(-1, 1)
        t = np.linspace(0, 1, 40)[:, None]
        out: Array = (1 - t) ** 2 * a2 + 2 * (1 - t) * t * mid + t**2 * b2
        return out

    # -- shapes -------------------------------------------------------------------

    def oval(self, box: tuple[float, float, float, float]) -> Array:
        """A quick encircling of the whole box (pixels), with a little room:
        never a true ellipse (its radius uneven, leaning), once round and a
        bit, the ends overlapping and parting."""
        x0, y0, x1, y1 = box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        rx, ry = (x1 - x0) / 2 * 1.12, (y1 - y0) / 2 * 1.12
        tilt = math.radians(self.rng.uniform(-12, 12))
        start = self.rng.uniform(math.pi * 0.9, math.pi * 1.4)  # a hand starts up left
        turn = 2 * math.pi * self.rng.uniform(1.08, 1.22)
        n = 120
        a = start - np.linspace(0, turn, n)  # anticlockwise, as most hands go
        p1, p2 = self.rng.uniform(0, 6.3, 2)
        wob = 1 + 0.07 * np.sin(a + p1) + 0.04 * np.sin(2 * a + p2)
        grow = 1 + np.linspace(-0.03, 0.09, n) * self.rng.uniform(0.6, 1.2)  # the ends part
        x = rx * np.cos(a) * wob * grow
        y = ry * np.sin(a) * wob * grow
        ox = cx + x * math.cos(tilt) - y * math.sin(tilt)
        oy = cy + x * math.sin(tilt) + y * math.cos(tilt)
        return np.stack([ox, oy], 1)

    def circle(self, box: tuple[float, float, float, float]) -> Array:
        """A round ring (its axes 1.0–1.08), as wide as the box is narrow:
        quick, once round and a bit, the ends overlapping."""
        x0, y0, x1, y1 = box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        r = min(x1 - x0, y1 - y0) / 2
        a0 = self.rng.uniform(math.pi * 0.9, math.pi * 1.4)
        a = a0 - np.linspace(0, 2 * math.pi * self.rng.uniform(1.08, 1.18), 70)
        sq = self.rng.uniform(1.0, 1.08)
        p = self.rng.uniform(0, 6.3)
        rr = r * (1 + 0.025 * np.sin(2 * a + p)) * np.linspace(0.98, 1.07, len(a))
        return np.stack([cx + rr * np.cos(a) * sq, cy + rr * np.sin(a)], 1)

    def head(self, path: Array, style: str) -> list[Array]:
        """An open arrowhead at the path's end: two short quick strokes of
        unequal length out of its end, never symmetrical.
        A: two barbs drawn back from the tip;
        B: one stroke, barb – tip – barb;
        C: barbs drawn into the tip and a little past it;
        D: the line runs on into one barb, the other added apart."""
        length = np.cumsum(np.r_[0, np.linalg.norm(np.diff(path, axis=0), axis=1)])
        back = int(np.searchsorted(length, length[-1] - min(0.06 * self.long, 0.3 * length[-1])))
        tip = path[-1]
        v = tip - path[min(back, len(path) - 2)]
        v = v / (np.linalg.norm(v) + 1e-6)
        n = np.array([-v[1], v[0]])
        size = self.long * self.rng.uniform(*HEAD)
        la, lb = size * self.rng.uniform(0.95, 1.1), size * self.rng.uniform(0.78, 0.9)
        aa = math.radians(self.rng.uniform(27, HEAD_ANGLE[1]))
        ab = math.radians(self.rng.uniform(HEAD_ANGLE[0], 31))
        if self.rng.random() < 0.5:
            la, lb, aa, ab = lb, la, ab, aa

        def end(length: float, ang: float, side: float) -> Array:
            out: Array = tip - v * length * math.cos(ang) + n * side * length * math.sin(ang)
            return out

        def flick(a: Array, b: Array, sag: float) -> Array:
            t = np.linspace(0, 1, 14)[:, None]
            d = b - a
            m = (a + b) / 2 + np.array([-d[1], d[0]]) * sag
            out: Array = (1 - t) ** 2 * a + 2 * (1 - t) * t * m + t**2 * b
            return out

        ea, eb = end(la, aa, 1), end(lb, ab, -1)
        if style == "A":
            return [flick(tip, ea, 0.06), flick(tip + v * 0.002 * self.long, eb, -0.05)]
        if style == "B":
            return [np.vstack([flick(ea, tip, -0.05), flick(tip, eb, 0.07)[1:]])]
        if style == "C":
            over = v * self.long * self.rng.uniform(0.004, 0.008)
            return [
                flick(ea, tip + over, 0.05),
                flick(eb, tip + over * 0.6 - v * 0.003 * self.long, -0.04),
            ]
        return [
            np.vstack([path[max(back, len(path) - 6) :], flick(tip, ea, 0.08)[1:]]),
            flick(tip - v * 0.004 * self.long, eb, -0.05),
        ]

    def blob(self, sheet: Array, p: Array) -> tuple[float, float, float, float]:
        """The thing an echo points at, round ``p`` (pixels), as a box: the
        part GrabCut finds in a window round the point that holds (or lies
        nearest) it; only its size is taken, never its outline."""
        k = 384 / self.long
        small = cv2.resize(
            sheet, (round(self.w * k), round(self.h * k)), interpolation=cv2.INTER_AREA
        )
        sh, sw = small.shape[:2]
        cx, cy = int(min(max(p[0] * k, 0), sw - 1)), int(min(max(p[1] * k, 0), sh - 1))
        lo, hi = RING[0] * self.long, RING[1] * self.long
        reach = int(0.12 * 384)
        x0, y0 = max(cx - reach, 1), max(cy - reach, 1)
        x1, y1 = min(cx + reach, sw - 2), min(cy + reach, sh - 2)
        mask = np.zeros((sh, sw), np.uint8)
        if x1 - x0 > 4 and y1 - y0 > 4:
            try:
                cv2.grabCut(
                    cv2.cvtColor(small, cv2.COLOR_RGB2BGR),
                    mask,
                    (x0, y0, x1 - x0, y1 - y0),
                    np.zeros((1, 65)),
                    np.zeros((1, 65)),
                    4,
                    cv2.GC_INIT_WITH_RECT,
                )
            except cv2.error:
                mask[:] = 0
        fg: Array = cv2.morphologyEx(
            np.isin(mask, (1, 3)).astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)
        )
        n, labels, stats, centres = cv2.connectedComponentsWithStats(fg)
        if n < 2:
            r = 0.034 * self.long
            return (p[0] - r, p[1] - r * 0.85, p[0] + r, p[1] + r * 0.85)
        idx = int(labels[cy, cx])
        if idx == 0:  # the part nearest the point
            d = np.hypot(centres[1:, 0] - cx, centres[1:, 1] - cy)
            idx = 1 + int(np.argmin(d - np.sqrt(stats[1:, cv2.CC_STAT_AREA]) * 0.5))
        bx, by, bw, bh = (int(v) for v in stats[idx, :4])
        bx0, by0, bx1, by1 = bx / k, by / k, (bx + bw) / k, (by + bh) / k
        # between the thing and the point, so that the ring never leaves the point
        mx, my = ((bx0 + bx1) / 2 + p[0]) / 2, ((by0 + by1) / 2 + p[1]) / 2
        hx = min(max(max(bx1 - mx, mx - bx0) * 1.05, lo), hi)
        hy = min(max(max(by1 - my, my - by0) * 1.05, lo * 0.8), hi)
        return (mx - hx, my - hy, mx + hx, my + hy)

    def arc(self, pts: Array) -> Array:
        """A motion's course as one smooth arc from its start to its end,
        bulging where the analysis's course bulges, never kinked."""
        a, b = pts[0], pts[-1]
        chord = b - a
        length = np.linalg.norm(chord) + 1e-6
        n = np.array([-chord[1], chord[0]]) / length
        mids = list(pts[1:-1]) if len(pts) > 2 else [(a + b) / 2]
        dev = float(np.mean([(m - a) @ n for m in mids]))
        bulge = (1.0 if dev >= 0 else -1.0) * max(abs(dev), MOTION_BULGE * length)
        c = (a + b) / 2 + n * 2 * bulge  # a quadratic's middle lies half way to its control point
        t = np.linspace(0, 1, 80)[:, None]
        out: Array = (1 - t) ** 2 * a + 2 * (1 - t) * t * c + t**2 * b
        return out

    def motion(self, layer: Array, pts: Array) -> None:
        """The motion sign: a smooth arc, thin at its start and fuller near
        its head, into an empty chalk triangle; beside it, on the arc's outer
        side and clear of the head, two thinner arcs, the farther shorter."""
        path = self.arc(pts)
        along = np.cumsum(np.r_[0, np.linalg.norm(np.diff(path, axis=0), axis=1)])
        hl, hw = MOTION_HEAD[0] * self.long, MOTION_HEAD[1] * self.long
        tip = path[-1]
        back = path[int(np.searchsorted(along, along[-1] - hl))]
        v = (tip - back) / (np.linalg.norm(tip - back) + 1e-6)
        nv = np.array([-v[1], v[0]])
        shaft = path[: int(np.searchsorted(along, along[-1] - hl * 0.7)) + 1]
        self.stroke(layer, shaft, press=1.0, taper=(0.55, 1.45), steady=0.25)
        base = tip - v * hl

        def jit() -> Array:
            out: Array = self.rng.normal(0, 0.0012 * self.long, 2)
            return out

        corners = np.array(
            [
                tip + v * 0.002 * self.long + jit(),
                base + nv * hw * self.rng.uniform(0.95, 1.1) + jit(),
                base - v * hl * 0.12 + jit(),
                base - nv * hw * self.rng.uniform(0.95, 1.1) + jit(),
            ]
        )
        # its outline in one stroke, tip – corner – corner – tip, a little past the start
        outline = np.vstack(
            [
                np.linspace(corners[0], corners[1], 8),
                np.linspace(corners[1], corners[3], 8)[1:],
                np.linspace(corners[3], corners[0], 8)[1:],
                np.linspace(corners[0], corners[1], 8)[1:3],
            ]
        )
        self.stroke(layer, outline, press=1.0, thin=0.8, steady=0.2)
        # the outer side: where the arc bulges
        outer = path[len(path) // 2] - (path[0] + path[-1]) / 2
        d = np.gradient(path, axis=0)
        nrm = np.stack([-d[:, 1], d[:, 0]], 1) / (np.linalg.norm(d, axis=1, keepdims=True) + 1e-6)
        if nrm[len(path) // 2] @ outer < 0:
            nrm = -nrm
        for (off, ta, tb, thick), press in zip(MOTION_ECHOES, (0.8, 0.7), strict=True):
            a, b = int(len(path) * ta), int(len(path) * tb)
            self.stroke(
                layer, path[a:b] + nrm[a:b] * off * self.long, press=press, thin=thick, steady=0.3
            )

    def tick(self, at: Array, size: float) -> Array:
        """A check mark in one movement: a short stroke down, a longer one up to the right."""
        s = size * self.rng.uniform(0.9, 1.1)
        p0 = at + np.array([-0.45, -0.05]) * s
        p1 = at + np.array([-0.12, 0.35]) * s + self.rng.normal(0, 0.03 * s, 2)
        p2 = at + np.array([0.55, -0.55]) * s
        t = np.linspace(0, 1, 10)[:, None]
        down = (1 - t) * p0 + t * p1
        k = p1 + (p2 - p1) * 0.5 + np.array([-(p2 - p1)[1], (p2 - p1)[0]]) * 0.08
        up = (1 - t) ** 2 * p1 + 2 * (1 - t) * t * k + t**2 * p2
        return np.vstack([down, up[1:]])

    # -- the chalk ----------------------------------------------------------------

    def stroke(
        self,
        layer: Array,
        path: Array,
        press: float = 1.0,
        thin: float = 1.0,
        taper: tuple[float, float] | None = None,
        steady: float = 1.0,
    ) -> None:
        """Lays one stroke into ``layer`` (0…1, the most of the two where
        strokes meet): heavier where it starts, lighter where it leaves (with
        ``taper``: thin at its start, fuller and pressed harder as it goes);
        its width breathes a little and its edge is broken by the paper's
        tooth. ``steady``: how much of the hand's tremor."""
        path = self.tremble(path, steady) if len(path) > 1 else path
        n = len(path)
        if n < 2:
            return
        t = np.linspace(0, 1, n)
        noise = self.rng.standard_normal((n, 1)).astype(np.float32)
        breathe = 1 + 0.54 * cv2.GaussianBlur(noise, (1, 0), 8).ravel()
        if taper:
            pressure = press * (0.6 + 0.4 * t) * np.clip(t / 0.04, 0.5, 1)
            half = (
                self.width
                * thin
                * np.clip(breathe, 0.85, 1.15)
                * np.linspace(taper[0], taper[1], n)
            )
        else:
            pressure = (
                press
                * (1.0 - 0.32 * t)
                * np.clip(t / 0.04, 0.35, 1)
                * np.clip((1 - t) / 0.05, 0.5, 1)
            )
            half = (
                self.width
                * thin
                * np.clip(breathe, 0.7, 1.3)
                * (0.75 + 0.25 * pressure / max(press, 1e-6))
            )
        x0, y0 = (int(v) for v in np.floor(path.min(0) - half.max() - 3))
        x1, y1 = (int(v) for v in np.ceil(path.max(0) + half.max() + 3))
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, self.w), min(y1, self.h)
        if x1 <= x0 or y1 <= y0:
            return
        scale = 2  # drawn at twice the size, then reduced: soft edges, not blurred ones
        cover: Array = np.zeros(((y1 - y0) * scale, (x1 - x0) * scale), np.float32)
        at = ((path - (x0, y0)) * scale * 16).astype(np.int64)
        for i in range(n - 1):
            thick = max(round(2 * float(half[i]) * scale), 1)
            a = (int(at[i][0]), int(at[i][1]))
            b = (int(at[i + 1][0]), int(at[i + 1][1]))
            cv2.line(cover, a, b, float(pressure[i]), thick, cv2.LINE_AA, 4)
        cover = cv2.resize(cover, (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA)
        tooth = self.tooth[y0:y1, x0:x1]
        # the wax lies on the tooth's tops: the harder the press, the deeper into the grain
        grain = np.clip((tooth - (0.60 - 0.58 * cover)) / 0.22, 0, 1) * np.clip(cover / 0.3, 0, 1)
        grain = np.clip(grain * (0.7 + 0.3 * cover), 0, 1)
        layer[y0:y1, x0:x1] = np.maximum(layer[y0:y1, x0:x1], grain.astype(np.float32))

    def strokes(
        self,
        layer: Array,
        paths: Sequence[Array],
        twice: float = TWICE,
        press: float = 0.95,
        thin: float = 1.0,
    ) -> None:
        """Lays the strokes, each now and then (``twice``) gone over again,
        a touch off and lighter."""
        for p in paths:
            self.stroke(layer, p, press * self.rng.uniform(0.9, 1.05), thin)
            if self.rng.random() < twice:
                off = self.rng.normal(0, 0.0025 * self.long, 2)
                part = p[: max(int(len(p) * self.rng.uniform(0.5, 1.0)), 2)] if len(p) > 3 else p
                self.stroke(layer, part + off, press * 0.6, 0.85)

    # -- the marks ----------------------------------------------------------------

    def echo(self, layer: Array, sheet: Array, pts: Array) -> None:
        """A round ring at each place, the rings joined by a thinner line, edge
        to edge, never through a ring: two a line, three a triangle, four a
        quadrangle…, its corners in turn round their middle (no side crosses
        another)."""
        rings = []
        for p in pts:
            box = self.blob(sheet, p)
            rings.append(
                (
                    np.array([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]),
                    min(box[2] - box[0], box[3] - box[1]) / 2,
                )
            )
            self.strokes(layer, [self.circle(box)], twice=0.1, press=0.9, thin=0.9)
        if len(rings) < 2:
            return
        middle = np.mean([c for c, _ in rings], axis=0)
        order = sorted(range(len(rings)), key=lambda i: math.atan2(*(rings[i][0] - middle)[::-1]))
        sides = list(zip(order, order[1:] + order[:1], strict=True)) if len(rings) > 2 else [(0, 1)]
        for i, j in sides:
            (ca, ra), (cb, rb) = rings[i], rings[j]
            u = (cb - ca) / (np.linalg.norm(cb - ca) + 1e-6)
            a, b = ca + u * ra * 1.15, cb - u * rb * 1.15
            if np.linalg.norm(b - a) > 0.02 * self.long:
                self.stroke(layer, self.bow(a, b, bend=0.02), press=0.8, thin=JOIN, steady=0.5)

    def rhythm(self, layer: Array, pts: Array) -> None:
        """A stroke along each element (a pair of points), drawn on a little
        past it, a check mark at its end: on the right of one across, a little
        above it; over one upright, or on its right where there is no room. A
        short rhythm (:data:`SHORT`) is a check mark on each element alone."""
        pairs = [(pts[i], pts[i + 1]) for i in range(0, len(pts) - 1, 2)]
        if not pairs:
            return
        size = TICK * self.long
        if np.median([np.linalg.norm(b - a) for a, b in pairs]) < SHORT * self.long:
            for a, b in pairs:
                self.strokes(layer, [self.tick((a + b) / 2, size)], twice=0.0)
            return
        edge = MARGIN * self.long
        for a, b in pairs:
            if abs(b[0] - a[0]) >= abs(b[1] - a[1]):
                a, b = (a, b) if a[0] <= b[0] else (b, a)
            else:
                a, b = (a, b) if a[1] >= b[1] else (b, a)
            ang = math.radians(self.rng.uniform(-1.2, 1.2))
            d = b - a
            d = np.array(
                [
                    d[0] * math.cos(ang) - d[1] * math.sin(ang),
                    d[0] * math.sin(ang) + d[1] * math.cos(ang),
                ]
            )
            u = d / (np.linalg.norm(d) + 1e-6)
            room = min(
                (self.w - edge - b[0]) / u[0] if u[0] > 1e-6 else 1e9,
                (b[0] - edge) / -u[0] if u[0] < -1e-6 else 1e9,
                (self.h - edge - b[1]) / u[1] if u[1] > 1e-6 else 1e9,
                (b[1] - edge) / -u[1] if u[1] < -1e-6 else 1e9,
            )
            past = max(min(self.rng.uniform(*RHYTHM_PAST) * self.long, room), 0)
            a2, b2 = a - u * 0.012 * self.long, b + u * past
            self.strokes(
                layer, [self.bow(a2, b2, bend=0.012)], twice=0.2, press=self.rng.uniform(0.82, 1.0)
            )
            if abs(u[0]) >= abs(u[1]):
                spot = b2 + np.array([0.012, -0.012]) * self.long
            else:
                spot = b2 + np.array([0.004, -0.016]) * self.long
                if spot[1] < edge:
                    spot = b2 + np.array([0.02, 0.01]) * self.long
            spot = np.clip(spot, edge, (self.w - edge, self.h - edge))
            self.strokes(layer, [self.tick(spot, size * 0.85)], twice=0.0)

    def mark(self, layer: Array, sheet: Array, mark: Stroke) -> None:
        pts = np.array([self.px(p) for p in mark.points], np.float64)
        shape = mark.shape
        lead = any(word in (mark.text or "").lower() for word in LEADS)
        style = str(self.rng.choice(list(HEADS)))
        if shape == "loop":
            (cx, cy) = mark.points[0]
            (kx, ky) = mark.points[1] if len(mark.points) > 1 else mark.points[0]
            rx, ry = max(abs(kx - cx), LOOP_LEAST) * self.w, max(abs(ky - cy), LOOP_LEAST) * self.h
            c = self.px((cx, cy))
            self.strokes(
                layer, [self.oval((c[0] - rx, c[1] - ry, c[0] + rx, c[1] + ry))], twice=0.35
            )
        elif shape in ("triangle", "rect"):
            if shape == "rect":
                (ax, ay), (bx, by) = pts[0], pts[-1]
                pts = np.array([(ax, ay), (bx, ay), (bx, by), (ax, by)])
            sides = [
                self.bow(pts[i], pts[(i + 1) % len(pts)], past=0.07, bend=0.03)
                for i in range(len(pts))
            ]
            self.strokes(layer, sides, twice=0.25)
        elif shape in ("line", "underline"):
            if len(pts) > 2:
                path = self.smooth(pts)
            else:
                path = self.bow(
                    pts[0], pts[-1], past=0.04 if shape == "underline" else 0.0, bend=0.035
                )
            self.strokes(layer, [path], twice=0.3)
            if lead and shape == "line":
                self.strokes(layer, self.head(path, style), twice=0.0, press=0.95, thin=0.95)
        elif shape == "motion":
            self.motion(layer, pts)
        elif shape == "arrow":
            path = self.bow(pts[0], pts[-1], bend=0.035)
            self.strokes(layer, [path], twice=0.2)
            self.strokes(layer, self.head(path, style), twice=0.0, press=0.95, thin=0.95)
        elif shape == "echo":
            self.echo(layer, sheet, pts)
        elif shape == "rhythm":
            self.rhythm(layer, pts)
        elif shape == "rays":
            vp = pts[0]
            paths = [
                self.bow(p, p + (vp - p) * self.rng.uniform(0.6, 0.8), bend=0.02) for p in pts[1:]
            ]
            self.strokes(layer, paths, twice=0.2)
        elif shape == "spiral" and len(pts) >= 3:
            course = _spiral(pts[0], pts[1], pts[-1])
            self.strokes(layer, [course] if len(course) > 2 else [], twice=0.1)
        elif len(pts) > 1:
            self.strokes(layer, [self.smooth(pts)], twice=0.3)


def draw(sheet: Array, marks: Sequence[Stroke], seed: int) -> list[Array]:
    """The marks in chalk over ``sheet`` (RGB, 0…255 or 0…1, the field):
    one layer for each (how much chalk lies at each pixel, 0…1)."""
    rgb = np.asarray(sheet)
    if rgb.dtype != np.uint8:
        rgb = (np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8)
    h, w = rgb.shape[:2]
    hand = Hand((w, h), seed)
    layers = []
    for mark in marks:
        layer = np.zeros((h, w), np.float32)
        hand.mark(layer, rgb, mark)
        layers.append(layer)
    return layers


__all__ = ["HEADS", "SHORT", "Stroke", "draw"]
