"""A museum photograph cut down to the work by a small model on the phone,
with no Claude at all (Mateusz 2026-11-20: „Celem jest całkowite uniknięcie
Opus”, „Gdy model brak pewności — po prostu zostawmy do ręcznego
kadrowania”, „Musi szukać prostokątów prawie na wprost”).

The model (``ios/Models/Kadr.mlpackage``; paintings' own
``KadrPainting.mlpackage``, trained on the Mac from Opus's and his own
cuts, ``framecam-share/kadr-muzea2``) gives two masks of
the photograph letterboxed to :data:`SIDE` (the work, the frame or
passe-partout round it) and how sure it is the photograph wants a cut at
all. What is made of them here is the truth the phone's core
(``core/scan/src/scan_crop.cpp``) is held to (``tests/test_scan_core.py``):

- :func:`mask_quad`: the work's mask as four straight sides and corners;
- :func:`..cut.snap` sets them on the photograph's own edges (the core's
  ``frame_crop_snap``);
- :func:`decide`: cut only when sure and when the work stands almost
  upright and square in the photograph; unsure stays whole, for him;
- :func:`plate`: a print's impression found on the sheet the model cut
  to, and the sheet cut down round it when its paper is wide;
- :func:`find`: all of it, from the photograph and the model's answer.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .cut import Quad, area, snap, valid

#: The model's name: a work looked at by another is looked at again.
#: Drawings, prints and the rest (``model_of``): their own (Mateusz
#: 2026-11-24 14:07 UTC, „Tak, wymień”), fine-tuned on his sheets as
#: kadr-10p on his paintings: 141 of 193 held out as he said against
#: kadr-4's 133, fewer left to him (62 against 69) and fewer cut when he
#: wanted them whole (7 against 11), at its own :data:`SURE`.
MODEL = "kadr-11s"
#: Paintings' own model (Mateusz 2026-11-21 21:31 UTC, „Tak, wymień dla
#: malarstwa”): fine-tuned on his 2137 paintings told at a glance ("Ucz
#: kadrowania"), with Opus's corners where he said a cut; 302 of 375 held
#: out as he said against kadr-4's 294, at its own :data:`PAINTING_SURE`.
PAINTING_MODEL = "kadr-10p"
#: The same models for the server's night (``crop_night.py``): the app's
#: weights exported to ONNX (``framecam-share/kadr-muzea2/onnx/export.py``),
#: each named after its model, in this folder.
WEIGHTS = Path(__file__).parent / "models"
#: The model's input: the photograph letterboxed into a square this long.
SIDE = 384
#: The photograph the phone looks at (``/full?side=``).
PHOTO_SIDE = 1024
#: A pixel is the work's when the model is at least this sure.
MASK = 0.5
#: How sure of a cut the model must be to cut, and below which the
#: photograph is whole for sure; between the two it is left to him.
SURE = 0.795
WHOLE = 0.1
#: :data:`PAINTING_MODEL`'s: as many cuts in the old test as kadr-4's at
#: 0.9 (it is less sure of itself, and tells them apart better).
PAINTING_SURE = 0.81
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

# A print is cut to its sheet, unless the paper round the impression is
# wide (Mateusz 2026-11-24 09:36 UTC: „kadrujmy do kartki, chyba że margines
# od odbitki jest wtedy bardzo duży. W takiej sytuacji trzeba ograniczyć
# margines do rozsądnej proporcji, równo od każdej strony od odbitki”;
# 10:37 the margin, 10:38 „ale próg nie 25% tylko 15%”). The impression is
# found with no model (``framecam-share/kadr-muzea2/margines1``): what
# stands apart from the paper in colour or grain, on the sheet set
# upright, and only where there is plain paper all round it.

#: What decides which prints are cut and how: raised when :func:`plate`
#: changes, the prints cut before are cut again once (``phone_crops``).
#: 2: a print the model left whole or unsure is cut where its paper bears
#: it out (:func:`sheet_cut`; Mateusz 2026-11-25: „Dlaczego takie dzieło
#: się nie kadruje?”), and the margin is round the impression with its
#: lettering („prawie wcina się w napis”); those looked at before are
#: looked at again (``phone_crops.wants``).
#: 3: a cut that leaves the drawing's fine lines out is none
#: (:data:`PLATE_DRAWN`; Mateusz 2026-11-27, a lithograph cut to one figure).
PLATE = 3
#: The photograph's own edges: the sheet of a print photographed with
#: nothing round it.
EDGES: Quad = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
#: The sheet is cut down when its widest margin is more than this share of
#: the impression's shorter side…
PLATE_OVER = 0.15
#: …to the impression and this much of its shorter side round it, the same
#: on every side (as much as the narrowest side has: never past the sheet).
PLATE_MARGIN = 0.08
#: The sheet set upright this long (px) to be looked at.
PLATE_SIDE = 900
#: The paper's colour is read in a band from this far in from the sheet's
#: edge to :data:`PLATE_BAND` (of its shorter side).
PLATE_EDGE = 0.015
PLATE_BAND = 0.05
#: What stands at least this far from the paper's colour (ΔE) or this far
#: from its grain (the local spread of lightness, 5 px) is the work; or
#: further, :data:`PLATE_SPREAD` median deviations above the band's.
PLATE_APART = 7.0
PLATE_GRAIN = 2.5
PLATE_SPREAD = 5 * 1.4826
#: The work's pixels grown by this share of the sheet's long side into one.
PLATE_GROW = 0.012
#: An impression turned by more than :data:`PLATE_TURN_LEAST` and at most
#: :data:`PLATE_TURN` degrees is boxed turned, when that box is smaller than
#: :data:`PLATE_TURN_GAIN` of the upright one; its edge pixels left out (share).
PLATE_TURN = 5.0
PLATE_TURN_LEAST = 0.3
PLATE_TURN_GAIN = 0.98
PLATE_STRAY = 0.001
#: A caption or signature at a side cut away: beyond a line emptier than
#: :data:`PLATE_GAP` of the impression's mean filling within :data:`PLATE_NEAR`
#: of its length, with what is beyond it sparser than :data:`PLATE_SPARSE`;
#: or, of a dense impression (:data:`PLATE_DENSE`), a band at its edge
#: sparser than :data:`PLATE_THIN` within :data:`PLATE_REACH`.
PLATE_GAP = 0.15
PLATE_NEAR = 0.10
PLATE_SPARSE = 0.6
PLATE_DENSE = 0.6
PLATE_THIN = 0.35
PLATE_REACH = 0.18
#: Plain paper round it: the band at most :data:`PLATE_SIDES` (ΔE) apart
#: between the sheet's sides and as light as :data:`PLATE_LIGHT` (L); its
#: grain's threshold at most :data:`PLATE_GRAIN_MOST`; of the paper beyond
#: the impression at most :data:`PLATE_BUSY` more than :data:`PLATE_LOOSE`
#: (ΔE) or :data:`PLATE_LOOSE_GRAIN` from it; the impression at least
#: :data:`PLATE_WHOLE` of all that stands apart, and at least
#: :data:`PLATE_LEAST` of the sheet.
PLATE_SIDES = 20.0
PLATE_LIGHT = 60.0
PLATE_GRAIN_MOST = 4.0
PLATE_BUSY = 0.10
PLATE_LOOSE = 10.0
PLATE_LOOSE_GRAIN = 3.0
PLATE_WHOLE = 0.8
PLATE_LEAST = 0.04
#: His own cut of a print is the impression alone when it overlaps it this
#: much (intersection over union): cut again to the impression and its
#: margin within the sheet, once (Mateusz 2026-11-24 10:39 UTC: „ręczne
#: kadry, jeżeli obejmują samą grafikę także obejmij tą zmianą”).
PLATE_SAME = 0.85
#: Less of the sheet than this is a speck, not something written on it.
PLATE_PART = 0.0002
#: The drawing's fine lines: darker than what lies round them (a black-hat
#: of :data:`PLATE_LINE` px on the upright sheet) by at least
#: :data:`PLATE_FAINT` (L), or :data:`PLATE_SPREAD` median deviations above
#: the band's. They are counted in squares of :data:`PLATE_CELL` px, those
#: with at least :data:`PLATE_CELL_LEAST` px of them (so a densely hatched
#: part weighs no more than a lightly drawn one), each where its middle is.
#: A cut that leaves more than :data:`PLATE_DRAWN` of them out beside it or
#: above it (under it is what is written under a print)
#: is no cut: an impression found as one dark part of a drawing printed
#: with no plate (Mateusz 2026-11-27, a lithograph by Toulouse-Lautrec cut
#: to one of its two figures: „Nie możemy tak robić”).
PLATE_LINE = 9
PLATE_FAINT = 3.0
PLATE_DRAWN = 0.14
PLATE_CELL = 24
#: …and only where the impression lies along less than :data:`PLATE_EDGED`
#: of its box's edges (:func:`_edged`): an etching's plate keeps its cut
#: whatever is pencilled or stained round it.
PLATE_EDGED = 0.6
PLATE_EDGE_DEPTH = 0.03
PLATE_CELL_LEAST = 12

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


def model_of(kind: int) -> str:
    """The model that looks at a work of ``kind`` (:data:`KINDS`)."""
    return PAINTING_MODEL if kind == 0 else MODEL


def sure_of(kind: int) -> float:
    """How sure of a cut :func:`model_of` ``kind`` must be to cut."""
    return PAINTING_SURE if kind == 0 else SURE


def decide(
    sure: float,
    quad: Sequence[Sequence[float]] | None,
    size: tuple[int, int],
    cut_at: float = SURE,
) -> str:
    """ "cut", "whole" (no cut wanted) or "unsure" (left whole for him to
    cut by hand) of the model's ``sure`` (that a cut is wanted, a cut at
    ``cut_at``: :func:`sure_of`) and the work's corners as snapped."""
    if sure <= WHOLE:
        return "whole"
    if sure < cut_at or quad is None:
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
class Impression:
    """A print's impression found on its sheet set upright (``size``: w, h;
    ``to_sheet`` the photograph's perspective onto it): its box (``box``:
    left, top, right, bottom) turned by ``turn`` degrees about ``middle``;
    ``inked``: the same with its lettering and signature (what
    :func:`_cut_caption` leaves out), which a cut never goes through."""

    box: tuple[float, float, float, float]
    turn: float
    middle: tuple[float, float]
    size: tuple[int, int]
    to_sheet: np.ndarray
    inked: tuple[float, float, float, float] | None = None
    #: The other things printed or written on the sheet, apart from it
    #: (a title, a name, a signature): their boxes, as ``box``.
    others: tuple[tuple[float, float, float, float], ...] = ()
    #: The drawing's fine lines (:func:`_lines`): the middles of the squares
    #: they are drawn in, as
    #: ``box`` (u, v; one row each).
    lines: np.ndarray | None = None
    #: How much of its box's edges it lies along (:func:`_edged`).
    edged: float = 1.0

    def corners(
        self,
        grow: Sequence[float] = (0.0, 0.0, 0.0, 0.0),
        box: tuple[float, float, float, float] | None = None,
    ) -> np.ndarray:
        """The box (or ``box``) grown by ``grow`` (left, top, right,
        bottom) on the upright sheet, its corners in order."""
        u0, v0, u1, v1 = box or self.box
        u0, v0, u1, v1 = u0 - grow[0], v0 - grow[1], u1 + grow[2], v1 + grow[3]
        a = np.deg2rad(self.turn)
        ca, sa = np.cos(a), np.sin(a)
        cx, cy = self.middle
        return np.array(
            [
                [cx + uu * ca - vv * sa, cy + uu * sa + vv * ca]
                for uu, vv in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))
            ]
        )

    def margins(
        self, box: tuple[float, float, float, float] | None = None
    ) -> tuple[float, float, float, float]:
        """The paper beyond it (or ``box``) on the sheet: left, top,
        right, bottom (px)."""
        q = self.corners(box=box)
        w, h = self.size
        return (
            (q[0, 0] + q[3, 0]) / 2,
            (q[0, 1] + q[1, 1]) / 2,
            w - (q[1, 0] + q[2, 0]) / 2,
            h - (q[2, 1] + q[3, 1]) / 2,
        )

    def on_photo(self, corners: np.ndarray, w: int, h: int) -> list[list[float]]:
        """``corners`` on the upright sheet as fractions of the photograph."""
        back = cv2.perspectiveTransform(
            np.array([corners], np.float32), np.linalg.inv(self.to_sheet)
        )[0]
        return [[float(x) / w, float(y) / h] for x, y in back]


