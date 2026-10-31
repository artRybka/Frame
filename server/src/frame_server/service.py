"""Application services: render + publish content, drive the panel."""

from __future__ import annotations

import asyncio
import io
import logging
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PIL import Image

from .ai import AiConfigStore, AiWorker, Claude, DailyJob, KeywordsJob, PlTextJob
from .ai.study import StudyJob
from .albums import Albums
from .config import Settings
from .daily import Daily
from .device import MdcClient, MdcConnectionError, MdcError, wol
from .imaging import Palette, RenderSettings, get_palette, render, render_multi
from .imaging.pipeline import encode_image
from .library import ImageCache, Importer, Library
from .library.commons import repair_library
from .library.museums import Access, europeana_mirrors
from .library.museums import client as museum_client
from .panel_app import POLL, PanelApp
from .panel_config import PanelConfigStore
from .player import Player
from .power import INSTALL_LOOK, WAKE_BURST_SECONDS, PowerManager
from .progress import ProgressTracker, Stage
from .rendered import RenderCache, Rendered, render_key
from .status import StatusMonitor
from .storage import StorageStore
from .store import ContentInfo, ContentStore
from .study import Study

log = logging.getLogger(__name__)

PREVIEW_MAX = 1280
# The Frame app's alarm rings this close to a push: it will ask by itself.
WAKE_SOON = timedelta(minutes=3)
PROGRESS_KEY = "progress_expected"
NO_CERTIFICATES = (
    "no app for the frame: copy the Samsung certificates to data/panel-app/certs on the server"
)


@dataclass
class PushOutcome:
    content: ContentInfo
    pushed: bool
    fetched: bool
    content_url: str
    message: str = ""


class Panel:
    """Serialises access to the panel (it accepts one MDC session at a time)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = asyncio.Lock()
        self.on_wake: Callable[[], None] | None = None  # e.g. to show "waking" in the app
        self.woke = False  # the last waking session had to wake it

    def client(self) -> MdcClient:
        host, pin = self.settings.require_device()
        return MdcClient(host, pin, self.settings.device_port)

    async def wake(self, seconds: int = 0) -> bool:
        """Wake-on-LAN; with ``seconds`` a packet a second for that long (a
        dozing Wi-Fi client only listens every few beacons)."""
        if not self.settings.device_mac:
            return False
        if seconds:
            await wol.wake(
                self.settings.device_mac, self.settings.device_host, repeats=seconds, interval=1.0
            )
        else:
            await wol.wake(self.settings.device_mac, self.settings.device_host)
        return True

    @asynccontextmanager
    async def waking_session(self) -> AsyncIterator[MdcClient]:
        """A session, waking the panel with Wake-on-LAN if it does not answer."""
        async with self._lock:
            client = self.client()
            self.woke = False
            try:
                await client.connect(attempts=2, retry_delay=5)
            except MdcConnectionError:
                if not self.settings.device_mac:
                    raise
                self.woke = True
                if self.on_wake:
                    self.on_wake()
                # On battery the panel answers one to three minutes into the
                # burst (E13): keep sending until it does.
                log.info("panel unreachable, sending Wake-on-LAN")
                burst = asyncio.create_task(self.wake(seconds=WAKE_BURST_SECONDS))
                try:
                    await self._connect_until(client, WAKE_BURST_SECONDS + 10)
                finally:
                    burst.cancel()
            try:
                yield client
            finally:
                await client.close()

    @staticmethod
    async def _connect_until(client: MdcClient, seconds: float) -> None:
        """Try to connect every few seconds until ``seconds`` have passed."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + seconds
        while True:
            await asyncio.sleep(5)
            try:
                await client.connect()
                return
            except MdcConnectionError:
                if loop.time() >= deadline:
                    raise

    @asynccontextmanager
    async def session(self) -> AsyncIterator[MdcClient]:
        """One short MDC session, never overlapping with another."""
        async with self._lock, self.client() as mdc:
            yield mdc

    async def sleep(self) -> None:
        """Power off but keep network standby, so Wake-on-LAN still works."""
        async with self.session() as mdc:
            await self.power_off(mdc)

    @staticmethod
    async def power_off(mdc: MdcClient) -> None:
        await mdc.set_network_standby(True)
        await mdc.set_power(False)


