"""Power policy against a fake panel: deep sleep at night, alarm, pending push."""

from __future__ import annotations

import socket
import ssl
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import trustme
from fake_panel import FakePanel

from frame_server import status as status_module
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


@pytest.mark.parametrize(("charger", "was_asleep"), [(False, False), (True, False), (True, True)])
async def test_light_sleep_after_a_picture(
    tmp_path: Path,
    server_ssl: ssl.SSLContext,
    monkeypatch: pytest.MonkeyPatch,
    charger: bool,
    was_asleep: bool,
) -> None:
    """On battery the panel goes back to light sleep (network standby on)
    once the picture is drawn; on the charger only when it was asleep
    before. A new picture in between keeps it awake."""
    import asyncio

    from frame_server import power

    plugged = [True]  # the last status check saw it on the charger

    def handler(command: int, data: bytes) -> tuple[bool, bytes]:
        if command == CMD_STATUS:
            ac = plugged[0]
            return True, bytes([0x73, 0x00, 0x01, 0x01, 80, 0x02, 0x02 if ac else 0x00])
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
        assert not service.status.on_battery
        # Unplugged since: the server learns it when the picture is drawn.
        plugged[0] = charger
        if was_asleep:
            service.power.put_back_to_sleep()

        service.power.after_push(fetched=True)
        service.power.cancel_light_sleep()  # the next picture is on its way
        await asyncio.sleep(0.5)
        assert (CMD_POWER, b"\x00") not in panel.received

        service.power.after_push(fetched=True)
        await asyncio.sleep(3)
        if charger and not was_asleep:
            assert (CMD_POWER, b"\x00") not in panel.received
            assert service.status.status.power_state == "online"
        else:
            assert (CMD_NETWORK_STANDBY, b"\x01") in panel.received
            assert (CMD_POWER, b"\x00") in panel.received
            assert service.status.status.power_state == "standby"
            assert service.status.on_battery is not charger
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
        # Still answering while it goes down: a look leaves it alone.
        sent = len(panel.received)
        assert (await service.status.refresh()).power_state == "standby"
        assert len(panel.received) == sent
    finally:
        await panel.stop()

    # Asleep with network standby on: Wake-on-LAN should reach it.
    status = await service.status.refresh(force=True)
    assert not status.reachable and status.power_state == "standby"
    # The server restarts while the panel sleeps: it still knows standby is on.
    restarted = FrameService(settings)
    assert restarted.status.status.network_standby is True
    assert restarted.status.status.power_state is None
    assert (await restarted.status.refresh(force=True)).power_state == "standby"
    # The night turned the Wi-Fi off and the panel has not been found since.
    state = service.power.state
    state.standby_off = True
    service.power._save(state)
    assert (await service.status.refresh(force=True)).power_state == "deep_sleep"

    # A panel never seen answering: nothing to go by.
    service.status.forget()
    service.power._save(state.model_copy(update={"standby_off": False}))
    assert (await service.status.refresh()).power_state == "offline"


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


@pytest.mark.parametrize("charger", [False, True])
async def test_status_check_wakes_and_lets_it_sleep_again(
    tmp_path: Path, server_ssl: ssl.SSLContext, monkeypatch: pytest.MonkeyPatch, charger: bool
) -> None:
    """The "Sprawdź stan" button wakes the panel only to look at it: it goes
    back to light sleep afterwards, on the charger as well."""
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
        assert (CMD_POWER, b"\x00") in panel.received
        assert service.status.status.power_state == "standby"
    finally:
        await panel.stop()


