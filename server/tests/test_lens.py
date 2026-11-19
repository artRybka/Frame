"""The lens's own bend taken out of the photograph of a work (Mateusz
2026-11-18 22:28 UTC, a frame's straight sides bowed outward:
"Zakrzywienie obiektywu iPhone? Jakieś możliwości prostowania czy to
bardzo skomplikowane?")."""

from __future__ import annotations

import io
import math

import cv2
import numpy as np
from PIL import Image

from frame_server.imaging import lens

#: A photograph as the phone's sensor gives it, small.
W, H = 900, 1200
#: A frame's outer edge in the scene, filling most of it (as his did).
FRAME = (90, 150, 810, 1050)
PHONE = "iPhone 18 Pro Max"
K1 = lens.BENDS[PHONE]


def scene() -> np.ndarray:
    """A dark frame with straight sides on a light wall, a work in it."""
    rng = np.random.default_rng(5)
    wall = np.full((H, W, 3), 205, np.uint8)
    x0, y0, x1, y1 = FRAME
    wall[y0:y1, x0:x1] = 40
    blocks = rng.integers(60, 200, (30, 22, 3), dtype=np.uint8)
    work = cv2.resize(blocks, (x1 - x0 - 80, y1 - y0 - 80), interpolation=cv2.INTER_CUBIC)
    wall[y0 + 40 : y1 - 40, x0 + 40 : x1 - 40] = work
    return wall


def where(x: np.ndarray, y: np.ndarray, k1: float) -> tuple[np.ndarray, np.ndarray]:
    """Where a lens with the bend ``k1`` draws the scene's point at each
    of the photograph's pixels: the scene's pixels to read them from."""
    half = math.hypot(W, H) / 2
    px, py = (x - (W - 1) / 2) / half, (y - (H - 1) / 2) / half
    ux, uy = px.copy(), py.copy()
    for _ in range(20):
        bent = 1 + k1 * (ux**2 + uy**2)
        ux, uy = px / bent, py / bent
    return ux * half + (W - 1) / 2, uy * half + (H - 1) / 2


def bent(img: np.ndarray, k1: float = K1) -> np.ndarray:
    """``img`` as a lens with the bend ``k1`` photographs it."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    sx, sy = where(xx, yy, k1)
    return cv2.remap(
        img,
        sx.astype(np.float32),
        sy.astype(np.float32),
        cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def bow(img: np.ndarray) -> float:
    """How far the frame's upper side is off a straight line, in pixels:
    where the wall turns dark down each column, the ends' line taken off."""
    grey = img[:, :, 1].astype(float)
    x0, y0, x1, _ = FRAME
    edge = []
    for x in range(x0 + 30, x1 - 30, 8):
        column = grey[y0 - 40 : y0 + 40, x]
        i = int(np.argmax(column < 122))
        # Between the two rows the level is passed.
        a, b = column[i - 1], column[i]
        edge.append(y0 - 40 + i - 1 + (a - 122) / (a - b))
    line = np.linspace(edge[0], edge[-1], len(edge))
    return float(np.abs(np.array(edge) - line).max())


def test_a_barrel_is_taken_out_and_the_frames_sides_are_straight_again() -> None:
    straight = scene()
    taken = bent(straight)
    # His frame's side bowed some 0.4% of its length: 3 pixels of 720.
    assert 2.0 < bow(taken) < 5.0
    made = lens.straight(taken, K1)
    assert made.shape == taken.shape and made.dtype == taken.dtype
    assert bow(made) < 0.3
    # The scene again, but for the two samplings on the way.
    inner = (slice(60, H - 60), slice(60, W - 60))
    off = np.abs(made[inner].astype(int) - straight[inner].astype(int)).mean()
    assert off < 2.0
    assert np.abs(taken[inner].astype(int) - straight[inner].astype(int)).mean() > 3 * off
    # A grey picture as well as one in colour; no bend, nothing moved.
    assert lens.straight(taken[:, :, 0], K1).shape == (H, W)
    assert np.array_equal(lens.straight(taken, 0.0), taken)


