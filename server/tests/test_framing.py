from __future__ import annotations

import json

import numpy as np
import pytest
from conftest import jpeg_bytes
from fastapi.testclient import TestClient
from PIL import Image

from frame_server.imaging import PRESETS
from frame_server.imaging.color import linear_to_oklab
from frame_server.imaging.interest import InterestMap, detect_faces
from frame_server.imaging.layout import (
    WHOLE,
    Crop,
    Fit,
    Orientation,
    caption_band,
    crop_box,
    detail_zoom,
    plan_layout,
    resolve_fit,
    whole,
)
from frame_server.imaging.mat import crease_dots, picture_tint
from frame_server.imaging.palette import SPECTRA6
from frame_server.imaging.pipeline import render
from frame_server.imaging.text import TextBlock, text_block_mask
from frame_server.library import ItemKind

CANVAS = (2560, 1440)


@pytest.mark.parametrize(
    ("size", "fit", "expected"),
    [
        ((1600, 900), Fit.AUTO, Fit.FILL),  # 16:9 on 16:9
        ((1200, 900), Fit.AUTO, Fit.FIT),  # 4:3: little room beside it
        ((800, 1200), Fit.AUTO, Fit.DESCRIPTION),  # portrait on a landscape frame
        ((1600, 900), Fit.DESCRIPTION, Fit.DESCRIPTION),  # chosen modes always apply
    ],
)
def test_auto_picks_fill_fit_or_description(size, fit, expected) -> None:
    assert resolve_fit(size, CANVAS, fit) == expected


def test_retired_details_mode_becomes_description() -> None:
    from frame_server.library.models import Framing
    from frame_server.schedule import FrameSettings

    settings = FrameSettings.model_validate({"art": {"fit": "details"}})
    assert settings.art.fit == Fit.DESCRIPTION
    wide, close = {"x": 0.2, "zoom": 1.5}, {"x": 0.7, "zoom": 2.5}
    framing = Framing.model_validate({"details": [wide, close]})
    assert framing.detail == Crop(**close)  # the closer one
    kept = Framing.model_validate({"details": [wide, close], "detail": wide})
    assert kept.detail == Crop(**wide)


def test_crop_box_zoom_and_clamping() -> None:
    # Cover crop of a 16:9 window on a 1000×1000 picture, then 2× closer.
    assert crop_box((1000, 1000), 16 / 9, Crop()) == pytest.approx((0, 218.75, 1000, 781.25))
    x0, _, x1, y1 = crop_box((1000, 1000), 16 / 9, Crop(x=0.0, y=1.0, zoom=2))
    assert (x0, y1) == (0, 1000) and x1 == pytest.approx(500)


def test_description_layout_sides() -> None:
    plan = plan_layout((800, 1200), CANVAS, Fit.DESCRIPTION, margin=0.05)
    main, close_up = plan.windows
    assert main.role == "picture" and main.rect == (0, 0, 960, 1440)
    assert close_up.role == "detail" and close_up.rect[0] > 960  # beside the picture
    assert plan.text_rect is not None and plan.text_rect[1] > close_up.rect[1] + close_up.rect[3]
    # The portrait frame and a landscape picture: picture on top, the rest side by side.
    plan = plan_layout((1500, 600), (1440, 2560), Fit.DESCRIPTION)
    main, close_up = plan.windows
    assert main.rect == (0, 0, 1440, 576) and close_up.rect[1] > 576
    assert plan.text_rect is not None and plan.text_rect[1] == close_up.rect[1]


@pytest.mark.parametrize("canvas", [CANVAS, (1440, 2560)])
def test_description_without_room_makes_the_picture_smaller(canvas) -> None:
    size = (canvas[0] * 9, canvas[1] * 9)  # the frame's own shape: no room beside it
    plan = plan_layout(size, canvas, Fit.DESCRIPTION, margin=0.05, caption=True)
    assert plan.fit == Fit.DESCRIPTION
    main, first = plan.windows
    x, y, w, h = main.rect
    assert x > 0 and y > 0 and w < canvas[0] and h < canvas[1]  # in a mat window now
    assert abs(w / h - size[0] / size[1]) < 0.01  # the whole picture
    beside = first.rect
    rest = plan.text_rect
    assert rest is not None
    # The close-up and the text line up with the picture.
    if beside[0] > x + w:  # a column at the right
        assert beside[1] == y and rest[1] + rest[3] == y + h
    else:  # a row below
        assert beside[0] == x and rest[0] + rest[2] == x + w
    assert min(beside[2], beside[3]) >= 0.2 * min(canvas)


