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

The chart sets the colours, and how light the photograph is only by
half. His first scan with a real chart, a small dark oil (2026-11-18
18:13 UTC: "Wyszło trochę blado i mdło. Sprawdzisz?"): the chart was
read well, and the photograph came out as the patches truly are, light
for light. That is a measurement and no picture: the chart's black is a
dark grey (52 of 255), the phone's contrast was undone, the wall beside
the work went from 218 to 190, and the chart leant on the canvas in more
light than the work had. Offered the chart's colours with the lightness
and contrast the phone gave its greys, he asked for the middle (18:49:
"A nie lepiej to odrobinę wyważyć?"; shown the three, 19:13: "Wyważone,
pół na pół"): blacks deeper than the measurement's, lights not as far
gone as the phone's. So white balance and hues are the chart's, and each
light is written part of the way from what it truly is to what the phone
made of a grey that light (:meth:`Chart.lit`, :data:`PHONE`).

Half way it was, to 2026-11-19. Then his e-paper frame, scanned with the
chart on its screen (2026-11-19 11:01 UTC: "Mam też wrażenie że skan
pomimo karty koloru jest za mało nasycony? Szczególnie widzę to po
zieleniach."). The chart's own patches were right in it, a tenth more
saturated than they are; the frame's green is a quarter of the chart's
green, and its white a grey. Shown the scan half way, three quarters of
the way and as the phone lit it, he took the second (11:37 UTC: "tak,
wolę mocniej - 3/4 w stronę telefonu."). The photographs a scan keeps
note how they were lit (:data:`LOOK`), and are lit as now when the work
is made again (:func:`relit`).

A photograph does not always hold the whole chart: in a dim room its
black patch is written as no light at all, under a lamp its white as the
photograph's top (his scans of 2026-11-18 21:11–21:20 UTC: "Dlaczego
karta kolorów nie jest tu wykrywana?", "Podobny problem."). The greys
that still say something give the curves (:func:`_usable`), and what is
at a channel's top is kept as grey as the other two have it
(:func:`_at_top`).

Without a chart nothing here does anything.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from .color import linear_to_oklab, srgb_to_linear, u8_to_linear

log = logging.getLogger(__name__)

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
#: A patch with less light than this in a channel (about 6 of 255) has
#: none that can be told from nothing, and one with more than this (250
#: of 255) is at the photograph's top: what it truly is, the photograph
#: no longer says.
DARKEST = 0.002
BRIGHTEST = 0.956
#: The fewest grey patches, one after another, that still give curves,
#: and the fewest colour patches that still give a matrix.
GREYS_LEAST = 4
COLOURS_LEAST = 8
#: The matrix is held towards "no change" by this much (of the patches'
#: summed squares): six noisy patches do not get to swing it.
HELD = 0.02
#: A colour patch this many times further off than the middle one after
#: the first fit (a glint on it, a finger) is left out of the second.
OUTLIER = 3.0
#: Rows of a photograph put right at a time.
STRIP = 256
#: How a photograph kept beside its chart is lit: 0 as the patches truly
#: are (to 1.145.243), 1 half way from that to how the phone had its
#: greys (to 2026-11-19), 2 three quarters of the way.
LOOK = 2
#: How a chart is read: 1 to 1.145.244 (all six greys in step, each
#: with light in it), 2 with the greys at the photograph's ends left out
#: (:func:`_usable`). A kept scan no chart was read in is looked at once
#: more when this is raised.
READING = 2
#: How much of the way: 0 is the measurement, 1 the phone's lightness
#: and contrast.
PHONE = 0.75
#: How much of the way each :data:`LOOK` went.
_WENT = (0.0, 0.5, PHONE)
#: How light a colour is (linear light).
_LUMA = np.array([0.2126, 0.7152, 0.0722])

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
    #: How the photographs kept beside it are lit (:data:`LOOK`).
    look: int = LOOK
    #: The grey patches the curves are made of, from this one (0, white)
    #: to this one (5, black): the others said nothing (:func:`_usable`).
    lightest: int = 0
    darkest: int = 5

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
            # One noted before the photographs were lit as the phone had them.
            look=int(data.get("look") or 0),
            lightest=int(data.get("lightest") or 0),
            darkest=5 if data.get("darkest") is None else int(data["darkest"]),
        )

    def curves(self) -> NDArray[np.float32]:
        """Each 8-bit value's true light, per channel (3 × 256)."""
        return _curves(np.array(self.greys).T, self.lightest, self.darkest).astype(np.float32)

    def lit(self, phone_: float = PHONE) -> NDArray[np.uint8]:
        """Each true light (of 65536, any channel) as it is written: its
        8-bit value, :data:`PHONE` of the way (``phone_``) from what that
        light is to what the photograph had a grey of that light at. That
        is straight between the greys that count, through nothing below
        the darkest one, and on above the lightest one as just below it."""
        use = slice(self.lightest, self.darkest + 1)
        seen = (np.array(self.greys).T[use] @ _LUMA)[::-1]
        true = _REFERENCE[_GREYS, 1][use][::-1]
        light = np.arange(65536) / 65535
        out = np.interp(light, np.concatenate([[0.0], true]), np.concatenate([[0.0], seen]))
        over = light > true[-1]
        steep = (seen[-1] - seen[-2]) / (true[-1] - true[-2])
        out[over] = seen[-1] + (light[over] - true[-1]) * steep
        phone = _ENCODE[(np.clip(out, 0.0, 1.0) * 65535 + 0.5).astype(np.uint16)]
        true_ = _ENCODE.astype(np.float64)
        return np.asarray(np.round(true_ + (phone - true_) * phone_), np.uint8)


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
    nearest: float | None = None
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
            greys, matrix, off, left, (lightest, darkest) = fitted
            nearest = left if nearest is None else min(nearest, left)
            if left <= LEFT_MOST and (best is None or left < best.left):
                best = Chart(
                    corners=[(round(float(x), 5), round(float(y), 5)) for x, y in box],
                    greys=[[round(float(v), 6) for v in row] for row in greys.T],
                    matrix=[[round(float(v), 6) for v in row] for row in matrix],
                    off=round(off, 4),
                    left=round(left, 4),
                    lightest=lightest,
                    darkest=darkest,
                )
    if best is None and named:
        # Why a chart he put beside the work was not taken is asked later.
        if nearest is None:
            log.info("colour chart seen, not read: its greys do not darken in step")
        else:
            log.info("colour chart seen, not read: its colours stay %.3f off", nearest)
    return best


def apply(photo: Photo, chart: Chart) -> Photo:
    """``photo`` (uint8 RGB) in the colours the chart gives it, most of
    the way as light and as steep as the phone had it (:meth:`Chart.lit`)."""
    return _put(photo, chart, chart.lit())


#: What begins a chart's :func:`tables`: raised when what follows changes,
#: and a core that knows another leaves the scan to the server.
TABLES = b"FRAMECH1"


def tables(chart: Chart) -> bytes:
    """What :func:`apply` goes by, for the phone's core to put its own
    photographs in the chart's colours before it makes the scan of them
    (``core/scan`` ``frame_scan_chart_file``; Mateusz 2026-11-19 08:09
    UTC: "Czy iPhone będzie także obsługiwać kartę koloru"): after
    :data:`TABLES` each channel's curve (3 × 256 float32), each 8-bit
    value's own light (256 float32), the matrix (3 × 3 float32), whether
    the curves end below the photograph's top (:func:`_at_top`; uint32)
    and where in each channel (3 float64), then how each light is written
    (:meth:`Chart.lit`, 65536 bytes). The numbers the low end first."""
    values = u8_to_linear(np.arange(256, dtype=np.uint8))
    return b"".join(
        [
            TABLES,
            chart.curves().astype("<f4").tobytes(),
            values.astype("<f4").tobytes(),
            np.array(chart.matrix, "<f4").tobytes(),
            np.array([1 if chart.lightest else 0], "<u4").tobytes(),
            np.array(chart.greys, "<f8").T[chart.lightest].tobytes(),
            chart.lit().tobytes(),
        ]
    )


def true(photo: Photo, chart: Chart) -> Photo:
    """``photo`` (uint8 RGB) as the chart's patches truly are, light for
    light: what :func:`apply` gave to 1.145.243."""
    return _put(photo, chart, _ENCODE)


def relit(photo: Photo, chart: Chart) -> Photo:
    """A photograph kept as an earlier release lit it (``chart.look``:
    as :func:`true` gave it, or half way to the phone), as :func:`apply`
    gives it now. Each of its 8-bit values is the light that was written
    so then (the middle one of those that were), written as now; a value
    no light was written as is as the ones about it."""
    was = np.maximum.accumulate(chart.lit(_WENT[min(chart.look, LOOK)]))
    values = np.arange(256)
    low = np.searchsorted(was, values, "left")
    high = np.searchsorted(was, values, "right")
    written = high > low
    light = np.interp(values, values[written], ((low + high - 1) / 2)[written])
    return np.asarray(chart.lit()[np.round(light).astype(np.uint16)][photo])


def _put(photo: Photo, chart: Chart, encode: NDArray[np.uint8]) -> Photo:
    """``photo`` in the chart's true light, each such light written as
    ``encode`` has it (65536 values)."""
    curves = chart.curves()
    matrix = np.array(chart.matrix, np.float32)
    values = u8_to_linear(np.arange(256, dtype=np.uint8)).astype(np.float32)
    greys = np.array(chart.greys).T
    out = np.empty_like(photo)
    for top in range(0, photo.shape[0], STRIP):
        strip = photo[top : top + STRIP]
        light = np.stack([curves[c][strip[..., c]] for c in range(3)], axis=-1)
        if chart.lightest:
            light = _at_top(light, values[strip], greys[chart.lightest])
        light = np.clip(cv2.transform(light, matrix), 0.0, 1.0)
        out[top : top + STRIP] = encode[(light * 65535 + 0.5).astype(np.uint16)]
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


def _curve(greys: Floats, true: Floats) -> Floats:
    """A channel's 8-bit values → true light, from its grey patches as
    measured and the light they ``true``-ly have (lightest first):
    straight between them, through nothing at all below the darkest one,
    and on above the lightest one as steeply as just below it (never less
    than that grey itself would have it)."""
    measured = greys[::-1]
    true = true[::-1]
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


def _usable(greys: Floats) -> tuple[int, int] | None:
    """The grey patches (6 × 3, white first) that say what the phone did,
    as the lightest and the darkest of them; None when they do not darken
    in step (no chart, or it lies the other way up) or too few are left.

    The phone writes what is too dark as no light at all and what is too
    light as its top, and a chart caught there was no chart to 1.145.244
    (Mateusz 2026-11-18 21:14 UTC, a chart on the frame in a dim room,
    its black patch at 0, 0, 0: "Dlaczego karta kolorów nie jest tu
    wykrywana?"; 21:20, one on a table under a lamp, its white and the
    grey after it both at blue's top: "Podobny problem."). A black patch
    without light never counts: three values of 255 cannot be spread
    over all there is below the chart's black. Light patches go only
    when the six are not in step as they are (a white at a channel's top
    that still stands clear of the next grey is the photograph's white
    as it always was): then those at a channel's top go, and at least
    :data:`GREYS_LEAST` in step must be left.

    A channel that still tells the lighter greys apart does not get to
    keep them: the phone presses the lights together (his table lamp:
    white at 244 of 255 in red, the next grey at 237), and a curve that
    steep made the yellow-green patch, 246 in green, half as light again
    as it is."""
    darkest = 5
    while darkest >= 0 and (greys[darkest] < DARKEST).any():
        darkest -= 1
    lightest = 0
    if (greys[1 : darkest + 1] > greys[:darkest] * STEP).any():
        while lightest < darkest and (greys[lightest] > BRIGHTEST).any():
            lightest += 1
    run = greys[lightest : darkest + 1]
    if len(run) < GREYS_LEAST or (run[1:] > run[:-1] * STEP).any():
        return None
    return lightest, darkest


def _curves(greys: Floats, lightest: int, darkest: int) -> Floats:
    """Each channel's curve (3 × 256) from the grey patches that count
    (``greys``: 6 × 3 as measured, white first)."""
    use = slice(lightest, darkest + 1)
    true = _REFERENCE[_GREYS, 1][use]
    return np.stack([_curve(greys[use, c], true) for c in range(3)])


def _at_top(light: NDArray[Any], measured: NDArray[Any], lightest: Floats) -> NDArray[Any]:
    """``light`` (… × 3, what the curves make of ``measured``) past the
    ``lightest`` grey the curves have (as measured, a value per channel):
    the photograph's top is near there, where a channel no longer says
    what it saw. What is there is taken to be at least as light as the
    lighter of the other two channels say, the more so the nearer the
    top: the chart's own white, at blue's top under his table lamp, came
    out cream (blue 0.43, red 0.53) and is neutral so."""
    out = light.copy()
    for c in range(3):
        start = float(lightest[c])
        near = np.clip((measured[..., c] - start) / max(1.0 - start, 1e-6), 0.0, 1.0)
        others = np.maximum(light[..., (c + 1) % 3], light[..., (c + 2) % 3])
        out[..., c] = light[..., c] + near * np.maximum(others - light[..., c], 0.0)
    return out


def _fit(measured: Floats) -> tuple[Floats, Floats, float, float, tuple[int, int]] | None:
    """The grey patches (6 × 3) and the matrix that put ``measured`` (the
    patches' light in the chart's order) back to its colours, with how
    far off they were and are and which greys counted (:func:`_usable`);
    None when the greys say nothing. A colour patch at the photograph's
    top in a channel is not what the chart has there: it is left out of
    the matrix and of how far off the chart is, as are the greys that do
    not count. (One without light in a channel stays: in a dim room that
    is most of them, a little too dark, and what is far off goes as an
    outlier.)"""
    greys = measured[_GREYS]
    usable = _usable(greys)
    if usable is None:
        return None
    lightest, darkest = usable
    straight = _through(_curves(greys, lightest, darkest), measured)
    if lightest:
        straight = _at_top(straight, measured, greys[lightest])
    told = (measured <= BRIGHTEST).all(1)
    told[18:] = False
    told[18 + lightest : 18 + darkest + 1] = True
    if told[:18].sum() < COLOURS_LEAST:
        return None
    kept = told.copy()
    matrix = np.eye(3)
    for _ in range(2):
        matrix = _matrix(straight[kept], _REFERENCE[kept])
        off = _off(straight @ matrix.T)
        colours = off[:18]
        kept = told.copy()
        kept[:18] &= colours <= max(OUTLIER * float(np.median(colours[told[:18]])), LEFT_MOST)
        if (kept == told).all() or kept[:18].sum() < 12:
            break
    after = _off(straight @ matrix.T)
    return greys, matrix, float(_off(measured).mean()), float(after[kept].mean()), usable


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


__all__ = ["LOOK", "READING", "Chart", "apply", "find", "relit", "true"]