def upright(rgb: np.ndarray, sheet: Sequence[Sequence[float]]) -> tuple[np.ndarray, np.ndarray]:
    """The sheet (corners in order, on ``rgb``) set upright, its long side
    :data:`PLATE_SIDE`; and the perspective onto it."""
    h, w = rgb.shape[:2]
    q = (np.array(sheet, np.float64) * [w, h]).astype(np.float32)
    width = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
    height = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
    s = PLATE_SIDE / max(width, height)
    cols, rows = max(8, round(width * s)), max(8, round(height * s))
    to = np.array([[0, 0], [cols, 0], [cols, rows], [0, rows]], np.float32)
    m = cv2.getPerspectiveTransform(q, to)
    flat = cv2.warpPerspective(
        rgb, m, (cols, rows), flags=cv2.INTER_AREA, borderMode=cv2.BORDER_REPLICATE
    )
    return flat, m


def _spread_above(values: np.ndarray) -> float:
    """The values' median and :data:`PLATE_SPREAD` median deviations."""
    mid = np.median(values)
    return float(mid + PLATE_SPREAD * np.median(np.abs(values - mid)))


def _others(
    work: np.ndarray,
    parts: np.ndarray,
    count: np.ndarray,
    k: int,
    middle: tuple[float, float],
    turn: float,
    area: int,
) -> tuple[tuple[float, float, float, float], ...]:
    """The boxes (as :class:`Impression`'s) of the sheet's other inked
    parts, all but specks (:data:`PLATE_PART` of it)."""
    ys, xs = np.nonzero(work)
    labels = parts[ys, xs]
    a = np.deg2rad(turn)
    ca, sa = np.cos(a), np.sin(a)
    u = (xs - middle[0]) * ca + (ys - middle[1]) * sa
    v = -(xs - middle[0]) * sa + (ys - middle[1]) * ca
    out = []
    for j in range(1, len(count)):
        if j == k or count[j] < PLATE_PART * area:
            continue
        mine = labels == j
        uj, vj = u[mine], v[mine]
        out.append((float(uj.min()), float(vj.min()), float(uj.max() + 1), float(vj.max() + 1)))
    return tuple(out)


