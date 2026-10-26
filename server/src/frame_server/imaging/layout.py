"""Loading source images and laying them out on the panel canvas."""

from __future__ import annotations

import io
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms, ImageOps
from pillow_heif import register_heif_opener
from pydantic import BaseModel, Field

from . import bands
from .color import FloatArray, linear_to_u8, u8_to_linear

PANEL_WIDTH = 2560
PANEL_HEIGHT = 1440

_SRGB_PROFILE = ImageCms.createProfile("sRGB")

# iPhone originals (newer shared iCloud albums, uploads) are HEIC.
register_heif_opener()


class Orientation(StrEnum):
    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"


class Fit(StrEnum):
    FILL = "fill"  # cover the canvas, crop the overflow
    FIT = "fit"  # whole image visible, mat around it
    DESCRIPTION = "description"  # the image, a close-up beside it and a printed description
    MULTI = "multi"  # photos only: several on one board, each in its own window
    AUTO = "auto"  # fill when the crop would be small, description when very different, else fit

    @classmethod
    def _missing_(cls, value: object) -> Fit | None:
        # "details" (two close-ups) was retired: settings saved with it get
        # the description, its closest relative.
        return cls.DESCRIPTION if value == "details" else None


class Crop(BaseModel):
    """Which part of a picture a window shows: its centre, as fractions of the
    picture, and the zoom (1 = the largest part of the window's shape)."""

    x: float = Field(0.5, ge=0, le=1)
    y: float = Field(0.5, ge=0, le=1)
    zoom: float = Field(1.0, ge=1, le=8)
    # FIT only: the window's shape (width / height); None keeps the picture's.
    aspect: float | None = Field(None, ge=0.2, le=5)


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
    pixels = np.asarray(img, dtype=np.uint8)
    if img.size == size:
        return u8_to_linear(pixels)
    out = np.empty((size[1], size[0], 3), dtype=np.float32)

    def plane(c: int) -> None:  # the three side by side: Pillow lets go of the GIL
        channel = Image.fromarray(u8_to_linear(pixels[..., c]))
        out[..., c] = np.asarray(channel.resize(size, Image.Resampling.LANCZOS))

    for _ in bands.pool.map(plane, range(3)):
        pass
    return np.clip(out, 0.0, 1.0, out=out)


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
DESCRIPTION_ROOM = 0.35  # canvas share beside the picture from which AUTO adds a description
BESIDE_SHARE = 0.33  # DESCRIPTION: the close-up and the text get at least this share
DETAIL_ZOOM = 3.0  # the close-up, if the source has the pixels
DETAIL_MAX_UPSCALE = 1.6  # enlarge source pixels at most this much, unless...
DETAIL_MIN_ENLARGEMENT = 1.8  # ...the close-up would be less than this times the picture
PICTURE_TRIM = 0.02  # a mat window is a bit smaller than the picture behind it

Rect = tuple[int, int, int, int]  # x, y, w, h
# Picks crops automatically: (window aspect, one zoom per crop) -> crops,
# each showing something away from the ones before it.
AutoCrop = Callable[[float, Sequence[float]], list[Crop]]


@dataclass(frozen=True)
class Window:
    """A cut-out of the canvas showing (part of) the picture."""

    rect: Rect
    box: tuple[float, float, float, float]  # part of the picture shown, in its pixels
    role: str  # "picture" (all of it, or as cropped), "fill" or "detail"
    crop: Crop | None = None  # what the user can adjust; None for MULTI's photos

    @property
    def aspect(self) -> float:
        return self.rect[2] / self.rect[3]


@dataclass(frozen=True)
class Plan:
    fit: Fit  # resolved: FIT, FILL, DESCRIPTION or MULTI
    canvas: tuple[int, int]
    windows: list[Window]
    caption_at: tuple[int, int, int] | None = None  # right x, top y, max width
    text_rect: Rect | None = None  # DESCRIPTION: where the text is printed on the mat

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
        return Fit.DESCRIPTION if room >= DESCRIPTION_ROOM else Fit.FIT
    return fit


