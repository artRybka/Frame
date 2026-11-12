"""The study sheet an analysis of a composition is drawn on: the picture as
a painter's synthesis, on the app's own page.

Mateusz 2026-11-11: the drawn analysis should look like "plastyczna praca
przygotowana na potrzeby takiej analizy", on "schematycznym szkicem obrazu
podkolorowanym akwarelą"; then, of the first sheets: the page must be the
app's background (light and dark), the pencil sketch had too many strokes
("jak kiepski komiks"), the watercolour was good, and "A co gdyby te
akwarele malować tak jak plamy na drodze dzieła, a rysunek jak rysunki
przy drodze dzieła?". Losing detail and shifting colours is fine with him:
"Taki szkic to ma być synteza, schemat dzieła na którym nanosi się zarys
analizy kompozycji".

So the sheet is:

- the page: ``Theme.paper`` of the app, flat (the app draws its own frame,
  grid, marks and notes around and over the picture this module makes);
- the picture's masses (about eight, by value first) as stains that spill
  like the ink stains of "Droga dzieła": a first pale wash under all, then
  each mass with a sharp wet edge where the pigment gathers and, in
  fragments, a paler second edge where the paper soaked; inside a stain the
  colour still moves a little, as the picture's does. Dark pictures are
  lifted into a watercolour's key, so that marks over them read. On the
  dark page the paint covers instead of staining and the picture stays
  dark;
- a few strokes of a nib (thick on the pull, thin where it lands and
  lifts), given by one who saw the picture (``ai.pen``); none when there
  are none.

No model is asked here; about two seconds a sheet.
"""

from __future__ import annotations

import io
import math
from collections.abc import Sequence
from typing import Any

import cv2
import numpy as np
import numpy.typing as npt
from PIL import Image

#: Pixels, as cv2 hands them about (its stubs know no dtypes).
Array = npt.NDArray[Any]
#: A stroke of the pen: its points (fractions of the picture), whether it
#: keeps its corners, whether it closes.
PenStroke = tuple[Sequence[tuple[float, float]], bool, bool]

#: Raised when the look changes, so that sheets made before are made again.
LOOK = 1
#: The sheet's longer side.
LONG = 1500
#: The app's page and ink (``Theme.paper``, ``Theme.ink``): light, dark.
PAGE = {False: (0xF5, 0xF1, 0xEA), True: (0x12, 0x11, 0x10)}
INK = {False: (0x1D, 0x1B, 0x18), True: (0xF1, 0xEC, 0xE4)}
#: The darkest a wash gets (of the page's light), so that marks over it read.
LIFT = 0.15
#: The masses a picture is gathered into, and the least a mass is (of the
#: picture): a smaller one joins what surrounds it.
MASSES = 8
LEAST = 0.005
#: The first pale wash over the whole field, under the stains.
FIRST = 0.3
#: How much of the ink a stroke of the nib lays, and its width.
NIB_INK = 0.66
NIB = 3.3


def _colour(rgb: tuple[int, int, int]) -> Array:
    return np.array(rgb, np.float32) / 255


def _noise(shape: tuple[int, int], sigma: float, rng: np.random.Generator) -> Array:
    """Smooth noise in -1…1 with features about ``sigma`` pixels."""
    h, w = shape
    if sigma > 6:  # made small and blown up: the same look, much faster
        k = sigma / 3
        raw = rng.standard_normal((max(int(h / k) + 2, 4), max(int(w / k) + 2, 4)))
        small = cv2.GaussianBlur(raw.astype(np.float32), (0, 0), 3)
        n = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    else:
        n = cv2.GaussianBlur(rng.standard_normal((h, w)).astype(np.float32), (0, 0), sigma)
    return n / (np.abs(n).max() + 1e-6)


