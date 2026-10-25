"""Colour-space conversions on float32 numpy arrays (..., 3).

Working space for the pipeline is linear-light sRGB/Rec.709 primaries, D65.
OKLab (Björn Ottosson, 2020) is used where perceptual distances matter.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float32]

# Rec.709 luminance weights for linear RGB.
LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

OKLAB_M1 = np.array(
    [
        [0.4122214708, 0.5363325363, 0.0514459929],
        [0.2119034982, 0.6806995451, 0.1073969566],
        [0.0883024619, 0.2817188376, 0.6299787005],
    ],
    dtype=np.float32,
)
OKLAB_M2 = np.array(
    [
        [0.2104542553, 0.7936177850, -0.0040720468],
        [1.9779984951, -2.4285922050, 0.4505937099],
        [0.0259040371, 0.7827717662, -0.8086757660],
    ],
    dtype=np.float32,
)
_M1_INV = np.linalg.inv(OKLAB_M1).astype(np.float32)
_M2_INV = np.linalg.inv(OKLAB_M2).astype(np.float32)


def srgb_to_linear(srgb: npt.ArrayLike) -> FloatArray:
    """sRGB-encoded values in [0, 1] to linear light."""
    x = np.asarray(srgb, dtype=np.float32)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


def linear_to_srgb(linear: npt.ArrayLike) -> FloatArray:
    x = np.clip(np.asarray(linear, dtype=np.float32), 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055).astype(np.float32)


# Every 8-bit value's linear light: a lookup is much quicker than the power
# function on a large picture, and gives exactly the same numbers.
_U8_LINEAR = srgb_to_linear(np.arange(256, dtype=np.float32) / 255.0)


def u8_to_linear(rgb: npt.ArrayLike) -> FloatArray:
    if isinstance(rgb, np.ndarray) and rgb.dtype == np.uint8:
        return _U8_LINEAR[rgb]
    return srgb_to_linear(np.asarray(rgb, dtype=np.float32) / 255.0)


def linear_to_u8(linear: npt.ArrayLike) -> npt.NDArray[np.uint8]:
    return np.round(linear_to_srgb(linear) * 255.0).astype(np.uint8)


def linear_to_oklab(rgb: npt.ArrayLike) -> FloatArray:
    lms = np.asarray(rgb, dtype=np.float32) @ OKLAB_M1.T
    return (np.cbrt(lms) @ OKLAB_M2.T).astype(np.float32)


def oklab_to_linear(lab: npt.ArrayLike) -> FloatArray:
    lms = (np.asarray(lab, dtype=np.float32) @ _M2_INV.T) ** 3
    return (lms @ _M1_INV.T).astype(np.float32)


def luminance(rgb: npt.ArrayLike) -> FloatArray:
    return (np.asarray(rgb, dtype=np.float32) @ LUMA).astype(np.float32)
