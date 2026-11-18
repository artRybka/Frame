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


def _in_a_dim_room(scene: np.ndarray) -> np.ndarray:
    """``scene`` as his phone gave it in a dim room (2026-11-18 21:14 UTC,
    a chart on the frame against a dark wall): warm, and what is dark is
    no light at all. The chart's black patch came out 0, 0, 0."""
    light = srgb_to_linear(scene / 255).astype(np.float64) * np.array([0.95, 0.68, 0.5])
    light = np.clip(light - 0.03, 0, 1)
    noise = np.random.default_rng(7).normal(0, 1.5, scene.shape)
    return np.clip(linear_to_srgb(light) * 255 + noise, 0, 255).astype(np.uint8)


def _under_a_lamp(scene: np.ndarray) -> np.ndarray:
    """``scene`` as his phone gave it on a table under a lamp (21:20 UTC,
    a dark work, so the phone made all of it light): bluish, and what is
    light is at the photograph's top. The chart's white and the grey
    after it both had blue at 255."""
    light = srgb_to_linear(scene / 255).astype(np.float64) * np.array([1.0, 1.05, 1.5]) * 1.6
    noise = np.random.default_rng(7).normal(0, 1.5, scene.shape)
    return np.clip(linear_to_srgb(np.clip(light, 0, 1)) * 255 + noise, 0, 255).astype(np.uint8)


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


def test_a_chart_whose_black_patch_has_no_light_is_read_from_the_greys_above() -> None:
    """Mateusz 2026-11-18 21:14 UTC, three scans of a painting on a dark
    wall with the chart on its frame: "Dlaczego karta kolorów nie jest tu
    wykrywana?". It was found each time, and refused: its black patch was
    0, 0, 0 in the photograph, and a chart needed light in all six greys
    (to 1.145.244). The five above it say what the phone did."""
    photo = _in_a_dim_room(_scene(_board(colorchecker.REFERENCE.astype(np.uint8))))
    assert _cast(photo, "light") > 0.2
    chart = colorchecker.find(photo)
    assert chart is not None
    assert (chart.lightest, chart.darkest) == (0, 4) and chart.left < 0.035
    lit = colorchecker.apply(photo, chart)
    for name in ("light", "skin"):
        assert _cast(lit, name) < 0.06, name
    for name in ("red", "green", "blue", "skin"):
        assert _hue(lit, name) < 12, name
    # What had no light has none: nothing is made of nothing.
    assert lit[photo.max(-1) == 0].max() == 0
    # It goes to a file and back the same.
    again = colorchecker.Chart.from_json(chart.to_json())
    assert again.darkest == 4 and np.array_equal(colorchecker.apply(photo, again), lit)
    # One noted before greys could be left out had all six.
    noted = chart.to_json()
    del noted["lightest"], noted["darkest"]
    assert colorchecker.Chart.from_json(noted).darkest == 5


def test_a_black_patch_with_next_to_no_light_is_no_point_of_the_curves() -> None:
    """His scan of 21:16 UTC, taken for a chart by 1.145.244: its black
    patch at 2 of 255. As a point of the curves that put the values 0, 1
    and 2 where 0, 33 and 52 are."""
    greys = np.array(
        [
            [0.854993, 0.610496, 0.450786],
            [0.502887, 0.361307, 0.274677],
            [0.238398, 0.168269, 0.130136],
            [0.082283, 0.052861, 0.040915],
            [0.016807, 0.012286, 0.009134],
            [0.000607, 0.000607, 0.000607],
        ]
    )
    assert colorchecker._usable(greys) == (0, 4)
    curves = colorchecker._curves(greys, 0, 4)
    assert curves[:, 2].max() < 0.01
    # Greys that do not darken in step are no chart, whatever is left out.
    assert colorchecker._usable(greys[[0, 2, 1, 3, 4, 5]]) is None
    # Nor are three of them.
    assert colorchecker._usable(np.vstack([np.ones((3, 3)), greys[3:]])) is None


