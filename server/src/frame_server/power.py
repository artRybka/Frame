"""Power policy (docs/WAKE.md). The schedule is the same on the charger and
on battery; only the night differs.

By day the panel sleeps with network standby on, so Wake-on-LAN (2.4 GHz
Wi-Fi) wakes it for a picture sent from the app or for a change. On battery
the server puts it back into that light sleep once a picture has been
downloaded and drawn, instead of leaving it awake on its own timer; on the
charger too when it was asleep before (put to sleep from the app, or woken
for the picture or for a status check). In quiet
hours on battery it sleeps with the Wi-Fi off, and its own alarm (MDC
on-timer) wakes it for the morning change that ends them; on the charger
pictures keep going out at once. Whatever could not reach the
panel waits as a pending push and goes out as soon as the panel shows up
again: after the alarm or a press of its button. The same goes for network
standby: the night turns it off, and until the panel is found again (alarm or
button) Wake-on-LAN cannot reach it, so the server keeps looking for it.

The economy mode ("Oszczędny") makes every sleep on battery a deep one: after
each picture the alarm is set to the next wake (the next change, or a check
between changes), the Wi-Fi goes off and the panel with it. When it wakes,
the server sends what waited for it, or a check with nothing to show sends
it straight back to sleep; a change due then goes out the usual way. The
panel never asks for pictures itself (E7), so a wake only works while the
server is up. On the charger the economy mode works like the online one.

All that is MDC's way, and on firmware 1130.7 the panel refuses the alarm.
When the panel runs the Frame app (panel_app.py) the app sets its own alarm
and goes to sleep by itself: the power manager then only answers its
questions, and both modes work through that.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel

from .device import MdcConnectionError, MdcError
from .device.mdc import ON_TIMER_REPEAT, MdcClient
from .schedule import (
    FrameSettings,
    in_quiet_hours,
    morning_change,
    next_change,
    next_check,
    quiet_hours,
)
from .status import DeviceStatus, PanelPower

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
# On battery the panel answered 60 s to 2.5 min into a burst of one packet a
# second (E13, 2026-10-27): keep sending for 3 minutes, look a bit longer.
WAKE_BURST_SECONDS = 180
WAKE_LOOK = timedelta(seconds=190)
# After the panel downloaded a picture: ~12 s to prepare it and ~31 s to
# redraw (E2), with a margin, before it is powered off into light sleep.
LIGHT_SLEEP_AFTER = 90.0
# "Sprawdź stan" woke the panel on battery only to look at it: back to light
# sleep after a while, unless something is sent to it first.
CHECK_SLEEP_AFTER = 60.0
# Economy: a wake closer than this is not worth a deep sleep, and a change
# due within it keeps a woken panel awake for it.
WAKE_MARGIN = timedelta(minutes=2)
# The panel refused the alarm (firmware 1130.7 NAKs every hh:mm write of
# 0x25): no deep sleep, and another try only after this long.
ALARM_RETRY = timedelta(days=1)


class PowerState(BaseModel):
    pending_push: bool = False  # content changed while the panel was unreachable
    night_of: str | None = None  # quiet hours (by start date) the deep sleep was entered for
    woke_on: str | None = None  # date the panel was found after the alarm
    timer: str | None = None  # HH:MM the panel's alarm is armed for, None: off
    # Network standby is off (the night turned it off, or a status check found
    # it off): Wake-on-LAN cannot work until the panel is found and it is back on.
    standby_off: bool = False
    # Economy mode: when the panel's alarm wakes it next (ISO), the wake it
    # was found for, and a wake it did not show up for.
    wake_at: str | None = None
    woke_for: str | None = None
    missed_wake: str | None = None
    # When the panel last refused the alarm (NAK): it cannot wake itself, so
    # it never sleeps with the Wi-Fi off.
    alarm_refused: str | None = None


class WakeResult(BaseModel):
    sent: bool  # magic packets went out
    woke: bool  # the panel answered MDC afterwards
    asleep_until: str | None = None  # deep sleep: Wake-on-LAN cannot reach it
    asleep_until_at: str | None = None  # the same as a moment (ISO)
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
        # Woken from a sleep only for a picture or a look: back to sleep after,
        # on the charger as well.
        self._put_back = False
        service.status.asleep = self.asleep_state

    # -- persisted state ------------------------------------------------------

    @property
    def state(self) -> PowerState:
        return PowerState.model_validate(self.service.library.get_state(POWER_KEY, {}))

    def _save(self, state: PowerState) -> None:
        self.service.library.set_state(POWER_KEY, state.model_dump(mode="json"))
        self.publish_status()

    def publish_status(self) -> None:
        """What the app's status shows of the power state."""
        state, app = self.state, self.service.app
        status = self.service.status.status
        status.pending_push = state.pending_push
        status.panel_app = app.active
        if app.active:
            wake = app.wakes_at()
            tz = self.service.player.settings.tz()
            status.wakes_at = wake.astimezone(tz).strftime("%H:%M") if wake else None
            status.alarm_refused = False  # the app has an alarm of its own
        else:
            status.wakes_at = state.timer
            status.alarm_refused = state.alarm_refused is not None

    @property
    def economy(self) -> bool:
        """Economy ("Oszczędny") on battery: the Wi-Fi is off between the
        alarm's wakes. Not while the panel refuses the alarm: then it works
        as online. With the Frame app the app decides (see panel_app.py)."""
        economy = self.service.player.settings.power_mode == "economy"
        if self.service.app.active:
            return economy
        return economy and self.service.status.on_battery and self.alarm_works()

    def alarm_works(self) -> bool:
        refused = self.state.alarm_refused
        return refused is None or datetime.now(UTC) - datetime.fromisoformat(refused) >= ALARM_RETRY

    async def _set_alarm(self, mdc: MdcClient, wake: time) -> bool:
        """The panel's own alarm, daily at ``wake``; False when it refuses."""
        try:
            await mdc.set_on_timer(wake.hour, wake.minute, ON_TIMER_REPEAT["daily"])
        except MdcConnectionError:
            raise
        except MdcError as err:
            state = self.state
            state.alarm_refused = datetime.now(UTC).isoformat(timespec="seconds")
            state.timer = None
            self._save(state)
            log.warning("the panel refused the alarm (%s): no sleep with the Wi-Fi off", err)
            return False
        state = self.state
        if state.alarm_refused is not None:
            state.alarm_refused = None
            self._save(state)
        return True

    def mark_pending(self, pending: bool) -> None:
        state = self.state
        if state.pending_push != pending:
            state.pending_push = pending
            self._save(state)

    def deep_asleep(self, now: datetime) -> bool:
        """In quiet hours on battery, or in the economy mode between wakes,
        the Wi-Fi is off: nothing reaches the panel."""
        settings = self.service.player.settings
        state = self.state
        if self.service.app.active:
            return self.service.app.deep_asleep()
        if self.economy and state.standby_off and state.wake_at is not None:
            return True
        return (
            self.service.status.on_battery
            and in_quiet_hours(now, settings)
            and state.night_of == night_key(now, settings)
            and state.standby_off  # the Wi-Fi did go off (the alarm was taken)
        )

    def wakes_at(self, now: datetime) -> datetime | None:
        """When the panel in deep sleep wakes next: the economy wake, or the
        next ring of the night's alarm. With the Frame app: its alarm, in
        any sleep."""
        if self.service.app.active:
            return self.service.app.wakes_at()
        if not self.deep_asleep(now):
            return None
        state = self.state
        if self.economy and state.wake_at:
            return datetime.fromisoformat(state.wake_at)
        if state.timer is None:
            return None
        tz = self.service.player.settings.tz()
        local = now.astimezone(tz)
        hh, mm = (int(part) for part in state.timer.split(":"))
        ring = datetime.combine(local.date(), time(hh, mm), tzinfo=tz)
        return ring if ring > local else ring + timedelta(days=1)

    def next_wake(self, now: datetime) -> datetime:
        """Economy: the next change, or a check between changes when sooner;
        under a hold for good still the next change time, so the panel is
        refreshed now and then."""
        settings = self.service.player.settings
        player = self.service.player.state
        soon = now + WAKE_MARGIN
        candidates: list[datetime] = []
        hold = player.hold
        if hold is not None and hold.active(now):
            if hold.until is not None:
                candidates.append(datetime.fromisoformat(hold.until))
        elif player.next_change_at is not None:
            due = datetime.fromisoformat(player.next_change_at)
            candidates.append(due if due > soon else next_change(soon, settings))
        check = next_check(soon, settings)
        if check is not None:
            candidates.append(check)
        candidates = [c for c in candidates if c > soon]
        return min(candidates) if candidates else next_change(soon, settings)

    def asleep_state(self, status: DeviceStatus) -> PanelPower:
        """Which sleep a panel that does not answer is most likely in."""
        app = self.service.app
        if app.asleep():
            return "deep_sleep" if app.deep_asleep() else "standby"
        if self.deep_asleep(datetime.now(UTC)) or self.state.standby_off:
            return "deep_sleep"  # Wi-Fi off: only its alarm or the button wakes it
        if status.network_standby is True:
            return "standby"
        if status.network_standby is False:
            return "deep_sleep"
        return "offline"  # never seen: asleep or off the network

    # -- panel ---------------------------------------------------------------

    async def arm(self, settings: FrameSettings) -> None:
        """Set the panel's alarm to the morning change, every day."""
        wake = alarm_time(settings)
        async with self.service.panel.session() as mdc:
            if not await self._set_alarm(mdc, wake):
                return
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
                if not await self._set_alarm(mdc, wake):
                    # It could not wake itself in the morning: light sleep,
                    # Wake-on-LAN keeps working through the night.
                    await self.service.panel.power_off(mdc)
                    self.service.status.note_sleep(deep=False)
                    return
                await mdc.set_network_standby(False)
                await mdc.set_power(False)
        except MdcError as err:
            log.warning("could not put the panel into deep sleep: %s", err)
            return
        state = self.state
        state.timer = wake.strftime("%H:%M")
        state.standby_off = True
        self._save(state)
        self.service.status.note_sleep(deep=True)
        log.info("panel in deep sleep until %s", state.timer)

    async def enter_deep(self, now: datetime) -> bool:
        """Economy: alarm for the next wake, Wi-Fi off, panel off. Nothing
        happens when the panel turns out to be on the charger."""
        self._last_arm = now
        status = self.service.status
        wake = self.next_wake(now)
        local = wake.astimezone(self.service.player.settings.tz())
        try:
            async with self.service.panel.waking_session() as mdc:
                await status.read_battery(mdc)
                if not status.on_battery or not await self._set_alarm(mdc, local.time()):
                    return False
                await mdc.set_network_standby(False)
                await mdc.set_power(False)
        except MdcError as err:
            log.warning("could not put the panel into deep sleep: %s", err)
            return False
        self.cancel_light_sleep()
        self._put_back = False
        state = self.state
        state.timer = local.strftime("%H:%M")
        state.wake_at = wake.isoformat(timespec="seconds")
        state.standby_off = True
        self._save(state)
        status.note_sleep(deep=True)
        log.info("economy: panel in deep sleep until %s", state.wake_at)
        return True

    def change_due(self, now: datetime) -> bool:
        """A change is being shown or comes within moments: a woken panel
        stays awake for it, and goes back to sleep after the picture."""
        player = self.service.player
        if player.busy:
            return True
        state = player.state
        if state.hold is not None and state.hold.active(now):
            return False
        due = state.next_change_at
        return due is not None and datetime.fromisoformat(due) - now < WAKE_MARGIN

    async def rendezvous(self, now: datetime) -> bool:
        """Catch the panel while it is awake: Wi-Fi back on for Wake-on-LAN,
        then whatever waited for it."""
        self._last_probe = now
        if self.service.status.settling(now):
            return False  # just put to sleep, and maybe still answering
        status = await self.service.status.refresh()
        if not status.reachable:
            return False
        state = self.state
        state.woke_on = now.astimezone(self.service.player.settings.tz()).date().isoformat()
        if state.wake_at is not None:
            state.woke_for = state.wake_at
            state.missed_wake = None
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
        elif self.economy and not self.change_due(now):
            # A check with nothing to show: straight back to sleep, no redraw.
            await self.enter_deep(now)
        return True

    async def tick(self, now: datetime | None = None) -> None:
        service = self.service
        if not service.device_configured:
            return
        now = now or datetime.now(UTC)
        settings = service.player.settings
        state = self.state
        if service.app.active:
            await service.app.tick(now)  # the app keeps its own alarm and sleep
            return
        if self.economy:
            await self._economy_tick(now)
            return
        if state.wake_at is not None and not state.standby_off:
            # Back from the economy mode (or on the charger): its wakes are over.
            state.wake_at = state.woke_for = state.missed_wake = None
            self._save(state)
        if in_quiet_hours(now, settings):
            # On battery only; a change at the very start of quiet hours
            # goes out first.
            tonight = state.night_of == night_key(now, settings)
            starting = service.player.change_starting(now)
            if service.status.on_battery and not tonight and not starting:
                await self.enter_night(now, settings)
            return

        want = alarm_time(settings).strftime("%H:%M")
        retry = self._due(self._last_arm, now, RETRY_ARM) and self.alarm_works()
        if state.timer != want and retry:
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

    async def _economy_tick(self, now: datetime) -> None:
        service = self.service
        state = self.state
        if not state.standby_off:
            # Awake or in light sleep: just switched to the economy mode,
            # unplugged, or woken and nothing put it back. Deep sleep, unless
            # a picture is on its way.
            light_sleep = self._light_sleep is not None and not self._light_sleep.done()
            busy = service.progress.active or light_sleep or self.change_due(now)
            if not busy and self._due(self._last_arm, now, RETRY_ARM):
                await self.enter_deep(now)
            return
        if state.wake_at is not None and state.woke_for != state.wake_at:
            wake = datetime.fromisoformat(state.wake_at)
            if wake - timedelta(minutes=1) <= now < wake + WAKE_WINDOW:
                if self._due(self._last_probe, now, PROBE_IN_WINDOW):
                    await self.rendezvous(now)
                return
            if now >= wake + WAKE_WINDOW:
                # Not found: the alarm rings daily, so the same time tomorrow.
                state.missed_wake = state.wake_at
                state.wake_at = (wake + timedelta(days=1)).isoformat(timespec="seconds")
                self._save(state)
                log.warning("economy: the panel did not wake at %s", state.missed_wake)
        if self._due(self._last_probe, now, PROBE_PENDING):
            await self.rendezvous(now)  # the button may have woken it

    # -- light sleep after a picture ------------------------------------------

    def cancel_light_sleep(self) -> None:
        """Another picture is on its way: the panel must stay awake for it."""
        if self._light_sleep and not self._light_sleep.done():
            self._light_sleep.cancel()
        self._light_sleep = None

    def put_back_to_sleep(self) -> None:
        """The panel was asleep before this picture: it goes back afterwards."""
        self._put_back = True

    def after_push(self, fetched: bool) -> None:
        """Back to light sleep once the picture is on the panel: on battery,
        and on the charger when it was asleep before. At night on battery
        the deep sleep follows anyway."""
        self.cancel_light_sleep()
        if fetched:
            self._sleep_soon(LIGHT_SLEEP_AFTER, only_on_battery=not self._put_back)

    def _sleep_soon(self, delay: float, only_on_battery: bool) -> None:
        now = datetime.now(UTC)
        if self.service.status.on_battery and in_quiet_hours(now, self.service.player.settings):
            return
        self.cancel_light_sleep()
        self._light_sleep = asyncio.create_task(self._sleep_later(delay, only_on_battery))

    async def _sleep_later(self, delay: float, only_on_battery: bool = False) -> None:
        await asyncio.sleep(delay)
        status = self.service.status
        economy = self.service.player.settings.power_mode == "economy"
        if economy and await self.enter_deep(datetime.now(UTC)):
            return  # on the charger: as in the online mode
        try:
            async with self.service.panel.session() as mdc:
                if only_on_battery:
                    # The charger may have gone in or out since the last check
                    # (a panel unplugged drops off the network at once).
                    await status.read_battery(mdc)
                    if not status.on_battery:
                        return
                await self.service.panel.power_off(mdc)
        except MdcError as err:
            log.info("could not put the panel into light sleep: %s", err)
            return
        self._put_back = False
        status.note_sleep(deep=False)
        log.info("panel in light sleep (network standby on)")

    async def sleep_now(self) -> None:
        """The app's "Uśpij ramkę": light sleep at once (economy on battery:
        deep, until the next wake). The Frame app sleeps at its next question."""
        self.cancel_light_sleep()
        if self.service.app.active:
            self.service.app.request_sleep()
            return
        if self.economy and await self.enter_deep(datetime.now(UTC)):
            return
        await self.service.panel.sleep()
        self._put_back = False
        self.service.status.note_sleep(deep=False)
        log.info("panel put to sleep from the app (network standby on)")

    async def wake_now(self, sleep_after: bool = False) -> WakeResult:
        """The app's "Obudź ramkę": a burst of magic packets, then look for
        the panel, so the app can say whether it actually woke.

        ``sleep_after`` ("Sprawdź stan"): woken only to be looked at, so it
        goes back to light sleep after a while, on the charger as well."""
        service = self.service
        now = datetime.now(UTC)
        if service.app.active and not self.deep_asleep(now):
            return await self._wake_app(now, sleep_after)
        if self.deep_asleep(now):
            state = self.state
            until = self.wakes_at(now)
            return WakeResult(
                sent=False,
                woke=False,
                asleep_until=state.timer,
                asleep_until_at=until.isoformat(timespec="seconds") if until else None,
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
                woke = bool((await service.status.refresh(force=True)).reachable)
                if not woke:
                    await asyncio.sleep(3)
        finally:
            burst.cancel()
        if woke:
            self._put_back = sleep_after  # "Obudź ramkę" means it is to stay awake
        state = self.state
        standby_off = state.standby_off or service.status.status.network_standby is False
        if woke and (state.pending_push or standby_off):
            # Network standby back on, and whatever waited goes out.
            self._background = asyncio.create_task(self.rendezvous(datetime.now(UTC)))
        if woke and sleep_after and not state.pending_push:
            # A waiting picture puts it back to sleep itself once drawn.
            self._sleep_soon(CHECK_SLEEP_AFTER, only_on_battery=False)
        log.info("Wake-on-LAN from the app: panel %s", "woke" if woke else "did not answer")
        return WakeResult(
            sent=True,
            woke=woke,
            reason=None if woke else "no answer: the packets may not reach it (see docs/WAKE.md)",
        )

    async def _wake_app(self, now: datetime, sleep_after: bool) -> WakeResult:
        """The Frame app: awake already (it asks every few seconds on the
        charger), or Wake-on-LAN until it asks again."""
        service, app = self.service, self.service.app
        if not sleep_after:
            app.keep_awake(now)
        if not app.asleep():
            return WakeResult(sent=False, woke=True)
        if not service.settings.device_mac:
            return WakeResult(sent=False, woke=False, reason="no MAC address set")
        burst = asyncio.create_task(service.panel.wake(seconds=WAKE_BURST_SECONDS))
        try:
            woke = await app.wait_for_contact(WAKE_LOOK.total_seconds())
        finally:
            burst.cancel()
        log.info("Wake-on-LAN for the Frame app: %s", "it asked" if woke else "no answer")
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
        self.publish_status()
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("power tick failed")
            await asyncio.sleep(period)
