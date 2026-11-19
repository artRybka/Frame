"""The lens's own bend taken out of the photograph of a work.

Mateusz 2026-11-18 22:28 UTC, his still life in its frame, the frame's
straight sides drawn over as a barrel: "Zakrzywienie obiektywu iPhone?
Jakieś możliwości prostowania czy to bardzo skomplikowane?". It is the
lens: the phone's main camera draws a straight line bowed outward, the
more the nearer the photograph's edge. Measured on the straight edges of
his frames (plumb lines: the one bend that makes them all straight): a
side of the frame as long as the photograph bows some 0.4% of its length,
20 pixels of 6048, the same in the first photograph of a scan (48 MP), in
the side ones the tracking takes, and in a photograph from the phone's
own Camera (24 MP).

One radial term says it. A point ``u`` of the straight picture (from the
photograph's middle, its half-diagonal 1) is in the photograph at
``u * (1 + k1 * |u|²)``; a barrel has ``k1`` below 0. Straightened, the
photograph keeps its size and its middle; with a barrel a rim of it (2%
at the corners, under 1% at the long sides' middle) falls outside.

Only a lens that was measured is taken out (:data:`BENDS`), and only
where the photograph's camera says so itself: a photograph that names no
camera, or another, or the same one zoomed, stays as it was taken."""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from PIL import Image
from pillow_heif import register_heif_opener

from .cut import Quad

# The phone's own photographs come as HEIC as well as JPEG.
register_heif_opener()

#: The bend (``k1``) of a phone's main camera, by the model its
#: photographs name. His iPhone 18 Pro Max: -0.024 and -0.021 on the first
#: photographs of two scans of framed works, -0.0235, -0.024 and -0.0235
#: on side photographs, -0.021 on a photograph of the panel's test chart
#: from Camera; their edges were off a line by 2 to 4 pixels (root mean
#: square, of 8064) and by 0.4 to 1.4 with it taken out.
BENDS = {"iPhone 18 Pro Max": -0.023}
#: The phone his scans were taken with before a scan noted its camera
#: (to 1.145.248): the app's camera is the main one, never zoomed.
PHONE = "iPhone 18 Pro Max"
#: The main camera as its photographs say it (the focal length a 35 mm
#: film would need): the wide one is 13, the long ones 48 and more, and
#: the main one zoomed in the sensor 28 or 35.
MAIN = (22.0, 26.0)
#: A photograph as the sensor gives it is 4:3 either way, within this: one
#: cut afterwards has its middle elsewhere.
SHAPE = 4 / 3
SHAPE_OFF = 0.01
#: Rows straightened at a time: the map of 48 MP whole is 400 MB.
STRIP = 512

_MODEL, _EXIF = 0x0110, 0x8769
_LENS, _FILM, _ZOOM = 0xA434, 0xA405, 0xA404


@dataclass(frozen=True)
class Seen:
    """What a photograph says took it: the camera's ``model``, its
    ``lens`` and the focal length as of 35 mm film (0 when not said),
    and whether it is the main camera's whole picture (``main``: not
    zoomed, not cut since), which is what a bend was measured on."""

    model: str
    lens: str = ""
    film: float = 0.0
    main: bool = False

    @property
    def bend(self) -> float | None:
        """This lens's bend (``k1``); None when it is not known, and the
        photograph stays as taken."""
        return BENDS.get(self.model) if self.main else None

    def to_json(self) -> dict[str, Any]:
        return {"model": self.model, "lens": self.lens, "film": self.film, "main": self.main}


def whole(width: int, height: int) -> bool:
    """Whether a photograph so large is the sensor's whole picture."""
    if min(width, height) <= 0:
        return False
    return abs(max(width, height) / min(width, height) - SHAPE) <= SHAPE * SHAPE_OFF


def seen(data: bytes) -> Seen | None:
    """What the photograph in ``data`` says of its camera; None when it
    names none (drawn anew on the way, or no photograph at all)."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            exif = img.getexif()
            size = img.size
            more = exif.get_ifd(_EXIF) if exif else {}
    except (OSError, ValueError, SyntaxError):
        return None
    model = str(exif.get(_MODEL) or "").strip() if exif else ""
    if not model:
        return None
    lens = str(more.get(_LENS) or "").strip()
    try:
        film = float(more.get(_FILM) or 0)
        zoom = float(more.get(_ZOOM) or 1)
    except (TypeError, ValueError, ZeroDivisionError):
        film, zoom = 0.0, 1.0
    main = MAIN[0] <= film <= MAIN[1] and zoom < 1.05 and "front" not in lens.lower()
    return Seen(model=model, lens=lens, film=film, main=main and whole(*size))


def straight(img: np.ndarray, k1: float) -> np.ndarray:
    """``img`` (rows, columns[, channels]) as a lens without the bend
    ``k1`` would have drawn it: the same size, the same middle."""
    height, width = img.shape[:2]
    half = math.hypot(width, height) / 2
    cx, cy = (width - 1) / 2, (height - 1) / 2
    out = np.empty_like(img)
    xs = (np.arange(width, dtype=np.float32) - cx) / half
    for top in range(0, height, STRIP):
        ys = (np.arange(top, min(top + STRIP, height), dtype=np.float32) - cy) / half
        bent = 1 + k1 * (xs[None, :] ** 2 + ys[:, None] ** 2)
        out[top : top + len(ys)] = cv2.remap(
            img,
            (xs[None, :] * bent * half + cx).astype(np.float32),
            (ys[:, None] * bent * half + cy).astype(np.float32),
            cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_REPLICATE,
        )
    return out


def moved(quad: Quad, width: int, height: int, k1: float) -> Quad:
    """Where the corners ``quad`` set on the photograph as taken (0–1
    across and down) are on it straightened (:func:`straight`); at its
    edge when they fell outside."""
    half = math.hypot(width, height) / 2
    out: Quad = []
    for x, y in quad:
        px, py = (x - 0.5) * width / half, (y - 0.5) * height / half
        ux, uy = px, py
        for _ in range(12):
            bent = 1 + k1 * (ux * ux + uy * uy)
            ux, uy = px / bent, py / bent
        out.append(
            (
                round(min(max(ux * half / width + 0.5, 0.0), 1.0), 5),
                round(min(max(uy * half / height + 0.5, 0.0), 1.0), 5),
            )
        )
    return out


__all__ = ["BENDS", "PHONE", "Seen", "moved", "seen", "straight", "whole"]
