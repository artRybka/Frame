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

from frame_server import panel_app as panel_app_module
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
    answer = service.app.answer(BATTERY, now=datetime.now(UTC) - timedelta(minutes=10))
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


async def test_a_silent_app_is_not_taken_for_awake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2026-10-29: unplugged, the panel fell asleep while the app was told to
    stay up on the charger. "Obudź ramkę" said "obudziła się" without a
    single magic packet, and the next picture waited for a wake that never
    came. Silent, the app is woken like a sleeping one."""
    monkeypatch.setattr(power, "WAKE_LOOK", timedelta(seconds=2))
    service = FrameService(_settings(tmp_path, _closed_port()))
    app = service.app
    now = datetime.now(UTC)
    app.answer(AppHello(charging=True), now=now - timedelta(minutes=5))
    assert not app.asleep() and not app.awake(now)

    sent: list[int] = []

    async def wake(seconds: int = 0) -> bool:
        sent.append(seconds)
        return True

    monkeypatch.setattr(service.panel, "wake", wake)
    task = asyncio.create_task(service.power.wake_now())
    await asyncio.sleep(0.3)
    app.answer(AppHello(reason="resume", charging=False))
    result = await task
    assert result.sent and result.woke and sent == [power.WAKE_BURST_SECONDS]
    assert app.awake()


@pytest.mark.parametrize(
    ("unplugged", "on_network", "power_state"),
    [
        # Unplugged, Wake-on-LAN does not wake it, on the Wi-Fi or not: in
        # UniFi it came back on "Ch. 0" and no magic packet woke it.
        (True, True, "deep_sleep"),
        (True, False, "deep_sleep"),
        (True, None, "deep_sleep"),
        # Asleep by itself on battery: the Wi-Fi decides.
        (False, True, "standby"),
        (False, False, "deep_sleep"),
        (False, None, "standby"),
    ],
)
async def test_a_panel_asleep_by_itself(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unplugged: bool,
    on_network: bool | None,
    power_state: str,
) -> None:
    """Silent and not answering MDC: asleep by itself, not a hung app.
    2026-10-29: unplugged, the panel slept and no Wake-on-LAN woke it, yet
    the app said "Czuwanie, wysyłka ją budzi" and "Sprawdź stan" said it is
    not on the Wi-Fi."""

    async def presence(host: str) -> bool | None:
        return on_network

    monkeypatch.setattr(status_module, "on_network", presence)
    service = FrameService(_settings(tmp_path, _closed_port()))
    app = service.app
    now = _at("2026-10-29T10:00")
    service.status.status.power_source = "ac" if unplugged else "battery"
    service.status.status.charging = unplugged
    if not unplugged:
        app.keep_awake(now)  # "Obudź ramkę": awake on battery
    assert app.answer(AppHello(charging=unplugged), now=now).action == "stay"
    await service.power.tick(now + timedelta(minutes=2))
    assert not app.asleep()
    await service.power.tick(now + timedelta(minutes=4))
    # The spare alarms the app keeps on the charger (online mode) wake it.
    spare = _at("2026-10-29T10:30") if unplugged else None
    assert app.asleep() and app.wakes_at(now + timedelta(minutes=4)) == spare
    wifi = power_state == "standby"
    assert app.deep_asleep() is not wifi and app.state.wifi_lost is not wifi
    status = service.status.status
    assert status.power_source == "battery" and not status.charging
    assert status.power_state == power_state and status.wifi_lost is not wifi
    assert (await service.status.refresh(force=True)).power_state == power_state
    # Nothing more to start until it is heard of again.
    await service.power.tick(now + timedelta(minutes=30))
    assert app.asleep() and app.state.missed_wake is None
    if not wifi:
        # No magic packets for a panel off the Wi-Fi: the button wakes it.
        result = await service.power.wake_now()
        assert not result.sent and result.deep_sleep and result.wifi_lost
    # Heard of again (the button): it sleeps as it is told to again.
    answer = app.answer(AppHello(reason="start", charging=False), now=now + timedelta(hours=1))
    assert answer.action == "sleep" and answer.standby == "ON"
    assert not app.deep_asleep() and not app.state.wifi_lost
    assert not service.status.status.wifi_lost


async def test_a_sleep_in_the_network_found_off_the_wifi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asleep with network standby on, but a look finds it off the Wi-Fi
    (no ARP answer): the tiles, "Sprawdź stan" and "Obudź ramkę" all say
    the button, none of them "wysyłka ją budzi"."""

    async def presence(host: str) -> bool | None:
        return False

    monkeypatch.setattr(status_module, "on_network", presence)
    service = FrameService(_settings(tmp_path, _closed_port()))
    _asleep(service, deep=False)
    status = await service.status.refresh(force=True)
    assert status.power_state == "deep_sleep" and status.on_network is False
    assert status.wifi_lost and status.wake_at is not None  # its alarm still rings
    assert service.app.deep_asleep()
    result = await service.power.wake_now()
    assert not result.sent and result.deep_sleep and result.wifi_lost


