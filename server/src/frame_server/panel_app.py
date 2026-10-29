"""The frame's own app (Samsung "Custom" content source, docs/WAKE.md E16).

The panel always runs it: pictures are never pushed over MDC (the "Mobile"
source's content.json) any more. The panel asks for its pictures. On
every start and every wake it asks ``/panel/next`` what to show, how long to
sleep and whether to keep the Wi-Fi on; it draws the picture, sets its own
alarm (``webapis.epaper.setScheduleWakeupTime``) and goes to sleep. That
alarm is what the MDC on-timer could never be on firmware 1130.7, so the
economy mode works through the app, and in the online mode changes no
longer depend on Wake-on-LAN.

The alarms cannot be cancelled and the launcher sometimes reinstalls and
restarts the app as it goes to sleep, so the app keeps no plan of its own:
whenever it wakes, for whatever reason, it asks again.

After a sleep with the Wi-Fi off the panel boots cold and the launcher
mostly does not start the app: the server does, over MDC. A cold boot
alone leaves the screen as it is, while the app at every start drew its
picture again (~40 s of blinking). So for such a sleep the app sets the
alarms for every economy check up to the next change at once, and at a
check with nothing new the server does not start it: the panel just goes
back to sleep by itself, unredrawn. At the last of those alarms it always
starts the app, which sets the next ones. The app keeps the picture it
shows across starts and does not draw the same one again.

With ``base_screen_resolution`` "always" in its config.xml the app's page is
2560x1440, so it gets the very picture the Mobile source shows (passthrough
or our dither, whatever the settings render) and shows it 1:1.

The server builds and signs the package itself (panel_package.py) with the
Samsung certificates made for this panel, uploaded once to its data
directory. A new package is built whenever its files (config.xml,
index.html) or the server's address change; the app then reboots the panel
so the launcher installs it. The app's logic (``app.js``) comes from the
server at every start, so most changes need no new package.

When the panel does not run the app (a fresh panel, or one that fell back to
another source and fetched content.json) the server points its launcher at
the app and starts it over MDC (``0xC7 82 <url>``, ``0xC7 81 01``).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from zoneinfo import ZoneInfo

from PIL import Image
from pydantic import BaseModel

from .device import MdcConnectionError, MdcError
from .device.mdc import CONTENT_SOURCE_CUSTOM
from .panel_package import CertificateInfo, Certificates, sign_package
from .progress import Stage
from .schedule import in_quiet_hours, next_check, quiet_hours

if TYPE_CHECKING:
    from .service import FrameService
    from .store import ContentInfo

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
# The alarms the app sets for one sleep with the Wi-Fi off at most: the
# economy checks before the next change (every hour there can be more: the
# server starts the app at the last one set, and it sets the next ones).
MAX_ALARMS = 12
# After a sleep with the Wi-Fi off the panel boots cold, and the launcher
# does not start the app when it finds the same version on the server (E16):
# MDC 0xC7 81 01 does (5 of 5 within 10 s), so this is the usual way, not a
# fallback. Tried this long after the alarm, then every ``KICK_EVERY`` until
# the wake is missed.
KICK_AFTER = timedelta(seconds=60)
KICK_EVERY = timedelta(minutes=2)
# "Obudź ramkę" keeps the woken app awake (asking every ``POLL``) this long.
KEEP_AWAKE = timedelta(minutes=10)
# "Głęboki sen": the frame sleeps with the Wi-Fi off for up to this long.
REST_MAX = timedelta(days=3)
# Resting, the app asks again: a wake this close around an alarm set before
# the rest (alarms cannot be cancelled, E16), or this soon after it was put
# to sleep (the launcher restarts it at goToSleep now and then), puts it back
# to sleep; any other one is the button, which ends the rest.
STRAY_BEFORE = timedelta(minutes=2)
STRAY_AFTER = timedelta(minutes=12)
REST_SETTLE = timedelta(minutes=5)
# After the button's cold boot (any sleep with the Wi-Fi off: a rest, the
# economy mode, quiet hours, or unplugged) the launcher seldom starts the app
# (E16): the server looks for the panel over MDC this often and starts it.
# Asleep with the Wi-Fi off the panel is not on the network, so a look costs
# nothing but a failed connection.
BUTTON_LOOK_EVERY = timedelta(minutes=1)
# While the app is awake the server reads the battery over MDC (Tizen's
# systeminfo fails on the panel) at most this often.
BATTERY_EVERY = timedelta(minutes=10)
BATTERY_TIMEOUT = 10.0
# The panel does not run the app: point its launcher at it and start it this
# often while it is not asking (a panel asleep simply does not answer).
NUDGE_EVERY = timedelta(minutes=5)
# Awake, told to ask again within a minute, and silent this long: the app
# hung or quit, and 0xC7 81 01 restarts it. A few tries, then the panel is
# most likely asleep (unplugged: it sleeps at once, E8).
SILENT_AFTER = timedelta(minutes=3)
SILENT_KICKS = 3
# Awake, the app is heard from at least this often: a question every 20 s on
# the charger, a minute at most while it waits, progress reports during a
# long download. Silent longer it may well be asleep after all (unplugged,
# the panel sleeps at once, E8), so "Obudź ramkę" and a picture wake it.
HEARD_EVERY = timedelta(seconds=90)
# Server-built packages count from here, above the ones signed by hand (1.x).
FIRST_BUILD = (2, 0, 0)
# Warn in the iOS app this long before the certificates expire.
CERTIFICATES_WARN = timedelta(days=60)
# The panel needs an icon; any small PNG will do (1x1 white).
ICON = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC"
)
# A full-colour (passthrough) picture goes to the app as a JPEG (4:4:4): ~1 MB
# instead of 3-4 MB of PNG over the panel's weak Wi-Fi (60-215 KB/s), and
# the loss does not show (E16). A dithered one, a handful of inks, stays the
# lossless PNG.
JPEG_QUALITY = 95
DITHERED_COLOURS = 16
# The app reports when it has downloaded a picture and put it on the page;
# after a push the progress bar waits for that this long at most.
SHOWN_WAIT = 300.0


class AppState(BaseModel):
    active: bool = False  # the panel's content comes from our app
    seen_at: str | None = None  # the app's last question (ISO)
    build: str | None = None  # the installed package's version
    code: str | None = None  # the version of the logic it ran (app.js)
    screen: str | None = None  # the page as the app sees it, e.g. "2560x1440@1"
    asleep: bool = False  # told to sleep at its last question
    wake_at: str | None = None  # when its alarm wakes it (ISO)
    # Every alarm set for this sleep (ISO), the first one ``wake_at``.
    wakes: list[str] = []
    shown: str | None = None  # the picture on the screen (file_id), as the app says
    standby: bool = True  # network standby through that sleep
    missed_wake: str | None = None  # an alarm it did not show up for
    reboot_for: str | None = None  # the package version it last rebooted to install
    installed_at: str | None = None  # the server last started it over MDC (ISO)
    mode: str | None = None  # the power mode it went to sleep in
    slept_at: str | None = None  # told to sleep (ISO)
    # Asleep with the Wi-Fi off although it was to keep it on (or stay up):
    # unplugged, the panel sleeps at once and leaves the Wi-Fi (E8,
    # 2026-10-29). Only the button (or an alarm still set) wakes it.
    wifi_lost: bool = False
    # "Głęboki sen" until ``rest_until``, or switched off (no alarm at all):
    # the Wi-Fi off, no changes, only the button ends it.
    rest_until: str | None = None
    off: bool = False
    rested_at: str | None = None  # put to sleep for it (None: not yet)
    # Alarms set before the rest, still to ring (they cannot be cancelled).
    stray: list[str] = []


class AppHello(BaseModel):
    """What the app says when it asks (all optional: old builds say less)."""

    reason: str = "start"  # start, resume, wake, poll, retry
    build: str | None = None
    code: str | None = None
    screen: str | None = None
    battery: int | None = None  # percent
    charging: bool | None = None
    shown: str | None = None  # file_id on the screen, "" for none


class NextAnswer(BaseModel):
    """What the app does next. ``sleep``: draw ``image``, set the alarm to
    ``wake_ms`` and sleep with network standby ``standby``; ``stay``: draw
    and ask again in ``wait_s`` (on the charger); ``wait``: a change is
    being prepared, ask again in ``wait_s``; ``reboot``: restart the panel,
    so the launcher installs the package the server now offers."""

    action: Literal["sleep", "stay", "wait", "reboot"]
    file_id: str | None = None
    image: str | None = None
    title: str = ""
    wait_s: int = 0
    wake_at: str | None = None
    wake_ms: int | None = None
    # More alarms after ``wake_ms`` (a sleep with the Wi-Fi off), set at once.
    wakes_ms: list[int] = []
    standby: Literal["ON", "OFF"] = "ON"
    code: str = ""  # app.js on the server: a different one is loaded at once


class PackageInfo(BaseModel):
    version: str
    size: int
    uploaded_at: str  # when it was built
    source: str | None = None  # fingerprint of what it was built from


class AppView(BaseModel):
    """The app as the iOS app shows it."""

    active: bool
    package: PackageInfo | None
    state: AppState
    certificates: list[CertificateInfo] = []
    # The earliest expiry, when within ``CERTIFICATES_WARN`` (or past).
    certificates_expire_at: str | None = None


APP_DIR = Path(__file__).parent / "web" / "panel_app"


def app_code() -> bytes:
    return (APP_DIR / "app.js").read_bytes()


CODE_VERSION = hashlib.sha256(app_code()).hexdigest()[:10]


class PanelApp:
    def __init__(self, service: FrameService) -> None:
        self.service = service
        self.dir: Path = service.settings.data_dir / "panel-app"
        self.contact = asyncio.Event()  # set at every question of the app
        self.contacts = 0  # questions so far, to wait for the next one
        self.heard_at: datetime | None = None  # the last question or report
        self.awake_until: datetime | None = None
        self.sleep_requested = False
        self.restart_requested = False
        self._kicked: datetime | None = None
        self._nudged: datetime | None = None
        self._looked: datetime | None = None  # for the button in a rest
        self._silent_kicks = 0
        self._kick_error: MdcError | None = None  # why the last start failed
        self._next_alarm: datetime | None = None  # as the status shows it
        self.certificates = Certificates(self.dir / "certs")
        self._images: dict[str, str] = {}  # file_id -> the path the app gets
        self._shown: dict[str, asyncio.Event] = {}
        self._waiting: set[asyncio.Task[None]] = set()

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

    def awake(self, now: datetime | None = None) -> bool:
        """Running and heard from lately: it asks again within seconds. Not
        told to sleep but silent longer than ``HEARD_EVERY`` does not count."""
        state = self.state
        if not state.active or state.asleep:
            return False
        heard = self.heard_at or (datetime.fromisoformat(state.seen_at) if state.seen_at else None)
        return heard is not None and (now or datetime.now(UTC)) - heard < HEARD_EVERY

    def wakes_at(self, now: datetime | None = None) -> datetime | None:
        """When the sleeping app's alarm wakes it next (the last one once
        all have passed)."""
        state = self.state
        alarms = _alarms(state)
        if not (state.active and state.asleep and alarms):
            return None
        now = now or datetime.now(UTC)
        return next((a for a in alarms if a > now), alarms[-1])

    def deep_asleep(self) -> bool:
        """Asleep with the Wi-Fi off: only its alarm or the button wakes it."""
        state = self.state
        return state.active and state.asleep and not state.standby

    def mode_pending(self) -> str | None:
        """The power mode was changed while the app sleeps: it switches to
        it (returned) at its alarm or the button, not before; out of the
        economy mode's deep sleep nothing reaches it sooner."""
        state = self.state
        mode = self.service.player.settings.power_mode
        if not (state.active and state.asleep) or state.mode in (None, mode):
            return None
        return mode

    # -- the package ----------------------------------------------------------

    def package(self) -> PackageInfo | None:
        try:
            info = PackageInfo.model_validate_json((self.dir / "package.json").read_text())
        except (OSError, ValueError):
            return None
        return info if self.package_path().is_file() else None

    def package_path(self) -> Path:
        return self.dir / f"{WIDGET}.wgt"

    def package_files(self, version: str) -> dict[str, bytes]:
        """What goes into the package: the page, the fallback copy of the
        logic, config.xml with ``version`` and where the server is."""
        config = (APP_DIR / "config.xml").read_text()
        config = re.sub(r'version="[^"]*" viewmodes', f'version="{version}" viewmodes', config)
        where = (
            f'window.FRAME_SERVER = "{self.service.settings.base_url()}";\n'
            f'window.FRAME_BUILD = "{version}";\n'
        )
        return {
            "app.js": app_code(),
            "config.js": where.encode(),
            "config.xml": config.encode(),
            "icon.png": ICON,
            "index.html": (APP_DIR / "index.html").read_bytes(),
        }

    def source(self) -> str:
        """What a package depends on: a change means a new one. Not app.js,
        which the app loads from the server anyway."""
        digest = hashlib.sha256()
        for part in (
            (APP_DIR / "config.xml").read_bytes(),
            (APP_DIR / "index.html").read_bytes(),
            self.service.settings.base_url().encode(),
        ):
            digest.update(hashlib.sha256(part).digest())
        return digest.hexdigest()[:12]

    def ensure_package(self) -> PackageInfo | None:
        """The package for the current files and address, built and signed
        here when it is missing or out of date (and the certificates are
        there); a new version makes the app reboot the panel to install it."""
        current = self.package()
        source = self.source()
        if (current is not None and current.source == source) or not self.certificates.present():
            return current
        version = _next_version(current.version if current else None)
        try:
            data = sign_package(self.package_files(version), self.certificates)
        except (OSError, ValueError) as err:
            log.warning("could not build the frame's app: %s", err)
            return current
        return self.store_package(data, version, source)

    def store_certificates(self, author: bytes, distributor: bytes, password: bytes) -> AppView:
        """The Samsung certificates (once, and again when renewed): kept in
        the data directory, and a package built with them at once."""
        self.certificates.save(author, distributor, password)
        state = self.state
        if state.active:
            # Whatever ran so far, the next tick points the panel at the app
            # built with these and starts it; the app is back at its question.
            state.active = False
            self._save(state)
        self._nudged = None
        current = self.package()
        if current is not None and current.source is not None:
            # Signed with other certificates: build again.
            current.source = None
            (self.dir / "package.json").write_text(current.model_dump_json())
        self.ensure_package()
        self.service.power.publish_status()
        return self.view()

    def certificates_warning(self, now: datetime) -> str | None:
        """When the certificates expire, if that is soon (or past)."""
        expires = self.certificates.expires_at()
        if expires is None or expires - now > CERTIFICATES_WARN:
            return None
        return expires.isoformat(timespec="seconds")

    def store_package(self, data: bytes, version: str, source: str | None = None) -> PackageInfo:
        """A signed package; the app reboots the panel to install it at its
        next question (``answer``)."""
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / f"{WIDGET}.wgt.part"
        tmp.write_bytes(data)
        tmp.replace(self.package_path())
        info = PackageInfo(
            version=version,
            size=len(data),
            uploaded_at=datetime.now(UTC).isoformat(timespec="seconds"),
            source=source,
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
            f"<widgetname>{WIDGET}</widgetname>\n<webtype>tizen</webtype>\n</widget>\n"
        )

    def view(self) -> AppView:
        state = self.state
        return AppView(
            active=state.active,
            package=self.package(),
            state=state,
            certificates=self.certificates.info(),
            certificates_expire_at=self.certificates_warning(datetime.now(UTC)),
        )

    # -- the app's questions --------------------------------------------------

    async def ask(self, hello: AppHello) -> NextAnswer:
        """``answer``, with the battery and charger read over MDC first when
        the last read is old (Tizen's systeminfo fails on the panel): on the
        charger the app stays awake."""
        self.ensure_package()  # the files or the address changed: a new one
        status = self.service.status
        checked = status.status.checked_at
        now = datetime.now(UTC)
        stale = checked is None or now - datetime.fromisoformat(checked) >= BATTERY_EVERY
        if stale and hello.charging is None and self.service.device_configured:
            try:
                await asyncio.wait_for(status.refresh(force=True), BATTERY_TIMEOUT)
            except (TimeoutError, MdcError) as err:
                log.info("no battery reading for the app: %s", err)
        waiting = self.service.power.state.pending_push
        answer = self.answer(hello)
        if waiting and answer.action != "reboot" and answer.file_id not in (None, hello.shown):
            self._deliver(answer)
        return answer

    def _deliver(self, answer: NextAnswer) -> None:
        """The picture that waited for the panel goes to it now (it woke:
        the button, an alarm): the progress bar in the iOS app shows its
        download and refresh as for a picture sent."""
        assert answer.file_id is not None
        progress = self.service.progress
        if not progress.active:
            progress.begin(answer.title, render=False, start=Stage.DOWNLOADING)
        progress.advance(Stage.DOWNLOADING)
        self.follow(answer.file_id)
        log.info("the waiting picture %s goes to the frame's app", answer.file_id)

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
                "image": f"{service.settings.base_url()}{self.image_path(content)}",
                "title": content.title,
            }
        if self._resting(now):
            return self._rest(now, common)
        if self.restart_requested:
            self.restart_requested = False
            return self._reboot(None, now, common)
        package = self.package()
        newer = package is not None and hello.build and hello.build != package.version
        if newer and package is not None and self.state.reboot_for != package.version:
            return self._reboot(package.version, now, common)
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
        alarms = [wake] if standby else self.alarms(now, wake)
        state = self.state
        state.asleep = True
        state.wake_at = wake.isoformat(timespec="seconds")
        state.wakes = [a.isoformat(timespec="seconds") for a in alarms]
        state.standby = standby
        state.mode = self.service.player.settings.power_mode
        state.slept_at = now.isoformat(timespec="seconds")
        state.wifi_lost = False
        self._save(state)
        return NextAnswer(
            action="sleep",
            wake_at=state.wake_at,
            wake_ms=_ms(wake),
            wakes_ms=[_ms(a) for a in alarms[1:]],
            standby="ON" if standby else "OFF",
            **common,
        )

    # -- "Głęboki sen" and "Wyłącz ramkę" ---------------------------------------

    def request_rest(self, now: datetime, until: datetime | None) -> None:
        """Sleep with the Wi-Fi off until ``until`` (at most ``REST_MAX``),
        or with no alarm at all (None, "Wyłącz ramkę"), from the app's next
        question on. Only the button (or the end) wakes it; the schedule's
        changes wait."""
        state = self.state
        state.off = until is None
        state.rest_until = (
            None if until is None else min(until, now + REST_MAX).isoformat(timespec="seconds")
        )
        state.rested_at = None
        self._save(state)
        self.awake_until = None
        self.sleep_requested = False
        log.info(
            "frame %s",
            "switched off" if until is None else f"to deep sleep until {state.rest_until}",
        )

    def end_rest(self, why: str) -> None:
        state = self.state
        if not (state.off or state.rest_until):
            return
        state.off = False
        state.rest_until = None
        state.rested_at = None
        state.stray = []
        self._save(state)
        log.info("frame rest over: %s", why)

    def rest_pending(self) -> bool:
        """A rest asked for, not yet slept into."""
        state = self.state
        return (state.off or state.rest_until is not None) and state.rested_at is None

    def _resting(self, now: datetime) -> bool:
        """Whether this question gets the rest's sleep: asked for and not
        over yet, and the app does not ask because of the button."""
        state = self.state
        if not (state.off or state.rest_until):
            return False
        if (
            state.rest_until is not None
            and now >= datetime.fromisoformat(state.rest_until) - MIN_SLEEP
        ):
            self.end_rest("its end")
            return False
        if state.rested_at is None:
            return True
        if now - datetime.fromisoformat(state.rested_at) < REST_SETTLE:
            return True  # restarted by the launcher as it went to sleep
        strays = [datetime.fromisoformat(a) for a in state.stray]
        if any(a - STRAY_BEFORE <= now <= a + STRAY_AFTER for a in strays):
            return True  # an old alarm rang: back to sleep
        self.end_rest("the button")
        return False

    def _rest(self, now: datetime, common: dict[str, object]) -> NextAnswer:
        state = self.state
        until = datetime.fromisoformat(state.rest_until) if state.rest_until else None
        # Whatever alarms were set so far still ring (minus the ones past).
        set_before = {a.isoformat(timespec="seconds") for a in _alarms(state) if a > now}
        strays = {a for a in state.stray if datetime.fromisoformat(a) + STRAY_AFTER > now}
        if state.rested_at is None:
            strays |= set_before
        state.stray = sorted(strays)
        state.rested_at = now.isoformat(timespec="seconds")
        state.asleep = True
        state.wake_at = state.rest_until
        state.wakes = [state.rest_until] if state.rest_until else []
        state.standby = False
        state.mode = self.service.player.settings.power_mode
        state.slept_at = state.rested_at
        state.wifi_lost = False
        self._save(state)
        return NextAnswer(
            action="sleep",
            wake_at=state.rest_until,
            wake_ms=_ms(until) if until else None,
            standby="OFF",
            **common,
        )

    def alarms(self, now: datetime, wake: datetime) -> list[datetime]:
        """The alarms for a sleep with the Wi-Fi off: ``wake`` and every
        economy check after it up to the next change."""
        settings = self.service.player.settings
        change = self.service.power.next_change_wake(now)
        alarms = [wake]
        while alarms[-1] < change and len(alarms) < MAX_ALARMS:
            check = next_check(alarms[-1], settings)
            alarms.append(check if check is not None and check < change else change)
        return [a for a in alarms if a - now <= MAX_AHEAD]

    def _reboot(self, version: str | None, now: datetime, common: dict[str, object]) -> NextAnswer:
        """The app reboots the panel (``webapis.systemcontrol.rebootDevice``):
        for a newer package (``version``), which the launcher installs at the
        cold boot, or for "Uruchom ponownie" from the iOS app (None). The
        launcher does not start the app after it, so ``tick`` does over MDC
        (E16, tested 2026-10-28). Once per version, so a package that does
        not install cannot keep the panel rebooting."""
        state = self.state
        if version is not None:
            state.reboot_for = version
        state.asleep = True
        state.wake_at = now.isoformat(timespec="seconds")  # back in a minute
        state.wakes = []
        state.shown = None  # the boot and the install draw over it
        self._save(state)
        if version is None:
            log.info("panel app %s reboots the panel, as asked from the app", state.build)
        else:
            log.info("panel app %s reboots to install %s", state.build, version)
        return NextAnswer(action="reboot", **common)

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
        package = self.package()
        if hello.build and package is not None and hello.build != package.version:
            # The launcher checks the version as the panel goes to sleep and
            # installs (and redraws) whatever sssp_config.xml offers (E16).
            log.warning(
                "the panel runs Frame app %s but the server offers %s: it will reinstall",
                hello.build,
                package.version,
            )
        state.build = hello.build or state.build
        state.code = hello.code or state.code
        state.screen = hello.screen or state.screen
        if hello.shown is not None:
            state.shown = hello.shown or None
        state.asleep = False
        state.wifi_lost = False
        state.missed_wake = None
        self._save(state)
        self._silent_kicks = 0
        self.heard_at = now
        self.service.status.note_app(now, hello.battery, hello.charging)
        self.contacts += 1
        self.contact.set()
        self.contact = asyncio.Event()

    def report(self, event: str, data: dict[str, object]) -> None:
        """What the app did: drew a picture, set its alarm, fell asleep, failed."""
        text = json.dumps(data, ensure_ascii=False)[:600]
        if event != "sleep":
            self.heard_at = datetime.now(UTC)
        if event == "error":
            log.warning("panel app: %s", text)
        else:
            log.info("panel app %s: %s", event, text)
        if event == "sleep":
            self.service.status.note_sleep(deep=not self.state.standby)
        elif event == "progress":
            loaded, total = data.get("loaded"), data.get("total")
            if isinstance(loaded, int | float) and isinstance(total, int | float) and total > 0:
                self.service.progress.note_download(loaded / total)
        elif event == "wifi":
            self.service.status.note_wifi(data)
        elif event == "shown":
            file_id = str(data.get("file_id", ""))
            state = self.state
            if file_id and state.shown != file_id:
                state.shown = file_id
                self._save(state)
            shown = self._shown.pop(file_id, None)
            if shown is not None:
                shown.set()

    # -- pictures -------------------------------------------------------------

    def image_path(self, content: ContentInfo) -> str:
        """What the app downloads for ``content``: the Mobile source's picture,
        as a JPEG when it is full colour."""
        path = self._images.get(content.file_id)
        if path is None:
            jpeg = self.picture(content.file_id)
            path = (
                f"/panel/app-images/{content.file_id}.jpg"
                if jpeg is not None
                else f"/panel/images/{content.file_name}"
            )
            self._images = {content.file_id: path}  # only the current one
        return path

    def picture(self, file_id: str) -> Path | None:
        """The JPEG copy of a full-colour picture (made once); None for a
        dithered one or an unknown ``file_id``."""
        store = self.service.store
        path = store.app_image_path(file_id)
        if path.is_file():
            return path
        source = store.panel_file(file_id)
        if source is None:
            return None
        try:
            with Image.open(source) as img:
                if img.mode == "P" or img.getcolors(DITHERED_COLOURS) is not None:
                    return None
                img.convert("RGB").save(path, "JPEG", quality=JPEG_QUALITY, subsampling=0)
        except OSError as err:  # the panel gets it as it is
            log.warning("no JPEG of %s for the panel app: %s", source.name, err)
            return None
        return path

    def follow(self, file_id: str) -> None:
        """A push reached the app: the bar moves on to the refresh once the
        app has the whole picture on its page (or after ``SHOWN_WAIT``)."""
        shown = self._shown[file_id] = asyncio.Event()

        async def wait() -> None:
            try:
                await asyncio.wait_for(shown.wait(), SHOWN_WAIT)
            except TimeoutError:
                log.info("the panel app did not report %s shown", file_id)
            self._shown.pop(file_id, None)
            self.service.progress.advance(Stage.REFRESHING)

        task = asyncio.create_task(wait())
        self._waiting.add(task)
        task.add_done_callback(self._waiting.discard)

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

    async def wait_for_contact(self, timeout: float, since: int | None = None) -> bool:
        """Whether the app asks within ``timeout``; with ``since`` (a count
        of ``contacts``) a question already asked after it counts too."""
        if since is not None and self.contacts > since:
            return True
        try:
            await asyncio.wait_for(self.contact.wait(), timeout)
        except TimeoutError:
            return False
        return True

    async def panel_answers(self) -> bool:
        """Whether the panel is up: it accepts an MDC session (asleep it
        does not)."""
        try:
            async with self.service.panel.session():
                return True
        except MdcConnectionError:
            return False
        except MdcError:
            return True  # it answered, and something else went wrong

    def keep_awake(self, now: datetime) -> None:
        self.end_rest("woken from the app")
        self.awake_until = now + KEEP_AWAKE
        self.sleep_requested = False

    def request_restart(self) -> None:
        """ "Uruchom ponownie": the app reboots the panel at its next question."""
        self.restart_requested = True
        self.sleep_requested = False

    def request_sleep(self) -> None:
        """ "Uśpij ramkę": the app sleeps at its next question."""
        self.end_rest("put to sleep from the app")
        self.awake_until = None
        self.sleep_requested = True

    async def tick(self, now: datetime) -> None:
        """Keep the app running: start it after its alarm when it does not
        ask (a cold boot after a sleep with the Wi-Fi off), restart it when it
        went silent while awake, note a wake it never showed up for, and
        point the panel at it again when it is not running or has not been
        heard of for long."""
        state = self.state
        seen = datetime.fromisoformat(state.seen_at) if state.seen_at else None
        if self.heard_at is not None and (seen is None or self.heard_at > seen):
            seen = self.heard_at  # a long download: it reports, not asks
        silent = seen is None or now - seen >= SILENT_AFTER
        if self.wakes_at(now) != self._next_alarm:
            # An alarm rang and the panel went back to sleep: show the next.
            self._next_alarm = self.wakes_at(now)
            self.service.power.publish_status()
        # The alarm that last rang, if the app has to run for it.
        wake = self._rung(now) if state.asleep else None
        missed = wake is not None and now >= wake + MISSED_AFTER
        rung = wake.isoformat(timespec="seconds") if wake is not None else None
        if state.active and missed and state.missed_wake != rung:
            state.missed_wake = rung
            self._save(state)
            log.warning("panel app did not wake at %s", rung)
        lost = (
            not state.active
            or missed
            or (not state.asleep and silent and self._silent_kicks >= SILENT_KICKS)
        )
        if lost:
            # Whatever the launcher points at (another source, another
            # server's app): ours, started, whenever the panel answers.
            if self._nudged is None or now - self._nudged >= NUDGE_EVERY:
                self._nudged = now
                await self._nudge()
            return
        if not state.asleep:
            due = self._kicked is None or now - self._kicked >= KICK_EVERY
            if silent and due and self._silent_kicks < SILENT_KICKS:
                self._kicked = now
                self._silent_kicks += 1
                log.info("the frame's app has been silent since %s", state.seen_at)
                if not await self._kick():
                    await self._fell_asleep()
            return
        if self._button_look_due(now):
            # Up although nothing rang: the button. Started, the app asks (a
            # rest is over, a waiting picture goes out).
            self._looked = now
            await self._kick(quiet=True)
            return
        after_alarm = wake is not None and wake + KICK_AFTER <= now
        if after_alarm and (self._kicked is None or now - self._kicked >= KICK_EVERY):
            self._kicked = now
            await self._kick()

    def _rung(self, now: datetime) -> datetime | None:
        """The last alarm at or before ``now``, when the app has to run for
        it: the last one set (the app sets the next ones), or there is
        something new to show or another power mode to switch to. At any
        other the panel, left alone, goes back to sleep by itself without
        redrawing the screen."""
        state = self.state
        alarms = [a for a in _alarms(state) if a <= now]
        if not alarms:
            return None
        wake = alarms[-1]
        if wake == _alarms(state)[-1]:
            return wake
        content = self.service.store.current()
        power = self.service.power
        new = content is not None and content.file_id != state.shown
        news = new or power.state.pending_push or power.change_due(now)
        return wake if news or self.mode_pending() is not None or self.rest_pending() else None

    def _button_look_due(self, now: datetime) -> bool:
        """Asleep with the Wi-Fi off (a rest, the economy mode, quiet hours,
        unplugged), settled, no alarm about to ring or ringing (at a check
        with nothing new the panel is left alone), and not looked for a
        while: time to see whether the button woke it."""
        state = self.state
        if not state.asleep or state.standby:
            return False
        since = state.rested_at or state.slept_at
        if since is not None and now - datetime.fromisoformat(since) < REST_SETTLE:
            # Still going down, or restarted by the launcher as it does.
            return False
        if any(
            datetime.fromisoformat(a) - STRAY_BEFORE
            <= now
            <= datetime.fromisoformat(a) + STRAY_AFTER
            for a in [*state.stray, *state.wakes]
        ):
            return False
        return self._looked is None or now - self._looked >= BUTTON_LOOK_EVERY

    async def _fell_asleep(self) -> None:
        """Not told to sleep, silent, and the panel does not answer MDC: it
        went to sleep by itself, with no alarm of ours. Most likely it was
        unplugged: the panel sleeps at once then and leaves the Wi-Fi,
        whatever network standby says (E8; 2026-10-29 it did not answer ARP
        and Wake-on-LAN did not reach it, the button did). On the charger
        the app never sleeps. Whether it is still on the Wi-Fi is asked
        (ARP): if so, a picture and "Obudź ramkę" send Wake-on-LAN; if not
        (or it cannot be told and it was on the charger), only the button
        wakes it, and the server looks for it over MDC to start the app."""
        status = self.service.status
        unplugged = status.status.power_source == "ac"
        on_network = await status.look_for_panel(self._kick_error)
        wifi = on_network is True or (on_network is None and not unplugged)
        state = self.state
        state.asleep = True
        state.standby = wifi
        state.wifi_lost = not wifi
        state.wake_at = None
        state.wakes = []
        state.slept_at = None  # down already: the panel did not answer
        self._save(state)
        status.note_fell_asleep(on_network, unplugged=unplugged, wifi=wifi)
        log.warning(
            "the frame's app fell silent and the panel does not answer: asleep by itself, %s",
            "in the network" if wifi else "without the Wi-Fi (only the button wakes it)",
        )

    def lost_wifi(self, now: datetime) -> bool:
        """A look found the panel off the Wi-Fi (no ARP answer): an app taken
        to sleep in the network, or silent for a while, is asleep without
        the Wi-Fi after all (unplugged), and Wake-on-LAN cannot reach it.
        The alarm it set still rings. Whether that changed anything."""
        state = self.state
        if not state.active or self.awake(now) or (state.asleep and not state.standby):
            return False
        if not state.asleep:
            state.wake_at = None
            state.wakes = []
        state.asleep = True
        state.standby = False
        state.wifi_lost = True
        state.slept_at = None
        self._save(state)
        log.warning("the frame is not on the Wi-Fi: asleep without it, only the button wakes it")
        return True

    async def _kick(self, quiet: bool = False, why: str = "was silent") -> bool:
        """Start the app (or restart a hung one): selecting the Custom source
        again starts it. The launcher's address is set again first, so a
        panel left pointing elsewhere (a test server) comes back to ours.
        ``quiet``: only looking whether the panel is up (a rest). Whether the
        panel answered."""
        self._kick_error = None
        try:
            async with self.service.panel.session() as mdc:
                await mdc.set_custom_app_url(self.app_url())
                await mdc.set_content_source(CONTENT_SOURCE_CUSTOM)
        except MdcError as err:
            self._kick_error = err
            if not quiet:
                log.info("could not start the frame's app: %s", err)
            return not isinstance(err, MdcConnectionError)
        log.info("the frame's app %s: started it over MDC", "woke by the button" if quiet else why)
        return True

    async def start(self, why: str) -> bool:
        """Start (or restart) the app over MDC, if the panel answers."""
        return await self._kick(why=why)

    async def _nudge(self) -> None:
        """The panel does not run the app: install and start it, if the
        panel answers (asleep it does not, and is left alone)."""
        if self.ensure_package() is None:
            return
        try:
            await self.install(waking=False)
        except MdcError as err:
            log.info("could not start the frame's app: %s", err)

    # -- getting the app onto the panel -----------------------------------------

    def app_url(self) -> str:
        return f"{self.service.settings.base_url()}/panel/app"

    async def install(self, waking: bool = True) -> AppState:
        """Point the panel's launcher at the app and select it: it installs
        the package (when the version differs) and starts the app at once.
        ``waking``: Wake-on-LAN when the panel does not answer."""
        if self.ensure_package() is None:
            raise MdcError("no app package: upload the Samsung certificates first")
        panel = self.service.panel
        async with panel.waking_session() if waking else panel.session() as mdc:
            await mdc.set_custom_app_url(self.app_url())
            await mdc.set_content_source(CONTENT_SOURCE_CUSTOM)
        state = self.state
        state.asleep = False
        state.installed_at = datetime.now(UTC).isoformat(timespec="seconds")
        self._save(state)
        log.info("the panel's launcher points at the frame's app: started it")
        return state

    def left(self) -> None:
        """The panel fetched content.json: its launcher is on another source
        (Mobile), not the app. The next tick starts the app again."""
        state = self.state
        self._nudged = None
        if state.active:
            state.active = False
            state.asleep = False
            self._save(state)
            self.service.status.forget_wifi()
            log.warning("the panel left the frame's app (it fetched content.json)")


def _next_version(previous: str | None) -> str:
    """The next server-built version: x.y.z with z one up, from 2.0.0."""
    try:
        parts = tuple(int(p) for p in (previous or "").split("."))
    except ValueError:
        parts = ()
    if len(parts) != 3 or parts < FIRST_BUILD:
        return ".".join(map(str, FIRST_BUILD))
    return f"{parts[0]}.{parts[1]}.{parts[2] + 1}"


def _alarms(state: AppState) -> list[datetime]:
    wakes = state.wakes or ([state.wake_at] if state.wake_at else [])
    return [datetime.fromisoformat(w) for w in wakes]


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _s(delta: timedelta) -> int:
    return int(delta.total_seconds())


def _next_at(now: datetime, at: time, tz: ZoneInfo) -> datetime:
    local = now.astimezone(tz)
    moment = datetime.combine(local.date(), at, tzinfo=tz)
    return moment if moment > local else moment + timedelta(days=1)