def _keyed(rgb: Array) -> Array:
    """The picture in a watercolour's key: its darks lifted, what a dark
    varnish hides drawn out a little."""
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    clahe = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(6, 6))
    light = clahe.apply(lab[..., 0]).astype(np.float32) / 255
    lo, hi = np.percentile(light, (1.5, 98.5))
    light = np.clip((light - lo) / max(hi - lo, 0.2), 0, 1) * 0.9
    middle = float(np.clip(np.median(light), 0.08, 0.92))
    if middle < 0.38:
        light = light ** float(np.clip(math.log(0.44) / math.log(middle), 0.55, 1.0))
    lab[..., 0] = np.clip(light * 255, 0, 255).astype(np.uint8)
    return cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)


def _flat(rgb: Array, side: int, spatial: int, colour: int) -> Array:
    """The picture without its small things, ``side`` pixels long (BGR)."""
    scale = side / max(rgb.shape[:2])
    small = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    flat = cv2.pyrMeanShiftFiltering(
        cv2.cvtColor(small, cv2.COLOR_RGB2BGR), spatial, colour, maxLevel=2
    )
    return cv2.medianBlur(flat, 5)


def masses(rgb: Array, seed: int = 1) -> tuple[Array, Array]:
    """The picture's masses: a small map of which mass each place belongs to
    (from 1) and each mass's colour. What is too small to be a mass joins
    the mass around it."""
    flat = _flat(rgb, 560, 12, 32)
    lab = cv2.cvtColor(flat, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab[..., 0] *= 1.3  # a painter sorts by value first
    cv2.setRNGSeed(seed)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _, tags, _ = cv2.kmeans(  # type: ignore[call-overload]
        lab.reshape(-1, 3), MASSES, None, criteria, 4, cv2.KMEANS_PP_CENTERS
    )
    tags = tags.reshape(lab.shape[:2]).astype(np.int32)
    floor = LEAST * tags.size
    piece = np.zeros(tags.shape, np.int32)
    count = 0
    for tag in range(MASSES):  # connected pieces of each colour; the small ones are let go
        n, comp, stats, _ = cv2.connectedComponentsWithStats(
            (tags == tag).astype(np.uint8), connectivity=4
        )
        for c in range(1, n):
            if stats[c, cv2.CC_STAT_AREA] >= floor:
                count += 1
                piece[comp == c] = count
    if count == 0:  # one flat colour: one mass
        piece[:] = 1
        count = 1
    loose = (piece == 0).astype(np.uint8)
    if loose.any():
        _, near = cv2.distanceTransformWithLabels(
            loose, cv2.DIST_L2, 3, labelType=cv2.DIST_LABEL_PIXEL
        )
        lut = np.zeros(int(near.max()) + 1, np.int32)
        lut[near[loose == 0]] = piece[loose == 0]
        piece = lut[near]
    plain = cv2.cvtColor(flat, cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    colours = np.zeros((count + 1, 3), np.float32)
    for c in range(1, count + 1):
        colours[c] = np.median(plain[piece == c], axis=0)
    return piece, colours


def _pigment(colours: Array) -> Array:
    """The masses' colours as washes: a little purer, never as dark as oil."""
    hsv = cv2.cvtColor(colours.reshape(1, -1, 3), cv2.COLOR_RGB2HSV)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.2, 0, 1)
    hsv[..., 2] = LIFT + (1 - LIFT) * hsv[..., 2]
    return np.clip(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB).reshape(-1, 3) ** 0.84, 0.02, 1)


def _steps(v: Array, n: int = 5, soft: float = 0.35) -> Array:
    """Values gathered softly into ``n`` steps (a painter's few tones)."""
    x = v * n
    f = np.floor(x)
    t = np.clip((x - f - 0.5) / soft + 0.5, 0, 1)
    return (f + t * t * (3 - 2 * t)) / n


