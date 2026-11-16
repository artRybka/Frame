"""Reflections taken out of a photograph of a work by two more taken
from the sides (the scan of three, Mateusz 2026-11-16: "pierwsze zdjęcie
na wprost, a kolejne pod większym kątem", "żeby efekt był rewelacyjny").

What his own photographs of a print behind glass showed: in a bright room
every view has a veil over the whole glass, the one from the front most
of all (the room behind the photographer), and each has sharp reflections
of its own (a window, a doorway, his own figure). Replacing bright patches
(:mod:`.glare`) only made smears there.

The work is flat, so within its corners the side photographs are laid
over the first with one homography each. In linear light a reflection
only adds: each view is the work plus its own reflection layer, and the
views' differences are differences of those layers alone, whatever the
work shows. Per pixel the least view, ``low``, is the work plus the veil
all the views share there, ``common``: the one unknown. It is found as
the least field that leaves every view's reflection layer
(``common + view - low``) piecewise smooth (total variation): an edge the
work has is in all the views and costs nothing, a reflection's edge is in
one and is paid for unless ``common`` takes it over. What the first
photograph's layer comes to is subtracted from the first photograph at
its full size, so every detail stays the first photograph's own; the side
ones only say what is reflection.

The frame's side hides the work's near edge from the side, so a side
photograph does not count in a band along the edge it was taken from."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

#: The long side the photographs are laid over each other at.
MATCH_SIDE = 2400
#: Matches a side photograph needs to be laid over the first.
MIN_MATCHES = 40
#: The width the reflection layers are worked out at: reflections are
#: soft, and the work's own grain must not show in them.
LAYER_WIDTH = 256
#: The width the views' exposures are compared at.
EVEN_WIDTH = 192
#: The pyramid: how much smaller, and how many steps there.
LEVELS = ((8, 1500), (4, 1000), (2, 600), (1, 300))
#: What a unit of shared veil costs beside the layers' smoothness: next
#: to nothing, only to choose the least of the equally smooth.
VEIL_COST = 0.002
#: The band at the edge a side photograph was taken from, where the
#: frame's side hides the work (of the work's width).
HIDDEN = 0.06
#: The work's corners are found by eye (Opus, or he moves them after):
#: this much more of the photograph around them is cleaned too (of the
#: work's size, each way), so a cut a little wider has no seam.
AROUND = 0.015
#: Less light than this taken off (of the first photograph's) is nothing.
LEAST = 0.01
#: More than this is no reflection: the photographs do not show one work
#: in one light, and nothing is touched.
MOST = 0.7
#: Rows worked on at once at full size.
ROWS = 512

Image = NDArray[Any]
Floats = NDArray[Any]
Quad = list[tuple[float, float]]


@dataclass
class Merged:
    image: Image
    #: Side photographs that could be laid over the first.
    used: int
    #: The share of the first photograph's light within the work that was
    #: reflection and is taken off (0–1).
    removed: float


@dataclass
class _View:
    #: The work as this photograph shows it, laid over the first's, linear.
    light: Floats
    #: -1 taken from the left, 1 from the right, 0 the first.
    side: int


def merge(first: Image, sides: list[Image], corners: Quad) -> Merged:
    """``first`` (RGB, H × W × 3) without the reflections ``sides`` do not
    share, within ``corners`` (the work: top left, top right, bottom
    right, bottom left, 0–1 across and down)."""
    h, w = first.shape[:2]
    quad = grown(corners) * [w, h]
    scale = min(1.0, MATCH_SIDE / max(h, w))
    small = _resize(first, scale)
    # The work upright, at the size the small copy has it.
    across = (np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3])) / 2 * scale
    down = (np.linalg.norm(quad[3] - quad[0]) + np.linalg.norm(quad[2] - quad[1])) / 2 * scale
    if across < 200 or down < 200:
        return Merged(first, 0, 0.0)
    wd, ht = round(across), round(down)
    rect = np.array([[0, 0], [wd, 0], [wd, ht], [0, ht]], np.float32)
    to_work = cv2.getPerspectiveTransform(((quad + 0.5) * scale - 0.5).astype(np.float32), rect)
    front = cv2.warpPerspective(small, to_work, (wd, ht), flags=cv2.INTER_LINEAR)

    views = [_View(_linear(front), 0)]
    for photo in sides:
        laid = _lay(front, photo)
        if laid is not None:
            views.append(laid)
    if len(views) < 2:
        return Merged(first, 0, 0.0)

    layer = _reflection(views)
    removed = float(layer.mean() / max(float(_coarse(views[0].light, layer.shape).mean()), 1e-6))
    if not LEAST <= removed <= MOST:
        return Merged(first, len(views) - 1, 0.0)
    # The layer's pixels → the photograph's (a pixel's place is its middle).
    to_photo = (
        _larger(1 / scale, 1 / scale)
        @ np.linalg.inv(to_work)
        @ _larger(wd / layer.shape[1], ht / layer.shape[0])
    )
    return Merged(_subtract(first, layer, to_photo, quad), len(views) - 1, round(removed, 4))


def grown(corners: Quad) -> NDArray[np.float64]:
    """The corners with :data:`AROUND` more about their middle: what
    :func:`merge` cleans."""
    quad = np.array(corners, np.float64)
    middle = quad.mean(0)
    return middle + (quad - middle) * (1 + 2 * AROUND)


def _larger(across: float, down: float) -> NDArray[np.float64]:
    """A picture's pixels → those of one so many times larger, middle
    of a pixel to the middle of what it covers."""
    return np.array(
        [[across, 0, (across - 1) / 2], [0, down, (down - 1) / 2], [0, 0, 1]], np.float64
    )


def _resize(img: Image, scale: float) -> Image:
    if scale >= 1:
        return img
    h, w = img.shape[:2]
    return cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)


_TO_LINEAR = np.where(
    np.arange(256) / 255 <= 0.04045,
    np.arange(256) / 255 / 12.92,
    ((np.arange(256) / 255 + 0.055) / 1.055) ** 2.4,
).astype(np.float32)


def _linear(img: Image) -> Floats:
    return _TO_LINEAR[img]


#: Linear light (in 65 536 steps) → sRGB bytes.
_FROM_LINEAR = (
    np.where(
        np.arange(65536) / 65535 <= 0.0031308,
        np.arange(65536) / 65535 * 12.92,
        1.055 * np.power(np.arange(65536) / 65535, 1 / 2.4) - 0.055,
    )
    * 255
    + 0.5
).astype(np.uint8)


def _srgb(light: Floats) -> Image:
    steps = np.clip(light * 65535 + 0.5, 0, 65535).astype(np.uint16)
    return _FROM_LINEAR[steps]


def _lay(front: Image, photo: Image) -> _View | None:
    """A side photograph laid over the work as the first shows it, or
    None when too little of them matches (another work, a blur)."""
    side = _resize(photo, min(1.0, MATCH_SIDE / max(photo.shape[:2])))
    sift = cv2.SIFT_create(8000, contrastThreshold=0.02)  # type: ignore[attr-defined]
    k1, d1 = sift.detectAndCompute(cv2.cvtColor(front, cv2.COLOR_RGB2GRAY), None)
    k2, d2 = sift.detectAndCompute(cv2.cvtColor(side, cv2.COLOR_RGB2GRAY), None)
    if d1 is None or d2 is None or len(k1) < MIN_MATCHES or len(k2) < MIN_MATCHES:
        return None
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(d2, d1, k=2)
    good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < 0.8 * p[1].distance]
    if len(good) < MIN_MATCHES:
        return None
    src = np.array([k2[m.queryIdx].pt for m in good], np.float32)
    dst = np.array([k1[m.trainIdx].pt for m in good], np.float32)
    found, inliers = cv2.findHomography(src, dst, cv2.USAC_MAGSAC, 2.0)
    if found is None or inliers is None or int(inliers.sum()) < MIN_MATCHES:
        return None
    ht, wd = front.shape[:2]
    # The work's corners in the side photograph: all of it must be there,
    # and its taller side is the one the photograph was taken from.
    back = np.linalg.inv(found)
    ends = cv2.perspectiveTransform(
        np.array([[[0, 0], [wd, 0], [wd, ht], [0, ht]]], np.float64), back
    )[0]
    sh, sw = side.shape[:2]
    if (ends < -0.02 * max(sh, sw)).any() or (ends > np.array([sw, sh]) * 1.02).any():
        return None
    left = float(np.linalg.norm(ends[3] - ends[0]))
    right = float(np.linalg.norm(ends[2] - ends[1]))
    if min(left, right) <= 0:
        return None
    lean = math.log(left / right)
    over = cv2.warpPerspective(side, found, (wd, ht), flags=cv2.INTER_LINEAR)
    return _View(_linear(over), -1 if lean > 0.03 else 1 if lean < -0.03 else 0)


def _coarse(light: Floats, shape: tuple[int, ...]) -> Floats:
    return cv2.resize(light, (shape[1], shape[0]), interpolation=cv2.INTER_AREA)


def _counts(views: list[_View], h: int, w: int) -> Floats:
    """Where each view counts (1) at this size: a side one not in the
    band along the edge it was taken from."""
    counts = np.ones((len(views), h, w), np.float32)
    band = max(1, round(w * HIDDEN))
    for n, view in enumerate(views):
        if view.side < 0:
            counts[n, :, :band] = 0
        elif view.side > 0:
            counts[n, :, w - band :] = 0
    return counts


def _even(views: list[_View]) -> None:
    """The side views brought to the first's exposure and white balance.
    The work's own edges are in every view and far stronger than a
    reflection's, so per channel the gain is what the side view's steps
    across them are of the first's (a reflection only adds light, and no
    place need be clean of it in both)."""
    shape = (
        max(8, round(views[0].light.shape[0] * EVEN_WIDTH / views[0].light.shape[1])),
        EVEN_WIDTH,
    )

    def steps(light: Floats) -> tuple[Floats, Floats]:
        soft = cv2.GaussianBlur(_coarse(light, shape), (0, 0), 1.5)
        return soft[:, 1:] - soft[:, :-1], soft[1:] - soft[:-1]

    fx, fy = steps(views[0].light)
    for view in views[1:]:
        sx, sy = steps(view.light)
        for c in range(3):
            a = np.concatenate([fx[..., c].ravel(), fy[..., c].ravel()])
            b = np.concatenate([sx[..., c].ravel(), sy[..., c].ravel()])
            strong = np.abs(a) >= np.quantile(np.abs(a), 0.9)
            ratio = b[strong] / a[strong]
            gain = float(np.clip(np.median(ratio), 0.5, 2.0))
            view.light[..., c] /= gain


def _reflection(views: list[_View]) -> Floats:
    """The first view's reflection layer (linear light, :data:`LAYER_WIDTH`
    wide)."""
    _even(views)
    ht, wd = views[0].light.shape[:2]
    common: Floats | None = None
    low = lights = None
    for shrink, steps in LEVELS:
        w = max(16, LAYER_WIDTH // shrink)
        h = max(16, round(ht * w / wd))
        lights = np.stack(
            [cv2.GaussianBlur(_coarse(v.light, (h, w)), (0, 0), 1.0) for v in views]
        ).astype(np.float32)
        counts = _counts(views, h, w)
        counted = np.where(counts[..., None] > 0, lights, np.inf)
        low = counted.min(0).astype(np.float32)
        over = np.where(counts[..., None] > 0, lights - low, 0).astype(np.float32)
        # A difference counts only where both its pixels do.
        across = counts.copy()
        across[:, :, :-1] *= counts[:, :, 1:]
        down = counts.copy()
        down[:, :-1] *= counts[:, 1:]
        start = (
            np.zeros_like(low)
            if common is None
            else cv2.resize(common, (w, h), interpolation=cv2.INTER_LINEAR)
        )
        common = _shared(over, across, down, low, np.minimum(start, low), steps)
    assert common is not None and low is not None and lights is not None
    return np.clip(lights[0] - (low - common), 0, None).astype(np.float32)


def _shared(
    over: Floats, across: Floats, down: Floats, most: Floats, start: Floats, steps: int
) -> Floats:
    """The veil the views share: the least ``m`` (0 … ``most``) with every
    ``m + over[i]`` piecewise smooth. Chambolle and Pock's primal-dual
    steps for Σ‖∇m + ∇over[i]‖₁ + cost·m."""
    n = over.shape[0]
    bx = np.zeros_like(over)
    by = np.zeros_like(over)
    bx[:, :, :-1] = over[:, :, 1:] - over[:, :, :-1]
    by[:, :-1] = over[:, 1:] - over[:, :-1]
    wx, wy = across[..., None], down[..., None]
    px = np.zeros_like(over)
    py = np.zeros_like(over)
    m = start.astype(np.float32)
    ahead = m.copy()
    step = np.float32(0.99 / math.sqrt(8.0 * n))
    cost = np.float32(VEIL_COST) * step
    gx = np.zeros_like(m)
    gy = np.zeros_like(m)
    for _ in range(steps):
        gx[:, :-1] = ahead[:, 1:] - ahead[:, :-1]
        gy[:-1] = ahead[1:] - ahead[:-1]
        px = (px + step * (gx + bx)) * wx
        py = (py + step * (gy + by)) * wy
        # Onto the unit ball over both directions and the three channels
        # at once: a step is one step whatever its colour, so the veil
        # does not come out in coloured patches.
        size = np.sqrt((px * px + py * py).sum(-1, keepdims=True))
        np.maximum(size, 1, out=size)
        px /= size
        py /= size
        sx, sy = px.sum(0), py.sum(0)
        # The divergence of (sx, sy): what the steps above are the adjoint of.
        div = np.zeros_like(m)
        div[:, :-1] += sx[:, :-1]
        div[:, 1:] -= sx[:, :-1]
        div[:-1] += sy[:-1]
        div[1:] -= sy[:-1]
        new = np.clip(m + step * div - cost, 0, most)
        ahead = 2 * new - m
        m = new
    return m


def _subtract(first: Image, layer: Floats, to_photo: NDArray[np.float64], quad: Floats) -> Image:
    """``first`` less its reflection ``layer`` (laid on it by ``to_photo``)
    within ``quad``, at full size, a band of rows at a time."""
    h, w = first.shape[:2]
    x0 = max(0, math.floor(quad[:, 0].min()) - 8)
    x1 = min(w, math.ceil(quad[:, 0].max()) + 8)
    y0 = max(0, math.floor(quad[:, 1].min()) - 8)
    y1 = min(h, math.ceil(quad[:, 1].max()) + 8)
    out = first.copy()
    feather = max(1.5, 0.002 * max(x1 - x0, y1 - y0))
    for top in range(y0, y1, ROWS):
        rows = min(ROWS, y1 - top)
        shift = np.array([[1, 0, -x0], [0, 1, -top], [0, 0, 1]], np.float64)
        part = cv2.warpPerspective(
            layer,
            shift @ to_photo,
            (x1 - x0, rows),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
        inside = np.zeros((rows, x1 - x0), np.uint8)
        cv2.fillConvexPoly(inside, np.round(quad - [x0, top]).astype(np.int32), 255)
        soft = cv2.GaussianBlur(inside.astype(np.float32) / 255, (0, 0), feather)
        light = _linear(first[top : top + rows, x0:x1]) - np.clip(part, 0, None) * soft[..., None]
        out[top : top + rows, x0:x1] = _srgb(light)
    return out


__all__ = ["Merged", "grown", "merge"]
