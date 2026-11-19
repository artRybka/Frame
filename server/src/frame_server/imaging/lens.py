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
camera, or another, or the same one zoomed, stays as it was taken.

The camera knows its own lens, too (Mateusz 2026-11-19 08:09 UTC:
"Korekta obiektywu - a nie ma natywnego rozwiązania od Apple w tym
zakresie?"). Apple straightens no photograph of the main camera itself,
but gives with one what it would be straightened by
(``AVCameraCalibrationData.lensDistortionLookupTable``: how much further
from the lens's middle a point of the straight picture is in the
photograph, at radii evenly from that middle to the photograph's farthest
corner; of that very photograph, at the distance it was focused). The
app sends it with a scan's first photograph, and where it says what the
measurement of that lens says (:data:`AGREES`) the photograph is
straightened by it (:class:`Bend`). Of a lens that was not measured it
is noted and not gone by, until it has been seen to say of his what the
measurement does (:data:`ALONE`)."""

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
#: The camera's own table is gone by where the one radial term nearest
#: it (:func:`like`) is within this share of the measured one: it is of
#: the very photograph, the measurement of a few. Further off, one of the
#: two is not what it is taken for, and the measurement was seen to make
#: his frames' sides straight.
AGREES = 0.35
#: Whether the camera's table is gone by for a lens that was not
#: measured (another phone). Not before his own scans have shown that it
#: says what the measurement says: read wrongly, it would bend a work
#: twice over, and nothing here could tell.
ALONE = False
#: A table is the camera's when it has so many values at least and
#: none says more than this (a main camera's are within a few percent),
#: about a middle no further than this from the photograph's.
TABLE_LEAST = 8
TABLE_MOST = 512
TABLE_FAR = 0.2
CENTRE_OFF = 0.1

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


@dataclass(frozen=True)
class Bend:
    """How a lens bends what it draws: a point of the straight picture
    is in the photograph further from the lens's middle (or nearer: a
    barrel) by a share that grows with its distance from it.

    Either the one radial term that was measured (``k1``: about the
    photograph's middle, ``k1 * |u|²`` at ``u`` half-diagonals from it),
    or the camera's own ``table`` of the very photograph: that share at
    radii evenly from the lens's middle (``centre``, 0–1 across and down
    the photograph) to the photograph's farthest corner from it."""

    k1: float = 0.0
    table: tuple[float, ...] = ()
    centre: tuple[float, float] = (0.5, 0.5)

    def __bool__(self) -> bool:
        return bool(self.k1) or any(self.table)

    def to_json(self) -> Any:
        """As a scan notes what its work was straightened by: the one
        number, as before there were tables, or the table."""
        if not self.table:
            return self.k1
        return {"table": list(self.table), "centre": list(self.centre)}

    @classmethod
    def from_json(cls, noted: Any) -> Bend | None:
        """What a scan noted; None for what is neither."""
        if isinstance(noted, int | float) and not isinstance(noted, bool):
            return cls(k1=float(noted))
        if isinstance(noted, dict):
            found = table(noted.get("table"), noted.get("centre"))
            return cls(table=found[0], centre=found[1]) if found is not None else None
        return None

    def _middle(self, width: int, height: int) -> tuple[float, float, float]:
        """The lens's middle in the photograph's pixels, and the radius
        there at which its distances are 1."""
        if not self.table:
            return (width - 1) / 2, (height - 1) / 2, math.hypot(width, height) / 2
        cx, cy = self.centre[0] * width, self.centre[1] * height
        reach = math.hypot(max(cx, width - cx), max(cy, height - cy))
        return cx - 0.5, cy - 0.5, reach

    def by(self, radius: Any) -> Any:
        """The share at ``radius`` (1 at the half-diagonal, or where the
        table ends; an array or a number)."""
        if not self.table:
            return self.k1 * radius * radius
        last = len(self.table) - 1
        return np.interp(np.asarray(radius) * last, np.arange(last + 1), self.table)


