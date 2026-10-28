"""The frame's own app (Samsung "Custom" content source, docs/WAKE.md E16).

With the app the panel asks for its pictures instead of being sent them. On
every start and every wake it asks ``/panel/next`` what to show, how long to
sleep and whether to keep the Wi-Fi on; it draws the picture, sets its own
alarm (``webapis.epaper.setScheduleWakeupTime``) and goes to sleep. That
alarm is what the MDC on-timer could never be on firmware 1130.7, so the
economy mode works through the app, and in the online mode changes no
longer depend on Wake-on-LAN.

The alarms cannot be cancelled and the launcher sometimes reinstalls and
restarts the app as it goes to sleep, so the app keeps no plan of its own:
whenever it wakes, for whatever reason, it asks again.

With ``base_screen_resolution`` "always" in its config.xml the app's page is
2560x1440, so it gets the very picture the Mobile source shows (passthrough
or our dither, whatever the settings render) and shows it 1:1.

The package has to be signed with the Samsung certificate made for this
panel, which lives on Mateusz's Mac: the server never builds it, it only
serves what ``scripts/panel-app/pack.sh`` uploaded. The app's logic
(``app.js``) comes from the server at every start, so most changes need no
new package.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from .device import MdcError
from .device.mdc import CONTENT_SOURCE_CUSTOM
from .schedule import in_quiet_hours, quiet_hours

if TYPE_CHECKING:
    from .service import FrameService

log = logging.getLogger(__name__)

APP_KEY = "panel_app"
WIDGET = "Frame"
# On the charger the app stays awake and asks this often.
POLL = timedelta(seconds=20)
# A change is being prepared: ask again after this.
RETRY = timedelta(seconds=15)
# The panel's alarm reaches a week ahead at most (604800 s).
MAX_AHEAD = timedelta(days=7) - timedelta(hours=1)
# No word from the app this long after its alarm: the wake was missed.
MISSED_AFTER = timedelta(minutes=15)
# JS keeps running up to ~130 s after goToSleep(), and an alarm due before
# the panel is really down is lost (E16): never sleep for less than this.
MIN_SLEEP = timedelta(minutes=5)
# After a sleep with the Wi-Fi off the panel boots cold and the launcher
# does not always start the app (E16): MDC 0xC7 81 01 starts it. Tried this
# long after the alarm, then every ``KICK_EVERY`` until the wake is missed.
KICK_AFTER = timedelta(seconds=90)
KICK_EVERY = timedelta(minutes=2)
# "Obudź ramkę" keeps the woken app awake (asking every ``POLL``) this long.
KEEP_AWAKE = timedelta(minutes=10)
# While the app is awake the server reads the battery over MDC (Tizen's
# systeminfo fails on the panel) at most this often.
BATTERY_EVERY = timedelta(minutes=10)
BATTERY_TIMEOUT = 10.0
# The source the panel had before Custom when it was never read (Samsung
# MDC: 00 = MagicInfo, which the Mobile mode most likely is).
MOBILE_SOURCE = 0x00


class AppState(BaseModel):
    active: bool = False  # the panel's content comes from our app
    seen_at: str | None = None  # the app's last question (ISO)
    build: str | None = None  # the installed package's version
    code: str | None = None  # the version of the logic it ran (app.js)
    screen: str | None = None  # the page as the app sees it, e.g. "2560x1440@1"
    asleep: bool = False  # told to sleep at its last question
    wake_at: str | None = None  # when its alarm wakes it (ISO)
    standby: bool = True  # network standby through that sleep
    missed_wake: str | None = None  # an alarm it did not show up for
    previous_source: int | None = None  # the launcher's source before Custom


class AppHello(BaseModel):
    """What the app says when it asks (all optional: old builds say less)."""

    reason: str = "start"  # start, resume, wake, poll, retry
    build: str | None = None
    code: str | None = None
    screen: str | None = None
    battery: int | None = None  # percent
    charging: bool | None = None


class NextAnswer(BaseModel):
    """What the app does next. ``sleep``: draw ``image``, set the alarm to
    ``wake_ms`` and sleep with network standby ``standby``; ``stay``: draw
    and ask again in ``wait_s`` (on the charger); ``wait``: a change is
    being prepared, ask again in ``wait_s``."""

    action: Literal["sleep", "stay", "wait"]
    file_id: str | None = None
    image: str | None = None
    title: str = ""
    wait_s: int = 0
    wake_at: str | None = None
    wake_ms: int | None = None
    standby: Literal["ON", "OFF"] = "ON"
    code: str = ""  # app.js on the server: a different one is loaded at once


class PackageInfo(BaseModel):
    version: str
    size: int
    uploaded_at: str


class AppView(BaseModel):
    """The app as the iOS app shows it."""

    active: bool
    package: PackageInfo | None
    state: AppState


APP_DIR = Path(__file__).parent / "web" / "panel_app"


def app_code() -> bytes:
    return (APP_DIR / "app.js").read_bytes()


CODE_VERSION = hashlib.sha256(app_code()).hexdigest()[:10]


class PanelApp:
    def __init__(self, service: FrameService) -> None:
        self.service = service
        self.dir: Path = service.settings.data_dir / "panel-app"
        self.contact = asyncio.Event()  # set at every question of the app
        self.awake_until: datetime | None = None
        self.sleep_requested = False
        self._kicked: datetime | None = None

    # -- persisted state ------------------------------------------------------

    @property
    def state(self) -> AppState:
        return AppState.model_validate(self.service.library.get_state(APP_KEY, {}))

    def _save(self, state: AppState) -> None:
        self.service.library.set_state(APP_KEY, state.model_dump(mode="json"))
        self.service.power.publish_status()

    @property
    def active(self) -> bool:
        return self.state.active

    def asleep(self) -> bool:
        state = self.state
        return state.active and state.asleep

    def wakes_at(self) -> datetime | None:
        """When the sleeping app's alarm wakes it."""
        state = self.state
        if not (state.active and state.asleep and state.wake_at):
            return None
        return datetime.fromisoformat(state.wake_at)

    def deep_asleep(self) -> bool:
        """Asleep with the Wi-Fi off: only its alarm or the button wakes it."""
        state = self.state
        return state.active and state.asleep and not state.standby

    # -- the package ----------------------------------------------------------

    def package(self) -> PackageInfo | None:
        try:
            info = PackageInfo.model_validate_json((self.dir / "package.json").read_text())
        except (OSError, ValueError):
            return None
        return info if self.package_path().is_file() else None

    def package_path(self) -> Path:
        return self.dir / f"{WIDGET}.wgt"

    def store_package(self, data: bytes, version: str) -> PackageInfo:
        """A package signed on the Mac; the panel installs it the next time
        it looks (switching to Custom, or now and then as it goes to sleep)."""
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / f"{WIDGET}.wgt.part"
        tmp.write_bytes(data)
        tmp.replace(self.package_path())
        info = PackageInfo(
            version=version,
            size=len(data),
            uploaded_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        (self.dir / "package.json").write_text(info.model_dump_json())
        log.info("panel app package %s (%d bytes) stored", version, len(data))
        return info

    def sssp_config(self) -> str | None:
        info = self.package()
        if info is None:
            return None
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f"<widget>\n<ver>{info.version}</ver>\n<size>{info.size}</size>\n"
            f"<widgetname>{WIDGET}</widgetname>\n</widget>\n"
        )

    def view(self) -> AppView:
        state = self.state
        return AppView(active=state.active, package=self.package(), state=state)

    # -- the app's questions --------------------------------------------------

    async def ask(self, hello: AppHello) -> NextAnswer:
        """``answer``, with the battery and charger read over MDC first when
        the last read is old (Tizen's systeminfo fails on the panel): on the
        charger the app stays awake."""
        status = self.service.status
        checked = status.status.checked_at
        now = datetime.now(UTC)
        stale = checked is None or now - datetime.fromisoformat(checked) >= BATTERY_EVERY
        if stale and hello.charging is None and self.service.device_configured:
            try:
                await asyncio.wait_for(status.refresh(force=True), BATTERY_TIMEOUT)
            except (TimeoutError, MdcError) as err:
                log.info("no battery reading for the app: %s", err)
        return self.answer(hello)

    def answer(self, hello: AppHello, now: datetime | None = None) -> NextAnswer:
        """What the app shows and does next; it asked, so it is awake."""
        service = self.service
        now = now or datetime.now(UTC)
        self._note_contact(hello, now)
        content = service.store.current()
        power = service.power
        if power.state.pending_push:
            # It waited for the panel: it stays until the next change.
            power.mark_pending(False)
            service.player.postpone()
        common: dict[str, object] = {"code": CODE_VERSION}
        if content is not None:
            common |= {
                "file_id": content.file_id,
                "image": f"{service.settings.base_url()}/panel/images/{content.file_name}",
                "title": content.title,
            }
        if power.change_due(now):
            return self._awake(NextAnswer(action="wait", wait_s=_s(RETRY), **common))
        awake = self.awake_until is not None and now < self.awake_until
        charger = service.status.status.power_source == "ac"
        if not self.sleep_requested and (awake or charger):
            return self._awake(NextAnswer(action="stay", wait_s=_s(POLL), **common))
        wake = self.next_wake(now)
        if wake - now < MIN_SLEEP:
            # Too close to sleep for: stay up for it.
            wait = min(60, max(_s(RETRY), int((wake - now).total_seconds())))
            return self._awake(NextAnswer(action="wait", wait_s=wait, **common))
        self.sleep_requested = False
        self.awake_until = None
        standby = not self._deep(now)
        state = self.state
        state.asleep = True
        state.wake_at = wake.isoformat(timespec="seconds")
        state.standby = standby
        self._save(state)
        return NextAnswer(
            action="sleep",
            wake_at=state.wake_at,
            wake_ms=int(wake.timestamp() * 1000),
            standby="ON" if standby else "OFF",
            **common,
        )

    def _awake(self, answer: NextAnswer) -> NextAnswer:
        state = self.state
        if state.asleep:
            state.asleep = False
            self._save(state)
        return answer

    def _note_contact(self, hello: AppHello, now: datetime) -> None:
        state = self.state
        if not state.active:
            log.info("the panel runs the Frame app (%s)", hello.build)
        state.active = True
        state.seen_at = now.isoformat(timespec="seconds")
        state.build = hello.build or state.build
        state.code = hello.code or state.code
        state.screen = hello.screen or state.screen
        state.asleep = False
        state.missed_wake = None
        self._save(state)
        self.service.status.note_app(now, hello.battery, hello.charging)
        self.contact.set()
        self.contact = asyncio.Event()

    def report(self, event: str, data: dict[str, object]) -> None:
        """What the app did: drew a picture, set its alarm, fell asleep, failed."""
        text = json.dumps(data, ensure_ascii=False)[:600]
        if event == "error":
            log.warning("panel app: %s", text)
        else:
            log.info("panel app %s: %s", event, text)
        if event == "sleep":
            self.service.status.note_sleep(deep=not self.state.standby)

    def next_wake(self, now: datetime) -> datetime:
        """The next change (or check, in the economy mode); on battery in the
        online mode also the start of quiet hours, so the Wi-Fi goes off
        for the night."""
        service = self.service
        settings = service.player.settings
        wake = service.power.next_wake(now)
        hours = quiet_hours(settings)
        if hours is not None and not in_quiet_hours(now, settings):
            wake = min(wake, _next_at(now, hours[0], settings.tz()))
        return min(wake, now + MAX_AHEAD)

    def _deep(self, now: datetime) -> bool:
        """The Wi-Fi off through the sleep: in the economy mode, and in quiet
        hours (on the charger the app does not sleep at all)."""
        settings = self.service.player.settings
        return settings.power_mode == "economy" or in_quiet_hours(now, settings)

    async def wait_for_contact(self, timeout: float) -> bool:
        try:
            await asyncio.wait_for(self.contact.wait(), timeout)
        except TimeoutError:
            return False
        return True

    def keep_awake(self, now: datetime) -> None:
        self.awake_until = now + KEEP_AWAKE
        self.sleep_requested = False

    def request_sleep(self) -> None:
        """ "Uśpij ramkę": the app sleeps at its next question."""
        self.awake_until = None
        self.sleep_requested = True

    async def tick(self, now: datetime) -> None:
        """After the app's alarm: start the app over MDC when it does not
        ask (a cold boot after a sleep with the Wi-Fi off), and note a wake
        it never showed up for."""
        state = self.state
        if not (state.active and state.asleep and state.wake_at):
            return
        wake = datetime.fromisoformat(state.wake_at)
        due = wake + KICK_AFTER <= now < wake + MISSED_AFTER
        if due and (self._kicked is None or now - self._kicked >= KICK_EVERY):
            self._kicked = now
            await self._kick()
            return
        if now >= wake + MISSED_AFTER and state.missed_wake != state.wake_at:
            state.missed_wake = state.wake_at
            self._save(state)
            log.warning("panel app did not wake at %s", state.wake_at)

    async def _kick(self) -> None:
        try:
            async with self.service.panel.session() as mdc:
                await mdc.set_content_source(CONTENT_SOURCE_CUSTOM)
        except MdcError as err:
            log.info("could not start the panel app after its alarm: %s", err)
            return
        log.info("panel app silent after its alarm: started it over MDC")

    # -- switching the panel over ---------------------------------------------

    def app_url(self) -> str:
        return f"{self.service.settings.base_url()}/panel/app"

    async def switch(self, on: bool) -> AppState:
        """Point the panel's launcher at our app (it installs it at once) or
        back to the source it had before."""
        if on and self.package() is None:
            raise MdcError("no app package uploaded yet")
        state = self.state
        async with self.service.panel.waking_session() as mdc:
            if on:
                current = await mdc.content_source()
                if current != CONTENT_SOURCE_CUSTOM:
                    state.previous_source = current
                await mdc.set_custom_app_url(self.app_url())
                await mdc.set_content_source(CONTENT_SOURCE_CUSTOM)
            else:
                source = state.previous_source
                await mdc.set_content_source(MOBILE_SOURCE if source is None else source)
        state.active = on
        state.asleep = False
        self._save(state)
        log.info("panel content source: %s", "Frame app" if on else "back to the previous one")
        return state

    def left(self) -> None:
        """The panel fetched content.json: it is not running our app."""
        state = self.state
        if state.active:
            state.active = False
            state.asleep = False
            self._save(state)
            log.info("the panel left the Frame app (it fetched content.json)")


def _s(delta: timedelta) -> int:
    return int(delta.total_seconds())


def _next_at(now: datetime, at: time, tz: ZoneInfo) -> datetime:
    local = now.astimezone(tz)
    moment = datetime.combine(local.date(), at, tzinfo=tz)
    return moment if moment > local else moment + timedelta(days=1)
