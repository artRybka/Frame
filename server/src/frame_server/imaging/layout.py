"""Loading source images and laying them out on the panel canvas."""

from __future__ import annotations

import io
from enum import StrEnum
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms, ImageOps

from .color import FloatArray, linear_to_u8, u8_to_linear

PANEL_WIDTH = 2560
PANEL_HEIGHT = 1440

_SRGB_PROFILE = ImageCms.createProfile("sRGB")


class Orientation(StrEnum):
    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"


class Fit(StrEnum):
    FILL = "fill"  # cover the canvas, crop the overflow
    FIT = "fit"  # whole image visible, mat around it
    AUTO = "auto"  # fill when the crop would be small, otherwise fit


def canvas_size(orientation: Orientation) -> tuple[int, int]:
    if orientation == Orientation.PORTRAIT:
        return PANEL_HEIGHT, PANEL_WIDTH
    return PANEL_WIDTH, PANEL_HEIGHT


def load_image(source: str | Path | bytes | Image.Image) -> Image.Image:
    """Open an image, apply EXIF orientation and convert it to 8-bit sRGB.

    iPhone photos are Display P3; converting through the embedded ICC profile
    keeps their colours instead of reading P3 numbers as sRGB.
    """
    if isinstance(source, Image.Image):
        img = source
    elif isinstance(source, bytes):
        img = Image.open(io.BytesIO(source))
    else:
        img = Image.open(source)
    img = ImageOps.exif_transpose(img) or img
    icc = img.info.get("icc_profile")
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() or "transparency" in img.info else "RGB")
    if img.mode == "RGBA":
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.getchannel("A"))
        img = background
    if icc:
        try:
            src_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            converted = ImageCms.profileToProfile(
                img, src_profile, _SRGB_PROFILE, renderingIntent=ImageCms.Intent.PERCEPTUAL
            )
            img = converted or img
        except (ImageCms.PyCMSError, OSError):
            pass  # unreadable profile: assume sRGB
    return img


def resize_linear(img: Image.Image, size: tuple[int, int]) -> FloatArray:
    """Resample in linear light (gamma-correct) and return linear float RGB."""
    lin = u8_to_linear(np.asarray(img, dtype=np.uint8))
    if img.size == size:
        return lin
    channels = [
        np.asarray(
            Image.fromarray(np.ascontiguousarray(lin[..., c])).resize(
                size, Image.Resampling.LANCZOS
            ),
            dtype=np.float32,
        )
        for c in range(3)
    ]
    return np.clip(np.stack(channels, axis=-1), 0.0, 1.0)


def _crop_box(
    src: tuple[int, int], target_ratio: float, focus: tuple[float, float]
) -> tuple[int, int, int, int]:
    w, h = src
    if w / h > target_ratio:
        new_w = round(h * target_ratio)
        left = round(min(max(focus[0] * w - new_w / 2, 0), w - new_w))
        return left, 0, left + new_w, h
    new_h = round(w / target_ratio)
    top = round(min(max(focus[1] * h - new_h / 2, 0), h - new_h))
    return 0, top, w, top + new_h


def edge_color(img: Image.Image) -> tuple[int, int, int]:
    """Average colour of the image border, a natural mat colour."""
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    border = np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]])
    lin = u8_to_linear(border).mean(axis=0)
    return tuple(int(v) for v in linear_to_u8(lin))  # type: ignore[return-value]


def compose(
    img: Image.Image,
    canvas: tuple[int, int],
    *,
    fit: Fit = Fit.AUTO,
    mat_color: tuple[int, int, int] = (255, 255, 255),
    margin: float = 0.0,
    auto_crop_tolerance: float = 0.12,
    focus: tuple[float, float] = (0.5, 0.5),
) -> FloatArray:
    """Place ``img`` on a canvas; returns linear RGB of size ``canvas``.

    ``margin`` is a passe-partout width as a fraction of the shorter canvas
    side; it is applied in FIT mode only.
    """
    cw, ch = canvas
    fit, (x0, y0, w, h) = placement(img.size, canvas, fit, margin, auto_crop_tolerance)
    if fit == Fit.FILL:
        cropped = img.crop(_crop_box(img.size, cw / ch, focus))
        return resize_linear(cropped, canvas)

    placed = resize_linear(img, (w, h))
    out = np.empty((ch, cw, 3), dtype=np.float32)
    out[:] = u8_to_linear(np.array(mat_color, dtype=np.uint8))
    out[y0 : y0 + h, x0 : x0 + w] = placed
    return out


def placement(
    size: tuple[int, int],
    canvas: tuple[int, int],
    fit: Fit,
    margin: float = 0.0,
    auto_crop_tolerance: float = 0.12,
) -> tuple[Fit, tuple[int, int, int, int]]:
    """Resolve AUTO and return where the picture lands: (fit, (x, y, w, h))."""
    cw, ch = canvas
    target_ratio = cw / ch
    ratio = size[0] / size[1]
    if fit == Fit.AUTO:
        mismatch = abs(ratio - target_ratio) / max(ratio, target_ratio)
        fit = Fit.FILL if mismatch <= auto_crop_tolerance else Fit.FIT
    if fit == Fit.FILL:
        return fit, (0, 0, cw, ch)
    pad = round(min(cw, ch) * margin)
    scale = min((cw - 2 * pad) / size[0], (ch - 2 * pad) / size[1])
    w, h = max(1, round(size[0] * scale)), max(1, round(size[1] * scale))
    return fit, ((cw - w) // 2, (ch - h) // 2, w, h)


def to_panel(canvas_pixels: np.ndarray, orientation: Orientation, rotation: int) -> np.ndarray:
    """Rotate a portrait canvas into the panel's native landscape framebuffer.

    ``rotation`` is the clockwise rotation (90 or 270) the frame was hung
    with; the image is turned the other way so it appears upright.
    """
    if orientation == Orientation.LANDSCAPE:
        return canvas_pixels
    k = 1 if rotation == 90 else -1  # np.rot90 rotates counter-clockwise
    return np.ascontiguousarray(np.rot90(canvas_pixels, k=k))
