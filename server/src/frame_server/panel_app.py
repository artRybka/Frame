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

from .device import MdcError
from .device.mdc import CONTENT_SOURCE_CUSTOM
from .panel_package import CertificateInfo, Certificates, sign_package
from .progress import Stage
from .schedule import in_quiet_hours, quiet_hours

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
# After a sleep with the Wi-Fi off the panel boots cold, and the launcher
# does not start the app when it finds the same version on the server (E16):
# MDC 0xC7 81 01 does (5 of 5 within 10 s), so this is the usual way, not a
# fallback. Tried this long after the alarm, then every ``KICK_EVERY`` until
# the wake is missed.
KICK_AFTER = timedelta(seconds=60)
KICK_EVERY = timedelta(minutes=2)
# "Obudź ramkę" keeps the woken app awake (asking every ``POLL``) this long.
KEEP_AWAKE = timedelta(minutes=10)
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
    standby: bool = True  # network standby through that sleep
    missed_wake: str | None = None  # an alarm it did not show up for
    reboot_for: str | None = None  # the package version it last rebooted to install
    installed_at: str | None = None  # the server last started it over MDC (ISO)


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
    being prepared, ask again in ``wait_s``; ``reboot``: restart the panel,
    so the launcher installs the package the server now offers."""

    action: Literal["sleep", "stay", "wait", "reboot"]
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
        self.awake_until: datetime | None = None
        self.sleep_requested = False
        self._kicked: datetime | None = None
        self._nudged: datetime | None = None
        self._silent_kicks = 0
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
                "image": f"{service.settings.base_url()}{self.image_path(content)}",
                "title": content.title,
            }
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

    def _reboot(self, version: str, now: datetime, common: dict[str, object]) -> NextAnswer:
        """A newer package is on the server: the app reboots the panel
        (``webapis.systemcontrol.rebootDevice``), the launcher installs it
        at the cold boot but does not start it, so ``tick`` does over MDC
        (E16, tested 2026-10-28). Once per version, so a package that does
        not install cannot keep the panel rebooting."""
        state = self.state
        state.reboot_for = version
        state.asleep = True
        state.wake_at = now.isoformat(timespec="seconds")  # back in a minute
        self._save(state)
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
        state.asleep = False
        state.missed_wake = None
        self._save(state)
        self._silent_kicks = 0
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
        elif event == "progress":
            loaded, total = data.get("loaded"), data.get("total")
            if isinstance(loaded, int | float) and isinstance(total, int | float) and total > 0:
                self.service.progress.note_download(loaded / total)
        elif event == "wifi":
            self.service.status.note_wifi(data)
        elif event == "shown":
            shown = self._shown.pop(str(data.get("file_id", "")), None)
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
        """Keep the app running: start it after its alarm when it does not
        ask (a cold boot after a sleep with the Wi-Fi off), restart it when it
        went silent while awake, note a wake it never showed up for, and
        point the panel at it again when it is not running or has not been
        heard of for long."""
        state = self.state
        seen = datetime.fromisoformat(state.seen_at) if state.seen_at else None
        silent = seen is None or now - seen >= SILENT_AFTER
        wake = datetime.fromisoformat(state.wake_at) if state.wake_at else None
        missed = state.asleep and wake is not None and now >= wake + MISSED_AFTER
        if state.active and missed and state.missed_wake != state.wake_at:
            state.missed_wake = state.wake_at
            self._save(state)
            log.warning("panel app did not wake at %s", state.wake_at)
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
                await self._kick()
            return
        after_alarm = wake is not None and wake + KICK_AFTER <= now
        if after_alarm and (self._kicked is None or now - self._kicked >= KICK_EVERY):
            self._kicked = now
            await self._kick()

    async def _kick(self) -> None:
        """Start the app (or restart a hung one): selecting the Custom source
        again starts it. The launcher's address is set again first, so a
        panel left pointing elsewhere (a test server) comes back to ours."""
        try:
            async with self.service.panel.session() as mdc:
                await mdc.set_custom_app_url(self.app_url())
                await mdc.set_content_source(CONTENT_SOURCE_CUSTOM)
        except MdcError as err:
            log.info("could not start the frame's app: %s", err)
            return
        log.info("the frame's app was silent: started it over MDC")

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


def _s(delta: timedelta) -> int:
    return int(delta.total_seconds())


def _next_at(now: datetime, at: time, tz: ZoneInfo) -> datetime:
    local = now.astimezone(tz)
    moment = datetime.combine(local.date(), at, tzinfo=tz)
    return moment if moment > local else moment + timedelta(days=1)
