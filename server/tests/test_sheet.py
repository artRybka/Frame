"""The study sheet an analysis of composition is drawn on: the picture as
stains and a few strokes of a pen on the app's page (light and dark), made
when first asked for and kept; the picture's own field on a reproduction
with margins; a colour that returns marked as an echo; at most five marks."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from test_composition import ANALYSIS_V6, SKETCH, _drawn, _old_page, _pipeline, _points
from test_daily import _app, _catalogue

from frame_server.ai.check import SYSTEM as CHECK_SYSTEM
from frame_server.ai.client import Answer
from frame_server.ai.composition import MAX_DRAWN, compose, draft, question
from frame_server.ai.daily import TAKE, Box, Spot, _view
from frame_server.ai.pen import strokes as pen_strokes
from frame_server.ai.sketch import draw, grid_fits, measure
from frame_server.ai.study import KIND as STUDY
from frame_server.imaging import sheet as sheets
from frame_server.service import FrameService
from frame_server.sheets import Sheets


def _scene(size: tuple[int, int] = (600, 400)) -> Image.Image:
    """A sky, a field and a red house: three masses."""
    img = Image.new("RGB", size, (150, 180, 220))
    canvas = ImageDraw.Draw(img)
    canvas.rectangle((0, size[1] * 0.6, size[0], size[1]), fill=(90, 120, 60))
    canvas.rectangle(
        (size[0] * 0.3, size[1] * 0.35, size[0] * 0.55, size[1] * 0.7), fill=(170, 40, 30)
    )
    return img


def test_the_sheet_is_stains_on_the_apps_page() -> None:
    light = sheets.render(_scene(), seed=3)
    assert max(light.size) == sheets.LONG and light.size == (1500, 1000)
    # The paint keeps inside the field: its corners are the page itself.
    assert light.getpixel((1, 1)) == sheets.PAGE[False]
    sky, house = light.getpixel((640, 300)), light.getpixel((640, 520))
    assert sky[2] > sky[0] and house[0] > house[2] + 40  # the masses keep their colours
    dark = sheets.render(_scene(), dark=True, seed=3)
    assert dark.getpixel((1, 1)) == sheets.PAGE[True]
    assert sum(dark.getpixel((640, 520))) < sum(house)  # a dark page's paint is darker
    # The same picture gives the same sheet.
    assert sheets.render(_scene(), seed=3).tobytes() == light.tobytes()
    # The file keeps the page's colour, so the sheet lies on the app's page without a seam.
    back = Image.open(io.BytesIO(sheets.jpeg(light))).getpixel((1, 1))
    assert max(abs(a - b) for a, b in zip(back, sheets.PAGE[False], strict=True)) <= 2


def _crowd(size: tuple[int, int] = (600, 400)) -> Image.Image:
    """Something everywhere: discs of every colour."""
    rng = np.random.default_rng(5)
    img = Image.new("RGB", size, (120, 110, 100))
    canvas = ImageDraw.Draw(img)
    for _ in range(260):
        x, y, r = rng.uniform(0, size[0]), rng.uniform(0, size[1]), rng.uniform(8, 22)
        colour = (int(rng.uniform(30, 230)), int(rng.uniform(30, 230)), int(rng.uniform(30, 230)))
        canvas.ellipse((x - r, y - r, x + r, y + r), fill=colour)
    return img


def _bare(sheet: Image.Image, dark: bool = False) -> Any:
    """Where the sheet is the page itself."""
    apart = np.abs(np.asarray(sheet, np.int32) - np.array(sheets.PAGE[dark])).sum(axis=2)
    return apart < 12


def test_where_little_happens_the_wash_is_general_and_leaves_the_page() -> None:
    """Mateusz 2026-11-12: the watercolour "ogólniejsza … tam gdzie mniej się
    dzieje", "nie zalewać plamą wszystkiego i fragmentami zostawiać tło
    podkładu"."""
    scene = np.asarray(_scene())
    lively = sheets.busy(scene, scene.shape[:2])
    assert lively[60, 480] < 0.05 and lively[330, 480] < 0.05  # the sky, the field
    assert lively[140, 180] > 0.9  # the house's corner
    crowd = np.asarray(_crowd())
    assert sheets.busy(crowd, crowd.shape[:2]).mean() > 0.8
    # A sky in three bands of nearly one blue is one stain.
    banded = _scene()
    canvas = ImageDraw.Draw(banded)
    for k, blue in enumerate(((150, 180, 220), (158, 186, 222), (166, 192, 224))):
        canvas.rectangle((0, k * 46, 600, k * 46 + 46), fill=blue)
    canvas.rectangle((180, 140, 330, 280), fill=(170, 40, 30))
    piece, colours = sheets.masses(np.asarray(banded), seed=3)
    assert len(np.unique(piece[5:120, 20:540])) == 1 and len(colours) - 1 <= 4
    # The quiet picture's page shows in fragments, never most of it; the
    # paint still lies around what happens (the house).
    light = sheets.render(_scene(), seed=3)
    left = _bare(light)
    assert 0.1 < left.mean() <= sheets.BARE_MOST + 0.04
    assert left[60:200, 1150:1450].mean() > 0.9  # the far sky
    assert not left[330:780, 430:860].any()  # the house and what is round it
    night = _bare(sheets.render(_scene(), dark=True, seed=3), dark=True)
    assert 0.05 < night.mean() <= sheets.BARE_MOST + 0.04
    # Where something happens everywhere, all is painted but the ragged edge.
    assert _bare(sheets.render(_crowd(), seed=3))[60:940, 60:1440].mean() < 0.01


