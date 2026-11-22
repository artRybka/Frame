"""A printed screen taken off a picture before it is drawn again.

Some museum pictures are scans of a printed page: the paint is there as
the printer's dots, a fine regular lattice. Drawn again larger (the
creative restorer, ``restorer.py``), the dots are made sharper still and
the whole work is seen through a net (Valtat's "Bateaux au port", Mateusz
2026-11-22). Such a lattice is a few bright points in the picture's
spectrum, far from its middle: they are found and taken out, and nothing
else of the picture is touched.

A JPEG's own 8-pixel blocks fall on the same kind of points, on the
eighths of the spectrum; those are left alone (the restorer takes the
blocks out itself).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable

import cv2
import numpy as np
from PIL import Image

log = logging.getLogger(__name__)

#: The finest and coarsest lattice taken for a screen, in pixels between
#: its dots. Coarser than this is the work's own pattern (a tiled floor,
#: a lace), never a printer's.
FINEST = 2.2
COARSEST = 12.0

#: How far above the spectrum around it a point has to stand (natural log
#: of the ratio) to be a screen's: a printed screen stands 4 or more,
#: a painting's brushwork and a canvas weave seldom 2.
STANDS = 3.0

#: The most points taken out: a screen's four, their next ones and a
#: second colour's.
MOST = 16

#: Fewest points (two pairs) for a screen: a lattice is never one line.
FEWEST = 4

#: Points this near (in cycles a pixel) to an eighth are a JPEG's blocks.
BLOCKS = 0.006

#: The notch around each point, as a share of the screen's own spacing
#: in the spectrum: a dot grows and shrinks with the tone it prints, and
#: that spreads its point.
NOTCH = 0.15

#: How far the lattice of a screen is followed (its sums and multiples).
HARMONICS = 6

#: Lattice points folded back nearer the middle than this many notches
#: are left: they would take the picture's masses away. (Those a little
#: farther are the screen's moiré, and go.)
NEAREST = 5.0

#: The mirrored border put round a picture before its spectrum is taken,
#: as a share of its longer side.
PAD = 0.04

#: A picture no longer than this is drawn more than three times larger;
#: its grain finer than :data:`SOFT` cycles a pixel (a period of under
#: two and a half pixels) is let go of, gently, up to none at the finest
#: (0.3 took Valtat's net away but left him blurred: Mateusz 2026-11-22).
SMALL = 1000
SOFT = 0.42

#: The picture is looked at no larger than this (its middle), for speed.
LOOKED = 1024


def _gray(picture: Image.Image) -> np.ndarray:
    return np.asarray(picture.convert("L"), dtype=np.float32) / 255.0


def screen(picture: Image.Image) -> list[tuple[float, float]]:
    """The points of a printed screen in ``picture``'s spectrum, as
    (cycles a pixel down, across); none when it has no screen."""
    gray = _gray(picture)
    h, w = gray.shape
    if min(h, w) < 64:
        return []
    side = min(LOOKED, h, w)
    top, left = (h - side) // 2, (w - side) // 2
    part = gray[top : top + side, left : left + side]
    part = part - float(part.mean())
    window = np.outer(np.hanning(side), np.hanning(side)).astype(np.float32)
    spectrum = np.fft.fftshift(np.abs(np.fft.fft2(part * window)))
    level = np.log(spectrum + 1e-6).astype(np.float32)
    ground = cv2.GaussianBlur(level, (0, 0), max(3.0, side / 96))
    stands = level - ground
    biggest = cv2.dilate(stands, np.ones((5, 5), np.uint8))
    freq = (np.arange(side) - side // 2) / side
    fy, fx = np.meshgrid(freq, freq, indexing="ij")
    radius = np.hypot(fy, fx)
    near_block = (np.abs(fy * 8 - np.round(fy * 8)) < BLOCKS * 8) & (
        np.abs(fx * 8 - np.round(fx * 8)) < BLOCKS * 8
    )
    found = (
        (stands >= biggest)
        & (stands > STANDS)
        & (radius > 1 / COARSEST)
        & (radius < 1 / FINEST)
        & ~near_block
    )
    ys, xs = np.nonzero(found)
    if len(ys) < FEWEST:
        return []
    order = np.argsort(-stands[ys, xs])[:MOST]
    return [(float(fy[ys[i], xs[i]]), float(fx[ys[i], xs[i]])) for i in order]


def lattice(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Every point of the lattice the screen's ``points`` lie on (its
    sums and multiples too, folded back into the spectrum where they
    pass its edge): a printed dot is no sine, and what is left of it
    otherwise is a finer net."""
    first = points[0]
    second = next(
        (p for p in points[1:] if abs(first[0] * p[1] - first[1] * p[0]) > 1e-4),
        None,
    )
    if second is None:
        return points
    near = min(math.hypot(py, px) for py, px in points)
    out: list[tuple[float, float]] = []
    for i in range(-HARMONICS, HARMONICS + 1):
        for j in range(-HARMONICS, HARMONICS + 1):
            if i == 0 and j == 0:
                continue
            py = (i * first[0] + j * second[0] + 0.5) % 1.0 - 0.5
            px = (i * first[1] + j * second[1] + 0.5) % 1.0 - 0.5
            if math.hypot(py, px) > NEAREST * NOTCH * near:
                out.append((py, px))
    return out


