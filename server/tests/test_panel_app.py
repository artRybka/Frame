"""The Frame app on the panel (Samsung "Custom" source): it asks for its
pictures and sets its own alarm (docs/WAKE.md, E16)."""

from __future__ import annotations

import asyncio
import io
import json
import ssl
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import trustme
from fake_panel import FakePanel
from fastapi.testclient import TestClient
from PIL import Image, JpegImagePlugin

from frame_server import status as status_module
from frame_server.config import Settings
from frame_server.device.mdc import CMD_CONTENT_DOWNLOAD
from frame_server.imaging.pipeline import encode_image
from frame_server.panel_app import AppHello
from frame_server.progress import Stage
from frame_server.schedule import FrameSettings
from frame_server.service import FrameService
from frame_server.status import wifi_reading
from frame_server.store import PanelRequest
from frame_server.web.player_api import _player_view

WARSAW = ZoneInfo("Europe/Warsaw")
PASSWORD = "secret"


def _p12(name: str, days: int = 365) -> bytes:
    """A self-signed RSA key and certificate as a .p12, like the Samsung ones."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=days))
        .sign(key, hashes.SHA256())
    )
    encryption = serialization.BestAvailableEncryption(PASSWORD.encode())
    return pkcs12.serialize_key_and_certificates(name.encode(), key, cert, None, encryption)


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
            client="192.0.2.20",
            method="GET",
            path=f"/panel/images/{content.file_name}",
            status=200,
            user_agent="",
            headers={},
        )
    )


# The server points the launcher at the app and starts it ...
INSTALL = [
    (CMD_CONTENT_DOWNLOAD, b"\x82http://127.0.0.1:8099/panel/app"),
    (CMD_CONTENT_DOWNLOAD, b"\x81\x01"),
]
# ... and reads the source first when it starts an app that should run.
START = [(CMD_CONTENT_DOWNLOAD, b"\x81"), *INSTALL]
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
    assert answer.wake_at == _at("2026-10-28T16:00").isoformat()


def test_charger_stays_awake_and_a_change_is_waited_for(tmp_path: Path) -> None:
    service = _service(tmp_path)
    now = _at("2026-10-28T12:00")
    _next_change(service, _at("2026-10-28T19:00"))
    answer = service.app.answer(AppHello(charging=True), now=now)
    assert answer.action == "stay" and answer.wait_s == 20
    assert not service.app.asleep()

    # "Uśpij ramkę": it sleeps at its next question, even on the charger.
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


async def test_the_server_installs_and_starts_the_app(
    tmp_path: Path, server_ssl: ssl.SSLContext
) -> None:
    panel = FakePanel(server_ssl)
    await panel.start()
    try:
        service = _service(tmp_path, panel.port)
        with pytest.raises(Exception, match="certificates"):
            await service.app.install()
        service.app.store_package(b"PK\x03\x04signed", "2.0.0")
        await service.app.install()
        assert panel.received == [
            (CMD_CONTENT_DOWNLOAD, b"\x82http://127.0.0.1:8099/panel/app"),
            (CMD_CONTENT_DOWNLOAD, b"\x81\x01"),
        ]
        assert not service.app.active  # until it asks
        service.app.answer(AppHello(reason="start", build="2.0.0", charging=True))
        assert service.app.active and service.status.status.panel_app
    finally:
        await panel.stop()


async def test_the_server_starts_the_app_when_the_panel_does_not_run_it(
    tmp_path: Path, server_ssl: ssl.SSLContext
) -> None:
    panel = FakePanel(server_ssl)
    await panel.start()
    try:
        service = _service(tmp_path, panel.port)
        app = service.app
        now = _at("2026-10-28T21:00")
        await service.power.tick(now)
        assert panel.received == []  # no package to install
        app.store_package(b"PK\x03\x04signed", "2.0.0")
        await service.power.tick(now + timedelta(seconds=5))
        assert panel.received == []  # not again so soon
        await service.power.tick(now + timedelta(minutes=5))
        assert panel.received[-1] == (CMD_CONTENT_DOWNLOAD, b"\x81\x01")

        # It runs, on the charger, asking every 20 s ... then falls silent:
        # restarted a few times, then only now and then (most likely unplugged).
        panel.received.clear()
        app.answer(AppHello(reason="start", build="2.0.0", charging=True), now=now)
        await service.power.tick(now + timedelta(minutes=2))
        assert panel.received == []
        for minutes in (4, 5, 7, 9):
            await service.power.tick(now + timedelta(minutes=minutes))
        assert panel.received == START * 3
        for minutes in (10, 11, 13):
            await service.power.tick(now + timedelta(minutes=minutes))
        assert panel.received == START * 3 + INSTALL

        # The panel fell back to Mobile and fetched content.json: started again.
        panel.received.clear()
        app.left()
        assert not app.active
        await service.power.tick(now + timedelta(minutes=14))
        assert panel.received[-1] == (CMD_CONTENT_DOWNLOAD, b"\x81\x01")
    finally:
        await panel.stop()


def test_panel_routes(tmp_path: Path) -> None:
    from frame_server.web import create_app

    service = _service(tmp_path)
    app = create_app(service.settings)
    svc = app.state.service
    with TestClient(app) as client:
        assert client.get("/panel/app/sssp_config.xml").status_code == 404
        author, distributor = _p12("Author"), _p12("Distributor")
        files = {"author": ("author.p12", author), "distributor": ("distributor.p12", distributor)}
        wrong = client.put("/api/device/app/certificates", files=files, data={"password": "no"})
        assert wrong.status_code == 400
        put = client.put(
            "/api/device/app/certificates", files=files, data={"password": PASSWORD + "\n"}
        )
        assert put.status_code == 200, put.text
        assert [c["role"] for c in put.json()["certificates"]] == ["author", "distributor"]
        assert put.json()["package"]["version"] == "2.0.0"
        config = client.get("/panel/app/sssp_config.xml").text
        assert "<ver>2.0.0</ver>" in config and "<widgetname>Frame</widgetname>" in config
        assert "<webtype>tizen</webtype>" in config
        wgt = client.get("/panel/app/Frame.wgt").content
        assert f"<size>{len(wgt)}</size>" in config
        with zipfile.ZipFile(io.BytesIO(wgt)) as z:
            assert 'version="2.0.0"' in z.read("config.xml").decode()
            assert b"http://127.0.0.1:8099" in z.read("config.js")
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

        # Fallen back to the Mobile source the panel fetches content.json:
        # it still gets the picture, and the server starts the app again.
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
        assert panel.received == START
        await service.power.tick(_at("2026-10-28T19:16"))
        assert service.app.state.missed_wake == _at("2026-10-28T19:00").isoformat()
        # Not heard of since: pointed at the app and started every 5 minutes.
        service.app.store_package(b"PK\x03\x04signed", "2.0.0")
        await service.power.tick(_at("2026-10-28T19:21"))
        assert panel.received == START + INSTALL
        assert service.app.state.missed_wake == _at("2026-10-28T19:00").isoformat()
    finally:
        await panel.stop()


def _ms(text: str) -> int:
    return int(_at(text).timestamp() * 1000)


async def test_a_check_with_nothing_new_leaves_the_panel_asleep(
    tmp_path: Path, server_ssl: ssl.SSLContext
) -> None:
    panel = FakePanel(server_ssl)
    await panel.start()
    try:
        service = _service(tmp_path, panel.port)
        service.player.save_settings(
            FrameSettings(
                change_times=["07:00", "19:00"],
                power_mode="economy",
                check_every_hours=2,
                quiet_start=None,
            )
        )
        _next_change(service, _at("2026-10-28T19:00"))
        app = service.app
        content = service.store.current()
        assert content is not None
        hello = BATTERY.model_copy(update={"shown": content.file_id})
        answer = app.answer(hello, now=_at("2026-10-28T12:00"))
        # The Wi-Fi off: every check up to the change, set at once.
        assert answer.standby == "OFF"
        assert answer.wake_at == _at("2026-10-28T14:00").isoformat()
        assert answer.wakes_ms == [
            _ms("2026-10-28T16:00"),
            _ms("2026-10-28T18:00"),
            _ms("2026-10-28T19:00"),
        ]

        # Nothing new at 14:00: the app is not started, the cold-booted panel
        # goes back to sleep by itself and no wake is missed.
        await service.power.tick(_at("2026-10-28T14:01:10"))
        await service.power.tick(_at("2026-10-28T14:10"))
        assert panel.received == []
        assert app.state.missed_wake is None
        assert app.wakes_at(_at("2026-10-28T14:10")) == _at("2026-10-28T16:00")

        # A new picture while it sleeps: started at the next check.
        service.store.publish(b"png", "png", title="Słoneczniki")
        await service.power.tick(_at("2026-10-28T16:01:10"))
        assert panel.received == START
        new = service.store.current()
        assert new is not None
        app.report("shown", {"file_id": new.file_id})
        assert app.state.shown == new.file_id

        # Shown: 18:00 is left alone, the last alarm (19:00) never is.
        await service.power.tick(_at("2026-10-28T18:01:10"))
        assert panel.received == START
        await service.power.tick(_at("2026-10-28T19:01:10"))
        assert panel.received == START * 2
    finally:
        await panel.stop()


def test_the_app_says_what_it_shows(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app = service.app
    app.answer(AppHello(shown="abc", charging=True))
    assert app.state.shown == "abc"
    app.answer(AppHello(charging=True))  # an older app.js says nothing
    assert app.state.shown == "abc"
    app.answer(AppHello(shown="", charging=True))  # nothing on the screen
    assert app.state.shown is None


def test_hourly_checks_are_set_up_to_the_next_change_outside_quiet_hours(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    service.player.save_settings(
        FrameSettings(change_times=["07:00", "19:00"], power_mode="economy", check_every_hours=1)
    )
    app = service.app
    # By day: every full hour up to the 19:00 change.
    _next_change(service, _at("2026-10-28T19:00"))
    alarms = app.alarms(_at("2026-10-28T08:30"), _at("2026-10-28T09:00"))
    assert alarms == [_at(f"2026-10-28T{h:02d}:00") for h in range(9, 20)]
    # In the evening: 20:00 and 21:00, then quiet hours until the 07:00 change.
    _next_change(service, _at("2026-10-29T07:00"))
    alarms = app.alarms(_at("2026-10-28T19:30"), _at("2026-10-28T20:00"))
    assert alarms == [_at("2026-10-28T20:00"), _at("2026-10-28T21:00"), _at("2026-10-29T07:00")]


async def test_a_new_package_is_installed_by_a_reboot(
    tmp_path: Path, server_ssl: ssl.SSLContext
) -> None:
    panel = FakePanel(server_ssl)
    await panel.start()
    try:
        service = _service(tmp_path, panel.port)
        app = service.app
        app.store_package(b"PK\x03\x04signed", "2.0.1")
        now = _at("2026-10-28T21:00")
        hello = AppHello(reason="poll", build="2.0.0", charging=True)
        assert app.answer(hello, now=now).action == "reboot"
        # Installed, not started: the server starts it a minute later.
        await service.power.tick(now + timedelta(seconds=70))
        assert panel.received == START
        # Once per version: a package that does not install reboots no more.
        assert app.answer(hello, now=now + timedelta(minutes=2)).action == "stay"
        new = AppHello(reason="start", build="2.0.1", charging=True)
        assert app.answer(new, now=now + timedelta(minutes=3)).action == "stay"
    finally:
        await panel.stop()


def test_wifi_reading_learns_the_home_network_and_warns_off_it() -> None:
    now = datetime(2026, 10, 28, 20, 0, tzinfo=UTC)
    host = "192.0.2.20"
    home = wifi_reading(
        {"level": 3, "ssid": "Frame_IoT", "ip": host, "frequency": 2437}, host, None, now
    )
    assert home is not None
    assert home.signal == pytest.approx(0.6) and home.level == 3 and home.frequency == 2437
    assert home.home_ssid == "Frame_IoT" and not home.wrong_network
    # After a power cut it joined the neighbour's SSID (E16).
    away = wifi_reading(
        {"signal": 0.8, "ssid": "Sasiad IoT", "ip": "198.51.100.20"}, host, home, now
    )
    assert away is not None and away.wrong_network
    assert away.home_ssid == "Frame_IoT" and away.expected_ip == host
    # Another SSID at the right address: reachable, so that is home now.
    other = wifi_reading({"signal": 0.5, "ssid": "Guest", "ip": host}, host, home, now)
    assert other is not None and other.wrong_network is False and other.home_ssid == "Guest"
    # Nothing read (no API, systeminfo silent): the last reading stays.
    assert wifi_reading({"error": "no answer"}, host, home, now) is None
    # A host name cannot be compared with the address.
    named = wifi_reading({"level": 9, "ssid": "X", "ip": "10.0.0.2"}, "frame.local", None, now)
    assert named is not None and named.signal == 1.0 and not named.wrong_network


def test_wifi_report_shows_in_the_status_until_the_panel_leaves_the_app(tmp_path: Path) -> None:
    from frame_server.web import create_app

    service = _service(tmp_path)
    app = create_app(service.settings)
    with TestClient(app) as client:
        client.get("/panel/next", params={"reason": "start", "charging": "true"})
        report = {"event": "wifi", "via": "webapis", "level": 2, "ssid": "IoT", "ip": "127.0.0.1"}
        client.post("/panel/report", content=json.dumps(report))
        wifi = client.get("/api/device/status").json()["wifi"]
        assert wifi["ssid"] == "IoT" and wifi["level"] == 2 and not wifi["wrong_network"]
        client.post("/panel/report", content='{"event": "wifi", "ip": "10.1.1.1", "signal": 0.4}')
        assert client.get("/api/device/status").json()["wifi"]["wrong_network"]
        assert client.get("/panel/content.json").status_code == 200
        assert client.get("/api/device/status").json()["wifi"] is None


def test_the_package_is_built_here_and_the_certificates_watched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from frame_server import panel_app
    from frame_server.panel_app import _next_version

    assert _next_version(None) == "2.0.0"
    assert _next_version("1.2.0") == "2.0.0"  # signed by hand on the Mac
    assert _next_version("2.0.7") == "2.0.8"
    assert _next_version("odd") == "2.0.0"

    service = _service(tmp_path)
    app = service.app
    assert app.ensure_package() is None  # no certificates yet
    view = app.store_certificates(_p12("Author", days=400), _p12("Distributor", days=30), b"secret")
    assert view.package is not None and view.package.version == "2.0.0"
    stored = tmp_path / "panel-app" / "certs"
    names = sorted(p.name for p in stored.iterdir())
    assert names == [".password", "author.p12", "distributor.p12"]
    assert all(p.stat().st_mode & 0o077 == 0 for p in stored.iterdir())
    # The distributor certificate expires within 60 days: the app warns.
    assert view.certificates_expire_at is not None
    assert service.status.status.certificates_expire_at == view.certificates_expire_at

    with zipfile.ZipFile(app.package_path()) as z:
        names = z.namelist()
        assert names[-2:] == ["author-signature.xml", "signature1.xml"]
        author = z.read("author-signature.xml").decode()
        assert "#role-author" in author and 'URI="config.xml"' in author
        assert 'URI="author-signature.xml"' in z.read("signature1.xml").decode()

    # Nothing changed: the same package. A new page: a new version.
    assert app.ensure_package() == app.package()
    index = tmp_path / "index.html"
    index.write_text("<html>new</html>")
    original = panel_app.APP_DIR
    monkeypatch.setattr(panel_app, "APP_DIR", tmp_path)
    for name in ("config.xml", "app.js"):
        (tmp_path / name).write_bytes((original / name).read_bytes())
    rebuilt = app.ensure_package()
    assert rebuilt is not None and rebuilt.version == "2.0.1"


def test_certificates_copied_in_by_hand_are_picked_up(tmp_path: Path) -> None:
    """Dropped into data/panel-app/certs (File Station), the password in a
    file with a name that does not hide: the next question builds the app."""
    service = _service(tmp_path)
    certs = tmp_path / "panel-app" / "certs"
    certs.mkdir(parents=True)
    (certs / "author.p12").write_bytes(_p12("Author"))
    (certs / "distributor.p12").write_bytes(_p12("Distributor"))
    (certs / "password.txt").write_text(PASSWORD + "\n")
    asyncio.run(service.app.ask(AppHello(reason="start", build="1.2.0", charging=True)))
    package = service.app.package()
    assert package is not None and package.version == "2.0.0"
    assert [c.role for c in service.app.view().certificates] == ["author", "distributor"]


def test_deep_sleep_for_hours_ends_at_its_time_or_with_the_button(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.player.save_settings(
        FrameSettings(
            change_times=["07:00", "19:00"],
            power_mode="economy",
            check_every_hours=4,
            quiet_start=None,
        )
    )
    app = service.app
    _next_change(service, _at("2026-10-28T19:00"))
    # Economy: alarms at 16:00 and 19:00 set; woken at 16:00, the 19:00 one
    # stays set on the panel.
    app.answer(BATTERY, now=_at("2026-10-28T12:00"))
    app.answer(BATTERY, now=_at("2026-10-28T16:01"))
    assert app.state.wakes[-1] == _at("2026-10-28T19:00").isoformat()

    # "Głęboki sen" for two days, asked while it is awake.
    app.request_rest(_at("2026-10-28T16:02"), _at("2026-10-30T16:02"))
    assert app.rest_pending()
    answer = app.answer(BATTERY, now=_at("2026-10-28T16:02:20"))
    assert answer.action == "sleep" and answer.standby == "OFF"
    assert answer.wake_ms == int(_at("2026-10-30T16:02").timestamp() * 1000)
    assert answer.wakes_ms == []
    assert app.deep_asleep() and not app.rest_pending()
    service.power.publish_status()
    status = service.status.status
    assert status.rest_until == _at("2026-10-30T16:02").isoformat() and not status.switched_off
    assert app.wakes_at() == _at("2026-10-30T16:02")

    # The 19:00 alarm set before still rings (alarms cannot be cancelled):
    # back to sleep, and no changes meanwhile.
    _next_change(service, _at("2026-10-28T19:00"))
    answer = app.answer(BATTERY, now=_at("2026-10-28T19:01:30"))
    assert answer.action == "sleep" and answer.standby == "OFF"
    assert answer.wake_ms == int(_at("2026-10-30T16:02").timestamp() * 1000)

    # The button the next day: the rest is over, the schedule is back.
    _next_change(service, _at("2026-10-29T19:00"))
    answer = app.answer(BATTERY, now=_at("2026-10-29T10:00"))
    assert app.state.rest_until is None
    assert answer.wake_at == _at("2026-10-29T12:00").isoformat()  # the next check

    # A rest that runs out: at its alarm it is over by itself.
    app.request_rest(_at("2026-10-29T10:00"), _at("2026-10-29T14:00"))
    app.answer(BATTERY, now=_at("2026-10-29T10:00:30"))
    answer = app.answer(BATTERY, now=_at("2026-10-29T13:59:50"))
    assert app.state.rest_until is None
    assert answer.wake_at == _at("2026-10-29T16:00").isoformat()


def test_switched_off_sleeps_without_an_alarm_even_on_the_charger(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app = service.app
    now = _at("2026-10-28T12:00")
    _next_change(service, _at("2026-10-28T19:00"))
    app.answer(AppHello(charging=True), now=now)
    app.request_rest(now, None)
    answer = app.answer(AppHello(charging=True), now=now + timedelta(seconds=20))
    assert answer.action == "sleep" and answer.standby == "OFF"
    assert answer.wake_ms is None and answer.wake_at is None
    assert app.deep_asleep() and app.wakes_at() is None
    service.power.publish_status()
    assert service.status.status.switched_off

    # The launcher restarts the app as it goes to sleep: still off.
    answer = app.answer(AppHello(charging=True), now=now + timedelta(minutes=1))
    assert answer.action == "sleep" and answer.wake_ms is None
    # The button hours later: on again, and on the charger it stays awake.
    answer = app.answer(AppHello(charging=True), now=now + timedelta(hours=5))
    assert answer.action == "stay" and not app.state.off
    # "Obudź ramkę" / "Uśpij ramkę" also end a rest asked for.
    app.request_rest(now, None)
    app.request_sleep()
    assert not app.state.off


def test_rest_api_limits_the_hours(tmp_path: Path) -> None:
    from frame_server.web import create_app

    service = _service(tmp_path)
    app = create_app(service.settings)
    with TestClient(app) as client:
        assert client.post("/api/device/sleep", params={"hours": 73}).status_code == 422
        reply = client.post("/api/device/sleep", params={"hours": 24})
        assert reply.status_code == 200, reply.text
        assert reply.json()["until"] is not None and reply.json()["applies"] == "soon"
        reply = client.post("/api/device/sleep", params={"off": "true"})
        assert reply.json()["until"] is None
        assert app.state.service.app.state.off


async def test_a_resting_panel_is_looked_for_now_and_then(
    tmp_path: Path, server_ssl: ssl.SSLContext
) -> None:
    panel = FakePanel(server_ssl)
    await panel.start()
    try:
        service = _service(tmp_path, panel.port)
        app = service.app
        now = _at("2026-10-28T12:00")
        _next_change(service, _at("2026-10-28T19:00"))
        app.answer(BATTERY, now=now)
        app.request_rest(now, None)
        app.answer(BATTERY, now=now + timedelta(seconds=10))
        await service.power.tick(now + timedelta(minutes=2))
        assert panel.received == []  # just put to sleep
        # Answering MDC although nothing rang: the button. The app is started.
        await service.power.tick(now + timedelta(minutes=6))
        assert panel.received == START
        await service.power.tick(now + timedelta(minutes=6, seconds=30))
        assert panel.received == START  # not again so soon
    finally:
        await panel.stop()


async def test_the_button_is_looked_for_in_any_sleep_without_wifi(
    tmp_path: Path, server_ssl: ssl.SSLContext
) -> None:
    """After the button the launcher seldom starts the app: in the economy
    mode and asleep by itself without the Wi-Fi the server looks for the
    panel too, but not around an alarm (a check with nothing new is left
    alone)."""
    panel = FakePanel(server_ssl)
    await panel.start()
    try:
        service = _service(tmp_path, panel.port)
        service.player.save_settings(
            FrameSettings(
                change_times=["07:00", "19:00"],
                power_mode="economy",
                check_every_hours=2,
                quiet_start=None,
            )
        )
        _next_change(service, _at("2026-10-28T19:00"))
        app = service.app
        content = service.store.current()
        assert content is not None
        hello = BATTERY.model_copy(update={"shown": content.file_id})
        app.answer(hello, now=_at("2026-10-28T12:00"))
        await service.power.tick(_at("2026-10-28T12:03"))
        assert panel.received == []  # just put to sleep
        await service.power.tick(_at("2026-10-28T14:05"))
        assert panel.received == []  # the 14:00 check
        # Answering MDC although nothing rang: the button.
        await service.power.tick(_at("2026-10-28T15:00"))
        assert panel.received == START

        # Unplugged on the charger: asleep by itself, off the Wi-Fi.
        app.answer(AppHello(charging=True), now=_at("2026-10-28T15:01"))
        state = app.state
        state.asleep, state.standby, state.wifi_lost = True, False, True
        state.wakes, state.wake_at, state.slept_at = [], None, None
        app._save(state)
        panel.received.clear()
        await service.power.tick(_at("2026-10-28T15:30"))
        assert panel.received == START
    finally:
        await panel.stop()


async def test_spare_alarms_on_the_charger_wake_a_frame_unplugged(
    tmp_path: Path, server_ssl: ssl.SSLContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mateusz, 2026-10-29: unplugged, the frame sleeps at once without the
    Wi-Fi. On the charger in the online mode the app keeps spare alarms, so
    it wakes by itself and the server starts the app, back to the usual
    sleep in the network. Not in the economy mode."""

    async def presence(host: str) -> bool | None:
        return False

    monkeypatch.setattr(status_module, "on_network", presence)
    panel = FakePanel(server_ssl)
    await panel.start()
    try:
        service = _service(tmp_path, panel.port)
        service.player.save_settings(
            FrameSettings(change_times=["07:00", "19:00"], quiet_start=None)
        )
        app = service.app
        service.status.status.power_source = "ac"
        now = _at("2026-10-29T10:12")
        answer = app.answer(AppHello(charging=True), now=now)
        assert answer.action == "stay"
        assert answer.wake_ms == _ms("2026-10-29T10:30")
        assert answer.wakes_ms == [_ms("2026-10-29T11:00")]
        # Less than five minutes before one: the next two.
        answer = app.answer(AppHello(charging=True), now=_at("2026-10-29T10:26"))
        assert answer.wake_ms == _ms("2026-10-29T11:00")
        assert len(app.state.spare) == 3

        # Unplugged at 10:27: silent, the panel does not answer, off the Wi-Fi.
        unplugged = _at("2026-10-29T10:27")
        app.heard_at = unplugged
        port = service.settings.device_port
        service.settings.device_port = 1  # nobody answers
        await service.power.tick(unplugged + timedelta(minutes=4))
        assert app.deep_asleep() and app.state.wifi_lost
        assert app.wakes_at(unplugged + timedelta(minutes=4)) == _at("2026-10-29T11:00")

        # 11:00: the spare alarm wakes it, the server starts the app.
        service.settings.device_port = port
        panel.received.clear()
        await service.power.tick(_at("2026-10-29T11:01:10"))
        assert panel.received == START

        # Economy: no spare alarms (sleeping without the Wi-Fi is the point).
        service.player.save_settings(
            FrameSettings(change_times=["07:00", "19:00"], quiet_start=None, power_mode="economy")
        )
        service.status.status.power_source = "ac"
        answer = app.answer(AppHello(charging=True), now=_at("2026-10-29T12:00"))
        assert answer.action == "stay" and answer.wake_ms is None and answer.wakes_ms == []
    finally:
        await panel.stop()