def table(values: Any, centre: Any) -> tuple[tuple[float, ...], tuple[float, float]] | None:
    """What the phone sent as its camera's table and the lens's middle,
    when they are that (:data:`TABLE_LEAST`…); None otherwise."""
    try:
        told = tuple(float(v) for v in values)
        x, y = (float(v) for v in centre)
    except (TypeError, ValueError):
        return None
    if not TABLE_LEAST <= len(told) <= TABLE_MOST:
        return None
    if not all(math.isfinite(v) and abs(v) <= TABLE_FAR for v in told):
        return None
    if not (abs(x - 0.5) <= CENTRE_OFF and abs(y - 0.5) <= CENTRE_OFF):
        return None
    return told, (round(x, 5), round(y, 5))


def like(bend: Bend) -> float:
    """The one radial term (``k1``) nearest what ``bend`` says of a
    photograph as the sensor gives it (4:3), over all of it: what a
    table is held against a measurement by, and said as in the log."""
    if not bend.table:
        return bend.k1
    width, height = 4.0, 3.0
    half = math.hypot(width, height) / 2
    cx, cy = bend.centre[0] * width, bend.centre[1] * height
    reach = math.hypot(max(cx, width - cx), max(cy, height - cy))
    # Rings of the same width count by how much of the picture they are.
    radius = (np.arange(200) + 0.5) / 200 * reach
    u = radius / half
    share = np.asarray(bend.by(radius / reach), float)
    return float((share * u**3).sum() / (u**5).sum())


def chosen(measured: float | None, values: Any = None, centre: Any = None) -> Bend | None:
    """What a photograph is straightened by: its camera's own table
    (``values`` about ``centre``, as the phone sent them) where it says
    what the measurement of that lens says, else the measurement
    (``measured``, None for a lens that was not); None when it is to stay
    as taken."""
    found = table(values, centre)
    own = Bend(table=found[0], centre=found[1]) if found is not None else None
    if measured is None:
        return own if ALONE and own else None
    if own and abs(like(own) - measured) <= AGREES * abs(measured):
        return own
    return Bend(k1=measured)


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


def straight(img: np.ndarray, bend: Bend | float) -> np.ndarray:
    """``img`` (rows, columns[, channels]) as a lens without ``bend``
    (one measured term ``k1``, or a :class:`Bend`) would have drawn it:
    the same size, the same middle."""
    if not isinstance(bend, Bend):
        bend = Bend(k1=float(bend))
    height, width = img.shape[:2]
    cx, cy, half = bend._middle(width, height)
    out = np.empty_like(img)
    xs = (np.arange(width, dtype=np.float32) - cx) / half
    for top in range(0, height, STRIP):
        ys = (np.arange(top, min(top + STRIP, height), dtype=np.float32) - cy) / half
        if bend.table:
            share = bend.by(np.hypot(xs[None, :], ys[:, None])).astype(np.float32)
            bent = 1 + share
        else:
            bent = 1 + bend.k1 * (xs[None, :] ** 2 + ys[:, None] ** 2)
        out[top : top + len(ys)] = cv2.remap(
            img,
            (xs[None, :] * bent * half + cx).astype(np.float32),
            (ys[:, None] * bent * half + cy).astype(np.float32),
            cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_REPLICATE,
        )
    return out


def moved(quad: Quad, width: int, height: int, bend: Bend | float) -> Quad:
    """Where the corners ``quad`` set on the photograph as taken (0–1
    across and down) are on it straightened (:func:`straight`); at its
    edge when they fell outside."""
    if not isinstance(bend, Bend):
        bend = Bend(k1=float(bend))
    if not bend.table:
        half = math.hypot(width, height) / 2
        k1 = bend.k1
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
    cx, cy, reach = bend._middle(width, height)
    there: Quad = []
    for x, y in quad:
        # (A corner is said from the photograph's edges, a pixel's
        # middle half a pixel in.)
        px, py = (x * width - 0.5 - cx) / reach, (y * height - 0.5 - cy) / reach
        ux, uy = px, py
        for _ in range(12):
            bent = 1 + float(bend.by(math.hypot(ux, uy)))
            ux, uy = px / bent, py / bent
        there.append(
            (
                round(min(max((ux * reach + cx + 0.5) / width, 0.0), 1.0), 5),
                round(min(max((uy * reach + cy + 0.5) / height, 0.0), 1.0), 5),
            )
        )
    return there


__all__ = [
    "BENDS",
    "PHONE",
    "Bend",
    "Seen",
    "chosen",
    "like",
    "moved",
    "seen",
    "straight",
    "table",
    "whole",
]
