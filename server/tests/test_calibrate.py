from __future__ import annotations

import io
import json
import time

import numpy as np
import pytest
from conftest import jpeg_bytes
from fastapi.testclient import TestClient
from PIL import Image

from frame_server.imaging.calibrate import (
    CalibrationError,
    measure,
    perspective_coefficients,
)
from frame_server.imaging.color import linear_to_u8, u8_to_linear
from frame_server.imaging.layout import PANEL_HEIGHT, PANEL_WIDTH
from frame_server.imaging.palette import EM32DX, SPECTRA6
from frame_server.imaging.testchart import palette_chart
from frame_server.library import ItemKind

PHOTO = (1600, 1200)
# Where the panel's corners land in the photo: TL, TR, BR, BL (a bit of perspective).
CORNERS = [(210.0, 160.0), (1440.0, 230.0), (1390.0, 990.0), (180.0, 1040.0)]
_N = [(x / PHOTO[0], y / PHOTO[1]) for x, y in CORNERS]  # as the app sends them


def _photo(gain: tuple[float, float, float] = (1.3, 1.1, 0.8)) -> bytes:
    """The chart as the inks really look, under a colour cast, photographed at an angle."""
    chart = np.asarray(palette_chart(SPECTRA6)).copy()
    looks = chart.copy()
    for color in SPECTRA6.colors:
        looks[np.all(chart == color.device, axis=-1)] = color.perceived
    lit = linear_to_u8(np.clip(u8_to_linear(looks) * np.array(gain, dtype=np.float32), 0, 1))
    panel = [(0.0, 0.0), (PANEL_WIDTH, 0.0), (PANEL_WIDTH, PANEL_HEIGHT), (0.0, PANEL_HEIGHT)]
    coeffs = perspective_coefficients(panel, CORNERS)
    photo = Image.fromarray(lit).transform(
        PHOTO,
        Image.Transform.PERSPECTIVE,
        coeffs,
        Image.Resampling.BILINEAR,
        fillcolor=(60, 55, 50),
    )
    buf = io.BytesIO()
    photo.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def test_measurement_recovers_the_inks_whatever_the_light() -> None:
    result = measure(_photo(), _N)
    assert result.warnings == []
    for ink in result.inks:
        expected = SPECTRA6.colors[SPECTRA6.index(ink.name)].perceived
        assert np.abs(np.array(ink.perceived) - np.array(expected)).max() <= 6, ink
        assert ink.spread < 0.05
    # The cast is in the raw measurement, not in the result.
    white = next(i for i in result.inks if i.name == "white")
    assert white.measured[0] > white.measured[2] + 20
    assert white.perceived == (190, 190, 190)
    palette = result.palette(SPECTRA6, name="em32dx-test", source="test")
    assert palette.white_index() == SPECTRA6.white_index()


@pytest.mark.parametrize(
    "corners",
    [
        [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)],  # the whole photo
        [_N[2], _N[3], _N[0], _N[1]],  # upside down
        [_N[1], _N[0], _N[3], _N[2]],  # mirrored
        [(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)],  # inside the chart
    ],
)
def test_corners_off_the_chart_are_rejected(corners) -> None:
    with pytest.raises(CalibrationError):
        measure(_photo(), corners)


def test_degenerate_corners_are_rejected() -> None:
    with pytest.raises(CalibrationError):
        measure(_photo(), [(0.1, 0.1), (0.1, 0.1), (0.1, 0.1), (0.1, 0.1)])


def _wait(condition, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.05)


def test_calibration_from_the_app(service) -> None:
    from frame_server.service import FrameService
    from frame_server.web import create_app

    app = create_app(service.settings)
    svc = app.state.service
    item = svc.importer.add_upload(jpeg_bytes((200, 40, 40)), kind=ItemKind.OWN, title="Work")
    with TestClient(app) as client:
        info = client.get("/api/calibration").json()
        assert not info["calibrated"] and info["palette"]["name"] == EM32DX.name

        assert client.post("/api/calibration/chart").status_code == 202
        # The hold is set just after the chart is published: wait for both.
        _wait(
            lambda: (
                svc.store.current().title == "Plansza kalibracji"
                and svc.player.state.hold is not None
            )
        )

        bad = client.post(
            "/api/calibration/measure",
            files={"file": ("photo.jpg", _photo(), "image/jpeg")},
            data={"corners": json.dumps([[0.4, 0.4], [0.6, 0.4], [0.6, 0.6], [0.4, 0.6]])},
        )
        assert bad.status_code == 422 and "narożniki" in bad.json()["detail"]

        measured = client.post(
            "/api/calibration/measure",
            files={"file": ("photo.jpg", _photo(), "image/jpeg")},
            data={"corners": json.dumps(_N)},
        ).json()
        candidate = measured["candidate_id"]
        assert [i["name"] for i in measured["inks"]] == SPECTRA6.names
        assert client.get(measured["chart_url"]).headers["content-type"] == "image/jpeg"
        preview = client.get(f"/api/calibration/candidates/{candidate}/preview/{item.id}")
        assert preview.headers["content-type"] == "image/png"
        assert client.get("/api/calibration/candidates/../preview/x").status_code == 404

        applied = client.post("/api/calibration/apply", json={"candidate_id": candidate}).json()
        assert applied["calibrated"] and applied["palette"]["name"].startswith("em32dx-")
        assert svc.palette.name == applied["palette"]["name"]
        _wait(lambda: svc.player.state.hold is None and not svc.player.busy)
        # Kept across restarts.
        assert FrameService(svc.settings).palette.name == svc.palette.name

        reset = client.delete("/api/calibration").json()
        assert not reset["calibrated"] and reset["palette"]["name"] == EM32DX.name
