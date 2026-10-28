"""Power policy against a fake panel: the frame's app sleeps and wakes by
itself, the server wakes it for a picture and starts it when it is not running."""

from __future__ import annotations

import asyncio
import socket
import ssl
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import trustme
from fake_panel import FakePanel

from frame_server import power
from frame_server import status as status_module
from frame_server.config import Settings
from frame_server.device.mdc import CMD_CONTENT_DOWNLOAD, CMD_NETWORK_STANDBY, CMD_STATUS
from frame_server.panel_app import AppHello
from frame_server.schedule import FrameSettings
from frame_server.service import FrameService

WARSAW = ZoneInfo("Europe/Warsaw")
BATTERY = AppHello(reason="wake", build="2.0.0", battery=80, charging=False)


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=WARSAW)


@pytest.fixture(scope="module")
def server_ssl() -> ssl.SSLContext:
    ca = trustme.CA()
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ca.issue_cert("panel.local").configure_cert(ctx)
    return ctx


def _handler(command: int, data: bytes) -> tuple[bool, bytes]:
    if command == CMD_STATUS:
        return True, bytes([0x73, 0x00, 0x01, 0x01, 80, 0x02, 0x00])
    if command == CMD_NETWORK_STANDBY and not data:
        return True, b"\x01"
    if command in (0x0E, 0x10, 0x0B, 0x67):
        return True, b"X"
    return True, data


def _settings(tmp_path: Path, port: int, mac: str | None = "aa:bb:cc:dd:ee:ff") -> Settings:
    return Settings(
        data_dir=tmp_path,
        seed_library=False,
        scheduler=False,
        public_host="127.0.0.1",
        device_host="127.0.0.1",
        device_pin="123456",
        device_port=port,
        device_mac=mac,
    )


def _asleep(service: FrameService, *, deep: bool) -> None:
    """The app was told to sleep until the next change."""
    service.app.awake_until = None
    service.player.save_settings(
        FrameSettings(
            change_times=["07:00", "19:00"],
            quiet_start=None,
            power_mode="economy" if deep else "online",
        )
    )
    answer = service.app.answer(BATTERY, now=datetime.now(UTC))
    assert answer.action == "sleep" and answer.standby == ("OFF" if deep else "ON")