def _lines(light: np.ndarray, band: np.ndarray, e: int) -> np.ndarray:
    """The drawing's fine lines on the upright sheet (``light``: its L;
    ``band``: the paper's band; ``e``: the edge left out), as a mask."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (PLATE_LINE, PLATE_LINE))
    dark = cv2.morphologyEx(light, cv2.MORPH_BLACKHAT, k)
    line = (dark > max(PLATE_FAINT, _spread_above(dark[band]))).astype(np.uint8)
    rows, cols = line.shape
    line[:e, :] = 0
    line[rows - e :, :] = 0
    line[:, :e] = 0
    line[:, cols - e :] = 0
    return cv2.morphologyEx(line, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


def _edged(u: np.ndarray, v: np.ndarray, box: Sequence[float]) -> float:
    """How much of the edges of ``box`` (left, top, right, bottom) the
    impression's pixels (``u``, ``v``) lie along, within
    :data:`PLATE_EDGE_DEPTH` of its shorter side inside them: the mean of
    its four sides' shares (px). A plate's impression, or one printed to a
    ruled edge, lies along all of them; a figure drawn with no plate
    touches them here and there."""
    u0, v0, u1, v1 = box
    d = max(3.0, PLATE_EDGE_DEPTH * min(u1 - u0, v1 - v0))
    inside = (u >= u0) & (u < u1) & (v >= v0) & (v < v1)
    u, v = u[inside], v[inside]
    nu, nv = max(1, int(u1 - u0)), max(1, int(v1 - v0))
    across = np.clip((u - u0).astype(int), 0, nu - 1)
    down = np.clip((v - v0).astype(int), 0, nv - 1)
    shares = []
    for near, at, n in (
        (v < v0 + d, across, nu),
        (v >= v1 - d, across, nu),
        (u < u0 + d, down, nv),
        (u >= u1 - d, down, nv),
    ):
        seen = np.zeros(n, bool)
        seen[at[near]] = True
        shares.append(float(seen.mean()))
    return float(np.mean(shares))


def _cut_caption(t: np.ndarray, lo: float, hi: float, across: float) -> tuple[float, float]:
    """The impression's extent along one axis (``t``: its pixels' places,
    from ``lo`` to ``hi``; ``across``: its extent the other way) without a
    caption or signature at either end."""
    n = int(hi - lo) + 1
    prof = np.bincount((t - lo).astype(int).clip(0, n - 1), minlength=n) / max(1.0, across)
    body = float(np.median(prof))
    reach = int(PLATE_REACH * n)
    gap = max(0.01, PLATE_GAP * body)
    ends = [lo, hi]
    for side in (0, 1):
        p = prof if side == 0 else prof[::-1]
        cut_at = None
        for j in range(2, int(PLATE_NEAR * n)):
            if p[j] <= gap and p[:j].mean() < PLATE_SPARSE * body:
                cut_at = j
        if cut_at is not None:
            j = cut_at
            while j < n - 1 and p[j] <= gap:
                j += 1
            cut_at = j
        elif body >= PLATE_DENSE:
            j = 0
            while j < reach and p[j] < PLATE_THIN * body:
                j += 1
            if 2 <= j < reach:
                cut_at = j
        if cut_at:
            ends[side] = lo + cut_at if side == 0 else hi - cut_at
    return ends[0], ends[1]


def impression(rgb: np.ndarray, sheet: Sequence[Sequence[float]]) -> Impression | None:
    """A print's impression on its ``sheet`` (corners in order, on
    ``rgb``), where there is plain paper all round it; None where there is
    none (printed to the edge, a page of text, a newspaper)."""
    flat, to_sheet = upright(rgb, sheet)
    rows, cols = flat.shape[:2]
    lab = cv2.cvtColor(
        cv2.GaussianBlur(flat, (0, 0), 1.2).astype(np.float32) / 255, cv2.COLOR_RGB2Lab
    )
    e = max(2, round(PLATE_EDGE * min(cols, rows)))
    b = max(e + 3, round(PLATE_BAND * min(cols, rows)))
    band = np.zeros((rows, cols), bool)
    band[e : rows - e, e : cols - e] = True
    band[b : rows - b, b : cols - b] = False
    paper = np.median(lab[band], axis=0)
    apart = np.linalg.norm(lab - paper, axis=2)
    far = max(PLATE_APART, _spread_above(apart[band]))
    light = lab[..., 0]
    mean = cv2.blur(light, (5, 5))
    grain = np.sqrt(np.maximum(cv2.blur(light * light, (5, 5)) - mean * mean, 0))
    rough = max(PLATE_GRAIN, _spread_above(grain[band]))
    work = ((apart > far) | (grain > rough)).astype(np.uint8)
    work[:e, :] = 0
    work[rows - e :, :] = 0
    work[:, :e] = 0
    work[:, cols - e :] = 0
    work = cv2.morphologyEx(work, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    r = max(2, round(PLATE_GROW * max(cols, rows)))
    grown = cv2.dilate(work, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    n, parts, _, _ = cv2.connectedComponentsWithStats(grown, connectivity=8)
    if n < 2:
        return None
    count = np.bincount(parts.ravel().astype(np.int64), weights=work.ravel(), minlength=n)
    count[0] = 0
    k = int(np.argmax(count))
    ys, xs = np.nonzero((parts == k) & (work > 0))
    (cx, cy), _, turn = cv2.minAreaRect(np.column_stack([xs, ys]).astype(np.float32))
    turn = ((turn + 45) % 90) - 45

    def boxed(turn: float) -> tuple[np.ndarray, np.ndarray, list[float]]:
        a = np.deg2rad(turn)
        ca, sa = np.cos(a), np.sin(a)
        u = (xs - cx) * ca + (ys - cy) * sa
        v = -(xs - cx) * sa + (ys - cy) * ca
        u0, u1 = np.percentile(u, [100 * PLATE_STRAY, 100 * (1 - PLATE_STRAY)])
        v0, v1 = np.percentile(v, [100 * PLATE_STRAY, 100 * (1 - PLATE_STRAY)])
        return u, v, [float(u0), float(v0), float(u1 + 1), float(v1 + 1)]

    def size(box: list[float]) -> float:
        return (box[2] - box[0]) * (box[3] - box[1])

    u, v, box = boxed(0.0)
    if PLATE_TURN_LEAST < abs(turn) <= PLATE_TURN:
        tu, tv, tbox = boxed(turn)
        if size(tbox) <= PLATE_TURN_GAIN * size(box):
            u, v, box = tu, tv, tbox
        else:
            turn = 0.0
    else:
        turn = 0.0
    keep = (u >= box[0]) & (u <= box[2]) & (v >= box[1]) & (v <= box[3])
    u, v = u[keep], v[keep]
    inked = (box[0], box[1], box[2], box[3])
    box[0], box[2] = _cut_caption(u, box[0], box[2], box[3] - box[1])
    box[1], box[3] = _cut_caption(v, box[1], box[3], box[2] - box[0])
    middle = (float(cx), float(cy))
    edges = (box[0], box[1], box[2], box[3])
    others = _others(work, parts, count, k, middle, float(turn), rows * cols)
    edged = _edged(u, v, edges)
    line = _lines(light, band, e)
    n_r, n_c = rows // PLATE_CELL, cols // PLATE_CELL
    cells = (
        line[: n_r * PLATE_CELL, : n_c * PLATE_CELL]
        .reshape(n_r, PLATE_CELL, n_c, PLATE_CELL)
        .sum(axis=(1, 3))
    )
    cy_, cx_ = np.nonzero(cells >= PLATE_CELL_LEAST)
    lx = (cx_ + 0.5) * PLATE_CELL
    ly = (cy_ + 0.5) * PLATE_CELL
    a = np.deg2rad(turn)
    lines = np.column_stack(
        [
            (lx - cx) * np.cos(a) + (ly - cy) * np.sin(a),
            -(lx - cx) * np.sin(a) + (ly - cy) * np.cos(a),
        ]
    )
    found = Impression(
        edges, float(turn), middle, (cols, rows), to_sheet, inked, others, lines, edged
    )
    # Plain paper round it: alike on every side, light, and little on it.
    sides = [
        lab[e:b, e : cols - e],
        lab[rows - b : rows - e, e : cols - e],
        lab[e : rows - e, e:b],
        lab[e : rows - e, cols - b : cols - e],
    ]
    med = [np.median(x.reshape(-1, 3), axis=0) for x in sides]
    sides_apart = max(float(np.linalg.norm(p - q)) for p in med for q in med)
    filled = np.zeros((rows, cols), np.uint8)
    cv2.fillPoly(filled, [np.round(found.corners()).astype(np.int32)], 1)
    beyond = cv2.dilate(filled, np.ones((2 * r + 1, 2 * r + 1), np.uint8)) == 0
    beyond[:e, :] = False
    beyond[rows - e :, :] = False
    beyond[:, :e] = False
    beyond[:, cols - e :] = False
    loose = (apart > PLATE_LOOSE) | (grain > PLATE_LOOSE_GRAIN)
    busy = float(loose[beyond].mean()) if beyond.sum() > 50 else 1.0
    plain = (
        busy <= PLATE_BUSY
        and rough <= PLATE_GRAIN_MOST
        and count[k] / max(1, int(work.sum())) >= PLATE_WHOLE
        and sides_apart <= PLATE_SIDES
        and paper[0] >= PLATE_LIGHT
        and size(box) >= PLATE_LEAST * cols * rows
    )
    return found if plain else None


def overlap(
    a: Sequence[Sequence[float]], b: Sequence[Sequence[float]], size: tuple[int, int]
) -> float:
    """How much two quads (fractions of a photograph of ``size``: w, h)
    overlap: intersection over union."""
    w, h = size
    s = 512 / max(w, h)
    cols, rows = max(1, round(w * s)), max(1, round(h * s))
    masks = []
    for quad in (a, b):
        m = np.zeros((rows, cols), np.uint8)
        cv2.fillPoly(m, [np.round(np.array(quad, float) * [cols, rows]).astype(np.int32)], 1)
        masks.append(m.astype(bool))
    union = int((masks[0] | masks[1]).sum())
    return float((masks[0] & masks[1]).sum()) / union if union else 0.0


def plate(
    rgb: np.ndarray, sheet: Sequence[Sequence[float]], over: float = PLATE_OVER
) -> tuple[Quad, Quad] | None:
    """A print's ``sheet`` (corners in order, on ``rgb``) cut down round
    its impression when the paper's widest margin is more than ``over`` of
    the impression's shorter side (:data:`PLATE_OVER`): the impression and
    :data:`PLATE_MARGIN` of it round it, the same on every side, never past
    the sheet; and the impression alone (:func:`kept`). None: the sheet
    stays."""
    found = impression(rgb, sheet)
    if found is None:
        return None
    u0, v0, u1, v1 = found.box
    least = min(u1 - u0, v1 - v0)
    margins = found.margins()
    if max(margins) <= over * least:
        return None
    # The margin round the impression with its lettering: a title or a
    # name printed under it is not cut through (Mateusz 2026-11-25, an
    # ex-libris: „kadrowanie jest za ostre - prawie wcina się w napis”).
    inked = found.inked or found.box
    for _ in range(3):
        least = min(inked[2] - inked[0], inked[3] - inked[1])
        pad = max(0.0, min(PLATE_MARGIN * least, *found.margins(inked)))
        reach = (inked[0] - pad, inked[1] - pad, inked[2] + pad, inked[3] + pad)
        # What the margin would cut through is taken in, and the margin
        # is round it all.
        touched = [o for o in found.others if _crosses(o, reach)]
        if not touched:
            break
        inked = (
            min(inked[0], *(o[0] for o in touched)),
            min(inked[1], *(o[1] for o in touched)),
            max(inked[2], *(o[2] for o in touched)),
            max(inked[3], *(o[3] for o in touched)),
        )
    # A cut that leaves the drawing out is none (a lithograph's one dark
    # figure taken for its impression, the rest of it drawn in fine lines).
    if found.lines is not None and len(found.lines):
        u, v = found.lines[:, 0], found.lines[:, 1]
        u0, v0, u1 = inked[0] - pad, inked[1] - pad, inked[2] + pad
        # Under it is what is written under a print (its title, a signature,
        # a pencilled note): not counted.
        out = (u < u0) | (u > u1) | (v < v0)
        if float(out.mean()) > PLATE_DRAWN and found.edged < PLATE_EDGED:
            return None
    h, w = rgb.shape[:2]
    cut = valid(found.on_photo(found.corners((pad, pad, pad, pad), inked), w, h))
    if cut is None:
        return None
    return cut, kept(found.on_photo(found.corners(), w, h))


def _crosses(part: Sequence[float], box: Sequence[float]) -> bool:
    """Whether ``part`` lies across ``box``'s edge: partly in, partly out."""
    meets = part[0] < box[2] and part[2] > box[0] and part[1] < box[3] and part[3] > box[1]
    inside = part[0] >= box[0] and part[1] >= box[1] and part[2] <= box[2] and part[3] <= box[3]
    return meets and not inside


