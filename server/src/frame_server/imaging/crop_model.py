"""A museum photograph cut down to the work by a small model on the phone,
with no Claude at all (Mateusz 2026-11-20: „Celem jest całkowite uniknięcie
Opus”, „Gdy model brak pewności — po prostu zostawmy do ręcznego
kadrowania”, „Musi szukać prostokątów prawie na wprost”).

The model (``ios/Frame/Resources/Kadr.mlpackage``, trained on the Mac from
Opus's and his own cuts, ``framecam-share/kadr-muzea2``) gives two masks of
the photograph letterboxed to :data:`SIDE` (the work, the frame or
passe-partout round it) and how sure it is the photograph wants a cut at
all. What is made of them here is the truth the phone's core
(``core/scan/src/scan_crop.cpp``) is held to (``tests/test_scan_core.py``):

- :func:`mask_quad`: the work's mask as four straight sides and corners;
- :func:`..cut.snap` sets them on the photograph's own edges (the core's
  ``frame_crop_snap``);
- :func:`decide`: cut only when sure and when the work stands almost
  upright and square in the photograph; unsure stays whole, for him;
- :func:`find`: all of it, from the photograph and the model's answer.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from .cut import Quad, area, snap, valid

#: The model's name: a work looked at by another is looked at again.
MODEL = "kadr-4"
#: The model's input: the photograph letterboxed into a square this long.
SIDE = 384
#: The photograph the phone looks at (``/full?side=``).
PHOTO_SIDE = 1024
#: A pixel is the work's when the model is at least this sure.
MASK = 0.5
#: How sure of a cut the model must be to cut, and below which the
#: photograph is whole for sure; between the two it is left to him.
SURE = 0.9
WHOLE = 0.1
#: A cut's corners and sides at most this far from upright and square
#: (degrees): a work photographed almost straight on.
UPRIGHT = 3.0
#: How far a work's corner may stand outside what was found around it (of
#: the photograph's sides) for that to be its frame: around a work it is
#: around all of it (Mateusz 2026-11-20, Chełmoński mnw: "dzieło wystaje
#: za ramę": the dark board behind a sheet, the sheet past its edge).
HOLD = 0.004
#: What is found round a work is its frame only when it has a colour of its
#: own or stands apart from what is round it: the band's mean colour at
#: least this far from grey (CIELAB chroma) or this far (ΔE) from
#: a strip :data:`FRAME_EDGE` pixels wide just outside it. Of his 131 frames
#: looked at (Mateusz 2026-11-20, „Model bardzo często dodaje ramę której
#: nie ma”): 38 of the 60 he kept pass, 13 of the 71 he took away; those were
#: pale, thin strips going on outwards (paper, the museum's backdrop). Its
#: being of one colour told nothing (gilded frames are less so).
FRAME_CHROMA = 16.0
FRAME_APART = 15.7
FRAME_EDGE = 5
#: The kinds of work the model is told of (the museum's own words, ``kinds``).
KINDS = ("painting", "drawing", "print", "photo", "other")

_PRINT = (
    r"print|etching|engraving|woodcut|wood engraving|lithograph|mezzotint|aquatint|drypoint|"
    r"screenprint|serigraph|linocut|grafika|akwaforta|miedzioryt|drzeworyt|litografia|staloryt|"
    r"akwatinta|sucha igła|linoryt|sitodruk|estampe|xylograph|burin|eau-forte|graphique|grafico|"
    r"αφίσα|gravure|radierung|kupferstich|holzschnitt|lithographie|ets|prent|poster|plakat|affiche|"
    r"druk|book|ksi[ąę]żk|illustrat"
)
_PHOTO = (
    r"photograph|fotografi|albumen|gelatin silver|daguerreotyp|cyanotyp|salted paper|"
    r"platinum print|foto"
)
_DRAWING = (
    r"drawing|watercolou?r|gouache|pastel|chalk|charcoal|graphite|pencil|pen and|ink|sepia|bistre|"
    r"wash|rysun|akwarel|gwasz|kred|węgiel|ołówek|tusz|piórk|lawowan|tempera on paper|zeichnung|"
    r"aquarell|dessin|tekening|on paper|papier|paper"
)
_PAINTING = (
    r"painting|miniature|vellum|icon|λάδι|oil|canvas|panel|tempera|acrylic|fresco|malarstwo|obraz|"
    r"olej|płótn|desk|deska|tektura|gemälde|peinture|schilderij|olieverf|copper|miedź"
)


def kind_of(classification: str | None, medium: str | None) -> int:
    """The work's kind (an index of :data:`KINDS`) from the museum's words,
    as the model was trained (``kinds.py`` on the Mac)."""
    text = f"{classification or ''} | {medium or ''}".lower()
    for index, words in ((2, _PRINT), (3, _PHOTO), (1, _DRAWING), (0, _PAINTING)):
        if re.search(words, text):
            return index
    return 4


def _order(q: np.ndarray) -> np.ndarray:
    c = q.mean(0)
    ang = np.arctan2(q[:, 1] - c[1], q[:, 0] - c[0])
    q = q[np.argsort(ang, kind="stable")]
    k = int(np.argmin(q.sum(1)))
    return np.roll(q, -k, axis=0)


def _fit(points: np.ndarray, how: int) -> np.ndarray:
    return cv2.fitLine(points.astype(np.float32), how, 0, 0.01, 0.01).ravel()


def mask_quad(prob: np.ndarray, threshold: float = MASK) -> tuple[list[list[float]] | None, float]:
    """The mask's largest part as four straight sides (each a line fitted
    to its outline, the worst fifth of it left out twice) and the corners
    where they meet, as fractions of the photograph; and the share of the
    photograph that part covers. None when the mask is empty."""
    rows, cols = prob.shape
    m = (prob > threshold).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=4)
    if n <= 1:
        return None, 0.0
    k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    comp = (lab == k).astype(np.uint8)
    cs, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cnt = max(cs, key=cv2.contourArea)
    cover = cv2.contourArea(cnt) / (cols * rows)
    hull = cv2.convexHull(cnt)
    peri = cv2.arcLength(hull, True)
    q0 = None
    for e in np.linspace(0.01, 0.12, 23):
        ap = cv2.approxPolyDP(hull, e * peri, True)
        if len(ap) == 4:
            q0 = ap.reshape(4, 2).astype(float)
            break
        if len(ap) < 4:
            break
    if q0 is None:
        q0 = cv2.boxPoints(cv2.minAreaRect(cnt)).astype(float)
    q0 = _order(q0)
    pts = cnt.reshape(-1, 2).astype(float)
    diag = math.hypot(cols, rows)
    lines: list[tuple[np.ndarray, np.ndarray]] = []
    for i in range(4):
        a, b = q0[i], q0[(i + 1) % 4]
        length = float(np.linalg.norm(b - a))
        d = (b - a) / max(length, 1e-9)
        nrm = np.array([-d[1], d[0]])
        t = (pts - a) @ d
        off = (pts - a) @ nrm
        sel = (t > 0.1 * length) & (t < 0.9 * length) & (np.abs(off) < 0.03 * diag)
        p = pts[sel]
        line = (a, d)
        if len(p) >= 10:
            for _ in range(2):
                vx, vy, x0, y0 = _fit(p, cv2.DIST_L2)
                r = np.abs((p[:, 0] - x0) * vy - (p[:, 1] - y0) * vx)
                keep = r <= np.quantile(r, 0.8)
                if keep.sum() >= 8:
                    p = p[keep]
            vx, vy, x0, y0 = _fit(p, cv2.DIST_HUBER)
            line = (np.array([x0, y0], dtype=float), np.array([vx, vy], dtype=float))
        lines.append(line)
    out = q0.copy()
    for i in range(4):
        (p1, d1), (p2, d2) = lines[i - 1], lines[i]
        mat = np.array([d1, -d2]).T
        if abs(np.linalg.det(mat)) < 1e-6:
            continue
        tt = np.linalg.solve(mat, p2 - p1)
        c = p1 + tt[0] * d1
        if np.linalg.norm(c - q0[i]) < 0.1 * diag:
            out[i] = c
    out = np.clip(out / [cols, rows], 0, 1)
    return out.tolist(), float(cover)


def holds(around: Sequence[Sequence[float]], work: Sequence[Sequence[float]]) -> bool:
    """Whether ``around`` (a quad, in order) holds every corner of ``work``,
    to :data:`HOLD`."""
    turn = 0.0
    for i in range(4):
        (ax, ay), (bx, by) = around[i], around[(i + 1) % 4]
        turn += ax * by - bx * ay
    sign = 1.0 if turn > 0 else -1.0
    for i in range(4):
        (ax, ay), (bx, by) = around[i], around[(i + 1) % 4]
        length = math.hypot(bx - ax, by - ay)
        if length <= 0:
            return False
        for px, py in work:
            inside = sign * ((bx - ax) * (py - ay) - (by - ay) * (px - ax)) / length
            if inside < -HOLD:
                return False
    return True


def _inside(quad: Sequence[Sequence[float]], w: int, h: int) -> np.ndarray:
    """The quad (in order) on a mask of a photograph ``w`` × ``h``: the
    pixels whose middles are inside it, 255."""
    q = np.array(quad, dtype=float) * [w, h]
    x, y = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
    turn = sum(q[i, 0] * q[(i + 1) % 4, 1] - q[(i + 1) % 4, 0] * q[i, 1] for i in range(4))
    sign = 1.0 if turn > 0 else -1.0
    keep = np.ones((h, w), bool)
    for i in range(4):
        (ax, ay), (bx, by) = q[i], q[(i + 1) % 4]
        keep &= sign * ((bx - ax) * (y - ay) - (by - ay) * (x - ax)) >= 0
    return keep.astype(np.uint8) * 255


def framed(
    rgb: np.ndarray, work: Sequence[Sequence[float]], around: Sequence[Sequence[float]]
) -> bool:
    """Whether the band between ``work`` and ``around`` (both in order, on
    ``rgb``) looks like a frame or a passe-partout (:data:`FRAME_CHROMA`,
    :data:`FRAME_APART`)."""
    h, w = rgb.shape[:2]
    lab = cv2.cvtColor(rgb.astype(np.float32) / 255.0, cv2.COLOR_RGB2Lab)
    outer = _inside(around, w, h)
    band = cv2.subtract(outer, _inside(work, w, h))
    if cv2.countNonZero(band) == 0:
        return False
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * FRAME_EDGE + 1, 2 * FRAME_EDGE + 1))
    strip = cv2.subtract(cv2.dilate(outer, kernel), outer)
    mean = np.array(cv2.mean(lab, band)[:3])
    if math.hypot(mean[1], mean[2]) >= FRAME_CHROMA:
        return True
    if cv2.countNonZero(strip) == 0:
        return False
    return float(np.linalg.norm(mean - np.array(cv2.mean(lab, strip)[:3]))) >= FRAME_APART


def upright_off(quad: Sequence[Sequence[float]], size: tuple[int, int]) -> float:
    """How far (degrees) the quad is from an upright rectangle: the worst
    of its corners' departure from a right angle and its sides' from the
    horizontal or the vertical, on a photograph of ``size`` (w, h)."""
    w, h = size
    p = _order(np.array(quad, dtype=float)) * [w, h]
    worst = 0.0
    for i in range(4):
        a, b, c = p[i - 1], p[i], p[(i + 1) % 4]
        u, v = a - b, c - b
        cos = float(u @ v) / max(float(np.linalg.norm(u) * np.linalg.norm(v)), 1e-9)
        worst = max(worst, abs(90.0 - math.degrees(math.acos(min(1.0, max(-1.0, cos))))))
    for i in range(4):
        d = p[(i + 1) % 4] - p[i]
        ang = math.degrees(math.atan2(abs(d[1]), abs(d[0])))
        worst = max(worst, min(ang, 90.0 - ang))
    return worst


def decide(sure: float, quad: Sequence[Sequence[float]] | None, size: tuple[int, int]) -> str:
    """ "cut", "whole" (no cut wanted) or "unsure" (left whole for him to
    cut by hand) of the model's ``sure`` (that a cut is wanted) and the
    work's corners as snapped."""
    if sure <= WHOLE:
        return "whole"
    if sure < SURE or quad is None:
        return "unsure"
    return "cut" if upright_off(quad, size) <= UPRIGHT else "unsure"


