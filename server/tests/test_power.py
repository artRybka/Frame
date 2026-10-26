"""Power policy against a fake panel: deep sleep at night, alarm, pending push."""

from __future__ import annotations

import ssl
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import trustme
from fake_panel import FakePanel

from frame_server.config import Settings
from frame_server.device.mdc import (
    CMD_NETWORK_STANDBY,
    CMD_ON_TIMER,
    CMD_POWER,
    CMD_STATUS,
)
from frame_server.power import alarm_time, night_key
from frame_server.schedule import FrameSettings
from frame_server.service import FrameService, PushOutcome

WARSAW = ZoneInfo("Europe/Warsaw")


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=WARSAW)


@pytest.fixture(scope="module")
def server_ssl() -> ssl.SSLContext:
    ca = trustme.CA()
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ca.issue_cert("panel.local").configure_cert(ctx)
    return ctx


def test_night_key_and_alarm() -> None:
    settings = FrameSettings()  # quiet hours 22:00 until the 07:00 change
    assert night_key(_at("2026-10-25T23:30"), settings) == "2026-10-25"
    assert night_key(_at("2026-10-26T03:00"), settings) == "2026-10-25"
    assert alarm_time(settings) == time(7, 0)
    later = FrameSettings(change_times=["06:45", "18:00"], quiet_start="20:00")
    assert alarm_time(later) == time(6, 45)
    # Without quiet hours the alarm still wakes the panel for the first change.
    assert alarm_time(FrameSettings(change_times=["09:00"], quiet_start=None)) == time(9, 0)


@pytest.mark.parametrize("charger", [False, True])
async def test_night_sleep_alarm_and_pending_push(
    tmp_path: Path, server_ssl: ssl.SSLContext, charger: bool
) -> None:
    """On battery the panel sleeps deeply at night; on the charger it stays
    reachable and pictures go out at once."""

    def handler(command: int, data: bytes) -> tuple[bool, bytes]:
        if command == CMD_STATUS:
            # Last byte 02: charger plugged in, 00: on battery (E1).
            return True, bytes([0x73, 0x00, 0x01, 0x01, 80, 0x02, 0x02 if charger else 0x00])
        if command == CMD_NETWORK_STANDBY and not data:
            return True, b"\x01"
        if command in (0x0E, 0x10, 0x0B, 0x67):
            return True, b"X"
        return True, data[:4] if command == CMD_ON_TIMER else b""

    panel = FakePanel(server_ssl, handler=handler)
    await panel.start()
    try:
        settings = Settings(
            data_dir=tmp_path,
            seed_library=False,
            scheduler=False,
            public_host="127.0.0.1",
            device_host="127.0.0.1",
            device_pin="123456",
            device_port=panel.port,
        )
        service = FrameService(settings)
        service.ensure_initial_content()
        await service.status.refresh()
        assert service.status.on_battery is not charger

        if charger:
            await service.power.tick(_at("2026-10-25T22:01"))
            assert (CMD_POWER, b"\x00") not in panel.received
            assert (CMD_NETWORK_STANDBY, b"\x00") not in panel.received
            assert not service.power.deep_asleep(_at("2026-10-25T23:00"))
            return

        # Evening: alarm for the morning change, Wi-Fi off, panel off.
        await service.power.tick(_at("2026-10-25T22:01"))
        assert (CMD_ON_TIMER, bytes([0x01, 0x02, 7, 0, 0x01])) in panel.received
        assert (CMD_NETWORK_STANDBY, b"\x00") in panel.received
        assert (CMD_POWER, b"\x00") in panel.received
        assert service.power.state.timer == "07:00"

        # A picture sent at night waits, without trying to reach the panel.
        sent = len(panel.received)
        assert service.power.deep_asleep(_at("2026-10-25T23:00"))
        await service.power.tick(_at("2026-10-25T23:00"))  # once a night only
        assert len(panel.received) == sent
        service.power.mark_pending(True)
        assert service.status.status.pending_push

        # Rotation holds off while a picture waits.
        await service.player.tick()

        # The alarm rings: the panel is found, Wi-Fi back on, the picture goes out.
        pushed: list[bool] = []

        async def fake_push(wait: float = 90.0) -> PushOutcome:
            pushed.append(True)
            service.power.mark_pending(False)
            content = service.store.current()
            assert content is not None
            return PushOutcome(content, True, True, "url")

        service.push_current = fake_push  # type: ignore[method-assign]
        await service.power.tick(_at("2026-10-26T07:00:10"))
        assert (CMD_NETWORK_STANDBY, b"\x01") in panel.received
        assert pushed == [True]
        assert not service.power.state.pending_push
        assert service.power.state.woke_on == "2026-10-26"
    finally:
        await panel.stop()