def test_a_chart_at_the_photographs_top_is_read_from_the_greys_below() -> None:
    """21:20 UTC, a dark work on a table under a lamp, the chart beside
    it: "Podobny problem.". The phone made the photograph light: the
    chart's white and the grey after it were both at blue's top, so the
    greys did not darken in step. The four below them do, and give the
    colours; what is at the top stays as grey as it is."""
    photo = _under_a_lamp(_scene(_board(colorchecker.REFERENCE.astype(np.uint8))))
    assert _cast(photo, "dark") > 0.2
    chart = colorchecker.find(photo)
    assert chart is not None
    assert (chart.lightest, chart.darkest) == (2, 5) and chart.left < 0.035
    lit = colorchecker.apply(photo, chart)
    assert _cast(lit, "dark") < 0.06
    for name in ("red", "green", "blue", "skin"):
        assert _hue(lit, name) < 12, name
    # The painting's light, at the top in all three: no colour comes of
    # that (red, green and blue each ended elsewhere: a cream).
    light = _field(lit, "light")
    assert light.max() - light.min() < 4
    # And the wall, at blue's top only.
    wall = lit[100:200, 100:400].reshape(-1, 3).mean(0)
    assert wall.max() - wall.min() < 12


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


def test_a_chart_not_read_when_the_scan_came_is_read_when_the_work_is_made_again(
    service: FrameService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """His scans of 2026-11-18 21:11–21:20 UTC became works with no chart
    read ("Dlaczego karta kolorów nie jest tu wykrywana?"). Their
    photographs are kept: after the update that reads such a chart they
    are put in its colours and the work is made of them once more, by
    itself; a scan without a chart is looked at once and left."""
    import json

    from test_own_works import TEXT, _client

    from frame_server.own_works import SCAN_INFO, OwnWorks

    def png(img: np.ndarray) -> bytes:
        out = io.BytesIO()
        Image.fromarray(img).save(out, "PNG")
        return out.getvalue()

    def warm(path: object) -> float:
        with Image.open(path) as img:  # type: ignore[arg-type]
            mean = np.asarray(img.convert("RGB")).reshape(-1, 3).mean(0)
        return float(mean[0] / mean[2])

    photo = _in_a_dim_room(_scene(_board(colorchecker.REFERENCE.astype(np.uint8))))
    work = [(0.125, 0.2), (0.625, 0.2), (0.625, 0.8), (0.125, 0.8)]
    # The merging is not what is asked about here.
    monkeypatch.setattr(OwnWorks, "_merge", staticmethod(lambda *_: (2, 0.01, False)))
    with monkeypatch.context() as then, _client(service) as client:
        # The release that took them: no chart in such a photograph.
        then.setattr(colorchecker, "find", lambda _: None)
        tokens = []
        for shown in (photo, photo[:, :1300]):
            token = client.post("/api/own/photos", files={"file": ("p.png", png(shown))}).json()[
                "token"
            ]
            for _ in range(2):
                client.post(f"/api/own/photos/{token}/sides", files={"file": ("s.png", png(shown))})
            client.post(f"/api/own/photos/{token}/merge", json={"outline": work})
            added = client.post(
                "/api/own/works",
                json={"token": token, "corners": work, "by": "owner", "text": TEXT},
            )
            assert added.status_code == 200, added.text
            tokens.append((token, added.json()["id"]))
    works = service.own_works
    for token, _ in tokens:
        note = works.scans / token / SCAN_INFO
        info = json.loads(note.read_text())
        assert info["chart"] is None
        del info["sought"]  # it did not note how it had looked
        note.write_text(json.dumps(info))
    (token, with_chart), (plain, _) = tokens
    item = service.library.get(with_chart)
    assert item is not None
    before = warm(service.images.museum_photo(item, urgent=True))
    assert before > 1.5

    assert works.scanned_again() == 1
    assert works.scanned_again() == 0
    info = json.loads((works.scans / token / SCAN_INFO).read_text())
    assert info["chart"]["darkest"] == 4 and info["sought"] == colorchecker.READING
    assert info["again"] and info["balance"] == 0.0
    for name in ("first.jpg", "side1.jpg", "side2.jpg"):
        with Image.open(works.scans / token / name) as img:
            assert _cast(np.asarray(img.convert("RGB")), "light") < 0.07, name
    again = service.library.get(with_chart)
    assert again is not None
    assert warm(service.images.museum_photo(again, urgent=True)) < before * 0.8
    # The one without a chart: looked at, and as it was.
    info = json.loads((works.scans / plain / SCAN_INFO).read_text())
    assert info["chart"] is None and info["sought"] == colorchecker.READING
    assert "again" not in info
    with Image.open(works.scans / plain / "first.jpg") as img:
        assert _cast(np.asarray(img.convert("RGB")), "light") > 0.2
