"""The Frame app on the panel (Samsung "Custom" source): it asks for its
pictures and sets its own alarm (docs/WAKE.md, E16)."""

from __future__ import annotations

import asyncio
import io
import ssl
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import trustme
from fake_panel import FakePanel
from fastapi.testclient import TestClient
from PIL import Image, JpegImagePlugin

from frame_server.config import Settings
from frame_server.device.mdc import CMD_CONTENT_DOWNLOAD
from frame_server.imaging.pipeline import encode_image
from frame_server.panel_app import AppHello
from frame_server.progress import Stage
from frame_server.schedule import FrameSettings
from frame_server.service import FrameService
from frame_server.store import PanelRequest
from frame_server.web.player_api import _player_view

WARSAW = ZoneInfo("Europe/Warsaw")


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=WARSAW)


def _service(tmp_path: Path, port: int = 1515) -> FrameService:
    settings = Settings(
        data_dir=tmp_path,
        seed_library=False,
        scheduler=False,
        public_host="127.0.0.1",
        device_host="127.0.0.1",
        device_pin="123456",
        device_port=port,
    )
    service = FrameService(settings)
    service.ensure_initial_content()
    return service


def _next_change(service: FrameService, at: datetime) -> None:
    state = service.player.state
    state.next_change_at = at.isoformat(timespec="seconds")
    service.player._save_state(state)


def _fetch(service: FrameService) -> None:
    """The app loads the picture it was told about."""
    content = service.store.current()
    assert content is not None
    service.store.log_request(
        PanelRequest(
            time=datetime.now(UTC).isoformat(),
            client="192.100.3.151",
            method="GET",
            path=f"/panel/images/{content.file_name}",
            status=200,
            user_agent="",
            headers={},
        )
    )


BATTERY = AppHello(reason="wake", build="1.0.0", battery=80, charging=False)


