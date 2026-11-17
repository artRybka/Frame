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


def test_what_the_glass_mirrors_goes_from_the_work_and_its_even_veil_stays() -> None:
    """Mateusz's print behind glass: a veil over all of it in the first
    photograph and his own figure in the middle; the side ones have less
    veil and reflections of their own elsewhere. What comes out is the
    first photograph without what had a shape, every other pixel of it
    untouched. The veil that is even over the whole work stays ("Skany
    wychodzą chyba odrobinę zbyt kontrastowe i ciemne?", 2026-11-16
    16:44 UTC: taken off, it left his paintings darker than they are)."""
    clean, first, sides = _three()
    done = merge(first, sides, CORNERS)
    assert done.used == 2 and 0.03 < done.removed < 0.6

    def over(img: np.ndarray, where: tuple[slice, slice]) -> float:
        """How much lighter than the work itself."""
        return float((img[where].astype(int) - clean[where]).mean())

    inner = (slice(Y0 + 40, Y1 - 40), slice(X0 + 60, X1 - 60))
    # Where the first photograph had its veil alone.
    calm = (slice(900, 1080), slice(300, 520))
    veil = over(first, calm)
    assert veil > 25 and over(done.image, calm) > veil * 0.8
    # The lamp's place is as the rest.
    lamp = (slice(540, 660), slice(440, 600))
    assert over(first, lamp) > veil + 40
    assert abs(over(done.image, lamp) - over(done.image, calm)) < 4
    # The window one side photograph had mirrored has left nothing.
    window = (slice(320, 600), slice(580, 840))
    assert abs(over(done.image, window) - over(done.image, calm)) < 4
    # Nowhere lighter than it was.
    assert over(done.image, inner) < over(first, inner)
    assert (done.image[inner].astype(int) <= first[inner].astype(int) + 1).all()
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


