"""The study sheet an analysis of composition is drawn on: the picture as
stains and a few strokes of a pen on the app's page (light and dark), whole
and as its two layers, made ahead and kept; the picture's own field on a reproduction
with margins; a colour that returns marked as an echo; at most five marks."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from test_composition import (
    ANALYSIS_V6,
    CLOSE,
    SKETCH,
    _drawn,
    _line,
    _old_page,
    _pipeline,
    _points,
    pen_points,
    sketch,
)
from test_daily import _app, _catalogue

from frame_server.ai import AiConfigUpdate, pen
from frame_server.ai.check import SYSTEM as CHECK_SYSTEM
from frame_server.ai.check import page_views
from frame_server.ai.client import FABLE, OPUS, Answer
from frame_server.ai.composition import MAX_DRAWN, compose, draft, question
from frame_server.ai.daily import CHECK_ROUND, ROUND, TAKE, Box, Spot, _view
from frame_server.ai.pen import strokes as pen_strokes
from frame_server.ai.redraw import KIND as PEN
from frame_server.ai.redraw import PenJob, redrawn, wants
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
    # (As much on the light page as on the dark one, and the stains as
    # light as before the darker ground he tried: Mateusz 2026-11-12 10:54,
    # "akwarela jednak jaśniejsza - tak jak wcześniej".)
    assert 0.1 < left.mean() <= sheets.BARE_MOST + 0.04
    assert left[40:140, 1300:1480].mean() > 0.9  # the far sky
    assert not left[330:780, 430:860].any()  # the house and what is round it
    night = _bare(sheets.render(_scene(), dark=True, seed=3), dark=True)
    assert 0.05 < night.mean() <= sheets.BARE_MOST + 0.04
    # Where something happens everywhere, all is painted but the ragged edge.
    assert _bare(sheets.render(_crowd(), seed=3))[60:940, 60:1440].mean() < 0.01
    # The stains stay a wash, clearly lighter than the picture they come
    # from, even where all is painted (the darker ground of the look before
    # was hardly lighter than the picture; he took it back).
    crowd = _crowd()
    washed = np.asarray(sheets.render(crowd, seed=3), np.float32)[100:-100, 100:-100]
    painted = np.asarray(crowd.resize((washed.shape[1] + 200, washed.shape[0] + 200)), np.float32)
    assert washed.mean() > painted[100:-100, 100:-100].mean() + 0.06 * 255


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


def _dusk(size: tuple[int, int] = (600, 400)) -> Image.Image:
    """The scene with a deep shadow across its foot."""
    img = _scene(size)
    ImageDraw.Draw(img).rectangle((0, size[1] * 0.72, size[0] * 0.7, size[1]), fill=(28, 34, 30))
    return img


def test_the_sheet_is_two_layers_and_the_pen_hatches_the_dark() -> None:
    """Mateusz 2026-11-12 09:47: the sheet "malować / rysować się na żywo"
    (so the stains and the pen come apart), the pen "gdzieniegdzie …
    'szkicować'/kreskować ciemniejsze partie"."""
    stroke = ([(0.1, 0.2), (0.5, 0.25), (0.9, 0.2)], False, False)
    wide_wash, wide_pen = sheets.layers(_dusk(), [stroke], seed=3)
    # (each with the page's margin beside the field: see the test below)
    wash, pen = sheets.field(wide_wash), sheets.field(wide_pen)
    assert wash.mode == "RGB" and pen.mode == "RGBA" and wash.size == pen.size == (1500, 1000)
    # One on the other they are the whole sheet.
    whole = wash.convert("RGBA")
    whole.alpha_composite(pen)
    assert whole.convert("RGB").tobytes() == sheets.render(_dusk(), [stroke], seed=3).tobytes()
    # The stains hold no pen: the same with a stroke and without.
    assert sheets.layers(_dusk(), seed=3)[0].tobytes() == wide_wash.tobytes()
    drawn = np.asarray(pen)[..., 3] > 40
    assert drawn[190:250, 600:900].any()  # the stroke across the sky
    # Slanted lines over the shadow, with paper between them; none in the sky.
    shadow = drawn[760:960, 100:900]
    assert 0.03 < shadow.mean() < 0.4
    assert not drawn[40:180, 100:1400].any() and not drawn[260:340, 100:1400].any()
    # A picture with no part darker than the rest gets none.
    even = np.asarray(sheets.layers(Image.new("RGB", (600, 400), (150, 180, 220)), seed=3)[1])
    assert not even[..., 3].any()
    assert Image.open(io.BytesIO(sheets.png(pen))).mode == "RGBA"


