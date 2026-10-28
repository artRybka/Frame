"""Source image -> panel framebuffer, plus the composed picture for the app
(and a simulation of how the panel will show it).

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
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cached_property
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from .bands import by_rows
from .caption import caption_mask
from .color import FloatArray, linear_to_u8, u8_to_linear
from .dither import Kernel, error_diffusion, nearest
from .filters import sharpen
from .grids import MAX_PHOTOS, MIN_PHOTOS, plan_multi
from .interest import InterestMap
from .layout import (
    AutoCrop,
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
from .mat import (
    CREASE_ON_DARK,
    CREASE_ON_LIGHT,
    PICTURE_MATS,
    crease_dots,
    is_dark,
    paint_mat,
    picture_tint,
    shade_pictures,
)
from .palette import EM32DX, Palette
from .text import TextBlock, text_block_mask
from .tone import ToneSettings, grade_for_panel, map_to_panel, precompensate


class Strategy(StrEnum):
    PASSTHROUGH = "passthrough"
    COMPENSATE = "compensate"
    DITHER = "dither"


class LayoutSettings(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    orientation: Orientation = Orientation.LANDSCAPE
    rotation: Literal[90, 270] = Field(90, description="Clockwise rotation of a portrait frame")
    fit: Fit = Fit.AUTO
    mat: Literal["white", "cream", "grey", "black", "picture", "picture_dark", "edge"] = "white"
    margin: float = Field(0.0, ge=0, le=0.3, description="Passe-partout, fraction of short side")
    crop: Crop | None = Field(None, description="FILL: part of the picture shown (else automatic)")
    detail: Crop | None = Field(None, description="DESCRIPTION: the close-up (else automatic)")
    picture_crop: Crop | None = Field(
        None, description="DESCRIPTION: the part of the picture in its window (else all of it)"
    )
    fit_crop: Crop | None = Field(
        None, description="FIT: the part shown and the window's shape (else the whole picture)"
    )
    grid: str = Field("auto", description="MULTI: the grid's letter, or auto (by the shapes)")


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


# The presets let the panel dither (passthrough): in E5 and in the tuning by
# eye of E14 its own mapping beat our dither on every kind of picture, once
# light parts are pulled to paper white and muted and greys are kept off green.
_LIGHT = {"white_point": 0.93, "highlight_chroma": 0.55}
# Greys lean green on the panel: nudge them towards magenta and a little cooler.
_NEUTRAL = {"tint": 0.006, "temperature": -0.003, "tint_region": "neutral"}

PRESETS: dict[str, RenderSettings] = {
    "photo": RenderSettings(
        strategy=Strategy.PASSTHROUGH,
        tone=ToneSettings(**_LIGHT, **_NEUTRAL, contrast=1.05, saturation=1.05),
        sharpen=0.6,
    ),
    # Paintings: lighter midtones and light parts, a passe-partout.
    "painting": RenderSettings(
        strategy=Strategy.PASSTHROUGH,
        layout=LayoutSettings(fit=Fit.FIT, margin=0.05),
        tone=ToneSettings(**_LIGHT, **_NEUTRAL, gamma=1.1, highlights=-0.15),
        sharpen=0.4,
    ),
    # Posters, prints, illustrations: as paintings, with more punch and crisper edges.
    "graphic": RenderSettings(
        strategy=Strategy.PASSTHROUGH,
        layout=LayoutSettings(fit=Fit.FIT, margin=0.04),
        tone=ToneSettings(
            **_LIGHT, **_NEUTRAL, gamma=1.1, highlights=-0.15, contrast=1.1, saturation=1.1
        ),
        sharpen=0.8,
    ),
    # Drawings, etchings, B&W photography: greys the panel dithers with all its
    # inks (smoother and deeper than black and white ink alone), kept off green.
    "bw": RenderSettings(
        strategy=Strategy.PASSTHROUGH,
        layout=LayoutSettings(fit=Fit.FIT, margin=0.05),
        tone=ToneSettings(
            white_point=0.93, saturation=0.0, contrast=1.1, tint=0.012, temperature=-0.006
        ),
        sharpen=0.9,
    ),
}


@dataclass
class RenderResult:
    panel: np.ndarray  # (1440, 2560, 3) uint8, what the panel receives
    original: np.ndarray  # canvas orientation, uint8, framed picture in its own colours
    settings: RenderSettings
    palette: Palette
    simulate: Callable[[], np.ndarray] = field(repr=False)

    @cached_property
    def preview(self) -> np.ndarray:
        """Canvas orientation, uint8, simulated look on the panel. Made when
        first asked for: publishing does not need it, and when the panel
        dithers, simulating that is a whole dither of its own."""
        return self.simulate()

    @property
    def pure_inks(self) -> bool:
        return self.settings.strategy == Strategy.DITHER

    def panel_image(self) -> Image.Image:
        return Image.fromarray(self.panel)

    def original_image(self) -> Image.Image:
        """The framed picture (crop, mat, lettering) in its own colours: no
        tone mapping or dither, which only the panel gets. What the app shows."""
        return Image.fromarray(self.original)

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
        # zlib's default level: as good as "optimize" within ~10 % of the
        # size, ten times quicker on a dithered 2560x1440 (seconds on a NAS).
        img.save(out, "PNG", compress_level=6)
    else:
        # 4:4:4 chroma: subsampling would smear single-pixel ink dots.
        img.save(out, "JPEG", quality=quality, subsampling=0, optimize=True)
    return out.getvalue()


# The colour a mat is composed with; paint_mat paints all but "edge" over it.
_NOMINAL_MATS = {
    "white": (255, 255, 255),
    "cream": (255, 248, 218),  # as mat._cream shows it in the app
    "grey": (150, 150, 150),
    "black": (0, 0, 0),
}


def _mat_rgb(img: Image.Image, mat: str) -> tuple[int, int, int]:
    if mat == "edge":
        return edge_color(img)
    if mat in PICTURE_MATS:
        small = img.copy()
        small.thumbnail((256, 256))
        pixels = u8_to_linear(np.asarray(small.convert("RGB")))
        dark = mat == "picture_dark"
        tint = picture_tint(pixels, np.ones(3, np.float32), np.zeros(3, np.float32), dark)
        return tuple(int(v) for v in linear_to_u8(tint))  # type: ignore[return-value]
    return _NOMINAL_MATS.get(mat, (255, 255, 255))


def plan_for(img: Image.Image, layout: LayoutSettings, caption: bool) -> Plan:
    """Where things go; the picture is analysed only if a crop must be chosen."""
    return plan_layout(
        img.size,
        canvas_size(layout.orientation),
        layout.fit,
        margin=layout.margin,
        caption=caption,
        crop=layout.crop,
        detail=layout.detail,
        picture_crop=layout.picture_crop,
        fit_crop=layout.fit_crop,
        auto=_interest_picker(img),
    )


def simulate_naive(linear: np.ndarray, palette: Palette) -> np.ndarray:
    """Our model of a stock pipeline: Floyd–Steinberg against nominal inks.

    Only a hypothesis until it is compared with photos of the panel (E5).
    """
    nominal = (palette.device_u8().astype(np.float32) / 255.0).astype(np.float32)
    return error_diffusion(linear, nominal, Kernel.FLOYD_STEINBERG, match_oklab=False)


Source = str | Path | bytes | Image.Image


def render(
    source: Source,
    settings: RenderSettings | None = None,
    palette: Palette = EM32DX,
) -> RenderResult:
    s = settings or RenderSettings()
    linear, plan = _compose_one(load_image(source), s)
    return _finish(linear, plan, s, palette)


def render_original(
    sources: Sequence[Source],
    settings: RenderSettings | None = None,
    palette: Palette = EM32DX,
    multi: bool = False,
    seed: str = "",
) -> Image.Image:
    """The framed picture in its own colours, as ``original_image()`` of
    ``render`` (or ``render_multi`` with ``multi``), several times faster:
    no tone mapping or dither, and each window is resampled in sRGB.

    For the app's previews only. Lettering on a mat of the picture's tint is
    white or black by the picture's own colours, not by the panel's, so it
    may differ from the panel's at the very edge between the two.
    """
    s = settings or RenderSettings()
    imgs = [load_image(source) for source in sources[:MAX_PHOTOS]]
    if multi and len(imgs) >= MIN_PHOTOS:
        linear, plan = _compose_multi(imgs, s, seed, fast=True)
        s = s.model_copy(update={"caption": None, "text": None})
    else:
        linear, plan = _compose_one(imgs[0], s, fast=True)
    pal = palette.subset(s.inks)
    board = paint_mat(linear, plan, palette.nominal(), s.layout.mat)
    dark_board = board is not None and is_dark(board, palette.nominal())
    original = by_rows(linear_to_u8, linear)
    for index, mask in _marks(plan, s, pal, dark_board):
        original[mask] = pal.device_u8()[index]
    return Image.fromarray(original)


def _compose_one(
    img: Image.Image, s: RenderSettings, fast: bool = False
) -> tuple[FloatArray, Plan]:
    plan = plan_for(img, s.layout, caption=bool(s.caption))
    return compose_plan(img, plan, mat_color=_mat_rgb(img, s.layout.mat), fast=fast), plan


def _compose_multi(
    imgs: list[Image.Image], s: RenderSettings, seed: str, fast: bool = False
) -> tuple[FloatArray, Plan]:
    pickers = [_interest_picker(img) for img in imgs]
    plan, order = plan_multi(
        [img.size for img in imgs],
        canvas_size(s.layout.orientation),
        s.layout.margin,
        s.layout.grid,
        seed,
        pickers,
    )
    mat_rgb = _mat_rgb(imgs[0], s.layout.mat)
    linear = compose_plan([imgs[i] for i in order], plan, mat_color=mat_rgb, fast=fast)
    return linear, plan


def render_multi(
    sources: Sequence[Source],
    settings: RenderSettings | None = None,
    palette: Palette = EM32DX,
    seed: str = "",
) -> RenderResult:
    """MULTI: several photos on one board, each in its own mat window.

    With a single source this is a passe-partout (FIT). ``seed`` (e.g. the
    photos' ids) keeps the automatic grid choice the same on a redraw.
    """
    s = settings or RenderSettings()
    if len(sources) < MIN_PHOTOS:
        return render(sources[0], s, palette)  # MULTI with one picture is a passe-partout
    imgs = [load_image(source) for source in sources[:MAX_PHOTOS]]
    linear, plan = _compose_multi(imgs, s, seed)
    no_text = s.model_copy(update={"caption": None, "text": None})
    return _finish(linear, plan, no_text, palette)


def _interest_picker(img: Image.Image) -> AutoCrop:
    """Crops by the picture's interest analysis, made only when first needed."""
    analysis: InterestMap | None = None

    def pick(aspect: float, zooms: Sequence[float]) -> list[Crop]:
        nonlocal analysis
        analysis = analysis or InterestMap(img)
        return analysis.pick(aspect, zooms)

    return pick


def _finish(
    linear: FloatArray,
    plan: Plan,
    s: RenderSettings,
    palette: Palette,
) -> RenderResult:
    """Tone, mat, dither and lettering for a composed canvas."""
    pal = palette.subset(s.inks)
    # The app's view: the composition in nominal colours, before any correction.
    original = linear.copy()
    paint_mat(original, plan, palette.nominal(), s.layout.mat)
    linear = sharpen(linear, s.sharpen)

    # The panel's look: our own dither, or (when the panel dithers) a
    # simulation of its dither of ``naive``, made only when asked for.
    naive: FloatArray | None = None
    dithered = np.zeros(0, dtype=np.uint8)
    on_mat: np.ndarray | None = None  # passthrough: the mat, dithered by us
    if s.strategy == Strategy.PASSTHROUGH:
        picture = by_rows(lambda part: grade_for_panel(part, s.tone), linear)
        mask = plan.mat_mask()
        dark_board = False
        if mask.any():
            # The mat and its bevels in pure inks, as in DITHER: the panel
            # keeps them 1:1 and dithers only the picture (E5). Our dither
            # runs on the mat alone.
            if s.layout.mat in (*PICTURE_MATS, "edge"):  # coloured by the picture
                target = by_rows(lambda part: map_to_panel(part, pal, s.tone), linear)
            else:  # only the mat matters here
                target = np.empty_like(linear)
            board = paint_mat(target, plan, pal, s.layout.mat, shade=False)
            dark_board = board is not None and is_dark(board, pal)
            shade_pictures(picture, plan)
            on_mat = _dither(target, pal, s.dither, only=mask)
        sent = by_rows(linear_to_u8, picture)
        naive = picture
        if on_mat is not None:
            sent[mask] = pal.device_u8()[on_mat[mask]]
    else:
        target = by_rows(lambda part: map_to_panel(part, pal, s.tone), linear)
        board = paint_mat(target, plan, pal, s.layout.mat)
        dark_board = board is not None and is_dark(board, pal)
        if s.strategy == Strategy.COMPENSATE:
            nominal = precompensate(target, pal)
            sent = by_rows(linear_to_u8, nominal)
            naive = nominal
        else:
            dithered = _dither(target, pal, s.dither)
            sent = pal.device_u8()[dithered]

    # The crease and the lettering in pure ink on the mat.
    marks = _marks(plan, s, pal, dark_board)
    original_u8 = by_rows(linear_to_u8, original)
    if marks:
        sent = sent.copy()
        for index, where in marks:
            sent[where] = pal.device_u8()[index]
            original_u8[where] = pal.device_u8()[index]

    def preview() -> np.ndarray:
        preview_idx = dithered if naive is None else simulate_naive(naive, pal)
        if on_mat is not None or marks:
            preview_idx = preview_idx.copy()
        if on_mat is not None:
            preview_idx[mask] = on_mat[mask]
        for index, where in marks:
            preview_idx[where] = index
        return pal.perceived_u8()[preview_idx]

    panel = to_panel(sent, s.layout.orientation, s.layout.rotation)
    return RenderResult(
        panel=panel, original=original_u8, settings=s, palette=pal, simulate=preview
    )


def _dither(
    target: FloatArray, pal: Palette, d: DitherSettings, only: np.ndarray | None = None
) -> np.ndarray:
    if d.method == "none":
        return nearest(target, pal.perceived_linear(), match_oklab=True)
    return error_diffusion(
        target,
        pal.perceived_linear(),
        Kernel(d.method),
        serpentine=d.serpentine,
        match_oklab=d.match == "oklab",
        error_clamp=d.error_clamp,
        only=only,
    )


def _marks(
    plan: Plan, s: RenderSettings, pal: Palette, dark_board: bool
) -> list[tuple[int, np.ndarray]]:
    """(ink index, mask) of what is printed on the mat in pure ink: the
    crease around the cut, then the lettering, white on a dark mat."""
    pattern = CREASE_ON_DARK if dark_board else CREASE_ON_LIGHT
    marks = [
        (pal.index(name), dots)
        for name, dots in crease_dots(plan, pattern).items()
        if name in pal.names
    ]
    ink = pal.white_index() if dark_board else pal.black_index()
    return marks + [(ink, mask) for mask in _letters(plan, s)]


def _letters(plan: Plan, s: RenderSettings) -> list[np.ndarray]:
    """Masks of the caption and the description printed on the mat."""
    letters = []
    if s.caption and plan.caption_at is not None:
        letters.append(caption_mask(plan.canvas, plan.caption_at, s.caption))
    if s.text and plan.text_rect is not None:
        letters.append(text_block_mask(plan.canvas, plan.text_rect, s.text))
    return letters
