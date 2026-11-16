"""The scan of three: reflections taken out of a photograph of a work
behind glass by two more from the sides (Mateusz 2026-11-16)."""

from __future__ import annotations

import cv2
import numpy as np

from frame_server.imaging.reflections import grown, merge

H, W = 1400, 1100
#: The work on the wall, in the first photograph.
X0, X1, Y0, Y1 = 200, 900, 250, 1150
CORNERS = [(X0 / W, Y0 / H), (X1 / W, Y0 / H), (X1 / W, Y1 / H), (X0 / W, Y1 / H)]


def _coded(light: np.ndarray) -> np.ndarray:
    light = np.clip(light, 0, 1)
    coded = np.where(light <= 0.0031308, light * 12.92, 1.055 * light ** (1 / 2.4) - 0.055)
    return (coded * 255 + 0.5).astype(np.uint8)


def _scene() -> np.ndarray:
    """A wall with a work on it, in linear light."""
    rng = np.random.default_rng(7)
    wall = np.full((H, W, 3), 0.35, np.float32) + rng.normal(0, 0.01, (H, W, 3)).astype(np.float32)
    blocks = rng.uniform(0.02, 0.55, (30, 24, 3)).astype(np.float32)
    work = cv2.resize(blocks, (X1 - X0, Y1 - Y0), interpolation=cv2.INTER_CUBIC)
    work += rng.normal(0, 0.03, work.shape).astype(np.float32)
    wall[Y0:Y1, X0:X1] = np.clip(work, 0.01, 0.7)
    return wall


def _glass(veil: float, window: tuple[int, int, int, int] | None, lamp: tuple[int, int] | None):
    """What the glass over the work mirrors: a veil all over it, a
    window's sharp reflection, a lamp's soft one."""
    light = np.zeros((H, W, 3), np.float32)
    light[Y0:Y1, X0:X1] = veil
    if window is not None:
        x0, y0, x1, y1 = window
        light[y0:y1, x0:x1] += np.float32([0.30, 0.33, 0.38])
    if lamp is not None:
        yy, xx = np.mgrid[0:H, 0:W]
        blob = np.exp(-(((xx - lamp[0]) / 120) ** 2 + ((yy - lamp[1]) / 90) ** 2)) * 0.45
        inside = np.zeros((H, W), np.float32)
        inside[Y0:Y1, X0:X1] = 1
        light += (blob * inside)[..., None].astype(np.float32)
    return light


def _from_side(light: np.ndarray, lean: int) -> np.ndarray:
    """The photograph as taken from a side: the near side of it taller."""
    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    if lean < 0:  # from the left
        dst = np.float32([[60, 0], [W - 160, 90], [W - 160, H - 90], [60, H]])
    else:
        dst = np.float32([[160, 90], [W - 60, 0], [W - 60, H], [160, H - 90]])
    return cv2.warpPerspective(
        light, cv2.getPerspectiveTransform(src, dst), (W, H), borderValue=(0.3, 0.3, 0.3)
    )


def _three() -> tuple[np.ndarray, np.ndarray, list[np.ndarray]]:
    scene = _scene()
    first = _coded(scene + _glass(0.14, None, (520, 600)))
    left = _coded(_from_side(scene + _glass(0.03, (560, 300, 860, 620), None), -1) * 0.9)
    right = _coded(_from_side(scene + _glass(0.04, None, (300, 950)), 1) * 1.1)
    return _coded(scene), first, [left, right]


def test_the_veil_and_what_the_glass_mirrors_go_from_the_work() -> None:
    """Mateusz's print behind glass: a veil over all of it in the first
    photograph and his own figure in the middle; the side ones have less
    veil and reflections of their own elsewhere. What comes out is the
    first photograph without them, every other pixel of it untouched."""
    clean, first, sides = _three()
    done = merge(first, sides, CORNERS)
    assert done.used == 2 and 0.1 < done.removed < 0.6

    inner = (slice(Y0 + 40, Y1 - 40), slice(X0 + 60, X1 - 60))
    before = np.abs(first[inner].astype(int) - clean[inner]).mean()
    after = np.abs(done.image[inner].astype(int) - clean[inner]).mean()
    assert before > 30 and after < before / 3
    # The lamp's place is no worse than the rest.
    lamp = (slice(540, 660), slice(440, 600))
    assert np.abs(done.image[lamp].astype(int) - clean[lamp]).mean() < before / 3
    # The window one side photograph had mirrored has left nothing.
    window = (slice(320, 600), slice(580, 840))
    assert np.abs(done.image[window].astype(int) - clean[window]).mean() < before / 3
    # The first photograph's own grain stays: only something smooth went.
    took = first[inner].astype(np.float32) - done.image[inner]
    assert np.abs(took - cv2.GaussianBlur(took, (0, 0), 3)).mean() < 2.5

    # Beyond what is cleaned around the work nothing is touched.
    around = np.zeros((H, W), np.uint8)
    cv2.fillConvexPoly(around, np.round(grown(CORNERS) * [W, H]).astype(np.int32), 1)
    far = cv2.dilate(around, np.ones((41, 41), np.uint8)) == 0
    assert (done.image[far] == first[far]).all()


def test_photographs_of_something_else_or_nothing_to_take_change_nothing() -> None:
    clean, first, _ = _three()
    rng = np.random.default_rng(3)
    other = rng.integers(0, 255, (H, W, 3), dtype=np.uint8)
    done = merge(first, [other], CORNERS)
    assert done.used == 0 and done.removed == 0 and done.image is first
    # Three alike: no reflection one has and another has not.
    same = merge(clean, [clean, clean], CORNERS)
    assert same.used == 2 and same.removed == 0 and same.image is clean
    # No work to speak of between the corners.
    tiny = [(0.5, 0.5), (0.52, 0.5), (0.52, 0.52), (0.5, 0.52)]
    assert merge(first, [first], tiny).image is first