def test_description_gives_the_picture_priority() -> None:
    canvas = (1440, 2560)
    # A little wider than tall-and-narrow: across the frame, as close to its
    # sides as to its top; the close-up and the text below get the rest.
    plan = plan_layout((750, 1000), canvas, Fit.DESCRIPTION)
    (x, y, w, _), (_, ry, _, rh) = (window.rect for window in plan.windows)
    assert x == y and w == canvas[0] - 2 * x and ry + rh == canvas[1] - y
    # Narrower (Monet's Rue Montorgueil): about as wide, a low row kept below.
    plan = plan_layout((617, 1000), canvas, Fit.DESCRIPTION)
    (x, y, _, _), (_, _, _, rh) = (window.rect for window in plan.windows)
    assert x < 1.3 * y and 0.2 * canvas[0] <= rh < 0.12 * canvas[1]


def test_fit_crop_takes_any_shape() -> None:
    plain = plan_layout((800, 1200), CANVAS, Fit.FIT, margin=0.05)
    (window,) = plain.windows
    assert window.crop is not None and window.box == pytest.approx(whole((800, 1200)))
    square = plan_layout(
        (800, 1200), CANVAS, Fit.FIT, margin=0.05, fit_crop=Crop(y=0.3, zoom=1.5, aspect=1.0)
    )
    (window,) = square.windows
    _, _, w, h = window.rect
    assert w == h and h == 1440 - 2 * 72  # the square fills the height between the margins
    x0, y0, x1, y1 = window.box
    assert x1 - x0 == pytest.approx(800 / 1.5) and y1 - y0 == pytest.approx(800 / 1.5)
    assert (y0 + y1) / 2 == pytest.approx(0.3 * 1200)


def test_picture_tint_follows_the_main_hue() -> None:
    white, black = np.ones(3, np.float32), np.zeros(3, np.float32)
    blue = np.zeros((100, 100, 3), np.float32)
    blue[:] = (0.1, 0.25, 0.7)
    blue[:20] = (0.6, 0.1, 0.05)  # a little red
    tint = picture_tint(blue, white, black)
    light, a, b = linear_to_oklab(tint)
    assert light > 0.85 and b < 0 and np.hypot(a, b) <= 0.025  # pale, blue, muted
    dark = picture_tint(blue * 0.02, white, black)
    assert linear_to_oklab(dark)[0] < 0.4  # a deep mat for a dark picture
    grey = picture_tint(np.full((10, 10, 3), 0.4, np.float32), white, black)
    assert np.hypot(*linear_to_oklab(grey)[1:]) < 0.013  # nearly colourless: an off-white


def test_picture_mat_and_its_lettering() -> None:
    settings = PRESETS["painting"].model_copy(deep=True)
    settings.layout.fit = Fit.FIT
    settings.layout.mat = "picture"
    settings.caption = "Someone — Something"
    dark = render(Image.new("RGB", (800, 1000), (30, 20, 15)), settings)
    plan = plan_layout((800, 1000), CANVAS, Fit.FIT, margin=0.05, caption=True)
    right, top, _ = plan.caption_at
    white = SPECTRA6.device_u8()[SPECTRA6.white_index()]
    text = dark.panel[top : top + 40, right - 300 : right]
    assert np.any(np.all(text == white, axis=-1))  # white letters on a deep mat


def test_description_layout() -> None:
    plan = plan_layout((800, 1200), CANVAS, Fit.DESCRIPTION, caption=True)
    main, close_up = plan.windows
    assert plan.fit == Fit.DESCRIPTION and (main.role, close_up.role) == ("picture", "detail")
    assert plan.caption_at is None  # the text says it all
    assert plan.text_rect is not None and plan.text_rect[1] > close_up.rect[1] + close_up.rect[3]
    assert main.crop == WHOLE and main.box == pytest.approx(whole((800, 1200)))


def enlargement(plan) -> float:
    """How much larger the close-up shows the picture than the main window."""
    main, close_up = plan.windows
    scale = [w.rect[2] / (w.box[2] - w.box[0]) for w in (main, close_up)]
    return scale[1] / scale[0]


