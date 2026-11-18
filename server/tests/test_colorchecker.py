"""A colour chart photographed beside the work sets the photograph's
colours (Mateusz 2026-11-16 22:25 UTC: "dodajmy obsługę. Oczywiście nie
jako obowiązkową, ale opcjonalna"). Drawn charts until he has one."""

from __future__ import annotations

import io

import cv2
import numpy as np
import pytest
from PIL import Image

from frame_server.imaging import colorchecker
from frame_server.imaging.color import linear_to_oklab, linear_to_srgb, srgb_to_linear
from frame_server.service import FrameService

WALL = (205, 200, 190)
#: Where the "painting" hangs, and flat fields of it to measure.
WORK = (slice(300, 1200), slice(250, 1250))
FIELDS = {
    "red": ((slice(350, 550), slice(300, 600)), (170, 60, 50)),
    "green": ((slice(650, 850), slice(300, 600)), (60, 120, 70)),
    "blue": ((slice(350, 550), slice(800, 1100)), (50, 70, 150)),
    "skin": ((slice(650, 850), slice(800, 1100)), (200, 160, 135)),
    "dark": ((slice(950, 1150), slice(300, 600)), (40, 38, 36)),
    "light": ((slice(950, 1150), slice(800, 1100)), (225, 220, 210)),
}


def _board(colours: np.ndarray, cell: int = 60, gap: int = 12) -> np.ndarray:
    """A chart as it lies: 4 rows of 6 patches on black."""
    h, w = 4 * cell + 5 * gap, 6 * cell + 7 * gap
    img = np.full((h, w, 3), 18, np.uint8)
    for n, colour in enumerate(colours):
        r, c = divmod(n, 6)
        y, x = gap + r * (cell + gap), gap + c * (cell + gap)
        img[y : y + cell, x : x + cell] = colour
    return img


def _scene(board: np.ndarray | None, turned: float = 0.0, size: int = 420) -> np.ndarray:
    """The wall with the painting on it as they are, and ``board``
    leaning beside it (``turned`` degrees, ``size`` pixels across)."""
    scene = np.full((1500, 2000, 3), WALL, np.uint8)
    scene[WORK] = (120, 100, 80)
    for where, colour in FIELDS.values():
        scene[where] = colour
    if board is None:
        return scene
    h, w = board.shape[:2]
    lay = cv2.getRotationMatrix2D((w / 2, h / 2), turned, size / w)
    lay[:, 2] += (1620 - w / 2, 700 - h / 2)
    whole = np.vstack([lay, [0, 0, 1]])
    whole[2, 0] = 3e-5  # seen a little from the side
    there = cv2.warpPerspective(np.full((h, w), 255, np.uint8), whole, (2000, 1500)) > 127
    scene[there] = cv2.warpPerspective(board, whole, (2000, 1500), flags=cv2.INTER_AREA)[there]
    return scene


def _photographed(scene: np.ndarray) -> np.ndarray:
    """``scene`` as a phone gives it under a warm lamp: the colours run
    into each other a little, the white is off, it is too dark, and the
    contrast is the phone's own."""
    light = srgb_to_linear(scene / 255).astype(np.float64)
    light = light @ np.array([[0.86, 0.09, 0.05], [0.06, 0.88, 0.06], [0.04, 0.1, 0.86]]).T
    light = (light * np.array([1.3, 1.0, 0.65]) * 0.7) ** 0.9
    noise = np.random.default_rng(7).normal(0, 1.5, scene.shape)
    return np.clip(linear_to_srgb(light) * 255 + noise, 0, 255).astype(np.uint8)


def _field(img: np.ndarray, name: str) -> np.ndarray:
    return img[FIELDS[name][0]].reshape(-1, 3).mean(0)


def _far(img: np.ndarray) -> float:
    """How far the painting's fields are from what they are (levels)."""
    return float(np.mean([np.abs(_field(img, name) - FIELDS[name][1]).mean() for name in FIELDS]))


def _cast(img: np.ndarray, name: str) -> float:
    """How far a field's colour is from its own, however light it is
    (red and blue beside green, in light)."""
    seen = srgb_to_linear(_field(img, name) / 255)
    true = srgb_to_linear(np.array(FIELDS[name][1]) / 255)
    return float(np.abs(seen / seen[1] - true / true[1]).max())


def _luma(img: np.ndarray, name: str) -> float:
    return float(_field(img, name) @ np.array([0.2126, 0.7152, 0.0722]))


def _hue(img: np.ndarray, name: str) -> float:
    """How far a field's hue is from its own (degrees)."""
    seen = linear_to_oklab(srgb_to_linear(_field(img, name) / 255).astype(np.float32))
    true = linear_to_oklab(srgb_to_linear(np.array(FIELDS[name][1]) / 255).astype(np.float32))
    turn = np.degrees(np.arctan2(seen[2], seen[1]) - np.arctan2(true[2], true[1]))
    return float(abs((turn + 180) % 360 - 180))