async def test_a_waiting_picture_goes_out_with_the_progress_bar(tmp_path: Path) -> None:
    """Woken by the button, the app asks and gets the picture that waited
    for it: the iOS app follows its download and refresh."""
    service = _service(tmp_path)
    app = service.app
    old = service.store.current()
    assert old is not None
    service.store.publish(b"png", "png", title="Słoneczniki")
    service.power.mark_pending(True)
    answer = await app.ask(BATTERY.model_copy(update={"shown": old.file_id}))
    assert answer.title == "Słoneczniki" and not service.power.state.pending_push
    progress = service.progress.view()
    assert progress.active and progress.stage == "downloading" and progress.title == "Słoneczniki"
    app.report("shown", {"file_id": answer.file_id})
    await asyncio.sleep(0)
    assert service.progress.view().stage == "refreshing"


def test_battery_rate_is_measured_on_battery(tmp_path: Path) -> None:
    service = _service(tmp_path)
    status = service.status
    start = _at("2026-10-28T08:00")
    for hours, level in [(0, 90), (0.2, 90), (6, 88)]:
        status.note_app(start + timedelta(hours=hours), level, False)
    assert status.status.battery_per_day is None  # not half a day yet
    status.note_app(start + timedelta(hours=13), 85, False)
    assert status.status.battery_per_day == 9.2
    status.note_app(start + timedelta(hours=24), 81, False)
    assert status.status.battery_per_day == 9.0
    assert status.status.battery_days == 9.0
    # Recharged: measured anew.
    status.note_app(start + timedelta(hours=25), 81, True)
    assert status.status.battery_per_day is None and status.status.battery_days is None
    status.note_app(start + timedelta(hours=30), 100, False)
    assert status.status.battery_days is None


