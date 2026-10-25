"""Small image filters implemented with numpy only."""

from __future__ import annotations

import numpy as np

from .bands import by_rows
from .color import FloatArray, linear_to_oklab, oklab_to_linear


def gaussian_kernel(sigma: float) -> np.ndarray:
    radius = max(1, int(3 * sigma + 0.5))
    x = np.arange(-radius, radius + 1, dtype=np.float32)
    k = np.exp(-(x**2) / (2 * sigma**2))
    return (k / k.sum()).astype(np.float32)


def gaussian_blur(channel: FloatArray, sigma: float) -> FloatArray:
    """Separable Gaussian blur of a 2-D array with edge padding."""
    k = gaussian_kernel(sigma)
    r = len(k) // 2
    padded = np.pad(channel, ((0, 0), (r, r)), mode="edge")
    tmp = sum(k[i] * padded[:, i : i + channel.shape[1]] for i in range(len(k)))
    padded = np.pad(tmp, ((r, r), (0, 0)), mode="edge")
    return sum(k[i] * padded[i : i + channel.shape[0]] for i in range(len(k))).astype(np.float32)


def sharpen(linear: FloatArray, amount: float, sigma: float = 1.2) -> FloatArray:
    """Unsharp mask on OKLab lightness only, so colours do not fringe.

    Dithering scatters fine detail; a little sharpening beforehand keeps
    edges and texture readable on the panel.
    """
    if amount <= 0:
        return linear
    lab = by_rows(lambda part: linear_to_oklab(np.clip(part, 0.0, None)), linear)
    light = lab[..., 0]
    lab[..., 0] = np.clip(light + amount * (light - gaussian_blur(light, sigma)), 0.0, 1.0)
    return by_rows(lambda part: np.clip(oklab_to_linear(part), 0.0, 1.0).astype(np.float32), lab)