async def test_no_magic_packets_while_the_panel_goes_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2026-11-01: a picture sent right after "Sprawdź stan" put the app to
    sleep. Magic packets sent while the panel was still going down woke it
    seconds after it went down, too soon for the app to notice, and it never
    asked again. The packets wait until the panel is down for sure."""
    # Noted to the second: down 1.5 to 2.5 s after the answer.
    monkeypatch.setattr(panel_app_module, "GOING_DOWN", timedelta(seconds=2.5))
    monkeypatch.setattr(power, "WAKE_LOOK", timedelta(seconds=0.3))
    monkeypatch.setattr(power, "WAKE_AFTER_DOWN", timedelta(seconds=1))
    service = FrameService(_settings(tmp_path, _closed_port()))
    app = service.app
    sent: list[int] = []

    async def wake(seconds: int = 0) -> bool:
        sent.append(seconds)
        return True

    monkeypatch.setattr(service.panel, "wake", wake)
    _asleep(service, deep=False)

    # Told to sleep just now: no packets yet; the look outlasts the wait.
    assert app.answer(BATTERY).action == "sleep"
    task = asyncio.create_task(service.power.wake_now(sleep_after=True))
    await asyncio.sleep(0.4)
    assert sent == [] and not task.done()
    for _ in range(30):
        await asyncio.sleep(0.1)
        if sent:
            break
    assert sent == [power.WAKE_BURST_SECONDS] and not task.done()
    app.answer(BATTERY)
    result = await task
    assert result.sent and result.woke

    # It asks while going down (the launcher restarted it): no packets at all.
    sent.clear()
    app.awake_until = None  # the look's window is over
    assert app.answer(BATTERY).action == "sleep"
    task = asyncio.create_task(service.power.wake_now(sleep_after=True))
    await asyncio.sleep(0.2)
    app.answer(BATTERY)
    result = await task
    assert result.woke and sent == []


async def test_a_status_check_keeps_the_frame_up_for_a_picture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2026-11-01: a picture sent right after "Sprawdź stan" had to wait for
    the panel to go down and be woken again. The look keeps it up a while."""
    monkeypatch.setattr(power, "WAKE_LOOK", timedelta(seconds=2))
    service = FrameService(_settings(tmp_path, _closed_port()))
    app = service.app

    async def wake(seconds: int = 0) -> bool:
        return True

    monkeypatch.setattr(service.panel, "wake", wake)
    _asleep(service, deep=False)
    task = asyncio.create_task(service.power.wake_now(sleep_after=True))
    await asyncio.sleep(0.3)
    now = datetime.now(UTC)
    answer = app.answer(BATTERY, now=now)
    assert answer.action == "stay" and answer.wait_s == 10
    assert (await task).woke
    assert app.answer(BATTERY, now=now + timedelta(seconds=90)).action == "stay"
    assert app.answer(BATTERY, now=now + timedelta(minutes=3)).action == "sleep"

    # No answer: no window for a question later on.
    app.answer(BATTERY, now=datetime.now(UTC) - timedelta(minutes=10))
    result = await service.power.wake_now(sleep_after=True)
    assert result.sent and not result.woke
    assert app.answer(BATTERY).action == "sleep"


