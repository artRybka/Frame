"""Panel status: battery, charging, reachability; cached and refreshed gently."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from .device import MdcError

if TYPE_CHECKING:
    from .device import MdcClient
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


def _readable(text: str) -> str | None:
    """The EM32DX answers the model query with a code (``02 7a 01``), not
    a name: keep only text worth showing."""
    text = text.strip()
    return text if len(text) >= 2 and text.isprintable() else None


class StatusMonitor:
    def __init__(self, panel: Panel) -> None:
        self.panel = panel
        self.status = DeviceStatus(configured=self._configured())
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
            self._slept_at = None
        except MdcError as err:
            status.reachable = False
            status.error = str(err)
            status.power_state = self.asleep(status) if self.asleep else "offline"
            log.info("panel status check failed: %s", err)
        self.status = status
        return status

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

    def note_sleep(self, deep: bool) -> None:
        """The server put the panel to sleep: light (network standby on) or deep."""
        self.status.network_standby = not deep
        self.status.power_state = "deep_sleep" if deep else "standby"
        self._slept_at = datetime.now(UTC)