def _halves(seed: int = 2) -> Image.Image:
    """A blue half over a red one, both speckled: something everywhere."""
    rng = np.random.default_rng(seed)
    img = Image.new("RGB", (600, 400), (60, 110, 190))
    canvas = ImageDraw.Draw(img)
    canvas.rectangle((0, 200, 600, 400), fill=(190, 60, 40))
    for _ in range(500):
        x, y, r = rng.uniform(0, 600), rng.uniform(0, 400), rng.uniform(2, 5)
        base = (60, 110, 190) if y < 200 else (190, 60, 40)
        speck = (
            int(np.clip(base[0] + rng.uniform(-25, 25), 0, 255)),
            int(np.clip(base[1] + rng.uniform(-25, 25), 0, 255)),
            int(np.clip(base[2] + rng.uniform(-25, 25), 0, 255)),
        )
        canvas.ellipse((x - r, y - r, x + r, y + r), fill=speck)
    return img


def test_neighbouring_stains_make_no_dark_band_and_alike_ones_are_one() -> None:
    """Mateusz 2026-11-12 07:01: "Teraz zawsze się nakładają jedna na drugą i
    powstaje ciemniejszy pas w każdym takim miejscu"; "jeżeli dwie plamy
    akwareli są do siebie bardzo podobne … to lepiej zlać je w jedną"."""
    # Specks of nearly the stain's own colour do not make patches of it,
    # busy as the picture is.
    _piece, colours = sheets.masses(np.asarray(_halves()), seed=3)
    assert len(colours) - 1 == 2
    for seed in (1, 2, 3):
        sheet = np.asarray(sheets.render(_halves(), seed=seed), np.float32)
        rows = sheet[:, 150:1350].sum(axis=2).mean(axis=1) / 3
        blue, red = rows[300:400].mean(), rows[560:660].mean()
        # Across the seam the rows go from the one stain's tone to the
        # other's: none is darker than the darker stain by more than its
        # own unevenness.
        assert rows[470:530].min() > min(blue, red) - 25
        assert rows[470:530].max() < max(blue, red) + 25


def test_the_pen_draws_over_the_stains() -> None:
    plain = np.asarray(sheets.render(_scene(), seed=3), np.int32)
    stroke = ([(0.1, 0.2), (0.5, 0.25), (0.9, 0.2)], False, False)
    frame = ([(0.3, 0.35), (0.55, 0.35), (0.55, 0.7), (0.3, 0.7)], True, True)
    drawn = np.asarray(sheets.render(_scene(), [stroke, frame], seed=3), np.int32)
    changed = np.abs(drawn - plain).sum(axis=2) > 60
    assert 0.002 < changed.mean() < 0.03  # a few strokes, not a hatching
    assert changed[300:420, 600:900].any()  # the first stroke, across the sky
    # In the ink of the page it lies on.
    light = drawn[changed].mean(axis=0)
    night = np.asarray(sheets.render(_scene(), [stroke, frame], dark=True, seed=3), np.int32)
    assert night[changed].mean() > light.mean()
    # A dot is no stroke, and none at all is no trouble.
    assert sheets.render(_scene(), [([(0.5, 0.5)], False, False)], seed=3).size == (1500, 1000)