def test_a_stain_runs_out_and_a_stroke_goes_on_past_the_frame() -> None:
    """Mateusz 2026-11-12 11:04: "plamy akwareli mogą w jednym czy max 2
    miejscach wylewać się i sięgać krawędzi bocznej ekranu. podobnie kreska
    rysunku - pojedyncza może wystawać poza kadr"."""
    # Three strokes end at a side heading out of it, one ends inside.
    strokes = [
        ([(0.5, 0.2), (0.8, 0.22), (0.99, 0.25)], False, False),
        ([(0.4, 0.5), (0.2, 0.52), (0.01, 0.5)], False, False),
        ([(0.99, 0.8), (0.7, 0.8)], False, False),
        ([(0.3, 0.3), (0.6, 0.35)], False, False),
    ]
    side = sheets.bleed(1500)
    assert side == round(sheets.BLEED * 1500) > 100
    page = np.array(sheets.PAGE[False], np.int16)
    for seed in (1, 2, 3, 4, 5, 6):
        wash, pen = sheets.layers(_crowd(), strokes, seed=seed)
        assert wash.size == pen.size == (1500 + 2 * side, 1000)
        assert sheets.field(wash).size == (1500, 1000)
        # The stains beside the field: in one place or two, each reaching
        # the layer's end (a phone's screen edge is nearer), the rest bare.
        stained = np.abs(np.asarray(wash, np.int16) - page).max(axis=2) > 14
        left, right = stained[:, : side - 4], stained[:, side + 1500 + 4 :]
        runs = 0
        for margin, end in ((left, 2), (right, side - 7)):
            rows = margin.any(axis=1).astype(np.int8)
            starts = int((np.diff(np.concatenate([[0], rows])) == 1).sum())
            assert starts <= 2
            runs += starts
            if starts:
                assert margin[:, end].any()  # as far as the layer goes
            assert rows.mean() < 0.5  # a tongue, not the whole side
        assert 1 <= runs <= 2
        # The pen beside the field: one stroke only, on one side.
        ink = np.asarray(pen)[..., 3] > 60
        out_left, out_right = ink[:, : side - 6], ink[:, side + 1500 + 6 :]
        assert out_left.any() != out_right.any()
        beyond = out_left if out_left.any() else out_right
        rows = np.flatnonzero(beyond.any(axis=1))
        assert rows.max() - rows.min() < 120  # one stroke's end, not three
    # What lies in the field does not depend on what runs out of it: the
    # same sheet as an app from before the margin gets.
    assert sheets.field(wash).size == sheets.render(_crowd(), strokes, seed=6).size
    # No stroke at a side, none goes on; a field bare at its sides spills nothing.
    calm = sheets.layers(_crowd(), [strokes[3]], seed=3)[1]
    assert not np.asarray(calm)[:, : side - 6, 3].any()
    assert not np.asarray(calm)[:, side + 1500 + 6 :, 3].any()
    bare = np.zeros((1000, 1500), bool)
    bare[:, 300:1200] = True
    edges = (np.ones(1000, np.int32), np.ones(1000, np.int32))
    assert not sheets._spills(bare, side, np.random.default_rng(1), edges)[0].any()


def test_what_runs_out_is_one_stain_of_one_colour() -> None:
    """Mateusz 2026-11-12 11:48, of the margin that mirrored the picture:
    "to musiałaby być jednolita plama, a nie odbicie lustrzane
    skomplikowanego układu"."""
    # A green strip down the left side and a yellow one down the right,
    # discs of every colour between them: a mirror would carry the discs out.
    crowd = _crowd()
    canvas = ImageDraw.Draw(crowd)
    canvas.rectangle((0, 0, 17, 400), fill=(40, 150, 70))
    canvas.rectangle((582, 0, 600, 400), fill=(225, 190, 50))
    side = sheets.bleed(1500)
    page = np.array(sheets.PAGE[False], np.int16)
    ran = 0
    for seed in (1, 2, 3, 4):
        wash = np.asarray(sheets.layers(crowd, seed=seed)[0], np.int16)
        stained = np.abs(wash - page).max(axis=2) > 30
        left, right = wash[:, : side - 8], wash[:, side + 1500 + 8 :]
        for margin, there, green in (
            (left, stained[:, : side - 8], True),
            (right, stained[:, side + 1500 + 8 :], False),
        ):
            if there.sum() < 500:
                continue
            ran += 1
            r, g, b = (margin[..., k][there] for k in range(3))
            one = (g > r + 12) & (g > b + 12) if green else (r > b + 40) & (g > b + 30)
            assert one.mean() > 0.97
    assert ran >= 4