async def test_network_standby_comes_back_after_a_missed_alarm(
    tmp_path: Path, server_ssl: ssl.SSLContext
) -> None:
    """The night turned network standby off and the alarm window passed
    without the panel: once the button wakes it, standby goes back on, so
    Wake-on-LAN works again by day. A status check finding it off does the same."""
    standby = [b"\x00"]

    def handler(command: int, data: bytes) -> tuple[bool, bytes]:
        if command == CMD_STATUS:
            return True, bytes([0x73, 0x00, 0x01, 0x01, 80, 0x02, 0x00])
        if command == CMD_NETWORK_STANDBY:
            if data:
                standby[0] = data[:1]
            return True, standby[0]
        if command in (0x0E, 0x10, 0x0B, 0x67):
            return True, b"X"
        return True, data[:4] if command == CMD_ON_TIMER else b""

    panel = FakePanel(server_ssl, handler=handler)
    await panel.start()
    try:
        settings = Settings(
            data_dir=tmp_path,
            seed_library=False,
            scheduler=False,
            public_host="127.0.0.1",
            device_host="127.0.0.1",
            device_pin="123456",
            device_port=panel.port,
        )
        service = FrameService(settings)
        service.ensure_initial_content()
        await service.status.refresh()
        assert service.status.status.network_standby is False

        # A status check by day found standby off: the server restores it.
        await service.power.tick(_at("2026-10-26T12:00"))
        assert standby[0] == b"\x01"
        assert not service.power.state.standby_off
        assert service.status.status.network_standby is True

        # The night turns it off again; nothing waits, the alarm window passes.
        await service.power.tick(_at("2026-10-26T22:01"))
        assert standby[0] == b"\x00"
        assert service.power.state.standby_off
        state = service.power.state
        state.woke_on = "2026-10-27"  # the alarm window is over
        service.power._save(state)
        await service.power.tick(_at("2026-10-27T09:00"))
        assert standby[0] == b"\x01"
        assert not service.power.state.standby_off
    finally:
        await panel.stop()


async def test_wake_from_the_app(tmp_path: Path, server_ssl: ssl.SSLContext) -> None:
    def handler(command: int, data: bytes) -> tuple[bool, bytes]:
        if command == CMD_STATUS:
            return True, bytes([0x73, 0x00, 0x01, 0x01, 80, 0x02, 0x00])
        if command == CMD_NETWORK_STANDBY and not data:
            return True, b"\x01"
        if command in (0x0E, 0x10, 0x0B, 0x67):
            return True, b"X"
        return True, b""

    panel = FakePanel(server_ssl, handler=handler)
    await panel.start()
    try:
        settings = Settings(
            data_dir=tmp_path,
            seed_library=False,
            scheduler=False,
            public_host="127.0.0.1",
            device_host="127.0.0.1",
            device_pin="123456",
            device_port=panel.port,
            device_mac="aa:bb:cc:dd:ee:ff",
        )
        service = FrameService(settings)
        result = await service.power.wake_now()
        assert result.sent and result.woke

        # Deep sleep on battery: the Wi-Fi is off, no packets are wasted.
        service.power.deep_asleep = lambda now: True  # type: ignore[method-assign]
        result = await service.power.wake_now()
        assert not result.sent and not result.woke
    finally:
        await panel.stop()


@pytest.mark.parametrize("charger", [False, True])
async def test_light_sleep_after_a_picture(
    tmp_path: Path, server_ssl: ssl.SSLContext, monkeypatch: pytest.MonkeyPatch, charger: bool
) -> None:
    """On battery the panel goes back to light sleep (network standby on)
    once the picture is drawn; a new picture in between keeps it awake."""
    import asyncio

    from frame_server import power

    def handler(command: int, data: bytes) -> tuple[bool, bytes]:
        if command == CMD_STATUS:
            return True, bytes([0x73, 0x00, 0x01, 0x01, 80, 0x02, 0x02 if charger else 0x00])
        if command == CMD_NETWORK_STANDBY and not data:
            return True, b"\x01"
        if command in (0x0E, 0x10, 0x0B, 0x67):
            return True, b"X"
        return True, b""

    panel = FakePanel(server_ssl, handler=handler)
    await panel.start()
    monkeypatch.setattr(power, "LIGHT_SLEEP_AFTER", 0.2)
    monkeypatch.setattr(power, "in_quiet_hours", lambda now, settings: False)
    try:
        settings = Settings(
            data_dir=tmp_path,
            seed_library=False,
            scheduler=False,
            public_host="127.0.0.1",
            device_host="127.0.0.1",
            device_pin="123456",
            device_port=panel.port,
        )
        service = FrameService(settings)
        await service.status.refresh()

        service.power.after_push(fetched=True)
        service.power.cancel_light_sleep()  # the next picture is on its way
        await asyncio.sleep(0.5)
        assert (CMD_POWER, b"\x00") not in panel.received

        service.power.after_push(fetched=True)
        await asyncio.sleep(3)
        if charger:
            assert (CMD_POWER, b"\x00") not in panel.received
        else:
            assert (CMD_NETWORK_STANDBY, b"\x01") in panel.received
            assert (CMD_POWER, b"\x00") in panel.received
    finally:
        await panel.stop()