def test_an_echo_is_rings_and_a_broken_line() -> None:
    echo = _drawn("echo", (0.2, 0.3), (0.8, 0.6))
    assert echo is not None and echo.anchor() == Spot(x=0.2, y=0.3)
    # Two to four places, each apart from the others.
    assert _drawn("echo", (0.2, 0.3), (0.21, 0.31)) is None
    many = _drawn("echo", (0.1, 0.1), (0.3, 0.3), (0.5, 0.5), (0.7, 0.7), (0.9, 0.9))
    assert many is not None and len(many.points) == 4
    assert _drawn("echo", (0.2, 0.3), (1.4, 0.6)).points[1].x == 1.0  # on the picture
    assert measure(echo, (900, 600)) == "miejsca: 180, 180; 720, 360"
    view = _view({"title": TAKE, "marks": [echo.model_dump()]})
    assert view is not None
    picture = Image.new("RGB", (900, 600), (40, 70, 140))
    drawn = draw(picture, view)
    ring = int(900 * 0.03)
    assert drawn.getpixel((180 + ring, 180)) != (40, 70, 140)  # a ring around the place
    assert drawn.getpixel((180, 180)) == (40, 70, 140)  # not on it
    # Between the rings the line is broken: some of it drawn, some not.
    between = [
        drawn.getpixel((x, y)) != (40, 70, 140) for x in range(260, 640) for y in range(180, 400)
    ]
    assert 0 < sum(between) < 380 * 12


def test_the_pictures_field_is_its_own() -> None:
    box = Box(x=0.1, y=0.2, w=0.8, h=0.5)
    view = _view(
        {
            "title": TAKE,
            "grid": "halves",
            "field": box.model_dump(),
            "marks": [
                {"shape": "line", "points": _points((0.1, 0.45), (0.9, 0.45)), "title": "Horyzont"}
            ],
        }
    )
    # The grid divides the field: its middle is the horizon's height, not the paper's.
    assert view is not None and view.field == box and grid_fits(view) and view.grid == "halves"
    inside = view.inside()
    assert inside.field is None
    assert [(round(p.x, 3), round(p.y, 3)) for p in inside.marks[0].points] == [(0, 0.5), (1, 0.5)]
    back = inside.on(box)
    assert [(round(p.x, 3), round(p.y, 3)) for p in back.marks[0].points] == [
        (0.1, 0.45),
        (0.9, 0.45),
    ]
    # The whole reproduction, a sliver and nonsense are no field.
    for raw in (
        {"x": 0.01, "y": 0, "w": 0.98, "h": 1},
        {"x": 0.4, "y": 0, "w": 0.2, "h": 1},
        {"x": "a"},
    ):
        whole = _view({**view.model_dump(), "grid": "none", "field": raw})
        assert whole is not None and whole.field is None


#: A print on its paper, in pixels of a 900 × 600 reproduction: the picture
#: is the box (90, 60)–(810, 420), its horizon in the middle of it.
PRINT = {
    "composition": {
        "views": [
            {
                "title": TAKE,
                "pole": {"left": 90, "top": 60, "right": 810, "bottom": 420},
                "marks": [
                    {
                        "shape": "line",
                        "points": _points((90, 240), (810, 240)),
                        "na": ["brzeg ryciny", "brzeg ryciny"],
                        "po": "linia horyzontu",
                        "title": "Horyzont",
                        "text": "dzieli pole na pół",
                    },
                    {
                        "shape": "loop",
                        "points": _points((400, 250), (500, 400)),
                        "na": ["grzbiet krowy", "kopyta"],
                        "po": "krowa",
                        "title": "Krowa",
                        "text": "dominanta",
                    },
                ],
                "points": [
                    {"x": 450, "y": 240, "na": "horyzont", "os": "y", "waga": "główny"},
                    {"x": 450, "y": 300, "na": "oś krowy", "os": "x", "waga": "ważny"},
                ],
                "text": "Horyzont dzieli rycinę na pół. Kompozycja zamknięta.",
            }
        ]
    }
}


