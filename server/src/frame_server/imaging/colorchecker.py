"""A colour chart beside the work sets the photograph's colours ("Dodaj
własne dzieło", Mateusz 2026-11-16 22:20 UTC, a picture of a Calibrite
ColorChecker Passport: "a co gdyby przy robieniu zdjęcia, przy obrazie
dawać coś takiego?"; 22:25: "Ok, to dodajmy obsługę. Oczywiście nie jako
obowiązkową, ale opcjonalna").

The phone decides how light a photograph is and what is white in it, and
decides anew each time: the same oil portrait came out with its blacks at
0 at 19:46 and at 38 at 22:40. A ColorChecker Classic (24 patches: the
Passport's "Classic" page, the Classic Mini, the Classic itself) is paint
of known colours; photographed with the work, it says what the phone did.

:func:`find` looks for the chart in the photograph (OpenCV's detector),
reads its patches and works out the way back:

- the six grey patches give each colour channel its curve (measured light
  → the light that grey really has): white balance, exposure and what the
  phone did to the contrast, in one;
- the eighteen colours then give a 3 × 3 matrix that leaves greys alone
  (rows sum to one) and puts hue and saturation right.

What the detector calls a chart is believed only when its patches, put
back so, come out as the chart's colours (:data:`LEFT_MOST`): it finds
"charts" in a row of cows and in a print's margin too.
:func:`apply` does the same to a whole photograph, strip by strip (a
48 MP one in floats is half a gigabyte).

Without a chart nothing here does anything.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from .color import linear_to_oklab, srgb_to_linear, u8_to_linear

#: OpenCV's types are loose: uint8 RGB (H × W × 3).
Photo = NDArray[Any]
Floats = NDArray[np.float64]

#: The Classic's 24 patches in sRGB (D65), as its maker publishes them,
#: row by row from "dark skin" to "black"; the last six are the greys,
#: white first.
REFERENCE = np.array(
    [
        [115, 82, 68], [194, 150, 130], [98, 122, 157],
        [87, 108, 67], [133, 128, 177], [103, 189, 170],
        [214, 126, 44], [80, 91, 166], [193, 90, 99],
        [94, 60, 108], [157, 188, 64], [224, 163, 46],
        [56, 61, 150], [70, 148, 73], [175, 54, 60],
        [231, 199, 31], [187, 86, 149], [8, 133, 161],
        [243, 243, 242], [200, 200, 200], [160, 160, 160],
        [122, 122, 121], [85, 85, 85], [52, 52, 52],
    ],
    np.float64,
)  # fmt: skip
_REFERENCE = srgb_to_linear(REFERENCE / 255).astype(np.float64)
_GREYS = slice(18, 24)

#: The longer side the chart is looked for at. A Passport beside a
#: painting a metre wide is some 190 pixels across at this size, about
#: the least the detector finds.
SEEN_SIDE = 4032
#: How many charts the detector may name (the Passport has two pages of
#: patches): the one whose colours come out right is the chart.
CANDIDATES = 3
#: The most a chart's patches may be off their colours once put back
#: (mean OKLab distance; a real chart comes to about 0.01, what the
#: detector mistakes for one to 0.1 and more).
LEFT_MOST = 0.035
#: Each grey patch must be darker than the one before it by this much of
#: its light, measured: else it is no chart, or a lamp lies on it.
STEP = 0.9
#: The matrix is held towards "no change" by this much (of the patches'
#: summed squares): six noisy patches do not get to swing it.
HELD = 0.02
#: A colour patch this many times further off than the middle one after
#: the first fit (a glint on it, a finger) is left out of the second.
OUTLIER = 3.0
#: Rows of a photograph put right at a time.
STRIP = 256

_ENCODE = np.round(
    np.where(
        np.arange(65536) / 65535 <= 0.0031308,
        np.arange(65536) / 65535 * 12.92,
        1.055 * (np.arange(65536) / 65535) ** (1 / 2.4) - 0.055,
    )
    * 255
).astype(np.uint8)


@dataclass(frozen=True)
class Chart:
    """A colour chart found in a photograph and the way back to true
    colours it gives."""

    #: Its four corners on the photograph (0–1 across and down).
    corners: list[tuple[float, float]]
    #: The grey patches as photographed (linear light, white first), a
    #: row per colour channel.
    greys: list[list[float]]
    #: Applied to the light the curves give: rows sum to one.
    matrix: list[list[float]]
    #: How far its patches were off their colours as photographed, and
    #: how far they are once put back (mean OKLab distance).
    off: float
    left: float

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Chart:
        return cls(
            corners=[(float(x), float(y)) for x, y in data["corners"]],
            greys=[[float(v) for v in row] for row in data["greys"]],
            matrix=[[float(v) for v in row] for row in data["matrix"]],
            off=float(data["off"]),
            left=float(data["left"]),
        )

    def curves(self) -> NDArray[np.float32]:
        """Each 8-bit value's true light, per channel (3 × 256)."""
        return np.stack([_curve(np.array(row)) for row in self.greys]).astype(np.float32)