def test_what_is_white_in_the_picture_stays_white() -> None:
    """Mateusz 2026-11-12 11:31, of a portrait's linen painted in the cream
    of the face: "(3) wskazuje i opisuje biel tkanin, a na szkicu jest
    cielisty-kremowy"."""
    # A dark ground, a red coat, a face and linen yellowed by the varnish.
    portrait = Image.new("RGB", (600, 400), (62, 52, 50))
    canvas = ImageDraw.Draw(portrait)
    canvas.rectangle((150, 120, 450, 400), fill=(170, 40, 30))
    canvas.ellipse((230, 40, 370, 200), fill=(236, 180, 130))
    canvas.rectangle((255, 215, 345, 330), fill=(243, 225, 192))
    found = sheets.whites(np.asarray(portrait))
    tall, wide = found.shape
    assert found[int(0.6 * tall) : int(0.78 * tall), int(0.45 * wide) : int(0.55 * wide)].all()
    assert not found[int(0.2 * tall) : int(0.4 * tall), int(0.45 * wide) : int(0.55 * wide)].any()
    assert 0.03 < found.mean() < 0.08
    linen, face = (slice(590, 780), slice(680, 820)), (slice(180, 420), slice(680, 820))
    light = np.asarray(sheets.render(portrait, seed=3), np.int16)
    # On the light page it is the paper, clearly lighter than the face.
    assert np.abs(light[linen] - np.array(sheets.PAGE[False])).max(axis=2).mean() < 10
    assert light[linen].mean(axis=(0, 1)).sum() > light[face].mean(axis=(0, 1)).sum() + 60
    # On the dark page light paint, plain, the lightest thing on the sheet.
    night = np.asarray(sheets.render(portrait, dark=True, seed=3), np.int16)
    paint = night[linen].mean(axis=(0, 1))
    assert paint.min() > 170 and paint.max() - paint.min() < 30
    assert paint.sum() > night[face].mean(axis=(0, 1)).sum() + 60
    # A pale blue sky is a colour, not a white; neither is a lamp's yellow.
    assert not sheets.whites(np.asarray(_scene())).any()
    lamp = Image.new("RGB", (600, 400), (40, 36, 60))
    ImageDraw.Draw(lamp).ellipse((240, 140, 360, 260), fill=(255, 214, 90))
    assert not sheets.whites(np.asarray(lamp)).any()


def _storm(size: tuple[int, int] = (600, 400)) -> Image.Image:
    """A storm under an old varnish: a great dark sky, a cloud with an
    opening of grey-blue as light as it, a sea whose browns run from dark
    to light band by band."""
    img = Image.new("RGB", size, (70, 52, 42))
    canvas = ImageDraw.Draw(img)
    canvas.ellipse((150, 110, 560, 330), fill=(176, 158, 128))  # the cloud
    canvas.ellipse((215, 150, 345, 235), fill=(128, 146, 150))  # the opening
    for k in range(9):  # the sea: each band a little lighter than the last
        tone = 62 + 19 * k
        canvas.rectangle((0, 240 + 18 * k, 600, 258 + 18 * k), fill=(tone, tone - 10, tone - 24))
    return img