@pytest.mark.parametrize(
    ("size", "canvas"),
    [
        ((800, 1200), CANVAS),  # a small source: the pixels would allow little zoom
        ((8000, 12000), CANVAS),  # a large one
        ((1500, 600), (1440, 2560)),
        ((2400, 1500), (1440, 2560)),  # little room: the picture is smaller
    ],
)
def test_automatic_close_up_is_at_least_much_larger(size, canvas) -> None:
    plan = plan_layout(size, canvas, Fit.DESCRIPTION)
    assert enlargement(plan) >= 1.8 - 1e-6
    # Also when the picture itself is zoomed in its window.
    zoomed = plan_layout(size, canvas, Fit.DESCRIPTION, picture_crop=Crop(zoom=1.5))
    assert enlargement(zoomed) >= 1.8 - 1e-6
    # A close-up chosen by the user is kept as it is.
    mine = plan_layout(size, canvas, Fit.DESCRIPTION, detail=Crop(zoom=1.0))
    assert mine.windows[1].crop == Crop(zoom=1.0)


def test_detail_zoom_prefers_the_sources_pixels() -> None:
    # A large source and a small picture: as close as DETAIL_ZOOM, beyond 1.8×.
    assert detail_zoom((8000, 8000), 1.0, 800, 0.05) == pytest.approx(3.0)
    # The picture shown large: 1.8× it, even past the pixels' limit.
    assert detail_zoom((1000, 1000), 1.0, 800, 1.0) == pytest.approx(1.8 * 1000 / 800)


def test_description_picture_can_be_cropped() -> None:
    crop = Crop(x=0.3, y=0.4, zoom=2.0)
    plan = plan_layout((800, 1200), CANVAS, Fit.DESCRIPTION, picture_crop=crop)
    main = plan.windows[0]
    assert main.crop == crop and main.rect == (0, 0, 960, 1440)  # same window, same shape
    x0, y0, x1, y1 = main.box
    assert x1 - x0 == pytest.approx(400) and y1 - y0 == pytest.approx(600)
    assert (x0 + x1) / 2 == pytest.approx(0.3 * 800) and (y0 + y1) / 2 == pytest.approx(480)


def test_picture_edge_hides_behind_the_mat() -> None:
    for fit in (Fit.FIT, Fit.DESCRIPTION):
        picture = plan_layout((800, 1200), CANVAS, fit).windows[0]
        x0, y0, x1, y1 = picture.box
        assert 0 < x0 < 0.05 * 800 and 0 < y0 < 0.05 * 1200
        assert 0.95 * 800 < x1 < 800 and 0.95 * 1200 < y1 < 1200


def test_description_text_block() -> None:
    rect = (1400, 800, 1000, 560)
    meta = ["Alphonse Mucha", "1896 · lithograph"]
    block = TextBlock(title="Zodiac", meta=meta, body="Word " * 2000)
    mask = text_block_mask(CANVAS, rect, block)
    ys, xs = np.nonzero(mask)
    assert xs.min() >= rect[0] and xs.max() < rect[0] + rect[2]
    assert ys.min() >= rect[1] and ys.max() < rect[1] + rect[3]  # long body: cut, not spilled
    assert mask[rect[1] : rect[1] + 120].any()  # the title on top


def test_description_keeps_whole_sentences() -> None:
    from PIL import ImageDraw

    from frame_server.imaging.caption import font
    from frame_server.imaging.text import sentences, whole_sentences

    text = "Painted c. 1890 in Paris. It shows the artist's room! Then a very long third one."
    assert sentences(text) == [
        "Painted c. 1890 in Paris.",
        "It shows the artist's room!",
        "Then a very long third one.",
    ]
    draw = ImageDraw.Draw(Image.new("1", (10, 10)))
    fnt = font(30, "serif")
    width = round(draw.textlength("Painted c. 1890 in Paris. It shows the", font=fnt))
    assert whole_sentences(draw, text, fnt, width, 1) == "Painted c. 1890 in Paris."
    assert whole_sentences(draw, text, fnt, width, 2) == " ".join(sentences(text)[:2])


def test_fill_leaves_a_strip_for_the_caption() -> None:
    plan = plan_layout((1600, 900), CANVAS, Fit.FILL, caption=True)
    (window,) = plan.windows
    assert window.rect == (0, 0, 2560, 1440 - caption_band(CANVAS))
    assert plan.caption_at is not None and plan.caption_at[1] > window.rect[3]


