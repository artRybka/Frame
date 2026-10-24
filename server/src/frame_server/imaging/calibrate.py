"""Measuring the perceived palette from a photo of the palette chart.

The app shows ``testchart.palette_chart`` on the frame, the user photographs
it and marks the four corners of the panel. The photo is straightened with a
perspective transform, each ink patch is sampled away from its edges, and the
result is normalised so the panel's white ink becomes a neutral grey at the
reference level. Exposure and white balance of the photo therefore do not
matter; only the inks' colours relative to each other do, and those are all
the dithering needs (OKLab distances scale uniformly with exposure).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from .color import linear_to_u8, u8_to_linear
from .layout import PANEL_HEIGHT, PANEL_WIDTH, load_image
from .palette import RGB, SPECTRA6, Palette
from .testchart import palette_patches

# Straightened chart is measured at a quarter of the panel resolution.
SCALE = 4
# Sample the middle of each patch: corners clicked a little off still land inside.
INSET = 0.25
# Coefficient of variation of a patch's luminance above which it looks uneven,
# and above which it is not one patch at all (the corners are off).
UNEVEN = 0.12
MIXED = 0.3

Point = tuple[float, float]


class CalibrationError(ValueError):
    """The photo does not look like the palette chart."""


@dataclass
class InkMeasurement:
    name: str
    device: RGB
    measured: RGB  # straight from the photo
    perceived: RGB  # normalised to the reference white
    spread: float  # luminance variation inside the patch


@dataclass
class Measurement:
    inks: list[InkMeasurement]
    chart: Image.Image  # the straightened photo with the sampled areas marked
    warnings: list[str] = field(default_factory=list)

    def palette(self, base: Palette, *, name: str, source: str) -> Palette:
        return base.with_perceived(
            {ink.name: ink.perceived for ink in self.inks}, name=name, source=source
        )


def perspective_coefficients(src: list[Point], dst: list[Point]) -> tuple[float, ...]:
    """PIL PERSPECTIVE data mapping points of ``dst`` (output) to ``src`` (input)."""
    rows, rhs = [], []
    for (x, y), (u, v) in zip(dst, src, strict=True):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        rhs.extend([u, v])
    coeffs = np.linalg.solve(np.array(rows, dtype=np.float64), np.array(rhs, dtype=np.float64))
    return tuple(float(c) for c in coeffs)


def straighten(photo: Image.Image, corners: list[Point]) -> Image.Image:
    """Cut the chart out of the photo; ``corners`` are TL, TR, BR, BL as
    fractions of the photo's width and height."""
    if len(corners) != 4:
        raise CalibrationError("need the four corners of the chart")
    w, h = photo.size
    src = [(x * w, y * h) for x, y in corners]
    size = (PANEL_WIDTH // SCALE, PANEL_HEIGHT // SCALE)
    dst = [(0.0, 0.0), (size[0], 0.0), (size[0], size[1]), (0.0, size[1])]
    try:
        coeffs = perspective_coefficients(src, dst)
    except np.linalg.LinAlgError as err:
        raise CalibrationError("the corners do not form a quadrilateral") from err
    return photo.transform(size, Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BILINEAR)


def _luminance(lin: np.ndarray) -> np.ndarray:
    return lin @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


INK_NAMES = {
    "black": "czarnej",
    "white": "białej",
    "yellow": "żółtej",
    "red": "czerwonej",
    "blue": "niebieskiej",
    "green": "zielonej",
}

# What each chromatic ink must look like, whatever the light: its strongest
# channels. Used to tell a mis-marked photo from a real measurement.
_DOMINANT = {"red": (0,), "green": (1,), "blue": (2,), "yellow": (0, 1)}


def measure(
    photo: bytes | Image.Image,
    corners: list[Point],
    palette: Palette = SPECTRA6,
    reference: Palette = SPECTRA6,
) -> Measurement:
    img = load_image(photo)
    chart = straighten(img, corners)
    lin = u8_to_linear(np.asarray(chart, dtype=np.uint8))

    samples: dict[str, tuple[np.ndarray, float]] = {}
    boxes = []
    for name, (x0, y0, x1, y1) in palette_patches(palette):
        dx, dy = (x1 - x0) * INSET, (y1 - y0) * INSET
        box = tuple(round(v / SCALE) for v in (x0 + dx, y0 + dy, x1 - dx, y1 - dy))
        patch = lin[box[1] : box[3], box[0] : box[2]].reshape(-1, 3)
        luma = _luminance(patch)
        spread = float(luma.std() / max(luma.mean(), 1e-4))
        samples[name] = (np.median(patch, axis=0), spread)
        boxes.append(box)

    if "white" not in samples:
        raise CalibrationError("the palette has no white ink to normalise against")
    white = samples["white"][0]
    ref_white = u8_to_linear(np.array(reference.colors[reference.index("white")].perceived))
    gain = ref_white / np.maximum(white, 1e-4)

    inks: list[InkMeasurement] = []
    for color in palette.colors:
        value, spread = samples[color.name]
        inks.append(
            InkMeasurement(
                name=color.name,
                device=color.device,
                measured=_rgb(value),
                perceived=_rgb(np.clip(value * gain, 0.0, 1.0)),
                spread=round(spread, 3),
            )
        )

    odd = _odd_inks(samples)
    mixed = [ink.name for ink in inks if ink.spread > MIXED]
    if len(odd) >= 2 or len(mixed) >= 3:
        raise CalibrationError(
            "To nie wygląda na planszę kalibracyjną: sprawdź, czy narożniki leżą "
            "na czarnych kwadratach w rogach ramki."
        )
    warnings = [
        f"Pole {INK_NAMES.get(name, name)} farby wygląda nietypowo: sprawdź narożniki."
        for name in odd
    ]
    warnings += [
        f"Pole {INK_NAMES.get(ink.name, ink.name)} farby jest nierówno oświetlone "
        "(odblask albo cień?)."
        for ink in inks
        if ink.spread > UNEVEN
    ]
    return Measurement(inks=inks, chart=_marked(chart, boxes), warnings=warnings)


def _rgb(lin: np.ndarray) -> RGB:
    r, g, b = (int(v) for v in linear_to_u8(np.asarray(lin, dtype=np.float32)))
    return r, g, b


def _odd_inks(samples: dict[str, tuple[np.ndarray, float]]) -> list[str]:
    """Inks whose colour cannot be right in any light."""
    luma = {name: float(_luminance(v)) for name, (v, _) in samples.items()}
    problems = []
    for name, channels in _DOMINANT.items():
        if name not in samples:
            continue
        value = samples[name][0]
        others = [c for c in range(3) if c not in channels]
        if not all(value[c] > value[o] for c in channels for o in others):
            problems.append(name)
    if "black" in luma and luma["black"] > 0.35 * luma["white"]:
        problems.append("black")
    if luma["white"] < 0.6 * max(luma.values()):
        problems.append("white")
    return problems


def _marked(chart: Image.Image, boxes: list[tuple[int, ...]]) -> Image.Image:
    from PIL import ImageDraw

    out = chart.copy()
    draw = ImageDraw.Draw(out)
    for x0, y0, x1, y1 in boxes:
        draw.rectangle([x0, y0, x1, y1], outline=(255, 0, 255), width=3)
    return out