def plan_layout(
    size: tuple[int, int],
    canvas: tuple[int, int],
    fit: Fit,
    *,
    margin: float = 0.0,
    caption: bool = False,
    crop: Crop | None = None,
    detail: Crop | None = None,
    picture_crop: Crop | None = None,
    fit_crop: Crop | None = None,
    auto: AutoCrop | None = None,
) -> Plan:
    """Where the picture, its close-up and its text go on the canvas.

    ``crop`` (FILL), ``detail`` and ``picture_crop`` (DESCRIPTION) and
    ``fit_crop`` (FIT) are corrections saved by the user; without them
    ``auto`` (the interest analysis) picks the crops, or they are centred,
    and FIT and DESCRIPTION show the whole picture.
    """
    resolved = resolve_fit(size, canvas, fit)  # MULTI with one picture: as FIT
    if resolved == Fit.FILL:
        return _plan_fill(size, canvas, caption, crop, auto)
    if resolved == Fit.DESCRIPTION:
        planned = _plan_description(size, canvas, margin, detail, picture_crop, auto)
        if planned is not None:
            return planned
    return _plan_fit(size, canvas, margin, caption, fit_crop)


def _auto(auto: AutoCrop | None, aspect: float, zooms: Sequence[float]) -> list[Crop]:
    found = auto(aspect, zooms) if auto else []
    return found if len(found) == len(zooms) else [Crop(zoom=z) for z in zooms]


def whole(size: tuple[int, int]) -> tuple[float, float, float, float]:
    """The picture in a mat window: its outermost edge stays behind the mat."""
    iw, ih = size
    return iw * PICTURE_TRIM, ih * PICTURE_TRIM, iw * (1 - PICTURE_TRIM), ih * (1 - PICTURE_TRIM)


WHOLE = Crop(zoom=1 / (1 - 2 * PICTURE_TRIM))  # FIT uncropped: ``whole`` as a crop


def _fitted(aspect: float, avail_w: int, avail_h: int) -> tuple[int, int]:
    if avail_w / avail_h > aspect:
        return max(1, round(avail_h * aspect)), avail_h
    return avail_w, max(1, round(avail_w / aspect))


def fit_area(canvas: tuple[int, int], margin: float, caption: bool) -> Rect:
    """FIT: where the mat window may go; it is centred in it at any shape."""
    cw, ch = canvas
    pad = round(min(cw, ch) * margin)
    bottom = max(pad, caption_band(canvas)) if caption else pad
    return pad, pad, cw - 2 * pad, ch - pad - bottom


