"""Panel status: battery, charging, reachability; cached and refreshed gently."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from .device import MdcError

if TYPE_CHECKING:
    from .service import Panel

log = logging.getLogger(__name__)


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
    firmware: str | None = None
    model: str | None = None
    serial: str | None = None
    name: str | None = None
    error: str | None = None
    last_push_at: str | None = None
    last_fetch_at: str | None = None


class StatusMonitor:
    def __init__(self, panel: Panel) -> None:
        self.panel = panel
        self.status = DeviceStatus(configured=self._configured())
        self._static_known = False

    def _configured(self) -> bool:
        s = self.panel.settings
        return bool(s.device_host and s.device_pin)

    @property
    def on_battery(self) -> bool:
        return self.status.power_source == "battery"

    async def refresh(self) -> DeviceStatus:
        status = self.status.model_copy(update={"configured": self._configured()})
        if not status.configured:
            self.status = status
            return status
        status.checked_at = _now()
        try:
            async with self.panel.session() as mdc:
                battery = await mdc.battery()
                status.battery_level = battery.level
                status.battery_raw = battery.raw.hex(" ")
                status.charging = battery.raw[1] == 0x01 if len(battery.raw) > 1 else None
                plugged = battery.external_power
                if plugged is None:
                    plugged = status.charging
                if plugged is not None:
                    status.power_source = "ac" if plugged else "battery"
                status.network_standby = await mdc.network_standby()
                if not self._static_known:
                    status.firmware = await mdc.software_version()
                    status.model = await mdc.model_name()
                    status.serial = await mdc.serial_number()
                    status.name = await mdc.device_name()
                    self._static_known = True
            status.reachable = True
            status.last_seen = status.checked_at
            status.error = None
        except MdcError as err:
            status.reachable = False
            status.error = str(err)
            log.info("panel status check failed: %s", err)
        self.status = status
        return status

    def note_push(self, fetched: bool) -> None:
        stamp = _now()
        self.status.last_push_at = stamp
        if fetched:
            self.status.last_fetch_at = stamp
            self.status.reachable = True
            self.status.last_seen = stamp