def test_corners_set_on_the_photograph_as_taken_go_with_it() -> None:
    x0, y0, x1, y1 = FRAME
    true = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    # Where the lens drew the frame's corners: outward of them it reads
    # the scene nearer its middle.
    half = math.hypot(W, H) / 2
    drawn = []
    for x, y in true:
        ux, uy = (x - W / 2) / half, (y - H / 2) / half
        f = 1 + K1 * (ux * ux + uy * uy)
        drawn.append(((ux * f * half + W / 2) / W, (uy * f * half + H / 2) / H))
    moved = lens.moved(drawn, W, H, K1)
    for (mx, my), (x, y) in zip(moved, true, strict=True):
        assert abs(mx * W - x) < 0.05 and abs(my * H - y) < 0.05
    # The lens drew them nearer the middle: a few pixels at the corners.
    assert 3 < abs(drawn[0][1] * H - y0) < 12
    # A corner that falls outside the straightened photograph is at its edge.
    assert lens.moved([(0.0, 0.0), (1.0, 1.0)], W, H, K1) == [(0.0, 0.0), (1.0, 1.0)]
    assert lens.moved([(0.5, 0.5)], W, H, K1) == [(0.5, 0.5)]


def photograph(
    model: str | None = PHONE,
    film: int = 24,
    zoom: float | None = None,
    lens_name: str = "iPhone 18 Pro Max back triple camera 6.93mm f/1.48",
    size: tuple[int, int] = (W, H),
    img: np.ndarray | None = None,
) -> bytes:
    """A JPEG as a phone's camera writes it: what took it in its EXIF."""
    picture = Image.fromarray(img) if img is not None else Image.new("RGB", size, (120, 120, 120))
    out = io.BytesIO()
    if model is None:
        picture.save(out, "JPEG", quality=95)
        return out.getvalue()
    exif = Image.Exif()
    exif[0x010F] = "Apple"
    exif[0x0110] = model
    more = {0xA434: lens_name, 0xA405: film}
    if zoom is not None:
        more[0xA404] = zoom
    exif[0x8769] = more
    picture.save(out, "JPEG", quality=95, exif=exif)
    return out.getvalue()


def test_only_a_lens_that_was_measured_is_taken_out() -> None:
    main = lens.seen(photograph())
    assert main is not None and main.model == PHONE and main.film == 24
    assert main.main and main.bend == K1
    assert lens.seen(photograph(size=(H, W))).bend == K1  # held on its side
    # The long camera, the main one zoomed in the sensor, the one in front.
    assert lens.seen(photograph(film=101, zoom=2.15)).bend is None
    assert lens.seen(photograph(film=48)).bend is None
    assert lens.seen(photograph(zoom=1.5)).bend is None
    front = lens.seen(photograph(lens_name="iPhone 18 Pro Max front camera 2.69mm f/1.9"))
    assert front is not None and front.bend is None
    # Cut since it was taken: its middle is no longer the lens's.
    assert lens.seen(photograph(size=(900, 900))).bend is None
    # Another phone: named, its bend not known.
    other = lens.seen(photograph(model="iPhone 16 Pro Max"))
    assert other is not None and other.model == "iPhone 16 Pro Max" and other.main
    assert other.bend is None
    # No camera named, or no picture at all.
    assert lens.seen(photograph(model=None)) is None
    assert lens.seen(b"not a picture") is None
    assert main.to_json() == {
        "model": PHONE,
        "lens": "iPhone 18 Pro Max back triple camera 6.93mm f/1.48",
        "film": 24.0,
        "main": True,
    }
    assert lens.whole(6048, 8064) and lens.whole(8064, 6048) and lens.whole(5712, 4284)
    assert not lens.whole(1100, 1400) and not lens.whole(0, 0)
