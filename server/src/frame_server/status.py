"""Panel status: battery, charging, reachability; cached and refreshed gently."""

from __future__ import annotations

import logging
from collections.abc import Callable
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
}


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
    wakes_at: str | None = None  # HH:MM of the panel's own alarm
    # The panel refused its alarm (MDC 0x25): no deep sleep, so neither the
    # economy mode nor the night's deep sleep can work.
    alarm_refused: bool = False


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
        self._remember()
        return status

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
        if status.on_network is True:
            return "standby"  # still on the Wi-Fi: Wake-on-LAN reaches it
        # No ARP answer is not taken as gone until the EM32DX is known to
        # answer ARP in its sleep (E15): the guess stands.
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

    def note_sleep(self, deep: bool) -> None:
        """The server put the panel to sleep: light (network standby on) or deep."""
        self.status.network_standby = not deep
        self.status.on_network = None
        self.status.power_state = "deep_sleep" if deep else "standby"
        self._slept_at = datetime.now(UTC)
        self._remember()