async def test_wake_from_the_app(
    tmp_path: Path, server_ssl: ssl.SSLContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(power, "WAKE_LOOK", timedelta(seconds=2))
    panel = FakePanel(server_ssl, handler=_handler)
    await panel.start()
    try:
        service = FrameService(_settings(tmp_path, panel.port))
        service.app.answer(AppHello(charging=True))  # on the charger, asking every 20 s
        result = await service.power.wake_now()
        assert not result.sent and result.woke

        # Asleep with the Wi-Fi on: Wake-on-LAN until the app asks.
        _asleep(service, deep=False)
        wake = asyncio.create_task(service.power.wake_now())
        await asyncio.sleep(0.3)
        service.app.answer(BATTERY)
        result = await wake
        assert result.sent and result.woke
        # "Obudź ramkę" keeps it awake for a while.
        assert service.app.answer(BATTERY).action == "stay"

        # Nobody answers: it says so.
        service.app.awake_until = None
        _asleep(service, deep=False)
        result = await service.power.wake_now(sleep_after=True)
        assert result.sent and not result.woke

        # Deep sleep: the Wi-Fi is off, no packets are wasted.
        _asleep(service, deep=True)
        result = await service.power.wake_now()
        assert not result.sent and not result.woke and result.asleep_until_at
        assert service.power.deep_asleep()
    finally:
        await panel.stop()


async def test_wake_starts_the_app_when_the_panel_does_not_run_it(
    tmp_path: Path, server_ssl: ssl.SSLContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(power, "INSTALL_LOOK", timedelta(seconds=2))
    panel = FakePanel(server_ssl, handler=_handler)
    await panel.start()
    try:
        service = FrameService(_settings(tmp_path, panel.port))
        # No package (no certificates): nothing to start.
        result = await service.power.wake_now()
        assert not result.woke and "certificates" in (result.reason or "")

        service.app.store_package(b"PK\x03\x04signed", "2.0.0")
        wake = asyncio.create_task(service.power.wake_now())
        await asyncio.sleep(0.5)
        assert (CMD_CONTENT_DOWNLOAD, b"\x82http://127.0.0.1:8099/panel/app") in panel.received
        assert panel.received[-1] == (CMD_CONTENT_DOWNLOAD, b"\x81\x01")
        service.app.answer(AppHello(reason="start", build="2.0.0", charging=True))
        result = await wake
        assert result.woke and service.status.status.panel_app
    finally:
        await panel.stop()


async def test_power_state_for_the_network_tile(tmp_path: Path, server_ssl: ssl.SSLContext) -> None:
    """Online when it answers; when it does not, the sleep the app went into:
    standby (Wake-on-LAN reaches it) or deep sleep (Wi-Fi off)."""
    panel = FakePanel(server_ssl, handler=_handler)
    await panel.start()
    settings = _settings(tmp_path, panel.port)
    service = FrameService(settings)
    try:
        assert service.status.status.power_state is None
        assert (await service.status.refresh()).power_state == "online"
    finally:
        await panel.stop()

    _asleep(service, deep=False)
    status = await service.status.refresh(force=True)
    assert not status.reachable and status.power_state == "standby"
    assert status.wakes_at is not None and status.wake_at is not None
    # The server restarts while the panel sleeps: it still knows.
    restarted = FrameService(settings)
    assert (await restarted.status.refresh(force=True)).power_state == "standby"
    _asleep(service, deep=True)
    assert (await service.status.refresh(force=True)).power_state == "deep_sleep"

    # A panel never seen answering: nothing to go by.
    fresh = FrameService(_settings(tmp_path / "fresh", _closed_port()))
    assert (await fresh.status.refresh()).power_state == "offline"


@pytest.mark.parametrize(
    ("standby", "on_network", "expected"),
    [
        (None, True, "standby"),  # never seen, but on the Wi-Fi: asleep
        (True, True, "standby"),
        (True, False, "standby"),  # no ARP answer: not taken as gone yet (E15)
        (False, True, "standby"),  # it is on the Wi-Fi after all
        (False, False, "deep_sleep"),
        (None, False, "offline"),
        (True, None, "standby"),  # cannot tell (behind a router): as before
    ],
)
async def test_asleep_on_the_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    standby: bool | None,
    on_network: bool | None,
    expected: str,
) -> None:
    """Not answering MDC: whether it still answers ARP tells sleep from gone,
    without waking it."""
    asked: list[str] = []

    async def presence(host: str) -> bool | None:
        asked.append(host)
        return on_network

    monkeypatch.setattr(status_module, "on_network", presence)
    settings = Settings(
        data_dir=tmp_path,
        seed_library=False,
        scheduler=False,
        public_host="127.0.0.1",
        device_host="127.0.0.1",
        device_pin="123456",
        device_port=_closed_port(),
    )
    service = FrameService(settings)
    service.status.status.network_standby = standby
    status = await service.status.refresh(force=True)
    assert not status.reachable
    assert asked == ["127.0.0.1"]
    assert status.on_network is on_network
    assert status.power_state == expected


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_economy_check_times() -> None:
    from frame_server.schedule import check_times, next_check, quiet_hours

    economy = FrameSettings(
        change_times=["07:00", "19:00"], power_mode="economy", check_every_hours=4
    )
    assert check_times(economy) == [time(11, 0), time(15, 0)]
    assert quiet_hours(economy) is None  # the panel sleeps deeply anyway
    assert next_check(_at("2026-10-27T15:00"), economy) == _at("2026-10-28T11:00")
    every3 = economy.model_copy(update={"check_every_hours": 3})
    assert check_times(every3) == [time(10, 0), time(13, 0), time(16, 0)]
    # One change a day: checks for twelve hours after it.
    alone = FrameSettings(change_times=["08:00"], power_mode="economy", check_every_hours=6)
    assert check_times(alone) == [time(14, 0)]
    assert check_times(economy.model_copy(update={"check_every_hours": 0})) == []
    assert check_times(economy.model_copy(update={"power_mode": "online"})) == []


def test_put_to_sleep_from_the_app(tmp_path: Path) -> None:
    """ "Uśpij ramkę" on the charger: the app sleeps at its next question."""
    service = FrameService(_settings(tmp_path, _closed_port()))
    service.ensure_initial_content()
    charger = AppHello(reason="poll", build="2.0.0", charging=True)
    assert service.app.answer(charger).action == "stay"
    asyncio.run(service.power.sleep_now())
    answer = service.app.answer(charger)
    assert answer.action == "sleep" and service.app.asleep()
    # Only once: the next wake on the charger stays up again.
    assert service.app.answer(charger).action == "stay"


def test_mode_changed_while_asleep(tmp_path: Path) -> None:
    """Oszczędny → Online while the frame sleeps with the Wi-Fi off: nothing
    reaches it, so the app says the change waits for its alarm or the button,
    until the frame asks again."""
    service = FrameService(_settings(tmp_path, _closed_port()))
    service.ensure_initial_content()
    _asleep(service, deep=True)
    status = service.status.status
    assert status.mode_pending is None
    online = service.player.settings.model_copy(update={"power_mode": "online"})
    service.player.save_settings(online)
    service.power.publish_status()
    assert status.mode_pending == "online"
    # Back to the economy mode before it woke: nothing waits.
    service.player.save_settings(online.model_copy(update={"power_mode": "economy"}))
    service.power.publish_status()
    assert status.mode_pending is None
    service.player.save_settings(online)
    service.power.publish_status()
    assert status.mode_pending == "online"
    # It wakes and asks: it is in the online mode now.
    service.app.answer(AppHello(reason="wake", build="2.0.0", charging=True))
    assert status.mode_pending is None