async def test_power_state_for_the_network_tile(tmp_path: Path, server_ssl: ssl.SSLContext) -> None:
    """Online when it answers; when it does not, the sleep it is most
    likely in: standby (Wake-on-LAN reaches it) or deep sleep (Wi-Fi off)."""

    def handler(command: int, data: bytes) -> tuple[bool, bytes]:
        if command == CMD_STATUS:
            return True, bytes([0x73, 0x00, 0x01, 0x01, 80, 0x02, 0x00])
        if command == CMD_NETWORK_STANDBY and not data:
            return True, b"\x01"
        if command in (0x0E, 0x10, 0x0B, 0x67):
            return True, b"X"
        return True, b""

    panel = FakePanel(server_ssl, handler=handler)
    await panel.start()
    settings = Settings(
        data_dir=tmp_path,
        seed_library=False,
        scheduler=False,
        public_host="127.0.0.1",
        device_host="127.0.0.1",
        device_pin="123456",
        device_port=panel.port,
    )
    service = FrameService(settings)
    try:
        assert service.status.status.power_state is None
        assert (await service.status.refresh()).power_state == "online"
        await service.power._sleep_later(0)
        assert service.status.status.power_state == "standby"
    finally:
        await panel.stop()

    # Asleep with network standby on: Wake-on-LAN should reach it.
    status = await service.status.refresh()
    assert not status.reachable and status.power_state == "standby"
    # The night turned the Wi-Fi off and the panel has not been found since.
    state = service.power.state
    state.standby_off = True
    service.power._save(state)
    assert (await service.status.refresh()).power_state == "deep_sleep"

    # A panel never seen answering: nothing to go by.
    service.status.forget()
    service.power._save(state.model_copy(update={"standby_off": False}))
    assert (await service.status.refresh()).power_state == "offline"


@pytest.mark.parametrize("charger", [False, True])
async def test_status_check_wakes_and_lets_it_sleep_again(
    tmp_path: Path, server_ssl: ssl.SSLContext, monkeypatch: pytest.MonkeyPatch, charger: bool
) -> None:
    """The "Sprawdź stan" button wakes the panel only to look at it: on battery it goes
    back to light sleep afterwards; on the charger it stays on."""
    import asyncio

    from frame_server import power

    def handler(command: int, data: bytes) -> tuple[bool, bytes]:
        if command == CMD_STATUS:
            return True, bytes([0x73, 0x00, 0x01, 0x01, 80, 0x02, 0x02 if charger else 0x00])
        if command == CMD_NETWORK_STANDBY and not data:
            return True, b"\x01"
        if command in (0x0E, 0x10, 0x0B, 0x67):
            return True, b"X"
        return True, b""

    panel = FakePanel(server_ssl, handler=handler)
    await panel.start()
    monkeypatch.setattr(power, "CHECK_SLEEP_AFTER", 0.2)
    monkeypatch.setattr(power, "in_quiet_hours", lambda now, settings: False)
    try:
        settings = Settings(
            data_dir=tmp_path,
            seed_library=False,
            scheduler=False,
            public_host="127.0.0.1",
            device_host="127.0.0.1",
            device_pin="123456",
            device_port=panel.port,
            device_mac="aa:bb:cc:dd:ee:ff",
        )
        service = FrameService(settings)
        result = await service.power.wake_now(sleep_after=True)
        assert result.woke
        assert service.status.status.power_state == "online"
        await asyncio.sleep(3)
        if charger:
            assert (CMD_POWER, b"\x00") not in panel.received
        else:
            assert (CMD_POWER, b"\x00") in panel.received
            assert service.status.status.power_state == "standby"
    finally:
        await panel.stop()
