"""Panel status: battery, charging, reachability; cached and refreshed gently."""

from __future__ import annotations

import ipaddress
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from .device import MdcConnectionError, MdcError
from .device.presence import connect_says_gone, on_network

if TYPE_CHECKING:
    from .device import MdcClient
    from .library import Library
    from .service import Panel

log = logging.getLogger(__name__)


# What the panel is doing, as far as the server can tell: answering MDC
# (online), asleep with network standby on so Wake-on-LAN can reach it
# (standby), asleep with the Wi-Fi off until its alarm or button
# (deep_sleep), or not answering for no known reason (offline).
PanelPower = Literal["online", "standby", "deep_sleep", "offline"]

# Put to sleep over MDC, the panel still answers for a while (about two
# minutes in node-samsung-emdx), and a session then may keep it awake: status
# checks leave it alone for that long and report the sleep it is going into.
SLEEP_SETTLE = timedelta(minutes=3)

# What was last read from the panel, kept across server restarts: a panel
# asleep since then is still known to sleep with network standby on.
STATUS_KEY = "device_status"
REMEMBERED = {
    "last_seen",
    "battery_level",
    "battery_raw",
    "charging",
    "power_source",
    "network_standby",
    "firmware",
    "model",
    "serial",
    "name",
    "last_push_at",
    "last_fetch_at",
    "wifi",
    "battery_per_day",
    "battery_days",
}

# How fast the battery runs down, measured rather than guessed: a reading at
# most every half hour while on battery, over the last three days; a rate
# once they span half a day and the level fell by a few points. Network
# standby (the online mode) and deep sleep (economy) differ a lot.
BATTERY_LOG_KEY = "battery_log"
BATTERY_SAMPLE_EVERY = timedelta(minutes=30)
BATTERY_WINDOW = timedelta(days=3)
BATTERY_MIN_SPAN = timedelta(hours=12)
BATTERY_MIN_DROP = 3


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class DeviceStatus(BaseModel):
    configured: bool = False
    reachable: bool | None = None
    checked_at: str | None = None
    last_seen: str | None = None
    battery_level: int | None = None
    # Interpretation of the status bytes follows ha-emdx (verified on an
    # EM32DX); still to be confirmed on this unit, see experiment E1.
    charging: bool | None = None
    power_source: Literal["ac", "battery"] | None = None
    battery_raw: str | None = None
    # Measured on battery (see ``BATTERY_LOG_KEY``): percent a day, and the
    # days left at that rate. None on the charger or until measured.
    battery_per_day: float | None = None
    battery_days: float | None = None
    network_standby: bool | None = None
    power_state: PanelPower | None = None
    # Not answering MDC, but on the Wi-Fi (answers ARP): asleep, not gone.
    # None: not asked, or cannot be told (panel behind a router).
    on_network: bool | None = None
    firmware: str | None = None
    model: str | None = None
    serial: str | None = None
    name: str | None = None
    error: str | None = None
    last_push_at: str | None = None
    last_fetch_at: str | None = None
    # A picture waits for the panel to wake (alarm or button), see power.py.
    pending_push: bool = False
    wakes_at: str | None = None  # HH:MM of the app's alarm
    wake_at: str | None = None  # the same alarm in full, for a countdown
    # The panel runs the frame's app (Samsung "Custom" source, panel_app.py):
    # it wakes and sleeps by itself and asks the server for its pictures.
    # False: not (yet) seen asking; the server is starting it over MDC.
    panel_app: bool = False
    # Its Wi-Fi, read by the frame's app.
    wifi: PanelWifi | None = None
    # The Samsung certificates the app is signed with expire soon (ISO).
    certificates_expire_at: str | None = None
    # The power mode set in the app while the frame sleeps: it takes it on at
    # its next wake ("online" or "economy"); None when nothing waits.
    mode_pending: str | None = None
    # "Głęboki sen" chosen in the app until this moment (ISO), or the frame
    # switched off from the app: no alarm, only the button wakes it.
    rest_until: str | None = None
    switched_off: bool = False
    # Asleep without the Wi-Fi by itself (unplugged, it sleeps at once and
    # leaves the Wi-Fi, E8): Wake-on-LAN cannot reach it, the button wakes it.
    wifi_lost: bool = False
    # The panel answers MDC, yet the frame's app has not been heard from
    # since then (ISO): it does not run or hangs, and no picture gets through
    # (2026-10-30: "Połączona" while the app had been frozen for 51 min).
    app_silent_since: str | None = None


