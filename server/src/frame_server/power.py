"""Power policy for a panel on battery (docs/WAKE.md).

By day the panel sleeps with network standby on, so Wake-on-LAN (2.4 GHz
Wi-Fi) wakes it for a picture sent from the app. In quiet hours it sleeps
with the Wi-Fi off, and its own alarm (MDC on-timer) wakes it when they end.
Whatever could not reach the panel waits as a pending push and goes out as
soon as the panel shows up again: after the alarm or a press of its button.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel

from .device import MdcError
from .device.mdc import ON_TIMER_REPEAT
from .schedule import FrameSettings, in_quiet_hours, quiet_hours

if TYPE_CHECKING:
    from .service import FrameService

log = logging.getLogger(__name__)

POWER_KEY = "power"
# After the alarm: how long to keep looking for the panel, and how often.
WAKE_WINDOW = timedelta(minutes=15)
PROBE_IN_WINDOW = timedelta(seconds=15)
# A picture is waiting outside that window: the button may wake the panel.
PROBE_PENDING = timedelta(minutes=2)
RETRY_ARM = timedelta(minutes=10)


class PowerState(BaseModel):
    pending_push: bool = False  # content changed while the panel was unreachable
    night_of: str | None = None  # quiet hours (by start date) the deep sleep was entered for
    woke_on: str | None = None  # date the panel was found after the alarm
    timer: str | None = None  # HH:MM the panel's alarm is armed for, None: off


def night_key(moment: datetime, settings: FrameSettings) -> str:
    """The start date of the quiet hours ``moment`` falls in (22:00-07:00
    at 03:00 belongs to the evening before)."""
    local = moment.astimezone(settings.tz())
    hours = quiet_hours(settings)
    day = local.date()
    if hours and hours[0] > hours[1] and local.time() < hours[1]:
        day -= timedelta(days=1)
    return day.isoformat()


def alarm_time(settings: FrameSettings) -> time | None:
    """The panel wakes itself when quiet hours end."""
    hours = quiet_hours(settings)
    return hours[1] if hours else None


class PowerManager:
    def __init__(self, service: FrameService) -> None:
        self.service = service
        self._last_probe: datetime | None = None
        self._last_arm: datetime | None = None

    # -- persisted state ------------------------------------------------------

    @property
    def state(self) -> PowerState:
        return PowerState.model_validate(self.service.library.get_state(POWER_KEY, {}))

    def _save(self, state: PowerState) -> None:
        self.service.library.set_state(POWER_KEY, state.model_dump(mode="json"))
        self.service.status.status.pending_push = state.pending_push
        self.service.status.status.wakes_at = state.timer

    def mark_pending(self, pending: bool) -> None:
        state = self.state
        if state.pending_push != pending:
            state.pending_push = pending
            self._save(state)

    def deep_asleep(self, now: datetime) -> bool:
        """In quiet hours on battery the Wi-Fi is off: nothing reaches the panel."""
        settings = self.service.player.settings
        return (
            self.service.status.on_battery
            and in_quiet_hours(now, settings)
            and self.state.night_of == night_key(now, settings)
        )

    # -- panel ---------------------------------------------------------------

    async def arm(self, settings: FrameSettings) -> None:
        """Set the panel's alarm to the end of quiet hours (or turn it off)."""
        wake = alarm_time(settings)
        want = wake.strftime("%H:%M") if wake else None
        async with self.service.panel.session() as mdc:
            if wake:
                await mdc.set_on_timer(wake.hour, wake.minute, ON_TIMER_REPEAT["daily"])
            else:
                await mdc.set_on_timer(0, 0, ON_TIMER_REPEAT["daily"], enabled=False)
        state = self.state
        state.timer = want
        self._save(state)
        log.info("panel alarm %s", want or "off")

    async def enter_night(self, now: datetime, settings: FrameSettings) -> None:
        """Alarm at the end of quiet hours, Wi-Fi off, panel off."""
        state = self.state
        state.night_of = night_key(now, settings)  # one attempt per night
        self._save(state)
        wake = alarm_time(settings)
        if wake is None:
            return
        try:
            async with self.service.panel.waking_session() as mdc:
                await mdc.set_on_timer(wake.hour, wake.minute, ON_TIMER_REPEAT["daily"])
                await mdc.set_network_standby(False)
                await mdc.set_power(False)
        except MdcError as err:
            log.warning("could not put the panel into deep sleep: %s", err)
            return
        state = self.state
        state.timer = wake.strftime("%H:%M")
        self._save(state)
        log.info("panel in deep sleep until %s", state.timer)

    async def rendezvous(self, now: datetime) -> bool:
        """Catch the panel while it is awake: Wi-Fi back on for Wake-on-LAN,
        then whatever waited for it."""
        self._last_probe = now
        status = await self.service.status.refresh()
        if not status.reachable:
            return False
        state = self.state
        state.woke_on = now.astimezone(self.service.player.settings.tz()).date().isoformat()
        self._save(state)
        try:
            async with self.service.panel.session() as mdc:
                await mdc.set_network_standby(True)
        except MdcError as err:
            log.warning("could not turn network standby back on: %s", err)
        if state.pending_push:
            outcome = await self.service.push_current(wait=120)
            if outcome.fetched:
                # It waited for the panel: let it stay until the next change.
                self.service.player.postpone()
        return True

    async def tick(self, now: datetime | None = None) -> None:
        service = self.service
        if not service.device_configured:
            return
        now = now or datetime.now(UTC)
        settings = service.player.settings
        state = self.state
        if in_quiet_hours(now, settings):
            if service.status.on_battery and state.night_of != night_key(now, settings):
                await self.enter_night(now, settings)
            return

        wake = alarm_time(settings)
        want = wake.strftime("%H:%M") if wake else None
        if state.timer != want and self._due(self._last_arm, now, RETRY_ARM):
            self._last_arm = now
            try:
                await self.arm(settings)
            except MdcError as err:
                log.info("could not set the panel alarm: %s", err)

        today = now.astimezone(settings.tz()).date()
        if self._in_wake_window(now, settings, today) and state.woke_on != today.isoformat():
            if self._due(self._last_probe, now, PROBE_IN_WINDOW):
                await self.rendezvous(now)
        elif state.pending_push and self._due(self._last_probe, now, PROBE_PENDING):
            await self.rendezvous(now)

    def _in_wake_window(self, now: datetime, settings: FrameSettings, today: date) -> bool:
        wake = alarm_time(settings)
        if wake is None:
            return False
        start = datetime.combine(today, wake, tzinfo=settings.tz())
        return start - timedelta(minutes=1) <= now < start + WAKE_WINDOW

    @staticmethod
    def _due(last: datetime | None, now: datetime, every: timedelta) -> bool:
        return last is None or now - last >= every

    async def run(self, period: float = 5.0) -> None:
        self.service.status.status.pending_push = self.state.pending_push
        self.service.status.status.wakes_at = self.state.timer
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("power tick failed")
            await asyncio.sleep(period)
