"""Power policy (docs/WAKE.md). The schedule is the same on the charger and
on battery; only the night differs.

By day the panel sleeps with network standby on, so Wake-on-LAN (2.4 GHz
Wi-Fi) wakes it for a picture sent from the app or for a change. On battery
the server puts it back into that light sleep once a picture has been
downloaded and drawn, instead of leaving it awake on its own timer. In quiet
hours on battery it sleeps with the Wi-Fi off, and its own alarm (MDC
on-timer) wakes it for the morning change that ends them; on the charger
pictures keep going out at once. Whatever could not reach the
panel waits as a pending push and goes out as soon as the panel shows up
again: after the alarm or a press of its button. The same goes for network
standby: the night turns it off, and until the panel is found again (alarm or
button) Wake-on-LAN cannot reach it, so the server keeps looking for it.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel

from .device import MdcError
from .device.mdc import ON_TIMER_REPEAT
from .schedule import FrameSettings, in_quiet_hours, morning_change, quiet_hours

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
# "Obudź ramkę": how long to keep sending magic packets and looking for the panel.
WAKE_BURST_SECONDS = 15
WAKE_LOOK = timedelta(seconds=30)
# After the panel downloaded a picture: ~12 s to prepare it and ~31 s to
# redraw (E2), with a margin, before it is powered off into light sleep.
LIGHT_SLEEP_AFTER = 90.0


class PowerState(BaseModel):
    pending_push: bool = False  # content changed while the panel was unreachable
    night_of: str | None = None  # quiet hours (by start date) the deep sleep was entered for
    woke_on: str | None = None  # date the panel was found after the alarm
    timer: str | None = None  # HH:MM the panel's alarm is armed for, None: off
    # Network standby is off (the night turned it off, or a status check found
    # it off): Wake-on-LAN cannot work until the panel is found and it is back on.
    standby_off: bool = False


class WakeResult(BaseModel):
    sent: bool  # magic packets went out
    woke: bool  # the panel answered MDC afterwards
    asleep_until: str | None = None  # deep sleep: Wake-on-LAN cannot reach it
    reason: str | None = None


def night_key(moment: datetime, settings: FrameSettings) -> str:
    """The start date of the quiet hours ``moment`` falls in (22:00-07:00
    at 03:00 belongs to the evening before)."""
    local = moment.astimezone(settings.tz())
    hours = quiet_hours(settings)
    day = local.date()
    if hours and hours[0] > hours[1] and local.time() < hours[1]:
        day -= timedelta(days=1)
    return day.isoformat()


def alarm_time(settings: FrameSettings) -> time:
    """The panel wakes itself for the morning change, when quiet hours end."""
    return morning_change(settings)


class PowerManager:
    def __init__(self, service: FrameService) -> None:
        self.service = service
        self._last_probe: datetime | None = None
        self._last_arm: datetime | None = None
        self._background: asyncio.Task[bool] | None = None
        self._light_sleep: asyncio.Task[None] | None = None

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
        """Set the panel's alarm to the morning change, every day."""
        wake = alarm_time(settings)
        async with self.service.panel.session() as mdc:
            await mdc.set_on_timer(wake.hour, wake.minute, ON_TIMER_REPEAT["daily"])
        state = self.state
        state.timer = wake.strftime("%H:%M")
        self._save(state)
        log.info("panel alarm %s", state.timer)

    async def enter_night(self, now: datetime, settings: FrameSettings) -> None:
        """Alarm for the morning change, Wi-Fi off, panel off."""
        state = self.state
        state.night_of = night_key(now, settings)  # one attempt per night
        self._save(state)
        wake = alarm_time(settings)
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
        state.standby_off = True
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
        else:
            state = self.state
            state.standby_off = False
            self._save(state)
            self.service.status.status.network_standby = True
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
            # On battery only; a change at the very start of quiet hours
            # goes out first.
            tonight = state.night_of == night_key(now, settings)
            starting = service.player.change_starting(now)
            if service.status.on_battery and not tonight and not starting:
                await self.enter_night(now, settings)
            return

        want = alarm_time(settings).strftime("%H:%M")
        if state.timer != want and self._due(self._last_arm, now, RETRY_ARM):
            self._last_arm = now
            try:
                await self.arm(settings)
            except MdcError as err:
                log.info("could not set the panel alarm: %s", err)

        if service.status.status.reachable and service.status.status.network_standby is False:
            # Found off by a status check (the alarm missed, or the button
            # woke the panel unnoticed): Wake-on-LAN would not reach it.
            state.standby_off = True
            self._save(state)

        today = now.astimezone(settings.tz()).date()
        if self._in_wake_window(now, settings, today) and state.woke_on != today.isoformat():
            if self._due(self._last_probe, now, PROBE_IN_WINDOW):
                await self.rendezvous(now)
        elif (state.pending_push or state.standby_off) and self._due(
            self._last_probe, now, PROBE_PENDING
        ):
            await self.rendezvous(now)

    # -- light sleep after a picture ------------------------------------------

    def cancel_light_sleep(self) -> None:
        """Another picture is on its way: the panel must stay awake for it."""
        if self._light_sleep and not self._light_sleep.done():
            self._light_sleep.cancel()
        self._light_sleep = None

    def after_push(self, fetched: bool) -> None:
        """On battery, back to light sleep once the picture is on the panel.
        At night the deep sleep follows anyway; on the charger it stays on."""
        self.cancel_light_sleep()
        settings = self.service.player.settings
        if not fetched or not self.service.status.on_battery:
            return
        if in_quiet_hours(datetime.now(UTC), settings):
            return
        self._light_sleep = asyncio.create_task(self._sleep_later(LIGHT_SLEEP_AFTER))

    async def _sleep_later(self, delay: float) -> None:
        await asyncio.sleep(delay)
        try:
            await self.service.panel.sleep()
        except MdcError as err:
            log.info("could not put the panel into light sleep: %s", err)
            return
        self.service.status.status.network_standby = True
        log.info("panel in light sleep (network standby on)")

    async def wake_now(self) -> WakeResult:
        """The app's "Obudź ramkę": a burst of magic packets, then look for
        the panel, so the app can say whether it actually woke."""
        service = self.service
        now = datetime.now(UTC)
        if self.deep_asleep(now):
            state = self.state
            return WakeResult(
                sent=False,
                woke=False,
                asleep_until=state.timer,
                reason="deep sleep (Wi-Fi off) until the alarm, only the button wakes it",
            )
        if not service.settings.device_mac:
            return WakeResult(sent=False, woke=False, reason="no MAC address set")
        self.cancel_light_sleep()
        burst = asyncio.create_task(service.panel.wake(seconds=WAKE_BURST_SECONDS))
        woke = False
        loop = asyncio.get_running_loop()
        deadline = loop.time() + WAKE_LOOK.total_seconds()
        try:
            await asyncio.sleep(2)
            while not woke and loop.time() < deadline:
                woke = bool((await service.status.refresh()).reachable)
                if not woke:
                    await asyncio.sleep(3)
        finally:
            burst.cancel()
        standby_off = self.state.standby_off or service.status.status.network_standby is False
        if woke and (self.state.pending_push or standby_off):
            # Network standby back on, and whatever waited goes out.
            self._background = asyncio.create_task(self.rendezvous(datetime.now(UTC)))
        log.info("Wake-on-LAN from the app: panel %s", "woke" if woke else "did not answer")
        return WakeResult(
            sent=True,
            woke=woke,
            reason=None if woke else "no answer: the packets may not reach it (see docs/WAKE.md)",
        )

    def _in_wake_window(self, now: datetime, settings: FrameSettings, today: date) -> bool:
        wake = alarm_time(settings)
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