class PanelWifi(BaseModel):
    """The panel's Wi-Fi as the Frame app last read it: ``webapis.network``
    (privilege network.public, package 1.2.0+) or ``tizen.systeminfo``."""

    read_at: str
    signal: float | None = None  # 0-1
    level: int | None = None  # 0-5 bars (webapis.network)
    ssid: str | None = None
    ip: str | None = None
    frequency: int | None = None  # MHz: 24xx is 2.4 GHz
    # Where the server looks for the panel (its MDC address), and the SSID
    # the panel was last on at that address.
    expected_ip: str | None = None
    home_ssid: str | None = None
    # On another network: the server reaches it neither over MDC nor with
    # Wake-on-LAN. After a power cut it once joined a neighbouring SSID (E16).
    wrong_network: bool = False


WIFI_LEVELS = 5


def wifi_reading(
    data: dict[str, object], host: str | None, before: PanelWifi | None, now: datetime
) -> PanelWifi | None:
    """What the app reported; None when it could read nothing."""

    def text(key: str) -> str | None:
        value = data.get(key)
        return value.strip() or None if isinstance(value, str) else None

    def number(key: str) -> float | None:
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            return None
        try:
            return float(value)
        except ValueError:
            return None

    level = number("level")
    signal = number("signal")
    if signal is None and level is not None:
        signal = level / WIFI_LEVELS
    ssid, ip = text("ssid"), text("ip")
    if signal is None and ssid is None and ip is None:
        return None
    frequency = number("frequency")
    try:
        expected = str(ipaddress.ip_address(host)) if host else None
    except ValueError:  # a host name: the address cannot be compared
        expected = None
    home = before.home_ssid if before else None
    at_home = expected is not None and ip == expected
    if at_home and ssid:
        home = ssid
    wrong = (expected is not None and ip is not None and ip != expected) or (
        ssid is not None and home is not None and ssid != home
    )
    return PanelWifi(
        read_at=now.isoformat(timespec="seconds"),
        signal=None if signal is None else min(1.0, max(0.0, signal)),
        level=None if level is None else int(level),
        ssid=ssid,
        ip=ip,
        frequency=None if frequency is None else int(frequency),
        expected_ip=expected,
        home_ssid=home,
        wrong_network=wrong,
    )


def _readable(text: str) -> str | None:
    """The EM32DX answers the model query with a code (``02 7a 01``), not
    a name: keep only text worth showing."""
    text = text.strip()
    return text if len(text) >= 2 and text.isprintable() else None