def test_mat_colour_bevel_and_caption_ink() -> None:
    settings = PRESETS["painting"].model_copy(deep=True)
    settings.layout.fit = Fit.FIT
    settings.layout.mat = "black"
    settings.layout.margin = 0.1
    settings.caption = "Someone — Something, 1900"
    result = render(Image.new("RGB", (800, 1000), (200, 60, 40)), settings)
    panel = result.panel
    black = SPECTRA6.device_u8()[SPECTRA6.black_index()]
    white = SPECTRA6.device_u8()[SPECTRA6.white_index()]
    assert np.all(panel[20, 20] == black)  # the mat is pure black ink
    plan = plan_layout((800, 1000), CANVAS, Fit.FIT, margin=0.1, caption=True)
    x, y, w, h = plan.windows[0].rect
    # The bevels are cut in the board's colour: no white core around the window.
    for bevel in (panel[y + h + 3, x + 20 : x + w - 20], panel[y - 4, x + 20 : x + w - 20]):
        assert np.all(bevel == white, axis=-1).mean() < 0.2
    right, top, _ = plan.caption_at
    text = panel[top : top + 40, right - 400 : right]
    assert np.any(np.all(text == white, axis=-1))  # white letters on black


def test_interest_finds_the_busy_part() -> None:
    rng = np.random.default_rng(1)
    pixels = np.full((1200, 800, 3), 128, dtype=np.uint8)
    pixels[850:1150, 100:700] = rng.integers(0, 255, (300, 600, 3), dtype=np.uint8)
    img = Image.fromarray(pixels)
    (crop,) = InterestMap(img).pick(16 / 9, [1.0])
    assert crop.y > 0.65  # the noisy bottom, not the middle
    first, second = InterestMap(img).pick(2.3, [1.5, 2.5])
    assert (first.zoom, second.zoom) == (1.5, 2.5)
    b1 = crop_box(img.size, 2.3, first)
    b2 = crop_box(img.size, 2.3, second)
    # Not one next to the other: a clear gap between them in one direction.
    gap_x = max(b1[0], b2[0]) - min(b1[2], b2[2])
    gap_y = max(b1[1], b2[1]) - min(b1[3], b2[3])
    assert max(gap_x, gap_y) > 0


def test_face_detector_loads() -> None:
    assert detect_faces(Image.new("RGB", (640, 480), (90, 90, 90))) == []


def test_framing_api(service) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    svc = app.state.service
    item = svc.importer.add_upload(
        jpeg_bytes((200, 40, 40), size=(1600, 1000)), kind=ItemKind.OWN, title="Wide"
    )
    with TestClient(app) as client:
        settings = client.get("/api/settings").json()
        settings["art"]["fit"] = "fill"
        client.put("/api/settings", json=settings)

        url = f"/api/library/items/{item.id}/framing"
        view = client.get(url, params={"orientation": "landscape"}).json()
        assert view["fit"] == "fill" and len(view["windows"]) == 1
        assert not view["windows"][0]["custom"]
        # The app draws its crop over the preview, at the window's place.
        x, y, w, h = view["windows"][0]["rect"]
        assert (x, y, w) == (0, 0, 1) and 0.9 < h <= 1 and view["windows"][0]["area"] is None

        crop = {"x": 0.3, "y": 0.5, "zoom": 1.5}
        saved = client.put(url, json={"orientation": "landscape", "crops": [crop]}).json()
        assert saved["windows"][0]["custom"] and saved["windows"][0]["crop"]["zoom"] == 1.5
        stored = svc.library.get(item.id).framing["landscape"].fill
        assert stored.zoom == 1.5
        # The automatic crop, offered without forgetting the saved one.
        auto = client.get(url, params={"orientation": "landscape", "automatic": True}).json()
        assert not auto["windows"][0]["custom"] and auto["windows"][0]["crop"]["zoom"] == 1
        assert svc.library.get(item.id).framing["landscape"].fill == stored
        render_settings = svc.player.render_settings(svc.library.get(item.id), svc.player.settings)
        assert render_settings.layout.crop == stored

        two = {"orientation": "landscape", "crops": [crop, crop]}
        assert client.put(url, json=two).status_code == 422  # FILL takes one

        reset = client.delete(url, params={"orientation": "landscape"}).json()
        assert not reset["windows"][0]["custom"]

        settings["art"]["fit"] = "description"
        client.put("/api/settings", json=settings)
        view = client.get(url, params={"orientation": "portrait"}).json()
        assert view["fit"] == "description" and len(view["windows"]) == 2
        picture, close_up = view["windows"]
        assert (picture["role"], close_up["role"]) == ("picture", "detail")
        # Only the close-up (apps that could not crop the picture yet).
        one = {"orientation": "portrait", "crops": [crop]}
        saved = client.put(url, json=one).json()
        assert saved["windows"][1]["custom"]
        stored = svc.library.get(item.id).framing["portrait"]
        assert stored.detail == Crop(**crop) and stored.picture is None
        # The picture left as it was stays automatic; a moved one is saved.
        both = {"orientation": "portrait", "crops": [picture["crop"], crop]}
        client.put(url, json=both)
        assert svc.library.get(item.id).framing["portrait"].picture is None
        moved = {"x": 0.4, "y": 0.5, "zoom": 1.6}
        both = {"orientation": "portrait", "crops": [moved, crop]}
        saved = client.put(url, json=both).json()
        assert saved["windows"][0]["crop"]["zoom"] == 1.6
        stored = svc.library.get(item.id).framing["portrait"]
        assert stored.picture == Crop(**moved) and stored.detail == Crop(**crop)
        render_settings = svc.player.render_settings(
            svc.library.get(item.id),
            svc.player.settings.model_copy(update={"orientation": Orientation.PORTRAIT}),
        )
        assert render_settings.layout.picture_crop == stored.picture

        # Passe-partout: one crop, with the window's shape.
        settings["art"]["fit"] = "fit"
        client.put("/api/settings", json=settings)
        view = client.get(url, params={"orientation": "portrait"}).json()
        assert view["fit"] == "fit" and not view["windows"][0]["custom"]
        square = {"x": 0.5, "y": 0.5, "zoom": 1.2, "aspect": 1.0}
        saved = client.put(url, json={"orientation": "portrait", "crops": [square]}).json()
        assert saved["windows"][0]["custom"] and saved["windows"][0]["aspect"] == 1.0
        # A square window centred in the area a window of any shape may take.
        _, ay, aw, ah = saved["windows"][0]["area"]
        x, y, w, h = saved["windows"][0]["rect"]
        assert w * 1440 == pytest.approx(h * 2560, abs=2) and w == pytest.approx(aw, abs=1e-3)
        assert y - ay == pytest.approx(ay + ah - y - h, abs=1e-3)
        # Another shape, tried on the preview before it is sent.
        preview = f"/api/library/items/{item.id}/preview"
        portrait = svc.player.settings.model_copy(update={"orientation": Orientation.PORTRAIT})
        tall = {"fit": {"x": 0.5, "y": 0.5, "zoom": 1, "aspect": 0.5}}
        query = {"settings": portrait.model_dump_json()}
        saved_png = client.get(preview, params=query).content
        tried_png = client.get(preview, params=query | {"framing": json.dumps(tall)}).content
        assert saved_png != tried_png
        assert svc.library.get(item.id).framing["portrait"].fit.aspect == 1.0
        bad = client.get(preview, params={"framing": '{"fit": {"zoom": 0}}'})
        assert bad.status_code == 422
        # Resetting it keeps the description's crops.
        client.delete(url, params={"orientation": "portrait"})
        stored = svc.library.get(item.id).framing["portrait"]
        assert stored.fit is None and stored.detail == Crop(**crop)
        assert stored.picture == Crop(**moved)


