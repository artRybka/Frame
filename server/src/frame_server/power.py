"""Power policy (docs/WAKE.md). The frame's app (panel_app.py) sets its own
alarm and goes to sleep by itself; the server only answers its questions,
so this is what is left of the policy on the server's side: the next wake,
a picture waiting for it, and "Obudź ramkę" / "Uśpij ramkę" from the app.

The schedule is the same on the charger and on battery; on the charger the
app does not sleep at all. On battery it sleeps with the Wi-Fi on between
changes (Wake-on-LAN reaches it for a picture sent from the app) and with
the Wi-Fi off in quiet hours and in the economy mode ("Oszczędny"), when
only its alarm or the button wakes it. Whatever could not reach it waits as
a pending push: the app gets it at its next question.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from .battery import day_plan
from .device import MdcError
from .schedule import next_change, next_check
from .status import DeviceStatus, PanelPower

if TYPE_CHECKING:
    from .service import FrameService

log = logging.getLogger(__name__)

POWER_KEY = "power"
# "Obudź ramkę": how long to keep sending magic packets and waiting for the app.
# On battery the panel answered 60 s to 2.5 min into a burst of one packet a
# second (E13, 2026-10-27): keep sending for 3 minutes, look a bit longer.
WAKE_BURST_SECONDS = 180
WAKE_LOOK = timedelta(seconds=190)
# Meanwhile the server looks this often whether the panel is up (answers
# MDC); up this long and its app still silent (hung, or not started after a
# boot), it starts the app over MDC (0xC7 81 01).
WAKE_STEP = timedelta(seconds=15)
APP_GRACE = timedelta(seconds=30)
# Woken just after it went down, the panel answers within seconds and the
# app asks at its next heartbeat (15 s): the look lasts at least this after
# the wait for a panel going down.
WAKE_AFTER_DOWN = timedelta(seconds=45)
# The launcher installs (or restarts) the app and it asks within this.
INSTALL_LOOK = timedelta(seconds=90)
# A wake closer than this is not worth a sleep, and a change due within it
# keeps a woken panel awake for it.
WAKE_MARGIN = timedelta(minutes=2)


class PowerState(BaseModel):
    pending_push: bool = False  # content changed while the panel was unreachable


class WakeResult(BaseModel):
    sent: bool  # magic packets went out
    woke: bool  # the app asked afterwards
    # The app was not asking although the panel was up: started over MDC.
    started: bool = False
    asleep_until: str | None = None  # deep sleep: Wake-on-LAN cannot reach it
    asleep_until_at: str | None = None  # the same as a moment (ISO)
    # Asleep with the Wi-Fi off (with or without an alarm): nothing was sent.
    deep_sleep: bool = False
    # The Wi-Fi went off by itself (unplugged): only the button wakes it.
    wifi_lost: bool = False
    reason: str | None = None
    # Why nothing could be tried: no Samsung certificates on the server (so
    # no app to start), or no MAC address for Wake-on-LAN.
    problem: Literal["no_certificates", "no_mac"] | None = None


class RestResult(BaseModel):
    """ "Głęboki sen" / "Wyłącz ramkę" from the app."""

    until: str | None = None  # ISO; None: switched off, only the button wakes it
    # "soon": the app is awake (or woken for it) and sleeps at its next
    # question; "at_wake": it sleeps with the Wi-Fi off already, so it takes
    # it at its next alarm or the button.
    applies: Literal["soon", "at_wake"] = "soon"


class PowerManager:
    def __init__(self, service: FrameService) -> None:
        self.service = service
        service.status.asleep = self.asleep_state
        service.status.off_network = self._off_network
        service.status.answered = self._answered
        service.status.rang = service.app.alarms_rang
        self._tasks: set[asyncio.Task[None]] = set()

    # -- persisted state ------------------------------------------------------

    @property
    def state(self) -> PowerState:
        return PowerState.model_validate(self.service.library.get_state(POWER_KEY, {}))

    def _save(self, state: PowerState) -> None:
        self.service.library.set_state(POWER_KEY, state.model_dump(mode="json"))
        self.publish_status()

    def publish_status(self) -> None:
        """What the app's status shows of the power state."""
        app = self.service.app
        status = self.service.status.status
        status.pending_push = self.state.pending_push
        status.panel_app = app.active
        wake = app.wakes_at()
        tz = self.service.player.settings.tz()
        status.wakes_at = wake.astimezone(tz).strftime("%H:%M") if wake else None
        status.wake_at = wake.isoformat(timespec="seconds") if wake else None
        status.certificates_expire_at = app.certificates_warning(datetime.now(UTC))
        status.mode_pending = app.mode_pending()
        state = app.state
        status.rest_until = state.rest_until
        status.switched_off = state.off
        status.wifi_lost = state.active and state.asleep and state.wifi_lost
        silent = app.silent_since(datetime.now(UTC))
        status.app_silent_since = silent.isoformat(timespec="seconds") if silent else None
        rest = datetime.fromisoformat(state.rest_until) if state.rest_until else None
        settings = self.service.player.settings
        now = datetime.now(UTC)
        self.service.status.estimate_battery(
            lambda awake: day_plan(settings, now, awake, rest_until=rest, off=state.off)
        )

    def _off_network(self) -> None:
        """A look found the panel off the Wi-Fi."""
        self.service.app.lost_wifi(datetime.now(UTC))

    async def _answered(self) -> None:
        """A look found the panel up: its app is started if it does not run."""
        await self.service.app.panel_up(datetime.now(UTC))

    def mark_pending(self, pending: bool) -> None:
        state = self.state
        if state.pending_push != pending:
            state.pending_push = pending
            self._save(state)

    def deep_asleep(self, now: datetime | None = None) -> bool:
        """Asleep with the Wi-Fi off: nothing reaches the panel until its
        alarm or the button."""
        return self.service.app.deep_asleep()

    def wakes_at(self, now: datetime | None = None) -> datetime | None:
        """When the app's alarm wakes the sleeping panel."""
        return self.service.app.wakes_at()

    def next_wake(self, now: datetime) -> datetime:
        """The next change, or a check between changes in the economy mode
        when sooner; under a hold for good still the next change time, so
        the panel is refreshed now and then."""
        wake = self.next_change_wake(now)
        check = next_check(now + WAKE_MARGIN, self.service.player.settings)
        return min(wake, check) if check is not None else wake

    def next_change_wake(self, now: datetime) -> datetime:
        """``next_wake`` without the economy checks: the next change, or the
        end of a hold."""
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
        candidates = [c for c in candidates if c > soon]
        return min(candidates) if candidates else next_change(soon, settings)

    def asleep_state(self, status: DeviceStatus) -> PanelPower:
        """Which sleep a panel that does not answer is most likely in."""
        app = self.service.app
        if app.asleep():
            return "deep_sleep" if app.deep_asleep() else "standby"
        if status.network_standby is True:
            return "standby"
        if status.network_standby is False:
            return "deep_sleep"
        return "offline"  # never seen: asleep or off the network

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

    async def tick(self, now: datetime | None = None) -> None:
        if not self.service.device_configured:
            return
        await self.service.app.tick(now or datetime.now(UTC))

    async def sleep_now(self) -> None:
        """The app's "Uśpij ramkę": the app sleeps at its next question."""
        self.service.app.request_sleep()

    async def rest_now(self, hours: int | None) -> RestResult:
        """ "Głęboki sen" for ``hours``, or "Wyłącz ramkę" (None): the app
        sleeps with the Wi-Fi off at its next question. Asleep in the
        network it is woken for it; asleep without the Wi-Fi it takes it at
        its next alarm (or the button)."""
        app = self.service.app
        now = datetime.now(UTC)
        app.request_rest(now, None if hours is None else now + timedelta(hours=hours))
        until = app.state.rest_until
        if app.deep_asleep():
            return RestResult(until=until, applies="at_wake")
        if app.active and not app.awake(now) and self.service.settings.device_mac:
            task = asyncio.create_task(self._wake_for_rest())
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return RestResult(until=until)

    async def _wake_for_rest(self) -> None:
        burst = asyncio.create_task(self.service.panel.wake(seconds=WAKE_BURST_SECONDS))
        try:
            woke = await self.service.app.wait_for_contact(WAKE_LOOK.total_seconds())
        finally:
            burst.cancel()
        log.info("Wake-on-LAN to put the frame to rest: %s", "it asked" if woke else "no answer")

    async def wake_now(self, sleep_after: bool = False) -> WakeResult:
        """The app's "Obudź ramkę": awake already (on the charger it asks
        every few seconds), or Wake-on-LAN until it asks again, so the app
        can say whether it actually woke. In deep sleep nothing reaches it.
        An app not told to sleep but silent (the panel fell asleep by itself,
        or the app hung) is not taken for awake: it is woken like a sleeping
        one, and started over MDC when the panel is up and it still does not
        ask.

        ``sleep_after`` ("Sprawdź stan"): woken only to be looked at, so it
        is not kept awake."""
        service, app = self.service, self.service.app
        now = datetime.now(UTC)
        if app.deep_asleep():
            return self._deep_result()
        if not sleep_after:
            app.keep_awake(now)
        if not app.active:
            return await self._install()
        if app.awake(now):
            return WakeResult(sent=False, woke=True)
        if not service.settings.device_mac:
            return WakeResult(sent=False, woke=False, problem="no_mac", reason="no MAC address set")
        woke, started = await self.reach()
        log.info("Wake-on-LAN for the frame's app: %s", "it asked" if woke else "no answer")
        return WakeResult(
            sent=True,
            woke=woke,
            started=started,
            reason=None if woke else "no answer: the packets may not reach it (see docs/WAKE.md)",
        )

    async def restart_now(self) -> WakeResult:
        """ "Uruchom ponownie" from the app: the app reboots the panel at its
        next question (``rebootDevice``, the server starts it again after
        the boot). Asleep in the network it is woken for it; up but with a
        silent app, the app is started over MDC first. In deep sleep nothing
        reaches it."""
        service, app = self.service, self.service.app
        if app.deep_asleep():
            return self._deep_result()
        if not app.active:
            return await self._install()  # starting it is all there is to do
        app.request_restart()
        awake = app.awake()
        mac = service.settings.device_mac
        woke, started = await self.reach(wol=bool(mac) and not awake)
        if not woke:
            app.restart_requested = False  # not at some later question out of the blue
        log.info("restart of the frame: %s", "the app reboots it" if woke else "no answer")
        return WakeResult(
            sent=bool(mac) and not awake,
            woke=woke,
            started=started,
            reason=None if woke else "no answer from the frame's app",
        )

    async def reach(self, wol: bool = True) -> tuple[bool, bool]:
        """Wake-on-LAN (``wol``) until the app asks; once the panel answers
        MDC and its app still does not ask, the app is started over MDC.
        Whether it asked, and whether it had to be started."""
        app = self.service.app
        loop = asyncio.get_running_loop()
        since = app.contacts
        # Told to sleep moments ago (a status check), the panel is still up:
        # magic packets then wake it seconds after it goes down, too soon for
        # the app to notice it slept, and it never asked again (2026-11-01, a
        # picture sent right after "Sprawdź stan"). They wait until it is down
        # for sure; within the usual look, so "Obudź ramkę" does not time out.
        down = app.down_in(datetime.now(UTC)) if wol else 0.0
        look = max(WAKE_LOOK.total_seconds(), down + WAKE_AFTER_DOWN.total_seconds())
        deadline = loop.time() + look
        if down and await app.wait_for_contact(down, since=since):
            return True, False
        burst = (
            asyncio.create_task(self.service.panel.wake(seconds=WAKE_BURST_SECONDS))
            if wol
            else None
        )
        up_at: float | None = None
        started = False
        try:
            while (left := deadline - loop.time()) > 0:
                step = min(WAKE_STEP.total_seconds(), left)
                if await app.wait_for_contact(step, since=since):
                    return True, started
                if started:
                    continue
                if up_at is None:
                    if await app.panel_answers():
                        up_at = loop.time()
                elif loop.time() - up_at >= APP_GRACE.total_seconds():
                    started = await app.start("did not ask after a wake")
            return await app.wait_for_contact(0, since=since), started
        finally:
            if burst is not None:
                burst.cancel()

    async def _install(self) -> WakeResult:
        """The panel does not run the app (never did, or fell back to
        another source): start it, waking the panel if need be."""
        service, app = self.service, self.service.app
        if app.ensure_package() is None:
            return WakeResult(
                sent=False,
                woke=False,
                problem="no_certificates",
                reason="no Samsung certificates on the server: no app to start",
            )
        try:
            await app.install()
        except MdcError as err:
            return WakeResult(sent=service.panel.woke, woke=False, reason=str(err))
        woke = await app.wait_for_contact(INSTALL_LOOK.total_seconds())
        return WakeResult(
            sent=service.panel.woke,
            woke=woke,
            reason=None if woke else "the frame's app did not start",
        )

    def _deep_result(self) -> WakeResult:
        app = self.service.app
        until = app.wakes_at()
        return WakeResult(
            sent=False,
            woke=False,
            asleep_until=self._hhmm(until),
            asleep_until_at=until.isoformat(timespec="seconds") if until else None,
            deep_sleep=True,
            wifi_lost=app.state.wifi_lost,
            reason="deep sleep (Wi-Fi off) until the alarm, only the button wakes it",
        )

    def _hhmm(self, moment: datetime | None) -> str | None:
        if moment is None:
            return None
        return moment.astimezone(self.service.player.settings.tz()).strftime("%H:%M")

    async def run(self, period: float = 5.0) -> None:
        self.publish_status()
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("power tick failed")
            await asyncio.sleep(period)