class FrameService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = ContentStore(settings.data_dir)
        self.panel = Panel(settings)
        self.progress = ProgressTracker()
        self.rendered = RenderCache()
        self.panel.on_wake = lambda: self.progress.advance(Stage.WAKING)
        self.palette: Palette = self._initial_palette()
        self.library = Library(settings.data_dir / "library.db")
        if repaired := repair_library(self.library):
            log.info("repaired stored text and links of %d items", repaired)
        # Before anything reads the panel's address: the app's values win.
        self.panel_config = PanelConfigStore(settings, self.library)
        self.images = ImageCache(settings.data_dir / "library", museum_client)
        self.images.mirrors["europeana"] = europeana_mirrors
        # Before the player trims or grows the catalogue: the app's limit wins.
        self.storage = StorageStore(settings, self.library, self.images, self.store)
        self.importer = Importer(
            self.library,
            self.images,
            self.palette,
            access=self._access,
        )
        self.status = StatusMonitor(self.panel, self.library)
        self.progress.restore(self.library.get_state(PROGRESS_KEY, {}))
        self.progress.on_learn = lambda learned: self.library.set_state(PROGRESS_KEY, learned)
        self.progress.likely_asleep = lambda: self.status.sleeping
        self.app = PanelApp(self)
        self.player = Player(self)
        self.power = PowerManager(self)
        self.albums = Albums(self)
        # The language model: keywords and Polish texts; idle without a key.
        self.ai_config = AiConfigStore(settings, self.library)
        self.claude = Claude(self.ai_config, self.library)
        self.ai = AiWorker(self.library, self.images, self.claude, self.ai_config)
        self.ai.register(KeywordsJob(self.library, self.images, self.ai_config))
        self.pl_text = PlTextJob(self.library, self.images, self.ai_config)
        self.ai.register(self.pl_text)
        # Discover's work of the day and its page.
        self.daily = Daily(
            self.library,
            self.player,
            self.ai,
            DailyJob(self.library, self.images, self.ai_config),
        )
        self.ai.register(self.daily.job)
        # Studies of any work, asked for on its card.
        self.study = Study(self.daily, self.ai, StudyJob(self.library, self.images, self.ai_config))
        self.ai.register(self.study.job)

        self._tasks: set[asyncio.Task[object]] = set()

    def _access(self) -> Access:
        """What the owner lets art sources return, and their credentials."""
        chosen, config = self.player.settings, self.settings
        app = None
        if config.openverse_client_id and config.openverse_client_secret:
            app = (config.openverse_client_id, config.openverse_client_secret)
        return Access(
            private_use=chosen.private_use,
            wikiart=chosen.wikiart,
            europeana_key=config.europeana_key,
            openverse_app=app,
        )

    @property
    def calibrated_palette_path(self) -> Path:
        return self.settings.data_dir / "palette.json"

    def _initial_palette(self) -> Palette:
        # A palette measured in the app wins over the configured default.
        path = self.calibrated_palette_path
        if path.is_file():
            try:
                return Palette.load(path)
            except (OSError, ValueError, KeyError) as err:
                log.warning("ignoring unreadable %s: %s", path, err)
        return get_palette(self.settings.palette)

    def set_palette(self, palette: Palette | None) -> Palette:
        """Use and keep a calibrated palette; None goes back to the default."""
        if palette is None:
            self.calibrated_palette_path.unlink(missing_ok=True)
            palette = get_palette(self.settings.palette)
        else:
            self.settings.data_dir.mkdir(parents=True, exist_ok=True)
            palette.save(self.calibrated_palette_path)
        self.palette = palette
        self.importer.palette = palette
        return palette

    @property
    def device_configured(self) -> bool:
        return bool(self.settings.device_host and self.settings.device_pin)

    def background(self, coro: Coroutine[object, object, object]) -> asyncio.Task[object]:
        """Run a coroutine after the response; keeps a reference until done."""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def prepare(
        self,
        image: bytes | list[bytes],
        render_settings: RenderSettings | None,
        *,
        raw: bool = False,
        fmt: str | None = None,
        title: str = "",
        description: str = "",
        source: str = "",
        extra: dict[str, object] | None = None,
        seed: str = "",
    ) -> ContentInfo:
        """Render (or pass through untouched with ``raw``) and publish.

        Several images are one board of photos (MULTI); ``seed`` keeps its
        automatic grid the same on a redraw."""
        if raw and not isinstance(image, list):
            img = Image.open(io.BytesIO(image))
            ext = "png" if img.format == "PNG" else "jpg"
            if img.format not in ("PNG", "JPEG"):
                image, ext = encode_image(img.convert("RGB"), "png"), "png"
            preview = img.convert("RGB")
            preview.thumbnail((PREVIEW_MAX, PREVIEW_MAX))
            return self.store.publish(
                image,
                ext,
                preview_png=encode_image(preview, "png"),
                title=title,
                description=description,
                source=source,
                render={"raw": True},
            )

        settings = render_settings or RenderSettings()
        done = self.render_content(image, settings, fmt=fmt, seed=seed)
        return self.store.publish(
            done.data,
            done.ext,
            preview_png=done.preview_png,
            title=title,
            description=description,
            source=source,
            render=settings.model_dump(mode="json") | {"palette": self.palette.name},
            extra=extra,
        )

    def render_content(
        self,
        image: bytes | list[bytes],
        settings: RenderSettings,
        *,
        fmt: str | None = None,
        seed: str = "",
    ) -> Rendered:
        """The panel's image and the app's preview; a render made ahead of
        time (``Player.render_ahead``) with the same inputs is reused."""
        palette = self.palette
        images = image if isinstance(image, list) else [image]
        key = render_key(
            images,
            settings.model_dump_json(),
            repr(palette),
            fmt or "",
            seed if isinstance(image, list) else "",
        )

        def make() -> Rendered:
            if isinstance(image, list):
                result = render_multi(image, settings, palette, seed=seed)
            else:
                result = render(image, settings, palette)
            data, ext = result.encode(fmt)  # type: ignore[arg-type]
            preview = result.original_image()  # the app shows the picture, not the dither
            preview.thumbnail((PREVIEW_MAX, PREVIEW_MAX))
            return Rendered(data, ext, encode_image(preview, "png"))

        return self.rendered.get(key, make)

    async def push_current(self, wait: float = 90.0) -> PushOutcome:
        """The frame's app asks for its pictures (panel_app.py): awake (on the
        charger) it does within seconds; asleep with the Wi-Fi on, Wake-on-LAN
        makes it ask, unless its alarm rings for this very change, and a
        panel up with its app not running gets the app started over MDC; in
        deep sleep the picture waits for the alarm or the button. A panel that does not run the
        app gets it installed and started first."""
        content = self.store.current()
        if content is None:
            raise RuntimeError("nothing published yet")
        url = f"{self.settings.base_url()}{self.app.image_path(content)}"
        app, power, progress = self.app, self.power, self.progress
        if not progress.active:
            progress.begin(content.title, render=False, origin=self.player.state.last_change_origin)
        progress.advance(Stage.SENDING)
        file_id = content.file_id
        now = datetime.now(UTC)
        wake = app.wakes_at()
        ringing = wake is not None and abs(wake - now) < WAKE_SOON
        self.store.expect_fetch(file_id)
        timeout = 0.0
        if not app.active and app.ensure_package() is None:
            # Nothing to install: the Samsung certificates are not here yet.
            self.store.cancel_fetch(file_id)
            power.mark_pending(True)
            message = NO_CERTIFICATES
            progress.finish(Stage.WAITING, message)
            return PushOutcome(
                content, pushed=False, fetched=False, content_url=url, message=message
            )
        try:
            if not app.active:
                await app.install()  # wakes the panel if need be
                timeout = max(wait, INSTALL_LOOK.total_seconds())
            elif app.awake():
                timeout = max(wait, POLL.total_seconds() + 30)
            elif ringing:
                assert wake is not None
                timeout = max(wait, (wake - now).total_seconds() + 120)
            elif not app.deep_asleep():
                # Wake-on-LAN until the app asks; a panel that is up (the
                # button) with its app not running gets the app started over
                # MDC (the launcher seldom does after a cold boot). Without a
                # MAC address only a panel up already.
                mac = bool(self.settings.device_mac)
                if mac or await app.panel_answers():
                    progress.advance(Stage.WAKING)
                    woke, _ = await power.reach(wol=mac)
                    timeout = wait if woke else 0.0
            fetched = await self.store.wait_for_fetch(file_id, timeout) if timeout else False
        except MdcError as err:
            log.info("could not start the frame's app for a picture: %s", err)
            fetched = False
        finally:
            self.store.cancel_fetch(file_id)
        self.status.note_push(fetched)
        if fetched:
            power.mark_pending(False)
            progress.advance(Stage.DOWNLOADING)
            app.follow(file_id)  # refreshing once the app has it all
            return PushOutcome(content, pushed=True, fetched=True, content_url=url)
        power.mark_pending(True)
        wake = app.wakes_at()
        when = wake.astimezone(self.player.settings.tz()).strftime("%H:%M") if wake else None
        message = (
            f"the frame asks for it at {when}" if when else "the frame asks for it when it wakes"
        )
        progress.finish(Stage.WAITING, message)
        return PushOutcome(content, pushed=False, fetched=False, content_url=url, message=message)

    def ensure_initial_content(self) -> None:
        """Publish a placeholder so the panel's URL never 404s on a fresh install."""
        if self.store.current() is not None:
            return
        from .imaging.testchart import welcome_card

        img = welcome_card()
        self.store.publish(
            encode_image(img, "png"),
            "png",
            preview_png=encode_image(img.resize((1280, 720)), "png"),
            title="Frame",
            description="Placeholder shown until the first image is sent.",
            source="frame",
        )


def outcome_json(outcome: PushOutcome) -> dict[str, object]:
    return {
        "content": asdict(outcome.content),
        "pushed": outcome.pushed,
        "fetched": outcome.fetched,
        "content_url": outcome.content_url,
        "message": outcome.message,
    }
