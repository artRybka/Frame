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
  like the ink stains of "Droga dzieła": a first pale wash where things
  happen, then each mass with a sharp wet edge where the pigment gathers
  and, in fragments, a paler second edge where the paper soaked; inside a
  stain the colour still moves a little, as the picture's does. Dark
  pictures are lifted into a watercolour's key, so that marks over them
  read. On the dark page the paint covers instead of staining and the
  picture stays dark;
- more general where less happens (Mateusz 2026-11-12: "Czy sama akwarela
  w tle mogłaby być ogólniejsza? Szczególnie tam gdzie mniej się dzieje?
  Może nawet nie zalewać plamą wszystkiego i fragmentami zostawiać tło
  podkładu"): there the small masses join the great ones, neighbours of
  nearly one colour are one stain, the stain is flat, and the page is left
  bare in fragments: most where the picture is nearest the page's own
  value (the lights on the light page, the darks on the dark one) and
  towards the field's edge, as a painter leaves a study unfinished;
- neighbours as he asked next (07:01): "Przerwy mogłyby pojawiać się czasem
  także pomiędzy plamami koloru. Teraz zawsze się nakładają jedna na drugą
  i powstaje ciemniejszy pas w każdym takim miejscu", and "jeżeli dwie
  plamy akwareli są do siebie bardzo podobne (np. niebieska ściana w
  pokoju van Gogha), to lepiej zlać je w jedną plamę". So neighbours very
  near in colour are one stain anywhere (:data:`SAME`); a stain's soaked
  edge lies on bare paper only, never over a neighbour; where two stains
  touch their wet fronts are faint; and here and there they keep apart and
  the page shows between them (:data:`GAP`);
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
LOOK = 2
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
#: Where nothing happens a mass must be this much of the picture, and
#: neighbours there no further apart than this (CIE Lab) are one stain.
QUIET_LEAST = 0.04
ALIKE = 15.0
#: Neighbours this near in colour are one stain anywhere.
SAME = 13.0
#: The first pale wash under the stains, where things happen.
FIRST = 0.3
#: What decides where the page is left bare in a quiet place: how near the
#: stain is to the page's own value, how near the field's edge, and chance;
#: bare where they come to more than :data:`BARE`.
BARE_NEAR = 0.7
BARE_RIM = 0.6
BARE_CHANCE = 0.45
BARE = 0.55
#: How far two neighbouring stains keep apart at most, where they do (of
#: the blurred edge between them: about three pixels each).
GAP = 0.38
#: How far under :data:`BARE` the wash begins to run thin, and the most of
#: the field that is left bare (a picture that is all sky is still painted).
BARE_THIN = 0.2
BARE_MOST = 0.3
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


def busy(rgb: Array, shape: tuple[int, int]) -> Array:
    """How much happens at each place of the picture, from 0 (a plain sky,
    a wall, a dark ground) to 1 (figures, foliage, a crowd), as a map of
    ``shape``: how many edges lie around the place, against the picture's
    own busiest parts but never against less than a plain picture has."""
    scale = 240 / max(rgb.shape[:2])
    small = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(cv2.GaussianBlur(small, (0, 0), 1.2), cv2.COLOR_RGB2LAB).astype(np.float32)
    lab[..., 0] *= 100 / 255
    edges = np.zeros(lab.shape[:2], np.float32)
    for channel in range(3):
        gx = cv2.Sobel(lab[..., channel], cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(lab[..., channel], cv2.CV_32F, 0, 1, ksize=3)
        edges += gx * gx + gy * gy
    around = cv2.GaussianBlur(np.sqrt(edges), (0, 0), 9)
    most = max(float(np.percentile(around, 90)), 14.0)
    t = np.clip((around / most - 0.22) / 0.5, 0, 1)
    return cv2.resize(t * t * (3 - 2 * t), (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)


def _joined(piece: Array, count: int, lab: Array, quiet: Array) -> Array:
    """The masses with neighbours of nearly one colour made one (anywhere
    when very near, further apart where little happens): the nearest pair
    first, until none is near enough."""
    flat = piece.ravel()
    area = np.bincount(flat, minlength=count + 1).astype(np.float64)
    total = np.stack(
        [np.bincount(flat, lab[..., k].ravel(), minlength=count + 1) for k in range(3)], axis=1
    )
    still = np.bincount(flat, quiet.ravel(), minlength=count + 1)
    pairs: set[tuple[int, int]] = set()
    for one, other in ((piece[:, :-1], piece[:, 1:]), (piece[:-1], piece[1:])):
        differ = one != other
        lo = np.minimum(one[differ], other[differ])
        hi = np.maximum(one[differ], other[differ])
        pairs.update(zip(lo.tolist(), hi.tolist(), strict=True))
    to = np.arange(count + 1)
    while pairs:
        best: tuple[int, int] | None = None
        nearest = 1.0
        for a, b in pairs:
            calm = float(min(still[a] / area[a], still[b] / area[b]))
            apart = float(np.linalg.norm(total[a] / area[a] - total[b] / area[b]))
            limit = max(SAME, ALIKE * calm if calm > 0.5 else 0.0)
            if apart < nearest * limit:
                best, nearest = (a, b), apart / limit
        if best is None:
            break
        a, b = best
        area[a] += area[b]
        total[a] += total[b]
        still[a] += still[b]
        to[to == b] = a
        moved = ((int(to[p]), int(to[q])) for p, q in pairs)
        pairs = {(min(x, y), max(x, y)) for x, y in moved if x != y}
    return to[piece]


def masses(rgb: Array, seed: int = 1) -> tuple[Array, Array]:
    """The picture's masses: a small map of which mass each place belongs to
    (from 1) and each mass's colour. What is too small to be a mass joins
    the mass around it, and where little happens a mass must be greater and
    neighbours of nearly one colour are one."""
    flat = _flat(rgb, 560, 12, 32)
    quiet = 1 - busy(rgb, flat.shape[:2])
    true = cv2.cvtColor(flat, cv2.COLOR_BGR2LAB).astype(np.float32)
    true[..., 0] *= 100 / 255
    lab = cv2.cvtColor(flat, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab[..., 0] *= 1.3  # a painter sorts by value first
    cv2.setRNGSeed(seed)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _, tags, _ = cv2.kmeans(  # type: ignore[call-overload]
        lab.reshape(-1, 3), MASSES, None, criteria, 4, cv2.KMEANS_PP_CENTERS
    )
    tags = tags.reshape(lab.shape[:2]).astype(np.int32)
    piece = np.zeros(tags.shape, np.int32)
    count = 0
    for tag in range(MASSES):  # connected pieces of each colour; the small ones are let go
        n, comp, stats, _ = cv2.connectedComponentsWithStats(
            (tags == tag).astype(np.uint8), connectivity=4
        )
        calm = np.bincount(comp.ravel(), quiet.ravel(), minlength=n)
        for c in range(1, n):
            area = stats[c, cv2.CC_STAT_AREA]
            least = LEAST + (QUIET_LEAST - LEAST) * calm[c] / area
            if area >= least * tags.size:
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
    joined = _joined(piece, count, true, quiet)
    kept = np.unique(joined)
    piece = np.searchsorted(kept, joined).astype(np.int32) + 1
    count = len(kept)
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
    lively = busy(rgb, (h, w))
    under = FIRST * (0.85 + 0.15 * blotch) * inside * lively
    # Where little happens the page is left bare in fragments: sooner where
    # the stain would be near the page's own value, and towards the edge.
    page_lab = cv2.cvtColor(_colour(PAGE[dark]).reshape(1, 1, 3), cv2.COLOR_RGB2LAB)[0, 0]
    worn = paints**1.3 if dark else paints
    apart = np.linalg.norm(
        cv2.cvtColor(worn.reshape(1, -1, 3), cv2.COLOR_RGB2LAB)[0] - page_lab, axis=1
    )
    near = np.clip(1.25 - apart / (52.0 if dark else 45.0), 0, 1)
    near[0] = 0
    near_map = cv2.GaussianBlur(
        cv2.resize(near[piece], (w, h), interpolation=cv2.INTER_LINEAR), (0, 0), 6
    )
    rim = np.clip(1 - inset / (0.3 * min(h, w)), 0, 1)
    chance = _noise((h, w), 0.07 * max(h, w), rng) * 0.8 + _noise((h, w), 18, rng) * 0.2
    bare = (1 - lively) * (BARE_NEAR * near_map + BARE_RIM * rim + BARE_CHANCE * chance)
    level = max(BARE, float(np.quantile(bare, 1 - BARE_MOST)))
    painted = bare < level
    # towards a bare place the wash runs thin before it stops
    thin = np.clip((level - bare) / BARE_THIN, 0, 1)
    least = 0.55 if dark else 0.35  # covering paint thinned much is a smudge
    thin = least + (1 - least) * thin * thin * (3 - 2 * thin)
    if dark:
        canvas[:] = (moving**1.3) * under[..., None]
        cover[:] = under
    else:
        canvas *= moving ** under[..., None]
    pad = 26
    # Where neighbours keep apart and the page shows between them.
    seam = np.clip(_noise((h, w), 60, rng) * 3 - 0.3, 0, 1)
    # Each stain's body first, light ones first as one paints: a stain's
    # soaked edge is then not laid over its neighbours.
    stains: list[tuple[int, tuple[slice, slice], Array]] = []
    taken = np.zeros((h, w), np.float32)
    for c in sorted(range(1, len(colours)), key=lambda c: -float(paints[c].sum())):
        ys, xs = np.nonzero(piece == c)
        y0, y1 = max(int(ys.min() * up) - pad, 0), min(int((ys.max() + 1) * up) + pad, h)
        x0, x1 = max(int(xs.min() * up) - pad, 0), min(int((xs.max() + 1) * up) + pad, w)
        part = (slice(y0, y1), slice(x0, x1))
        mask = cv2.resize((piece == c).astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
        mask = cv2.GaussianBlur(mask[part], (0, 0), 2.6)
        # neighbours meet, or here and there keep apart (wet paint beside
        # wet paint would run) and the page shows between them
        short = 0.5 + (GAP + 0.6 * np.abs(wander[part])) * seam[part]
        body = ((mask > short) & painted[part]).astype(np.uint8)
        if body.sum() < 40:
            continue
        stains.append((c, part, body))
        taken[part] = np.maximum(taken[part], body)
    for c, part, body in stains:
        d_in = cv2.distanceTransform(body, cv2.DIST_L2, 3)
        d_out = cv2.distanceTransform(1 - body, cv2.DIST_L2, 3)
        aa = np.clip(d_in, 0, 1)
        others = cv2.GaussianBlur(taken[part] - body, (0, 0), 2.5)
        touch = np.clip(others * 3, 0, 1)
        # the wet front: pigment carried to the edge and left there, most
        # where the edge is open; two fronts side by side would be a dark band
        load = (1 - FIRST) * (0.8 + 0.2 * blotch[part]) * thin[part] + 0.1 * grain[part]
        load += (0.42 * np.exp(-d_in / 1.3) + 0.1 * np.exp(-d_in / 9)) * (1 - 0.8 * touch)
        # the paper soaks at the edge: a paler second stain, in fragments,
        # on the bare paper only
        far = 5 + 7 * np.clip(patchy[part] + 0.2, 0, 1)
        halo = ((d_out > 0) & (d_out < far) & (patchy[part] > -0.1)).astype(np.float32)
        halo *= np.clip(1 - others * 4, 0, 1)
        halo_load = (0.16 + 0.14 * np.exp(-np.abs(far - d_out) / 1.1)) * halo
        flat = paints[c][None, None]
        # the stain is flat where nothing happens, and moves where much does
        own = (0.12 + 0.43 * lively[part])[..., None]
        tint = (1 - own) * flat + own * moving[part]
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
