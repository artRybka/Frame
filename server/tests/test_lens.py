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
from pytest import approx

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


def table(k1: float = K1, count: int = 42, centre: tuple[float, float] = (0.5, 0.5)) -> list[float]:
    """What a camera whose lens has the bend ``k1`` says of it for a
    photograph (Apple's ``lensDistortionLookupTable``): how much further
    out a point is drawn, at ``count`` radii evenly from the lens's
    middle to the photograph's farthest corner from it."""
    cx, cy = centre[0] * W, centre[1] * H
    reach = math.hypot(max(cx, W - cx), max(cy, H - cy))
    half = math.hypot(W, H) / 2
    return [float(k1 * (i / (count - 1) * reach / half) ** 2) for i in range(count)]


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


def test_the_cameras_own_table_takes_the_bend_out_as_the_measured_number_does() -> None:
    """Mateusz 2026-11-19 08:09 UTC: "Korekta obiektywu - a nie ma
    natywnego rozwiązania od Apple w tym zakresie?". The camera's table
    of a photograph says how its lens bent it; a table that says what
    the one measured term says straightens as that does."""
    taken = bent(scene())
    own = lens.Bend(table=tuple(table()))
    made = lens.straight(taken, own)
    assert made.shape == taken.shape and made.dtype == taken.dtype
    assert bow(made) < 0.3
    by_number = lens.straight(taken, K1).astype(int)
    assert np.abs(made.astype(int) - by_number).mean() < 0.5
    assert np.array_equal(lens.straight(taken, lens.Bend(k1=K1)), lens.straight(taken, K1))
    # As one number, it is the one it was made of; a short table too.
    assert lens.like(own) == approx(K1, rel=0.01)
    assert lens.like(lens.Bend(table=tuple(table(count=9)))) == approx(K1, rel=0.03)
    assert lens.like(lens.Bend(k1=K1)) == K1
    # A table of no bend at all moves nothing, and is no bend.
    flat = lens.Bend(table=(0.0,) * 12)
    assert not flat and np.array_equal(lens.straight(taken, flat), taken)
    assert lens.Bend(k1=K1) and own and not lens.Bend()

    # Corners set on the photograph as taken go with it, as with the number.
    x0, y0, x1, y1 = FRAME
    half = math.hypot(W, H) / 2
    drawn = []
    for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
        ux, uy = (x - W / 2) / half, (y - H / 2) / half
        f = 1 + K1 * (ux * ux + uy * uy)
        drawn.append(((ux * f * half + W / 2) / W, (uy * f * half + H / 2) / H))
    by_table, by_k1 = lens.moved(drawn, W, H, own), lens.moved(drawn, W, H, K1)
    for (tx, ty), (kx, ky) in zip(by_table, by_k1, strict=True):
        assert abs(tx - kx) * W < 0.1 and abs(ty - ky) * H < 0.1
    assert lens.moved([(0.5, 0.5)], W, H, own) == [(0.5, 0.5)]


def test_a_lens_whose_middle_is_not_the_photographs() -> None:
    """The camera says where its lens's middle is, too: a few pixels off
    the photograph's. The table is about that."""
    centre = (0.52, 0.49)
    cx, cy = centre[0] * W - 0.5, centre[1] * H - 0.5
    half = math.hypot(W, H) / 2
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    # Where such a lens draws the scene's points: the scene's pixels to read.
    px, py = (xx - cx) / half, (yy - cy) / half
    ux, uy = px.copy(), py.copy()
    for _ in range(20):
        f = 1 + K1 * (ux**2 + uy**2)
        ux, uy = px / f, py / f
    taken = cv2.remap(
        scene(),
        (ux * half + cx).astype(np.float32),
        (uy * half + cy).astype(np.float32),
        cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    own = lens.Bend(table=tuple(table(centre=centre)), centre=centre)
    assert bow(lens.straight(taken, own)) < 0.3
    # Taken for a lens in the photograph's middle, a slope is left in
    # the frame's side: not straight.
    assert bow(lens.straight(taken, K1)) > 2 * bow(lens.straight(taken, own))
    assert lens.like(own) == approx(K1, rel=0.08)
    # A corner goes where the frame's is.
    x0, y0 = FRAME[:2]
    u = ((x0 - 0.5 - cx) / half, (y0 - 0.5 - cy) / half)
    f = 1 + K1 * (u[0] ** 2 + u[1] ** 2)
    drawn = [((u[0] * f * half + cx + 0.5) / W, (u[1] * f * half + cy + 0.5) / H)]
    ((mx, my),) = lens.moved(drawn, W, H, own)
    assert abs(mx * W - x0) < 0.1 and abs(my * H - y0) < 0.1


def test_which_of_the_two_a_photograph_is_straightened_by() -> None:
    """The camera's table where it says what the measurement of that lens
    says; the measurement where it does not, or there is no table; and a
    lens that was not measured stays as taken until the table has been
    seen to say of his lens what the measurement does."""
    own = table()
    by_table = lens.chosen(K1, own, [0.5, 0.5])
    assert by_table is not None and by_table.table == tuple(own) and by_table.centre == (0.5, 0.5)
    # Within a third of the measured one, either way.
    for share in (0.7, 1.3):
        near = lens.chosen(K1, table(K1 * share), (0.5, 0.5))
        assert near is not None and near.table
    for other in (table(-K1), table(K1 * 1.5), table(K1 * 0.5), table(0.0)):
        assert lens.chosen(K1, other, (0.5, 0.5)) == lens.Bend(k1=K1)
    # No table, or what is none: too short, a number that is none, a
    # share no main camera has, a middle far from the photograph's.
    for none in (
        (None, None),
        (own[:4], (0.5, 0.5)),
        ([*own[:-1], float("nan")], (0.5, 0.5)),
        ([*own[:-1], 0.4], (0.5, 0.5)),
        (own, (0.7, 0.5)),
        (own, None),
        ("table", (0.5, 0.5)),
        (own, (0.5,)),
    ):
        assert lens.table(*none) is None
        assert lens.chosen(K1, *none) == lens.Bend(k1=K1)
    # A lens not measured.
    assert lens.ALONE is False
    assert lens.chosen(None, own, (0.5, 0.5)) is None
    assert lens.chosen(None) is None

    # As a scan notes it, and reads it back.
    assert lens.Bend(k1=K1).to_json() == K1
    assert lens.Bend.from_json(K1) == lens.Bend(k1=K1)
    assert lens.Bend.from_json(by_table.to_json()) == by_table
    assert lens.Bend.from_json(None) is None and lens.Bend.from_json({"table": [1]}) is None
    assert lens.Bend.from_json(True) is None