def kept(quad: Sequence[Sequence[float]]) -> Quad:
    """Corners as they are kept (within the picture, five places), with no
    question of their being a cut worth making (an impression kept beside
    its cut, ``Cut.plate``)."""
    inside = [(min(max(float(x), 0.0), 1.0), min(max(float(y), 0.0), 1.0)) for x, y in quad]
    return [(round(x, 5), round(y, 5)) for x, y in inside]


@dataclass(frozen=True)
class Found:
    """What the model made of a photograph: "cut", "whole" or "unsure"
    (:func:`decide`), the work's corners set on the photograph's edges and
    the frame's or passe-partout's outer edge (None where there is none),
    and how sure it was a cut is wanted. Of a print whose sheet was cut
    down round its impression (:func:`plate`): the sheet the model found
    and the impression alone."""

    verdict: str
    work: Quad | None
    surround: Quad | None
    sure: float
    sheet: Quad | None = None
    plate: Quad | None = None


def find(
    rgb: np.ndarray, logits: np.ndarray, sure: float, cut_at: float = SURE, kind: int | None = None
) -> Found:
    """The phone's look at a museum photograph (``rgb``: the one it
    letterboxed), from the model's ``masks`` and ``cut`` (a cut at
    ``cut_at``, :func:`sure_of` its kind); a print's (``kind``) sheet cut
    down round its impression (:func:`plate`)."""
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
    verdict = decide(sure, work, (w, h), cut_at)
    if kind == KINDS.index("print"):
        made = sheet_cut(rgb, verdict, work)
        if made is not None:
            verdict, sheet, cut = made
            return Found(verdict, cut[0], surround, sure, sheet=sheet, plate=cut[1])
    return Found(verdict, work, surround, sure)