def test_a_print_is_analysed_in_its_field(service: FrameService) -> None:
    _catalogue(service)
    item = service.library.get("met:1")
    assert item is not None
    params = question(service.images, item, service.daily.job.sources(item))
    found = draft(PRINT, params)
    assert found is not None and found.field == Box(x=0.1, y=0.1, w=0.8, h=0.6)
    # In the field the horizon runs from edge to edge through its middle.
    assert [(round(p.x, 3), round(p.y, 3)) for p in found.view.marks[0].points] == [
        (0, 0.5),
        (1, 0.5),
    ]
    assert round(found.keys[0].y, 6) == 0.5 and found.po["Krowa"] == "krowa"
    asked: list[dict[str, Any]] = []
    answers = _pipeline(asked, PRINT)

    def ask(params: dict[str, Any]) -> Answer:
        if params["system"][0]["text"] == CHECK_SYSTEM:  # the check leaves this one be
            asked.append(params)
            return Answer({"marks": [], "points": [], "text": ""}, False, 0.01, "haiku")
        return answers(params)

    page = compose(service.images, item, service.daily.job.sources(item), ask)
    check = next(p for p in asked if p["system"][0]["text"] == CHECK_SYSTEM)
    # Every later step looks at the field alone.
    text = check["messages"][0]["content"][-1]["text"]
    assert "OBRAZ: 720 × 360 px" in text and "punkty: (0, 180) (720, 180)" in text
    (view,) = page["composition"]["views"]
    assert view["field"] == {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.6}
    # The marks go back on the whole reproduction, as apps before the sheet draw them.
    horizon = view["marks"][0]["points"]
    assert [(round(p["x"], 3), round(p["y"], 3)) for p in horizon] == [(0.1, 0.4), (0.9, 0.4)]
    assert view["grid"] == "halves"  # measured in the field, where the horizon is the middle
    assert len(view["sketch"]) == 4


def test_at_most_five_marks_and_a_sketch_of_some_strokes(service: FrameService) -> None:
    _catalogue(service)
    item = service.library.get("met:1")
    assert item is not None
    lines = [
        {"shape": "line", "points": _points((0, 60 * n), (900, 60 * n)), "title": f"Pas {n}"}
        for n in range(1, 8)
    ]
    view = {**ANALYSIS_V6["composition"]["views"][0], "marks": lines}
    params = question(service.images, item, service.daily.job.sources(item))
    found = draft({"composition": {"views": [view]}}, params)
    assert found is not None and len(found.view.marks) == MAX_DRAWN == 5
    # The pen: fractions of the picture, whatever size it was sent at; too few strokes are none.
    drawn = pen_strokes(SKETCH, (900, 600))
    assert drawn is not None and len(drawn) == 4
    assert (drawn[1].points[1].x, drawn[1].points[1].y) == (1.0, 0.5) and drawn[1].sharp
    assert pen_strokes({"szkic": SKETCH["szkic"][:2]}, (900, 600)) is None
    assert pen_strokes(None, (900, 600)) is None
    big = pen_strokes(SKETCH, (1800, 1200))  # sent at 1024 × 683: its pixels are of that
    assert big is not None and round(big[1].points[1].x, 2) == round(900 / 1024, 2)


def test_the_app_gets_the_sheet_of_the_take_it_shows(tmp_path: Path) -> None:
    app = _app(tmp_path)
    svc: FrameService = app.state.service
    with TestClient(app) as client:
        _catalogue(svc)
        _old_page(svc)
        work = client.get("/api/study/met:1").json()["work"]
        url = work["composition_sheet"]
        assert url.startswith("/api/composition/sheet?item=met%3A1&v=")
        got = client.get(url)
        assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
        light = Image.open(io.BytesIO(got.content))
        assert max(light.size) == sheets.LONG and light.size[0] * 2 == light.size[1] * 3
        dark = Image.open(io.BytesIO(client.get(url + "&dark=1").content))
        assert sum(dark.getpixel((1, 1))) < 80 < 600 < sum(light.getpixel((1, 1)))
        # Made once, then kept.
        item = svc.library.get("met:1")
        assert item is not None
        view = svc.sheets.view(item)
        assert view is not None and len(list(svc.sheets.dir.glob("*.jpg"))) == 2
        made = svc.sheets.path(item, view, False).stat().st_mtime_ns
        assert client.get(url).content == got.content
        assert svc.sheets.path(item, view, False).stat().st_size == len(got.content)
        assert made <= svc.sheets.path(item, view, False).stat().st_mtime_ns
        # Another sketch or field is another sheet at another address.
        sketched = view.model_copy(update={"sketch": pen_strokes(SKETCH, (900, 600))})
        assert Sheets.key(sketched) != Sheets.key(view)
        assert Sheets.key(
            view.model_copy(update={"field": Box(x=0.1, y=0.1, w=0.8, h=0.6)})
        ) != Sheets.key(view)
        # An address from before the analysis was made anew still gets the take's sheet.
        assert client.get("/api/composition/sheet?item=met%3A1&v=old").status_code == 200
        assert client.get("/api/composition/sheet?item=met%3A2").status_code == 404
        assert client.get("/api/composition/sheet?item=nothing%3A1").status_code == 404
    assert STUDY
