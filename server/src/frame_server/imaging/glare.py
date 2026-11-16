"""A lamp's or a window's reflection taken out of a photograph of a work
by the two more photographs taken a little from each side ("Dodaj własne
dzieło", Mateusz 2026-11-16: "Zdjęcia pod różnym kątem dla uniknięcia
odbić i refleksów").

The work is flat, so each side photograph is laid over the first with
one homography (found on a small copy, SIFT and RANSAC). A reflection
stays with the light, not with the work: where the first photograph is
much brighter and paler than the side ones laid over it, it is the glare,
and the darker side photograph's pixels take its place, feathered at the
edge. Everything else is the first photograph untouched."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

#: The side the photographs are matched and the glare is found at.
MATCH_SIDE = 1200
#: Matches a side photograph needs to be laid over the first.
MIN_MATCHES = 40
#: How much brighter (0–1) the first photograph is than the side ones in a glare.
BRIGHTER = 0.12
#: A glare is bright: darker places only differ by the light.
BRIGHT = 0.45
#: …and pale (HSV saturation, 0–1), as a reflection of a white light is.
PALE = 0.45
#: Less of the picture than this is no glare, only noise: nothing is replaced.
LEAST = 0.0005

#: OpenCV's types are loose: uint8 RGB (H × W × 3) and float32 maps.
Image = NDArray[Any]
Floats = NDArray[Any]


@dataclass
class Merged:
    image: Image
    #: Side photographs that could be laid over the first.
    used: int
    #: The share of the photograph taken from the side ones (0–1).
    replaced: float


@dataclass
class _Side:
    photo: Image
    #: The side photograph's pixels → the first's, at full size.
    homography: NDArray[np.float64]
    gains: Floats
    #: Laid over the first's small copy, and where it covers it.
    small: Image
    covers: NDArray[np.bool_]


def merge(first: Image, sides: list[Image]) -> Merged:
    """``first`` with its glare taken from ``sides`` (RGB, H × W × 3)."""
    h, w = first.shape[:2]
    scale = MATCH_SIDE / max(h, w)
    small = _resize(first, scale)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    laid: list[_Side] = []
    for photo in sides:
        side_scale = MATCH_SIDE / max(photo.shape[:2])
        side_small = _resize(photo, side_scale)
        found = _homography(gray, cv2.cvtColor(side_small, cv2.COLOR_RGB2GRAY))
        if found is None:
            continue
        size = (small.shape[1], small.shape[0])
        over = cv2.warpPerspective(side_small, found, size, flags=cv2.INTER_LINEAR)
        covers = cv2.warpPerspective(
            np.full(side_small.shape[:2], 255, np.uint8), found, size, flags=cv2.INTER_NEAREST
        )
        covered = cv2.erode(covers, np.ones((7, 7), np.uint8)) > 0
        if covered.mean() < 0.3:
            continue
        gains = _gains(small, over, covered)
        full = np.diag([1 / scale, 1 / scale, 1.0]) @ found @ np.diag([side_scale, side_scale, 1.0])
        laid.append(_Side(photo, full, gains, _apply(over, gains), covered))
    if not laid:
        return Merged(first, 0, 0.0)

    mask = _glare(small, laid)
    replaced = float((mask > 0.5).mean())
    if replaced < LEAST:
        return Merged(first, len(laid), 0.0)
    return Merged(_replace(first, laid, mask), len(laid), replaced)


def _resize(img: Image, scale: float) -> Image:
    h, w = img.shape[:2]
    if scale >= 1:
        return img
    return cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)


def _homography(first: Image, side: Image) -> NDArray[np.float64] | None:
    """The side photograph's small copy laid over the first's, or None
    when too little of them matches (another work, a blur)."""
    sift = cv2.SIFT_create(4000)  # type: ignore[attr-defined]
    k1, d1 = sift.detectAndCompute(first, None)
    k2, d2 = sift.detectAndCompute(side, None)
    if d1 is None or d2 is None or len(k1) < MIN_MATCHES or len(k2) < MIN_MATCHES:
        return None
    pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(d2, d1, k=2)
    good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < 0.75 * p[1].distance]
    if len(good) < MIN_MATCHES:
        return None
    src = np.array([k2[m.queryIdx].pt for m in good], np.float32)
    dst = np.array([k1[m.trainIdx].pt for m in good], np.float32)
    found, inliers = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
    if found is None or inliers is None or int(inliers.sum()) < MIN_MATCHES:
        return None
    return np.asarray(found, np.float64)


def _gains(first: Image, side: Image, where: NDArray[np.bool_]) -> Floats:
    """Per channel, what brings the side photograph's light to the
    first's (the camera may have exposed it a little otherwise)."""
    a = first[where].astype(np.float32)
    b = side[where].astype(np.float32)
    gains = (np.median(a, axis=0) + 1) / (np.median(b, axis=0) + 1)
    return np.clip(gains, 0.7, 1.4).astype(np.float32)


def _apply(img: Image, gains: Floats) -> Image:
    return np.clip(img.astype(np.float32) * gains, 0, 255).astype(np.uint8)


def _light(img: Image) -> Floats:
    return (img.astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)) / 255


def _glare(first: Image, laid: list[_Side]) -> Floats:
    """Where the first small photograph has a reflection the side ones do
    not (0–1, feathered)."""
    light = _light(first)
    darkest = np.full(light.shape, np.inf, np.float32)
    for side in laid:
        darkest = np.where(side.covers, np.minimum(darkest, _light(side.small)), darkest)
    pale = cv2.cvtColor(first, cv2.COLOR_RGB2HSV)[..., 1].astype(np.float32) / 255 < PALE
    glare = ((light - darkest) > BRIGHTER) & (light > BRIGHT) & pale & np.isfinite(darkest)
    # Thin lines are the photographs not quite one over the other at an edge.
    opened = cv2.morphologyEx(
        glare.astype(np.uint8) * 255, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)
    )
    grown = cv2.dilate(opened, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    feathered = cv2.GaussianBlur(grown.astype(np.float32) / 255, (0, 0), 3)
    covered = np.zeros(light.shape, bool)
    for side in laid:
        covered |= side.covers
    return np.where(covered, feathered, 0).astype(np.float32)


def _replace(first: Image, laid: list[_Side], mask: Floats) -> Image:
    """The glare's pixels from the darker side photograph, at full size,
    only within the glare's box (the rest is not touched)."""
    h, w = first.shape[:2]
    big = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)
    ys, xs = np.nonzero(big > 0.01)
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    box = (x1 - x0, y1 - y0)
    shift = np.array([[1, 0, -x0], [0, 1, -y0], [0, 0, 1]], np.float64)
    best: Image | None = None
    best_light: Floats | None = None
    for side in laid:
        over = cv2.warpPerspective(
            side.photo,
            shift @ side.homography,
            box,
            flags=cv2.INTER_LINEAR,
            borderValue=(255, 255, 255),
        )
        over = _apply(over, side.gains)
        light = _light(over)
        if best is None or best_light is None:
            best, best_light = over, light
            continue
        darker = light < best_light
        best = np.where(darker[..., None], over, best)
        best_light = np.where(darker, light, best_light)
    assert best is not None
    out = first.copy()
    m = big[y0:y1, x0:x1, None]
    part = first[y0:y1, x0:x1].astype(np.float32)
    out[y0:y1, x0:x1] = np.clip(part * (1 - m) + best.astype(np.float32) * m, 0, 255).astype(
        np.uint8
    )
    return out


__all__ = ["Merged", "merge"]