@pytest.mark.parametrize("turned", [0.0, 12.0, 90.0, 180.0])
def test_a_chart_beside_the_work_gives_the_photograph_its_colours(turned: float) -> None:
    photo = _photographed(_scene(_board(colorchecker.REFERENCE.astype(np.uint8)), turned))
    assert _far(photo) > 12
    chart = colorchecker.find(photo)
    assert chart is not None
    assert chart.off > 0.05 and chart.left < 0.02
    # Where it lies: beside the work, not on it.
    assert all(x > 0.65 for x, _ in chart.corners)
    true = colorchecker.true(photo, chart)
    assert _far(true) < 5
    # The wall too, which the chart knows nothing of.
    assert np.abs(true[100:200, 100:400].reshape(-1, 3).mean(0) - WALL).max() < 6
    # It goes to a file and back the same.
    again = colorchecker.Chart.from_json(chart.to_json())
    assert np.array_equal(colorchecker.true(photo, again), true)
    assert again.look == colorchecker.LOOK


def test_the_chart_sets_the_colours_and_how_light_the_photograph_is_by_half() -> None:
    """His first scan with a real chart (2026-11-18 18:13 UTC: "Wyszło
    trochę blado i mdło"): the photograph came out as the chart's patches
    truly are, its blacks a dark grey and the phone's contrast undone.
    Shown that, the phone's own lightness and the middle of the two
    (19:13 UTC): "Wyważone, pół na pół"."""
    photo = _photographed(_scene(_board(colorchecker.REFERENCE.astype(np.uint8))))
    chart = colorchecker.find(photo)
    assert chart is not None
    lit = colorchecker.apply(photo, chart)
    # Nothing has the lamp's colour any more: the wall, a dark and a
    # light of the painting are as grey as they are.
    assert _cast(photo, "light") > 0.2
    for name in ("light", "dark"):
        assert _cast(lit, name) < 0.05
    wall = lit[100:200, 100:400].reshape(-1, 3).mean(0)
    assert np.abs(wall / wall[1] - np.array(WALL) / WALL[1]).max() < 0.04
    # And each is half way between as light as it truly is and as light
    # as the phone had it.
    true = colorchecker.true(photo, chart)
    for name in FIELDS:
        middle = (_luma(true, name) + _luma(photo, name)) / 2
        assert abs(_luma(lit, name) - middle) < 0.08 * middle + 3, name
    assert max(abs(_luma(true, name) - _luma(photo, name)) for name in FIELDS) > 8
    # The colours are the painting's: red is red by as much as it is.
    for name in ("red", "green", "blue", "skin"):
        assert _hue(lit, name) < 12, name
        assert _hue(photo, name) > _hue(lit, name), name
    # A photograph kept as the patches truly are comes to the same.
    relit = colorchecker.relit(colorchecker.true(photo, chart), chart)
    assert np.abs(relit.astype(int) - lit).mean() < 1.5
    # One noted by an earlier release was kept so.
    noted = chart.to_json()
    del noted["look"]
    assert colorchecker.Chart.from_json(noted).look == 0


def test_a_small_chart_is_read_too() -> None:
    """A Passport beside a large canvas is a small thing in the photograph."""
    photo = _photographed(_scene(_board(colorchecker.REFERENCE.astype(np.uint8)), size=220))
    chart = colorchecker.find(photo)
    assert chart is not None
    assert _far(colorchecker.true(photo, chart)) < 6


def test_a_glint_on_one_patch_does_not_turn_the_colours() -> None:
    board = _board(colorchecker.REFERENCE.astype(np.uint8))
    board[12:72, 156:216] = 250  # the lamp on "blue sky"
    photo = _photographed(_scene(board))
    chart = colorchecker.find(photo)
    assert chart is not None
    assert _far(colorchecker.true(photo, chart)) < 6


def test_without_a_chart_nothing_is_found() -> None:
    assert colorchecker.find(_photographed(_scene(None))) is None


def test_coloured_squares_that_are_no_chart_are_not_believed() -> None:
    """The detector names rows of squares charts (his cows, a print's
    margin): what does not fit the chart's colours is none."""
    squares = np.random.default_rng(3).integers(20, 235, (24, 3)).astype(np.uint8)
    assert colorchecker.find(_photographed(_scene(_board(squares)))) is None


def _jpeg(img: np.ndarray) -> bytes:
    out = io.BytesIO()
    Image.fromarray(img).save(out, "JPEG", quality=95)
    return out.getvalue()


def test_the_scans_photographs_are_all_put_in_the_charts_colours(service: FrameService) -> None:
    own = service.own_works
    photo = _photographed(_scene(_board(colorchecker.REFERENCE.astype(np.uint8))))
    seen = own.take(_jpeg(photo))
    assert seen.chart is not None and len(seen.chart) == 4
    with Image.open(own.path(seen.token)) as img:
        assert _cast(np.asarray(img.convert("RGB")), "light") < 0.06
    # A side photograph has no chart read of its own: the first one's.
    own.side(seen.token, _jpeg(photo))
    with Image.open(own.incoming / f"{seen.token}-side1.jpg") as img:
        assert _cast(np.asarray(img.convert("RGB")), "light") < 0.06
    # The phone is told again when it asks for the work (no key: none found).
    assert own._charted(seen.token) is not None

    # No chart: the photograph as it came.
    plain = own.take(_jpeg(photo[:, :1300]))
    assert plain.chart is None
    with Image.open(own.path(plain.token)) as img:
        assert _cast(np.asarray(img.convert("RGB")), "light") > 0.2