async def test_no_start_over_mdc_once_the_app_asked_or_sleeps(
    tmp_path: Path, server_ssl: ssl.SSLContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2026-10-30: the server took the app for silent, and its start over MDC
    went out just as the app asked and was told to sleep. The panel went down
    halfway through the launcher's restart and the app never ran again. A
    question while the session opens, or a sleep answer moments ago, stops
    the start."""
    panel = FakePanel(server_ssl)
    await panel.start()
    try:
        service = _service(tmp_path, panel.port)
        app = service.app
        app.store_package(b"PK\x03\x04signed", "2.0.0")
        _next_change(service, datetime.now(UTC) + timedelta(hours=3))
        opened = service.panel.session

        def asking_meanwhile():  # type: ignore[no-untyped-def]
            hello = AppHello(reason="resume", build="2.0.0", battery=80, charging=False)
            assert app.answer(hello).action == "sleep"  # it asks, and goes to sleep
            return opened()

        monkeypatch.setattr(service.panel, "session", asking_meanwhile)
        assert await app._kick()
        assert panel.received == []
        monkeypatch.setattr(service.panel, "session", opened)
        assert not await app.start("did not ask after a wake")
        assert panel.received == []
        # Down for a while: started again.
        state = app.state
        state.slept_at = (datetime.now(UTC) - timedelta(minutes=4)).isoformat()
        app._save(state)
        assert await app.start("did not ask after a wake")
        assert panel.received == START
        app.report("sleep", {"why": "plan"})
        assert not await app.start("did not ask after a wake")
    finally:
        await panel.stop()


async def test_an_app_that_never_starts_is_installed_again(
    tmp_path: Path, server_ssl: ssl.SSLContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2026-10-30: the panel acknowledged start after start over MDC and the
    app never asked (the launcher took it for running). After two starts
    without a question a new version is installed, which starts it afresh;
    a question in between resets the count."""
    panel = FakePanel(server_ssl)
    await panel.start()
    try:
        service = _service(tmp_path, panel.port)
        app = service.app
        app.store_package(b"PK\x03\x04signed", "2.0.0")
        built: list[str] = []

        def rebuild():  # type: ignore[no-untyped-def]
            info = app.store_package(b"PK\x03\x04again", "2.0.1")
            built.append(info.version)
            return info

        monkeypatch.setattr(app, "_rebuild_package", rebuild)
        await app.start("did not ask after a wake")
        app.answer(AppHello(reason="start", build="2.0.0", charging=True))  # it asked
        await app.start("did not ask after a wake")
        await app.start("did not ask after a wake")
        assert built == [] and panel.received == START * 3
        panel.received.clear()
        await app.start("did not ask after a wake")
        assert built == ["2.0.1"] and panel.received == INSTALL
        assert app.sssp_config() is not None and "<ver>2.0.1</ver>" in app.sssp_config()
        # Not again within half an hour: started as usual.
        panel.received.clear()
        await app.start("did not ask after a wake")
        await app.start("did not ask after a wake")
        await app.start("did not ask after a wake")
        assert built == ["2.0.1"] and panel.received == START * 3
    finally:
        await panel.stop()


def test_a_panel_that_answers_while_its_app_is_silent_says_so(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app = service.app
    stay = AppHello(reason="wake", build="1.0.0", battery=90, charging=True)
    asked = datetime.now(UTC) - timedelta(minutes=51)
    app.answer(stay, now=asked)
    status = service.status.status
    assert status.power_state == "online"
    # Asked just now: nothing to say.
    assert app.silent_since(asked + timedelta(minutes=2)) is None
    # The panel answers MDC (power_state stays online), the app never asks again.
    now = datetime.now(UTC)
    assert app.silent_since(now) == asked
    service.power.publish_status()
    assert status.app_silent_since == asked.isoformat(timespec="seconds")
    # Asleep as far as the server can tell: not "silent".
    service.status.note_sleep(deep=False)
    assert app.silent_since(now) is None
    service.power.publish_status()
    assert status.app_silent_since is None


def test_unanswered_starts_space_out_on_battery(tmp_path: Path) -> None:
    """2026-10-30: a stuck app was started every few minutes all night, and
    every MDC session kept the panel up (97 % to 58 %). Past two unanswered
    starts on battery the next ones wait 5, 10, 20 ... minutes, at most an
    hour; on the charger they do not."""
    service = _service(tmp_path)
    app = service.app
    now = _at("2026-10-30T06:00")
    service.status.status.power_source = "battery"
    app._unanswered = 2
    app._kicked = now
    assert not app._backing_off(now)  # the reinstall is still to come
    app._unanswered = 3
    assert app._backing_off(now + timedelta(minutes=4))
    assert not app._backing_off(now + timedelta(minutes=5))
    app._unanswered = 5
    assert app._backing_off(now + timedelta(minutes=19))
    assert not app._backing_off(now + timedelta(minutes=20))
    app._unanswered = 20
    assert not app._backing_off(now + timedelta(hours=1))
    service.status.status.power_source = "ac"
    assert not app._backing_off(now + timedelta(minutes=1))
    app.answer(AppHello(reason="start", build="2.0.0", charging=True), now=now)
    assert app._unanswered == 0


async def test_a_panel_stuck_after_a_reinstall_is_put_into_deep_sleep(
    tmp_path: Path, server_ssl: ssl.SSLContext
) -> None:
    """2026-10-30: after the reinstall not even the launcher asked the server
    for hours, and MDC has no restart (0x11 02 NAK). Ten minutes on, the
    panel is put into deep sleep, which ends in a fresh boot at its alarm or
    the button."""
    panel = FakePanel(server_ssl)
    await panel.start()
    try:
        service = _service(tmp_path, panel.port)
        app = service.app
        app.answer(
            AppHello(reason="start", build="2.0.0", charging=False), now=_at("2026-10-30T00:24")
        )
        app._reinstall_pending = True
        app._reinstalled = datetime.now(UTC) - timedelta(minutes=5)
        now = datetime.now(UTC)
        assert not app._stuck_after_reinstall()
        app._reinstalled = datetime.now(UTC) - timedelta(minutes=11)
        panel.received.clear()
        await service.power.tick(now)
        assert panel.received == [(0xB5, b"\x00"), (0x11, b"\x00")]
        state = app.state
        assert state.asleep and not state.standby and state.wifi_lost
        assert app.deep_asleep()
        # Once: the next tick leaves it alone (just put to sleep).
        panel.received.clear()
        await service.power.tick(now + timedelta(seconds=5))
        assert panel.received == []
    finally:
        await panel.stop()