def test_upload_photo_with_place(service) -> None:
    from frame_server.web import create_app

    app = create_app(service.settings)
    with TestClient(app) as client:
        response = client.post(
            "/api/library/upload",
            files={"file": ("a.jpg", jpeg_bytes((90, 120, 200)), "image/jpeg")},
            data={
                "kind": "photo",
                "title": "Morze",
                "taken_at": "2026-07-01T10:00:00",
                "latitude": "54.5",
                "longitude": "18.6",
            },
        ).json()
    assert response["kind"] == "photo" and response["photo"]["latitude"] == 54.5
    assert response["date_text"] == "2026-07-01"


def test_crease_outlines_the_cut() -> None:
    settings = PRESETS["painting"].model_copy(deep=True)
    settings.layout.mat = "white"
    result = render(Image.new("RGB", (800, 1000), (200, 60, 40)), settings)
    plan = plan_layout((800, 1000), CANVAS, Fit.FIT, margin=0.05)
    (marks,) = crease_dots(plan, "k.").values()
    x, y, w, h = plan.windows[0].rect
    assert np.all(result.panel[marks] == SPECTRA6.device_u8()[SPECTRA6.black_index()])
    edges = (
        marks[y + h :, x : x + w],
        marks[:y, x : x + w],
        marks[y : y + h, :x],
        marks[y : y + h, x + w :],
    )
    assert all(edge.any() for edge in edges)
    assert not marks[y : y + h, x : x + w].any()  # never on the picture
    # On a dark board: white and blue dots, half as many of each.
    settings.layout.mat = "black"
    dark = render(Image.new("RGB", (800, 1000), (200, 60, 40)), settings)
    dots = crease_dots(plan, "w.b.")
    assert dots["white"].sum() + dots["blue"].sum() == marks.sum()
    for name, where in dots.items():
        assert np.all(dark.panel[where] == SPECTRA6.device_u8()[SPECTRA6.index(name)])
