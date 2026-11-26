"""A printed screen is found and taken off; a painting is left as it is."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageFilter

from frame_server.imaging.descreen import cleared, descreened, screen


def _painting(h: int = 600, w: int = 480) -> np.ndarray:
    rng = np.random.default_rng(1)
    y, x = np.mgrid[0:h, 0:w]
    base = np.stack(
        [0.5 + 0.4 * np.sin(x / 90), 0.5 + 0.3 * np.cos(y / 70), 0.4 + 0.3 * np.sin((x + y) / 120)],
        -1,
    )
    base = base + rng.normal(0, 0.03, (h, w, 1))
    for _ in range(20):
        cy, cx, r = rng.integers(0, h), rng.integers(0, w), rng.integers(10, 70)
        base[(y - cy) ** 2 + (x - cx) ** 2 < r * r] = rng.random(3)
    return np.clip(base, 0, 1)


def _jpeg(img: Image.Image, quality: int) -> Image.Image:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def _printed(base: np.ndarray, period: float, angle: float) -> Image.Image:
    h, w = base.shape[:2]
    y, x = np.mgrid[0:h, 0:w]
    a = np.deg2rad(angle)
    u = (x * np.cos(a) + y * np.sin(a)) / period
    v = (-x * np.sin(a) + y * np.cos(a)) / period
    dot = np.hypot(u - np.round(u), v - np.round(v))
    ink = dot[..., None] < np.sqrt((1 - base) / np.pi)
    out = np.where(ink, 0.0, 1.0) * 0.85 + base * 0.15
    img = Image.fromarray((out * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8))
    return _jpeg(img, 80)


def _fine(img: Image.Image, sigma: float) -> float:
    a = np.asarray(img, dtype=np.float32)
    b = np.asarray(img.filter(ImageFilter.GaussianBlur(sigma)), dtype=np.float32)
    return float(np.abs(a - b).mean())


def test_a_painting_and_its_jpeg_have_no_screen() -> None:
    plain = Image.fromarray((_painting() * 255).astype(np.uint8))
    assert screen(plain) == []
    assert screen(_jpeg(plain, 50)) == []
    big = Image.fromarray((_painting(1200, 1100) * 255).astype(np.uint8))
    assert descreened(big) is big


def test_a_printed_screen_is_taken_off_and_the_masses_stay() -> None:
    base = _painting()
    for period, angle in ((3.5, 45), (5, 15), (8, 75)):
        printed = _printed(base, period, angle)
        assert screen(printed)
        clean = descreened(printed)
        assert clean.size == printed.size
        assert _fine(clean, period) < 0.45 * _fine(printed, period)
        masses = np.asarray(printed.filter(ImageFilter.GaussianBlur(12)), dtype=np.float32)
        kept = np.asarray(clean.filter(ImageFilter.GaussianBlur(12)), dtype=np.float32)
        assert float(np.abs(masses - kept).mean()) < 3.0


def test_a_tiny_picture_keeps_its_size() -> None:
    small = Image.new("RGB", (40, 30), "white")
    assert screen(small) == []
    assert descreened(small).size == (40, 30)


def test_a_small_picture_loses_only_its_finest_grain() -> None:
    plain = Image.fromarray((_painting() * 255).astype(np.uint8))
    soft = descreened(plain)
    assert soft is not plain and soft.size == plain.size
    masses = np.asarray(plain.filter(ImageFilter.GaussianBlur(3)), dtype=np.float32)
    kept = np.asarray(soft.filter(ImageFilter.GaussianBlur(3)), dtype=np.float32)
    assert float(np.abs(masses - kept).mean()) < 1.0
    y, x = np.mgrid[0:400, 0:400]
    net = Image.fromarray(
        np.stack([((np.sin(2.6 * x) * np.sin(2.6 * y)) * 40 + 128)] * 3, -1).astype(np.uint8)
    )
    assert np.asarray(descreened(net), dtype=np.float32).std() < 0.2 * np.asarray(net).std()


def test_the_edges_are_left_as_they_were() -> None:
    printed = _printed(_painting(), 5, 45)
    clean = np.asarray(descreened(printed.resize((1200, 1500))), dtype=np.float32)
    before = np.asarray(printed.resize((1200, 1500)), dtype=np.float32)
    edge = np.abs(clean - before)[:6].mean()
    middle = np.abs(clean - before)[600:606].mean()
    assert edge < 1.5 * middle


def test_a_printed_picture_is_shown_cleared_and_sharpened_back() -> None:
    plain = Image.fromarray((_painting() * 255).astype(np.uint8))
    assert cleared(plain) is None
    printed = _printed(_painting(), 3.5, 45)
    shown = cleared(printed)
    assert shown is not None and shown.size == printed.size
    assert _fine(shown, 3.5) < 0.6 * _fine(printed, 3.5)
    # Sharpened above the screen: its edges stand out more than the
    # screen taken off alone.
    soft = descreened(printed)
    edges = np.asarray(shown.filter(ImageFilter.FIND_EDGES), dtype=np.float32).mean()
    assert edges > np.asarray(soft.filter(ImageFilter.FIND_EDGES), dtype=np.float32).mean()


def test_what_is_left_of_a_print_goes_too() -> None:
    """Lines a scanner left over a printed screen stand lower than the
    screen; once the picture is known to be printed they go as well."""
    printed = np.asarray(_printed(_painting(), 3.5, 45), dtype=np.float32)
    y = np.arange(printed.shape[0], dtype=np.float32)[:, None, None]
    lined = Image.fromarray(
        np.clip(printed + 6 * np.sin(2 * np.pi * y / 5), 0, 255).astype(np.uint8)
    )
    clean = np.asarray(descreened(lined).convert("L"), dtype=np.float32)
    rows = clean.mean(axis=1)
    rows -= np.convolve(rows, np.ones(15) / 15, mode="same")
    assert float(np.abs(rows[20:-20]).mean()) < 1.0


def test_even_lines_one_way_are_no_screen() -> None:
    """A drawing's even hatching (lines all one way) is no printer's dots."""
    base = (_painting() * 255).astype(np.float32)
    x = np.arange(base.shape[1])[None, :, None]
    hatched = Image.fromarray(np.where(x % 5 == 0, base * 0.7, base).astype(np.uint8))
    assert screen(hatched) == []