class StatusMonitor:
    def __init__(self, panel: Panel, library: Library | None = None) -> None:
        self.panel = panel
        self.library = library
        saved = library.get_state(STATUS_KEY, {}) if library else {}
        known = {k: v for k, v in saved.items() if k in REMEMBERED}
        self.status = DeviceStatus.model_validate({**known, "configured": self._configured()})
        self._static_known = False
        self._slept_at: datetime | None = None  # the server last put it to sleep
        # Which sleep a panel that does not answer is in (see PowerManager).
        self.asleep: Callable[[DeviceStatus], PanelPower] | None = None
        # Told when a panel that does not answer is not on the Wi-Fi either,
        # and when it answers (its app may not be running).
        self.off_network: Callable[[], None] | None = None
        self.answered: Callable[[], Awaitable[None]] | None = None

    def _configured(self) -> bool:
        s = self.panel.settings
        return bool(s.device_host and s.device_pin)

    def forget(self) -> None:
        """Another panel (or address): nothing known about it yet, but what
        was sent and what waits for a wake stays."""
        keep = self.status.model_dump(
            include={"last_push_at", "last_fetch_at", "pending_push", "wakes_at"}
        )
        self.status = DeviceStatus(configured=self._configured(), **keep)
        self._static_known = False
        self._slept_at = None
        self._remember()

    def _remember(self) -> None:
        if self.library is not None:
            self.library.set_state(STATUS_KEY, self.status.model_dump(include=REMEMBERED))

    @property
    def on_battery(self) -> bool:
        return self.status.power_source == "battery"

    @property
    def sleeping(self) -> bool:
        return self.status.power_state in ("standby", "deep_sleep")

    def settling(self, now: datetime | None = None) -> bool:
        """Just put to sleep: it may still answer, but is on its way down."""
        if self._slept_at is None:
            return False
        return timedelta(0) <= (now or datetime.now(UTC)) - self._slept_at < SLEEP_SETTLE

    async def refresh(self, force: bool = False) -> DeviceStatus:
        """Ask the panel. Without ``force`` a panel the server has just put
        to sleep is not asked (see ``SLEEP_SETTLE``); waking it forces."""
        status = self.status.model_copy(update={"configured": self._configured()})
        if not status.configured or (not force and self.settling()):
            self.status = status
            return status
        status.checked_at = _now()
        try:
            async with self.panel.session() as mdc:
                await self._read_battery(mdc, status)
                status.network_standby = await mdc.network_standby()
                if not self._static_known:
                    status.firmware = await mdc.software_version()
                    status.model = _readable(await mdc.model_name())
                    status.serial = await mdc.serial_number()
                    status.name = await mdc.device_name()
                    self._static_known = True
            status.reachable = True
            status.last_seen = status.checked_at
            status.error = None
            self._track_battery(status, datetime.now(UTC))
            status.power_state = "online"
            status.on_network = True
            self._slept_at = None
        except MdcError as err:
            status.reachable = False
            status.error = str(err)
            status.on_network = await self._on_network(err)
            status.power_state = self._sleep_state(status)
            log.info("panel status check failed: %s (on the network: %s)", err, status.on_network)
        self.status = status
        if status.on_network is False and self.off_network:
            self.off_network()  # it publishes what it changed into this status
        self._remember()
        if status.reachable and self.answered:
            await self.answered()
        return status

    async def look_for_panel(self, err: MdcError | None) -> bool | None:
        """Whether a panel that did not answer (``err``) is still on the
        Wi-Fi, asked without waking it."""
        on_network = await self._on_network(err) if err is not None else None
        self.status.on_network = on_network
        return on_network

    async def _on_network(self, err: MdcError) -> bool | None:
        """Asleep on the Wi-Fi or gone? Asked without waking the panel."""
        if not isinstance(err, MdcConnectionError):
            return None  # it answered, and something else went wrong
        host = self.panel.settings.device_host
        if not host:
            return None
        if connect_says_gone(err.__cause__):
            return False
        return await on_network(host)

    def _sleep_state(self, status: DeviceStatus) -> PanelPower:
        """A panel that does not answer MDC: what it is most likely doing."""
        guess = self.asleep(status) if self.asleep else "offline"
        if status.on_network is True and guess != "deep_sleep":
            return "standby"  # still on the Wi-Fi: Wake-on-LAN reaches it
        # Known to sleep deeply, an ARP answer does not change that: unplugged,
        # the panel showed up on the Wi-Fi again ("Ch. 0" in UniFi) and still
        # no magic packet woke it (2026-10-29).
        if status.on_network is False and guess == "standby":
            # No ARP answer: not on the Wi-Fi, whatever network standby says
            # (unplugged, the panel sleeps at once and leaves it, E8 and
            # 2026-10-29). Wake-on-LAN cannot reach it, the button can.
            return "deep_sleep"
        return guess

    @staticmethod
    async def _read_battery(mdc: MdcClient, status: DeviceStatus) -> None:
        battery = await mdc.battery()
        status.battery_level = battery.level
        status.battery_raw = battery.raw.hex(" ")
        status.charging = battery.raw[1] == 0x01 if len(battery.raw) > 1 else None
        plugged = battery.external_power
        if plugged is None:
            plugged = status.charging
        if plugged is not None:
            status.power_source = "ac" if plugged else "battery"

    async def read_battery(self, mdc: MdcClient) -> None:
        """Battery and charger within a session opened for something else."""
        await self._read_battery(mdc, self.status)

    def note_push(self, fetched: bool) -> None:
        stamp = _now()
        self.status.last_push_at = stamp
        if fetched:
            self.status.last_fetch_at = stamp
            self.status.reachable = True
            self.status.last_seen = stamp
            self.status.power_state = "online"
            self._slept_at = None
        self._remember()

    def note_app(self, now: datetime, battery: int | None, charging: bool | None) -> None:
        """The Frame app asked for its picture: the panel is awake, and the
        app may know its battery better than the last MDC read."""
        stamp = now.isoformat(timespec="seconds")
        status = self.status
        status.reachable = True
        status.last_seen = stamp
        status.power_state = "online"
        status.on_network = True
        status.error = None
        if battery is not None:
            status.battery_level = battery
        if charging is not None:
            status.charging = charging
            status.power_source = "ac" if charging else "battery"
        self._track_battery(status, now)
        self._slept_at = None
        self._remember()

    def _track_battery(self, status: DeviceStatus, now: datetime) -> None:
        """Note the level on battery and work out how fast it falls."""
        level = status.battery_level
        if self.library is None or level is None:
            return
        if status.power_source != "battery" or status.charging:
            status.battery_per_day = status.battery_days = None
            if self.library.get_state(BATTERY_LOG_KEY):
                self.library.set_state(BATTERY_LOG_KEY, [])
            return
        samples = [
            (datetime.fromisoformat(at), int(was))
            for at, was in self.library.get_state(BATTERY_LOG_KEY, [])
        ]
        if samples and level > samples[-1][1] + 2:
            samples = []  # charged in between
        if not samples or now - samples[-1][0] >= BATTERY_SAMPLE_EVERY:
            samples.append((now, level))
        samples = [s for s in samples if now - s[0] <= BATTERY_WINDOW] or samples[-1:]
        self.library.set_state(
            BATTERY_LOG_KEY, [[at.isoformat(timespec="seconds"), was] for at, was in samples]
        )
        first_at, first = samples[0]
        span, drop = now - first_at, first - level
        if span < BATTERY_MIN_SPAN or drop < BATTERY_MIN_DROP:
            status.battery_per_day = status.battery_days = None
            return
        per_day = drop / (span / timedelta(days=1))
        status.battery_per_day = round(per_day, 1)
        status.battery_days = round(level / per_day, 1)

    def note_wifi(self, data: dict[str, object], now: datetime | None = None) -> None:
        """The Frame app read the panel's Wi-Fi."""
        before = self.status.wifi
        wifi = wifi_reading(data, self.panel.settings.device_host, before, now or datetime.now(UTC))
        if wifi is None:
            return
        if wifi.wrong_network and not (before and before.wrong_network):
            log.warning(
                "the panel is on another network: %s at %s (expected %s at %s)",
                wifi.ssid,
                wifi.ip,
                wifi.home_ssid,
                wifi.expected_ip,
            )
        self.status.wifi = wifi
        self._remember()

    def forget_wifi(self) -> None:
        """The panel left the app: nothing reads the Wi-Fi until it is back."""
        if self.status.wifi is not None:
            self.status.wifi = None
            self._remember()

    def note_fell_asleep(self, on_network: bool | None, *, unplugged: bool, wifi: bool) -> None:
        """The app fell silent and the panel does not answer: asleep by
        itself, in the network (``wifi``) or without it. ``unplugged``: the
        last reading said charger, and on the charger the app never sleeps,
        so it was unplugged. Not "ładuje się" until it answers again."""
        status = self.status
        if unplugged:
            status.power_source = "battery"
            status.charging = False
        status.reachable = False
        status.on_network = on_network
        status.power_state = "standby" if wifi else "deep_sleep"
        self._remember()

    def note_sleep(self, deep: bool) -> None:
        """The server put the panel to sleep: light (network standby on) or deep."""
        self.status.network_standby = not deep
        self.status.on_network = None
        self.status.power_state = "deep_sleep" if deep else "standby"
        self._slept_at = datetime.now(UTC)
        self._remember()