def test_online_sleeps_until_the_change_and_deeply_at_night(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.player.save_settings(
        FrameSettings(change_times=["07:00", "19:00"], quiet_start="22:00")
    )
    _next_change(service, _at("2026-10-28T19:00"))
    app = service.app

    answer = app.answer(BATTERY, now=_at("2026-10-28T12:00"))
    content = service.store.current()
    assert content is not None
    assert answer.action == "sleep"
    # The welcome card is black on white, a dithered picture: the PNG.
    assert answer.image == f"http://127.0.0.1:8099/panel/images/{content.file_name}"
    assert answer.wake_at == _at("2026-10-28T19:00").isoformat()
    assert answer.wake_ms == int(_at("2026-10-28T19:00").timestamp() * 1000)
    assert answer.standby == "ON"  # Wake-on-LAN still reaches it by day
    status = service.status.status
    assert status.panel_app and status.battery_level == 80 and status.power_source == "battery"
    assert status.wakes_at == "19:00"
    assert status.wake_at == _at("2026-10-28T19:00").isoformat()
    assert app.asleep() and not app.deep_asleep()

    # After the evening change: up again when quiet hours start, to turn the
    # Wi-Fi off for the night.
    _next_change(service, _at("2026-10-29T07:00"))
    answer = app.answer(BATTERY, now=_at("2026-10-28T19:01"))
    assert answer.wake_at == _at("2026-10-28T22:00").isoformat()
    answer = app.answer(BATTERY, now=_at("2026-10-28T22:00:05"))
    assert answer.standby == "OFF"
    assert answer.wake_at == _at("2026-10-29T07:00").isoformat()
    assert app.deep_asleep()
    assert service.power.deep_asleep(_at("2026-10-28T23:00"))


def test_economy_wakes_for_checks_with_the_wifi_off(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.player.save_settings(
        FrameSettings(
            change_times=["07:00", "19:00"],
            power_mode="economy",
            check_every_hours=4,
            quiet_start=None,
        )
    )
    _next_change(service, _at("2026-10-28T19:00"))
    answer = service.app.answer(BATTERY, now=_at("2026-10-28T12:00"))
    assert answer.action == "sleep"
    assert answer.standby == "OFF"
    assert answer.wake_at == _at("2026-10-28T15:00").isoformat()
    assert service.power.economy  # the app's alarm works, unlike MDC's
    assert not service.status.status.alarm_refused


def test_charger_stays_awake_and_a_change_is_waited_for(tmp_path: Path) -> None:
    service = _service(tmp_path)
    now = _at("2026-10-28T12:00")
    _next_change(service, _at("2026-10-28T19:00"))
    answer = service.app.answer(AppHello(charging=True), now=now)
    assert answer.action == "stay" and answer.wait_s == 20
    assert not service.app.asleep()

    # "Uśpij ramkę": it sleeps at its next question, even on the charger.
    service.power.cancel_light_sleep()
    service.app.request_sleep()
    assert service.app.answer(AppHello(charging=True), now=now).action == "sleep"

    # Woken a few seconds early for a change: ask again shortly.
    _next_change(service, now + timedelta(seconds=5))
    answer = service.app.answer(BATTERY, now=now)
    assert answer.action == "wait" and answer.wait_s == 15


def test_a_waiting_picture_goes_out_at_the_wake(tmp_path: Path) -> None:
    service = _service(tmp_path)
    now = datetime.now(UTC)
    _next_change(service, now + timedelta(hours=5))
    service.app.answer(BATTERY, now=now)  # asleep, Wi-Fi on, no MAC: no Wake-on-LAN
    _fetch(service)  # the welcome card is on the frame
    service.store.publish(b"png", "png", title="Słoneczniki")

    async def push() -> None:
        outcome = await service.push_current(wait=0)
        assert not outcome.pushed
        assert "asks for it at" in outcome.message

    asyncio.run(push())
    assert service.power.state.pending_push
    delivery = _player_view(service).delivery
    assert delivery.state == "waiting"
    wake = service.app.wakes_at()
    assert wake is not None and delivery.asleep_until_at == wake.isoformat(timespec="seconds")

    # The alarm rings: the app gets it, and it stays until the next change.
    answer = service.app.answer(BATTERY)
    assert not service.power.state.pending_push
    assert answer.file_id == service.store.current().file_id  # type: ignore[union-attr]


async def test_push_to_an_awake_app(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _next_change(service, datetime.now(UTC) + timedelta(hours=5))
    service.app.answer(AppHello(charging=True))  # on the charger, asking every 20 s

    task = asyncio.create_task(service.push_current(wait=5))
    await asyncio.sleep(0.2)
    _fetch(service)
    outcome = await task
    assert outcome.fetched
    assert not service.power.state.pending_push
    assert _player_view(service).delivery.state == "shown"

    # The bar shows the download until the app has the picture on its page.
    file_id = outcome.content.file_id
    service.app.report("progress", {"file_id": file_id, "loaded": 300_000, "total": 1_000_000})
    assert service.progress.view().stage == Stage.DOWNLOADING
    service.app.report("shown", {"file_id": file_id})
    await asyncio.sleep(0.05)
    assert service.progress.view().stage == Stage.REFRESHING


def test_full_colour_pictures_go_as_jpeg_dithered_ones_as_png(tmp_path: Path) -> None:
    service = _service(tmp_path)
    store, app = service.store, service.app
    gradient = Image.linear_gradient("L").resize((2560, 1440)).convert("RGB")
    store.publish(encode_image(gradient, "png"), "png", title="Passthrough")
    content = store.current()
    assert content is not None
    assert app.image_path(content) == f"/panel/app-images/{content.file_id}.jpg"
    with Image.open(store.app_image_path(content.file_id)) as img:
        assert img.size == (2560, 1440) and img.format == "JPEG"
        assert JpegImagePlugin.get_sampling(img) == 0  # 4:4:4

    inks = gradient.quantize(6)
    store.publish(encode_image(inks.convert("RGB"), "png"), "png", title="Dithered")
    content = store.current()
    assert content is not None
    assert app.image_path(content) == f"/panel/images/{content.file_name}"


@pytest.fixture(scope="module")
def server_ssl() -> ssl.SSLContext:
    ca = trustme.CA()
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ca.issue_cert("panel.local").configure_cert(ctx)
    return ctx


async def test_switch_the_panel_to_the_app_and_back(
    tmp_path: Path, server_ssl: ssl.SSLContext
) -> None:
    def handler(command: int, data: bytes) -> tuple[bool, bytes]:
        if command == CMD_CONTENT_DOWNLOAD and data == b"\x81":
            return True, b"\x81\x00"  # Mobile
        return True, data

    panel = FakePanel(server_ssl, handler=handler)
    await panel.start()
    try:
        service = _service(tmp_path, panel.port)
        with pytest.raises(Exception, match="no app package"):
            await service.app.switch(True)
        service.app.store_package(b"PK\x03\x04signed", "1.0.0")
        await service.app.switch(True)
        assert (CMD_CONTENT_DOWNLOAD, b"\x82http://127.0.0.1:8099/panel/app") in panel.received
        assert panel.received[-1] == (CMD_CONTENT_DOWNLOAD, b"\x81\x01")
        assert service.app.active and service.app.state.previous_source == 0
        assert service.status.status.panel_app

        # A new package for an awake app: restarted so the launcher installs it.
        panel.received.clear()
        assert await service.app.install()
        assert panel.received == [(CMD_CONTENT_DOWNLOAD, b"\x81\x01")]

        await service.app.switch(False)
        assert panel.received[-1] == (CMD_CONTENT_DOWNLOAD, b"\x81\x00")
        assert not service.app.active
    finally:
        await panel.stop()


def test_panel_routes(tmp_path: Path) -> None:
    from frame_server.web import create_app

    service = _service(tmp_path)
    app = create_app(service.settings)
    svc = app.state.service
    with TestClient(app) as client:
        assert client.get("/panel/app/sssp_config.xml").status_code == 404
        put = client.put(
            "/api/device/app/package",
            params={"version": "1.0.0"},
            content=b"PK\x03\x04signed",
        )
        assert put.status_code == 200, put.text
        config = client.get("/panel/app/sssp_config.xml").text
        assert "<ver>1.0.0</ver>" in config and "<size>10</size>" in config
        assert "<widgetname>Frame</widgetname>" in config
        assert "<webtype>tizen</webtype>" in config
        assert client.get("/panel/app/Frame.wgt").content == b"PK\x03\x04signed"
        code = client.get("/panel/app/app.js")
        assert code.text.startswith("window.FRAME_CODE = ")

        answer = client.get("/panel/next", params={"reason": "start", "charging": "true"})
        assert answer.headers["access-control-allow-origin"] == "*"
        assert answer.json()["action"] == "stay"
        # The picture of the Mobile source at the panel's size; full colour as JPEG.
        gradient = Image.linear_gradient("L").resize((2560, 1440)).convert("RGB")
        svc.store.publish(encode_image(gradient, "png"), "png", title="Passthrough")
        answer = client.get("/panel/next", params={"reason": "poll", "charging": "true"})
        image = client.get(answer.json()["image"].removeprefix("http://127.0.0.1:8099"))
        assert image.status_code == 200
        with Image.open(io.BytesIO(image.content)) as img:
            assert img.size == (2560, 1440) and img.format == "JPEG"
        assert client.get("/panel/app-images/nothing.jpg").status_code == 404
        assert svc.app.active
        assert client.post("/panel/report", content='{"event": "shown"}').status_code == 200
        assert client.get("/api/device/app").json()["active"]

        # Back in the Mobile source the panel fetches content.json again.
        assert client.get("/panel/content.json").status_code == 200
        assert not svc.app.active


def test_never_sleeps_for_less_than_five_minutes(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.player.save_settings(
        FrameSettings(change_times=["07:00", "19:00"], quiet_start="22:00")
    )
    _next_change(service, _at("2026-10-29T07:00"))
    # Quiet hours start in 4 minutes: an alarm that close could be lost.
    answer = service.app.answer(BATTERY, now=_at("2026-10-28T21:56"))
    assert answer.action == "wait" and answer.wait_s == 60
    assert not service.app.asleep()


async def test_a_silent_app_is_started_after_its_alarm(
    tmp_path: Path, server_ssl: ssl.SSLContext
) -> None:
    panel = FakePanel(server_ssl)
    await panel.start()
    try:
        service = _service(tmp_path, panel.port)
        service.player.save_settings(
            FrameSettings(change_times=["07:00", "19:00"], power_mode="economy", quiet_start=None)
        )
        _next_change(service, _at("2026-10-28T19:00"))
        service.app.answer(BATTERY, now=_at("2026-10-28T12:00"))  # Wi-Fi off until 19:00
        await service.power.tick(_at("2026-10-28T19:00:30"))
        assert panel.received == []  # still booting
        await service.power.tick(_at("2026-10-28T19:01:40"))
        assert panel.received == [(CMD_CONTENT_DOWNLOAD, b"\x81\x01")]
        await service.power.tick(_at("2026-10-28T19:16"))
        assert service.app.state.missed_wake == _at("2026-10-28T19:00").isoformat()
    finally:
        await panel.stop()
