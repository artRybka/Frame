"""A study sheet drawn by an image model, made ready for the app
(``ai.drawn`` asks the model; here are the pictures' own sums).

The model redraws the work as a painter's study, watercolour and pen in
one picture (Mateusz 2026-11-12 19:44: "całość łącznie z akwarela robi
model graficzny"), then draws the analysis's marks over it, each with a
coloured pencil of its own, and lets one wash and one line run out past
the study's edge. What comes back is a picture each time, never layers,
and never quite where it was asked to be. So:

- the study is laid back on the work (:func:`measure`, :func:`laid`): the
  model keeps the framing to about a third of a per cent, and now and then
  answers in another shape, a per cent or two stretched;
- the marks are taken off the study as one layer each (:func:`split`): a
  pencil's colour tells whose a stroke is, so a number can stand ON its
  own line (Mateusz 2026-11-12 21:26: "kółka z numerami stały na liniach,
  a nie obok nich … to możliwe tylko wtedy gdy będzie on na tej lini";
  :func:`spots`), a tapped note can leave its mark alone, and the sheet
  under them stays the one the model made first, untouched (drawing the
  marks, it repaints the study a little: about 5 of 255);
- of the answer with the spill only the side margins are kept
  (:func:`spilt`): the study itself stays as it was.

The marks keep the colours they were drawn in (Mateusz 2026-11-12 21:59:
"świetnie wyglądają kolorowe linie i bardzo poprawiają czytelność!
Absolutnie muszą zostać").
"""

from __future__ import annotations

import io
import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt
from PIL import Image

from .sheet import BLEED, LONG, PAGE, _noise, bleed

Array = npt.NDArray[Any]

#: The picture's longer side as the model gets it.
SENT = 1536
#: The copy the study is laid on the work by.
FIT_SIDE = 768
#: A study further off the work than this (its corners, of the longer
#: side) is not the work's: it is asked for again.
FAR_OFF = 6.0
#: A study laid on its work shares this much of its edges with it at
#: least (their correlation; the trial's four: 0.53 to 0.76, a study laid
#: on another work: 0.40 at most).
ALIKE = 0.45
#: The pencils, the six hues furthest apart first; a seventh only for a
#: seventh mark.
PENCILS = (
    ("BLUE", "#2446B4"),
    ("RED", "#D4261C"),
    ("GREEN", "#1E8C3C"),
    ("ORANGE", "#F08000"),
    ("VIOLET", "#8E30C0"),
    ("TURQUOISE", "#00A0B4"),
    ("MAGENTA", "#D81B8C"),
)
#: A number's ring on the sheet (its radius, of the sheet's longer side),
#: as the app draws it on a phone.
NUMBER = 0.02
#: A mark's layer is thinned by this many pixels (the model presses hard,
#: so that the pencils can be told apart) and lets the paper's tooth through.
THIN = 3
#: Less pencil than this (of the sheet) is no mark: the model left it out.
NO_MARK = 0.0006


def _rgb(colour: str) -> Array:
    return np.array([int(colour[i : i + 2], 16) for i in (1, 3, 5)], np.float32) / 255


def _hex(colour: Array) -> str:
    return "#" + "".join(f"{round(float(v) * 255):02x}" for v in np.clip(colour, 0, 1))


def _lab(colours: Array) -> Array:
    return cv2.cvtColor(np.asarray(colours, np.float32).reshape(1, -1, 3), cv2.COLOR_RGB2LAB)[0]


def _float(img: Image.Image) -> Array:
    return np.asarray(img.convert("RGB"), np.float32) / 255


def field_size(picture: Image.Image) -> tuple[int, int]:
    """The sheet's field for a picture of this shape, :data:`LONG` long."""
    k = LONG / max(picture.size)
    return max(round(picture.width * k), 1), max(round(picture.height * k), 1)


def sent(picture: Image.Image, long: int = SENT) -> Image.Image:
    """The picture as the model gets it."""
    img = picture.convert("RGB")
    if max(img.size) > long:
        k = long / max(img.size)
        img = img.resize((round(img.width * k), round(img.height * k)), Image.Resampling.LANCZOS)
    return img