def find(photo: Photo) -> Chart | None:
    """The ColorChecker Classic in ``photo`` (uint8 RGB), or None: none
    there, or none whose patches can be put back to their colours."""
    h, w = photo.shape[:2]
    scale = min(1.0, SEEN_SIDE / max(h, w))
    seen = photo
    if scale < 1:
        seen = cv2.resize(photo, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    detector = cv2.mcc.CCheckerDetector.create()
    detector.setColorChartType(cv2.mcc.MCC24)
    try:
        if not detector.process(np.ascontiguousarray(seen[:, :, ::-1]), CANDIDATES):
            return None
        named = detector.getListColorChecker()
    except cv2.error:
        return None
    best: Chart | None = None
    for one in named:
        patches = _patches(seen, np.asarray(one.getColorCharts(), np.float64).reshape(-1, 4, 2))
        if patches is None:
            continue
        box = np.asarray(one.getBox(), np.float64).reshape(4, 2) / [seen.shape[1], seen.shape[0]]
        # The detector does not always know which way up the chart is.
        for measured in (patches, patches[::-1]):
            fitted = _fit(measured)
            if fitted is None:
                continue
            greys, matrix, off, left = fitted
            if left <= LEFT_MOST and (best is None or left < best.left):
                best = Chart(
                    corners=[(round(float(x), 5), round(float(y), 5)) for x, y in box],
                    greys=[[round(float(v), 6) for v in row] for row in greys.T],
                    matrix=[[round(float(v), 6) for v in row] for row in matrix],
                    off=round(off, 4),
                    left=round(left, 4),
                )
    return best


def apply(photo: Photo, chart: Chart) -> Photo:
    """``photo`` (uint8 RGB) in the colours the chart gives it."""
    curves = chart.curves()
    matrix = np.array(chart.matrix, np.float32)
    out = np.empty_like(photo)
    for top in range(0, photo.shape[0], STRIP):
        strip = photo[top : top + STRIP]
        light = np.stack([curves[c][strip[..., c]] for c in range(3)], axis=-1)
        light = np.clip(cv2.transform(light, matrix), 0.0, 1.0)
        out[top : top + STRIP] = _ENCODE[(light * 65535 + 0.5).astype(np.uint16)]
    return out


def _patches(seen: Photo, cells: Floats) -> Floats | None:
    """The 24 patches' light (linear, 24 × 3): the middle value of each
    patch's middle, so that a speck or a glint on it does not count."""
    if len(cells) != 24:
        return None
    h, w = seen.shape[:2]
    found = np.empty((24, 3))
    for n, cell in enumerate(cells):
        x0, y0 = np.floor(cell.min(0)).astype(int)
        x1, y1 = np.ceil(cell.max(0)).astype(int) + 1
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
        if x1 - x0 < 3 or y1 - y0 < 3:
            return None
        inside = np.zeros((y1 - y0, x1 - x0), np.uint8)
        cv2.fillConvexPoly(inside, np.round(cell - [x0, y0]).astype(np.int32), 1)
        pixels = seen[y0:y1, x0:x1][inside > 0]
        if len(pixels) < 9:
            return None
        found[n] = np.median(u8_to_linear(pixels), axis=0)
    return found


def _curve(greys: Floats) -> Floats:
    """A channel's 8-bit values → true light, from its six grey patches
    as measured (white first): straight between them, through nothing at
    all below the black one, and on above the white one as steeply as
    just below it (never less than white itself would have it)."""
    measured = greys[::-1]
    true = _REFERENCE[_GREYS, 1][::-1]
    values = u8_to_linear(np.arange(256, dtype=np.uint8)).astype(np.float64)
    out = np.interp(values, np.concatenate([[0.0], measured]), np.concatenate([[0.0], true]))
    last = (true[-1] - true[-2]) / max(measured[-1] - measured[-2], 1e-6)
    steep = max(last, true[-1] / max(measured[-1], 1e-6))
    over = values > measured[-1]
    out[over] = true[-1] + (values[over] - measured[-1]) * steep
    return np.asarray(np.clip(out, 0.0, 1.0))


def _through(curve_of: Floats, measured: Floats) -> Floats:
    """``measured`` light (… × 3) through each channel's curve, as
    :func:`apply` does it to 8-bit values but on the light itself."""
    out = np.empty_like(measured)
    values = u8_to_linear(np.arange(256, dtype=np.uint8)).astype(np.float64)
    for c in range(3):
        out[..., c] = np.interp(measured[..., c], values, curve_of[c])
    return out


def _off(light: Floats) -> Floats:
    """How far each patch's ``light`` is from its colour (OKLab)."""
    there = linear_to_oklab(np.clip(light, 0.0, 1.0)).astype(np.float64)
    true = linear_to_oklab(_REFERENCE).astype(np.float64)
    return np.asarray(np.linalg.norm(there - true, axis=1))


def _fit(measured: Floats) -> tuple[Floats, Floats, float, float] | None:
    """The grey patches (6 × 3) and the matrix that put ``measured`` (the
    patches' light in the chart's order) back to its colours, with how
    far off they were and are; None when the greys do not darken in
    step (no chart, or it lies the other way up)."""
    greys = measured[_GREYS]
    if (greys[1:] > greys[:-1] * STEP).any() or (greys[-1] <= 0).any():
        return None
    curves = np.stack([_curve(greys[:, c]) for c in range(3)])
    straight = _through(curves, measured)
    kept = np.ones(24, bool)
    matrix = np.eye(3)
    for _ in range(2):
        matrix = _matrix(straight[kept], _REFERENCE[kept])
        off = _off(straight @ matrix.T)
        colours = off[:18]
        kept = np.ones(24, bool)
        kept[:18] = colours <= max(OUTLIER * float(np.median(colours)), LEFT_MOST)
        if kept.all() or kept[:18].sum() < 12:
            break
    after = _off(straight @ matrix.T)
    return greys, matrix, float(_off(measured).mean()), float(after[kept].mean())


def _matrix(light: Floats, true: Floats) -> Floats:
    """The 3 × 3 matrix that takes the patches' ``light`` (after the
    curves) nearest their ``true`` light while leaving greys alone: each
    row sums to one, and is held towards no change (:data:`HELD`)."""
    # A row is "no change" plus two free numbers that do not move its sum.
    free = np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, -1.0]])
    moved = light @ free
    held = HELD * float((light**2).sum()) * (free.T @ free)
    matrix = np.eye(3)
    for row in range(3):
        wanted = true[:, row] - light[:, row]
        matrix[row] += free @ np.linalg.solve(moved.T @ moved + held, moved.T @ wanted)
    return matrix


__all__ = ["Chart", "apply", "find"]
