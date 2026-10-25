from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from frame_server.imaging import (
    PRESETS,
    SPECTRA6,
    Palette,
    RenderSettings,
    Strategy,
    render,
    render_original,
)
from frame_server.imaging.color import (
    linear_to_oklab,
    linear_to_srgb,
    oklab_to_linear,
    srgb_to_linear,
    u8_to_linear,
)
from frame_server.imaging.dither import Kernel, error_diffusion
from frame_server.imaging.gamut import hull_planes, inside
from frame_server.imaging.layout import Fit, Orientation
from frame_server.imaging.testchart import CHARTS
from frame_server.imaging.tone import ToneSettings, map_to_panel, precompensate


def _gradient(w: int = 400, h: int = 300) -> Image.Image:
    x = np.linspace(0, 255, w, dtype=np.float32)
    y = np.linspace(0, 255, h, dtype=np.float32)
    arr = np.stack(np.broadcast_arrays(x[None, :], y[:, None], 255 - x[None, :]), axis=-1)
    return Image.fromarray(arr.astype(np.uint8))


def test_u8_lookup_matches_the_formula() -> None:
    values = np.arange(256, dtype=np.uint8)
    assert np.array_equal(u8_to_linear(values), srgb_to_linear(values / np.float32(255.0)))


def test_color_roundtrips() -> None:
    v = np.linspace(0, 1, 101, dtype=np.float32)
    assert np.allclose(linear_to_srgb(srgb_to_linear(v)), v, atol=1e-5)
    rgb = np.random.default_rng(0).random((50, 3), dtype=np.float32)
    assert np.allclose(oklab_to_linear(linear_to_oklab(rgb)), rgb, atol=1e-4)
    assert np.isclose(linear_to_oklab(np.ones(3, dtype=np.float32))[0], 1.0, atol=1e-3)


def test_palette_json_roundtrip_and_subset() -> None:
    again = Palette.from_json(SPECTRA6.to_json())
    assert again == SPECTRA6
    bw = SPECTRA6.subset(["black", "white"])
    assert bw.names == ["black", "white"]
    with pytest.raises(ValueError):
        SPECTRA6.subset(["purple"])


def test_hull_contains_inks_but_not_pure_primaries() -> None:
    planes = hull_planes(SPECTRA6.perceived_linear())
    assert inside(SPECTRA6.perceived_linear(), planes).all()
    assert not inside(np.array([[1.0, 1.0, 1.0], [0.0, 0.0, 1.0]], dtype=np.float32), planes).any()


@pytest.mark.parametrize("rgb", [(110, 150, 210), (230, 180, 150), (60, 140, 60), (180, 40, 40)])
def test_dither_preserves_average_colour(rgb: tuple[int, int, int]) -> None:
    src = np.broadcast_to(u8_to_linear(np.array(rgb, dtype=np.uint8)), (120, 120, 3)).copy()
    target = map_to_panel(src, SPECTRA6, ToneSettings())
    idx = error_diffusion(target, SPECTRA6.perceived_linear(), Kernel.FLOYD_STEINBERG)
    got = SPECTRA6.perceived_linear()[idx].reshape(-1, 3).mean(axis=0)
    delta = np.linalg.norm(linear_to_oklab(got) - linear_to_oklab(target[0, 0]))
    assert delta < 0.01


def test_precompensate_inverts_affine_fit() -> None:
    target = map_to_panel(u8_to_linear(np.asarray(_gradient())), SPECTRA6, ToneSettings())
    nominal = precompensate(target, SPECTRA6)
    assert nominal.shape == target.shape
    assert nominal.min() >= 0 and nominal.max() <= 1