def _filtered(rgb: np.ndarray, keep: Callable[[int, int], np.ndarray]) -> np.ndarray:
    """``rgb`` through a filter of its spectrum, ``keep(h, w)`` (in the
    order of ``np.fft.fftfreq``), mirrored at its edges first so that the
    spectrum's wrapping round leaves no band along them."""
    h, w = rgb.shape[:2]
    pad = max(8, round(PAD * max(h, w)))
    # Padded on to a size the transform is quick at (2, 3 and 5 only).
    bh, bw = cv2.getOptimalDFTSize(h + 2 * pad), cv2.getOptimalDFTSize(w + 2 * pad)
    top, left = (bh - h) // 2, (bw - w) // 2
    big = cv2.copyMakeBorder(rgb, top, bh - h - top, left, bw - w - left, cv2.BORDER_REFLECT)
    mask = keep(bh, bw)
    out = np.empty_like(rgb)
    for c in range(3):
        spectrum = cv2.dft(np.ascontiguousarray(big[..., c]), flags=cv2.DFT_COMPLEX_OUTPUT)
        spectrum[..., 0] *= mask
        spectrum[..., 1] *= mask
        back = cv2.idft(spectrum, flags=cv2.DFT_SCALE | cv2.DFT_REAL_OUTPUT)
        out[..., c] = back[top : top + h, left : left + w]
        del spectrum, back
    return out


def _notches(points: list[tuple[float, float]], notch: float) -> Callable[[int, int], np.ndarray]:
    def keep(h: int, w: int) -> np.ndarray:
        mask = np.ones((h, w), dtype=np.float32)
        ry, rx = max(1, int(4 * notch * h)), max(1, int(4 * notch * w))
        dy = (np.arange(-ry, ry + 1) / h)[:, None]
        dx = (np.arange(-rx, rx + 1) / w)[None, :]
        for py, px in points:
            for sy, sx in ((py, px), (-py, -px)):
                cy, cx = round(sy * h), round(sx * w)
                gy = (dy + cy / h - sy) ** 2
                gx = (dx + cx / w - sx) ** 2
                rows = np.arange(cy - ry, cy + ry + 1) % h
                cols = np.arange(cx - rx, cx + rx + 1) % w
                dip = np.exp(-(gy + gx) / (2 * notch * notch)).astype(np.float32)
                mask[np.ix_(rows, cols)] *= 1.0 - dip
        return mask

    return keep


def _finest_off(h: int, w: int) -> np.ndarray:
    fy = np.fft.fftfreq(h).astype(np.float32)[:, None]
    fx = np.fft.fftfreq(w).astype(np.float32)[None, :]
    radius = np.sqrt(fy * fy + fx * fx)
    # Full below SOFT, none at the corner of the spectrum, smooth between.
    t = np.clip((radius - SOFT) / (0.5 - SOFT), 0.0, 1.0)
    return (0.5 + 0.5 * np.cos(np.pi * t)).astype(np.float32)


def descreened(picture: Image.Image) -> Image.Image:
    """``picture`` with a printed screen taken out; ``picture`` itself
    when it has none. A small picture (no longer than :data:`SMALL`) loses
    its finest grain as well: a screen there is at the edge of what its
    pixels hold, too weak to be found, and drawn three times larger it
    was a sharp net (Valtat's, a 595-pixel photograph)."""
    found = screen(picture)
    small = max(picture.size) <= SMALL
    if not found and not small:
        return picture
    rgb = np.asarray(picture.convert("RGB"), dtype=np.float32)
    h, w = rgb.shape[:2]
    if found:
        notch = NOTCH * min(math.hypot(py, px) for py, px in found)
        rgb = _filtered(rgb, _notches(lattice(found), notch))
        log.info("descreen: a printed screen (%d points) taken out of %dx%d", len(found), w, h)
    if small:
        rgb = _filtered(rgb, _finest_off)
    return Image.fromarray(np.clip(rgb + 0.5, 0, 255).astype(np.uint8))