def _plan_fit(
    size: tuple[int, int],
    canvas: tuple[int, int],
    margin: float,
    caption: bool,
    crop: Crop | None = None,
) -> Plan:
    """The picture in one mat window: whole, or cropped to any shape."""
    (iw, ih), (cw, _) = size, canvas
    chosen = crop or WHOLE
    aspect = chosen.aspect or iw / ih
    pad, _, avail_w, avail_h = fit_area(canvas, margin, caption)
    w, h = _fitted(aspect, avail_w, avail_h)
    x, y = (cw - w) // 2, pad + (avail_h - h) // 2
    at = (x + w, y + h + round(caption_size(canvas) * 0.6), w) if caption else None
    window = Window((x, y, w, h), crop_box(size, aspect, chosen), "picture", chosen)
    return Plan(Fit.FIT, canvas, [window], at)


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
    chosen = crop or _auto(auto, aspect, [1.0])[0]
    window = Window((0, 0, cw, ch - band), crop_box(size, aspect, chosen), "fill", chosen)
    at = None
    if caption:
        pad = round(min(cw, ch) * 0.03)
        at = (cw - pad, ch - band + (band - round(caption_size(canvas) * 1.2)) // 2, cw - 2 * pad)
    return Plan(Fit.FILL, canvas, [window], at)


def detail_zoom(size: tuple[int, int], aspect: float, window_width: int, picture: float) -> float:
    """The close-up: as close as the source's pixels allow, and at least
    ``DETAIL_MIN_ENLARGEMENT`` times larger than the picture beside it, shown
    at ``picture`` canvas pixels per source pixel."""
    iw, ih = size
    cover_w = min(iw, ih * aspect)  # source pixels across the window at zoom 1
    closest = cover_w * DETAIL_MAX_UPSCALE / window_width
    least = DETAIL_MIN_ENLARGEMENT * picture * cover_w / window_width
    return min(max(1.5, min(DETAIL_ZOOM, closest), least), 8.0)


def _plan_description(
    size: tuple[int, int],
    canvas: tuple[int, int],
    margin: float,
    detail: Crop | None,
    picture_crop: Crop | None,
    auto: AutoCrop | None,
) -> Plan | None:
    """The picture, a close-up beside it, and the text printed on the mat.

    The picture goes at the left with the rest stacked beside it, or on top
    with the rest side by side, whichever shows it larger. It spans the full
    height (or width) when that leaves the rest at least ``BESIDE_SHARE`` of
    the canvas; otherwise it is made smaller and sits in a mat window, the
    close-up and the text aligned with it. ``picture_crop`` moves and zooms
    the picture in its window; the window keeps the picture's shape.
    """
    options = [
        planned
        for side in (True, False)
        if (planned := _beside(size, canvas, margin, side)) is not None
    ]
    if not options:
        return None
    main, (close_rect, text_rect) = max(options, key=lambda o: o[0][2] * o[0][3])
    if picture_crop is None:
        shown, box = WHOLE, whole(size)
    else:
        shown, box = picture_crop, crop_box(size, main[2] / main[3], picture_crop)
    aspect = close_rect[2] / close_rect[3]
    if detail is None:
        zoom = detail_zoom(size, aspect, close_rect[2], main[2] / (box[2] - box[0]))
        detail = _auto(auto, aspect, [zoom])[0]
    windows = [
        Window(main, box, "picture", shown),
        Window(close_rect, crop_box(size, aspect, detail), "detail", detail),
    ]
    return Plan(Fit.DESCRIPTION, canvas, windows, None, text_rect)


def _beside(
    size: tuple[int, int], canvas: tuple[int, int], margin: float, side: bool
) -> tuple[Rect, list[Rect]] | None:
    """One arrangement: (picture, [close-up, text])."""
    (iw, ih), (cw, ch) = size, canvas
    m = round(min(cw, ch) * max(margin, 0.04))
    main: Rect
    if side:  # picture at the left; the rest stacked in a column at the right
        full_w = round(ch * iw / ih)
        if cw - full_w >= cw * BESIDE_SHARE:
            main = (0, 0, full_w, ch)
            col = (full_w + m, m, cw - full_w - 2 * m, ch - 2 * m)
        else:
            col_w = round((cw - 3 * m) * BESIDE_SHARE)
            avail_h = ch - 2 * m
            w, h = _fitted(iw / ih, cw - 3 * m - col_w, avail_h)
            x, y = (cw - w - m - col_w) // 2, m + (avail_h - h) // 2
            main, col = (x, y, w, h), (x + w + m, y, col_w, h)
        cx, cy, colw, colh = col
        win_h = (colh - m) // 2
        rects = [(cx, cy, colw, win_h), (cx, cy + win_h + m, colw, colh - win_h - m)]
    else:  # picture on top; the rest side by side in a row below
        full_h = round(cw * ih / iw)
        if ch - full_h >= ch * BESIDE_SHARE:
            main = (0, 0, cw, full_h)
            row = (m, full_h + m, cw - 2 * m, ch - full_h - 2 * m)
        else:
            row_h = round((ch - 3 * m) * BESIDE_SHARE)
            avail_h = ch - 3 * m - row_h
            w, h = _fitted(iw / ih, cw - 2 * m, avail_h)
            x, y = (cw - w) // 2, m + (avail_h - h) // 2
            main, row = (x, y, w, h), (x, y + h + m, w, row_h)
        rx, ry, roww, rowh = row
        win_w = (roww - m) // 2
        rects = [(rx, ry, win_w, rowh), (rx + win_w + m, ry, roww - win_w - m, rowh)]
    if min(rects[0][2], rects[0][3]) < 0.12 * min(cw, ch):
        return None
    return main, rects


def compose_plan(
    img: Image.Image | Sequence[Image.Image],
    plan: Plan,
    mat_color: tuple[int, int, int] = (255, 255, 255),
    fast: bool = False,
) -> FloatArray:
    """Linear RGB canvas: each window gets its part of the picture, resampled
    in linear light; the rest is ``mat_color`` (painted over later).

    ``img`` is one picture for all windows, or one per window (MULTI).
    ``fast`` resamples in sRGB instead, a little darker in fine detail but
    much quicker: for previews in the app."""
    cw, ch = plan.canvas
    out = np.empty((ch, cw, 3), dtype=np.float32)
    out[:] = u8_to_linear(np.array(mat_color, dtype=np.uint8))
    images = [img] * len(plan.windows) if isinstance(img, Image.Image) else list(img)
    for window, img in zip(plan.windows, images, strict=True):
        x, y, w, h = window.rect
        x0, y0, x1, y1 = window.box
        part = img.crop((round(x0), round(y0), round(x1), round(y1)))
        if fast:
            part = part.resize((w, h), Image.Resampling.LANCZOS)
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
