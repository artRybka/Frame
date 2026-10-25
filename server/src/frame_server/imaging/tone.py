"""Tone and gamut mapping from a display-referred image onto the panel.

The panel's white is a light grey and its inks are dark and muted, so a
source image has to be squeezed into a much smaller colour volume before
dithering. All curves operate on OKLab lightness L in [0, 1]; chroma is
handled separately so hue is preserved.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from .color import FloatArray, linear_to_oklab, oklab_to_linear
from .gamut import compress_chroma
from .palette import Palette


class ToneSettings(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    exposure: float = Field(0.0, ge=-3, le=3, description="EV stops applied in linear light")
    gamma: float = Field(1.0, gt=0.2, le=3, description=">1 brightens midtones")
    shadows: float = Field(0.0, ge=-1, le=1, description=">0 lifts shadow detail")
    highlights: float = Field(0.0, ge=-1, le=1, description=">0 recovers highlight detail")
    contrast: float = Field(1.0, gt=0.2, le=3, description="S-curve strength, 1 = neutral")
    saturation: float = Field(1.0, ge=0, le=3)
    compress_range: bool = Field(
        True, description="Map black..white onto the panel's real black..white"
    )
    gamut_knee: float = Field(
        0.75,
        ge=0.0,
        le=1.0,
        description="Fraction of the panel gamut boundary where chroma roll-off starts; 1 = clip",
    )
    # Passthrough only (the panel dithers): corrections for its own colour mapping.
    white_point: float = Field(
        1.0, ge=0.5, le=1.0, description="Source lightness that becomes paper white"
    )
    highlight_chroma: float = Field(
        1.0,
        ge=0.0,
        le=2.0,
        description="Chroma factor in the light parts; <1 keeps the panel from"
        " dotting them with blue and green",
    )
    tint: float = Field(0.0, ge=-0.05, le=0.05, description="OKLab a shift: >0 magenta, <0 green")
    temperature: float = Field(0.0, ge=-0.05, le=0.05, description="OKLab b shift: >0 warmer")
    tint_region: Literal["all", "highlights", "neutral"] = Field(
        "all", description="Where tint and temperature apply"
    )


# Light parts for highlight_chroma and tint_region="highlights": a ramp in OKLab L.
HIGHLIGHT_RAMP = (0.55, 0.9)
# tint_region="neutral": full shift on greys, fading out by this chroma.
NEUTRAL_CHROMA = 0.06


def _bump(x: FloatArray, peak: float) -> FloatArray:
    """Smooth bump that is 0 at x=0 and x=1, with maximum 1 at ``peak``."""
    if peak < 0.5:  # L (1-L)^2, peak at 1/3
        return (27 / 4) * x * (1 - x) ** 2
    return (27 / 4) * x**2 * (1 - x)  # peak at 2/3


def _s_curve(x: FloatArray, strength: float) -> FloatArray:
    lo = 0.5 * (2 * x) ** strength
    hi = 1 - 0.5 * (2 * (1 - x)) ** strength
    return np.where(x < 0.5, lo, hi)


def tone_curve(lightness: FloatArray, s: ToneSettings) -> FloatArray:
    x = np.clip(lightness, 0.0, 1.0)
    if s.gamma != 1.0:
        x = x ** (1.0 / s.gamma)
    if s.shadows:
        x = x + 0.25 * s.shadows * _bump(x, 1 / 3)
    if s.highlights:
        x = x - 0.25 * s.highlights * _bump(x, 2 / 3)
    x = np.clip(x, 0.0, 1.0)
    if s.contrast != 1.0:
        x = _s_curve(x, s.contrast)
    return x.astype(np.float32)


def map_to_panel(linear: FloatArray, palette: Palette, s: ToneSettings) -> FloatArray:
    """Source linear RGB (white = 1) -> target linear RGB in perceived panel space."""
    rgb = linear * np.float32(2.0**s.exposure) if s.exposure else linear
    lab = linear_to_oklab(np.clip(rgb, 0.0, None))
    light = tone_curve(lab[..., 0], s)

    if s.compress_range:
        lo, hi = palette.neutral_range()
        light = lo + (hi - lo) * light

    mapped = np.stack([light, lab[..., 1] * s.saturation, lab[..., 2] * s.saturation], axis=-1)
    mapped = compress_chroma(mapped, palette, s.gamut_knee)
    out = oklab_to_linear(mapped)
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def _smoothstep(lo: float, hi: float, x: FloatArray) -> FloatArray:
    t = np.clip((x - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def grade_for_panel(linear: FloatArray, s: ToneSettings) -> FloatArray:
    """Passthrough: adjust the picture, leave range, gamut and dithering to the panel.

    Tuned by eye on the EM32DX (docs/EXPERIMENTS.md, E14): its own mapping
    turns light, slightly coloured areas into blue and green dots, and greys
    lean green, so light parts are pulled to paper white and muted, and greys
    can be nudged the other way.
    """
    rgb = linear * np.float32(2.0**s.exposure) if s.exposure else linear
    lab = linear_to_oklab(np.clip(rgb, 0.0, None))
    light = tone_curve(np.clip(lab[..., 0] / s.white_point, 0.0, 1.0), s)
    a, b = lab[..., 1] * s.saturation, lab[..., 2] * s.saturation
    highlight = _smoothstep(*HIGHLIGHT_RAMP, light)
    if s.highlight_chroma != 1.0:
        factor = 1.0 + (s.highlight_chroma - 1.0) * highlight
        a, b = a * factor, b * factor
    if s.tint or s.temperature:
        if s.tint_region == "highlights":
            weight = highlight
        elif s.tint_region == "neutral":
            weight = np.clip(1.0 - np.hypot(a, b) / NEUTRAL_CHROMA, 0.0, 1.0)
        else:
            weight = np.ones_like(light)
        a, b = a + s.tint * weight, b + s.temperature * weight
    out = oklab_to_linear(np.stack([light, a, b], axis=-1))
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def compensation_matrix(palette: Palette) -> FloatArray:
    """Affine map (4x3) from nominal ink RGB to perceived ink RGB, linear light.

    Least-squares fit over the palette colours. Used for the "compensate"
    strategy, where we leave dithering to the panel but pre-distort the image
    so a ditherer that believes the nominal colours lands on our target.
    """
    # Device values are 0/255 per channel, so they are the same in any encoding.
    nominal = palette.device_u8().astype(np.float32) / 255.0
    perceived = palette.perceived_linear()
    design = np.hstack([nominal, np.ones((len(palette), 1), dtype=np.float32)])
    solution, *_ = np.linalg.lstsq(design, perceived, rcond=None)
    return solution.astype(np.float32)


def precompensate(target: FloatArray, palette: Palette) -> FloatArray:
    """Invert compensation_matrix: the nominal-space image that maps to ``target``."""
    m = compensation_matrix(palette)
    linear_part, offset = m[:3], m[3]
    inv = np.linalg.inv(linear_part)
    nominal = (target - offset) @ inv
    return np.clip(nominal, 0.0, 1.0).astype(np.float32)