def test_the_sheet_keeps_what_the_picture_is_made_of() -> None:
    """Mateusz 2026-11-12 13:46, of a storm by Turner: "na szkicu bardzo
    brakuje ciemnej plamy nieba. to istotny element, a akwarela go
    pominęła. chyba błękit/prześwit nieba też powinien się pokazać w
    akwareli"; "Szkic musi oddawać istotę i ideę obrazu"."""
    storm = _storm()
    piece, colours = sheets.masses(np.asarray(storm), seed=3)
    tall, wide = piece.shape

    def at(x: float, y: float) -> int:
        return int(piece[int(y * tall), int(x * wide)])

    # Tones that run into one another are not one stain from the darkest
    # to the lightest: the sea's dark is another than its light.
    assert at(0.05, 0.63) != at(0.05, 0.97)
    assert colours[at(0.05, 0.97)].sum() > colours[at(0.05, 0.63)].sum() + 0.6
    # The opening is a stain of its own, though as light as the cloud.
    sky, cloud, opening = at(0.1, 0.1), at(0.8, 0.5), at(0.47, 0.48)
    assert len({sky, cloud, opening}) == 3
    assert abs(float(colours[opening].sum() - colours[cloud].sum())) < 0.25
    for dark in (False, True):
        sheet = np.asarray(sheets.render(storm, dark=dark, seed=3), np.int16)
        # ... and is blue on the sheet beside a cloud that is not.
        blue = sheet[440:520, 620:780].mean(axis=(0, 1))
        cream = sheet[420:560, 1150:1300].mean(axis=(0, 1))
        assert blue[2] > blue[0] + 6 and cream[0] > cream[2] + 10
    # The dark sky is painted on the light page, quiet as it is and at the
    # field's edge: a dark stain, darker than the cloud under it.
    light = sheets.render(storm, seed=3)
    assert _bare(light)[40:240, 40:1460].mean() < 0.02
    lit = np.asarray(light, np.float32)
    assert lit[60:220, 100:1400].mean() < lit[420:560, 1150:1300].mean() - 40
    # A picture all in one green has no varnish to see through: its paint
    # stays green.
    wood = Image.new("RGB", (600, 400), (70, 110, 60))
    canvas = ImageDraw.Draw(wood)
    canvas.rectangle((0, 0, 600, 150), fill=(120, 150, 90))
    canvas.ellipse((250, 180, 380, 300), fill=(150, 160, 90))
    green = np.asarray(sheets.render(wood, seed=3), np.int16)[450:700, 150:450].mean(axis=(0, 1))
    assert green[1] > green[0] + 12 and green[1] > green[2] + 12


def test_the_sheets_are_made_ahead_of_the_reader(tmp_path: Path) -> None:
    """Mateusz 2026-11-12 09:47: "Po wejściu w studium sporo czasu czekam aż
    pojawi się obraz analizy kompozycji"."""
    app = _app(tmp_path)
    svc: FrameService = app.state.service
    with TestClient(app):
        _catalogue(svc)
        assert svc.sheets.wanting() == [] and svc.sheets.ahead() is False
        _old_page(svc)
        item = svc.library.get("met:1")
        assert item is not None
        assert [(i.id, dark) for i, _, dark in svc.sheets.wanting()] == [
            ("met:1", False),
            ("met:1", True),
        ]
        assert svc.sheets.ahead() is True and svc.sheets.ahead() is True
        assert svc.sheets.wanting() == [] and svc.sheets.ahead() is False
        view = svc.sheets.view(item)
        assert view is not None
        for dark in (False, True):
            for layer in ("", "wash", "pen", "wash-bleed", "pen-bleed"):
                assert svc.sheets.path(item, view, dark, layer).is_file()
        # A work whose picture cannot be had does not hold the others up.
        for kept in svc.sheets.dir.iterdir():
            kept.unlink()

        def gone(item: Any, urgent: bool = False) -> Any:
            raise OSError("no picture")

        svc.images.picture = gone  # type: ignore[method-assign]
        assert svc.sheets.ahead() is True  # tried
        assert svc.sheets.wanting() == [] and svc.sheets.ahead() is False


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
    answers = _pipeline(asked, PRINT, of=(720, 360), boat=False)  # (the pen draws the field)

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
    # The pen: fractions of the picture, whatever size it has; too few strokes are none.
    blank = Image.new("RGB", (900, 600), "white")
    drawn = pen_strokes(SKETCH, blank)
    assert drawn is not None and len(drawn) == 4
    horizon = drawn[3]  # (what is not the subject comes last)
    assert (horizon.points[1].x, round(horizon.points[1].y, 3)) == (1.0, 0.5) and horizon.sharp
    assert pen_strokes({"szkic": SKETCH["szkic"][:2]}, blank) is None
    assert pen_strokes(None, blank) is None
    # (a larger picture is read at the same size, the most a model reads: the same pixels)
    assert pen.read_size(1800, 1200) == pen.read_size(900, 600)
    assert pen_strokes(SKETCH, Image.new("RGB", (1800, 1200), "white")) == drawn


