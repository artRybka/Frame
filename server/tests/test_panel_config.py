"""Panel address, PIN and MAC set in the app win over frame.env and persist."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frame_server.config import Settings
from frame_server.panel_config import clean_host, clean_mac
from frame_server.service import FrameService
from frame_server.web import create_app


def _settings(tmp_path: Path, **kw: object) -> Settings:
    return Settings(
        data_dir=tmp_path,
        seed_library=False,
        scheduler=False,
        public_host="127.0.0.1",
        **kw,  # type: ignore[arg-type]
    )


def test_cleaning() -> None:
    assert clean_host(" http://192.168.1.152/ ") == "192.168.1.152"
    assert clean_host("frame.local") == "frame.local"
    assert clean_host("") is None
    with pytest.raises(ValueError):
        clean_host("192.168.1.152; rm")
    assert clean_mac("a4-30-7a-01-02-ff") == "A4:30:7A:01:02:FF"
    assert clean_mac("a430.7a01.02ff") == "A4:30:7A:01:02:FF"
    assert clean_mac(" ") is None
    with pytest.raises(ValueError):
        clean_mac("A4:30:7A:01:02")


def test_app_values_win_and_survive_restart(tmp_path: Path) -> None:
    env = {"device_host": "192.168.1.50", "device_pin": "000000"}
    app = create_app(_settings(tmp_path, **env))
    with TestClient(app) as client:
        view = client.get("/api/device/config").json()
        assert view == {
            "host": "192.168.1.50",
            "mac": None,
            "port": 1515,
            "pin_set": True,
            "from_app": False,
        }
        assert "pin" not in view

        saved = client.put(
            "/api/device/config",
            json={"host": "192.168.1.152", "pin": "123456", "mac": "a4307a0102ff"},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["mac"] == "A4:30:7A:01:02:FF"
        assert saved.json()["from_app"] is True
        svc: FrameService = app.state.service
        assert (svc.settings.device_host, svc.settings.device_pin) == ("192.168.1.152", "123456")
        assert svc.status.status.configured

        # No PIN in the request keeps the one saved.
        client.put("/api/device/config", json={"host": "192.168.1.152", "mac": None})
        assert svc.settings.device_pin == "123456"
        assert svc.settings.device_mac is None

        bad = client.put("/api/device/config", json={"host": "192.168.1.152", "mac": "nope"})
        assert bad.status_code == 400
        assert svc.settings.device_host == "192.168.1.152"

    # A restart with the same frame.env keeps what the app saved.
    restarted = FrameService(_settings(tmp_path, **env))
    assert restarted.settings.device_host == "192.168.1.152"
    assert restarted.settings.device_pin == "123456"
    assert restarted.panel_config.view().from_app


def test_reset_goes_back_to_frame_env(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, device_host="192.168.1.50", device_pin="000000"))
    with TestClient(app) as client:
        client.put("/api/device/config", json={"host": "192.168.1.152", "pin": "1234"})
        view = client.delete("/api/device/config").json()
        assert (view["host"], view["from_app"]) == ("192.168.1.50", False)
        assert app.state.service.settings.device_pin == "000000"


def test_configured_from_the_app_alone(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        assert not client.get("/api/status").json()["device"]["configured"]
        client.put("/api/device/config", json={"host": "192.168.1.152", "pin": "0000"})
        assert client.get("/api/status").json()["device"]["configured"]
        # Removing the PIN leaves the panel unconfigured again.
        client.put("/api/device/config", json={"host": "192.168.1.152", "pin": ""})
        assert not client.get("/api/status").json()["device"]["configured"]
