"""The scan of three: reflections taken out of a photograph of a work
behind glass by two more from the sides (Mateusz 2026-11-16)."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from frame_server.imaging import reflections
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


def test_a_hand_in_the_glass_leaves_no_dark_lines_about_its_fingers() -> None:
    """His cows the third time (2026-11-17 00:06 UTC, shown the scan of
    1.145.203: "To dalej nie wygląda idealnie. Czy nie możemy zrobić
    miękkich, daleko sięgających przejść?"): the fingers went, and each
    left a dark line along either side, on the plain dark of a print."""
    scene = _scene()
    rng = np.random.default_rng(3)
    yy, xx = np.mgrid[0:H, 0:W]
    # A plain dark part of the work.
    plain = np.zeros((H, W), bool)
    plain[Y0 + 260 : Y0 + 620, X0 + 150 : X0 + 560] = True
    grain = rng.normal(0, 0.002, (int(plain.sum()), 3)).astype(np.float32)
    scene[plain] = np.float32([0.035, 0.05, 0.08]) + grain
    # A hand: fingers fanning out, sharp at their sides, in the first view alone.
    cx, cy = X0 + 350, Y0 + 640
    turned, far = np.arctan2(xx - cx, cy - yy), np.hypot(xx - cx, yy - cy)
    hand = np.zeros((H, W), np.float32)
    for finger in (-0.5, -0.25, 0.0, 0.25, 0.5):
        there = (np.abs(turned - finger) * far < 9) & (far > 60) & (far < 330)
        hand = np.maximum(hand, there.astype(np.float32))
    hand = cv2.GaussianBlur(hand, (0, 0), 0.8)
    clean = _coded(scene)
    first = _coded(
        scene + _glass(0.02, None, None) + hand[..., None] * np.float32([0.10, 0.07, 0.06])
    )
    left = _coded(_from_side(scene + _glass(0.12, None, None), -1) * 0.9)
    right = _coded(_from_side(scene + _glass(0.10, None, None), 1) * 1.1)
    done = merge(first, [left, right], CORNERS)
    assert done.used == 2

    was, now, is_ = (img.astype(np.float32).mean(-1) for img in (first, done.image, clean))
    within = cv2.erode(plain.astype(np.uint8), np.ones((31, 31), np.uint8)) > 0
    about = (cv2.dilate(hand, np.ones((41, 41), np.uint8)) > 0.5) & within
    left_on = (now - is_)[about]
    left_on = left_on - left_on.mean()
    assert (was - is_)[about].std() > 12
    assert left_on.std() < 4.5
    # No line darker than the print beside a finger (they were 19 levels).
    assert np.percentile(left_on, 1) > -8


def test_a_lamp_goes_whole_where_a_side_view_has_a_window_in_the_glass() -> None:
    """His drawing behind glass (2026-11-17 06:57 UTC, three places
    ringed; "Jest coraz lepiej. Ale myślę że można jeszcze poprawić
    efekt"): the lamp in the first photograph lay where the one from the
    left had a window in the glass. What both side photographs said was
    the lamp's was its red alone, and a green patch stayed. The one from
    the right shows the place as it is."""
    scene = _scene()
    yy, xx = np.mgrid[0:H, 0:W]
    lamp = np.exp(-(((xx - 520) / 45.0) ** 2 + ((yy - 600) / 35.0) ** 2)).astype(np.float32) * 3
    clean = _coded(scene)
    first = _coded(scene + _glass(0.05, None, None) + lamp[..., None])
    left = _coded(_from_side(scene + _glass(0.12, (400, 500, 640, 700), None), -1) * 0.9)
    right = _coded(_from_side(scene + _glass(0.1, None, None), 1) * 1.1)
    done = merge(first, [left, right], CORNERS)
    assert done.used == 2

    burnt = lamp > 1.5
    calm = (slice(900, 1080), slice(300, 520))
    veil = float((done.image[calm].astype(int) - clean[calm]).mean())
    off = done.image[burnt].astype(np.float32) - clean[burnt] - veil
    assert abs(float(off.mean())) < 12
    # In its own colours: no colour of the lamp is left over the others.
    colours = off.mean(0)
    assert float(colours.max() - colours.min()) < 8
    # Nor about it, where the lamp was not yet white.
    about = (lamp > 0.1) & ~burnt
    around = (done.image[about].astype(np.float32) - clean[about] - veil).mean(0)
    assert float(np.abs(around).max()) < 12 and float(around.max() - around.min()) < 8


def test_lines_put_in_under_a_lamp_are_as_pale_as_the_lines_about_it() -> None:
    """The same drawing, shown the plate of the scan after that (2026-11-17
    08:08 UTC, the lamp's place ringed: "Czy „odzyskiwany” z bocznego
    zdjęcia fragment nie mógłby być korygowany kolorystycznie do
    otoczenia? Teraz jeszcze się odcina"). About a lamp the phone presses
    the photograph flat: the pencil lines are pale there. The side
    photographs have them as they are, and put in under the lamp they
    were black among the pale ones."""
    scene = _scene()
    yy, xx = np.mgrid[0:H, 0:W]
    # A sheet with pencil lines across it.
    sheet = np.zeros((H, W), bool)
    sheet[Y0 + 150 : Y1 - 60, X0 + 80 : X1 - 80] = True
    paper = np.float32([0.46, 0.40, 0.30])
    pencil = 1 - 0.55 * np.exp(-(((((xx + yy) % 18) - 9) / 1.6) ** 2))
    scene[sheet] = (paper * pencil[..., None].astype(np.float32))[sheet]
    lamp = np.clip(1.6 - np.hypot((xx - 550) / 110.0, (yy - 620) / 45.0), 0, 1) * 3
    lamp = cv2.GaussianBlur(lamp.astype(np.float32), (0, 0), 3)
    # The first photograph keeps half of its lines about the lamp.
    flat = np.exp(-(((xx - 550) / 260.0) ** 2 + ((yy - 620) / 200.0) ** 2)).astype(np.float32)
    even = cv2.GaussianBlur(scene, (0, 0), 6)
    pressed = even + (scene - even) * (1 - 0.5 * flat[..., None])
    first = _coded(pressed + _glass(0.05, None, None) + lamp[..., None])
    left = _coded(_from_side(scene + _glass(0.03, None, None), -1) * 0.9)
    right = _coded(_from_side(scene + _glass(0.04, None, None), 1) * 1.1)
    done = merge(first, [left, right], CORNERS)
    assert done.used == 2

    def lines(img: np.ndarray) -> np.ndarray:
        grey = img.astype(np.float32).mean(-1)
        return grey - cv2.GaussianBlur(grey, (0, 0), 6)

    burnt = cv2.erode((lamp > 1.5).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    about = (flat > 0.75) & ~(cv2.dilate((lamp > 0.05).astype(np.uint8), np.ones((31, 31))) > 0)
    was, now = lines(first), lines(done.image)
    assert float(was[burnt].std()) < 0.3 * float(was[about].std())
    assert 0.65 < float(now[burnt].std()) / float(now[about].std()) < 1.4
    # And the paper under it is the paper about it.
    tone = cv2.GaussianBlur(done.image.astype(np.float32), (0, 0), 8)
    assert float(np.abs(tone[burnt].mean(0) - tone[about].mean(0)).max()) < 6


def test_what_is_put_in_under_a_lamp_ends_by_degrees_beyond_the_lamp() -> None:
    """And shown that (2026-11-17 08:33 UTC): "Świetnie! Korekta koloru
    bardzo pomogła. A nie możemy delikatnie „wtopić”, rozmyć krawędzi
    wklejanej łatki? Oczywiście na zewnątrz, tak żeby nie pokazać
    chowanej lampy czy odbicia". The patch ended on the lamp's soft edge,
    and what was left of that edge drew the lamp on the paper."""
    ht, wd = 600, 1600
    work = np.full((ht, wd, 3), 0.4, np.float32)
    views = [reflections._View(work.copy(), side) for side in (0, -1, 1)]
    told = [np.zeros((ht, wd, 3), np.float32) for _ in range(2)]
    yy, xx = np.mgrid[0:ht, 0:wd]
    beyond = np.hypot(xx - 800, yy - 300) - 60
    patch = (beyond <= 0).astype(np.float32)[..., None]
    beside = reflections._outward(work, patch, wd * reflections.GLARE_FEATHER)
    wider = reflections._rim(views, told, work, patch, beside)[..., 0]
    out = wd * reflections.GLARE_OUT
    # All of the lamp still, and whole a little beyond it.
    assert float(wider[beyond <= 0].min()) == 1
    assert float(wider[(beyond > 0) & (beyond < 0.7 * out)].min()) > 0.9
    # Then less and less, and nothing further off.
    falling = wider[(beyond > 1.3 * out) & (beyond < 1.7 * out)]
    assert float(falling.min()) > 0.05 and float(falling.max()) < 0.95
    assert float(wider[beyond > 2.3 * out].max()) < 0.01


def test_what_is_put_in_under_a_lamp_does_not_go_over_the_edge_of_a_print() -> None:
    """The cows, each print behind its window in a mount, a lamp on one
    of them near its edge: from the side the print ends a little
    elsewhere under the mount, and what went outward over that edge was a
    pale bite in the print and a grey bar on the mount."""
    ht, wd = 600, 1600
    work = np.full((ht, wd, 3), 0.4, np.float32)
    # The mount begins a few pixels from the lamp.
    work[:, 870:] = 0.8
    views = [reflections._View(work.copy(), side) for side in (0, -1, 1)]
    told = [np.zeros((ht, wd, 3), np.float32) for _ in range(2)]
    yy, xx = np.mgrid[0:ht, 0:wd]
    beyond = np.hypot(xx - 800, yy - 300) - 60
    patch = (beyond <= 0).astype(np.float32)[..., None]
    beside = reflections._outward(work, patch, wd * reflections.GLARE_FEATHER)
    wider = reflections._rim(views, told, work, patch, beside)[..., 0]
    out = wd * reflections.GLARE_OUT
    # Not toward the mount, nor onto it.
    assert float(wider[(beyond > 0) & (xx >= 862)].max()) == 0
    assert not np.isfinite(beside[:, 870:]).any()
    # The other way as ever.
    assert float(wider[(beyond > 0) & (beyond < 0.7 * out) & (xx < 780)].min()) > 0.9


def test_his_own_figure_dark_in_the_glass_leaves_no_outline_on_the_paper() -> None:
    """The same drawing: he stood before it, and the glass mirrored the
    room about his figure and not in it. The even part of that veil
    stays on the work, and it stayed about the figure and not in it: his
    head and shoulders on the paper, a shade darker, with a pale line
    along them."""
    scene = _scene()
    rng = np.random.default_rng(5)
    yy, xx = np.mgrid[0:H, 0:W]
    # A plain sheet where the figure stands.
    sheet = np.zeros((H, W), bool)
    sheet[Y0 + 150 : Y1 - 60, X0 + 80 : X1 - 80] = True
    scene[sheet] = np.float32([0.46, 0.40, 0.30]) + rng.normal(
        0, 0.004, (int(sheet.sum()), 3)
    ).astype(np.float32)
    # Head and shoulders, sharp at the edge.
    head = ((xx - 550) / 110.0) ** 2 + ((yy - 620) / 130.0) ** 2 < 1
    figure = head | ((yy > 720) & (yy < 950) & (np.abs(xx - 550) < 150))
    figure = cv2.GaussianBlur(figure.astype(np.float32), (0, 0), 1.0)
    veil = _glass(0.08, None, None) * (1 - 0.85 * figure[..., None])
    clean = _coded(scene)
    first = _coded(scene + veil)
    left = _coded(_from_side(scene + _glass(0.03, None, None), -1) * 0.9)
    right = _coded(_from_side(scene + _glass(0.04, None, None), 1) * 1.1)
    done = merge(first, [left, right], CORNERS)
    assert done.used == 2

    was, now, is_ = (img.astype(np.float32).mean(-1) for img in (first, done.image, clean))
    within = cv2.erode(sheet.astype(np.uint8), np.ones((41, 41), np.uint8)) > 0
    inside = (cv2.erode(figure, np.ones((25, 25), np.uint8)) > 0.99) & within
    near = cv2.dilate(figure, np.ones((41, 41), np.uint8)) > 0.01
    outside = near & (cv2.dilate(figure, np.ones((25, 25), np.uint8)) < 0.01) & within
    step = float((was - is_)[outside].mean() - (was - is_)[inside].mean())
    assert step > 10
    # Beside the figure the paper is nearer to what it is in it than to
    # what it was: no step, a slow rise to what stays further off.
    assert abs(float((now - is_)[outside].mean() - (now - is_)[inside].mean())) < 0.4 * step
    # And along its edge no line: what is left over is as even as beside.
    edge = (cv2.dilate(figure, np.ones((9, 9), np.uint8)) > 0.01) & ~(
        cv2.erode(figure, np.ones((9, 9), np.uint8)) > 0.99
    )
    edge &= within
    left_on = cv2.GaussianBlur(now - is_, (0, 0), 1.5)
    assert left_on[edge].std() < 2.5
    # Far from him the even veil stays as before.
    calm = (slice(Y0 + 40, Y0 + 120), slice(X0 + 40, X0 + 160))
    assert float((now - is_)[calm].mean()) > 0.5 * float((was - is_)[calm].mean())


def test_a_lamp_and_his_figure_in_the_first_photograph_do_not_set_the_side_ones_light() -> None:
    """His pencil drawing behind glass, scanned in one arc (2026-11-18
    16:11 UTC: "w Test i Test 4 które są za szybą mogłoby być lepiej"): a
    lamp burnt into the first photograph and his own figure dark in the
    glass. The strongest steps of the first were the lamp's rim and the
    figure's outline, which no side photograph has, and the side ones'
    exposure and white balance were told by those: a half and a sixth of
    what they were. The lamp stayed as a pale patch with green lines."""
    rng = np.random.default_rng(5)
    yy, xx = np.mgrid[0:600, 0:900]
    # Pale pencil lines on a sheet.
    pencil = 1 - 0.35 * np.exp(-(((((xx + yy) % 40) - 20) / 2.5) ** 2))
    work = np.float32([0.46, 0.40, 0.30]) * pencil[..., None].astype(np.float32)
    work += rng.normal(0, 0.003, work.shape).astype(np.float32)
    lamp = (np.hypot((xx - 300) / 150.0, (yy - 200) / 40.0) < 1).astype(np.float32)
    lamp = cv2.GaussianBlur(lamp, (0, 0), 2.0)[..., None]
    figure = ((np.abs(xx - 600) < 120) & (yy > 250)).astype(np.float32)
    figure = cv2.GaussianBlur(figure, (0, 0), 2.0)[..., None]
    first = np.clip(work + 0.12 * (1 - 0.85 * figure) + 3 * lamp, 0, 1).astype(np.float32)
    # The side photographs: lighter, and in another white balance.
    lighter = np.float32([1.2, 1.3, 1.4])
    views = [
        reflections._View(first, 0),
        reflections._View(work * lighter, -1),
        reflections._View(work * lighter * 0.8, 1),
    ]
    reflections._even(views)
    for view in views[1:]:
        assert np.abs(np.median(view.light / work, (0, 1)) - 1).max() < 0.05


def test_the_room_in_the_glass_all_over_one_side_view_is_no_doubt() -> None:
    """His Nikifor behind glass (the same day, "Test 4"): from the left
    the glass was clean, from the right the bright room was all over it,
    more light than the dark work has. The two differed nearly
    everywhere, which was taken for a work that is no flat one, and the
    one photograph with its reflections was proposed. A reflection only
    adds light: the work is what the darker one shows."""
    rng = np.random.default_rng(7)
    ht, wd = 900, 700
    work = cv2.resize(
        rng.uniform(0.01, 0.15, (30, 24, 3)).astype(np.float32),
        (wd, ht),
        interpolation=cv2.INTER_CUBIC,
    )
    work = np.clip(work + rng.normal(0, 0.005, work.shape).astype(np.float32), 0.005, 0.4)

    def room(seed: int) -> np.ndarray:
        light = np.random.default_rng(seed).uniform(0.02, 0.45, (9, 7, 3)).astype(np.float32)
        return np.clip(cv2.resize(light, (wd, ht), interpolation=cv2.INTER_CUBIC), 0.02, None)

    def differ(left: np.ndarray, right: np.ndarray) -> float:
        views = [reflections._View(work + 0.06, 0)]
        views += [reflections._View(left, -1), reflections._View(right, 1)]
        return reflections._alone(views)[2]

    assert differ(work + 0.02, work + room(9)) <= reflections.NOT_ONE
    # A mirror shows each of them another room: that is no flat work.
    assert differ(room(8), room(9)) > reflections.NOT_ONE


def test_a_lamp_that_reaches_the_frame_goes_to_its_end() -> None:
    """His drawing and his Nikifor, each with a lamp in the glass that
    reached the frame (2026-11-18 17:39 UTC, shown what was made of them:
    "znowu pokazują się ostre krawędzie w miejscach podmian"). Along the
    frame the side photograph taken from there does not show the work,
    and where one does not, nothing was the first's alone: the lamp's end
    stayed there, cut off straight where that photograph begins to
    count. The other one shows the place."""
    scene = _scene()
    yy, xx = np.mgrid[0:H, 0:W]
    lamp = np.exp(-(((xx - X0 - 10) / 70.0) ** 2 + ((yy - 600) / 35.0) ** 2)).astype(np.float32) * 3
    lamp[:, :X0] = 0
    clean = _coded(scene)
    first = _coded(scene + _glass(0.05, None, None) + lamp[..., None])
    left = _coded(_from_side(scene + _glass(0.12, None, None), -1) * 0.9)
    right = _coded(_from_side(scene + _glass(0.1, None, None), 1) * 1.1)
    done = merge(first, [left, right], CORNERS)
    assert done.used == 2

    calm = (slice(900, 1080), slice(300, 520))
    veil = float((done.image[calm].astype(int) - clean[calm]).mean())
    # By the frame, beyond what cleaning about the work's edge softens.
    end = (lamp > 1.5) & (xx > X0 + 6) & (xx < X0 + 40)
    assert (first[end] > 250).mean() > 0.95
    off = done.image[end].astype(np.float32) - clean[end] - veil
    assert abs(float(off.mean())) < 14 and float((done.image[end] > 250).mean()) < 0.02


def test_under_a_lamp_the_work_is_as_fine_as_the_side_photographs_have_it() -> None:
    """Shown his drawing with the lamp taken out (2026-11-18 17:41 UTC):
    "wklejki są niższej jakości…". The views are a third of the first
    photograph's size, and the work put in under a lamp was the views':
    soft among the first's sharp lines. The side photographs are larger."""
    rng = np.random.default_rng(3)
    ht, wd = 300, 400
    # Lines finer than the views can show, in photographs twice their size.
    yy, xx = np.mgrid[0 : 2 * ht, 0 : 2 * wd]
    light = 0.4 + 0.15 * np.sin(xx * 2.2 + yy * 0.3) + rng.normal(0, 0.005, (2 * ht, 2 * wd))
    photo = _coded(np.repeat(light[..., None], 3, -1).astype(np.float32))
    whole = reflections._linear(photo)
    small = cv2.resize(whole, (wd, ht), interpolation=cv2.INTER_AREA)
    at = np.mgrid[0:ht, 0:wd].astype(np.float32)
    seen = np.stack([(at[1] + 0.5) * 2 - 0.5, (at[0] + 0.5) * 2 - 0.5], -1)
    views = [reflections._View(small.copy(), 0)]
    views += [reflections._View(small.copy(), side, photo=photo, seen=seen) for side in (-1, 1)]
    told = [np.zeros((ht, wd, 3), np.float32) for _ in range(2)]
    finer = reflections._finer(views, told, small)

    to_part = np.array([[2, 0, 0.5], [0, 2, 0.5], [0, 0, 1]], np.float64)
    plain = cv2.warpPerspective(small, to_part, (2 * wd, 2 * ht), flags=cv2.INTER_CUBIC)
    more = finer(to_part, np.ones((2 * ht, 2 * wd), np.float32))
    inner = (slice(100, 500), slice(200, 600))
    soft = float(np.abs(plain - whole)[inner].mean())
    assert soft > 0.03
    assert float(np.abs(plain + more - whole)[inner].mean()) < 0.2 * soft
    # Nothing where there is no glare.
    part = np.zeros((2 * ht, 2 * wd), np.float32)
    part[200:300, 300:500] = 1
    more = finer(to_part, part)
    assert not more[:200].any() and not more[:, :300].any() and more[200:300, 300:500].any()


def _relief() -> tuple[np.ndarray, list[np.ndarray]]:
    """Three photographs of a work that is no flat one: each shows its
    own picture in every other tile of it (a mirror, a shine on foil)."""
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
    return first, [left, right]


def test_views_that_do_not_show_one_flat_work_change_nothing_unless_asked() -> None:
    """His collage of a mirror, foil and a circuit board in relief
    (2026-11-16 19:00 UTC): each photograph shows another thing in the
    mirror and another shine on the foil. No reflection can be told from
    the work there, and what was made of the three was worse than the
    one photograph.

    Asked for all the same it is made, in doubt, for him to choose
    between the two with the one photograph proposed (2026-11-17 22:43
    UTC: "wybór pomiędzy obrazem składanym (inteligentnym) a z
    pojedynczego zdjęcia - zawsze go dawaj, a w sytuacji gdzie
    podejrzewasz płaskorzeźbę albo dzieło które wymaga pojedynczego
    zdjęcia ustawiaj je jako domyślne")."""
    first, sides = _relief()
    done = merge(first, sides, CORNERS)
    assert done.used == 2 and done.removed == 0 and done.image is first and done.doubt

    made = merge(first, sides, CORNERS, anyway=True)
    assert made.used == 2 and made.removed > 0 and made.doubt
    assert made.image is not first and made.image.shape == first.shape
    assert np.abs(made.image.astype(int) - first).mean() > 0.5

    # A flat work behind glass is in no doubt, asked for anyway or not.
    _, glass, beside = _three()
    plain, asked = merge(glass, beside, CORNERS), merge(glass, beside, CORNERS, anyway=True)
    assert not plain.doubt and not asked.doubt
    assert plain.removed == asked.removed and np.array_equal(plain.image, asked.image)


def test_a_side_view_of_a_work_that_is_no_plane_is_laid_on_the_first_place_by_place(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """His small oil on canvas in a floating frame (2026-11-17 16:04 UTC:
    "czy najpierw nie trzeba dokładnie nanieść poszczególnych zdjęć na
    siebie a dopiero potem robić dalsze edycje? Tutaj obraz jakby się
    rozjeżdżał"): one homography left the side views 4 to 7 pixels off
    the first, 22 at the edges, and every stroke that lay elsewhere was
    taken for a reflection. A canvas that bulges, seen from the side,
    lies on the first to a fraction of a pixel all the same."""
    scene = _scene()
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    # Seen from the side the middle of the canvas stands out of its plane.
    bulge = 9 * np.exp(-(((xx - 480) / 260) ** 2 + ((yy - 640) / 330) ** 2))
    bulged = cv2.remap(scene, xx + bulge, yy + 0.4 * bulge, cv2.INTER_CUBIC)
    photo = _coded(_from_side(bulged, -1))
    front = _coded(scene)[Y0:Y1, X0:X1]
    marks = reflections._marks(front)

    def off(view: reflections._View | None) -> np.ndarray:
        assert view is not None and view.side == -1
        fine = reflections._fine(reflections._linear(front))
        said = reflections._off(fine, reflections._fine(view.light), 128)
        return np.hypot(said[..., 0], said[..., 1])

    settled = off(reflections._lay(front, marks, photo))
    assert settled.max() < 0.5
    monkeypatch.setattr(reflections, "SETTLE_TILES", ())
    assert off(reflections._lay(front, marks, photo)).max() > 3


def test_a_square_with_a_reflection_in_it_does_not_say_where_a_side_view_lies() -> None:
    """A window in the glass has edges of its own, elsewhere in every
    view: the square it fills says another thing than the squares about
    it, and a square of bare paper says nothing. Both are told by those
    about them."""
    off = np.zeros((9, 7, 3), np.float32)
    off[..., 0], off[..., 1], off[..., 2] = 2.0, -1.0, 0.9
    off[4, 3] = (20.0, 15.0, 0.9)  # a window's edge
    off[1:3, 1:3, 2] = 0.02  # bare paper
    off[1:3, 1:3, :2] = (-30.0, 40.0)
    field = reflections._field(off, 64, (320, 256))
    assert field is not None and field.shape == (2, 320, 256)
    assert np.abs(field[0] - 2.0).max() < 0.05 and np.abs(field[1] + 1.0).max() < 0.05
    off[..., 2] = 0.02
    assert reflections._field(off, 64, (320, 256)) is None


def _doorway() -> tuple[np.ndarray, np.ndarray, np.ndarray, list[reflections._View]]:
    """A work behind glass, the views' size: what it is, what is left on
    the first view once a lit doorway in the glass over its left came
    off, the layer that came off, and the views (the one from the left
    clean, the one from the right with the room all over it)."""
    rng = np.random.default_rng(11)
    ht, wd = 420, 600
    blocks = rng.uniform(0.1, 0.5, (14, 20, 3)).astype(np.float32)
    work = cv2.resize(blocks, (wd, ht), interpolation=cv2.INTER_CUBIC)
    work += rng.normal(0, 0.004, work.shape).astype(np.float32)
    soft = np.zeros_like(work)
    soft[110:330, :160] = (0.3, 0.27, 0.24)
    left_on = np.zeros_like(work)
    left_on[110:330, :160] = (0.05, 0.04, 0.03)
    room = cv2.resize(rng.uniform(0.08, 0.2, (5, 7, 3)).astype(np.float32), (wd, ht))
    views = [
        reflections._View(work + soft + left_on, 0),
        reflections._View(work * 1.02, -1, hidden=0.06, shows=0.035),
        reflections._View(work + room, 1, hidden=0.06, shows=0.035),
    ]
    return work, left_on, soft, views


def test_under_a_veil_in_the_glass_the_tone_is_what_the_side_views_show() -> None:
    """His Nikifor behind glass (2026-11-18 18:13 UTC: "Teraz nadal widać
    odcięcie"; 18:19: "Problemem jest chyba tonacja i kolorystyka na
    łączeniu. Istotne jest wyrównanie nie tylko fragmentami, ale
    względem nakładanych, półprzejrzystych obszarów"): a lit doorway in
    the glass over the left of the sky. Taken off, the sky under it
    stayed paler than the sky beside it, with the doorway's edge between
    them. What stayed comes off by what the side views show there, up to
    the frame (where only the view with the room in the glass counts),
    and nothing comes off where no veil was."""
    work, left_on, soft, views = _doorway()
    none = np.zeros_like(work)
    off, fine = reflections._veiled(work + left_on, soft, views, none)
    inside = (slice(130, 310), slice(40, 140))
    assert np.abs(off[inside] - left_on[inside]).mean() < 0.006
    # The strip along the frame, which the view from the left does not show.
    strip = (slice(130, 310), slice(8, 20))
    assert np.abs(off[strip] - left_on[strip]).mean() < 0.012
    assert np.abs(off[:, 260:]).max() < 0.004
    # Where the veil is as light as the work under it their fine goes in too.
    dark = cv2.GaussianBlur((work + left_on).mean(-1), (0, 0), 6.0)[inside] < 0.24
    assert dark.any() and fine[inside][dark].min() > 0.9 and fine[:, 260:].max() == 0

    # Two photographs say nothing of it.
    assert not reflections._veiled(work + left_on, soft, views[:2], none)[0].any()


def test_under_a_heavy_veil_the_picture_is_the_side_views() -> None:
    """The doorway's edge ran down through a tree: the half of the tree
    under it was a ghost of the other half, the phone having pressed
    what it saw through the veil flat. What is wider than the fine of
    the work is the side views' there."""
    work, left_on, soft, views = _doorway()
    flat = work + left_on
    under = flat[110:330, :160]
    flat[110:330, :160] = under.mean((0, 1)) + (under - under.mean((0, 1))) * 0.5
    off, _ = reflections._veiled(flat, soft, views, np.zeros_like(work))
    inside = (slice(130, 310), slice(40, 140))

    def wide(of: np.ndarray) -> np.ndarray:
        return cv2.GaussianBlur(of, (0, 0), 3.0)[inside]

    assert np.abs(wide(flat - work)).mean() > 0.04
    assert np.abs(wide(flat - off - work)).mean() < 0.008


def test_the_sheen_of_an_oil_is_no_veil_in_glass() -> None:
    """His oil portraits (2026-11-18 16:11 UTC: "Na olejach nie jest
    źle"): the sheen of the varnish is a large share of the dark paint's
    light nearly everywhere, and lies on the paint's grain. Held a veil,
    it made the portrait the side views' picture, a hand gone from pink
    to ochre. Unless it is strong in itself, it is left as it is."""
    work, left_on, soft, views = _doorway()
    dark = work * 0.2
    views = [reflections._View(v.light - work + dark, v.side, v.hidden, v.shows) for v in views]
    sheen = np.full_like(work, 0.7)
    for layer in (soft * 0.15, soft):
        off, fine = reflections._veiled(dark + left_on, layer, views, sheen)
        assert not off.any() and not fine.any()
    # Gouache behind glass has a grain too, here and there: a sheen on
    # it at the top of the doorway, and the doorway is a veil all the
    # same, being as light as it is; a weak layer there is the grain's.
    sheen[:] = 0
    sheen[110:170, :160] = 0.7
    off, _ = reflections._veiled(dark + left_on, soft, views, sheen)
    assert np.abs(off[130:310, 40:140] - left_on[130:310, 40:140]).mean() < 0.01
    off, _ = reflections._veiled(dark + left_on, soft * 0.15, views, sheen)
    assert np.abs(off[125:150, 40:140]).max() < 0.004
    assert np.abs(off[240:310, 40:140] - left_on[240:310, 40:140]).mean() < 0.01


def test_a_side_view_shows_the_works_tone_from_where_its_lines_are_the_others() -> None:
    """Along the frame's side it was taken from a side view counts for
    nothing (:data:`reflections.HIDDEN`), and there only the other one
    says what the work is. On his Nikifor that other one had the room in
    the glass, and the strip by the frame stayed pale. The frame's side
    hid three hundredths of the width, not six: from where the view's
    lines are the other views' its tone is the work's."""
    rng = np.random.default_rng(5)
    ht, wd = 300, 400
    lines = cv2.GaussianBlur(rng.uniform(0.1, 0.6, (ht, wd, 1)).astype(np.float32), (0, 0), 1.5)
    work = np.repeat(lines.reshape(ht, wd, 1), 3, -1)
    left = work.copy()
    # The frame's side, with a grain of its own, over the first of it.
    left[:, :12] = 0.3 + rng.normal(0, 0.05, (ht, 12, 1)).astype(np.float32)
    views = [reflections._View(work.copy(), 0), reflections._View(left, -1)]
    views.append(reflections._View(work + 0.1, 1))
    reflections._hide(views)
    assert views[1].hidden == reflections.HIDDEN
    assert 0.03 <= views[1].shows <= 0.05
    assert views[2].hidden == views[2].shows == reflections.HIDDEN_SHOWN
    tone = reflections._counts(views, ht, wd, tone=True)
    whole = reflections._counts(views, ht, wd)
    assert tone[1][:, 28].min() == 1 and whole[1][:, 28].max() < 0.5
    assert tone[1][:, :10].max() == 0
