"""Loading source images and laying them out on the panel canvas."""

from __future__ import annotations

import io
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms, ImageOps
from pydantic import BaseModel, Field

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
    DETAILS = "details"  # whole image edge to edge, two close-ups beside it
    AUTO = "auto"  # fill when the crop would be small, details when very different, else fit


class Crop(BaseModel):
    """Which part of a picture a window shows: its centre, as fractions of the
    picture, and the zoom (1 = the largest part of the window's shape)."""

    x: float = Field(0.5, ge=0, le=1)
    y: float = Field(0.5, ge=0, le=1)
    zoom: float = Field(1.0, ge=1, le=8)


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


def crop_box(size: tuple[int, int], aspect: float, crop: Crop) -> tuple[float, float, float, float]:
    """The part of a picture of ``size`` shown in a window of ``aspect``."""
    w, h = size
    bw, bh = (h * aspect, float(h)) if w / h > aspect else (float(w), w / aspect)
    bw, bh = bw / crop.zoom, bh / crop.zoom
    cx = min(max(crop.x * w, bw / 2), w - bw / 2)
    cy = min(max(crop.y * h, bh / 2), h - bh / 2)
    return cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2


def edge_color(img: Image.Image) -> tuple[int, int, int]:
    """Average colour of the image border, a natural mat colour."""
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    border = np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]])
    lin = u8_to_linear(border).mean(axis=0)
    return tuple(int(v) for v in linear_to_u8(lin))  # type: ignore[return-value]


# -- Planning the canvas ------------------------------------------------------

AUTO_CROP_TOLERANCE = 0.12  # aspect mismatch AUTO still fills
DETAILS_ROOM = 0.35  # canvas share beside the picture from which AUTO shows details
DETAILS_MIN_ROOM = 0.2  # below this even an explicit DETAILS falls back to FIT
DETAIL_ZOOM = 2.2  # close-ups: this much closer than the window-shaped whole
DETAIL_MAX_UPSCALE = 1.6  # ... unless the source has too few pixels for it

Rect = tuple[int, int, int, int]  # x, y, w, h
# Picks crops automatically: (window aspect, zoom, how many) -> crops.
AutoCrop = Callable[[float, float, int], list[Crop]]


@dataclass(frozen=True)
class Window:
    """A cut-out of the canvas showing (part of) the picture."""

    rect: Rect
    box: tuple[float, float, float, float]  # part of the picture shown, in its pixels
    role: str  # "picture" (all of it), "fill" or "detail"
    crop: Crop | None = None  # for "fill" and "detail"

    @property
    def aspect(self) -> float:
        return self.rect[2] / self.rect[3]


@dataclass(frozen=True)
class Plan:
    fit: Fit  # resolved: FIT, FILL or DETAILS
    canvas: tuple[int, int]
    windows: list[Window]
    caption_at: tuple[int, int, int] | None = None  # right x, top y, max width

    def mat_mask(self) -> np.ndarray:
        """Canvas pixels not covered by a window: the passe-partout."""
        cw, ch = self.canvas
        mask = np.ones((ch, cw), dtype=bool)
        for x, y, w, h in (window.rect for window in self.windows):
            mask[y : y + h, x : x + w] = False
        return mask


def caption_size(canvas: tuple[int, int]) -> int:
    return max(18, round(min(canvas) * 0.02))


def caption_band(canvas: tuple[int, int]) -> int:
    """Height of the strip a caption needs below a picture."""
    return round(caption_size(canvas) * 2.6)


def _room_beside(size: tuple[int, int], canvas: tuple[int, int]) -> float:
    """Canvas share left over when the picture spans the full height (or width)."""
    (iw, ih), (cw, ch) = size, canvas
    ratio = iw / ih
    if ratio < cw / ch:
        return 1 - ch * ratio / cw
    return 1 - cw / ratio / ch


def resolve_fit(size: tuple[int, int], canvas: tuple[int, int], fit: Fit) -> Fit:
    ratio, target = size[0] / size[1], canvas[0] / canvas[1]
    room = _room_beside(size, canvas)
    if fit == Fit.AUTO:
        if abs(ratio - target) / max(ratio, target) <= AUTO_CROP_TOLERANCE:
            return Fit.FILL
        return Fit.DETAILS if room >= DETAILS_ROOM else Fit.FIT
    if fit == Fit.DETAILS and room < DETAILS_MIN_ROOM:
        return Fit.FIT
    return fit


def plan_layout(
    size: tuple[int, int],
    canvas: tuple[int, int],
    fit: Fit,
    *,
    margin: float = 0.0,
    caption: bool = False,
    crop: Crop | None = None,
    details: Sequence[Crop] | None = None,
    auto: AutoCrop | None = None,
) -> Plan:
    """Where the picture (and its close-ups) go on the canvas.

    ``crop``/``details`` are corrections saved by the user; without them
    ``auto`` (the interest analysis) picks the crops, or they are centred.
    """
    resolved = resolve_fit(size, canvas, fit)
    if resolved == Fit.FILL:
        return _plan_fill(size, canvas, caption, crop, auto)
    if resolved == Fit.DETAILS:
        planned = _plan_details(size, canvas, margin, caption, details, auto)
        if planned is not None:
            return planned
    return _plan_fit(size, canvas, margin, caption)