async def test_put_to_sleep_from_the_app(
    tmp_path: Path, server_ssl: ssl.SSLContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "Uśpij ramkę" on the charger: the panel shows as asleep at once, is
    left alone while it goes down, and a picture sent to it later puts it
    back to sleep once drawn."""
    import asyncio

    from frame_server import power

    def handler(command: int, data: bytes) -> tuple[bool, bytes]:
        if command == CMD_STATUS:
            return True, bytes([0x73, 0x00, 0x01, 0x01, 80, 0x02, 0x02])
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
        service.ensure_initial_content()
        assert (await service.status.refresh()).power_state == "online"

        await service.power.sleep_now()
        assert (CMD_POWER, b"\x00") in panel.received
        sent = len(panel.received)
        status = await service.status.refresh()
        assert status.power_state == "standby"
        assert len(panel.received) == sent  # not asked while it goes down

        # A picture: the panel takes it (the fake answers at once) ...
        panel.received.clear()

        async def fetched(file_id: str, timeout: float) -> bool:
            return True

        service.store.wait_for_fetch = fetched  # type: ignore[method-assign]
        outcome = await service.push_current(wait=1)
        assert outcome.fetched
        assert service.status.status.power_state == "online"
        # ... and goes back to sleep afterwards, though on the charger.
        await asyncio.sleep(2)
        assert (CMD_POWER, b"\x00") in panel.received
        assert service.status.status.power_state == "standby"
    finally:
        await panel.stop()


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


async def test_economy_deep_sleep_between_wakes(tmp_path: Path, server_ssl: ssl.SSLContext) -> None:
    """Economy on battery: deep sleep until the next wake, a picture from the
    app waits for it, a check with nothing to show goes straight back to
    sleep, and a wake the panel misses moves to the next day."""

    def handler(command: int, data: bytes) -> tuple[bool, bytes]:
        if command == CMD_STATUS:
            return True, bytes([0x73, 0x00, 0x01, 0x01, 80, 0x02, 0x00])  # battery
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
        player = service.player
        player.save_settings(
            FrameSettings(
                change_times=["07:00", "19:00"],
                power_mode="economy",
                check_every_hours=4,
                quiet_start=None,
            )
        )
        state = player.state
        state.next_change_at = _at("2026-10-27T19:00").isoformat()
        player._save_state(state)
        await service.status.refresh()
        assert service.power.economy

        # Awake at noon: alarm for the 15:00 check, Wi-Fi off, panel off.
        await service.power.tick(_at("2026-10-27T12:00"))
        assert (CMD_ON_TIMER, bytes([0x01, 0x02, 15, 0, 0x01])) in panel.received
        assert (CMD_NETWORK_STANDBY, b"\x00") in panel.received
        assert (CMD_POWER, b"\x00") in panel.received
        assert service.power.deep_asleep(_at("2026-10-27T12:30"))
        assert service.power.wakes_at(_at("2026-10-27T12:30")) == _at("2026-10-27T15:00")

        # A picture from the app waits for that wake.
        outcome = await service.push_current(wait=0)
        assert not outcome.pushed
        assert service.power.state.pending_push

        pushed: list[bool] = []

        async def fake_push(wait: float = 90.0) -> PushOutcome:
            pushed.append(True)
            service.power.mark_pending(False)
            content = service.store.current()
            assert content is not None
            return PushOutcome(content, True, True, "url")

        service.push_current = fake_push  # type: ignore[method-assign]
        service.status._slept_at = None  # hours later, not settling any more
        await service.power.tick(_at("2026-10-27T15:00:10"))
        assert pushed == [True]
        assert service.power.state.woke_for == _at("2026-10-27T15:00").isoformat()

        # After the picture: deep sleep again, until the 19:00 change.
        state = player.state
        state.next_change_at = _at("2026-10-27T19:00").isoformat()  # postpone() uses the clock
        player._save_state(state)
        panel.received.clear()
        assert await service.power.enter_deep(_at("2026-10-27T15:05"))
        assert (CMD_ON_TIMER, bytes([0x01, 0x02, 19, 0, 0x01])) in panel.received

        # The panel does not show up at 19:00: tomorrow, same time.
        await panel.stop()
        service.status._slept_at = None
        await service.power.tick(_at("2026-10-27T19:20"))
        power_state = service.power.state
        assert power_state.missed_wake == _at("2026-10-27T19:00").isoformat()
        assert power_state.wake_at == _at("2026-10-28T19:00").isoformat()
    finally:
        await panel.stop()


async def test_economy_check_with_nothing_to_show(
    tmp_path: Path, server_ssl: ssl.SSLContext
) -> None:
    """A check wake with nothing waiting sends the panel straight back to
    sleep, without a picture; a change due now keeps it awake for it."""

    def handler(command: int, data: bytes) -> tuple[bool, bytes]:
        if command == CMD_STATUS:
            return True, bytes([0x73, 0x00, 0x01, 0x01, 80, 0x02, 0x00])
        if command == CMD_NETWORK_STANDBY and not data:
            return True, b"\x00"
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
        player = service.player
        player.save_settings(
            FrameSettings(
                change_times=["07:00", "19:00"], power_mode="economy", check_every_hours=4
            )
        )
        state = player.state
        state.next_change_at = _at("2026-10-27T19:00").isoformat()
        player._save_state(state)
        await service.status.refresh()
        power_state = service.power.state
        power_state.standby_off = True
        power_state.wake_at = _at("2026-10-27T11:00").isoformat()
        service.power._save(power_state)

        await service.power.tick(_at("2026-10-27T11:00:20"))
        assert (CMD_NETWORK_STANDBY, b"\x01") in panel.received  # found
        assert (CMD_ON_TIMER, bytes([0x01, 0x02, 15, 0, 0x01])) in panel.received
        assert service.power.state.wake_at == _at("2026-10-27T15:00").isoformat()
        assert service.power.deep_asleep(_at("2026-10-27T12:00"))

        # The 19:00 change: found a minute early, it stays awake for the change.
        panel.received.clear()
        power_state = service.power.state
        power_state.wake_at = _at("2026-10-27T19:00").isoformat()
        service.power._save(power_state)
        service.status._slept_at = None
        await service.power.tick(_at("2026-10-27T18:59:30"))
        assert (CMD_NETWORK_STANDBY, b"\x01") in panel.received
        assert (CMD_POWER, b"\x00") not in panel.received
        assert not service.power.deep_asleep(_at("2026-10-27T18:59:40"))
    finally:
        await panel.stop()


async def test_refused_alarm_keeps_the_wifi_on(tmp_path: Path, server_ssl: ssl.SSLContext) -> None:
    """Firmware 1130.7 NAKs every hh:mm write of 0x25: the panel could not
    wake itself, so it never sleeps with the Wi-Fi off, at night or in the
    economy mode (which then works as online)."""

    def handler(command: int, data: bytes) -> tuple[bool, bytes]:
        if command == CMD_STATUS:
            return True, bytes([0x73, 0x00, 0x01, 0x01, 80, 0x02, 0x00])  # battery
        if command == CMD_NETWORK_STANDBY and not data:
            return True, b"\x01"
        if command == CMD_ON_TIMER and len(data) > 1:
            return False, b"\x01"  # NAK
        if command in (0x0E, 0x10, 0x0B, 0x67):
            return True, b"X"
        return True, b"\x00" if command == CMD_ON_TIMER else b""

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

        await service.power.tick(_at("2026-10-27T22:01"))
        assert (CMD_NETWORK_STANDBY, b"\x00") not in panel.received
        assert (CMD_POWER, b"\x00") in panel.received  # light sleep
        assert not service.power.deep_asleep(_at("2026-10-27T23:00"))
        assert service.status.status.alarm_refused
        assert service.power.state.timer is None

        service.player.save_settings(FrameSettings(power_mode="economy"))
        assert not service.power.economy
        assert not await service.power.enter_deep(_at("2026-10-28T12:00"))
        assert (CMD_NETWORK_STANDBY, b"\x00") not in panel.received
    finally:
        await panel.stop()