async def test_wake_starts_a_hung_app(
    tmp_path: Path, server_ssl: ssl.SSLContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Up (it answers MDC) but its app does not ask: started over MDC."""
    monkeypatch.setattr(power, "WAKE_LOOK", timedelta(seconds=3))
    monkeypatch.setattr(power, "WAKE_STEP", timedelta(seconds=0.2))
    monkeypatch.setattr(power, "APP_GRACE", timedelta(seconds=0.5))
    panel = FakePanel(server_ssl, handler=_handler)
    await panel.start()
    try:
        service = FrameService(_settings(tmp_path, panel.port))
        service.app.store_package(b"PK\x03\x04signed", "2.0.0")
        _asleep(service, deep=False)
        task = asyncio.create_task(service.power.wake_now())
        for _ in range(40):
            await asyncio.sleep(0.1)
            if (CMD_CONTENT_DOWNLOAD, b"\x81\x01") in panel.received:
                break
        assert panel.received[-1] == (CMD_CONTENT_DOWNLOAD, b"\x81\x01")
        service.app.answer(AppHello(reason="start", build="2.0.0", charging=False))
        result = await task
        assert result.woke and result.started
    finally:
        await panel.stop()


async def test_a_picture_starts_the_app_of_a_panel_up(
    tmp_path: Path, server_ssl: ssl.SSLContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2026-10-29, 0.34.0: woken by the button, the panel was on the Wi-Fi
    and answered MDC, but its app did not run (the launcher seldom starts it
    after a cold boot). A picture sent kept "Budzę ramkę" with magic packets
    for nothing. Now it starts the app over MDC, and a status look that
    finds the panel up does too."""
    monkeypatch.setattr(power, "WAKE_LOOK", timedelta(seconds=3))
    monkeypatch.setattr(power, "WAKE_STEP", timedelta(seconds=0.2))
    monkeypatch.setattr(power, "APP_GRACE", timedelta(seconds=0.5))
    panel = FakePanel(server_ssl, handler=_handler)
    await panel.start()
    try:
        service = FrameService(_settings(tmp_path, panel.port))
        app = service.app
        app.store_package(b"PK\x03\x04signed", "2.0.0")
        service.ensure_initial_content()
        _asleep(service, deep=False)
        sent: list[int] = []

        async def wake(seconds: int = 0) -> bool:
            sent.append(seconds)
            return True

        monkeypatch.setattr(service.panel, "wake", wake)
        task = asyncio.create_task(service.push_current(wait=5))
        for _ in range(40):
            await asyncio.sleep(0.1)
            if (CMD_CONTENT_DOWNLOAD, b"\x81\x01") in panel.received:
                break
        assert panel.received[-1] == (CMD_CONTENT_DOWNLOAD, b"\x81\x01")
        # Started, the app asks and downloads the picture.
        app.answer(AppHello(reason="start", build="2.0.0", charging=False))
        content = service.store.current()
        assert content is not None
        service.store._fetch_waiters[content.file_id].set()
        outcome = await task
        assert outcome.fetched and not service.power.state.pending_push

        # Asleep again a while later, the panel answers a status look: the
        # app is started.
        _asleep(service, deep=False)
        state = app.state
        state.slept_at = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
        state.wakes, state.wake_at = [], None
        app._save(state)
        app.heard_at = datetime.now(UTC) - timedelta(minutes=10)
        app._kicked = None
        panel.received.clear()
        await service.status.refresh(force=True)
        assert panel.received[-1] == (CMD_CONTENT_DOWNLOAD, b"\x81\x01")
        # Not while it asks: the battery read before its answer leaves it be.
        panel.received.clear()
        app._kicked = None
        service.status.status.checked_at = None  # the battery is read first
        await app.ask(AppHello(reason="resume", build="2.0.0"))
        assert panel.received  # read it was
        assert (CMD_CONTENT_DOWNLOAD, b"\x81\x01") not in panel.received
    finally:
        await panel.stop()


async def test_restart_from_the_app(
    tmp_path: Path, server_ssl: ssl.SSLContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "Uruchom ponownie": the app reboots the panel at its next question,
    and the server starts it after the boot."""
    monkeypatch.setattr(power, "WAKE_LOOK", timedelta(seconds=2))
    panel = FakePanel(server_ssl, handler=_handler)
    await panel.start()
    try:
        service = FrameService(_settings(tmp_path, panel.port))
        app = service.app
        app.store_package(b"PK\x03\x04signed", "2.0.0")
        hello = AppHello(reason="poll", build="2.0.0", charging=True)
        assert app.answer(hello).action == "stay"
        task = asyncio.create_task(service.power.restart_now())
        await asyncio.sleep(0.3)
        assert app.answer(hello).action == "reboot"
        result = await task
        assert result.woke and not result.sent
        assert app.state.reboot_for is None  # not a package's reboot
        assert app.answer(hello).action == "stay"  # once
        # The launcher does not start it after the boot: the server does.
        app.restart_requested = True
        assert app.answer(hello).action == "reboot"
        rebooted = datetime.fromisoformat(app.state.wake_at or "")
        panel.received.clear()
        await service.power.tick(rebooted + timedelta(seconds=30))
        assert panel.received == []
        await service.power.tick(rebooted + timedelta(seconds=70))
        assert panel.received[-1] == (CMD_CONTENT_DOWNLOAD, b"\x81\x01")

        # Nobody asks: not rebooted later out of the blue.
        app.answer(hello)
        app.heard_at = datetime.now(UTC) - timedelta(minutes=5)
        result = await service.power.restart_now()
        assert not result.woke and not app.restart_requested
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
        (True, False, "deep_sleep"),  # no ARP answer: off the Wi-Fi (unplugged, E8)
        (False, True, "deep_sleep"),  # on the Wi-Fi is not wakeable (2026-10-29)
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
    # On the clock from midnight, but not from 22:00 to 07:00.
    assert economy.check_quiet_start == "22:00" and economy.check_quiet_end == "07:00"
    assert check_times(economy) == [time(8, 0), time(12, 0), time(16, 0), time(20, 0)]
    assert quiet_hours(economy) is None  # the panel sleeps deeply anyway
    assert next_check(_at("2026-10-27T20:00"), economy) == _at("2026-10-28T08:00")
    every3 = economy.model_copy(update={"check_every_hours": 3})
    assert check_times(every3) == [time(9, 0), time(12, 0), time(15, 0), time(18, 0), time(21, 0)]
    no_quiet = economy.model_copy(update={"check_quiet_start": None})
    assert check_times(no_quiet) == [time(h, 0) for h in (0, 4, 8, 12, 16, 20)]
    assert next_check(_at("2026-10-27T20:00"), no_quiet) == _at("2026-10-28T00:00")
    # Not at a change time; every hour.
    hourly = economy.model_copy(update={"check_every_hours": 1})
    assert time(7, 0) not in check_times(hourly) and time(19, 0) not in check_times(hourly)
    assert len(check_times(hourly)) == 13  # 8:00 … 21:00 without 19:00
    # The changes do not move the checks.
    close = economy.model_copy(update={"change_times": ["00:50", "03:50"]})
    assert check_times(close) == check_times(economy)
    # Quiet hours inside the day.
    nap = no_quiet.model_copy(update={"check_quiet_start": "11:00", "check_quiet_end": "17:00"})
    assert check_times(nap) == [time(h, 0) for h in (0, 4, 8, 20)]
    assert check_times(economy.model_copy(update={"check_every_hours": 0})) == []
    assert check_times(economy.model_copy(update={"power_mode": "online"})) == []


def test_put_to_sleep_from_the_app(tmp_path: Path) -> None:
    """ "Uśpij ramkę" on the charger: the app sleeps at its next question."""
    service = FrameService(_settings(tmp_path, _closed_port()))
    service.ensure_initial_content()
    # Off on the real clock: just before 22:00 the app would wait for them.
    settings = service.player.settings
    settings.quiet_start = None
    service.player.save_settings(settings)
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