def _auto(auto: AutoCrop | None, aspect: float, zoom: float, count: int) -> list[Crop]:
    found = auto(aspect, zoom, count) if auto else []
    return (found + [Crop(zoom=zoom)] * count)[:count]


def _plan_fit(size: tuple[int, int], canvas: tuple[int, int], margin: float, caption: bool) -> Plan:
    (iw, ih), (cw, ch) = size, canvas
    pad = round(min(cw, ch) * margin)
    bottom = max(pad, caption_band(canvas)) if caption else pad
    avail_w, avail_h = cw - 2 * pad, ch - pad - bottom
    scale = min(avail_w / iw, avail_h / ih)
    w, h = max(1, round(iw * scale)), max(1, round(ih * scale))
    x, y = (cw - w) // 2, pad + (avail_h - h) // 2
    at = (x + w, y + h + round(caption_size(canvas) * 0.6), w) if caption else None
    return Plan(Fit.FIT, canvas, [Window((x, y, w, h), (0, 0, iw, ih), "picture")], at)


def _plan_fill(
    size: tuple[int, int],
    canvas: tuple[int, int],
    caption: bool,
    crop: Crop | None,
    auto: AutoCrop | None,
) -> Plan:
    cw, ch = canvas
    band = caption_band(canvas) if caption else 0
    aspect = cw / (ch - band)
    chosen = crop or _auto(auto, aspect, 1.0, 1)[0]
    window = Window((0, 0, cw, ch - band), crop_box(size, aspect, chosen), "fill", chosen)
    at = None
    if caption:
        pad = round(min(cw, ch) * 0.03)
        at = (cw - pad, ch - band + (band - round(caption_size(canvas) * 1.2)) // 2, cw - 2 * pad)
    return Plan(Fit.FILL, canvas, [window], at)


def _plan_details(
    size: tuple[int, int],
    canvas: tuple[int, int],
    margin: float,
    caption: bool,
    details: Sequence[Crop] | None,
    auto: AutoCrop | None,
) -> Plan | None:
    (iw, ih), (cw, ch) = size, canvas
    m = round(min(cw, ch) * max(margin, 0.04))
    band = caption_band(canvas) if caption else 0
    gap = round(caption_size(canvas) * 0.6)
    rects: list[Rect]
    if iw / ih < cw / ch:  # picture at the left, full height; close-ups stacked
        main_w = round(ch * iw / ih)
        main: Rect = (0, 0, main_w, ch)
        win_w, win_h = cw - main_w - 2 * m, (ch - 3 * m - band) // 2
        rects = [(main_w + m, m, win_w, win_h), (main_w + m, 2 * m + win_h, win_w, win_h)]
        at = (main_w + m + win_w, 2 * m + 2 * win_h + gap, win_w)
    else:  # picture at the top, full width; close-ups side by side
        main_h = round(cw * ih / iw)
        main = (0, 0, cw, main_h)
        win_w, win_h = (cw - 3 * m) // 2, ch - main_h - 2 * m - band
        rects = [(m, main_h + m, win_w, win_h), (2 * m + win_w, main_h + m, win_w, win_h)]
        at = (2 * m + 2 * win_w, main_h + m + win_h + gap, 2 * win_w + m)
    if min(win_w, win_h) < 0.12 * min(cw, ch):
        return None
    aspect = win_w / win_h
    if details is not None and len(details) == 2:
        chosen = list(details)
    else:
        # As close as the source's pixels allow, and at least a little closer.
        cover_w = min(iw, ih * aspect)
        zoom = max(1.3, min(DETAIL_ZOOM, cover_w * DETAIL_MAX_UPSCALE / win_w))
        chosen = _auto(auto, aspect, zoom, 2)
    windows = [Window(main, (0, 0, iw, ih), "picture")]
    windows += [
        Window(rect, crop_box(size, aspect, c), "detail", c)
        for rect, c in zip(rects, chosen, strict=True)
    ]
    return Plan(Fit.DETAILS, canvas, windows, at if caption else None)


def compose_plan(
    img: Image.Image, plan: Plan, mat_color: tuple[int, int, int] = (255, 255, 255)
) -> FloatArray:
    """Linear RGB canvas: each window gets its part of the picture, resampled
    in linear light; the rest is ``mat_color`` (painted over later)."""
    cw, ch = plan.canvas
    out = np.empty((ch, cw, 3), dtype=np.float32)
    out[:] = u8_to_linear(np.array(mat_color, dtype=np.uint8))
    for window in plan.windows:
        x, y, w, h = window.rect
        x0, y0, x1, y1 = window.box
        part = img.crop((round(x0), round(y0), round(x1), round(y1)))
        out[y : y + h, x : x + w] = resize_linear(part, (w, h))
    return out


def to_panel(canvas_pixels: np.ndarray, orientation: Orientation, rotation: int) -> np.ndarray:
    """Rotate a portrait canvas into the panel's native landscape framebuffer.

    ``rotation`` is the clockwise rotation (90 or 270) the frame was hung
    with; the image is turned the other way so it appears upright.
    """
    if orientation == Orientation.LANDSCAPE:
        return canvas_pixels
    k = 1 if rotation == 90 else -1  # np.rot90 rotates counter-clockwise
    return np.ascontiguousarray(np.rot90(canvas_pixels, k=k))
