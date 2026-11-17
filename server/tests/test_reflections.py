"""The scan of three: reflections taken out of a photograph of a work
behind glass by two more from the sides (Mateusz 2026-11-16)."""

from __future__ import annotations

import cv2
import numpy as np

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
