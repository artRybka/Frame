from __future__ import annotations

import numpy as np
import pytest
from conftest import jpeg_bytes
from fastapi.testclient import TestClient
from PIL import Image

from frame_server.imaging import PRESETS
from frame_server.imaging.interest import InterestMap, detect_faces
from frame_server.imaging.layout import (
    Crop,
    Fit,
    caption_band,
    crop_box,
    plan_layout,
    resolve_fit,
)
from frame_server.imaging.palette import SPECTRA6
from frame_server.imaging.pipeline import render
from frame_server.library import ItemKind

CANVAS = (2560, 1440)


@pytest.mark.parametrize(
    ("size", "fit", "expected"),
    [
        ((1600, 900), Fit.AUTO, Fit.FILL),  # 16:9 on 16:9
        ((1200, 900), Fit.AUTO, Fit.FIT),  # 4:3: little room beside it
        ((800, 1200), Fit.AUTO, Fit.DETAILS),  # portrait on a landscape frame
        ((1600, 900), Fit.DETAILS, Fit.FIT),  # no room for close-ups
    ],
)
def test_auto_picks_fill_fit_or_details(size, fit, expected) -> None:
    assert resolve_fit(size, CANVAS, fit) == expected


def test_crop_box_zoom_and_clamping() -> None:
    # Cover crop of a 16:9 window on a 1000×1000 picture, then 2× closer.
    assert crop_box((1000, 1000), 16 / 9, Crop()) == pytest.approx((0, 218.75, 1000, 781.25))
    x0, _, x1, y1 = crop_box((1000, 1000), 16 / 9, Crop(x=0.0, y=1.0, zoom=2))
    assert (x0, y1) == (0, 1000) and x1 == pytest.approx(500)


def test_details_layout() -> None:
    plan = plan_layout((800, 1200), CANVAS, Fit.DETAILS, margin=0.05, caption=True)
    main, first, second = plan.windows
    assert main.role == "picture" and main.rect == (0, 0, 960, 1440)
    assert first.role == second.role == "detail"
    assert first.rect[0] == second.rect[0] > 960  # stacked beside the picture
    assert first.rect[1] + first.rect[3] < second.rect[1]  # mat between them
    assert plan.caption_at is not None and plan.caption_at[1] > second.rect[1] + second.rect[3]
    # The portrait frame and a landscape picture: picture on top, close-ups side by side.
    plan = plan_layout((1500, 600), (1440, 2560), Fit.DETAILS)
    main, first, second = plan.windows
    assert main.rect == (0, 0, 1440, 576) and first.rect[1] == second.rect[1] > 576


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
    # The lit bevel below the window shows the mat's white core.
    bevel = panel[y + h + 3, x + 20 : x + w - 20]
    assert np.all(bevel == white, axis=-1).mean() > 0.9
    right, top, _ = plan.caption_at
    text = panel[top : top + 40, right - 400 : right]
    assert np.any(np.all(text == white, axis=-1))  # white letters on black


def test_interest_finds_the_busy_part() -> None:
    rng = np.random.default_rng(1)
    pixels = np.full((1200, 800, 3), 128, dtype=np.uint8)
    pixels[850:1150, 100:700] = rng.integers(0, 255, (300, 600, 3), dtype=np.uint8)
    img = Image.fromarray(pixels)
    (crop,) = InterestMap(img).best(16 / 9, 1.0, 1)
    assert crop.y > 0.65  # the noisy bottom, not the middle
    first, second = InterestMap(img).best(2.3, 2.0, 2)
    b1 = crop_box(img.size, 2.3, first)
    b2 = crop_box(img.size, 2.3, second)
    overlap = max(0, min(b1[2], b2[2]) - max(b1[0], b2[0])) * max(
        0, min(b1[3], b2[3]) - max(b1[1], b2[1])
    )
    assert overlap <= 0.1 * (b1[2] - b1[0]) * (b1[3] - b1[1])


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

        crop = {"x": 0.3, "y": 0.5, "zoom": 1.5}
        saved = client.put(url, json={"orientation": "landscape", "crops": [crop]}).json()
        assert saved["windows"][0]["custom"] and saved["windows"][0]["crop"]["zoom"] == 1.5
        stored = svc.library.get(item.id).framing["landscape"].fill
        assert stored.zoom == 1.5
        render_settings = svc.player.render_settings(svc.library.get(item.id), svc.player.settings)
        assert render_settings.layout.crop == stored

        two = {"orientation": "landscape", "crops": [crop, crop]}
        assert client.put(url, json=two).status_code == 422  # FILL takes one

        reset = client.delete(url, params={"orientation": "landscape"}).json()
        assert not reset["windows"][0]["custom"]
