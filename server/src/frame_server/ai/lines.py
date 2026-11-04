"""The picture's own lines, found in code: long level and upright boundaries
(sky over sea, a wall's edge, a table top) and long straight slants.

A model points at a horizon by eye, a few per cent off; the picture knows
where it lies. So the grid under a composition (``ai.grid``) is chosen by
what lies on these lines and on the places the analysis named, and the
step about movement (``ai.motion``) is told how much of the picture runs
level, upright or slanting. No model is asked.

Two detectors, both on a blurred OKLab copy :data:`SIDE` pixels long:

1. Steps: for every row (and column) the colour just above is compared
   with just below. A boundary counts where the step is large, keeps one
   direction all along (the sky lighter than the sea) and runs unbroken
   for a good part of the width.
2. Straight edges: Canny and a probabilistic Hough transform on the
   lightness, long segments only, at any angle; the level and upright ones
   become lines too.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np
import numpy.typing as npt
from PIL import Image

from ..imaging.color import linear_to_oklab, u8_to_linear

#: The copy the lines are looked for in, this many pixels long.
SIDE = 600
#: Boundaries hugging the edge are the scan's border or a frame.
MARGIN = 0.04
#: A boundary runs at least this share of the width (or height)…
MIN_RUN = 0.25
#: …with gaps no wider than this inside it.
GAP = 0.03
#: How much of a boundary keeps one direction (lighter above all along).
COHERENT = 0.6
#: One line per band this wide.
APART = 0.04
#: The strongest lines kept per axis.
TOP = 3
#: Straight segments at least this long (share of the shorter side).
MIN_SEGMENT = 0.3
#: Slants handed on at most.
MAX_SLANTS = 6
#: An edge's direction within this of level or upright counts as such
#: (:func:`directions`).
STRAIGHT_DEGREES = 12.0

FloatArray = npt.NDArray[np.float32]


@dataclass
class Edge:
    """A level line (``axis`` "y": it lies at height ``pos``) or an upright
    one ("x": at width ``pos``), running from ``start`` to ``end`` along
    the other side; all in fractions of the picture."""

    axis: str
    pos: float
    start: float
    end: float
    strength: float
    #: "granica" (a step in lightness or colour), "prosta krawędź" (a
    #: straight edge) or both.
    kind: str
    #: The step: lightness (below minus above, right minus left) and colour.
    lightness: float = 0.0
    colour: float = 0.0
    #: Its name for the models: L1, L2…, strongest first.
    name: str = ""

    def side(self) -> str:
        """What changes across it, in words for the models."""
        if self.kind == "prosta krawędź":
            return "prosta krawędź"
        before, after = ("nad", "pod") if self.axis == "y" else ("po lewej", "po prawej")
        parts = []
        if abs(self.lightness) >= 0.03:
            parts.append(f"jaśniej {before if self.lightness < 0 else after}")
        if self.colour >= 0.03:
            parts.append("zmiana koloru")
        return ", ".join(parts) or "łagodna granica"

    def run(self) -> float:
        return self.end - self.start


@dataclass
class Slant:
    """A long straight segment that is neither level nor upright."""

    x1: float
    y1: float
    x2: float
    y2: float
    angle: float


@dataclass
class Found:
    edges: list[Edge]
    slants: list[Slant]


def _lab(pic: Image.Image) -> tuple[FloatArray, FloatArray]:
    """The picture :data:`SIDE` long in OKLab: blurred for the boundaries,
    barely for the straight edges."""
    img = pic.convert("RGB").copy()
    img.thumbnail((SIDE, SIDE), Image.Resampling.LANCZOS)
    lab = linear_to_oklab(u8_to_linear(np.asarray(img))).astype(np.float32)
    sigma = 0.008 * max(lab.shape[:2])
    blurred = np.asarray(cv2.GaussianBlur(lab, (0, 0), sigma), dtype=np.float32)
    return blurred, np.asarray(cv2.GaussianBlur(lab, (0, 0), 1.2), dtype=np.float32)


def _longest(mask: npt.NDArray[np.bool_], gap: int) -> tuple[int, int]:
    """The longest run of True with gaps up to ``gap``: its first and last."""
    best, start, last = (0, 0), -1, -(10**9)
    for i in map(int, np.flatnonzero(mask)):
        if start < 0 or i - last > gap + 1:
            start = i
        last = i
        if last - start > best[1] - best[0]:
            best = (start, last)
    return best


def _apart(found: list[Edge]) -> list[Edge]:
    """The strongest of each band :data:`APART` wide."""
    kept: list[Edge] = []
    for e in sorted(found, key=lambda e: -e.strength):
        if all(abs(e.pos - k.pos) > APART for k in kept):
            kept.append(e)
    return kept


def _steps(lab: FloatArray, axis: str) -> list[Edge]:
    """Boundaries across rows (``axis`` "y": level lines) or columns ("x")."""
    a = lab if axis == "y" else lab.transpose(1, 0, 2)
    n, m = a.shape[:2]
    d = max(2, int(0.02 * n))
    weight = np.array([1.0, 1.4, 1.4], dtype=np.float32)  # colour a bit louder than in OKLab
    step = (a[2 * d :] - a[: -2 * d]) * weight  # row i lies at i + d
    size = np.linalg.norm(step, axis=2)
    if size.size == 0:
        return []
    threshold = max(0.045, float(np.percentile(size, 85)))
    found = []
    for i in range(size.shape[0]):
        pos = (i + d) / n
        if not MARGIN <= pos <= 1 - MARGIN:
            continue
        s, e = _longest(size[i] > threshold, int(GAP * m))
        if (e - s) / m < MIN_RUN:
            continue
        seg = step[i, s : e + 1]
        coherence = np.linalg.norm(seg.mean(0)) / (np.linalg.norm(seg, axis=1).mean() + 1e-9)
        if coherence < COHERENT:
            continue
        mean = seg.mean(0) / weight
        found.append(
            Edge(
                axis=axis,
                pos=pos,
                start=s / m,
                end=e / m,
                strength=float(size[i, s : e + 1].mean()) * (e - s) / m,
                kind="granica",
                lightness=float(mean[0]),
                colour=float(math.hypot(mean[1], mean[2])),
            )
        )
    return _apart(found)


def _segments(lab: FloatArray) -> tuple[list[Edge], list[Slant]]:
    """Long straight segments: the level and upright ones as edges, the
    rest as slants, near twins left out."""
    lightness = np.clip(lab[..., 0] * 255, 0, 255).astype(np.uint8)
    h, w = lightness.shape
    found = cv2.HoughLinesP(
        cv2.Canny(lightness, 40, 110),
        1,
        np.pi / 360,
        threshold=int(0.15 * min(h, w)),
        minLineLength=MIN_SEGMENT * min(h, w),
        maxLineGap=0.02 * max(h, w),
    )
    if found is None:
        return [], []
    raw = []
    for x1, y1, x2, y2 in found.reshape(-1, 4).astype(float):
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180
        raw.append((math.hypot(x2 - x1, y2 - y1) / min(h, w), angle, x1, y1, x2, y2))
    raw.sort(key=lambda r: -r[0])
    edges: list[Edge] = []
    slants: list[Slant] = []
    for length, angle, x1, y1, x2, y2 in raw:
        if angle < 6 or angle > 174:
            edge = Edge("y", (y1 + y2) / 2 / h, min(x1, x2) / w, max(x1, x2) / w, 0.08 * length, "")
        elif 84 < angle < 96:
            edge = Edge("x", (x1 + x2) / 2 / w, min(y1, y2) / h, max(y1, y2) / h, 0.08 * length, "")
        else:
            slant = Slant(x1 / w, y1 / h, x2 / w, y2 / h, round(angle, 1))
            twin = any(
                abs(slant.angle - s.angle) < 4
                and abs((slant.x1 + slant.x2) - (s.x1 + s.x2)) / 2 < 0.03
                and abs((slant.y1 + slant.y2) - (s.y1 + s.y2)) / 2 < 0.03
                for s in slants
            )
            if not twin:
                slants.append(slant)
            continue
        edge.kind = "prosta krawędź"
        if not any(e.axis == edge.axis and abs(e.pos - edge.pos) < 0.015 for e in edges):
            edges.append(edge)
    return edges, slants


def find(pic: Image.Image) -> Found:
    """The picture's strongest level and upright lines (:data:`TOP` per
    axis, named L1… strongest first) and its long slants."""
    blurred, sharp = _lab(pic)
    bounds = _steps(blurred, "y") + _steps(blurred, "x")
    straight, slants = _segments(sharp)
    edges: list[Edge] = []
    for axis in ("x", "y"):
        candidates = [b for b in bounds if b.axis == axis]
        for s in straight:
            if s.axis != axis or not MARGIN <= s.pos <= 1 - MARGIN:
                continue
            twin = next((b for b in candidates if abs(b.pos - s.pos) < 0.02), None)
            if twin is not None:
                twin.kind = "granica i prosta krawędź"
                twin.strength *= 1.5
            else:
                candidates.append(s)
        edges += _apart(candidates)[:TOP]
    edges.sort(key=lambda e: -e.strength)
    for n, edge in enumerate(edges, start=1):
        edge.name = f"L{n}"
    return Found(edges=edges, slants=slants[:MAX_SLANTS])


def directions(pic: Image.Image) -> tuple[float, float, float]:
    """How much of the picture's edge strength runs level, upright and
    slanting or curved (shares adding up to 1; about 0.13, 0.13 and 0.74
    for edges at random)."""
    blurred, _ = _lab(pic)
    lightness = blurred[..., 0]
    gx = cv2.Sobel(lightness, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(lightness, cv2.CV_32F, 0, 1, ksize=3)
    size = np.hypot(gx, gy)
    edge = ((np.degrees(np.arctan2(gy, gx)) + 180) % 180 + 90) % 180  # along the edge
    strong = size > np.percentile(size, 80)
    weight, along = size[strong], edge[strong]
    total = float(weight.sum())
    if total <= 0:
        return 0.0, 0.0, 1.0
    level = np.minimum(along, 180 - along) <= STRAIGHT_DEGREES
    upright = np.abs(along - 90) <= STRAIGHT_DEGREES
    flat, tall = float(weight[level].sum()) / total, float(weight[upright].sum()) / total
    return flat, tall, max(0.0, 1 - flat - tall)