def test_the_shine_of_the_work_itself_is_no_reflection() -> None:
    """His dark folder with gold letters, lying on a desk without glass
    (2026-11-16, "efekt wychodzi nazbyt kontrastowy i zbyt nasycony"):
    the letters shine from the front and not from the sides, the cover a
    little. That is how the work looks: it came out black, with a blacker
    halo about each letter and patches of colour."""
    scene = _scene()
    ground = (slice(Y0 + 420, Y1 - 60), slice(X0 + 60, X1 - 60))
    rng = np.random.default_rng(11)
    dark = np.float32([0.012, 0.013, 0.02]) + rng.normal(0, 0.001, (*scene[ground].shape[:2], 3))
    scene[ground] = dark.astype(np.float32)
    letters = np.zeros((H, W), bool)
    for x in range(X0 + 100, X1 - 100, 36):
        letters[Y0 + 470 : Y1 - 110, x : x + 3] = True
    for y in range(Y0 + 480, Y1 - 120, 90):
        letters[y : y + 3, X0 + 100 : X1 - 100] = True

    def seen(gold: tuple[float, float, float], sheen: float) -> np.ndarray:
        light = scene.copy()
        light[ground] += sheen
        light[letters] = np.float32(gold)
        return light

    first = _coded(seen((0.45, 0.34, 0.12), 0.004))
    left = _coded(_from_side(seen((0.26, 0.24, 0.2), 0.0), -1) * 0.95)
    right = _coded(_from_side(seen((0.3, 0.25, 0.16), 0.001), 1) * 1.05)
    done = merge(first, [left, right], CORNERS)
    assert done.used == 2

    cover = np.zeros((H, W), bool)
    cover[ground] = True
    near = cv2.dilate(letters.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool)
    beside = (
        cover & near & ~cv2.dilate(letters.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    )
    before, after = first.astype(np.float32), done.image.astype(np.float32)
    # No halo: the cover beside a letter is as it is away from one.
    away = cover & ~near
    assert after[beside].mean() > after[away].mean() * 0.88
    # The cover is not made black, nor its colour another.
    assert after[away].mean() > before[away].mean() * 0.75
    assert np.percentile(after[away], 2) > np.percentile(before[away], 2) * 0.6
    was, now = before[away].mean(0), after[away].mean(0)
    assert np.abs(now / now.mean() - was / was.mean()).max() < 0.1
    # The letters keep their gold.
    assert after[letters].mean() > before[letters].mean() * 0.9


def test_a_sheen_on_the_paint_goes_from_its_ridges_and_no_furrow_goes_black() -> None:
    """His oil portrait without glass (2026-11-16 19:01 UTC, "chyba działa
    zbyt punktowo i z ostrym odcięciem"): the window's sheen lies on the
    ridges of the paint and not in the furrows between them. Taken off
    every place alike it left the furrows black and the ridges shining."""
    scene = _scene()
    # Strokes of paint: a ridge every sixteen pixels, a furrow between.
    ridge = np.zeros((H, W), bool)
    ridge[:, (np.arange(W) % 16) < 8] = True
    work = np.zeros((H, W), bool)
    work[Y0:Y1, X0:X1] = True
    scene[work & ~ridge] *= 0.45
    lit = np.zeros((H, W), bool)
    lit[Y0 + 150 : Y0 + 500, X0 + 120 : X0 + 520] = True
    sheen = np.zeros((H, W, 3), np.float32)
    sheen[lit & ridge] = np.float32([0.2, 0.22, 0.25])
    sheen = cv2.GaussianBlur(sheen, (0, 0), 0.8)
    clean = _coded(scene)
    first = _coded(scene + sheen)
    left = _coded(_from_side(scene, -1) * 0.95)
    right = _coded(_from_side(scene, 1) * 1.05)
    done = merge(first, [left, right], CORNERS)
    assert done.used == 2 and done.removed > 0.02

    inner = cv2.erode(lit.astype(np.uint8), np.ones((41, 41), np.uint8)).astype(bool)
    furrow = inner & ~cv2.dilate(ridge.astype(np.uint8), np.ones((1, 3), np.uint8)).astype(bool)
    top = inner & cv2.erode(ridge.astype(np.uint8), np.ones((1, 3), np.uint8)).astype(bool)
    was, now, is_ = (img.astype(np.float32) for img in (first, done.image, clean))
    # The sheen is mostly gone from the ridges.
    assert (now[top] - is_[top]).mean() < (was[top] - is_[top]).mean() * 0.5
    # And the furrows are as dark as they are, no darker.
    assert now[furrow].mean() > is_[furrow].mean() * 0.85
    assert np.percentile(now[furrow], 2) > np.percentile(is_[furrow], 2) * 0.6


def test_under_a_lamp_that_burnt_the_photograph_the_work_is_what_the_sides_tell() -> None:
    """His sixteen cows behind glass (2026-11-16 18:16 UTC): the lamp in
    the glass had burnt the first photograph white over one of them, and
    nothing of the work was left under it to keep; taken off, it left a
    patch of colour. Both side photographs show the cow whole."""
    scene = _scene()
    yy, xx = np.mgrid[0:H, 0:W]
    lamp = np.exp(-(((xx - 520) / 45.0) ** 2 + ((yy - 600) / 35.0) ** 2)).astype(np.float32) * 3
    clean = _coded(scene)
    first = _coded(scene + _glass(0.05, None, None) + lamp[..., None])
    left = _coded(_from_side(scene + _glass(0.12, None, None), -1) * 0.9)
    right = _coded(_from_side(scene + _glass(0.1, None, None), 1) * 1.1)
    done = merge(first, [left, right], CORNERS)
    assert done.used == 2

    burnt = lamp > 1.5
    assert (first[burnt] > 250).mean() > 0.95
    calm = (slice(900, 1080), slice(300, 520))
    veil = float((done.image[calm].astype(int) - clean[calm]).mean())
    off = done.image[burnt].astype(np.float32) - clean[burnt] - veil
    # The work is there again, in its own colours (grain and all it is
    # not: the side photographs are smaller).
    assert abs(float(off.mean())) < 12
    assert (
        np.abs(cv2.GaussianBlur(done.image.astype(np.float32) - clean - veil, (0, 0), 4))[
            burnt
        ].mean()
        < 14
    )


def test_a_finger_in_the_glass_goes_from_the_lines_and_the_dark_as_from_beside_them() -> None:
    """His sixteen cows scanned again (2026-11-16 22:30 UTC, three places
    ringed; "Odbicia w szybie - jest lepiej, ale przejście powinno być
    jeszcze łagodniejsze"): his hand in the glass went from the sky about
    a cow and stayed on her, in patches, and a finger stayed over the
    dark of a print."""
    scene = _scene()
    yy, xx = np.mgrid[0:H, 0:W]
    # A drawing in black lines on the work.
    drawn = np.zeros((H, W), bool)
    drawn[Y0 + 300 : Y0 + 500, X0 + 230 : X0 + 470] = True
    lines = drawn & (((xx + yy) % 7 < 2) | ((xx - yy) % 11 < 2))
    scene[lines] *= 0.08
    # A finger: a narrow band down the glass, in the first view alone.
    band = np.exp(-(((xx - (X0 + 330 + (yy - Y0) * 0.15)) / 9.0) ** 4)).astype(np.float32)
    band[: Y0 + 120] = 0
    band[Y1 - 80 :] = 0
    finger = band[..., None] * np.float32([0.10, 0.07, 0.06])
    clean = _coded(scene)
    first = _coded(scene + _glass(0.02, None, None) + finger)
    left = _coded(_from_side(scene + _glass(0.12, None, None), -1) * 0.9)
    right = _coded(_from_side(scene + _glass(0.10, None, None), 1) * 1.1)
    done = merge(first, [left, right], CORNERS)
    assert done.used == 2

    was, now, is_ = (img.astype(np.float32) for img in (first, done.image, clean))
    calm = (slice(Y0 + 600, Y0 + 800), slice(X0 + 450, X0 + 650))
    veil = float((now[calm] - is_[calm]).mean())
    on = band > 0.9
    grey = is_.mean(-1)
    dark = on & ~drawn & (grey < np.percentile(grey[on & ~drawn], 25))

    def left_of(where: np.ndarray) -> float:
        added = float((was[where] - is_[where]).mean() - (was[calm] - is_[calm]).mean())
        return (float((now[where] - is_[where]).mean()) - veil) / added

    assert left_of(on & ~drawn) < 0.08
    assert left_of(on & drawn & ~lines) < 0.1
    assert left_of(dark) < 0.15
    # And beside it the work is as it was.
    beside = (band < 0.01) & (cv2.GaussianBlur(band, (0, 0), 12) > 0.05)
    assert abs(float((now[beside] - is_[beside]).mean()) - veil) < 3


def test_views_that_do_not_show_one_flat_work_change_nothing() -> None:
    """His collage of a mirror, foil and a circuit board in relief
    (2026-11-16 19:00 UTC): each photograph shows another thing in the
    mirror and another shine on the foil. No reflection can be told from
    the work there, and what was made of the three was worse than the
    one photograph."""
    scene = _scene()

    def seen(seed: int) -> np.ndarray:
        rng = np.random.default_rng(seed)
        light = scene.copy()
        # Its own picture in every other tile of the work.
        own = cv2.resize(
            rng.uniform(0.02, 0.7, (18, 14, 3)).astype(np.float32),
            (X1 - X0, Y1 - Y0),
            interpolation=cv2.INTER_NEAREST,
        )
        tiles = (np.add.outer(np.arange(Y1 - Y0) // 50, np.arange(X1 - X0) // 50) % 2) == 0
        light[Y0:Y1, X0:X1][tiles] = own[tiles]
        return light

    first = _coded(seen(1))
    left = _coded(_from_side(seen(2), -1) * 0.95)
    right = _coded(_from_side(seen(3), 1) * 1.05)
    done = merge(first, [left, right], CORNERS)
    assert done.used == 2 and done.removed == 0 and done.image is first