def letterbox(rgb: np.ndarray) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """The photograph (rows × columns × 3, 8 bits) as the model takes it:
    shrunk into a black square :data:`SIDE` long, in the middle, as floats
    0–255 (rows × columns × 3); and where it is in the square (left, top,
    width, height)."""
    h, w = rgb.shape[:2]
    s = SIDE / max(w, h)
    nw, nh = round(w * s), round(h * s)
    ox, oy = (SIDE - nw) // 2, (SIDE - nh) // 2
    x = np.zeros((SIDE, SIDE, 3), np.float32)
    x[oy : oy + nh, ox : ox + nw] = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA).astype(
        np.float32
    )
    return x, (ox, oy, nw, nh)


def probabilities(
    logits: np.ndarray, box: tuple[int, int, int, int], size: tuple[int, int]
) -> np.ndarray:
    """The model's masks (its ``masks``: 2 × :data:`SIDE` × :data:`SIDE`,
    before the sigmoid) as how sure it is of each pixel of the photograph
    of ``size`` (w, h): 2 × rows × columns."""
    ox, oy, nw, nh = box
    w, h = size
    p = 1 / (1 + np.exp(-logits[:, oy : oy + nh, ox : ox + nw].astype(np.float32)))
    return np.stack([cv2.resize(c, (w, h), interpolation=cv2.INTER_LINEAR) for c in p])


@dataclass(frozen=True)
class Found:
    """What the model made of a photograph: "cut", "whole" or "unsure"
    (:func:`decide`), the work's corners set on the photograph's edges and
    the frame's or passe-partout's outer edge (None where there is none),
    and how sure it was a cut is wanted."""

    verdict: str
    work: Quad | None
    surround: Quad | None
    sure: float


def find(rgb: np.ndarray, logits: np.ndarray, sure: float) -> Found:
    """The phone's look at a museum photograph (``rgb``: the one it
    letterboxed), from the model's ``masks`` and ``cut``."""
    h, w = rgb.shape[:2]
    _, box = letterbox(rgb)
    probs = probabilities(logits, box, (w, h))
    quad, _ = mask_quad(probs[0])
    work = valid(quad) if quad is not None else None
    if work is not None:
        work = snap(Image.fromarray(rgb), work)
    around, _ = mask_quad(probs[1])
    surround = valid(around) if around is not None else None
    if surround is not None and (
        work is None
        or area(surround) <= area(work)
        or not holds(surround, work)
        or not framed(rgb, work, surround)
    ):
        surround = None
    return Found(decide(sure, work, (w, h)), work, surround, sure)
