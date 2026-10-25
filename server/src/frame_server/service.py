"""Application services: render + publish content, drive the panel."""

from __future__ import annotations

import asyncio
import io
import logging
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image

from .config import Settings
from .device import MdcClient, MdcConnectionError, wol
from .imaging import Palette, RenderSettings, get_palette, render, render_multi
from .imaging.pipeline import encode_image
from .library import ImageCache, Importer, Job, Library
from .library.icloud import sync_album
from .library.museums import client as museum_client
from .player import Player
from .status import StatusMonitor
from .store import ContentInfo, ContentStore

log = logging.getLogger(__name__)

PREVIEW_MAX = 1280


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

    def client(self) -> MdcClient:
        host, pin = self.settings.require_device()
        return MdcClient(host, pin, self.settings.device_port)

    async def wake(self) -> bool:
        if not self.settings.device_mac:
            return False
        await wol.wake(self.settings.device_mac, self.settings.device_host)
        return True

    async def set_content_url(self, url: str) -> None:
        async with self._lock:
            client = self.client()
            try:
                await client.connect(attempts=2, retry_delay=5)
            except MdcConnectionError:
                if not await self.wake():
                    raise
                log.info("panel unreachable, sent Wake-on-LAN")
                await asyncio.sleep(15)
                await client.connect(attempts=4, retry_delay=8)
            try:
                await client.content_download(url)
            finally:
                await client.close()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[MdcClient]:
        """One short MDC session, never overlapping with another."""
        async with self._lock, self.client() as mdc:
            yield mdc

    async def sleep(self) -> None:
        """Power off but keep network standby, so Wake-on-LAN still works."""
        async with self._lock, self.client() as mdc:
            await mdc.set_network_standby(True)
            await mdc.set_power(False)


class FrameService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = ContentStore(settings.data_dir)
        self.panel = Panel(settings)
        self.palette: Palette = self._initial_palette()
        self.library = Library(settings.data_dir / "library.db")
        self.images = ImageCache(settings.data_dir / "library", museum_client)
        self.importer = Importer(
            self.library,
            self.images,
            self.palette,
            private_use=lambda: self.player.settings.private_use,
        )
        self.status = StatusMonitor(self.panel)
        self.player = Player(self)

        self._tasks: set[asyncio.Task[object]] = set()

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

    def start_album_sync(self) -> Job:
        """Mirror the shared iCloud album (one sync at a time)."""
        for job in self.importer.jobs.values():
            if job.description == "album" and not job.finished:
                return job
        url = self.player.settings.album_url

        def work(job: Job) -> None:
            sync_album(self.importer, url, job)

        return self.importer.start_job("album", work)

    def background(self, coro: Coroutine[object, object, object]) -> asyncio.Task[object]:
        """Run a coroutine after the response; keeps a reference until done."""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def content_url(self, file_id: str) -> str:
        # The query only changes the URL per push; the server ignores it.
        return f"{self.settings.base_url()}/panel/content.json?v={file_id}"

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
        if isinstance(image, list):
            result = render_multi(image, settings, self.palette, seed=seed)
        else:
            result = render(image, settings, self.palette)
        data, ext = result.encode(fmt)  # type: ignore[arg-type]
        preview = result.original_image()  # the app shows the picture, not the dither
        preview.thumbnail((PREVIEW_MAX, PREVIEW_MAX))
        return self.store.publish(
            data,
            ext,
            preview_png=encode_image(preview, "png"),
            title=title,
            description=description,
            source=source,
            render=settings.model_dump(mode="json") | {"palette": self.palette.name},
            extra=extra,
        )

    async def push_current(self, wait: float = 90.0) -> PushOutcome:
        content = self.store.current()
        if content is None:
            raise RuntimeError("nothing published yet")
        url = self.content_url(content.file_id)
        if wait:
            self.store.expect_fetch(content.file_id)
        try:
            await self.panel.set_content_url(url)
        except BaseException:
            self.store.cancel_fetch(content.file_id)
            raise
        fetched = await self.store.wait_for_fetch(content.file_id, wait) if wait else False
        self.status.note_push(fetched)
        message = "" if fetched or not wait else "panel did not download the image in time"
        return PushOutcome(content, pushed=True, fetched=fetched, content_url=url, message=message)

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