def _moving(rgb: Array, rng: np.random.Generator) -> Array:
    """The picture's own gradations as soft washes at full size (how much
    light each lets through): what moves inside a stain."""
    h, w = rgb.shape[:2]
    flat = cv2.cvtColor(_flat(rgb, 840, 10, 30), cv2.COLOR_BGR2RGB)
    img = cv2.resize(flat, (w, h), interpolation=cv2.INTER_CUBIC)
    # paint does not keep to the drawing: pushed about a little
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    dx, dy = _noise((h, w), 30, rng) * 3.5, _noise((h, w), 30, rng) * 3.5
    img = cv2.remap(img, gx + dx, gy + dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    soft = cv2.edgePreservingFilter(
        cv2.cvtColor(img, cv2.COLOR_RGB2BGR), flags=cv2.RECURS_FILTER, sigma_s=32, sigma_r=0.26
    )
    hsv = cv2.cvtColor(
        cv2.cvtColor(soft, cv2.COLOR_BGR2RGB).astype(np.float32) / 255, cv2.COLOR_RGB2HSV
    )
    hsv[..., 2] = 0.24 + 0.76 * _steps(hsv[..., 2])
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.1, 0, 1)
    return np.clip(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB), 0.02, 1) ** 0.8


def _chaikin(points: Array, times: int = 3) -> Array:
    """A line through the points with its corners cut."""
    p = points
    for _ in range(times):
        if len(p) < 3:
            break
        q = 0.75 * p[:-1] + 0.25 * p[1:]
        r = 0.25 * p[:-1] + 0.75 * p[1:]
        p = np.concatenate([p[:1], np.stack([q, r], axis=1).reshape(-1, 2), p[-1:]])
    return p