def test_the_pen_draws_the_subject_closely_and_little_else() -> None:
    """Mateusz 2026-11-12 14:50: "Najlepiej gdyby rysunek był dokładny tam
    gdzie dzieło tego wymaga (temat, postać, istotny fragment) a pominięty
    lub bardzo ogólny w reszcie dzieła"; 17:32: "Lepszy był rysunek modelu,
    ale musi być dokładniejszy"."""
    blank = Image.new("RGB", (900, 600), "white")
    p = pen_points
    kx, ky = pen.read_size(900, 600)[0] / 900, pen.read_size(900, 600)[1] / 600

    def place(what: str, x: float, y: float, w: float, h: float) -> dict[str, Any]:
        return {"co": what, "x": x * kx, "y": y * ky, "w": w * kx, "h": h * ky}

    plan = {
        "temat": "statek na morzu",
        "fragmenty": [
            place("statek", 300, 100, 320, 330),
            place("bandera", 440, 100, 80, 60),
            place("drobiazg", 10, 10, 5, 5),  # too small: widened to the least worth a look
            place("wszystko", 0, 0, 900, 560),  # most of the picture: no closer
            {"co": "nic", "x": "?", "y": 0, "w": 10, "h": 10},
        ],
        "szkic": [
            _line("brzeg morza", p((0, 404), (900, 404)), temat=False, ostra=True),
            _line("fala", p((100, 500), (250, 470), (400, 500)), temat=True),
            _line("lina na brzeg", p((200, 250), (500, 250)), temat=True, ostra=True),
            _line("rama", p((2, 2), (898, 2), (898, 598), (2, 598)), temat=True, zamknieta=True),
            *[
                _line(f"chmura {n}", p((40, 20 + 8 * n), (860, 30 + 8 * n)), temat=False)
                for n in range(7)
            ],
        ],
    }
    places = pen.boxes(plan, blank.size)
    assert [name for name, _ in places] == ["statek", "bandera", "drobiazg"]
    ship, flag, speck = (box for _, box in places)
    assert (round(ship.x * 900), round(ship.w * 900), round(ship.h * 600)) == (300, 320, 330)
    assert round(speck.w * 900) == round(900 / 14)  # (and kept inside the picture)
    assert speck.x == 0 and speck.y == 0
    # The ship's close-up: its place and a tenth around it (267 to 653 by 67
    # to 463), enlarged four times; the flag's: 432 to 528 by 90 to 170.
    hull = _line("kadłub", "172,1132 1372,1132 1212,1412 332,1412", ostra=True, zamknieta=True)
    mast = _line("maszt", "732,152 732,1100", ostra=True)
    sail = _line("żagiel w banderze", "700,160 900,160 900,380 700,380", lekka=True)
    cloth = _line("płótno", "40,40 340,40 340,260 40,260", zamknieta=True)
    closer = [{"szkic": [hull, mast, sail]}, {"szkic": [cloth]}]
    drawn = pen_strokes({**plan, pen.CLOSE_KEY: closer}, blank)
    assert drawn is not None
    # The subject first: what the whole picture gave of it outside the places
    # (the rope is cut at the ship's side, the frame of the picture is left
    # out), then each place as its close-up drew it, the larger first, then
    # a few lines of the rest.
    assert len(drawn) == 2 + 2 + 1 + pen.MAX_GENERAL
    wave, rope, ship_hull, ship_mast, flag_cloth = drawn[: -pen.MAX_GENERAL]
    assert len(wave.points) == 3 and wave.weight == 1.0
    assert round(rope.points[0].x * 900) == 200 and abs(rope.points[-1].x * 900 - 300) < 3
    # The ship's own strokes are thinner than the whole's, the flag's thinner
    # still: a hand presses less on what is small.
    assert ship_hull.closed and ship_hull.sharp and ship_hull.weight == 0.87
    assert [(round(pt.x * 900), round(pt.y * 600)) for pt in ship_hull.points] == [
        (310, 350),
        (610, 350),
        (570, 420),
        (350, 420),
    ]
    # The ship gives way to the flag in it: its mast begins where the flag's
    # place ends and its sail there is gone; the flag's own close-up drew it.
    top, foot = ship_mast.points
    assert abs(top.y - (flag.y + flag.h)) < 0.004 and round(foot.y * 600) == 342
    assert flag_cloth.closed and flag_cloth.weight == 0.59
    assert all(_inside(pt, flag) for pt in flag_cloth.points)
    # Of the rest a few lines: the shore (cut where the ship stands), some clouds.
    assert all(s.weight == 1.0 for s in drawn[-pen.MAX_GENERAL :])
    assert abs(drawn[-pen.MAX_GENERAL].points[-1].x * 900 - 300) < 3
    # A place whose close-up gave nothing keeps what the whole drew of it.
    kept = pen_strokes({**plan, pen.CLOSE_KEY: [None, None]}, blank)
    assert kept is not None and len(kept[1].points) == 2
    assert [round(pt.x * 900) for pt in kept[1].points] == [200, 500]


