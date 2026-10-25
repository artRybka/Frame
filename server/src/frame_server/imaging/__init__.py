"""Image pipeline for the Spectra 6 colour e-paper panel."""

from .palette import EM32DX, SPECTRA6, SPECTRA6_THEORETICAL, Palette, PaletteColor, get_palette
from .pipeline import (
    PRESETS,
    DitherSettings,
    LayoutSettings,
    RenderResult,
    RenderSettings,
    Strategy,
    render,
    render_multi,
    render_original,
)
from .tone import ToneSettings

__all__ = [
    "EM32DX",
    "PRESETS",
    "SPECTRA6",
    "SPECTRA6_THEORETICAL",
    "DitherSettings",
    "LayoutSettings",
    "Palette",
    "PaletteColor",
    "RenderResult",
    "RenderSettings",
    "Strategy",
    "ToneSettings",
    "get_palette",
    "render",
    "render_multi",
    "render_original",
]