def _nib(layer: Array, points: Array, rng: np.random.Generator, width: float) -> None:
    """One stroke of a nib: thin where it lands and lifts, fuller between,
    fuller still on the pull than on the push."""
    seg = np.hypot(*np.diff(points, axis=0).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    if s[-1] < 4:
        return
    t = np.linspace(0, s[-1], max(int(s[-1] / 3), 2))
    p = np.stack([np.interp(t, s, points[:, 0]), np.interp(t, s, points[:, 1])], axis=1)
    n = len(p)
    d = np.gradient(p, axis=0)
    angle = np.arctan2(d[:, 1], d[:, 0])
    along = np.linspace(0, 1, n)
    body = np.sin(np.pi * along) ** 0.45
    pull = 0.72 + 0.4 * np.abs(np.sin(angle - 0.6))  # the nib is cut at an angle
    sway = np.interp(along, np.linspace(0, 1, 7), rng.uniform(0.85, 1.1, 7))
    w = np.maximum(width * (0.3 + 0.7 * body) * pull * sway, 1.0)
    q = np.round(p * 4).astype(np.int32)
    for i in range(n - 1):
        a, b = (int(q[i][0]), int(q[i][1])), (int(q[i + 1][0]), int(q[i + 1][1]))
        cv2.line(layer, a, b, 1.0, round(float(w[i]) * 2), cv2.LINE_AA, 2)


def render(
    picture: Image.Image,
    strokes: Sequence[PenStroke] = (),
    *,
    dark: bool = False,
    seed: int = 1,
) -> Image.Image:
    """The picture (its field alone) as the sheet's underlay: stains and a
    few strokes of a nib on the app's page, :data:`LONG` pixels long."""
    rng = np.random.default_rng(seed)
    src = np.asarray(picture.convert("RGB"))
    scale = LONG / max(src.shape[:2])
    size = (max(round(src.shape[1] * scale), 8), max(round(src.shape[0] * scale), 8))
    rgb = _keyed(
        cv2.resize(src, size, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    )
    h, w = rgb.shape[:2]
    piece, colours = masses(rgb, seed=seed % 2**31)
    paints = _pigment(colours)
    up = w / piece.shape[1]
    moving = _moving(rgb, rng)
    canvas = np.zeros((h, w, 3), np.float32) if dark else np.ones((h, w, 3), np.float32)
    cover = np.zeros((h, w), np.float32)
    # The paint keeps inside the field, raggedly.
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    inset = np.minimum.reduce([xx, yy, w - 1 - xx, h - 1 - yy])
    ragged = _noise((h, w), 20, rng) * 9 + _noise((h, w), 4, rng) * 2
    inside = np.clip((inset + ragged - 9) / 1.5, 0, 1)
    wander = _noise((h, w), 16, rng) * 0.1 + _noise((h, w), 3, rng) * 0.05  # no edge is ruled
    blotch = _noise((h, w), 46, rng) * 0.6 + _noise((h, w), 11, rng) * 0.4
    grain = _noise((h, w), 0.9, rng)
    patchy = _noise((h, w), 26, rng)  # where the paper soaks at a stain's edge
    under = FIRST * (0.85 + 0.15 * blotch) * inside
    if dark:
        canvas[:] = (moving**1.3) * under[..., None]
        cover[:] = under
    else:
        canvas *= moving ** under[..., None]
    pad = 26
    # Light first, as one paints.
    for c in sorted(range(1, len(colours)), key=lambda c: -float(paints[c].sum())):
        ys, xs = np.nonzero(piece == c)
        y0, y1 = max(int(ys.min() * up) - pad, 0), min(int((ys.max() + 1) * up) + pad, h)
        x0, x1 = max(int(xs.min() * up) - pad, 0), min(int((xs.max() + 1) * up) + pad, w)
        part = (slice(y0, y1), slice(x0, x1))
        mask = cv2.resize((piece == c).astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
        mask = cv2.GaussianBlur(mask[part], (0, 0), 2.6)
        # stains stop a hair short of each other: wet paint beside wet paint would run
        body = (mask > 0.5 + 0.6 * np.abs(wander[part])).astype(np.uint8)
        if body.sum() < 40:
            continue
        d_in = cv2.distanceTransform(body, cv2.DIST_L2, 3)
        d_out = cv2.distanceTransform(1 - body, cv2.DIST_L2, 3)
        aa = np.clip(d_in, 0, 1)
        # the wet front: pigment carried to the edge and left there
        load = (1 - FIRST) * (0.8 + 0.2 * blotch[part]) + 0.1 * grain[part]
        load += 0.42 * np.exp(-d_in / 1.3) + 0.1 * np.exp(-d_in / 9)
        # the paper soaks at the edge: a paler second stain, in fragments
        far = 5 + 7 * np.clip(patchy[part] + 0.2, 0, 1)
        halo = ((d_out > 0) & (d_out < far) & (patchy[part] > -0.1)).astype(np.float32)
        halo_load = (0.16 + 0.14 * np.exp(-np.abs(far - d_out) / 1.1)) * halo
        flat = paints[c][None, None]
        tint = 0.45 * flat + 0.55 * moving[part]
        if dark:  # on a dark page paint covers instead of staining
            alpha = np.clip((aa * load * 0.9 + (1 - aa) * halo_load * 1.3) * inside[part], 0, 1)
            canvas[part] = canvas[part] * (1 - alpha[..., None]) + (tint**1.3) * alpha[..., None]
            cover[part] = 1 - (1 - cover[part]) * (1 - alpha)
        else:
            canvas[part] *= tint ** (aa * load * inside[part])[..., None]
            canvas[part] *= flat ** ((1 - aa) * halo_load * inside[part])[..., None]
    page, ink = _colour(PAGE[dark]), _colour(INK[dark])
    sheet = np.empty((h, w, 3), np.float32)
    sheet[:] = page
    sheet = sheet * (1 - np.clip(cover, 0, 1)[..., None]) + canvas if dark else sheet * canvas
    # A few strokes of the nib, by one who saw the picture.
    line = np.zeros((h, w), np.float32)
    for points, sharp, closed in strokes:
        pts = np.asarray(points, np.float32).reshape(-1, 2) * (w, h)
        if len(pts) < 2:
            continue
        if closed:
            pts = np.concatenate([pts, pts[:2]])  # closed a little past where it began
        _nib(line, pts if sharp or len(pts) < 3 else _chaikin(pts), rng, NIB)
    laid = (np.clip(line, 0, 1) * inside * NIB_INK)[..., None]
    sheet = sheet * (1 - laid) + ink * laid
    return Image.fromarray((np.clip(sheet, 0, 1) * 255).astype(np.uint8))


def jpeg(sheet: Image.Image) -> bytes:
    """The sheet as the app gets it: its flat page must stay the page's own
    colour, so the chroma is kept whole."""
    out = io.BytesIO()
    sheet.save(out, "JPEG", quality=88, subsampling=0, optimize=True)
    return out.getvalue()
