"""A printed screen is found and taken off; a painting is left as it is."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageFilter

from frame_server.imaging.descreen import descreened, screen


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
    assert descreened(plain) is plain


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


def test_a_tiny_picture_is_left() -> None:
    small = Image.new("RGB", (40, 40), "white")
    assert descreened(small) is small