def _inside(point: Any, box: Box) -> bool:
    return box.x <= point.x <= box.x + box.w and box.y <= point.y <= box.y + box.h


def test_the_pen_asks_about_the_whole_then_about_each_place() -> None:
    whole = Image.new("RGB", (3000, 2000), "white")
    asked = pen.question(whole, ["Statek", "Łódź", "Statek", " "])
    assert asked["model"] == FABLE and asked["output_config"]["effort"] == "medium"
    said = asked["messages"][0]["content"][-1]["text"]
    width, height = pen.read_size(3000, 2000)
    assert max(width, height) > 2000  # as large as a model reads one
    assert f"OBRAZ: {width} × {height} px" in said
    assert said.endswith("ANALIZA WSKAZUJE: Statek; Łódź")
    assert "ANALIZA" not in pen.question(whole)["messages"][0]["content"][-1]["text"]
    assert {"temat", "fragmenty", "szkic"} <= set(
        asked["output_config"]["format"]["schema"]["properties"]
    )
    # A small picture is enlarged, at most four times.
    assert pen.read_size(300, 200) == (1200, 800)

    # The whole answer: the first one and, in the order of its places, what
    # each close-up drew (asked together when that can be).
    small = Image.new("RGB", (900, 600), "white")
    plan = sketch(boat=True)
    questions: list[dict[str, Any]] = []

    def ask(params: dict[str, Any]) -> dict[str, Any] | None:
        questions.append(params)
        return plan if params["system"][0]["text"] == pen.SYSTEM else CLOSE

    together: list[int] = []

    def many(several: list[dict[str, Any]]) -> list[dict[str, Any] | None]:
        together.append(len(several))
        return [ask(params) for params in several]

    drawn = pen.draw(small, ["Łódź"], ask, many)
    assert drawn is not None and drawn[pen.CLOSE_KEY] == [CLOSE] and together == [1]
    first, close = questions
    assert first["model"] == pen.MODEL == FABLE and close["model"] == pen.CLOSE_MODEL == OPUS
    assert close["system"][0]["text"] == pen.CLOSE_SYSTEM
    found = pen_strokes(drawn, small)
    assert found is not None and len(found) == 5
    # The first answer had already (a night's batch): only the close-ups are asked.
    questions.clear()
    assert pen.draw(small, [], ask, plan=plan) == drawn
    assert [q["model"] for q in questions] == [OPUS]
    # One who will not draw the whole: asked of the spare; with no answer
    # from it either there is no sketch.
    questions.clear()
    refusing = iter([None, plan, CLOSE])
    assert pen.draw(small, [], lambda params: questions.append(params) or next(refusing)) == drawn
    assert [q["model"] for q in questions] == [FABLE, pen.SPARE, OPUS]
    assert pen.draw(small, [], lambda params: None) is None
    assert pen_strokes(None, small) is None


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
        # Each as it is whole, its stains and its pen, and those two with
        # the margin beside the field.
        assert view is not None and len(list(svc.sheets.dir.glob("*.jpg"))) == 6
        assert len(list(svc.sheets.dir.glob("*.png"))) == 4
        made = svc.sheets.path(item, view, False).stat().st_mtime_ns
        assert client.get(url).content == got.content
        assert svc.sheets.path(item, view, False).stat().st_size == len(got.content)
        assert made <= svc.sheets.path(item, view, False).stat().st_mtime_ns
        # The app that draws the sheet before the reader asks for its two
        # layers: the stains with no pen, the pen with nothing round it.
        assert work["composition_layers"] is True
        wash = client.get(url + "&layer=wash")
        assert wash.headers["content-type"] == "image/jpeg" and wash.content != got.content
        pen = client.get(url + "&layer=pen")
        assert pen.headers["content-type"] == "image/png"
        ink = Image.open(io.BytesIO(pen.content))
        assert ink.mode == "RGBA" and ink.size == light.size
        assert client.get(url + "&layer=other").status_code == 422
        # The app that lets the sheet run out of its frame asks for them
        # with the page's margin beside the field (Mateusz 2026-11-12 11:04).
        assert work["composition_bleed"] == sheets.BLEED
        wider = (light.size[0] + 2 * sheets.bleed(light.size[0]), light.size[1])
        out = client.get(url + "&layer=wash-bleed")
        assert out.headers["content-type"] == "image/jpeg"
        assert Image.open(io.BytesIO(out.content)).size == wider
        out = client.get(url + "&layer=pen-bleed&dark=1")
        assert out.headers["content-type"] == "image/png"
        assert Image.open(io.BytesIO(out.content)).size == wider
        # Another sketch or field is another sheet at another address.
        blank = Image.new("RGB", (900, 600), "white")
        sketched = view.model_copy(update={"sketch": pen_strokes(SKETCH, blank)})
        assert Sheets.key(sketched) != Sheets.key(view)
        assert Sheets.key(
            view.model_copy(update={"field": Box(x=0.1, y=0.1, w=0.8, h=0.6)})
        ) != Sheets.key(view)
        # An address from before the analysis was made anew still gets the take's sheet.
        assert client.get("/api/composition/sheet?item=met%3A1&v=old").status_code == 200
        assert client.get("/api/composition/sheet?item=met%3A2").status_code == 404
        assert client.get("/api/composition/sheet?item=nothing%3A1").status_code == 404
    assert STUDY


