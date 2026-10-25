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
    """The same on the charger and on battery."""

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
