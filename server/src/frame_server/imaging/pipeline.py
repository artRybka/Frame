"""Source image -> panel framebuffer, plus a preview of how it will look.

Three strategies, to be compared on the real panel (experiment E5):

* passthrough – only layout/resize; the panel's own firmware does all colour
                work. This is roughly what the Samsung E-Paper app sends.
* compensate  – our tone/gamut mapping, then pre-distortion so the panel's
                own ditherer (assumed to believe the nominal ink colours)
                lands on our target. Panel still dithers.
* dither      – full pipeline; we dither to the six inks ourselves and send
                an image that contains only pure ink colours.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from .caption import caption_mask
from .color import linear_to_u8, luminance, u8_to_linear
from .dither import Kernel, error_diffusion, nearest
from .filters import sharpen
from .interest import InterestMap
from .layout import (
    Crop,
    Fit,
    Orientation,
    Plan,
    canvas_size,
    compose_plan,
    edge_color,
    load_image,
    plan_layout,
    to_panel,
)
from .mat import is_dark, paint_mat, picture_tint
from .palette import EM32DX, Palette
from .text import TextBlock, text_block_mask
from .tone import ToneSettings, map_to_panel, precompensate


class Strategy(StrEnum):
    PASSTHROUGH = "passthrough"
    COMPENSATE = "compensate"
    DITHER = "dither"


class LayoutSettings(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    orientation: Orientation = Orientation.LANDSCAPE
    rotation: Literal[90, 270] = Field(90, description="Clockwise rotation of a portrait frame")
    fit: Fit = Fit.AUTO
    mat: Literal["white", "cream", "grey", "black", "picture", "edge"] = "white"
    margin: float = Field(0.0, ge=0, le=0.3, description="Passe-partout, fraction of short side")
    crop: Crop | None = Field(None, description="FILL: part of the picture shown (else automatic)")
    details: list[Crop] | None = Field(
        None, min_length=2, max_length=2, description="DETAILS: the two close-ups (else automatic)"
    )
    detail: Crop | None = Field(None, description="DESCRIPTION: the close-up (else automatic)")
    fit_crop: Crop | None = Field(
        None, description="FIT: the part shown and the window's shape (else the whole picture)"
    )


class DitherSettings(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    method: Kernel | Literal["none"] = Kernel.FLOYD_STEINBERG
    serpentine: bool = True
    match: Literal["oklab", "linear"] = "oklab"
    error_clamp: float = Field(0.25, ge=0, le=2)


class RenderSettings(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    strategy: Strategy = Strategy.DITHER
    layout: LayoutSettings = Field(default_factory=LayoutSettings)
    tone: ToneSettings = Field(default_factory=ToneSettings)
    dither: DitherSettings = Field(default_factory=DitherSettings)
    sharpen: float = Field(0.0, ge=0, le=3)
    inks: list[str] | None = Field(None, description="Restrict to these inks, e.g. black+white")
    caption: str | None = Field(None, description="Museum-style label drawn in pure ink")
    text: TextBlock | None = Field(None, description="DESCRIPTION: printed on the mat")


PRESETS: dict[str, RenderSettings] = {
    # Photos: lift shadows (dark inks swallow them), mild contrast and colour boost.
    # Passthrough for now: in E5 the panel's own colour mapping beat our dither on
    # a real photo (docs/EXPERIMENTS.md). Back to DITHER once 1.3/1.4 catch up.
    "photo": RenderSettings(
        strategy=Strategy.PASSTHROUGH,
        tone=ToneSettings(gamma=1.15, shadows=0.35, highlights=0.1, contrast=1.1, saturation=1.2),
        sharpen=0.6,
    ),
    # Paintings: keep tonal relationships, gentle saturation, a passe-partout.
    "painting": RenderSettings(
        layout=LayoutSettings(fit=Fit.FIT, margin=0.05),
        tone=ToneSettings(gamma=1.1, shadows=0.25, contrast=1.05, saturation=1.15),
        sharpen=0.4,
    ),
    # Posters, prints, illustrations: flat colour, crisp edges.
    "graphic": RenderSettings(
        layout=LayoutSettings(fit=Fit.FIT, margin=0.04),
        tone=ToneSettings(contrast=1.2, saturation=1.3, gamut_knee=0.9),
        dither=DitherSettings(method=Kernel.ATKINSON, error_clamp=0.1),
        sharpen=0.8,
    ),
    # Drawings, etchings, B&W photography: black and white ink only.
    "bw": RenderSettings(
        layout=LayoutSettings(fit=Fit.FIT, margin=0.05),
        tone=ToneSettings(gamma=1.1, shadows=0.2, contrast=1.1, saturation=0.0),
        dither=DitherSettings(method=Kernel.JARVIS),
        inks=["black", "white"],
        sharpen=0.5,
    ),
}


@dataclass
class RenderResult:
    panel: np.ndarray  # (1440, 2560, 3) uint8, what the panel receives
    preview: np.ndarray  # canvas orientation, uint8, simulated look on the panel
    settings: RenderSettings
    palette: Palette

    @property
    def pure_inks(self) -> bool:
        return self.settings.strategy == Strategy.DITHER

    def panel_image(self) -> Image.Image:
        return Image.fromarray(self.panel)

    def preview_image(self, adapted: bool = True) -> Image.Image:
        """Simulated look of the panel.

        ``adapted`` rescales so the panel's paper white shows as screen white,
        as the eye adapts to it in a room; otherwise the raw measured colours
        (a grey-looking "white") are shown.
        """
        if not adapted:
            return Image.fromarray(self.preview)
        white = self.palette.perceived_linear()[self.palette.white_index()]
        lin = u8_to_linear(self.preview) / np.maximum(white, 1e-3)
        return Image.fromarray(linear_to_u8(lin))

    def encode(self, fmt: Literal["png", "jpeg"] | None = None) -> tuple[bytes, str]:
        """Encode the panel image; returns (bytes, extension)."""
        fmt = fmt or ("png" if self.pure_inks else "jpeg")
        return encode_image(self.panel_image(), fmt), ("png" if fmt == "png" else "jpg")


def encode_image(img: Image.Image, fmt: Literal["png", "jpeg"], quality: int = 95) -> bytes:
    out = io.BytesIO()
    if fmt == "png":
        img.save(out, "PNG", optimize=True)
    else:
        # 4:4:4 chroma: subsampling would smear single-pixel ink dots.
        img.save(out, "JPEG", quality=quality, subsampling=0, optimize=True)
    return out.getvalue()


# Mats in nominal colours, for the passthrough strategy (the panel dithers).
_NOMINAL_MATS = {
    "white": (255, 255, 255),
    "cream": (250, 242, 214),
    "grey": (150, 150, 150),
    "black": (0, 0, 0),
}


def _mat_rgb(img: Image.Image, mat: str) -> tuple[int, int, int]:
    if mat == "edge":
        return edge_color(img)
    if mat == "picture":
        small = img.copy()
        small.thumbnail((256, 256))
        pixels = u8_to_linear(np.asarray(small.convert("RGB")))
        tint = picture_tint(pixels, np.ones(3, np.float32), np.zeros(3, np.float32))
        return tuple(int(v) for v in linear_to_u8(tint))  # type: ignore[return-value]
    return _NOMINAL_MATS.get(mat, (255, 255, 255))


def plan_for(img: Image.Image, layout: LayoutSettings, caption: bool) -> Plan:
    """Where things go; the picture is analysed only if a crop must be chosen."""
    analysis: InterestMap | None = None

    def auto(aspect: float, zooms: Sequence[float]) -> list[Crop]:
        nonlocal analysis
        analysis = analysis or InterestMap(img)
        return analysis.pick(aspect, zooms)

    return plan_layout(
        img.size,
        canvas_size(layout.orientation),
        layout.fit,
        margin=layout.margin,
        caption=caption,
        crop=layout.crop,
        details=layout.details,
        detail=layout.detail,
        fit_crop=layout.fit_crop,
        auto=auto,
    )


def simulate_naive(linear: np.ndarray, palette: Palette) -> np.ndarray:
    """Our model of a stock pipeline: Floyd–Steinberg against nominal inks.

    Only a hypothesis until it is compared with photos of the panel (E5).
    """
    nominal = (palette.device_u8().astype(np.float32) / 255.0).astype(np.float32)
    return error_diffusion(linear, nominal, Kernel.FLOYD_STEINBERG, match_oklab=False)


def render(
    source: str | Path | bytes | Image.Image,
    settings: RenderSettings | None = None,
    palette: Palette = EM32DX,
) -> RenderResult:
    s = settings or RenderSettings()
    pal = palette.subset(s.inks)
    img = load_image(source)
    plan = plan_for(img, s.layout, caption=bool(s.caption))
    linear = compose_plan(img, plan, mat_color=_mat_rgb(img, s.layout.mat))
    linear = sharpen(linear, s.sharpen)

    if s.strategy == Strategy.PASSTHROUGH:
        sent = linear_to_u8(linear)
        preview_idx = simulate_naive(linear, pal)
        mat = u8_to_linear(np.array(_mat_rgb(img, s.layout.mat), dtype=np.uint8))
        dark_board = float(luminance(mat)) < 0.18
    else:
        target = map_to_panel(linear, pal, s.tone)
        board = paint_mat(target, plan, pal, s.layout.mat)
        dark_board = board is not None and is_dark(board, pal)
        if s.strategy == Strategy.COMPENSATE:
            nominal = precompensate(target, pal)
            sent = linear_to_u8(nominal)
            preview_idx = simulate_naive(nominal, pal)
        else:
            if s.dither.method == "none":
                preview_idx = nearest(target, pal.perceived_linear(), match_oklab=True)
            else:
                preview_idx = error_diffusion(
                    target,
                    pal.perceived_linear(),
                    Kernel(s.dither.method),
                    serpentine=s.dither.serpentine,
                    match_oklab=s.dither.match == "oklab",
                    error_clamp=s.dither.error_clamp,
                )
            sent = pal.device_u8()[preview_idx]

    # Lettering in pure ink on the mat: white on a dark mat, black otherwise.
    letters = []
    if s.caption and plan.caption_at is not None:
        letters.append(caption_mask(plan.canvas, plan.caption_at, s.caption))
    if s.text and plan.text_rect is not None:
        letters.append(text_block_mask(plan.canvas, plan.text_rect, s.text))
    if letters:
        ink = pal.white_index() if dark_board else pal.black_index()
        preview_idx = preview_idx.copy()
        sent = sent.copy()
        for mask in letters:
            preview_idx[mask] = ink
            sent[mask] = pal.device_u8()[ink]

    preview = pal.perceived_u8()[preview_idx]
    panel = to_panel(sent, s.layout.orientation, s.layout.rotation)
    return RenderResult(panel=panel, preview=preview, settings=s, palette=pal)