@pytest.mark.parametrize("orientation", list(Orientation))
def test_render_dither_outputs_only_inks(orientation: Orientation) -> None:
    settings = PRESETS["photo"].model_copy(deep=True)
    settings.strategy = Strategy.DITHER
    settings.layout.orientation = orientation
    result = render(_gradient(), settings)
    assert result.panel.shape == (1440, 2560, 3)
    expected_preview = (1440, 2560) if orientation is Orientation.LANDSCAPE else (2560, 1440)
    assert result.preview.shape[:2] == expected_preview
    inks = {tuple(c) for c in SPECTRA6.device_u8()}
    used = {tuple(c) for c in np.unique(result.panel.reshape(-1, 3), axis=0)}
    assert used <= inks
    data, ext = result.encode()
    assert ext == "png"
    assert Image.open(io.BytesIO(data)).size == (2560, 1440)


@pytest.mark.parametrize("strategy", list(Strategy))
def test_original_keeps_the_pictures_colours(strategy: Strategy) -> None:
    """The app shows the framed picture untouched; only the panel is corrected."""
    colour = (200, 120, 40)
    settings = PRESETS["painting"].model_copy(deep=True)
    settings.strategy = strategy
    settings.layout.orientation = Orientation.LANDSCAPE
    result = render(Image.new("RGB", (400, 300), colour), settings)
    original = result.original_image()
    assert original.size == (2560, 1440)
    assert original.getpixel((1280, 720)) == colour  # no tone map, no dither
    assert original.getpixel((5, 5)) == (255, 255, 255)  # the white mat, as paper
    assert result.preview_image().getpixel((1280, 720)) != colour


@pytest.mark.parametrize("preset", ["painting", "photo", "bw"])
@pytest.mark.parametrize(
    ("fit", "mat"), [(Fit.FIT, "picture"), (Fit.FILL, "white"), (Fit.DETAILS, "black")]
)
def test_fast_original_matches_the_render(preset: str, fit: Fit, mat: str) -> None:
    """The app's quick preview is the render's original, lettering included."""
    settings = PRESETS[preset].model_copy(deep=True)
    settings.layout.fit = fit
    settings.layout.mat = mat
    settings.layout.orientation = Orientation.PORTRAIT
    settings.caption = "Claude Monet, Gare Saint-Lazare, 1877"
    source = _gradient(900, 700)
    full = np.asarray(render(source, settings).original_image(), dtype=np.float32)
    fast = np.asarray(render_original([source], settings), dtype=np.float32)
    assert fast.shape == full.shape
    assert np.abs(full - fast).mean() < 0.5
    assert np.percentile(np.abs(full - fast), 99.9) <= 2


def test_bw_preset_uses_two_inks() -> None:
    result = render(_gradient(), PRESETS["bw"])
    used = {tuple(c) for c in np.unique(result.panel.reshape(-1, 3), axis=0)}
    assert used <= {(0, 0, 0), (255, 255, 255)}


def test_photo_preset_is_passthrough() -> None:
    # E5: the panel's own colour mapping looked best on photos.
    assert PRESETS["photo"].strategy == Strategy.PASSTHROUGH


def test_passthrough_is_jpeg() -> None:
    result = render(_gradient(), RenderSettings(strategy=Strategy.PASSTHROUGH))
    data, ext = result.encode()
    assert ext == "jpg" and data[:2] == b"\xff\xd8"


@pytest.mark.parametrize("name", list(CHARTS))
def test_charts_are_native_size(name: str) -> None:
    img = CHARTS[name]()
    assert img.size == (2560, 1440) and img.mode == "RGB"


def test_paper_white_is_the_white_ink() -> None:
    # Spectra 6 yellow is lighter than its white; white must still map to white.
    assert SPECTRA6.names[SPECTRA6.white_index()] == "white"
    settings = PRESETS["photo"].model_copy(deep=True)
    settings.strategy = Strategy.DITHER
    settings.layout.fit = Fit.FILL
    result = render(Image.new("RGB", (320, 180), (255, 255, 255)), settings)
    white = np.all(result.panel == 255, axis=-1).mean()
    assert white > 0.99