# -- the study laid on the work -------------------------------------------------


def _edges(rgb: Array, sigma: float) -> Array:
    lab = cv2.GaussianBlur(cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32), (0, 0), sigma)
    g = np.zeros(lab.shape[:2], np.float32)
    for c in range(3):
        gx = cv2.Sobel(lab[..., c], cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(lab[..., c], cv2.CV_32F, 0, 1, ksize=3)
        g += gx * gx + gy * gy
    g = cv2.GaussianBlur(np.sqrt(g), (0, 0), sigma)
    return g / max(float(np.percentile(g, 99)), 1e-3)


def measure(picture: Image.Image, sheet: Image.Image) -> tuple[Array, float]:
    """Where the model's ``sheet`` lies on the ``picture`` it was made
    from: the affine that carries a place on the picture to its place on
    the sheet (both in fractions of their sides), and how far the sheet's
    corners are from where they should be (per cent of the longer side).

    Found on the two pictures' edges, blurred, coarse to fine; the sheet's
    own rim (ragged paint, a bare margin) says nothing of where the work
    lies and is left out.
    """
    k = FIT_SIDE / max(picture.size)
    w, h = max(round(picture.width * k), 16), max(round(picture.height * k), 16)
    a = np.asarray(picture.convert("RGB").resize((w, h), Image.Resampling.LANCZOS))
    b = np.asarray(sheet.convert("RGB").resize((w, h), Image.Resampling.LANCZOS))
    warp: Array = np.eye(2, 3, dtype=np.float32)
    stop = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6)
    for down, sigma in ((4, 1.5), (2, 2.0), (1, 2.0)):
        size = (w // down, h // down)
        ea = _edges(cv2.resize(a, size, interpolation=cv2.INTER_AREA), sigma)
        eb = _edges(cv2.resize(b, size, interpolation=cv2.INTER_AREA), sigma)
        m = warp.copy()
        m[:, 2] /= down
        rim = max(round(0.05 * max(size)), 2)
        inner = np.zeros((size[1], size[0]), np.uint8)
        inner[rim:-rim, rim:-rim] = 255
        try:
            _, m = cv2.findTransformECC(ea, eb, m, cv2.MOTION_AFFINE, stop, inner, 5)
        except cv2.error:  # nothing to hold on to: taken as it lies
            break
        m[:, 2] *= down
        warp = m
    corners = np.array([[0, 0], [w, 0], [0, h], [w, h]], np.float32)
    there = corners @ warp[:, :2].T + warp[:, 2]
    off = float(np.linalg.norm(there - corners, axis=1).max() / max(w, h) * 100)
    # Laid so, the sheet's edges must be the picture's: a sheet of another
    # framing (or of nothing of the work) fits nowhere, however it is laid.
    back = cv2.warpAffine(
        b,
        warp,
        (w, h),
        flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_REPLICATE,
    )
    rim = max(round(0.05 * max(w, h)), 2)
    ours = _edges(a, 2.0)[rim:-rim, rim:-rim].ravel()
    theirs = _edges(back, 2.0)[rim:-rim, rim:-rim].ravel()
    if ours.std() < 1e-6 or theirs.std() < 1e-6 or np.corrcoef(ours, theirs)[0, 1] < ALIKE:
        off = math.inf
    frac = warp.astype(np.float64)
    frac[0, 2] /= w
    frac[1, 2] /= h
    frac[0, 1] *= h / w
    frac[1, 0] *= w / h
    return frac, off


def _pixels(frac: Array, size: tuple[int, int]) -> Array:
    w, h = size
    m = np.asarray(frac, np.float32).copy()
    m[0, 2] *= w
    m[1, 2] *= h
    m[0, 1] *= w / h
    m[1, 0] *= h / w
    return m


def laid(sheet: Image.Image, frac: Array, size: tuple[int, int]) -> Image.Image:
    """The sheet moved onto the picture (:func:`measure`), ``size`` large."""
    src = np.asarray(sheet.resize(size, Image.Resampling.LANCZOS))
    out = cv2.warpAffine(
        src,
        _pixels(frac, size),
        size,
        flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return Image.fromarray(out)


def paper(rgb: Array) -> Array:
    """The model's own paper: the middle of its lightest."""
    lum = rgb.mean(axis=2)
    return np.median(rgb[lum >= np.percentile(lum, 94)].reshape(-1, 3), axis=0)


def on_page(rgb: Array) -> Array:
    """The sheet with its paper brought to the app's page: the model's
    cream is near the page's colour, never the same, and a seam would show
    where the sheet ends."""
    page = np.array(PAGE[False], np.float32) / 255
    return np.clip(rgb * (page / np.maximum(paper(rgb), 1e-3)), 0, 1)


# -- the marks, a layer each ------------------------------------------------------


def _under(points: Sequence[tuple[float, float]], closed: bool, sheet: Array) -> Array:
    """The sheet's colours along a mark's course."""
    h, w = sheet.shape[:2]
    course = list(points) + (list(points[:1]) if closed else [])
    dense = [
        (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        for a, b in itertools.pairwise(course)
        for t in np.linspace(0, 1, 16)
    ] or course
    return np.array(
        [sheet[min(max(int(y * h), 0), h - 1), min(max(int(x * w), 0), w - 1)] for x, y in dense],
        np.float32,
    )


def pencils(
    courses: Sequence[tuple[Sequence[tuple[float, float]], bool]], sheet: Image.Image
) -> list[tuple[str, str]]:
    """Which pencil (its name for the model, its colour) draws which mark:
    the choice in which every pencil stands out most from the wash it will
    lie on (a red one is lost on a red coat). ``courses``: where each
    mark runs, in fractions of the sheet, and whether it closes."""
    count = min(len(courses), len(PENCILS))
    small = cv2.GaussianBlur(_float(sheet.resize((256, 256))), (0, 0), 2)
    score = np.zeros((count, len(PENCILS)))
    for i, (points, closed) in enumerate(courses[:count]):
        below = _lab(_under(points, closed, small))
        for j, (_, colour) in enumerate(PENCILS):
            score[i, j] = np.percentile(np.linalg.norm(below - _lab(_rgb(colour)), axis=1), 20)
    best, pick = -1.0, tuple(range(count))
    for perm in itertools.permutations(range(min(max(count, 6), len(PENCILS))), count):
        got = [score[i, j] for i, j in enumerate(perm)]
        value = min(got) * 3 + sum(got) / max(count, 1) if got else 0.0
        if value > best:
            best, pick = value, perm
    return [PENCILS[j] for j in pick]


def split(
    base: Image.Image, marked: Image.Image, colours: Sequence[str]
) -> tuple[list[Array], list[str]]:
    """What each pencil drew over ``base`` to make ``marked``: a layer per
    colour (how much pencil lies at each pixel, 0…1, ``base`` large), and
    the pencils' colours as the model really made them.

    Each pixel's change from the base is explained by one pencil laid over
    it: the pencil that explains most of it with least left over has it;
    neighbours vote, since a stroke is one pencil's; what has not the
    pencil's own hue in the answer (an ink line the model drew again) and
    what lies far from the mark's strokes (a speck of repainting) is
    dropped.
    """
    size = base.size
    a = cv2.GaussianBlur(_float(base), (0, 0), 0.8)
    frac, _ = measure(base, marked)
    b = cv2.GaussianBlur(_float(laid(marked, frac, size)), (0, 0), 0.8)
    d = b - a
    cols = [_rgb(c) for c in colours]
    alphas = np.zeros((len(cols), *d.shape[:2]), np.float32)
    scores = alphas
    strong = np.zeros(d.shape[:2], bool)
    label = np.zeros(d.shape[:2], np.int64)
    for turn in range(2):
        found_a, found_s = [], []
        for c in cols:
            to = c[None, None] - a
            n2 = np.maximum((to * to).sum(axis=2), 1e-3)
            al = np.clip((d * to).sum(axis=2) / n2, 0, 1)
            left = np.linalg.norm(d - al[..., None] * to, axis=2)
            found_a.append(al)
            found_s.append(al * np.sqrt(n2) - 1.2 * left)
        alphas, scores = np.stack(found_a), np.stack(found_s)
        label = scores.argmax(axis=0)
        strong = scores.max(axis=0) > 0.10
        if turn == 0:  # the pencils as the model really made them
            for k in range(len(cols)):
                own = strong & (label == k) & (alphas[k] > 0.75)
                if own.sum() > 150:
                    cols[k] = np.median(b[own], axis=0)
    votes = np.stack(
        [
            cv2.GaussianBlur(
                np.where(strong & (label == k), np.maximum(scores[k], 0), 0).astype(np.float32),
                (0, 0),
                2.5,
            )
            for k in range(len(cols))
        ]
    )
    label = votes.argmax(axis=0)
    drawn = votes.max(axis=0) > 0.02
    hsv = cv2.cvtColor(b, cv2.COLOR_RGB2HSV)
    reach = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (71, 71))
    layers = []
    for k in range(len(cols)):
        al = np.where(drawn & (label == k), alphas[k], 0).astype(np.float32)
        al = cv2.GaussianBlur(np.clip((al - 0.12) / 0.6, 0, 1), (0, 0), 0.5)
        n, parts, stats, _ = cv2.connectedComponentsWithStats(
            (al > 0.25).astype(np.uint8), connectivity=8
        )
        own = cv2.cvtColor(np.asarray(cols[k], np.float32).reshape(1, 1, 3), cv2.COLOR_RGB2HSV)[
            0, 0
        ]
        turn_ = np.abs((hsv[..., 0] - own[0] + 180) % 360 - 180)
        good = []
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] < 14:
                continue
            heavy = (parts == i) & (al > 0.5)
            if heavy.sum() >= 6 and (
                np.median(turn_[heavy]) > 28 or np.median(hsv[..., 1][heavy]) < 0.3 * own[1]
            ):
                continue  # another hue, or greyer than the pencil
            good.append(i)
        # the dots of a dotted arc lie close to the mark's strokes; a stray bit does not
        kept = np.isin(parts, [i for i in good if stats[i, cv2.CC_STAT_AREA] >= 120])
        for _ in range(6):
            near = cv2.dilate(kept.astype(np.uint8), reach) > 0
            kept = np.isin(parts, [i for i in good if near[parts == i].any()])
        layers.append(al * (cv2.dilate(kept.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0))
    return layers, [_hex(c) for c in cols]


def softened(layer: Array, seed: int) -> Array:
    """A mark's layer as it goes on the sheet: a little thinner, the
    paper's tooth showing through it again."""
    h, w = layer.shape
    rng = np.random.default_rng(seed)
    tooth = np.clip(0.88 + 0.3 * _noise((h, w), 0.8, rng), 0, 1) * (
        0.94 + 0.06 * _noise((h, w), 9, rng)
    )
    thin = cv2.erode(layer, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (THIN, THIN)))
    return np.clip(cv2.GaussianBlur(thin, (0, 0), 0.6) * tooth, 0, 1) * 0.96


# -- a number on its own line -------------------------------------------------------


@dataclass(frozen=True)
class Placed:
    """What is known of a mark when its number is set: its shape, its
    points on the sheet (pixels) and, of a loop, the box it holds."""

    shape: str
    points: Sequence[tuple[float, float]]
    box: tuple[float, float, float, float] | None = None


def _spot(
    layer: Array,
    others: Array,
    taken: Sequence[tuple[float, float]],
    radius: float,
    busy: Array | None,
    held: Sequence[tuple[float, float, float, float]],
    near: tuple[float, float] | None = None,
    reach: float = 0.0,
) -> tuple[float, float] | None:
    """A place for a number ON this mark's own stroke: on its middle, clear
    of the other marks' strokes and of the numbers already set, where the
    sheet beneath is calm, at the rim of what another mark's loop holds."""
    h, w = layer.shape
    core = layer > 0.3
    if near is not None:
        yy, xx = np.mgrid[0:h, 0:w]
        core = core & (np.hypot(xx - near[0], yy - near[1]) < reach)
    if core.sum() < 20:
        return None
    body = (cv2.GaussianBlur(layer, (0, 0), 1.2) > 0.2).astype(np.uint8)
    inside = cv2.distanceTransform(body, cv2.DIST_L2, 3)
    ys, xs = np.nonzero(core & (inside >= min(2.5, float(inside[core].max()) * 0.6)))
    if not len(xs):
        return None
    clear = cv2.distanceTransform((~(others > 0.3)).astype(np.uint8), cv2.DIST_L2, 3)[ys, xs]
    score = np.minimum(clear, radius * 3.0)
    for tx, ty in taken:
        dist = np.hypot(xs - tx, ys - ty)
        score = (
            score
            - np.where(dist < radius * 2.4, 400, 0)
            - np.clip(radius * 5 - dist, 0, None) * 0.5
        )
    edge = np.minimum.reduce([xs, ys, w - 1 - xs, h - 1 - ys])
    score = score - np.where(edge < radius + 6, 300, 0)
    # the stroke runs right through the ring: much of this mark under the number
    size = int(radius * 2) | 1
    dense = cv2.blur((layer > 0.3).astype(np.float32), (size, size))[ys, xs]
    score = score + np.minimum(dense, 0.25) * 60
    for cx, cy, rx, ry in held:
        deep = 1 - np.hypot((xs - cx) / rx, (ys - cy) / ry)
        score = score - np.clip(deep, 0, 1) * 90
    if busy is not None:
        score = score - busy[ys, xs] * 45
    if near is not None:
        score = score - np.hypot(xs - near[0], ys - near[1]) * 0.25
    i = int(score.argmax())
    return float(xs[i]), float(ys[i])


def _busy(sheet: Array, radius: float) -> Array:
    """How much drawing lies under a number's disc at each place."""
    grey = cv2.cvtColor(sheet.astype(np.float32), cv2.COLOR_RGB2GRAY)
    fine = np.abs(grey - cv2.GaussianBlur(grey, (0, 0), 3))
    busy = cv2.GaussianBlur(fine, (0, 0), radius * 0.8)
    return np.clip(busy / max(float(np.percentile(busy, 97)), 1e-4), 0, 1)


def _rings(layer: Array, far: float) -> list[Array]:
    """The rings of an echo the model drew, each as its part of the layer:
    arcs of one ring that another mark cuts are one ring."""
    drawn = cv2.dilate((layer > 0.3).astype(np.uint8), np.ones((7, 7), np.uint8))
    n, parts, stats, cents = cv2.connectedComponentsWithStats(drawn, connectivity=8)
    top = max((stats[c, cv2.CC_STAT_AREA] for c in range(1, n)), default=0)
    big = [c for c in range(1, n) if stats[c, cv2.CC_STAT_AREA] >= max(0.3 * top, 500)]
    rings: list[list[int]] = []
    for c in sorted(big, key=lambda c: -stats[c, cv2.CC_STAT_AREA]):
        same = next((r for r in rings if math.dist(cents[c], cents[r[0]]) < far), None)
        if same is not None:
            same.append(c)
        else:
            rings.append([c])
    return [layer * np.isin(parts, r) for r in rings]


def spots(
    marks: Sequence[Placed], layers: Sequence[Array], sheet: Array
) -> list[list[tuple[float, float]]]:
    """Where each mark's number stands (pixels of the sheet), on its own
    stroke. A mark of repetitions carries its number at each place
    (Mateusz 2026-11-12 21:26: "Jeżeli numer dotyczy powtórzeń, to może
    warto go powtórzyć?"): at every ring of an echo, at a rhythm's first
    and last beat. A mark the model left out has none."""
    h, w = sheet.shape[:2]
    radius = NUMBER * max(w, h)
    busy = _busy(sheet, radius)
    taken: list[tuple[float, float]] = []
    out: list[list[tuple[float, float]]] = [[] for _ in marks]
    # the smallest marks choose first: a long line has room left anywhere
    for i in sorted(range(len(marks)), key=lambda i: float((layers[i] > 0.3).sum())):
        mark, layer = marks[i], layers[i]
        rest = [layer_ for j, layer_ in enumerate(layers) if j != i]
        others = np.max(rest, axis=0) if rest else np.zeros_like(layer)
        held = [
            (
                (b[0] + b[2]) / 2,
                (b[1] + b[3]) / 2,
                max((b[2] - b[0]) / 2, 1),
                max((b[3] - b[1]) / 2, 1),
            )
            for j, m in enumerate(marks)
            if j != i and (b := m.box) is not None
        ]
        found: list[tuple[float, float]] = []
        places: list[tuple[float, float]] = []
        if mark.shape == "echo":
            rings = _rings(layer, 0.07 * max(w, h))
            if 2 <= len(rings) <= 5:
                for ring in rings:
                    spot = _spot(ring, others, taken + found, radius, busy, held)
                    if spot:
                        found.append(spot)
            else:
                places = list(mark.points)
        elif mark.shape == "rhythm" and len(mark.points) >= 4:
            ends = list(mark.points)
            places = [
                ((ends[0][0] + ends[1][0]) / 2, (ends[0][1] + ends[1][1]) / 2),
                ((ends[-2][0] + ends[-1][0]) / 2, (ends[-2][1] + ends[-1][1]) / 2),
            ]
        for place in places:
            spot = _spot(layer, others, taken + found, radius, busy, held, place, 0.085 * max(w, h))
            if spot:
                found.append(spot)
        if not found:
            spot = _spot(layer, others, taken, radius, busy, held)
            if spot:
                found = [spot]
        taken += found
        out[i] = found
    return out


# -- the study leaving its field --------------------------------------------------


def padded(sheet: Image.Image) -> tuple[Image.Image, int]:
    """The model's sheet on a wider sheet of its own paper, as it is sent
    to have a wash and a line run out of it; and the margin's width."""
    a = _float(sheet)
    m = bleed(sheet.width)
    out = np.empty((sheet.height + 2 * m, sheet.width + 2 * m, 3), np.float32)
    out[:] = paper(a)[None, None]
    out[m:-m, m:-m] = a
    return Image.fromarray((out * 255).astype(np.uint8)), m


def spilt(
    sheet: Image.Image, answer: Image.Image, frac: Array, size: tuple[int, int]
) -> tuple[Array, Array]:
    """The side margins of the model's ``answer`` to :func:`padded`, laid
    beside the field as the sheet itself is (``frac``: :func:`measure` of
    the work and the sheet; ``size``: the field's): the sheet with its
    margins (``size[1]`` high, wider by :func:`bleed` each side, the
    answer's paper brought to the page) and how much of each margin pixel
    is spill (0 inside the field and where the paper is bare)."""
    wide, m_raw = padded(sheet)
    fitted, _ = measure(wide, answer)
    there = np.asarray(laid(answer, fitted, wide.size))
    fw, fh = size
    m = bleed(fw)
    # a place on the page (the field with its margins) → its place on the sheet
    # → on the padded sheet
    a = np.asarray(frac, np.float64)
    sw, sh = sheet.size
    warp = np.array(
        [
            [a[0, 0] * sw / fw, a[0, 1] * sw / fh, 0.0],
            [a[1, 0] * sh / fw, a[1, 1] * sh / fh, 0.0],
        ],
        np.float64,
    )
    warp[0, 2] = a[0, 2] * sw + m_raw - m * warp[0, 0]
    warp[1, 2] = a[1, 2] * sh + m_raw - m * warp[1, 0]
    out = cv2.warpAffine(
        there,
        warp.astype(np.float32),
        (fw + 2 * m, fh),
        flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
        borderMode=cv2.BORDER_REPLICATE,
    )
    rgb = out.astype(np.float32) / 255
    own = paper(rgb)
    far = np.linalg.norm((rgb - own[None, None]) * np.array([1, 1, 1.2], np.float32), axis=2)
    alpha = np.clip((cv2.GaussianBlur(far, (0, 0), 1.0) - 0.035) / 0.07, 0, 1)
    alpha[:, m : m + fw] = 0
    # the ends of a margin are the page's corners: nothing there
    rows = np.arange(fh)
    alpha *= np.clip(np.minimum(rows, fh - 1 - rows) / 40, 0, 1)[:, None]
    page = np.array(PAGE[False], np.float32) / 255
    return np.clip(rgb * (page / np.maximum(own, 1e-3)), 0, 1), alpha


def page(field: Array, spill: tuple[Array, Array] | None, seed: int) -> Array:
    """The sheet as the app lays it: the field (already on the page's
    paper, :func:`on_page`) with a ragged edge, the page's margin on each
    side of it (:func:`bleed`), and in the margins what ran out (``spill``:
    :func:`spilt`). Where a wash leaves, the field's edge is open and the
    wash keeps the tone it has there for a short way, then pales as the
    model made it: no step at the frame."""
    fh, fw = field.shape[:2]
    m = bleed(fw)
    paper_ = np.array(PAGE[False], np.float32) / 255
    out = np.empty((fh, fw + 2 * m, 3), np.float32)
    out[:] = paper_[None, None]
    yy, xx = np.mgrid[0:fh, 0:fw].astype(np.float32)
    inset = np.minimum.reduce([xx, yy, fw - 1 - xx, fh - 1 - yy])
    rng = np.random.default_rng(seed)
    ragged = _noise((fh, fw), 20, rng) * 9 + _noise((fh, fw), 4, rng) * 2
    inside = np.clip((inset + ragged - 9) / 1.5, 0, 1)
    shown = field
    if spill is not None:
        wide, alpha = spill
        wide = wide.copy()
        left = cv2.GaussianBlur(alpha[:, m - 14 : m].max(axis=1).reshape(-1, 1), (0, 0), 6).ravel()
        right = cv2.GaussianBlur(
            alpha[:, m + fw : m + fw + 14].max(axis=1).reshape(-1, 1), (0, 0), 6
        ).ravel()
        reach = 0.05 * max(fw, fh)
        open_ = np.maximum(
            left[:, None] * np.clip(1 - xx / reach, 0, 1),
            right[:, None] * np.clip(1 - (fw - 1 - xx) / reach, 0, 1),
        )
        # there the model's own joint of study and spill is taken: the wash runs on unbroken
        shown = field * (1 - open_[..., None]) + wide[:, m : m + fw] * open_[..., None]
        inside = np.maximum(inside, np.clip(open_ * 3, 0, 1))
        hold = np.clip(1 - np.arange(m, dtype=np.float32) / (m * 0.4), 0, 1) ** 1.2
        for edge, strip, fade in (
            (shown[:, :10].mean(axis=1), wide[:, :m], hold[::-1]),
            (shown[:, -10:].mean(axis=1), wide[:, m + fw :], hold),
        ):
            tone = cv2.GaussianBlur(edge.reshape(-1, 1, 3), (0, 0), 14).reshape(-1, 3)
            strip[:] = strip * (1 - fade[None, :, None]) + tone[:, None] * fade[None, :, None]
        out = out * (1 - alpha[..., None]) + wide * alpha[..., None]
    out[:, m : m + fw] = paper_[None, None] * (1 - inside[..., None]) + shown * inside[..., None]
    return np.clip(out, 0, 1)


# -- as the app gets them -------------------------------------------------------------


def jpeg(rgb: Array) -> bytes:
    """The sheet: its bare paper must stay the page's own colour, so the
    chroma is kept whole."""
    out = io.BytesIO()
    img = Image.fromarray((np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8))
    img.save(out, "JPEG", quality=88, subsampling=0, optimize=True)
    return out.getvalue()


def png(layer: Array) -> bytes:
    """A mark's layer: black, as much of it as there is pencil (clear
    elsewhere); the app gives it the pencil's colour."""
    alpha = (np.clip(layer, 0, 1) * 255 + 0.5).astype(np.uint8)
    rgba = np.zeros((*alpha.shape, 4), np.uint8)
    rgba[..., 3] = alpha
    out = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(out, "PNG", optimize=True)
    return out.getvalue()


__all__ = [
    "BLEED",
    "FAR_OFF",
    "LONG",
    "NO_MARK",
    "PENCILS",
    "Placed",
    "bleed",
    "field_size",
    "jpeg",
    "laid",
    "measure",
    "on_page",
    "padded",
    "page",
    "pencils",
    "png",
    "sent",
    "softened",
    "spilt",
    "split",
    "spots",
]