def test_sketches_of_an_earlier_pen_are_drawn_again_at_night(service: FrameService) -> None:
    """Mateusz 2026-11-12 09:47: the pen's contours "trochę dokładniejsze,
    może być ich też trochę więcej", in the studies there are too; 08:15,
    of work nobody waits for: "w pakiecie? Tzn wolniej ale taniej?"."""
    from test_ai import GOOD_KEY, FakeAnthropic, _message
    from test_ordered_later import _batched

    from frame_server.ai.composition import drawn_from
    from frame_server.ai.jobs import BATCHES_KEY, LATER_KEY

    _catalogue(service)
    item = service.library.get("met:1")
    assert item is not None
    fake = FakeAnthropic(GOOD_KEY)
    got = _batched(fake)
    of = drawn_from(service.images, item, None).size  # (the catalogue's test picture)
    plan = sketch(of, boat=True)
    read = pen.read_size(*of)
    fuji = {"co": "Fudżi", "x": 0.6 * read[0], "y": 0.6 * read[1], "w": 0.16, "h": 0.14}
    plan["fragmenty"].append({**fuji, "w": 0.16 * read[0], "h": 0.14 * read[1]})
    answers = {pen.SYSTEM: plan, pen.CLOSE_SYSTEM: CLOSE}

    def results(batch_id: str) -> list[Any]:
        out = []
        for r in fake.batches[batch_id]:
            got.append(r["params"])
            message = _message(answers[r["params"]["system"][0]["text"]])
            message.model = r["params"]["model"]
            ok = SimpleNamespace(type="succeeded", message=message)
            out.append(SimpleNamespace(custom_id=r["custom_id"], result=ok))
        return out

    fake.messages.batches.results = results
    service.claude.factory = lambda key: fake
    service.ai_config.set_key(GOOD_KEY)
    service.ai_config.update(
        AiConfigUpdate(keywords_artworks=False, keywords_photos=False, pl_text=False)
    )
    job = service.ai.jobs[PEN]
    assert isinstance(job, PenJob) and job.night and job.follow_up and job.model == FABLE
    # A page whose whole analysis is about to be made again gets the new pen with it.
    _old_page(service, **{CHECK_ROUND: ROUND - 1})
    assert not job.wanted(item)
    # One that has its analysis: its sketch alone, at night, never at once.
    _old_page(service, **{CHECK_ROUND: ROUND})
    service.compose.forget()
    job._pages = (0.0, set())
    assert job.wanted(item) and not job.in_library(item)
    assert service.ai.need_now("met:1", PEN).result(timeout=1) is None
    assert service.ai.order_night() == 1 and not fake.asked
    (requests,) = fake.batches.values()
    asked = requests[0]["params"]
    assert asked["model"] == FABLE and asked["system"][0]["text"] == pen.SYSTEM
    assert "timeout" not in asked  # (the client's own, no part of a request)
    assert service.ai.order_night() == 0  # already in a batch
    # The pen's first answer in: the place it asked to see closer goes into
    # a batch of its own, for half the price too; nothing is asked at once.
    fake.ended = True
    assert service.ai.poll_batches() == 0
    assert list(fake.batches) == ["batch_1", "batch_2"] and not fake.asked
    close, other = fake.batches["batch_2"]  # both places together
    assert (close["custom_id"], other["custom_id"]) == ("q", "q1")
    assert close["params"]["model"] == other["params"]["model"] == OPUS
    assert close["params"]["system"][0]["text"] == pen.CLOSE_SYSTEM
    assert "FRAGMENT: łódź" in close["params"]["messages"][0]["content"][-1]["text"]
    assert "FRAGMENT: Fudżi" in other["params"]["messages"][0]["content"][-1]["text"]
    assert service.ai.later(PEN, "met:1") and service.ai.order_night() == 0
    page = service.library.note("met:1", STUDY)
    assert page is not None and wants(page)  # not drawn yet
    assert service.ai.poll_batches() == 1
    assert service.library.get_state(LATER_KEY, {}) == {}
    assert service.library.get_state(BATCHES_KEY, []) == []
    assert [q["model"] for q in got] == [FABLE, OPUS, OPUS]
    page = service.library.note("met:1", STUDY)
    assert page is not None and page.data[pen.PEN_KEY] == pen.ROUND
    shown = page_views(page.data)[0]
    # The crest as the whole picture gave it, the boat and Fuji as their
    # close-ups drew them (what the whole had of them is gone), the horizon.
    crest, hull, oar, *fuji, horizon = shown.sketch
    assert crest.weight == horizon.weight == 1.0 and horizon.sharp and len(crest.points) == 3
    assert hull.closed and hull.weight == 0.83 and oar.weight == 0.52
    assert len(fuji) == 3 and all(s.weight < hull.weight for s in fuji)
    assert [m.title for m in shown.marks]  # the analysis itself is as it was
    assert not job.wanted(item) and service.ai.order_night() == 0
    # Another sketch is another sheet, made ahead like any.
    assert [(i.id, dark) for i, _, dark in service.sheets.wanting()] == [
        ("met:1", False),
        ("met:1", True),
    ]
    # The versions a page keeps of the same field get it too; an answer
    # with no sketch leaves the one there was and is not asked again.
    kept = {**page.data, "composition_versions": [{"composition": page.data["composition"]}]}
    strokes = pen_strokes(SKETCH, Image.new("RGB", (900, 600), "white"))
    assert strokes is not None
    again = redrawn({**kept, pen.PEN_KEY: 1}, strokes[:3] + strokes[:1])
    assert len(page_views(again)[0].sketch) == 4
    assert again["composition_versions"][0]["composition"] == again["composition"]
    left = redrawn({**kept, pen.PEN_KEY: 1}, None)
    assert left["composition"] == kept["composition"] and left[pen.PEN_KEY] == pen.ROUND
    # Which pages are drawn again is the owner's word (the redrawing costs):
    # he said yes for the first pen's pages and for the second's, and was
    # not asked yet about the third's.
    assert wants(page.model_copy(update={"data": {**page.data, pen.PEN_KEY: 1}}))
    assert wants(page.model_copy(update={"data": {**page.data, pen.PEN_KEY: 2}}))
    assert not wants(page.model_copy(update={"data": {**page.data, pen.PEN_KEY: 3}}))
    assert pen.REDRAWN <= pen.ROUND