def sheet_cut(
    rgb: np.ndarray, verdict: str, work: Sequence[Sequence[float]] | None
) -> tuple[str, Quad, tuple[Quad, Quad | None]] | None:
    """A print's cut where its paper says more than the model (Mateusz
    2026-11-25: „Dlaczego takie dzieło się nie kadruje?”): the verdict
    after it, the sheet, and the cut and the impression alone (None where
    the sheet itself is the cut). None: as the model left it.

    - Cut by the model: its sheet cut down round its impression
      (:func:`plate`) where the paper is wide.
    - Wanted whole: the photograph is the sheet, cut down so too.
    - Unsure, with a sheet standing upright: cut when the paper bears it
      out, round the impression where it is wide (plain paper all round
      it), else to the sheet where what the photograph shows apart from
      its surround is that sheet (a sheet on a board).
    - Unsure with no sheet: as when wanted whole."""
    h, w = rgb.shape[:2]
    if verdict == "cut":
        if work is None:
            return None
        made = plate(rgb, work)
        return (verdict, _quad(work), made) if made is not None else None
    if verdict == "unsure" and work is not None:
        if upright_off(work, (w, h)) > UPRIGHT:
            return None
        made = plate(rgb, work)
        if made is not None:
            return ("cut", _quad(work), made)
        seen = plate(rgb, EDGES, over=0.0)
        if seen is not None and box_overlap(seen[1], work) >= PLATE_SAME:
            return ("cut", _quad(work), (_quad(work), None))
        return None
    made = plate(rgb, EDGES)
    return ("cut", list(EDGES), made) if made is not None else None


def _quad(q: Sequence[Sequence[float]]) -> Quad:
    return [(float(x), float(y)) for x, y in q]


def box_overlap(a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]) -> float:
    """How much two quads' upright boxes overlap (intersection over union;
    the same on the phone, ``MuseumCrop.boxOverlap``)."""
    ax0, ax1 = min(p[0] for p in a), max(p[0] for p in a)
    ay0, ay1 = min(p[1] for p in a), max(p[1] for p in a)
    bx0, bx1 = min(p[0] for p in b), max(p[0] for p in b)
    by0, by1 = min(p[1] for p in b), max(p[1] for p in b)
    iw = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    ih = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = iw * ih
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return float(inter / union) if union > 0 else 0.0
